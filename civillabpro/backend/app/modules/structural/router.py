from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require
from app.core.errors import Conflict
from app.modules.identity.models import User
from app.modules.identity.permissions import P
from app.modules.projects.service import get_project
from app.modules.structural import service
from app.modules.structural.domain.registry import ELEMENTS
from app.modules.structural.exports.bbs_xlsx import build_bbs_xlsx
from app.modules.structural.exports.dxf import build_dxf
from app.modules.structural.exports.pdf_report import build_pdf
from app.modules.structural.models import StructuralDesign
from app.modules.structural.schemas import DesignOut, DesignResult, DesignSave, DesignSummary, DesignUpdate, ElementOut, RevisionOut

router = APIRouter(tags=["structural"])


@router.get("/structural/elements", response_model=list[ElementOut], summary="Element types this server can design")
def elements(_: User = Depends(require(P.DESIGN_READ))) -> list[ElementOut]:
    return [
        ElementOut(type=e.type, title=e.title, description=e.description, engine_version=e.engine_version, code_basis=list(e.code_basis),
                   limitations=list(e.limitations), defaults=e.input_model().model_dump(mode="json"), input_schema=e.input_schema())
        for e in ELEMENTS.values()
    ]


@router.post("/structural/{element_type}/calculate", response_model=DesignResult, summary="Run a design without saving it")
def calculate(element_type: str, inputs: dict[str, Any] = Body(...), _: User = Depends(require(P.DESIGN_READ))) -> dict[str, Any]:
    return service.calculate(element_type, inputs)[1]


@router.get("/projects/{project_id}/designs", response_model=list[DesignSummary])
def list_designs(project_id: uuid.UUID, user: User = Depends(require(P.DESIGN_READ)), db: Session = Depends(get_db, scope="function")) -> list[StructuralDesign]:
    return service.list_designs(db, user.org_id, project_id)


@router.post("/projects/{project_id}/designs", response_model=DesignOut, status_code=status.HTTP_201_CREATED)
def save_design(project_id: uuid.UUID, data: DesignSave, user: User = Depends(require(P.DESIGN_WRITE)), db: Session = Depends(get_db, scope="function")) -> StructuralDesign:
    return service.save_design(db, user, project_id, data)


@router.get("/designs/{design_id}", response_model=DesignOut)
def get_design(design_id: uuid.UUID, user: User = Depends(require(P.DESIGN_READ)), db: Session = Depends(get_db, scope="function")) -> StructuralDesign:
    return service.get_design(db, user.org_id, design_id)


@router.put("/designs/{design_id}", response_model=DesignOut, summary="Save new inputs as the next revision")
def update_design(design_id: uuid.UUID, data: DesignUpdate, user: User = Depends(require(P.DESIGN_WRITE)), db: Session = Depends(get_db, scope="function")) -> StructuralDesign:
    return service.update_design(db, user, design_id, data)


@router.post("/designs/{design_id}/approve", response_model=DesignOut)
def approve_design(design_id: uuid.UUID, user: User = Depends(require(P.DESIGN_APPROVE)), db: Session = Depends(get_db, scope="function")) -> StructuralDesign:
    return service.approve_design(db, user, design_id)


@router.delete("/designs/{design_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_design(design_id: uuid.UUID, user: User = Depends(require(P.DESIGN_DELETE)), db: Session = Depends(get_db, scope="function")) -> None:
    service.delete_design(db, user, design_id)


@router.get("/designs/{design_id}/revisions", response_model=list[RevisionOut])
def revisions(design_id: uuid.UUID, user: User = Depends(require(P.DESIGN_READ)), db: Session = Depends(get_db, scope="function")) -> list[Any]:
    return list(service.list_revisions(db, user.org_id, design_id))


def _meta(db: Session, user: User, design: StructuralDesign) -> dict[str, str]:
    project = get_project(db, user.org_id, design.project_id)
    title = ELEMENTS[design.element_type].title if design.element_type in ELEMENTS else design.element_type
    return {
        "organization": user.organization.name,
        "project": project.name,
        "job": project.code,
        "client": project.client or "-",
        "calculation": f"{title} {design.name}",
        "revision": f"R{design.revision}" + ("" if design.review_status == "approved" else " (draft)"),
        "designed": design.designed_by_name or "-",
        "checked": design.approved_by_name or "-",
        "date": design.updated_at.strftime("%d %b %Y"),
        "footer": f"CivilLabPro OS  |  {design.element_type} engine {design.engine_version}  |  design {str(design.id)[:8]}",
    }


def _filename(design: StructuralDesign, suffix: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{design.element_type}_{design.name}_R{design.revision}").strip("_")
    return f'attachment; filename="{stem}{suffix}"'


@router.get("/designs/{design_id}/report.pdf", summary="Calculation report (PDF, A4)", response_class=Response)
def report_pdf(design_id: uuid.UUID, user: User = Depends(require(P.DESIGN_READ)), db: Session = Depends(get_db, scope="function")) -> Response:
    design = service.get_design(db, user.org_id, design_id)
    schema = service.element_or_404(design.element_type).input_schema()
    pdf = build_pdf(_meta(db, user, design), design.inputs, schema, design.result)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": _filename(design, "_report.pdf")})


@router.get("/designs/{design_id}/bbs.xlsx", summary="Bar bending schedule (Excel)", response_class=Response)
def bbs_xlsx(design_id: uuid.UUID, user: User = Depends(require(P.DESIGN_READ)), db: Session = Depends(get_db, scope="function")) -> Response:
    design = service.get_design(db, user.org_id, design_id)
    if not design.result.get("bbs"):
        raise Conflict("This design has no bar schedule: the calculation stopped before detailing.")
    data = build_bbs_xlsx(_meta(db, user, design), design.result["bbs"])
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": _filename(design, "_bbs.xlsx")})


@router.get("/designs/{design_id}/drawing.dxf", summary="Reinforcement drawing (DXF, mm)", response_class=Response)
def drawing_dxf(design_id: uuid.UUID, user: User = Depends(require(P.DESIGN_READ)), db: Session = Depends(get_db, scope="function")) -> Response:
    design = service.get_design(db, user.org_id, design_id)
    if not design.result.get("drawing"):
        raise Conflict("This design has no drawing: the calculation stopped before detailing.")
    return Response(build_dxf(design.result["drawing"]), media_type="application/dxf", headers={"Content-Disposition": _filename(design, ".dxf")})
