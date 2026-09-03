from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from ecdat.domain.enums import TargetKind
from ecdat.domain.models import RiskContext, ScanRequest, ScanTarget
from ecdat.graph.memory import InMemoryGraphStore
from ecdat.orchestration.pipeline import ScanPipeline
from ecdat.risk.quantum import QuantumRiskEngine
from ecdat.scanners.registry import discovery_scanners

app = typer.Typer(help="ECDAT discovery developer CLI")


def _emit(summary) -> None:  # type: ignore[no-untyped-def]
    typer.echo(json.dumps(summary.model_dump(mode="json"), indent=2))


@app.command("scan-directory")
def scan_directory(
    path: Path,
    data_lifetime_years: float = 12,
    migration_time_years: float = 4,
    quantum_horizon_years: float = 15,
) -> None:
    """Run the registered discovery adapters against a local directory."""

    async def _run() -> None:
        root = path.expanduser().resolve()
        summary = await ScanPipeline(
            scanners=discovery_scanners(),
            graph_store=InMemoryGraphStore(),
            risk_engine=QuantumRiskEngine(),
        ).run(
            ScanRequest(target=ScanTarget(kind=TargetKind.DIRECTORY, locator=str(root), display_name=root.name)),
            RiskContext(
                data_lifetime_years=data_lifetime_years,
                migration_time_years=migration_time_years,
                quantum_horizon_years=quantum_horizon_years,
            ),
        )
        _emit(summary)

    asyncio.run(_run())


if __name__ == "__main__":
    app()
