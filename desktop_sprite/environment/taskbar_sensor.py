from __future__ import annotations

import ctypes
from ctypes import wintypes

from desktop_sprite.models.geometry import Rect
from desktop_sprite.utils.dpi import normalize_win32_rect_to_qt


class _WinRect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class TaskbarSensor:
    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None

    def get_taskbar_rect(self) -> Rect | None:
        if self._user32 is None:
            return None
        hwnd = self._user32.FindWindowW("Shell_TrayWnd", None)
        if not hwnd:
            return None
        raw = _WinRect()
        if not self._user32.GetWindowRect(hwnd, ctypes.byref(raw)):
            return None
        rect = Rect(raw.left, raw.top, raw.right, raw.bottom)
        screen_width = self._user32.GetSystemMetrics(0)
        rect = normalize_win32_rect_to_qt(rect, screen_width)
        return rect if rect.is_valid() else None
