"""AI 互动子页接入到 MainWindow 的集成测试。"""
from PySide6.QtWidgets import QApplication
from qfluentwidgets import CardWidget

from desktop_sprite.ui.main_window import MainWindow
from desktop_sprite.ui.ai_panel import AIPanelWidget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _write_default_config(tmp_path, *, history_max_lines: int = 200) -> None:
    (tmp_path / "default.json").write_text(
        '{"app":{"fps":60,"always_on_top":true,"debug_draw":false,"log_level":"INFO"},'
        '"physics":{"gravity":1800,"max_fall_speed":1800,"drag_throw_factor":0.65,"edge_snap_distance":10,'
        '"walk_speed":120,"climb_speed":92,"jump_speed_x":180,"jump_speed_y":-520},'
        '"behavior":{"idle_min_seconds":1.0,"idle_max_seconds":2.5,"prefer_foreground_window":true,"target_repick_seconds":3.5},'
        '"attributes":{"wander":1,"vigor":1,"recovery":1,"awareness":1,"focus":1,"satiety":1,"spark":1,"radiance":0,"trail":0,"resonance":0,"aura":0,"arcana":0,"attunement":0},'
        '"interaction":{"draggable":true,"throw_enabled":true,"click_reaction":true,"mouse_hover_reaction":true,"target_search_down_distance":220,"target_search_up_distance":80},'
        '"character":{"default_type":"pet","profile_files":{}},'
        '"pet":{"width":84,"height":104,"default_spawn_x":300,"default_spawn_y":300},'
        f'"ai":{{"enabled":false,"base_url":"x","model":"m","api_key":"",'
        f'"request_timeout_s":30.0,"max_inflight":1,"throttle_overrides":{{}},'
        f'"history_max_lines":{history_max_lines},"bubble_visible_seconds":3.0}}}}',
        encoding="utf-8",
    )


class FakeOrchestrator:
    def trigger_test(self): pass


def test_main_window_constructor_with_ai_orchestrator_registers_panel(qtbot, tmp_path):
    """完整覆盖 production 路径：`ai_orchestrator` 注入时 MainWindow 构造
    不能抛 ValueError（qfluentwidgets addSubInterface 强制 objectName 非空）。
    """
    _write_default_config(tmp_path)
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
        ai_orchestrator=FakeOrchestrator(),
    )
    qtbot.addWidget(win)
    # 构造没抛 → 通过；进一步断言 panel 已注册
    assert win._ai_panel_widget is not None
    assert win._ai_panel_widget.objectName() == "aiPanelPage"
    found = [w for w in win.findChildren(AIPanelWidget)]
    assert len(found) >= 1


def test_ai_panel_uses_fluentui_card_widgets(qtbot, tmp_path):
    """AI 互动面板要和其它子页一致走 FluentUI：CardWidget 包段落。"""
    _write_default_config(tmp_path)
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
        ai_orchestrator=FakeOrchestrator(),
    )
    qtbot.addWidget(win)
    panel = win._ai_panel_widget
    # 至少要有"对话历史"和"运行状态"两张 CardWidget
    card_object_names = {c.objectName() for c in panel.findChildren(CardWidget)}
    assert "aiHistoryCard" in card_object_names, f"missing history card, got {card_object_names}"
    assert "aiStatusCard" in card_object_names, f"missing status card, got {card_object_names}"


def test_ai_panel_sits_in_quan_zidong_slot(qtbot, tmp_path):
    """AI 互动子页要替换原来的"全自动"占位页（位置、图标）。

    用 FluentWindow.stackedWidget 的索引来锁住顺序：home → realtime →
    growth → inventory → AI 互动（替换原 全自动）→ 辅助操控 → 调试 → 通知
    → 设置。
    """
    _write_default_config(tmp_path)
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
        ai_orchestrator=FakeOrchestrator(),
    )
    qtbot.addWidget(win)
    sw = win.stackedWidget
    object_names = [sw.widget(i).objectName() for i in range(sw.count())]
    # AI 互动要在 第 5 位（原 全自动 位置）
    assert "aiPanelPage" in object_names, f"aiPanelPage not in sub pages: {object_names}"
    assert object_names.index("aiPanelPage") == 4, (
        f"AI 互动应在 index 4（原 全自动 位置），实际 {object_names.index('aiPanelPage')}: {object_names}"
    )


def test_ai_panel_history_max_lines_from_constructor(qtbot, tmp_path):
    """MainWindow 接受 `ai_history_max_lines` 参数并传给 AIPanelWidget。"""
    _write_default_config(tmp_path, history_max_lines=999)
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
        ai_orchestrator=FakeOrchestrator(),
        ai_history_max_lines=999,
    )
    qtbot.addWidget(win)
    panel = win._ai_panel_widget
    assert panel._history.document().maximumBlockCount() == 999
