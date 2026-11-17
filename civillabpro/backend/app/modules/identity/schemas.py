from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.identity.permissions import Role

OrgKind = Literal["consultant", "contractor", "government", "laboratory", "academic"]


def _strong(password: str) -> str:
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        raise ValueError("Use at least one letter and one digit.")
    return password


class RegisterIn(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    organization_kind: OrgKind = "consultant"
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

    _pw = field_validator("password")(_strong)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    kind: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    full_name: str
    designation: str
    role: Role
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class MeOut(UserOut):
    organization: OrganizationOut
    permissions: list[str]


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    designation: str = Field("", max_length=120)
    role: Role = Role.ENGINEER
    password: str = Field(min_length=10, max_length=128)

    _pw = field_validator("password")(_strong)


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=200)
    designation: str | None = Field(None, max_length=120)
    role: Role | None = None
    is_active: bool | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)

    _pw = field_validator("new_password")(_strong)


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_name: str
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    summary: str
    created_at: datetime
