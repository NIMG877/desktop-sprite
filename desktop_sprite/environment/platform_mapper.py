from __future__ import annotations

from desktop_sprite.models.geometry import Rect
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.models.window_info import WindowInfo


class PlatformMapper:
    def __init__(self, pet_width: int, pet_height: int) -> None:
        self.pet_width = pet_width
        self.pet_height = pet_height

    def map_platforms(
        self,
        screen_rect: Rect,
        work_area_rect: Rect,
        taskbar_rect: Rect | None,
        windows: list[WindowInfo],
    ) -> list[Platform]:
        platforms = [
            Platform(
                id="ground:work_area",
                type=PlatformType.GROUND,
                rect=Rect(work_area_rect.left, work_area_rect.bottom, work_area_rect.right, work_area_rect.bottom + 4),
                walkable=True,
                climbable=False,
            )
        ]

        if taskbar_rect and taskbar_rect.is_valid():
            platforms.append(
                Platform(
                    id="taskbar:main",
                    type=PlatformType.TASKBAR,
                    rect=Rect(taskbar_rect.left, taskbar_rect.top, taskbar_rect.right, taskbar_rect.top + 4),
                    walkable=True,
                    climbable=False,
                    dynamic=True,
                )
            )

        for window in windows:
            if window.minimized:
                continue
            platforms.extend(self._window_platforms(window, screen_rect))

        return platforms

    def _window_platforms(self, window: WindowInfo, screen_rect: Rect) -> list[Platform]:
        rect = window.rect
        top_rect = Rect(rect.left, rect.top, rect.right, rect.top + 8)
        left_rect = Rect(rect.left - 8, rect.top, rect.left + 6, rect.bottom)
        right_rect = Rect(rect.right - 6, rect.top, rect.right + 8, rect.bottom)

        return [
            Platform(
                id=f"window:{window.hwnd}:top",
                type=PlatformType.WINDOW_TOP,
                rect=self._clip_horizontal(top_rect, screen_rect),
                walkable=True,
                climbable=False,
                dynamic=True,
                source_id=window.hwnd,
            ),
            Platform(
                id=f"window:{window.hwnd}:left",
                type=PlatformType.WINDOW_LEFT,
                rect=left_rect,
                walkable=False,
                climbable=True,
                dynamic=True,
                source_id=window.hwnd,
            ),
            Platform(
                id=f"window:{window.hwnd}:right",
                type=PlatformType.WINDOW_RIGHT,
                rect=right_rect,
                walkable=False,
                climbable=True,
                dynamic=True,
                source_id=window.hwnd,
            ),
        ]

    def _clip_horizontal(self, rect: Rect, bounds: Rect) -> Rect:
        return Rect(max(rect.left, bounds.left), rect.top, min(rect.right, bounds.right), rect.bottom)
