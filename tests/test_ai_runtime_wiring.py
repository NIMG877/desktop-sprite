import pytest
import argparse
from PySide6.QtWidgets import QApplication
from desktop_sprite.app import __all__ as app_all
from desktop_sprite.app.runtime import AppRuntime


def test_app_package_exposes_new_ai_symbols():
    for name in ("OpenAIProvider", "DisabledProvider", "EventBus",
                 "UseCaseRegistry", "Persona", "AIPanelWidget",
                 "BubbleOverlayWindow", "make_test_probe_use_case"):
        assert name in app_all, f"{name} not in desktop_sprite.app.__all__"


def test_app_symbols_includes_ai_symbols():
    from desktop_sprite.app import runtime as rt
    syms = rt._app_symbols()
    for key in ("OpenAIProvider", "DisabledProvider", "EventBus",
                "UseCaseRegistry", "AIPanelWidget", "BubbleOverlayWindow"):
        assert key in syms, f"{key} not in _app_symbols()"


def test_app_runtime_constructs_ai_orchestrator_when_enabled(monkeypatch, tmp_path):
    from desktop_sprite.utils.config import load_config

    (tmp_path / "default.json").write_text(
        '{"app":{"fps":60,"always_on_top":true,"debug_draw":false,"log_level":"INFO"},'
        '"pet":{"width":84,"height":104,"default_spawn_x":300,"default_spawn_y":300},'
        '"physics":{"gravity":1800,"walk_speed":120,"climb_speed":92,"jump_speed_x":180,"jump_speed_y":-520,"max_fall_speed":1800,"drag_throw_factor":0.65,"edge_snap_distance":10},'
        '"behavior":{"idle_min_seconds":1.0,"idle_max_seconds":2.5,"prefer_foreground_window":true,"target_repick_seconds":3.5},'
        '"attributes":{"wander":1,"vigor":1,"recovery":1,"awareness":1,"focus":1,"satiety":1,"spark":1,"radiance":0,"trail":0,"resonance":0,"aura":0,"arcana":0,"attunement":0},'
        '"interaction":{"draggable":true,"throw_enabled":true,"click_reaction":true,"mouse_hover_reaction":true,"target_search_down_distance":220,"target_search_up_distance":80},'
        '"character":{"default_type":"pet","profile_files":{}},'
        '"ai":{"enabled":true,"base_url":"https://x","model":"m","api_key":"k",'
        '"request_timeout_s":30.0,"max_inflight":1,"throttle_overrides":{},'
        '"history_max_lines":200,"bubble_visible_seconds":3.0}}',
        encoding="utf-8",
    )
    user_json = tmp_path / "user.json"
    user_json.write_text("{}", encoding="utf-8")

    cfg = load_config(tmp_path / "default.json", user_json)

    fake_provider_class_calls = []
    class FakeOpenAIProvider:
        def __init__(self, base_url, api_key, model):
            fake_provider_class_calls.append((base_url, api_key, model))
            self.base_url, self.api_key, self.model = base_url, api_key, model
        def generate(self, system, user, *, timeout=30.0):
            return "ok"

    monkeypatch.setattr("desktop_sprite.app.OpenAIProvider", FakeOpenAIProvider)
    monkeypatch.setattr("desktop_sprite.app.DisabledProvider", lambda: (_ for _ in ()).throw(RuntimeError("should not be called when enabled=True")))

    app = QApplication.instance() or QApplication([])

    paths = type("P", (), {})()
    paths.config_path = tmp_path / "default.json"
    paths.user_config_path = user_json
    paths.user_inventory_path = tmp_path / "inv.json"
    paths.user_spirit_mark_path = tmp_path / "sm.json"
    paths.user_ui_state_path = tmp_path / "ui.json"

    rt = AppRuntime(paths, [], argparse.Namespace(character="pet"), cfg, app)
    assert rt.ai_orchestrator is not None
    assert fake_provider_class_calls
    rt.ai_orchestrator.stop()


