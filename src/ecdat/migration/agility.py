from __future__ import annotations

from collections import defaultdict

from ecdat.domain.enums import GraphEdgeType, GraphNodeType
from ecdat.domain.models import ScanSummary
from ecdat.migration.models import AgilityFactor, CryptoAgilityScore


class CryptoAgilityEngine:
    """Evidence-bounded crypto agility estimate.

    This intentionally scores only observable indicators. Missing architecture facts are
    represented by `coverage=partial` rather than silently assumed.
    """

    def score(self, summary: ScanSummary) -> tuple[CryptoAgilityScore, ...]:
        findings_by_service: dict[str, list] = defaultdict(list)
        dependencies: dict[str, set[str]] = defaultdict(set)
        node_by_id = {node.id: node for node in summary.graph_nodes}
        finding_by_asset = {f"asset:{finding.asset.id}": finding for finding in summary.findings}

        for edge in summary.graph_edges:
            if edge.edge_type is GraphEdgeType.USES and edge.source_id.startswith("service:") and edge.target_id in finding_by_asset:
                findings_by_service[edge.source_id].append(finding_by_asset[edge.target_id])
            if edge.edge_type in {GraphEdgeType.DEPENDS_ON, GraphEdgeType.CONNECTS_TO, GraphEdgeType.AUTHENTICATES_WITH}:
                if edge.source_id.startswith("service:") and edge.target_id.startswith("service:"):
                    dependencies[edge.source_id].add(edge.target_id)
                    dependencies[edge.target_id].add(edge.source_id)

        scores: list[CryptoAgilityScore] = []
        for node in summary.graph_nodes:
            if node.node_type not in {GraphNodeType.SERVICE, GraphNodeType.CONTAINER}:
                continue
            score = 82
            factors: list[AgilityFactor] = []
            findings = findings_by_service.get(node.id, [])
            dep_count = len(dependencies.get(node.id, set()))
            migration_time = float(node.properties.get("migration_time_years") or 0)

            if not findings:
                factors.append(AgilityFactor(code="no-observed-crypto", label="No owned crypto evidence", impact=-8, rationale="No crypto finding is directly owned by this service in the current scan; agility confidence is therefore limited."))
                score -= 8
            if len(findings) >= 4:
                factors.append(AgilityFactor(code="crypto-surface", label="Broad crypto surface", impact=-12, rationale=f"{len(findings)} distinct normalized crypto assets are owned by this service."))
                score -= 12
            elif findings:
                factors.append(AgilityFactor(code="bounded-surface", label="Bounded crypto surface", impact=5, rationale=f"Only {len(findings)} normalized crypto assets are directly owned in this scan."))
                score += 5

            hardcoded = any("hardcoded" in " ".join(f.tags).lower() or any("hardcoded" in e.method.lower() for e in f.evidence) for f in findings)
            if hardcoded:
                factors.append(AgilityFactor(code="hardcoded-crypto", label="Hardcoded crypto choice/material", impact=-25, rationale="Deterministic evidence indicates hardcoded cryptographic material or algorithm selection, increasing replacement effort."))
                score -= 25

            if migration_time >= 5:
                factors.append(AgilityFactor(code="long-migration", label="Long declared migration window", impact=-16, rationale=f"Enterprise context estimates {migration_time:g} years of migration effort."))
                score -= 16
            elif 0 < migration_time <= 3:
                factors.append(AgilityFactor(code="short-migration", label="Shorter declared migration window", impact=6, rationale=f"Enterprise context estimates {migration_time:g} years of migration effort."))
                score += 6

            if dep_count >= 4:
                factors.append(AgilityFactor(code="coupling", label="High service coupling", impact=-18, rationale=f"The service participates in {dep_count} service-level relationships."))
                score -= 18
            elif dep_count <= 1:
                factors.append(AgilityFactor(code="limited-coupling", label="Limited observed coupling", impact=5, rationale=f"Only {dep_count} service-level relationship is visible in the current context graph."))
                score += 5

            score = max(0, min(100, score))
            difficulty = "low" if score >= 76 else "moderate" if score >= 56 else "high" if score >= 31 else "critical"
            coverage = "good" if findings and migration_time > 0 else "partial"
            scores.append(CryptoAgilityScore(node_id=node.id, label=node.label, score=score, difficulty=difficulty, coverage=coverage, factors=tuple(factors)))
        return tuple(sorted(scores, key=lambda item: (item.score, item.label)))
