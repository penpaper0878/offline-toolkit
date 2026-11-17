from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_user, require
from app.modules.identity import service
from app.modules.identity.models import User
from app.modules.identity.permissions import ROLE_LABELS, ROLE_PERMISSIONS, P, permissions_of
from app.modules.identity.schemas import AuditOut, MeOut, PasswordChange, RefreshIn, RegisterIn, TokenPair, UserCreate, UserOut, UserUpdate

auth = APIRouter(prefix="/auth", tags=["auth"])
users = APIRouter(prefix="/users", tags=["users"])


def _agent(request: Request) -> str:
    return request.headers.get("user-agent", "")


@auth.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED, summary="Create an organisation and its owner")
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)) -> TokenPair:
    return service.register(db, data, _agent(request))


@auth.post("/login", response_model=TokenPair, summary="OAuth2 password grant: username is the email")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenPair:
    return service.login(db, form.username, form.password, _agent(request))


@auth.post("/refresh", response_model=TokenPair, summary="Rotate the refresh token")
def refresh(data: RefreshIn, request: Request, db: Session = Depends(get_db)) -> TokenPair:
    return service.refresh(db, data.refresh_token, _agent(request))


@auth.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: RefreshIn, db: Session = Depends(get_db)) -> None:
    service.logout(db, data.refresh_token)


@auth.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user)) -> MeOut:
    return MeOut.model_validate({**UserOut.model_validate(user).model_dump(), "organization": user.organization,
                                 "permissions": sorted(p.value for p in permissions_of(user.role))})


@auth.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(data: PasswordChange, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    service.change_password(db, user, data.current_password, data.new_password)


@users.get("", response_model=list[UserOut])
def list_users(user: User = Depends(require(P.USER_MANAGE)), db: Session = Depends(get_db)) -> list[User]:
    return service.list_users(db, user.org_id)


@users.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, user: User = Depends(require(P.USER_MANAGE)), db: Session = Depends(get_db)) -> User:
    return service.create_user(db, user, data)


@users.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, data: UserUpdate, user: User = Depends(require(P.USER_MANAGE)), db: Session = Depends(get_db)) -> User:
    return service.update_user(db, user, user_id, data)


@users.get("/roles", summary="System roles and what each may do")
def roles(_: User = Depends(current_user)) -> list[dict[str, object]]:
    return [{"role": r.value, "label": ROLE_LABELS[r], "permissions": sorted(p.value for p in perms)} for r, perms in ROLE_PERMISSIONS.items()]


@users.get("/audit", response_model=list[AuditOut])
def audit_log(limit: int = 50, user: User = Depends(require(P.AUDIT_READ)), db: Session = Depends(get_db)) -> list[object]:
    return list(service.recent_audit(db, user.org_id, min(max(limit, 1), 200)))
