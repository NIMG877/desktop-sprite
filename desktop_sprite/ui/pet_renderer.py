from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from desktop_sprite.ui.render_pose import LimbPose, PoseRect, RenderPose


class PetRenderer:
    def draw_pose(self, painter: QPainter, pose: RenderPose, width: int, height: int) -> None:
        painter.save()
        try:
            painter.translate(width / 2 + pose.offset.x, height / 2 + pose.offset.y)
            if pose.facing.value == "left":
                painter.scale(-1, 1)
            painter.rotate(pose.rotation)
            painter.translate(-width / 2, -height / 2)

            self._draw_shadow(painter, pose)
            self._draw_edge_line(painter, pose)
            self._draw_limbs(painter, pose)
            self._draw_body(painter, pose)
            self._draw_scarf(painter, pose)
            self._draw_eyes(painter, pose)
        finally:
            painter.restore()

    def _draw_shadow(self, painter: QPainter, pose: RenderPose) -> None:
        painter.save()
        try:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(24, 29, 36, pose.shadow.opacity))
            self._draw_ellipse(painter, pose.shadow.ellipse)
        finally:
            painter.restore()

    def _draw_edge_line(self, painter: QPainter, pose: RenderPose) -> None:
        if pose.edge_line is None:
            return
        start, end = pose.edge_line
        painter.save()
        try:
            pen = QPen(QColor(67, 82, 98, 155), 4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPoint(round(start.x), round(start.y)), QPoint(round(end.x), round(end.y)))
        finally:
            painter.restore()

    def _draw_limbs(self, painter: QPainter, pose: RenderPose) -> None:
        painter.save()
        try:
            for limb in pose.limbs:
                self._draw_limb(painter, limb)
        finally:
            painter.restore()

    def _draw_limb(self, painter: QPainter, limb: LimbPose) -> None:
        pen = QPen(QColor(44, 135, 142), max(3, round(limb.radius)))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(
            QPoint(round(limb.root.x), round(limb.root.y)),
            QPoint(round(limb.joint.x), round(limb.joint.y)),
        )
        painter.drawLine(
            QPoint(round(limb.joint.x), round(limb.joint.y)),
            QPoint(round(limb.end.x), round(limb.end.y)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(157, 239, 211))
        radius = limb.terminal_radius
        painter.drawEllipse(QRectF(limb.end.x - radius, limb.end.y - radius * 0.75, radius * 2, radius * 1.5))

    def _draw_body(self, painter: QPainter, pose: RenderPose) -> None:
        painter.save()
        try:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(44, 135, 142))
            self._draw_ellipse(painter, pose.body.back)
            painter.setBrush(QColor(92, 210, 182))
            self._draw_ellipse(painter, pose.body.front)
            painter.setBrush(QColor(157, 239, 211))
            self._draw_ellipse(painter, pose.body.highlight)
        finally:
            painter.restore()

    def _draw_scarf(self, painter: QPainter, pose: RenderPose) -> None:
        painter.save()
        try:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(242, 132, 96))
            band = pose.scarf.band
            painter.drawRoundedRect(QRectF(band.x, band.y, band.width, band.height), 5, 5)
            painter.drawPolygon(
                [
                    QPoint(round(pose.scarf.tail_a.x), round(pose.scarf.tail_a.y)),
                    QPoint(round(pose.scarf.tail_tip.x), round(pose.scarf.tail_tip.y)),
                    QPoint(round(pose.scarf.tail_b.x), round(pose.scarf.tail_b.y)),
                ]
            )
        finally:
            painter.restore()

    def _draw_eyes(self, painter: QPainter, pose: RenderPose) -> None:
        painter.save()
        try:
            painter.setBrush(QColor(22, 28, 34))
            if pose.eyes.sleeping:
                pen = QPen(QColor(22, 28, 34), 3)
                painter.setPen(pen)
                self._draw_sleep_eye(painter, pose.eyes.left)
                self._draw_sleep_eye(painter, pose.eyes.right)
                return

            painter.setPen(Qt.PenStyle.NoPen)
            self._draw_ellipse(painter, pose.eyes.left)
            self._draw_ellipse(painter, pose.eyes.right)
            painter.setBrush(QColor(255, 255, 255, 230))
            self._draw_ellipse(painter, pose.eyes.left_highlight)
            self._draw_ellipse(painter, pose.eyes.right_highlight)
        finally:
            painter.restore()

    def _draw_sleep_eye(self, painter: QPainter, rect: PoseRect) -> None:
        y = rect.y + rect.height / 2
        painter.drawLine(QPoint(round(rect.x), round(y)), QPoint(round(rect.x + rect.width), round(y)))

    def _draw_ellipse(self, painter: QPainter, rect: PoseRect) -> None:
        painter.drawEllipse(QRectF(rect.x, rect.y, rect.width, rect.height))
