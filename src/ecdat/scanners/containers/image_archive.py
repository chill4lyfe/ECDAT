from __future__ import annotations

import io
import re
import tarfile
from pathlib import Path

from ecdat.confidence.model import confidence_from_score
from ecdat.domain.enums import AssetType, TargetKind
from ecdat.domain.models import CryptoAsset, Evidence, Finding, ScanRequest, SourceLocation
from ecdat.evidence.fingerprint import evidence_fingerprint
from ecdat.scanners.base import ScannerCapabilities
from ecdat.scanners.fs import relative_path, resolve_target_root

_LIBRARY_PATHS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(^|/)libssl(?:\.so(?:\.[0-9.]+)?)?$", re.I), "OpenSSL/libssl"),
    (re.compile(r"(^|/)libcrypto(?:\.so(?:\.[0-9.]+)?)?$", re.I), "OpenSSL/libcrypto"),
    (re.compile(r"(^|/)libsodium(?:\.so(?:\.[0-9.]+)?)?$", re.I), "libsodium"),
    (re.compile(r"(^|/)libgnutls(?:\.so(?:\.[0-9.]+)?)?$", re.I), "GnuTLS"),
    (re.compile(r"(^|/)(usr/)?bin/openssl$", re.I), "OpenSSL"),
)
_PACKAGE_RE = re.compile(
    r"(?ims)(?:^Package:\s*|^P:)(openssl|libssl[^\s]*|libsodium[^\s]*|gnutls[^\s]*)"
    r".*?(?:^Version:\s*|^V:)([^\s]+)"
)
_PACKAGE_DB_SUFFIXES = ("var/lib/dpkg/status", "lib/apk/db/installed")


class ContainerImageArchiveScanner:
    """Offline Docker/OCI image archive inspection.

    Image contents are never executed. A direct image target scans one TAR; a combined
    assessment scans TARs staged under ``sources/container-images``. Malformed image
    archives are isolated from other images so one source cannot erase evidence from
    the rest of the assessment.
    """

    scanner_id = "containers.image_archive"
    version = "0.5.0"
    capabilities = ScannerCapabilities(
        target_kinds=frozenset({TargetKind.CONTAINER_IMAGE, TargetKind.DIRECTORY, TargetKind.REPOSITORY}),
        deterministic=True,
    )

    async def scan(self, request: ScanRequest) -> tuple[Finding, ...]:
        root = resolve_target_root(request.target.locator)
        if root.is_file():
            return tuple(self._scan_archive(request, root, root.name))

        image_root = root / "sources" / "container-images"
        if not image_root.is_dir():
            image_root = root / "container-images"
        if not image_root.is_dir():
            return ()

        findings: list[Finding] = []
        for archive in sorted(path for path in image_root.rglob("*") if path.is_file() and path.name.lower().endswith((".tar", ".tar.gz", ".tgz"))):
            findings.extend(self._scan_archive(request, archive, relative_path(root, archive)))
        return tuple(findings)

    def _scan_archive(self, request: ScanRequest, archive: Path, logical_archive: str) -> list[Finding]:
        findings: list[Finding] = []
        seen: set[tuple[str, str | None]] = set()
        try:
            with tarfile.open(archive, mode="r:*") as outer:
                for member in outer.getmembers():
                    if not member.isfile() or member.size > 128 * 1024 * 1024:
                        continue
                    name = member.name
                    if not (name.endswith(".tar") or name.startswith("blobs/sha256/")):
                        continue
                    source = outer.extractfile(member)
                    if source is None:
                        continue
                    layer_bytes = source.read()
                    try:
                        with tarfile.open(fileobj=io.BytesIO(layer_bytes), mode="r:*") as layer:
                            findings.extend(self._inspect_layer(request, logical_archive, member.name, layer, seen))
                    except tarfile.TarError:
                        continue
        except (OSError, tarfile.TarError):
            return []
        return findings

    def _inspect_layer(
        self,
        request: ScanRequest,
        logical_archive: str,
        layer_name: str,
        layer: tarfile.TarFile,
        seen: set[tuple[str, str | None]],
    ) -> list[Finding]:
        findings: list[Finding] = []
        for member in layer.getmembers():
            if not member.isfile():
                continue
            normalized = member.name.lstrip("./")
            for pattern, canonical in _LIBRARY_PATHS:
                if pattern.search(normalized):
                    key = (canonical, None)
                    if key not in seen:
                        seen.add(key)
                        findings.append(self._finding(request, logical_archive, layer_name, normalized, canonical, None, "image-layer-path"))
            if normalized.endswith(_PACKAGE_DB_SUFFIXES) and member.size <= 3_000_000:
                source = layer.extractfile(member)
                if source is None:
                    continue
                text = source.read().decode("utf-8", errors="replace")
                for match in _PACKAGE_RE.finditer(text):
                    package, version = match.group(1), match.group(2)
                    canonical = "OpenSSL" if package.lower().startswith(("openssl", "libssl")) else package
                    key = (canonical.lower(), version)
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append(self._finding(request, logical_archive, layer_name, normalized, canonical, version, "image-package-database"))
        return findings

    def _finding(
        self,
        request: ScanRequest,
        logical_archive: str,
        layer: str,
        path: str,
        canonical: str,
        version: str | None,
        method: str,
    ) -> Finding:
        attrs = {
            "image_archive": logical_archive,
            "layer": layer,
            "layer_path": path,
            "offline_inspection": True,
            "runtime_execution_asserted": False,
        }
        evidence_path = f"{logical_archive}!/{layer}!/{path}"
        evidence = Evidence(
            detector=self.scanner_id,
            detector_version=self.version,
            method=method,
            location=SourceLocation(uri=request.target.locator, path=evidence_path),
            fingerprint=evidence_fingerprint(
                detector=self.scanner_id,
                locator=request.target.locator,
                payload={"archive": logical_archive, "layer": layer, "path": path, "asset": canonical, "version": version},
            ),
            summary=f"{canonical}{f' {version}' if version else ''} observed in offline container image layer {path}.",
            attributes=attrs,
        )
        return Finding(
            scanner_id=self.scanner_id,
            title=f"Container image cryptographic library: {canonical}",
            asset=CryptoAsset(
                asset_type=AssetType.LIBRARY,
                canonical_name=canonical,
                version=version,
                algorithm_family="system-crypto-library",
                properties=attrs,
            ),
            evidence=(evidence,),
            confidence=confidence_from_score(
                0.92 if version else 0.84,
                "Observed in offline image layer package metadata/path; runtime invocation is not asserted.",
            ),
            tags=("container", "image-archive", "offline"),
        )
