from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget


logger = logging.getLogger(__name__)


class TrayController:
    def __init__(self, window: QWidget, on_set_target: Callable[[], None] | None = None) -> None:
        self.window = window
        self.on_set_target = on_set_target
        self.tray = QSystemTrayIcon(self._create_icon(), window)
        self.tray.setToolTip("Desktop Sprite")
        self.tray.setContextMenu(self._create_menu())

    def show(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray is not available; tray controls are disabled.")
            return
        self.tray.show()

    def quit(self) -> None:
        self.tray.hide()
        self.window.close()
        QApplication.quit()

    def _create_menu(self) -> QMenu:
        menu = QMenu(self.window)
        if self.on_set_target is not None:
            set_target_action = QAction("设置目标点", menu)
            set_target_action.triggered.connect(self.on_set_target)
            menu.addAction(set_target_action)
            menu.addSeparator()
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        return menu

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
