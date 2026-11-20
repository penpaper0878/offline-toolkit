"""Structural design use cases: calculate, save, revise, approve."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import utcnow
from app.core.errors import Conflict, NotFound, from_pydantic
from app.modules.identity.models import User
from app.modules.identity.service import audit
from app.modules.projects.service import get_project
from app.modules.structural.domain.registry import ElementSpec, element_title, get_element
from app.modules.structural.models import StructuralDesign, StructuralDesignRevision
from app.modules.structural.schemas import DesignSave, DesignUpdate


def element_or_404(element_type: str) -> ElementSpec:
    spec = get_element(element_type)
    if spec is None:
        raise NotFound(f"Unknown element type '{element_type}'.")
    return spec


def calculate(element_type: str, inputs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate the inputs and run the engine. Returns (normalised inputs, result)."""
    spec = element_or_404(element_type)
    try:
        model = spec.input_model.model_validate(inputs)
    except ValidationError as exc:
        raise from_pydantic(exc) from exc
    return model.model_dump(mode="json"), spec.design(model)


def get_design(db: Session, org_id: uuid.UUID, design_id: uuid.UUID) -> StructuralDesign:
    design = db.get(StructuralDesign, design_id)
    if design is None or design.org_id != org_id:
        raise NotFound("Design not found.")
    return design


def list_designs(db: Session, org_id: uuid.UUID, project_id: uuid.UUID) -> list[StructuralDesign]:
    get_project(db, org_id, project_id)
    stmt = select(StructuralDesign).where(StructuralDesign.project_id == project_id).order_by(StructuralDesign.updated_at.desc())
    return list(db.scalars(stmt))


def save_design(db: Session, actor: User, project_id: uuid.UUID, data: DesignSave) -> StructuralDesign:
    project = get_project(db, actor.org_id, project_id)
    inputs, result = calculate(data.element_type, data.inputs)
    design = StructuralDesign(
        org_id=actor.org_id, project_id=project.id, element_type=data.element_type, name=data.name.strip(), status=result["status"],
        engine_version=result["engine_version"], max_utilisation=result["max_utilisation"], inputs=inputs, result=result,
        designed_by=actor.id, designed_by_name=actor.full_name,
    )
    db.add(design)
    db.flush()
    audit(db, actor, "design.created", "structural_design", design.id, f"{element_title(data.element_type)} {design.name} saved in {project.code}",
          {"status": design.status})
    return design


def update_design(db: Session, actor: User, design_id: uuid.UUID, data: DesignUpdate) -> StructuralDesign:
    """Saving new inputs supersedes the current state: it is archived as a revision and any approval lapses."""
    design = get_design(db, actor.org_id, design_id)
    if data.inputs is not None:
        inputs, result = calculate(design.element_type, data.inputs)
        db.add(StructuralDesignRevision(
            design_id=design.id, revision=design.revision, status=design.status, review_status=design.review_status,
            engine_version=design.engine_version, inputs=design.inputs, result=design.result, saved_by_name=design.designed_by_name,
        ))
        design.inputs, design.result = inputs, result
        design.status, design.engine_version, design.max_utilisation = result["status"], result["engine_version"], result["max_utilisation"]
        design.revision += 1
        design.review_status, design.approved_by, design.approved_by_name, design.approved_at = "draft", None, "", None
        design.designed_by, design.designed_by_name = actor.id, actor.full_name
    if data.name is not None:
        design.name = data.name.strip()
    design.updated_at = utcnow()
    audit(db, actor, "design.updated", "structural_design", design.id, f"{element_title(design.element_type)} {design.name} revised to R{design.revision}",
          {"status": design.status})
    return design


def approve_design(db: Session, actor: User, design_id: uuid.UUID) -> StructuralDesign:
    design = get_design(db, actor.org_id, design_id)
    if design.status != "ok":
        raise Conflict("Only a design with every check OK can be approved.")
    if design.designed_by == actor.id and not get_settings().allow_self_approval:
        raise Conflict("A design is checked by someone other than its designer.")
    design.review_status, design.approved_by, design.approved_by_name, design.approved_at = "approved", actor.id, actor.full_name, utcnow()
    audit(db, actor, "design.approved", "structural_design", design.id, f"{element_title(design.element_type)} {design.name} R{design.revision} approved")
    return design


def delete_design(db: Session, actor: User, design_id: uuid.UUID) -> None:
    design = get_design(db, actor.org_id, design_id)
    audit(db, actor, "design.deleted", "structural_design", design.id, f"{element_title(design.element_type)} {design.name} deleted")
    db.delete(design)


def list_revisions(db: Session, org_id: uuid.UUID, design_id: uuid.UUID) -> list[StructuralDesignRevision]:
    design = get_design(db, org_id, design_id)
    stmt = select(StructuralDesignRevision).where(StructuralDesignRevision.design_id == design.id).order_by(StructuralDesignRevision.revision.desc())
    return list(db.scalars(stmt))
