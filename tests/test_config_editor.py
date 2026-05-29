import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit, QSpinBox, QToolButton

from desktop_sprite.ui.config_editor import ConfigEditorWidget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _write_config_tree(tmp_path):
    profile_dir = tmp_path / "characters"
    profile_dir.mkdir()
    profile_path = profile_dir / "pet.json"
    profile_path.write_text(
        json.dumps({"pet": {"width": 84, "flight": {"speed": 380}}}),
        encoding="utf-8",
    )
    config_path = tmp_path / "default.json"
    config_path.write_text(
        json.dumps(
            {
                "app": {"fps": 60},
                "physics": {"gravity": 1800},
                "character": {"profile_files": {"pet": "characters/pet.json"}},
            }
        ),
        encoding="utf-8",
    )
    return config_path, profile_path


def test_config_editor_discovers_profile_files_and_creates_ui_state(tmp_path):
    _app()
    config_path, profile_path = _write_config_tree(tmp_path)

    editor = ConfigEditorWidget(config_path)

    assert [document.path for document in editor.documents] == [config_path, profile_path.resolve()]
    section_titles = [button.text() for button in editor.findChildren(QToolButton)]
    assert "default" in section_titles
    assert "characters" in section_titles
    assert "pet" in section_titles

    state = json.loads((tmp_path / "ui_state.json").read_text(encoding="utf-8"))
    expanded = state["settings"]["expanded"]
    assert expanded["default"] is True
    assert expanded["default.app"] is True
    assert expanded["default.physics"] is True
    assert expanded["default.character"] is True
    assert expanded["characters"] is False
    assert expanded["characters.pet"] is False
    assert expanded["characters.pet.flight"] is False


def test_config_editor_uses_plain_numeric_inputs(tmp_path):
    _app()
    config_path, _profile_path = _write_config_tree(tmp_path)

    editor = ConfigEditorWidget(config_path)

    assert editor.findChildren(QSpinBox) == []
    assert any(line.text() == "60" for line in editor.findChildren(QLineEdit))


def test_config_editor_saves_only_when_requested(tmp_path):
    _app()
    config_path, _profile_path = _write_config_tree(tmp_path)
    editor = ConfigEditorWidget(config_path)
    dirty_states: list[bool] = []
    editor.dirtyChanged.connect(dirty_states.append)
    line = next(item for item in editor.findChildren(QLineEdit) if item.text() == "60")

    line.setText("75")
    line.editingFinished.emit()

    assert json.loads(config_path.read_text(encoding="utf-8"))["app"]["fps"] == 60
    assert editor.is_dirty
    assert dirty_states == [True]

    assert editor.save()

    assert json.loads(config_path.read_text(encoding="utf-8"))["app"]["fps"] == 75
    assert not editor.is_dirty
    assert dirty_states == [True, False]


def test_config_editor_undo_discards_pending_edits(tmp_path):
    _app()
    config_path, _profile_path = _write_config_tree(tmp_path)
    editor = ConfigEditorWidget(config_path)
    line = next(item for item in editor.findChildren(QLineEdit) if item.text() == "60")

    line.setText("75")
    line.editingFinished.emit()
    editor.undo_changes()

    assert not editor.is_dirty
    assert json.loads(config_path.read_text(encoding="utf-8"))["app"]["fps"] == 60
    assert any(item.text() == "60" for item in editor.findChildren(QLineEdit))
