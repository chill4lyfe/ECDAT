from __future__ import annotations

import json
from pathlib import Path

from ecdat.domain.enums import TargetKind
from ecdat.domain.models import Finding, ScanRequest
from ecdat.integrations.cyclonedx.importer import CycloneDXImporter
from ecdat.scanners.base import ScannerCapabilities
from ecdat.scanners.fs import iter_files, relative_path, resolve_target_root


class CycloneDXBomScanner:
    """Imports CycloneDX crypto assets from a direct BOM or an assessment workspace.

    Directory support is intentionally content-detected instead of filename-only so a
    company may supply multiple independently named BOMs in one assessment without
    teaching ECDAT their naming convention.
    """

    scanner_id = "bom.cyclonedx"
    version = "0.2.0"
    capabilities = ScannerCapabilities(
        target_kinds=frozenset({TargetKind.BOM, TargetKind.DIRECTORY, TargetKind.REPOSITORY}),
        deterministic=True,
    )

    async def scan(self, request: ScanRequest) -> tuple[Finding, ...]:
        root = resolve_target_root(request.target.locator)
        if root.is_file():
            return CycloneDXImporter().import_file(root)

        findings: list[Finding] = []
        bom_root = root / "sources" / "boms"
        if not bom_root.is_dir():
            bom_root = root / "boms"
        if not bom_root.is_dir():
            return ()
        for path in iter_files(bom_root, suffixes=frozenset({".json"}), max_file_bytes=20_000_000):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, dict) or payload.get("bomFormat") != "CycloneDX":
                continue
            findings.extend(
                CycloneDXImporter().import_file(
                    path,
                    logical_path=relative_path(root, path),
                    source_uri=request.target.locator,
                )
            )
        return tuple(findings)
