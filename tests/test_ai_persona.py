import pytest
from desktop_sprite.ai.persona import Persona
from desktop_sprite.utils.config import AIPersonaConfig, AppConfig, _PERSONA_DEFAULTS


def test_from_config_uses_persona_block():
    fake_cfg = _build_cfg(persona=AIPersonaConfig(
        system_prompt="我是小翼", default_fallback="嗯"
    ))
    p = Persona.from_config(fake_cfg, character_id="pet")
    assert p.name == "pet"
    assert p.system_prompt == "我是小翼"
    assert p.default_fallback == "嗯"


def test_from_config_empty_system_prompt_falls_back_to_code_default():
    with pytest.raises(ValueError):
        AIPersonaConfig(system_prompt="", default_fallback="x")
    # 直接验证 from_config 不会拿到空 system_prompt：load_config 已在前面拒绝
    fake_cfg = _build_cfg(persona=AIPersonaConfig(**_PERSONA_DEFAULTS))
    p = Persona.from_config(fake_cfg, character_id="pet")
    assert p.system_prompt == _PERSONA_DEFAULTS["system_prompt"]


def _build_cfg(persona: AIPersonaConfig) -> AppConfig:
    """构造一个最小 AppConfig 用于 persona 测试。"""
    from desktop_sprite.utils.config import (
        RuntimeConfig, PetConfig, PetFlightConfig, PetWingConfig, PetHoverConfig,
        PhysicsConfig, BehaviorConfig, AttributesConfig, InteractionConfig,
        CharacterConfig, AIConfig, _AI_DEFAULTS,
    )
    return AppConfig(
        app=RuntimeConfig(fps=60, always_on_top=True, debug_draw=False, log_level="INFO"),
        pet=PetConfig(width=84, height=104, default_spawn_x=0, default_spawn_y=0),
        physics=PhysicsConfig(gravity=1800, walk_speed=120, climb_speed=92,
                              jump_speed_x=180, jump_speed_y=-520,
                              max_fall_speed=1800, drag_throw_factor=0.65, edge_snap_distance=10),
        behavior=BehaviorConfig(idle_min_seconds=1.0, idle_max_seconds=2.5,
                               prefer_foreground_window=True, target_repick_seconds=3.5),
        interaction=InteractionConfig(draggable=True, throw_enabled=True,
                                      click_reaction=True, mouse_hover_reaction=True,
                                      target_search_down_distance=220, target_search_up_distance=80),
        character=CharacterConfig(default_type="pet", profile_files={}),
        attributes=AttributesConfig(wander=1, vigor=1, recovery=1, awareness=1, focus=1,
                                    satiety=1, spark=1, radiance=0, trail=0, resonance=0,
                                    aura=0, arcana=0, attunement=0),
        ai=AIConfig(**_AI_DEFAULTS),
        ai_persona=persona,
    )
