from typing import Protocol

from ecdat.domain.models import Finding, RiskAssessment
from ecdat.migration.models import MigrationConstraints, MigrationRecommendation


class MigrationEngine(Protocol):
    def recommend(
        self,
        finding: Finding,
        risk: RiskAssessment,
        constraints: MigrationConstraints,
    ) -> MigrationRecommendation: ...
