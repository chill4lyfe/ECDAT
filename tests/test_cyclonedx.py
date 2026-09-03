import json
from pathlib import Path

from ecdat.domain.enums import TargetKind
from ecdat.domain.models import RiskContext, ScanRequest, ScanTarget
from ecdat.graph.memory import InMemoryGraphStore
from ecdat.integrations.cyclonedx.exporter import CycloneDXExporter
from ecdat.integrations.cyclonedx.importer import CycloneDXImporter
from ecdat.orchestration.pipeline import ScanPipeline
from ecdat.risk.quantum import QuantumRiskEngine
from ecdat.scanners.source.scanner import SourceCodeScanner


async def test_cyclonedx_export_and_crypto_import(tmp_path) -> None:
    source = tmp_path / "a.py"
    source.write_text("import hashlib\nhashlib.sha1(b'x')\n")
    summary = await ScanPipeline(
        scanners=(SourceCodeScanner(),),
        graph_store=InMemoryGraphStore(),
        risk_engine=QuantumRiskEngine(),
    ).run(
        ScanRequest(target=ScanTarget(kind=TargetKind.DIRECTORY, locator=str(tmp_path))),
        RiskContext(data_lifetime_years=1, migration_time_years=1, quantum_horizon_years=15),
    )
    bom = CycloneDXExporter().export(summary)
    assert bom["specVersion"] == "1.7"
    crypto = [component for component in bom["components"] if "cryptoProperties" in component]
    assert crypto
    assert crypto[0]["cryptoProperties"]["assetType"] == "algorithm"

    path = Path(tmp_path / "bom.json")
    path.write_text(json.dumps(bom), encoding="utf-8")
    imported = CycloneDXImporter().import_file(path)
    assert any(finding.asset.canonical_name == "SHA-1" for finding in imported)
