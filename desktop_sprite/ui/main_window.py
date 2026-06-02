from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QTimer, QSize
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
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
from desktop_sprite.ui.config_editor import ConfigEditorWidget
from desktop_sprite.ui.inventory_widget import InventoryWidget


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
        parent: QWidget | None = None,
    ) -> None:
        setTheme(Theme.DARK)
        super().__init__(parent)
        self.config_path = Path(config_path)
        self.user_config_path = Path(user_config_path) if user_config_path else None
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
        self._initial_size_applied = False
        self._target_initial_size = QSize(1120, 720)

        self.setWindowTitle("Desktop Sprite")
        self.setMinimumSize(920, 560)
        self.resize(self._target_initial_size)

        self.home_page = self._create_home_page()
        self.realtime_page = self._create_realtime_page()
        self.inventory_page = InventoryWidget(inventory_snapshot or InventorySnapshot.empty())
        self.settings_page = self._create_settings_page()

        self._add_interfaces()
        self._ensure_config_editor()

    def show_settings(self) -> None:
        self._select_settings()
        self.show()
        self.raise_()
        self.activateWindow()

    def open_home(self) -> None:
        self.switchTo(self.home_page)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._initial_size_applied:
            return
        self._initial_size_applied = True
        QTimer.singleShot(0, self._apply_initial_window_size)
        QTimer.singleShot(60, self._apply_initial_window_size)

    def _apply_initial_window_size(self) -> None:
        if self.isMaximized() or self.size() == self._target_initial_size:
            return
        center = self.frameGeometry().center()
        self.resize(self._target_initial_size)
        frame = self.frameGeometry()
        frame.moveCenter(center)
        self.move(frame.topLeft())

    def _add_interfaces(self) -> None:
        pages = [
            (self.home_page, FIF.PLAY, "启动", NavigationItemPosition.TOP),
            (self.realtime_page, FIF.SYNC, "实时触发", NavigationItemPosition.TOP),
            (self._create_placeholder_page("独立任务", "这里可以管理一次性任务、脚本和桌宠行为队列。"), FIF.CHECKBOX, "独立任务", NavigationItemPosition.TOP),
            (self.inventory_page, FIF.SHOPPING_CART, "背包", NavigationItemPosition.TOP),
            (self._create_placeholder_page("全自动", "这里可以管理自动运行策略。"), FIF.ROBOT, "全自动", NavigationItemPosition.TOP),
            (self._create_placeholder_page("辅助操控", "这里可以放桌宠移动、展示和目标选择控制。"), FIF.GAME, "辅助操控", NavigationItemPosition.TOP),
            (self._create_placeholder_page("快捷键", "这里可以配置全局快捷键。"), FIF.SPEED_HIGH, "快捷键", NavigationItemPosition.TOP),
            (self._create_placeholder_page("通知", "这里可以管理提醒和消息。"), FIF.RINGER, "通知", NavigationItemPosition.TOP),
            (self.settings_page, FIF.SETTING, "设置", NavigationItemPosition.BOTTOM),
        ]
        for page, icon, title, position in pages:
            self.addSubInterface(page, icon, title, position)

    def _select_settings(self) -> None:
        self._ensure_config_editor()
        self.switchTo(self.settings_page)

    def _create_home_page(self) -> QWidget:
        page = self._page("homePage")
        layout = page.layout()
        layout.addWidget(self._hero())
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
