from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require
from app.modules.estimation import exports, service
from app.modules.estimation.models import Estimate, RateAnalysis
from app.modules.estimation.schemas import (
    DesignQuantities,
    EstimateCreate,
    EstimateDoc,
    EstimateOut,
    EstimateSave,
    EstimateSummary,
    RateAnalysisIn,
    RateAnalysisOut,
    SorBookImport,
    SorBookOut,
    SorImportResult,
    SorItemOut,
    SorItemPage,
)
from app.modules.identity.models import User
from app.modules.identity.permissions import P
from app.modules.projects.service import get_project

router = APIRouter(tags=["estimation"])
DB = Depends(get_db, scope="function")


# ----------------------------------------------------------------------------- schedules of rates


@router.get("/sor-books", response_model=list[SorBookOut], summary="Schedules of rates imported by the organisation")
def list_books(user: User = Depends(require(P.ESTIMATE_READ)), db: Session = DB) -> list[SorBookOut]:
    return [SorBookOut.model_validate(b).model_copy(update={"item_count": n}) for b, n in service.list_books(db, user.org_id)]


@router.post("/sor-books/import", response_model=SorImportResult, status_code=status.HTTP_201_CREATED,
             summary="Import a schedule of rates from a CSV file or an Excel workbook")
def import_book(data: SorBookImport, user: User = Depends(require(P.RATES_MANAGE)), db: Session = DB) -> SorImportResult:
    book, n, headings, skipped = service.import_sor(db, user, data)
    return SorImportResult(book=SorBookOut.model_validate(book).model_copy(update={"item_count": n}), imported=n, headings=headings, skipped=skipped[:200])


@router.get("/sor-books/{book_id}/items", response_model=SorItemPage, summary="Search a schedule's items by code and words")
def search_items(book_id: uuid.UUID, q: str = Query("", max_length=200), limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                 user: User = Depends(require(P.ESTIMATE_READ)), db: Session = DB) -> SorItemPage:
    rows, total = service.search_items(db, user.org_id, book_id, q, limit, offset)
    return SorItemPage(items=[SorItemOut(id=r.id, item_code=r.item_code, chapter=r.chapter, description=r.description, unit=r.unit,
                                         rate=service.rupees(r.rate_paise)) for r in rows], total=total)


