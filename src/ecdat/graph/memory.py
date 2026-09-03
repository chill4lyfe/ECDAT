from ecdat.domain.models import GraphEdge, GraphNode


class InMemoryGraphStore:
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}

    async def upsert_node(self, node: GraphNode) -> None:
        self._nodes[node.id] = node

    async def upsert_edge(self, edge: GraphEdge) -> None:
        self._edges[edge.id] = edge

    async def snapshot(self) -> tuple[tuple[GraphNode, ...], tuple[GraphEdge, ...]]:
        return tuple(self._nodes.values()), tuple(self._edges.values())
