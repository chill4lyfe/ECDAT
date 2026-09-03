from pathlib import Path

from ecdat.api.catalog import catalog
from ecdat.api.routes.reports import _report
from ecdat.domain.enums import TargetKind
from ecdat.domain.models import RiskContext, ScanRequest, ScanTarget
from ecdat.graph.memory import InMemoryGraphStore
from ecdat.migration.catalog import migration_catalog
from ecdat.migration.models import MigrationConstraints
from ecdat.migration.planner import MigrationPlanner
from ecdat.orchestration.pipeline import ScanPipeline
from ecdat.risk.quantum import QuantumRiskEngine
from ecdat.scanners.registry import discovery_scanners
from tests.test_discovery_reference import reference_summary


async def test_zero_findings_are_reported_as_coverage_not_proof_of_absence(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("A small service with no observable cryptographic API usage.\n", encoding="utf-8")
    summary = await ScanPipeline(
        scanners=discovery_scanners(),
        graph_store=InMemoryGraphStore(),
        risk_engine=QuantumRiskEngine(),
    ).run(
        ScanRequest(target=ScanTarget(kind=TargetKind.DIRECTORY, locator=str(tmp_path), display_name="Sparse service")),
        RiskContext(),
    )
    assert len(summary.findings) == 0
    assert summary.coverage is not None
    assert summary.coverage.files_observed == 1
    assert any("No deterministic cryptographic evidence" in item for item in summary.coverage.observations)
    assert any("does not prove cryptography is absent" in item for item in summary.coverage.limitations)


async def test_executive_report_retains_evidence_and_uncertainty() -> None:
    summary = await reference_summary()
    catalog.put(summary)
    migration_catalog.put(MigrationPlanner().build(summary, MigrationConstraints()))
    report = _report(summary.scan_id)

    assert report.metrics["crypto_assets"] == len(summary.findings)
    assert report.migration["waves"] >= 2
    assert report.management_summary
    assert report.technical_observations
    assert any("not a predicted CRQC date" in item for item in report.limitations)
    evidence = [location for item in report.priority_findings for location in item["evidence_locations"]]
    assert "services/payments/config/payments-prod.yaml:148" in evidence
