import json
from pathlib import Path

import pytest

from desktop_sprite.utils.config import (
    AIConfig,
    AIPersonaConfig,
    AppConfig,
    load_config,
)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_load_config_with_ai_block(tmp_path: Path):
    cfg_path = tmp_path / "default.json"
    _write_json(cfg_path, {
        "app": {"fps": 60, "always_on_top": True, "debug_draw": False, "log_level": "INFO"},
        "pet": {"width": 84, "height": 104, "default_spawn_x": 300, "default_spawn_y": 300,
                "walk_speed": 120, "climb_speed": 92, "jump_speed_x": 180, "jump_speed_y": -520},
        "physics": {"gravity": 1800, "max_fall_speed": 1800, "drag_throw_factor": 0.65, "edge_snap_distance": 10},
        "behavior": {"idle_min_seconds": 1.0, "idle_max_seconds": 2.5, "prefer_foreground_window": True, "target_repick_seconds": 3.5},
        "attributes": {"wander": 1, "vigor": 1, "recovery": 1, "awareness": 1, "focus": 1, "satiety": 1, "spark": 1, "radiance": 0, "trail": 0, "resonance": 0, "aura": 0, "arcana": 0, "attunement": 0},
        "interaction": {"draggable": True, "throw_enabled": True, "click_reaction": True, "mouse_hover_reaction": True, "target_search_down_distance": 220, "target_search_up_distance": 80},
        "character": {"default_type": "pet", "profile_files": {}},
        "ai": {
            "enabled": False, "base_url": "https://x", "model": "gpt-x",
            "api_key": "", "request_timeout_s": 30.0, "max_inflight": 1,
            "throttle_overrides": {}, "history_max_lines": 200,
            "bubble_visible_seconds": 3.0,
        },
    })
    cfg = load_config(cfg_path, None)
    assert isinstance(cfg.ai, AIConfig)
    assert cfg.ai.enabled is False
    assert cfg.ai.max_inflight == 1


def test_load_config_without_ai_block_uses_safe_defaults(tmp_path: Path):
    cfg_path = tmp_path / "default.json"
    _write_json(cfg_path, {
        "app": {"fps": 60, "always_on_top": True, "debug_draw": False, "log_level": "INFO"},
        "pet": {"width": 84, "height": 104, "default_spawn_x": 300, "default_spawn_y": 300,
                "walk_speed": 120, "climb_speed": 92, "jump_speed_x": 180, "jump_speed_y": -520},
        "physics": {"gravity": 1800, "max_fall_speed": 1800, "drag_throw_factor": 0.65, "edge_snap_distance": 10},
        "behavior": {"idle_min_seconds": 1.0, "idle_max_seconds": 2.5, "prefer_foreground_window": True, "target_repick_seconds": 3.5},
        "attributes": {"wander": 1, "vigor": 1, "recovery": 1, "awareness": 1, "focus": 1, "satiety": 1, "spark": 1, "radiance": 0, "trail": 0, "resonance": 0, "aura": 0, "arcana": 0, "attunement": 0},
        "interaction": {"draggable": True, "throw_enabled": True, "click_reaction": True, "mouse_hover_reaction": True, "target_search_down_distance": 220, "target_search_up_distance": 80},
        "character": {"default_type": "pet", "profile_files": {}},
    })
    cfg = load_config(cfg_path, None)
    assert cfg.ai.enabled is False
    assert cfg.ai.max_inflight == 1


