from __future__ import annotations

from dataclasses import dataclass

from desktop_sprite.models.geometry import Rect
from desktop_sprite.models.platform import Platform
from desktop_sprite.models.window_info import WindowInfo


@dataclass(frozen=True, slots=True)
class EnvironmentSnapshot:
    screen_rect: Rect
    work_area_rect: Rect
    taskbar_rect: Rect | None
    windows: list[WindowInfo]
    platforms: list[Platform]
    timestamp: float

    def platform_by_id(self, platform_id: str | None) -> Platform | None:
        if platform_id is None:
            return None
        return next((platform for platform in self.platforms if platform.id == platform_id), None)

    @property
    def foreground_window(self) -> WindowInfo | None:
        return next((window for window in self.windows if window.is_foreground), None)
