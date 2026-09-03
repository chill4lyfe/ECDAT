from typing import Protocol

from ecdat.domain.models import CryptoAsset, RiskAssessment, RiskContext


class RiskEngine(Protocol):
    model_version: str

    def assess(self, asset: CryptoAsset, context: RiskContext) -> RiskAssessment: ...
