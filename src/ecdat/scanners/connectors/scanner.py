from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ecdat.confidence.model import confidence_from_score
from ecdat.domain.enums import AssetType, TargetKind
from ecdat.domain.models import CryptoAsset, Evidence, Finding, ScanRequest, SourceLocation
from ecdat.evidence.fingerprint import evidence_fingerprint
from ecdat.scanners.base import ScannerCapabilities
from ecdat.scanners.fs import relative_path, resolve_target_root

_CONNECTOR_FILES = {
    "tls": "integrations/tls-endpoints.json",
    "cloud_kms": "integrations/cloud-kms.json",
    "pki": "integrations/pki-inventory.json",
}
_CONNECTOR_SCHEMAS = {
    "ecdat.connector.tls.v1": "tls",
    "ecdat.connector.cloud-kms.v1": "cloud_kms",
    "ecdat.connector.pki.v1": "pki",
}


def _family(value: str | None) -> str | None:
    if not value:
        return None
    upper = value.upper().replace("_", "-")
    if upper.startswith("RSA"):
        return "RSA"
    if upper.startswith(("ECDSA", "EC", "P-256", "P-384")):
        return "ECC"
    if upper.startswith("X25519"):
        return "X25519"
    if upper.startswith("AES"):
        return "AES"
    if upper.startswith("ML-KEM"):
        return "ML-KEM"
    if upper.startswith("ML-DSA"):
        return "ML-DSA"
    if upper.startswith("SLH-DSA"):
        return "SLH-DSA"
    return upper.split("-")[0]