def test_user_json_overrides_ai_block(tmp_path: Path):
    cfg_path = tmp_path / "default.json"
    user_path = tmp_path / "user.json"
    _write_json(cfg_path, {
        "app": {"fps": 60, "always_on_top": True, "debug_draw": False, "log_level": "INFO"},
        "pet": {"width": 84, "height": 104, "default_spawn_x": 300, "default_spawn_y": 300,
                "walk_speed": 120, "climb_speed": 92, "jump_speed_x": 180, "jump_speed_y": -520},
        "physics": {"gravity": 1800, "max_fall_speed": 1800, "drag_throw_factor": 0.65, "edge_snap_distance": 10},
        "behavior": {"idle_min_seconds": 1.0, "idle_max_seconds": 2.5, "prefer_foreground_window": True, "target_repick_seconds": 3.5},
        "attributes": {"wander": 1, "vigor": 1, "recovery": 1, "awareness": 1, "focus": 1, "satiety": 1, "spark": 1, "radiance": 0, "trail": 0, "resonance": 0, "aura": 0, "arcana": 0, "attunement": 0},
        "interaction": {"draggable": True, "throw_enabled": True, "click_reaction": True, "mouse_hover_reaction": True, "target_search_down_distance": 220, "target_search_up_distance": 80},
        "character": {"default_type": "pet", "profile_files": {}},
        "ai": {"enabled": False, "base_url": "x", "model": "m", "api_key": "",
               "request_timeout_s": 30.0, "max_inflight": 1, "throttle_overrides": {},
               "history_max_lines": 200, "bubble_visible_seconds": 3.0},
    })
    _write_json(user_path, {"ai": {"enabled": True, "api_key": "sk-123", "max_inflight": 2}})
    cfg = load_config(cfg_path, user_path)
    assert cfg.ai.enabled is True
    assert cfg.ai.api_key == "sk-123"
    assert cfg.ai.max_inflight == 2
    # 未覆盖字段保留默认
    assert cfg.ai.base_url == "x"


def test_ai_config_strict_validation_rejects_unknown_key(tmp_path: Path):
    cfg_path = tmp_path / "default.json"
    _write_json(cfg_path, {
        "app": {"fps": 60, "always_on_top": True, "debug_draw": False, "log_level": "INFO"},
        "pet": {"width": 84, "height": 104, "default_spawn_x": 300, "default_spawn_y": 300,
                "walk_speed": 120, "climb_speed": 92, "jump_speed_x": 180, "jump_speed_y": -520},
        "physics": {"gravity": 1800, "max_fall_speed": 1800, "drag_throw_factor": 0.65, "edge_snap_distance": 10},
        "behavior": {"idle_min_seconds": 1.0, "idle_max_seconds": 2.5, "prefer_foreground_window": True, "target_repick_seconds": 3.5},
        "attributes": {"wander": 1, "vigor": 1, "recovery": 1, "awareness": 1, "focus": 1, "satiety": 1, "spark": 1, "radiance": 0, "trail": 0, "resonance": 0, "aura": 0, "arcana": 0, "attunement": 0},
        "interaction": {"draggable": True, "throw_enabled": True, "click_reaction": True, "mouse_hover_reaction": True, "target_search_down_distance": 220, "target_search_up_distance": 80},
        "character": {"default_type": "pet", "profile_files": {}},
        "ai": {"enabled": False, "unknown_field": True},
    })
    with pytest.raises(ValueError, match="unknown"):
        load_config(cfg_path, None)


def test_ai_config_strict_validation_rejects_out_of_range(tmp_path: Path):
    cfg_path = tmp_path / "default.json"
    _write_json(cfg_path, {
        "app": {"fps": 60, "always_on_top": True, "debug_draw": False, "log_level": "INFO"},
        "pet": {"width": 84, "height": 104, "default_spawn_x": 300, "default_spawn_y": 300,
                "walk_speed": 120, "climb_speed": 92, "jump_speed_x": 180, "jump_speed_y": -520},
        "physics": {"gravity": 1800, "max_fall_speed": 1800, "drag_throw_factor": 0.65, "edge_snap_distance": 10},
        "behavior": {"idle_min_seconds": 1.0, "idle_max_seconds": 2.5, "prefer_foreground_window": True, "target_repick_seconds": 3.5},
        "attributes": {"wander": 1, "vigor": 1, "recovery": 1, "awareness": 1, "focus": 1, "satiety": 1, "spark": 1, "radiance": 0, "trail": 0, "resonance": 0, "aura": 0, "arcana": 0, "attunement": 0},
        "interaction": {"draggable": True, "throw_enabled": True, "click_reaction": True, "mouse_hover_reaction": True, "target_search_down_distance": 220, "target_search_up_distance": 80},
        "character": {"default_type": "pet", "profile_files": {}},
        "ai": {"enabled": False, "max_inflight": 10, "base_url": "x", "model": "m", "api_key": "",
               "request_timeout_s": 30.0, "throttle_overrides": {},
               "history_max_lines": 200, "bubble_visible_seconds": 3.0},
    })
    with pytest.raises(ValueError, match="max_inflight"):
        load_config(cfg_path, None)


