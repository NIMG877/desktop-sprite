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
from desktop_sprite.core.pet_mode import ModeController, PetMode
from desktop_sprite.core.pet_show_director import (
    SHOW_HOVER_SECONDS,
    FlightAbility,
    HoverAbility,
    PetShowDirector,
    ShowContext,
    WingAbility,
)
from desktop_sprite.core.physics_engine import PhysicsEngine
from desktop_sprite.core.show_phase_durations import (
    SHOW_RENDER_SCALE_X,
    SHOW_RENDER_SCALE_Y,
    SHOW_TITLE_SECONDS,
)
from desktop_sprite.environment.desktop_environment import DesktopEnvironment
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.geometry import Vec2
from desktop_sprite.models.pet_attribute import (
    PetAttributeSheet,
    PetEffectiveStats,
    PetResourceInfluence,
    PetRuntimeResources,
)
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.models.state import Facing, Pet, PetState
from desktop_sprite.utils.config import AppConfig, PhysicsConfig


PetAbility = WingAbility | FlightAbility | HoverAbility


WALK_TARGET_ARRIVAL_DISTANCE = 0.8


class PetController:
    WALK_TARGET_ARRIVAL_DISTANCE = WALK_TARGET_ARRIVAL_DISTANCE

    # ------------------------------------------------------------------
    # Mediator shim (P0-C)
    #
    # Code that predates the `PetStateMediator` reaches into the
    # controller to read or write `state_machine`, `orchestrator`, or
    # `mode_controller` directly. The fragile
    # `test_pet_controller_climb_reach.py` constructs controllers with
    # `__new__` and assigns those names by hand; the production
    # `PetController.__init__` no longer sets them. `__getattr__`
    # forwards to the mediator so both styles work; it only fires on
    # attribute miss, so a test-set instance attribute still wins.
    # ------------------------------------------------------------------
    _MEDIATOR_FORWARD = frozenset(
        {"mediator", "state_machine", "orchestrator", "mode_controller"}
    )

    def __getattr__(self, name: str):
        if name not in self._MEDIATOR_FORWARD:
            raise AttributeError(name)
        # Use object.__getattribute__ to bypass our own __getattr__
        # while we look up the mediator.
        d = object.__getattribute__(self, "__dict__")
        mediator = d.get("mediator")
        if mediator is None:
            raise AttributeError(name)
        return getattr(mediator, name)

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.attribute_sheet = PetAttributeSheet.from_config(config)
        self._effective_stats = PetEffectiveStats.from_sheet(config, self.attribute_sheet)
        self.resources = PetRuntimeResources.from_stats(self._effective_stats)
        self._own_window_handle: int | None = None
        self.pet = Pet(
            position=Vec2(config.pet.default_spawn_x, config.pet.default_spawn_y),
            velocity=Vec2(),
            width=config.pet.width,
            height=config.pet.height,
        )
        self.environment = DesktopEnvironment(config.pet.width, config.pet.height)
        self.physics = PhysicsEngine(self._effective_stats.physics)
        self.pathfinder = PathFinder()
        self.path_executor = PathExecutor(self)
        self.path_plan: PathPlan | None = None
        # State truth source: a single mediator that owns the
        # state machine, the orchestrator, the mode controller, and
        # the pet.  Sub-attributes (`state_machine`, `orchestrator`,
        # `mode_controller`) are still reachable on the controller
        # via the `__getattr__` shim for backward compatibility with
        # code that pre-dates the mediator.
        from desktop_sprite.core.pet_state_mediator import PetStateMediator

        self.mediator = PetStateMediator(
            pet=self.pet,
            state_machine=BehaviorStateMachine(self.pet.state),
            orchestrator=BehaviorOrchestrator(BehaviorPhaseName.IDLE_WAIT),
            mode_controller=ModeController(PetMode.IDLE),
        )
        self.animation = AnimationPlayer()
        self.snapshot = self.environment.snapshot()
        self._last_environment_refresh = 0.0
        self._state_goal_until = 0.0
        self._landed_on_platform_last_tick = False
        self._drag_offset = Vec2()
        self._show_context: ShowContext | None = None
        self._active_pet_ability: PetAbility | None = None
        self._show_director = PetShowDirector()
        self._auto_sleeping = False
        self._resource_resting = False
        self._seeking_food = False
        self._pick_new_idle_goal()

    def set_own_window_handle(self, hwnd: int | None) -> None:
        self._own_window_handle = hwnd
        self.environment.set_own_window_handle(hwnd)

    def apply_config(self, config: AppConfig) -> None:
        size_changed = self.pet.width != config.pet.width or self.pet.height != config.pet.height
        # A size change rebuilds the environment + snapshot, which
        # would invalidate the in-flight ShowContext (hover/land
        # coordinates captured against the old snapshot). Finish the
        # Show first so its closing frames still land on the old
        # surface, and the *next* Show is built from the new env.
        if size_changed and self._is_show_mode():
            self._finish_show()
        modifiers = getattr(self, "attribute_sheet", PetAttributeSheet.from_config(self.config)).modifiers
        self.config = config
        self.attribute_sheet = PetAttributeSheet.from_config(config).with_modifiers(modifiers)
        self._refresh_effective_stats()
        if size_changed:
            self.pet.width = config.pet.width
            self.pet.height = config.pet.height
            self.environment = DesktopEnvironment(config.pet.width, config.pet.height)
            self.environment.set_own_window_handle(self._own_window_handle)
            self.snapshot = self.environment.snapshot()
            self.path_plan = None
        self._state_goal_until = min(self._state_goal_until, time.monotonic())

    def set_attribute_sheet(self, attribute_sheet: PetAttributeSheet) -> None:
        self.attribute_sheet = attribute_sheet
        self._refresh_effective_stats()

    def _refresh_effective_stats(self) -> None:
        self._effective_stats = PetEffectiveStats.from_sheet(self.config, self.attribute_sheet)
        if not hasattr(self, "resources"):
            self.resources = PetRuntimeResources.from_stats(self._effective_stats)
        else:
            self.resources.clamp_to_stats(self._effective_stats)
        if hasattr(self, "physics"):
            self.physics.config = self.runtime_physics()

    def effective_stats(self) -> PetEffectiveStats:
        stats = getattr(self, "_effective_stats", None)
        if stats is None:
            sheet = getattr(self, "attribute_sheet", PetAttributeSheet.from_config(self.config))
            stats = PetEffectiveStats.from_sheet(self.config, sheet)
            self._effective_stats = stats
        return stats

    def runtime_physics(self) -> PhysicsConfig:
        stats = self.effective_stats()
        return replace_physics_movement(stats.physics, self._resource_influence())

    def tick(self, dt: float) -> None:
        self._ensure_runtime_layers()
        self.physics.config = self.runtime_physics()
        self.orchestrator.tick(dt)
        self._refresh_environment_if_needed()
        if self.mode_controller.is_show():
            self._update_show(dt)
            self._tick_resources(dt)
            self.pet.state_time += dt
            self.animation.set_state(self.pet.state)
            self.animation.update(dt)
            return
        self._update_behavior(dt)
        old_state = self.pet.state
        old_support_surface_id = self.pet.support_surface_id
        motion_events = self.physics.update(self.pet, self.snapshot, dt)
        self._apply_motion_events(motion_events)
        self._tick_resources(dt)
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

    def sleep(self) -> bool:
        if self._is_show_mode():
            return False
        if self.pet.state not in {PetState.IDLE, PetState.WALK, PetState.SLEEP}:
            return False

        self.path_plan = None
        self.pet.target_window_id = None
        self.pet.target_surface_id = None
        self.pet.velocity.x = 0.0
        self.mode_controller.set_mode(PetMode.IDLE)
        self.orchestrator.begin(BehaviorPhaseName.IDLE_WAIT)
        self._transition(PetState.SLEEP)
        return True

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
            physics=self.runtime_physics(),
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
        # Set the mode and orchestrator *before* handing control to the
        # director: the director's `_start_open_wings` calls
        # `controller._transition(OPEN_WINGS)`, which expects the
        # orchestrator/state_machine to already be live.
        self.mode_controller.set_mode(PetMode.SHOW, force=True, lock=True)
        self.orchestrator.begin_show()
        self.pet.position = Vec2(start_x, start_y)
        self._show_director.start(self, self._show_context)
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

        if self._apply_resource_behavior():
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
        if not hasattr(self, "mediator"):
            from desktop_sprite.core.pet_state_mediator import PetStateMediator

            self.mediator = PetStateMediator(
                pet=self.pet,
                state_machine=BehaviorStateMachine(self.pet.state),
                orchestrator=BehaviorOrchestrator(BehaviorPhaseName.IDLE_WAIT),
                mode_controller=ModeController(PetMode.IDLE),
            )
        if not hasattr(self, "_show_director"):
            self._show_director = PetShowDirector()

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

    def _update_show(self, dt: float = 0.0) -> None:
        """Per-frame Show tick. Delegates to the show director.

        Kept as a method (rather than a one-liner in `tick`) so the
        fragile `test_pet_controller_climb_reach.py` can call it
        directly to drive a Show sequence manually.
        """
        self._ensure_runtime_layers()
        if self._show_director.update(self, dt):
            self._finish_show()

    def _finish_show(self) -> None:
        """Hand the controller back to idle after the Show sequence ends."""
        self._ensure_runtime_layers()
        self._show_director.finish(self)

    def _start_show_phase_ability(
        self, phase: BehaviorPhaseName | str, context: ShowContext
    ) -> None:
        """Deprecated shim — see `PetShowDirector._start_phase_ability`."""
        self._ensure_runtime_layers()
        self._show_director._start_phase_ability(self, phase, context)

    def _start_open_wings(self) -> None:
        """Deprecated shim — see `PetShowDirector._start_open_wings`."""
        self._ensure_runtime_layers()
        self._show_director._start_open_wings(self)

    def _start_close_wings(self) -> None:
        """Deprecated shim — see `PetShowDirector._start_close_wings`."""
        self._ensure_runtime_layers()
        self._show_director._start_close_wings(self)

    def _start_flight_to(
        self, target_x: float, target_y: float, *, state: PetState, speed: float
    ) -> None:
        """Deprecated shim — see `PetShowDirector._start_flight_to`."""
        self._ensure_runtime_layers()
        self._show_director._start_flight_to(
            self, target_x, target_y, state=state, speed=speed
        )

    def _start_hover(
        self, base_x: float, base_y: float, duration: float | None = None
    ) -> None:
        """Deprecated shim — see `PetShowDirector._start_hover`."""
        self._ensure_runtime_layers()
        self._show_director._start_hover(self, base_x, base_y, duration)

    def _update_pet_ability(self, dt: float) -> bool:
        """Deprecated shim — see `PetShowDirector._update_ability`."""
        self._ensure_runtime_layers()
        return self._show_director._update_ability(self, dt)

    def _update_flight_ability(self, ability: FlightAbility, dt: float) -> bool:
        """Deprecated shim — see `PetShowDirector._update_flight`."""
        self._ensure_runtime_layers()
        return self._show_director._update_flight(self, ability, dt)

    def _update_hover_ability(self, ability: HoverAbility, dt: float) -> bool:
        """Deprecated shim — see `PetShowDirector._update_hover`."""
        self._ensure_runtime_layers()
        return self._show_director._update_hover(self, ability, dt)

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
        horizontal_close = abs(target_x - self.pet.position.x) <= self.runtime_physics().edge_snap_distance * 2
        bottom_gap = self.pet.bottom - target_bottom
        can_touch_now = abs(bottom_gap) <= self.runtime_physics().edge_snap_distance * 3
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
                self.pet.velocity.x = abs(self.runtime_physics().walk_speed)
                self.pet.facing = Facing.RIGHT
            elif self.pet.center_x > support.rect.right - self.pet.width * 0.65:
                self.pet.velocity.x = -abs(self.runtime_physics().walk_speed)
                self.pet.facing = Facing.LEFT

    def _start_random_wander(self, support: Platform) -> bool:
        if self._is_show_mode():
            return True
        plan = None
        if random.random() < self.effective_stats().reachable_wander_probability * self._resource_influence().wander_factor:
            plan = self._random_reachable_platform_plan(support)
        if plan is None:
            plan = self._random_point_plan(support)
        if plan is None:
            self._pick_new_idle_goal()
            return True

        self._start_path_plan(plan)
        return True

    def _random_reachable_platform_plan(self, support: Platform) -> PathPlan | None:
        graph = self.pathfinder.build_surface_graph(self.pet, self.snapshot, self.runtime_physics())
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
            physics=self.runtime_physics(),
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

        min_distance = min(
            self.pet.width * self.effective_stats().min_wander_distance_factor,
            max((right - left) / 2, 0.0),
        )
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
            self.effective_stats().idle_min_seconds,
            max(self.effective_stats().idle_max_seconds, self.effective_stats().idle_min_seconds),
        )

    def _transition(self, state: PetState) -> None:
        if self.pet.state == state:
            return
        self._ensure_runtime_layers()
        self.mediator.transition(state)

    def _apply_motion_events(self, events) -> None:
        # Physics emits *events*; this method is the only path that
        # translates them into ``pet.state`` transitions. Going through
        # ``_transition`` (which delegates to the mediator) keeps the
        # state machine as the single writer for ``pet.state`` and
        # ``pet.state_time`` — physics never touches them.
        if events.climb_support_lost:
            self._transition(PetState.FALL)
        elif events.support_lost and self.pet.state != PetState.DRAGGED:
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
            physics=self.runtime_physics(),
            mode=self.mode_controller.mode,
            phase=self.orchestrator.phase.name,
            phase_elapsed=self.orchestrator.phase.elapsed,
        )

    def _tick_resources(self, dt: float) -> None:
        if not hasattr(self, "resources"):
            self.resources = PetRuntimeResources.from_stats(self.effective_stats())
        self.resources.tick(self.pet.state, dt, self.effective_stats())

    def _resource_influence(self) -> PetResourceInfluence:
        resources = getattr(self, "resources", None)
        if resources is None:
            return PetRuntimeResources.from_stats(self.effective_stats()).influence(self.effective_stats())
        return resources.influence(self.effective_stats())

    def _apply_resource_behavior(self) -> bool:
        influence = self._resource_influence()
        if self.pet.state == PetState.SLEEP:
            if getattr(self, "_auto_sleeping", False) and influence.should_wake:
                self._auto_sleeping = False
                self._transition(PetState.IDLE)
                self._pick_new_idle_goal()
            return True

        if influence.should_sleep and self.pet.state in {PetState.IDLE, PetState.WALK}:
            self._auto_sleeping = True
            self.sleep()
            return True

        if getattr(self, "_resource_resting", False):
            if influence.should_stop_rest:
                self._resource_resting = False
                self._pick_new_idle_goal()
                return False
            self.path_plan = None
            self.pet.velocity.x = 0.0
            self._transition(PetState.IDLE)
            return True

        if influence.should_rest and self.pet.state in {PetState.IDLE, PetState.WALK} and self.path_plan is None:
            self._resource_resting = True
            self.pet.velocity.x = 0.0
            self._transition(PetState.IDLE)
            self._pick_new_idle_goal()
            return True

        self._seeking_food = influence.should_seek_food or (
            getattr(self, "_seeking_food", False) and not influence.should_stop_seek_food
        )
        return False


def replace_physics_movement(physics: PhysicsConfig, influence: PetResourceInfluence) -> PhysicsConfig:
    return PhysicsConfig(
        gravity=physics.gravity,
        walk_speed=max(physics.walk_speed * influence.movement_factor, 1.0),
        climb_speed=max(physics.climb_speed * influence.climb_factor, 1.0),
        jump_speed_x=physics.jump_speed_x * influence.jump_factor,
        jump_speed_y=physics.jump_speed_y * influence.jump_factor,
        max_fall_speed=physics.max_fall_speed,
        drag_throw_factor=physics.drag_throw_factor,
        edge_snap_distance=physics.edge_snap_distance,
    )
