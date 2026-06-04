"""Show-mode overlay window.

Draws a translucent full-screen title ("苍翼裁决者") during the Show
sequence. Historically the widget owned its own 33ms QTimer to drive
geometry syncs, but the parent `SpriteWindow` already ticks at
`config.app.fps` and calls `update()` on the overlay once per frame.
P2-14 removed the redundant timer; the overlay is now driven by the
parent's tick via `sync()` and self-hides when the character leaves
Show mode.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
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

    def start(self) -> None:
        """Make the overlay visible and align it with the screen rect.

        Geometry is refreshed here so the first frame is already
        correctly positioned; subsequent per-frame syncs come from
        `sync()` (driven by `SpriteWindow._tick`).
        """

        self._sync_geometry()
        self.show()
        self.raise_()

    def stop(self) -> None:
        """Hide the overlay. Safe to call from any mode."""

        self.hide()

    def sync(self) -> None:
        """Per-frame update driven by the parent `SpriteWindow`.

        If the character is no longer in Show mode the overlay hides
        itself. Otherwise it refreshes geometry and triggers a repaint.
        """

        debug = self.character.debug_state()
        if debug.mode != PetMode.SHOW:
            self.hide()
            return
        if not self.isVisible():
            self._sync_geometry()
            self.show()
            self.raise_()
        else:
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
