from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from desktop_sprite.models.geometry import Rect, Vec2


class PetState(StrEnum):
    IDLE = "idle"
    WALK = "walk"
    JUMP = "jump"
    CLIMB = "climb"
    FALL = "fall"
    DRAGGED = "dragged"
    SLEEP = "sleep"


class Facing(StrEnum):
    LEFT = "left"
    RIGHT = "right"


@dataclass(slots=True)
class Pet:
    position: Vec2
    velocity: Vec2
    width: int
    height: int
    facing: Facing = Facing.RIGHT
    state: PetState = PetState.FALL
    support_surface_id: str | None = None
    target_surface_id: str | None = None
    target_window_id: int | None = None
    state_time: float = 0.0
    idle_timer: float = 0.0
    drag_positions: list[tuple[float, float, float]] = field(default_factory=list)

    @property
    def rect(self) -> Rect:
        return Rect.from_xywh(self.position.x, self.position.y, self.width, self.height)

    @property
    def bottom(self) -> float:
        return self.position.y + self.height

    @property
    def center_x(self) -> float:
        return self.position.x + self.width / 2
