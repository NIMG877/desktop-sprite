from __future__ import annotations

from desktop_sprite.models.platform import Platform
from desktop_sprite.utils.config import PhysicsConfig


class ReachabilityPolicy:
    def __init__(self, physics: PhysicsConfig, edge_snap_distance: float) -> None:
        self.physics = physics
        self.edge_snap_distance = edge_snap_distance

    def can_reach_side_bottom(self, source: Platform, side: Platform) -> bool:
        bottom_gap = source.rect.top - side.rect.bottom
        if bottom_gap <= self.edge_snap_distance:
            return True
        return bottom_gap <= self.max_jump_height()

    def can_jump_between(self, source: Platform, target: Platform, *, horizontal_gap: float) -> bool:
        if target.rect.top > source.rect.top + self.edge_snap_distance:
            return False
        if self.can_walk_transfer(source, target, horizontal_gap=horizontal_gap):
            return False
        vertical_up = max(0.0, source.rect.top - target.rect.top)
        if vertical_up > self.max_jump_height():
            return False
        return horizontal_gap <= self.max_jump_distance()

    def can_walk_transfer(self, source: Platform, target: Platform, *, horizontal_gap: float) -> bool:
        same_level = abs(source.rect.top - target.rect.top) <= self.edge_snap_distance
        if not same_level:
            return False
        return horizontal_gap <= self.edge_snap_distance

    def can_drop(self, source: Platform, target: Platform, *, horizontal_gap: float) -> bool:
        if target.rect.top <= source.rect.top:
            return False
        return horizontal_gap <= max(source.rect.width, target.rect.width) * 0.25

    def can_climb_to_top(self, side: Platform, top: Platform) -> bool:
        return True

    def max_jump_height(self) -> float:
        jump_speed_y = abs(self.physics.jump_speed_y)
        gravity = max(self.physics.gravity, 1.0)
        return jump_speed_y * jump_speed_y / (2.0 * gravity)

    def max_jump_distance(self) -> float:
        jump_speed_y = abs(self.physics.jump_speed_y)
        gravity = max(self.physics.gravity, 1.0)
        air_time = 2.0 * jump_speed_y / gravity
        return self.physics.jump_speed_x * air_time
