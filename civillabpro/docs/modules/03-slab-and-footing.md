# Release note 0.3.0: RCC slab and isolated footing to IS 456:2000

The third and fourth structural elements, and the last two of phase 1's exit criterion. Both were added through the element registry: a domain module, its detailing, a hand check and a registry entry each. No new endpoint, table, migration or screen. The shared changes were general ones: a kernel module for slab tables, drawing tabs that follow an element's views, and vertical text in drawings.

## 1. Requirements analysis

**Goal.** Design a solid slab panel and an isolated column footing, and issue for each its calculation, bar bending schedule, quantities and drawing, with the same traceability as the beam and column.

**Slab, in scope.** One rectangular panel on beams or walls on all four edges, each edge continuous or discontinuous; one-way when l_y/l_x is more than 2 (simply supported, or an end or interior span of a continuous strip by Tables 12 and 13); two-way otherwise (Table 26 with corners held down, Table 27 when simply supported with corners free); uniform load; flexure, minimum steel, bar size and spacing, shear, deflection; top steel over continuous and discontinuous edges, edge strips, torsion steel at corners, distribution bars.

**Footing, in scope.** A rectangular pad of uniform depth under one rectangular column; service axial load with moments in both planes; plan size from the safe bearing pressure with no loss of contact (or entered); depth from bending without compression steel, one-way shear and punching shear (or entered and checked); steel both ways with the central band rule; development length within the projection, with end bends where needed; bearing at the base of the column; minimum dowels.

**Out of scope, by decision.** Redistribution of unequal moments between adjacent panels (Annex D-1.1), flat and ribbed slabs, openings, concentrated loads; sloped and stepped footings, combined, strap and pile footings, settlement. Each is in the backlog or stated in the registry's limitations.

**Status of the code text.** As for the column, the text of IS 456:2000 could not be read in the building session. Table 27 was verified by derivation; the other tables and clauses are as commonly published, corroborated where a secondary source reproduced them. The code register lists what remains to compare.

## 2. System architecture

| Layer | Addition |
|---|---|
| Engineering kernel | `is456_slabs.py`: Tables 12, 13, 26 and 27 (27 generated from its expressions), Table 26 case selection and interpolation, the slab shear factor k, minimum steel, bar size and spacing limits, the deflection rule of Cl. 24.1 note 2, the Annex D detailing constants |
| Structural domain | `slab.py` and `slab_detailing.py`; `footing.py` and `footing_detailing.py`; two registry entries |
| Drawing model | `text(..., vertical=True)`: text turned 90 degrees, rendered on screen, in the PDF and in the DXF |
| Web workspace | the two drawing tabs show the element's first and second views and take their titles ("Plan" and "Section along L" for a footing; "Section A-A" and "Longitudinal section" for a beam) |

## 3. Database changes

None. Slabs and footings are rows of `structural_designs` with `element_type` `slab` or `footing`.

## 4. API endpoints

None new. `GET /structural/elements` lists `slab` and `footing` with defaults and input schemas; `POST /structural/{type}/calculate` runs them; saving, revising, approval and the three exports are the generic endpoints.

## 5. Backend implementation

| Path | Content |
|---|---|
| `app/engineering/is456_slabs.py` | tables and rules listed above; pure |
| `app/modules/structural/domain/slab.py` | `SlabInput`; spans and effective spans; one-way or two-way plan (`_plan`); flexure per location (Annex G); one bar size per panel; shear with k; deflection; torsion corners; calculation sheet; flags |
| `app/modules/structural/domain/slab_detailing.py` | schedule (bottom middle and edge strips both ways, top bars over continuous edges scheduled whole, L-bars at discontinuous edges, torsion mats, distribution bars under top bars), quantities, plan and section drawings |
| `app/modules/structural/domain/footing.py` | `FootingInput`; service and factored pressures; plan sizing; `trial` (one depth and bar size: moments, steel, spacing, shears, anchorage); `select_section` (straight bars first, then bent ends); plan enlargement when bars cannot be anchored; bearing and dowels; calculation sheet |
| `app/modules/structural/domain/footing_detailing.py` | schedule (straight or bent-up bars; band and outer parts), quantities with the levelling course stated, plan and section drawings |
| `app/modules/structural/exports/pdf_report.py`, `dxf.py` | vertical text; the drawing height on a page follows the view's aspect |

## 6. Frontend implementation

| Path | Content |
|---|---|
| `src/pages/DesignWorkspacePage.tsx` | drawing panels by position (first and second view), titled from the views on load, on layout reset and when the result changes |
| `src/components/DrawingCanvas.tsx`, `src/api/types.ts` | vertical text |
| `src/pages/StructuralPage.tsx` | the "next" list no longer names slab and footing |
| `e2e/walkthrough.js` | slab and footing legs: create, plan, save, PDF / Excel / DXF, section and schedule tabs |

