from __future__ import annotations

import re
from pathlib import Path

from ecdat.confidence.model import confidence_from_score
from ecdat.domain.enums import AssetType, TargetKind
from ecdat.domain.models import CryptoAsset, Evidence, Finding, ScanRequest, SourceLocation
from ecdat.evidence.fingerprint import evidence_fingerprint
from ecdat.scanners.base import ScannerCapabilities
from ecdat.scanners.fs import iter_files, relative_path, resolve_target_root

_BINARY_SUFFIXES = frozenset({".so", ".dll", ".dylib", ".exe", ".bin", ".elf", ".a"})
_INDICATORS: tuple[tuple[bytes, str, str], ...] = (
    (b"libcrypto", "OpenSSL/libcrypto", "library-reference"),
    (b"libssl", "OpenSSL/libssl", "library-reference"),
    (b"OpenSSL", "OpenSSL", "string-signature"),
    (b"EVP_PKEY", "OpenSSL EVP", "import-or-string-signature"),
    (b"RSA_public_encrypt", "RSA", "openssl-symbol"),
    (b"AES_set_encrypt_key", "AES", "openssl-symbol"),
    (b"libsodium", "libsodium", "library-reference"),
    (b"CryptoPP", "Crypto++", "library-reference"),
)
_PRINTABLE = re.compile(rb"[ -~]{5,}")


class BinaryHeuristicScanner:
    scanner_id = "binaries.heuristic"
    version = "0.1.0"
    capabilities = ScannerCapabilities(
        target_kinds=frozenset({TargetKind.DIRECTORY, TargetKind.REPOSITORY, TargetKind.BINARY}),
        deterministic=True,
    )

    async def scan(self, request: ScanRequest) -> tuple[Finding, ...]:
        root = resolve_target_root(request.target.locator)
        findings: list[Finding] = []
        for path in iter_files(root, suffixes=_BINARY_SUFFIXES, max_file_bytes=20_000_000):
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if not self._looks_binary(raw):
                continue
            string_blob = b"\n".join(_PRINTABLE.findall(raw))
            for needle, canonical, method in _INDICATORS:
                if needle.lower() not in string_blob.lower():
                    continue
                findings.append(self._finding(request, root, path, canonical, method, needle.decode("ascii")))
        return tuple(findings)

    @staticmethod
    def _looks_binary(raw: bytes) -> bool:
        return raw.startswith(b"\x7fELF") or raw.startswith(b"MZ") or b"\x00" in raw[:1024]

    def _finding(
        self,
        request: ScanRequest,
        root: Path,
        path: Path,
        canonical: str,
        method: str,
        indicator: str,
    ) -> Finding:
        rel = relative_path(root, path)
        attrs = {
            "indicator": indicator,
            "binary_path": rel,
            "limitations": "String/symbol evidence does not prove runtime execution of the cryptographic primitive.",
        }
        evidence = Evidence(
            detector=self.scanner_id,
            detector_version=self.version,
            method=method,
            location=SourceLocation(uri=request.target.locator, path=rel),
            fingerprint=evidence_fingerprint(
                detector=self.scanner_id,
                locator=request.target.locator,
                payload={"path": rel, "indicator": indicator},
            ),
            summary=f"Binary crypto indicator {indicator} found in {rel}; runtime use is not asserted.",
            attributes=attrs,
        )
        if canonical in {"RSA", "AES"}:
            asset_type = AssetType.ALGORITHM
        elif "library" in method or canonical.startswith("OpenSSL") or canonical in {"libsodium", "Crypto++"}:
            asset_type = AssetType.LIBRARY
        else:
            asset_type = AssetType.CRYPTO_USAGE
        return Finding(
            scanner_id=self.scanner_id,
            title=f"Binary cryptographic indicator: {canonical}",
            asset=CryptoAsset(
                asset_type=asset_type,
                canonical_name=canonical,
                algorithm_family=canonical if canonical in {"RSA", "AES"} else None,
                properties=attrs,
            ),
            evidence=(evidence,),
            confidence=confidence_from_score(0.66, "Binary string/symbol heuristic; runtime execution is unverified"),
            tags=("binary", "heuristic"),
        )