@router.delete("/sor-books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: uuid.UUID, user: User = Depends(require(P.RATES_MANAGE)), db: Session = DB) -> None:
    service.delete_book(db, user, book_id)


# ----------------------------------------------------------------------------- rate analyses


def _analysis_out(a: RateAnalysis) -> RateAnalysisOut:
    res = service.analysis_result(a.doc)
    return RateAnalysisOut(id=a.id, title=a.title, unit=a.unit, **a.doc, rate=res["rate"], result=res, updated_at=a.updated_at)


@router.get("/rate-analyses", response_model=list[RateAnalysisOut])
def list_analyses(user: User = Depends(require(P.ESTIMATE_READ)), db: Session = DB) -> list[RateAnalysisOut]:
    return [_analysis_out(a) for a in service.list_analyses(db, user.org_id)]


@router.post("/rate-analyses/calculate", response_model=dict[str, Any], summary="Work out a rate without saving it")
def calculate_analysis(data: RateAnalysisIn, user: User = Depends(require(P.ESTIMATE_READ))) -> dict[str, Any]:
    return service.analysis_result(data.model_dump(exclude={"title", "unit"}))


@router.post("/rate-analyses", response_model=RateAnalysisOut, status_code=status.HTTP_201_CREATED)
def create_analysis(data: RateAnalysisIn, user: User = Depends(require(P.RATES_MANAGE)), db: Session = DB) -> RateAnalysisOut:
    return _analysis_out(service.save_analysis(db, user, data))


@router.get("/rate-analyses/{analysis_id}", response_model=RateAnalysisOut)
def get_analysis(analysis_id: uuid.UUID, user: User = Depends(require(P.ESTIMATE_READ)), db: Session = DB) -> RateAnalysisOut:
    return _analysis_out(service.get_analysis(db, user.org_id, analysis_id))


@router.put("/rate-analyses/{analysis_id}", response_model=RateAnalysisOut)
def update_analysis(analysis_id: uuid.UUID, data: RateAnalysisIn, user: User = Depends(require(P.RATES_MANAGE)), db: Session = DB) -> RateAnalysisOut:
    return _analysis_out(service.save_analysis(db, user, data, analysis_id))


@router.delete("/rate-analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis(analysis_id: uuid.UUID, user: User = Depends(require(P.RATES_MANAGE)), db: Session = DB) -> None:
    service.delete_analysis(db, user, analysis_id)


# ----------------------------------------------------------------------------- estimates


def _summary(e: Estimate) -> EstimateSummary:
    return EstimateSummary.model_validate(e).model_copy(update={"total": service.rupees(e.total_paise), "item_count": len(e.doc.get("items", []))})


def _out(db: Session, e: Estimate) -> EstimateOut:
    return EstimateOut(**_summary(e).model_dump(), notes=e.notes, doc=EstimateDoc.model_validate(e.doc), result=service.compute(db, e))


@router.get("/estimates", response_model=list[EstimateSummary], summary="Every estimate of the organisation, newest first")
def list_all(user: User = Depends(require(P.ESTIMATE_READ)), db: Session = DB) -> list[EstimateSummary]:
    return [_summary(e) for e in service.list_estimates(db, user.org_id)]


@router.get("/projects/{project_id}/estimates", response_model=list[EstimateSummary])
def list_for_project(project_id: uuid.UUID, user: User = Depends(require(P.ESTIMATE_READ)), db: Session = DB) -> list[EstimateSummary]:
    return [_summary(e) for e in service.list_estimates(db, user.org_id, project_id)]


@router.post("/projects/{project_id}/estimates", response_model=EstimateOut, status_code=status.HTTP_201_CREATED)
def create(project_id: uuid.UUID, data: EstimateCreate, user: User = Depends(require(P.ESTIMATE_WRITE)), db: Session = DB) -> EstimateOut:
    return _out(db, service.create_estimate(db, user, project_id, data.title))


@router.get("/projects/{project_id}/design-quantities", response_model=list[DesignQuantities],
            summary="The quantities the project's designs report, for estimate items")
def design_quantities(project_id: uuid.UUID, user: User = Depends(require(P.ESTIMATE_READ)), db: Session = DB) -> list[dict[str, Any]]:
    get_project(db, user.org_id, project_id)
    return service.design_quantities(db, user.org_id, project_id)


@router.get("/estimates/{estimate_id}", response_model=EstimateOut)
def get(estimate_id: uuid.UUID, user: User = Depends(require(P.ESTIMATE_READ)), db: Session = DB) -> EstimateOut:
    return _out(db, service.get_estimate(db, user.org_id, estimate_id))


@router.put("/estimates/{estimate_id}", response_model=EstimateOut)
def save(estimate_id: uuid.UUID, data: EstimateSave, user: User = Depends(require(P.ESTIMATE_WRITE)), db: Session = DB) -> EstimateOut:
    return _out(db, service.save_estimate(db, user, estimate_id, data))


@router.post("/estimates/{estimate_id}/preview", response_model=dict, summary="Quantities, amounts and abstract of an unsaved document")
def preview(estimate_id: uuid.UUID, doc: EstimateDoc, user: User = Depends(require(P.ESTIMATE_READ)), db: Session = DB) -> dict[str, Any]:
    result = service.preview(db, user.org_id, estimate_id, doc)
    db.rollback()  # nothing of a preview is kept
    return result


@router.post("/estimates/{estimate_id}/refresh", response_model=EstimateOut, summary="Take the designs' current quantities")
def refresh(estimate_id: uuid.UUID, user: User = Depends(require(P.ESTIMATE_WRITE)), db: Session = DB) -> EstimateOut:
    return _out(db, service.refresh_estimate(db, user, estimate_id))


@router.post("/estimates/{estimate_id}/issue", response_model=EstimateOut)
def issue(estimate_id: uuid.UUID, user: User = Depends(require(P.ESTIMATE_ISSUE)), db: Session = DB) -> EstimateOut:
    return _out(db, service.issue_estimate(db, user, estimate_id))


@router.post("/estimates/{estimate_id}/revise", response_model=EstimateOut)
def revise(estimate_id: uuid.UUID, user: User = Depends(require(P.ESTIMATE_WRITE)), db: Session = DB) -> EstimateOut:
    return _out(db, service.revise_estimate(db, user, estimate_id))


@router.delete("/estimates/{estimate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(estimate_id: uuid.UUID, user: User = Depends(require(P.ESTIMATE_WRITE)), db: Session = DB) -> None:
    service.delete_estimate(db, user, estimate_id)


def _meta(db: Session, user: User, e: Estimate) -> dict[str, str]:
    project = get_project(db, user.org_id, e.project_id)
    return {
        "organization": user.organization.name, "project": project.name, "job": project.code, "client": project.client or "-",
        "calculation": e.title, "revision": f"R{e.revision}" + ("" if e.status == "issued" else " (draft)"),
        "designed": e.prepared_by_name or "-", "checked": e.issued_by_name or "-", "date": e.updated_at.strftime("%d %b %Y"),
        "footer": f"CivilLabPro OS  |  estimate {str(e.id)[:8]}",
    }


def _filename(e: Estimate, suffix: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", f"estimate_{e.title}_R{e.revision}").strip("_")
    return f'attachment; filename="{stem}{suffix}"'


@router.get("/estimates/{estimate_id}/estimate.xlsx", response_class=Response, summary="Abstract and details of measurement (Excel)")
def export_xlsx(estimate_id: uuid.UUID, user: User = Depends(require(P.ESTIMATE_READ)), db: Session = DB) -> Response:
    e = service.get_estimate(db, user.org_id, estimate_id)
    body = exports.build_xlsx(_meta(db, user, e), e.doc, service.compute(db, e))
    return Response(body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": _filename(e, ".xlsx")})


@router.get("/estimates/{estimate_id}/estimate.pdf", response_class=Response, summary="The estimate (PDF, A4)")
def export_pdf(estimate_id: uuid.UUID, user: User = Depends(require(P.ESTIMATE_READ)), db: Session = DB) -> Response:
    e = service.get_estimate(db, user.org_id, estimate_id)
    body = exports.build_pdf(_meta(db, user, e), e.doc, service.compute(db, e), e.status, e.notes)
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": _filename(e, ".pdf")})

