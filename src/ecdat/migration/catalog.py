from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from ecdat.migration.models import MigrationRoadmap
from ecdat.persistence.sql.models import MigrationPlanRecord
from ecdat.persistence.sql.session import SessionLocal


class MigrationCatalog:
    def __init__(self) -> None:
        self._plans: dict[UUID, MigrationRoadmap] = {}

    def put(self, plan: MigrationRoadmap) -> None:
        self._plans[plan.plan_id] = plan
        if SessionLocal is None:
            return
        try:
            with SessionLocal() as session:
                payload = plan.model_dump(mode="json")
                stmt = insert(MigrationPlanRecord).values(
                    id=plan.plan_id,
                    scan_id=plan.scan_id,
                    generated_at=plan.generated_at,
                    plan_json=payload,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[MigrationPlanRecord.id],
                    set_={"plan_json": payload, "generated_at": plan.generated_at},
                )
                session.execute(stmt)
                session.commit()
        except SQLAlchemyError:
            return

    def get(self, plan_id: UUID) -> MigrationRoadmap | None:
        cached = self._plans.get(plan_id)
        if cached is not None:
            return cached
        if SessionLocal is None:
            return None
        try:
            with SessionLocal() as session:
                record = session.get(MigrationPlanRecord, plan_id)
                if record:
                    plan = MigrationRoadmap.model_validate(record.plan_json)
                    self._plans[plan_id] = plan
                    return plan
        except SQLAlchemyError:
            return None
        return None

    def latest(self) -> MigrationRoadmap | None:
        if SessionLocal is None:
            return next(reversed(self._plans.values())) if self._plans else None
        try:
            with SessionLocal() as session:
                record = session.scalar(
                    select(MigrationPlanRecord).order_by(MigrationPlanRecord.generated_at.desc()).limit(1)
                )
                if record:
                    plan = MigrationRoadmap.model_validate(record.plan_json)
                    self._plans[plan.plan_id] = plan
                    return plan
        except SQLAlchemyError:
            pass
        return next(reversed(self._plans.values())) if self._plans else None


migration_catalog = MigrationCatalog()
