import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QAbstractSpinBox, QSpinBox
from qfluentwidgets import SimpleExpandGroupSettingCard

from desktop_sprite.ui.config_editor import ConfigEditorWidget, _ConfigGroupCard, _ValueSettingCard


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
    section_titles = [
        section.card.titleLabel.text()
        for section in editor.findChildren(SimpleExpandGroupSettingCard)
    ]
    assert "DEFAULT" in section_titles
    assert "CHARACTERS" in section_titles
    assert "PET" in section_titles

    state = json.loads((tmp_path / "ui_state.json").read_text(encoding="utf-8"))
    expanded = state["settings"]["expanded"]
    assert expanded["default"] is True
    assert expanded["default.app"] is True
    assert expanded["default.physics"] is True
    assert expanded["default.character"] is True
    assert expanded["characters"] is False
    assert expanded["characters.pet"] is False
    assert expanded["characters.pet.flight"] is False


def test_config_editor_uses_fluent_numeric_inputs_without_step_buttons(tmp_path):
    _app()
    config_path, _profile_path = _write_config_tree(tmp_path)

    editor = ConfigEditorWidget(config_path)

    spins = editor.findChildren(QSpinBox)
    assert any(spin.value() == 60 for spin in spins)
    assert all(spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons for spin in spins)
    assert all(not spin.upButton.isVisible() and not spin.downButton.isVisible() for spin in spins)


def test_config_editor_uses_transparent_dark_theme_background(tmp_path):
    _app()
    config_path, _profile_path = _write_config_tree(tmp_path)

    editor = ConfigEditorWidget(config_path)

    assert not editor.scroll.viewport().autoFillBackground()
    assert not editor.content.autoFillBackground()
    assert "background: transparent" in editor.content.styleSheet()


def test_config_editor_indents_group_and_value_icons_by_depth(tmp_path):
    _app()
    config_path, _profile_path = _write_config_tree(tmp_path)

    editor = ConfigEditorWidget(config_path)
    groups = {group.card.titleLabel.text(): group for group in editor.findChildren(_ConfigGroupCard)}
    fps_card = next(card for card in editor.findChildren(_ValueSettingCard) if card.titleLabel.text() == "fps")

    assert groups["DEFAULT"].card.hBoxLayout.contentsMargins().left() == 16
    assert groups["APP"].card.hBoxLayout.contentsMargins().left() == 34
    assert fps_card.hBoxLayout.contentsMargins().left() == 52


def test_config_editor_saves_only_when_requested(tmp_path):
    _app()
    config_path, _profile_path = _write_config_tree(tmp_path)
    editor = ConfigEditorWidget(config_path)
    dirty_states: list[bool] = []
    editor.dirtyChanged.connect(dirty_states.append)
    spin = next(item for item in editor.findChildren(QSpinBox) if item.value() == 60)

    spin.setValue(75)

    assert json.loads(config_path.read_text(encoding="utf-8"))["app"]["fps"] == 60
    assert editor.is_dirty
    assert dirty_states == [True]

    assert editor.save()

    assert json.loads(config_path.read_text(encoding="utf-8"))["app"]["fps"] == 75
    assert not editor.is_dirty
    assert dirty_states == [True, False]


def test_config_editor_writes_user_config_without_changing_defaults(tmp_path):
    _app()
    config_path, profile_path = _write_config_tree(tmp_path)
    user_config_path = tmp_path / "user.json"
    editor = ConfigEditorWidget(config_path, user_config_path)
    spin = next(item for item in editor.findChildren(QSpinBox) if item.value() == 60)

    spin.setValue(75)

    assert editor.save()
    assert json.loads(config_path.read_text(encoding="utf-8"))["app"]["fps"] == 60
    assert json.loads(profile_path.read_text(encoding="utf-8"))["pet"]["width"] == 84
    user_config = json.loads(user_config_path.read_text(encoding="utf-8"))
    assert user_config["app"]["fps"] == 75
    assert user_config["pet"]["width"] == 84


def test_config_editor_restores_defaults_by_removing_user_config(tmp_path):
    _app()
    config_path, _profile_path = _write_config_tree(tmp_path)
    user_config_path = tmp_path / "user.json"
    user_config_path.write_text(json.dumps({"app": {"fps": 75}}), encoding="utf-8")

    editor = ConfigEditorWidget(config_path, user_config_path)
    assert any(item.value() == 75 for item in editor.findChildren(QSpinBox))

    assert editor.restore_defaults()

    assert not user_config_path.exists()
    assert not editor.is_dirty
    assert any(item.value() == 60 for item in editor.findChildren(QSpinBox))


def test_config_editor_undo_discards_pending_edits(tmp_path):
    _app()
    config_path, _profile_path = _write_config_tree(tmp_path)
    editor = ConfigEditorWidget(config_path)
    spin = next(item for item in editor.findChildren(QSpinBox) if item.value() == 60)

    spin.setValue(75)
    editor.undo_changes()

    assert not editor.is_dirty
    assert json.loads(config_path.read_text(encoding="utf-8"))["app"]["fps"] == 60
    assert any(item.value() == 60 for item in editor.findChildren(QSpinBox))
