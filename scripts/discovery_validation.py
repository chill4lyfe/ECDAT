from __future__ import annotations

import asyncio
from pathlib import Path

from ecdat.domain.enums import TargetKind
from ecdat.domain.models import RiskContext, ScanRequest, ScanTarget
from ecdat.graph.memory import InMemoryGraphStore
from ecdat.orchestration.pipeline import ScanPipeline
from ecdat.risk.quantum import QuantumRiskEngine
from ecdat.scanners.registry import discovery_scanners

EXPECTED = {
    ("RSA", "services/payments/config/payments-prod.yaml", 148),
    ("MD5", "services/partner/legacy.js", 2),
    ("ML-KEM-768", "services/ledger/security.yaml", 1),
}


async def main() -> None:
    root = Path("sample/asteria-financial").resolve()
    summary = await ScanPipeline(scanners=discovery_scanners(), graph_store=InMemoryGraphStore(), risk_engine=QuantumRiskEngine()).run(
        ScanRequest(target=ScanTarget(kind=TargetKind.DIRECTORY, locator=str(root), display_name="Asteria Financial Services")),
        RiskContext(data_lifetime_years=12, migration_time_years=4, quantum_horizon_years=15, data_sensitivity="high", business_criticality="high", public_exposure=True, confidentiality_required=True),
    )
    observed = {(finding.asset.canonical_name, evidence.location.path, evidence.location.line_start) for finding in summary.findings for evidence in finding.evidence}
    missing = sorted(EXPECTED - observed)
    connectors = [finding for finding in summary.findings if finding.scanner_id == "connectors.enterprise"]
    print("ECDAT labelled discovery validation")
    print(f"  findings: {len(summary.findings)}")
    print(f"  evidence records: {summary.coverage.evidence_records if summary.coverage else 0}")
    print(f"  connector findings: {len(connectors)}")
    print(f"  required labelled signals: {len(EXPECTED) - len(missing)}/{len(EXPECTED)}")
    if missing:
        for item in missing:
            print(f"  MISSING: {item}")
        raise SystemExit(1)
    print("  PASS: required showcase evidence was reproduced through the normal scanner pipeline")


if __name__ == "__main__":
    asyncio.run(main())
