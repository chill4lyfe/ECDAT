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
    """Memory-first catalog with best-effort PostgreSQL durability.

    Memory keeps unit tests and degraded local operation deterministic. When PostgreSQL is
    available, every completed scan is also persisted and can survive API restarts.
    """

    def __init__(self) -> None:
        self._summaries: dict[UUID, ScanSummary] = {}

    def put(self, summary: ScanSummary) -> None:
        self._summaries[summary.scan_id] = summary
        if SessionLocal is None:
            return
        try:
            with SessionLocal() as session:
                payload = summary.model_dump(mode="json")
                stmt = insert(ScanRecord).values(
                    id=summary.scan_id,
                    status=summary.status.value,
                    target_kind=summary.target.kind,
                    target_locator=summary.target.locator,
                    requested_at=datetime.now(UTC),
                    summary_json=payload,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[ScanRecord.id],
                    set_={
                        "status": summary.status.value,
                        "target_kind": summary.target.kind,
                        "target_locator": summary.target.locator,
                        "summary_json": payload,
                    },
                )
                session.execute(stmt)
                session.commit()
        except SQLAlchemyError:
            # Persistence must never erase a valid scan result. Readiness reports DB health.
            return

    def get(self, scan_id: UUID) -> ScanSummary | None:
        cached = self._summaries.get(scan_id)
        if cached is not None:
            return cached
        if SessionLocal is None:
            return None
        try:
            with SessionLocal() as session:
                record = session.get(ScanRecord, scan_id)
                if record and record.summary_json:
                    summary = ScanSummary.model_validate(record.summary_json)
                    self._summaries[scan_id] = summary
                    return summary
        except SQLAlchemyError:
            return None
        return None

    def latest(self) -> ScanSummary | None:
        if SessionLocal is None:
            return next(reversed(self._summaries.values())) if self._summaries else None
        try:
            with SessionLocal() as session:
                record = session.scalar(select(ScanRecord).order_by(ScanRecord.requested_at.desc()).limit(1))
                if record and record.summary_json:
                    summary = ScanSummary.model_validate(record.summary_json)
                    self._summaries[summary.scan_id] = summary
                    return summary
        except SQLAlchemyError:
            pass
        if not self._summaries:
            return None
        return next(reversed(self._summaries.values()))

    def list(self, limit: int = 30) -> list[tuple[ScanSummary, datetime]]:
        if SessionLocal is None:
            now = datetime.now(UTC)
            return [(summary, now) for summary in reversed(list(self._summaries.values()))][:limit]
        try:
            with SessionLocal() as session:
                records = session.scalars(
                    select(ScanRecord).order_by(ScanRecord.requested_at.desc()).limit(limit)
                ).all()
                result: list[tuple[ScanSummary, datetime]] = []
                for record in records:
                    if not record.summary_json:
                        continue
                    summary = ScanSummary.model_validate(record.summary_json)
                    self._summaries[summary.scan_id] = summary
                    result.append((summary, record.requested_at))
                if result:
                    return result
        except SQLAlchemyError:
            pass
        now = datetime.now(UTC)
        return [(summary, now) for summary in reversed(list(self._summaries.values()))][:limit]


catalog = ScanCatalog()
