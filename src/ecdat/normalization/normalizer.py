from __future__ import annotations

from collections import defaultdict
from typing import Any

from ecdat.domain.enums import AssetType
from ecdat.domain.models import CryptoAsset, Evidence, Finding

_NORMALIZATION_VERSION = "normalization.v2"

_ALGORITHM_ALIASES = {
    "rsa": "RSA",
    "rsa-2048": "RSA",
    "rsa2048": "RSA",
    "rsa-pss": "RSA-PSS",
    "dsa": "DSA",
    "dh": "DH",
    "ecdsa": "ECDSA",
    "ecdh": "ECDH",
    "ecc": "ECC",
    "ed25519": "Ed25519",
    "ed448": "Ed448",
    "eddsa": "EdDSA",
    "x25519": "X25519",
    "x448": "X448",
    "aes": "AES",
    "aes-gcm": "AES",
    "aesgcm": "AES",
    "3des": "3DES",
    "desede": "3DES",
    "des": "DES",
    "sha1": "SHA-1",
    "sha-1": "SHA-1",
    "sha224": "SHA-224",
    "sha-224": "SHA-224",
    "sha256": "SHA-256",
    "sha-256": "SHA-256",
    "sha384": "SHA-384",
    "sha-384": "SHA-384",
    "sha512": "SHA-512",
    "sha-512": "SHA-512",
    "md5": "MD5",
    "chacha20": "ChaCha20",
    "chacha20-poly1305": "ChaCha20-Poly1305",
    "ml-kem": "ML-KEM",
    "ml-dsa": "ML-DSA",
    "slh-dsa": "SLH-DSA",
}


def _canonical_name(name: str) -> str:
    cleaned = name.strip()
    return _ALGORITHM_ALIASES.get(cleaned.lower(), cleaned)


def _semantic_usage_key(asset: CryptoAsset) -> tuple[str, ...]:
    """Return only semantic usage dimensions, never source-location dimensions.

    Phase 9 intentionally does not put file path/line number into normalized identity:
    repeated observations remain one semantic asset with many evidence records rather
    than escaping correlation as duplicates.
    """

    props = asset.properties
    fields = ("purpose", "operation", "config_kind", "capability", "connector")
    return tuple(str(props.get(field) or "").strip().lower() for field in fields)


def _asset_key(asset: CryptoAsset) -> tuple[Any, ...]:
    canonical = _canonical_name(asset.canonical_name).lower()
    family = "" if asset.asset_type == AssetType.LIBRARY else (asset.algorithm_family or "").lower()
    base: tuple[Any, ...] = (
        asset.asset_type.value,
        canonical,
        family,
        asset.key_size_bits,
        (asset.mode or "").lower(),
    )

    if asset.asset_type == AssetType.LIBRARY:
        # Different deployed library versions can have materially different support
        # and migration characteristics. Unknown-version observations still correlate.
        return (*base, (asset.version or "").strip().lower())
    if asset.asset_type == AssetType.CERTIFICATE:
        # Two certificates may share a subject; content fingerprint is the identity
        # when structural parsing provided one.
        return (*base, str(asset.properties.get("sha256") or ""))
    if asset.asset_type == AssetType.KEY:
        key_id = asset.properties.get("key_id") or asset.properties.get("kid") or asset.properties.get("fingerprint")
        return (*base, str(key_id or ""))
    if asset.asset_type == AssetType.CRYPTO_USAGE:
        return (*base, *_semantic_usage_key(asset))
    return base


def _sorted_strings(values: set[str]) -> list[str]:
    return sorted((value for value in values if value), key=str.lower)


class FindingNormalizer:
    """Canonicalize and correlate findings while preserving occurrence provenance.

    Phase 9 keeps the existing canonical asset model, but correlation is now
    type-aware and non-destructive. Source paths never become identity keys, so
    repeated observations cannot escape normalization as duplicates. Instead, their
    paths/methods/operations are retained as occurrence metadata alongside immutable
    evidence records.
    """

    version = _NORMALIZATION_VERSION

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
            versions: set[str] = set()
            detectors: set[str] = set()
            source_paths: set[str] = set()
            methods: set[str] = set()
            purposes: set[str] = set()
            operations: set[str] = set()
            api_calls: set[str] = set()
            property_values: dict[str, list[Any]] = defaultdict(list)

            for finding in group:
                tags.update(finding.tags)
                detectors.add(finding.scanner_id)
                if finding.asset.version:
                    versions.add(finding.asset.version)
                for key, value in finding.asset.properties.items():
                    if value is not None and value not in property_values[key]:
                        property_values[key].append(value)
                for evidence in finding.evidence:
                    evidence_by_fingerprint[evidence.fingerprint] = evidence
                    if evidence.location.path:
                        source_paths.add(evidence.location.path)
                    methods.add(evidence.method)
                    api_call = evidence.attributes.get("api_call")
                    if isinstance(api_call, str):
                        api_calls.add(api_call)
                    operation = evidence.attributes.get("operation") or evidence.attributes.get("purpose")
                    if isinstance(operation, str):
                        operations.add(operation)
                purpose = finding.asset.properties.get("purpose")
                if isinstance(purpose, str):
                    purposes.add(purpose)
                if finding.confidence.score > best_score:
                    best_score = finding.confidence.score
                    best_level = finding.confidence.level
                reasons.extend(finding.confidence.reasons)

            # Preserve a stable representative scalar for backward compatibility.
            # Conflicting values are represented explicitly in *_values collections.
            properties: dict[str, Any] = {}
            for key, values in property_values.items():
                if len(values) == 1:
                    properties[key] = values[0]
                elif values:
                    properties[key] = values[0]
                    properties[f"{key}_values"] = values

            if versions:
                properties["detected_versions"] = _sorted_strings(versions)
            properties.update(
                {
                    "normalization_version": self.version,
                    "occurrence_count": len(evidence_by_fingerprint),
                    "source_paths": _sorted_strings(source_paths),
                    "evidence_methods": _sorted_strings(methods),
                    "detectors": _sorted_strings(detectors),
                }
            )
            if purposes:
                properties["purposes"] = _sorted_strings(purposes)
                properties.setdefault("purpose", sorted(purposes)[0])
            if operations:
                properties["operations"] = _sorted_strings(operations)
            if api_calls:
                properties["api_calls"] = _sorted_strings(api_calls)

            asset = first.asset.model_copy(
                update={
                    "version": next(iter(versions)) if len(versions) == 1 else first.asset.version,
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
                    finding.asset.key_size_bits or 0,
                    (finding.asset.mode or "").lower(),
                    str(finding.id),
                ),
            )
        )
