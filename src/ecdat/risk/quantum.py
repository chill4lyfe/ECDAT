from __future__ import annotations

from ecdat.domain.enums import AssetType, QuantumPosture, RiskPriority
from ecdat.domain.models import CryptoAsset, RiskAssessment, RiskContext, RiskFactor

_VULNERABLE_FAMILIES = {
    "RSA", "DSA", "DH", "ECDSA", "ECDH", "ECC", "ED25519", "ED448", "EDDSA", "X25519", "X448"
}
_REDUCED_MARGIN_FAMILIES = {"AES", "CHACHA20", "HMAC", "SHA-2", "SHA2", "SHA-3", "SHA3"}
_RESISTANT_FAMILIES = {"ML-KEM", "ML-DSA", "SLH-DSA"}
_CLASSICALLY_WEAK = {"MD5", "SHA-1", "SHA1", "DES", "3DES", "RC4"}
_SIGNATURE_NAMES = {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EDDSA"}


def _norm(value: str | None) -> str:
    return (value or "").strip().upper()


def quantum_posture(asset: CryptoAsset) -> QuantumPosture:
    family = _norm(asset.algorithm_family)
    name = _norm(asset.canonical_name)
    if family in _RESISTANT_FAMILIES or name in _RESISTANT_FAMILIES:
        return QuantumPosture.RESISTANT
    if family in _VULNERABLE_FAMILIES or name in _VULNERABLE_FAMILIES or name in _SIGNATURE_NAMES:
        return QuantumPosture.VULNERABLE
    if family in _REDUCED_MARGIN_FAMILIES or name in _REDUCED_MARGIN_FAMILIES or name.startswith("AES"):
        return QuantumPosture.REDUCED_MARGIN
    if asset.asset_type in {AssetType.PROTOCOL, AssetType.LIBRARY, AssetType.CRYPTO_USAGE}:
        return QuantumPosture.CONTEXTUAL
    return QuantumPosture.UNKNOWN


def _priority(score: int) -> RiskPriority:
    if score >= 80:
        return RiskPriority.CRITICAL
    if score >= 60:
        return RiskPriority.ELEVATED
    if score >= 35:
        return RiskPriority.MODERATE
    return RiskPriority.LOW


def _ranked(value: str | None, table: dict[str, int]) -> int:
    return table.get((value or "").lower(), 0)


def _purpose(asset: CryptoAsset) -> str:
    values = [
        asset.properties.get("purpose"),
        asset.properties.get("purposes"),
        asset.properties.get("operation"),
        asset.properties.get("operations"),
        asset.properties.get("config_kind"),
        asset.properties.get("capability"),
    ]
    return " ".join(str(value) for value in values if value).lower()


def _is_potential_confidentiality_primitive(asset: CryptoAsset) -> bool:
    name = _norm(asset.canonical_name)
    family = _norm(asset.algorithm_family)
    purpose = _purpose(asset)
    if asset.asset_type is AssetType.CERTIFICATE:
        return False
    if any(token in purpose for token in ("sign", "signature", "jwt", "hash", "authentication")):
        return False
    if name in _SIGNATURE_NAMES or family in {"ECDSA", "DSA", "EDDSA", "ED25519", "ED448"}:
        return False
    return family in {"RSA", "DH", "ECDH", "ECC", "X25519", "X448"} or name in {"RSA", "DH", "ECDH", "ECC", "X25519", "X448"}


class QuantumRiskEngine:
    """Deterministic quantum-readiness prioritization.

    The engine applies Mosca's planning inequality using operator-supplied values:
    data lifetime (X) + migration lead time (Y) > quantum-risk horizon (Z).
    The score is a prioritization index, not a probability that a CRQC will exist by a date.
    """

    model_version = "quantum-readiness.v2"

    def assess(self, asset: CryptoAsset, context: RiskContext) -> RiskAssessment:
        posture = quantum_posture(asset)
        factors: list[RiskFactor] = []
        rationale: list[str] = []
        score = 0

        if posture is QuantumPosture.VULNERABLE:
            score += 35
            factors.append(RiskFactor(
                code="quantum-vulnerable",
                label="Quantum-vulnerable public-key primitive",
                contribution=35,
                rationale="The observed public-key family is vulnerable to a sufficiently capable Shor-style quantum attack.",
            ))
        elif posture is QuantumPosture.REDUCED_MARGIN:
            score += 8
            factors.append(RiskFactor(
                code="quantum-margin",
                label="Reduced quantum security margin",
                contribution=8,
                rationale="Symmetric/hash primitives retain security but generic quantum search reduces their effective margin.",
            ))
        elif posture is QuantumPosture.CONTEXTUAL:
            score += 5
            factors.append(RiskFactor(
                code="context-required",
                label="Context-dependent cryptography",
                contribution=5,
                rationale="The library or protocol must be resolved to the concrete primitive used at runtime before a definitive quantum posture can be assigned.",
            ))

        name = _norm(asset.canonical_name)
        family = _norm(asset.algorithm_family)
        if name in _CLASSICALLY_WEAK or family in _CLASSICALLY_WEAK:
            score += 30
            factors.append(RiskFactor(
                code="classical-weakness",
                label="Existing classical weakness",
                contribution=30,
                rationale="This primitive is weak or deprecated independently of the quantum threat and warrants remediation on classical-security grounds.",
            ))

        lifetime = context.data_lifetime_years
        migration = context.migration_time_years
        horizon = context.quantum_horizon_years
        mosca_margin: float | None = None
        if lifetime is not None and migration is not None and horizon is not None:
            exposure_window = lifetime + migration
            mosca_margin = horizon - exposure_window
            rationale.append(
                f"Mosca planning test: X={lifetime:g}y data lifetime + Y={migration:g}y migration lead time = {exposure_window:g}y; "
                f"Z={horizon:g}y configured quantum-risk horizon; margin={mosca_margin:g}y."
            )
            if mosca_margin <= -5:
                score += 25
                factors.append(RiskFactor(
                    code="mosca-overlap-severe",
                    label="Mosca window materially exceeds horizon",
                    contribution=25,
                    rationale="Data lifetime plus migration lead time exceeds the configured horizon by at least five years, leaving no credible migration margin under this scenario.",
                ))
            elif mosca_margin < 0:
                score += 20
                factors.append(RiskFactor(
                    code="mosca-overlap",
                    label="Mosca exposure overlap",
                    contribution=20,
                    rationale="Data lifetime plus migration lead time exceeds the configured quantum-risk horizon.",
                ))
            elif mosca_margin <= 2:
                score += 12
                factors.append(RiskFactor(
                    code="mosca-thin-margin",
                    label="Thin migration margin",
                    contribution=12,
                    rationale="Two years or less remain between the planning window and the configured horizon, making delay operationally risky.",
                ))
            elif mosca_margin <= 5:
                score += 6
                factors.append(RiskFactor(
                    code="mosca-watch-margin",
                    label="Limited planning margin",
                    contribution=6,
                    rationale="The planning margin is positive but narrow enough to warrant active migration preparation.",
                ))
        else:
            rationale.append("Mosca planning test was not calculated because data lifetime, migration lead time, or quantum-risk horizon is missing.")

        hndl = bool(
            posture is QuantumPosture.VULNERABLE
            and context.public_exposure is True
            and context.confidentiality_required is True
            and horizon is not None
            and lifetime is not None
            and lifetime > horizon
            and _is_potential_confidentiality_primitive(asset)
        )
        if hndl:
            score += 25
            factors.append(RiskFactor(
                code="hndl",
                label="Harvest-now-decrypt-later exposure",
                contribution=25,
                rationale="Observable ciphertext can be collected now while the protected information remains sensitive beyond the configured quantum horizon.",
            ))

        sensitivity_points = _ranked(context.data_sensitivity, {"medium": 3, "high": 7, "critical": 10, "restricted": 10})
        if sensitivity_points:
            score += sensitivity_points
            factors.append(RiskFactor(
                code="sensitivity",
                label="Data sensitivity",
                contribution=sensitivity_points,
                rationale=f"The associated data classification is {context.data_sensitivity}.",
            ))

        criticality_points = _ranked(context.business_criticality, {"medium": 2, "high": 5, "critical": 8})
        if criticality_points:
            score += criticality_points
            factors.append(RiskFactor(
                code="criticality",
                label="Business criticality",
                contribution=criticality_points,
                rationale=f"The owning workload is classified as {context.business_criticality} criticality.",
            ))

        if posture is QuantumPosture.VULNERABLE and context.public_exposure is True and not hndl:
            score += 3
            factors.append(RiskFactor(
                code="observable-surface",
                label="Externally observable attack surface",
                contribution=3,
                rationale="The workload is publicly exposed, increasing the operational importance of its quantum-vulnerable public-key cryptography.",
            ))

        score = min(100, score)
        rationale.extend(factor.rationale for factor in factors)
        rationale.append("The configured quantum-risk horizon is a planning assumption, not a prediction of when a cryptographically relevant quantum computer will exist.")

        return RiskAssessment(
            asset_id=asset.id,
            priority=_priority(score),
            model_version=self.model_version,
            rationale=tuple(dict.fromkeys(rationale)),
            assumptions={
                "quantum_horizon_years": horizon,
                "quantum_horizon_is_operator_configured": True,
                "data_lifetime_years": lifetime,
                "migration_time_years": migration,
                "data_sensitivity": context.data_sensitivity,
                "business_criticality": context.business_criticality,
                "public_exposure": context.public_exposure,
                "confidentiality_required": context.confidentiality_required,
                "context_profile": context.context_profile,
                "assumption_basis": context.assumption_basis,
                "mosca_equation": "X + Y > Z",
            },
            score=score,
            quantum_posture=posture,
            hndl_exposure=hndl,
            mosca_margin_years=mosca_margin,
            factors=tuple(factors),
        )
