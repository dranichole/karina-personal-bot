"""System tray icon and global hotkey (Ctrl+Shift+K) to show Karina."""

from __future__ import annotations

import threading
from typing import Callable, Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None
    ImageDraw = None
    ImageFont = None

try:
    import pystray
except ImportError:  # pragma: no cover
    pystray = None


def is_tray_available() -> bool:
    return pystray is not None and Image is not None


def _make_icon() -> "Image.Image":
    image = Image.new("RGBA", (64, 64), (31, 31, 43, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, 60, 60), fill=(74, 108, 255, 255))
    try:
        font = ImageFont.truetype("segoeui.ttf", 32)
    except Exception:
        font = ImageFont.load_default()
    draw.text((20, 12), "K", fill=(255, 255, 255, 255), font=font)
    return image


class TrayController:
    def __init__(self, on_show: Callable[[], None], on_quit: Callable[[], None]) -> None:
        self.on_show = on_show
        self.on_quit = on_quit
        self.icon: Optional["pystray.Icon"] = None

    def start(self) -> bool:
        if not is_tray_available():
            return False

        menu = pystray.Menu(
            pystray.MenuItem("Show Karina", lambda: self.on_show(), default=True),
            pystray.MenuItem("Quit", lambda: self._quit()),
        )
        self.icon = pystray.Icon("Karina", _make_icon(), "Karina Desktop AI", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()
        _start_hotkey_thread(self.on_show)
        return True

    def _quit(self) -> None:
        self.stop()
        self.on_quit()

    def stop(self) -> None:
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None


def _start_hotkey_thread(callback: Callable[[], None]) -> None:
    def worker() -> None:
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            MOD_CONTROL = 0x0002
            MOD_SHIFT = 0x0004
            VK_K = 0x4B
            HOTKEY_ID = 74
            WM_HOTKEY = 0x0312

            if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, VK_K):
                return

            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY:
                    callback()
            user32.UnregisterHotKey(None, HOTKEY_ID)
        except Exception:
            return

    threading.Thread(target=worker, daemon=True).start()
