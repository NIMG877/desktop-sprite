from __future__ import annotations

import ctypes
from ctypes import wintypes

from desktop_sprite.models.geometry import Rect
from desktop_sprite.models.window_info import WindowInfo
from desktop_sprite.utils.dpi import normalize_win32_rect_to_qt


class _WinRect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


IGNORED_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "Button",
    "Windows.UI.Core.CoreWindow",
}


class WindowSensor:
    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
        self._own_hwnd: int | None = None

    def set_own_window_handle(self, hwnd: int | None) -> None:
        self._own_hwnd = hwnd

    def get_windows(self) -> list[WindowInfo]:
        if self._user32 is None:
            return []

        foreground = int(self._user32.GetForegroundWindow())
        windows: list[WindowInfo] = []

        def callback(hwnd: int, _lparam: int) -> bool:
            info = self._window_info(int(hwnd), foreground)
            if info is not None and self._is_usable_window(info):
                windows.append(info)
            return True

        self._user32.EnumWindows(EnumWindowsProc(callback), 0)
        windows.sort(key=lambda item: 0 if item.is_foreground else 1)
        return windows

    def get_foreground_window(self) -> WindowInfo | None:
        return next((window for window in self.get_windows() if window.is_foreground), None)

    def _window_info(self, hwnd: int, foreground: int) -> WindowInfo | None:
        if hwnd == self._own_hwnd:
            return None
        if not self._user32.IsWindowVisible(hwnd):
            return None

        raw = _WinRect()
        if not self._user32.GetWindowRect(hwnd, ctypes.byref(raw)):
            return None
        rect = Rect(raw.left, raw.top, raw.right, raw.bottom)
        rect = normalize_win32_rect_to_qt(rect, self._user32.GetSystemMetrics(0))
        if not rect.is_valid():
            return None

        title = self._window_text(hwnd)
        class_name = self._class_name(hwnd)
        minimized = bool(self._user32.IsIconic(hwnd))

        return WindowInfo(
            hwnd=hwnd,
            title=title,
            rect=rect,
            visible=True,
            minimized=minimized,
            is_foreground=hwnd == foreground,
            class_name=class_name,
        )

    def _is_usable_window(self, info: WindowInfo) -> bool:
        if info.minimized:
            return False
        if info.class_name in IGNORED_CLASSES:
            return False
        if info.rect.width < 120 or info.rect.height < 80:
            return False
        if not info.title.strip() and not info.is_foreground:
            return False
        return True

    def _window_text(self, hwnd: int) -> str:
        length = self._user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        self._user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def _class_name(self, hwnd: int) -> str:
        buffer = ctypes.create_unicode_buffer(256)
        self._user32.GetClassNameW(hwnd, buffer, 256)
        return buffer.value
