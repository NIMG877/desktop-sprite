from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget
from qfluentwidgets import FluentIcon as FIF


logger = logging.getLogger(__name__)


class TrayController:
    def __init__(
        self,
        window: QWidget,
        on_set_target: Callable[[], None] | None = None,
        on_show: Callable[[], None] | None = None,
        on_open_window: Callable[[], None] | None = None,
        owner: QWidget | None = None,
    ) -> None:
        self.window = window
        self.owner = owner or window
        self.on_set_target = on_set_target
        self.on_show = on_show
        self.on_open_window = on_open_window
        self.tray = QSystemTrayIcon(self._create_icon(), self.owner)
        self.tray.setToolTip("Desktop Sprite")
        self.menu = self._create_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)

    def show(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray is not available; tray controls are disabled.")
            return
        self.tray.show()

    def set_window(self, window: QWidget) -> None:
        self.window = window

    def quit(self) -> None:
        self.tray.hide()
        self.window.close()
        QApplication.quit()

    def _create_menu(self) -> QMenu:
        menu = QMenu(self.owner)
        if self.on_show is not None:
            show_action = QAction(FIF.PLAY.icon(), "展示", menu)
            show_action.triggered.connect(self.on_show)
            menu.addAction(show_action)
        if self.on_set_target is not None:
            set_target_action = QAction(FIF.GAME.icon(), "设置目标点", menu)
            set_target_action.triggered.connect(self.on_set_target)
            menu.addAction(set_target_action)
        if self.on_set_target is not None:
            menu.addSeparator()
        quit_action = QAction(FIF.POWER_BUTTON.icon(), "退出", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        return menu

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if self.on_open_window is None:
            return
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.on_open_window()

    def _create_icon(self) -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(18, 70, 36), 2))
        painter.setBrush(QColor(52, 190, 96))
        painter.drawEllipse(4, 4, 24, 24)
        painter.setPen(QPen(QColor(10, 40, 24), 2))
        painter.drawPoint(13, 14)
        painter.drawPoint(21, 14)
        painter.drawArc(12, 14, 10, 8, 200 * 16, 140 * 16)
        painter.end()

        return QIcon(pixmap)
