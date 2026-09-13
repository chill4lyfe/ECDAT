from __future__ import annotations

import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from ecdat.api.catalog import catalog
from ecdat.auth.security import Principal, require_authenticated
from ecdat.domain.enums import GraphEdgeType
from ecdat.migration.catalog import migration_catalog
from ecdat.migration.models import MigrationConstraints
from ecdat.migration.planner import MigrationPlanner

router = APIRouter(prefix="/reports", tags=["reports"])


class ExecutiveReport(BaseModel):
    scan_id: UUID
    title: str
    posture: str
    headline: str
    scope: dict[str, object]
    metrics: dict[str, int]
    coverage: dict[str, object]
    priority_findings: list[dict[str, object]]
    management_summary: list[str]
    technical_observations: list[str]
    migration: dict[str, object]
    assumptions: dict[str, object]
    limitations: list[str]


def _report(scan_id: UUID, organization_id: UUID | None = None) -> ExecutiveReport:
    summary = catalog.get(scan_id, organization_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    q = summary.quantum_summary
    ordered = sorted(summary.risk_assessments, key=lambda item: item.score or 0, reverse=True)
    finding_by_asset = {item.asset.id: item for item in summary.findings}

    plan = migration_catalog.latest(organization_id, scan_id)
    if plan is None or plan.scan_id != summary.scan_id:
        # Reporting reads must not create a migration-plan revision. Build an
        # ephemeral default view when the organization has not saved a plan yet.
        plan = MigrationPlanner().build(summary, MigrationConstraints())
    recommendation_by_asset = {item.asset_id: item for item in plan.recommendations}

    services_by_asset: dict[str, list[str]] = {}
    node_labels = {item.id: item.label for item in summary.graph_nodes}
    for edge in summary.graph_edges:
        if edge.edge_type is GraphEdgeType.USES and edge.source_id.startswith("service:") and edge.target_id.startswith("asset:"):
            services_by_asset.setdefault(edge.target_id.removeprefix("asset:"), []).append(node_labels.get(edge.source_id, edge.source_id.removeprefix("service:")))

    priorities: list[dict[str, object]] = []
    for risk in ordered[:10]:
        finding = finding_by_asset.get(risk.asset_id)
        if finding is None:
            continue
        recommendation = recommendation_by_asset.get(risk.asset_id)
        evidence_locations = []
        for item in finding.evidence[:5]:
            location = item.location.path or item.location.uri
            if item.location.line_start:
                location = f"{location}:{item.location.line_start}"
            evidence_locations.append(location)
        priorities.append({
            "asset_id": str(finding.asset.id),
            "asset": finding.asset.canonical_name,
            "type": finding.asset.asset_type.value,
            "priority": risk.priority.value,
            "score": risk.score,
            "quantum_posture": risk.quantum_posture.value,
            "hndl": risk.hndl_exposure,
            "evidence": len(finding.evidence),
            "evidence_locations": evidence_locations,
            "affected_services": sorted(set(services_by_asset.get(str(finding.asset.id), []))),
            "reason": risk.rationale[0] if risk.rationale else "No rationale available",
            "recommended_action": recommendation.strategy.replace("_", " ") if recommendation else "review context",
            "target_profiles": [item.name for item in recommendation.target_profiles] if recommendation else [],
        })

    critical = q.critical_assets if q else 0
    hndl = q.hndl_exposed_assets if q else 0
    vulnerable = q.vulnerable_assets if q else 0
    posture = "critical" if critical else "elevated" if vulnerable else "observed"
    headline = (
        f"{vulnerable} quantum-vulnerable assets were identified. {hndl} currently meet the modeled HNDL condition, "
        f"and {q.migration_blockers if q else 0} graph-central dependencies affect migration sequencing."
    )
    assumptions: dict[str, object] = dict(ordered[0].assumptions) if ordered else {}
    metadata = summary.target.metadata
    coverage = summary.coverage

    management_summary = [
        f"Prioritize {critical} critical cryptographic asset(s) before lower-impact modernization work." if critical else "No cryptographic asset currently crosses the critical prioritization threshold under the stored assumptions.",
        f"Treat {hndl} HNDL-exposed asset(s) as confidentiality-timeline decisions, not merely future technology upgrades." if hndl else "No current finding meets the HNDL condition under the stored horizon and exposure assumptions.",
        f"Sequence migration across {len(plan.waves)} dependency-aware wave(s); shared blockers should be remediated before dependent services.",
    ]
    technical_observations = [
        f"{len(summary.findings)} normalized crypto assets are backed by {coverage.evidence_records if coverage else sum(len(item.evidence) for item in summary.findings)} evidence records.",
        f"The weakest observed migration readiness score is {plan.summary.lowest_agility_score if plan.summary.lowest_agility_score is not None else 'unavailable'}/100; higher readiness is better.",
        f"The current roadmap contains {plan.summary.total_actions} actions, with {plan.summary.actions_within_window} inside the selected execution window.",
    ]
    limitations = list(coverage.limitations if coverage else ()) + [
        "Binary cryptography detection is heuristic and does not prove runtime execution.",
        "Quantum-risk horizon is operator-configured scenario input, not a predicted CRQC date.",
        "Migration recommendations require organization-specific interoperability, performance, PKI and operational validation before production rollout.",
        "Static artifact analysis may not observe managed KMS/HSM usage, remote cryptographic services, runtime feature flags or dynamically loaded implementations.",
    ]
    limitations = list(dict.fromkeys(limitations))

    return ExecutiveReport(
        scan_id=summary.scan_id,
        title=summary.target.display_name or "ECDAT Cryptographic Estate Assessment",
        posture=posture,
        headline=headline,
        scope={
            "environment": metadata.get("environment", "Unspecified"),
            "owner": metadata.get("owner", "Unassigned"),
            "team": metadata.get("team", "Unassigned"),
            "source": metadata.get("source", summary.target.kind),
            "target_kind": summary.target.kind,
            "context_manifest": "linked" if summary.context_manifest_loaded else "artifact-only",
        },
        metrics={
            "crypto_assets": len(summary.findings),
            "quantum_vulnerable": vulnerable,
            "hndl_exposed": hndl,
            "critical": critical,
            "migration_blockers": q.migration_blockers if q else 0,
            "migration_waves": len(plan.waves),
            "migration_actions": plan.summary.total_actions,
        },
        coverage={
            "files_observed": coverage.files_observed if coverage else 0,
            "source_files": coverage.source_files if coverage else 0,
            "config_files": coverage.config_files if coverage else 0,
            "dependency_manifests": coverage.dependency_manifests if coverage else 0,
            "certificate_files": coverage.certificate_files if coverage else 0,
            "binary_files": coverage.binary_files if coverage else 0,
            "container_definitions": coverage.container_definitions if coverage else 0,
            "scanners_completed": coverage.scanners_completed if coverage else len(summary.scanner_executions),
            "scanners_failed": coverage.scanners_failed if coverage else 0,
            "evidence_records": coverage.evidence_records if coverage else sum(len(item.evidence) for item in summary.findings),
            "average_confidence": coverage.confidence_average if coverage else None,
            "observations": list(coverage.observations if coverage else ()),
        },
        priority_findings=priorities,
        management_summary=management_summary,
        technical_observations=technical_observations,
        migration={
            "waves": len(plan.waves),
            "actions": plan.summary.total_actions,
            "effort_points": plan.summary.total_effort_points,
            "lowest_readiness": plan.summary.lowest_agility_score,
            "estimated_calendar_weeks": plan.summary.estimated_calendar_weeks,
            "actions_within_window": plan.summary.actions_within_window,
            "deferred_actions": plan.summary.deferred_actions,
            "critical_path": list(plan.critical_path),
            "strategy_explanation": list(plan.strategy_explanation),
            "standards_basis": list(plan.standards_snapshot),
            "risk_scenario_horizon_years": plan.risk_scenario_horizon_years or assumptions.get("quantum_horizon_years"),
        },
        assumptions=assumptions,
        limitations=limitations,
    )


@router.get("/scans/{scan_id}/executive", response_model=ExecutiveReport)
async def executive_report(scan_id: UUID, principal: Principal = Depends(require_authenticated)) -> ExecutiveReport:
    return _report(scan_id, principal.organization_id)


@router.get("/scans/{scan_id}/executive.md")
async def executive_markdown(scan_id: UUID, principal: Principal = Depends(require_authenticated)) -> PlainTextResponse:
    report = _report(scan_id, principal.organization_id)
    lines = [
        f"# {report.title}", "", f"**Overall posture:** {report.posture.upper()}", "", report.headline, "",
        "## Assessment scope",
    ]
    lines.extend(f"- **{key.replace('_', ' ').title()}:** {value}" for key, value in report.scope.items())
    lines.extend(["", "## Executive metrics"])
    lines.extend(f"- **{key.replace('_', ' ').title()}:** {value}" for key, value in report.metrics.items())
    lines.extend(["", "## Management interpretation"])
    lines.extend(f"- {item}" for item in report.management_summary)
    lines.extend(["", "## Priority cryptographic findings"])
    for item in report.priority_findings:
        lines.extend([
            f"### {item['asset']} — {str(item['priority']).upper()} ({item['score']}/100)",
            f"- Quantum posture: {str(item['quantum_posture']).replace('_', ' ')}",
            f"- HNDL exposure: {'Yes' if item['hndl'] else 'No'}",
            f"- Affected services: {', '.join(item['affected_services']) or 'No explicit service ownership in supplied context'}",
            f"- Evidence: {', '.join(item['evidence_locations']) or 'No printable source location'}",
            f"- Why it matters: {item['reason']}",
            f"- Recommended action: {item['recommended_action']}",
            f"- Candidate target(s): {', '.join(item['target_profiles']) or 'Resolve implementation context first'}",
            "",
        ])
    lines.extend(["## Migration program", f"- Planning quantum-risk horizon (Z): {report.migration.get('risk_scenario_horizon_years', 'unavailable')} years", f"- Waves: {report.migration['waves']}", f"- Actions: {report.migration['actions']}", f"- Relative effort points: {report.migration['effort_points']}", f"- Estimated planning duration: {report.migration['estimated_calendar_weeks']} weeks", f"- Actions inside current change window: {report.migration['actions_within_window']}"])
    lines.extend(["", "## Analysis coverage"])
    lines.extend(f"- **{key.replace('_', ' ').title()}:** {value}" for key, value in report.coverage.items() if key != "observations")
    lines.extend(str(item) for item in report.coverage.get("observations", []))
    lines.extend(["", "## Assumptions"])
    lines.extend(f"- **{key.replace('_', ' ').title()}:** {value}" for key, value in report.assumptions.items())
    lines.extend(["", "## Known limitations and uncertainty"])
    lines.extend(f"- {item}" for item in report.limitations)
    lines.extend(["", "---", "Generated from evidence retained by ECDAT. Risk scores are prioritization indices, not breach probabilities or CRQC forecasts."])
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="ecdat-{scan_id}-decision-report.md"'},
    )


