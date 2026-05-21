from __future__ import annotations

from dataclasses import dataclass

from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.core.stamina_system import StaminaSystem
from desktop_sprite.models.platform import Platform
from desktop_sprite.models.platform_topology import PlatformTopology
from desktop_sprite.models.state import Facing, Pet, PetState
from desktop_sprite.utils.config import PhysicsConfig


@dataclass(slots=True)
class MotionEvents:
    landed_on: str | None = None
    support_lost: bool = False
    climb_completed: bool = False
    clamped_to_ground: bool = False
    clamped_to_screen: bool = False


class PhysicsEngine:
    def __init__(
        self,
        config: PhysicsConfig,
        stamina: StaminaSystem | None = None,
        *,
        apply_state_transitions: bool = True,
    ) -> None:
        self.config = config
        self.stamina = stamina
        self.apply_state_transitions = apply_state_transitions

    def reconcile_platform_motion(
        self,
        pet: Pet,
        previous_snapshot: EnvironmentSnapshot,
        current_snapshot: EnvironmentSnapshot,
    ) -> None:
        if pet.state == PetState.DRAGGED or pet.support_platform_id is None:
            return

        previous = previous_snapshot.platform_by_id(pet.support_platform_id)
        current = current_snapshot.platform_by_id(pet.support_platform_id)
        if previous is None or current is None or not current.dynamic or not current.walkable:
            return

        dy = current.rect.top - previous.rect.top
        if dy >= 0:
            return
        if not pet.rect.overlaps_x(current.rect, padding=8):
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
            self._update_climb(pet, snapshot, dt, events)
            self._clamp_to_work_area(pet, snapshot, events)
            self._clamp_to_screen(pet, snapshot, events)
            return events

        self._validate_support(pet, snapshot, events)
        old_bottom = pet.bottom

        if pet.support_platform_id is None:
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

    def _update_climb(self, pet: Pet, snapshot: EnvironmentSnapshot, dt: float, events: MotionEvents) -> None:
        side = snapshot.platform_by_id(pet.target_platform_id)
        if side is None:
            events.support_lost = True
            if self.apply_state_transitions:
                pet.state = PetState.FALL
            pet.target_platform_id = None
            return

        top_id = self._top_platform_id_for(side)
        top = snapshot.platform_by_id(top_id)
        if top is None:
            events.support_lost = True
            if self.apply_state_transitions:
                pet.state = PetState.FALL
            pet.target_platform_id = None
            return

        pet.velocity.x = 0.0
        climb_speed = self.stamina.effective_climb_speed(pet) if self.stamina else self.config.climb_speed
        pet.velocity.y = -climb_speed
        pet.position.y += pet.velocity.y * dt

        if pet.bottom <= top.rect.top + 3:
            pet.position.y = top.rect.top - pet.height
            pet.support_platform_id = top.id
            pet.target_platform_id = None
            pet.velocity.y = 0.0
            pet.velocity.x = 0.0
            events.climb_completed = True
            events.landed_on = top.id

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
            if platform.walkable and old_bottom <= platform.rect.top <= pet.bottom and pet.rect.overlaps_x(platform.rect, padding=8)
        ]
        if not candidates:
            if pet.support_platform_id and snapshot.platform_by_id(pet.support_platform_id) is None:
                pet.support_platform_id = None
                events.support_lost = True
                if self.apply_state_transitions:
                    pet.state = PetState.FALL
            return

        platform = min(candidates, key=lambda item: item.rect.top)
        pet.position.y = platform.rect.top - pet.height
        pet.velocity.y = 0.0
        pet.support_platform_id = platform.id
        events.landed_on = platform.id
        if pet.state in {PetState.FALL, PetState.JUMP}:
            pet.velocity.x = 0.0
            if self.apply_state_transitions:
                pet.state = PetState.IDLE

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

    def _validate_support(self, pet: Pet, snapshot: EnvironmentSnapshot, events: MotionEvents) -> None:
        if pet.support_platform_id is None:
            return

        platform = snapshot.platform_by_id(pet.support_platform_id)
        if platform is None or not platform.walkable:
            pet.support_platform_id = None
            events.support_lost = True
            if self.apply_state_transitions:
                pet.state = PetState.FALL
            return

        vertical_tolerance = 3.0
        is_on_top = abs(pet.bottom - platform.rect.top) <= vertical_tolerance
        overlaps = pet.rect.overlaps_x(platform.rect, padding=8)
        if is_on_top and overlaps:
            return

        pet.support_platform_id = None
        events.support_lost = True
        if self.apply_state_transitions:
            pet.state = PetState.FALL

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
        if pet.bottom < floor_y:
            return

        pet.position.y = floor_y - pet.height
        pet.velocity.y = 0.0
        pet.support_platform_id = "ground:work_area"
        events.clamped_to_ground = True
        events.landed_on = "ground:work_area"
        if pet.state in {PetState.FALL, PetState.JUMP}:
            pet.velocity.x = 0.0
            if self.apply_state_transitions:
                pet.state = PetState.IDLE

    def _clamp_to_screen(self, pet: Pet, snapshot: EnvironmentSnapshot, events: MotionEvents) -> None:
        bottom_limit = snapshot.screen_rect.bottom + pet.height * 2
        if pet.position.y > bottom_limit:
            pet.position.y = snapshot.work_area_rect.bottom - pet.height
            pet.velocity.y = 0.0
            pet.support_platform_id = "ground:work_area"
            events.clamped_to_screen = True
            events.landed_on = "ground:work_area"
            if self.apply_state_transitions:
                pet.state = PetState.IDLE

    def _top_platform_id_for(self, side: Platform) -> str:
        return PlatformTopology.top_id_for_side(side)
