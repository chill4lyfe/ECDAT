from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ecdat.api.catalog import catalog
from ecdat.risk.scenario import RiskScenarioResult, evaluate_scenario

router = APIRouter(prefix="/risk", tags=["risk"])


class RiskScenarioPayload(BaseModel):
    scan_id: UUID | None = None
    quantum_horizon_years: float = Field(ge=1, le=100)


@router.post("/scenarios", response_model=RiskScenarioResult)
async def risk_scenario(payload: RiskScenarioPayload) -> RiskScenarioResult:
    summary = catalog.get(payload.scan_id) if payload.scan_id else catalog.latest()
    if summary is None:
        raise HTTPException(status_code=404, detail="No assessment is available for scenario analysis.")
    return evaluate_scenario(summary, payload.quantum_horizon_years)
