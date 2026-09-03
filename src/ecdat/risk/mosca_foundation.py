from ecdat.domain.enums import RiskPriority
from ecdat.domain.models import CryptoAsset, RiskAssessment, RiskContext


class MoscaFoundationRiskEngine:
    """Minimal, explainable Phase 0 implementation.

    This intentionally does NOT estimate when a cryptographically relevant quantum
    computer will exist. It consumes an operator-configured horizon assumption.
    """

    model_version = "phase0.mosca-foundation.v1"

    def assess(self, asset: CryptoAsset, context: RiskContext) -> RiskAssessment:
        required = (
            context.data_lifetime_years,
            context.migration_time_years,
            context.quantum_horizon_years,
        )
        if any(value is None for value in required):
            return RiskAssessment(
                asset_id=asset.id,
                priority=RiskPriority.UNKNOWN,
                model_version=self.model_version,
                rationale=(
                    "Insufficient context for Mosca-style evaluation; data lifetime, migration time, and configured quantum horizon are required.",
                ),
                assumptions={"quantum_horizon_is_operator_configured": True},
            )

        lifetime = float(context.data_lifetime_years or 0)
        migration = float(context.migration_time_years or 0)
        horizon = float(context.quantum_horizon_years or 0)
        exposure_window = lifetime + migration

        elevated = exposure_window > horizon
        rationale = (
            f"Data lifetime ({lifetime:g}y) + migration time ({migration:g}y) = {exposure_window:g}y.",
            f"Configured quantum-risk horizon = {horizon:g}y; this is an assumption, not a predicted CRQC date.",
            "Exposure window exceeds configured horizon." if elevated else "Exposure window does not exceed configured horizon.",
        )
        return RiskAssessment(
            asset_id=asset.id,
            priority=RiskPriority.ELEVATED if elevated else RiskPriority.LOW,
            model_version=self.model_version,
            rationale=rationale,
            assumptions={
                "quantum_horizon_years": horizon,
                "quantum_horizon_is_operator_configured": True,
                "phase0_model": True,
            },
        )
