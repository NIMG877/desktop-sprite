from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    DoubleSpinBox,
    FluentIcon as FIF,
    LineEdit,
    PlainTextEdit,
    SettingCard,
    SimpleExpandGroupSettingCard,
    SmoothScrollArea,
    SpinBox,
    SwitchButton,
)

from desktop_sprite.ui.ui_state_store import UiStateStore
from desktop_sprite.utils.safe_io import merge_dict


JsonPath = tuple[str, ...]
UI_STATE_FILENAME = "ui_state.json"
USER_CONFIG_DIRNAME = "user"


@dataclass(slots=True)
class _Document:
    label: str
    path: Path
    data: dict[str, Any]
    saved_data: dict[str, Any]


class ConfigEditorWidget(QWidget):
    dirtyChanged = Signal(bool)

    def __init__(
        self,
        config_path: str | Path,
        user_config_path: str | Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        if isinstance(user_config_path, QWidget) and parent is None:
            parent = user_config_path
            user_config_path = None
        super().__init__(parent)
        self.config_path = Path(config_path)
        self.user_config_path = Path(user_config_path) if user_config_path else None
        self.ui_state_path = self.config_path.parent / USER_CONFIG_DIRNAME / UI_STATE_FILENAME
        self.documents: list[_Document] = []
        self._value_setters: dict[tuple[Path, JsonPath], Callable[[Any], None]] = {}
        self._value_widgets: dict[tuple[Path, JsonPath], QWidget] = {}
        self._ui_state: dict[str, Any] = {}
        self._dirty = False

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(12)

        hint = BodyLabel("修改后点击保存并应用才会写入用户配置文件。", self)
        root_layout.addWidget(hint)

        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.content = QWidget(self.scroll)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 12, 0)
        self.content_layout.setSpacing(12)
        self.scroll.setWidget(self.content)
        self.scroll.enableTransparentBackground()
        self.scroll.viewport().setAutoFillBackground(False)
        self.content.setAutoFillBackground(False)
        root_layout.addWidget(self.scroll, 1)

        self.reload()

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def reload(self) -> None:
        try:
            self.documents = self._load_documents()
            self._ui_state = self._load_or_create_ui_state()
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "配置读取失败", str(exc))
            return

        self._build_tree()
        self._set_dirty(False)

    def save(self) -> bool:
        try:
            if self.user_config_path is None:
                for document in self.documents:
                    self._write_json_object(document.path, document.data)
            else:
                self._write_json_object(self.user_config_path, self._user_config_data())
            for document in self.documents:
                document.saved_data = copy.deepcopy(document.data)
        except (OSError, TypeError) as exc:
            QMessageBox.critical(self, "配置保存失败", str(exc))
            return False

        self._set_dirty(False)
        return True

    def restore_defaults(self) -> bool:
        try:
            if self.user_config_path is not None and self.user_config_path.exists():
                self.user_config_path.unlink()
            self.documents = self._load_documents()
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "默认配置恢复失败", str(exc))
            return False

        self._build_tree()
        self._set_dirty(False)
        return True

    def undo_changes(self) -> None:
        for document in self.documents:
            document.data = copy.deepcopy(document.saved_data)
            self._reset_document_editors(document)
        self._set_dirty(False)

    def _build_tree(self) -> None:
        self._value_setters.clear()
        self._value_widgets.clear()
        self.setUpdatesEnabled(False)
        try:
            self._clear_layout(self.content_layout)

            default_document = self.documents[0]
            self._add_config_node(
                self.content_layout,
                default_document,
                (),
                default_document.data,
                title="default",
                section_key="default",
            )

            profile_documents = self.documents[1:]
            if profile_documents:
                characters_section = self._create_section("characters", "characters", 0, self.content)
                for document in profile_documents:
                    profile_path, profile_data = self._profile_root(document)
                    self._add_config_node(
                        characters_section,
                        document,
                        profile_path,
                        profile_data,
                        title=document.label,
                        indent=1,
                        section_key=f"characters.{document.label}",
                    )
                self.content_layout.addWidget(characters_section)

            self.content_layout.addStretch(1)
        finally:
            self.setUpdatesEnabled(True)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def _load_documents(self) -> list[_Document]:
        root_data = self._load_json_object(self.config_path)
        user_data = (
            self._load_json_object(self.user_config_path)
            if self.user_config_path is not None and self.user_config_path.is_file()
            else None
        )
        if user_data is not None:
            self._apply_user_config_to_document(root_data, user_data)
        documents = [_Document("default", self.config_path, root_data, copy.deepcopy(root_data))]

        profile_files = root_data.get("character", {}).get("profile_files", {})
        if isinstance(profile_files, dict):
            for name, relative_path in profile_files.items():
                if not isinstance(relative_path, str):
                    continue
                profile_path = (self.config_path.parent / relative_path).resolve()
                if not profile_path.is_file():
                    continue
                data = self._load_json_object(profile_path)
                documents.append(_Document(name, profile_path, data, copy.deepcopy(data)))

        if user_data is not None:
            self._apply_user_config(documents, user_data)
            for document in documents:
                document.saved_data = copy.deepcopy(document.data)

        return documents

    def _apply_user_config(self, documents: list[_Document], user_data: dict[str, Any]) -> None:
        for document in documents:
            self._apply_user_config_to_document(document.data, user_data)

    def _apply_user_config_to_document(
        self,
        document_data: dict[str, Any],
        user_data: dict[str, Any],
    ) -> None:
        matching = {
            key: copy.deepcopy(value)
            for key, value in user_data.items()
            if key in document_data
        }
        merge_dict(document_data, matching)

    def _user_config_data(self) -> dict[str, Any]:
        data = copy.deepcopy(self.documents[0].data)
        for document in self.documents[1:]:
            merge_dict(data, document.data)
        return data

    def _load_or_create_ui_state(self) -> dict[str, Any]:
        section_defaults = self._section_default_states()
        # `UiStateStore.read()` returns `{}` on missing file or JSON error,
        # which is the same behaviour the local helper used to have.
        state = self._ui_state_store.read()
        settings = state.setdefault("settings", {})
        expanded = settings.setdefault("expanded", {})
        changed = False
        for key, default_value in section_defaults.items():
            if key not in expanded:
                expanded[key] = default_value
                changed = True
        stale_keys = [key for key in expanded if key not in section_defaults]
        for key in stale_keys:
            del expanded[key]
            changed = True
        if changed or not self.ui_state_path.is_file():
            # `state` already contains everything that was on disk plus
            # the merged section defaults; writing it preserves any
            # other top-level keys (e.g. `main_window`).
            self._ui_state_store.write(state)
        return state

    @property
    def _ui_state_store(self) -> UiStateStore:
        return UiStateStore(self.ui_state_path)

    def _section_default_states(self) -> dict[str, bool]:
        defaults: dict[str, bool] = {"default": True}
        root = self.documents[0].data
        for key, value in root.items():
            if isinstance(value, dict):
                defaults[f"default.{key}"] = True
                self._collect_section_defaults(value, f"default.{key}", defaults, default_open=False)

        profile_documents = self.documents[1:]
        if profile_documents:
            defaults["characters"] = False
        for document in profile_documents:
            _profile_path, profile_data = self._profile_root(document)
            base_key = f"characters.{document.label}"
            defaults[base_key] = False
            if isinstance(profile_data, dict):
                self._collect_section_defaults(profile_data, base_key, defaults, default_open=False)
        return defaults

    def _collect_section_defaults(
        self,
        data: dict[str, Any],
        prefix: str,
        defaults: dict[str, bool],
        *,
        default_open: bool,
    ) -> None:
        for key, value in data.items():
            if isinstance(value, dict):
                section_key = f"{prefix}.{key}"
                defaults[section_key] = default_open
                self._collect_section_defaults(value, section_key, defaults, default_open=default_open)

    def _profile_root(self, document: _Document) -> tuple[JsonPath, Any]:
        if document.label in document.data and isinstance(document.data[document.label], dict):
            return (document.label,), document.data[document.label]
        return (), document.data

    def _load_json_object(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError(f"{path} 顶层必须是 JSON 对象。")
        return data

    def _write_json_object(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")

    def _add_config_node(
        self,
        container: QVBoxLayout | "_ConfigGroupCard",
        document: _Document,
        path: JsonPath,
        value: Any,
        title: str | None = None,
        indent: int = 0,
        section_key: str | None = None,
    ) -> None:
        if isinstance(value, dict):
            key = section_key or ".".join(path)
            parent = container.parentWidget() if isinstance(container, QVBoxLayout) else container
            section = self._create_section(title or path[-1], key, indent, parent)
            for child_key, child_value in value.items():
                child_section_key = f"{key}.{child_key}" if key else child_key
                self._add_config_node(
                    section,
                    document,
                    (*path, child_key),
                    child_value,
                    indent=indent + 1,
                    section_key=child_section_key,
                )
            self._add_widget(container, section)
            return

        parent = container.parentWidget() if isinstance(container, QVBoxLayout) else container
        self._add_widget(container, self._create_value_row(document, path, value, indent, parent))

    def _add_widget(self, container: QVBoxLayout | "_ConfigGroupCard", widget: QWidget) -> None:
        if isinstance(container, QVBoxLayout):
            container.addWidget(widget)
        else:
            container.addGroupWidget(widget)

    def _create_section(
        self,
        title: str,
        key: str,
        indent: int,
        parent: QWidget | None,
    ) -> "_ConfigGroupCard":
        expanded = bool(self._ui_state.get("settings", {}).get("expanded", {}).get(key, False))
        section = _ConfigGroupCard(FIF.FOLDER, title.upper(), indent, parent=parent)
        section.expandChanged.connect(
            lambda value, section_key=key: self._set_section_expanded(section_key, value)
        )
        section.setExpand(expanded)
        return section

    def _set_section_expanded(self, key: str, expanded: bool) -> None:
        # `update` reads the current state (which may also hold
        # `main_window` and other top-level keys we don't own), hands
        # it to the mutator, then writes the result back. The mutator
        # is free to mutate in place and return None — the store
        # writes whatever it received.
        def mutate(state: dict[str, Any]) -> None:
            expanded_map = state.setdefault("settings", {}).setdefault("expanded", {})
            if expanded_map.get(key) == expanded:
                return
            expanded_map[key] = expanded

        self._ui_state_store.update(mutate)

    def _create_value_row(
        self,
        document: _Document,
        path: JsonPath,
        value: Any,
        indent: int,
        parent: QWidget | None,
    ) -> QWidget:
        editor = self._create_value_editor(document, path, value, parent)
        return _ValueSettingCard(FIF.EDIT, path[-1], editor, indent, parent)

    def _create_value_editor(self, document: _Document, path: JsonPath, value: Any, parent: QWidget) -> QWidget:
        if isinstance(value, bool):
            switch = SwitchButton(parent)
            switch.setChecked(value)
            switch.checkedChanged.connect(lambda checked: self._update_value(document, path, checked))
            self._track_value_editor(document, path, switch, switch.setChecked)
            return switch

        if isinstance(value, int):
            spin = _NoWheelSpinBox(parent)
            spin.setRange(-1_000_000_000, 1_000_000_000)
            spin.setValue(value)
            spin.valueChanged.connect(lambda new_value: self._update_value(document, path, new_value))
            self._track_value_editor(document, path, spin, spin.setValue)
            return spin

        if isinstance(value, float):
            spin = _NoWheelDoubleSpinBox(parent)
            spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
            spin.setDecimals(4)
            spin.setValue(value)
            spin.valueChanged.connect(lambda new_value: self._update_value(document, path, new_value))
            self._track_value_editor(document, path, spin, spin.setValue)
            return spin

        if isinstance(value, str):
            line = LineEdit(parent)
            line.setText(value)
            line.editingFinished.connect(lambda: self._update_value(document, path, line.text()))
            self._track_value_editor(document, path, line, lambda new_value, widget=line: widget.setText(str(new_value)))
            return line

        editor = PlainTextEdit(parent)
        editor.setPlainText(json.dumps(value, ensure_ascii=False, indent=2))
        editor.setMinimumHeight(82)
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        timer = QTimer(editor)
        timer.setSingleShot(True)
        timer.setInterval(450)
        timer.timeout.connect(lambda: self._commit_json_text(editor, document, path))
        editor.textChanged.connect(timer.start)
        self._track_value_editor(
            document,
            path,
            editor,
            lambda new_value, widget=editor: widget.setPlainText(json.dumps(new_value, ensure_ascii=False, indent=2)),
        )
        return editor

    def _track_value_editor(
        self,
        document: _Document,
        path: JsonPath,
        widget: QWidget,
        setter: Callable[[Any], None],
    ) -> None:
        key = (document.path, path)
        self._value_widgets[key] = widget
        self._value_setters[key] = setter

    def _commit_json_text(self, editor: PlainTextEdit, document: _Document, path: JsonPath) -> None:
        try:
            value = json.loads(editor.toPlainText())
        except json.JSONDecodeError:
            return
        self._update_value(document, path, value)

    def _update_value(self, document: _Document, path: JsonPath, value: Any) -> None:
        parent = document.data
        for key in path[:-1]:
            parent = parent[key]
        if parent[path[-1]] == value:
            return
        parent[path[-1]] = value
        self._set_dirty(self._has_unsaved_changes())

    def _has_unsaved_changes(self) -> bool:
        return any(document.data != document.saved_data for document in self.documents)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirtyChanged.emit(dirty)

    def _reset_document_editors(self, document: _Document) -> None:
        for path, value in self._iter_leaf_values(document.data):
            key = (document.path, path)
            setter = self._value_setters.get(key)
            if setter is None:
                continue
            widget = self._value_widgets.get(key)
            if widget is not None:
                widget.blockSignals(True)
            setter(value)
            if widget is not None:
                widget.blockSignals(False)

    def _iter_leaf_values(self, data: dict[str, Any], path: JsonPath = ()):
        for key, value in data.items():
            current_path = (*path, key)
            if isinstance(value, dict):
                yield from self._iter_leaf_values(value, current_path)
            else:
                yield current_path, value

class _ConfigGroupCard(SimpleExpandGroupSettingCard):
    expandChanged = Signal(bool)
    heightChanged = Signal()

    def __init__(self, icon, title: str, indent: int, parent: QWidget | None = None) -> None:
        super().__init__(icon, title, parent=parent)
        self.indent = indent
        self.card.hBoxLayout.setContentsMargins(16 + indent * 18, 0, 0, 0)

    def setExpand(self, is_expand: bool) -> None:
        changed = self.isExpand != is_expand
        super().setExpand(is_expand)
        if changed:
            self.expandChanged.emit(is_expand)

    def addGroupWidget(self, widget: QWidget) -> None:
        super().addGroupWidget(widget)
        if isinstance(widget, _ConfigGroupCard):
            widget.heightChanged.connect(self._adjustViewSize)

    def _onExpandValueChanged(self) -> None:
        super()._onExpandValueChanged()
        self.heightChanged.emit()

    def _adjustViewSize(self) -> None:
        super()._adjustViewSize()
        self.heightChanged.emit()


class _ValueSettingCard(SettingCard):
    def __init__(
        self,
        icon,
        title: str,
        editor: QWidget,
        indent: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(icon, title, parent=parent)
        self.indent = indent
        self.hBoxLayout.setContentsMargins(16 + indent * 18, 0, 0, 0)
        self.editor = editor
        self.editor.setParent(self)
        self.hBoxLayout.addWidget(self.editor)
        self.hBoxLayout.addSpacing(16)

    def paintEvent(self, event) -> None:
        pass


class _NoWheelSpinBox(SpinBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSymbolVisible(False)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

    def wheelEvent(self, event) -> None:
        event.ignore()


class _NoWheelDoubleSpinBox(DoubleSpinBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSymbolVisible(False)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

    def wheelEvent(self, event) -> None:
        event.ignore()


