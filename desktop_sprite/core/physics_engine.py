from __future__ import annotations

from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.core.stamina_system import StaminaSystem
from desktop_sprite.models.platform import Platform
from desktop_sprite.models.state import Facing, Pet, PetState
from desktop_sprite.utils.config import PhysicsConfig


class PhysicsEngine:
    def __init__(self, config: PhysicsConfig, stamina: StaminaSystem | None = None) -> None:
        self.config = config
        self.stamina = stamina

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

    def update(self, pet: Pet, snapshot: EnvironmentSnapshot, dt: float) -> None:
        if pet.state == PetState.DRAGGED:
            self._clamp_to_work_area(pet, snapshot)
            return
        if pet.state == PetState.CLIMB:
            self._update_climb(pet, snapshot, dt)
            self._clamp_to_work_area(pet, snapshot)
            self._clamp_to_screen(pet, snapshot)
            return

        self._validate_support(pet, snapshot)
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

        self._clamp_to_work_area(pet, snapshot)
        self._resolve_platform_landing(pet, snapshot, old_bottom)
        self._clamp_to_work_area(pet, snapshot)
        self._clamp_to_screen(pet, snapshot)

    def _update_climb(self, pet: Pet, snapshot: EnvironmentSnapshot, dt: float) -> None:
        side = snapshot.platform_by_id(pet.target_platform_id)
        if side is None:
            pet.state = PetState.FALL
            pet.target_platform_id = None
            return

        top_id = self._top_platform_id_for(side)
        top = snapshot.platform_by_id(top_id)
        if top is None:
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
            walk_speed = self.stamina.effective_walk_speed(pet) if self.stamina else self.config.walk_speed
            pet.velocity.x = walk_speed if pet.facing == Facing.RIGHT else -walk_speed
            pet.state = PetState.WALK

    def _resolve_platform_landing(self, pet: Pet, snapshot: EnvironmentSnapshot, old_bottom: float) -> None:
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
                pet.state = PetState.FALL
            return

        platform = min(candidates, key=lambda item: item.rect.top)
        pet.position.y = platform.rect.top - pet.height
        pet.velocity.y = 0.0
        pet.support_platform_id = platform.id
        if pet.state in {PetState.FALL, PetState.JUMP}:
            pet.state = PetState.IDLE if abs(pet.velocity.x) < 1 else PetState.WALK

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

    def _validate_support(self, pet: Pet, snapshot: EnvironmentSnapshot) -> None:
        if pet.support_platform_id is None:
            return

        platform = snapshot.platform_by_id(pet.support_platform_id)
        if platform is None or not platform.walkable:
            pet.support_platform_id = None
            pet.state = PetState.FALL
            return

        vertical_tolerance = 3.0
        is_on_top = abs(pet.bottom - platform.rect.top) <= vertical_tolerance
        overlaps = pet.rect.overlaps_x(platform.rect, padding=8)
        if is_on_top and overlaps:
            return

        pet.support_platform_id = None
        pet.state = PetState.FALL

    def _clamp_to_work_area(self, pet: Pet, snapshot: EnvironmentSnapshot) -> None:
        self._clamp_horizontal(pet, snapshot)
        self._resolve_ceiling_boundary(pet, snapshot)
        self._resolve_floor_boundary(pet, snapshot)

    def _resolve_ceiling_boundary(self, pet: Pet, snapshot: EnvironmentSnapshot) -> None:
        ceiling_y = snapshot.work_area_rect.top
        if pet.position.y >= ceiling_y:
            return

        pet.position.y = ceiling_y
        if pet.velocity.y < 0:
            pet.velocity.y = 0.0

    def _resolve_floor_boundary(self, pet: Pet, snapshot: EnvironmentSnapshot) -> None:
        floor_y = snapshot.work_area_rect.bottom
        if pet.bottom < floor_y:
            return

        pet.position.y = floor_y - pet.height
        pet.velocity.y = 0.0
        pet.support_platform_id = "ground:work_area"
        if pet.state in {PetState.FALL, PetState.JUMP}:
            pet.state = PetState.IDLE if abs(pet.velocity.x) < 1 else PetState.WALK

    def _clamp_to_screen(self, pet: Pet, snapshot: EnvironmentSnapshot) -> None:
        bottom_limit = snapshot.screen_rect.bottom + pet.height * 2
        if pet.position.y > bottom_limit:
            pet.position.y = snapshot.work_area_rect.bottom - pet.height
            pet.velocity.y = 0.0
            pet.support_platform_id = "ground:work_area"
            pet.state = PetState.IDLE

    def _top_platform_id_for(self, side: Platform) -> str:
        parts = side.id.split(":")
        return f"{parts[0]}:{parts[1]}:top" if len(parts) >= 3 else side.id
