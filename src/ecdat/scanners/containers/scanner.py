from __future__ import annotations

import re
from pathlib import Path

from ecdat.confidence.model import confidence_from_score
from ecdat.domain.enums import AssetType, TargetKind
from ecdat.domain.models import CryptoAsset, Evidence, Finding, ScanRequest, SourceLocation
from ecdat.evidence.fingerprint import evidence_fingerprint
from ecdat.scanners.base import ScannerCapabilities
from ecdat.scanners.fs import iter_files, relative_path, resolve_target_root

_DOCKERFILE_RE = re.compile(r"^Dockerfile(?:\..+)?$")
_CRYPTO_PACKAGE_RE = re.compile(r"\b(openssl|libssl(?:-dev|\d+)?|libcrypto(?:\d+)?|gnutls|libgcrypt|libsodium)\b", re.I)


class ContainerDefinitionScanner:
    """Deterministic Dockerfile cryptography package scanner.

    This adapter inspects build definitions only; offline image-layer inspection is handled by
    the dedicated container archive adapter and no remote image execution is implied.
    """

    scanner_id = "containers.dockerfile"
    version = "0.1.0"
    capabilities = ScannerCapabilities(
        target_kinds=frozenset({TargetKind.DIRECTORY, TargetKind.REPOSITORY}),
        deterministic=True,
    )

    async def scan(self, request: ScanRequest) -> tuple[Finding, ...]:
        root = resolve_target_root(request.target.locator)
        findings: list[Finding] = []
        for path in iter_files(root, max_file_bytes=1_000_000):
            if not _DOCKERFILE_RE.match(path.name):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_no, line in enumerate(lines, 1):
                match = _CRYPTO_PACKAGE_RE.search(line)
                if not match:
                    continue
                findings.append(self._finding(request, root, path, line_no, match.group(1)))
        return tuple(findings)

    def _finding(self, request: ScanRequest, root: Path, path: Path, line: int, package: str) -> Finding:
        rel = relative_path(root, path)
        canonical = package.lower()
        attrs = {"declared_package": package, "container_definition": rel, "image_layers_inspected": False}
        evidence = Evidence(
            detector=self.scanner_id,
            detector_version=self.version,
            method="dockerfile-package-declaration",
            location=SourceLocation(uri=request.target.locator, path=rel, line_start=line),
            fingerprint=evidence_fingerprint(
                detector=self.scanner_id,
                locator=request.target.locator,
                payload={"path": rel, "line": line, "package": canonical},
            ),
            summary=f"Crypto-capable OS package {package} declared in {rel}:{line}.",
            attributes=attrs,
        )
        return Finding(
            scanner_id=self.scanner_id,
            title=f"Container crypto package: {package}",
            asset=CryptoAsset(
                asset_type=AssetType.LIBRARY,
                canonical_name=canonical,
                algorithm_family="system-crypto-library",
                properties=attrs,
            ),
            evidence=(evidence,),
            confidence=confidence_from_score(0.9, "Package declaration found in Dockerfile; image layers not yet inspected"),
            tags=("container", "dockerfile"),
        )
