from __future__ import annotations

from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.platform import Platform
from desktop_sprite.models.state import Facing, Pet, PetState
from desktop_sprite.utils.config import PhysicsConfig


class PhysicsEngine:
    def __init__(self, config: PhysicsConfig) -> None:
        self.config = config

    def update(self, pet: Pet, snapshot: EnvironmentSnapshot, dt: float) -> None:
        if pet.state == PetState.DRAGGED:
            self._clamp_to_work_area(pet, snapshot)
            return
        if pet.state == PetState.CLIMB:
            self._update_climb(pet, snapshot, dt)
            self._clamp_to_work_area(pet, snapshot)
            self._clamp_to_screen(pet, snapshot)
            return

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
        pet.velocity.y = -self.config.climb_speed
        pet.position.y += pet.velocity.y * dt

        if pet.bottom <= top.rect.top + 3:
            pet.position.y = top.rect.top - pet.height
            pet.support_platform_id = top.id
            pet.target_platform_id = None
            pet.velocity.y = 0.0
            pet.velocity.x = self.config.walk_speed if pet.facing == Facing.RIGHT else -self.config.walk_speed
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
        if pet.state == PetState.FALL:
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
        if pet.state == PetState.FALL:
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