## 7. UI screens

The workspace, unchanged in layout. For a slab the property grid has Member, Geometry, Edges (four edge conditions and the corner restraint), Materials, Loading and Reinforcement; the summary strip shows the panel type and table case, design load, short-span moment, bottom bars both ways and steel. For a footing: Member, Column, Loading, Soil, Size (blank for automatic), Materials, Reinforcement; the strip shows L x B x D, the largest pressure, bars both ways, the punching ratio and steel. The drawing tabs read "Plan" and the section's own title.

## 8. Engineering logic

### Slab engine 1.0.0

| Step | Rule | Reference |
|---|---|---|
| Durability | grade for exposure; cover from Table 16 | Table 5, Table 16 |
| Effective span | clear span + d, not more than centre to centre | Cl. 22.2 |
| Load | self-weight (optional) + finishes, imposed; factored | Table 18 |
| One or two way | one-way when l_y/l_x > 2 | Annex D-1.11 |
| One-way moments | simply supported w l^2/8; continuous: Table 12 end or interior span, support next to the end support | Cl. 22.5.1, Table 12 |
| Two-way moments | Table 26 case from the edges, interpolated in l_y/l_x; Table 27 when all edges are discontinuous and the corners are free | Annex D-1.1, D-2 |
| Flexure | per metre, each location at its own effective depth (short-span bars outer) | Annex G |
| Minimum steel, bars | 0.12 percent HYSD (0.15 mild); bar not more than D/8; main spacing 3d or 300, distribution 5d or 450 | Cl. 26.5.2.1, 26.5.2.2, 26.3.3(b) |
| Edge strips | one-eighth of each side, minimum steel | Annex D-1.2, D-1.7 |
| Top steel | over continuous edges for the negative moment, to 0.3 l each side; at discontinuous edges half the mid-span steel to 0.1 l | Annex D-1.5, D-1.6 |
| Torsion | 3/4 of the mid-span steel in four layers over l_x/5 at corners with both edges discontinuous; half where one is continuous | Annex D-1.8 to D-1.10 |
| Shear | V_u at d from the face; tau_v <= k tau_c and half of Table 20 | Cl. 22.6.2.1, 40.2.1.1, 40.2.3.1 |
| Deflection | l_x/D within 40 x 0.8 (35 x 0.8 simply supported) where note 2 applies; otherwise l_x/d within (20 or 26) x k_t | Cl. 24.1 note 2, 23.2.1, Fig. 4 |

Worked example (the defaults): corner panel, clear spans 3.3 x 4.5 m on 230 mm beams, D = 150, M25 / Fe 415, moderate exposure, finishes 1.5 and imposed 3.0 kN/m2. w_u = 1.5 (3.75 + 1.5 + 3.0) = 12.375 kN/m2; l_x = 3416, l_y = 4608 mm; l_y/l_x = 1.349, two-way, Table 26 case 4 (two adjacent edges discontinuous); alpha_x 0.0510 (+), 0.0679 (-); alpha_y 0.035 (+), 0.047 (-). M_x+ 7.36, M_x- 9.81, M_y+ 5.05, M_y- 6.79 kN m/m. Minimum steel (180 mm2/m) governs mid-span: T8 at 270 both ways; T8 at 200 over the continuous long edge, at 280 over the continuous short edge; torsion 135 mm2/m, T8 at 300. V_u 18.98 kN/m, tau_v 0.164 against k tau_c = 1.3 x 0.297 N/mm2. Deflection by note 2: l_x/D = 22.8 against 32. 25 of 25 checks; 140.9 kg of steel.

### Footing engine 1.0.0

| Step | Rule | Reference |
|---|---|---|
| Cover | at least 50 mm, more if Table 16 asks | Cl. 26.4.2.2, Table 16 |
| Plan | equal projections; q_max within the safe bearing pressure, q_min not negative, with moments both ways | statics |
| Design pressure | largest factored net pressure, uniform | Table 18 |
| Moments | at the column faces over the full width | Cl. 34.2.3.1, 34.2.3.2 |
| Steel | Annex G; minimum as for slabs; spacing 3d or 300 | Annex G-1.1, Cl. 26.5.2.1, 26.3.3(b) |
| Short-direction steel | 2/(beta + 1) in the central band of width B, the rest outside | Cl. 34.3.1(b) |
| One-way shear | at d from the faces, tau_c of Table 19 | Cl. 34.2.4.1(a) |
| Punching | at d/2, k_s 0.25 sqrt(f_ck) | Cl. 31.6, 34.2.4.1(b) |
| Depth | least in 50 mm steps (from 300) with no compression steel and no shear steel; edge at least 150 | Cl. 34.1.2 |
| Anchorage | L_d within the projection less cover; else 90 degree bends (8 diameters each); else a larger plan | Cl. 34.2.4.3, 26.2.1, 26.2.2.1(b) |
| Bearing | P_u/(b_c D_c) within 0.45 f_ck sqrt(A_1/A_2), at most twice; A_1 in a 1 in 2 frustum | Cl. 34.4 |
| Dowels | at least 0.5 percent of the column area | Cl. 34.4.3 |

