from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Protocol

from desktop_sprite.core.animation_player import AnimationPlayer
from desktop_sprite.core.behavior_orchestrator import BehaviorPhaseName
from desktop_sprite.core.pathfinding import PathFinder, PathPlan
from desktop_sprite.core.pet_mode import PetMode
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.state import Pet
from desktop_sprite.utils.config import AppConfig, PhysicsConfig


@dataclass(frozen=True, slots=True)
class CharacterRenderState:
    x: float
    y: float
    width: int
    height: int
    body: Pet | None = None
    animation: AnimationPlayer | None = None
    payload: Any = None
    body_width: int | None = None
    body_height: int | None = None
    body_offset_x: float = 0.0
    body_offset_y: float = 0.0

    @property
    def pose_width(self) -> int:
        return self.body_width if self.body_width is not None else self.width

    @property
    def pose_height(self) -> int:
        return self.body_height if self.body_height is not None else self.height


@dataclass(frozen=True, slots=True)
class CharacterDebugState:
    snapshot: EnvironmentSnapshot
    pathfinder: PathFinder
    path_plan: PathPlan | None
    physics: PhysicsConfig
    mode: PetMode = PetMode.IDLE
    phase: BehaviorPhaseName | str = BehaviorPhaseName.IDLE_WAIT
    phase_elapsed: float = 0.0


class DesktopCharacter(Protocol):
    def set_own_window_handle(self, hwnd: int | None) -> None: ...
    def apply_config(self, config: AppConfig) -> None: ...
    def tick(self, dt: float) -> None: ...
    def start_drag(self, mouse_x: float, mouse_y: float) -> None: ...
    def drag_to(self, mouse_x: float, mouse_y: float) -> None: ...
    def release_drag(self, mouse_x: float, mouse_y: float) -> None: ...
    def poke(self) -> None: ...
    def sleep(self) -> bool: ...
    def set_target_surface_point(self, surface_id: str, anchor_t: float) -> bool: ...
    def start_show(self) -> bool: ...
    def render_state(self) -> CharacterRenderState: ...
    def debug_state(self) -> CharacterDebugState: ...
