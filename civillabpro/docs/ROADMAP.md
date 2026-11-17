# CivilLabPro OS: roadmap

The platform is built one module at a time. A module is done when its engines are hand-checked, its tests pass on both database engines, and it is reachable from the shell. Nothing is listed as done on the strength of a screen alone.

Phases are ordered by what the next one needs, not by size. No dates are given: each phase is planned when the one before it closes.

## Phase 1: platform core and structural design (in progress)

| Item | State |
|---|---|
| Architecture, schema, roadmap, backlog, code register, project memory | done |
| Identity: organisations, users, JWT sessions, roles, audit trail | done |
| Projects | done |
| Shell: ribbon, sidebar, document tabs, command palette, calculator, shortcuts, themes, PWA | done |
| Dashboard (projects, design status, activity) | done |
| Engineering kernel: calculation sheet, IS 456 rules, drawing model | done |
| Beam engine (rectangular; simply supported and cantilever; flexure, shear, torsion, deflection, detailing) | done, engine 1.0.0 |
| Reports: PDF calculation, Excel bar schedule, DXF drawing | done |
| Revisions and approval | done |
| Section analysis kernel (strain compatibility, Cl. 39.1) | done |
| Column (axial load with biaxial bending, slenderness, ties) | done, engine 1.0.0; clauses to compare with the printed code |
| Charts in the result contract (interaction diagrams) | done |
| Slab (one-way, two-way to Annex D) | next |
| Isolated footing | planned |
| Beam extensions: flanged sections, continuous beams (Table 12 and 13), curtailment, stirrup zones, IS 13920 detailing | planned |

Exit: beam, column, slab and isolated footing designed, hand-checked and issued from one workspace.

## Phase 2: platform completion, estimation and standards library

* Desktop shell (Electron) for Windows and Linux on the single-process backend with SQLite; installer.
* Files and document control; object storage port; Word export.
* Per-project membership and custom roles; OIDC single sign-on; refresh token in an httpOnly cookie.
* Job queue (Redis, Celery) and WebSocket notifications.
* **Standards library**: register of IS, IRC, CPHEEO, MoRTH and NBC with status and amendments; clause index; search; bookmarks; organisation notes.
* **Quantity estimation**: SOR import (CPWD DSR, MoRTH, GWSSB, Gujarat R&B first), rate analysis, BOQ, abstract and detailed estimates, measurement book, running and final bills. Quantities flow in from designs.
* Remaining structural members: combined and strap footing, pile cap, staircase, retaining wall.

Exit: a consultant can design a building frame's members, price them against a state SOR and issue the estimate, on a laptop with no network.

## Phase 3: water engineering

Population forecast, water demand and fire demand, peak factors (CPHEEO manual); transmission main; distribution network with HGL and EGL (solver through the job queue; EPANET import and export); pump selection; ESR, GSR, sump and intake well; rectangular and circular tanks to IS 3370; treatment plant units.

## Phase 4: sewerage engineering

Sewer network design (CPHEEO sewerage manual), manholes, pumping stations, STP process design (ASP, SBR, MBBR, UASB), reuse planning. Box and pipe culverts.

## Phase 5: highway engineering

Flexible pavement (IRC 37), rigid pavement (IRC 58), horizontal and vertical curves, superelevation (IRC 38, IRC 73), cross sections and earthwork, drainage (IRC SP 42), road inventory, MoRTH specification references.

## Phase 6: laboratory information management

Sample register; tests for concrete, cement, steel, aggregate, soil, bitumen, bricks, paver blocks and tiles with code limits; pass and fail; NABL report format; QR verification; digital signature.

## Phase 7: GIS

Map interface (MapLibre GL), PostGIS layers, import and export of Shapefile, GeoJSON, KML and DXF, satellite base maps, utility networks linked to the water and sewer models, land parcels, road network.

## Phase 8: project management

Gantt schedule and dependencies, resources and equipment, inventory, DPR, RFI, daily progress, quality and safety inspections, document control workflows.

## Phase 9: AI assistant

Retrieval over the standards library with citations; calculation review using the kernel's engines as tools; drafting of DPRs, technical notes and BOQ descriptions; drawing review. Built last because it depends on the library, the engines and the document store all existing.

## Later

Android and iOS clients on the same API; 3D model viewer (Three.js) and BIM exchange (IFC); frame analysis.

## How a phase is run

1. Requirements and scope note for the module, with its code set.
2. Codes confirmed and recorded in the code register (edition, amendments, clauses used, interpretations).
3. Domain engine with its worked example, then an independent hand check.
4. API, persistence and migration.
5. Screens, on the shared shell and components.
6. Tests at every level; browser walkthrough.
7. Documents updated: module note, backlog, project memory.
