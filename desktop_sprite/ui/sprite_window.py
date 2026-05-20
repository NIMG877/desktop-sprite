from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget

from desktop_sprite.core.pathfinding import PathAction, PathEdge
from desktop_sprite.core.pet_controller import PetController
from desktop_sprite.models.platform import Platform, PlatformType
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
        self.debug_overlay = DebugOverlayWindow(controller, config) if config.app.debug_draw else None

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
            if self.debug_overlay is not None:
                self.debug_overlay.sync_to_snapshot()
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

    def closeEvent(self, event) -> None:
        if self.debug_overlay is not None:
            self.debug_overlay.close()
        super().closeEvent(event)


class DebugOverlayWindow(QWidget):
    def __init__(self, controller: PetController, config: AppConfig) -> None:
        super().__init__()
        self.controller = controller
        self.config = config

        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        if config.app.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(False)

    def sync_to_snapshot(self) -> None:
        screen = self.controller.snapshot.screen_rect
        self.setGeometry(
            round(screen.left),
            round(screen.top),
            max(round(screen.width), 1),
            max(round(screen.height), 1),
        )
        if not self.isVisible():
            self.show()
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        screen = self.controller.snapshot.screen_rect
        painter.translate(-screen.left, -screen.top)
        self._draw_debug(painter)

    def _draw_debug(self, painter: QPainter) -> None:
        graph = self._navigation_graph()
        self._draw_navigation_map(painter)
        self._draw_navigation_graph(painter, graph)
        self._draw_collision_box(painter)
        self._draw_complete_path(painter)
        self._draw_debug_info(painter, graph)

    def _draw_navigation_map(self, painter: QPainter) -> None:
        snapshot = self.controller.snapshot

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(90, 90, 90, 80), 1))
        painter.drawRect(
            QRectF(
                snapshot.screen_rect.left,
                snapshot.screen_rect.top,
                snapshot.screen_rect.width,
                snapshot.screen_rect.height,
            )
        )

        work_pen = QPen(QColor(80, 80, 80, 120), 1)
        work_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(work_pen)
        painter.drawRect(
            QRectF(
                snapshot.work_area_rect.left,
                snapshot.work_area_rect.top,
                snapshot.work_area_rect.width,
                snapshot.work_area_rect.height,
            )
        )

        for window in snapshot.windows:
            color = QColor(255, 170, 40, 95) if window.is_foreground else QColor(80, 80, 80, 45)
            painter.setPen(QPen(color, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(window.rect.left, window.rect.top, window.rect.width, window.rect.height))

        for platform in snapshot.platforms:
            self._draw_platform(painter, platform)

    def _draw_platform(self, painter: QPainter, platform: Platform) -> None:
        rect = QRectF(platform.rect.left, platform.rect.top, platform.rect.width, platform.rect.height)
        if platform.walkable:
            pen = QPen(QColor(45, 120, 255, 140), 1)
            brush = QColor(45, 120, 255, 35)
        elif platform.climbable:
            pen = QPen(QColor(25, 155, 90, 150), 1)
            brush = QColor(25, 155, 90, 35)
        else:
            pen = QPen(QColor(100, 100, 100, 80), 1)
            brush = QColor(100, 100, 100, 20)

        if platform.type == PlatformType.GROUND:
            pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(brush)
        painter.drawRect(rect)

        if platform.walkable:
            self._draw_node_marker(painter, QPointF(platform.rect.center_x, platform.rect.top), QColor(45, 120, 255, 180))
        elif platform.climbable:
            self._draw_climb_marker(painter, QPointF(platform.rect.center_x, platform.rect.center_y))

    def _draw_node_marker(self, painter: QPainter, point: QPointF, color: QColor) -> None:
        painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 220), 1))
        painter.setBrush(color)
        painter.drawEllipse(point, 4, 4)

    def _draw_climb_marker(self, painter: QPainter, point: QPointF) -> None:
        color = QColor(25, 155, 90, 185)
        size = 5
        painter.setPen(QPen(QColor(20, 110, 70, 220), 1))
        painter.setBrush(color)
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(point.x(), point.y() - size),
                    QPointF(point.x() + size, point.y()),
                    QPointF(point.x(), point.y() + size),
                    QPointF(point.x() - size, point.y()),
                ]
            )
        )

    def _draw_navigation_graph(self, painter: QPainter, graph: dict[str, list[PathEdge]]) -> None:
        if not graph:
            return

        for edges in graph.values():
            for edge in edges:
                color = self._graph_edge_color(edge.action)
                pen = QPen(color, 1)
                pen.setStyle(Qt.PenStyle.DotLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for start, end in self._graph_edge_segments(edge):
                    painter.drawLine(start, end)
                    if self._distance(start, end) >= 24:
                        self._draw_arrowhead(painter, start, end, color, 5)

    def _draw_collision_box(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor(255, 60, 60), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pet = self.controller.pet
        painter.drawRect(QRectF(pet.position.x, pet.position.y, pet.width, pet.height))

    def _draw_debug_info(self, painter: QPainter, graph: dict[str, list[PathEdge]]) -> None:
        pet = self.controller.pet
        lines = self._debug_lines(graph)

        painter.setFont(QFont("Consolas", 8))
        metrics = painter.fontMetrics()
        width = max(metrics.horizontalAdvance(line) for line in lines) + 12
        height = metrics.lineSpacing() * len(lines) + 10
        screen = self.controller.snapshot.screen_rect
        width = min(width, max(round(screen.width) - 16, 80))
        height = min(height, max(round(screen.height) - 16, metrics.lineSpacing() + 10))
        rect = self._debug_info_rect(width, height)

        painter.setPen(QPen(QColor(40, 40, 40, 180), 1))
        painter.setBrush(QColor(255, 255, 255, 215))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QPen(QColor(20, 20, 20), 1))
        painter.drawText(rect.adjusted(6, 5, -6, -5), Qt.AlignmentFlag.AlignLeft, "\n".join(lines))

    def _debug_lines(self, graph: dict[str, list[PathEdge]]) -> list[str]:
        pet = self.controller.pet
        floor_y = self.controller.snapshot.work_area_rect.bottom
        overflow = pet.bottom - floor_y
        scale = qt_primary_screen_scale()
        lines = [
            f"{pet.state}",
            f"xy=({pet.position.x:.0f},{pet.position.y:.0f})",
            f"center=({pet.center_x:.0f},{pet.position.y + pet.height / 2:.0f})",
            f"bottom={pet.bottom:.0f}",
            f"floor={floor_y:.0f} over={overflow:.0f}",
            f"scale={scale:.2f}",
            f"v=({pet.velocity.x:.0f},{pet.velocity.y:.0f})",
            f"stamina={pet.stamina:.0f}/{self.config.stamina.max_stamina:.0f}",
            f"p={pet.support_platform_id or '-'}",
        ]
        graph_edges = sum(len(edges) for edges in graph.values())
        walkable = sum(1 for platform in self.controller.snapshot.platforms if platform.walkable)
        climbable = sum(1 for platform in self.controller.snapshot.platforms if platform.climbable)
        lines.append(f"map nodes={walkable} climb={climbable} edges={graph_edges}")
        lines.append("map: blue walk green climb")
        lines.append("graph: dotted path: bold")
        path_plan = self.controller.path_plan
        if path_plan is None or path_plan.is_complete:
            lines.append("path=-")
            return lines

        lines.append(f"path={path_plan.current_index + 1}/{len(path_plan.edges)}")
        for index, edge in enumerate(path_plan.edges, start=1):
            marker = ">" if index - 1 == path_plan.current_index else " "
            lines.append(f"{marker}{index}:{edge.action}->{edge.to_platform_id}")
        return lines

    def _debug_info_rect(self, width: int, height: int) -> QRectF:
        pet = self.controller.pet
        screen = self.controller.snapshot.screen_rect
        margin = 8
        x = pet.position.x + pet.width + margin
        y = pet.position.y

        if x + width > screen.right - margin:
            left_x = pet.position.x - width - margin
            if left_x >= screen.left + margin:
                x = left_x
            else:
                x = min(max(pet.position.x, screen.left + margin), screen.right - width - margin)

        if y + height > screen.bottom - margin:
            below_y = pet.position.y + pet.height + margin
            above_y = pet.position.y - height - margin
            if below_y + height <= screen.bottom - margin:
                y = below_y
            elif above_y >= screen.top + margin:
                y = above_y
            else:
                y = min(max(y, screen.top + margin), screen.bottom - height - margin)

        return QRectF(x, y, width, height)

    def _draw_complete_path(self, painter: QPainter) -> None:
        path_plan = self.controller.path_plan
        if path_plan is None or path_plan.is_complete:
            return

        segments = self._path_segments()
        if not segments:
            return

        self._draw_path_platforms(painter)
        for start, end, edge_index, action in segments:
            current = edge_index == path_plan.current_index
            color = self._path_color(action, current)
            pen = QPen(color, 3 if current else 2)
            if not current:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(start, end)
            self._draw_arrowhead(painter, start, end, color, 9 if current else 7)
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 80))
            painter.drawEllipse(end, 5 if current else 4, 5 if current else 4)

        self._draw_path_labels(painter, segments)

    def _navigation_graph(self) -> dict[str, list[PathEdge]]:
        return self.controller.pathfinder.build_navigation_graph(
            self.controller.pet,
            self.controller.snapshot,
            self.controller.stamina,
        )

    def _graph_edge_segments(self, edge: PathEdge) -> list[tuple[QPointF, QPointF]]:
        source = self.controller.snapshot.platform_by_id(edge.from_platform_id)
        if source is None:
            return []

        pet = self.controller.pet
        current = QPointF(source.rect.center_x, source.rect.top - pet.height / 2)
        segments: list[tuple[QPointF, QPointF]] = []
        for waypoint in self._edge_waypoints(edge):
            segments.append((current, waypoint))
            current = waypoint
        return segments

    def _path_segments(self) -> list[tuple[QPointF, QPointF, int, PathAction]]:
        path_plan = self.controller.path_plan
        if path_plan is None or path_plan.is_complete:
            return []

        pet = self.controller.pet
        current = QPointF(pet.center_x, pet.position.y + pet.height / 2)
        segments: list[tuple[QPointF, QPointF, int, PathAction]] = []
        for edge_index in range(path_plan.current_index, len(path_plan.edges)):
            edge = path_plan.edges[edge_index]
            for waypoint in self._edge_waypoints(edge):
                segments.append((current, waypoint, edge_index, edge.action))
                current = waypoint
        return segments

    def _edge_waypoints(self, edge: PathEdge) -> list[QPointF]:
        pet = self.controller.pet
        snapshot = self.controller.snapshot
        target = snapshot.platform_by_id(edge.to_platform_id)
        if target is None:
            return []

        if edge.action == PathAction.CLIMB:
            side = snapshot.platform_by_id(edge.side_platform_id)
            if side is None:
                return [QPointF(edge.target_x + pet.width / 2, target.rect.top - pet.height / 2)]
            return [
                QPointF(side.rect.center_x, side.rect.bottom - pet.height / 2),
                QPointF(side.rect.center_x, target.rect.top - pet.height / 2),
            ]

        return [QPointF(edge.target_x + pet.width / 2, target.rect.top - pet.height / 2)]

    def _draw_path_platforms(self, painter: QPainter) -> None:
        path_plan = self.controller.path_plan
        if path_plan is None:
            return

        platform_ids: set[str] = set()
        for edge in path_plan.edges[path_plan.current_index :]:
            platform_ids.add(edge.from_platform_id)
            platform_ids.add(edge.to_platform_id)
            if edge.side_platform_id is not None:
                platform_ids.add(edge.side_platform_id)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        for platform_id in platform_ids:
            platform = self.controller.snapshot.platform_by_id(platform_id)
            if platform is None:
                continue
            color = QColor(35, 150, 90, 150) if platform.climbable else QColor(40, 110, 255, 130)
            painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
            painter.drawRect(QRectF(platform.rect.left, platform.rect.top, platform.rect.width, platform.rect.height))

    def _draw_path_labels(self, painter: QPainter, segments: list[tuple[QPointF, QPointF, int, PathAction]]) -> None:
        seen: set[int] = set()
        painter.setFont(QFont("Consolas", 8))
        for _start, end, edge_index, action in segments:
            if edge_index in seen:
                continue
            seen.add(edge_index)
            label = f"{edge_index + 1}:{action}"
            metrics = painter.fontMetrics()
            rect = QRectF(end.x() + 6, end.y() - 18, metrics.horizontalAdvance(label) + 8, 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 210))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QPen(QColor(20, 20, 20), 1))
            painter.drawText(rect.adjusted(4, 1, -4, -1), Qt.AlignmentFlag.AlignLeft, label)

    def _draw_arrowhead(self, painter: QPainter, start: QPointF, end: QPointF, color: QColor, size: int) -> None:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        if math.hypot(dx, dy) < 1:
            return
        angle = math.atan2(dy, dx)
        left = QPointF(
            end.x() - size * math.cos(angle - math.pi / 6),
            end.y() - size * math.sin(angle - math.pi / 6),
        )
        right = QPointF(
            end.x() - size * math.cos(angle + math.pi / 6),
            end.y() - size * math.sin(angle + math.pi / 6),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([end, left, right]))

    def _distance(self, start: QPointF, end: QPointF) -> float:
        return math.hypot(end.x() - start.x(), end.y() - start.y())

    def _graph_edge_color(self, action: PathAction) -> QColor:
        if action == PathAction.CLIMB:
            return QColor(30, 145, 85, 80)
        if action == PathAction.DROP:
            return QColor(140, 75, 200, 75)
        return QColor(45, 105, 220, 70)

    def _path_color(self, action: PathAction, current: bool) -> QColor:
        alpha = 230 if current else 165
        if action == PathAction.CLIMB:
            return QColor(30, 160, 90, alpha)
        if action == PathAction.DROP:
            return QColor(150, 80, 210, alpha)
        return QColor(255, 145, 35, alpha) if current else QColor(45, 120, 255, alpha)
