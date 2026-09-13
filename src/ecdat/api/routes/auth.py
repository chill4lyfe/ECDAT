from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from ecdat.auth.security import (
    ROLE_LABELS,
    SESSION_COOKIE,
    OrganizationRole,
    Principal,
    require_admin,
    require_authenticated,
)
from ecdat.auth.service import (
    IdentityUnavailable,
    accept_invitation,
    bootstrap_platform,
    bootstrap_required,
    create_invitation,
    create_organization,
    change_password,
    login,
    login_organization_options,
    logout,
    switch_organization,
)
from ecdat.persistence.sql.models import MembershipRecord, OrganizationRecord, SessionRecord, UserRecord
from ecdat.operations.maintenance import reset_organization_assessment_data
from ecdat.persistence.sql.session import SessionLocal
from ecdat.settings import get_settings

router = APIRouter(prefix="/auth", tags=["authentication"])


class BootstrapStatus(BaseModel):
    setup_required: bool


class OrganizationSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    role: str
    role_label: str


class AuthUser(BaseModel):
    id: UUID
    email: str
    display_name: str


class AuthState(BaseModel):
    user: AuthUser
    active_organization: OrganizationSummary
    organizations: list[OrganizationSummary]


class BootstrapPayload(BaseModel):
    organization_name: str = Field(min_length=2, max_length=160)
    display_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)


class LoginPayload(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)
    organization_id: UUID | None = None


