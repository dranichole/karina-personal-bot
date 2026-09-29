"""Start Ollama and pull the default model from inside Karina."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

ProgressFn = Callable[[str], None]

DEFAULT_MODEL = os.environ.get("KARINA_LLM_MODEL", "llama3.2").strip() or "llama3.2"
OLLAMA_API = "http://127.0.0.1:11434/v1"
CREATE_NO_WINDOW = 0x08000000
INSTALL_URL = "https://ollama.com/download"


def _notify(progress: Optional[ProgressFn], message: str) -> None:
    if progress:
        progress(message)


def find_ollama() -> Optional[str]:
    resolved = shutil.which("ollama")
    if resolved:
        return resolved

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Ollama" / "ollama.exe",
        Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _ollama_running() -> bool:
    try:
        import urllib.request

        urllib.request.urlopen(f"{OLLAMA_API}/models", timeout=1).read()
        return True
    except Exception:
        return False


def _run_hidden(command: list[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess[str]:
    kwargs: dict = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(command, **kwargs)


def start_ollama_serve(ollama_exe: str, progress: Optional[ProgressFn] = None) -> bool:
    if _ollama_running():
        return True

    _notify(progress, "Starting Ollama...")
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    subprocess.Popen([ollama_exe, "serve"], **kwargs)

    for _ in range(30):
        if _ollama_running():
            return True
        time.sleep(1)
    return _ollama_running()


def _model_installed(ollama_exe: str, model: str) -> bool:
    result = _run_hidden([ollama_exe, "list"], timeout=15)
    if result.returncode != 0:
        return False
    lines = (result.stdout or "").splitlines()
    needle = model.lower()
    for line in lines[1:]:
        name = line.split()[0].lower() if line.split() else ""
        if name == needle or name.startswith(f"{needle}:"):
            return True
    return False


def pull_model(ollama_exe: str, model: str, progress: Optional[ProgressFn] = None) -> tuple[bool, str]:
    if _model_installed(ollama_exe, model):
        return True, f"Model {model} is already installed."

    _notify(progress, f"Downloading {model}. This can take several minutes on first launch...")
    kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NO_WINDOW

    try:
        process = subprocess.Popen([ollama_exe, "pull", model], **kwargs)
    except Exception as exc:
        return False, f"Could not start model download: {exc}"

    last_line = ""
    assert process.stdout is not None
    try:
        for line in process.stdout:
            last_line = line.strip()
            if last_line:
                _notify(progress, last_line)
    except UnicodeDecodeError:
        pass

    code = process.wait()
    if code != 0:
        return False, f"Failed to download {model}. {last_line}".strip()
    return True, f"Downloaded {model}."


def bootstrap_ollama(progress: Optional[ProgressFn] = None) -> tuple[bool, str]:
    """Start Ollama and ensure the default model exists."""
    ollama_exe = find_ollama()
    if ollama_exe is None:
        return (
            False,
            "Ollama is not installed. Karina can still run commands, but chat needs Ollama. "
            f"Install it from {INSTALL_URL}, then restart Karina. "
            "The app will start the server and download the model automatically.",
        )

    if not start_ollama_serve(ollama_exe, progress):
        return False, "Found Ollama but could not start its server."

    ok, message = pull_model(ollama_exe, DEFAULT_MODEL, progress)
    if not ok:
        return False, message

    _notify(progress, f"Local model ready: {DEFAULT_MODEL}")
    return True, f"Ollama is running with {DEFAULT_MODEL}."


def model_is_tool_capable(name: str) -> bool:
    lowered = name.lower()
    blocked = ("neural-chat", "orca-mini", "tinyllama", "gemma:2b", "phi:")
    return not any(marker in lowered for marker in blocked)
