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
class AIConfig:
    enabled: bool
    base_url: str
    model: str
    api_key: str
    request_timeout_s: float
    max_inflight: int
    throttle_overrides: dict[str, int]
    history_max_lines: int
    bubble_visible_seconds: float

    def __post_init__(self) -> None:
        if not 1.0 <= self.request_timeout_s <= 120.0:
            raise ValueError(f"ai.request_timeout_s out of range: {self.request_timeout_s}")
        if not 1 <= self.max_inflight <= 4:
            raise ValueError(f"ai.max_inflight out of range: {self.max_inflight}")
        if not 10 <= self.history_max_lines <= 5000:
            raise ValueError(f"ai.history_max_lines out of range: {self.history_max_lines}")
        if not 0.5 <= self.bubble_visible_seconds <= 30.0:
            raise ValueError(f"ai.bubble_visible_seconds out of range: {self.bubble_visible_seconds}")
        for uc_id, ms in self.throttle_overrides.items():
            if ms < 0:
                raise ValueError(f"ai.throttle_overrides[{uc_id!r}] must be >= 0")


_AI_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "api_key": "",
    "request_timeout_s": 30.0,
    "max_inflight": 1,
    "throttle_overrides": {},
    "history_max_lines": 200,
    "bubble_visible_seconds": 3.0,
}

_AI_KNOWN_KEYS: frozenset[str] = frozenset(_AI_DEFAULTS.keys())


@dataclass(frozen=True, slots=True)
class AIPersonaConfig:
    system_prompt: str
    default_fallback: str

    def __post_init__(self) -> None:
        if not self.system_prompt:
            raise ValueError("ai_persona.system_prompt must be non-empty")


_PERSONA_DEFAULTS: dict[str, Any] = {
    "system_prompt": "你是一只温顺的桌宠小翼。",
    "default_fallback": "（沉默）",
}


@dataclass(frozen=True, slots=True)
class AppConfig:
    app: RuntimeConfig
    pet: PetConfig
    physics: PhysicsConfig
    behavior: BehaviorConfig
    interaction: InteractionConfig
    character: CharacterConfig
    attributes: AttributesConfig
    ai: AIConfig
    ai_persona: AIPersonaConfig


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

    # ai 段：缺省/严格校验/合并
    ai_raw = dict(data.get("ai") or {})
    unknown_ai = set(ai_raw) - _AI_KNOWN_KEYS
    if unknown_ai:
        raise ValueError(f"ai block has unknown keys: {sorted(unknown_ai)}")
    ai_merged = {**_AI_DEFAULTS, **ai_raw}
    ai_merged["throttle_overrides"] = {
        **{k: int(v) for k, v in _AI_DEFAULTS["throttle_overrides"].items()},
        **{k: int(v) for k, v in ai_merged.get("throttle_overrides", {}).items()},
    }

    # ai_persona 段：从 character profile merge 出来（profile 已 merge 进 data）
    persona_raw = data.get("ai_persona") or {}
    if not isinstance(persona_raw, dict):
        raise ValueError("ai_persona must be a dict if present")
    if "system_prompt" in persona_raw and not persona_raw["system_prompt"]:
        raise ValueError("ai_persona.system_prompt must be non-empty if provided")
    persona_merged = {**_PERSONA_DEFAULTS, **persona_raw}

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
        ai=AIConfig(**ai_merged),
        ai_persona=AIPersonaConfig(**persona_merged),
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
