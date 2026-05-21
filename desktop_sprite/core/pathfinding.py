from __future__ import annotations

import heapq
from dataclasses import dataclass
from enum import StrEnum

from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.platform import Platform
from desktop_sprite.models.state import Pet
from desktop_sprite.core.stamina_system import StaminaSystem


class PathAction(StrEnum):
    WALK = "walk"
    JUMP = "jump"
    CLIMB = "climb"


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
    target_window_id: int | None
    snapshot_timestamp: float
    target_platform_id: str | None = None
    target_x: float | None = None

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

        return self.find_path_to_platform(
            pet=pet,
            snapshot=snapshot,
            target_platform_id=target_id,
            stamina=stamina,
            target_window_id=target_window_id,
        )

    def find_path_to_platform(
        self,
        pet: Pet,
        snapshot: EnvironmentSnapshot,
        target_platform_id: str,
        stamina: StaminaSystem,
        target_window_id: int | None = None,
    ) -> PathPlan | None:
        start_id = pet.support_platform_id
        if start_id is None or start_id == target_platform_id:
            return None

        walkable = {platform.id: platform for platform in snapshot.platforms if platform.walkable}
        if start_id not in walkable or target_platform_id not in walkable:
            return None

        graph = self.build_navigation_graph(pet, snapshot, stamina)
        return self._find_path_between(
            graph=graph,
            start_id=start_id,
            target_id=target_platform_id,
            target_window_id=target_window_id,
            timestamp=snapshot.timestamp,
        )

    def find_path_to_point(
        self,
        pet: Pet,
        snapshot: EnvironmentSnapshot,
        target_platform_id: str,
        target_x: float,
        stamina: StaminaSystem,
        target_window_id: int | None = None,
    ) -> PathPlan | None:
        start_id = pet.support_platform_id
        if start_id is None:
            return None

        walkable = {platform.id: platform for platform in snapshot.platforms if platform.walkable}
        start = walkable.get(start_id)
        target = walkable.get(target_platform_id)
        if start is None or target is None:
            return None

        target_x = min(max(target_x, target.rect.left), target.rect.right - pet.width)
        if start_id == target_platform_id:
            return self._single_walk_plan(
                pet=pet,
                platform=start,
                target_x=target_x,
                stamina=stamina,
                target_window_id=target_window_id,
                timestamp=snapshot.timestamp,
            )

        plan = self.find_path_to_platform(
            pet=pet,
            snapshot=snapshot,
            target_platform_id=target_platform_id,
            stamina=stamina,
            target_window_id=target_window_id,
        )
        if plan is None:
            return None

        plan.edges.append(
            self._point_walk_edge(
                source=target,
                target=target,
                target_x=target_x,
                stamina=stamina,
                pet=pet,
            )
        )
        plan.target_x = target_x
        return plan

    def _find_path_between(
        self,
        graph: dict[str, list[PathEdge]],
        start_id: str,
        target_id: str,
        target_window_id: int | None,
        timestamp: float,
    ) -> PathPlan | None:
        distances: dict[str, float] = {start_id: 0.0}
        previous: dict[str, tuple[str, PathEdge]] = {}
        queue: list[tuple[float, str]] = [(0.0, start_id)]

        while queue:
            cost, platform_id = heapq.heappop(queue)
            if cost > distances.get(platform_id, float("inf")):
                continue
            if platform_id == target_id:
                return self._reconstruct_plan(previous, start_id, target_id, target_window_id, timestamp)

            for edge in graph.get(platform_id, []):
                next_cost = cost + edge.cost
                if next_cost >= distances.get(edge.to_platform_id, float("inf")):
                    continue
                distances[edge.to_platform_id] = next_cost
                previous[edge.to_platform_id] = (platform_id, edge)
                heapq.heappush(queue, (next_cost, edge.to_platform_id))

        return None

    def build_navigation_graph(
        self,
        pet: Pet,
        snapshot: EnvironmentSnapshot,
        stamina: StaminaSystem,
    ) -> dict[str, list[PathEdge]]:
        walkable = {platform.id: platform for platform in snapshot.platforms if platform.walkable}
        return self._build_graph(pet, snapshot, walkable, stamina)

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
                if self._can_walk_transfer(source, target, stamina):
                    graph[source.id].append(self._walk_edge(source, target, stamina, pet))
                elif self._can_drop(source, target):
                    graph[source.id].append(self._walk_off_edge(source, target, stamina, pet))
                elif self._can_jump(source, target, stamina, pet):
                    graph[source.id].append(self._jump_edge(source, target, stamina, pet))

        return graph

    def _reconstruct_plan(
        self,
        previous: dict[str, tuple[str, PathEdge]],
        start_id: str,
        target_id: str,
        target_window_id: int | None,
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
        return PathPlan(
            edges=edges,
            current_index=0,
            target_window_id=target_window_id,
            snapshot_timestamp=timestamp,
            target_platform_id=target_id,
        )

    def _single_walk_plan(
        self,
        pet: Pet,
        platform: Platform,
        target_x: float,
        stamina: StaminaSystem,
        target_window_id: int | None,
        timestamp: float,
    ) -> PathPlan:
        return PathPlan(
            edges=[
                self._point_walk_edge(
                    source=platform,
                    target=platform,
                    target_x=target_x,
                    stamina=stamina,
                    pet=pet,
                )
            ],
            current_index=0,
            target_window_id=target_window_id,
            snapshot_timestamp=timestamp,
            target_platform_id=platform.id,
            target_x=target_x,
        )

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
        if target.rect.top > source.rect.top + stamina.physics.edge_snap_distance:
            return False
        if self._can_walk_transfer(source, target, stamina):
            return False
        vertical_up = max(0.0, source.rect.top - target.rect.top)
        if vertical_up > stamina.max_jump_height(pet):
            return False
        return self._horizontal_gap(source, target) <= stamina.max_jump_distance(pet)

    def _can_walk_transfer(self, source: Platform, target: Platform, stamina: StaminaSystem) -> bool:
        same_level = abs(source.rect.top - target.rect.top) <= stamina.physics.edge_snap_distance
        if not same_level:
            return False
        return self._horizontal_gap(source, target) <= stamina.physics.edge_snap_distance

    def _walk_edge(self, source: Platform, target: Platform, stamina: StaminaSystem, pet: Pet) -> PathEdge:
        horizontal = abs(source.rect.center_x - target.rect.center_x)
        return PathEdge(
            action=PathAction.WALK,
            from_platform_id=source.id,
            to_platform_id=target.id,
            target_x=self._target_x_on_platform(source, target, pet),
            cost=horizontal / max(stamina.effective_walk_speed(pet), 1.0),
        )

    def _point_walk_edge(
        self,
        source: Platform,
        target: Platform,
        target_x: float,
        stamina: StaminaSystem,
        pet: Pet,
    ) -> PathEdge:
        return PathEdge(
            action=PathAction.WALK,
            from_platform_id=source.id,
            to_platform_id=target.id,
            target_x=target_x,
            cost=abs(target_x - pet.position.x) / max(stamina.effective_walk_speed(pet), 1.0),
        )

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

    def _walk_off_edge(self, source: Platform, target: Platform, stamina: StaminaSystem, pet: Pet) -> PathEdge:
        vertical = target.rect.top - source.rect.top
        target_x = self._platform_exit_x(source, target, pet)
        return PathEdge(
            action=PathAction.WALK,
            from_platform_id=source.id,
            to_platform_id=target.id,
            target_x=target_x,
            cost=vertical / 200.0 + 3.0,
        )

    def _platform_exit_x(self, source: Platform, target: Platform, pet: Pet) -> float:
        exit_offset = 7.0
        if target.rect.center_x < source.rect.center_x:
            return source.rect.left - pet.width + exit_offset
        return source.rect.right - exit_offset

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
            center = target.rect.right if target.rect.center_x < source.rect.center_x else target.rect.left
        return center - pet.width / 2

    def _max_climb_distance(self, pet: Pet, stamina: StaminaSystem) -> float:
        available = max(0.0, pet.stamina - stamina.config.exhausted_threshold)
        cost_per_px = max(stamina.config.climb_cost_per_px, 0.001)
        return available / cost_per_px
