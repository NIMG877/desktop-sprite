from __future__ import annotations

import random
import time

from desktop_sprite.core.animation_player import AnimationPlayer
from desktop_sprite.core.behavior_state_machine import BehaviorStateMachine
from desktop_sprite.core.character import CharacterDebugState, CharacterRenderState
from desktop_sprite.core.pathfinding import PathFinder, PathPlan, PathStep, TraversalAction
from desktop_sprite.core.path_executor import PathExecutor
from desktop_sprite.core.physics_engine import PhysicsEngine
from desktop_sprite.core.reachability_policy import ReachabilityPolicy
from desktop_sprite.environment.desktop_environment import DesktopEnvironment
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.geometry import Vec2
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.models.platform_topology import PlatformTopology
from desktop_sprite.models.state import Facing, Pet, PetState
from desktop_sprite.utils.config import AppConfig


LOCAL_WANDER_PROBABILITY = 0.5
WALK_TARGET_ARRIVAL_DISTANCE = 0.8
MIN_WANDER_DISTANCE_FACTOR = 0.8


class PetController:
    WALK_TARGET_ARRIVAL_DISTANCE = WALK_TARGET_ARRIVAL_DISTANCE

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.pet = Pet(
            position=Vec2(config.pet.default_spawn_x, config.pet.default_spawn_y),
            velocity=Vec2(),
            width=config.pet.width,
            height=config.pet.height,
        )
        self.environment = DesktopEnvironment(config.pet.width, config.pet.height)
        self.physics = PhysicsEngine(config.physics, apply_state_transitions=False)
        self.pathfinder = PathFinder()
        self.path_executor = PathExecutor(self)
        self.path_plan: PathPlan | None = None
        self.state_machine = BehaviorStateMachine(self.pet.state)
        self.animation = AnimationPlayer()
        self.snapshot = self.environment.snapshot()
        self._last_environment_refresh = 0.0
        self._state_goal_until = 0.0
        self._landed_on_platform_last_tick = False
        self._drag_offset = Vec2()
        self._pick_new_idle_goal()

    def set_own_window_handle(self, hwnd: int | None) -> None:
        self.environment.set_own_window_handle(hwnd)

    def tick(self, dt: float) -> None:
        self._refresh_environment_if_needed()
        self._update_behavior(dt)
        old_state = self.pet.state
        old_support_platform_id = self.pet.support_platform_id
        motion_events = self.physics.update(self.pet, self.snapshot, dt)
        self._apply_motion_events(motion_events)
        self._landed_on_platform_last_tick = (
            old_support_platform_id is None
            and self.pet.support_platform_id is not None
            and old_state in {PetState.FALL, PetState.JUMP}
        )
        self.pet.state_time += dt
        self.animation.set_state(self.pet.state)
        self.animation.update(dt)

    def start_drag(self, mouse_x: float, mouse_y: float) -> None:
        self._transition(PetState.DRAGGED)
        self.pet.support_platform_id = None
        self.pet.target_platform_id = None
        self.pet.velocity = Vec2()
        self.pet.drag_positions.clear()
        self._drag_offset = Vec2(mouse_x - self.pet.position.x, mouse_y - self.pet.position.y)
        self._record_drag(mouse_x, mouse_y)

    def drag_to(self, mouse_x: float, mouse_y: float) -> None:
        if self.pet.state != PetState.DRAGGED:
            return
        self.pet.position.x = mouse_x - self._drag_offset.x
        self.pet.position.y = mouse_y - self._drag_offset.y
        self._record_drag(mouse_x, mouse_y)

    def release_drag(self, mouse_x: float, mouse_y: float) -> None:
        self._record_drag(mouse_x, mouse_y)
        throw = self._drag_throw_velocity()
        if self.config.interaction.throw_enabled:
            self.pet.velocity.x = throw.x * self.config.physics.drag_throw_factor
            self.pet.velocity.y = throw.y * self.config.physics.drag_throw_factor
        self.pet.support_platform_id = None
        self._transition(PetState.FALL)

    def poke(self) -> None:
        if self.pet.state == PetState.DRAGGED:
            return
        self.pet.velocity.y = min(self.pet.velocity.y, -220)
        self.pet.support_platform_id = None
        self._transition(PetState.FALL)

    def _refresh_environment_if_needed(self) -> None:
        now = time.monotonic()
        refresh_interval = 1.0 / max(self.config.app.fps, 1)
        if now - self._last_environment_refresh < refresh_interval:
            return
        previous_snapshot = self.snapshot
        self.snapshot = self.environment.snapshot()
        self.physics.reconcile_platform_motion(self.pet, previous_snapshot, self.snapshot)
        self._validate_path_plan()
        self._last_environment_refresh = now

    def _update_behavior(self, dt: float) -> None:
        if self.pet.state == PetState.DRAGGED:
            return

        if getattr(self, "_landed_on_platform_last_tick", False):
            self._landed_on_platform_last_tick = False
            return

        if self.path_plan is None and self.pet.state == PetState.WALK:
            self.pet.velocity.x = 0.0
            self._transition(PetState.IDLE)
            self._pick_new_idle_goal()
            return

        support = self.snapshot.platform_by_id(self.pet.support_platform_id)
        if support is None and self.pet.state not in {PetState.FALL, PetState.JUMP, PetState.CLIMB}:
            self._transition(PetState.FALL)
            return

        if self.pet.state == PetState.FALL:
            return

        if self.pet.state == PetState.JUMP:
            step = self.path_plan.current_step if self.path_plan else None
            if step and (
                step.action == TraversalAction.JUMP
                and bool((side := self.snapshot.platform_by_id(step.to_surface_id)) and side.climbable)
            ):
                self._maybe_grab_climb_side_while_jumping()
            return

        if self.pet.state == PetState.CLIMB:
            self._snap_to_climb_side()
            if self._execute_path_plan():
                return
            return

        self._advance_path_if_reached()
        if self._execute_path_plan():
            return

        target_side = self.snapshot.platform_by_id(self.pet.target_platform_id)
        if target_side and target_side.climbable:
            self._walk_toward_climb_side(target_side)
            return

        self._keep_walking_on_platform(support, dt)

    def _execute_path_plan(self) -> bool:
        return self._executor().execute_path_plan()

    def _walk_toward_x(self, target_x: float) -> bool:
        return self._executor().walk_toward_x(target_x)

    def _advance_path_if_reached(self) -> None:
        if self.path_plan is None:
            return
        step = self.path_plan.current_step
        if step is None:
            self.path_plan = None
            return
        if step.action == TraversalAction.MOVE and step.from_surface_id == step.to_surface_id:
            return
        if self.pet.support_platform_id != step.to_surface_id:
            return
        self.path_plan.advance()
        if self.path_plan.is_complete:
            self._finish_path_plan()

    def _finish_path_plan(self, *, finish_climb: bool = False) -> None:
        self.path_plan = None
        self.pet.velocity.x = 0.0
        active_states = {PetState.FALL, PetState.JUMP, PetState.DRAGGED}
        if not finish_climb:
            active_states.add(PetState.CLIMB)
        if self.pet.state not in active_states:
            self._transition(PetState.IDLE)
            self._pick_new_idle_goal()

    def _validate_path_plan(self) -> None:
        if self.path_plan is None:
            return
        step = self.path_plan.current_step
        if step is None:
            self.path_plan = None
            return
        if not self._is_path_step_present(step):
            self.path_plan = None

    def _is_path_step_present(self, step: PathStep) -> bool:
        if self.snapshot.platform_by_id(step.from_surface_id) is None:
            return False
        if self.snapshot.platform_by_id(step.to_surface_id) is None:
            return False
        if step.contact_surface_id and self.snapshot.platform_by_id(step.contact_surface_id) is None:
            return False
        return True

    def _executor(self) -> PathExecutor:
        executor = getattr(self, "path_executor", None)
        if executor is None:
            executor = PathExecutor(self)
            self.path_executor = executor
        return executor

    def _nearest_reachable_side_for_window(self, hwnd: int) -> Platform | None:
        sides = [
            platform
            for platform in self.snapshot.platforms
            if platform.source_id == hwnd and platform.climbable and self._can_ever_reach_climb_side(platform)
        ]
        if not sides:
            return None
        return min(sides, key=lambda platform: abs(platform.rect.center_x - self.pet.center_x))

    def _walk_toward_climb_side(self, side: Platform) -> None:
        reachability = self._climb_reachability(side)
        if reachability == "unreachable":
            self.pet.target_platform_id = None
            self.pet.target_window_id = None
            self.pet.velocity.x = 0.0
            self._transition(PetState.IDLE)
            self._pick_new_idle_goal()
            return

        target_x = side.rect.center_x - self.pet.width / 2
        distance = target_x - self.pet.position.x
        if reachability == "jump" and abs(distance) <= self._max_jump_distance():
            self._start_jump_toward_climb_side(side, distance)
            return

        if abs(distance) <= self.config.physics.edge_snap_distance:
            self.pet.position.x = target_x
            self.pet.velocity.x = 0.0
            self.pet.target_platform_id = side.id
            self.pet.facing = Facing.RIGHT if side.type == PlatformType.WINDOW_LEFT else Facing.LEFT
            self.pet.support_platform_id = None
            self._transition(PetState.CLIMB)
            return

        direction = 1 if distance > 0 else -1
        self.pet.velocity.x = direction * self.config.physics.walk_speed
        self.pet.facing = Facing.RIGHT if direction > 0 else Facing.LEFT
        self._transition(PetState.WALK)

    def _start_jump_toward_climb_side(self, side: Platform, distance: float) -> None:
        target_x = side.rect.center_x - self.pet.width / 2
        target_y = side.rect.bottom - self.pet.height
        vx, vy = self._executor().compute_jump_velocity_to(target_x, target_y)
        direction = 0 if abs(vx) <= 1e-6 else (1 if vx > 0 else -1)
        self.pet.target_platform_id = side.id
        self.pet.target_window_id = side.source_id
        self.pet.support_platform_id = None
        self.pet.velocity.x = vx
        self.pet.velocity.y = vy
        if direction:
            self.pet.facing = Facing.RIGHT if direction > 0 else Facing.LEFT
        self._transition(PetState.JUMP)

    def _maybe_grab_climb_side_while_jumping(self) -> None:
        step = self.path_plan.current_step if self.path_plan else None
        side_id = self.pet.target_platform_id
        if step and step.action == TraversalAction.JUMP:
            candidate = self.snapshot.platform_by_id(step.to_surface_id)
            if candidate and candidate.climbable:
                side_id = step.to_surface_id

        side = self.snapshot.platform_by_id(side_id)
        if side is None or not side.climbable:
            self.pet.target_platform_id = None
            return

        target_x = side.rect.center_x - self.pet.width / 2
        target_bottom = side.rect.bottom
        if step and step.action == TraversalAction.JUMP and step.to_surface_id == side.id:
            if step.land_point is not None:
                target_x = step.land_point[0]
                target_bottom = step.land_point[1] + self.pet.height
            elif step.land_t is not None:
                target_bottom = step.land_t
        horizontal_close = abs(target_x - self.pet.position.x) <= self.config.physics.edge_snap_distance * 2
        bottom_gap = self.pet.bottom - target_bottom
        can_touch_now = abs(bottom_gap) <= self.config.physics.edge_snap_distance * 3
        if not horizontal_close or not can_touch_now:
            return

        self.pet.position.x = target_x
        self.pet.velocity.x = 0.0
        self.pet.velocity.y = 0.0
        self.pet.support_platform_id = None
        self.pet.target_platform_id = side.id
        self.pet.facing = Facing.RIGHT if side.type == PlatformType.WINDOW_LEFT else Facing.LEFT
        if step and step.action == TraversalAction.JUMP and step.to_surface_id == side.id:
            self.path_plan.advance()
            if self.path_plan.is_complete:
                self._finish_path_plan(finish_climb=True)
                return
        self._transition(PetState.CLIMB)

    def _snap_to_climb_side(self) -> None:
        side = self.snapshot.platform_by_id(self.pet.target_platform_id)
        if side is None:
            return
        self.pet.position.x = side.rect.center_x - self.pet.width / 2

    def _climb_reachability(self, side: Platform) -> str:
        reachability = ReachabilityPolicy(self.config.physics, self.config.physics.edge_snap_distance)
        top = self._top_platform_for_side(side)
        if top is None:
            return "unreachable"

        if not reachability.can_climb_to_top(side, top):
            return "unreachable"

        bottom_gap = self.pet.bottom - side.rect.bottom
        if bottom_gap <= self.config.physics.edge_snap_distance:
            return "stand"
        if bottom_gap <= self._max_jump_height():
            return "jump"
        return "unreachable"

    def _can_ever_reach_climb_side(self, side: Platform) -> bool:
        reachability = ReachabilityPolicy(self.config.physics, self.config.physics.edge_snap_distance)
        top = self._top_platform_for_side(side)
        if top is None:
            return False
        if not reachability.can_climb_to_top(side, top):
            return False
        bottom_gap = self.pet.bottom - side.rect.bottom
        return bottom_gap <= self._max_jump_height()

    def _top_platform_for_side(self, side: Platform) -> Platform | None:
        return self.snapshot.platform_by_id(PlatformTopology.top_id_for_side(side))

    def _max_jump_height(self) -> float:
        jump_speed_y = abs(self.config.physics.jump_speed_y)
        gravity = max(self.config.physics.gravity, 1.0)
        return jump_speed_y * jump_speed_y / (2.0 * gravity)

    def _max_jump_distance(self) -> float:
        jump_speed_y = abs(self.config.physics.jump_speed_y)
        gravity = max(self.config.physics.gravity, 1.0)
        air_time = 2.0 * jump_speed_y / gravity
        return self.config.physics.jump_speed_x * air_time

    def _keep_walking_on_platform(self, support: Platform | None, dt: float) -> None:
        now = time.monotonic()
        if support is None:
            return

        if self.pet.state == PetState.IDLE and now >= self._state_goal_until:
            if self._start_random_wander(support):
                return

        if self.pet.state == PetState.WALK:
            if self.pet.center_x < support.rect.left + self.pet.width * 0.65:
                self.pet.velocity.x = abs(self.config.physics.walk_speed)
                self.pet.facing = Facing.RIGHT
            elif self.pet.center_x > support.rect.right - self.pet.width * 0.65:
                self.pet.velocity.x = -abs(self.config.physics.walk_speed)
                self.pet.facing = Facing.LEFT

    def _start_random_wander(self, support: Platform) -> bool:
        plan = None
        if random.random() > LOCAL_WANDER_PROBABILITY:
            plan = self._random_reachable_platform_plan(support)
        if plan is None:
            plan = self._random_point_plan(support)
        if plan is None:
            self._pick_new_idle_goal()
            return True

        self.path_plan = plan
        self.pet.target_window_id = plan.target_window_id
        return True

    def _random_reachable_platform_plan(self, support: Platform) -> PathPlan | None:
        graph = self.pathfinder.build_surface_graph(self.pet, self.snapshot, self.config.physics)
        reachable = self._reachable_surface_ids(support.id, graph)
        candidates = [
            platform
            for platform in self.snapshot.platforms
            if platform.walkable and platform.id in reachable and platform.id != support.id
        ]
        if not candidates:
            return None

        random.shuffle(candidates)
        for platform in candidates:
            plan = self._random_point_plan(platform)
            if plan is not None:
                return plan
        return None

    def _random_point_plan(self, platform: Platform) -> PathPlan | None:
        target_x = self._random_x_on_platform(platform)
        if target_x is None:
            return None
        return self.pathfinder.find_path_to_surface_point(
            pet=self.pet,
            snapshot=self.snapshot,
            target_surface_id=platform.id,
            target_anchor_t=target_x,
            physics=self.config.physics,
            target_window_id=platform.source_id,
        )

    def _reachable_surface_ids(self, start_surface_id: str, graph) -> set[str]:
        start_node_ids = [node.id for node in graph.nodes.values() if node.surface_id == start_surface_id]
        seen_nodes = set(start_node_ids)
        seen_surfaces = {start_surface_id}
        stack = list(start_node_ids)
        while stack:
            node_id = stack.pop()
            for edge in graph.adjacency.get(node_id, []):
                target_node = graph.nodes.get(edge.to_node_id)
                if target_node is None:
                    continue
                seen_surfaces.add(target_node.surface_id)
                if target_node.id in seen_nodes:
                    continue
                seen_nodes.add(target_node.id)
                stack.append(target_node.id)
        return seen_surfaces

    def _random_x_on_platform(self, platform: Platform) -> float | None:
        left = platform.rect.left
        right = platform.rect.right - self.pet.width
        if right < left:
            return None
        if abs(right - left) <= WALK_TARGET_ARRIVAL_DISTANCE:
            return left

        min_distance = min(self.pet.width * MIN_WANDER_DISTANCE_FACTOR, max((right - left) / 2, 0.0))
        candidates = [
            target
            for target in (random.uniform(left, right) for _ in range(8))
            if abs(target - self.pet.position.x) >= min_distance
        ]
        if candidates:
            return random.choice(candidates)

        farther_endpoint = right if abs(right - self.pet.position.x) > abs(left - self.pet.position.x) else left
        if abs(farther_endpoint - self.pet.position.x) >= WALK_TARGET_ARRIVAL_DISTANCE:
            return farther_endpoint
        return None

    def _pick_new_idle_goal(self) -> None:
        self._state_goal_until = time.monotonic() + random.uniform(
            self.config.behavior.idle_min_seconds,
            self.config.behavior.idle_max_seconds,
        )

    def _transition(self, state: PetState) -> None:
        if self.pet.state == state:
            return
        self.state_machine.state = self.pet.state
        if self.state_machine.transition(state):
            self.pet.state = state
            self.pet.state_time = 0.0

    def _apply_motion_events(self, events) -> None:
        if events.support_lost and self.pet.state not in {PetState.DRAGGED, PetState.CLIMB}:
            self._transition(PetState.FALL)
        if events.landed_on and self.pet.state in {PetState.FALL, PetState.JUMP}:
            self.pet.velocity.x = 0.0
            self._transition(PetState.IDLE)

    def _record_drag(self, mouse_x: float, mouse_y: float) -> None:
        now = time.monotonic()
        self.pet.drag_positions.append((now, mouse_x, mouse_y))
        self.pet.drag_positions[:] = self.pet.drag_positions[-8:]

    def _drag_throw_velocity(self) -> Vec2:
        if len(self.pet.drag_positions) < 2:
            return Vec2()
        start = self.pet.drag_positions[0]
        end = self.pet.drag_positions[-1]
        dt = max(end[0] - start[0], 0.001)
        return Vec2((end[1] - start[1]) / dt, (end[2] - start[2]) / dt)

    def render_state(self) -> CharacterRenderState:
        return CharacterRenderState(
            x=self.pet.position.x,
            y=self.pet.position.y,
            width=self.pet.width,
            height=self.pet.height,
            body=self.pet,
            animation=self.animation,
        )

    def debug_state(self) -> CharacterDebugState:
        return CharacterDebugState(
            snapshot=self.snapshot,
            pathfinder=self.pathfinder,
            path_plan=self.path_plan,
            physics=self.config.physics,
        )
