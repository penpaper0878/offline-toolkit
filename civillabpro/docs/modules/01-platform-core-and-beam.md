# Release note 0.1.0: platform core and RCC beam design

Follows the project's standard format for every increment.

## 1. Requirements analysis

**Goal of the increment.** A working application that one organisation can sign in to, hold projects in, and use to design a reinforced concrete beam to IS 456:2000 with everything a design office issues: calculation, bar bending schedule, quantities and drawing.

**In scope.** Organisations and users with roles; projects; rectangular beams, simply supported or cantilever, under uniformly distributed load or factored forces from an external analysis, with optional torsion; revisions and approval; PDF, Excel and DXF output; dashboard and search.

**Out of scope, by decision.** Flanged and continuous beams, curtailment, calculated deflection, IS 13920 detailing (backlog STR-014 to STR-019); the other ten modules; the desktop shell.

**Who uses it.** Design engineer (creates and revises), reviewer (approves), administrator (people and roles), viewer (reads and downloads).

## 2. System architecture

See [ARCHITECTURE.md](../ARCHITECTURE.md). This increment established the pattern every later module follows: pure domain engine, application service, thin router, generic exporters, schema-driven screen, all joined by the element registry.

## 3. Database changes

Migration `0001`: `organizations`, `users`, `refresh_tokens`, `audit_log`, `projects`, `structural_designs`, `structural_design_revisions`. Column lists in [DATABASE_SCHEMA.md](../DATABASE_SCHEMA.md), part 1.

## 4. API endpoints

Base path `/api/v1`. Interactive documentation at `/api/docs`.

| Method and path | Permission | Purpose |
|---|---|---|
| POST `/auth/register` | open (can be switched off) | create an organisation and its owner |
| POST `/auth/login` | open | OAuth2 password grant; returns access and refresh tokens |
| POST `/auth/refresh`, `/auth/logout` | refresh token | rotate or revoke |
| GET `/auth/me` | signed in | profile and permissions |
| POST `/auth/change-password` | signed in | |
| GET, POST `/users`; PATCH `/users/{id}` | `user:manage` | people and roles |
| GET `/users/roles` | signed in | what each role may do |
| GET `/users/audit` | `audit:read` | audit trail |
| GET, POST `/projects`; GET, PATCH, DELETE `/projects/{id}` | `project:read` / `write` / `delete` | project register |
| GET `/structural/elements` | `design:read` | element types with defaults and input schema |
| POST `/structural/{type}/calculate` | `design:read` | run an engine without saving |
| GET, POST `/projects/{id}/designs` | `design:read` / `write` | list, save |
| GET, PUT, DELETE `/designs/{id}` | `design:read` / `write` / `delete` | open, revise, delete |
| POST `/designs/{id}/approve` | `design:approve` | approval by a second person |
| GET `/designs/{id}/revisions` | `design:read` | superseded states |
| GET `/designs/{id}/report.pdf`, `/bbs.xlsx`, `/drawing.dxf` | `design:read` | issue documents |
| GET `/dashboard/summary`, `/search?q=` | `project:read` | read models |
| GET `/health` | open | liveness and database engine |

## 5. Backend implementation

| Path | Content |
|---|---|
| `app/core/` | settings, engine and session, password and token handling, error envelope, permission guards |
| `app/engineering/trace.py` | calculation sheet: steps, checks, flags |
| `app/engineering/is456.py` | one function per clause |
| `app/engineering/drawing.py`, `rebar.py` | drawing primitives, bar data |
| `app/modules/identity/` | registration, login, refresh rotation with reuse detection, lockout, users, audit |
| `app/modules/projects/` | project register |
| `app/modules/structural/domain/beam.py` | inputs, forces, bar selection, checks, calculation sheet |
| `app/modules/structural/domain/beam_detailing.py` | bar schedule, quantities, drawing |
| `app/modules/structural/domain/registry.py` | element registry |
| `app/modules/structural/exports/` | PDF report, Excel schedule, DXF drawing |
| `app/modules/dashboard/` | summary and search queries |

## 6. Frontend implementation