def test_app_runtime_uses_disabled_provider_when_ai_disabled(monkeypatch, tmp_path):
    from desktop_sprite.utils.config import load_config

    (tmp_path / "default.json").write_text(
        '{"app":{"fps":60,"always_on_top":true,"debug_draw":false,"log_level":"INFO"},'
        '"pet":{"width":84,"height":104,"default_spawn_x":300,"default_spawn_y":300},'
        '"physics":{"gravity":1800,"walk_speed":120,"climb_speed":92,"jump_speed_x":180,"jump_speed_y":-520,"max_fall_speed":1800,"drag_throw_factor":0.65,"edge_snap_distance":10},'
        '"behavior":{"idle_min_seconds":1.0,"idle_max_seconds":2.5,"prefer_foreground_window":true,"target_repick_seconds":3.5},'
        '"attributes":{"wander":1,"vigor":1,"recovery":1,"awareness":1,"focus":1,"satiety":1,"spark":1,"radiance":0,"trail":0,"resonance":0,"aura":0,"arcana":0,"attunement":0},'
        '"interaction":{"draggable":true,"throw_enabled":true,"click_reaction":true,"mouse_hover_reaction":true,"target_search_down_distance":220,"target_search_up_distance":80},'
        '"character":{"default_type":"pet","profile_files":{}},'
        '"ai":{"enabled":false,"base_url":"https://x","model":"m","api_key":"",'
        '"request_timeout_s":30.0,"max_inflight":1,"throttle_overrides":{},'
        '"history_max_lines":200,"bubble_visible_seconds":3.0}}',
        encoding="utf-8",
    )
    user_json = tmp_path / "user.json"
    user_json.write_text("{}", encoding="utf-8")
    cfg = load_config(tmp_path / "default.json", user_json)

    disabled_called = []
    class FakeDisabled:
        def __init__(self): disabled_called.append(True)
    monkeypatch.setattr("desktop_sprite.app.DisabledProvider", FakeDisabled)
    monkeypatch.setattr("desktop_sprite.app.OpenAIProvider", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("should not be called when enabled=False")))

    app = QApplication.instance() or QApplication([])

    paths = type("P", (), {})()
    paths.config_path = tmp_path / "default.json"
    paths.user_config_path = user_json
    paths.user_inventory_path = tmp_path / "inv.json"
    paths.user_spirit_mark_path = tmp_path / "sm.json"
    paths.user_ui_state_path = tmp_path / "ui.json"

    rt = AppRuntime(paths, [], argparse.Namespace(character="pet"), cfg, app)
    assert rt.ai_orchestrator is not None
    assert disabled_called == [True]
    rt.ai_orchestrator.stop()


def test_app_runtime_wires_all_three_channels(monkeypatch, tmp_path):
    """`_init_ai` 必须同时接 pet_bubble / chat_panel / os_notification。

    之前只接 pet_bubble，导致 AI 200 OK 回来后 chat panel 历史一直是空。
    这个测试锁住三个 channel name 都在 orchestrator 的 channels 列表里。
    """
    from desktop_sprite.utils.config import load_config
    from desktop_sprite.ai.orchestrator import AIOrchestrator

    (tmp_path / "default.json").write_text(
        '{"app":{"fps":60,"always_on_top":true,"debug_draw":false,"log_level":"INFO"},'
        '"pet":{"width":84,"height":104,"default_spawn_x":300,"default_spawn_y":300},'
        '"physics":{"gravity":1800,"walk_speed":120,"climb_speed":92,"jump_speed_x":180,"jump_speed_y":-520,"max_fall_speed":1800,"drag_throw_factor":0.65,"edge_snap_distance":10},'
        '"behavior":{"idle_min_seconds":1.0,"idle_max_seconds":2.5,"prefer_foreground_window":true,"target_repick_seconds":3.5},'
        '"attributes":{"wander":1,"vigor":1,"recovery":1,"awareness":1,"focus":1,"satiety":1,"spark":1,"radiance":0,"trail":0,"resonance":0,"aura":0,"arcana":0,"attunement":0},'
        '"interaction":{"draggable":true,"throw_enabled":true,"click_reaction":true,"mouse_hover_reaction":true,"target_search_down_distance":220,"target_search_up_distance":80},'
        '"character":{"default_type":"pet","profile_files":{}},'
        '"ai":{"enabled":true,"base_url":"https://x","model":"m","api_key":"k",'
        '"request_timeout_s":30.0,"max_inflight":1,"throttle_overrides":{},'
        '"history_max_lines":200,"bubble_visible_seconds":3.0}}',
        encoding="utf-8",
    )
    user_json = tmp_path / "user.json"
    user_json.write_text("{}", encoding="utf-8")
    cfg = load_config(tmp_path / "default.json", user_json)

    class FakeOpenAIProvider:
        def __init__(self, base_url, api_key, model): pass
        def generate(self, system, user, *, timeout=30.0): return "ok"

    monkeypatch.setattr("desktop_sprite.app.OpenAIProvider", FakeOpenAIProvider)
    monkeypatch.setattr("desktop_sprite.app.DisabledProvider", lambda: (_ for _ in ()).throw(RuntimeError("disabled")))

    app = QApplication.instance() or QApplication([])
    paths = type("P", (), {})()
    paths.config_path = tmp_path / "default.json"
    paths.user_config_path = user_json
    paths.user_inventory_path = tmp_path / "inv.json"
    paths.user_spirit_mark_path = tmp_path / "sm.json"
    paths.user_ui_state_path = tmp_path / "ui.json"

    rt = AppRuntime(paths, [], argparse.Namespace(character="pet"), cfg, app)
    assert rt.ai_orchestrator is not None
    names = {ch.name for ch in rt.ai_orchestrator._channels}
    assert names == {"pet_bubble", "chat_panel", "os_notification"}, (
        f"expected all 3 channels, got {names}"
    )
    rt.ai_orchestrator.stop()
