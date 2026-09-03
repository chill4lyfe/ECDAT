from __future__ import annotations

from ecdat.confidence.model import confidence_from_score
from ecdat.domain.enums import AssetType, QuantumPosture, RiskPriority
from ecdat.domain.models import Finding, RiskAssessment
from ecdat.migration.models import MigrationConstraints, MigrationRecommendation, TargetProfile

_CLASSICALLY_WEAK = {"MD5", "SHA-1", "SHA1", "DES", "3DES", "RC4"}
_SIGNATURES = {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EDDSA"}
_SIGNATURE_FAMILIES = {"ECDSA", "DSA", "EDDSA", "ED25519", "ED448"}
_KEX_FAMILIES = {"RSA", "DH", "ECDH", "ECC", "X25519", "X448"}


def _norm(value: str | None) -> str:
    return (value or "").strip().upper()


def _purpose(finding: Finding) -> str:
    name = _norm(finding.asset.canonical_name)
    family = _norm(finding.asset.algorithm_family)
    evidence_text = " ".join(
        [finding.title, *finding.tags]
        + [item.method for item in finding.evidence]
        + [str(item.attributes.get("config_kind", "")) for item in finding.evidence]
        + [str(item.attributes.get("purpose", "")) for item in finding.evidence]
        + [str(finding.asset.properties.get("purpose", ""))]
    ).upper()
    if name in _SIGNATURES or family in _SIGNATURE_FAMILIES or "SIGN" in evidence_text or "JWT" in evidence_text:
        return "signature"
    if finding.asset.asset_type is AssetType.CERTIFICATE:
        return "certificate"
    if "TLS" in evidence_text or finding.asset.asset_type is AssetType.PROTOCOL:
        return "transport"
    if family in _KEX_FAMILIES or name in _KEX_FAMILIES or "KEY-EXCHANGE" in evidence_text:
        return "key-establishment"
    return "general"


def _signature_targets(mode: str) -> tuple[TargetProfile, ...]:
    if mode == "performance":
        return (TargetProfile(
            name="ML-DSA-44",
            category="signature",
            standard="NIST FIPS 204",
            maturity="standardized",
            purpose="Lower-overhead standardized post-quantum signatures where the organization's security profile permits category-2 strength.",
            operational_notes=("Validate organization security-strength requirements before selecting the smaller parameter set.",),
        ),)
    if mode == "conservative":
        return (
            TargetProfile(
                name="ML-DSA-87",
                category="signature",
                standard="NIST FIPS 204",
                maturity="standardized",
                purpose="Higher-security standardized ML-DSA profile for risk-minimizing transition policy.",
                operational_notes=("Expect larger keys/signatures and higher operational cost than smaller ML-DSA parameter sets.",),
            ),
            TargetProfile(
                name="SLH-DSA",
                category="signature",
                standard="NIST FIPS 205",
                maturity="standardized",
                purpose="Hash-based alternative for environments that value algorithmic diversity.",
                operational_notes=("Large signatures can materially affect bandwidth, storage and certificate workflows.",),
            ),
        )
    return (TargetProfile(
        name="ML-DSA-65",
        category="signature",
        standard="NIST FIPS 204",
        maturity="standardized",
        purpose="Balanced standardized post-quantum signature profile for general enterprise migration planning.",
        operational_notes=("Benchmark signing, verification, certificate and message-size impact with representative workloads.",),
    ),)


def _kem_name(mode: str) -> str:
    return "ML-KEM-512" if mode == "performance" else "ML-KEM-1024" if mode == "conservative" else "ML-KEM-768"


def _targets(purpose: str, constraints: MigrationConstraints) -> tuple[TargetProfile, ...]:
    if purpose == "signature":
        return _signature_targets(constraints.mode)
    if purpose == "certificate":
        profile = "ML-DSA-87" if constraints.mode == "conservative" else "ML-DSA-44" if constraints.mode == "performance" else "ML-DSA-65"
        return (TargetProfile(
            name=f"{profile} certificate pilot",
            category="signature",
            standard="NIST FIPS 204; X.509/PKI ecosystem support must be validated",
            maturity="transitional",
            purpose="Pilot post-quantum certificate authentication without assuming that the surrounding CA, trust-store and relying-party ecosystem is already production-ready.",
            operational_notes=("Use a staged PKI pilot and preserve rollback/trust compatibility during transition.",),
        ),)
    if purpose == "transport" and constraints.prefer_hybrid:
        return (
            TargetProfile(
                name="X25519MLKEM768",
                category="hybrid_tls",
                standard="IETF RFC 10024 + NIST FIPS 203",
                maturity="standardized",
                purpose="TLS 1.3 hybrid key establishment that combines traditional X25519 with ML-KEM-768.",
                operational_notes=(
                    "Use only where both peers negotiate the standardized group.",
                    "Measure handshake size, CPU and latency under representative traffic before rollout.",
                ),
            ),
            TargetProfile(
                name=_kem_name(constraints.mode),
                category="kem",
                standard="NIST FIPS 203",
                maturity="standardized",
                purpose="Direct post-quantum key encapsulation for systems with native protocol support.",
            ),
        )
    if purpose == "key-establishment" and constraints.prefer_hybrid:
        return (
            TargetProfile(
                name=f"Classical + {_kem_name(constraints.mode)} transition",
                category="kem",
                standard="NIST FIPS 203; use only a protocol-defined hybrid construction",
                maturity="transitional",
                purpose="Preserve a classical key-establishment component during staged PQC adoption while the concrete protocol integration is validated.",
                operational_notes=("Do not invent an ad-hoc combiner; select the hybrid mechanism defined by the deployed protocol or cryptographic provider.",),
            ),
            TargetProfile(
                name=_kem_name(constraints.mode),
                category="kem",
                standard="NIST FIPS 203",
                maturity="standardized",
                purpose="Direct post-quantum key encapsulation once the surrounding protocol and both peers support it natively.",
            ),
        )
    if purpose in {"transport", "key-establishment"}:
        return (TargetProfile(
            name=_kem_name(constraints.mode),
            category="kem",
            standard="NIST FIPS 203",
            maturity="standardized",
            purpose="Post-quantum key encapsulation; protocol-specific hybridization must follow a defined interoperable construction rather than an ad-hoc combiner.",
        ),)
    return ()


def _effort(base: int, constraints: MigrationConstraints) -> int:
    if constraints.mode == "conservative":
        return min(21, base + 2)
    if constraints.mode == "performance":
        return max(1, base - 1)
    return base


class MigrationRecommendationEngine:
    def recommend(self, finding: Finding, risk: RiskAssessment, constraints: MigrationConstraints) -> MigrationRecommendation:
        name = _norm(finding.asset.canonical_name)
        family = _norm(finding.asset.algorithm_family)
        purpose = _purpose(finding)
        rationales: list[str] = []
        prerequisites: list[str] = []
        interoperability: list[str] = []
        performance: list[str] = []
        standards: list[str] = []

        mode_explanation = {
            "performance": "Runtime-efficiency policy favors smaller standardized parameter sets and lower migration overhead where security requirements permit.",
            "balanced": "Balanced policy targets broadly useful standardized parameter sets while retaining interoperability safeguards.",
            "conservative": "Risk-minimizing policy favors stronger parameter sets, additional validation and algorithmic diversity at higher operational cost.",
        }[constraints.mode]

        if name in _CLASSICALLY_WEAK or family in _CLASSICALLY_WEAK:
            strategy = "classical_remediation"
            targets = (TargetProfile(
                name="Modern approved classical primitive",
                category="classical",
                standard="Organization cryptographic policy / current platform guidance",
                maturity="review",
                purpose="Remove an already weak/deprecated primitive before or alongside PQC transition work.",
            ),)
            rationales.append("The primitive has an existing classical weakness; PQC migration does not replace basic cryptographic hygiene.")
            effort = _effort(3, constraints)
        elif risk.quantum_posture is QuantumPosture.VULNERABLE:
            targets = _targets(purpose, constraints)
            strategy = "hybrid_transition" if constraints.prefer_hybrid and purpose in {"transport", "key-establishment"} else "pqc_transition"
            rationales.extend([
                "The observed public-key primitive is quantum-vulnerable and requires a migration path rather than a simple risk label.",
                mode_explanation,
            ])
            if risk.hndl_exposure:
                rationales.append("HNDL exposure increases urgency because captured ciphertext can remain sensitive beyond the configured quantum-risk horizon.")
            if risk.priority in {RiskPriority.CRITICAL, RiskPriority.ELEVATED}:
                rationales.append(f"The contextual risk engine ranks this asset {risk.priority.value}.")
            if purpose == "certificate":
                prerequisites.append("Validate certificate profiles, CA issuance, trust stores and relying-party support before changing the certificate algorithm.")
                interoperability.append("Certificate migration may require parallel classical/PQC trust paths while ecosystem support matures.")
            elif purpose == "signature":
                prerequisites.append("Validate signing/verifying libraries, key management and protocol support for the selected PQC signature profile.")
                performance.append("Benchmark signature size, verification throughput and storage impact under representative traffic.")
            else:
                prerequisites.append("Validate both endpoints and cryptographic-provider support before changing key establishment.")
                performance.append("Benchmark handshake/message-size, CPU and latency impact before production rollout.")
            if constraints.mode == "conservative":
                prerequisites.append("Require interoperability test evidence, rollback procedure and staged canary validation before production promotion.")
            standards.extend(profile.standard for profile in targets)
            effort = _effort(8 if purpose in {"certificate", "transport"} else 5, constraints)
        elif risk.quantum_posture is QuantumPosture.REDUCED_MARGIN:
            strategy = "retain_monitor"
            targets = (TargetProfile(
                name="Retain with quantum-strength review",
                category="retain",
                standard="Current symmetric/hash policy",
                maturity="review",
                purpose="Retain where effective security strength remains adequate; review parameter sizes for long-lived sensitive data.",
            ),)
            rationales.append("Symmetric/hash primitives are not broken by Shor-style attacks; parameter strength and data lifetime drive the transition decision.")
            effort = _effort(2, constraints)
        else:
            strategy = "context_review"
            targets = (TargetProfile(
                name="Resolve concrete cryptographic configuration",
                category="review",
                standard="Evidence-driven review",
                maturity="review",
                purpose="Determine the actual primitive/configuration beneath this library, protocol or generic crypto usage before prescribing migration.",
            ),)
            rationales.append("The finding is contextual; recommending a PQC primitive without resolving actual usage would be misleading.")
            prerequisites.append("Trace configuration/runtime usage to a concrete cryptographic primitive.")
            effort = _effort(2, constraints)

        confidence_score = min(0.98, max(0.55, finding.confidence.score * (0.96 if purpose != "general" else 0.82)))
        priority_score = risk.score or 0
        if strategy == "classical_remediation":
            priority_score = max(priority_score, 82)
        if risk.hndl_exposure:
            priority_score = min(100, priority_score + 8)

        return MigrationRecommendation(
            asset_id=finding.asset.id,
            current_primitive=finding.asset.canonical_name,
            strategy=strategy,
            priority_score=priority_score,
            target_profiles=targets,
            rationale=tuple(rationales),
            prerequisites=tuple(prerequisites),
            interoperability_notes=tuple(interoperability),
            performance_notes=tuple(performance),
            effort_points=effort,
            confidence=confidence_from_score(confidence_score, "Recommendation derived from deterministic evidence and contextual risk."),
            standards_basis=tuple(dict.fromkeys(standards)),
        )
