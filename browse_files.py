"""Karina file browsing helpers."""

from __future__ import annotations

import os
from pathlib import Path


def normalize_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def list_folder(path: str = "") -> str:
    target = normalize_path(path or ".")
    if not os.path.exists(target):
        return f"Path does not exist: {target}"

    if not os.path.isdir(target):
        return f"{target} is not a folder."

    try:
        entries = sorted(os.listdir(target))
    except Exception as exc:
        return f"Could not list folder contents: {exc}"

    if not entries:
        return f"Folder is empty: {target}"

    lines = [f"Contents of {target}:"]
    for entry in entries:
        full_path = os.path.join(target, entry)
        marker = "[DIR]" if os.path.isdir(full_path) else "[FILE]"
        lines.append(f"{marker} {entry}")
    return "\n".join(lines)


def open_path(path: str) -> str:
    target = normalize_path(path)
    if not os.path.exists(target):
        return f"Path does not exist: {target}"

    try:
        os.startfile(target)
        return f"Opened {target}."
    except Exception as exc:
        return f"Could not open {target}: {exc}"
