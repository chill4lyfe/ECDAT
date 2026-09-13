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
        self._owners: dict[UUID, UUID | None] = {}

    def put(self, plan: MigrationRoadmap, organization_id: UUID | None = None) -> None:
        self._plans[plan.plan_id] = plan
        self._owners[plan.plan_id] = organization_id
        if SessionLocal is None:
            return
        try:
            with SessionLocal() as session:
                payload = plan.model_dump(mode="json")
                stmt = insert(MigrationPlanRecord).values(
                    id=plan.plan_id,
                    scan_id=plan.scan_id,
                    organization_id=organization_id,
                    generated_at=plan.generated_at,
                    plan_json=payload,
                )
                update_values: dict[str, object] = {"plan_json": payload, "generated_at": plan.generated_at}
                if organization_id is not None:
                    update_values["organization_id"] = organization_id
                stmt = stmt.on_conflict_do_update(index_elements=[MigrationPlanRecord.id], set_=update_values)
                session.execute(stmt)
                session.commit()
        except SQLAlchemyError:
            return

    def clear_organization(self, organization_id: UUID) -> int:
        """Evict cached migration plans owned by one organization."""
        plan_ids = [plan_id for plan_id, owner in self._owners.items() if owner == organization_id]
        for plan_id in plan_ids:
            self._plans.pop(plan_id, None)
            self._owners.pop(plan_id, None)
        return len(plan_ids)

    def get(self, plan_id: UUID, organization_id: UUID | None = None) -> MigrationRoadmap | None:
        cached = self._plans.get(plan_id)
        if cached is not None:
            owner = self._owners.get(plan_id)
            if organization_id is None or owner == organization_id:
                return cached
            # Legacy pre-auth plans can be claimed in PostgreSQL during first bootstrap
            # while the process cache still remembers them as unowned. Resolve that
            # transitional case from durable storage rather than returning a false 404.
            if owner is not None:
                return None
        if SessionLocal is None:
            return None
        try:
            with SessionLocal() as session:
                statement = select(MigrationPlanRecord).where(MigrationPlanRecord.id == plan_id)
                if organization_id is not None:
                    statement = statement.where(MigrationPlanRecord.organization_id == organization_id)
                record = session.scalar(statement)
                if record:
                    plan = MigrationRoadmap.model_validate(record.plan_json)
                    self._plans[plan_id] = plan
                    self._owners[plan_id] = record.organization_id
                    return plan
        except SQLAlchemyError:
            return None
        return None

    def latest(self, organization_id: UUID | None = None, scan_id: UUID | None = None) -> MigrationRoadmap | None:
        if SessionLocal is None:
            for plan_id, plan in reversed(list(self._plans.items())):
                if organization_id is not None and self._owners.get(plan_id) != organization_id:
                    continue
                if scan_id is not None and plan.scan_id != scan_id:
                    continue
                return plan
            return None
        try:
            with SessionLocal() as session:
                statement = select(MigrationPlanRecord).order_by(MigrationPlanRecord.generated_at.desc()).limit(1)
                if organization_id is not None:
                    statement = statement.where(MigrationPlanRecord.organization_id == organization_id)
                if scan_id is not None:
                    statement = statement.where(MigrationPlanRecord.scan_id == scan_id)
                record = session.scalar(statement)
                if record:
                    plan = MigrationRoadmap.model_validate(record.plan_json)
                    self._plans[plan.plan_id] = plan
                    self._owners[plan.plan_id] = record.organization_id
                    return plan
        except SQLAlchemyError:
            pass
        for plan_id, plan in reversed(list(self._plans.items())):
            if organization_id is not None and self._owners.get(plan_id) != organization_id:
                continue
            if scan_id is not None and plan.scan_id != scan_id:
                continue
            return plan
        return None


migration_catalog = MigrationCatalog()
