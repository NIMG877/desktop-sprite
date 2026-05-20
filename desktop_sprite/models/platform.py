from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from desktop_sprite.models.geometry import Rect


class PlatformType(StrEnum):
    GROUND = "ground"
    TASKBAR = "taskbar"
    WINDOW_TOP = "window_top"
    WINDOW_LEFT = "window_left"
    WINDOW_RIGHT = "window_right"


@dataclass(frozen=True, slots=True)
class Platform:
    id: str
    type: PlatformType
    rect: Rect
    walkable: bool
    climbable: bool
    dynamic: bool = False
    source_id: int | None = None

    @property
    def top_y(self) -> float:
        return self.rect.top
