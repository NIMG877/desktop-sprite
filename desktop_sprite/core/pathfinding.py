from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from desktop_sprite.core.planner import GraphPlanner
from desktop_sprite.core.reachability_policy import ReachabilityPolicy
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.platform import Platform
from desktop_sprite.models.platform_topology import PlatformTopology
from desktop_sprite.models.state import Pet
from desktop_sprite.utils.config import PhysicsConfig


class PathAction(StrEnum):
    WALK = "walk"
    JUMP = "jump"
    CLIMB = "climb"


class NavNodeKind(StrEnum):
    DROP_POINT = "drop_point"
    JUMP_POINT = "jump_point"
    CLIMB_CONTACT = "climb_contact"
    CLIMB_ENDPOINT = "climb_endpoint"


@dataclass(frozen=True, slots=True)
class NavNode:
    id: str
    platform_id: str
    x: float
    y: float
    kind: NavNodeKind


@dataclass(frozen=True, slots=True)
class NavEdge:
    from_node_id: str
    to_node_id: str
    action: PathAction
    cost: float
    side_platform_id: str | None = None
    meta: dict[str, float | str] = field(default_factory=dict)


@dataclass(slots=True)
class NavigationMesh:
    nodes: dict[str, NavNode]
    adjacency: dict[str, list[NavEdge]]

    @property
    def edges(self) -> list[NavEdge]:
        return [edge for edges in self.adjacency.values() for edge in edges]


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
        physics: PhysicsConfig,
    ) -> PathPlan | None:
        return self.find_path_to_platform(
            pet=pet,
            snapshot=snapshot,
            target_platform_id=PlatformTopology.window_top_id(target_window_id),
            physics=physics,
            target_window_id=target_window_id,
        )

    def find_path_to_platform(
        self,
        pet: Pet,
        snapshot: EnvironmentSnapshot,
        target_platform_id: str,
        physics: PhysicsConfig,
        target_window_id: int | None = None,
    ) -> PathPlan | None:
        start_platform_id = pet.support_platform_id
        if start_platform_id is None or start_platform_id == target_platform_id:
            return None
        if snapshot.platform_by_id(start_platform_id) is None or snapshot.platform_by_id(target_platform_id) is None:
            return None

        mesh = self.build_navigation_mesh(pet, snapshot, physics)
        start_platform = snapshot.platform_by_id(start_platform_id)
        start_node = self._ensure_jump_node(mesh, start_platform, pet, pet.position.x, physics) if start_platform else None
        target_platform = snapshot.platform_by_id(target_platform_id)
        if start_node is None or target_platform is None:
            return None
        target_x = target_platform.rect.center_x - pet.width / 2
        target_node = self._ensure_jump_node(mesh, target_platform, pet, target_x, physics)
        if target_node is None:
            return None

        nav_edges = self._search(mesh, start_node.id, target_node.id)
        if not nav_edges:
            return None
        path_edges = self._map_edges(nav_edges, mesh)
        if not path_edges:
            return None
        return PathPlan(path_edges, 0, target_window_id, snapshot.timestamp, target_platform_id=target_platform_id)

    def find_path_to_point(
        self,
        pet: Pet,
        snapshot: EnvironmentSnapshot,
        target_platform_id: str,
        target_x: float,
        physics: PhysicsConfig,
        target_window_id: int | None = None,
    ) -> PathPlan | None:
        start_platform_id = pet.support_platform_id
        if start_platform_id is None:
            return None
        target_platform = snapshot.platform_by_id(target_platform_id)
        start_platform = snapshot.platform_by_id(start_platform_id)
        if target_platform is None or start_platform is None:
            return None
        clamped_target_x = min(max(target_x, target_platform.rect.left), target_platform.rect.right - pet.width)
        if start_platform_id == target_platform_id:
            return PathPlan(
                edges=[self._point_walk_edge(start_platform, clamped_target_x, physics, pet)],
                current_index=0,
                target_window_id=target_window_id,
                snapshot_timestamp=snapshot.timestamp,
                target_platform_id=target_platform_id,
                target_x=clamped_target_x,
            )

        mesh = self.build_navigation_mesh(pet, snapshot, physics)
        start_node = self._ensure_jump_node(mesh, start_platform, pet, pet.position.x, physics)
        target_node = self._ensure_jump_node(mesh, target_platform, pet, clamped_target_x, physics)
        if start_node is None or target_node is None:
            return None
        nav_edges = self._search(mesh, start_node.id, target_node.id)
        if not nav_edges:
            return None
        path_edges = self._map_edges(nav_edges, mesh)
        if not path_edges:
            return None
        path_edges.append(self._point_walk_edge(target_platform, clamped_target_x, physics, pet))
        return PathPlan(
            edges=path_edges,
            current_index=0,
            target_window_id=target_window_id,
            snapshot_timestamp=snapshot.timestamp,
            target_platform_id=target_platform_id,
            target_x=clamped_target_x,
        )

    def build_navigation_mesh(self, pet: Pet, snapshot: EnvironmentSnapshot, physics: PhysicsConfig) -> NavigationMesh:
        nodes: dict[str, NavNode] = {}
        adjacency: dict[str, list[NavEdge]] = {}
        mesh = NavigationMesh(nodes, adjacency)
        platforms = snapshot.platforms
        walkable = [platform for platform in platforms if platform.walkable]
        climbable = [platform for platform in platforms if platform.climbable]
        reachability = ReachabilityPolicy(physics, physics.edge_snap_distance)
        max_jump_h = reachability.max_jump_height()
        max_jump_d = reachability.max_jump_distance()

        for side in climbable:
            node = NavNode(
                id=f"{side.id}:climb_contact",
                platform_id=side.id,
                x=side.rect.center_x - pet.width / 2,
                y=side.rect.bottom - pet.height,
                kind=NavNodeKind.CLIMB_CONTACT,
            )
            nodes[node.id] = node
            adjacency[node.id] = []

        for side in climbable:
            top = snapshot.platform_by_id(PlatformTopology.top_id_for_side(side))
            if top is None or not top.walkable:
                continue
            # Only create climb endpoints on the same window's top platform.
            if side.source_id is None or top.source_id is None or side.source_id != top.source_id:
                continue
            contact = nodes.get(f"{side.id}:climb_contact")
            if contact is None:
                continue
            endpoint = self._ensure_climb_endpoint_node(mesh, top, side, pet, contact.x, physics)
            if endpoint is None:
                continue
            climb_distance = max(0.0, side.rect.bottom - top.rect.top)
            adjacency[contact.id].append(
                NavEdge(contact.id, endpoint.id, PathAction.CLIMB, climb_distance / max(physics.climb_speed, 1.0), side_platform_id=side.id)
            )

        for source in walkable:
            for side in ("left", "right"):
                if not self._is_drop_side_valid(source, side, snapshot, pet):
                    continue
                drop_x = source.rect.left - pet.width + 7.0 if side == "left" else source.rect.right - 7.0
                landing = self._first_platform_hit_below(source, drop_x, walkable, pet)
                if landing is None:
                    continue
                drop_node = self._ensure_drop_node(mesh, source, pet, drop_x, side, physics)
                landing_anchor = self._ensure_drop_landing_node(mesh, landing, pet, drop_x, source.id, side, physics)
                if drop_node is None or landing_anchor is None:
                    continue
                vertical = landing.rect.top - source.rect.top
                adjacency[drop_node.id].append(
                    NavEdge(drop_node.id, landing_anchor.id, PathAction.WALK, vertical / 200.0 + 3.0, meta={"drop": "1"})
                )

            for target in walkable:
                if target.id == source.id:
                    continue
                launch_x = self._jump_launch_x_for_platform_target(source, target, pet)
                landing_x = self._jump_landing_x_for_platform_target(source, target, pet)
                launch_x = self._clamp_jump_x(source, launch_x, pet)
                if not self._jump_reachable(source, launch_x, target, landing_x, max_jump_h, max_jump_d, physics.edge_snap_distance):
                    continue
                jump_node = self._ensure_jump_node(mesh, source, pet, launch_x, physics)
                target_anchor = self._ensure_jump_node(mesh, target, pet, landing_x, physics)
                if jump_node is None or target_anchor is None:
                    continue
                horizontal = abs(landing_x - launch_x)
                vertical = abs(target.rect.top - source.rect.top)
                air_time = 2.0 * abs(physics.jump_speed_y) / max(physics.gravity, 1.0)
                adjacency[jump_node.id].append(
                    NavEdge(
                        jump_node.id,
                        target_anchor.id,
                        PathAction.JUMP,
                        air_time + horizontal / max(physics.jump_speed_x, 1.0) + vertical / 400.0 + 2.0,
                        meta={"target_x": landing_x},
                    )
                )

            for side in climbable:
                top = snapshot.platform_by_id(PlatformTopology.top_id_for_side(side))
                if top is None or not top.walkable:
                    continue
                if source.source_id is not None and side.source_id is not None and source.source_id == side.source_id:
                    continue
                contact = nodes.get(f"{side.id}:climb_contact")
                if contact is None:
                    continue
                launch_x = self._clamp_jump_x(source, self._jump_launch_x_for_contact_target(source, side, contact, pet), pet)
                if not self._jump_reachable_to_contact(source, launch_x, side, contact.x, max_jump_h, max_jump_d):
                    continue
                jump_node = self._ensure_jump_node(mesh, source, pet, launch_x, physics)
                if jump_node is None:
                    continue
                horizontal = abs(contact.x - launch_x)
                adjacency[jump_node.id].append(
                    NavEdge(jump_node.id, contact.id, PathAction.JUMP, 2.0 + horizontal / max(physics.jump_speed_x, 1.0))
                )

        for source in walkable:
            for target in walkable:
                if source.id == target.id:
                    continue
                if abs(source.rect.top - target.rect.top) > physics.edge_snap_distance:
                    continue
                if self._platform_horizontal_gap(source, target) > physics.edge_snap_distance:
                    continue
                source_node = self._ensure_jump_node(mesh, source, pet, target.rect.center_x - pet.width / 2, physics)
                target_node = self._ensure_jump_node(mesh, target, pet, source.rect.center_x - pet.width / 2, physics)
                if source_node is None or target_node is None:
                    continue
                cost = abs(target_node.x - source_node.x) / max(physics.walk_speed, 1.0)
                adjacency[source_node.id].append(NavEdge(source_node.id, target_node.id, PathAction.WALK, cost))

        return mesh

    def build_navigation_graph(self, pet: Pet, snapshot: EnvironmentSnapshot, physics: PhysicsConfig) -> dict[str, list[PathEdge]]:
        mesh = self.build_navigation_mesh(pet, snapshot, physics)
        grouped: dict[str, list[PathEdge]] = {}
        for edge in mesh.edges:
            mapped = self._to_path_edge(edge, mesh)
            if mapped is None:
                continue
            grouped.setdefault(mapped.from_platform_id, []).append(mapped)
        return grouped

    def _ensure_drop_node(
        self,
        mesh: NavigationMesh,
        platform: Platform,
        pet: Pet,
        x: float,
        side: str,
        physics: PhysicsConfig,
    ) -> NavNode | None:
        node_id = f"{platform.id}:drop:{side}"
        node = mesh.nodes.get(node_id)
        if node is None:
            node = NavNode(node_id, platform.id, x, platform.rect.top - pet.height, NavNodeKind.DROP_POINT)
            mesh.nodes[node_id] = node
            mesh.adjacency.setdefault(node_id, [])
            self._rewire_platform_walk(mesh, platform.id, physics)
        return node

    def _ensure_drop_landing_node(
        self,
        mesh: NavigationMesh,
        platform: Platform,
        pet: Pet,
        x: float,
        source_platform_id: str,
        side: str,
        physics: PhysicsConfig,
    ) -> NavNode | None:
        clamped = self._clamp_jump_x(platform, x, pet)
        node_id = f"{platform.id}:drop_target:{source_platform_id}:{side}:{round(clamped,1)}"
        node = mesh.nodes.get(node_id)
        if node is None:
            node = NavNode(node_id, platform.id, clamped, platform.rect.top - pet.height, NavNodeKind.DROP_POINT)
            mesh.nodes[node_id] = node
            mesh.adjacency.setdefault(node_id, [])
            self._rewire_platform_walk(mesh, platform.id, physics)
        return node

    def _ensure_jump_node(self, mesh: NavigationMesh, platform: Platform | None, pet: Pet, x: float, physics: PhysicsConfig) -> NavNode | None:
        if platform is None or not platform.walkable:
            return None
        clamped = self._clamp_jump_x(platform, x, pet)
        node_id = f"{platform.id}:jump:{round(clamped,1)}"
        node = mesh.nodes.get(node_id)
        if node is None:
            node = NavNode(node_id, platform.id, clamped, platform.rect.top - pet.height, NavNodeKind.JUMP_POINT)
            mesh.nodes[node_id] = node
            mesh.adjacency.setdefault(node_id, [])
            self._rewire_platform_walk(mesh, platform.id, physics)
        return node

    def _ensure_climb_endpoint_node(
        self,
        mesh: NavigationMesh,
        platform: Platform,
        side: Platform,
        pet: Pet,
        x: float,
        physics: PhysicsConfig,
    ) -> NavNode | None:
        clamped = self._clamp_jump_x(platform, x, pet)
        node_id = f"{platform.id}:climb_endpoint:{side.id}:{round(clamped,1)}"
        node = mesh.nodes.get(node_id)
        if node is None:
            node = NavNode(node_id, platform.id, clamped, platform.rect.top - pet.height, NavNodeKind.CLIMB_ENDPOINT)
            mesh.nodes[node_id] = node
            mesh.adjacency.setdefault(node_id, [])
            self._rewire_platform_walk(mesh, platform.id, physics)
        return node

    def _rewire_platform_walk(self, mesh: NavigationMesh, platform_id: str, physics: PhysicsConfig) -> None:
        nodes = [node for node in mesh.nodes.values() if node.platform_id == platform_id and node.kind != NavNodeKind.CLIMB_CONTACT]
        node_ids = {node.id for node in nodes}
        for node in nodes:
            mesh.adjacency.setdefault(node.id, [])
            mesh.adjacency[node.id] = [edge for edge in mesh.adjacency[node.id] if not (edge.action == PathAction.WALK and edge.to_node_id in node_ids)]
        nodes.sort(key=lambda node: node.x)
        for i in range(len(nodes) - 1):
            left = nodes[i]
            right = nodes[i + 1]
            cost = abs(right.x - left.x) / max(physics.walk_speed, 1.0)
            mesh.adjacency[left.id].append(NavEdge(left.id, right.id, PathAction.WALK, cost))
            mesh.adjacency[right.id].append(NavEdge(right.id, left.id, PathAction.WALK, cost))

    def _search(self, mesh: NavigationMesh, start: str, target: str) -> list[NavEdge]:
        previous = self.planner.shortest_path_tree(mesh.adjacency, start, target)
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

    def _map_edges(self, edges: list[NavEdge], mesh: NavigationMesh) -> list[PathEdge]:
        raw: list[PathEdge] = []
        for edge in edges:
            mapped = self._to_path_edge(edge, mesh)
            if mapped is not None:
                raw.append(mapped)
        return raw

    def _to_path_edge(self, edge: NavEdge, mesh: NavigationMesh) -> PathEdge | None:
        source = mesh.nodes.get(edge.from_node_id)
        target = mesh.nodes.get(edge.to_node_id)
        if source is None or target is None:
            return None
        target_x = target.x
        if edge.meta.get("drop") == "1":
            target_x = source.x
        if edge.action == PathAction.JUMP and "target_x" in edge.meta:
            target_x = float(edge.meta["target_x"])
        if edge.action == PathAction.CLIMB:
            target_x = source.x
        return PathEdge(edge.action, source.platform_id, target.platform_id, target_x, edge.cost, edge.side_platform_id)

    def _point_walk_edge(self, platform: Platform, target_x: float, physics: PhysicsConfig, pet: Pet) -> PathEdge:
        return PathEdge(PathAction.WALK, platform.id, platform.id, target_x, abs(target_x - pet.position.x) / max(physics.walk_speed, 1.0))

    def _trim_platform_walk_transitions(self, edges: list[PathEdge]) -> list[PathEdge]:
        if len(edges) <= 1:
            return edges
        trimmed = list(edges)
        while (
            len(trimmed) > 1
            and trimmed[0].action == PathAction.WALK
            and trimmed[0].from_platform_id == trimmed[0].to_platform_id
            and trimmed[1].action in {PathAction.CLIMB, PathAction.JUMP}
            and trimmed[1].from_platform_id == trimmed[0].from_platform_id
        ):
            trimmed.pop(0)
        while (
            len(trimmed) > 1
            and trimmed[-1].action == PathAction.WALK
            and trimmed[-1].from_platform_id == trimmed[-1].to_platform_id
            and trimmed[-2].to_platform_id == trimmed[-1].from_platform_id
        ):
            trimmed.pop()
        return trimmed

    def _first_platform_hit_below(
        self,
        source: Platform,
        drop_x: float,
        platforms: list[Platform],
        pet: Pet,
    ) -> Platform | None:
        candidates = [
            target
            for target in platforms
            if target.id != source.id
            and target.rect.top > source.rect.top
            and target.rect.left <= drop_x <= target.rect.right - pet.width
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda platform: platform.rect.top)

    def _is_drop_side_valid(
        self,
        platform: Platform,
        side: str,
        snapshot: EnvironmentSnapshot,
        pet: Pet,
    ) -> bool:
        bounds = snapshot.screen_rect
        if side == "left":
            gap = platform.rect.left - bounds.left
            return gap >= pet.width
        gap = bounds.right - platform.rect.right
        return gap >= pet.width

    def _jump_reachable(
        self,
        source_platform: Platform,
        source_x: float,
        target_platform: Platform,
        target_x: float,
        max_jump_h: float,
        max_jump_d: float,
        edge_snap: float,
    ) -> bool:
        if target_platform.rect.top > source_platform.rect.top + edge_snap:
            return False
        same_level = abs(target_platform.rect.top - source_platform.rect.top) <= edge_snap
        if same_level:
            if source_platform.rect.overlaps_x(target_platform.rect):
                return False
            gap = self._platform_horizontal_gap(source_platform, target_platform)
            if gap <= edge_snap:
                return False
        vertical_up = max(0.0, source_platform.rect.top - target_platform.rect.top)
        if vertical_up > max_jump_h:
            return False
        return abs(target_x - source_x) <= max_jump_d

    def _jump_reachable_to_contact(
        self,
        source_platform: Platform,
        source_x: float,
        side: Platform,
        contact_x: float,
        max_jump_h: float,
        max_jump_d: float,
    ) -> bool:
        vertical_up = max(0.0, source_platform.rect.top - side.rect.bottom)
        if vertical_up > max_jump_h:
            return False
        return abs(contact_x - source_x) <= max_jump_d

    def _jump_launch_x_for_platform_target(self, source: Platform, target: Platform, pet: Pet) -> float:
        return source.rect.right - pet.width / 2 if target.rect.center_x >= source.rect.center_x else source.rect.left - pet.width / 2

    def _jump_landing_x_for_platform_target(self, source: Platform, target: Platform, pet: Pet) -> float:
        return target.rect.left - pet.width / 2 if target.rect.center_x >= source.rect.center_x else target.rect.right - pet.width / 2

    def _jump_launch_x_for_contact_target(self, source: Platform, side: Platform, contact: NavNode, pet: Pet) -> float:
        if side.rect.center_x >= source.rect.center_x:
            return min(source.rect.right - pet.width / 2, contact.x)
        return max(source.rect.left - pet.width / 2, contact.x)

    def _clamp_jump_x(self, platform: Platform, x: float, pet: Pet) -> float:
        return min(max(x, platform.rect.left - pet.width / 2), platform.rect.right - pet.width / 2)

    def _platform_horizontal_gap(self, source: Platform, target: Platform) -> float:
        if source.rect.overlaps_x(target.rect):
            return 0.0
        if source.rect.right < target.rect.left:
            return target.rect.left - source.rect.right
        return source.rect.left - target.rect.right