class EnterpriseConnectorScanner:
    """Consumes local/offline exports from common enterprise crypto control planes.

    The adapter intentionally reads files already supplied to ECDAT. It does not send
    repository contents, credentials or key material to third-party services. Each
    finding records the connector type and source record so downstream reasoning can
    distinguish connector telemetry from source-code evidence.
    """

    scanner_id = "connectors.enterprise"
    version = "0.2.0"
    capabilities = ScannerCapabilities(
        target_kinds=frozenset({TargetKind.DIRECTORY, TargetKind.REPOSITORY}),
        deterministic=True,
    )

    async def scan(self, request: ScanRequest) -> tuple[Finding, ...]:
        root = resolve_target_root(request.target.locator)
        findings: list[Finding] = []
        candidates: list[Path] = []
        for rel in _CONNECTOR_FILES.values():
            path = root / rel
            if path.is_file():
                candidates.append(path)
        staged = root / "sources" / "connectors"
        if staged.is_dir():
            candidates.extend(sorted(path for path in staged.rglob("*.json") if path.is_file()))

        seen_paths: set[Path] = set()
        for path in candidates:
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            connector = _CONNECTOR_SCHEMAS.get(str(payload.get("schema") or ""))
            if connector is None:
                # Backward compatibility with the canonical Phase-8 integration filenames.
                connector = next((kind for kind, rel in _CONNECTOR_FILES.items() if path == root / rel), None)
            if connector == "tls":
                findings.extend(self._tls(request, root, path, payload))
            elif connector == "cloud_kms":
                findings.extend(self._kms(request, root, path, payload))
            elif connector == "pki":
                findings.extend(self._pki(request, root, path, payload))
        return tuple(findings)

    def _evidence(
        self,
        request: ScanRequest,
        root: Path,
        path: Path,
        *,
        connector: str,
        record_id: str,
        method: str,
        summary: str,
        attributes: dict[str, Any],
    ) -> Evidence:
        rel = relative_path(root, path)
        attrs = {
            **attributes,
            "connector": connector,
            "record_id": record_id,
            "provenance": "enterprise_connector_export",
        }
        return Evidence(
            detector=self.scanner_id,
            detector_version=self.version,
            method=method,
            location=SourceLocation(uri=request.target.locator, path=rel, symbol=record_id),
            fingerprint=evidence_fingerprint(
                detector=self.scanner_id,
                locator=request.target.locator,
                payload={"path": rel, "connector": connector, "record_id": record_id, "attributes": attrs},
            ),
            summary=summary,
            attributes=attrs,
        )

    def _finding(
        self,
        request: ScanRequest,
        root: Path,
        path: Path,
        *,
        connector: str,
        record_id: str,
        canonical: str,
        asset_type: AssetType,
        family: str | None,
        purpose: str,
        confidence: float,
        method: str,
        summary: str,
        attributes: dict[str, Any],
        key_size_bits: int | None = None,
    ) -> Finding:
        attrs = {**attributes, "purpose": purpose, "connector": connector}
        evidence = self._evidence(
            request,
            root,
            path,
            connector=connector,
            record_id=record_id,
            method=method,
            summary=summary,
            attributes=attrs,
        )
        return Finding(
            scanner_id=self.scanner_id,
            title=f"{connector.replace('_', ' ').upper()} inventory: {canonical}",
            asset=CryptoAsset(
                asset_type=asset_type,
                canonical_name=canonical,
                algorithm_family=family,
                key_size_bits=key_size_bits,
                properties=attrs,
            ),
            evidence=(evidence,),
            confidence=confidence_from_score(confidence, "Structured enterprise connector inventory record"),
            tags=("connector", connector, purpose),
        )

    def _tls(self, request: ScanRequest, root: Path, path: Path, payload: Any) -> list[Finding]:
        records = payload.get("endpoints", []) if isinstance(payload, dict) else []
        out: list[Finding] = []
        for index, item in enumerate(records):
            if not isinstance(item, dict):
                continue
            record_id = str(item.get("id") or f"tls-{index + 1}")
            endpoint = str(item.get("endpoint") or item.get("host") or record_id)
            base = {
                "endpoint": endpoint,
                "service_id": item.get("service_id"),
                "observed_at": item.get("observed_at"),
                "source_system": item.get("source_system", "TLS inventory"),
            }
            protocol = str(item.get("protocol") or "TLS 1.3")
            out.append(self._finding(request, root, path, connector="tls", record_id=record_id, canonical=protocol, asset_type=AssetType.PROTOCOL, family="TLS", purpose="transport", confidence=0.95, method="tls-endpoint-inventory", summary=f"TLS endpoint inventory reports {protocol} at {endpoint}.", attributes=base))
            kex = item.get("key_exchange")
            if kex:
                kex_name = str(kex).upper()
                out.append(self._finding(request, root, path, connector="tls", record_id=f"{record_id}:kex", canonical=kex_name, asset_type=AssetType.ALGORITHM, family=_family(kex_name), purpose="key-establishment", confidence=0.96, method="tls-negotiated-key-exchange", summary=f"TLS inventory reports key establishment {kex_name} at {endpoint}.", attributes=base))
            cert_alg = item.get("certificate_public_key")
            if cert_alg:
                cert_name = str(cert_alg).upper()
                key_size = item.get("certificate_key_size_bits")
                out.append(self._finding(request, root, path, connector="tls", record_id=f"{record_id}:cert", canonical=cert_name, asset_type=AssetType.CERTIFICATE, family=_family(cert_name), purpose="certificate", confidence=0.95, method="tls-certificate-metadata", summary=f"TLS inventory reports a {cert_name} certificate at {endpoint}.", attributes=base, key_size_bits=int(key_size) if isinstance(key_size, int) else None))
        return out

    def _kms(self, request: ScanRequest, root: Path, path: Path, payload: Any) -> list[Finding]:
        records = payload.get("keys", []) if isinstance(payload, dict) else []
        out: list[Finding] = []
        for index, item in enumerate(records):
            if not isinstance(item, dict):
                continue
            record_id = str(item.get("key_id") or f"kms-{index + 1}")
            algorithm = str(item.get("algorithm") or "UNKNOWN").upper().replace("_", "-")
            provider = str(item.get("provider") or "cloud")
            purpose = str(item.get("purpose") or "key-management")
            key_size = item.get("key_size_bits")
            attrs = {
                "provider": provider,
                "key_id": record_id,
                "service_id": item.get("service_id"),
                "managed": bool(item.get("managed", True)),
                "region": item.get("region"),
                "rotation_enabled": item.get("rotation_enabled"),
            }
            out.append(self._finding(request, root, path, connector="cloud_kms", record_id=record_id, canonical=algorithm, asset_type=AssetType.CLOUD_CRYPTO_SERVICE, family=_family(algorithm), purpose=purpose, confidence=0.98, method="cloud-kms-inventory", summary=f"{provider} KMS inventory reports key {record_id} using {algorithm}.", attributes=attrs, key_size_bits=int(key_size) if isinstance(key_size, int) else None))
        return out

    def _pki(self, request: ScanRequest, root: Path, path: Path, payload: Any) -> list[Finding]:
        records = payload.get("certificates", []) if isinstance(payload, dict) else []
        out: list[Finding] = []
        for index, item in enumerate(records):
            if not isinstance(item, dict):
                continue
            record_id = str(item.get("serial") or f"pki-{index + 1}")
            subject = str(item.get("subject") or record_id)
            algorithm = str(item.get("public_key_algorithm") or "UNKNOWN").upper()
            key_size = item.get("key_size_bits")
            attrs = {
                "subject": subject,
                "issuer": item.get("issuer"),
                "service_id": item.get("service_id"),
                "not_after": item.get("not_after"),
                "certificate_profile": item.get("profile"),
            }
            out.append(self._finding(request, root, path, connector="pki", record_id=record_id, canonical=subject, asset_type=AssetType.CERTIFICATE, family=_family(algorithm), purpose="certificate", confidence=0.98, method="pki-inventory", summary=f"PKI inventory reports certificate {subject} using {algorithm}.", attributes=attrs, key_size_bits=int(key_size) if isinstance(key_size, int) else None))
        return out
