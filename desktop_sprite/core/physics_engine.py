"""Physics engine.

A pure kinematics + collision module. It mutates ``pet.position``,
``pet.velocity``, ``pet.support_surface_id`` and ``pet.target_surface_id``
in place but **never** writes ``pet.state`` or ``pet.state_time`` —
those are owned exclusively by :class:`PetStateMediator`. State
transitions in response to physics are signalled through
:class:`MotionEvents` and consumed by the controller (which delegates
to the mediator).

The contract for callers is:

    events = physics.update(pet, snapshot, dt)
    controller._apply_motion_events(events)   # calls mediator.transition

This split keeps the state machine as the single source of truth for
``pet.state`` and lets the physics engine stay free of any
``BehaviorStateMachine`` coupling.
"""

from __future__ import annotations

from dataclasses import dataclass

from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.state import Facing, Pet, PetState
from desktop_sprite.utils.config import PhysicsConfig


@dataclass(slots=True)
class MotionEvents:
    """Semantic events emitted by a single physics update.

    The controller translates these into state transitions via the
    mediator. Physics itself never writes ``pet.state``.

    * ``landed_on`` — pet came to rest on the named platform this
      frame (was airborne). Caller transitions FALL/JUMP → IDLE.
    * ``support_lost`` — pet's standing support disappeared while not
      in a DRAGGED or CLIMB state. Caller transitions → FALL.
    * ``climb_support_lost`` — pet was CLIMB and the climb surface
      disappeared or became non-climbable. Caller transitions
      CLIMB → FALL.
    """

    landed_on: str | None = None
    support_lost: bool = False
    climb_support_lost: bool = False


