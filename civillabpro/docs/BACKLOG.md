# CivilLabPro OS: development backlog

Ordered within each epic. IDs are stable: refer to them in commits and in [PROJECT_MEMORY.md](PROJECT_MEMORY.md).
State: **done**, **next** (the item to start with), **ready** (can be started), **later** (needs something before it).

## Done (versions 0.1 to 0.4)

| ID | Item |
|---|---|
| PLAT-001 | Monorepo layout, backend and frontend toolchains, lint, CI |
| PLAT-002 | Configuration with production guards |
| PLAT-003 | Portable schema on PostgreSQL and SQLite, Alembic history, schema drift test |
| IDN-001 | Organisation registration, login, rotating refresh tokens, lockout, password change |
| IDN-002 | Roles and permissions, user administration, last-owner protection |
| IDN-003 | Tenant isolation with tests on every endpoint |
| IDN-004 | Audit trail |
| PRJ-001 | Project register: create, search, filter, update, delete |
| ENG-001 | Calculation sheet model (steps, checks, flags) |
| ENG-002 | IS 456 rule functions with cross-checks |
| ENG-003 | Drawing model with SVG, DXF and PDF renderers |
| STR-001 | Beam engine 1.0.0 with independent hand check |
| STR-002 | Element registry, generic design storage, revisions, approval |
| STR-003 | PDF calculation report, Excel bar schedule, DXF drawing |
| UI-001 | Shell: ribbon, sidebar, document tabs, status bar, themes |
| UI-002 | Command palette with search, floating calculator, shortcuts |
| UI-003 | Design workspace with dockable panels and schema-driven property grid |
| UI-004 | Dashboard, projects, structural catalogue, users and roles |
| OPS-001 | Single-process serving of the client, Dockerfile, compose file |
| OPS-002 | Alembic ignores tables owned by PostgreSQL extensions (0.1.1) |
| STR-010 | Column engine 1.0.0: slenderness, minimum eccentricity, additional moments, biaxial bending, ties (0.2.0) |
| ENG-004 | Section analysis kernel `rc_section` (0.2.0) |
| UI-005 | Charts in the result contract, the workspace and the PDF (0.2.0) |
| ENG-005 | Slab rules kernel `is456_slabs`: Tables 12, 13, 26, 27, Annex D, slab shear factor (0.3.0) |
| STR-011 | One-way slab: simply supported and continuous strips (0.3.0) |
| STR-012 | Two-way slab, corners held down (Table 26) or free (Table 27), torsion steel (0.3.0) |
| STR-013 | Isolated footing: plan, depth, one-way and punching shear, central band, anchorage, bearing (0.3.0) |
| UI-006 | Drawing tabs follow each element's views; vertical text in drawings (0.3.0) |
| STR-014 | Beam engine 1.1.0: flanged sections (T and L), Annex G-2, Fig. 6, rib quantities and drawing (0.4.0) |
| UI-007 | Conditional property rows on a list of values (`show_if` with several values) (0.4.0) |
| PLAT-010 | Desktop app: Electron shell over the one-process server (`app/serve.py`: migrate, then serve, watching the shell), SQLite in the user's data folder, PyInstaller server bundle, Linux AppImage and Windows NSIS installers built and smoke-tested in CI (0.5.0) |
| PLAT-021 | Database sessions end before the response is sent (`Depends(get_db, scope="function")`), with a test over every route: with FastAPI's default scope a write was committed after its success response, so an immediate read could miss it (a defect since 0.1.0, found by the desktop smoke test) (0.5.0) |
| UI-008 | Table fields in the property grid: lists of records from the input schema, rows added and removed, validated cell by cell (0.5.0) |
| STR-015 | Continuous beam 1.0.0: equal spans by Tables 12 and 13, elastic placing of the points of inflection, schedule for the whole beam (0.4.0) |
| ENG-006 | Continuous beam analysis kernel `continuous.py` (three-moment equation, Cl. 22.4.1 arrangements, envelope) (0.4.0) |
| STR-016 | Curtailment (Cl. 26.2.3, with the three conditions of 26.2.3.2) and stirrup zones for the simple and the continuous beam (0.4.0) |
| STR-017 | Anchorage at simple supports and points of inflection, Cl. 26.2.3.3(c), enforced in bar selection, bends and curtailment (0.4.0) |
| STR-038 | Continuous beam 1.3.0: Cl. 26.2.3.3(c) in its bar selection, with its own stop message (0.5.0) |
| STR-042 | Continuous beam 1.6.0: cantilevers at either or both ends (elastic method): their moments in the analysis, each loaded and unloaded; the support designed with top bars to the tip; shear, deflection (ratio 7) and anchorage of the cantilever; bottom bars raised where a support needs compression steel; uplift warned (0.6.0) |
| STR-040 | Continuous beam 1.6.0: support sections designed for the moments at the faces of monolithic supports (Cl. 22.6.2), an option of the elastic method (0.6.0) |
| STR-044 | Strap footing 1.0.0: an exterior column at a property line on an eccentric pad, tied by a rigid strap to an interior column on its own pad; reactions by statics; the strap's hogging, shear zones and stirrups; pad 1 across the strap; pad 2 by the isolated footing engine; bearing for the columns' whole loads (0.7.0) |
| STR-045 | Combined footing 1.1.0: service moments at the columns in the plane of the length; the plan centred on loads and moments, the moments couples in the statics, a flag that they are one load case (0.7.0) |
| STR-020 | Combined footing 1.0.0: two rectangular columns on a rectangular footing of uniform depth; plan centred on the loads or from a property line; bending and shear along and across, bands under the columns, punching (cut by the edges, merged where the perimeters overlap), development at the stress of each section, bearing; strap and trapezoidal footings split to STR-044 (0.6.0) |
| PLAT-018 | Backup and restore (`docs/OPERATIONS.md`): project archives exported and imported between installations as calculated; a backup of a single-organisation SQLite database from the client; restore from the desktop menu, the old database kept (0.6.0) |
| STR-036 | Continuous beam 1.5.0: elastic analysis of two to twelve spans of any length, uniform and point loads, redistribution by Cl. 37.1.1; every span and support designed, detailed, curtailed and drawn; table inputs in the property grid and the report; a view picker for drawings of many views (0.5.0) |
| STR-039 | Continuous beam 1.5.0: bottom bars are not curtailed where a support uses them as compression steel (a defect of 1.1.0 to 1.4.0) (0.5.0) |
| STR-037 | Beam 1.4.0, continuous beam 1.4.0: U-hooks (16 phi) where a 90 degree bend is not enough for Cl. 26.2.3.3(c); L_0 measured to the start of the bend or hook (correcting STR-017), and the footing's bend likewise (footing 1.1.0) (0.5.0) |

