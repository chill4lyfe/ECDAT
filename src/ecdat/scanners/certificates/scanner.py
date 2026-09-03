from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

from ecdat.confidence.model import confidence_from_score
from ecdat.domain.enums import AssetType, TargetKind
from ecdat.domain.models import CryptoAsset, Evidence, Finding, ScanRequest, SourceLocation
from ecdat.evidence.fingerprint import evidence_fingerprint
from ecdat.scanners.base import ScannerCapabilities
from ecdat.scanners.fs import iter_files, relative_path, resolve_target_root

_CERT_SUFFIXES = frozenset({".pem", ".crt", ".cer"})

try:
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed25519, ed448, rsa
except ImportError:  # pragma: no cover - runtime fallback is tested indirectly
    x509 = None  # type: ignore[assignment]
    dsa = ec = ed25519 = ed448 = rsa = None  # type: ignore[assignment]


def _load_certificate(raw: bytes):  # type: ignore[no-untyped-def]
    if x509 is None:
        return None
    try:
        if b"-----BEGIN CERTIFICATE-----" in raw:
            return x509.load_pem_x509_certificate(raw)
        return x509.load_der_x509_certificate(raw)
    except ValueError:
        return None


def _public_key_info(public_key: Any) -> tuple[str | None, int | None]:
    if rsa is not None and isinstance(public_key, rsa.RSAPublicKey):
        return "RSA", public_key.key_size
    if ec is not None and isinstance(public_key, ec.EllipticCurvePublicKey):
        return "ECC", public_key.key_size
    if dsa is not None and isinstance(public_key, dsa.DSAPublicKey):
        return "DSA", public_key.key_size
    if ed25519 is not None and isinstance(public_key, ed25519.Ed25519PublicKey):
        return "Ed25519", 256
    if ed448 is not None and isinstance(public_key, ed448.Ed448PublicKey):
        return "Ed448", 456
    return None, None


class CertificateScanner:
    scanner_id = "certificates.x509"
    version = "0.1.0"
    capabilities = ScannerCapabilities(
        target_kinds=frozenset({TargetKind.DIRECTORY, TargetKind.REPOSITORY}),
        deterministic=True,
    )

    async def scan(self, request: ScanRequest) -> tuple[Finding, ...]:
        root = resolve_target_root(request.target.locator)
        findings: list[Finding] = []
        for path in iter_files(root, suffixes=_CERT_SUFFIXES, max_file_bytes=4_000_000):
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if b"-----BEGIN CERTIFICATE-----" not in raw and not raw.startswith(b"0"):
                continue
            cert = _load_certificate(raw)
            findings.append(self._finding(request, root, path, raw, cert))
        return tuple(findings)

    def _finding(self, request: ScanRequest, root: Path, path: Path, raw: bytes, cert: Any) -> Finding:
        rel = relative_path(root, path)
        sha256 = hashlib.sha256(raw).hexdigest()
        attrs: dict[str, Any] = {"sha256": sha256, "parser": "structural"}
        family: str | None = None
        key_size: int | None = None
        canonical = path.name
        confidence = 0.72
        method = "x509-structural-file"

        if cert is not None:
            public_key = cert.public_key()
            family, key_size = _public_key_info(public_key)
            subject = cert.subject.rfc4514_string()
            issuer = cert.issuer.rfc4514_string()
            canonical = subject or path.name
            attrs.update(
                {
                    "subject": subject,
                    "issuer": issuer,
                    "serial_number_hex": format(cert.serial_number, "x"),
                    "not_valid_before": cert.not_valid_before_utc.isoformat(),
                    "not_valid_after": cert.not_valid_after_utc.isoformat(),
                    "signature_hash_algorithm": getattr(cert.signature_hash_algorithm, "name", None),
                    "signature_algorithm_oid": cert.signature_algorithm_oid.dotted_string,
                    "public_key_family": family,
                    "key_size_bits": key_size,
                    "parser": "cryptography.x509",
                }
            )
            confidence = 0.99
            method = "x509-parser"
        elif b"-----BEGIN CERTIFICATE-----" in raw:
            # Validate PEM envelope without storing certificate body in evidence.
            body = raw.split(b"-----BEGIN CERTIFICATE-----", 1)[1].split(b"-----END CERTIFICATE-----", 1)[0]
            try:
                base64.b64decode(b"".join(body.split()), validate=True)
                confidence = 0.82
            except ValueError:
                confidence = 0.55

        evidence = Evidence(
            detector=self.scanner_id,
            detector_version=self.version,
            method=method,
            location=SourceLocation(uri=request.target.locator, path=rel),
            fingerprint=evidence_fingerprint(
                detector=self.scanner_id,
                locator=request.target.locator,
                payload={"path": rel, "sha256": sha256},
            ),
            summary=f"X.509 certificate discovered at {rel}; certificate material is not copied into evidence.",
            attributes=attrs,
        )
        return Finding(
            scanner_id=self.scanner_id,
            title=f"X.509 certificate: {canonical}",
            asset=CryptoAsset(
                asset_type=AssetType.CERTIFICATE,
                canonical_name=canonical,
                algorithm_family=family,
                key_size_bits=key_size,
                properties=attrs,
            ),
            evidence=(evidence,),
            confidence=confidence_from_score(confidence, "Parsed X.509 certificate" if cert is not None else "Certificate envelope detected"),
            tags=("certificate", "x509"),
        )
