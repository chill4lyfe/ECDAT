import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from ecdat.domain.enums import TargetKind
from ecdat.domain.models import RiskContext, ScanRequest, ScanTarget
from ecdat.graph.memory import InMemoryGraphStore
from ecdat.migration.models import MigrationConstraints
from ecdat.migration.planner import MigrationPlanner
from ecdat.operations.maintenance import _managed_intake_roots
from ecdat.orchestration.pipeline import ScanPipeline
from ecdat.risk.quantum import QuantumRiskEngine
from ecdat.scanners.registry import discovery_scanners


async def test_multi_source_workspace_correlates_evidence_and_exposes_source_provenance(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repo = workspace / "sources/repositories/01-trust-safety"
    repo.mkdir(parents=True)
    (repo / "crypto.py").write_text("import hashlib\ndigest = hashlib.sha256(b'payload').hexdigest()\n", encoding="utf-8")

    boms = workspace / "sources/boms"
    boms.mkdir(parents=True)
    (boms / "02-platform.cdx.json").write_text(json.dumps({
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "components": [{
            "type": "cryptographic-asset",
            "bom-ref": "crypto/sha256",
            "name": "SHA-256",
            "cryptoProperties": {"assetType": "algorithm", "algorithmProperties": {"algorithmFamily": "SHA-2"}},
        }],
    }), encoding="utf-8")

    connectors = workspace / "sources/connectors"
    connectors.mkdir(parents=True)
    (connectors / "03-edge-tls.json").write_text(json.dumps({
        "schema": "ecdat.connector.tls.v1",
        "endpoints": [{"id": "public-edge", "endpoint": "api.example.test:443", "protocol": "TLS 1.3", "key_exchange": "X25519"}],
    }), encoding="utf-8")

    sources = [
        {"id": "source-01", "kind": "repository", "display_name": "Trust Safety", "filename": "trust-safety.zip", "path_prefix": "sources/repositories/01-trust-safety"},
        {"id": "source-02", "kind": "bom", "display_name": "Platform BOM", "filename": "platform.cdx.json", "path_prefix": "sources/boms/02-platform.cdx.json"},
        {"id": "source-03", "kind": "connector", "display_name": "Edge TLS", "filename": "edge-tls.json", "path_prefix": "sources/connectors/03-edge-tls.json"},
    ]
    request = ScanRequest(target=ScanTarget(kind=TargetKind.DIRECTORY, locator=str(workspace), display_name="Combined assessment", metadata={"sources": sources}))
    summary = await ScanPipeline(scanners=discovery_scanners(), graph_store=InMemoryGraphStore(), risk_engine=QuantumRiskEngine()).run(
        request,
        RiskContext(data_lifetime_years=10, migration_time_years=3, quantum_horizon_years=15),
    )

    sha = next(item for item in summary.findings if item.asset.canonical_name == "SHA-256" and item.asset.asset_type.value == "algorithm")
    assert len(sha.evidence) == 2
    assert {e.detector for e in sha.evidence} == {"source.static", "cyclonedx.import"}
    assert any(node.id == "source:source-01" for node in summary.graph_nodes)
    assert any(node.id == "source:source-02" for node in summary.graph_nodes)
    assert any(edge.properties.get("provenance") == "supplied_source" for edge in summary.graph_edges)
    assert any(item.scanner_id == "connectors.enterprise" for item in summary.findings)
    assert summary.coverage is not None
    assert any("3 supplied source" in item for item in summary.coverage.observations)
    assert any("No enterprise context manifest" in item for item in summary.coverage.limitations)

    plan = MigrationPlanner().build(summary, MigrationConstraints())
    source_readiness = {item.node_id: item for item in plan.agility_scores}
    assert "source:source-01" in source_readiness
    assert source_readiness["source:source-01"].coverage == "partial"
    assert any(factor.code == "source-context-only" for factor in source_readiness["source:source-01"].factors)
    assert source_readiness["source:source-01"].basis == "technical_evidence"
    assert plan.sequencing_mode == "evidence_prioritized"
    assert plan.critical_path == ()
    assert any("does not infer business criticality" in item for item in plan.strategy_explanation)
    assert any("evidence-prioritized execution stages" in item for item in plan.strategy_explanation)
    assert all(not item.node_id.startswith("target:") for item in plan.agility_scores)


def test_managed_intake_cleanup_never_targets_external_mount(monkeypatch, tmp_path: Path) -> None:
    intake = tmp_path / "intake"
    monkeypatch.setenv("ECDAT_INTAKE_DIR", str(intake))
    from ecdat.settings import get_settings
    get_settings.cache_clear()
    organization_id = uuid4()
    managed = intake / "organizations" / str(organization_id) / "assessment-1"
    external = tmp_path / "company-repo"
    managed.mkdir(parents=True)
    external.mkdir()
    records = [
        SimpleNamespace(summary_json={"target": {"locator": str(managed / "workspace"), "metadata": {"managed_intake_root": str(managed)}}}),
        SimpleNamespace(summary_json={"target": {"locator": str(external), "metadata": {}}}),
    ]
    roots = _managed_intake_roots(records, organization_id)
    assert managed.resolve() in roots
    assert external.resolve() not in roots
    get_settings.cache_clear()


def test_repository_extraction_respects_remaining_combined_budget(tmp_path: Path) -> None:
    import zipfile
    from fastapi import HTTPException
    from ecdat.api.routes.intake import _extract_zip

    archive = tmp_path / "repo.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("src/payload.bin", b"x" * 128)
    destination = tmp_path / "out"
    destination.mkdir()
    try:
        _extract_zip(archive, destination, max_extracted_bytes=64, max_members=10)
    except HTTPException as exc:
        assert exc.status_code == 413
    else:
        raise AssertionError("combined extraction budget should reject oversized expansion")


def test_context_manifest_upload_validation_accepts_ecdat_context_v1(tmp_path: Path) -> None:
    from fastapi import HTTPException
    from ecdat.api.routes.intake import _SOURCE_KINDS, _validate_context_manifest

    assert "context" in _SOURCE_KINDS
    valid = tmp_path / "ecdat.context.json"
    valid.write_text(json.dumps({
        "schema": "ecdat.context.v1",
        "data_classes": [{"id": "messages", "name": "Customer Messages", "sensitivity": "high", "lifetime_years": 8}],
        "services": [{
            "id": "messaging", "name": "Messaging", "path_prefixes": ["sources/repositories/01-messaging/"],
            "business_criticality": "high", "public_exposure": True, "confidentiality_required": True,
            "migration_time_years": 2, "protects": ["messages"],
        }],
        "relationships": [],
    }), encoding="utf-8")
    _validate_context_manifest(valid, valid.name)

    invalid = tmp_path / "bad-context.json"
    invalid.write_text(json.dumps({"schema": "ecdat.context.v2", "services": []}), encoding="utf-8")
    try:
        _validate_context_manifest(invalid, invalid.name)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "ecdat.context.v1" in str(exc.detail)
    else:
        raise AssertionError("unsupported enterprise context schema should be rejected")
