"""Offline text-to-speech for Karina replies."""

from __future__ import annotations

import threading
from typing import Optional

from config import get_settings

try:
    import pyttsx3
except ImportError:  # pragma: no cover
    pyttsx3 = None

_lock = threading.Lock()
_engine = None


def is_tts_available() -> tuple[bool, str]:
    if pyttsx3 is None:
        return False, "Text-to-speech requires pyttsx3. Install with `pip install pyttsx3`."
    return True, "Text-to-speech is ready."


def _get_engine():
    global _engine
    if _engine is None and pyttsx3 is not None:
        _engine = pyttsx3.init()
        _engine.setProperty("rate", 185)
    return _engine


def speak(text: str) -> None:
    """Speak text in the background if TTS is enabled."""
    if not text or not get_settings().tts_enabled:
        return
    if pyttsx3 is None:
        return

    snippet = text.strip()
    if len(snippet) > 400:
        snippet = snippet[:400] + "..."

    def worker() -> None:
        with _lock:
            try:
                engine = _get_engine()
                if engine is None:
                    return
                engine.say(snippet)
                engine.runAndWait()
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()
