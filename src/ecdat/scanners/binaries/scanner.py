from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ecdat.confidence.model import confidence_from_score
from ecdat.domain.enums import AssetType, TargetKind
from ecdat.domain.models import CryptoAsset, Evidence, Finding, ScanRequest, SourceLocation
from ecdat.evidence.fingerprint import evidence_fingerprint
from ecdat.scanners.base import ScannerCapabilities
from ecdat.scanners.binaries.inspector import iter_ar_members, looks_binary, printable_blob, profile_binary
from ecdat.scanners.fs import iter_files, relative_path, resolve_target_root


@dataclass(frozen=True, slots=True)
class BinaryIndicator:
    needle: bytes
    canonical: str
    method: str
    asset_type: AssetType
    family: str | None = None
    purpose: str | None = None
    confidence: float = 0.72


_INDICATORS: tuple[BinaryIndicator, ...] = (
    BinaryIndicator(b"libcrypto", "OpenSSL/libcrypto", "linked-library-string", AssetType.LIBRARY, confidence=0.76),
    BinaryIndicator(b"libssl", "OpenSSL/libssl", "linked-library-string", AssetType.LIBRARY, confidence=0.76),
    BinaryIndicator(b"OpenSSL", "OpenSSL", "library-string", AssetType.LIBRARY, confidence=0.65),
    BinaryIndicator(b"EVP_CIPHER_fetch", "OpenSSL EVP cipher usage", "openssl-symbol", AssetType.CRYPTO_USAGE, "OpenSSL", "encryption", 0.84),
    BinaryIndicator(b"EVP_MD_fetch", "OpenSSL EVP digest usage", "openssl-symbol", AssetType.CRYPTO_USAGE, "OpenSSL", "hashing", 0.84),
    BinaryIndicator(b"EVP_MAC_fetch", "OpenSSL EVP MAC usage", "openssl-symbol", AssetType.CRYPTO_USAGE, "OpenSSL", "message-authentication", 0.84),
    BinaryIndicator(b"EVP_KDF_fetch", "OpenSSL EVP KDF usage", "openssl-symbol", AssetType.CRYPTO_USAGE, "OpenSSL", "key-derivation", 0.84),
    BinaryIndicator(b"EVP_PKEY", "OpenSSL EVP PKEY usage", "openssl-symbol", AssetType.CRYPTO_USAGE, "OpenSSL", "public-key", 0.8),
    BinaryIndicator(b"RSA_public_encrypt", "RSA", "openssl-symbol", AssetType.ALGORITHM, "RSA", "encryption", 0.86),
    BinaryIndicator(b"RSA_sign", "RSA", "openssl-symbol", AssetType.ALGORITHM, "RSA", "signature", 0.86),
    BinaryIndicator(b"ECDSA_sign", "ECDSA", "openssl-symbol", AssetType.ALGORITHM, "ECDSA", "signature", 0.86),
    BinaryIndicator(b"ECDH_compute_key", "ECDH", "openssl-symbol", AssetType.ALGORITHM, "ECDH", "key-establishment", 0.86),
    BinaryIndicator(b"X25519", "X25519", "symbol-or-string", AssetType.ALGORITHM, "X25519", "key-establishment", 0.76),
    BinaryIndicator(b"X448", "X448", "symbol-or-string", AssetType.ALGORITHM, "X448", "key-establishment", 0.76),
    BinaryIndicator(b"ED25519", "Ed25519", "symbol-or-string", AssetType.ALGORITHM, "EdDSA", "signature", 0.76),
    BinaryIndicator(b"ED448", "Ed448", "symbol-or-string", AssetType.ALGORITHM, "EdDSA", "signature", 0.76),
    BinaryIndicator(b"AES_set_encrypt_key", "AES", "openssl-symbol", AssetType.ALGORITHM, "AES", "encryption", 0.86),
    BinaryIndicator(b"EVP_aes_256_gcm", "AES", "openssl-symbol", AssetType.ALGORITHM, "AES", "encryption", 0.86),
    BinaryIndicator(b"ChaCha20", "ChaCha20", "symbol-or-string", AssetType.ALGORITHM, "ChaCha20", "encryption", 0.74),
    BinaryIndicator(b"Poly1305", "Poly1305", "symbol-or-string", AssetType.ALGORITHM, "Poly1305", "message-authentication", 0.74),
    BinaryIndicator(b"HMAC_", "HMAC", "openssl-symbol", AssetType.ALGORITHM, "HMAC", "message-authentication", 0.8),
    BinaryIndicator(b"SHA256_", "SHA-256", "openssl-symbol", AssetType.ALGORITHM, "SHA-2", "hashing", 0.8),
    BinaryIndicator(b"SHA512_", "SHA-512", "openssl-symbol", AssetType.ALGORITHM, "SHA-2", "hashing", 0.8),
    BinaryIndicator(b"ML-KEM", "ML-KEM", "pqc-string", AssetType.ALGORITHM, "ML-KEM", "key-establishment", 0.72),
    BinaryIndicator(b"ML-DSA", "ML-DSA", "pqc-string", AssetType.ALGORITHM, "ML-DSA", "signature", 0.72),
    BinaryIndicator(b"libsodium", "libsodium", "linked-library-string", AssetType.LIBRARY, confidence=0.76),
    BinaryIndicator(b"CryptoPP", "Crypto++", "library-string", AssetType.LIBRARY, confidence=0.7),
    BinaryIndicator(b"bcrypt.dll", "Windows CNG/bcrypt", "linked-library-string", AssetType.LIBRARY, confidence=0.76),
    BinaryIndicator(b"Crypt32.dll", "Windows CryptoAPI", "linked-library-string", AssetType.LIBRARY, confidence=0.76),
)


