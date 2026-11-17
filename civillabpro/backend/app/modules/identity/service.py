"""Identity use cases: registration, login, token rotation, user administration, audit."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.database import utcnow
from app.core.errors import Conflict, Forbidden, Locked, NotFound, Unauthorized
from app.modules.identity.models import AuditLog, Organization, RefreshToken, User
from app.modules.identity.permissions import Role
from app.modules.identity.schemas import RegisterIn, TokenPair, UserCreate, UserUpdate


def audit(db: Session, user: User, action: str, entity_type: str, entity_id: uuid.UUID | None, summary: str, detail: dict[str, Any] | None = None) -> None:
    db.add(AuditLog(org_id=user.org_id, user_id=user.id, user_name=user.full_name, action=action, entity_type=entity_type,
                    entity_id=entity_id, summary=summary[:300], detail=detail or {}))


def _issue_tokens(db: Session, user: User, user_agent: str = "") -> TokenPair:
    access, ttl = security.create_access_token(user.id, user.org_id, user.role)
    token, token_hash, expires = security.new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires, user_agent=user_agent[:300]))
    return TokenPair(access_token=access, refresh_token=token, expires_in=ttl)


def register(db: Session, data: RegisterIn, user_agent: str = "") -> TokenPair:
    if not get_settings().allow_self_registration:
        raise Forbidden("Self-registration is switched off. Ask your administrator for an account.")
    email = data.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise Conflict("An account with this email already exists.")
    org = Organization(name=data.organization_name.strip(), kind=data.organization_kind)
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email=email, full_name=data.full_name.strip(), role=Role.OWNER.value,
                password_hash=security.hash_password(data.password), last_login_at=utcnow())
    db.add(user)
    db.flush()
    audit(db, user, "organization.created", "organization", org.id, f"Organisation {org.name} registered")
    return _issue_tokens(db, user, user_agent)


def login(db: Session, email: str, password: str, user_agent: str = "") -> TokenPair:
    s = get_settings()
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        security.hash_password(password)  # spend the same time whether or not the account exists
        raise Unauthorized("Incorrect email or password.")
    now = utcnow()
    if user.locked_until and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise Locked(f"Too many failed attempts. Try again in {minutes} minute(s).")
    if not security.verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= s.max_failed_logins:
            user.locked_until = now + timedelta(minutes=s.lockout_minutes)
            user.failed_logins = 0
        db.commit()  # the counter must survive the error response
        raise Unauthorized("Incorrect email or password.")
    if not user.is_active:
        raise Forbidden("This account is deactivated.")
    user.failed_logins, user.locked_until, user.last_login_at = 0, None, now
    if security.password_needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    return _issue_tokens(db, user, user_agent)


def refresh(db: Session, token: str, user_agent: str = "") -> TokenPair:
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == security.digest(token)))
    if row is None:
        raise Unauthorized("Session expired. Sign in again.")
    if row.revoked_at is not None:
        # A rotated token was presented again: assume it leaked and end every session of this user.
        db.execute(update(RefreshToken).where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=utcnow()))
        db.commit()
        raise Unauthorized("Session expired. Sign in again.")
    if row.expires_at <= utcnow():
        raise Unauthorized("Session expired. Sign in again.")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Session expired. Sign in again.")
    row.revoked_at = utcnow()
    return _issue_tokens(db, user, user_agent)


def logout(db: Session, token: str) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.token_hash == security.digest(token), RefreshToken.revoked_at.is_(None)).values(revoked_at=utcnow()))


def list_users(db: Session, org_id: uuid.UUID) -> list[User]:
    return list(db.scalars(select(User).where(User.org_id == org_id).order_by(User.full_name)))


def create_user(db: Session, actor: User, data: UserCreate) -> User:
    email = data.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise Conflict("An account with this email already exists.")
    if data.role == Role.OWNER and actor.role != Role.OWNER.value:
        raise Forbidden("Only an owner can create another owner.")
    user = User(org_id=actor.org_id, email=email, full_name=data.full_name.strip(), designation=data.designation, role=data.role.value,
                password_hash=security.hash_password(data.password))
    db.add(user)
    db.flush()
    audit(db, actor, "user.created", "user", user.id, f"User {user.full_name} added as {user.role}")
    return user


def update_user(db: Session, actor: User, user_id: uuid.UUID, data: UserUpdate) -> User:
    user = db.get(User, user_id)
    if user is None or user.org_id != actor.org_id:
        raise NotFound("User not found.")
    changes = data.model_dump(exclude_unset=True)
    touches_owner = user.role == Role.OWNER.value or changes.get("role") == Role.OWNER
    if touches_owner and actor.role != Role.OWNER.value:
        raise Forbidden("Only an owner can change an owner account.")
    losing_owner = user.role == Role.OWNER.value and (changes.get("role", Role.OWNER) != Role.OWNER or changes.get("is_active") is False)
    if losing_owner:
        owners = db.scalar(select(func.count()).select_from(User).where(User.org_id == actor.org_id, User.role == Role.OWNER.value, User.is_active))
        if (owners or 0) <= 1:
            raise Conflict("The organisation must keep at least one active owner.")
    for key, value in changes.items():
        setattr(user, key, value.value if isinstance(value, Role) else value)
    if changes.get("is_active") is False:
        db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=utcnow()))
    audit(db, actor, "user.updated", "user", user.id, f"User {user.full_name} updated", {k: str(v) for k, v in changes.items()})
    return user


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not security.verify_password(current, user.password_hash):
        raise Unauthorized("Current password is incorrect.")
    user.password_hash = security.hash_password(new)
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=utcnow()))
    audit(db, user, "user.password_changed", "user", user.id, "Password changed")


def recent_audit(db: Session, org_id: uuid.UUID, limit: int = 50) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.org_id == org_id).order_by(AuditLog.created_at.desc()).limit(limit)))
