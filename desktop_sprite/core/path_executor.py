from __future__ import annotations

import math

from desktop_sprite.core.pathfinding import PathStep, TraversalAction
from desktop_sprite.models.state import Facing, PetState


class PathExecutor:
    def __init__(self, controller) -> None:
        self.controller = controller

    def execute_path_plan(self) -> bool:
        controller = self.controller
        if controller.path_plan is None or controller.path_plan.is_complete:
            return False

        step = controller.path_plan.current_step
        if step is None:
            return False
        if not controller._is_path_step_present(step):
            controller.path_plan = None
            return False

        if controller.pet.support_platform_id == step.to_surface_id and step.action != TraversalAction.MOVE:
            controller.path_plan.advance()
            if controller.path_plan.is_complete:
                target = controller.snapshot.platform_by_id(step.to_surface_id)
                controller._finish_path_plan(finish_climb=bool(target and target.walkable))
                return True
            return self.execute_path_plan()

        if controller.pet.support_platform_id != step.from_surface_id:
            controller.path_plan = None
            return False

        if step.action == TraversalAction.TRANSFORM:
            if not self.execute_transform_step(step):
                controller.path_plan = None
                return False
            return True

        if step.action == TraversalAction.MOVE:
            if self.execute_move_step(step):
                controller.path_plan.advance()
                if controller.path_plan.is_complete:
                    controller._finish_path_plan()
            return True

        if step.action == TraversalAction.FALL:
            source = controller.snapshot.platform_by_id(step.from_surface_id)
            if source is None:
                controller.path_plan = None
                return False
            if self.move_along_surface(source, step.target_t):
                controller.pet.support_platform_id = None
                controller.pet.target_platform_id = step.to_surface_id
                controller._transition(PetState.FALL)
            return True

        if step.action == TraversalAction.JUMP:
            source = controller.snapshot.platform_by_id(step.from_surface_id)
            if source is None:
                controller.path_plan = None
                return False
            if self.move_along_surface(source, step.target_t):
                self.start_jump_toward_surface(step)
            return True

        return False

    def walk_toward_x(self, target_x: float) -> bool:
        support = self.controller.snapshot.platform_by_id(self.controller.pet.support_platform_id)
        if support is not None and support.walkable:
            return self.move_along_surface(support, target_x)
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

    def move_along_surface(self, surface, target_t: float) -> bool:
        if surface.climbable:
            return self._move_along_axis(
                target_t - self.controller.pet.height,
                axis="y",
                speed=self.controller.config.physics.climb_speed,
                state=PetState.CLIMB,
                surface_id=surface.id,
            )
        return self._move_along_axis(
            target_t,
            axis="x",
            speed=self.controller.config.physics.walk_speed,
            state=PetState.WALK,
            surface_id=surface.id,
        )

    def _move_along_axis(self, target_value: float, *, axis: str, speed: float, state: PetState, surface_id: str) -> bool:
        controller = self.controller
        current = controller.pet.position.y if axis == "y" else controller.pet.position.x
        velocity = controller.pet.velocity.y if axis == "y" else controller.pet.velocity.x
        distance = target_value - current
        passed_target = (velocity > 0 and current >= target_value) or (
            velocity < 0 and current <= target_value
        )
        if abs(distance) <= controller.WALK_TARGET_ARRIVAL_DISTANCE or passed_target:
            if axis == "y":
                controller.pet.position.y = target_value
                controller.pet.velocity.y = 0.0
            else:
                controller.pet.position.x = target_value
                controller.pet.velocity.x = 0.0
            return True
        direction = 1 if distance > 0 else -1
        if axis == "y":
            controller.pet.velocity.x = 0.0
            controller.pet.velocity.y = direction * speed
            controller.pet.support_platform_id = surface_id
            controller.pet.target_platform_id = surface_id
        else:
            controller.pet.velocity.x = direction * speed
            controller.pet.velocity.y = 0.0
            controller.pet.facing = Facing.RIGHT if direction > 0 else Facing.LEFT
        controller._transition(state)
        return False

    def execute_move_step(self, step: PathStep) -> bool:
        controller = self.controller
        target = controller.snapshot.platform_by_id(step.to_surface_id)
        if target is None:
            controller.path_plan = None
            return True
        reached = self.move_along_surface(target, step.target_t)
        if reached:
            controller.pet.support_platform_id = target.id
            controller.pet.target_platform_id = target.id if target.climbable else None
        return reached

    def start_jump_toward_surface(self, step: PathStep) -> None:
        controller = self.controller
        target = controller.snapshot.platform_by_id(step.to_surface_id)
        if target is None:
            controller.path_plan = None
            return
        land_point = step.land_point or step.approach_point
        if land_point is None:
            controller.path_plan = None
            return
        if target.climbable:
            target_x, target_y = land_point
        else:
            raw_land_x, raw_land_y = land_point
            target_x = min(
                max(raw_land_x, target.rect.left - controller.pet.width / 2),
                target.rect.right - controller.pet.width / 2,
            )
            target_y = raw_land_y
        vx, vy = self.compute_jump_velocity_to(target_x, target_y)
        direction = 0 if abs(vx) <= 1e-6 else (1 if vx > 0 else -1)
        controller.pet.target_platform_id = step.to_surface_id
        controller.pet.support_platform_id = None
        controller.pet.velocity.x = vx
        controller.pet.velocity.y = vy
        if direction:
            controller.pet.facing = Facing.RIGHT if direction > 0 else Facing.LEFT
        controller._transition(PetState.JUMP)

    def execute_transform_step(self, step: PathStep) -> bool:
        controller = self.controller
        source = controller.snapshot.platform_by_id(step.from_surface_id)
        target = controller.snapshot.platform_by_id(step.to_surface_id)
        if source is None or target is None:
            return False
        land_point = step.land_point
        if target.climbable:
            target_x, target_y = land_point if land_point is not None else (
                target.rect.center_x - controller.pet.width / 2,
                controller.pet.position.y,
            )
            controller.pet.position.x = target_x
            controller.pet.position.y = target_y
            controller.pet.support_platform_id = target.id
            controller.pet.target_platform_id = target.id
            controller.pet.velocity.x = 0.0
            controller.pet.velocity.y = 0.0
            controller._transition(PetState.CLIMB)
        else:
            target_x, target_y = land_point if land_point is not None else (
                step.target_t,
                target.rect.top - controller.pet.height,
            )
            controller.pet.position.x = target_x
            controller.pet.position.y = target_y
            controller.pet.support_platform_id = target.id
            controller.pet.target_platform_id = None
            controller.pet.velocity.x = 0.0
            controller.pet.velocity.y = 0.0
            controller._transition(PetState.WALK)
        controller.path_plan.advance()
        if controller.path_plan.is_complete:
            controller._finish_path_plan(finish_climb=source.climbable or target.climbable)
        return True

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

