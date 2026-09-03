from __future__ import annotations

from collections import defaultdict, deque

from ecdat.domain.enums import GraphEdgeType, GraphNodeType
from ecdat.domain.models import GraphEdge, GraphInsight, GraphNode

_SERVICE_EDGE_TYPES = {
    GraphEdgeType.DEPENDS_ON,
    GraphEdgeType.CONNECTS_TO,
    GraphEdgeType.AUTHENTICATES_WITH,
}


class GraphAnalyzer:
    def analyze(
        self,
        nodes: tuple[GraphNode, ...],
        edges: tuple[GraphEdge, ...],
    ) -> tuple[GraphInsight, ...]:
        incoming: dict[str, list[GraphEdge]] = defaultdict(list)
        outgoing: dict[str, list[GraphEdge]] = defaultdict(list)
        for edge in edges:
            incoming[edge.target_id].append(edge)
            outgoing[edge.source_id].append(edge)

        max_degree = max(
            (len(incoming[node.id]) + len(outgoing[node.id]) for node in nodes),
            default=1,
        )
        insights: list[GraphInsight] = []
        node_map = {node.id: node for node in nodes}
        for node in nodes:
            inbound = len(incoming[node.id])
            outbound = len(outgoing[node.id])
            degree = inbound + outbound
            blast = self._blast_radius(node.id, outgoing, node_map)
            centrality = degree / max_degree if max_degree else 0.0
            impacted_services = self._impacted_services(node.id, incoming, outgoing, node_map)
            blocker = len(impacted_services) >= 2 and node.node_type in {
                GraphNodeType.CERTIFICATE,
                GraphNodeType.KEY,
                GraphNodeType.LIBRARY,
                GraphNodeType.PROTOCOL,
                GraphNodeType.SERVICE,
            }
            reasons = []
            if blast >= 3:
                reasons.append(f"Changing this node can affect {blast} downstream graph nodes.")
            if len(impacted_services) >= 2:
                reasons.append(f"It is connected to {len(impacted_services)} service contexts.")
            if centrality >= 0.65:
                reasons.append("It has high relative graph centrality in this scan.")
            insights.append(
                GraphInsight(
                    node_id=node.id,
                    degree=degree,
                    inbound=inbound,
                    outbound=outbound,
                    blast_radius=blast,
                    centrality=round(centrality, 4),
                    migration_blocker=blocker,
                    reasons=tuple(reasons),
                )
            )
        return tuple(sorted(insights, key=lambda item: (-item.centrality, -item.blast_radius, item.node_id)))

    def _blast_radius(
        self,
        start: str,
        outgoing: dict[str, list[GraphEdge]],
        nodes: dict[str, GraphNode],
    ) -> int:
        queue = deque([start])
        seen = {start}
        while queue:
            current = queue.popleft()
            for edge in outgoing[current]:
                if edge.edge_type not in _SERVICE_EDGE_TYPES | {GraphEdgeType.PROTECTS, GraphEdgeType.USES}:
                    continue
                if edge.target_id not in seen and edge.target_id in nodes:
                    seen.add(edge.target_id)
                    queue.append(edge.target_id)
        return max(0, len(seen) - 1)

    def _impacted_services(
        self,
        start: str,
        incoming: dict[str, list[GraphEdge]],
        outgoing: dict[str, list[GraphEdge]],
        nodes: dict[str, GraphNode],
    ) -> set[str]:
        queue = deque([start])
        seen = {start}
        services: set[str] = set()
        while queue:
            current = queue.popleft()
            node = nodes.get(current)
            if node and node.node_type in {GraphNodeType.SERVICE, GraphNodeType.CONTAINER}:
                services.add(current)
            for edge in incoming[current] + outgoing[current]:
                if edge.edge_type not in _SERVICE_EDGE_TYPES | {GraphEdgeType.USES}:
                    continue
                neighbor = edge.source_id if edge.target_id == current else edge.target_id
                if neighbor not in seen and neighbor in nodes:
                    seen.add(neighbor)
                    queue.append(neighbor)
        return services
