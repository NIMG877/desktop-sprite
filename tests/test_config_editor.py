import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QAbstractSpinBox, QSpinBox
from qfluentwidgets import SimpleExpandGroupSettingCard

from desktop_sprite.utils.config import load_config
from desktop_sprite.ui.config_editor import ConfigEditorWidget, _ConfigGroupCard, _ValueSettingCard


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _write_config_tree(tmp_path):
    profile_dir = tmp_path / "characters"
    profile_dir.mkdir()
    profile_path = profile_dir / "pet.json"
    profile_path.write_text(
        json.dumps({"pet": {"width": 84, "walk_speed": 140, "flight": {"speed": 380}}}),
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


def test_load_config_maps_character_pet_motion_fields_to_physics(tmp_path):
    profile_dir = tmp_path / "characters"
    profile_dir.mkdir()
    (profile_dir / "pet.json").write_text(
        json.dumps(
            {
                "pet": {
                    "width": 84,
                    "height": 104,
                    "default_spawn_x": 300,
                    "default_spawn_y": 300,
                    "walk_speed": 140,
                    "climb_speed": 96,
                    "jump_speed_x": 210,
                    "jump_speed_y": -560,
                }
            }
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "default.json"
    config_path.write_text(
        json.dumps(
            {
                "app": {"fps": 60, "always_on_top": True, "debug_draw": False, "log_level": "INFO"},
                "pet": {"width": 1, "height": 1, "default_spawn_x": 0, "default_spawn_y": 0},
                "physics": {
                    "gravity": 1800,
                    "max_fall_speed": 1100,
                    "drag_throw_factor": 0.65,
                    "edge_snap_distance": 10,
                },
                "behavior": {
                    "idle_min_seconds": 1.0,
                    "idle_max_seconds": 2.5,
                    "sleep_after_seconds": 120,
                    "prefer_foreground_window": True,
                    "target_repick_seconds": 3.5,
                },
                "attributes": {
                    "wander": 100,
                    "vigor": 210,
                    "recovery": 5,
                    "awareness": 100,
                    "focus": 2,
                    "satiety": 100,
                    "spark": 5,
                    "radiance": 50,
                    "trail": 0,
                    "resonance": 0,
                    "aura": 50,
                    "arcana": 100,
                    "attunement": 100,
                },
                "interaction": {
                    "draggable": True,
                    "throw_enabled": True,
                    "click_reaction": True,
                    "mouse_hover_reaction": True,
                    "target_search_down_distance": 220,
                    "target_search_up_distance": 80,
                },
                "character": {"default_type": "pet", "profile_files": {"pet": "characters/pet.json"}},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.physics.walk_speed == 140
    assert config.physics.climb_speed == 96
    assert config.physics.jump_speed_x == 210
    assert config.physics.jump_speed_y == -560


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

    state = json.loads((tmp_path / "user" / "ui_state.json").read_text(encoding="utf-8"))
    expanded = state["settings"]["expanded"]
    assert expanded["default"] is True
    assert expanded["default.app"] is True
    assert expanded["default.physics"] is True
    assert expanded["default.character"] is True
    assert expanded["characters"] is False
    assert expanded["characters.pet"] is False
    assert expanded["characters.pet.flight"] is False


def test_config_editor_preserves_main_window_geometry_in_ui_state(tmp_path):
    _app()
    config_path, _profile_path = _write_config_tree(tmp_path)
    state_path = tmp_path / "user" / "ui_state.json"
    state_path.parent.mkdir()
    state_path.write_text(
        json.dumps({"main_window": {"geometry": "saved-geometry"}}),
        encoding="utf-8",
    )

    editor = ConfigEditorWidget(config_path)
    editor._set_section_expanded("default", False)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["main_window"]["geometry"] == "saved-geometry"


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
