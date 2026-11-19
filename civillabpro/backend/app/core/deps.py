"""Request dependencies: the current user and permission guards."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core import security
from app.core.database import get_db
from app.core.errors import Forbidden, Unauthorized
from app.modules.identity.models import User
from app.modules.identity.permissions import P, has_permission

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db, scope="function")) -> User:
    if not token:
        raise Unauthorized("Sign in to continue.")
    try:
        payload = security.decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise Unauthorized("Session expired. Sign in again.") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Session expired. Sign in again.")
    return user


def require(permission: P) -> Callable[[User], User]:
    """Dependency factory: the caller must hold ``permission``."""

    def guard(user: User = Depends(current_user)) -> User:
        if not has_permission(user.role, permission):
            raise Forbidden(f"Your role does not allow this action ({permission.value}).")
        return user

    return guard
