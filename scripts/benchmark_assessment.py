from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from time import perf_counter

from ecdat.domain.enums import TargetKind
from ecdat.domain.models import RiskContext, ScanRequest, ScanTarget
from ecdat.graph.memory import InMemoryGraphStore
from ecdat.migration.models import MigrationConstraints
from ecdat.migration.planner import MigrationPlanner
from ecdat.orchestration.pipeline import ScanPipeline
from ecdat.risk.quantum import QuantumRiskEngine
from ecdat.scanners.registry import discovery_scanners


async def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "sample/asteria-financial").resolve()
    if not root.exists():
        raise SystemExit(f"assessment target does not exist: {root}")
    started = perf_counter()
    summary = await ScanPipeline(scanners=discovery_scanners(), graph_store=InMemoryGraphStore(), risk_engine=QuantumRiskEngine()).run(
        ScanRequest(target=ScanTarget(kind=TargetKind.DIRECTORY, locator=str(root), display_name=root.name)),
        RiskContext(data_lifetime_years=12, migration_time_years=4, quantum_horizon_years=15, data_sensitivity="high", business_criticality="high", public_exposure=True, confidentiality_required=True),
    )
    scan_seconds = perf_counter() - started
    plan_started = perf_counter()
    plan = MigrationPlanner().build(summary, MigrationConstraints())
    plan_seconds = perf_counter() - plan_started
    coverage = summary.coverage
    print("ECDAT reproducible local assessment benchmark")
    print(f"  target: {root}")
    print(f"  files observed: {coverage.files_observed if coverage else 0}")
    print(f"  findings: {len(summary.findings)}")
    print(f"  evidence records: {coverage.evidence_records if coverage else 0}")
    print(f"  graph: {len(summary.graph_nodes)} nodes / {len(summary.graph_edges)} edges")
    print(f"  scanners: {len(summary.scanner_executions)} completed adapters")
    print(f"  scan pipeline: {scan_seconds:.4f}s")
    print(f"  migration planning: {plan_seconds:.4f}s")
    print(f"  migration programme: {len(plan.waves)} waves / {plan.summary.total_actions} actions")
    print("  Note: this is a local reproducible workload measurement, not an enterprise-scale throughput claim.")


if __name__ == "__main__":
    asyncio.run(main())
