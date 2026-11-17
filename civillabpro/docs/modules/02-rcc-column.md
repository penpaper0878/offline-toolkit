# Release note 0.2.0: RCC column to IS 456:2000

Second structural element, built on the element registry introduced in 0.1.0. It needed no new endpoint, table, migration or screen; it did extend the shared result contract with charts, which every element can now use.

## 1. Requirements analysis

**Goal.** Design a rectangular tied column from the forces of an external analysis, and issue its calculation, bar bending schedule, quantities and drawing, with the same traceability as the beam.

**In scope.** Factored axial load with end moments about both axes; effective length from Table 28 or an entered factor; short and slender columns, braced or sway; minimum eccentricity; additional moments with the reduction factor; the axial formula for short columns with only minimum eccentricity; biaxial bending; selection of bars and ties; cross-ties; laps; one lift of the column.

**Out of scope, by decision.** Circular and helically reinforced columns (Cl. 39.4); effective length from storey stiffness (Annex E charts); generation of load combinations; IS 13920 ductile detailing; a column stack over several storeys. Each is in the backlog.

**Users.** Design engineer, reviewer, viewer, as for the beam.

**Status of the code text.** The clauses were implemented from IS 456:2000 as commonly published and corroborated against secondary sources; the text itself could not be read in the session that built the engine. See the code register before relying on the engine for issued work.

## 2. System architecture

No new layer or module. The work sits in three places:

| Layer | Addition |
|---|---|
| Engineering kernel | `rc_section.py`: strain-compatibility analysis of a rectangular section under axial load and bending (Cl. 39.1). Reusable by footings, walls and pile caps. |
| Structural domain | `column.py` (inputs, design, selection), `column_detailing.py` (schedule, quantities, drawing), one registry entry |
| Result contract | optional `charts`: id, title, axes, series of points (`line` or `point`), note. Rendered by the web workspace and the PDF report for any element. |

## 3. Database changes

None. Column designs are rows of `structural_designs` with `element_type = 'column'`; charts travel inside the `result` document.

## 4. API endpoints

None new. The column is reached through the generic endpoints:

| Method and path | Use for the column |
|---|---|
| GET `/structural/elements` | lists `column` with its defaults and input schema (groups, units, Table 28 labels, conditional rows) |
| POST `/structural/column/calculate` | runs the engine without saving |
| POST `/projects/{id}/designs` with `element_type: "column"` | saves |
| PUT, approve, revisions, `report.pdf`, `bbs.xlsx`, `drawing.dxf` | as for every element |

## 5. Backend implementation

| Path | Content |
|---|---|
| `app/engineering/rc_section.py` | Fig. 21 block integrated in closed form for any neutral-axis depth, including the Cl. 39.1(b) pivot; bar stresses from Fig. 23 with displaced concrete deducted; force and moment for a neutral-axis depth; capacity at an axial load by bisection; squash load; balanced state; interaction curve |
| `app/modules/structural/domain/column.py` | `ColumnInput`; Table 28; per-axis geometry (effective length, slenderness, e_min, initial and additional moments); load cases; candidate arrangements; evaluation of one arrangement (P_uz, P_b, k, design moments, capacities, alpha_n, ratios); selection; calculation sheet; charts |
| `app/modules/structural/domain/column_detailing.py` | bar schedule (main bars with lap, ties, cross-ties), quantities, section and elevation drawing |
| `app/modules/structural/exports/pdf_report.py` | charts; prose versus formula rendering; leader labels anchored away from their point; notes kept with the last view |
| `app/modules/structural/exports/dxf.py` | right-aligned leader text when the label is left of its point |

## 6. Frontend implementation

| Path | Content |
|---|---|
| `src/components/ChartView.tsx` | x-y chart from the result contract: capacity line, design points with labels that read away from each other, legend, tooltip, table view |
| `src/pages/DesignWorkspacePage.tsx` | Charts panel beside Section and Elevation; charts side by side when the panel is wide; validation of the values actually sent |
| `src/components/Fx.tsx` | alpha, symbol powers (`^alpha_n`), decimal powers, and a prose mode for titles |
| `src/components/DrawingCanvas.tsx` | leader labels anchored away from their point |

## 7. UI screens

The design workspace, unchanged in layout, now shows for a column: the property grid (member, geometry, effective length with Table 28 presets and conditional custom-factor rows, materials, loading, reinforcement); the summary strip (verdict, checks, highest utilisation, axial load, design moments, interaction ratio, bars, steel ratio); Section, Elevation and Charts panels; Calculation, Checks, Bar schedule and Quantities panels. The structural catalogue lists the column with its scope limits.

## 8. Engineering logic

Column engine 1.0.0. Axes: M_ux bends about x and acts in the plane of D; M_uy about y, in the plane of b.

