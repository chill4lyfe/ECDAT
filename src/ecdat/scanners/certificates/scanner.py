from __future__ import annotations

import base64
import hashlib
import re
import warnings
from pathlib import Path
from typing import Any

from ecdat.confidence.model import confidence_from_score
from ecdat.domain.enums import AssetType, TargetKind
from ecdat.domain.models import CryptoAsset, Evidence, Finding, ScanRequest, SourceLocation
from ecdat.evidence.fingerprint import evidence_fingerprint
from ecdat.scanners.base import ScannerCapabilities
from ecdat.scanners.fs import iter_files, relative_path, resolve_target_root

_CERT_SUFFIXES = frozenset({".pem", ".crt", ".cer", ".der", ".p12", ".pfx"})
_PEM_CERT = re.compile(
    rb"-----BEGIN CERTIFICATE-----\s+.+?-----END CERTIFICATE-----",
    re.DOTALL,
)

try:
    from cryptography import x509
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed25519, ed448, rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
except ImportError:  # pragma: no cover - runtime fallback is tested indirectly
    x509 = None  # type: ignore[assignment]
    UnsupportedAlgorithm = Exception  # type: ignore[assignment,misc]
    hashes = dsa = ec = ed25519 = ed448 = rsa = pkcs12 = None  # type: ignore[assignment]


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


def _cert_sha256(cert: Any, fallback: bytes) -> str:
    try:
        return cert.fingerprint(hashes.SHA256()).hex()
    except Exception:
        return hashlib.sha256(fallback).hexdigest()


