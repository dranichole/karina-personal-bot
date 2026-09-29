"""Persistent Karina settings."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Optional

from paths import app_root

SETTINGS_FILE = "karina_settings.json"


@dataclass
class Settings:
    fuzzy_threshold: float = 0.65
    tts_enabled: bool = True
    wake_word_enabled: bool = False
    confirm_destructive: bool = True
    mic_device_index: Optional[int] = None


_settings: Optional[Settings] = None


def settings_path():
    return app_root() / SETTINGS_FILE


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def load_settings() -> Settings:
    path = settings_path()
    if not path.is_file():
        return Settings()
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return Settings()

    defaults = Settings()
    mic = data.get("mic_device_index", defaults.mic_device_index)
    if mic is not None:
        try:
            mic = int(mic)
        except (TypeError, ValueError):
            mic = None
    threshold = float(data.get("fuzzy_threshold", defaults.fuzzy_threshold))
    threshold = min(0.95, max(0.5, threshold))
    return Settings(
        fuzzy_threshold=threshold,
        tts_enabled=bool(data.get("tts_enabled", defaults.tts_enabled)),
        wake_word_enabled=bool(data.get("wake_word_enabled", defaults.wake_word_enabled)),
        confirm_destructive=bool(data.get("confirm_destructive", defaults.confirm_destructive)),
        mic_device_index=mic,
    )


def save_settings(settings: Settings) -> None:
    global _settings
    _settings = settings
    settings_path().write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
