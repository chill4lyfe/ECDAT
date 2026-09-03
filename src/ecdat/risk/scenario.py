from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ecdat.domain.enums import QuantumPosture, RiskPriority
from ecdat.domain.models import QuantumRiskSummary, RiskAssessment, RiskContext, ScanSummary
from ecdat.risk.quantum import QuantumRiskEngine


class ScenarioModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ScenarioAssetDelta(ScenarioModel):
    asset_id: UUID
    asset_name: str
    before_score: int
    after_score: int
    score_delta: int
    before_priority: RiskPriority
    after_priority: RiskPriority
    before_hndl: bool
    after_hndl: bool
    before_mosca_margin_years: float | None = None
    after_mosca_margin_years: float | None = None


class ScenarioNarrative(ScenarioModel):
    headline: str
    interpretation: str
    material_changes: tuple[str, ...]
    unchanged_explanation: str | None = None


class RiskScenarioResult(ScenarioModel):
    scan_id: UUID
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    baseline_horizon_years: float | None
    scenario_horizon_years: float
    assessments: tuple[RiskAssessment, ...]
    quantum_summary: QuantumRiskSummary
    deltas: tuple[ScenarioAssetDelta, ...]
    changed_assets: int
    priority_increases: int
    priority_decreases: int
    hndl_added: int
    hndl_removed: int
    narrative: ScenarioNarrative


def _context_from_assessment(risk: RiskAssessment, horizon: float) -> RiskContext:
    a = risk.assumptions
    return RiskContext(
        data_lifetime_years=a.get("data_lifetime_years"),
        migration_time_years=a.get("migration_time_years"),
        quantum_horizon_years=horizon,
        data_sensitivity=a.get("data_sensitivity"),
        business_criticality=a.get("business_criticality"),
        public_exposure=a.get("public_exposure"),
        confidentiality_required=a.get("confidentiality_required"),
    )


def evaluate_scenario(summary: ScanSummary, horizon_years: float) -> RiskScenarioResult:
    engine = QuantumRiskEngine()
    baseline_by_asset = {item.asset_id: item for item in summary.risk_assessments}
    findings = {item.asset.id: item for item in summary.findings}
    assessments: list[RiskAssessment] = []
    deltas: list[ScenarioAssetDelta] = []

    priority_rank = {
        RiskPriority.UNKNOWN: 0,
        RiskPriority.LOW: 1,
        RiskPriority.MODERATE: 2,
        RiskPriority.ELEVATED: 3,
        RiskPriority.CRITICAL: 4,
    }

    for asset_id, finding in findings.items():
        before = baseline_by_asset.get(asset_id)
        if before is None:
            continue
        after = engine.assess(finding.asset, _context_from_assessment(before, horizon_years))
        assessments.append(after)
        before_score = before.score or 0
        after_score = after.score or 0
        if (
            before_score != after_score
            or before.priority is not after.priority
            or before.hndl_exposure != after.hndl_exposure
            or before.mosca_margin_years != after.mosca_margin_years
        ):
            deltas.append(ScenarioAssetDelta(
                asset_id=asset_id,
                asset_name=finding.asset.canonical_name,
                before_score=before_score,
                after_score=after_score,
                score_delta=after_score - before_score,
                before_priority=before.priority,
                after_priority=after.priority,
                before_hndl=before.hndl_exposure,
                after_hndl=after.hndl_exposure,
                before_mosca_margin_years=before.mosca_margin_years,
                after_mosca_margin_years=after.mosca_margin_years,
            ))

    assessments_tuple = tuple(assessments)
    blockers = summary.quantum_summary.migration_blockers if summary.quantum_summary else sum(item.migration_blocker for item in summary.graph_insights)
    q = QuantumRiskSummary(
        vulnerable_assets=sum(item.quantum_posture is QuantumPosture.VULNERABLE for item in assessments_tuple),
        hndl_exposed_assets=sum(item.hndl_exposure for item in assessments_tuple),
        critical_assets=sum(item.priority is RiskPriority.CRITICAL for item in assessments_tuple),
        elevated_assets=sum(item.priority is RiskPriority.ELEVATED for item in assessments_tuple),
        migration_blockers=blockers,
    )

    increases = sum(priority_rank[item.after_priority] > priority_rank[item.before_priority] for item in deltas)
    decreases = sum(priority_rank[item.after_priority] < priority_rank[item.before_priority] for item in deltas)
    hndl_added = sum(not item.before_hndl and item.after_hndl for item in deltas)
    hndl_removed = sum(item.before_hndl and not item.after_hndl for item in deltas)
    baseline_horizon = next((item.assumptions.get("quantum_horizon_years") for item in summary.risk_assessments if item.assumptions.get("quantum_horizon_years") is not None), None)

    material: list[str] = []
    for item in sorted(deltas, key=lambda d: abs(d.score_delta), reverse=True)[:6]:
        direction = "increased" if item.score_delta > 0 else "decreased"
        text = f"{item.asset_name}: priority score {direction} from {item.before_score} to {item.after_score}"
        if item.before_priority is not item.after_priority:
            text += f" ({item.before_priority.value} → {item.after_priority.value})"
        if item.before_hndl != item.after_hndl:
            text += "; HNDL exposure entered the scenario" if item.after_hndl else "; HNDL exposure no longer applies under this horizon"
        material.append(text + ".")

    if baseline_horizon is None:
        baseline_text = "the stored assessment did not contain a common horizon"
    else:
        baseline_text = f"the stored {float(baseline_horizon):g}-year horizon"
    if deltas:
        headline = f"{len(deltas)} assets change under a {horizon_years:g}-year quantum-risk horizon."
        interpretation = (
            f"Compared with {baseline_text}, the scenario produces {increases} priority increase(s), {decreases} decrease(s), "
            f"{hndl_added} new HNDL exposure(s) and {hndl_removed} removed HNDL exposure(s). "
            "Only the planning assumption changed; the underlying discovery evidence and assessment history were not rewritten."
        )
        unchanged = None
    else:
        headline = f"No asset crosses a modeled threshold at a {horizon_years:g}-year horizon."
        interpretation = (
            f"The horizon differs from {baseline_text}, but every asset remains in the same deterministic score/priority state for the available lifetime and migration inputs."
        )
        unchanged = "This is a meaningful no-change result: scenario controls only alter outcomes when an asset's Mosca margin or HNDL condition crosses a defined threshold."

    return RiskScenarioResult(
        scan_id=summary.scan_id,
        baseline_horizon_years=float(baseline_horizon) if baseline_horizon is not None else None,
        scenario_horizon_years=horizon_years,
        assessments=assessments_tuple,
        quantum_summary=q,
        deltas=tuple(deltas),
        changed_assets=len(deltas),
        priority_increases=increases,
        priority_decreases=decreases,
        hndl_added=hndl_added,
        hndl_removed=hndl_removed,
        narrative=ScenarioNarrative(
            headline=headline,
            interpretation=interpretation,
            material_changes=tuple(material),
            unchanged_explanation=unchanged,
        ),
    )
