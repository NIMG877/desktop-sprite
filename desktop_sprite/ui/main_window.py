from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    ComboBox,
    FluentIcon as FIF,
    FluentWindow,
    NavigationItemPosition,
    PrimaryPushButton,
    PushButton,
    SubtitleLabel,
    Theme,
    TitleLabel,
    setTheme,
)

from desktop_sprite.models.inventory import InventorySnapshot
from desktop_sprite.models.pet_attribute import PetAttributeSheet
from desktop_sprite.models.spirit_mark import SpiritMarkInventory
from desktop_sprite.ui.config_editor import ConfigEditorWidget, UI_STATE_FILENAME, USER_CONFIG_DIRNAME
from desktop_sprite.ui.debug_widget import DebugWidget
from desktop_sprite.ui.growth_widget import PetGrowthWidget
from desktop_sprite.ui.inventory_widget import InventoryWidget
from desktop_sprite.ui.ui_state_store import UiStateStore


# Display label → qfluentwidgets.Theme enum. The dict's iteration order
# defines the order the home-page ComboBox shows options to the user;
# the keys are also the strings persisted in ``ui_state.json``.
_THEME_OPTIONS: dict[str, Theme] = {
    "深色": Theme.DARK,
    "浅色": Theme.LIGHT,
    "跟随系统": Theme.AUTO,
}


