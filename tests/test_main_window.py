import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from desktop_sprite.ui.config_editor import ConfigEditorWidget
from desktop_sprite.ui.main_window import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_embeds_config_editor_in_settings(tmp_path):
    _app()
    config_path = tmp_path / "default.json"
    config_path.write_text(
        json.dumps(
            {
                "app": {"fps": 60},
                "character": {"profile_files": {}},
            }
        ),
        encoding="utf-8",
    )

    window = MainWindow(config_path, on_set_target=lambda: None, on_show=lambda: None)
    window.show_settings()

    assert window.stackedWidget.currentWidget() is window.settings_page
    assert window.findChild(ConfigEditorWidget) is not None


def test_main_window_creates_config_editor_on_startup(tmp_path):
    _app()
    config_path = tmp_path / "default.json"
    config_path.write_text(
        json.dumps(
            {
                "app": {"fps": 60},
                "character": {"profile_files": {}},
            }
        ),
        encoding="utf-8",
    )

    window = MainWindow(config_path, on_set_target=lambda: None, on_show=lambda: None)

    assert window.findChild(ConfigEditorWidget) is not None
    assert (tmp_path / "ui_state.json").exists()

    window.show_settings()

    assert window.findChild(ConfigEditorWidget) is not None
    assert (tmp_path / "ui_state.json").exists()


def test_main_window_has_restart_and_quit_actions(tmp_path):
    _app()
    config_path = tmp_path / "default.json"
    config_path.write_text(
        json.dumps(
            {
                "app": {"fps": 60},
                "character": {"profile_files": {}},
            }
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    window = MainWindow(
        config_path,
        on_set_target=lambda: None,
        on_show=lambda: None,
        on_restart=lambda: calls.append("restart"),
        on_apply_config=lambda: calls.append("apply"),
        on_quit=lambda: calls.append("quit"),
    )
    buttons = {button.text(): button for button in window.findChildren(QPushButton)}

    buttons["重启"].click()
    buttons["退出"].click()

    assert calls == ["restart", "quit"]


def test_main_window_realtime_sleep_action_calls_callback(tmp_path):
    _app()
    config_path = tmp_path / "default.json"
    config_path.write_text(
        json.dumps(
            {
                "app": {"fps": 60},
                "character": {"profile_files": {}},
            }
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    window = MainWindow(
        config_path,
        on_set_target=lambda: None,
        on_show=lambda: None,
        on_sleep=lambda: calls.append("sleep"),
    )
    buttons = {button.text(): button for button in window.findChildren(QPushButton)}

    buttons["睡觉"].click()

    assert calls == ["sleep"]


def test_main_window_enables_config_actions_only_when_dirty(tmp_path):
    _app()
    config_path = tmp_path / "default.json"
    config_path.write_text(
        json.dumps(
            {
                "app": {"fps": 60},
                "character": {"profile_files": {}},
            }
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    window = MainWindow(
        config_path,
        on_set_target=lambda: None,
        on_show=lambda: None,
        on_apply_config=lambda: calls.append("apply"),
    )
    buttons = {button.text(): button for button in window.findChildren(QPushButton)}
    assert not buttons["保存并应用"].isEnabled()
    assert not buttons["撤销修改"].isEnabled()

    window.show_settings()
    line = next(item for item in window.findChildren(QLineEdit) if item.text() == "60")
    line.setText("75")
    line.editingFinished.emit()

    assert buttons["保存并应用"].isEnabled()
    assert buttons["撤销修改"].isEnabled()

    buttons["保存并应用"].click()

    assert calls == ["apply"]
    assert not buttons["保存并应用"].isEnabled()
    assert not buttons["撤销修改"].isEnabled()