def test_ai_persona_config_from_character_profile(tmp_path: Path):
    cfg_path = tmp_path / "default.json"
    char_dir = tmp_path / "characters"
    char_dir.mkdir()
    (char_dir / "pet.json").write_text(
        json.dumps({"ai_persona": {"system_prompt": "我是小翼", "default_fallback": "嗯"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_json(cfg_path, {
        "app": {"fps": 60, "always_on_top": True, "debug_draw": False, "log_level": "INFO"},
        "pet": {"width": 84, "height": 104, "default_spawn_x": 300, "default_spawn_y": 300,
                "walk_speed": 120, "climb_speed": 92, "jump_speed_x": 180, "jump_speed_y": -520},
        "physics": {"gravity": 1800, "max_fall_speed": 1800, "drag_throw_factor": 0.65, "edge_snap_distance": 10},
        "behavior": {"idle_min_seconds": 1.0, "idle_max_seconds": 2.5, "prefer_foreground_window": True, "target_repick_seconds": 3.5},
        "attributes": {"wander": 1, "vigor": 1, "recovery": 1, "awareness": 1, "focus": 1, "satiety": 1, "spark": 1, "radiance": 0, "trail": 0, "resonance": 0, "aura": 0, "arcana": 0, "attunement": 0},
        "interaction": {"draggable": True, "throw_enabled": True, "click_reaction": True, "mouse_hover_reaction": True, "target_search_down_distance": 220, "target_search_up_distance": 80},
        "character": {"default_type": "pet", "profile_files": {"pet": "characters/pet.json"}},
    })
    cfg = load_config(cfg_path, None)
    assert isinstance(cfg.ai_persona, AIPersonaConfig)
    assert cfg.ai_persona.system_prompt == "我是小翼"


def test_ai_persona_missing_uses_code_default(tmp_path: Path):
    cfg_path = tmp_path / "default.json"
    _write_json(cfg_path, {
        "app": {"fps": 60, "always_on_top": True, "debug_draw": False, "log_level": "INFO"},
        "pet": {"width": 84, "height": 104, "default_spawn_x": 300, "default_spawn_y": 300,
                "walk_speed": 120, "climb_speed": 92, "jump_speed_x": 180, "jump_speed_y": -520},
        "physics": {"gravity": 1800, "max_fall_speed": 1800, "drag_throw_factor": 0.65, "edge_snap_distance": 10},
        "behavior": {"idle_min_seconds": 1.0, "idle_max_seconds": 2.5, "prefer_foreground_window": True, "target_repick_seconds": 3.5},
        "attributes": {"wander": 1, "vigor": 1, "recovery": 1, "awareness": 1, "focus": 1, "satiety": 1, "spark": 1, "radiance": 0, "trail": 0, "resonance": 0, "aura": 0, "arcana": 0, "attunement": 0},
        "interaction": {"draggable": True, "throw_enabled": True, "click_reaction": True, "mouse_hover_reaction": True, "target_search_down_distance": 220, "target_search_up_distance": 80},
        "character": {"default_type": "pet", "profile_files": {}},
    })
    cfg = load_config(cfg_path, None)
    assert isinstance(cfg.ai_persona, AIPersonaConfig)
    assert cfg.ai_persona.system_prompt  # 非空
