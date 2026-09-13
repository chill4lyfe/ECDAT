from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select

from ecdat.api.routes.scans import REFERENCE_PATH, run_directory_scan
from ecdat.auth.security import OrganizationRole
from ecdat.domain.models import RiskContext
from ecdat.migration.catalog import migration_catalog
from ecdat.migration.models import MigrationConstraints
from ecdat.migration.planner import MigrationPlanner
from ecdat.persistence.sql.models import MembershipRecord
from ecdat.persistence.sql.session import SessionLocal


def validation_owner():
    """Resolve one local admin only for trusted in-container validation.

    This script is invoked through `docker compose exec`; it is not an API authentication
    bypass. Before first-time setup, validation output is intentionally unscoped and will be
    claimed by the first organization during bootstrap.
    """
    if SessionLocal is None:
        return None, None
    try:
        with SessionLocal() as session:
            membership = session.scalar(
                select(MembershipRecord)
                .where(MembershipRecord.status == "active", MembershipRecord.role == OrganizationRole.ADMIN.value)
                .order_by(MembershipRecord.created_at)
                .limit(1)
            )
            if membership is None:
                return None, None
            return membership.organization_id, membership.user_id
    except Exception:
        return None, None


async def main() -> None:
    organization_id, user_id = validation_owner()
    scan = await run_directory_scan(
        Path(REFERENCE_PATH),
        "Asteria Financial Services — Cryptographic Estate",
        [],
        RiskContext(
            data_lifetime_years=12,
            migration_time_years=4,
            quantum_horizon_years=15,
            data_sensitivity="high",
            business_criticality="high",
            public_exposure=True,
            confidentiality_required=True,
        ),
        metadata={
            "environment": "Production",
            "owner": "Security Architecture",
            "team": "Platform Cryptography",
            "source": "Reference enterprise workspace",
            "reference": "true",
        },
        organization_id=organization_id,
        created_by_user_id=user_id,
    )
    plan = MigrationPlanner().build(scan, MigrationConstraints())
    migration_catalog.put(plan, organization_id)
    coverage = scan.coverage
    q = scan.quantum_summary
    print("ECDAT reference estate")
    print(f"  ✓ {len(scan.findings)} normalized cryptographic assets")
    print(f"  ✓ {coverage.evidence_records if coverage else 0} retained evidence records across {coverage.files_observed if coverage else 0} observed files")
    print(f"  ✓ {q.vulnerable_assets if q else 0} quantum-vulnerable assets")
    print(f"  ✓ {q.hndl_exposed_assets if q else 0} HNDL-exposed assets")
    print(f"  ✓ {q.migration_blockers if q else 0} migration blockers")
    print(f"  ✓ {len(plan.waves)} migration waves / {plan.summary.total_actions} actions")
    print(f"  ✓ assessment persisted as {scan.scan_id}")
    print(f"  ✓ organization scope: {organization_id or 'pre-setup local validation'}")


if __name__ == "__main__":
    asyncio.run(main())
