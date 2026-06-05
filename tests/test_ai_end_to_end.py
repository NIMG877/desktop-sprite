import argparse
from pathlib import Path

from PySide6.QtWidgets import QApplication

from desktop_sprite.ai.provider import AIProvider
from desktop_sprite.app.runtime import AppRuntime
from desktop_sprite.app.config_paths import RuntimePaths
from desktop_sprite.utils.config import load_config


class _ScriptedProvider(AIProvider):
    """按 use_case_id 计数返回固定文本。"""
    def __init__(self):
        self.calls = []
    def generate(self, system, user, *, timeout=30.0):
        self.calls.append({"system": system, "user": user})
        return "小翼对你点头"
    def ping(self, *, timeout=5.0) -> float:
        return 12.0


def _make_paths(tmp_path: Path):
    paths = type("P", (), {})()
    paths.config_path = tmp_path / "default.json"
    paths.user_config_path = tmp_path / "user.json"
    paths.user_inventory_path = tmp_path / "inv.json"
    paths.user_spirit_mark_path = tmp_path / "sm.json"
    paths.user_ui_state_path = tmp_path / "ui.json"
    return paths


def _write_config(tmp_path: Path, *, ai_enabled: bool, api_key: str = "k") -> None:
    (tmp_path / "default.json").write_text(
        '{"app":{"fps":60,"always_on_top":true,"debug_draw":false,"log_level":"INFO"},'
        '"physics":{"gravity":1800,"max_fall_speed":1800,"drag_throw_factor":0.65,"edge_snap_distance":10,'
        '"walk_speed":120,"climb_speed":92,"jump_speed_x":180,"jump_speed_y":-520},'
        '"behavior":{"idle_min_seconds":1.0,"idle_max_seconds":2.5,"prefer_foreground_window":true,"target_repick_seconds":3.5},'
        '"attributes":{"wander":1,"vigor":1,"recovery":1,"awareness":1,"focus":1,"satiety":1,"spark":1,"radiance":0,"trail":0,"resonance":0,"aura":0,"arcana":0,"attunement":0},'
        '"interaction":{"draggable":true,"throw_enabled":true,"click_reaction":true,"mouse_hover_reaction":true,"target_search_down_distance":220,"target_search_up_distance":80},'
        '"character":{"default_type":"pet","profile_files":{}},'
        '"pet":{"width":84,"height":104,"default_spawn_x":300,"default_spawn_y":300},'
        f'"ai":{{"enabled":{str(ai_enabled).lower()},"base_url":"https://x","model":"m","api_key":"{api_key}",'
        '"request_timeout_s":30.0,"max_inflight":1,"throttle_overrides":{},'
        '"history_max_lines":200,"bubble_visible_seconds":1.0}}',
        encoding="utf-8",
    )
    (tmp_path / "user.json").write_text("{}", encoding="utf-8")
    (tmp_path / "inv.json").write_text("{}", encoding="utf-8")
    (tmp_path / "sm.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ui.json").write_text("{}", encoding="utf-8")


def test_end_to_end_disabled_no_calls(monkeypatch, tmp_path, qtbot):
    _write_config(tmp_path, ai_enabled=False)
    cfg = load_config(tmp_path / "default.json", tmp_path / "user.json")

    # 注入 fake provider；如果被调用就 fail
    def fail(*a, **k):
        raise RuntimeError("OpenAIProvider should not be constructed when enabled=False")
    monkeypatch.setattr("desktop_sprite.app.OpenAIProvider", fail)

    app = QApplication.instance() or QApplication([])
    paths = _make_paths(tmp_path)
    rt = AppRuntime(paths, [], argparse.Namespace(character="pet"), cfg, app)
    assert rt.ai_orchestrator is not None
    # 触发：DisabledProvider 抛 ProviderDisabled → fallback
    rt.ai_orchestrator.trigger_test()
    # 走 orchestrator 的内部 fallback；不依赖 UI 渲染
    qtbot.wait(200)
    rt.ai_orchestrator.stop()


def test_end_to_end_enabled_full_chain(monkeypatch, tmp_path, qtbot):
    _write_config(tmp_path, ai_enabled=True, api_key="sk-test")
    cfg = load_config(tmp_path / "default.json", tmp_path / "user.json")

    scripted = _ScriptedProvider()
    monkeypatch.setattr("desktop_sprite.app.OpenAIProvider", lambda *a, **k: scripted)

    app = QApplication.instance() or QApplication([])
    paths = _make_paths(tmp_path)
    rt = AppRuntime(paths, [], argparse.Namespace(character="pet"), cfg, app)
    assert rt.ai_orchestrator is not None
    assert rt.ai_bubble is not None

    # 把 bubble 替换为可断言的 fake
    from tests.ai_fakes import RecordingChannel
    fake_ch = RecordingChannel(name="pet_bubble")
    rt.ai_orchestrator._channels = [fake_ch]  # type: ignore[attr-defined]

    rt.ai_orchestrator.trigger_test(user_hint="end-to-end")
    qtbot.waitUntil(lambda: len(fake_ch.dispatched) == 1, timeout=2000)
    assert fake_ch.dispatched[0].text == "小翼对你点头"
    assert fake_ch.dispatched[0].source == "ai"
    assert len(scripted.calls) == 1
    assert "end-to-end" in scripted.calls[0]["user"]

    rt.ai_orchestrator.stop()
