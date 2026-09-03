from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ScanRecord(Base):
    __tablename__ = "scans"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    target_kind: Mapped[str] = mapped_column(String(64))
    target_locator: Mapped[str] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    summary_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class MigrationPlanRecord(Base):
    __tablename__ = "migration_plans"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    scan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    plan_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
