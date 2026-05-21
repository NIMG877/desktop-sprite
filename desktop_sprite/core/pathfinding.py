from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from desktop_sprite.core.planner import GraphPlanner
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.platform import Platform
from desktop_sprite.models.platform_topology import PlatformTopology
from desktop_sprite.models.state import Pet
from desktop_sprite.core.stamina_system import StaminaSystem
from desktop_sprite.core.reachability_policy import ReachabilityPolicy


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
    def __init__(self) -> None:
        self.planner = GraphPlanner()

    def find_path(
        self,
        pet: Pet,
        snapshot: EnvironmentSnapshot,
        target_window_id: int,
        stamina: StaminaSystem,
    ) -> PathPlan | None:
        start_id = pet.support_platform_id
        target_id = PlatformTopology.window_top_id(target_window_id)
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
        previous = self.planner.shortest_path_tree(
            graph=graph,
            start_id=start_id,
            target_id=target_id,
        )
        if previous is None:
            return None
        return self._reconstruct_plan(previous, start_id, target_id, target_window_id, timestamp)

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
        reachability = ReachabilityPolicy(stamina, stamina.physics.edge_snap_distance)
        graph: dict[str, list[PathEdge]] = {platform_id: [] for platform_id in walkable}

        for side in [platform for platform in snapshot.platforms if platform.climbable]:
            top = self._top_for_side(side, walkable)
            if top is None:
                continue
            climb_distance = max(0.0, side.rect.bottom - top.rect.top)
            if climb_distance > reachability.max_climb_distance(pet):
                continue
            for source in walkable.values():
                if source.id == top.id:
                    continue
                if not reachability.can_reach_side_bottom(pet, source, side):
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
                horizontal_gap = self._horizontal_gap(source, target)
                if reachability.can_walk_transfer(source, target, horizontal_gap=horizontal_gap):
                    graph[source.id].append(self._walk_edge(source, target, stamina, pet))
                elif reachability.can_drop(source, target, horizontal_gap=horizontal_gap):
                    graph[source.id].append(self._walk_off_edge(source, target, stamina, pet))
                elif reachability.can_jump_between(pet, source, target, horizontal_gap=horizontal_gap):
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
        return walkable.get(PlatformTopology.top_id_for_side(side))

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
