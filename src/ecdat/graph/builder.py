from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ecdat.domain.enums import GraphEdgeType, GraphNodeType
from ecdat.domain.models import Finding, GraphEdge, GraphNode, RiskContext, ScanTarget
from ecdat.graph.context import EnterpriseContextManifest, ServiceContext, load_context_manifest
from ecdat.graph.ontology import asset_node, target_node


@dataclass(frozen=True, slots=True)
class GraphBuildResult:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    asset_contexts: dict[UUID, RiskContext]
    manifest_loaded: bool


def _edge(source: str, target: str, edge_type: GraphEdgeType, **properties: object) -> GraphEdge:
    return GraphEdge(
        id=f"{edge_type.value}:{source}:{target}",
        source_id=source,
        target_id=target,
        edge_type=edge_type,
        properties=dict(properties),
    )


def _service_node_id(service_id: str) -> str:
    return f"service:{service_id}"


def _data_node_id(data_id: str) -> str:
    return f"data:{data_id}"


class EnterpriseGraphBuilder:
    """Builds an evidence-linked enterprise graph without inventing topology.

    Discovered assets always originate from scanner findings. Business/service topology
    is added only when an explicit `ecdat.context.json` is present in the scan target.
    """

    def build(
        self,
        target: ScanTarget,
        findings: tuple[Finding, ...],
        fallback_context: RiskContext,
    ) -> GraphBuildResult:
        manifest = load_context_manifest(target.locator)
        root = target_node(target)
        nodes: dict[str, GraphNode] = {root.id: root}
        edges: dict[str, GraphEdge] = {}
        contexts: dict[UUID, RiskContext] = {}

        if manifest is not None:
            self._add_manifest_graph(manifest, root.id, nodes, edges)

        for finding in findings:
            crypto = asset_node(finding.asset)
            nodes[crypto.id] = crypto

            owners = self._owners_for_finding(manifest, finding)
            if owners:
                service_contexts: list[RiskContext] = []
                for service in owners:
                    owner_id = _service_node_id(service.id)
                    relation = _edge(owner_id, crypto.id, GraphEdgeType.USES, evidence_count=len(finding.evidence))
                    edges[relation.id] = relation
                    service_contexts.append(manifest.risk_context_for_service(service, fallback_context))
                contexts[finding.asset.id] = self._merge_contexts(service_contexts, fallback_context)
            else:
                relation = _edge(root.id, crypto.id, GraphEdgeType.USES, evidence_count=len(finding.evidence))
                edges[relation.id] = relation
                contexts[finding.asset.id] = fallback_context

        return GraphBuildResult(
            nodes=tuple(nodes.values()),
            edges=tuple(edges.values()),
            asset_contexts=contexts,
            manifest_loaded=manifest is not None,
        )

    def _add_manifest_graph(
        self,
        manifest: EnterpriseContextManifest,
        root_id: str,
        nodes: dict[str, GraphNode],
        edges: dict[str, GraphEdge],
    ) -> None:
        data_by_id = {item.id: item for item in manifest.data_classes}
        for data_class in manifest.data_classes:
            node = GraphNode(
                id=_data_node_id(data_class.id),
                node_type=GraphNodeType.DATA_CLASS,
                label=data_class.name,
                properties={
                    "sensitivity": data_class.sensitivity,
                    "lifetime_years": data_class.lifetime_years,
                },
            )
            nodes[node.id] = node

        for service in manifest.services:
            node_type = GraphNodeType.CONTAINER if service.kind == "container" else GraphNodeType.SERVICE
            node = GraphNode(
                id=_service_node_id(service.id),
                node_type=node_type,
                label=service.name,
                properties={
                    "business_criticality": service.business_criticality,
                    "public_exposure": service.public_exposure,
                    "migration_time_years": service.migration_time_years,
                },
            )
            nodes[node.id] = node
            contains = _edge(root_id, node.id, GraphEdgeType.CONTAINS)
            edges[contains.id] = contains
            for data_id in service.protects:
                if data_id not in data_by_id:
                    continue
                protects = _edge(node.id, _data_node_id(data_id), GraphEdgeType.PROTECTS)
                edges[protects.id] = protects

        edge_map = {
            "depends_on": GraphEdgeType.DEPENDS_ON,
            "connects_to": GraphEdgeType.CONNECTS_TO,
            "authenticates_with": GraphEdgeType.AUTHENTICATES_WITH,
        }
        known_services = {item.id for item in manifest.services}
        for relationship in manifest.relationships:
            if relationship.source not in known_services or relationship.target not in known_services:
                continue
            edge_type = edge_map.get(relationship.type, GraphEdgeType.DEPENDS_ON)
            relation = _edge(
                _service_node_id(relationship.source),
                _service_node_id(relationship.target),
                edge_type,
            )
            edges[relation.id] = relation

    def _owners_for_finding(
        self,
        manifest: EnterpriseContextManifest | None,
        finding: Finding,
    ) -> tuple[ServiceContext, ...]:
        if manifest is None:
            return ()
        owners = []
        seen: set[str] = set()
        for evidence in finding.evidence:
            service = manifest.service_for_path(evidence.location.path)
            if service is not None and service.id not in seen:
                owners.append(service)
                seen.add(service.id)
        return tuple(owners)

    def _merge_contexts(self, contexts: list[RiskContext], fallback: RiskContext) -> RiskContext:
        if not contexts:
            return fallback
        sensitivity_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3, "restricted": 4}
        criticality_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        return fallback.model_copy(
            update={
                "data_lifetime_years": max(
                    (item.data_lifetime_years or 0 for item in contexts),
                    default=fallback.data_lifetime_years,
                ),
                "migration_time_years": max(
                    (item.migration_time_years or 0 for item in contexts),
                    default=fallback.migration_time_years,
                ),
                "data_sensitivity": max(
                    (item.data_sensitivity or "medium" for item in contexts),
                    key=lambda value: sensitivity_rank.get(value.lower(), 1),
                ),
                "business_criticality": max(
                    (item.business_criticality or "medium" for item in contexts),
                    key=lambda value: criticality_rank.get(value.lower(), 1),
                ),
                "public_exposure": any(item.public_exposure is True for item in contexts),
                "confidentiality_required": any(item.confidentiality_required is True for item in contexts),
            }
        )
