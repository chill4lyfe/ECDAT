from __future__ import annotations

from ecdat.domain.enums import TargetKind
from ecdat.domain.models import Finding, ScanRequest
from ecdat.integrations.cyclonedx.importer import CycloneDXImporter
from ecdat.scanners.base import ScannerCapabilities
from ecdat.scanners.fs import resolve_target_root


class CycloneDXBomScanner:
    scanner_id = "bom.cyclonedx"
    version = "0.1.0"
    capabilities = ScannerCapabilities(
        target_kinds=frozenset({TargetKind.BOM}),
        deterministic=True,
    )

    async def scan(self, request: ScanRequest) -> tuple[Finding, ...]:
        path = resolve_target_root(request.target.locator)
        if not path.is_file():
            raise ValueError("CycloneDX BOM target must be a file")
        return CycloneDXImporter().import_file(path)
