from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ecdat.api.catalog import catalog
from ecdat.migration.catalog import migration_catalog
from ecdat.migration.models import MigrationConstraints, MigrationRoadmap
from ecdat.migration.planner import MigrationPlanner
from ecdat.risk.scenario import evaluate_scenario

router = APIRouter(prefix="/migration", tags=["migration"])


class MigrationPlanPayload(BaseModel):
    scan_id: UUID | None = None
    quantum_horizon_years: float | None = Field(default=None, gt=0, le=100)
    constraints: MigrationConstraints = Field(default_factory=MigrationConstraints)


@router.post("/plans", response_model=MigrationRoadmap)
async def create_plan(payload: MigrationPlanPayload) -> MigrationRoadmap:
    summary = catalog.get(payload.scan_id) if payload.scan_id else catalog.latest()
    if summary is None:
        raise HTTPException(status_code=404, detail="No scan is available for migration planning.")
    planning_summary = summary
    planning_horizon = payload.quantum_horizon_years
    if planning_horizon is not None:
        scenario = evaluate_scenario(summary, planning_horizon)
        planning_summary = summary.model_copy(update={
            "risk_assessments": scenario.assessments,
            "quantum_summary": scenario.quantum_summary,
        })
    plan = MigrationPlanner().build(planning_summary, payload.constraints)
    if planning_horizon is not None:
        plan = plan.model_copy(update={"risk_scenario_horizon_years": planning_horizon})
    migration_catalog.put(plan)
    return plan


@router.get("/plans/latest", response_model=MigrationRoadmap)
async def latest_plan() -> MigrationRoadmap:
    plan = migration_catalog.latest()
    if plan is None:
        raise HTTPException(status_code=404, detail="No migration plan is available for the active workspace.")
    return plan


@router.get("/plans/{plan_id}", response_model=MigrationRoadmap)
async def get_plan(plan_id: UUID) -> MigrationRoadmap:
    plan = migration_catalog.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Migration plan not found.")
    return plan
