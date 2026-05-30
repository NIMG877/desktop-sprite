from __future__ import annotations

import heapq
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from desktop_sprite.core.pathfinding import NavEdge


class GraphPlanner:
    def shortest_path_tree(
        self,
        adjacency: Mapping[str, Sequence["NavEdge"]],
        start_id: str,
        target_id: str,
    ) -> dict[str, tuple[str, "NavEdge"]] | None:
        distances: dict[str, float] = {start_id: 0.0}
        previous: dict[str, tuple[str, "NavEdge"]] = {}
        queue: list[tuple[float, str]] = [(0.0, start_id)]

        while queue:
            cost, node_id = heapq.heappop(queue)
            if cost > distances.get(node_id, float("inf")):
                continue
            if node_id == target_id:
                return previous

            for edge in adjacency.get(node_id, []):
                to_id = edge.to_node_id
                next_cost = cost + edge.cost
                if next_cost >= distances.get(to_id, float("inf")):
                    continue
                distances[to_id] = next_cost
                previous[to_id] = (node_id, edge)
                heapq.heappush(queue, (next_cost, to_id))
        return None