| Path | Content |
|---|---|
| `src/api/` | fetch client with token refresh and one error type, response types, query hooks |
| `src/shell/` | ribbon, sidebar, document tabs, status bar, command palette, floating calculator, shortcuts |
| `src/components/PropertyGrid.tsx` | input grid generated from the element schema |
| `src/components/DrawingCanvas.tsx` | SVG renderer of the drawing model with pan and zoom |
| `src/components/CalcSheet.tsx`, `Schedule.tsx`, `Status.tsx` | calculation sheet, checks, bar schedule, quantities, verdicts |
| `src/pages/DesignWorkspacePage.tsx` | dockable workspace with live calculation |
| `src/pages/` | sign-in, dashboard, projects, project, structural catalogue, users |

## 7. UI screens

1. **Sign in / create organisation.**
2. **Dashboard**: four tiles, design activity over 14 days (chart with a table view), design status, recent designs, activity feed.
3. **Projects** and **project**: register with search and status filter; a project's designs with result, utilisation, review state and report download.
4. **Structural design**: catalogue of available members with scope limits, and what comes next.
5. **Design workspace**: summary strip (verdict, checks passed, highest utilisation, key results); dock panels for Properties, Section, Longitudinal section, Calculation, Checks, Bar schedule, Quantities; contextual ribbon tab with Save, Revert, Report PDF, BBS Excel, Drawing DXF, Approve, Reset layout.
6. **Users and roles**: people, role matrix, audit trail.

Shortcuts: Ctrl K search and commands; Alt 1 / 2 / 3 modules; Alt C calculator; Alt T theme; Alt B sidebar; Ctrl S save; Alt R report; Alt W close tab; ? help.

## 8. Engineering logic

Beam engine 1.0.0. Units: mm, kN, kN m, N/mm2.

| Step | Rule | Reference |
|---|---|---|
| Durability | grade not below the minimum for the exposure; cover not below nominal | Table 5, Table 16 |
| Effective span | simply supported: lesser of clear span + d and centre to centre of supports; cantilever: clear projection + d/2 | Cl. 22.2 |
| Loads | wu = 1.5 (DL + self-weight + LL); Mu = wu l2/8 or wu l2/2 | Table 18 |
| Shear section | at d from the face of a simple support; at the face for a cantilever | Cl. 22.6.2.1 |
| Torsion | Ve = Vu + 1.6 Tu/b; Mt = Tu (1 + D/b)/1.7; Me1 = Mu + Mt; Me2 = Mt - Mu when positive | Cl. 41.3, 41.4 |
| Flexure | xu,max from the strain condition; Mu,lim; singly or doubly reinforced steel | Cl. 38.1, Annex G |
| Steel limits | As >= 0.85 b d / fy; As <= 0.04 b D on either face | Cl. 26.5.1.1, 26.5.1.2 |
| Bar selection | least total steel, in up to two layers, meeting Annex G, the steel limits, bar spacing rules and an under-reinforced section as detailed | Cl. 26.3.2, 26.3.3, 38.1(f) |
| Resistance as detailed | neutral axis by equilibrium with compression steel stress from its strain; Mu <= Mu,R | Cl. 38.1 |
| Shear | tau_v = Vu/(b d); tau_c from Table 19 by interpolation; tau_v <= tau_c,max; Vus = Vu - tau_c b d; sv = 0.87 fy Asv d / Vus | Cl. 40, Tables 19, 20 |
| Stirrup limits | minimum shear steel; 0.75 d; 300 mm; with torsion x1, (x1 + y1)/4 and the Cl. 41.4.3 expressions; stirrup fy not above 415 | Cl. 26.5.1.5 to 26.5.1.7, 40.4, 41.4.3 |
| Deflection | l/d <= basic ratio x kt x kc (x 10/l above 10 m) | Cl. 23.2.1, Fig. 4, Fig. 5 |
| Detailing | development length; side face bars above 750 mm depth, or 450 mm with torsion; lateral stability | Cl. 26.2.1, 26.5.1.3, 23.3 |
| Bar schedule | lengths along the outside of the bar, less 2d per 90 degree and 3d per 135 degree bend, rounded up to 5 mm; Ld/3 into a simple support, Ld for cantilever tension bars | IS 2502, Cl. 26.2.3.3(a), 26.2.1 |
| Quantities | concrete over the bearings; formwork to soffit and sides over the clear span; steel from the schedule | stated in the result |

