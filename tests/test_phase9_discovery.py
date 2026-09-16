from __future__ import annotations

from pathlib import Path

from ecdat.confidence.model import confidence_from_score
from ecdat.domain.enums import AssetType, TargetKind
from ecdat.domain.models import CryptoAsset, Evidence, Finding, RiskContext, ScanRequest, ScanTarget, SourceLocation
from ecdat.normalization.normalizer import FindingNormalizer
from ecdat.scanners.binaries.scanner import BinaryHeuristicScanner
from ecdat.scanners.source.scanner import SourceCodeScanner


def _finding(*, name: str, path: str, fingerprint: str, asset_type: AssetType = AssetType.ALGORITHM, purpose: str | None = None) -> Finding:
    properties = {"purpose": purpose} if purpose else {}
    evidence = Evidence(
        detector="phase9.test",
        detector_version="1",
        method="fixture",
        location=SourceLocation(uri="fixture", path=path, line_start=1, line_end=1),
        fingerprint=fingerprint,
        summary=f"{name} fixture",
        attributes={"purpose": purpose} if purpose else {},
    )
    return Finding(
        scanner_id="phase9.test",
        title=f"{name} fixture",
        asset=CryptoAsset(asset_type=asset_type, canonical_name=name, algorithm_family=name if asset_type == AssetType.ALGORITHM else "OpenSSL", properties=properties),
        evidence=(evidence,),
        confidence=confidence_from_score(0.9, "fixture"),
    )


def test_normalization_v2_deduplicates_locations_but_retains_occurrences() -> None:
    normalized = FindingNormalizer().normalize((
        _finding(name="RSA", path="apps/a.c", fingerprint="rsa-a"),
        _finding(name="RSA", path="ssl/b.c", fingerprint="rsa-b"),
    ))

    assert len(normalized) == 1
    finding = normalized[0]
    assert len(finding.evidence) == 2
    assert finding.asset.properties["occurrence_count"] == 2
    assert finding.asset.properties["source_paths"] == ["apps/a.c", "ssl/b.c"]
    assert finding.asset.properties["normalization_version"] == "normalization.v2"


def test_normalization_v2_distinguishes_semantic_usage_not_file_location() -> None:
    normalized = FindingNormalizer().normalize((
        _finding(name="OpenSSL EVP usage", path="apps/a.c", fingerprint="enc-a", asset_type=AssetType.CRYPTO_USAGE, purpose="encryption"),
        _finding(name="OpenSSL EVP usage", path="apps/b.c", fingerprint="enc-b", asset_type=AssetType.CRYPTO_USAGE, purpose="encryption"),
        _finding(name="OpenSSL EVP usage", path="apps/c.c", fingerprint="hash-c", asset_type=AssetType.CRYPTO_USAGE, purpose="hashing"),
    ))

    assert len(normalized) == 2
    by_purpose = {item.asset.properties.get("purpose"): item for item in normalized}
    assert len(by_purpose["encryption"].evidence) == 2
    assert len(by_purpose["hashing"].evidence) == 1


async def test_source_scanner_resolves_openssl_evp_algorithms(tmp_path: Path) -> None:
    (tmp_path / "crypto.c").write_text(
        'EVP_CIPHER_fetch(NULL, "AES-256-GCM", NULL);\n'
        'EVP_MD_fetch(NULL, "SHA256", NULL);\n'
        'EVP_PKEY_CTX_new_from_name(NULL, "X25519", NULL);\n',
        encoding="utf-8",
    )
    request = ScanRequest(target=ScanTarget(kind=TargetKind.DIRECTORY, locator=str(tmp_path)))
    findings = await SourceCodeScanner().scan(request)
    names = {item.asset.canonical_name for item in findings}

    assert {"AES", "SHA-256", "X25519"} <= names
    aes = next(item for item in findings if item.asset.canonical_name == "AES")
    assert aes.asset.key_size_bits == 256
    assert aes.asset.mode == "GCM"
    assert aes.evidence[0].attributes.get("api_call") == "EVP_CIPHER_fetch"


