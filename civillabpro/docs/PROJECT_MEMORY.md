# CivilLabPro OS: project memory

The living record of the project. Read this first in every new session, then the latest entry of the log, then NEXT STEPS. Update it at the end of every piece of work: status, log entry, next steps. It is what lets work resume after a break or a context reset without re-deriving decisions.

## What this is

CivilLabPro OS is an Indian civil engineering operating system: design to Indian codes, estimation, laboratory, GIS, project management and an AI assistant in one application, for web, PWA and desktop. Owner's brief: enterprise grade, production-ready code only, no placeholders, one complete module at a time, every module in the same codebase.

It lives in `civillabpro/` of the `offline-toolkit` repository. The rest of that repository is a separate project (Offline Toolkit); do not mix the two.

## Current status

Version 0.5.0. Phase 1 is done: beams (rectangular, T and L; simple, cantilever and continuous, with curtailment, stirrup zones and anchorage at supports), columns, slabs and isolated footings are designed, hand-checked and issued from one workspace. 0.5.0 adds continuous beams of any spans and point loads by elastic analysis with redistribution, U-hooks, and the desktop app for Windows and Linux, and fixes three defects (bend anchorage counted twice, curtailment of compression steel at continuous supports, writes committed after the response). Still open from phase 1: the comparison of the clauses with the printed code (STR-009, blocked on the code text).

