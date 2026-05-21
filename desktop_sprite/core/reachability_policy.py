from __future__ import annotations

from desktop_sprite.core.stamina_system import StaminaSystem
from desktop_sprite.models.platform import Platform
from desktop_sprite.models.state import Pet


class ReachabilityPolicy:
    def __init__(self, stamina: StaminaSystem, edge_snap_distance: float) -> None:
        self.stamina = stamina
        self.edge_snap_distance = edge_snap_distance

    def can_reach_side_bottom(self, pet: Pet, source: Platform, side: Platform) -> bool:
        bottom_gap = source.rect.top - side.rect.bottom
        if bottom_gap <= self.edge_snap_distance:
            return True
        return bottom_gap <= self.stamina.max_jump_height(pet)

    def can_jump_between(self, pet: Pet, source: Platform, target: Platform, *, horizontal_gap: float) -> bool:
        if target.rect.top > source.rect.top + self.edge_snap_distance:
            return False
        if self.can_walk_transfer(source, target, horizontal_gap=horizontal_gap):
            return False
        vertical_up = max(0.0, source.rect.top - target.rect.top)
        if vertical_up > self.stamina.max_jump_height(pet):
            return False
        return horizontal_gap <= self.stamina.max_jump_distance(pet)

    def can_walk_transfer(self, source: Platform, target: Platform, *, horizontal_gap: float) -> bool:
        same_level = abs(source.rect.top - target.rect.top) <= self.edge_snap_distance
        if not same_level:
            return False
        return horizontal_gap <= self.edge_snap_distance

    def can_drop(self, source: Platform, target: Platform, *, horizontal_gap: float) -> bool:
        if target.rect.top <= source.rect.top:
            return False
        return horizontal_gap <= max(source.rect.width, target.rect.width) * 0.25

    def max_climb_distance(self, pet: Pet) -> float:
        available = max(0.0, pet.stamina - self.stamina.config.exhausted_threshold)
        cost_per_px = max(self.stamina.config.climb_cost_per_px, 0.001)
        return available / cost_per_px

    def has_stamina_for_climb_to_top(self, pet: Pet, side: Platform, top: Platform) -> bool:
        climb_distance = max(0.0, side.rect.bottom - top.rect.top)
        return climb_distance <= self.max_climb_distance(pet)

