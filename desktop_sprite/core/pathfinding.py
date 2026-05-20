from __future__ import annotations

import heapq
from dataclasses import dataclass
from enum import StrEnum

from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.platform import Platform
from desktop_sprite.models.state import Pet
from desktop_sprite.core.stamina_system import StaminaSystem


class PathAction(StrEnum):
    JUMP = "jump"
    CLIMB = "climb"
    DROP = "drop"


@dataclass(frozen=True, slots=True)
class PathNode:
    platform_id: str


@dataclass(frozen=True, slots=True)
class PathEdge:
    action: PathAction
    from_platform_id: str
    to_platform_id: str
    target_x: float
    cost: float
    side_platform_id: str | None = None


@dataclass(slots=True)
class PathPlan:
    edges: list[PathEdge]
    current_index: int
    target_window_id: int
    snapshot_timestamp: float

    @property
    def current_edge(self) -> PathEdge | None:
        if self.current_index >= len(self.edges):
            return None
        return self.edges[self.current_index]

    @property
    def is_complete(self) -> bool:
        return self.current_index >= len(self.edges)

    def advance(self) -> None:
        self.current_index += 1


class PathFinder:
    def find_path(
        self,
        pet: Pet,
        snapshot: EnvironmentSnapshot,
        target_window_id: int,
        stamina: StaminaSystem,
    ) -> PathPlan | None:
        start_id = pet.support_platform_id
        target_id = f"window:{target_window_id}:top"
        if start_id is None or start_id == target_id:
            return None

        walkable = {platform.id: platform for platform in snapshot.platforms if platform.walkable}
        if start_id not in walkable or target_id not in walkable:
            return None

        graph = self._build_graph(pet, snapshot, walkable, stamina)
        distances: dict[str, float] = {start_id: 0.0}
        previous: dict[str, tuple[str, PathEdge]] = {}
        queue: list[tuple[float, str]] = [(0.0, start_id)]

        while queue:
            cost, platform_id = heapq.heappop(queue)
            if cost > distances.get(platform_id, float("inf")):
                continue
            if platform_id == target_id:
                return self._reconstruct_plan(previous, start_id, target_id, target_window_id, snapshot.timestamp)

            for edge in graph.get(platform_id, []):
                next_cost = cost + edge.cost
                if next_cost >= distances.get(edge.to_platform_id, float("inf")):
                    continue
                distances[edge.to_platform_id] = next_cost
                previous[edge.to_platform_id] = (platform_id, edge)
                heapq.heappush(queue, (next_cost, edge.to_platform_id))

        return None

    def _build_graph(
        self,
        pet: Pet,
        snapshot: EnvironmentSnapshot,
        walkable: dict[str, Platform],
        stamina: StaminaSystem,
    ) -> dict[str, list[PathEdge]]:
        graph: dict[str, list[PathEdge]] = {platform_id: [] for platform_id in walkable}

        for side in [platform for platform in snapshot.platforms if platform.climbable]:
            top = self._top_for_side(side, walkable)
            if top is None:
                continue
            climb_distance = max(0.0, side.rect.bottom - top.rect.top)
            if climb_distance > self._max_climb_distance(pet, stamina):
                continue
            for source in walkable.values():
                if source.id == top.id:
                    continue
                if not self._can_reach_side_bottom(source, side, stamina, pet):
                    continue
                horizontal = abs(source.rect.center_x - side.rect.center_x)
                graph[source.id].append(
                    PathEdge(
                        action=PathAction.CLIMB,
                        from_platform_id=source.id,
                        to_platform_id=top.id,
                        target_x=side.rect.center_x - pet.width / 2,
                        side_platform_id=side.id,
                        cost=horizontal / max(stamina.effective_walk_speed(pet), 1.0)
                        + climb_distance / max(stamina.effective_climb_speed(pet), 1.0),
                    )
                )

        platforms = list(walkable.values())
        for source in platforms:
            for target in platforms:
                if source.id == target.id:
                    continue
                if self._can_jump(source, target, stamina, pet):
                    graph[source.id].append(self._jump_edge(source, target, stamina, pet))
                elif self._can_drop(source, target):
                    graph[source.id].append(self._drop_edge(source, target, pet))

        return graph

    def _reconstruct_plan(
        self,
        previous: dict[str, tuple[str, PathEdge]],
        start_id: str,
        target_id: str,
        target_window_id: int,
        timestamp: float,
    ) -> PathPlan | None:
        edges: list[PathEdge] = []
        current = target_id
        while current != start_id:
            item = previous.get(current)
            if item is None:
                return None
            parent, edge = item
            edges.append(edge)
            current = parent
        edges.reverse()
        return PathPlan(edges=edges, current_index=0, target_window_id=target_window_id, snapshot_timestamp=timestamp)

    def _top_for_side(self, side: Platform, walkable: dict[str, Platform]) -> Platform | None:
        if side.source_id is None:
            return None
        return walkable.get(f"window:{side.source_id}:top")

    def _can_reach_side_bottom(self, source: Platform, side: Platform, stamina: StaminaSystem, pet: Pet) -> bool:
        bottom_gap = source.rect.top - side.rect.bottom
        if bottom_gap <= stamina.physics.edge_snap_distance:
            return True
        return bottom_gap <= stamina.max_jump_height(pet)

    def _can_jump(self, source: Platform, target: Platform, stamina: StaminaSystem, pet: Pet) -> bool:
        vertical_up = max(0.0, source.rect.top - target.rect.top)
        if vertical_up > stamina.max_jump_height(pet):
            return False
        return self._horizontal_gap(source, target) <= stamina.max_jump_distance(pet)

    def _jump_edge(self, source: Platform, target: Platform, stamina: StaminaSystem, pet: Pet) -> PathEdge:
        horizontal = self._horizontal_gap(source, target)
        vertical = abs(source.rect.top - target.rect.top)
        air_time = 2.0 * abs(stamina.effective_jump_speed_y(pet)) / max(stamina.physics.gravity, 1.0)
        return PathEdge(
            action=PathAction.JUMP,
            from_platform_id=source.id,
            to_platform_id=target.id,
            target_x=self._target_x_on_platform(source, target, pet),
            cost=air_time + horizontal / max(stamina.effective_jump_speed_x(pet), 1.0) + vertical / 400.0 + 2.0,
        )

    def _can_drop(self, source: Platform, target: Platform) -> bool:
        if target.rect.top <= source.rect.top:
            return False
        return self._horizontal_gap(source, target) <= max(source.rect.width, target.rect.width) * 0.25

    def _drop_edge(self, source: Platform, target: Platform, pet: Pet) -> PathEdge:
        vertical = target.rect.top - source.rect.top
        return PathEdge(
            action=PathAction.DROP,
            from_platform_id=source.id,
            to_platform_id=target.id,
            target_x=self._target_x_on_platform(source, target, pet),
            cost=vertical / 200.0 + 3.0,
        )

    def _horizontal_gap(self, source: Platform, target: Platform) -> float:
        if source.rect.overlaps_x(target.rect):
            return 0.0
        if source.rect.right < target.rect.left:
            return target.rect.left - source.rect.right
        return source.rect.left - target.rect.right

    def _target_x_on_platform(self, source: Platform, target: Platform, pet: Pet) -> float:
        left = max(target.rect.left, source.rect.left)
        right = min(target.rect.right, source.rect.right)
        if left <= right:
            center = (left + right) / 2
        else:
            center = target.rect.left if target.rect.center_x < source.rect.center_x else target.rect.right
        return center - pet.width / 2

    def _max_climb_distance(self, pet: Pet, stamina: StaminaSystem) -> float:
        available = max(0.0, pet.stamina - stamina.config.exhausted_threshold)
        cost_per_px = max(stamina.config.climb_cost_per_px, 0.001)
        return available / cost_per_px
