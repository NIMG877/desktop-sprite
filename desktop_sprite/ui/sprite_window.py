from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from desktop_sprite.core.pet_controller import PetController
from desktop_sprite.models.state import Facing, PetState
from desktop_sprite.utils.config import AppConfig
from desktop_sprite.utils.dpi import qt_primary_screen_scale


class SpriteWindow(QWidget):
    def __init__(self, controller: PetController, config: AppConfig) -> None:
        super().__init__()
        self.controller = controller
        self.config = config
        self._last_tick = time.monotonic()
        self._press_global: QPoint | None = None
        self._dragging = False

        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if config.app.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.resize(config.pet.width, config.pet.height)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(max(int(1000 / config.app.fps), 1))

    def _tick(self) -> None:
        try:
            now = time.monotonic()
            dt = min(now - self._last_tick, 0.05)
            self._last_tick = now
            self.controller.tick(dt)

            pet = self.controller.pet
            self.move(round(pet.position.x), round(pet.position.y))
            self.update()
        except KeyboardInterrupt:
            QApplication.quit()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_pet(painter)
        if self.config.app.debug_draw:
            self._draw_debug(painter)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._press_global = event.globalPosition().toPoint()
        self._dragging = True
        global_pos = event.globalPosition()
        self.controller.start_drag(global_pos.x(), global_pos.y())

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        global_pos = event.globalPosition()
        self.controller.drag_to(global_pos.x(), global_pos.y())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        global_pos = event.globalPosition()
        if self._dragging:
            self.controller.release_drag(global_pos.x(), global_pos.y())
        self._dragging = False
        self._press_global = None

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.poke()

    def _draw_pet(self, painter: QPainter) -> None:
        pet = self.controller.pet
        state = pet.state
        phase = self.controller.animation.phase
        w = self.width()
        h = self.height()

        bob = 0.0
        if state in {PetState.WALK, PetState.MOVE_TO_TARGET}:
            bob = math.sin(phase * math.tau) * 4
        elif state == PetState.IDLE:
            bob = math.sin(phase * math.tau) * 2
        elif state == PetState.FALL:
            bob = 5
        elif state == PetState.CLIMB:
            bob = math.sin(phase * math.tau) * 3

        painter.translate(w / 2, h / 2 + bob)
        if pet.facing == Facing.LEFT:
            painter.scale(-1, 1)
        painter.translate(-w / 2, -h / 2)

        shadow = QColor(24, 29, 36, 70)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow)
        painter.drawEllipse(QRectF(w * 0.22, h * 0.84, w * 0.56, h * 0.10))

        body = QColor(92, 210, 182)
        body_dark = QColor(44, 135, 142)
        body_light = QColor(157, 239, 211)
        scarf = QColor(242, 132, 96)

        painter.setBrush(body_dark)
        painter.drawEllipse(QRectF(w * 0.22, h * 0.18, w * 0.58, h * 0.70))
        painter.setBrush(body)
        painter.drawEllipse(QRectF(w * 0.19, h * 0.14, w * 0.58, h * 0.68))
        painter.setBrush(body_light)
        painter.drawEllipse(QRectF(w * 0.31, h * 0.23, w * 0.20, h * 0.18))

        painter.setBrush(scarf)
        painter.drawRoundedRect(QRectF(w * 0.18, h * 0.57, w * 0.58, h * 0.12), 5, 5)
        painter.drawPolygon(
            [
                QPoint(round(w * 0.66), round(h * 0.62)),
                QPoint(round(w * 0.93), round(h * (0.58 + phase * 0.04))),
                QPoint(round(w * 0.68), round(h * 0.73)),
            ]
        )

        eye_y = h * (0.40 if state != PetState.SLEEP else 0.43)
        painter.setBrush(QColor(22, 28, 34))
        if state == PetState.SLEEP:
            pen = QPen(QColor(22, 28, 34), 3)
            painter.setPen(pen)
            painter.drawLine(QPoint(round(w * 0.42), round(eye_y)), QPoint(round(w * 0.50), round(eye_y)))
            painter.drawLine(QPoint(round(w * 0.59), round(eye_y)), QPoint(round(w * 0.67), round(eye_y)))
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.drawEllipse(QRectF(w * 0.41, eye_y, w * 0.08, h * 0.08))
            painter.drawEllipse(QRectF(w * 0.58, eye_y, w * 0.08, h * 0.08))
            painter.setBrush(QColor(255, 255, 255, 230))
            painter.drawEllipse(QRectF(w * 0.44, eye_y + h * 0.015, w * 0.022, h * 0.022))
            painter.drawEllipse(QRectF(w * 0.61, eye_y + h * 0.015, w * 0.022, h * 0.022))

        foot_offset = math.sin(phase * math.tau) * 4 if state in {PetState.WALK, PetState.MOVE_TO_TARGET} else 0
        painter.setBrush(body_dark)
        painter.drawEllipse(QRectF(w * 0.25, h * 0.78 + foot_offset, w * 0.22, h * 0.10))
        painter.drawEllipse(QRectF(w * 0.52, h * 0.78 - foot_offset, w * 0.22, h * 0.10))

    def _draw_debug(self, painter: QPainter) -> None:
        pet = self.controller.pet
        floor_y = self.controller.snapshot.work_area_rect.bottom
        overflow = pet.bottom - floor_y
        scale = qt_primary_screen_scale()
        painter.resetTransform()
        painter.setPen(QPen(QColor(255, 60, 60), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(1, 1, self.width() - 2, self.height() - 2)

        painter.setPen(QPen(QColor(20, 20, 20), 1))
        painter.setFont(QFont("Consolas", 8))
        lines = [
            f"{pet.state}",
            #f"xy=({pet.position.x:.0f},{pet.position.y:.0f})",
            #f"center=({pet.center_x:.0f},{pet.position.y + pet.height / 2:.0f})",
            #f"bottom={pet.bottom:.0f}",
            #f"floor={floor_y:.0f} over={overflow:.0f}",
            #f"scale={scale:.2f}",
            f"v=({pet.velocity.x:.0f},{pet.velocity.y:.0f})",
            f"p={pet.support_platform_id or '-'}",
        ]
        painter.drawText(QRectF(4, 4, self.width() - 8, 104), "\n".join(lines))
