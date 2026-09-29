"""Resolve project and bundled resource paths for source and frozen builds."""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Directory containing the running app (exe folder or source folder)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundle_root() -> Path:
    """PyInstaller extract dir, or the source/app directory."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return app_root()


def resource_dirs() -> list[Path]:
    dirs = [app_root(), bundle_root()]
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in dirs:
        resolved = path.resolve()
        if resolved not in seen:
            unique.append(resolved)
            seen.add(resolved)
    return unique
