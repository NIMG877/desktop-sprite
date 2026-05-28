from __future__ import annotations

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

from desktop_sprite.core.behavior_orchestrator import BehaviorPhaseName
from desktop_sprite.core.character import DesktopCharacter
from desktop_sprite.core.pet_mode import PetMode


SHOW_TITLE = "苍翼裁决者"


class ShowOverlayWindow(QWidget):
    def __init__(self, character: DesktopCharacter) -> None:
        super().__init__()
        self.character = character
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._sync)

    def start(self) -> None:
        self._sync_geometry()
        self.show()
        self.raise_()
        self.timer.start(33)

    def stop(self) -> None:
        self.timer.stop()
        self.hide()

    def _sync(self) -> None:
        debug = self.character.debug_state()
        if debug.mode != PetMode.SHOW:
            self.stop()
            return
        self._sync_geometry()
        self.update()

    def _sync_geometry(self) -> None:
        screen = self.character.debug_state().snapshot.screen_rect
        self.setGeometry(
            QRect(
                round(screen.left),
                round(screen.top),
                max(round(screen.width), 1),
                max(round(screen.height), 1),
            )
        )

    def paintEvent(self, _event) -> None:
        debug = self.character.debug_state()
        if debug.mode != PetMode.SHOW:
            return

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 170))
        if debug.phase != BehaviorPhaseName.SHOW_TITLE:
            return

        font = QFont("Microsoft YaHei", 128, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 255))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, SHOW_TITLE)
