"""Karina desktop helper: open Windows applications by friendly name."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Dict, Optional, Tuple

from fuzzy_match import find_fuzzy_matches, resolve_fuzzy_match

KNOWN_APPS: Dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "explorer": "explorer.exe",
    "edge": "msedge.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "vlc": "vlc.exe",
    "visual studio code": "code.exe",
    "code": "code.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "spotify": "spotify.exe",
}

COMMON_PATHS = [
    os.path.expandvars(r"%ProgramFiles%"),
    os.path.expandvars(r"%ProgramFiles(x86)%"),
    os.path.expandvars(r"%LocalAppData%"),
    os.path.expandvars(r"%ProgramW6432%"),
]

SEARCH_NAMES: Dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "firefox": "firefox.exe",
    "vlc": "vlc.exe",
    "code": "code.cmd",
    "visual studio code": "code.cmd",
}


def find_executable(command: str) -> Optional[str]:
    """Return an executable path if available on PATH or known install locations."""
    resolved = shutil.which(command)
    if resolved:
        return resolved

    for base in COMMON_PATHS:
        if not base:
            continue
        candidate = os.path.join(base, command)
        if os.path.isfile(candidate):
            return candidate

    return None


def resolve_known_app(app_name: str) -> Tuple[Optional[str], Optional[str]]:
    """Fuzzy-match app_name against KNOWN_APPS keys."""
    keys = list(KNOWN_APPS.keys())
    match, error = resolve_fuzzy_match(app_name, keys)
    if error:
        return None, error
    return match.item, None


def build_launch_command(app_name: str) -> Tuple[Optional[str], Optional[str]]:
    """Build a command string to launch the requested app."""
    app_key = app_name.strip().lower()

    if app_key in KNOWN_APPS:
        command = KNOWN_APPS[app_key]
        exe = find_executable(command)
        if exe:
            return exe, None
        return command, None

    resolved_key, error = resolve_known_app(app_name)
    if resolved_key:
        command = KNOWN_APPS[resolved_key]
        exe = find_executable(command)
        if exe:
            return exe, None
        return command, None

    if error:
        return None, error

    if app_key.endswith(".exe"):
        exe = find_executable(app_key)
        if exe:
            return exe, None
        return app_key, None

    return None, None


def open_app(app_name: str) -> str:
    """Open an app by friendly name and return a status message."""
    if sys.platform != "win32":
        return "Karina currently supports Windows application launch only."

    launch_cmd, error = build_launch_command(app_name)
    if error:
        return error
    if not launch_cmd:
        near_misses = [f"'{match.label}'" for match in find_fuzzy_matches(app_name, list(KNOWN_APPS.keys()))[:3]]
        suggestion = f" Did you mean: {', '.join(near_misses)}?" if near_misses else ""
        return (
            f"I don't know how to open '{app_name}'.{suggestion} "
            "Try a common app name like notepad, chrome, edge, firefox, or vlc."
        )

    try:
        subprocess.Popen([launch_cmd], shell=False)
        return f"Opening {app_name} now."
    except FileNotFoundError:
        return f"Could not locate the executable for '{app_name}'."
    except Exception as exc:
        return f"Failed to open '{app_name}': {exc}"


def list_supported_apps() -> str:
    """Return a human-readable list of supported application names."""
    return ", ".join(sorted(KNOWN_APPS.keys()))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Karina helper to open desktop apps.")
    parser.add_argument("app", nargs="*", help="The app name to open.")
    parser.add_argument("--list", action="store_true", help="List supported app names.")
    args = parser.parse_args()

    if args.list:
        print("Supported apps:")
        print(list_supported_apps())
        return 0

    if not args.app:
        print("Usage: python open_app.py <app name>\nUse --list to see supported apps.")
        return 1

    app_name = " ".join(args.app)
    result = open_app(app_name)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
