from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget

from desktop_sprite.core.character import CharacterDebugState, DesktopCharacter
from desktop_sprite.core.pathfinding import NavNodeKind, PathStep, SurfaceGraph, TraversalAction
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.ui.pet_renderer import PetRenderer
from desktop_sprite.ui.render_pose import PoseBuilder
from desktop_sprite.utils.config import AppConfig
from desktop_sprite.utils.dpi import qt_primary_screen_scale


class SpriteWindow(QWidget):
    def __init__(self, character: DesktopCharacter, config: AppConfig) -> None:
        super().__init__()
        self.character = character
        self.config = config
        self._last_tick = time.monotonic()
        self._press_global: QPoint | None = None
        self._dragging = False
        self.pet_renderer = PetRenderer()
        self.pose_builder = PoseBuilder(config.pet.wings.open_seconds, config.pet.wings.close_seconds)
        self.debug_overlay = DebugOverlayWindow(character, config) if config.app.debug_draw else None

        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if config.app.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        initial = self.character.render_state()
        self.resize(initial.width, initial.height)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(max(int(1000 / config.app.fps), 1))

    def apply_config(self, config: AppConfig) -> None:
        self.config = config
        self.pose_builder = PoseBuilder(config.pet.wings.open_seconds, config.pet.wings.close_seconds)
        self.timer.setInterval(max(int(1000 / config.app.fps), 1))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, config.app.always_on_top)
        if config.app.debug_draw and self.debug_overlay is None:
            self.debug_overlay = DebugOverlayWindow(self.character, config)
        elif not config.app.debug_draw and self.debug_overlay is not None:
            self.debug_overlay.close()
            self.debug_overlay = None
        elif self.debug_overlay is not None:
            self.debug_overlay.apply_config(config)
        if self.isVisible():
            self.show()

    def _tick(self) -> None:
        try:
            now = time.monotonic()
            dt = min(now - self._last_tick, 0.05)
            self._last_tick = now
            self.character.tick(dt)

            render_state = self.character.render_state()
            if self.width() != render_state.width or self.height() != render_state.height:
                self.resize(render_state.width, render_state.height)
            self.move(round(render_state.x), round(render_state.y))
            self.update()
            if self.character.debug_state().mode.value == "show":
                self.raise_()
            if self.debug_overlay is not None:
                self.debug_overlay.sync_to_snapshot()
        except KeyboardInterrupt:
            QApplication.quit()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_fn = getattr(self.character, "paint", None)
        if callable(paint_fn) and paint_fn(painter, self.width(), self.height()):
            return

        render_state = self.character.render_state()
        if render_state.body is None or render_state.animation is None:
            return
        effective_stats = getattr(self.character, "effective_stats", None)
        if callable(effective_stats):
            stats = effective_stats()
            self.pose_builder.wing_open_seconds = stats.wing_open_seconds
            self.pose_builder.wing_close_seconds = stats.wing_close_seconds
        animation = render_state.animation
        pose = self.pose_builder.build(
            render_state.body,
            animation.phase,
            render_state.pose_width,
            render_state.pose_height,
            state_elapsed=animation.elapsed,
        )
        if animation.previous_state is not None and animation.blend_alpha < 1.0:
            previous_pose = self.pose_builder.build(
                render_state.body,
                animation.previous_phase,
                render_state.pose_width,
                render_state.pose_height,
                state=animation.previous_state,
                state_elapsed=animation.previous_elapsed,
            )
            pose = previous_pose.blend(pose, animation.blend_alpha)
        painter.save()
        painter.translate(render_state.body_offset_x, render_state.body_offset_y)
        self.pet_renderer.draw_pose(
            painter,
            pose,
            render_state.pose_width,
            render_state.pose_height,
        )
        painter.restore()

        if self.config.app.debug_draw:
            self._draw_debug_window_bounds(painter)

    def _draw_debug_window_bounds(self, painter: QPainter) -> None:
        pen = QPen(QColor(255, 40, 40, 230), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(1, 1, max(self.width() - 2, 0), max(self.height() - 2, 0)))

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._press_global = event.globalPosition().toPoint()
        self._dragging = True
        global_pos = event.globalPosition()
        self.character.start_drag(global_pos.x(), global_pos.y())

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        global_pos = event.globalPosition()
        self.character.drag_to(global_pos.x(), global_pos.y())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        global_pos = event.globalPosition()
        if self._dragging:
            self.character.release_drag(global_pos.x(), global_pos.y())
        self._dragging = False
        self._press_global = None

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.character.poke()

    def closeEvent(self, event) -> None:
        if self.debug_overlay is not None:
            self.debug_overlay.close()
        super().closeEvent(event)


