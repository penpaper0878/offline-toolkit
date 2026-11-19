from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require
from app.modules.identity.models import User
from app.modules.identity.permissions import P
from app.modules.projects import service
from app.modules.projects.models import Project
from app.modules.projects.schemas import ProjectCreate, ProjectOut, ProjectPage, ProjectStatus, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


def _out(db: Session, projects: list[Project]) -> list[ProjectOut]:
    """Attach the read-side counts the project list shows."""
    from app.modules.structural.models import StructuralDesign  # read model only; projects own no structural logic

    ids = [p.id for p in projects]
    counts: dict[uuid.UUID, int] = {}
    if ids:
        rows = db.execute(select(StructuralDesign.project_id, func.count()).where(StructuralDesign.project_id.in_(ids)).group_by(StructuralDesign.project_id))
        counts = {pid: n for pid, n in rows}
    return [ProjectOut.model_validate(p).model_copy(update={"design_count": counts.get(p.id, 0)}) for p in projects]


@router.get("", response_model=ProjectPage)
def list_projects(q: str = Query("", max_length=100), status_: ProjectStatus | None = Query(None, alias="status"), limit: int = Query(50, ge=1, le=200),
                  offset: int = Query(0, ge=0), user: User = Depends(require(P.PROJECT_READ)), db: Session = Depends(get_db, scope="function")) -> ProjectPage:
    rows, total = service.list_projects(db, user.org_id, q, status_, limit, offset)
    return ProjectPage(items=_out(db, rows), total=total)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, user: User = Depends(require(P.PROJECT_WRITE)), db: Session = Depends(get_db, scope="function")) -> ProjectOut:
    return _out(db, [service.create_project(db, user, data)])[0]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, user: User = Depends(require(P.PROJECT_READ)), db: Session = Depends(get_db, scope="function")) -> ProjectOut:
    return _out(db, [service.get_project(db, user.org_id, project_id)])[0]


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: uuid.UUID, data: ProjectUpdate, user: User = Depends(require(P.PROJECT_WRITE)), db: Session = Depends(get_db, scope="function")) -> ProjectOut:
    return _out(db, [service.update_project(db, user, project_id, data)])[0]


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: uuid.UUID, user: User = Depends(require(P.PROJECT_DELETE)), db: Session = Depends(get_db, scope="function")) -> None:
    service.delete_project(db, user, project_id)