class PhysicsEngine:
    def __init__(self, config: PhysicsConfig) -> None:
        self.config = config

    def reconcile_platform_motion(
        self,
        pet: Pet,
        previous_snapshot: EnvironmentSnapshot,
        current_snapshot: EnvironmentSnapshot,
    ) -> None:
        if pet.state == PetState.DRAGGED or pet.support_surface_id is None:
            return

        previous = previous_snapshot.platform_by_id(pet.support_surface_id)
        current = current_snapshot.platform_by_id(pet.support_surface_id)
        if previous is None or current is None or not current.dynamic or not current.walkable:
            return

        dy = current.rect.top - previous.rect.top
        if dy >= 0:
            return
        if not pet.rect.overlaps_x(current.rect):
            return

        pet.position.y += dy
        if pet.velocity.y > 0:
            pet.velocity.y = 0.0

    def update(self, pet: Pet, snapshot: EnvironmentSnapshot, dt: float) -> MotionEvents:
        events = MotionEvents()
        if pet.state == PetState.DRAGGED:
            self._clamp_to_work_area(pet, snapshot, events)
            return events
        if pet.state == PetState.CLIMB:
            self._validate_climb_support(pet, snapshot, events)
            if not events.climb_support_lost:
                pet.position.x += pet.velocity.x * dt
                pet.position.y += pet.velocity.y * dt
            self._clamp_to_work_area(pet, snapshot, events)
            self._clamp_to_screen(pet, snapshot, events)
            return events

        self._validate_support(pet, snapshot, events)
        old_bottom = pet.bottom

        if pet.support_surface_id is None:
            pet.velocity.y = min(
                pet.velocity.y + self.config.gravity * dt,
                self.config.max_fall_speed,
            )
        else:
            pet.velocity.y = 0.0

        pet.position.x += pet.velocity.x * dt
        pet.position.y += pet.velocity.y * dt

        self._clamp_to_work_area(pet, snapshot, events)
        self._resolve_platform_landing(pet, snapshot, old_bottom, events)
        self._clamp_to_work_area(pet, snapshot, events)
        self._clamp_to_screen(pet, snapshot, events)
        return events

    def _validate_climb_support(
        self,
        pet: Pet,
        snapshot: EnvironmentSnapshot,
        events: MotionEvents,
    ) -> None:
        side = snapshot.platform_by_id(pet.support_surface_id or pet.target_surface_id)
        if side is None or not side.climbable:
            events.climb_support_lost = True
            pet.support_surface_id = None
            pet.target_surface_id = None
            return
        pet.support_surface_id = side.id
        pet.target_surface_id = side.id

    def _resolve_platform_landing(
        self,
        pet: Pet,
        snapshot: EnvironmentSnapshot,
        old_bottom: float,
        events: MotionEvents,
    ) -> None:
        if pet.velocity.y < 0:
            return

        candidates = [
            platform
            for platform in snapshot.platforms
            if platform.walkable
            and old_bottom <= platform.rect.top <= pet.bottom
            and pet.rect.overlaps_x(platform.rect)
        ]
        if not candidates:
            if pet.support_surface_id and snapshot.platform_by_id(pet.support_surface_id) is None:
                pet.support_surface_id = None
                events.support_lost = True
            return

        platform = min(candidates, key=lambda item: item.rect.top)
        pet.position.y = platform.rect.top - pet.height
        pet.velocity.y = 0.0
        pet.support_surface_id = platform.id
        events.landed_on = platform.id
        if pet.state in {PetState.FALL, PetState.JUMP}:
            pet.velocity.x = 0.0

    def _clamp_horizontal(self, pet: Pet, snapshot: EnvironmentSnapshot) -> None:
        bounds = snapshot.work_area_rect
        if pet.position.x < bounds.left:
            pet.position.x = bounds.left
            pet.velocity.x = abs(pet.velocity.x)
            pet.facing = Facing.RIGHT
        elif pet.position.x + pet.width > bounds.right:
            pet.position.x = bounds.right - pet.width
            pet.velocity.x = -abs(pet.velocity.x)
            pet.facing = Facing.LEFT

    def _validate_support(
        self,
        pet: Pet,
        snapshot: EnvironmentSnapshot,
        events: MotionEvents,
    ) -> None:
        if pet.support_surface_id is None:
            return

        platform = snapshot.platform_by_id(pet.support_surface_id)
        if platform is None or not platform.walkable:
            pet.support_surface_id = None
            events.support_lost = True
            return

        vertical_tolerance = 3.0
        is_on_top = abs(pet.bottom - platform.rect.top) <= vertical_tolerance
        overlaps = pet.rect.overlaps_x(platform.rect)
        if is_on_top and overlaps:
            return

        pet.support_surface_id = None
        events.support_lost = True

    def _clamp_to_work_area(self, pet: Pet, snapshot: EnvironmentSnapshot, events: MotionEvents) -> None:
        self._clamp_horizontal(pet, snapshot)
        self._resolve_ceiling_boundary(pet, snapshot)
        self._resolve_floor_boundary(pet, snapshot, events)

    def _resolve_ceiling_boundary(self, pet: Pet, snapshot: EnvironmentSnapshot) -> None:
        ceiling_y = snapshot.work_area_rect.top
        if pet.position.y >= ceiling_y:
            return

        pet.position.y = ceiling_y
        if pet.velocity.y < 0:
            pet.velocity.y = 0.0

    def _resolve_floor_boundary(self, pet: Pet, snapshot: EnvironmentSnapshot, events: MotionEvents) -> None:
        floor_y = snapshot.work_area_rect.bottom
        if pet.bottom <= floor_y:
            return

        pet.position.y = floor_y - pet.height
        pet.velocity.y = 0.0
        pet.support_surface_id = "ground:work_area"
        events.landed_on = "ground:work_area"
        if pet.state in {PetState.FALL, PetState.JUMP}:
            pet.velocity.x = 0.0

    def _clamp_to_screen(self, pet: Pet, snapshot: EnvironmentSnapshot, events: MotionEvents) -> None:
        bottom_limit = snapshot.screen_rect.bottom + pet.height * 2
        if pet.position.y > bottom_limit:
            pet.position.y = snapshot.work_area_rect.bottom - pet.height
            pet.velocity.y = 0.0
            pet.support_surface_id = "ground:work_area"
            events.landed_on = "ground:work_area"
