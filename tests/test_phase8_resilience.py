from ecdat.migration.models import MigrationConstraints
from ecdat.migration.planner import MigrationPlanner
from tests.test_discovery_reference import reference_summary


async def test_enterprise_connectors_contribute_traceable_evidence() -> None:
    summary = await reference_summary()
    connector_evidence = [evidence for item in summary.findings for evidence in item.evidence if evidence.detector == "connectors.enterprise"]
    assert len(connector_evidence) >= 8
    connector_types = {evidence.attributes.get("connector") for evidence in connector_evidence}
    assert {"tls", "cloud_kms", "pki"} <= connector_types
    assert all(evidence.attributes.get("provenance") == "enterprise_connector_export" for evidence in connector_evidence)


def _edge_provenance(summary):
    return {edge.properties.get("provenance") for edge in summary.graph_edges}


async def test_graph_edges_expose_observed_declared_and_connector_provenance() -> None:
    summary = await reference_summary()
    provenance = _edge_provenance(summary)
    assert "observed_evidence" in provenance
    assert "declared_context" in provenance
    assert "connector" in provenance


async def test_showcase_generates_four_dependency_aware_migration_waves() -> None:
    summary = await reference_summary()
    plan = MigrationPlanner().build(summary, MigrationConstraints(mode="balanced", prefer_hybrid=True, max_parallel_actions=3, change_window_weeks=12))
    assert plan.sequencing_mode == "dependency_aware"
    assert plan.context_quality == "enterprise_context"
    assert len(plan.waves) == 4
    assert [wave.wave for wave in plan.waves] == [1, 2, 3, 4]
    assert plan.summary.total_actions > 0
    assert plan.summary.deferred_actions > 0


async def test_binary_evidence_carries_format_and_opacity_limits() -> None:
    summary = await reference_summary()
    binary = [item for item in summary.findings if item.scanner_id == "binaries.heuristic"]
    assert binary
    attrs = binary[0].evidence[0].attributes
    assert attrs.get("binary_format") == "ELF"
    assert "likely_stripped" in attrs
    assert "opaque_or_packed_signal" in attrs

async def test_binary_scanner_accepts_static_archive_magic(tmp_path) -> None:
    from ecdat.domain.enums import TargetKind
    from ecdat.domain.models import ScanRequest, ScanTarget
    from ecdat.scanners.binaries.scanner import BinaryHeuristicScanner

    archive = tmp_path / "liblegacy.a"
    archive.write_bytes(b"!<arch>\n" + b"CryptoPP\x00RSA_public_encrypt\x00" + b"\x00" * 64)
    request = ScanRequest(target=ScanTarget(kind=TargetKind.DIRECTORY, locator=str(tmp_path)))
    findings = await BinaryHeuristicScanner().scan(request)
    assert findings
    assert any(item.evidence[0].attributes.get("binary_format") == "static-archive" for item in findings)
