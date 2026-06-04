from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from desktop_sprite.utils.safe_io import merge_dict


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    fps: int
    always_on_top: bool
    debug_draw: bool
    log_level: str


@dataclass(frozen=True, slots=True)
class PetFlightConfig:
    speed: float = 520.0
    landing_speed: float = 360.0


@dataclass(frozen=True, slots=True)
class PetWingConfig:
    open_seconds: float = 0.7
    close_seconds: float = 0.7


@dataclass(frozen=True, slots=True)
class PetHoverConfig:
    amplitude: float = 8.0
    frequency: float = 2.2


@dataclass(frozen=True, slots=True)
class PetConfig:
    width: int
    height: int
    default_spawn_x: int
    default_spawn_y: int
    flight: PetFlightConfig = field(default_factory=PetFlightConfig)
    wings: PetWingConfig = field(default_factory=PetWingConfig)
    hover: PetHoverConfig = field(default_factory=PetHoverConfig)


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
    prefer_foreground_window: bool
    target_repick_seconds: float


@dataclass(frozen=True, slots=True)
class AttributesConfig:
    wander: float
    vigor: float
    recovery: float
    awareness: float
    focus: float
    satiety: float
    spark: float
    radiance: float
    trail: float
    resonance: float
    aura: float
    arcana: float
    attunement: float


@dataclass(frozen=True, slots=True)
class InteractionConfig:
    draggable: bool
    throw_enabled: bool
    click_reaction: bool
    mouse_hover_reaction: bool
    target_search_down_distance: float
    target_search_up_distance: float


@dataclass(frozen=True, slots=True)
class CharacterConfig:
    default_type: str
    profile_files: dict[str, str]

@dataclass(frozen=True, slots=True)
class AppConfig:
    app: RuntimeConfig
    pet: PetConfig
    physics: PhysicsConfig
    behavior: BehaviorConfig
    interaction: InteractionConfig
    character: CharacterConfig
    attributes: AttributesConfig


def load_config(
    path: str | Path | None = None,
    user_path: str | Path | None = None,
) -> AppConfig:
    config_path = Path(path) if path else Path(__file__).resolve().parents[2] / "config" / "default.json"
    with config_path.open("r", encoding="utf-8") as file:
        data: dict[str, Any] = json.load(file)

    overrides: dict[str, Any] | None = None
    if user_path is not None:
        override_path = Path(user_path)
        if override_path.is_file():
            with override_path.open("r", encoding="utf-8") as file:
                overrides = json.load(file)
            if isinstance(overrides.get("character"), dict):
                merge_dict(data.setdefault("character", {}), overrides["character"])

    _load_character_profiles(config_path.parent, data)
    if overrides is not None:
        merge_dict(data, overrides)

    app_data = data["app"]
    interaction_data = data["interaction"]
    interaction_data.setdefault("target_search_down_distance", 220.0)
    interaction_data.setdefault("target_search_up_distance", 80.0)

    pet_data = dict(data["pet"])
    flight_data = pet_data.pop("flight", {})
    wing_data = pet_data.pop("wings", {})
    hover_data = pet_data.pop("hover", {})
    physics_data = dict(data["physics"])
    _migrate_pet_motion_keys(pet_data, physics_data)

    return AppConfig(
        app=RuntimeConfig(
            fps=app_data["fps"],
            always_on_top=app_data["always_on_top"],
            debug_draw=app_data["debug_draw"],
            log_level=app_data["log_level"],
        ),
        pet=PetConfig(
            **pet_data,
            flight=PetFlightConfig(**flight_data),
            wings=PetWingConfig(**wing_data),
            hover=PetHoverConfig(**hover_data),
        ),
        physics=PhysicsConfig(**physics_data),
        behavior=BehaviorConfig(**data["behavior"]),
        interaction=InteractionConfig(**interaction_data),
        character=CharacterConfig(**data["character"]),
        attributes=AttributesConfig(**data["attributes"]),
    )


def _load_character_profiles(config_root: Path, data: dict[str, Any]) -> None:
    character_cfg = data.get("character", {})
    profile_files = character_cfg.get("profile_files", {})
    for _name, relative_path in profile_files.items():
        profile_path = config_root / relative_path
        with profile_path.open("r", encoding="utf-8") as file:
            profile_data: dict[str, Any] = json.load(file)
        merge_dict(data, profile_data)


# Motion-key set that historically lived under the `pet` segment and
# has to be hoisted into the `physics` segment before we build
# `PhysicsConfig`. See `config/characters/pet.json` for the source of
# truth and `README.md` for the migration note.
_PET_MOTION_KEYS: tuple[str, ...] = (
    "walk_speed",
    "climb_speed",
    "jump_speed_x",
    "jump_speed_y",
)


def _migrate_pet_motion_keys(pet_data: dict[str, Any], physics_data: dict[str, Any]) -> None:
    """Move `walk_speed` / `climb_speed` / `jump_speed_*` from `pet` to `physics`.

    Older character profiles and default configs placed motion
    parameters under the `pet` segment, alongside the cosmetic
    settings (`flight`, `wings`, `hover`). The runtime now consumes
    them via `PhysicsConfig`, so this helper performs the silent
    migration in one explicit location. New configs should write the
    values directly into the `physics` segment.
    """

    for key in _PET_MOTION_KEYS:
        if key in pet_data:
            physics_data[key] = pet_data.pop(key)
