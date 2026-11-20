from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require
from app.modules.identity.models import User
from app.modules.identity.permissions import P
from app.modules.projects.router import _out
from app.modules.transfer import service
from app.modules.transfer.schemas import ImportResult, ProjectArchive

router = APIRouter(tags=["transfer"])


@router.get("/projects/{project_id}/export", summary="Project archive (JSON): the project, its designs and their revisions",
            response_class=Response)
def export_project(project_id: uuid.UUID, user: User = Depends(require(P.DESIGN_READ)), db: Session = Depends(get_db, scope="function")) -> Response:
    archive = service.export_project(db, user, project_id)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{archive.project.code}_{archive.project.name}").strip("_")[:80]
    return Response(archive.model_dump_json(indent=1), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{stem}.clp.json"'})


@router.post("/projects/import", response_model=ImportResult, status_code=status.HTTP_201_CREATED,
             summary="Create a project from an archive; designs and revisions come in as recorded")
def import_project(archive: ProjectArchive, user: User = Depends(require(P.PROJECT_WRITE)), _: User = Depends(require(P.DESIGN_WRITE)),
                   db: Session = Depends(get_db, scope="function")) -> ImportResult:
    project, n, n_rev, changed = service.import_project(db, user, archive)
    note = f"Imported as job number {project.code}" + (f" ({archive.project.code} is already in use)." if changed else ".")
    return ImportResult(project=_out(db, [project])[0], designs=n, revisions=n_rev, code_changed=changed, note=note)


@router.get("/admin/backup", summary="A consistent copy of this installation's SQLite database (single organisation)",
            response_class=FileResponse)
def backup(tasks: BackgroundTasks, user: User = Depends(require(P.ORG_MANAGE)), db: Session = Depends(get_db, scope="function")) -> FileResponse:
    path = service.snapshot_database(db, user)
    tasks.add_task(path.unlink, missing_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M")
    return FileResponse(path, media_type="application/vnd.sqlite3", filename=f"civillabpro-backup-{stamp}.db", background=tasks)
