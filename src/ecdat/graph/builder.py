from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
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


def _source_node_id(source_id: str) -> str:
    return f"source:{source_id}"


def _source_node_type(kind: str) -> GraphNodeType:
    return {
        "repository": GraphNodeType.REPOSITORY,
        "container_image": GraphNodeType.CONTAINER,
        "bom": GraphNodeType.INFRASTRUCTURE,
        "connector": GraphNodeType.INFRASTRUCTURE,
    }.get(kind, GraphNodeType.INFRASTRUCTURE)


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

        sources = self._add_supplied_sources(target, root.id, nodes, edges)
        component_by_path = self._add_technical_components(
            root.id, findings, sources, nodes, edges
        )

        for finding in findings:
            crypto = asset_node(finding.asset)
            nodes[crypto.id] = crypto

            supplied_sources = self._sources_for_finding(sources, finding)
            for source in supplied_sources:
                relation = _edge(
                    _source_node_id(str(source["id"])), crypto.id, GraphEdgeType.USES,
                    evidence_count=sum(1 for evidence in finding.evidence if self._evidence_matches_source(source, evidence.location.path)),
                    provenance="supplied_source",
                    source_kind=str(source.get("kind", "artifact")),
                )
                edges[relation.id] = relation

            component_counts = Counter(
                component_by_path[evidence.location.path]
                for evidence in finding.evidence
                if evidence.location.path in component_by_path
            )
            for component_id, evidence_count in component_counts.items():
                relation = _edge(
                    component_id, crypto.id, GraphEdgeType.USES,
                    evidence_count=evidence_count,
                    provenance="observed_evidence",
                    technical_context=True,
                )
                edges[relation.id] = relation

            owners = self._owners_for_finding(manifest, finding)
            if owners:
                service_contexts: list[RiskContext] = []
                for service in owners:
                    owner_id = _service_node_id(service.id)
                    relation = _edge(
                        owner_id, crypto.id, GraphEdgeType.USES,
                        evidence_count=len(finding.evidence),
                        provenance="connector" if any(e.attributes.get("provenance") == "enterprise_connector_export" for e in finding.evidence) else "observed_evidence",
                        detector=finding.scanner_id,
                    )
                    edges[relation.id] = relation
                    service_contexts.append(manifest.risk_context_for_service(service, fallback_context))
                contexts[finding.asset.id] = self._merge_contexts(service_contexts, fallback_context)
            else:
                if not supplied_sources:
                    relation = _edge(
                        root.id, crypto.id, GraphEdgeType.USES,
                        evidence_count=len(finding.evidence),
                        provenance="connector" if any(e.attributes.get("provenance") == "enterprise_connector_export" for e in finding.evidence) else "observed_evidence",
                        detector=finding.scanner_id,
                    )
                    edges[relation.id] = relation
                contexts[finding.asset.id] = fallback_context

        return GraphBuildResult(
            nodes=tuple(nodes.values()),
            edges=tuple(edges.values()),
            asset_contexts=contexts,
            manifest_loaded=manifest is not None,
        )

    def _add_technical_components(
        self,
        root_id: str,
        findings: tuple[Finding, ...],
        sources: tuple[dict[str, object], ...],
        nodes: dict[str, GraphNode],
        edges: dict[str, GraphEdge],
    ) -> dict[str, str]:
        """Add evidence-derived source/module buckets without claiming business topology."""

        records: list[tuple[str, str, tuple[str, ...]]] = []
        by_owner_dirs: dict[str, list[tuple[str, ...]]] = {}
        for finding in findings:
            for evidence in finding.evidence:
                path = evidence.location.path
                if not path:
                    continue
                source = next((item for item in sources if self._evidence_matches_source(item, path)), None)
                owner_id = _source_node_id(str(source["id"])) if source else root_id
                rel = path
                if source is not None:
                    prefix = str(source.get("path_prefix") or "").rstrip("/")
                    if prefix and (path == prefix or path.startswith(prefix + "/")):
                        rel = path[len(prefix):].lstrip("/")
                parts = tuple(part for part in rel.replace("\\", "/").split("/") if part)
                dirs = parts[:-1] if len(parts) > 1 else ()
                records.append((path, owner_id, dirs))
                by_owner_dirs.setdefault(owner_id, []).append(dirs)

        def common_prefix(values: list[tuple[str, ...]]) -> tuple[str, ...]:
            if not values:
                return ()
            prefix = list(values[0])
            for value in values[1:]:
                limit = min(len(prefix), len(value))
                index = 0
                while index < limit and prefix[index] == value[index]:
                    index += 1
                prefix = prefix[:index]
                if not prefix:
                    break
            return tuple(prefix)

        common_by_owner = {owner: common_prefix(values) for owner, values in by_owner_dirs.items()}
        component_by_path: dict[str, str] = {}
        for path, owner_id, dirs in records:
            common = common_by_owner.get(owner_id, ())
            remainder = dirs[len(common):] if dirs[:len(common)] == common else dirs
            if not remainder:
                continue
            component_name = remainder[0]
            component_prefix = "/".join((*common, component_name))
            digest = hashlib.sha256(f"{owner_id}|{component_prefix}".encode("utf-8")).hexdigest()[:18]
            component_id = f"component:{digest}"
            if component_id not in nodes:
                nodes[component_id] = GraphNode(
                    id=component_id,
                    node_type=GraphNodeType.INFRASTRUCTURE,
                    label=component_name,
                    properties={
                        "technical_component": True,
                        "path_prefix": component_prefix,
                        "provenance": "observed_evidence",
                        "business_topology": False,
                    },
                )
                relation = _edge(
                    owner_id, component_id, GraphEdgeType.CONTAINS,
                    provenance="observed_evidence",
                    technical_context=True,
                )
                edges[relation.id] = relation
            component_by_path[path] = component_id
        return component_by_path

    def _add_supplied_sources(
        self,
        target: ScanTarget,
        root_id: str,
        nodes: dict[str, GraphNode],
        edges: dict[str, GraphEdge],
    ) -> tuple[dict[str, object], ...]:
        raw_sources = target.metadata.get("sources")
        if not isinstance(raw_sources, list):
            return ()
        sources: list[dict[str, object]] = []
        for item in raw_sources:
            if not isinstance(item, dict) or not item.get("id") or not item.get("path_prefix"):
                continue
            source = dict(item)
            source_id = str(source["id"])
            kind = str(source.get("kind", "artifact"))
            node = GraphNode(
                id=_source_node_id(source_id),
                node_type=_source_node_type(kind),
                label=str(source.get("display_name") or source.get("filename") or source_id),
                properties={
                    "source_kind": kind,
                    "filename": source.get("filename"),
                    "path_prefix": source.get("path_prefix"),
                    "provenance": "supplied_source",
                },
            )
            nodes[node.id] = node
            relation = _edge(root_id, node.id, GraphEdgeType.CONTAINS, provenance="supplied_source")
            edges[relation.id] = relation
            sources.append(source)
        return tuple(sources)

    @staticmethod
    def _evidence_matches_source(source: dict[str, object], evidence_path: str | None) -> bool:
        if not evidence_path:
            return False
        prefix = str(source.get("path_prefix") or "").rstrip("/")
        return bool(prefix) and (evidence_path == prefix or evidence_path.startswith(prefix + "/") or evidence_path.startswith(prefix + "!"))

    def _sources_for_finding(self, sources: tuple[dict[str, object], ...], finding: Finding) -> tuple[dict[str, object], ...]:
        matches: list[dict[str, object]] = []
        for source in sources:
            if any(self._evidence_matches_source(source, evidence.location.path) for evidence in finding.evidence):
                matches.append(source)
        return tuple(matches)

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
            contains = _edge(root_id, node.id, GraphEdgeType.CONTAINS, provenance="declared_context")
            edges[contains.id] = contains
            for data_id in service.protects:
                if data_id not in data_by_id:
                    continue
                protects = _edge(node.id, _data_node_id(data_id), GraphEdgeType.PROTECTS, provenance="declared_context")
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
                provenance="declared_context",
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
        services_by_id = {service.id: service for service in manifest.services}
        for evidence in finding.evidence:
            declared_service_id = evidence.attributes.get("service_id")
            if isinstance(declared_service_id, str) and declared_service_id in services_by_id:
                service = services_by_id[declared_service_id]
                if service.id not in seen:
                    owners.append(service)
                    seen.add(service.id)
                continue
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
