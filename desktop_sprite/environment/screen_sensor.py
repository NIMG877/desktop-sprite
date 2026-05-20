from __future__ import annotations

import ctypes
from ctypes import wintypes

from desktop_sprite.models.geometry import Rect
from desktop_sprite.utils.dpi import qt_primary_screen_rects

SM_CXSCREEN = 0
SM_CYSCREEN = 1
SPI_GETWORKAREA = 0x0030


class _WinRect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class ScreenSensor:
    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None

    def get_screen_rect(self) -> Rect:
        qt_rects = qt_primary_screen_rects()
        if qt_rects is not None:
            return qt_rects[0]
        if self._user32 is None:
            return Rect.from_xywh(0, 0, 1280, 720)
        width = self._user32.GetSystemMetrics(SM_CXSCREEN)
        height = self._user32.GetSystemMetrics(SM_CYSCREEN)
        return Rect.from_xywh(0, 0, width, height)

    def get_work_area_rect(self) -> Rect:
        qt_rects = qt_primary_screen_rects()
        if qt_rects is not None:
            return qt_rects[1]
        if self._user32 is None:
            return self.get_screen_rect()
        raw = _WinRect()
        ok = self._user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(raw), 0)
        if not ok:
            return self.get_screen_rect()
        return Rect(raw.left, raw.top, raw.right, raw.bottom)
