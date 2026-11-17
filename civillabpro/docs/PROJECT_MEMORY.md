# CivilLabPro OS: project memory

The living record of the project. Read this first in every new session, then the latest entry of the log, then NEXT STEPS. Update it at the end of every piece of work: status, log entry, next steps. It is what lets work resume after a break or a context reset without re-deriving decisions.

## What this is

CivilLabPro OS is an Indian civil engineering operating system: design to Indian codes, estimation, laboratory, GIS, project management and an AI assistant in one application, for web, PWA and desktop. Owner's brief: enterprise grade, production-ready code only, no placeholders, one complete module at a time, every module in the same codebase.

It lives in `civillabpro/` of the `offline-toolkit` repository. The rest of that repository is a separate project (Offline Toolkit); do not mix the two.

## Current status

Version 0.2.0. Phase 1 in progress: beam and column built; slabs and footing next.

| Area | State |
|---|---|
| Platform core (identity, roles, audit, projects) | built, tested on SQLite and PostgreSQL 16 |
| Shell and client | built, walked through in a browser in light and dark |
| Structural: beam engine 1.0.0 | built, independent hand check passing |
| Structural: column engine 1.0.0 | built, independent hand check passing; code text not yet compared (see the code register) |
| Exports: PDF, Excel, DXF | built, reviewed page by page |
| Deployment | single-process mode verified; Dockerfile and compose file written, compose validated, image not built (no Docker daemon in the build session) |
| Desktop shell (Electron) | not started (PLAT-010) |
| Modules 3 to 11 | designed in ARCHITECTURE.md and DATABASE_SCHEMA.md, not started |
| Cloud environment | personal environment `offline-toolkit` (allows law.resource.org; setup script installs the venv, npm packages and PostGIS). The script is unproven until a fresh session starts on it. |

Test counts at 0.2.0: backend 178 (140 engineering, architecture and hand checks; 38 API, one of them PostgreSQL-only); frontend 18; hand checks: beam 360 values over 18 cases, column 506 values over 18 cases, 2 stop states each; browser walkthrough with beam and column, 0 console errors.

## NEXT STEPS

1. **Compare the column clauses with the code text** (the "To cross-check" list in the code register). Reading law.resource.org needs either the environment's network (now allowed) plus approval of a direct download, or the user pasting the pages. Fix anything that differs and re-run both hand checks.
2. **STR-011 and STR-012 slabs**, then **STR-013 isolated footing** (the footing can use `rc_section` for column-to-footing checks). Same loop: codes, engine, hand check, tests, registry entry.
3. Beam extensions STR-014 to STR-017.
4. PLAT-010 desktop shell.

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
