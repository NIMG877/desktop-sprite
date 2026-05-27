from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Protocol

from desktop_sprite.core.animation_player import AnimationPlayer
from desktop_sprite.core.pathfinding import PathFinder, PathPlan
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.state import Pet
from desktop_sprite.utils.config import PhysicsConfig


@dataclass(frozen=True, slots=True)
class CharacterRenderState:
    x: float
    y: float
    width: int
    height: int
    body: Pet | None = None
    animation: AnimationPlayer | None = None
    payload: Any = None


@dataclass(frozen=True, slots=True)
class CharacterDebugState:
    snapshot: EnvironmentSnapshot
    pathfinder: PathFinder
    path_plan: PathPlan | None
    physics: PhysicsConfig


class DesktopCharacter(Protocol):
    def set_own_window_handle(self, hwnd: int | None) -> None: ...
    def tick(self, dt: float) -> None: ...
    def start_drag(self, mouse_x: float, mouse_y: float) -> None: ...
    def drag_to(self, mouse_x: float, mouse_y: float) -> None: ...
    def release_drag(self, mouse_x: float, mouse_y: float) -> None: ...
    def poke(self) -> None: ...
    def set_target_surface_point(self, surface_id: str, anchor_t: float) -> bool: ...
    def render_state(self) -> CharacterRenderState: ...
    def debug_state(self) -> CharacterDebugState: ...
