from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
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
        on_restart: Callable[[], None] | None = None,
        on_apply_config: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config_path = Path(config_path)
        self.on_set_target = on_set_target
        self.on_show = on_show
        self.on_restart = on_restart or QApplication.quit
        self.on_apply_config = on_apply_config or self.on_restart
        self.on_quit = on_quit or QApplication.quit
        self.config_editor: ConfigEditorWidget | None = None
        self.save_apply_button: QPushButton | None = None
        self.undo_button: QPushButton | None = None
        self.settings_page: QWidget | None = None
        self.settings_layout: QVBoxLayout | None = None
        self.settings_editor_slot: QWidget | None = None

        self.setWindowTitle("Desktop Sprite")
        self.resize(1120, 720)
        self.setMinimumSize(920, 560)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setObjectName("sidebar")
        root.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        root.addWidget(self.stack, 1)

        self.setCentralWidget(central)
        self._build_pages()
        self._apply_style()

        self.sidebar.currentRowChanged.connect(self._switch_page)
        self.sidebar.setCurrentRow(0)

    def show_settings(self) -> None:
        self.sidebar.setCurrentRow(self.sidebar.count() - 1)
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

    def _build_pages(self) -> None:
        modules = [
            ("启动", self._create_home_page()),
            ("实时触发", self._create_placeholder_page("实时触发", "这里可以承载条件触发、动作编排和运行状态。")),
            ("独立任务", self._create_placeholder_page("独立任务", "这里可以管理一次性任务、脚本和桌宠行为队列。")),
            ("一条龙", self._create_placeholder_page("一条龙", "这里可以放连续工作流和预设方案。")),
            ("全自动", self._create_placeholder_page("全自动", "这里可以管理自动运行策略。")),
            ("辅助操控", self._create_placeholder_page("辅助操控", "这里可以放桌宠移动、展示和目标选择控制。")),
            ("快捷键", self._create_placeholder_page("快捷键", "这里可以配置全局快捷键。")),
            ("通知", self._create_placeholder_page("通知", "这里可以管理提醒和消息。")),
            ("设置", self._create_settings_page()),
        ]
        for title, page in modules:
            self.sidebar.addItem(QListWidgetItem(title))
            self.stack.addWidget(page)

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
                "展示桌宠",
                "执行当前桌宠的展示动作。",
                "展示",
                self.on_show,
            )
        )
        layout.addWidget(
            self._action_row(
                "设置目标点",
                "在桌面上选择一个目标位置，让桌宠前往。",
                "选择",
                self.on_set_target,
            )
        )
        layout.addWidget(
            self._action_row(
                "重启应用",
                "重新启动桌宠并加载最新配置。",
                "重启",
                self.on_restart,
            )
        )
        layout.addWidget(
            self._action_row(
                "退出应用",
                "关闭桌宠和管理界面。",
                "退出",
                self.on_quit,
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
        self.undo_button = QPushButton("撤销修改")
        self.undo_button.clicked.connect(self._undo_config_changes)
        self.undo_button.setEnabled(False)
        header_row.addWidget(self.undo_button)

        self.save_apply_button = QPushButton("保存并应用")
        self.save_apply_button.clicked.connect(self._save_and_apply_config)
        self.save_apply_button.setProperty("primary", True)
        self.save_apply_button.setEnabled(False)
        header_row.addWidget(self.save_apply_button)
        layout.addLayout(header_row)
        self.settings_editor_slot = QWidget(page)
        slot_layout = QVBoxLayout(self.settings_editor_slot)
        slot_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.settings_editor_slot, 1)
        return page

    def _switch_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if self.sidebar.item(index).text() == "设置":
            self._ensure_config_editor()

    def _ensure_config_editor(self) -> None:
        if self.config_editor is not None or self.settings_editor_slot is None:
            return
        self.config_editor = ConfigEditorWidget(self.config_path, self.settings_page)
        self.config_editor.dirtyChanged.connect(self._set_config_actions_enabled)
        self.settings_editor_slot.layout().addWidget(self.config_editor)

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
        if self.config_editor is None or self.settings_editor_slot is None:
            return
        self.config_editor.setVisible(False)
        self.settings_editor_slot.layout().removeWidget(self.config_editor)
        self.config_editor.deleteLater()
        self.config_editor = None
        self._set_config_actions_enabled(False)
        self._ensure_config_editor()

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
        button.clicked.connect(callback)
        button.setProperty("primary", True)
        layout.addWidget(button)
        return row

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #202727;
                color: #f5f7f7;
            }
            #sidebar {
                background: #151c1c;
                border: none;
                padding: 72px 8px 16px 8px;
                color: #e8eeee;
                font-size: 17px;
                outline: 0;
            }
            #sidebar::item {
                min-height: 44px;
                padding: 0 18px;
                border-radius: 4px;
            }
            #sidebar::item:selected {
                background: #283132;
                border-left: 4px solid #72d5e7;
                color: #ffffff;
            }
            #sidebar::item:hover {
                background: #222b2b;
            }
            #content {
                background: #202727;
            }
            QLabel {
                color: #f5f7f7;
                font-size: 15px;
            }
            #hero {
                min-height: 220px;
                border-radius: 8px;
                background: #303736;
                border: 1px solid #3c4543;
            }
            #heroTitle {
                font-size: 40px;
                font-weight: 700;
            }
            #heroSubtitle {
                font-size: 20px;
                color: #d8dfdf;
            }
            #pageTitle {
                font-size: 28px;
                font-weight: 700;
            }
            #actionRow {
                background: #2b3232;
                border: 1px solid #363f3e;
                border-radius: 6px;
            }
            #cardTitle {
                font-size: 19px;
                font-weight: 600;
            }
            #mutedText {
                color: #c1caca;
            }
            QPushButton {
                min-height: 34px;
                padding: 0 18px;
                border-radius: 5px;
                border: 1px solid #495354;
                background: #343d3d;
                color: #f5f7f7;
            }
            QPushButton:hover {
                background: #3d4848;
            }
            QPushButton[primary="true"] {
                background: #65c6d4;
                color: #101616;
                border: none;
                font-weight: 600;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
                background: #182020;
                color: #f5f7f7;
                border: 1px solid #465252;
                border-radius: 4px;
                padding: 4px 6px;
            }
            QLineEdit {
                min-width: 150px;
                max-width: 240px;
                min-height: 30px;
            }
            QCheckBox {
                min-width: 150px;
            }
            #sectionHeader {
                background: #3a4141;
                border: none;
                border-radius: 4px;
                color: #ffffff;
                font-size: 16px;
                font-weight: 600;
                min-height: 34px;
                text-align: left;
            }
            #sectionHeader:hover {
                background: #454d4d;
            }
            #configRow {
                background: transparent;
                min-height: 44px;
            }
            #configRow:hover {
                background: #273030;
            }
            #configScroll {
                background: transparent;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background: #202727;
            }
            """
        )