class CertificateScanner:
    scanner_id = "certificates.x509"
    version = "0.2.1"
    capabilities = ScannerCapabilities(
        target_kinds=frozenset({TargetKind.DIRECTORY, TargetKind.REPOSITORY}),
        deterministic=True,
    )

    async def scan(self, request: ScanRequest) -> tuple[Finding, ...]:
        root = resolve_target_root(request.target.locator)
        findings: list[Finding] = []
        files_scanned = 0
        certificates_parsed = 0
        limited_files = 0
        unreadable = 0

        for path in iter_files(root, suffixes=_CERT_SUFFIXES, max_file_bytes=8_000_000):
            try:
                raw = path.read_bytes()
            except OSError:
                unreadable += 1
                continue
            files_scanned += 1
            certs, load_limitations = self._load_certificates(path, raw)
            if load_limitations:
                limited_files += 1

            if certs:
                for index, (cert, parse_warnings) in enumerate(certs, start=1):
                    findings.append(
                        self._finding(
                            request,
                            root,
                            path,
                            raw,
                            cert,
                            certificate_index=index,
                            limitations=tuple(dict.fromkeys((*load_limitations, *parse_warnings))),
                        )
                    )
                    certificates_parsed += 1
                continue

            # Preserve the previous envelope-level discovery behavior for certificate
            # material that cannot be structurally parsed. The limitation is explicit.
            if b"-----BEGIN CERTIFICATE-----" in raw or path.suffix.lower() in {".der", ".p12", ".pfx"}:
                findings.append(
                    self._finding(
                        request,
                        root,
                        path,
                        raw,
                        None,
                        certificate_index=1,
                        limitations=load_limitations or ("Certificate container detected but structural parsing did not succeed.",),
                    )
                )

        self.last_metrics = {
            "files_scanned": files_scanned,
            "certificates_parsed": certificates_parsed,
            "limited_files": limited_files,
            "unreadable_files": unreadable,
            "raw_findings": len(findings),
        }
        return tuple(findings)

    def _load_certificates(self, path: Path, raw: bytes) -> tuple[list[tuple[Any, tuple[str, ...]]], tuple[str, ...]]:
        if x509 is None:
            return [], ("cryptography.x509 is unavailable in this runtime.",)

        suffix = path.suffix.lower()
        loaded: list[tuple[Any, tuple[str, ...]]] = []
        limitations: list[str] = []

        if suffix in {".p12", ".pfx"}:
            if pkcs12 is None:
                return [], ("PKCS#12 support is unavailable in this runtime.",)
            try:
                _key, certificate, additional = pkcs12.load_key_and_certificates(raw, None)
            except (ValueError, UnsupportedAlgorithm) as exc:
                return [], (f"PKCS#12 could not be opened without credentials or uses an unsupported algorithm: {type(exc).__name__}.",)
            if certificate is not None:
                loaded.append((certificate, ()))
            loaded.extend((item, ()) for item in additional or ())
            return loaded, () if loaded else ("PKCS#12 container contained no readable certificates.",)

        pem_blocks = _PEM_CERT.findall(raw)
        if pem_blocks:
            for block in pem_blocks:
                cert, captured, error = self._load_one(block, pem=True)
                if cert is not None:
                    loaded.append((cert, captured))
                elif error:
                    limitations.append(error)
            return loaded, tuple(limitations)

        # .crt/.cer/.der may contain DER. Avoid treating arbitrary PEM key files as DER.
        if suffix in {".der", ".crt", ".cer"} or raw.startswith(b"0"):
            cert, captured, error = self._load_one(raw, pem=False)
            if cert is not None:
                loaded.append((cert, captured))
            elif error:
                limitations.append(error)
        return loaded, tuple(limitations)

    @staticmethod
    def _load_one(raw: bytes, *, pem: bool) -> tuple[Any | None, tuple[str, ...], str | None]:
        if x509 is None:
            return None, (), "cryptography.x509 is unavailable."
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                cert = x509.load_pem_x509_certificate(raw) if pem else x509.load_der_x509_certificate(raw)
            except (ValueError, UnsupportedAlgorithm) as exc:
                return None, (), f"Certificate parser rejected this object: {type(exc).__name__}."
        messages = tuple(str(item.message) for item in caught)
        return cert, messages, None

    def _finding(
        self,
        request: ScanRequest,
        root: Path,
        path: Path,
        raw: bytes,
        cert: Any,
        *,
        certificate_index: int,
        limitations: tuple[str, ...] = (),
    ) -> Finding:
        rel = relative_path(root, path)
        sha256 = _cert_sha256(cert, raw) if cert is not None else hashlib.sha256(raw).hexdigest()
        attrs: dict[str, Any] = {
            "sha256": sha256,
            "parser": "structural",
            "certificate_index": certificate_index,
        }
        family: str | None = None
        key_size: int | None = None
        canonical = path.name
        confidence = 0.72
        method = "x509-structural-file"
        field_limitations = list(limitations)

        if cert is not None:
            try:
                subject = cert.subject.rfc4514_string()
            except Exception as exc:
                subject = ""
                field_limitations.append(f"Subject could not be decoded: {type(exc).__name__}.")
            try:
                issuer = cert.issuer.rfc4514_string()
            except Exception as exc:
                issuer = ""
                field_limitations.append(f"Issuer could not be decoded: {type(exc).__name__}.")

            canonical = subject or path.name
            serial_hex: str | None = None
            with warnings.catch_warnings(record=True) as serial_warnings:
                warnings.simplefilter("always")
                try:
                    serial_hex = format(cert.serial_number, "x")
                except Exception as exc:
                    field_limitations.append(f"Certificate serial number could not be read: {type(exc).__name__}.")
            for item in serial_warnings:
                field_limitations.append(str(item.message))

            attrs.update(
                {
                    "subject": subject,
                    "issuer": issuer,
                    "serial_number_hex": serial_hex,
                    "not_valid_before": cert.not_valid_before_utc.isoformat(),
                    "not_valid_after": cert.not_valid_after_utc.isoformat(),
                    "signature_algorithm_oid": cert.signature_algorithm_oid.dotted_string,
                    "parser": "cryptography.x509",
                }
            )

            key_oid = getattr(cert, "public_key_algorithm_oid", None)
            if key_oid is not None:
                attrs["public_key_algorithm_oid"] = getattr(key_oid, "dotted_string", str(key_oid))
            try:
                public_key = cert.public_key()
                family, key_size = _public_key_info(public_key)
            except (UnsupportedAlgorithm, ValueError) as exc:
                field_limitations.append(
                    f"Public key metadata is partially unresolved because cryptography does not support this key type: {type(exc).__name__}."
                )

            try:
                signature_hash = cert.signature_hash_algorithm
                attrs["signature_hash_algorithm"] = getattr(signature_hash, "name", None)
            except (UnsupportedAlgorithm, ValueError) as exc:
                attrs["signature_hash_algorithm"] = None
                field_limitations.append(
                    f"Signature hash metadata is unresolved for this certificate: {type(exc).__name__}."
                )

            attrs.update({"public_key_family": family, "key_size_bits": key_size})
            confidence = 0.99 if not field_limitations else 0.9
            method = "x509-parser"
        elif b"-----BEGIN CERTIFICATE-----" in raw:
            body = raw.split(b"-----BEGIN CERTIFICATE-----", 1)[1].split(b"-----END CERTIFICATE-----", 1)[0]
            try:
                base64.b64decode(b"".join(body.split()), validate=True)
                confidence = 0.82
            except ValueError:
                confidence = 0.55

        if field_limitations:
            attrs["limitations"] = list(dict.fromkeys(field_limitations))

        evidence = Evidence(
            detector=self.scanner_id,
            detector_version=self.version,
            method=method,
            location=SourceLocation(uri=request.target.locator, path=rel),
            fingerprint=evidence_fingerprint(
                detector=self.scanner_id,
                locator=request.target.locator,
                payload={"path": rel, "sha256": sha256, "certificate_index": certificate_index},
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
            confidence=confidence_from_score(
                confidence,
                "Parsed X.509 certificate with field-level isolation" if cert is not None else "Certificate envelope/container detected",
            ),
            tags=("certificate", "x509", "partial") if field_limitations else ("certificate", "x509"),
        )
