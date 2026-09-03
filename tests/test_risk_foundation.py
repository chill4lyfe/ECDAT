from ecdat.domain.enums import AssetType, RiskPriority
from ecdat.domain.models import CryptoAsset, RiskContext
from ecdat.risk.mosca_foundation import MoscaFoundationRiskEngine


def test_mosca_foundation_returns_unknown_without_required_context() -> None:
    asset = CryptoAsset(asset_type=AssetType.ALGORITHM, canonical_name="RSA")
    result = MoscaFoundationRiskEngine().assess(asset, RiskContext())
    assert result.priority is RiskPriority.UNKNOWN


def test_mosca_foundation_uses_configured_horizon_not_predicted_date() -> None:
    asset = CryptoAsset(asset_type=AssetType.ALGORITHM, canonical_name="RSA")
    result = MoscaFoundationRiskEngine().assess(
        asset,
        RiskContext(data_lifetime_years=8, migration_time_years=3, quantum_horizon_years=10),
    )
    assert result.priority is RiskPriority.ELEVATED
    assert result.assumptions["quantum_horizon_is_operator_configured"] is True
