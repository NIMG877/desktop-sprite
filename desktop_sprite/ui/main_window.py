from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from desktop_sprite.ui.config_editor import ConfigEditorWidget


class MainWindow(QMainWindow):
    def __init__(
        self,
        config_path: str | Path,
        on_set_target: Callable[[], None],
        on_show: Callable[[], None],
        user_config_path: str | Path | None = None,
        on_restart: Callable[[], None] | None = None,
        on_apply_config: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config_path = Path(config_path)
        self.user_config_path = Path(user_config_path) if user_config_path else None
        self.on_set_target = on_set_target
        self.on_show = on_show
        self.on_restart = on_restart or QApplication.quit
        self.on_apply_config = on_apply_config or self.on_restart
        self.on_quit = on_quit or QApplication.quit
        self.config_editor: ConfigEditorWidget | None = None
        self.restore_defaults_button: QPushButton | None = None
        self.save_apply_button: QPushButton | None = None
        self.undo_button: QPushButton | None = None
        self.settings_page: QWidget | None = None
        self.settings_layout: QVBoxLayout | None = None
        self.sidebar_expanded = True
        self.sidebar_animation: QPropertyAnimation | None = None

        self.setWindowTitle("Desktop Sprite")
        self.resize(1120, 720)
        self.setMinimumSize(920, 560)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar_container = QWidget()
        self.sidebar_container.setObjectName("sidebarContainer")
        self.sidebar_container.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self.sidebar_container)
        sidebar_layout.setContentsMargins(0, 72, 0, 16)
        sidebar_layout.setSpacing(8)

        self.sidebar_toggle = QToolButton()
        self.sidebar_toggle.setObjectName("sidebarToggle")
        self.sidebar_toggle.setIcon(self._icon("menu"))
        self.sidebar_toggle.setIconSize(QSize(20, 20))
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)
        sidebar_layout.addWidget(self.sidebar_toggle)

        self.sidebar = QListWidget()
        self.sidebar.setIconSize(QSize(20, 20))
        self.sidebar.setObjectName("sidebar")
        sidebar_layout.addWidget(self.sidebar, 1)

        self.settings_nav = QListWidget()
        self.settings_nav.setIconSize(QSize(20, 20))
        self.settings_nav.setObjectName("settingsNav")
        self.settings_nav.setFixedHeight(52)
        sidebar_layout.addWidget(self.settings_nav)

        root.addWidget(self.sidebar_container)

        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        root.addWidget(self.stack, 1)

        self.setCentralWidget(central)
        self._build_pages()
        self._apply_style()

        self.sidebar.currentRowChanged.connect(self._switch_page)
        self.settings_nav.currentRowChanged.connect(self._switch_to_settings)
        self.sidebar.setCurrentRow(0)

    def show_settings(self) -> None:
        self._select_settings()
        self.show()
        self.raise_()
        self.activateWindow()

    def open_home(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()

    def _toggle_sidebar(self) -> None:
        self.sidebar_expanded = not self.sidebar_expanded
        collapsed = not self.sidebar_expanded
        end_width = 220 if self.sidebar_expanded else 68
        self.sidebar.setProperty("collapsed", not self.sidebar_expanded)
        self.settings_nav.setProperty("collapsed", not self.sidebar_expanded)
        for index in range(self.sidebar.count()):
            item = self.sidebar.item(index)
            item.setSizeHint(QSize(44 if collapsed else 188, 44))
            item.setText(item.data(Qt.ItemDataRole.UserRole) if self.sidebar_expanded else "")
        settings_item = self.settings_nav.item(0)
        if settings_item is not None:
            settings_item.setSizeHint(QSize(44 if collapsed else 188, 44))
            settings_item.setText(
                settings_item.data(Qt.ItemDataRole.UserRole)
                if self.sidebar_expanded
                else ""
            )
        self.sidebar.style().unpolish(self.sidebar)
        self.sidebar.style().polish(self.sidebar)
        self.settings_nav.style().unpolish(self.settings_nav)
        self.settings_nav.style().polish(self.settings_nav)
        if self.sidebar_animation is not None:
            self.sidebar_animation.stop()
        self.sidebar_animation = QPropertyAnimation(self.sidebar_container, b"maximumWidth", self)
        self.sidebar_animation.setDuration(180)
        self.sidebar_animation.setStartValue(self.sidebar_container.width())
        self.sidebar_animation.setEndValue(end_width)
        self.sidebar_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.sidebar_container.setMinimumWidth(end_width)
        self.sidebar_animation.start()

    def _build_pages(self) -> None:
        modules = [
            ("启动", self._create_home_page()),
            ("实时触发", self._create_realtime_page()),
            ("独立任务", self._create_placeholder_page("独立任务", "这里可以管理一次性任务、脚本和桌宠行为队列。")),
            ("一条龙", self._create_placeholder_page("一条龙", "这里可以放连续工作流和预设方案。")),
            ("全自动", self._create_placeholder_page("全自动", "这里可以管理自动运行策略。")),
            ("辅助操控", self._create_placeholder_page("辅助操控", "这里可以放桌宠移动、展示和目标选择控制。")),
            ("快捷键", self._create_placeholder_page("快捷键", "这里可以配置全局快捷键。")),
            ("通知", self._create_placeholder_page("通知", "这里可以管理提醒和消息。")),
        ]
        icon_names = [
            "play",
            "refresh",
            "list",
            "list-view",
            "controls",
            "tool",
            "controls",
            "bell",
        ]
        for icon_name, (title, page) in zip(icon_names, modules, strict=True):
            item = QListWidgetItem(self._icon(icon_name), title)
            item.setData(Qt.ItemDataRole.UserRole, title)
            item.setSizeHint(QSize(188, 44))
            self.sidebar.addItem(item)
            self.stack.addWidget(page)

        settings_item = QListWidgetItem(self._icon("settings"), "设置")
        settings_item.setData(Qt.ItemDataRole.UserRole, "设置")
        settings_item.setSizeHint(QSize(188, 44))
        self.settings_nav.addItem(settings_item)
        self.stack.addWidget(self._create_settings_page())

    def _create_home_page(self) -> QWidget:
        page = self._page_container()
        layout = page.layout()

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(32, 28, 32, 28)
        title = QLabel("Desktop Sprite")
        title.setObjectName("heroTitle")
        subtitle = QLabel("桌宠运行、行为控制与配置管理")
        subtitle.setObjectName("heroSubtitle")
        hero_layout.addStretch(1)
        hero_layout.addWidget(title)
        hero_layout.addWidget(subtitle)
        layout.addWidget(hero)

        layout.addWidget(
            self._action_row(
                "重启桌宠",
                "重新启动桌宠运行实例，管理界面保持打开。",
                "重启",
                self.on_restart,
                "refresh",
            )
        )
        layout.addWidget(
            self._action_row(
                "退出应用",
                "关闭桌宠和管理界面。",
                "退出",
                self.on_quit,
                "power",
            )
        )
        layout.addStretch(1)
        return page

    def _create_realtime_page(self) -> QWidget:
        page = self._page_container()
        layout = page.layout()

        heading = QLabel("实时触发")
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        layout.addWidget(
            self._action_row(
                "展示桌宠",
                "执行当前桌宠的展示动作。",
                "展示",
                self.on_show,
                "play",
            )
        )
        layout.addWidget(
            self._action_row(
                "设置目标点",
                "在桌面上选择一个目标位置，让桌宠前往。",
                "选择",
                self.on_set_target,
                "tool",
            )
        )
        layout.addStretch(1)
        return page

    def _create_settings_page(self) -> QWidget:
        page = self._page_container()
        layout = page.layout()
        self.settings_page = page
        self.settings_layout = layout
        header_row = QHBoxLayout()
        header = QLabel("设置")
        header.setObjectName("pageTitle")
        header_row.addWidget(header)
        header_row.addStretch(1)
        self.restore_defaults_button = QPushButton("恢复默认配置")
        self.restore_defaults_button.setIcon(self._icon("refresh"))
        self.restore_defaults_button.clicked.connect(self._restore_default_config)
        header_row.addWidget(self.restore_defaults_button)

        self.undo_button = QPushButton("撤销修改")
        self.undo_button.setIcon(self._icon("undo"))
        self.undo_button.clicked.connect(self._undo_config_changes)
        self.undo_button.setEnabled(False)
        header_row.addWidget(self.undo_button)

        self.save_apply_button = QPushButton("保存并应用")
        self.save_apply_button.setIcon(self._icon("save"))
        self.save_apply_button.clicked.connect(self._save_and_apply_config)
        self.save_apply_button.setProperty("primary", True)
        self.save_apply_button.setEnabled(False)
        header_row.addWidget(self.save_apply_button)
        layout.addLayout(header_row)
        layout.addStretch(1)
        return page

    def _switch_page(self, index: int) -> None:
        if index < 0:
            return
        self.settings_nav.blockSignals(True)
        self.settings_nav.clearSelection()
        self.settings_nav.setCurrentRow(-1)
        self.settings_nav.blockSignals(False)
        self.stack.setCurrentIndex(index)

    def _switch_to_settings(self, index: int) -> None:
        if index < 0:
            return
        self._select_settings()

    def _select_settings(self) -> None:
        settings_index = self.stack.count() - 1
        self.sidebar.blockSignals(True)
        self.sidebar.clearSelection()
        self.sidebar.setCurrentRow(-1)
        self.sidebar.blockSignals(False)
        self.settings_nav.blockSignals(True)
        self.settings_nav.setCurrentRow(0)
        self.settings_nav.blockSignals(False)
        self._ensure_config_editor()
        self.stack.setCurrentIndex(settings_index)

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

    def _create_placeholder_page(self, title: str, description: str) -> QWidget:
        page = self._page_container()
        layout = page.layout()
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        body = QLabel(description)
        body.setObjectName("mutedText")
        body.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(body)
        layout.addStretch(1)
        return page

    def _page_container(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(64, 32, 64, 32)
        layout.setSpacing(20)
        return page

    def _action_row(
        self,
        title: str,
        description: str,
        button_text: str,
        callback: Callable[[], None],
        icon_name: str | None = None,
    ) -> QWidget:
        row = QFrame()
        row.setObjectName("actionRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(18)

        text_layout = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        description_label = QLabel(description)
        description_label.setObjectName("mutedText")
        description_label.setWordWrap(True)
        text_layout.addWidget(title_label)
        text_layout.addWidget(description_label)
        layout.addLayout(text_layout, 1)

        button = QPushButton(button_text)
        if icon_name is not None:
            button.setIcon(self._icon(icon_name))
        button.clicked.connect(callback)
        button.setProperty("primary", True)
        layout.addWidget(button)
        return row

    def _icon(self, name: str) -> QIcon:
        return QIcon(str(Path(__file__).with_name("icons") / f"{name}.svg"))

    def _apply_style(self) -> None:
        self.setStyleSheet(
            Path(__file__).with_name("main_window.qss").read_text(encoding="utf-8")
        )
