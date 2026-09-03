"""platform persistence baseline

Revision ID: 0001_platform
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_platform"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("target_kind", sa.String(length=64), nullable=False),
        sa.Column("target_locator", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary_json", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_scans_status", "scans", ["status"])
    op.create_index("ix_scans_requested_at", "scans", ["requested_at"])
    op.create_table(
        "migration_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plan_json", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_migration_plans_scan_id", "migration_plans", ["scan_id"])
    op.create_index("ix_migration_plans_generated_at", "migration_plans", ["generated_at"])


def downgrade() -> None:
    op.drop_index("ix_migration_plans_generated_at", table_name="migration_plans")
    op.drop_index("ix_migration_plans_scan_id", table_name="migration_plans")
    op.drop_table("migration_plans")
    op.drop_index("ix_scans_requested_at", table_name="scans")
    op.drop_index("ix_scans_status", table_name="scans")
    op.drop_table("scans")
