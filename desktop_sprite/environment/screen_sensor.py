"""Screen geometry sensor.

Reads the primary monitor's full-screen and work-area rects through
the Qt screen API. The previous Win32 fallback (`GetSystemMetrics`
+ `SystemParametersInfo`) is removed: the runtime only calls this
sensor after `QApplication` is constructed, so the Qt path is
guaranteed to succeed and the Win32 branch was dead.
"""

from __future__ import annotations

from desktop_sprite.models.geometry import Rect
from desktop_sprite.utils.dpi import qt_primary_screen_rects


class ScreenSensor:
    def get_screen_rect(self) -> Rect:
        rects = qt_primary_screen_rects()
        if rects is None:
            return Rect.from_xywh(0, 0, 1280, 720)
        return rects[0]

    def get_work_area_rect(self) -> Rect:
        rects = qt_primary_screen_rects()
        if rects is None:
            return self.get_screen_rect()
        return rects[1]
