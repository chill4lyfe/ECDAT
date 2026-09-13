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
        findings_by_context: dict[str, list] = defaultdict(list)
        dependencies: dict[str, set[str]] = defaultdict(set)
        node_by_id = {node.id: node for node in summary.graph_nodes}
        finding_by_asset = {f"asset:{finding.asset.id}": finding for finding in summary.findings}
        readiness_types = {GraphNodeType.SERVICE, GraphNodeType.CONTAINER, GraphNodeType.REPOSITORY, GraphNodeType.APPLICATION}

        for edge in summary.graph_edges:
            owner = node_by_id.get(edge.source_id)
            if edge.edge_type is GraphEdgeType.USES and owner and owner.node_type in readiness_types and edge.target_id in finding_by_asset:
                findings_by_context[edge.source_id].append(finding_by_asset[edge.target_id])
            if edge.edge_type in {GraphEdgeType.DEPENDS_ON, GraphEdgeType.CONNECTS_TO, GraphEdgeType.AUTHENTICATES_WITH}:
                if edge.source_id.startswith("service:") and edge.target_id.startswith("service:"):
                    dependencies[edge.source_id].add(edge.target_id)
                    dependencies[edge.target_id].add(edge.source_id)

        scores: list[CryptoAgilityScore] = []
        for node in summary.graph_nodes:
            if node.node_type not in readiness_types:
                continue
            if node.id.startswith("target:") and isinstance(summary.target.metadata.get("sources"), list):
                # In a combined assessment the root is only an assessment container;
                # readiness belongs to the owned repository/container source contexts.
                continue
            # Do not invent readiness records for unrelated graph nodes. Supplied
            # repository/container contexts are included only when they own evidence.
            findings = findings_by_context.get(node.id, [])
            source_context = node.properties.get("provenance") == "supplied_source"
            if source_context and not findings:
                continue
            score = 82
            factors: list[AgilityFactor] = []
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

            if source_context:
                # Missing enterprise topology reduces confidence, not the observable technical
                # readiness itself.  Keep it explicit as a zero-impact factor and differentiate
                # source contexts using evidence we can actually prove.
                factors.append(AgilityFactor(
                    code="source-context-only",
                    label="Business topology not supplied",
                    impact=0,
                    rationale="This is a technical-evidence readiness estimate for the supplied source. Service dependencies, business criticality and organization-specific migration lead time remain unknown.",
                ))
                detectors = {evidence.detector for finding in findings for evidence in finding.evidence}
                evidence_records = [evidence for finding in findings for evidence in finding.evidence]
                if len(detectors) >= 3:
                    factors.append(AgilityFactor(
                        code="evidence-diversity",
                        label="Multi-detector evidence coverage",
                        impact=6,
                        rationale=f"{len(detectors)} independent detector families contribute evidence for this source context, improving confidence in the technical inventory.",
                    ))
                    score += 6
                elif len(detectors) == 2:
                    factors.append(AgilityFactor(
                        code="evidence-diversity",
                        label="Cross-checked evidence",
                        impact=3,
                        rationale="Two detector families contribute evidence for this source context.",
                    ))
                    score += 3

                opaque_binary = any(
                    bool(evidence.attributes.get("likely_stripped")) or bool(evidence.attributes.get("opaque_or_packed_signal"))
                    for evidence in evidence_records
                )
                if opaque_binary:
                    factors.append(AgilityFactor(
                        code="opaque-binary",
                        label="Opaque binary dependency",
                        impact=-12,
                        rationale="Binary evidence is stripped, packed, or otherwise opaque enough that replacement effort cannot be fully verified from supplied artifacts.",
                    ))
                    score -= 12

                legacy_names = {"MD5", "SHA-1", "SHA1", "DES", "3DES", "RC4"}
                legacy_count = sum(1 for finding in findings if finding.asset.canonical_name.upper() in legacy_names)
                if legacy_count:
                    factors.append(AgilityFactor(
                        code="legacy-crypto-pressure",
                        label="Legacy cryptography requires cleanup",
                        impact=-10,
                        rationale=f"{legacy_count} normalized legacy cryptographic asset(s) require classical remediation before or alongside post-quantum transition work.",
                    ))
                    score -= 10

                pqc_count = sum(1 for finding in findings if finding.asset.canonical_name.upper().startswith(("ML-KEM", "ML-DSA", "SLH-DSA")))
                if pqc_count:
                    factors.append(AgilityFactor(
                        code="pqc-present",
                        label="Standardized PQC already present",
                        impact=5,
                        rationale=f"{pqc_count} standardized post-quantum primitive(s) are already visible in this supplied source context.",
                    ))
                    score += 5
            elif dep_count >= 4:
                factors.append(AgilityFactor(code="coupling", label="High service coupling", impact=-18, rationale=f"The service participates in {dep_count} service-level relationships."))
                score -= 18
            elif dep_count <= 1:
                factors.append(AgilityFactor(code="limited-coupling", label="Limited observed coupling", impact=5, rationale=f"Only {dep_count} service-level relationship is visible in the current context graph."))
                score += 5

            score = max(0, min(100, score))
            difficulty = "low" if score >= 76 else "moderate" if score >= 56 else "high" if score >= 31 else "critical"
            coverage = "good" if findings and migration_time > 0 and not source_context else "partial"
            basis = "technical_evidence" if source_context else "enterprise_context"
            scores.append(CryptoAgilityScore(node_id=node.id, label=node.label, score=score, difficulty=difficulty, coverage=coverage, basis=basis, factors=tuple(factors)))
        return tuple(sorted(scores, key=lambda item: (item.score, item.label)))
