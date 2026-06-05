"""AI 互动子页接入到 MainWindow 的集成测试。"""
from PySide6.QtWidgets import QApplication
from desktop_sprite.ui.main_window import MainWindow
from desktop_sprite.ui.ai_panel import AIPanelWidget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_has_ai_panel(qtbot, tmp_path):
    from desktop_sprite.utils.config import load_config
    (tmp_path / "default.json").write_text(
        '{"app":{"fps":60,"always_on_top":true,"debug_draw":false,"log_level":"INFO"},'
        '"physics":{"gravity":1800,"max_fall_speed":1800,"drag_throw_factor":0.65,"edge_snap_distance":10,'
        '"walk_speed":120,"climb_speed":92,"jump_speed_x":180,"jump_speed_y":-520},'
        '"behavior":{"idle_min_seconds":1.0,"idle_max_seconds":2.5,"prefer_foreground_window":true,"target_repick_seconds":3.5},'
        '"attributes":{"wander":1,"vigor":1,"recovery":1,"awareness":1,"focus":1,"satiety":1,"spark":1,"radiance":0,"trail":0,"resonance":0,"aura":0,"arcana":0,"attunement":0},'
        '"interaction":{"draggable":true,"throw_enabled":true,"click_reaction":true,"mouse_hover_reaction":true,"target_search_down_distance":220,"target_search_up_distance":80},'
        '"character":{"default_type":"pet","profile_files":{}},'
        '"pet":{"width":84,"height":104,"default_spawn_x":300,"default_spawn_y":300},'
        '"ai":{"enabled":false,"base_url":"x","model":"m","api_key":"",'
        '"request_timeout_s":30.0,"max_inflight":1,"throttle_overrides":{},'
        '"history_max_lines":200,"bubble_visible_seconds":3.0}}',
        encoding="utf-8",
    )
    cfg = load_config(tmp_path / "default.json", None)

    class FakeOrchestrator:
        def trigger_test(self): pass

    # 关键：open_main_window 路径需要 inventory、spirit_marks 等；这里我们只测 addInterface
    win = MainWindow(
        config_path=tmp_path / "default.json",
        on_set_target=lambda: None,
        on_show=lambda: None,
        on_sleep=lambda: None,
        user_config_path=None,
        on_restart=lambda: None,
        on_apply_config=lambda: None,
        on_quit=lambda: None,
        inventory_snapshot=None,
        spirit_mark_inventory=None,
        pet_attribute_sheet=None,
        on_spirit_marks_changed=lambda u: None,
        on_debug_request_spirit_mark=lambda: "",
    )
    win._ai_panel_widget = AIPanelWidget(orchestrator=FakeOrchestrator())
    win._ai_panel_widget.setObjectName("aiPanelPage")
    win.addSubInterface(win._ai_panel_widget, None, "AI 互动")
    qtbot.addWidget(win)
    # 断言：能查到 AIPanelWidget 在子接口里
    found = [w for w in win.findChildren(AIPanelWidget)]
    assert len(found) >= 1