| Step | Rule | Reference |
|---|---|---|
| Durability | grade for exposure; cover to ties the larger of Table 16 and 40 mm less the tie | Table 5, Table 16, Cl. 26.4.2.1 |
| Effective length | k l from the end restraint about each axis | Cl. 25.2, Table 28 |
| Slenderness | short when l_e/D and l_e/b are both less than 12; l not more than 60 b_min; l not more than 100 b^2/D with a free end | Cl. 25.1.2, 25.3 |
| Minimum eccentricity | l/500 + D/30, at least 20 mm, about one axis at a time | Cl. 25.4 |
| Initial moment | braced slender: max(0.4 M_u1 + 0.6 M_u2, 0.4 M_u2); otherwise M_u2 | Cl. 39.7.1, note 1 |
| Additional moment | M_a = P_u D/2000 (l_e/D)^2 about each slender axis | Cl. 39.7.1 |
| Reduction factor | k = (P_uz - P_u)/(P_uz - P_b), at most 1; P_b by strain compatibility at x_u,max | Cl. 39.7.1.1, 38.1(f) |
| Design moments | two cases; per axis max(initial, P_u e_min on the case's axis) + k M_a, not less than M_u2 | Cl. 25.4, 39.7.1 |
| Axial formula | short, no end moments, e_min not more than 0.05 D and 0.05 b: P_u <= 0.4 fck Ac + 0.67 fy Asc | Cl. 39.3 |
| Biaxial bending | (M_ux/M_ux1)^alpha_n + (M_uy/M_uy1)^alpha_n <= 1 for both cases; M_u1 by strain compatibility at P_u; alpha_n 1.0 to 2.0 over P_u/P_uz 0.2 to 0.8 | Cl. 39.1, 39.6 |
| Bars | symmetric; 0.8 percent to the maximum entered (4 by default, 6 allowed); four or more; 12 mm or more; at most 300 mm apart along the faces; clear spacing of Cl. 26.3.2; lightest in steel per metre, ties included, that passes | Cl. 26.5.3.1, 26.3.2 |
| Ties | at least a quarter of the bar and 6 mm; pitch the least of b_min, 16 d and 300; cross-ties for intermediate bars by the 75 mm rule | Cl. 26.5.3.2 |
| Laps | development length in compression, at least 24 d | Cl. 26.2.5.1(d) |
| Schedule | main bars: clear height + beam depth + lap; ties over the clear height, 50 mm from each end; lengths as IS 2502 practice | IS 2502:1963 |

Worked example (the defaults): 300 x 450, l = 3.6 m, Table 28 row (c) about both axes, M25 / Fe 500, moderate exposure, P_u 1200 kN, M_ux 90 (other end -45), M_uy 30 (other end 10). Short about x (8.0), slender about y (12.0); e_x,min 22.2 mm, e_y,min 20.0 mm; M_iy 22.0 kN m; M_ay 25.92 kN m; P_uz 2012.4 kN; k_y 0.484; design moments 90.00 / 34.54 (case 1) and 90.00 / 36.54 (case 2); M_ux1 125.42, M_uy1 70.99 kN m; alpha_n 1.66; ratios 0.879 and 0.908; 12-T12 (5 on each face of width b, 3 on each face of depth D), 1.01 percent; T8 ties at 175 with two cross-ties; lap 466 mm; 66.1 kg of steel.

## 9. Validation rules

| Input | Rule |
|---|---|
| Width b, depth D | 200 to 2000 and 200 to 3000 mm; the longer not more than four times the shorter (else a wall, Cl. 32.1) |
| Unsupported lengths | 500 to 30 000 mm; about y blank means the same as about x |
| End restraint | Table 28 rows (a) to (g), or custom with a factor of 0.5 to 3.0 and a sway flag |
| Grades | M20 to M55; Fe 250, 415, 500, 550 |
| Cover to ties | blank, or 15 to 100 mm |
| Axial load | more than 0 (compression) |
| End moments | the larger end moment 0 or more; the other end not larger in size, signed for curvature |
| Maximum steel | 0.8 to 6 percent |
| Bars, ties | 12 to 32 mm; ties 8, 10 or 12 mm |

Stop state: no arrangement within the maximum steel carries the forces; the message says what to change. Failed limits (cover, length) are reported as Not OK checks, not hidden.

## 10. Unit tests

| Suite | Tests | Proves |
|---|---|---|
| `tests/unit/test_rc_section.py` | 17 | Fig. 21 constants, continuity at x_u = D, the Cl. 39.1(b) strain rule, uniform limit, monotonic P, round trip at an axial load, squash and balanced states, agreement with the beam capacity in pure bending, the curve's shape |
| `tests/unit/test_column.py` | 46 | worked example to hand values; every lighter arrangement fails; Table 28; e_min floor; initial moment rules; total not below M_u2; one axis at a time; alpha_n; k = 1 below balanced; Cl. 39.3 and its exclusion; cantilever limit; reported failures; stop state; cross-tie rule; tie and cover rules; validation; schedule, quantities and drawing; charts; references and JSON safety; a sweep of 216 inputs |
| `tests/handcheck/check_column.py` | 35 base results, 471 values over 17 cases, 2 stops | independent route: strip integration, SP 16 Table A, grid-and-bisection neutral axis |
| `tests/api/test_structural.py` | 2 new | the column's life cycle through the generic endpoints, input errors by field |
| `frontend/src/components/components.test.tsx` | 3 new | alpha and decimal powers, prose mode, chart table view |
| `e2e/walkthrough.js` | column leg | create, Charts panel, save, PDF / Excel / DXF, both themes; no console errors |

The P_b comparison in the hand check is measured against 5 percent of P_uz where P_b is small: in a 230 x 230 column it is the 4 kN difference of forces of 109 to 175 kN, and the whole route difference there is the rounding of SP 16 Table A, which the engine reproduces exactly when given Table A's stresses.

## 11. Integration steps

As for 0.1.0. After pulling, run `pip install -e ".[dev]"` and `npm ci` again only if dependencies changed (they did not). No migration.

## 12. Deployment notes

No database change; deploy the new image or restart the single process. Saved beam designs are unaffected. Clients holding a docking layout from 0.1.0 get the new default layout (the stored layout key changed).

## 13. Future enhancements

Circular and helical columns; Annex E effective lengths from stiffness ratios; column stacks with lap positions per storey; IS 13920 confinement; import of column forces from analysis files. See BACKLOG.md.
