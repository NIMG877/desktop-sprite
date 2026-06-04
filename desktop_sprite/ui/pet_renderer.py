from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF

from desktop_sprite.ui.render_pose import LimbPose, PosePoint, PoseRect, RenderPose


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
            self._draw_wings(painter, pose)
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

    def _draw_limbs(self, painter: QPainter, pose: RenderPose) -> None:
        painter.save()
        try:
            for limb in pose.limbs:
                self._draw_limb(painter, limb)
        finally:
            painter.restore()

    def _draw_wings(self, painter: QPainter, pose: RenderPose) -> None:
        if pose.wings is None or pose.wings.opacity <= 0:
            return
        painter.save()
        try:
            wing = pose.wings
            self._draw_feathered_wing(
                painter,
                root=wing.left_root,
                tip=wing.left_tip,
                lower=wing.left_lower,
                side=-1,
                opacity=wing.opacity,
                openness=wing.openness,
                flap=wing.flap,
            )
            self._draw_feathered_wing(
                painter,
                root=wing.right_root,
                tip=wing.right_tip,
                lower=wing.right_lower,
                side=1,
                opacity=wing.opacity,
                openness=wing.openness,
                flap=wing.flap,
            )
        finally:
            painter.restore()

    def _draw_feathered_wing(
        self,
        painter: QPainter,
        root: PosePoint,
        tip: PosePoint,
        lower: PosePoint,
        side: int,
        opacity: int,
        openness: float,
        flap: float,
    ) -> None:
        span = abs(tip.x - root.x)
        drop = lower.y - root.y
        lift = tip.y - root.y
        wing_alpha = min(opacity, 235)

        self._draw_primary_feathers(painter, root, side, span, lift, drop, wing_alpha, openness, flap)
        self._draw_secondary_feathers(painter, root, side, span, lift, drop, wing_alpha, openness, flap)

    def _draw_primary_feathers(
        self,
        painter: QPainter,
        root: PosePoint,
        side: int,
        span: float,
        lift: float,
        drop: float,
        opacity: int,
        openness: float,
        flap: float,
    ) -> None:
        feathers = (
            (0.82, -0.47, 0.04, 0.06, 22.0),
            (0.90, -0.33, 0.07, 0.10, 24.0),
            (0.88, -0.18, 0.10, 0.15, 26.0),
            (0.80, -0.01, 0.13, 0.21, 27.0),
            (0.70, 0.15, 0.15, 0.28, 26.0),
            (0.58, 0.30, 0.17, 0.34, 24.0),
            (0.46, 0.43, 0.18, 0.40, 22.0),
        )
        for tip_xf, tip_yf, base_xf, base_yf, width in feathers:
            base = PosePoint(
                root.x + side * span * base_xf,
                root.y + span * base_yf * 0.35,
            )
            tip = PosePoint(
                root.x + side * span * tip_xf,
                root.y + span * tip_yf + flap * (60.0 - tip_xf * 26.0) * max(openness, 0.35),
            )
            self._draw_feather(
                painter,
                base,
                tip,
                side,
                width + openness * 4.0,
                QColor(251, 253, 255, round(opacity * 0.92)),
                QColor(118, 132, 160, round(opacity * 0.48)),
            )

    def _draw_secondary_feathers(
        self,
        painter: QPainter,
        root: PosePoint,
        side: int,
        span: float,
        lift: float,
        drop: float,
        opacity: int,
        openness: float,
        flap: float,
    ) -> None:
        feathers = (
            (0.48, -0.27, 0.03, 0.08, 16.0),
            (0.56, -0.13, 0.05, 0.13, 17.0),
            (0.55, 0.02, 0.07, 0.18, 18.0),
            (0.48, 0.17, 0.09, 0.24, 17.0),
            (0.38, 0.31, 0.10, 0.30, 16.0),
        )
        for tip_xf, tip_yf, base_xf, base_yf, width in feathers:
            base = PosePoint(root.x + side * span * base_xf, root.y + span * base_yf * 0.34)
            tip = PosePoint(
                root.x + side * span * tip_xf,
                root.y + span * tip_yf + flap * 34.0 * max(openness, 0.35),
            )
            self._draw_feather(
                painter,
                base,
                tip,
                side,
                width,
                QColor(244, 248, 255, round(opacity * 0.76)),
                QColor(130, 145, 174, round(opacity * 0.36)),
            )

    def _draw_feather(
        self,
        painter: QPainter,
        base: PosePoint,
        tip: PosePoint,
        side: int,
        width: float,
        fill: QColor,
        outline: QColor,
    ) -> None:
        dx = tip.x - base.x
        dy = tip.y - base.y
        length = max((dx * dx + dy * dy) ** 0.5, 1.0)
        normal_x = -dy / length
        normal_y = dx / length
        mid = PosePoint(base.x + dx * 0.52, base.y + dy * 0.52)
        shoulder = width * 0.58
        base_width = width * 0.18

        painter.setPen(QPen(outline, 1))
        painter.setBrush(fill)
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(base.x + normal_x * base_width, base.y + normal_y * base_width),
                    QPointF(mid.x + normal_x * shoulder, mid.y + normal_y * shoulder),
                    self._point(tip),
                    QPointF(mid.x - normal_x * shoulder * 0.82, mid.y - normal_y * shoulder * 0.82),
                    QPointF(base.x - normal_x * base_width, base.y - normal_y * base_width),
                ]
            )
        )

        vein = QPen(QColor(165, 178, 204, max(40, round(outline.alpha() * 0.65))), 1)
        painter.setPen(vein)
        painter.drawLine(QPoint(round(base.x), round(base.y)), QPoint(round(tip.x), round(tip.y)))

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

    def _point(self, point) -> QPointF:
        return QPointF(point.x, point.y)

    def _draw_ellipse(self, painter: QPainter, rect: PoseRect) -> None:
        painter.drawEllipse(QRectF(rect.x, rect.y, rect.width, rect.height))
