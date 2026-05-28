from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

from desktop_sprite.core.animation_player import AnimationPlayer
from desktop_sprite.core.behavior_orchestrator import BehaviorOrchestrator, BehaviorPhaseName
from desktop_sprite.core.behavior_state_machine import BehaviorStateMachine
from desktop_sprite.core.character import CharacterDebugState, CharacterRenderState
from desktop_sprite.core.pathfinding import PathFinder, PathPlan, PathStep, TraversalAction
from desktop_sprite.core.path_executor import PathExecutor
from desktop_sprite.core.physics_engine import PhysicsEngine
from desktop_sprite.core.pet_mode import ModeController, PetMode
from desktop_sprite.environment.desktop_environment import DesktopEnvironment
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.geometry import Vec2
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.models.state import Facing, Pet, PetState
from desktop_sprite.utils.config import AppConfig


LOCAL_WANDER_PROBABILITY = 0.5
WALK_TARGET_ARRIVAL_DISTANCE = 0.8
MIN_WANDER_DISTANCE_FACTOR = 0.8
SHOW_RENDER_SCALE_X = 5.0
SHOW_RENDER_SCALE_Y = 2.6


@dataclass(slots=True)
class ShowContext:
    start_x: float
    start_y: float
    hover_x: float
    hover_y: float
    land_x: float
    land_y: float
    render_width: int
    render_height: int


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
        self.mode_controller = ModeController(PetMode.IDLE)
        self.orchestrator = BehaviorOrchestrator(BehaviorPhaseName.IDLE_WAIT)
        self.state_machine = BehaviorStateMachine(self.pet.state)
        self.animation = AnimationPlayer()
        self.snapshot = self.environment.snapshot()
        self._last_environment_refresh = 0.0
        self._state_goal_until = 0.0
        self._landed_on_platform_last_tick = False
        self._drag_offset = Vec2()
        self._show_context: ShowContext | None = None
        self._pick_new_idle_goal()

    def set_own_window_handle(self, hwnd: int | None) -> None:
        self.environment.set_own_window_handle(hwnd)

    def tick(self, dt: float) -> None:
        self._ensure_runtime_layers()
        self.orchestrator.tick(dt)
        self._refresh_environment_if_needed()
        if self.mode_controller.is_show():
            self._update_show()
            self.pet.state_time += dt
            self.animation.set_state(self.pet.state)
            self.animation.update(dt)
            return
        self._update_behavior(dt)
        old_state = self.pet.state
        old_support_surface_id = self.pet.support_surface_id
        motion_events = self.physics.update(self.pet, self.snapshot, dt)
        self._apply_motion_events(motion_events)
        self._landed_on_platform_last_tick = (
            old_support_surface_id is None
            and self.pet.support_surface_id is not None
            and old_state in {PetState.FALL, PetState.JUMP}
        )
        self.pet.state_time += dt
        self.animation.set_state(self.pet.state)
        self.animation.update(dt)

    def start_drag(self, mouse_x: float, mouse_y: float) -> None:
        if self._is_show_mode():
            return
        self._transition(PetState.DRAGGED)
        self.pet.support_surface_id = None
        self.pet.target_surface_id = None
        self.pet.velocity = Vec2()
        self.pet.drag_positions.clear()
        self._drag_offset = Vec2(mouse_x - self.pet.position.x, mouse_y - self.pet.position.y)
        self._record_drag(mouse_x, mouse_y)

    def drag_to(self, mouse_x: float, mouse_y: float) -> None:
        if self._is_show_mode():
            return
        if self.pet.state != PetState.DRAGGED:
            return
        self.pet.position.x = mouse_x - self._drag_offset.x
        self.pet.position.y = mouse_y - self._drag_offset.y
        self._record_drag(mouse_x, mouse_y)

    def release_drag(self, mouse_x: float, mouse_y: float) -> None:
        if self._is_show_mode():
            return
        self._record_drag(mouse_x, mouse_y)
        throw = self._drag_throw_velocity()
        if self.config.interaction.throw_enabled:
            self.pet.velocity.x = throw.x * self.config.physics.drag_throw_factor
            self.pet.velocity.y = throw.y * self.config.physics.drag_throw_factor
        self.pet.support_surface_id = None
        self._transition(PetState.FALL)

    def poke(self) -> None:
        if self._is_show_mode():
            return
        if self.pet.state == PetState.DRAGGED:
            return
        self.pet.velocity.y = min(self.pet.velocity.y, -220)
        self.pet.support_surface_id = None
        self._transition(PetState.FALL)

    def set_target_surface_point(self, surface_id: str, anchor_t: float) -> bool:
        self._ensure_runtime_layers()
        if self.mode_controller.is_show():
            return False
        target = self.snapshot.platform_by_id(surface_id)
        plan = self.pathfinder.find_path_to_surface_point(
            pet=self.pet,
            snapshot=self.snapshot,
            target_surface_id=surface_id,
            target_anchor_t=anchor_t,
            physics=self.config.physics,
            target_window_id=target.source_id if target else None,
        )
        if plan is None:
            return False

        self._start_path_plan(plan)
        return True

    def start_show(self) -> bool:
        self._ensure_runtime_layers()
        if self.mode_controller.is_show():
            return False

        render_width = round(self.pet.width * SHOW_RENDER_SCALE_X)
        render_height = round(self.pet.height * SHOW_RENDER_SCALE_Y)
        screen = self.snapshot.screen_rect
        work = self.snapshot.work_area_rect
        start_x = self.pet.position.x
        start_y = self.pet.position.y
        hover_x = screen.left + screen.width / 2 - self.pet.width / 2
        hover_y = screen.top + screen.height * 0.3
        land_x = hover_x
        land_y = work.bottom - self.pet.height

        self._show_context = ShowContext(
            start_x=start_x,
            start_y=start_y,
            hover_x=hover_x,
            hover_y=hover_y,
            land_x=land_x,
            land_y=land_y,
            render_width=render_width,
            render_height=render_height,
        )
        self.path_plan = None
        self.pet.target_window_id = None
        self.pet.support_surface_id = None
        self.pet.target_surface_id = None
        self.pet.velocity = Vec2()
        self.pet.position = Vec2(start_x, start_y)
        self.mode_controller.set_mode(PetMode.SHOW, force=True, lock=True)
        self.orchestrator.begin_show()
        self._transition(PetState.OPEN_WINGS)
        return True

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
        if self._is_show_mode():
            return
        if self.pet.state == PetState.DRAGGED:
            return

        if getattr(self, "_landed_on_platform_last_tick", False):
            self._landed_on_platform_last_tick = False
            return

        if self.path_plan is None and self.pet.state == PetState.WALK:
            self.pet.velocity.x = 0.0
            self._transition(PetState.IDLE)
            self._enter_idle_mode()
            return

        support = self.snapshot.platform_by_id(self.pet.support_surface_id)
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
            self._clear_path_plan()
            return
        if step.action == TraversalAction.MOVE and step.from_surface_id == step.to_surface_id:
            return
        if self.pet.support_surface_id != step.to_surface_id:
            return
        self.path_plan.advance()
        if self.path_plan.is_complete:
            self._finish_path_plan()

    def _finish_path_plan(self, *, finish_climb: bool = False) -> None:
        self._ensure_runtime_layers()
        self.orchestrator.advance(BehaviorPhaseName.PATH_FINISHED)
        self.path_plan = None
        self.pet.velocity.x = 0.0
        active_states = {PetState.FALL, PetState.JUMP, PetState.DRAGGED}
        if not finish_climb:
            active_states.add(PetState.CLIMB)
        if self.pet.state not in active_states:
            self._transition(PetState.IDLE)
            self._enter_idle_mode()
        else:
            self._enter_idle_mode(pick_new_goal=False)

    def _validate_path_plan(self) -> None:
        if self.path_plan is None:
            return
        step = self.path_plan.current_step
        if step is None:
            self._clear_path_plan()
            return
        if not self._is_path_step_present(step):
            self._clear_path_plan()

    def _start_path_plan(self, plan: PathPlan) -> None:
        self._ensure_runtime_layers()
        if self.mode_controller.is_show():
            return
        self.path_plan = plan
        self.pet.target_window_id = plan.target_window_id
        self.mode_controller.set_mode(PetMode.GO_TO_TARGET)
        self.orchestrator.begin(BehaviorPhaseName.PATH_EXECUTING)

    def _clear_path_plan(self) -> None:
        self.path_plan = None
        self._enter_idle_mode()

    def _enter_idle_mode(self, *, pick_new_goal: bool = True) -> None:
        self._ensure_runtime_layers()
        if not self.mode_controller.set_mode(PetMode.IDLE):
            return
        self.orchestrator.begin(BehaviorPhaseName.IDLE_WAIT)
        if pick_new_goal:
            self._pick_new_idle_goal()

    def _ensure_runtime_layers(self) -> None:
        if not hasattr(self, "mode_controller"):
            self.mode_controller = ModeController(PetMode.IDLE)
        if not hasattr(self, "orchestrator"):
            self.orchestrator = BehaviorOrchestrator(BehaviorPhaseName.IDLE_WAIT)

    def _is_path_step_present(self, step: PathStep) -> bool:
        if self.snapshot.platform_by_id(step.from_surface_id) is None:
            return False
        if self.snapshot.platform_by_id(step.to_surface_id) is None:
            return False
        if step.contact_surface_id and self.snapshot.platform_by_id(step.contact_surface_id) is None:
            return False
        return True

    def _is_show_mode(self) -> bool:
        self._ensure_runtime_layers()
        return self.mode_controller.is_show()

    def _update_show(self) -> None:
        context = getattr(self, "_show_context", None)
        if context is None:
            self._finish_show()
            return

        phase = self.orchestrator.phase.name
        self._sync_show_state_to_phase()
        if self.orchestrator.is_sequence_complete():
            self._finish_show()
            return

        if phase == BehaviorPhaseName.SHOW_OPEN_WINGS:
            self.pet.position = Vec2(context.start_x, context.start_y)
            return

        if phase == BehaviorPhaseName.SHOW_FLY:
            t = self._smooth_progress(self.orchestrator.phase_progress())
            self.pet.position = Vec2(
                self._lerp(context.start_x, context.hover_x, t),
                self._lerp(context.start_y, context.hover_y, t),
            )
            return

        if phase == BehaviorPhaseName.SHOW_HOVER:
            self.pet.position = Vec2(context.hover_x, context.hover_y + self._hover_offset())
            return

        if phase == BehaviorPhaseName.SHOW_TITLE:
            self.pet.position = Vec2(context.hover_x, context.hover_y + self._hover_offset())
            return

        if phase == BehaviorPhaseName.SHOW_LAND:
            t = self._smooth_progress(self.orchestrator.phase_progress())
            self.pet.position = Vec2(
                self._lerp(context.hover_x, context.land_x, t),
                self._lerp(context.hover_y, context.land_y, t),
            )
            return

        if phase == BehaviorPhaseName.SHOW_CLOSE_WINGS:
            self.pet.position = Vec2(context.land_x, context.land_y)

    def _sync_show_state_to_phase(self) -> None:
        state_by_phase = {
            BehaviorPhaseName.SHOW_OPEN_WINGS: PetState.OPEN_WINGS,
            BehaviorPhaseName.SHOW_FLY: PetState.FLY,
            BehaviorPhaseName.SHOW_HOVER: PetState.HOVER,
            BehaviorPhaseName.SHOW_TITLE: PetState.HOVER,
            BehaviorPhaseName.SHOW_LAND: PetState.WING_LAND,
            BehaviorPhaseName.SHOW_CLOSE_WINGS: PetState.CLOSE_WINGS,
        }
        state = state_by_phase.get(self.orchestrator.phase.name)
        if state is not None:
            self._transition(state)

    def _finish_show(self) -> None:
        context = getattr(self, "_show_context", None)
        if context is not None:
            self.pet.position = Vec2(context.land_x, context.land_y)
        self._show_context = None
        self.pet.velocity = Vec2()
        self.pet.support_surface_id = None
        self.pet.target_surface_id = None
        self.mode_controller.unlock()
        self.mode_controller.set_mode(PetMode.IDLE, force=True)
        self.orchestrator.begin(BehaviorPhaseName.IDLE_WAIT)
        self._transition(PetState.IDLE)
        self._pick_new_idle_goal()

    def _hover_offset(self) -> float:
        return math.sin(self.pet.state_time * 2.2) * 8.0

    def _smooth_progress(self, value: float) -> float:
        t = min(max(value, 0.0), 1.0)
        return t * t * (3.0 - 2.0 * t)

    def _lerp(self, start: float, end: float, t: float) -> float:
        return start + (end - start) * t

    def _executor(self) -> PathExecutor:
        executor = getattr(self, "path_executor", None)
        if executor is None:
            executor = PathExecutor(self)
            self.path_executor = executor
        return executor

    def _maybe_grab_climb_side_while_jumping(self) -> None:
        step = self.path_plan.current_step if self.path_plan else None
        side_id = self.pet.target_surface_id
        if step and step.action == TraversalAction.JUMP:
            candidate = self.snapshot.platform_by_id(step.to_surface_id)
            if candidate and candidate.climbable:
                side_id = step.to_surface_id

        side = self.snapshot.platform_by_id(side_id)
        if side is None or not side.climbable:
            self.pet.target_surface_id = None
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
        self.pet.support_surface_id = None
        self.pet.target_surface_id = side.id
        self.pet.facing = Facing.RIGHT if side.type == PlatformType.WINDOW_LEFT else Facing.LEFT
        if step and step.action == TraversalAction.JUMP and step.to_surface_id == side.id:
            self.path_plan.advance()
            if self.path_plan.is_complete:
                self._finish_path_plan(finish_climb=True)
                return
        self._transition(PetState.CLIMB)

    def _snap_to_climb_side(self) -> None:
        side = self.snapshot.platform_by_id(self.pet.target_surface_id)
        if side is None:
            return
        self.pet.position.x = side.rect.center_x - self.pet.width / 2

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
        if self._is_show_mode():
            return True
        plan = None
        if random.random() > LOCAL_WANDER_PROBABILITY:
            plan = self._random_reachable_platform_plan(support)
        if plan is None:
            plan = self._random_point_plan(support)
        if plan is None:
            self._pick_new_idle_goal()
            return True

        self._start_path_plan(plan)
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
        context = getattr(self, "_show_context", None)
        width = context.render_width if context is not None else self.pet.width
        height = context.render_height if context is not None else self.pet.height
        body_offset_x = (width - self.pet.width) / 2 if context is not None else 0.0
        body_offset_y = (height - self.pet.height) / 2 if context is not None else 0.0
        return CharacterRenderState(
            x=self.pet.position.x - body_offset_x,
            y=self.pet.position.y - body_offset_y,
            width=width,
            height=height,
            body=self.pet,
            animation=getattr(self, "animation", None),
            body_width=self.pet.width,
            body_height=self.pet.height,
            body_offset_x=body_offset_x,
            body_offset_y=body_offset_y,
        )

    def debug_state(self) -> CharacterDebugState:
        self._ensure_runtime_layers()
        return CharacterDebugState(
            snapshot=self.snapshot,
            pathfinder=self.pathfinder,
            path_plan=self.path_plan,
            physics=self.config.physics,
            mode=self.mode_controller.mode,
            phase=self.orchestrator.phase.name,
            phase_elapsed=self.orchestrator.phase.elapsed,
        )
