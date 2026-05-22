from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from desktop_sprite.core.planner import GraphPlanner
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.models.platform_topology import PlatformTopology
from desktop_sprite.models.state import Pet
from desktop_sprite.utils.config import PhysicsConfig


class SurfaceOrientation(StrEnum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class TraversalAction(StrEnum):
    MOVE = "move"
    JUMP = "jump"
    TRANSFORM = "transform"
    FALL = "fall"

    # Compatibility aliases for the old platform vocabulary.
    WALK = "move"
    CLIMB = "transform"


PathAction = TraversalAction


class SurfaceCapability(StrEnum):
    MOVE = "move"
    JUMP_TARGET = "jump_target"
    FALL = "fall"
    TRANSFORM = "transform"


class NavNodeKind(StrEnum):
    EVENT_POINT = "event_point"
    DROP_POINT = "drop_point"
    JUMP_POINT = "jump_point"
    CLIMB_CONTACT = "climb_contact"
    CLIMB_ENDPOINT = "climb_endpoint"
    TRANSFORM_POINT = "transform_point"


@dataclass(frozen=True, slots=True)
class Surface:
    id: str
    rect: object
    orientation: SurfaceOrientation
    capabilities: frozenset[SurfaceCapability]
    dynamic: bool = False
    source_id: int | None = None
    type: PlatformType | None = None

    @classmethod
    def from_platform(cls, platform: Platform) -> "Surface":
        if platform.climbable:
            orientation = SurfaceOrientation.VERTICAL
            capabilities = frozenset(
                {
                    SurfaceCapability.MOVE,
                    SurfaceCapability.TRANSFORM,
                    SurfaceCapability.JUMP_TARGET,
                }
            )
        else:
            orientation = SurfaceOrientation.HORIZONTAL
            capabilities = frozenset(
                {
                    SurfaceCapability.MOVE,
                    SurfaceCapability.FALL,
                    SurfaceCapability.JUMP_TARGET,
                }
            )
        return cls(
            id=platform.id,
            rect=platform.rect,
            orientation=orientation,
            capabilities=capabilities,
            dynamic=platform.dynamic,
            source_id=platform.source_id,
            type=platform.type,
        )

    @property
    def is_horizontal(self) -> bool:
        return self.orientation == SurfaceOrientation.HORIZONTAL

    @property
    def is_vertical(self) -> bool:
        return self.orientation == SurfaceOrientation.VERTICAL


class SurfaceTopology:
    @staticmethod
    def window_top_id(hwnd: int) -> str:
        return PlatformTopology.window_top_id(hwnd)

    @staticmethod
    def window_left_id(hwnd: int) -> str:
        return PlatformTopology.window_left_id(hwnd)

    @staticmethod
    def window_right_id(hwnd: int) -> str:
        return PlatformTopology.window_right_id(hwnd)

    @staticmethod
    def top_id_for_side_id(side_id: str) -> str:
        return PlatformTopology.top_id_for_side_id(side_id)

    @staticmethod
    def top_id_for_side(side: Surface | Platform) -> str:
        return SurfaceTopology.top_id_for_side_id(side.id)


@dataclass(frozen=True, slots=True)
class NavNode:
    id: str
    surface_id: str
    anchor_t: float
    role: NavNodeKind
    x: float
    y: float

    @property
    def platform_id(self) -> str:
        return self.surface_id

    @property
    def kind(self) -> NavNodeKind:
        return self.role


@dataclass(frozen=True, slots=True)
class NavEdge:
    from_node_id: str
    to_node_id: str
    action: TraversalAction
    cost: float
    contact_surface_id: str | None = None
    meta: dict[str, float | str] = field(default_factory=dict)

    @property
    def side_platform_id(self) -> str | None:
        return self.contact_surface_id


@dataclass(slots=True)
class SurfaceGraph:
    nodes: dict[str, NavNode] = field(default_factory=dict)
    adjacency: dict[str, list[NavEdge]] = field(default_factory=dict)
    surfaces: dict[str, Surface] = field(default_factory=dict)

    @property
    def edges(self) -> list[NavEdge]:
        return [edge for edges in self.adjacency.values() for edge in edges]


NavigationMesh = SurfaceGraph


@dataclass(frozen=True, slots=True, init=False)
class PathStep:
    action: TraversalAction
    from_surface_id: str
    to_surface_id: str
    target_t: float
    cost: float
    contact_surface_id: str | None
    land_t: float | None
    approach_point: tuple[float, float] | None
    land_point: tuple[float, float] | None

    def __init__(
        self,
        action: TraversalAction,
        from_surface_id: str | None = None,
        to_surface_id: str | None = None,
        target_t: float | None = None,
        cost: float = 0.0,
        contact_surface_id: str | None = None,
        land_t: float | None = None,
        approach_point: tuple[float, float] | None = None,
        land_point: tuple[float, float] | None = None,
        *,
        from_platform_id: str | None = None,
        to_platform_id: str | None = None,
        target_x: float | None = None,
        side_platform_id: str | None = None,
        land_x: float | None = None,
    ) -> None:
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "from_surface_id", from_surface_id or from_platform_id or "")
        object.__setattr__(self, "to_surface_id", to_surface_id or to_platform_id or "")
        object.__setattr__(self, "target_t", target_t if target_t is not None else (target_x if target_x is not None else 0.0))
        object.__setattr__(self, "cost", cost)
        object.__setattr__(self, "contact_surface_id", contact_surface_id or side_platform_id)
        object.__setattr__(self, "land_t", land_t if land_t is not None else land_x)
        fallback_x = target_t if target_t is not None else target_x
        fallback_land_x = land_x if land_x is not None else fallback_x
        object.__setattr__(self, "approach_point", approach_point or ((fallback_x, 0.0) if fallback_x is not None else None))
        object.__setattr__(self, "land_point", land_point or ((fallback_land_x, 0.0) if fallback_land_x is not None else None))

    @property
    def from_platform_id(self) -> str:
        return self.from_surface_id

    @property
    def to_platform_id(self) -> str:
        return self.to_surface_id

    @property
    def side_platform_id(self) -> str | None:
        return self.contact_surface_id

    @property
    def target_x(self) -> float:
        return self.target_t

    @property
    def approach_x(self) -> float:
        if self.approach_point is not None:
            return self.approach_point[0]
        return self.target_t

    @property
    def land_x(self) -> float | None:
        if self.land_point is not None:
            return self.land_point[0]
        return self.land_t

    @property
    def approach_y(self) -> float | None:
        if self.approach_point is None:
            return None
        return self.approach_point[1]

    @property
    def land_y(self) -> float | None:
        if self.land_point is None:
            return None
        return self.land_point[1]


