from __future__ import annotations

from neo4j import AsyncDriver, AsyncGraphDatabase

from ecdat.domain.enums import GraphEdgeType, GraphNodeType
from ecdat.domain.models import GraphEdge, GraphNode
from ecdat.settings import get_settings


class Neo4jGraphStore:
    """Neo4j-backed graph store with per-instance snapshot scoping.

    Node/edge IDs written by this store instance are tracked locally so the API response
    represents the current scan, while Neo4j may retain previous enterprise graph state.
    """

    def __init__(self, driver: AsyncDriver | None = None) -> None:
        settings = get_settings()
        self.driver = driver or AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        self._node_ids: set[str] = set()
        self._edge_ids: set[str] = set()
        self._schema_ready = False

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        async with self.driver.session() as session:
            result = await session.run(
                "CREATE CONSTRAINT ecdat_node_id IF NOT EXISTS FOR (n:ECDATNode) REQUIRE n.id IS UNIQUE"
            )
            await result.consume()
        self._schema_ready = True

    async def upsert_node(self, node: GraphNode) -> None:
        await self._ensure_schema()
        query = """
        MERGE (n:ECDATNode {id: $id})
        SET n.type = $type,
            n.label = $label,
            n += $properties,
            n.updated_at = datetime()
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                id=node.id,
                type=node.node_type.value,
                label=node.label,
                properties=node.properties,
            )
            await result.consume()
        self._node_ids.add(node.id)

    async def upsert_edge(self, edge: GraphEdge) -> None:
        query = """
        MATCH (a:ECDATNode {id:$source}), (b:ECDATNode {id:$target})
        MERGE (a)-[r:ECDAT_REL {id:$id}]->(b)
        SET r.type = $type,
            r += $properties,
            r.updated_at = datetime()
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                source=edge.source_id,
                target=edge.target_id,
                id=edge.id,
                type=edge.edge_type.value,
                properties=edge.properties,
            )
            await result.consume()
        self._edge_ids.add(edge.id)

    async def snapshot(self) -> tuple[tuple[GraphNode, ...], tuple[GraphEdge, ...]]:
        if not self._node_ids:
            return (), ()
        async with self.driver.session() as session:
            node_result = await session.run(
                """
                MATCH (n:ECDATNode)
                WHERE n.id IN $ids
                RETURN n.id AS id, n.type AS type, n.label AS label,
                       properties(n) AS properties
                ORDER BY n.id
                """,
                ids=sorted(self._node_ids),
            )
            nodes: list[GraphNode] = []
            async for record in node_result:
                properties = dict(record["properties"] or {})
                for reserved in ("id", "type", "label", "updated_at"):
                    properties.pop(reserved, None)
                nodes.append(
                    GraphNode(
                        id=record["id"],
                        node_type=GraphNodeType(record["type"]),
                        label=record["label"],
                        properties=properties,
                    )
                )

            edge_result = await session.run(
                """
                MATCH (a:ECDATNode)-[r:ECDAT_REL]->(b:ECDATNode)
                WHERE r.id IN $ids
                RETURN r.id AS id, a.id AS source, b.id AS target,
                       r.type AS type, properties(r) AS properties
                ORDER BY r.id
                """,
                ids=sorted(self._edge_ids),
            )
            edges: list[GraphEdge] = []
            async for record in edge_result:
                properties = dict(record["properties"] or {})
                for reserved in ("id", "type", "updated_at"):
                    properties.pop(reserved, None)
                edges.append(
                    GraphEdge(
                        id=record["id"],
                        source_id=record["source"],
                        target_id=record["target"],
                        edge_type=GraphEdgeType(record["type"]),
                        properties=properties,
                    )
                )
        return tuple(nodes), tuple(edges)

    async def close(self) -> None:
        await self.driver.close()
