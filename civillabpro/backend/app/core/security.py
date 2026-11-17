"""Password hashing and token handling.

Access tokens are short-lived JWTs. Refresh tokens are opaque random strings,
stored only as SHA-256 digests, rotated on every use and revocable.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings
from app.core.database import utcnow

_hasher = PasswordHasher()  # Argon2id with the library's current defaults


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> tuple[str, int]:
    s = get_settings()
    now = utcnow()
    ttl = s.access_token_minutes * 60
    payload = {"sub": str(user_id), "org": str(org_id), "role": role, "iat": now, "exp": now + timedelta(seconds=ttl), "typ": "access"}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm), ttl


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError when the token is invalid or expired."""
    s = get_settings()
    payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub", "org"]})
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return payload


def new_refresh_token() -> tuple[str, str, datetime]:
    """Return (token for the client, digest for the database, expiry)."""
    token = secrets.token_urlsafe(48)
    return token, digest(token), utcnow() + timedelta(days=get_settings().refresh_token_days)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