async def test_binary_scanner_finds_extensionless_elf_and_reports_unresolved(tmp_path: Path) -> None:
    detected = tmp_path / "openssl-tool"
    detected.write_bytes(b"\x7fELF" + b"\x02\x01" + b"\x00" * 64 + b"libcrypto.so.3\x00RSA_public_encrypt\x00")
    unresolved = tmp_path / "opaque-tool"
    unresolved.write_bytes(b"\x7fELF" + b"\x02\x01" + b"\x00" * 128)

    request = ScanRequest(target=ScanTarget(kind=TargetKind.DIRECTORY, locator=str(tmp_path)))
    scanner = BinaryHeuristicScanner()
    findings = await scanner.scan(request)
    names = {item.asset.canonical_name for item in findings}

    assert "OpenSSL/libcrypto" in names
    assert "RSA" in names
    assert scanner.last_metrics["binary_files_scanned"] == 2
    assert scanner.last_metrics["unresolved_binary_files"] == 1


def test_risk_context_allows_unknown_enterprise_inputs() -> None:
    context = RiskContext(quantum_horizon_years=15, context_profile="evidence_first", assumption_basis="operator")
    assert context.data_lifetime_years is None
    assert context.migration_time_years is None
    assert context.data_sensitivity is None
    assert context.business_criticality is None
    assert context.public_exposure is None
    assert context.confidentiality_required is None


async def test_native_dependency_scanner_detects_openssl_cmake(tmp_path: Path) -> None:
    from ecdat.scanners.dependencies.scanner import DependencyScanner

    (tmp_path / "CMakeLists.txt").write_text("find_package(OpenSSL REQUIRED)\ntarget_link_libraries(app PRIVATE OpenSSL::Crypto)\n", encoding="utf-8")
    request = ScanRequest(target=ScanTarget(kind=TargetKind.DIRECTORY, locator=str(tmp_path)))
    findings = await DependencyScanner().scan(request)

    assert findings
    assert {item.asset.canonical_name for item in findings} == {"OpenSSL"}


async def test_certificate_scanner_reads_pem_bundle_without_adapter_failure(tmp_path: Path) -> None:
    from ecdat.scanners.certificates.scanner import CertificateScanner

    cert = Path("sample/asteria-financial/certs/edge.crt").read_bytes()
    (tmp_path / "bundle.pem").write_bytes(cert + b"\n" + cert)
    request = ScanRequest(target=ScanTarget(kind=TargetKind.DIRECTORY, locator=str(tmp_path)))
    scanner = CertificateScanner()
    findings = await scanner.scan(request)

    assert len(findings) == 2
    assert scanner.last_metrics["certificates_parsed"] == 2
    assert all(item.evidence[0].attributes.get("certificate_index") in {1, 2} for item in findings)

async def test_readiness_includes_evidence_derived_repository_components(tmp_path: Path) -> None:
    from ecdat.graph.memory import InMemoryGraphStore
    from ecdat.migration.agility import CryptoAgilityEngine
    from ecdat.orchestration.pipeline import ScanPipeline
    from ecdat.risk.quantum import QuantumRiskEngine

    repo = tmp_path / "sources" / "repositories" / "01-openssl"
    (repo / "crypto").mkdir(parents=True)
    (repo / "crypto" / "digest.py").write_text(
        "import hashlib\nvalue = hashlib.sha256(b'phase9').hexdigest()\n",
        encoding="utf-8",
    )
    (repo / "ssl").mkdir(parents=True)
    (repo / "ssl" / "session.py").write_text(
        "import hashlib\nvalue = hashlib.sha512(b'phase9').hexdigest()\n",
        encoding="utf-8",
    )
    request = ScanRequest(target=ScanTarget(
        kind=TargetKind.DIRECTORY,
        locator=str(tmp_path),
        display_name="OpenSSL Source Test",
        metadata={"sources": [{
            "id": "openssl-source",
            "kind": "repository",
            "display_name": "OpenSSL Source Test",
            "filename": "openssl.zip",
            "path_prefix": "sources/repositories/01-openssl",
        }]},
    ))
    summary = await ScanPipeline(
        scanners=(SourceCodeScanner(),),
        graph_store=InMemoryGraphStore(),
        risk_engine=QuantumRiskEngine(),
    ).run(request, RiskContext(quantum_horizon_years=15))

    component_nodes = [node for node in summary.graph_nodes if node.properties.get("technical_component") is True]
    assert component_nodes
    scores = {item.node_id: item for item in CryptoAgilityEngine().score(summary)}
    assert any(node.id in scores for node in component_nodes)
    component_score = next(scores[node.id] for node in component_nodes if node.id in scores)
    assert component_score.basis == "technical_evidence"
    assert component_score.coverage == "partial"
    assert any(factor.code == "technical-component-only" for factor in component_score.factors)
