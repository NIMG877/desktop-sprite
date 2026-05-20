from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from desktop_sprite.models.state import Facing, Pet, PetState


class PetRenderer:
    def draw(self, painter: QPainter, pet: Pet, phase: float, width: int, height: int) -> None:
        state = pet.state
        w = width
        h = height

        bob = 0.0
        if state in {PetState.WALK, PetState.MOVE_TO_TARGET}:
            bob = math.sin(phase * math.tau) * 4
        elif state == PetState.IDLE:
            bob = math.sin(phase * math.tau) * 2
        elif state == PetState.FALL:
            bob = 7
        elif state == PetState.CLIMB:
            bob = math.sin(phase * math.tau) * 3

        painter.translate(w / 2, h / 2 + bob)
        if pet.facing == Facing.LEFT:
            painter.scale(-1, 1)
        if state == PetState.FALL:
            painter.rotate(-18)
        elif state == PetState.CLIMB:
            painter.rotate(-7)
            painter.translate(w * 0.03, 0)
        painter.translate(-w / 2, -h / 2)

        self._draw_shadow(painter, state, w, h)

        body = QColor(92, 210, 182)
        body_dark = QColor(44, 135, 142)
        body_light = QColor(157, 239, 211)
        scarf = QColor(242, 132, 96)

        self._draw_action_limbs(painter, state, phase, w, h, body_dark, body_light)
        self._draw_body(painter, state, w, h, body, body_dark, body_light)
        self._draw_scarf(painter, state, phase, w, h, scarf)
        self._draw_eyes(painter, state, w, h)
        self._draw_feet(painter, state, phase, w, h, body_dark)

    def _draw_shadow(self, painter: QPainter, state: PetState, w: int, h: int) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        if state == PetState.FALL:
            painter.setBrush(QColor(24, 29, 36, 32))
            painter.drawEllipse(QRectF(w * 0.31, h * 0.90, w * 0.38, h * 0.06))
            return

        painter.setBrush(QColor(24, 29, 36, 70))
        painter.drawEllipse(QRectF(w * 0.22, h * 0.84, w * 0.56, h * 0.10))

    def _draw_action_limbs(
        self,
        painter: QPainter,
        state: PetState,
        phase: float,
        w: int,
        h: int,
        body_dark: QColor,
        body_light: QColor,
    ) -> None:
        limb_pen = QPen(body_dark, max(4, round(w * 0.07)))
        limb_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        limb_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        if state == PetState.CLIMB:
            self._draw_climb_limbs(painter, phase, w, h, limb_pen, body_light)
        elif state == PetState.FALL:
            self._draw_fall_limbs(painter, phase, w, h, limb_pen)

    def _draw_climb_limbs(
        self,
        painter: QPainter,
        phase: float,
        w: int,
        h: int,
        limb_pen: QPen,
        body_light: QColor,
    ) -> None:
        grip_x = w * 0.79
        hand_shift = math.sin(phase * math.tau) * h * 0.035
        foot_shift = math.sin(phase * math.tau + math.pi) * h * 0.035

        edge_pen = QPen(QColor(67, 82, 98, 155), max(4, round(w * 0.05)))
        edge_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(edge_pen)
        painter.drawLine(QPoint(round(grip_x), round(h * 0.12)), QPoint(round(grip_x), round(h * 0.84)))

        painter.setPen(limb_pen)
        painter.drawLine(
            QPoint(round(w * 0.42), round(h * 0.34)),
            QPoint(round(grip_x), round(h * 0.25 + hand_shift)),
        )
        painter.drawLine(
            QPoint(round(w * 0.44), round(h * 0.50)),
            QPoint(round(grip_x), round(h * 0.43 - hand_shift)),
        )
        painter.drawLine(
            QPoint(round(w * 0.42), round(h * 0.70)),
            QPoint(round(w * 0.68), round(h * 0.70 + foot_shift)),
        )
        painter.drawLine(
            QPoint(round(w * 0.36), round(h * 0.75)),
            QPoint(round(w * 0.62), round(h * 0.82 - foot_shift)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(body_light)
        painter.drawEllipse(QRectF(grip_x - w * 0.055, h * 0.22 + hand_shift, w * 0.11, h * 0.08))
        painter.drawEllipse(QRectF(grip_x - w * 0.055, h * 0.40 - hand_shift, w * 0.11, h * 0.08))

    def _draw_fall_limbs(self, painter: QPainter, phase: float, w: int, h: int, limb_pen: QPen) -> None:
        arm_wave = math.sin(phase * math.tau) * h * 0.035
        painter.setPen(limb_pen)
        painter.drawLine(
            QPoint(round(w * 0.34), round(h * 0.44)),
            QPoint(round(w * 0.08), round(h * 0.29 + arm_wave)),
        )
        painter.drawLine(
            QPoint(round(w * 0.64), round(h * 0.45)),
            QPoint(round(w * 0.91), round(h * 0.30 - arm_wave)),
        )
        painter.drawLine(
            QPoint(round(w * 0.40), round(h * 0.74)),
            QPoint(round(w * 0.20), round(h * 0.88)),
        )
        painter.drawLine(
            QPoint(round(w * 0.58), round(h * 0.74)),
            QPoint(round(w * 0.78), round(h * 0.88)),
        )
        painter.setPen(Qt.PenStyle.NoPen)

    def _draw_body(
        self,
        painter: QPainter,
        state: PetState,
        w: int,
        h: int,
        body: QColor,
        body_dark: QColor,
        body_light: QColor,
    ) -> None:
        body_back_rect = QRectF(w * 0.22, h * 0.18, w * 0.58, h * 0.70)
        body_front_rect = QRectF(w * 0.19, h * 0.14, w * 0.58, h * 0.68)
        highlight_rect = QRectF(w * 0.31, h * 0.23, w * 0.20, h * 0.18)
        if state == PetState.CLIMB:
            body_back_rect = QRectF(w * 0.25, h * 0.14, w * 0.48, h * 0.72)
            body_front_rect = QRectF(w * 0.22, h * 0.12, w * 0.48, h * 0.70)
            highlight_rect = QRectF(w * 0.32, h * 0.22, w * 0.16, h * 0.17)
        elif state == PetState.FALL:
            body_back_rect = QRectF(w * 0.20, h * 0.21, w * 0.62, h * 0.62)
            body_front_rect = QRectF(w * 0.17, h * 0.18, w * 0.62, h * 0.60)
            highlight_rect = QRectF(w * 0.31, h * 0.27, w * 0.19, h * 0.15)

        painter.setBrush(body_dark)
        painter.drawEllipse(body_back_rect)
        painter.setBrush(body)
        painter.drawEllipse(body_front_rect)
        painter.setBrush(body_light)
        painter.drawEllipse(highlight_rect)

    def _draw_scarf(self, painter: QPainter, state: PetState, phase: float, w: int, h: int, scarf: QColor) -> None:
        painter.setBrush(scarf)
        scarf_y = h * 0.57
        if state == PetState.CLIMB:
            scarf_y = h * 0.54
        elif state == PetState.FALL:
            scarf_y = h * 0.51
        painter.drawRoundedRect(QRectF(w * 0.18, scarf_y, w * 0.58, h * 0.12), 5, 5)
        tail_tip_y = h * (0.58 + phase * 0.04)
        if state == PetState.FALL:
            tail_tip_y = h * (0.28 + math.sin(phase * math.tau) * 0.03)
        elif state == PetState.CLIMB:
            tail_tip_y = h * (0.52 + math.sin(phase * math.tau) * 0.025)
        painter.drawPolygon(
            [
                QPoint(round(w * 0.66), round(scarf_y + h * 0.05)),
                QPoint(round(w * 0.93), round(tail_tip_y)),
                QPoint(round(w * 0.68), round(scarf_y + h * 0.16)),
            ]
        )

    def _draw_eyes(self, painter: QPainter, state: PetState, w: int, h: int) -> None:
        eye_y = h * (0.40 if state != PetState.SLEEP else 0.43)
        if state == PetState.FALL:
            eye_y = h * 0.38
        elif state == PetState.CLIMB:
            eye_y = h * 0.36
        painter.setBrush(QColor(22, 28, 34))
        if state == PetState.SLEEP:
            pen = QPen(QColor(22, 28, 34), 3)
            painter.setPen(pen)
            painter.drawLine(QPoint(round(w * 0.42), round(eye_y)), QPoint(round(w * 0.50), round(eye_y)))
            painter.drawLine(QPoint(round(w * 0.59), round(eye_y)), QPoint(round(w * 0.67), round(eye_y)))
            painter.setPen(Qt.PenStyle.NoPen)
            return

        eye_w = w * (0.095 if state == PetState.FALL else 0.08)
        eye_h = h * (0.10 if state == PetState.FALL else 0.08)
        painter.drawEllipse(QRectF(w * 0.41, eye_y, eye_w, eye_h))
        painter.drawEllipse(QRectF(w * 0.58, eye_y, eye_w, eye_h))
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawEllipse(QRectF(w * 0.44, eye_y + h * 0.015, w * 0.022, h * 0.022))
        painter.drawEllipse(QRectF(w * 0.61, eye_y + h * 0.015, w * 0.022, h * 0.022))

    def _draw_feet(self, painter: QPainter, state: PetState, phase: float, w: int, h: int, body_dark: QColor) -> None:
        if state in {PetState.CLIMB, PetState.FALL}:
            return

        foot_offset = math.sin(phase * math.tau) * 4 if state in {PetState.WALK, PetState.MOVE_TO_TARGET} else 0
        painter.setBrush(body_dark)
        painter.drawEllipse(QRectF(w * 0.25, h * 0.78 + foot_offset, w * 0.22, h * 0.10))
        painter.drawEllipse(QRectF(w * 0.52, h * 0.78 - foot_offset, w * 0.22, h * 0.10))
