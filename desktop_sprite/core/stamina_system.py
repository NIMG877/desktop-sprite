from __future__ import annotations

import math

from desktop_sprite.models.geometry import Vec2
from desktop_sprite.models.state import Pet, PetState
from desktop_sprite.utils.config import PhysicsConfig, StaminaConfig


class StaminaSystem:
    def __init__(self, config: StaminaConfig, physics: PhysicsConfig) -> None:
        self.config = config
        self.physics = physics

    def clamp(self, pet: Pet) -> None:
        pet.stamina = min(max(pet.stamina, 0.0), self.config.max_stamina)

    def fraction(self, pet: Pet) -> float:
        if self.config.max_stamina <= 0:
            return 0.0
        return min(max(pet.stamina / self.config.max_stamina, 0.0), 1.0)

    def capability(self, pet: Pet) -> float:
        return max(self.config.min_capability_factor, math.sqrt(self.fraction(pet)))

    def can_act(self, pet: Pet) -> bool:
        return pet.stamina > self.config.exhausted_threshold

    def can_resume(self, pet: Pet) -> bool:
        return pet.stamina >= self.config.resume_threshold

    def effective_walk_speed(self, pet: Pet) -> float:
        return self.physics.walk_speed * self.capability(pet)

    def effective_climb_speed(self, pet: Pet) -> float:
        return self.physics.climb_speed * self.capability(pet)

    def effective_jump_speed_x(self, pet: Pet) -> float:
        return self.physics.jump_speed_x * self.capability(pet)

    def effective_jump_speed_y(self, pet: Pet) -> float:
        return self.physics.jump_speed_y * self.capability(pet)

    def max_jump_height(self, pet: Pet) -> float:
        jump_speed_y = abs(self.effective_jump_speed_y(pet))
        gravity = max(self.physics.gravity, 1.0)
        return jump_speed_y * jump_speed_y / (2.0 * gravity)

    def max_jump_distance(self, pet: Pet) -> float:
        jump_speed_y = abs(self.effective_jump_speed_y(pet))
        gravity = max(self.physics.gravity, 1.0)
        air_time = 2.0 * jump_speed_y / gravity
        return self.effective_jump_speed_x(pet) * air_time

    def consume_jump(self, pet: Pet) -> None:
        cost = self.config.full_jump_cost * self.capability(pet) ** 2
        self.consume(pet, cost)

    def apply_motion_cost(self, pet: Pet, old_position: Vec2, old_state: PetState) -> None:
        dx = pet.position.x - old_position.x
        dy = pet.position.y - old_position.y
        if old_state in {PetState.WALK, PetState.MOVE_TO_TARGET}:
            self.consume(pet, abs(dx) * self.config.walk_cost_per_px)
        elif old_state == PetState.CLIMB and dy < 0:
            self.consume(pet, abs(dy) * self.config.climb_cost_per_px)

    def recover(self, pet: Pet, dt: float, resting: bool) -> None:
        rate = self.config.rest_recover_per_second if resting else self.config.recover_per_second
        pet.stamina += rate * dt
        self.clamp(pet)

    def consume(self, pet: Pet, amount: float) -> None:
        pet.stamina -= max(amount, 0.0)
        self.clamp(pet)