Interpretations and items to cross-check: [CODE_REGISTER.md](../CODE_REGISTER.md).

**Limits the engine states itself** (shown in the catalogue and on the sheet): rectangular sections; UDL or supplied forces; no curtailment and one stirrup spacing; span/depth rule only; no IS 13920 detailing.

## 9. Validation rules

| Input | Rule |
|---|---|
| Clear span | 300 to 30 000 mm |
| Support width | 100 to 2 000 mm |
| Width b | 150 to 2 000 mm |
| Depth D | 150 to 3 000 mm |
| Concrete | M20 to M55 in steps of 5 |
| Steel | Fe 250, 415, 500, 550 |
| Cover | blank (Table 16) or 15 to 100 mm |
| Aggregate | 10 to 40 mm |
| Loads | not negative; at least one of dead load, imposed load or self-weight |
| Load factor | 1.0 to 2.0 |
| Force input | moment above zero and shear not negative are required; torsion only in this mode |
| Unknown fields | rejected |

Limits live once, in the Pydantic input model. The client reads them from the JSON schema for immediate feedback; the server validates again. A value that is valid but fails the code is not an input error: it is a Not OK check.

**Stop states** (the engine cannot go on, and says what to change): effective span below twice the depth (deep beam, Cl. 29); too little effective depth; no bar arrangement of up to two layers within the steel limits.

Platform rules: password of at least 10 characters with a letter and a digit; unique email; job number unique within the organisation; end date not before start date; the last active owner cannot be removed; a design is approved by another person and only with every check OK.

## 10. Unit tests

| Suite | Tests | What it proves |
|---|---|---|
| `tests/unit/test_is456.py` | 46 | clause functions against SP 16 Table E and F, Table 19 against its closed form, bond multiples, capacity equals demand for the required steel |
| `tests/unit/test_beam.py` | 26 | worked example to hand-calculated values; doubly reinforced, cantilever, torsion, two layers, four legs; failed limits reported; stop states; invalid input; a sweep of about 500 input sets |
| `tests/unit/test_architecture.py` | 3 | layering rules |
| `tests/handcheck/check_beam.py` | 1 (360 values) | independent recomputation: stress-block bisection, SP 16 Table A, closed-form shear strength |
| `tests/api/` | 35 | authentication, roles, tenant isolation, projects, design life cycle, exports open as real PDF / XLSX / DXF, dashboard, migrations, client serving |
| `frontend/src/**/*.test.*` | 15 | calculator parser, symbol markup, property grid, calculation sheet, drawing renderer |
| `e2e/walkthrough.js` | 1 flow | the whole path in a browser, both themes, no console errors |

## 11. Integration steps

```bash
# backend
cd civillabpro/backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head                 # creates civillabpro.db (SQLite) unless CLP_DATABASE_URL is set
uvicorn app.main:app --reload        # http://127.0.0.1:8000/api/docs

# frontend, in a second terminal
cd civillabpro/frontend
npm ci
npm run dev                          # http://127.0.0.1:5173

# checks
cd civillabpro/backend && ruff check app tests alembic && pytest && python tests/handcheck/check_beam.py
cd civillabpro/frontend && npm run typecheck && npm test && npm run build
node civillabpro/e2e/walkthrough.js /tmp/shots     # with both servers running
```

Open the client, create an organisation, create a project, choose New RCC beam.

## 12. Deployment notes

* **Single process**: `npm run build`, then run the API with `CLP_STATIC_DIR=../frontend/dist`. Verified in a browser.
* **Containers**: `docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build` starts PostgreSQL with PostGIS and the application on port 8000. The compose file validates; the image itself was not built in the session that wrote it because no Docker daemon was available there. Build it once and run the walkthrough against it before relying on it.
* **Required in production**: `CLP_JWT_SECRET` (32 or more random characters) and a PostgreSQL `CLP_DATABASE_URL`. The server refuses to start without them. Terminate TLS in a proxy in front.
* **After the first organisation exists**, set `CLP_ALLOW_SELF_REGISTRATION=false`.
* Migrations run on container start.

## 13. Future enhancements

Next: column engine (STR-010), slabs, isolated footing, beam extensions, desktop shell. Full list with order and dependencies in [BACKLOG.md](../BACKLOG.md).
