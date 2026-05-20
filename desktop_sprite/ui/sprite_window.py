from __future__ import annotations

import time

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from desktop_sprite.core.pet_controller import PetController
from desktop_sprite.ui.pet_renderer import PetRenderer
from desktop_sprite.ui.render_pose import PoseBuilder
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
        self.pet_renderer = PetRenderer()
        self.pose_builder = PoseBuilder()

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
        animation = self.controller.animation
        pose = self.pose_builder.build(
            self.controller.pet,
            animation.phase,
            self.width(),
            self.height(),
        )
        if animation.previous_state is not None and animation.blend_alpha < 1.0:
            previous_pose = self.pose_builder.build(
                self.controller.pet,
                animation.previous_phase,
                self.width(),
                self.height(),
                state=animation.previous_state,
            )
            pose = previous_pose.blend(pose, animation.blend_alpha)
        self.pet_renderer.draw_pose(
            painter,
            pose,
            self.width(),
            self.height(),
        )
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
            f"stamina={pet.stamina:.0f}/{self.config.stamina.max_stamina:.0f}",
            f"p={pet.support_platform_id or '-'}",
        ]
        painter.drawText(QRectF(4, 4, self.width() - 8, 104), "\n".join(lines))
