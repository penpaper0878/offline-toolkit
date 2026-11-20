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

from app.modules.structural.domain import beam, column, combined_footing, continuous_beam, footing, slab


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

    def input_schema(self) -> dict[str, Any]:
        """The input model's JSON schema with the definitions of list items inlined, as the property grid and the report read it."""
        schema = self.input_model.model_json_schema()
        defs = schema.pop("$defs", {})

        def inline(node: Any) -> Any:
            if isinstance(node, dict):
                if "$ref" in node:
                    return inline({**defs[node["$ref"].rsplit("/", 1)[-1]], **{k: v for k, v in node.items() if k != "$ref"}})
                return {k: inline(v) for k, v in node.items()}
            if isinstance(node, list):
                return [inline(v) for v in node]
            return node

        return inline(schema)  # type: ignore[no-any-return]


ELEMENTS: dict[str, ElementSpec] = {
    beam.ELEMENT_TYPE: ElementSpec(
        type=beam.ELEMENT_TYPE,
        title="RCC beam",
        description="Rectangular, T or L beam, simply supported or cantilever: flexure, shear, torsion, deflection and detailing.",
        engine_version=beam.ENGINE_VERSION,
        code_basis=beam.CODE_BASIS,
        input_model=beam.BeamInput,
        design=beam.design_beam,
        limitations=(
            "T and L beams take the slab as the flange (Cl. 23.1.2); the slab's own reinforcement is designed with the slab.",
            "Uniformly distributed load, or factored forces from an external analysis; continuous beams are their own element.",
            "With forces entered there is no diagram: the bars run the full length and the stirrups are at one spacing.",
            "Deflection by the span/depth rule of Cl. 23.2.1; no calculated deflection or crack width.",
            "Ductile detailing to IS 13920 is not applied.",
        ),
    ),
    continuous_beam.ELEMENT_TYPE: ElementSpec(
        type=continuous_beam.ELEMENT_TYPE,
        title="RCC continuous beam",
        description="Beam over two or more spans: by the coefficients of Tables 12 and 13 (equal spans, uniform load), or by elastic "
                    "analysis with redistribution of moments (any spans, point loads). Span and support sections, shear, deflection, "
                    "curtailment, anchorage, schedule and drawing for the whole beam.",
        engine_version=continuous_beam.ENGINE_VERSION,
        code_basis=continuous_beam.CODE_BASIS,
        input_model=continuous_beam.ContinuousBeamInput,
        design=continuous_beam.design_continuous_beam,
        limitations=(
            "One section and one support width for the whole beam; supports are knife edges and the end supports are free to rotate.",
            "Coefficients: three or more spans of one clear span (the longest where they differ by up to 15 percent), uniform load, no "
            "redistribution (Cl. 22.5.1).",
            "Elastic analysis: two to twelve spans, uniform and point loads, redistribution up to 30 percent (Cl. 37.1.1); support moments "
            "at the centre lines of the supports, or at the faces where the construction is monolithic (Cl. 22.6.2).",
            "Cantilevers at the ends with the elastic method only; their top bars are not curtailed. Torsion and ductile detailing to "
            "IS 13920 are not covered.",
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
    slab.ELEMENT_TYPE: ElementSpec(
        type=slab.ELEMENT_TYPE,
        title="RCC slab",
        description="Solid slab panel, one-way or two-way by its spans and edges: Annex D coefficients, flexure, shear, deflection, corner torsion steel.",
        engine_version=slab.ENGINE_VERSION,
        code_basis=slab.CODE_BASIS,
        input_model=slab.SlabInput,
        design=slab.design_slab,
        limitations=(
            "One rectangular panel under uniform load; supports are beams or walls on all four edges.",
            "Continuous one-way panels use Tables 12 and 13, which assume three or more nearly equal spans.",
            "Unequal support moments of adjacent two-way panels are not redistributed (Annex D).",
            "One bar size for the panel; no flat slabs, ribbed slabs, openings or concentrated loads.",
            "Table 26 coefficients are still to be compared with the printed code (see the code register).",
        ),
    ),
    footing.ELEMENT_TYPE: ElementSpec(
        type=footing.ELEMENT_TYPE,
        title="RCC isolated footing",
        description="Rectangular pad of uniform depth under one column: size from the bearing pressure, depth from bending and shear, central band steel.",
        engine_version=footing.ENGINE_VERSION,
        code_basis=footing.CODE_BASIS,
        input_model=footing.FootingInput,
        design=footing.design_footing,
        limitations=(
            "Uniform depth; sloped and stepped footings are not covered.",
            "Service loads and moments from the column, with an allowance for own weight; one load case.",
            "The largest factored pressure is used over the whole footing, which is on the safe side with moments.",
            "Safe bearing pressure from the soil investigation; settlement is not checked.",
            "Combined footings are their own element; strap and pile footings are in the backlog.",
        ),
    ),
    combined_footing.ELEMENT_TYPE: ElementSpec(
        type=combined_footing.ELEMENT_TYPE,
        title="RCC combined footing",
        description="Rectangular footing of uniform depth under two columns: plan centred on the loads (or from a property line), bending "
                    "and shear along and across, punching around each column, bands of steel under the columns.",
        engine_version=combined_footing.ENGINE_VERSION,
        code_basis=combined_footing.CODE_BASIS,
        input_model=combined_footing.CombinedFootingInput,
        design=combined_footing.design_combined_footing,
        limitations=(
            "Two rectangular columns on the footing's long axis, axial service loads only (no column moments or horizontal loads); one load case.",
            "Rigid footing: the pressure varies linearly along it and is uniform across it. Settlement is not checked.",
            "Uniform depth and no shear reinforcement: the depth is chosen for shear. The width is the least the bearing pressure allows; enter "
            "a wider one for a shallower footing.",
            "Bars along run the full length uncurtailed. Trapezoidal and strap footings, for a heavier column at a property line, are in the backlog.",
        ),
    ),
}


def get_element(element_type: str) -> ElementSpec | None:
    return ELEMENTS.get(element_type)