class DebugOverlayWindow(QWidget):
    def __init__(self, character: DesktopCharacter, config: AppConfig) -> None:
        super().__init__()
        self.character = character
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

    def apply_config(self, config: AppConfig) -> None:
        self.config = config
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, config.app.always_on_top)
        if self.isVisible():
            self.show()

    def sync_to_snapshot(self) -> None:
        screen = self.character.debug_state().snapshot.screen_rect
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
        screen = self.character.debug_state().snapshot.screen_rect
        painter.translate(-screen.left, -screen.top)
        self._draw_debug(painter)

    def _draw_debug(self, painter: QPainter) -> None:
        graph = self._surface_graph()
        self._draw_navigation_map(painter)
        self._draw_surface_graph(painter, graph)
        self._draw_collision_box(painter)
        self._draw_complete_path(painter)
        self._draw_debug_info(painter, graph)

    def _draw_navigation_map(self, painter: QPainter) -> None:
        snapshot = self.character.debug_state().snapshot

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

    def _draw_surface_graph(self, painter: QPainter, graph: SurfaceGraph) -> None:
        if not graph.adjacency:
            return

        for node in graph.nodes.values():
            self._draw_nav_node_marker(painter, node)

        for edges in graph.adjacency.values():
            for edge in edges:
                color = self._graph_edge_color(edge.action)
                pen = QPen(color, 1)
                pen.setStyle(Qt.PenStyle.DotLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for start, end in self._graph_edge_segments(edge, graph):
                    painter.drawLine(start, end)
                    if self._distance(start, end) >= 24:
                        self._draw_arrowhead(painter, start, end, color, 5)

    def _draw_nav_node_marker(self, painter: QPainter, node) -> None:
        render_state = self.character.render_state()
        point = QPointF(node.x + render_state.pose_width / 2, node.y + render_state.pose_height / 2)
        color = QColor(55, 135, 255, 160)
        if node.kind == NavNodeKind.DROP_POINT:
            color = QColor(70, 110, 220, 135)
        elif node.kind == NavNodeKind.JUMP_POINT:
            color = QColor(235, 185, 45, 165)
        elif node.kind == NavNodeKind.TRANSFORM_POINT:
            color = QColor(30, 160, 90, 180)
        self._draw_node_marker(painter, point, color)

    def _draw_collision_box(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor(255, 60, 60), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pet = self.character.render_state().body
        if pet is None:
            render = self.character.render_state()
            painter.drawRect(QRectF(render.x, render.y, render.width, render.height))
            return
        painter.drawRect(QRectF(pet.position.x, pet.position.y, pet.width, pet.height))

    def _draw_debug_info(self, painter: QPainter, graph: SurfaceGraph) -> None:
        pet = self.character.render_state().body
        lines = self._debug_lines(graph)

        painter.setFont(QFont("Consolas", 8))
        metrics = painter.fontMetrics()
        width = max(metrics.horizontalAdvance(line) for line in lines) + 12
        height = metrics.lineSpacing() * len(lines) + 10
        screen = self.character.debug_state().snapshot.screen_rect
        width = min(width, max(round(screen.width) - 16, 80))
        height = min(height, max(round(screen.height) - 16, metrics.lineSpacing() + 10))
        rect = self._debug_info_rect(width, height)

        painter.setPen(QPen(QColor(40, 40, 40, 180), 1))
        painter.setBrush(QColor(255, 255, 255, 215))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QPen(QColor(20, 20, 20), 1))
        painter.drawText(rect.adjusted(6, 5, -6, -5), Qt.AlignmentFlag.AlignLeft, "\n".join(lines))

    def _debug_lines(self, graph: SurfaceGraph) -> list[str]:
        debug_state = self.character.debug_state()
        pet = self.character.render_state().body
        graph_edges = len(graph.edges)
        move_edges = sum(1 for edge in graph.edges if edge.action == TraversalAction.MOVE)
        fall_edges = sum(1 for edge in graph.edges if edge.action == TraversalAction.FALL)
        jump_edges = sum(1 for edge in graph.edges if edge.action == TraversalAction.JUMP)
        transform_edges = sum(1 for edge in graph.edges if edge.action == TraversalAction.TRANSFORM)
        if pet is None:
            payload = self.character.render_state().payload or {}
            lines = [
                f"{payload.get('state', 'custom')}",
                f"center=({payload.get('center_x', 0.0):.1f},{payload.get('center_y', 0.0):.1f})",
                f"driver=({payload.get('driver_x', 0.0):.1f},{payload.get('driver_y', 0.0):.1f})",
                f"v=({payload.get('center_vx', 0.0):.1f},{payload.get('center_vy', 0.0):.1f})",
                f"driver_v=({payload.get('driver_vx', 0.0):.1f},{payload.get('driver_vy', 0.0):.1f})",
                f"contacts={payload.get('contacts', 0)}",
                f"area_err={payload.get('area_error_ratio', 0.0):+.3f}",
            ]
            horizontal = sum(1 for surface in graph.surfaces.values() if surface.is_horizontal)
            vertical = sum(1 for surface in graph.surfaces.values() if surface.is_vertical)
            lines.append(f"surfaces h={horizontal} v={vertical}")
            lines.append(f"graph nodes={len(graph.nodes)} edges={graph_edges}")
            lines.append(f"edge move={move_edges} fall={fall_edges} jump={jump_edges} transform={transform_edges}")
            lines.append(f"mode={debug_state.mode}")
            lines.append(f"phase={debug_state.phase} {debug_state.phase_elapsed:.2f}s")
            lines.append("path=-")
            return lines
        floor_y = debug_state.snapshot.work_area_rect.bottom
        overflow = pet.bottom - floor_y
        scale = qt_primary_screen_scale()
        lines = [
            f"mode={debug_state.mode}",
            f"phase={debug_state.phase} {debug_state.phase_elapsed:.2f}s",
            f"behavior:{pet.state}",
            # f"xy=({pet.position.x:.0f},{pet.position.y:.0f})",
            f"center=({pet.center_x:.2f},{pet.position.y + pet.height / 2:.2f})",
            # f"bottom={pet.bottom:.0f}",
            # f"floor={floor_y:.0f} over={overflow:.0f}",
            f"scale={scale:.1f}",
            f"v=({pet.velocity.x:.0f},{pet.velocity.y:.0f})",
            *self._resource_debug_lines(),
            f"platform={pet.support_surface_id or '-'}",
            # f"p_name={self._support_window_title()}",
        ]
        # walkable = sum(1 for platform in debug_state.snapshot.platforms if platform.walkable)
        # climbable = sum(1 for platform in debug_state.snapshot.platforms if platform.climbable)
        # lines.append(f"map platform={walkable} climb={climbable}")
        # lines.append(f"mesh nodes={len(mesh.nodes)} edges={graph_edges}")
        # lines.append(f"edge walk={walk_edges} drop={drop_edges} jump={jump_edges} climb={climb_edges}")
        # lines.append("map: blue walk green climb")
        # lines.append("graph: dotted path: bold yellow=dotted jump-related")
        path_plan = debug_state.path_plan
        if path_plan is None or path_plan.is_complete:
            lines.append("path=-")
            return lines

        lines.append(f"path={path_plan.current_index + 1}/{len(path_plan.steps)}")
        for index, step in enumerate(path_plan.steps, start=1):
            marker = ">" if index - 1 == path_plan.current_index else " "
            lines.append(f"{marker}{index}:{step.action}->{step.to_surface_id}")
            if index - 1 >= path_plan.current_index:
                lines.extend(f"  {line}" for line in self._step_debug_lines(step))
        return lines

    def _resource_debug_lines(self) -> list[str]:
        resources = getattr(self.character, "resources", None)
        effective_stats = getattr(self.character, "effective_stats", None)
        if resources is None or not callable(effective_stats):
            return []

        stats = effective_stats()
        return [
            f"vigor={resources.stamina:.0f}/{stats.max_stamina:.0f}",
            f"awareness={resources.energy:.0f}/{stats.max_energy:.0f}",
            f"satiety={resources.satiety:.0f}/{stats.satiety:.0f}",
        ]

    def _debug_info_rect(self, width: int, height: int) -> QRectF:
        pet = self.character.render_state().body
        if pet is None:
            return QRectF(8, 8, width, height)
        screen = self.character.debug_state().snapshot.screen_rect
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
        path_plan = self.character.debug_state().path_plan
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

    def _surface_graph(self) -> SurfaceGraph:
        debug_state: CharacterDebugState = self.character.debug_state()
        body = self.character.render_state().body
        if body is None:
            return SurfaceGraph(nodes={}, adjacency={})
        return debug_state.pathfinder.build_surface_graph(body, debug_state.snapshot, debug_state.physics)

    def _graph_edge_segments(self, edge, graph: SurfaceGraph) -> list[tuple[QPointF, QPointF]]:
        source = graph.nodes.get(edge.from_node_id)
        target = graph.nodes.get(edge.to_node_id)
        if source is None or target is None:
            return []
        pet = self.character.render_state().body
        half_w = pet.width / 2 if pet else 0.0
        half_h = pet.height / 2 if pet else 0.0
        start = QPointF(source.x + half_w, source.y + half_h)
        end = QPointF(target.x + half_w, target.y + half_h)
        return [(start, end)]

    def _path_segments(self) -> list[tuple[QPointF, QPointF, int, TraversalAction]]:
        path_plan = self.character.debug_state().path_plan
        if path_plan is None or path_plan.is_complete:
            return []

        pet = self.character.render_state().body
        if pet is None:
            return []
        current = QPointF(pet.center_x, pet.position.y + pet.height / 2)
        segments: list[tuple[QPointF, QPointF, int, TraversalAction]] = []
        for step_index in range(path_plan.current_index, len(path_plan.steps)):
            step = path_plan.steps[step_index]
            for waypoint in self._step_waypoints(step):
                if self._distance(current, waypoint) >= 1:
                    segments.append((current, waypoint, step_index, step.action))
                current = waypoint
        return segments

    def _step_waypoints(self, step: PathStep) -> list[QPointF]:
        pet = self.character.render_state().body
        if pet is None:
            return []
        snapshot = self.character.debug_state().snapshot
        target = snapshot.platform_by_id(step.to_surface_id)
        if target is None:
            return []

        points: list[QPointF] = []
        if step.action in {TraversalAction.JUMP, TraversalAction.FALL, TraversalAction.TRANSFORM}:
            if step.approach_point is not None:
                points.append(self._body_center_point(step.approach_point, pet))
            if step.land_point is not None:
                points.append(self._body_center_point(step.land_point, pet))
            elif step.land_t is not None:
                points.append(self._body_center_point(self._surface_body_point(target, step.land_t, pet), pet))
            return points

        if step.land_point is not None:
            return [self._body_center_point(step.land_point, pet)]
        return [self._body_center_point(self._surface_body_point(target, step.target_t, pet), pet)]

    def _body_center_point(self, body_point: tuple[float, float], pet) -> QPointF:
        return QPointF(body_point[0] + pet.width / 2, body_point[1] + pet.height / 2)

    def _surface_body_point(self, platform: Platform, anchor_t: float, pet) -> tuple[float, float]:
        if platform.climbable:
            return platform.rect.center_x - pet.width / 2, anchor_t - pet.height
        return anchor_t, platform.rect.top - pet.height

    def _step_debug_lines(self, step: PathStep) -> list[str]:
        snapshot = self.character.debug_state().snapshot
        target = snapshot.platform_by_id(step.to_surface_id)
        target_label = self._anchor_label(target, step.target_t)
        land_label = self._anchor_label(target, step.land_t)
        approach_label = self._point_label(step.approach_point)
        land_point_label = self._point_label(step.land_point)
        if step.action == TraversalAction.MOVE:
            return [f"move {target_label} -> {step.to_surface_id}"]
        if step.action == TraversalAction.TRANSFORM:
            contact = step.contact_surface_id or "-"
            return [
                f"contact {approach_label} via {contact}",
                f"transform land {land_label} {land_point_label} -> {step.to_surface_id}",
            ]
        if step.action == TraversalAction.JUMP:
            return [
                f"approach {approach_label}",
                f"jump land {land_label} {land_point_label} -> {step.to_surface_id}",
            ]
        if step.action == TraversalAction.FALL:
            return [
                f"drop {approach_label}",
                f"fall land {land_label} {land_point_label} -> {step.to_surface_id}",
            ]
        return [f"{step.action} -> {step.to_surface_id}"]

    def _anchor_label(self, platform: Platform | None, anchor_t: float | None) -> str:
        if anchor_t is None:
            return "t=-"
        if platform is not None and platform.climbable:
            return f"y={anchor_t:.0f}"
        return f"x={anchor_t:.0f}"

    def _point_label(self, point: tuple[float, float] | None) -> str:
        if point is None:
            return "(--, --)"
        return f"({point[0]:.0f},{point[1]:.0f})"

    def _support_window_title(self) -> str:
        debug_state = self.character.debug_state()
        pet = self.character.render_state().body
        if pet is None:
            return "-"
        platform = debug_state.snapshot.platform_by_id(pet.support_surface_id)
        if platform is None or platform.source_id is None:
            return "-"
        window = next(
            (item for item in debug_state.snapshot.windows if item.hwnd == platform.source_id),
            None,
        )
        if window is None:
            return f"<{platform.source_id}>"
        title = window.title.strip()
        if not title:
            return f"<{platform.source_id}>"
        return self._shorten_debug_text(title, 64)

    def _shorten_debug_text(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return f"{text[: max(limit - 3, 0)]}..."

    def _draw_path_platforms(self, painter: QPainter) -> None:
        path_plan = self.character.debug_state().path_plan
        if path_plan is None:
            return

        platform_ids: set[str] = set()
        for step in path_plan.steps[path_plan.current_index :]:
            platform_ids.add(step.from_surface_id)
            platform_ids.add(step.to_surface_id)
            if step.contact_surface_id is not None:
                platform_ids.add(step.contact_surface_id)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        for platform_id in platform_ids:
            platform = self.character.debug_state().snapshot.platform_by_id(platform_id)
            if platform is None:
                continue
            color = QColor(35, 150, 90, 150) if platform.climbable else QColor(40, 110, 255, 130)
            painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
            painter.drawRect(QRectF(platform.rect.left, platform.rect.top, platform.rect.width, platform.rect.height))

    def _draw_path_labels(self, painter: QPainter, segments: list[tuple[QPointF, QPointF, int, TraversalAction]]) -> None:
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

    def _graph_edge_color(self, action: TraversalAction) -> QColor:
        if action == TraversalAction.MOVE:
            return QColor(35, 125, 220, 85)
        if action == TraversalAction.TRANSFORM:
            return QColor(30, 160, 90, 95)
        if action == TraversalAction.FALL:
            return QColor(90, 110, 220, 95)
        return QColor(230, 180, 40, 95)

    def _path_color(self, action: TraversalAction, current: bool) -> QColor:
        alpha = 230 if current else 165
        if action == TraversalAction.MOVE:
            return QColor(40, 130, 230, alpha)
        if action == TraversalAction.TRANSFORM:
            return QColor(30, 160, 90, alpha)
        if action == TraversalAction.FALL:
            return QColor(90, 110, 220, alpha)
        return QColor(255, 145, 35, alpha)
