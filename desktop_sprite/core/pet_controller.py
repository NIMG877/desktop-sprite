from __future__ import annotations

import random
import time

from desktop_sprite.core.animation_player import AnimationPlayer
from desktop_sprite.core.behavior_state_machine import BehaviorStateMachine
from desktop_sprite.core.physics_engine import PhysicsEngine
from desktop_sprite.environment.desktop_environment import DesktopEnvironment
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.geometry import Vec2
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.models.state import Facing, Pet, PetState
from desktop_sprite.utils.config import AppConfig


class PetController:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.pet = Pet(
            position=Vec2(config.pet.default_spawn_x, config.pet.default_spawn_y),
            velocity=Vec2(),
            width=config.pet.width,
            height=config.pet.height,
        )
        self.environment = DesktopEnvironment(config.pet.width, config.pet.height)
        self.physics = PhysicsEngine(config.physics)
        self.state_machine = BehaviorStateMachine(self.pet.state)
        self.animation = AnimationPlayer()
        self.snapshot = self.environment.snapshot()
        self._last_environment_refresh = 0.0
        self._state_goal_until = 0.0
        self._drag_offset = Vec2()
        self._pick_new_idle_goal()

    def set_own_window_handle(self, hwnd: int | None) -> None:
        self.environment.set_own_window_handle(hwnd)

    def tick(self, dt: float) -> None:
        self._refresh_environment_if_needed()
        self._update_behavior(dt)
        self.physics.update(self.pet, self.snapshot, dt)
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
        self._last_environment_refresh = now

    def _update_behavior(self, dt: float) -> None:
        if self.pet.state == PetState.DRAGGED:
            return

        support = self.snapshot.platform_by_id(self.pet.support_platform_id)
        if support is None and self.pet.state not in {PetState.FALL, PetState.JUMP, PetState.CLIMB}:
            self._transition(PetState.FALL)
            return

        if self.pet.state == PetState.FALL:
            return

        if self.pet.state == PetState.JUMP:
            self._maybe_grab_climb_side_while_jumping()
            return

        if self.pet.state == PetState.CLIMB:
            self._snap_to_climb_side()
            return

        self._maybe_target_foreground_window()
        target_side = self.snapshot.platform_by_id(self.pet.target_platform_id)
        if target_side and target_side.climbable:
            self._walk_toward_climb_side(target_side)
            return

        self._keep_walking_on_platform(support, dt)

    def _maybe_target_foreground_window(self) -> None:
        if not self.config.behavior.prefer_foreground_window:
            return
        if self.pet.target_platform_id and self.snapshot.platform_by_id(self.pet.target_platform_id):
            return
        foreground = self.snapshot.foreground_window
        if foreground is None:
            return
        if self.pet.support_platform_id and self.pet.support_platform_id.startswith(f"window:{foreground.hwnd}:top"):
            return

        side = self._nearest_reachable_side_for_window(foreground.hwnd)
        if side is None:
            return
        self.pet.target_platform_id = side.id
        self.pet.target_window_id = foreground.hwnd
        self._transition(PetState.MOVE_TO_TARGET)

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
        self._transition(PetState.MOVE_TO_TARGET)

    def _start_jump_toward_climb_side(self, side: Platform, distance: float) -> None:
        direction = 0
        if abs(distance) > self.config.physics.edge_snap_distance:
            direction = 1 if distance > 0 else -1

        self.pet.target_platform_id = side.id
        self.pet.target_window_id = side.source_id
        self.pet.support_platform_id = None
        self.pet.velocity.x = direction * self.config.physics.jump_speed_x
        self.pet.velocity.y = self.config.physics.jump_speed_y
        if direction:
            self.pet.facing = Facing.RIGHT if direction > 0 else Facing.LEFT
        self._transition(PetState.JUMP)

    def _maybe_grab_climb_side_while_jumping(self) -> None:
        side = self.snapshot.platform_by_id(self.pet.target_platform_id)
        if side is None or not side.climbable:
            self.pet.target_platform_id = None
            return

        top = self._top_platform_for_side(side)
        if top is None:
            self.pet.target_platform_id = None
            return

        target_x = side.rect.center_x - self.pet.width / 2
        horizontal_close = abs(target_x - self.pet.position.x) <= self.config.physics.edge_snap_distance * 2
        current_reach_height = self.pet.bottom - top.rect.top
        can_touch_now = -self.pet.height * 0.15 <= current_reach_height <= self.pet.height + 12
        if not horizontal_close or not can_touch_now:
            return

        self.pet.position.x = target_x
        self.pet.velocity.x = 0.0
        self.pet.velocity.y = 0.0
        self.pet.support_platform_id = None
        self.pet.target_platform_id = side.id
        self.pet.facing = Facing.RIGHT if side.type == PlatformType.WINDOW_LEFT else Facing.LEFT
        self._transition(PetState.CLIMB)

    def _snap_to_climb_side(self) -> None:
        side = self.snapshot.platform_by_id(self.pet.target_platform_id)
        if side is None:
            return
        self.pet.position.x = side.rect.center_x - self.pet.width / 2

    def _climb_reachability(self, side: Platform) -> str:
        top = self._top_platform_for_side(side)
        if top is None:
            return "unreachable"

        required_height = max(0.0, self.pet.bottom - top.rect.top)
        if required_height <= self.pet.height + 4:
            return "stand"
        if required_height <= self.pet.height + self._max_jump_height():
            return "jump"
        return "unreachable"

    def _can_ever_reach_climb_side(self, side: Platform) -> bool:
        top = self._top_platform_for_side(side)
        if top is None:
            return False
        required_height = max(0.0, self.pet.bottom - top.rect.top)
        return required_height <= self.pet.height + self._max_jump_height()

    def _top_platform_for_side(self, side: Platform) -> Platform | None:
        if side.source_id is None:
            return None
        return self.snapshot.platform_by_id(f"window:{side.source_id}:top")

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
            self._transition(PetState.WALK)
            direction = random.choice([-1, 1])
            self.pet.velocity.x = direction * self.config.physics.walk_speed
            self.pet.facing = Facing.RIGHT if direction > 0 else Facing.LEFT
            self._state_goal_until = now + random.uniform(
                self.config.behavior.walk_min_seconds,
                self.config.behavior.walk_max_seconds,
            )

        if self.pet.state in {PetState.WALK, PetState.MOVE_TO_TARGET}:
            if self.pet.center_x < support.rect.left + self.pet.width * 0.65:
                self.pet.velocity.x = abs(self.config.physics.walk_speed)
                self.pet.facing = Facing.RIGHT
            elif self.pet.center_x > support.rect.right - self.pet.width * 0.65:
                self.pet.velocity.x = -abs(self.config.physics.walk_speed)
                self.pet.facing = Facing.LEFT

            if now >= self._state_goal_until:
                self.pet.velocity.x = 0.0
                self._transition(PetState.IDLE)
                self._pick_new_idle_goal()

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
