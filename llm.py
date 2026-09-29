"""Local LLM client for Karina (Ollama / LM Studio, OpenAI-compatible)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional

from audio import get_current_audio_device, list_audio_devices, select_audio_device
from browse_files import list_folder, open_path
from camera import take_snapshot
from ollama_runtime import DEFAULT_MODEL, bootstrap_ollama, model_is_tool_capable
from open_app import list_supported_apps, open_app
from window_manager import (
    close_window,
    focus_window,
    list_monitors,
    list_windows,
    maximize_window,
    minimize_window,
    move_window_to_monitor,
    restore_window,
    snap_window,
)

DEFAULT_ENDPOINTS = (
    "http://127.0.0.1:11434/v1",
    "http://127.0.0.1:1234/v1",
)
MAX_TOOL_ROUNDS = 5
REQUEST_TIMEOUT = 120

SYSTEM_PROMPT = (
    "You are Karina, a local offline personal desktop assistant. "
    "You help with apps, files, audio devices, the webcam, and window management. "
    "Use tools for any desktop action instead of guessing results. "
    "If a request is ambiguous, ask a short clarifying question. "
    "Keep answers concise."
)


@dataclass
class ToolResult:
    text: str
    should_close: bool = False


@dataclass
class LlmReply:
    text: str
    should_close: bool = False
    used_llm: bool = True


@dataclass
class LlmConfig:
    base_url: str
    model: str
    api_key: str = "karina"


_cached_config: Optional[LlmConfig] = None


def reset_llm_cache() -> None:
    global _cached_config
    _cached_config = None


def _env_base_url() -> Optional[str]:
    value = os.environ.get("KARINA_LLM_BASE_URL", "").strip().rstrip("/")
    return value or None


def _json_request(
    url: str,
    payload: Optional[dict[str, Any]] = None,
    api_key: str = "karina",
    timeout: int = 8,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _list_models(base_url: str, api_key: str) -> list[str]:
    data = _json_request(f"{base_url}/models", api_key=api_key, timeout=1)
    models = data.get("data") or []
    names: list[str] = []
    for item in models:
        name = item.get("id") if isinstance(item, dict) else None
        if name:
            names.append(name)
    return names


def _pick_model(models: list[str], preferred_model: str) -> Optional[str]:
    preferred_lower = preferred_model.lower()
    for name in models:
        if name.lower() == preferred_lower or name.lower().startswith(f"{preferred_lower}:"):
            return name

    preferred_families = (
        "llama3.2",
        "llama3.1",
        "llama3",
        "qwen2.5",
        "mistral",
        "phi4",
        "gemma2",
    )
    for family in preferred_families:
        for name in models:
            if name.lower().startswith(family) and model_is_tool_capable(name):
                return name

    for name in models:
        if model_is_tool_capable(name):
            return name
    return None


def discover_llm() -> tuple[Optional[LlmConfig], str]:
    """Find a local OpenAI-compatible server. Returns (config, status)."""
    global _cached_config
    if _cached_config is not None:
        return _cached_config, f"Using {_cached_config.model} at {_cached_config.base_url}"

    api_key = os.environ.get("KARINA_LLM_API_KEY", "karina")
    preferred_model = os.environ.get("KARINA_LLM_MODEL", "").strip() or DEFAULT_MODEL
    candidates = []
    env_url = _env_base_url()
    if env_url:
        candidates.append(env_url)
    candidates.extend(DEFAULT_ENDPOINTS)

    last_error = "No local LLM server found."
    found_unsupported = None
    for base_url in dict.fromkeys(candidates):
        try:
            models = _list_models(base_url, api_key)
        except Exception:
            last_error = f"Could not reach {base_url}."
            continue

        if not models:
            last_error = f"{base_url} is running but has no models loaded."
            continue

        model = _pick_model(models, preferred_model)
        if model is None:
            found_unsupported = models[0]
            last_error = (
                f"Found {found_unsupported}, which cannot use Karina tools. "
                f"Need {preferred_model} (or another tool-capable model)."
            )
            continue

        _cached_config = LlmConfig(base_url=base_url, model=model, api_key=api_key)
        return _cached_config, f"Using {model} at {base_url}"

    return None, (
        f"{last_error} Karina will try to start Ollama automatically. "
        "Known commands still work without an LLM."
    )


def ensure_local_llm(progress: Optional[Callable[[str], None]] = None) -> tuple[bool, str]:
    """Use a tool-capable local model, otherwise start Ollama and pull the default model."""
    reset_llm_cache()
    config, status = discover_llm()
    preferred = os.environ.get("KARINA_LLM_MODEL", "").strip() or DEFAULT_MODEL
    if config is not None and (
        config.model.lower().startswith(preferred.lower()) or model_is_tool_capable(config.model)
    ):
        if config.model.lower().startswith(preferred.lower()):
            return True, status

    try:
        ok, message = bootstrap_ollama(progress=progress)
    except Exception as exc:
        ok, message = False, f"Could not prepare Ollama: {exc}"
    reset_llm_cache()
    config, status = discover_llm()
    if config is not None:
        return True, status
    if ok:
        return True, message
    return False, message or status


def is_llm_available() -> tuple[bool, str]:
    config, status = discover_llm()
    return config is not None, status


def llm_status() -> str:
    available, status = is_llm_available()
    prefix = "Local LLM is ready." if available else "Local LLM is not available."
    return f"{prefix} {status}"


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open a Windows application by friendly name.",
            "parameters": {
                "type": "object",
                "properties": {"app_name": {"type": "string"}},
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_apps",
            "description": "List applications Karina knows how to launch.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_audio_devices",
            "description": "List available audio input and output devices.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_audio_device",
            "description": "Show the currently selected audio device.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_audio_device",
            "description": "Select an audio device by name or index. Fuzzy matching is supported.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_snapshot",
            "description": "Capture a photo from the webcam.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_folder",
            "description": "List files in a folder path.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_path",
            "description": "Open a file or folder in the default application.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_windows",
            "description": "List currently open desktop windows.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_monitors",
            "description": "List connected monitors.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "focus_window",
            "description": "Bring a window to the front by title.",
            "parameters": {
                "type": "object",
                "properties": {"window": {"type": "string"}},
                "required": ["window"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "maximize_window",
            "parameters": {
                "type": "object",
                "properties": {"window": {"type": "string"}},
                "required": ["window"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "minimize_window",
            "parameters": {
                "type": "object",
                "properties": {"window": {"type": "string"}},
                "required": ["window"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restore_window",
            "parameters": {
                "type": "object",
                "properties": {"window": {"type": "string"}},
                "required": ["window"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_window_to_monitor",
            "description": "Move a window to a monitor number (1-based).",
            "parameters": {
                "type": "object",
                "properties": {
                    "window": {"type": "string"},
                    "monitor": {"type": "integer"},
                },
                "required": ["window", "monitor"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "snap_window",
            "description": "Snap a window to left, right, top, or bottom of its monitor.",
            "parameters": {
                "type": "object",
                "properties": {
                    "window": {"type": "string"},
                    "side": {"type": "string", "enum": ["left", "right", "top", "bottom"]},
                },
                "required": ["window", "side"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_window",
            "description": "Close a specific window by title. Do not use this to quit Karina.",
            "parameters": {
                "type": "object",
                "properties": {"window": {"type": "string"}},
                "required": ["window"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_karina",
            "description": "Quit the Karina assistant when the user wants to end the session.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _run_tool(name: str, arguments: dict[str, Any]) -> ToolResult:
    handlers: dict[str, Callable[[], ToolResult]] = {
        "open_app": lambda: ToolResult(open_app(str(arguments.get("app_name", "")))),
        "list_apps": lambda: ToolResult(f"Supported apps: {list_supported_apps()}"),
        "list_audio_devices": lambda: ToolResult(list_audio_devices()),
        "get_current_audio_device": lambda: ToolResult(get_current_audio_device()),
        "select_audio_device": lambda: ToolResult(select_audio_device(str(arguments.get("name", "")))),
        "take_snapshot": lambda: ToolResult(take_snapshot()),
        "list_folder": lambda: ToolResult(list_folder(str(arguments.get("path", ".")))),
        "open_path": lambda: ToolResult(open_path(str(arguments.get("path", "")))),
        "list_windows": lambda: ToolResult(list_windows()),
        "list_monitors": lambda: ToolResult(list_monitors()),
        "focus_window": lambda: ToolResult(focus_window(str(arguments.get("window", "")))),
        "maximize_window": lambda: ToolResult(maximize_window(str(arguments.get("window", "")))),
        "minimize_window": lambda: ToolResult(minimize_window(str(arguments.get("window", "")))),
        "restore_window": lambda: ToolResult(restore_window(str(arguments.get("window", "")))),
        "move_window_to_monitor": lambda: ToolResult(
            move_window_to_monitor(str(arguments.get("window", "")), int(arguments.get("monitor", 1)))
        ),
        "snap_window": lambda: ToolResult(
            snap_window(str(arguments.get("window", "")), str(arguments.get("side", "left")))
        ),
        "close_window": lambda: ToolResult(close_window(str(arguments.get("window", "")))),
        "close_karina": lambda: ToolResult("Okay, closing Karina now. Goodbye!", should_close=True),
    }
    handler = handlers.get(name)
    if handler is None:
        return ToolResult(f"Unknown tool '{name}'.")
    try:
        return handler()
    except Exception as exc:
        return ToolResult(f"Tool '{name}' failed: {exc}")


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def chat(user_text: str, history: list[dict[str, Any]]) -> LlmReply:
    config, status = discover_llm()
    if config is None:
        return LlmReply(
            "I can still run known commands without a language model. "
            f"{status} Try 'help' for the command list.",
            used_llm=False,
        )

    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-12:])
    messages.append({"role": "user", "content": user_text})

    should_close = False
    last_text = ""
    use_tools = model_is_tool_capable(config.model)

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            payload: dict[str, Any] = {
                "model": config.model,
                "messages": messages,
                "temperature": 0.3,
            }
            if use_tools:
                payload["tools"] = TOOLS
                payload["tool_choice"] = "auto"
            data = _json_request(
                f"{config.base_url}/chat/completions",
                payload=payload,
                api_key=config.api_key,
                timeout=REQUEST_TIMEOUT,
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if use_tools and "does not support tools" in detail.lower():
                use_tools = False
                continue
            return LlmReply(f"Local LLM request failed ({exc.code}): {detail[:400]}")
        except Exception as exc:
            return LlmReply(f"Local LLM request failed: {exc}")

        choices = data.get("choices") or []
        if not choices:
            return LlmReply("The local LLM returned no response.")

        message = choices[0].get("message") or {}
        messages.append(message)
        last_text = (message.get("content") or "").strip()
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            break

        for call in tool_calls:
            function = call.get("function") or {}
            name = function.get("name") or ""
            arguments = _parse_arguments(function.get("arguments"))
            result = _run_tool(name, arguments)
            should_close = should_close or result.should_close
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or name,
                    "name": name,
                    "content": result.text,
                }
            )
            if result.should_close:
                last_text = result.text
                history.append({"role": "user", "content": user_text})
                history.append({"role": "assistant", "content": last_text})
                return LlmReply(last_text, should_close=True)

    if not last_text:
        last_text = "I understood the request but had nothing to say."

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": last_text})
    return LlmReply(last_text, should_close=should_close)