PathEdge = PathStep


@dataclass(slots=True, init=False)
class PathPlan:
    steps: list[PathStep]
    current_index: int
    target_window_id: int | None
    snapshot_timestamp: float
    target_surface_id: str | None
    target_anchor_t: float | None

    def __init__(
        self,
        steps: list[PathStep] | None = None,
        current_index: int = 0,
        target_window_id: int | None = None,
        snapshot_timestamp: float = 0.0,
        target_surface_id: str | None = None,
        target_anchor_t: float | None = None,
        *,
        edges: list[PathStep] | None = None,
        target_platform_id: str | None = None,
        target_x: float | None = None,
    ) -> None:
        self.steps = steps if steps is not None else (edges or [])
        self.current_index = current_index
        self.target_window_id = target_window_id
        self.snapshot_timestamp = snapshot_timestamp
        self.target_surface_id = target_surface_id or target_platform_id
        self.target_anchor_t = target_anchor_t if target_anchor_t is not None else target_x

    @property
    def edges(self) -> list[PathStep]:
        return self.steps

    @property
    def target_platform_id(self) -> str | None:
        return self.target_surface_id

    @property
    def target_x(self) -> float | None:
        return self.target_anchor_t

    @property
    def current_edge(self) -> PathStep | None:
        return self.current_step

    @property
    def current_step(self) -> PathStep | None:
        if self.current_index >= len(self.steps):
            return None
        return self.steps[self.current_index]

    @property
    def is_complete(self) -> bool:
        return self.current_index >= len(self.steps)

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
        physics: PhysicsConfig,
    ) -> PathPlan | None:
        target_surface_id = SurfaceTopology.window_top_id(target_window_id)
        target_surface = snapshot.platform_by_id(target_surface_id)
        if target_surface is None:
            return None
        return self.find_path_to_point(
            pet=pet,
            snapshot=snapshot,
            target_platform_id=target_surface_id,
            target_x=target_surface.rect.center_x - pet.width / 2,
            physics=physics,
            target_window_id=target_window_id,
        )

    def find_path_to_point(
        self,
        pet: Pet,
        snapshot: EnvironmentSnapshot,
        target_platform_id: str,
        target_x: float,
        physics: PhysicsConfig,
        target_window_id: int | None = None,
    ) -> PathPlan | None:
        target_platform = snapshot.platform_by_id(target_platform_id)
        if target_platform is None:
            return None
        target_surface = Surface.from_platform(target_platform)
        target_anchor_t = self._clamp_anchor(target_surface, target_x, pet)
        return self.find_path_to_surface_point(
            pet=pet,
            snapshot=snapshot,
            target_surface_id=target_platform_id,
            target_anchor_t=target_anchor_t,
            physics=physics,
            target_window_id=target_window_id,
        )

    def find_path_to_surface_point(
        self,
        pet: Pet,
        snapshot: EnvironmentSnapshot,
        target_surface_id: str,
        target_anchor_t: float,
        physics: PhysicsConfig,
        target_window_id: int | None = None,
    ) -> PathPlan | None:
        start_surface_id = pet.support_platform_id
        if start_surface_id is None:
            return None
        start_platform = snapshot.platform_by_id(start_surface_id)
        target_platform = snapshot.platform_by_id(target_surface_id)
        if start_platform is None or target_platform is None:
            return None

        start_surface = Surface.from_platform(start_platform)
        target_surface = Surface.from_platform(target_platform)
        clamped_target_t = self._clamp_anchor(target_surface, target_anchor_t, pet)
        if start_surface_id == target_surface_id:
            return PathPlan(
                steps=[self._point_move_step(start_surface, clamped_target_t, physics, pet)],
                current_index=0,
                target_window_id=target_window_id,
                snapshot_timestamp=snapshot.timestamp,
                target_surface_id=target_surface_id,
                target_anchor_t=clamped_target_t,
            )

        graph = self.build_surface_graph(pet, snapshot, physics)
        start_node = self._ensure_node(graph, start_surface, pet, self._pet_anchor_t(start_surface, pet), NavNodeKind.JUMP_POINT, physics)
        target_node = self._ensure_node(graph, target_surface, pet, clamped_target_t, NavNodeKind.JUMP_POINT, physics)
        if start_node is None or target_node is None:
            return None
        nav_edges = self._search(graph, start_node.id, target_node.id)
        if not nav_edges:
            return None
        steps = self._map_edges(nav_edges, graph)
        if not steps:
            return None
        steps = self._merge_consecutive_same_surface_move_steps(steps)
        return PathPlan(
            steps=steps,
            current_index=0,
            target_window_id=target_window_id,
            snapshot_timestamp=snapshot.timestamp,
            target_surface_id=target_surface_id,
            target_anchor_t=clamped_target_t,
        )

    def build_surface_graph(self, pet: Pet, snapshot: EnvironmentSnapshot, physics: PhysicsConfig) -> SurfaceGraph:
        surfaces = {
            platform.id: Surface.from_platform(platform)
            for platform in snapshot.platforms
            if platform.walkable or platform.climbable
        }
        graph = SurfaceGraph(surfaces=surfaces)
        horizontals = [surface for surface in surfaces.values() if surface.is_horizontal]

        for source in horizontals:
            for side_name in ("left", "right"):
                if not self._is_drop_side_valid(source, side_name, snapshot, pet):
                    continue
                drop_t = source.rect.left - pet.width if side_name == "left" else source.rect.right
                landing = self._first_horizontal_hit_below(source, drop_t, horizontals, pet)
                if landing is None:
                    continue
                drop_node = self._ensure_node(graph, source, pet, drop_t, NavNodeKind.DROP_POINT, physics, clamp=False)
                landing_node = self._ensure_node(graph, landing, pet, drop_t, NavNodeKind.DROP_POINT, physics, clamp=False)
                if drop_node is None or landing_node is None:
                    continue
                vertical = max(0.0, landing.rect.top - source.rect.top)
                graph.adjacency[drop_node.id].append(
                    NavEdge(
                        drop_node.id,
                        landing_node.id,
                        TraversalAction.FALL,
                        self._fall_cost(vertical, physics),
                        meta={"drop": "1"},
                    )
                )

        surface_list = list(surfaces.values())
        for source in surface_list:
            for target in surface_list:
                if source.id == target.id:
                    continue
                if self._can_transform_between_surfaces(source, target):
                    source_t, target_t = self._transform_anchors(source, target, pet)
                    source_node = self._ensure_node(graph, source, pet, source_t, NavNodeKind.TRANSFORM_POINT, physics)
                    target_node = self._ensure_node(graph, target, pet, target_t, NavNodeKind.TRANSFORM_POINT, physics)
                    if source_node is not None and target_node is not None:
                        contact = source.id if source.is_vertical else target.id
                        graph.adjacency[source_node.id].append(
                            NavEdge(
                                source_node.id,
                                target_node.id,
                                TraversalAction.TRANSFORM,
                                0.0,
                                contact_surface_id=contact,
                            )
                        )
                    continue
                if source.source_id is not None and target.source_id is not None and source.source_id == target.source_id:
                    continue
                if source.is_horizontal and target.is_horizontal and self._can_move_between_horizontals(source, target, physics):
                    source_t = self._clamp_anchor(source, target.rect.center_x - pet.width / 2, pet)
                    target_t = self._clamp_anchor(target, source.rect.center_x - pet.width / 2, pet)
                    source_node = self._ensure_node(graph, source, pet, source_t, NavNodeKind.JUMP_POINT, physics)
                    target_node = self._ensure_node(graph, target, pet, target_t, NavNodeKind.JUMP_POINT, physics)
                    if source_node is None or target_node is None:
                        continue
                    graph.adjacency[source_node.id].append(
                        NavEdge(
                            source_node.id,
                            target_node.id,
                            TraversalAction.TRANSFORM,
                            abs(target_node.x - source_node.x) / max(physics.walk_speed, 1.0),
                        )
                    )
                    continue

                if source.is_vertical:
                    continue

                jump = self._jump_candidate(source, target, pet)
                if jump is None:
                    continue
                launch_t, land_t = jump
                if not self._jump_reachable(
                    source,
                    launch_t,
                    target,
                    land_t,
                    abs(physics.jump_speed_x),
                    abs(physics.jump_speed_y),
                    physics.gravity,
                    physics.edge_snap_distance,
                    pet,
                ):
                    continue
                source_node = self._ensure_node(graph, source, pet, launch_t, NavNodeKind.JUMP_POINT, physics)
                target_node = self._ensure_node(graph, target, pet, land_t, NavNodeKind.JUMP_POINT, physics)
                if source_node is None or target_node is None:
                    continue
                graph.adjacency[source_node.id].append(
                    NavEdge(
                        source_node.id,
                        target_node.id,
                        TraversalAction.JUMP,
                        self._jump_cost(source_node, target_node, physics),
                        meta={"target_t": target_node.anchor_t},
                    )
                )

        return graph

    def build_navigation_mesh(self, pet: Pet, snapshot: EnvironmentSnapshot, physics: PhysicsConfig) -> SurfaceGraph:
        return self.build_surface_graph(pet, snapshot, physics)

    def build_navigation_graph(self, pet: Pet, snapshot: EnvironmentSnapshot, physics: PhysicsConfig) -> dict[str, list[PathStep]]:
        graph = self.build_surface_graph(pet, snapshot, physics)
        grouped: dict[str, list[PathStep]] = {}
        for edge in graph.edges:
            mapped = self._to_path_step(edge, graph)
            if mapped is None:
                continue
            grouped.setdefault(mapped.from_surface_id, []).append(mapped)
        return grouped

    def _ensure_node(
        self,
        graph: SurfaceGraph,
        surface: Surface | None,
        pet: Pet,
        anchor_t: float,
        role: NavNodeKind,
        physics: PhysicsConfig,
        *,
        clamp: bool = True,
    ) -> NavNode | None:
        if surface is None:
            return None
        if SurfaceCapability.MOVE not in surface.capabilities:
            return None
        clamped = self._clamp_anchor(surface, anchor_t, pet) if clamp else anchor_t
        node_id = f"{surface.id}:{role}:{round(clamped, 1)}"
        node = graph.nodes.get(node_id)
        if node is None:
            x, y = self._point_for_anchor(surface, clamped, pet)
            node = NavNode(node_id, surface.id, clamped, role, x, y)
            graph.nodes[node_id] = node
            graph.adjacency.setdefault(node_id, [])
            self._rewire_surface_move(graph, surface.id, physics)
        return node

    def _rewire_surface_move(self, graph: SurfaceGraph, surface_id: str, physics: PhysicsConfig) -> None:
        surface = graph.surfaces.get(surface_id)
        if surface is None:
            return
        nodes = [node for node in graph.nodes.values() if node.surface_id == surface_id]
        node_ids = {node.id for node in nodes}
        for node in nodes:
            graph.adjacency.setdefault(node.id, [])
            graph.adjacency[node.id] = [
                edge
                for edge in graph.adjacency[node.id]
                if not (edge.action == TraversalAction.MOVE and edge.to_node_id in node_ids)
            ]
        nodes.sort(key=lambda node: node.anchor_t)
        for index in range(len(nodes) - 1):
            left = nodes[index]
            right = nodes[index + 1]
            cost = self._move_cost(surface, left.anchor_t, right.anchor_t, physics)
            graph.adjacency[left.id].append(NavEdge(left.id, right.id, TraversalAction.MOVE, cost))
            graph.adjacency[right.id].append(NavEdge(right.id, left.id, TraversalAction.MOVE, cost))

    def _search(self, graph: SurfaceGraph, start: str, target: str) -> list[NavEdge]:
        previous = self.planner.shortest_path_tree(graph.adjacency, start, target)
        if previous is None:
            return []
        edges: list[NavEdge] = []
        current = target
        while current != start:
            item = previous.get(current)
            if item is None:
                return []
            parent, edge = item
            edges.append(edge)
            current = parent
        edges.reverse()
        return edges

    def _map_edges(self, edges: list[NavEdge], graph: SurfaceGraph) -> list[PathStep]:
        raw: list[PathStep] = []
        for edge in edges:
            mapped = self._to_path_step(edge, graph)
            if mapped is not None:
                raw.append(mapped)
        return raw

    def _to_path_step(self, edge: NavEdge, graph: SurfaceGraph) -> PathStep | None:
        source = graph.nodes.get(edge.from_node_id)
        target = graph.nodes.get(edge.to_node_id)
        if source is None or target is None:
            return None
        target_t = target.anchor_t
        land_t: float | None = target.anchor_t
        approach_point = (target.x, target.y)
        land_point = (target.x, target.y)
        if edge.action in {TraversalAction.JUMP, TraversalAction.FALL, TraversalAction.TRANSFORM}:
            target_t = source.anchor_t
            land_t = target.anchor_t
            approach_point = (source.x, source.y)
        if "target_t" in edge.meta:
            land_t = float(edge.meta["target_t"])
        return PathStep(
            edge.action,
            source.surface_id,
            target.surface_id,
            target_t,
            edge.cost,
            edge.contact_surface_id,
            land_t,
            approach_point=approach_point,
            land_point=land_point,
        )

    def _point_move_step(self, surface: Surface, target_t: float, physics: PhysicsConfig, pet: Pet) -> PathStep:
        return PathStep(
            TraversalAction.MOVE,
            surface.id,
            surface.id,
            target_t,
            abs(target_t - self._pet_anchor_t(surface, pet)) / max(self._move_speed(surface, physics), 1.0),
            land_t=target_t,
            approach_point=self._point_for_anchor(surface, target_t, pet),
            land_point=self._point_for_anchor(surface, target_t, pet),
        )

    def _merge_consecutive_same_surface_move_steps(self, steps: list[PathStep]) -> list[PathStep]:
        if len(steps) <= 1:
            return steps
        merged: list[PathStep] = []
        index = 0
        while index < len(steps):
            current = steps[index]
            if not (current.action == TraversalAction.MOVE and current.from_surface_id == current.to_surface_id):
                merged.append(current)
                index += 1
                continue

            total_cost = current.cost
            last = current
            scan = index + 1
            while scan < len(steps):
                nxt = steps[scan]
                if not (
                    nxt.action == TraversalAction.MOVE
                    and nxt.from_surface_id == nxt.to_surface_id
                    and nxt.from_surface_id == current.from_surface_id
                ):
                    break
                total_cost += nxt.cost
                last = nxt
                scan += 1
            merged.append(
                PathStep(
                    TraversalAction.MOVE,
                    current.from_surface_id,
                    current.to_surface_id,
                    last.target_t,
                    total_cost,
                    land_t=last.land_t if last.land_t is not None else last.target_t,
                    approach_point=last.approach_point,
                    land_point=last.land_point,
                )
            )
            index = scan
        return merged

    def _first_horizontal_hit_below(
        self,
        source: Surface,
        drop_t: float,
        surfaces: list[Surface],
        pet: Pet,
    ) -> Surface | None:
        candidates = [
            target
            for target in surfaces
            if target.id != source.id
            and target.rect.top > source.rect.top
            and target.rect.left - pet.width <= drop_t <= target.rect.right
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda surface: surface.rect.top)

    def _is_drop_side_valid(
        self,
        surface: Surface,
        side: str,
        snapshot: EnvironmentSnapshot,
        pet: Pet,
    ) -> bool:
        bounds = snapshot.screen_rect
        if side == "left":
            gap = surface.rect.left - bounds.left
            return gap >= pet.width
        gap = bounds.right - surface.rect.right
        return gap >= pet.width

    def _jump_candidate(self, source: Surface, target: Surface, pet: Pet) -> tuple[float, float] | None:
        if source.is_vertical:
            return None

        source_min, source_max = self._anchor_interval(source, pet)
        if target.is_horizontal:
            if self._can_fall_between_horizontals(source, target, pet):
                return None
            target_min, target_max = self._anchor_interval(target, pet)
            launch_t, land_t = self._closest_values_between_intervals(source_min, source_max, target_min, target_max)
            return self._clamp_anchor(source, launch_t, pet), self._clamp_anchor(target, land_t, pet)

        target_x = target.rect.center_x - pet.width / 2
        launch_t = self._clamp_value(target_x, source_min, source_max)
        source_y = source.rect.top - pet.height
        target_t = self._clamp_value(source_y + pet.height, target.rect.top, target.rect.bottom)
        return self._clamp_anchor(source, launch_t, pet), self._clamp_anchor(target, target_t, pet)

    def _jump_reachable(
        self,
        source: Surface,
        source_t: float,
        target: Surface,
        target_t: float,
        max_horizontal_speed: float,
        max_vertical_speed: float,
        gravity: float,
        edge_snap: float,
        pet: Pet,
    ) -> bool:
        source_x, source_y = self._point_for_anchor(source, source_t, pet)
        target_x, target_y = self._point_for_anchor(target, target_t, pet)
        if source.is_horizontal and target.is_horizontal:
            same_level = abs(source.rect.top - target.rect.top) <= edge_snap
            if same_level:
                if source.rect.overlaps_x(target.rect):
                    return False
                if self._horizontal_gap(source, target) <= edge_snap:
                    return False

        dx = abs(target_x - source_x)
        dy = target_y - source_y
        max_vx = max(max_horizontal_speed, 1.0)
        max_up_vy = max(max_vertical_speed, 1.0)
        g = max(gravity, 1.0)
        t = max(dx / max_vx, 0.18)
        required_vy = (dy - 0.5 * g * t * t) / t
        if required_vy > -1.0:
            required_vy = -max_up_vy
            disc = required_vy * required_vy + 2.0 * g * max(dy, 0.0)
            t = max((math.sqrt(max(disc, 0.0)) - required_vy) / g, 0.18)
        required_vx = dx / max(t, 1e-3)
        if required_vx > max_vx:
            return False
        if required_vy < -max_up_vy:
            return False
        return True

    def _can_move_between_horizontals(self, source: Surface, target: Surface, physics: PhysicsConfig) -> bool:
        if abs(source.rect.top - target.rect.top) > physics.edge_snap_distance:
            return False
        return self._horizontal_gap(source, target) <= physics.edge_snap_distance

    def _can_transform_between_surfaces(self, source: Surface, target: Surface) -> bool:
        if source.is_horizontal == target.is_horizontal:
            return False
        return source.rect.intersects(target.rect)

    def _transform_anchors(self, source: Surface, target: Surface, pet: Pet) -> tuple[float, float]:
        if source.is_horizontal:
            horizontal = source
            vertical = target
        else:
            horizontal = target
            vertical = source
        horizontal_t = self._clamp_anchor(horizontal, vertical.rect.center_x - pet.width / 2, pet)
        vertical_t = self._clamp_anchor(vertical, horizontal.rect.top, pet)
        if source.is_horizontal:
            return horizontal_t, vertical_t
        return vertical_t, horizontal_t

    def _can_fall_between_horizontals(self, source: Surface, target: Surface, pet: Pet) -> bool:
        if not source.is_horizontal or not target.is_horizontal:
            return False
        if target.rect.top <= source.rect.top:
            return False
        return source.rect.left - pet.width <= target.rect.right and source.rect.right >= target.rect.left - pet.width

    def _horizontal_gap(self, source: Surface, target: Surface) -> float:
        if source.rect.overlaps_x(target.rect):
            return 0.0
        if source.rect.right < target.rect.left:
            return target.rect.left - source.rect.right
        return source.rect.left - target.rect.right

    def _anchor_interval(self, surface: Surface, pet: Pet) -> tuple[float, float]:
        if surface.is_horizontal:
            return surface.rect.left - pet.width / 2, surface.rect.right - pet.width / 2
        return surface.rect.top, surface.rect.bottom

    def _closest_values_between_intervals(
        self,
        source_min: float,
        source_max: float,
        target_min: float,
        target_max: float,
    ) -> tuple[float, float]:
        overlap_min = max(source_min, target_min)
        overlap_max = min(source_max, target_max)
        if overlap_min <= overlap_max:
            value = (overlap_min + overlap_max) / 2
            return value, value
        if source_max < target_min:
            return source_max, target_min
        return source_min, target_max

    def _clamp_value(self, value: float, minimum: float, maximum: float) -> float:
        return min(max(value, minimum), maximum)

    def _clamp_anchor(self, surface: Surface, anchor_t: float, pet: Pet) -> float:
        if surface.is_horizontal:
            return min(max(anchor_t, surface.rect.left - pet.width / 2), surface.rect.right - pet.width / 2)
        return min(max(anchor_t, surface.rect.top), surface.rect.bottom)

    def _pet_anchor_t(self, surface: Surface, pet: Pet) -> float:
        if surface.is_horizontal:
            return pet.position.x
        return pet.bottom

    def _point_for_anchor(self, surface: Surface, anchor_t: float, pet: Pet) -> tuple[float, float]:
        if surface.is_horizontal:
            return anchor_t, surface.rect.top - pet.height
        return surface.rect.center_x - pet.width / 2, anchor_t - pet.height

    def _move_speed(self, surface: Surface, physics: PhysicsConfig) -> float:
        if surface.is_vertical:
            return physics.climb_speed
        return physics.walk_speed

    def _move_cost(self, surface: Surface, from_t: float, to_t: float, physics: PhysicsConfig) -> float:
        return abs(to_t - from_t) / max(self._move_speed(surface, physics), 1.0)

    def _jump_cost(self, source: NavNode, target: NavNode, physics: PhysicsConfig) -> float:
        horizontal = abs(target.x - source.x)
        vertical = abs(target.y - source.y)
        air_time = 2.0 * abs(physics.jump_speed_y) / max(physics.gravity, 1.0)
        return air_time + horizontal / max(physics.jump_speed_x, 1.0) + vertical / 400.0 + 2.0

    def _fall_cost(self, vertical: float, physics: PhysicsConfig) -> float:
        gravity = max(physics.gravity, 1.0)
        return (2.0 * max(vertical, 0.0) / gravity) ** 0.5