class BinaryHeuristicScanner:
    scanner_id = "binaries.heuristic"
    version = "0.3.0"
    capabilities = ScannerCapabilities(
        target_kinds=frozenset({TargetKind.DIRECTORY, TargetKind.REPOSITORY, TargetKind.BINARY}),
        deterministic=True,
    )

    async def scan(self, request: ScanRequest) -> tuple[Finding, ...]:
        root = resolve_target_root(request.target.locator)
        findings: list[Finding] = []
        files_considered = 0
        binaries_scanned = 0
        unresolved_binaries = 0
        opaque_binaries = 0
        unreadable = 0

        # Phase 9 checks magic for every bounded file so extensionless ELF/PE artifacts
        # are not invisible. Full bytes are read only after the prefix looks binary.
        for path in iter_files(root, max_file_bytes=20_000_000):
            files_considered += 1
            try:
                with path.open("rb") as handle:
                    prefix = handle.read(4096)
                if not looks_binary(prefix, filename=path.name):
                    continue
                raw = path.read_bytes()
            except OSError:
                unreadable += 1
                continue
            if not looks_binary(raw[:4096], filename=path.name):
                continue
            binaries_scanned += 1
            profile = profile_binary(raw)
            if profile.opaque_or_packed_signal or profile.likely_stripped:
                opaque_binaries += 1

            before = len(findings)
            if profile.format == "static-archive":
                members = tuple(iter_ar_members(raw))
                if members:
                    for member_name, member_raw in members:
                        findings.extend(self._scan_blob(request, root, path, member_raw, profile.as_attributes(), archive_member=member_name))
                else:
                    findings.extend(self._scan_blob(request, root, path, raw, profile.as_attributes()))
            else:
                findings.extend(self._scan_blob(request, root, path, raw, profile.as_attributes()))
            if len(findings) == before:
                unresolved_binaries += 1

        self.last_metrics = {
            "files_considered": files_considered,
            "binary_files_scanned": binaries_scanned,
            "unresolved_binary_files": unresolved_binaries,
            "opaque_or_stripped_files": opaque_binaries,
            "unreadable_files": unreadable,
            "raw_findings": len(findings),
        }
        return tuple(findings)

    def _scan_blob(
        self,
        request: ScanRequest,
        root: Path,
        path: Path,
        raw: bytes,
        profile: dict[str, object],
        *,
        archive_member: str | None = None,
    ) -> list[Finding]:
        string_blob = printable_blob(raw).lower()
        findings: list[Finding] = []
        for indicator in _INDICATORS:
            if indicator.needle.lower() not in string_blob:
                continue
            findings.append(self._finding(request, root, path, indicator, profile, archive_member=archive_member))
        return findings

    def _finding(
        self,
        request: ScanRequest,
        root: Path,
        path: Path,
        indicator: BinaryIndicator,
        profile: dict[str, object],
        *,
        archive_member: str | None = None,
    ) -> Finding:
        rel = relative_path(root, path)
        attrs: dict[str, object] = {
            "indicator": indicator.needle.decode("ascii", errors="replace"),
            "binary_path": rel,
            **profile,
            "evidence_tier": "symbol-or-linked-library" if indicator.method in {"openssl-symbol", "linked-library-string"} else "embedded-string",
            "limitations": "Static import/symbol/string evidence does not prove runtime execution; stripped, packed or dynamically resolved cryptography may remain invisible.",
        }
        if archive_member:
            attrs["archive_member"] = archive_member
        if indicator.purpose:
            attrs["purpose"] = indicator.purpose
            attrs["operation"] = indicator.purpose
        evidence = Evidence(
            detector=self.scanner_id,
            detector_version=self.version,
            method=indicator.method,
            location=SourceLocation(uri=request.target.locator, path=rel, symbol=archive_member),
            fingerprint=evidence_fingerprint(
                detector=self.scanner_id,
                locator=request.target.locator,
                payload={"path": rel, "indicator": attrs["indicator"], "archive_member": archive_member},
            ),
            summary=f"Binary crypto indicator {attrs['indicator']} found in {rel}{f'::{archive_member}' if archive_member else ''}; runtime use is not asserted.",
            attributes=attrs,
        )
        return Finding(
            scanner_id=self.scanner_id,
            title=f"Binary cryptographic indicator: {indicator.canonical}",
            asset=CryptoAsset(
                asset_type=indicator.asset_type,
                canonical_name=indicator.canonical,
                algorithm_family=indicator.family,
                properties=attrs,
            ),
            evidence=(evidence,),
            confidence=confidence_from_score(indicator.confidence, "Binary format-aware static symbol/library/string evidence; runtime execution remains unverified"),
            tags=("binary", "heuristic", attrs["evidence_tier"]),
        )
