"""Shared core logic for Karina desktop commands."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from audio import get_current_audio_device, list_audio_devices, select_audio_device
from browse_files import list_folder, open_path
from camera import take_snapshot
from open_app import list_supported_apps, open_app
from command_registry import get_registry
from llm import chat as llm_chat, llm_status
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

OPEN_PATTERNS = [
    r"open\s+(.+)",
    r"launch\s+(.+)",
    r"run\s+(.+)",
    r"start\s+(.+)",
    r"please open\s+(.+)",
    r"please launch\s+(.+)",
]

LIST_FOLDER_PATTERNS = [
    r"(?:list|show|browse)\s+(?:files|folder|folders|directory|directories)(?:\s+in\s+(.+))?",
    r"(?:show|list)\s+(.+)\s+files",
]

OPEN_PATH_PATTERNS = [
    r"open\s+(?:file|folder|path)\s+(.+)",
    r"open\s+(.+\.(?:txt|pdf|docx|xlsx|pptx|jpg|png|mp4|mp3))",
]

SNAPSHOT_PATTERNS = [
    r"(?:take|capture|snap)(?: a)?(?: photo| picture| snapshot)(?: with camera)?",
    r"(?:camera|webcam)\s*(?:snapshot|photo|picture)",
]

LIST_AUDIO_PATTERNS = [
    r"(?:list|show)\s+(?:audio|sound)\s+(?:devices|outputs|inputs)",
    r"(?:what|which)\s+(?:audio|sound)\s+(?:devices|outputs|inputs)\b",
    r"current\s+(?:audio|sound)\s+device",
]

SELECT_AUDIO_PATTERNS = [
    r"(?:select|choose|set)\s+(?:audio|sound)\s+(?:device|output|input)\s+(.+)",
    r"(?:use|switch to)\s+(.+)\s+(?:audio|sound)\s+(?:device|output|input)",
    r"(?:set|choose|select)\s+(.+)\s+as\s+(?:audio|sound)\s+(?:device|output|input)",
]

CLOSE_PATTERNS = [
    r"(?:close|exit|quit|shutdown|shut down|terminate|stop)(?:\s+karina|\s+the app|\s+the chat|\s+this)?",
    r".*(?:i want to close|i'm done|i am done|stop now|end this session|close this).*",
]

LIST_WINDOWS_PATTERNS = [
    r"(?:list|show)\s+(?:open\s+)?windows?",
]

LIST_MONITORS_PATTERNS = [
    r"(?:list|show)\s+monitors?",
]

MOVE_MONITOR_PATTERNS = [
    r"move\s+(.+?)\s+to\s+monitor\s+(\d+)",
    r"move\s+(?:window\s+)?(.+?)\s+to\s+(?:screen|display)\s+(\d+)",
]

MAXIMIZE_PATTERNS = [
    r"maximize\s+(?:window\s+)?(.+)",
]

MINIMIZE_PATTERNS = [
    r"minimize\s+(?:window\s+)?(.+)",
]

RESTORE_PATTERNS = [
    r"restore\s+(?:window\s+)?(.+)",
]

FOCUS_PATTERNS = [
    r"focus\s+(?:window\s+)?(.+)",
    r"bring\s+(.+?)\s+to\s+(?:the\s+)?front",
    r"switch\s+to\s+(.+)",
]

SNAP_PATTERNS = [
    r"snap\s+(.+?)\s+to\s+(?:the\s+)?(left|right|top|bottom)",
    r"snap\s+(.+?)\s+(left|right|top|bottom)",
]

CLOSE_WINDOW_PATTERNS = [
    r"close\s+window\s+(.+)",
    r"close\s+(.+?)\s+window",
]


@dataclass
class KarinaResponse:
    text: str
    should_close: bool = False


@dataclass
class KarinaSession:
    history: list[dict[str, Any]] = field(default_factory=list)


_default_session = KarinaSession()


def get_session() -> KarinaSession:
    return _default_session


def parse_app_command(text: str) -> Optional[str]:
    cleaned = text.strip().lower()
    for pattern in OPEN_PATTERNS:
        match = re.match(pattern, cleaned)
        if match:
            return match.group(1).strip()
    return None


def parse_folder_command(text: str) -> Optional[str]:
    cleaned = text.strip().lower()
    for pattern in LIST_FOLDER_PATTERNS:
        match = re.match(pattern, cleaned)
        if not match:
            continue
        folder = match.group(1)
        if folder:
            return folder.strip()
        return "."
    return None


def parse_open_path_command(text: str) -> Optional[str]:
    cleaned = text.strip().lower()
    for pattern in OPEN_PATH_PATTERNS:
        match = re.match(pattern, cleaned)
        if match:
            return match.group(1).strip()
    return None


def parse_snapshot_command(text: str) -> bool:
    cleaned = text.strip().lower()
    return any(re.match(pattern, cleaned) for pattern in SNAPSHOT_PATTERNS)


def parse_list_audio_command(text: str) -> bool:
    cleaned = text.strip().lower()
    return any(re.match(pattern, cleaned) for pattern in LIST_AUDIO_PATTERNS)


def parse_select_audio_command(text: str) -> Optional[str]:
    cleaned = text.strip().lower()
    for pattern in SELECT_AUDIO_PATTERNS:
        match = re.match(pattern, cleaned)
        if match:
            return match.group(1).strip()
    return None


def parse_close_command(text: str) -> bool:
    cleaned = text.strip().lower()
    if cleaned in {"exit", "quit", "bye", "goodbye"}:
        return True

    if parse_close_window_command(text):
        return False

    if any(re.match(pattern, cleaned) for pattern in CLOSE_PATTERNS):
        return True

    if "close" in cleaned and any(word in cleaned for word in ["program", "app", "karina", "chat", "assistant"]):
        return True

    if cleaned in {"close", "close karina", "close the app", "close the chat"}:
        return True

    return False


def parse_list_windows_command(text: str) -> bool:
    cleaned = text.strip().lower()
    return any(re.match(pattern, cleaned) for pattern in LIST_WINDOWS_PATTERNS)


def parse_list_monitors_command(text: str) -> bool:
    cleaned = text.strip().lower()
    return any(re.match(pattern, cleaned) for pattern in LIST_MONITORS_PATTERNS)


def parse_move_monitor_command(text: str) -> Optional[tuple[str, int]]:
    cleaned = text.strip().lower()
    for pattern in MOVE_MONITOR_PATTERNS:
        match = re.match(pattern, cleaned)
        if match:
            return match.group(1).strip(), int(match.group(2))
    return None


def parse_maximize_command(text: str) -> Optional[str]:
    cleaned = text.strip().lower()
    for pattern in MAXIMIZE_PATTERNS:
        match = re.match(pattern, cleaned)
        if match:
            return match.group(1).strip()
    return None


def parse_minimize_command(text: str) -> Optional[str]:
    cleaned = text.strip().lower()
    for pattern in MINIMIZE_PATTERNS:
        match = re.match(pattern, cleaned)
        if match:
            return match.group(1).strip()
    return None


def parse_restore_command(text: str) -> Optional[str]:
    cleaned = text.strip().lower()
    for pattern in RESTORE_PATTERNS:
        match = re.match(pattern, cleaned)
        if match:
            return match.group(1).strip()
    return None


def parse_focus_command(text: str) -> Optional[str]:
    cleaned = text.strip().lower()
    for pattern in FOCUS_PATTERNS:
        match = re.match(pattern, cleaned)
        if match:
            return match.group(1).strip()
    return None


def parse_snap_command(text: str) -> Optional[tuple[str, str]]:
    cleaned = text.strip().lower()
    for pattern in SNAP_PATTERNS:
        match = re.match(pattern, cleaned)
        if match:
            return match.group(1).strip(), match.group(2).strip()
    return None


def parse_close_window_command(text: str) -> Optional[str]:
    cleaned = text.strip().lower()
    for pattern in CLOSE_WINDOW_PATTERNS:
        match = re.match(pattern, cleaned)
        if match:
            return match.group(1).strip()
    return None


def try_parsed_command(text: str) -> Optional[KarinaResponse]:
    lowered = text.strip().lower()
    if not lowered:
        return KarinaResponse("Please type a command.")

    if parse_close_command(text):
        return KarinaResponse("Okay, closing Karina now. Goodbye!", should_close=True)

    if lowered in {"help", "commands"}:
        plugin_help = ""
        plugin_lines = get_registry().help_lines()
        if plugin_lines:
            plugin_help = "\nPlugin commands:\n" + "\n".join(plugin_lines)
        return KarinaResponse(
            "Commands:\n"
            "  open <app>                  - open an application\n"
            "  list apps                   - show supported app names\n"
            "  list audio devices          - show available sound devices\n"
            "  current audio device        - show the currently selected device\n"
            "  select audio device <name>  - choose an audio device\n"
            "  list windows                - show open windows\n"
            "  list monitors               - show connected monitors\n"
            "  focus <window>              - bring a window to the front\n"
            "  maximize / minimize / restore <window>\n"
            "  move <window> to monitor <n> - move window to a monitor\n"
            "  snap <window> to left|right|top|bottom\n"
            "  close window <name>         - close a specific window\n"
            "  take a snapshot             - capture a webcam photo\n"
            "  list files in <folder>      - show folder contents\n"
            "  open file <path>            - open a file or folder\n"
            "  llm status                  - check the local language model\n"
            "  close / exit                - close Karina\n"
            "Free-form questions use a local LLM. Karina starts Ollama and downloads llama3.2 on first launch if needed."
            f"{plugin_help}"
        )

    plugin_result = get_registry().try_handle(text)
    if plugin_result is not None:
        return KarinaResponse(plugin_result)

    if lowered in {"llm status", "llm", "model status"}:
        return KarinaResponse(llm_status())

    if lowered in {"list apps", "supported apps", "apps"}:
        return KarinaResponse(f"Supported apps: {list_supported_apps()}")

    if "current audio device" in lowered:
        return KarinaResponse(get_current_audio_device())

    if parse_list_audio_command(text):
        return KarinaResponse(list_audio_devices())

    select_audio = parse_select_audio_command(text)
    if select_audio:
        return KarinaResponse(select_audio_device(select_audio))

    if parse_snapshot_command(text):
        return KarinaResponse(take_snapshot())

    if parse_list_windows_command(text):
        return KarinaResponse(list_windows())

    if parse_list_monitors_command(text):
        return KarinaResponse(list_monitors())

    move_monitor = parse_move_monitor_command(text)
    if move_monitor:
        window_name, monitor_number = move_monitor
        return KarinaResponse(move_window_to_monitor(window_name, monitor_number))

    maximize_target = parse_maximize_command(text)
    if maximize_target:
        return KarinaResponse(maximize_window(maximize_target))

    minimize_target = parse_minimize_command(text)
    if minimize_target:
        return KarinaResponse(minimize_window(minimize_target))

    restore_target = parse_restore_command(text)
    if restore_target:
        return KarinaResponse(restore_window(restore_target))

    focus_target = parse_focus_command(text)
    if focus_target:
        return KarinaResponse(focus_window(focus_target))

    snap_target = parse_snap_command(text)
    if snap_target:
        window_name, side = snap_target
        return KarinaResponse(snap_window(window_name, side))

    close_window_target = parse_close_window_command(text)
    if close_window_target:
        return KarinaResponse(close_window(close_window_target))

    folder_path = parse_folder_command(text)
    if folder_path:
        return KarinaResponse(list_folder(folder_path))

    open_path_result = parse_open_path_command(text)
    if open_path_result:
        return KarinaResponse(open_path(open_path_result))

    app_name = parse_app_command(text)
    if app_name:
        return KarinaResponse(open_app(app_name))

    if "list files" in lowered or "show files" in lowered or "browse folder" in lowered:
        cwd = os.getcwd()
        return KarinaResponse(f"Try 'list files in <folder>' or 'browse folder <folder>'. Current folder: {cwd}")

    if "snapshot" in lowered or "photo" in lowered or "picture" in lowered:
        return KarinaResponse("Try 'take a snapshot' or 'capture a photo' to use the camera.")

    return None


def get_response(text: str, session: Optional[KarinaSession] = None) -> KarinaResponse:
    parsed = try_parsed_command(text)
    if parsed is not None:
        return parsed

    active_session = session or get_session()
    reply = llm_chat(text, active_session.history)
    return KarinaResponse(reply.text, should_close=reply.should_close)