## Epic STR: structural design

| ID | Item | State | Notes |
|---|---|---|---|
| STR-009 | Compare the column, slab and footing clauses with the printed code | **blocked** | the three cross-check lists in CODE_REGISTER.md; needs the code text (a download the user approves, or pasted pages) |
| STR-033 | Slab: unequal support moments of adjacent panels (Annex D-1.1 distribution) | ready | needs a panel group: several slabs sharing edges |
| STR-034 | Footing: sloped and stepped footings | ready | Cl. 34.1.2, 34.4 frustum already in place |
| STR-035 | Footing: pressure distribution with moments for bending (instead of the uniform maximum) | ready | lighter footings under large moments |
| STR-041 | Continuous beam: a support width and a section for each span | ready | the elastic method's tables can take them; the schedule already works per span |
| STR-043 | Continuous beam: the coefficient method on the per-span pipeline of the elastic method | ready | one detailing and curtailment path instead of two; outputs per span |
| STR-018 | Beam: calculated deflection and crack width | later | Annex C, Annex F |
| STR-019 | Ductile detailing | later | IS 13920:2016; needs frame context |
| STR-047 | Trapezoidal combined footing, for a heavier column at a property line where a strap does not suit | ready | the combined footing's statics with a width varying along |
| STR-046 | Moments across a combined footing and horizontal loads (sliding, the moment of the shear at the base) | ready | pressure varying across the width, bands designed for the heavier side |
| STR-021 | Pile cap | later | truss and bending methods |
| STR-022 | Staircase | later | |
| STR-023 | Retaining wall (cantilever, counterfort) | later | stability and structural design |
| STR-024 | Water tanks to IS 3370: rectangular, circular, GSR, ESR | later | with phase 3 |
| STR-025 | Box culvert and pipe culvert | later | IRC loading; with phase 4 |
| STR-026 | Load combinations of IS 875 and IS 1893 | later | needed once frame forces are imported |
| STR-027 | Compare two revisions of a design side by side | ready | data already stored |
| STR-028 | Design groups: one design applied to several members, schedule multiplied | ready | |
| STR-029 | Circular columns, and helical reinforcement (Cl. 39.4) | ready | `rc_section` needs a circular section |
| STR-030 | Effective length from storey stiffness (Annex E charts) | later | needs beam and column stiffnesses at both ends |
| STR-031 | Column stack: several lifts, lap positions, bar changes between storeys | later | |
| STR-032 | Column forces imported from an analysis file (STAAD, ETABS exports) | later | with STR-026 |

## Epic PLAT: platform

