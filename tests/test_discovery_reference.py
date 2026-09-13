from pathlib import Path

from ecdat.domain.enums import TargetKind
from ecdat.domain.models import RiskContext, ScanRequest, ScanTarget
from ecdat.graph.memory import InMemoryGraphStore
from ecdat.orchestration.pipeline import ScanPipeline
from ecdat.risk.quantum import QuantumRiskEngine
from ecdat.scanners.registry import discovery_scanners


async def reference_summary():
    root = Path("sample/asteria-financial").resolve()
    return await ScanPipeline(
        scanners=discovery_scanners(),
        graph_store=InMemoryGraphStore(),
        risk_engine=QuantumRiskEngine(),
    ).run(
        ScanRequest(target=ScanTarget(kind=TargetKind.DIRECTORY, locator=str(root), display_name="Asteria Financial Services")),
        RiskContext(
            data_lifetime_years=12,
            migration_time_years=4,
            quantum_horizon_years=15,
            data_sensitivity="high",
            business_criticality="high",
            public_exposure=True,
            confidentiality_required=True,
        ),
    )


async def test_reference_estate_exercises_full_discovery_pipeline() -> None:
    summary = await reference_summary()
    assert summary.status.value == "completed"
    assert summary.context_manifest_loaded is True
    assert len(summary.scanner_executions) == 9
    assert all(item.status == "completed" for item in summary.scanner_executions)
    assert len(summary.findings) >= 18
    assert summary.coverage is not None
    assert summary.coverage.files_observed >= 15
    assert summary.coverage.evidence_records >= len(summary.findings)
    assert len(summary.graph_nodes) > len(summary.findings)
    assert summary.quantum_summary is not None
    assert summary.quantum_summary.vulnerable_assets >= 5
    assert summary.quantum_summary.hndl_exposed_assets >= 1
    assert summary.quantum_summary.migration_blockers >= 1


async def test_reference_estate_retains_exact_source_evidence() -> None:
    summary = await reference_summary()
    locations = [
        (finding.asset.canonical_name, evidence.location.path, evidence.location.line_start)
        for finding in summary.findings
        for evidence in finding.evidence
    ]
    assert ("RSA", "services/payments/config/payments-prod.yaml", 148) in locations


async def test_modern_pqc_is_not_misclassified_as_quantum_vulnerable() -> None:
    summary = await reference_summary()
    findings = {finding.asset.id: finding for finding in summary.findings}
    pqc = [risk for risk in summary.risk_assessments if findings[risk.asset_id].asset.canonical_name.startswith(("ML-KEM", "ML-DSA"))]
    assert pqc
    assert all(item.quantum_posture.value == "resistant" for item in pqc)
