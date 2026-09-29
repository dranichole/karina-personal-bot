"""Windows window and monitor management for Karina."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from fuzzy_match import resolve_fuzzy_match

try:
    import win32api
    import win32con
    import win32gui
except ImportError:  # pragma: no cover
    win32api = None
    win32con = None
    win32gui = None


@dataclass
class WindowInfo:
    hwnd: int
    title: str


@dataclass
class MonitorInfo:
    index: int
    left: int
    top: int
    right: int
    bottom: int
    is_primary: bool

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def label(self) -> str:
        role = "primary" if self.is_primary else "secondary"
        return (
            f"Monitor {self.index + 1} ({role}, "
            f"{self.width}x{self.height} at {self.left},{self.top})"
        )


def is_window_manager_available() -> bool:
    return sys.platform == "win32" and win32gui is not None


def _require_windows() -> Optional[str]:
    if sys.platform != "win32":
        return "Window management is only supported on Windows."
    if win32gui is None:
        return "Window management requires pywin32. Install with `pip install pywin32`."
    return None


def _is_valid_window(hwnd: int) -> bool:
    if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
        return False
    title = win32gui.GetWindowText(hwnd)
    if not title:
        return False
    if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
        return False
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    if style & win32con.WS_DISABLED:
        return False
    return True


def get_open_windows() -> List[WindowInfo]:
    error = _require_windows()
    if error:
        return []

    windows: List[WindowInfo] = []

    def callback(hwnd: int, _extra) -> bool:
        if _is_valid_window(hwnd):
            windows.append(WindowInfo(hwnd=hwnd, title=win32gui.GetWindowText(hwnd)))
        return True

    win32gui.EnumWindows(callback, None)
    windows.sort(key=lambda window: window.title.lower())
    return windows


def get_monitors() -> List[MonitorInfo]:
    error = _require_windows()
    if error:
        return []

    monitors: List[MonitorInfo] = []
    primary = win32api.GetMonitorInfo(win32api.MonitorFromPoint((0, 0)))["Monitor"]

    for index, (_handle, _device, rect) in enumerate(win32api.EnumDisplayMonitors()):
        left, top, right, bottom = rect
        is_primary = (left, top, right, bottom) == primary
        monitors.append(
            MonitorInfo(
                index=index,
                left=left,
                top=top,
                right=right,
                bottom=bottom,
                is_primary=is_primary,
            )
        )
    return monitors


def list_windows() -> str:
    error = _require_windows()
    if error:
        return error

    windows = get_open_windows()
    if not windows:
        return "No open windows were found."

    lines = ["Open windows:"]
    for index, window in enumerate(windows):
        lines.append(f"  {index}: {window.title}")
    return "\n".join(lines)


def list_monitors() -> str:
    error = _require_windows()
    if error:
        return error

    monitors = get_monitors()
    if not monitors:
        return "No monitors were found."

    lines = ["Monitors:"]
    for monitor in monitors:
        lines.append(f"  {monitor.index + 1}: {monitor.label}")
    return "\n".join(lines)


def _resolve_window(query: str) -> Tuple[Optional[WindowInfo], Optional[str]]:
    windows = get_open_windows()
    if not windows:
        return None, "No open windows were found."

    def label_fn(window: WindowInfo, _index: int) -> str:
        return window.title

    match, error = resolve_fuzzy_match(query, windows, label_fn=label_fn)
    if error:
        return None, error
    return match.item, None


def _resolve_monitor(monitor_number: int) -> Tuple[Optional[MonitorInfo], Optional[str]]:
    monitors = get_monitors()
    if not monitors:
        return None, "No monitors were found."

    index = monitor_number - 1
    if index < 0 or index >= len(monitors):
        valid = ", ".join(str(monitor.index + 1) for monitor in monitors)
        return None, f"Monitor {monitor_number} does not exist. Valid monitors: {valid}."
    return monitors[index], None


def _with_window(query: str, action: Callable[[WindowInfo], str]) -> str:
    error = _require_windows()
    if error:
        return error

    window, resolve_error = _resolve_window(query)
    if resolve_error:
        return resolve_error
    assert window is not None
    return action(window)


def _bring_to_front(hwnd: int) -> None:
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        win32gui.BringWindowToTop(hwnd)


def focus_window(query: str) -> str:
    def action(window: WindowInfo) -> str:
        _bring_to_front(window.hwnd)
        return f"Focused '{window.title}'."

    return _with_window(query, action)


def minimize_window(query: str) -> str:
    def action(window: WindowInfo) -> str:
        win32gui.ShowWindow(window.hwnd, win32con.SW_MINIMIZE)
        return f"Minimized '{window.title}'."

    return _with_window(query, action)


def maximize_window(query: str) -> str:
    def action(window: WindowInfo) -> str:
        win32gui.ShowWindow(window.hwnd, win32con.SW_MAXIMIZE)
        return f"Maximized '{window.title}'."

    return _with_window(query, action)


def restore_window(query: str) -> str:
    def action(window: WindowInfo) -> str:
        win32gui.ShowWindow(window.hwnd, win32con.SW_RESTORE)
        return f"Restored '{window.title}'."

    return _with_window(query, action)


def close_window(query: str) -> str:
    def action(window: WindowInfo) -> str:
        win32gui.PostMessage(window.hwnd, win32con.WM_CLOSE, 0, 0)
        return f"Closed '{window.title}'."

    return _with_window(query, action)


def move_window_to_monitor(query: str, monitor_number: int) -> str:
    error = _require_windows()
    if error:
        return error

    window, resolve_error = _resolve_window(query)
    if resolve_error:
        return resolve_error
    assert window is not None

    monitor, monitor_error = _resolve_monitor(monitor_number)
    if monitor_error:
        return monitor_error
    assert monitor is not None

    hwnd = window.hwnd
    if win32gui.IsZoomed(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    # Position on target monitor, preserving size when possible
    rect = win32gui.GetWindowRect(hwnd)
    width = rect[2] - rect[0]
    height = rect[3] - rect[1]
    width = min(width, monitor.width)
    height = min(height, monitor.height)

    x = monitor.left + max(0, (monitor.width - width) // 2)
    y = monitor.top + max(0, (monitor.height - height) // 2)

    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOP,
        x,
        y,
        width,
        height,
        win32con.SWP_SHOWWINDOW,
    )
    _bring_to_front(hwnd)
    return f"Moved '{window.title}' to monitor {monitor_number}."


def snap_window(query: str, side: str) -> str:
    error = _require_windows()
    if error:
        return error

    window, resolve_error = _resolve_window(query)
    if resolve_error:
        return resolve_error
    assert window is not None

    side = side.strip().lower()
    hwnd = window.hwnd
    if win32gui.IsZoomed(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    monitor_handle = win32api.MonitorFromWindow(hwnd)
    monitor_info = win32api.GetMonitorInfo(monitor_handle)
    work_area = monitor_info["Work"]
    left, top, right, bottom = work_area
    width = right - left
    height = bottom - top

    if side in {"left", "right"}:
        snap_width = width // 2
        snap_height = height
        snap_x = left if side == "left" else left + snap_width
        snap_y = top
    elif side in {"top", "bottom"}:
        snap_width = width
        snap_height = height // 2
        snap_x = left
        snap_y = top if side == "top" else top + snap_height
    else:
        return f"Unknown snap position '{side}'. Use left, right, top, or bottom."

    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOP,
        snap_x,
        snap_y,
        snap_width,
        snap_height,
        win32con.SWP_SHOWWINDOW,
    )
    _bring_to_front(hwnd)
    return f"Snapped '{window.title}' to the {side}."