class MainWindow(FluentWindow):

    def __init__(
        self,
        config_path: str | Path,
        on_set_target: Callable[[], None],
        on_show: Callable[[], None],
        on_sleep: Callable[[], None] | None = None,
        user_config_path: str | Path | None = None,
        on_restart: Callable[[], None] | None = None,
        on_apply_config: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        inventory_snapshot: InventorySnapshot | None = None,
        spirit_mark_inventory: SpiritMarkInventory | None = None,
        pet_attribute_sheet: PetAttributeSheet | None = None,
        on_spirit_marks_changed: Callable[[SpiritMarkInventory], None] | None = None,
        on_debug_request_spirit_mark: Callable[[], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        # Placeholder until `ui_state_path` is set below; `_load_saved_theme`
        # will read the persisted choice (or fall back to DARK) and apply it.
        self._current_theme: Theme = Theme.DARK
        super().__init__(parent)
        # Half the qfluentwidgets default expand-width (322 → 160). The
        # default leaves the nav so wide that the four-character labels
        # ("实时触发" etc.) sit in a column of empty space.
        self.navigationInterface.setExpandWidth(160)
        self.config_path = Path(config_path)
        self.user_config_path = Path(user_config_path) if user_config_path else None
        self.ui_state_path = self.config_path.parent / USER_CONFIG_DIRNAME / UI_STATE_FILENAME
        # Restore the previously selected theme and apply it before any child
        # widget (including the home-page ComboBox) is created. The
        # `currentTextChanged` signal fires on initial `setCurrentText` and
        # bails on the equality check below, so this explicit `setTheme`
        # call is what actually paints the window in the saved theme.
        self._current_theme = self._load_saved_theme()
        setTheme(self._current_theme)
        self.on_set_target = on_set_target
        self.on_show = on_show
        self.on_sleep = on_sleep or (lambda: None)
        self.on_restart = on_restart or QApplication.quit
        self.on_apply_config = on_apply_config or self.on_restart
        self.on_quit = on_quit or QApplication.quit
        self.config_editor: ConfigEditorWidget | None = None
        self.restore_defaults_button: PushButton | None = None
        self.save_apply_button: PrimaryPushButton | None = None
        self.undo_button: PushButton | None = None
        self.settings_layout: QVBoxLayout | None = None
        self._target_initial_size = QSize(1120, 720)

        self.setWindowTitle("Desktop Sprite")
        self.setMinimumSize(920, 560)

        self.home_page = self._create_home_page()
        self.realtime_page = self._create_realtime_page()
        inventory = inventory_snapshot or InventorySnapshot.empty()
        self.growth_page = PetGrowthWidget(
            inventory,
            spirit_mark_inventory or SpiritMarkInventory(),
            pet_attribute_sheet,
            on_spirit_marks_changed,
        )
        self.inventory_page = InventoryWidget(inventory)
        self.debug_page = DebugWidget(on_debug_request_spirit_mark)
        self.settings_page = self._create_settings_page()

        self._add_interfaces()
        self._ensure_config_editor()
        self._apply_initial_window_size()
        self._saved_geometry = self._load_saved_geometry()

    def show_settings(self) -> None:
        self._select_settings()
        self._show_window()

    def open_home(self) -> None:
        self.switchTo(self.home_page)
        self._show_window()

    def _show_window(self) -> None:
        if not self.isVisible() and self._saved_geometry is not None:
            self.restoreGeometry(self._saved_geometry)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        self._save_window_geometry()
        event.ignore()
        self.hide()

    def _apply_initial_window_size(self) -> None:
        if self.layout() is not None:
            self.layout().activate()
        size = self._target_initial_size.expandedTo(self.minimumSizeHint())
        size = size.expandedTo(self.minimumSize())
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            size = size.boundedTo(screen.availableGeometry().size())
            size = size.expandedTo(self.minimumSize())
        self.resize(size)

    def _load_saved_geometry(self) -> QByteArray | None:
        state = self._ui_state_store.read()
        main_window_state = state.get("main_window")
        if not isinstance(main_window_state, dict):
            return None
        encoded = main_window_state.get("geometry")
        if not isinstance(encoded, str):
            return None
        try:
            geometry = QByteArray.fromBase64(encoded.encode("ascii"))
        except UnicodeEncodeError:
            return None
        return geometry if not geometry.isEmpty() else None

    def _save_window_geometry(self) -> None:
        self._saved_geometry = self.saveGeometry()
        encoded = bytes(self._saved_geometry.toBase64()).decode("ascii")

        def mutate(state: dict) -> None:
            state.setdefault("main_window", {})["geometry"] = encoded

        self._ui_state_store.update(mutate)

    @property
    def _ui_state_store(self) -> UiStateStore:
        return UiStateStore(self.ui_state_path)

    def _add_interfaces(self) -> None:
        pages = [
            (self.home_page, FIF.PLAY, "启动", NavigationItemPosition.TOP),
            (self.realtime_page, FIF.SYNC, "实时触发", NavigationItemPosition.TOP),
            (self.growth_page, FIF.CHECKBOX, "养成", NavigationItemPosition.TOP),
            (self.inventory_page, FIF.SHOPPING_CART, "背包", NavigationItemPosition.TOP),
            (self._create_placeholder_page("全自动", "这里可以管理自动运行策略。"), FIF.ROBOT, "全自动", NavigationItemPosition.TOP),
            (self._create_placeholder_page("辅助操控", "这里可以放桌宠移动、展示和目标选择控制。"), FIF.GAME, "辅助操控", NavigationItemPosition.TOP),
            (self.debug_page, FIF.SPEED_HIGH, "调试", NavigationItemPosition.TOP),
            (self._create_placeholder_page("通知", "这里可以管理提醒和消息。"), FIF.RINGER, "通知", NavigationItemPosition.TOP),
            (self.settings_page, FIF.SETTING, "设置", NavigationItemPosition.BOTTOM),
        ]
        for page, icon, title, position in pages:
            self.addSubInterface(page, icon, title, position)

    def _select_settings(self) -> None:
        self._ensure_config_editor()
        self.switchTo(self.settings_page)

    def update_inventory_and_spirit_marks(
        self,
        inventory_snapshot: InventorySnapshot,
        spirit_mark_inventory: SpiritMarkInventory,
    ) -> None:
        self.inventory_page.set_snapshot(inventory_snapshot)
        self.growth_page.set_data(inventory_snapshot, spirit_mark_inventory)

    def _create_home_page(self) -> QWidget:
        page = self._page("homePage")
        layout = page.layout()
        layout.addWidget(self._hero())
        layout.addWidget(self._create_theme_row())
        layout.addWidget(
            self._action_card(
                "重启桌宠",
                "重新启动桌宠运行实例，管理界面保持打开。",
                "重启",
                self.on_restart,
                FIF.SYNC,
                primary=True,
            )
        )
        layout.addWidget(
            self._action_card(
                "退出应用",
                "关闭桌宠和管理界面。",
                "退出",
                self.on_quit,
                FIF.POWER_BUTTON,
            )
        )
        layout.addStretch(1)
        return page

    def _create_theme_row(self) -> QWidget:
        """Inline row with a `主题` label + ComboBox; switches the qfluentwidgets
        theme live. Session-only — not persisted to disk."""

        card = CardWidget()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.addWidget(SubtitleLabel("主题", card))
        body = BodyLabel("切换 Fluent 界面主题，立即生效，仅本次会话有效。", card)
        body.setWordWrap(True)
        text_layout.addWidget(body)
        layout.addLayout(text_layout, 1)

        self.theme_combo = ComboBox(card)
        for label in _THEME_OPTIONS:
            self.theme_combo.addItem(label)
        self.theme_combo.setCurrentText(self._label_for_theme(self._current_theme))
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        layout.addWidget(self.theme_combo)
        return card

    def _on_theme_changed(self, label: str) -> None:
        # The ComboBox only ever feeds us labels that came from
        # `_THEME_OPTIONS`, so a KeyError here would mean the dict and
        # the dropdown have drifted out of sync — fail loudly in that
        # case rather than silently no-op.
        theme = _THEME_OPTIONS[label]
        if theme == self._current_theme:
            return
        self._current_theme = theme
        setTheme(theme)
        self._save_theme(theme)

    @staticmethod
    def _label_for_theme(theme: Theme) -> str:
        for label, candidate in _THEME_OPTIONS.items():
            if candidate == theme:
                return label
        return next(iter(_THEME_OPTIONS))

    def _load_saved_theme(self) -> Theme:
        state = self._ui_state_store.read()
        return self._theme_for_label(state.get("theme")) or Theme.DARK

    def _save_theme(self, theme: Theme) -> None:
        label = self._label_for_theme(theme)

        def mutate(state: dict) -> None:
            state["theme"] = label

        self._ui_state_store.update(mutate)

    @staticmethod
    def _theme_for_label(label: object) -> Theme | None:
        if not isinstance(label, str):
            return None
        return _THEME_OPTIONS.get(label)

    def _create_realtime_page(self) -> QWidget:
        page = self._page("realtimePage")
        layout = page.layout()
        layout.addWidget(TitleLabel("实时触发", page))
        layout.addWidget(
            self._action_card(
                "展示桌宠",
                "执行当前桌宠的展示动作。",
                "展示",
                self.on_show,
                FIF.PLAY,
                primary=True,
            )
        )
        layout.addWidget(
            self._action_card(
                "设置目标点",
                "在桌面上选择一个目标位置，让桌宠前往。",
                "选择",
                self.on_set_target,
                FIF.GAME,
            )
        )
        layout.addWidget(
            self._action_card(
                "让桌宠睡觉",
                "让当前处于空闲或行走状态的桌宠停下来睡觉。",
                "睡觉",
                self.on_sleep,
                FIF.RINGER,
            )
        )
        layout.addStretch(1)
        return page

    def _create_settings_page(self) -> QWidget:
        page = self._page("settingsPage")
        layout = page.layout()
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(TitleLabel("设置", page))
        header.addStretch(1)

        self.restore_defaults_button = PushButton(FIF.SYNC, "恢复默认配置", page)
        self.restore_defaults_button.clicked.connect(self._restore_default_config)
        header.addWidget(self.restore_defaults_button)

        self.undo_button = PushButton(FIF.RETURN, "撤销修改", page)
        self.undo_button.clicked.connect(self._undo_config_changes)
        self.undo_button.setEnabled(False)
        header.addWidget(self.undo_button)

        self.save_apply_button = PrimaryPushButton(FIF.SAVE, "保存并应用", page)
        self.save_apply_button.clicked.connect(self._save_and_apply_config)
        self.save_apply_button.setEnabled(False)
        header.addWidget(self.save_apply_button)

        layout.addLayout(header)
        layout.addStretch(1)
        self.settings_layout = layout
        return page

    def _create_placeholder_page(self, title: str, description: str) -> QWidget:
        page = self._page(f"{title}Page")
        layout = page.layout()
        layout.addWidget(TitleLabel(title, page))
        body = BodyLabel(description, page)
        body.setWordWrap(True)
        layout.addWidget(body)
        layout.addStretch(1)
        return page

    def _page(self, object_name: str) -> QWidget:
        page = QWidget()
        page.setObjectName(object_name)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 80, 48, 32)
        layout.setSpacing(16)
        return page

    def _hero(self) -> CardWidget:
        hero = CardWidget()
        hero.setMinimumHeight(180)
        hero.setObjectName("heroCard")
        layout = QVBoxLayout(hero)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.addStretch(1)
        layout.addWidget(TitleLabel("Desktop Sprite", hero))
        layout.addWidget(SubtitleLabel("桌宠运行、行为控制与配置管理", hero))
        return hero

    def _action_card(
        self,
        title: str,
        description: str,
        button_text: str,
        callback: Callable[[], None],
        icon,
        *,
        primary: bool = False,
    ) -> CardWidget:
        card = CardWidget()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(18)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        text_layout.addWidget(SubtitleLabel(title, card))
        body = BodyLabel(description, card)
        body.setWordWrap(True)
        text_layout.addWidget(body)
        layout.addLayout(text_layout, 1)

        button_class = PrimaryPushButton if primary else PushButton
        button = button_class(icon, button_text, card)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return card

    def _ensure_config_editor(self) -> None:
        if self.config_editor is not None or self.settings_layout is None:
            return
        stretch = self.settings_layout.takeAt(self.settings_layout.count() - 1)
        if stretch is not None:
            del stretch
        self.config_editor = ConfigEditorWidget(
            self.config_path,
            self.user_config_path,
            self.settings_page,
        )
        self.config_editor.dirtyChanged.connect(self._set_config_actions_enabled)
        self.settings_layout.addWidget(self.config_editor, 1)

    def _set_config_actions_enabled(self, enabled: bool) -> None:
        if self.save_apply_button is not None:
            self.save_apply_button.setEnabled(enabled)
        if self.undo_button is not None:
            self.undo_button.setEnabled(enabled)

    def _save_and_apply_config(self) -> None:
        if self.config_editor is None:
            return
        if self.config_editor.save():
            self.on_apply_config()

    def _undo_config_changes(self) -> None:
        if self.config_editor is not None:
            self.config_editor.undo_changes()

    def _restore_default_config(self) -> None:
        self._ensure_config_editor()
        if self.config_editor is not None and self.config_editor.restore_defaults():
            self.on_apply_config()
