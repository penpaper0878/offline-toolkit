"""Dashboard read model and global search: queries only, across module tables."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db, utcnow
from app.core.deps import require
from app.modules.identity.models import AuditLog, User
from app.modules.identity.permissions import P
from app.modules.projects.models import Project
from app.modules.structural.models import StructuralDesign

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary")
def summary(user: User = Depends(require(P.PROJECT_READ)), db: Session = Depends(get_db, scope="function")) -> dict[str, Any]:
    org = user.org_id
    by_project_status = dict(db.execute(select(Project.status, func.count()).where(Project.org_id == org).group_by(Project.status)).all())
    by_design_status = dict(db.execute(select(StructuralDesign.status, func.count()).where(StructuralDesign.org_id == org).group_by(StructuralDesign.status)).all())
    by_review = dict(db.execute(select(StructuralDesign.review_status, func.count()).where(StructuralDesign.org_id == org).group_by(StructuralDesign.review_status)).all())
    by_type = dict(db.execute(select(StructuralDesign.element_type, func.count()).where(StructuralDesign.org_id == org).group_by(StructuralDesign.element_type)).all())
    awaiting = db.scalar(select(func.count()).select_from(StructuralDesign).where(StructuralDesign.org_id == org, StructuralDesign.status == "ok",
                                                                                 StructuralDesign.review_status == "draft")) or 0

    recent = db.execute(
        select(StructuralDesign, Project.code, Project.name).join(Project, Project.id == StructuralDesign.project_id)
        .where(StructuralDesign.org_id == org).order_by(StructuralDesign.updated_at.desc()).limit(8)
    ).all()

    since = utcnow() - timedelta(days=13)
    start = since.replace(hour=0, minute=0, second=0, microsecond=0)
    events = db.scalars(select(AuditLog.created_at).where(AuditLog.org_id == org, AuditLog.created_at >= start, AuditLog.action.like("design.%"))).all()
    per_day: dict[str, int] = {(start + timedelta(days=i)).date().isoformat(): 0 for i in range(14)}
    for ts in events:
        key = ts.date().isoformat()
        if key in per_day:
            per_day[key] += 1

    feed = db.scalars(select(AuditLog).where(AuditLog.org_id == org).order_by(AuditLog.created_at.desc()).limit(10)).all()
    return {
        "projects": {"total": sum(by_project_status.values()), "by_status": by_project_status},
        "designs": {"total": sum(by_design_status.values()), "by_status": by_design_status, "by_review": by_review, "by_type": by_type,
                    "awaiting_approval": awaiting},
        "recent_designs": [
            {"id": str(d.id), "project_id": str(d.project_id), "project_code": code, "project_name": name, "element_type": d.element_type, "name": d.name,
             "status": d.status, "review_status": d.review_status, "revision": d.revision, "max_utilisation": d.max_utilisation,
             "designed_by_name": d.designed_by_name, "updated_at": d.updated_at.isoformat()}
            for d, code, name in recent
        ],
        "design_activity": [{"date": k, "count": v} for k, v in per_day.items()],
        "activity": [{"id": str(a.id), "user_name": a.user_name, "action": a.action, "summary": a.summary, "entity_type": a.entity_type,
                      "entity_id": str(a.entity_id) if a.entity_id else None, "created_at": a.created_at.isoformat()} for a in feed],
    }


@router.get("/search", summary="Search everywhere: projects and designs of the organisation")
def search(q: str = Query(..., min_length=1, max_length=100), limit: int = Query(20, ge=1, le=50), user: User = Depends(require(P.PROJECT_READ)),
           db: Session = Depends(get_db, scope="function")) -> list[dict[str, Any]]:
    like = f"%{q.strip().lower()}%"
    hits: list[dict[str, Any]] = []
    projects = db.scalars(select(Project).where(Project.org_id == user.org_id, or_(func.lower(Project.name).like(like), func.lower(Project.code).like(like),
                                                                                    func.lower(Project.client).like(like))).order_by(Project.updated_at.desc()).limit(limit))
    for p in projects:
        hits.append({"kind": "project", "id": str(p.id), "title": f"{p.code}  {p.name}", "subtitle": p.client or p.location, "project_id": str(p.id)})
    designs = db.execute(
        select(StructuralDesign, Project.code).join(Project, Project.id == StructuralDesign.project_id)
        .where(StructuralDesign.org_id == user.org_id, func.lower(StructuralDesign.name).like(like)).order_by(StructuralDesign.updated_at.desc()).limit(limit)
    ).all()
    for d, code in designs:
        hits.append({"kind": "design", "id": str(d.id), "title": f"{d.element_type.capitalize()} {d.name}", "subtitle": f"{code}  R{d.revision}  {d.status}",
                     "project_id": str(d.project_id), "element_type": d.element_type})
    return hits[:limit]
