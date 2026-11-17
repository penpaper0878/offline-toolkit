from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Invalid, NotFound
from app.modules.identity.models import User
from app.modules.identity.service import audit
from app.modules.projects.models import Project
from app.modules.projects.schemas import ProjectCreate, ProjectUpdate


def get_project(db: Session, org_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    """Fetch a project of this organisation. Another tenant's project reads as not found."""
    project = db.get(Project, project_id)
    if project is None or project.org_id != org_id:
        raise NotFound("Project not found.")
    return project


def list_projects(db: Session, org_id: uuid.UUID, q: str = "", status: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[Project], int]:
    stmt = select(Project).where(Project.org_id == org_id)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Project.name).like(like), func.lower(Project.code).like(like), func.lower(Project.client).like(like)))
    if status:
        stmt = stmt.where(Project.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Project.updated_at.desc()).limit(limit).offset(offset))
    return list(rows), total


def create_project(db: Session, actor: User, data: ProjectCreate) -> Project:
    code = data.code.strip()
    if db.scalar(select(Project.id).where(Project.org_id == actor.org_id, func.lower(Project.code) == code.lower())):
        raise Conflict(f"Job number {code} is already in use.")
    project = Project(org_id=actor.org_id, created_by=actor.id, **{**data.model_dump(), "code": code})
    db.add(project)
    db.flush()
    audit(db, actor, "project.created", "project", project.id, f"Project {project.code} {project.name} created")
    return project


def update_project(db: Session, actor: User, project_id: uuid.UUID, data: ProjectUpdate) -> Project:
    project = get_project(db, actor.org_id, project_id)
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(project, key, value)
    if project.start_date and project.end_date and project.end_date < project.start_date:
        raise Invalid("The end date is before the start date.")
    audit(db, actor, "project.updated", "project", project.id, f"Project {project.code} updated", {k: str(v) for k, v in changes.items()})
    return project


def delete_project(db: Session, actor: User, project_id: uuid.UUID) -> None:
    project = get_project(db, actor.org_id, project_id)
    audit(db, actor, "project.deleted", "project", project.id, f"Project {project.code} {project.name} deleted")
    db.delete(project)
