from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ecdat.persistence.sql.models import MembershipRecord, SessionRecord, UserRecord
from ecdat.persistence.sql.session import SessionLocal
from ecdat.settings import get_settings

SESSION_COOKIE = "ecdat_session"
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class OrganizationRole(StrEnum):
    ADMIN = "organization_admin"
    ANALYST = "security_analyst"
    VIEWER = "viewer"


ROLE_LABELS = {
    OrganizationRole.ADMIN.value: "Organization Administrator",
    OrganizationRole.ANALYST.value: "Security Architect / Analyst",
    OrganizationRole.VIEWER.value: "Viewer / Executive",
}


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    organization_id: UUID
    role: OrganizationRole
    email: str
    display_name: str
    session_id: UUID

    @property
    def can_write(self) -> bool:
        return self.role in {OrganizationRole.ADMIN, OrganizationRole.ANALYST}

    @property
    def is_admin(self) -> bool:
        return self.role is OrganizationRole.ADMIN


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 320 or not _EMAIL_RE.match(email):
        raise ValueError("Enter a valid email address.")
    return email


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    if len(password) > 256:
        raise ValueError("Password is too long.")
    groups = sum(
        (
            any(ch.islower() for ch in password),
            any(ch.isupper() for ch in password),
            any(ch.isdigit() for ch in password),
            any(not ch.isalnum() for ch in password),
        )
    )
    if groups < 3:
        raise ValueError("Password must use at least three of: lowercase, uppercase, numbers, symbols.")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        n,
        r,
        p,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n_text, r_text, p_text, salt_text, digest_text = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_text),
            r=int(r_text),
            p=int(p_text),
            dklen=len(expected),
        )
    except (binascii.Error, OverflowError, TypeError, ValueError):
        return False
    return hmac.compare_digest(actual, expected)


def new_session_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, token_digest(token)


def new_invitation_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, token_digest(token)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(hours=get_settings().auth_session_hours)


def invitation_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(hours=get_settings().auth_invitation_hours)


def _database_required() -> None:
    if SessionLocal is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Identity database is unavailable.")


def resolve_principal(request: Request) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    _database_required()
    now = datetime.now(UTC)
    digest = token_digest(token)
    try:
        assert SessionLocal is not None
        with SessionLocal() as session:
            record = session.scalar(select(SessionRecord).where(SessionRecord.token_hash == digest))
            if record is None or record.expires_at <= now:
                if record is not None:
                    session.delete(record)
                    session.commit()
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid.")
            user = session.get(UserRecord, record.user_id)
            membership = session.scalar(
                select(MembershipRecord).where(
                    MembershipRecord.user_id == record.user_id,
                    MembershipRecord.organization_id == record.active_organization_id,
                    MembershipRecord.status == "active",
                )
            )
            if user is None or not user.is_active or membership is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer authorized.")
            try:
                role = OrganizationRole(membership.role)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Membership role is not recognized.") from exc
            # Reduce DB churn while retaining useful session activity timestamps.
            if (now - record.last_seen_at).total_seconds() >= 300:
                record.last_seen_at = now
                session.commit()
            return Principal(
                user_id=user.id,
                organization_id=record.active_organization_id,
                role=role,
                email=user.email,
                display_name=user.display_name,
                session_id=record.id,
            )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Identity service is unavailable.") from exc


def require_authenticated(request: Request) -> Principal:
    return resolve_principal(request)


def require_analyst(principal: Principal = Depends(require_authenticated)) -> Principal:
    if not principal.can_write:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action requires Security Analyst or Organization Administrator access.")
    return principal


def require_admin(principal: Principal = Depends(require_authenticated)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action requires Organization Administrator access.")
    return principal
