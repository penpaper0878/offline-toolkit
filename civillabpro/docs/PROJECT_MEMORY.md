# CivilLabPro OS: project memory

The living record of the project. Read this first in every new session, then the latest entry of the log, then NEXT STEPS. Update it at the end of every piece of work: status, log entry, next steps. It is what lets work resume after a break or a context reset without re-deriving decisions.

## What this is

CivilLabPro OS is an Indian civil engineering operating system: design to Indian codes, estimation, laboratory, GIS, project management and an AI assistant in one application, for web, PWA and desktop. Owner's brief: enterprise grade, production-ready code only, no placeholders, one complete module at a time, every module in the same codebase.

It lives in `civillabpro/` of the `offline-toolkit` repository. The rest of that repository is a separate project (Offline Toolkit); do not mix the two.

## Current status

Version 0.1.0. Phase 1 in progress.

| Area | State |
|---|---|
| Platform core (identity, roles, audit, projects) | built, tested on SQLite and PostgreSQL 16 |
| Shell and client | built, walked through in a browser in light and dark |
| Structural: beam engine 1.0.0 | built, independent hand check passing |
| Exports: PDF, Excel, DXF | built, reviewed page by page |
| Deployment | single-process mode verified; Dockerfile and compose file written, compose validated, image not built (no Docker daemon in the build session) |
| Desktop shell (Electron) | not started (PLAT-010) |
| Modules 3 to 11 | designed in ARCHITECTURE.md and DATABASE_SCHEMA.md, not started |

Test counts at 0.1.0: backend 111 (76 engineering and architecture, 35 API), frontend 15, hand check 360 values over 18 cases plus 2 stop states, browser walkthrough 0 console errors.

## NEXT STEPS

1. **STR-010 column engine.** Confirm IS 456 Cl. 25 and Cl. 39 and SP 16 charts in the code register; build `domain/column.py` as a pure engine with a worked example; hand check against SP 16 interaction charts; add the registry entry. No new endpoint, table or screen should be needed: if one is, the registry pattern has a gap to fix first.
2. STR-011 and STR-012 slabs, STR-013 isolated footing (same loop).
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
* PostgreSQL tests: `CLP_TEST_DATABASE_URL=postgresql+psycopg://... pytest tests/api`.
* The repository root `.gitignore` ignores `fonts/` and `models/` for the other project; `civillabpro/.gitignore` re-includes them.
* Library versions at 0.1.0 are recent majors (React 19, MUI 9, Vite 8, Tailwind 4, TypeScript 7, dockview-react 8, recharts 3, FastAPI 0.16x, SQLAlchemy 2.1). Check the installed typings before assuming an older API.

## Log

### 0.1.0 (16 to 17 November 2026): platform core and beam engine

* Built: identity, projects, structural (beam), dashboard and search on the backend; shell, dashboard, projects, structural catalogue, design workspace and user administration on the client; PDF, Excel and DXF exports; single-process serving; Dockerfile, compose file, CI.
* Beam engine 1.0.0. Worked example: 230 x 450, 4.0 m clear span on 230 supports, M25 / Fe 500, moderate exposure, DL 12 + LL 8 kN/m gives wu 33.881 kN/m, l 4230 mm, Mu 75.78 kN m, Vu 54.07 kN at d from the face, Ast,req 481 mm2, 3-T16 bottom, 2-T12 top, T8 two-legged at 300, 36.3 kg steel, 15 of 15 checks OK.
* Found by tests and fixed during the build: non-converging iteration on effective depth (replaced by judging each bar arrangement at its own depth); rounded neutral-axis ratios disagreeing with SP 16 (now the unrounded strain condition); a slow bar search (sorted with early exit).
* Found in the browser and fixed: MUI Tooltip breaking NavLink class functions; calculator input swallowing global shortcuts; dock layout proportions; drawing caption overlapping the drawing.
* Codes confirmed: IS 456:2000 current, reaffirmed 2021, Amendments 1 to 6; revision in draft. Items to cross-check are listed in the code register.
* Not done, stated plainly: the Docker image was not built (no daemon); the Electron shell is not written; ten of the eleven modules have not been started.
