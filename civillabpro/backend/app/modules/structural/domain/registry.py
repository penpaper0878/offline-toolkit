"""Registry of structural element designers.

Each element type registers its input model and its design function. The API,
the persistence layer, the exports and the web workspace are written against
this registry, so adding a column, slab or footing is a new domain module plus
one entry here: no new endpoints, tables or screens for the shared parts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.modules.structural.domain import beam, column


@dataclass(frozen=True)
class ElementSpec:
    type: str
    title: str
    description: str
    engine_version: str
    code_basis: tuple[str, ...]
    input_model: type[BaseModel]
    design: Callable[[Any], dict[str, Any]]
    limitations: tuple[str, ...] = ()


ELEMENTS: dict[str, ElementSpec] = {
    beam.ELEMENT_TYPE: ElementSpec(
        type=beam.ELEMENT_TYPE,
        title="RCC beam",
        description="Rectangular simply supported or cantilever beam: flexure, shear, torsion, deflection and detailing.",
        engine_version=beam.ENGINE_VERSION,
        code_basis=beam.CODE_BASIS,
        input_model=beam.BeamInput,
        design=beam.design_beam,
        limitations=(
            "Rectangular sections only: flanged (T and L) beams are not yet covered.",
            "Uniformly distributed load, or factored forces from an external analysis. Continuous beams by force input.",
            "No curtailment of bars and one stirrup spacing along the span.",
            "Deflection by the span/depth rule of Cl. 23.2.1; no calculated deflection or crack width.",
            "Ductile detailing to IS 13920 is not applied.",
        ),
    ),
    column.ELEMENT_TYPE: ElementSpec(
        type=column.ELEMENT_TYPE,
        title="RCC column",
        description="Rectangular tied column under axial load and biaxial bending: slenderness, minimum eccentricity, additional moments, ties.",
        engine_version=column.ENGINE_VERSION,
        code_basis=column.CODE_BASIS,
        input_model=column.ColumnInput,
        design=column.design_column,
        limitations=(
            "Rectangular tied columns only: circular and helically reinforced columns are not yet covered.",
            "Axial load and end moments come from an external analysis; load combinations are not generated.",
            "Effective length from Table 28 or an entered factor; the frame stability charts of Annex E are not used.",
            "Additional moments are applied about the slender axes only.",
            "One lift per design. Ductile detailing to IS 13920 is not applied.",
        ),
    ),
}


def get_element(element_type: str) -> ElementSpec | None:
    return ELEMENTS.get(element_type)
