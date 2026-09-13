from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from ecdat.domain.models import ScanSummary
from ecdat.persistence.sql.models import ScanRecord
from ecdat.persistence.sql.session import SessionLocal


class ScanCatalog:
    """Memory-first catalog with tenant-aware PostgreSQL durability.

    Domain scan summaries remain unchanged; organization and creator ownership live only at
    the persistence/access boundary. Optional organization arguments preserve deterministic
    unit tests that exercise the domain without an identity database.
    """

    def __init__(self) -> None:
        self._summaries: dict[UUID, ScanSummary] = {}
        self._owners: dict[UUID, UUID | None] = {}

    def put(
        self,
        summary: ScanSummary,
        organization_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
    ) -> None:
        self._summaries[summary.scan_id] = summary
        self._owners[summary.scan_id] = organization_id
        if SessionLocal is None:
            return
        try:
            with SessionLocal() as session:
                payload = summary.model_dump(mode="json")
                stmt = insert(ScanRecord).values(
                    id=summary.scan_id,
                    organization_id=organization_id,
                    created_by_user_id=created_by_user_id,
                    status=summary.status.value,
                    target_kind=summary.target.kind,
                    target_locator=summary.target.locator,
                    requested_at=datetime.now(UTC),
                    summary_json=payload,
                )
                update_values: dict[str, object] = {
                    "status": summary.status.value,
                    "target_kind": summary.target.kind,
                    "target_locator": summary.target.locator,
                    "summary_json": payload,
                }
                if organization_id is not None:
                    update_values["organization_id"] = organization_id
                if created_by_user_id is not None:
                    update_values["created_by_user_id"] = created_by_user_id
                stmt = stmt.on_conflict_do_update(index_elements=[ScanRecord.id], set_=update_values)
                session.execute(stmt)
                session.commit()
        except SQLAlchemyError:
            # Persistence must never erase a valid scan result. Readiness reports DB health.
            return

    def get(self, scan_id: UUID, organization_id: UUID | None = None) -> ScanSummary | None:
        cached = self._summaries.get(scan_id)
        if cached is not None:
            owner = self._owners.get(scan_id)
            if organization_id is None or owner == organization_id:
                return cached
            # A pre-auth scan may still be cached as unowned even after first bootstrap
            # claimed its persisted row. In that one case, consult PostgreSQL before
            # deciding it is outside the active organization.
            if owner is not None:
                return None
        if SessionLocal is None:
            return None
        try:
            with SessionLocal() as session:
                statement = select(ScanRecord).where(ScanRecord.id == scan_id)
                if organization_id is not None:
                    statement = statement.where(ScanRecord.organization_id == organization_id)
                record = session.scalar(statement)
                if record and record.summary_json:
                    summary = ScanSummary.model_validate(record.summary_json)
                    self._summaries[scan_id] = summary
                    self._owners[scan_id] = record.organization_id
                    return summary
        except SQLAlchemyError:
            return None
        return None

    def latest(self, organization_id: UUID | None = None) -> ScanSummary | None:
        if SessionLocal is None:
            for scan_id, summary in reversed(list(self._summaries.items())):
                if organization_id is None or self._owners.get(scan_id) == organization_id:
                    return summary
            return None
        try:
            with SessionLocal() as session:
                statement = select(ScanRecord).order_by(ScanRecord.requested_at.desc()).limit(1)
                if organization_id is not None:
                    statement = statement.where(ScanRecord.organization_id == organization_id)
                record = session.scalar(statement)
                if record and record.summary_json:
                    summary = ScanSummary.model_validate(record.summary_json)
                    self._summaries[summary.scan_id] = summary
                    self._owners[summary.scan_id] = record.organization_id
                    return summary
        except SQLAlchemyError:
            pass
        for scan_id, summary in reversed(list(self._summaries.items())):
            if organization_id is None or self._owners.get(scan_id) == organization_id:
                return summary
        return None

    def clear_organization(self, organization_id: UUID) -> int:
        """Evict cached summaries owned by one organization.

        Durable rows are removed by the maintenance service. Keeping cache cleanup
        explicit prevents a reset workspace from resurfacing stale in-memory results.
        """
        scan_ids = [scan_id for scan_id, owner in self._owners.items() if owner == organization_id]
        for scan_id in scan_ids:
            self._summaries.pop(scan_id, None)
            self._owners.pop(scan_id, None)
        return len(scan_ids)

    def list(self, limit: int = 30, organization_id: UUID | None = None) -> list[tuple[ScanSummary, datetime]]:
        if SessionLocal is None:
            now = datetime.now(UTC)
            return [
                (summary, now)
                for scan_id, summary in reversed(list(self._summaries.items()))
                if organization_id is None or self._owners.get(scan_id) == organization_id
            ][:limit]
        try:
            with SessionLocal() as session:
                statement = select(ScanRecord).order_by(ScanRecord.requested_at.desc()).limit(limit)
                if organization_id is not None:
                    statement = statement.where(ScanRecord.organization_id == organization_id)
                records = session.scalars(statement).all()
                result: list[tuple[ScanSummary, datetime]] = []
                for record in records:
                    if not record.summary_json:
                        continue
                    summary = ScanSummary.model_validate(record.summary_json)
                    self._summaries[summary.scan_id] = summary
                    self._owners[summary.scan_id] = record.organization_id
                    result.append((summary, record.requested_at))
                if result:
                    return result
        except SQLAlchemyError:
            pass
        now = datetime.now(UTC)
        return [
            (summary, now)
            for scan_id, summary in reversed(list(self._summaries.items()))
            if organization_id is None or self._owners.get(scan_id) == organization_id
        ][:limit]


catalog = ScanCatalog()