class LoginOptionsPayload(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class LoginOptionsResponse(BaseModel):
    organizations: list[OrganizationSummary]


class SwitchOrganizationPayload(BaseModel):
    organization_id: UUID


class OrganizationCreatePayload(BaseModel):
    name: str = Field(min_length=2, max_length=160)


class InvitationPayload(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: OrganizationRole = OrganizationRole.ANALYST


class InvitationResponse(BaseModel):
    invitation_id: UUID
    email: str
    role: str
    expires_at: datetime
    invite_token: str


class AcceptInvitationPayload(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    display_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=256)


class MemberSummary(BaseModel):
    membership_id: UUID
    user_id: UUID
    email: str
    display_name: str
    role: str
    role_label: str
    status: str
    joined_at: datetime


class MemberUpdatePayload(BaseModel):
    role: OrganizationRole | None = None
    status: str | None = Field(default=None, pattern="^(active|suspended)$")


class PasswordChangePayload(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)
    confirm_password: str = Field(min_length=12, max_length=256)


class AssessmentResetPayload(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    confirmation: str = Field(min_length=5, max_length=32)


class AssessmentResetResponse(BaseModel):
    scans_deleted: int
    migration_plans_deleted: int
    graph_nodes_deleted: int
    graph_edges_deleted: int
    intake_workspaces_deleted: int = 0
    graph_cleanup_warning: str | None = None


class SessionSummary(BaseModel):
    id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    active_organization_id: UUID
    current: bool


class SessionRevokeResponse(BaseModel):
    revoked: int


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.auth_session_hours * 3600,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")


def _auth_state(principal: Principal) -> AuthState:
    if SessionLocal is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Identity database is unavailable.")
    try:
        with SessionLocal() as session:
            user = session.get(UserRecord, principal.user_id)
            if user is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
            memberships = session.scalars(
                select(MembershipRecord).where(
                    MembershipRecord.user_id == principal.user_id,
                    MembershipRecord.status == "active",
                ).order_by(MembershipRecord.created_at)
            ).all()
            organization_ids = [item.organization_id for item in memberships]
            organizations = {
                item.id: item
                for item in session.scalars(select(OrganizationRecord).where(OrganizationRecord.id.in_(organization_ids))).all()
            } if organization_ids else {}
            items = [
                OrganizationSummary(
                    id=membership.organization_id,
                    name=organizations[membership.organization_id].name,
                    slug=organizations[membership.organization_id].slug,
                    role=membership.role,
                    role_label=ROLE_LABELS.get(membership.role, membership.role.replace("_", " ").title()),
                )
                for membership in memberships
                if membership.organization_id in organizations
            ]
            active = next((item for item in items if item.id == principal.organization_id), None)
            if active is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active organization membership is unavailable.")
            return AuthState(
                user=AuthUser(id=user.id, email=user.email, display_name=user.display_name),
                active_organization=active,
                organizations=items,
            )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Identity service is unavailable.") from exc


@router.get("/bootstrap-status", response_model=BootstrapStatus)
def bootstrap_status() -> BootstrapStatus:
    try:
        return BootstrapStatus(setup_required=bootstrap_required())
    except IdentityUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/bootstrap", response_model=AuthState, status_code=status.HTTP_201_CREATED)
def bootstrap(payload: BootstrapPayload, response: Response) -> AuthState:
    try:
        _, _, token = bootstrap_platform(payload.organization_name, payload.display_name, payload.email, payload.password)
        _set_session_cookie(response, token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IdentityUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    # Resolve from the newly issued token without trusting client-provided organization state.
    # Constructing a tiny synthetic request is unnecessary: login re-verification would be wasteful,
    # so load state by the persisted session directly below.
    from ecdat.auth.security import token_digest
    if SessionLocal is None:
        raise HTTPException(status_code=503, detail="Identity database is unavailable.")
    with SessionLocal() as session:
        auth_session = session.scalar(select(SessionRecord).where(SessionRecord.token_hash == token_digest(token)))
        if auth_session is None:
            raise HTTPException(status_code=500, detail="Unable to establish administrator session.")
        user = session.get(UserRecord, auth_session.user_id)
        membership = session.scalar(select(MembershipRecord).where(MembershipRecord.user_id == auth_session.user_id, MembershipRecord.organization_id == auth_session.active_organization_id))
        if user is None or membership is None:
            raise HTTPException(status_code=500, detail="Unable to establish administrator session.")
        principal = Principal(user.id, auth_session.active_organization_id, OrganizationRole(membership.role), user.email, user.display_name, auth_session.id)
    return _auth_state(principal)


@router.post("/login-options", response_model=LoginOptionsResponse)
def login_options(payload: LoginOptionsPayload) -> LoginOptionsResponse:
    """Return authorized workspaces only after credential verification."""
    try:
        _, options = login_organization_options(payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.") from exc
    except IdentityUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return LoginOptionsResponse(organizations=[
        OrganizationSummary(
            id=organization.id,
            name=organization.name,
            slug=organization.slug,
            role=membership.role,
            role_label=ROLE_LABELS.get(membership.role, membership.role.replace("_", " ").title()),
        )
        for organization, membership in options
    ])


@router.post("/login", response_model=AuthState)
def login_route(payload: LoginPayload, response: Response) -> AuthState:
    try:
        user, organization, membership, token = login(payload.email, payload.password, payload.organization_id)
        _set_session_cookie(response, token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.") from exc
    except IdentityUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    # Load the session id just created so the returned state follows the same server-side path.
    from ecdat.auth.security import token_digest
    assert SessionLocal is not None
    with SessionLocal() as session:
        auth_session = session.scalar(select(SessionRecord).where(SessionRecord.token_hash == token_digest(token)))
        if auth_session is None:
            raise HTTPException(status_code=500, detail="Unable to establish session.")
        principal = Principal(user.id, organization.id, OrganizationRole(membership.role), user.email, user.display_name, auth_session.id)
    return _auth_state(principal)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_route(response: Response, principal: Principal = Depends(require_authenticated)) -> Response:
    try:
        logout(principal.session_id)
    except IdentityUnavailable:
        # Clear the browser session even if persistence is degraded.
        pass
    _clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=AuthState)
def me(principal: Principal = Depends(require_authenticated)) -> AuthState:
    return _auth_state(principal)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_own_password(payload: PasswordChangePayload, response: Response, principal: Principal = Depends(require_authenticated)) -> Response:
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="New password confirmation does not match.")
    try:
        change_password(principal.user_id, payload.current_password, payload.new_password, principal.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IdentityUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/organization/reset-assessment-data", response_model=AssessmentResetResponse)
async def reset_assessment_data(payload: AssessmentResetPayload, principal: Principal = Depends(require_admin)) -> AssessmentResetResponse:
    if payload.confirmation.strip().upper() != "RESET":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Type RESET to confirm organization assessment-data removal.")
    result = await reset_organization_assessment_data(principal.organization_id, principal.user_id, payload.current_password)
    return AssessmentResetResponse(
        scans_deleted=result.scans_deleted,
        migration_plans_deleted=result.migration_plans_deleted,
        graph_nodes_deleted=result.graph_nodes_deleted,
        graph_edges_deleted=result.graph_edges_deleted,
        intake_workspaces_deleted=result.intake_workspaces_deleted,
        graph_cleanup_warning=result.graph_cleanup_warning,
    )


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(principal: Principal = Depends(require_authenticated)) -> list[SessionSummary]:
    if SessionLocal is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Identity database is unavailable.")
    with SessionLocal() as session:
        records = session.scalars(
            select(SessionRecord).where(
                SessionRecord.user_id == principal.user_id,
                SessionRecord.expires_at > datetime.now(UTC),
            ).order_by(SessionRecord.last_seen_at.desc())
        ).all()
        return [
            SessionSummary(
                id=item.id,
                created_at=item.created_at,
                last_seen_at=item.last_seen_at,
                expires_at=item.expires_at,
                active_organization_id=item.active_organization_id,
                current=item.id == principal.session_id,
            )
            for item in records
        ]


@router.post("/sessions/revoke-others", response_model=SessionRevokeResponse)
def revoke_other_sessions(principal: Principal = Depends(require_authenticated)) -> SessionRevokeResponse:
    if SessionLocal is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Identity database is unavailable.")
    with SessionLocal() as session:
        records = session.scalars(
            select(SessionRecord).where(SessionRecord.user_id == principal.user_id, SessionRecord.id != principal.session_id)
        ).all()
        count = len(records)
        for item in records:
            session.delete(item)
        session.commit()
    return SessionRevokeResponse(revoked=count)


@router.post("/switch-organization", response_model=AuthState)
def switch_workspace(payload: SwitchOrganizationPayload, principal: Principal = Depends(require_authenticated)) -> AuthState:
    try:
        switch_organization(principal.session_id, principal.user_id, payload.organization_id)
    except IdentityUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    switched = Principal(principal.user_id, payload.organization_id, principal.role, principal.email, principal.display_name, principal.session_id)
    # Role may differ between organizations, so reload it rather than carrying the old role.
    if SessionLocal is None:
        raise HTTPException(status_code=503, detail="Identity database is unavailable.")
    with SessionLocal() as session:
        membership = session.scalar(select(MembershipRecord).where(MembershipRecord.user_id == principal.user_id, MembershipRecord.organization_id == payload.organization_id, MembershipRecord.status == "active"))
        if membership is None:
            raise HTTPException(status_code=403, detail="Organization membership is unavailable.")
        switched = Principal(principal.user_id, payload.organization_id, OrganizationRole(membership.role), principal.email, principal.display_name, principal.session_id)
    return _auth_state(switched)


@router.post("/organizations", response_model=OrganizationSummary, status_code=status.HTTP_201_CREATED)
def create_workspace(payload: OrganizationCreatePayload, principal: Principal = Depends(require_admin)) -> OrganizationSummary:
    try:
        organization, membership = create_organization(principal.user_id, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IdentityUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return OrganizationSummary(
        id=organization.id, name=organization.name, slug=organization.slug,
        role=membership.role, role_label=ROLE_LABELS[membership.role],
    )


@router.post("/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
def invite_member(payload: InvitationPayload, principal: Principal = Depends(require_admin)) -> InvitationResponse:
    try:
        invitation, token = create_invitation(principal.organization_id, principal.user_id, payload.email, payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IdentityUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return InvitationResponse(invitation_id=invitation.id, email=invitation.email, role=invitation.role, expires_at=invitation.expires_at, invite_token=token)


@router.post("/invitations/accept", response_model=AuthState)
def accept_invite(payload: AcceptInvitationPayload, response: Response) -> AuthState:
    try:
        user, organization, membership, token = accept_invitation(payload.token, payload.display_name, payload.password)
        _set_session_cookie(response, token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IdentityUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    from ecdat.auth.security import token_digest
    assert SessionLocal is not None
    with SessionLocal() as session:
        auth_session = session.scalar(select(SessionRecord).where(SessionRecord.token_hash == token_digest(token)))
        if auth_session is None:
            raise HTTPException(status_code=500, detail="Unable to establish session.")
        principal = Principal(user.id, organization.id, OrganizationRole(membership.role), user.email, user.display_name, auth_session.id)
    return _auth_state(principal)


@router.get("/members", response_model=list[MemberSummary])
def members(principal: Principal = Depends(require_admin)) -> list[MemberSummary]:
    if SessionLocal is None:
        raise HTTPException(status_code=503, detail="Identity database is unavailable.")
    try:
        with SessionLocal() as session:
            memberships = session.scalars(select(MembershipRecord).where(MembershipRecord.organization_id == principal.organization_id).order_by(MembershipRecord.created_at)).all()
            users = {item.id: item for item in session.scalars(select(UserRecord).where(UserRecord.id.in_([m.user_id for m in memberships]))).all()} if memberships else {}
            return [
                MemberSummary(
                    membership_id=item.id,
                    user_id=item.user_id,
                    email=users[item.user_id].email,
                    display_name=users[item.user_id].display_name,
                    role=item.role,
                    role_label=ROLE_LABELS.get(item.role, item.role.replace("_", " ").title()),
                    status=item.status,
                    joined_at=item.created_at,
                )
                for item in memberships if item.user_id in users
            ]
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Identity service is unavailable.") from exc


@router.patch("/members/{membership_id}", response_model=MemberSummary)
def update_member(membership_id: UUID, payload: MemberUpdatePayload, principal: Principal = Depends(require_admin)) -> MemberSummary:
    if SessionLocal is None:
        raise HTTPException(status_code=503, detail="Identity database is unavailable.")
    try:
        with SessionLocal() as session:
            membership = session.get(MembershipRecord, membership_id)
            if membership is None or membership.organization_id != principal.organization_id:
                raise HTTPException(status_code=404, detail="Membership not found.")
            if membership.user_id == principal.user_id and payload.status == "suspended":
                raise HTTPException(status_code=400, detail="You cannot suspend your own active administrator membership.")
            if membership.user_id == principal.user_id and payload.role is not None and payload.role is not OrganizationRole.ADMIN:
                raise HTTPException(status_code=400, detail="You cannot remove your own administrator role.")
            if payload.role is not None:
                membership.role = payload.role.value
            if payload.status is not None:
                membership.status = payload.status
                if payload.status == "suspended":
                    # Suspension must take effect immediately. Remove sessions whose
                    # active workspace is this organization so restoration requires
                    # a fresh sign-in rather than reviving an old browser session.
                    session.execute(
                        delete(SessionRecord).where(
                            SessionRecord.user_id == membership.user_id,
                            SessionRecord.active_organization_id == principal.organization_id,
                        )
                    )
            session.commit()
            user = session.get(UserRecord, membership.user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="User not found.")
            return MemberSummary(
                membership_id=membership.id, user_id=membership.user_id, email=user.email,
                display_name=user.display_name, role=membership.role,
                role_label=ROLE_LABELS.get(membership.role, membership.role.replace("_", " ").title()),
                status=membership.status, joined_at=membership.created_at,
            )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Identity service is unavailable.") from exc
