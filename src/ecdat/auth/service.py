from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ecdat.auth.security import (
    OrganizationRole,
    hash_password,
    invitation_expiry,
    new_invitation_token,
    new_session_token,
    normalize_email,
    session_expiry,
    token_digest,
    verify_password,
)
from ecdat.persistence.sql.models import (
    InvitationRecord,
    MembershipRecord,
    MigrationPlanRecord,
    OrganizationRecord,
    ScanRecord,
    SessionRecord,
    UserRecord,
)
from ecdat.persistence.sql.session import SessionLocal

_DUMMY_PASSWORD_HASH = hash_password("ECDAT-Dummy-Password-47!")



class IdentityUnavailable(RuntimeError):
    pass


def _session_factory():
    if SessionLocal is None:
        raise IdentityUnavailable("Identity database is unavailable.")
    return SessionLocal


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")[:72] or "organization"
    return base


def bootstrap_required() -> bool:
    factory = _session_factory()
    try:
        with factory() as session:
            return (session.scalar(select(func.count()).select_from(UserRecord)) or 0) == 0
    except SQLAlchemyError as exc:
        raise IdentityUnavailable("Identity database is unavailable.") from exc


def _unique_slug(session, organization_name: str) -> str:
    base = _slugify(organization_name)
    slug = base
    counter = 2
    while session.scalar(select(OrganizationRecord.id).where(OrganizationRecord.slug == slug)) is not None:
        slug = f"{base[:82]}-{counter}"
        counter += 1
    return slug


def create_session(session, user_id: UUID, organization_id: UUID) -> tuple[SessionRecord, str]:
    token, digest = new_session_token()
    now = datetime.now(UTC)
    record = SessionRecord(
        id=uuid4(),
        user_id=user_id,
        active_organization_id=organization_id,
        token_hash=digest,
        created_at=now,
        expires_at=session_expiry(),
        last_seen_at=now,
    )
    session.add(record)
    return record, token


def bootstrap_platform(organization_name: str, display_name: str, email: str, password: str) -> tuple[UUID, UUID, str]:
    factory = _session_factory()
    organization_name = organization_name.strip()
    display_name = display_name.strip()
    if len(organization_name) < 2:
        raise ValueError("Organization name is required.")
    if len(display_name) < 2:
        raise ValueError("Your name is required.")
    normalized_email = normalize_email(email)
    password_hash = hash_password(password)
    now = datetime.now(UTC)
    try:
        with factory() as session:
            if (session.scalar(select(func.count()).select_from(UserRecord)) or 0) != 0:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Platform setup has already been completed.")
            organization = OrganizationRecord(id=uuid4(), name=organization_name, slug=_unique_slug(session, organization_name), created_at=now)
            user = UserRecord(id=uuid4(), email=normalized_email, display_name=display_name, password_hash=password_hash, is_active=True, created_at=now)

            # Persist the FK parents before inserting membership/session rows.  The identity
            # models deliberately do not use ORM relationships, so relying on SQLAlchemy to
            # infer insert order from object relationships can leave PostgreSQL seeing a child
            # row before its referenced user/organization during first-time bootstrap.
            session.add_all([organization, user])
            session.flush()

            membership = MembershipRecord(id=uuid4(), user_id=user.id, organization_id=organization.id, role=OrganizationRole.ADMIN.value, status="active", created_at=now)
            session.add(membership)
            session.flush()

            # Preserve pre-auth local assessment history by assigning otherwise-unowned rows
            # to the first organization established on this installation.
            session.execute(update(ScanRecord).where(ScanRecord.organization_id.is_(None)).values(organization_id=organization.id, created_by_user_id=user.id))
            session.execute(update(MigrationPlanRecord).where(MigrationPlanRecord.organization_id.is_(None)).values(organization_id=organization.id))
            _, token = create_session(session, user.id, organization.id)
            session.flush()
            session.commit()
            return user.id, organization.id, token
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The administrator account could not be created.") from exc
    except SQLAlchemyError as exc:
        raise IdentityUnavailable("Identity database is unavailable.") from exc


