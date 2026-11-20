"""Project archives (export, import) and the snapshot of a single-organisation SQLite database."""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import __version__
from app.core.database import get_engine
from app.core.errors import Conflict, Invalid
from app.modules.identity.models import Organization, User
from app.modules.identity.service import audit
from app.modules.projects.models import Project
from app.modules.projects.service import get_project
from app.modules.structural.domain.registry import ELEMENTS
from app.modules.structural.models import StructuralDesign, StructuralDesignRevision
from app.modules.transfer.schemas import FORMAT, FORMAT_VERSION, DesignRecord, ProjectArchive, ProjectRecord, RevisionRecord

_PROJECT_FIELDS = ("code", "name", "client", "location", "state", "project_type", "status", "description", "start_date", "end_date")


def export_project(db: Session, actor: User, project_id: uuid.UUID) -> ProjectArchive:
    project = get_project(db, actor.org_id, project_id)
    designs = list(db.scalars(select(StructuralDesign).where(StructuralDesign.project_id == project.id).order_by(StructuralDesign.created_at)))
    revs: dict[uuid.UUID, list[StructuralDesignRevision]] = {}
    if designs:
        for r in db.scalars(select(StructuralDesignRevision).where(StructuralDesignRevision.design_id.in_([d.id for d in designs]))
                            .order_by(StructuralDesignRevision.revision)):
            revs.setdefault(r.design_id, []).append(r)
    org = db.get(Organization, actor.org_id)
    archive = ProjectArchive(
        format=FORMAT, format_version=FORMAT_VERSION, app_version=__version__, exported_at=datetime.now(UTC),
        organization=org.name if org else "", exported_by=actor.full_name,
        project=ProjectRecord(**{k: getattr(project, k) for k in _PROJECT_FIELDS}),
        designs=[DesignRecord(
            element_type=d.element_type, name=d.name, status=d.status, review_status=d.review_status, revision=d.revision,  # type: ignore[arg-type]
            engine_version=d.engine_version, max_utilisation=d.max_utilisation, inputs=d.inputs, result=d.result,
            designed_by_name=d.designed_by_name, approved_by_name=d.approved_by_name, approved_at=d.approved_at,
            created_at=d.created_at, updated_at=d.updated_at,
            revisions=[RevisionRecord(revision=r.revision, status=r.status, review_status=r.review_status, engine_version=r.engine_version,  # type: ignore[arg-type]
                                      inputs=r.inputs, result=r.result, saved_by_name=r.saved_by_name, created_at=r.created_at)
                       for r in revs.get(d.id, [])],
        ) for d in designs],
    )
    audit(db, actor, "project.exported", "project", project.id, f"Project {project.code} exported with {len(designs)} designs")
    return archive


def _free_code(db: Session, org_id: uuid.UUID, code: str) -> str:
    def taken(c: str) -> bool:
        return db.scalar(select(Project.id).where(Project.org_id == org_id, func.lower(Project.code) == c.lower())) is not None

    if not taken(code):
        return code
    for k in range(2, 1000):
        candidate = f"{code[:36]}-{k}"
        if not taken(candidate):
            return candidate
    raise Conflict(f"Job number {code} and its numbered variants are all in use.")


def import_project(db: Session, actor: User, archive: ProjectArchive) -> tuple[Project, int, int, bool]:
    """A new project in the actor's organisation, with every design and revision as recorded. Nothing is recalculated."""
    unknown = sorted({d.element_type for d in archive.designs} - set(ELEMENTS))
    if unknown:
        raise Invalid(f"This installation has no designer for {', '.join(unknown)}: update it before importing this project.")
    for d in archive.designs:
        if d.result.get("status") != d.status or d.result.get("engine_version") != d.engine_version:
            raise Invalid(f"Design {d.name}: its result does not match its record; the file has been altered or damaged.")
    data = archive.project.model_dump()
    code = _free_code(db, actor.org_id, data["code"].strip())
    project = Project(org_id=actor.org_id, created_by=actor.id, **{**data, "code": code})
    db.add(project)
    db.flush()
    n_rev = 0
    for d in archive.designs:
        design = StructuralDesign(
            org_id=actor.org_id, project_id=project.id, element_type=d.element_type, name=d.name, status=d.status, review_status=d.review_status,
            revision=d.revision, engine_version=d.engine_version, max_utilisation=d.max_utilisation, inputs=d.inputs, result=d.result,
            designed_by=None, designed_by_name=d.designed_by_name, approved_by=None, approved_by_name=d.approved_by_name, approved_at=d.approved_at,
            created_at=d.created_at, updated_at=d.updated_at,
        )
        db.add(design)
        db.flush()
        for r in d.revisions:
            db.add(StructuralDesignRevision(design_id=design.id, revision=r.revision, status=r.status, review_status=r.review_status,
                                            engine_version=r.engine_version, inputs=r.inputs, result=r.result, saved_by_name=r.saved_by_name,
                                            created_at=r.created_at))
            n_rev += 1
    audit(db, actor, "project.imported", "project", project.id,
          f"Project {project.code} {project.name} imported with {len(archive.designs)} designs",
          {"from_organization": archive.organization, "exported_by": archive.exported_by, "exported_at": archive.exported_at.isoformat(),
           "app_version": archive.app_version, "original_code": archive.project.code})
    return project, len(archive.designs), n_rev, code != archive.project.code.strip()


def snapshot_database(db: Session, actor: User) -> Path:
    """A consistent copy of the SQLite database (VACUUM INTO), for an installation that holds only the actor's organisation."""
    engine = get_engine()
    if engine.dialect.name != "sqlite":
        raise Conflict("This server keeps its data in PostgreSQL: back it up with pg_dump (see the operations guide).")
    others = db.scalar(select(func.count()).select_from(Organization).where(Organization.id != actor.org_id)) or 0
    if others:
        raise Conflict("This database holds other organisations too: it is backed up at the server, not from here.")
    fd, name = tempfile.mkstemp(prefix="civillabpro-backup-", suffix=".db")
    os.close(fd)
    os.unlink(name)  # VACUUM INTO writes a new file
    raw = engine.raw_connection()
    try:
        raw.execute("VACUUM INTO ?", (name,))  # type: ignore[attr-defined]
    finally:
        raw.close()
    audit(db, actor, "data.backup", "organization", actor.org_id, "Database backed up")
    return Path(name)
