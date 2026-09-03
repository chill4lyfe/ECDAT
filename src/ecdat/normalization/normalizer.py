from __future__ import annotations

from collections import defaultdict
from typing import Any

from ecdat.domain.models import CryptoAsset, Evidence, Finding

_ALGORITHM_ALIASES = {
    "rsa": "RSA",
    "rsa-2048": "RSA",
    "rsa2048": "RSA",
    "ecdsa": "ECDSA",
    "ecdh": "ECDH",
    "aes": "AES",
    "aes-gcm": "AES",
    "aesgcm": "AES",
    "3des": "3DES",
    "desede": "3DES",
    "des": "DES",
    "sha1": "SHA-1",
    "sha-1": "SHA-1",
    "sha256": "SHA-256",
    "sha-256": "SHA-256",
    "sha384": "SHA-384",
    "sha512": "SHA-512",
    "md5": "MD5",
    "chacha20": "ChaCha20",
    "chacha20-poly1305": "ChaCha20-Poly1305",
}


def _canonical_name(name: str) -> str:
    cleaned = name.strip()
    return _ALGORITHM_ALIASES.get(cleaned.lower(), cleaned)


def _asset_key(asset: CryptoAsset) -> tuple[Any, ...]:
    family = "" if asset.asset_type.value == "library" else (asset.algorithm_family or "").lower()
    return (
        asset.asset_type.value,
        _canonical_name(asset.canonical_name).lower(),
        family,
        asset.key_size_bits,
        (asset.mode or "").lower(),
    )


class FindingNormalizer:
    """Canonicalizes and correlates findings without discarding provenance."""

    def normalize(self, findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
        grouped: dict[tuple[Any, ...], list[Finding]] = defaultdict(list)
        for finding in findings:
            canonical_asset = finding.asset.model_copy(
                update={"canonical_name": _canonical_name(finding.asset.canonical_name)}
            )
            grouped[_asset_key(canonical_asset)].append(
                finding.model_copy(update={"asset": canonical_asset})
            )

        merged: list[Finding] = []
        for group in grouped.values():
            first = group[0]
            evidence_by_fingerprint: dict[str, Evidence] = {}
            tags: set[str] = set()
            reasons: list[str] = []
            best_score = 0.0
            best_level = first.confidence.level
            properties: dict[str, Any] = {}
            versions: set[str] = set()

            for finding in group:
                tags.update(finding.tags)
                properties.update(finding.asset.properties)
                if finding.asset.version:
                    versions.add(finding.asset.version)
                for evidence in finding.evidence:
                    evidence_by_fingerprint[evidence.fingerprint] = evidence
                if finding.confidence.score > best_score:
                    best_score = finding.confidence.score
                    best_level = finding.confidence.level
                reasons.extend(finding.confidence.reasons)

            if versions:
                properties["detected_versions"] = sorted(versions)
            asset = first.asset.model_copy(
                update={
                    "version": next(iter(versions)) if len(versions) == 1 else None,
                    "properties": properties,
                }
            )
            merged.append(
                first.model_copy(
                    update={
                        "asset": asset,
                        "evidence": tuple(evidence_by_fingerprint.values()),
                        "confidence": first.confidence.model_copy(
                            update={
                                "score": best_score,
                                "level": best_level,
                                "reasons": tuple(dict.fromkeys(reasons)),
                            }
                        ),
                        "tags": tuple(sorted(tags)),
                    }
                )
            )

        return tuple(
            sorted(
                merged,
                key=lambda finding: (
                    finding.asset.canonical_name.lower(),
                    finding.asset.asset_type.value,
                    str(finding.id),
                ),
            )
        )
