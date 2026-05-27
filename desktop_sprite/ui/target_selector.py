from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from desktop_sprite.core.character import DesktopCharacter
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.platform import Platform
from desktop_sprite.utils.config import AppConfig


@dataclass(frozen=True, slots=True)
class TargetCandidate:
    platform: Platform
    anchor_t: float
    flag_x: float
    flag_y: float


def select_target_candidate(
    snapshot: EnvironmentSnapshot,
    cursor_x: float,
    cursor_y: float,
    pet_width: float,
    search_down_distance: float,
    search_up_distance: float,
) -> TargetCandidate | None:
    candidates: list[TargetCandidate] = []
    for platform in snapshot.platforms:
        if not platform.walkable:
            continue
        if not platform.rect.left <= cursor_x <= platform.rect.right:
            continue
        vertical_distance = platform.rect.top - cursor_y
        if vertical_distance > search_down_distance or vertical_distance < -search_up_distance:
            continue

        anchor_left = platform.rect.left
        anchor_right = platform.rect.right - pet_width
        if anchor_right < anchor_left:
            continue
        anchor_t = min(max(cursor_x - pet_width / 2, anchor_left), anchor_right)
        candidates.append(
            TargetCandidate(
                platform=platform,
                anchor_t=anchor_t,
                flag_x=anchor_t + pet_width / 2,
                flag_y=platform.rect.top,
            )
        )

    if not candidates:
        return None
    return min(candidates, key=lambda candidate: abs(candidate.flag_y - cursor_y))


class TargetSelectorOverlay(QWidget):
    def __init__(self, character: DesktopCharacter, config: AppConfig) -> None:
        super().__init__()
        self.character = character
        self.config = config
        self.candidate: TargetCandidate | None = None

        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def start(self) -> None:
        screen = self.character.debug_state().snapshot.screen_rect
        self.setGeometry(
            QRect(
                round(screen.left),
                round(screen.top),
                max(round(screen.width), 1),
                max(round(screen.height), 1),
            )
        )
        self._update_candidate(QCursor.pos())
        self.show()
        self.raise_()
        self.activateWindow()

    def stop(self) -> None:
        self.candidate = None
        self.hide()

    def mouseMoveEvent(self, event) -> None:
        self._update_candidate(event.globalPosition().toPoint())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.stop()
            return

        if event.button() != Qt.MouseButton.LeftButton or self.candidate is None:
            return

        if self.character.set_target_surface_point(self.candidate.platform.id, self.candidate.anchor_t):
            self.stop()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))

        if self.candidate is None:
            return

        origin = self.character.debug_state().snapshot.screen_rect
        point = QPointF(self.candidate.flag_x - origin.left, self.candidate.flag_y - origin.top)

        pole_top = QPointF(point.x(), point.y() - 28)
        painter.setPen(QPen(QColor(170, 20, 20), 2))
        painter.drawLine(point, pole_top)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(230, 35, 35))
        painter.drawPolygon(
            QPolygonF(
                [
                    pole_top,
                    QPointF(pole_top.x() + 20, pole_top.y() + 6),
                    QPointF(pole_top.x(), pole_top.y() + 13),
                ]
            )
        )
        painter.setBrush(QColor(160, 20, 20))
        painter.drawEllipse(point - QPointF(3, 3), 3, 3)

    def _update_candidate(self, global_pos: QPoint) -> None:
        state = self.character.render_state()
        self.candidate = select_target_candidate(
            snapshot=self.character.debug_state().snapshot,
            cursor_x=global_pos.x(),
            cursor_y=global_pos.y(),
            pet_width=state.width,
            search_down_distance=self.config.interaction.target_search_down_distance,
            search_up_distance=self.config.interaction.target_search_up_distance,
        )
        self.update()
