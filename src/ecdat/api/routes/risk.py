from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ecdat.api.catalog import catalog
from ecdat.auth.security import Principal, require_analyst
from ecdat.risk.scenario import RiskScenarioResult, evaluate_scenario

router = APIRouter(prefix="/risk", tags=["risk"])


class RiskScenarioPayload(BaseModel):
    scan_id: UUID | None = None
    quantum_horizon_years: float = Field(ge=1, le=100)


@router.post("/scenarios", response_model=RiskScenarioResult)
async def risk_scenario(payload: RiskScenarioPayload, principal: Principal = Depends(require_analyst)) -> RiskScenarioResult:
    summary = catalog.get(payload.scan_id, principal.organization_id) if payload.scan_id else catalog.latest(principal.organization_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="No assessment is available for scenario analysis.")
    return evaluate_scenario(summary, payload.quantum_horizon_years)
