from __future__ import annotations

from datetime import UTC, datetime

from ecdat.domain.enums import AssetType
from ecdat.domain.models import Finding, ScanSummary


class CycloneDXExporter:
    """CycloneDX 1.7 JSON projection for ECDAT discovery results.

    ECDAT-specific provenance and confidence remain namespaced properties; standardized
    cryptoProperties are emitted only when the ECDAT asset maps cleanly to the CDX model.
    """

    spec_version = "1.7"

    def export(self, summary: ScanSummary) -> dict[str, object]:
        components = [self._component(finding) for finding in summary.findings]
        return {
            "$schema": "https://cyclonedx.org/schema/bom-1.7.schema.json",
            "bomFormat": "CycloneDX",
            "specVersion": self.spec_version,
            "serialNumber": f"urn:uuid:{summary.scan_id}",
            "version": 1,
            "metadata": {
                "timestamp": datetime.now(UTC).isoformat(),
                "tools": {
                    "components": [
                        {"type": "application", "name": "ECDAT", "version": "1.0.0"}
                    ]
                },
                "properties": [
                    {"name": "ecdat:scan:status", "value": summary.status.value},
                    {"name": "ecdat:target:locator", "value": summary.target.locator},
                ],
            },
            "components": components,
        }


    def _component(self, finding: Finding) -> dict[str, object]:
        asset = finding.asset
        component: dict[str, object] = {
            "type": "library" if asset.asset_type is AssetType.LIBRARY else "cryptographic-asset",
            "bom-ref": f"asset:{asset.id}",
            "name": asset.canonical_name,
            "properties": [
                {"name": "ecdat:confidence:level", "value": finding.confidence.level.value},
                {"name": "ecdat:confidence:score", "value": f"{finding.confidence.score:.3f}"},
                {"name": "ecdat:scanner:id", "value": finding.scanner_id},
                {"name": "ecdat:evidence:count", "value": str(len(finding.evidence))},
            ],
        }
        if asset.version:
            component["version"] = asset.version

        crypto_properties = self._crypto_properties(finding)
        if crypto_properties:
            component["cryptoProperties"] = crypto_properties
        return component

    @staticmethod
    def _crypto_properties(finding: Finding) -> dict[str, object] | None:
        asset = finding.asset
        if asset.asset_type is AssetType.ALGORITHM:
            props: dict[str, object] = {"assetType": "algorithm"}
            algorithm: dict[str, object] = {}
            if asset.algorithm_family:
                algorithm["algorithmFamily"] = asset.algorithm_family
            if algorithm:
                props["algorithmProperties"] = algorithm
            return props
        if asset.asset_type is AssetType.CERTIFICATE:
            return {"assetType": "certificate"}
        if asset.asset_type is AssetType.PROTOCOL:
            return {"assetType": "protocol"}
        if asset.asset_type is AssetType.KEY:
            return {"assetType": "related-crypto-material"}
        return None