@router.get("/scans/{scan_id}/findings.csv")
async def findings_csv(scan_id: UUID, principal: Principal = Depends(require_authenticated)) -> StreamingResponse:
    summary = catalog.get(scan_id, principal.organization_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    risks = {item.asset_id: item for item in summary.risk_assessments}
    node_labels = {item.id: item.label for item in summary.graph_nodes}
    owners: dict[str, list[str]] = {}
    for edge in summary.graph_edges:
        if edge.edge_type is GraphEdgeType.USES and edge.source_id.startswith("service:") and edge.target_id.startswith("asset:"):
            owners.setdefault(edge.target_id.removeprefix("asset:"), []).append(node_labels.get(edge.source_id, edge.source_id))
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["asset_id", "asset", "type", "version", "key_size_bits", "scanner", "confidence", "risk", "risk_score", "quantum_posture", "hndl", "affected_services", "evidence_count", "evidence_locations"])
    for finding in summary.findings:
        risk = risks.get(finding.asset.id)
        locations = []
        for evidence in finding.evidence:
            value = evidence.location.path or evidence.location.uri
            if evidence.location.line_start:
                value = f"{value}:{evidence.location.line_start}"
            locations.append(value)
        writer.writerow([
            finding.asset.id, finding.asset.canonical_name, finding.asset.asset_type.value, finding.asset.version or "", finding.asset.key_size_bits or "", finding.scanner_id,
            f"{finding.confidence.score:.2f}", risk.priority.value if risk else "unknown", risk.score if risk and risk.score is not None else "", risk.quantum_posture.value if risk else "unknown",
            risk.hndl_exposure if risk else False, "; ".join(sorted(set(owners.get(str(finding.asset.id), [])))), len(finding.evidence), "; ".join(locations),
        ])
    payload = io.BytesIO(buffer.getvalue().encode("utf-8"))
    return StreamingResponse(payload, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="ecdat-{scan_id}-findings.csv"'})
