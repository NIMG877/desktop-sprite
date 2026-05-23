from __future__ import annotations

import heapq


class GraphPlanner:
    def shortest_path_tree(
        self,
        graph,
        start_id: str,
        target_id: str,
    ) -> dict[str, tuple[str, object]] | None:
        distances: dict[str, float] = {start_id: 0.0}
        previous: dict[str, tuple[str, object]] = {}
        queue: list[tuple[float, str]] = [(0.0, start_id)]

        while queue:
            cost, platform_id = heapq.heappop(queue)
            if cost > distances.get(platform_id, float("inf")):
                continue
            if platform_id == target_id:
                return previous

            for edge in graph.get(platform_id, []):
                to_id = self._edge_target_id(edge)
                if to_id is None:
                    continue
                next_cost = cost + edge.cost
                if next_cost >= distances.get(to_id, float("inf")):
                    continue
                distances[to_id] = next_cost
                previous[to_id] = (platform_id, edge)
                heapq.heappush(queue, (next_cost, to_id))
        return None

    def _edge_target_id(self, edge) -> str | None:
        if hasattr(edge, "to_node_id"):
            return getattr(edge, "to_node_id")
        return None