| ID | Item | State | Notes |
|---|---|---|---|
| PLAT-011 | Auto-update of the desktop app | later | installers exist (PLAT-010); needs a release channel |
| PLAT-022 | Code-signing of the desktop installers | ready | Windows SmartScreen warns on unsigned installers; needs a certificate |
| PLAT-023 | macOS build of the desktop app | later | the shell is platform-neutral; needs a Mac runner and notarisation |
| PLAT-012 | File storage port (S3-compatible and local folder), `files` table | ready | |
| PLAT-013 | Document control register and transmittals | later | after PLAT-012 |
| PLAT-014 | Job queue (Redis, Celery) and job status API | later | first needed by WAT-030 |
| PLAT-015 | WebSocket channel for notifications and job progress | later | with PLAT-014 |
| PLAT-016 | Word export of reports | ready | python-docx, same generic result |
| PLAT-017 | Organisation branding on reports (logo, address, title block) | ready | |
| PLAT-019 | Structured request logging, metrics, error tracking | ready | |
| PLAT-020 | Indian number formatting and optional Hindi / Gujarati interface | later | |

## Epic IDN: identity and access

| ID | Item | State | Notes |
|---|---|---|---|
| IDN-010 | Per-project membership | ready | `project_members` |
| IDN-011 | Custom roles per organisation | later | after IDN-010 |
| IDN-012 | Refresh token in an httpOnly cookie for the web deployment | ready | keep header mode for desktop |
| IDN-013 | OIDC single sign-on (Google, Microsoft, government SSO) | later | |
| IDN-014 | Password reset by email; invitations | ready | needs a mail port |
| IDN-015 | Two-factor authentication (TOTP) | later | |
| IDN-016 | Rate limiting on auth endpoints at the proxy | ready | lockout exists; this adds per-IP limits |
| IDN-017 | Digital signature (DSC) on issued reports | later | with LIMS |

## Epic UI: client

| ID | Item | State | Notes |
|---|---|---|---|
| UI-010 | Edit project details; project settings page | ready | |
| UI-011 | Revision history panel in the workspace | ready | endpoint exists |
| UI-012 | Print view of the calculation sheet from the browser | ready | PDF export exists |
| UI-013 | ESLint with the React hooks rules in CI | ready | TypeScript strict is on |
| UI-014 | Walkthrough script in CI (Playwright) | ready | script exists in `e2e/` |
| UI-015 | Measure and annotate tools on the drawing canvas | later | |
| UI-016 | 3D reinforcement view (Three.js) | later | from the same drawing data plus bar geometry |
| UI-017 | Tablet layout for site use | later | |

## Epics for later phases (broken down when the phase opens)

| Epic | First items |
|---|---|
| STD: standards library | STD-001 register and status import; STD-002 clause index and search; STD-003 bookmarks and notes |
| EST: estimation | EST-001 SOR import format and CPWD DSR; EST-002 rate analysis; EST-003 BOQ from designs; EST-004 measurement book; EST-005 RA and final bills |
| WAT: water | WAT-001 population forecast; WAT-002 demand and peak factors; WAT-010 transmission main; WAT-020 reservoirs; WAT-030 network solver; WAT-040 EPANET exchange |
| SEW: sewerage | SEW-001 sewer reach design; SEW-010 STP processes; SEW-020 pumping station |
| HWY: highway | HWY-001 flexible pavement IRC 37; HWY-002 rigid pavement IRC 58; HWY-010 curves and superelevation |
| LAB: laboratory | LAB-001 sample register; LAB-002 concrete cube test; LAB-010 NABL report and QR verification |
| GIS | GIS-001 map and layers; GIS-002 imports; GIS-010 network link to WAT and SEW |
| PM | PM-001 tasks and Gantt; PM-002 DPR; PM-003 RFI; PM-010 inspections |
| AI | AI-001 LLM gateway port; AI-002 retrieval with citations; AI-003 engines as tools; AI-010 evaluation sets |

## Definition of done (every item that adds or changes an engine)

1. Codes confirmed and entered in [CODE_REGISTER.md](CODE_REGISTER.md) with the clauses used and every interpretation.
2. Domain code pure; each formula line cites its clause; each limit is a check.
3. Defaults are a worked example with its expected values written in the module docstring.
4. Independent hand check in `tests/handcheck/`, by a different method, covering the base case, 10 to 20 alternative cases and every stop state.
5. Unit tests for each branch; a sweep proving no input in range breaks it.
6. API tests on SQLite and PostgreSQL; migration reversible; schema drift test green.
7. Report, schedule and drawing looked at page by page.
8. Browser walkthrough clean, in light and dark.
9. Module note, backlog and project memory updated; engine version bumped.
