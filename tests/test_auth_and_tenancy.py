from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import ecdat.api.catalog as catalog_module
import ecdat.auth.service as auth_service
import ecdat.migration.catalog as migration_catalog_module
from ecdat.api.app import create_app
from ecdat.api.catalog import ScanCatalog
from ecdat.auth.security import OrganizationRole, Principal, hash_password, require_admin, require_analyst, verify_password
from ecdat.domain.enums import ScanStatus, TargetKind
from ecdat.domain.models import ScanSummary, ScanTarget
from ecdat.migration.catalog import MigrationCatalog
from ecdat.migration.models import MigrationConstraints
from ecdat.migration.planner import MigrationPlanner
from ecdat.persistence.sql.models import MembershipRecord, OrganizationRecord, UserRecord


def _summary() -> ScanSummary:
    return ScanSummary(
        scan_id=uuid4(),
        status=ScanStatus.COMPLETED,
        target=ScanTarget(kind=TargetKind.DIRECTORY, locator="/workspace/example", display_name="Example"),
        findings=(),
        graph_nodes=(),
        graph_edges=(),
        risk_assessments=(),
    )


def _principal(role: OrganizationRole) -> Principal:
    return Principal(
        user_id=uuid4(),
        organization_id=uuid4(),
        role=role,
        email="person@example.test",
        display_name="Example Person",
        session_id=uuid4(),
    )


def test_password_hash_is_salted_and_verifiable() -> None:
    password = "Correct-Horse-47-Battery"
    first = hash_password(password)
    second = hash_password(password)
    assert first != second
    assert verify_password(password, first)
    assert not verify_password("Wrong-Horse-47-Battery", first)
    assert not verify_password(password, "scrypt$not-a-valid-hash")


def test_role_guards_enforce_write_and_admin_boundaries() -> None:
    admin = _principal(OrganizationRole.ADMIN)
    analyst = _principal(OrganizationRole.ANALYST)
    viewer = _principal(OrganizationRole.VIEWER)

    assert require_analyst(admin) is admin
    assert require_analyst(analyst) is analyst
    assert require_admin(admin) is admin

    with pytest.raises(HTTPException) as analyst_denied:
        require_admin(analyst)
    assert analyst_denied.value.status_code == 403

    with pytest.raises(HTTPException) as viewer_denied:
        require_analyst(viewer)
    assert viewer_denied.value.status_code == 403


def test_catalog_does_not_cross_organization_boundary(monkeypatch) -> None:
    monkeypatch.setattr(catalog_module, "SessionLocal", None)
    catalog = ScanCatalog()
    organization_a = uuid4()
    organization_b = uuid4()
    summary = _summary()
    catalog.put(summary, organization_a, uuid4())

    assert catalog.get(summary.scan_id, organization_a) == summary
    assert catalog.get(summary.scan_id, organization_b) is None
    assert catalog.latest(organization_b) is None
    assert catalog.list(organization_id=organization_b) == []


def test_migration_catalog_does_not_cross_organization_boundary(monkeypatch) -> None:
    monkeypatch.setattr(migration_catalog_module, "SessionLocal", None)
    catalog = MigrationCatalog()
    organization_a = uuid4()
    organization_b = uuid4()
    plan = MigrationPlanner().build(_summary(), MigrationConstraints())
    catalog.put(plan, organization_a)

    assert catalog.get(plan.plan_id, organization_a) == plan
    assert catalog.get(plan.plan_id, organization_b) is None
    assert catalog.latest(organization_b) is None


@pytest.mark.parametrize(
    "path",
    [
        "/v1/scans/latest",
        "/v1/migration/plans/latest",
        f"/v1/reports/scans/{uuid4()}/executive",
        f"/v1/exports/scans/{uuid4()}/cyclonedx",
        "/v1/auth/members",
    ],
)
def test_sensitive_read_endpoints_require_authentication(path: str) -> None:
    with TestClient(create_app()) as client:
        response = client.get(path)
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required."


def test_catalog_reset_evicts_only_target_organization(monkeypatch) -> None:
    monkeypatch.setattr(catalog_module, "SessionLocal", None)
    catalog = ScanCatalog()
    organization_a = uuid4()
    organization_b = uuid4()
    summary_a = _summary()
    summary_b = _summary()
    catalog.put(summary_a, organization_a, uuid4())
    catalog.put(summary_b, organization_b, uuid4())

    assert catalog.clear_organization(organization_a) == 1
    assert catalog.get(summary_a.scan_id, organization_a) is None
    assert catalog.get(summary_b.scan_id, organization_b) == summary_b


def test_migration_catalog_reset_evicts_only_target_organization(monkeypatch) -> None:
    monkeypatch.setattr(migration_catalog_module, "SessionLocal", None)
    catalog = MigrationCatalog()
    organization_a = uuid4()
    organization_b = uuid4()
    plan_a = MigrationPlanner().build(_summary(), MigrationConstraints())
    plan_b = MigrationPlanner().build(_summary(), MigrationConstraints())
    catalog.put(plan_a, organization_a)
    catalog.put(plan_b, organization_b)

    assert catalog.clear_organization(organization_a) == 1
    assert catalog.get(plan_a.plan_id, organization_a) is None
    assert catalog.get(plan_b.plan_id, organization_b) == plan_b


def test_account_security_mutations_require_authentication() -> None:
    with TestClient(create_app()) as client:
        password_response = client.post(
            "/v1/auth/change-password",
            json={
                "current_password": "Current-Password-47!",
                "new_password": "Replacement-Password-48!",
                "confirm_password": "Replacement-Password-48!",
            },
        )
        reset_response = client.post(
            "/v1/auth/organization/reset-assessment-data",
            json={"current_password": "Current-Password-47!", "confirmation": "RESET"},
        )

    assert password_response.status_code == 401
    assert reset_response.status_code == 401


def test_create_organization_flushes_parent_before_membership(monkeypatch) -> None:
    user_id = uuid4()
    events: list[tuple[str, str | None]] = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, model, key):
            assert model is UserRecord
            assert key == user_id
            return type("User", (), {"is_active": True})()

        def add(self, record):
            events.append(("add", type(record).__name__))

        def flush(self):
            events.append(("flush", None))

        def commit(self):
            events.append(("commit", None))

        def refresh(self, record):
            events.append(("refresh", type(record).__name__))

    fake = FakeSession()
    monkeypatch.setattr(auth_service, "_session_factory", lambda: (lambda: fake))
    monkeypatch.setattr(auth_service, "_unique_slug", lambda session, name: "secondary-workspace")

    organization, membership = auth_service.create_organization(user_id, "Secondary Workspace")

    assert isinstance(organization, OrganizationRecord)
    assert isinstance(membership, MembershipRecord)
    assert membership.organization_id == organization.id
    assert membership.user_id == user_id
    assert membership.role == OrganizationRole.ADMIN.value
    assert events[:3] == [("add", "OrganizationRecord"), ("flush", None), ("add", "MembershipRecord")]
