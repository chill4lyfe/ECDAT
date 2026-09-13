"""identity, organization membership and tenant scope

Revision ID: 0002_identity_tenancy
Revises: 0001_platform
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_identity_tenancy"
down_revision = "0001_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)
    op.create_index("ix_organizations_created_at", "organizations", ["created_at"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_created_at", "users", ["created_at"])

    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_index("ix_memberships_organization_id", "memberships", ["organization_id"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("active_organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_active_organization_id", "auth_sessions", ["active_organization_id"])
    op.create_index("ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True)
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    op.create_table(
        "organization_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=48), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_org_invites_org", "organization_invitations", ["organization_id"])
    op.create_index("ix_org_invites_email", "organization_invitations", ["email"])
    op.create_index("ix_org_invites_token", "organization_invitations", ["token_hash"], unique=True)
    op.create_index("ix_org_invites_expires", "organization_invitations", ["expires_at"])

    op.add_column("scans", sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("scans", sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_scans_organization", "scans", "organizations", ["organization_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_scans_creator", "scans", "users", ["created_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_scans_organization_id", "scans", ["organization_id"])
    op.create_index("ix_scans_created_by_user_id", "scans", ["created_by_user_id"])

    op.add_column("migration_plans", sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_migration_plans_organization", "migration_plans", "organizations", ["organization_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_migration_plans_organization_id", "migration_plans", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_migration_plans_organization_id", table_name="migration_plans")
    op.drop_constraint("fk_migration_plans_organization", "migration_plans", type_="foreignkey")
    op.drop_column("migration_plans", "organization_id")
    op.drop_index("ix_scans_created_by_user_id", table_name="scans")
    op.drop_index("ix_scans_organization_id", table_name="scans")
    op.drop_constraint("fk_scans_creator", "scans", type_="foreignkey")
    op.drop_constraint("fk_scans_organization", "scans", type_="foreignkey")
    op.drop_column("scans", "created_by_user_id")
    op.drop_column("scans", "organization_id")
    op.drop_table("organization_invitations")
    op.drop_table("auth_sessions")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("organizations")
