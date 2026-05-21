from __future__ import annotations

import math

from desktop_sprite.core.pathfinding import PathAction, PathEdge
from desktop_sprite.models.platform import PlatformType
from desktop_sprite.models.state import Facing, PetState


class PathExecutor:
    def __init__(self, controller) -> None:
        self.controller = controller

    def execute_path_plan(self) -> bool:
        controller = self.controller
        if controller.path_plan is None or controller.path_plan.is_complete:
            return False

        edge = controller.path_plan.current_edge
        if edge is None:
            return False
        if not controller._is_path_edge_present(edge):
            controller.path_plan = None
            return False

        if controller.pet.support_platform_id == edge.to_platform_id and not (
            edge.action == PathAction.WALK and edge.from_platform_id == edge.to_platform_id
        ):
            controller.path_plan.advance()
            if controller.path_plan.is_complete:
                controller._finish_path_plan()
            return True

        if controller.pet.support_platform_id != edge.from_platform_id:
            controller.path_plan = None
            return False

        if edge.action == PathAction.CLIMB:
            if not self.execute_climb_edge(edge):
                controller.path_plan = None
                return False
            return True

        if edge.action == PathAction.WALK:
            if self.walk_toward_x(edge.approach_x):
                target = controller.snapshot.platform_by_id(edge.to_platform_id)
                source = controller.snapshot.platform_by_id(edge.from_platform_id)
                if target is None or source is None:
                    controller.path_plan = None
                    return True
                if target.rect.top > source.rect.top + controller.config.physics.edge_snap_distance:
                    controller.pet.support_platform_id = None
                    controller._transition(PetState.FALL)
                else:
                    controller.pet.support_platform_id = edge.to_platform_id
                    controller.path_plan.advance()
                    if controller.path_plan.is_complete:
                        controller._finish_path_plan()
            return True

        if edge.action == PathAction.JUMP:
            if self.walk_toward_x(edge.approach_x):
                self.start_jump_toward_platform(edge)
            return True

        return False

    def walk_toward_x(self, target_x: float) -> bool:
        controller = self.controller
        distance = target_x - controller.pet.position.x
        passed_target = (controller.pet.velocity.x > 0 and controller.pet.position.x >= target_x) or (
            controller.pet.velocity.x < 0 and controller.pet.position.x <= target_x
        )
        if abs(distance) <= controller.WALK_TARGET_ARRIVAL_DISTANCE or passed_target:
            controller.pet.position.x = target_x
            controller.pet.velocity.x = 0.0
            return True
        direction = 1 if distance > 0 else -1
        controller.pet.velocity.x = direction * controller.config.physics.walk_speed
        controller.pet.facing = Facing.RIGHT if direction > 0 else Facing.LEFT
        controller._transition(PetState.WALK)
        return False

    def start_jump_toward_platform(self, edge: PathEdge) -> None:
        controller = self.controller
        target = controller.snapshot.platform_by_id(edge.to_platform_id)
        if target is None:
            controller.path_plan = None
            return
        raw_land_x = edge.land_x if edge.land_x is not None else edge.approach_x
        if target.climbable:
            target_x = raw_land_x
            target_y = target.rect.bottom - controller.pet.height
        else:
            target_x = min(
                max(raw_land_x, target.rect.left - controller.pet.width / 2),
                target.rect.right - controller.pet.width / 2,
            )
            target_y = target.rect.top - controller.pet.height
        vx, vy = self.compute_jump_velocity_to(target_x, target_y)
        direction = 0 if abs(vx) <= 1e-6 else (1 if vx > 0 else -1)
        controller.pet.target_platform_id = edge.to_platform_id
        controller.pet.support_platform_id = None
        controller.pet.velocity.x = vx
        controller.pet.velocity.y = vy
        if direction:
            controller.pet.facing = Facing.RIGHT if direction > 0 else Facing.LEFT
        controller._transition(PetState.JUMP)

    def compute_jump_velocity_to(self, target_x: float, target_y: float) -> tuple[float, float]:
        controller = self.controller
        start_x = controller.pet.position.x
        start_y = controller.pet.position.y
        dx = target_x - start_x
        dy = target_y - start_y
        g = max(controller.config.physics.gravity, 1.0)
        max_vx = max(abs(controller.config.physics.jump_speed_x), 1.0)
        min_up_vy = min(controller.config.physics.jump_speed_y, -1.0)

        # Pick a feasible flight time from horizontal travel, then derive vertical speed.
        t = max(abs(dx) / max_vx, 0.18)
        vy = (dy - 0.5 * g * t * t) / t
        if vy > -1.0:
            # Force an upward takeoff; increase apex by solving with required vy.
            vy = min_up_vy
            disc = vy * vy + 2.0 * g * max(dy, 0.0)
            t = max((math.sqrt(max(disc, 0.0)) - vy) / g, 0.18)
        vx = dx / max(t, 1e-3)
        return vx, vy

    def execute_climb_edge(self, edge: PathEdge) -> bool:
        controller = self.controller
        side = controller.snapshot.platform_by_id(edge.side_platform_id)
        source = controller.snapshot.platform_by_id(edge.from_platform_id)
        if side is None or source is None or not side.climbable:
            return False

        launch_x = edge.approach_x
        distance = launch_x - controller.pet.position.x
        if abs(distance) > controller.config.physics.edge_snap_distance:
            direction = 1 if distance > 0 else -1
            controller.pet.velocity.x = direction * controller.config.physics.walk_speed
            controller.pet.facing = Facing.RIGHT if direction > 0 else Facing.LEFT
            controller._transition(PetState.WALK)
            return True

        controller.pet.position.x = launch_x
        controller.pet.velocity.x = 0.0
        controller.pet.target_platform_id = side.id
        controller.pet.target_window_id = side.source_id
        if source.rect.top - side.rect.bottom > controller.config.physics.edge_snap_distance:
            side_align_x = side.rect.center_x - controller.pet.width / 2
            controller._start_jump_toward_climb_side(side, side_align_x - controller.pet.position.x)
            return True

        controller.pet.position.x = side.rect.center_x - controller.pet.width / 2
        controller.pet.facing = Facing.RIGHT if side.type == PlatformType.WINDOW_LEFT else Facing.LEFT
        controller.pet.support_platform_id = None
        controller._transition(PetState.CLIMB)
        return True
