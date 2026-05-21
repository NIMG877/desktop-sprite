from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    fps: int
    always_on_top: bool
    debug_draw: bool
    log_level: str


@dataclass(frozen=True, slots=True)
class PetConfig:
    width: int
    height: int
    default_spawn_x: int
    default_spawn_y: int


@dataclass(frozen=True, slots=True)
class PhysicsConfig:
    gravity: float
    walk_speed: float
    climb_speed: float
    jump_speed_x: float
    jump_speed_y: float
    max_fall_speed: float
    drag_throw_factor: float
    edge_snap_distance: float


@dataclass(frozen=True, slots=True)
class BehaviorConfig:
    idle_min_seconds: float
    idle_max_seconds: float
    sleep_after_seconds: float
    prefer_foreground_window: bool
    target_repick_seconds: float


@dataclass(frozen=True, slots=True)
class InteractionConfig:
    draggable: bool
    throw_enabled: bool
    click_reaction: bool
    mouse_hover_reaction: bool


@dataclass(frozen=True, slots=True)
class AppConfig:
    app: RuntimeConfig
    pet: PetConfig
    physics: PhysicsConfig
    behavior: BehaviorConfig
    interaction: InteractionConfig


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path else Path(__file__).resolve().parents[2] / "config" / "default.json"
    with config_path.open("r", encoding="utf-8") as file:
        data: dict[str, Any] = json.load(file)

    app_data = data["app"]
    return AppConfig(
        app=RuntimeConfig(
            fps=app_data["fps"],
            always_on_top=app_data["always_on_top"],
            debug_draw=app_data["debug_draw"],
            log_level=app_data["log_level"],
        ),
        pet=PetConfig(**data["pet"]),
        physics=PhysicsConfig(**data["physics"]),
        behavior=BehaviorConfig(**data["behavior"]),
        interaction=InteractionConfig(**data["interaction"]),
    )