def login_organization_options(email: str, password: str) -> tuple[UserRecord, list[tuple[OrganizationRecord, MembershipRecord]]]:
    """Verify credentials before revealing organization memberships.

    This keeps multi-workspace discovery from becoming an email-enumeration endpoint: the
    organization list is returned only after the supplied password has been verified.
    """
    factory = _session_factory()
    try:
        normalized_email = normalize_email(email)
    except ValueError:
        normalized_email = email.strip().lower()
    try:
        with factory() as session:
            user = session.scalar(select(UserRecord).where(UserRecord.email == normalized_email))
            encoded = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
            password_valid = verify_password(password, encoded)
            if user is None or not user.is_active or not password_valid:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
            memberships = session.scalars(
                select(MembershipRecord).where(
                    MembershipRecord.user_id == user.id,
                    MembershipRecord.status == "active",
                ).order_by(MembershipRecord.created_at)
            ).all()
            if not memberships:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account has no active organization membership.")
            options: list[tuple[OrganizationRecord, MembershipRecord]] = []
            for membership in memberships:
                organization = session.get(OrganizationRecord, membership.organization_id)
                if organization is not None:
                    options.append((organization, membership))
            if not options:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account has no available organization workspace.")
            session.expunge(user)
            for organization, membership in options:
                session.expunge(organization)
                session.expunge(membership)
            return user, options
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise IdentityUnavailable("Identity database is unavailable.") from exc


def login(email: str, password: str, organization_id: UUID | None = None) -> tuple[UserRecord, OrganizationRecord, MembershipRecord, str]:
    factory = _session_factory()
    try:
        normalized_email = normalize_email(email)
    except ValueError:
        # Preserve a non-disclosing authentication response.
        normalized_email = email.strip().lower()
    try:
        with factory() as session:
            user = session.scalar(select(UserRecord).where(UserRecord.email == normalized_email))
            encoded = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
            password_valid = verify_password(password, encoded)
            if user is None or not user.is_active or not password_valid:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
            memberships = session.scalars(
                select(MembershipRecord).where(MembershipRecord.user_id == user.id, MembershipRecord.status == "active").order_by(MembershipRecord.created_at)
            ).all()
            if not memberships:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account has no active organization membership.")
            membership = next((item for item in memberships if item.organization_id == organization_id), None) if organization_id else memberships[0]
            if membership is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not authorized for that organization.")
            organization = session.get(OrganizationRecord, membership.organization_id)
            if organization is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization membership is unavailable.")
            _, token = create_session(session, user.id, organization.id)
            session.commit()
            session.refresh(user)
            session.refresh(organization)
            session.refresh(membership)
            return user, organization, membership, token
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise IdentityUnavailable("Identity database is unavailable.") from exc


def change_password(user_id: UUID, current_password: str, new_password: str, current_session_id: UUID) -> None:
    factory = _session_factory()
    try:
        with factory() as session:
            user = session.get(UserRecord, user_id)
            if user is None or not user.is_active or not verify_password(current_password, user.password_hash):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")
            if verify_password(new_password, user.password_hash):
                raise ValueError("New password must be different from the current password.")
            user.password_hash = hash_password(new_password)
            # A password change invalidates every other browser/session while preserving
            # the session that performed the verified change.
            session.execute(
                delete(SessionRecord).where(
                    SessionRecord.user_id == user_id,
                    SessionRecord.id != current_session_id,
                )
            )
            session.commit()
    except (HTTPException, ValueError):
        raise
    except SQLAlchemyError as exc:
        raise IdentityUnavailable("Identity database is unavailable.") from exc


def logout(session_id: UUID) -> None:
    factory = _session_factory()
    try:
        with factory() as session:
            record = session.get(SessionRecord, session_id)
            if record is not None:
                session.delete(record)
                session.commit()
    except SQLAlchemyError as exc:
        raise IdentityUnavailable("Identity database is unavailable.") from exc


def switch_organization(session_id: UUID, user_id: UUID, organization_id: UUID) -> None:
    factory = _session_factory()
    try:
        with factory() as session:
            membership = session.scalar(select(MembershipRecord).where(MembershipRecord.user_id == user_id, MembershipRecord.organization_id == organization_id, MembershipRecord.status == "active"))
            if membership is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not an active member of that organization.")
            auth_session = session.get(SessionRecord, session_id)
            if auth_session is None or auth_session.user_id != user_id:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid.")
            auth_session.active_organization_id = organization_id
            auth_session.last_seen_at = datetime.now(UTC)
            session.commit()
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise IdentityUnavailable("Identity database is unavailable.") from exc