| Area | State |
|---|---|
| Platform core (identity, roles, audit, projects) | built, tested on SQLite and PostgreSQL 16 |
| Shell and client | built, walked through in a browser in light and dark |
| Structural: beam engine 1.4.0 (rectangular, T, L; curtailment, stirrup zones, anchorage with bends and U-hooks) | built, independent hand check passing; Fig. 6, Cl. 23.1.2(c), (d) and 26.2.3 to compare with the code |
| Structural: continuous beam engine 1.6.0 (Tables 12 and 13, or elastic analysis of any spans, point loads and cantilever ends with redistribution and optional face moments; curtailment, zones, anchorage, U-hooks) | built, independent hand check passing; Table 13 and Cl. 22.2(b), 22.4.1, 26.2.3 to compare with the code |
| Structural: column engine 1.0.0 | built, independent hand check passing; code text not yet compared (see the code register) |
| Structural: slab engine 1.0.0 (one-way, two-way) | built, independent hand check passing; Table 26 rows and Annex D extents to compare with the code |
| Structural: isolated footing engine 1.1.0 | built, independent hand check passing; Cl. 34 wording to compare with the code |
| Structural: combined footing engine 1.0.0 (two columns, rectangular, uniform depth) | built (0.6.0), independent hand check passing; the band width across is an interpretation (no clause) |
| Exports: PDF, Excel, DXF | built, reviewed page by page |
| Deployment | single-process mode verified; Dockerfile and compose file written, compose validated, image not built (no Docker daemon in the build session) |
| Desktop app (Electron) | built: shell, PyInstaller server bundle, Linux AppImage verified here (packaged smoke test, a killed shell's server stops itself); Windows NSIS built and smoke-tested by CI only (`civillabpro-desktop.yml`) |
| Backup, restore, project transfer | built (0.6.0): project archive export and import, backup from the client for a single-organisation SQLite database, restore from the desktop menu; procedures in OPERATIONS.md |
| Modules 3 to 11 | designed in ARCHITECTURE.md and DATABASE_SCHEMA.md, not started |
| Cloud environment | personal environment `offline-toolkit` (allows law.resource.org; setup script installs the venv, npm packages and PostGIS). The script is unproven until a fresh session starts on it. |

Test counts at 0.5.0: backend 345 (298 engineering, architecture, hand checks and the server entry; 47 API, one of them PostgreSQL-only); frontend 22; desktop launcher 8; hand checks: beam 716 values over 27 cases, continuous beam 897 over 15, continuous beam by elastic analysis 936 over 14, column 471 over 17, slab 379 over 18, footing 384 over 16, with 1 to 3 stop states each; browser walkthrough with beam, column, slab, footing and continuous beam by both methods, 0 console errors; desktop smoke test of the packaged app (Linux here, Linux and Windows in CI).

## NEXT STEPS

1. **STR-009, blocked: compare the column, slab and footing clauses with the code text** (the three "To cross-check" lists in the code register). It needs the user: either approval of a direct download of the public copy, or the pages pasted into the session. Do not work around a declined download. Fix anything that differs and re-run every hand check.
2. **The continuous beam's follow-ups**: STR-041 a support width and section per span, STR-043 the coefficient method on the per-span path.
3. **Desktop**: PLAT-022 code-signing (needs a certificate), PLAT-011 auto-update.
4. **Footings**: STR-044 strap and trapezoidal footings, STR-045 column moments on combined footings.
5. **Phase 2's engineering**: the estimation module and the standards library (see ROADMAP.md).

## Decisions (do not reopen without a reason recorded here)

| # | Decision | Why |
|---|---|---|
| D1 | Modular monolith, clean layers per module, boundaries enforced by a test | one transactional record, small team, desktop must be one process |
| D2 | Engines are pure functions returning a calculation sheet | reproducible, auditable, testable without a server |
| D3 | Element registry: one endpoint, one table, one exporter, one screen for all structural elements | modules grow by adding domain code only |
| D4 | Property grid generated from the input model's JSON schema (`group`, `unit`, `show_if`, `labels`) | no per-element form code in the client |
| D5 | Drawing model of primitives rendered to SVG, DXF and PDF | one description, three outputs |
| D6 | Portable schema: UUID, UTC timestamps, JSON documents; one Alembic history for PostgreSQL and SQLite | offline desktop without a second code path |
| D7 | Synchronous SQLAlchemy sessions | calculations are CPU work; simpler and as fast here |
| D8 | Roles are code-defined permission sets; endpoints ask for a permission | custom roles later without touching endpoints |
| D9 | Four-eyes approval; revising withdraws approval; `CLP_ALLOW_SELF_APPROVAL` for one-person firms | what a design office expects |
| D10 | Single-process mode (`CLP_STATIC_DIR`) is the desktop and small-server deployment | one artefact to package |
| D11 | Redis, Celery and WebSockets are introduced with the first feature that needs them | no unused infrastructure |
| D12 | The AI assistant never produces design numbers; it calls the engines and cites clauses | engineering accountability |
| D13 | No code text is shipped; the library holds references and the organisation's notes | BIS copyright |
| D14 | Bundled DejaVu Sans in reports | Greek letters and maths signs identical on every machine |
| D15 | Bars are chosen for least total steel among arrangements that satisfy Annex G, Cl. 26.5.1, Table 15 spacing and Cl. 38.1(f), each judged at its own effective depth | consistent without iteration |
| D16 | The generic result contract carries optional `charts` (axes, series of `line` or `point`); the workspace and the PDF render any element's charts | interaction diagrams without a column-specific screen |
| D17 | Section analysis under axial load and bending lives in the kernel (`rc_section.py`), not in the column module | footings, walls and pile caps need it too |
| D18 | Column bars are chosen by least steel per metre including ties and cross-ties, each arrangement judged with its own P_b, P_uz and k | main steel alone picks many small bars that cost more ties |
| D19 | The workspace validates the debounced values it sends, not only the values on screen | a pause on an invalid entry otherwise sent a stale request |
| D20 | Titles and notes render in prose mode (no " x " to "×", no "sqrt" to "√"); formulas in maths mode | "about the x axis" printed as "about the × axis" |
| D21 | Slab tables live in the kernel (`is456_slabs.py`); Table 27 is generated from its expressions, not transcribed | one copy for slabs, footings, tanks and continuous beams; a derived table cannot carry a typing slip |
| D22 | The workspace's two drawing panels show an element's first and second views and take their titles; panel ids stay fixed | plans for slabs and footings, sections for members, and saved layouts keep working |
| D23 | Footing bars: straight at any depth before bent ends; an automatic plan grows to anchor the bars rather than stopping | site practice prefers straight bars; a stop for a small, lightly loaded footing told the user nothing useful |
| D24 | Top bars over a support shared with the next panel are scheduled whole with the panel being designed, and the schedule says so | one schedule per design, no half bars; the adjacent panel leaves them out |
| D25 | Flanged beams are an option of the beam element (`section`), not a separate element; flexure dispatches on whether the flange is in compression | one engine, one hand check and one schedule for every beam; continuous beams need both cases in one design |
| D26 | `show_if` may list several values | the flange rows serve both T and L sections without duplicating fields |
| D27 | A continuous beam is its own element designed whole (3 to 12 equal spans), reusing the beam's section routines | per-span designs would schedule the bars over a shared support twice or leave them undeveloped |
| D28 | Design moments of continuous beams from Table 12; points of inflection from an elastic analysis of the Cl. 22.4.1 arrangements | the coefficients give no moment diagram; combining Table 12 peaks with a span carrying dead load alone is not a real case and over-extends the bars |
| D29 | Curtailment diagrams of the continuous beam: the elastic envelope scaled up (never down) to the Table 12 and 13 values | consistent with the sections as designed and with the real arrangements of load |
| D30 | Cl. 26.2.3.2 is one shared function for both beams, trying (a), then (c), then (b) with closer stirrups; curtailment is skipped where it saves nothing | (a) alone rejected most practical cut-offs |
| D31 | Unequal spans and point loads are a second method of the continuous beam element (`analysis`), with its own per-span engine and detailing beside the coefficient method's | one element and one workspace for continuous beams; the coefficient engine's outputs and hand check stay as released (porting it onto the per-span path is STR-043) |
| D32 | Lists of records (spans, point loads) are table fields of the input schema: the server inlines their rows' schema, the grid edits them as tables, the report prints a line per row | the registry pattern carries any element's tabular input; no element-specific form code |
| D34 | Every route takes its session as `Depends(get_db, scope="function")`; a test walks all routes | the commit, and any error it raises, must come before the client hears of success |
| D33 | The redistribution entered is a maximum: a support whose section cannot meet Cl. 37.1.1(d) with it takes 5 percent less, recorded on the sheet | the designer's intent survives a section that cannot take all of it, instead of a stop |
| D35 | A project travels as a JSON archive and is imported as calculated, never recalculated, by a `transfer` context that copies rows across the projects and structural tables (the second sanctioned exception after the dashboard); the client's backup is offered only for SQLite holding one organisation | an issued calculation must arrive with the numbers it was issued with; the structural service would recalculate and revise; no owner may download another tenant's rows |
| D36 | A combined footing with its plan left to the engine is centred on the resultant with the left end that balances the greatest sagging and hogging along it, among footings no wider than they are long, and the least width the bearing allows; its bands across are the column's depth plus 0.75 d each side | least concrete always pushed a column to the footing's end; balanced moments is the textbook economy and gives the least steel in the worked example; the band width is the middle of the published range (b + d to b + 2d) |

Engineering interpretations are in [CODE_REGISTER.md](CODE_REGISTER.md), not here.

## Conventions

* **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2, Pydantic 2. Settings from `CLP_*` environment variables. Errors as `{"error": {"code", "message", "details"}}`. Every service function filters by `org_id`; another tenant's record is `NotFound`.
* **Domain code**: N, mm, N/mm2 inside rule functions; kN, kN m, mm at engine inputs and in the sheet. Symbols in sheet text use the markup `f_ck`, `x_u,max`, `tau_c`, `gamma_f`, `eps_sc`, `^2`, `sqrt`, `<=`, ` x ` (rendered by `Fx.tsx` on screen and `fx()` in the PDF).
* **References**: `IS 456:2000, Cl. 26.5.1.1(a)`, also `Table`, `Fig.`, `Annex`. Inputs show `Input`; choices show `Selected`; pure statics show `Statics`.
* **Verdicts**: OK / Not OK with a utilisation where a ratio has meaning. Status on screen is always an icon and a word.
* **Writing in the product**: sentence case, plain verbs, errors say what to enter.
* **Frontend**: TypeScript strict; Tailwind for layout, MUI for controls; colours only through the CSS tokens in `index.css`; no external requests.
* **Tests**: a hand check per engine; API tests run on both databases; a schema drift test guards migrations.
* **Commits**: one concern each; no model names in commit messages or code.

## How to add a structural element (the checklist the registry exists for)

1. `backend/app/modules/structural/domain/<element>.py`: a frozen Pydantic input model using `_f(...)` field metadata, and `design_<element>(inp) -> dict` returning the generic result (see `DesignResult` in `structural/schemas.py`). Defaults are a worked example; expected values go in the module docstring.
2. Detailing (schedule, quantities, drawing) beside it.
3. `tests/handcheck/check_<element>.py` from the code text, by a different method. `tests/unit/test_<element>.py` for branches, stop states and a sweep.
4. One entry in `domain/registry.py`.
5. Look at the PDF, the Excel file and the DXF; run `e2e/walkthrough.js`.
6. Code register, backlog, this file, module note.

## How to add a module

`backend/app/modules/<name>/` with `domain/`, `models.py`, `schemas.py`, `service.py`, `router.py`; include the router in `app/main.py`; import the models in `modules/models_registry.py`; `alembic revision --autogenerate`, then replace app types with `sa.` types in the generated file; add the entry in `frontend/src/app/modules.ts`, the route in `App.tsx` and the sidebar icon.

## Environment notes

* Backend: `cd civillabpro/backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`; `pytest`; `uvicorn app.main:app --reload`.
* Frontend: `cd civillabpro/frontend && npm ci && npm run dev` (proxies `/api` to 127.0.0.1:8000).
* PostgreSQL tests: `CLP_TEST_DATABASE_URL=postgresql+psycopg://... pytest tests/api`. Test against a database with the PostGIS extensions installed (as CI and the compose file do), not only plain PostgreSQL: see the 0.1.1 log entry.
* A throwaway local PostgreSQL cluster must not live in the scratchpad: its folder permissions get reset and the server aborts. Use the postgres user's home, `/var/lib/postgresql/`.
* The repository root `.gitignore` ignores `fonts/` and `models/` for the other project; `civillabpro/.gitignore` re-includes them.
* Library versions at 0.1.0 are recent majors (React 19, MUI 9, Vite 8, Tailwind 4, TypeScript 7, dockview-react 8, recharts 3, FastAPI 0.16x, SQLAlchemy 2.1). Check the installed typings before assuming an older API.

## Log

### 0.6.0 in progress (20 November 2026): STR-020 combined footing

* Built: the `combined_footing` element (engine 1.0.0, a domain module, detailing, hand check and registry entry). Two columns on a rectangular footing of uniform depth, centred on the loads or from a property line; bending along (sagging at the faces, hogging between) and across (bands under the columns); one-way shear along and across; punching cut by the edges or merged; development at the stress of each section; bearing; charts, schedule, three drawing views. Interpretations 95 to 103 (D36).
* Rejected on the way: choosing the left end for the least concrete always drove column 1 to the end of the footing; the left end now balances the sagging and hogging (D36).
* Hand check: 75 values of the worked example and 1467 over 21 cases, 1 stop; six sabotages each fail it.

### 0.6.0 in progress (20 November 2026): PLAT-018 backup, restore and project transfer

* Built: a `transfer` context (D35). Export project saves a `.clp.json` archive with the designs, revisions and review record; Import project makes a new project from it (free job number, names kept as text, refusals of unknown elements and inconsistent results, audit). Download a backup on the new Data and backup page (owner only; SQLite with one organisation; `VACUUM INTO`). Desktop File menu: Back up data, and Restore from backup (the old database kept as `before-restore`, undone if the server will not start). `docs/OPERATIONS.md` covers the desktop, SQLite servers and PostgreSQL (`pg_dump`, `pg_restore`).
* Verified: API tests on SQLite and PostgreSQL (the backup refuses PostgreSQL with the pg_dump pointer); launcher tests for the swap and undo; the desktop smoke test backs up, adds a project, restores and finds it gone with the designs back; the browser walkthrough exports, imports as `-2` and downloads a backup.

### 0.6.0 in progress (20 November 2026): STR-042 cantilever ends

* Built: cantilevers at either or both ends of a continuous beam (elastic method): known end moments in the analysis, each cantilever loaded and unloaded, the support designed with top bars to the tip, the cantilever's shear, deflection and anchorage, its schedule rows and drawing, uplift warnings. Continuous beam 1.6.0.
* Found and fixed: a support short of compression steel stopped the design (a left cantilever lightens span 1's bottom bars); the engine now raises the lighter span's bottom bars first, and redistributes less only where that cannot help.
* Hand check: elastic 1223 values over 17 cases; a sabotaged cantilever length fails it on 47 values.

### 0.6.0 in progress (20 November 2026): STR-040 face moments

* Built: the elastic method designs the supports for the moments at their faces where the construction is monolithic (Cl. 22.6.2), as an option; Cl. 37.1.1(d) judged at the same face. Continuous beam 1.6.0. Release note `docs/modules/06-faces-cantilevers-backup-combined-footing.md`.
* Hand check: elastic 1060 values over 15 cases.

### 0.5.0 released (20 November 2026)

* Released: version 0.5.0, samples and screenshots regenerated, README and roadmap updated. CI green on the release commit: backend (SQLite and PostgreSQL), frontend, and the desktop workflow on Ubuntu and Windows. The Windows packaged app passed the smoke test in CI: every element designed, 18 exports recognised. The NSIS installer and the AppImage are kept as build artifacts.
* Found and fixed: the first Windows run failed two launcher tests, which asked for Linux paths on a Windows host; `paths()` now uses the path rules of the platform asked about.

### 0.5.0 in progress (19 November 2026): PLAT-010 desktop app

* Built: `app/serve.py` (migrate with Alembic, then serve with uvicorn; `--parent-pid` stops the server when the shell is gone); `desktop/`: Electron shell (`main.js`: splash, single instance, window locked to the local origin, menu, `--smoke-test`), launcher (`launcher.js`: paths, environment, signing key, kept port, start, health wait, stop), PyInstaller bundle script, electron-builder config (AppImage, NSIS), README; CI workflow building and smoke-testing the packaged app on Ubuntu and Windows.
* Verified here: launcher tests (8); the shell from a checkout and the packaged app (unpacked and AppImage) pass the smoke test (sign up, every element designed, 18 exports fetched and recognised through the window); a SIGKILLed shell's server shuts down cleanly within seconds. Not verified here: the Windows installer (CI builds and smoke-tests it).
* Found and fixed (PLAT-021): every route's session committed after the response was sent (FastAPI's default dependency scope), so the smoke test's first read after a write could get "not found". Sessions are now scoped to the path operation, with a test over every route.

### 0.5.0 in progress (19 November 2026): STR-036 continuous beams by elastic analysis

* Built: the continuous beam's elastic method. Kernel: any spans with uniform and point loads (three-moment equation), the arrangements of Cl. 22.4.1, redistribution by Cl. 37.1.1 per support, envelopes with stations either side of every point load. Engine `continuous_elastic.py`: effective spans, per-span and per-support design with Cl. 37.1.1(b), (c), (d), shear at d (or at the face beside a point load), stirrup bands, curtailment, anchorage, laps of meeting top bars by developed resistance, charts. Detailing `continuous_elastic_detailing.py`: per-span layout, merged schedule, an elevation per span. Table fields in the property grid and the report (D32); a view picker in the drawing panels; charts draw negative values.
* Found and fixed while building it: the first lap check of meeting top bars took the weaker set without compression steel across the whole overlap and failed 141 of 400 random designs; it is now a check of the developed resistance at every section. The "Number of spans" field had its condition in the unit slot. A section that cannot take all the redistribution entered now takes less instead of stopping (D33).
* Hand check `check_continuous_elastic.py`: Hardy Cross with point-load fixed-end moments, statics from the left reaction, the resistance diagram against the design envelope (and so 0.7 of the elastic one), anchorage, extents, cut-offs, every stirrup gap; 936 values over 14 cases and 2 stops. Sabotage runs (a point-load term from the wrong end, no redistribution cap, anchorage at the points of inflection switched off, stirrups 10 percent wider) each fail it.

### 0.5.0 in progress (19 November 2026): STR-038 and STR-037 anchorage completed

* Built: STR-038, the continuous beam's bar selection passes over bottom bars that cannot be anchored at the end supports or the points of inflection (continuous beam 1.3.0). STR-037, U-hooks where a bend is not enough, chosen as the least end detail that passes, in both beams' selection, check, schedule and drawing (beam 1.4.0, continuous beam 1.4.0).
* Found and fixed: L_0 with a bend counted the r + phi of bar inside the bend twice (5 phi too much for deformed bars). STR-017's interpretation 73 and the footing's interpretation 37 are corrected (footing 1.1.0). `rebar.bend_radius` holds the IS 2502 radii for all three.
* Found and fixed (STR-039): the continuous beam's bottom-bar curtailment could stop bars that a support section relied on as compression steel (66 of 193 sampled designs). Curtailment is now withdrawn there (continuous beam 1.5.0), and the hand check recomputes each support with the bars that actually reach it; without the fix it fails the T-beam floor case.
* Hand checks: beam 716 values over 27 cases and 3 stops; continuous beam 897 over 15 cases and 3 stops; footing 384 over 16.

### 0.4.0 (19 November 2026): STR-017 anchorage, release; phase 1 closed

* Built: Cl. 26.2.3.3(c) for both beams (`anchorage_ok`, `anchorage_check`, `is456.moment_at_design_stress`): enforced in the simple beam's bar selection, by bends where straight bars fall short, and by withdrawing curtailment where the continuing bars alone would fail; the continuous beam checks its end supports and the points of inflection. Beam engine 1.3.0, continuous beam 1.2.0. Release 0.4.0: version, walkthrough leg for the continuous beam, samples, screenshots, README.
* Found and fixed: M_1 was first capped at x_u,max like the moment checks, which is not the clause's "all reinforcement stressed to f_d" and rejected beams that pass; the stop message when only anchorage rejects every arrangement now says so.
* Test counts at 0.4.0 are in the status section.

### 0.4.0 in progress (19 November 2026): STR-016 curtailment and stirrup zones

* Built: beam engine 1.2.0 and continuous beam engine 1.1.0 with curtailment (Cl. 26.2.3.1 to 26.2.3.4, the three conditions of 26.2.3.2) and stirrup zones; `continuous.shear_envelope`; `continuous_curtailment.py`; schedules split into continuing and curtailed bars; stirrups from their positions; drawings show both. Two commits: the simple beam, then the continuous beam.
* Worked examples: simple beam 36.3 to 32.8 kg; four-span continuous beam 388.6 to 322.3 kg, all checks OK.
* Found on the way: condition (a) alone rejected most cut-offs (condition (b) added); a cut-off 50 mm from a support saves nothing (rule: not within d); the hand check's own bisection was written wrong once (fixed in the check, not the engine); it needed the compression steel the engine counts; pattern loading flattens and moves the interior span's peak, and L_d from a single peak point left 8 mm of margin against the hand envelope (L_d now from both edges of the peak region).

### 0.4.0 in progress (19 November 2026): STR-015 continuous beams

* Built: `engineering/continuous.py` (three-moment equation, Cl. 22.4.1 arrangements, points of inflection, envelope); continuous beam element 1.0.0 (`continuous_beam.py`, `continuous_beam_detailing.py`, registry entry): Cl. 22.2(b) spans, Tables 12 and 13, four design sections, shear and deflection per span type, top bars to the elastic points of inflection plus Cl. 26.2.3.4, hangers lapped in compression, bars that meet lapped at mid-span with a check, schedule and quantities for the whole beam, elevation and two sections. Beam helpers made public and the cross-section drawing extracted for reuse (beam drawing output unchanged, verified). Quantities heading kept with its table in the PDF.
* Worked example: 4 spans of 5 m, 300 x 500, M25 / Fe 500, DL 25 + LL 15: 5-T16 / 4-T16 bottom, 6-T16 over B, 10-T12 over C, 37 of 37 checks, 388.6 kg.
* Hand check: 368 values over 12 cases; the points of inflection by Hardy Cross agree with the engine's three-moment solution to 0.1 mm.
* Found and fixed before committing: the first placing of the points of inflection (Table 12 peaks at both ends of a span carrying dead load alone) is not a real load case and ran the top bars through every interior span; support bars that met kept their full extents and doubled the steel (now lapped at mid-span); a dimension showed the distance to the drawing's break instead of the bars' extent; one hand-check case was set up too heavy for two-legged T8 stirrups (the engine rightly reported it Not OK).
* The session's worker restarted mid-way; the working tree was intact and the work resumed from it.

### 0.4.0 in progress (18 November 2026): STR-014 flanged beams

* Built: flanged-section rules in the kernel (`is456.py`: effective width, Annex G-2 compression, design and capacity, Fig. 6); beam engine 1.1.0 with `section` (rectangular, T, L) and the flange inputs; rib self-weight and quantities; section drawing with the flange and chained depth dimensions; `show_if` with a list of values (grid and PDF). Details in `docs/modules/04-beam-extensions.md`.
* Worked example: T-beam 300 x 550, slab 120, beams at 3 m, 6 m clear span, M25 / Fe 500, DL 30 + LL 15 kN/m: b_f 2070, axis in the flange, A_st,req 1732 mm2, 9-T16, 15 of 15 checks.
* Hand check: 8 flanged cases added (axis in flange and web, y_f < D_f, isolated T and L, doubly reinforced, entered l_0, cantilever with the flange in tension); 501 values over 25 cases agree.
* Code text: not read. Fig. 6 is the item most worth comparing (one secondary source tabulates different points).
* A comparison I first wrote into the module note (the rectangle needing about 4 percent more steel) was wrong; measured, it is 18 percent, and the note now gives the measured figures.

### 0.3.0 (18 November 2026): RCC slab and isolated footing

* Built: `is456_slabs` kernel (Tables 12, 13, 26, 27, Annex D, k); slab engine 1.0.0 with detailing (one-way and two-way, edge strips, top bars, torsion mats, distribution bars); footing engine 1.0.0 with detailing (plan, depth, one-way and punching shear, central band, anchorage with bends, plan growth for anchorage, bearing with the 1 in 2 frustum, dowels); two registry entries; drawing tabs that follow the element's views; vertical text in drawings (screen, PDF, DXF); slab and footing legs in the walkthrough and in the API tests. Details in `docs/modules/03-slab-and-footing.md`.
* Worked examples: slab 3.3 x 4.5 m corner panel, D 150, M25 / Fe 415: Table 26 case 4, M_x+ 7.36 kN m/m, T8 at 270 both ways, T8 at 200 and 280 top, 140.9 kg, 25 of 25 checks. Footing 300 x 450 column, 800 kN, 200 kN/m2: 2200 x 2050 x 450, 8-T20 at 270 and 290, punching 0.915 against 1.25 N/mm2, 79.9 kg, 16 of 16 checks.
* Code text: still not read (same reason as 0.2.0). Table 27 verified by derivation; Table 26 by structure tests, a double-entry hand check and the rows secondary sources reproduce. The code register lists the rest.
* Found and fixed during the build: footing moments 1000 times too small (a unit slip, caught by the hand check); outer parts of the short-direction steel narrower than a practical spacing (now spread uniformly); T25 chosen although it could not develop in the projection (anchorage added to the selection); short projections stopping the design (bent ends); bent ends chosen over straight bars at a greater depth (straight first); small footings on strong soil stopping (plan growth); the bearing area ignoring the footing depth (the frustum); slab top steel over short edges using the short-span depth; distribution bars sized for the longer edge in both directions; rule steps printing 0; the slab's short-edge labels over the l_x dimension (vertical text); a uniform spread labelled as a band; slab and footing plans missing from the workspace (the panel looked for a view named "section").
* Version 0.3.0 (backend and client).

### 0.2.0 (17 November 2026): RCC column

* Built: `rc_section` kernel; column engine 1.0.0 with detailing; registry entry; `charts` in the result contract; chart panel in the workspace and charts in the PDF; prose rendering of titles; leader labels anchored away from their points (screen, PDF, DXF); a column leg in the browser walkthrough. Details in `docs/modules/02-rcc-column.md`.
* Worked example: 300 x 450, l 3.6 m, M25 / Fe 500, P_u 1200 kN, M_ux 90 (-45), M_uy 30 (10): slender about y only, k_y 0.484, ratios 0.879 and 0.908, 12-T12 (5 + 3), T8 at 175 with two cross-ties, 66.1 kg.
* Code text: law.resource.org was blocked by the network policy. A personal environment `offline-toolkit` allowing it was created and this session moved onto it, but the page-fetching tool resolves names outside the proxy and still could not reach it, and the direct download through the proxy was declined by the permission check. The clauses were corroborated through secondary sources; the code register lists what remains to compare.
* Found and fixed during the build: cross-ties hidden under the axis lines in the section drawing; labels left of a leader running back across the drawing; notes orphaned on their own PDF page; "x axis" rendered as a product; coincident design points with overlapping labels; and, in the workspace, a stale invalid request sent after correcting an input (reproduced deterministically in the walkthrough before the fix, and gone after it).
* Hand check of the column: one disagreement, the balanced load of a 230 x 230 column (3.61 against 3.69 kN). Shown to be the rounding of SP 16 Table A acting on forces that cancel: the engine gives the hand value exactly when fed Table A's stresses. The comparison now measures P_b against the force scale.
* Version 0.2.0 (backend and client).

### 0.1.1 (17 November 2026): CI fix for PostGIS databases

* The first CI run failed at `alembic check` on the PostgreSQL job. The CI service (and the production compose file) use the PostGIS image, which installs `postgis`, `postgis_topology` and `postgis_tiger_geocoder`; these add their schemas to the database `search_path`, and SQLAlchemy reflects every table visible on it. Alembic therefore reported `spatial_ref_sys`, the topology tables and about forty geocoder tables as tables to drop. Local testing had used plain PostgreSQL, so it passed there.
* Fix: `app/core/migrations.py` gives Alembic an `include_name` hook that leaves out relations PostgreSQL records as extension members (`pg_depend`, `deptype = 'e'`) unless a model defines the same name. Real drift is still reported.
* The first version of the fix read the catalogue before Alembic opened its transaction, which made Alembic leave the commit to the caller: `upgrade` ran and was rolled back. The lookup is now lazy and happens only during comparison. Both mistakes are covered by `test_extension_tables_are_ignored_but_real_drift_is_not` (runs when `CLP_TEST_DATABASE_URL` is PostgreSQL), which upgrades, compares, and checks that only a deliberately stray table is reported.
* Verified locally on PostgreSQL 16 with PostGIS 3 and the same four extensions as the CI image, on plain PostgreSQL 16, and on SQLite.

### 0.1.0 (16 to 17 November 2026): platform core and beam engine

* Built: identity, projects, structural (beam), dashboard and search on the backend; shell, dashboard, projects, structural catalogue, design workspace and user administration on the client; PDF, Excel and DXF exports; single-process serving; Dockerfile, compose file, CI.
* Beam engine 1.0.0. Worked example: 230 x 450, 4.0 m clear span on 230 supports, M25 / Fe 500, moderate exposure, DL 12 + LL 8 kN/m gives wu 33.881 kN/m, l 4230 mm, Mu 75.78 kN m, Vu 54.07 kN at d from the face, Ast,req 481 mm2, 3-T16 bottom, 2-T12 top, T8 two-legged at 300, 36.3 kg steel, 15 of 15 checks OK.
* Found by tests and fixed during the build: non-converging iteration on effective depth (replaced by judging each bar arrangement at its own depth); rounded neutral-axis ratios disagreeing with SP 16 (now the unrounded strain condition); a slow bar search (sorted with early exit).
* Found in the browser and fixed: MUI Tooltip breaking NavLink class functions; calculator input swallowing global shortcuts; dock layout proportions; drawing caption overlapping the drawing.
* Codes confirmed: IS 456:2000 current, reaffirmed 2021, Amendments 1 to 6; revision in draft. Items to cross-check are listed in the code register.
* Not done, stated plainly: the Docker image was not built (no daemon); the Electron shell is not written; ten of the eleven modules have not been started.
