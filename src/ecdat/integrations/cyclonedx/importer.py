from __future__ import annotations

import json
from pathlib import Path

from ecdat.confidence.model import confidence_from_score
from ecdat.domain.enums import AssetType
from ecdat.domain.models import CryptoAsset, Evidence, Finding, SourceLocation
from ecdat.evidence.fingerprint import evidence_fingerprint

_ASSET_TYPE_MAP = {
    "algorithm": AssetType.ALGORITHM,
    "certificate": AssetType.CERTIFICATE,
    "protocol": AssetType.PROTOCOL,
    "related-crypto-material": AssetType.KEY,
}


class CycloneDXImporter:
    scanner_id = "cyclonedx.import"
    version = "0.1.0"

    def import_file(self, path: str | Path, *, logical_path: str | None = None, source_uri: str | None = None) -> tuple[Finding, ...]:
        source = Path(path).expanduser().resolve()
        data = json.loads(source.read_text(encoding="utf-8"))
        if data.get("bomFormat") != "CycloneDX":
            raise ValueError("Not a CycloneDX BOM")

        findings: list[Finding] = []
        for component in data.get("components", []) or []:
            if not isinstance(component, dict):
                continue
            crypto = component.get("cryptoProperties")
            if not isinstance(crypto, dict):
                continue
            cdx_asset_type = str(crypto.get("assetType", ""))
            asset_type = _ASSET_TYPE_MAP.get(cdx_asset_type)
            if asset_type is None:
                continue

            algorithm = crypto.get("algorithmProperties") if isinstance(crypto.get("algorithmProperties"), dict) else {}
            family = algorithm.get("algorithmFamily") if isinstance(algorithm, dict) else None
            name = str(component.get("name") or family or cdx_asset_type)
            attrs = {
                "bom_ref": component.get("bom-ref"),
                "cyclonedx_spec_version": data.get("specVersion"),
                "cyclonedx_asset_type": cdx_asset_type,
            }
            evidence = Evidence(
                detector=self.scanner_id,
                detector_version=self.version,
                method="cyclonedx-1.7-json",
                location=SourceLocation(uri=source_uri or str(source), path=logical_path or source.name),
                fingerprint=evidence_fingerprint(
                    detector=self.scanner_id,
                    locator=str(source),
                    payload={"bom_ref": component.get("bom-ref"), "name": name, "asset_type": cdx_asset_type},
                ),
                summary=f"Cryptographic asset {name} imported from CycloneDX BOM.",
                attributes=attrs,
            )
            findings.append(
                Finding(
                    scanner_id=self.scanner_id,
                    title=f"CycloneDX cryptographic asset: {name}",
                    asset=CryptoAsset(
                        asset_type=asset_type,
                        canonical_name=name,
                        version=str(component.get("version")) if component.get("version") else None,
                        algorithm_family=str(family) if family else None,
                        properties=attrs,
                    ),
                    evidence=(evidence,),
                    confidence=confidence_from_score(0.99, "Structured CycloneDX cryptographic asset"),
                    tags=("cyclonedx", "bom-import"),
                )
            )
        return tuple(findings)