Worked example (the defaults): column 300 x 450, 800 kN service, no moment, safe bearing pressure 200 kN/m2, 10 percent own weight, M25 / Fe 415. Plan 2200 x 2050 (A 4.51 m2, q_max 195.1 kN/m2); q_u 266.1 kN/m2; M_L 208.8, M_B 224.1 kN m; D = 450 with T20 (d 390 and 370); A_s 1532 and 1740 mm2: 8-T20 at 270 along L, 8-T20 at 290 along B (the band spacing covers the length, so uniform). One-way shear 0.331 against 0.393 and 0.363 against 0.391 N/mm2; punching 0.915 against 1.25 N/mm2; L_d 806 within 825 mm, straight; bearing 8.89 against 22.5 N/mm2. 16 of 16 checks; 79.9 kg of steel, 2.03 m3 of concrete. At D = 400 no bar size passes with straight bars.

## 9. Validation rules

| Input | Rule |
|---|---|
| Slab spans | l_x 500 to 12 000 mm, l_y 500 to 30 000 mm, l_y not less than l_x |
| Slab thickness, supports | 75 to 500 mm; supports 100 to 1000 mm |
| Slab loads | 0 to 50 kN/m2 each; some load, or the self-weight |
| Slab cover | blank (Table 16) or 15 to 75 mm |
| Footing column | b_c 150 to 2000, D_c 150 to 3000 mm |
| Footing loads | P more than 0; moments 0 or more; own-weight allowance 0 to 40 percent |
| Safe bearing pressure | more than 0, up to 5000 kN/m2 |
| Footing size | L and B both entered or both blank, each larger than the column; D blank or 200 to 3000 |
| Footing grades, cover | M20 to M40; cover blank or 40 to 100 mm (less than 50 is reported Not OK) |

Stop states. Slab: too thin for 8 mm bars; no bar size carries the moments without compression steel. Footing: no plan within 20 m keeps the pressure within limits; an entered depth needs compression steel; an entered plan too small to anchor even 10 mm bars with bends; no depth up to 3 m works. Each message says what to change.

## 10. Unit tests

| Suite | Tests | Proves |
|---|---|---|
| `tests/unit/test_is456_slabs.py` | 28 | Table 27 against printed values; corroborated Table 26 rows; Table 26 structure; interpolation; Tables 12 and 13; k; slab rules |
| `tests/unit/test_slab.py` | 30 | worked example to hand values; Table 26 case from the edges; Table 27 only with free corners, and the flag when corners are free beside a continuous edge; one-way above a ratio of 2 and its coefficients; minimum steel and one bar size; spacing rounding; deflection method; shear and k; failed limits reported; stop; validation; schedule, quantities, drawing; references; a sweep |
| `tests/unit/test_footing.py` | 16 | worked example and minimality; moments both ways; central band and uniform spread; entered depth; bearing with remedy and the frustum limit; anchorage, bent ends and plan growth; cover; stops and validation; schedule and drawing; references; a sweep of 162 inputs with no stop |
| `tests/handcheck/check_slab.py` | 29 base results, 379 values over 18 cases, 1 stop | independent route: Table 26 typed again with its own case mapping (double entry), Table 27 from the unrounded expressions, steel by stress-block bisection, tau_c by the SP 16 closed form |
| `tests/handcheck/check_footing.py` | 29 base results, 384 values over 16 cases (2 with enlarged plans), 2 stops | independent route: plan by a quadratic in the projection, steel by bisection, tau_c closed form, bearing frustum, T10 anchorage for enlarged plans |
| `tests/api/test_structural.py` | 2 new, 1 changed | slab and footing life cycles through the generic endpoints; the registry lists four elements |
| `e2e/walkthrough.js` | slab and footing legs | as for the column; 0 console errors |

## 11. Integration steps

As for 0.2.0. No dependency or migration change.

## 12. Deployment notes

No database change; deploy the new image or restart the single process. Saved beam and column designs are unaffected. Docking layouts stored by 0.2.0 clients still load: the panel ids did not change, only their titles, which now come from the drawing.

## 13. Future enhancements

Panel groups with Annex D-1.1 distribution of unequal support moments; flat slabs; openings and concentrated loads; sloped and stepped footings; the actual pressure distribution for bending under large moments; combined, strap and pile footings. See BACKLOG.md.