def create_organization(user_id: UUID, organization_name: str) -> tuple[OrganizationRecord, MembershipRecord]:
    factory = _session_factory()
    organization_name = organization_name.strip()
    if len(organization_name) < 2:
        raise ValueError("Organization name is required.")
    now = datetime.now(UTC)
    try:
        with factory() as session:
            user = session.get(UserRecord, user_id)
            if user is None or not user.is_active:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
            organization = OrganizationRecord(id=uuid4(), name=organization_name, slug=_unique_slug(session, organization_name), created_at=now)
            # Flush the parent row before inserting the membership. The models use
            # UUID foreign keys without ORM relationship ordering, so relying on one
            # add_all() flush can let PostgreSQL see the membership first.
            session.add(organization)
            session.flush()
            membership = MembershipRecord(id=uuid4(), user_id=user_id, organization_id=organization.id, role=OrganizationRole.ADMIN.value, status="active", created_at=now)
            session.add(membership)
            session.commit()
            session.refresh(organization)
            session.refresh(membership)
            return organization, membership
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The organization workspace could not be created.") from exc
    except SQLAlchemyError as exc:
        raise IdentityUnavailable("Identity database is unavailable.") from exc

def create_invitation(organization_id: UUID, invited_by_user_id: UUID, email: str, role: OrganizationRole) -> tuple[InvitationRecord, str]:
    if role is OrganizationRole.ADMIN:
        # Admin grants are allowed, but deliberately explicit via the same audited invitation path.
        pass
    factory = _session_factory()
    normalized_email = normalize_email(email)
    now = datetime.now(UTC)
    token, digest = new_invitation_token()
    try:
        with factory() as session:
            existing_user = session.scalar(select(UserRecord).where(UserRecord.email == normalized_email))
            if existing_user is not None:
                existing_membership = session.scalar(select(MembershipRecord).where(MembershipRecord.user_id == existing_user.id, MembershipRecord.organization_id == organization_id))
                if existing_membership is not None and existing_membership.status == "active":
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That user is already an active organization member.")
            # Keep only one live invitation per organization/email. A newly issued link
            # invalidates older unused links rather than leaving multiple bearer credentials valid.
            session.execute(
                delete(InvitationRecord).where(
                    InvitationRecord.organization_id == organization_id,
                    InvitationRecord.email == normalized_email,
                    InvitationRecord.accepted_at.is_(None),
                )
            )
            invitation = InvitationRecord(
                id=uuid4(), organization_id=organization_id, email=normalized_email, role=role.value,
                token_hash=digest, invited_by_user_id=invited_by_user_id, created_at=now,
                expires_at=invitation_expiry(), accepted_at=None,
            )
            session.add(invitation)
            session.commit()
            session.refresh(invitation)
            return invitation, token
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An invitation could not be created for that address.") from exc
    except SQLAlchemyError as exc:
        raise IdentityUnavailable("Identity database is unavailable.") from exc


def accept_invitation(token: str, display_name: str, password: str) -> tuple[UserRecord, OrganizationRecord, MembershipRecord, str]:
    factory = _session_factory()
    digest = token_digest(token.strip())
    display_name = display_name.strip()
    if len(display_name) < 2:
        raise ValueError("Your name is required.")
    now = datetime.now(UTC)
    password_hash = hash_password(password)
    try:
        with factory() as session:
            invitation = session.scalar(select(InvitationRecord).where(InvitationRecord.token_hash == digest))
            if invitation is None or invitation.accepted_at is not None or invitation.expires_at <= now:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation is invalid, expired, or already used.")
            user = session.scalar(select(UserRecord).where(UserRecord.email == invitation.email))
            if user is None:
                user = UserRecord(id=uuid4(), email=invitation.email, display_name=display_name, password_hash=password_hash, is_active=True, created_at=now)
                session.add(user)
                session.flush()
            else:
                # An existing account proves possession by authenticating separately; do not let
                # an invitation silently replace its password.
                if not verify_password(password, user.password_hash):
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This email already has an account. Enter its existing password to accept the invitation.")
                if not user.is_active:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is suspended.")
            membership = session.scalar(select(MembershipRecord).where(MembershipRecord.user_id == user.id, MembershipRecord.organization_id == invitation.organization_id))
            if membership is None:
                membership = MembershipRecord(id=uuid4(), user_id=user.id, organization_id=invitation.organization_id, role=invitation.role, status="active", created_at=now)
                session.add(membership)
            else:
                membership.role = invitation.role
                membership.status = "active"
            invitation.accepted_at = now
            organization = session.get(OrganizationRecord, invitation.organization_id)
            if organization is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation organization no longer exists.")
            _, session_token = create_session(session, user.id, invitation.organization_id)
            session.commit()
            session.refresh(user)
            session.refresh(membership)
            session.refresh(organization)
            return user, organization, membership, session_token
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation acceptance conflicted with an existing account.") from exc
    except SQLAlchemyError as exc:
        raise IdentityUnavailable("Identity database is unavailable.") from exc
