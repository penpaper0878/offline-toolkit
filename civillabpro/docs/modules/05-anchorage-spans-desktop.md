# Release note 0.5.0: anchorage completed, unequal spans, desktop shell

The items left open at 0.4.0, built one at a time: STR-038 and STR-037 finish the anchorage of beam bars, STR-036 extends the continuous beam to unequal spans and point loads, and PLAT-010 packages the platform as a desktop application. None needs a new endpoint, table, migration or screen. This note grows with each item.

| Item | State | Engine |
|---|---|---|
| STR-038 anchorage in the continuous beam's bar selection | done | continuous beam 1.3.0 |
| STR-037 U-hooks; L_0 measured to the start of the bend | done | beam 1.4.0, continuous beam 1.4.0, footing 1.1.0 |
| STR-039 curtailment kept off the compression steel of the supports (defect) | done | continuous beam 1.5.0 |
| STR-036 continuous beams of unequal spans and point loads | done | continuous beam 1.5.0 (elastic method) |
| PLAT-021 sessions committed before the response (defect) | done | platform |
| PLAT-010 desktop app | done | platform; desktop 0.5.0 |

## STR-038: anchorage in the continuous beam's bar selection

### 1. Requirements

**Goal.** At 0.4.0 the continuous beam checked Cl. 26.2.3.3(c) after choosing its bars and reported Not OK where they failed. The simple beam already passed over such bars while choosing. The continuous beam now does the same, at its end supports and at the points of inflection.

### 2. Engineering logic

| Step | Rule | Reference |
|---|---|---|
| Shears for selection | Table 13 at the end support; the scaled elastic envelope at the points of inflection, computed for the effective depth of each trial (cached by d) | Cl. 26.2.3.3(c), 22.5 |
| Margin | 2 percent on both shears, because the final check uses the spans of the bars actually chosen | |
| Rejection | end span bottom bars that fail at the end support (a bend or hook allowed) or at the point of inflection next to B; interior span bottom bars that fail at either point of inflection | Cl. 26.2.3.3(c) |
| Stop | when anchorage alone rejects every arrangement, the stop message says so and gives the remedies | |

Worked example: four 3 m spans on 150 mm supports, 450 deep, T32 fixed. 3-T32 carry the end span's moment but cannot develop at the end supports; 4-T32 raise M_1 enough (L_d = 1554 mm against 1.3 M_1/V + L_0 = 2181 mm, with a bend). At 4.5 m spans no number of T32 can be anchored and the design stops with that reason.

### 3. Tests

| Suite | Tests | Proves |
|---|---|---|
| `tests/unit/test_continuous_beam.py` | 1 new | the fourth bar chosen for anchorage; the stop message |
| `tests/handcheck/check_continuous_beam.py` | 1 case, 1 stop | the case and the stop by the independent route |

## STR-037: U-hooks, and L_0 to the start of the bend

### 1. Requirements

**Goal.** Where a 90 degree bend's 8 phi are not enough for Cl. 26.2.3.3(c), give the bars a standard U-hook (16 phi, Cl. 26.2.2.1(b)) instead of rejecting them. Show the hook in the bar schedule and in the drawing.

**Correction found while building it.** STR-017 took L_0 with a bend as w_s/2 - cover + 8 phi. The bend's anchorage value replaces the bar inside the bend, so the straight part must stop where the bend starts. That point is r + phi inside the bar's outer face, with r the IS 2502 internal radius. The old figure counted that length twice: 5 phi too much for deformed bars and 3 phi for mild steel, on the unsafe side. The isolated footing had the same error in its end bends. Both are corrected, and both corrections are recorded in the code register (interpretations 37 and 73).

### 2. Engineering logic

| Step | Rule | Reference |
|---|---|---|
| Radius | r = 2 phi for mild steel, 4 phi for deformed bars (`rebar.bend_radius`) | IS 2502 |
| L_0 at a simple support | straight: w_s/2 - cover; bend: w_s/2 - cover - (r + phi) + 8 phi; U-hook: w_s/2 - cover - (r + phi) + 16 phi | Cl. 26.2.3.3(c), 26.2.2.1(b) |
| End detail | the least that passes, in the order straight, bend, hook; bars that Cl. 26.2.3.3(a) already bends start from the bend | |
| Schedule | simple beam "U-hook both ends", A + 2 hook; continuous beam's end spans "U-hook at the end support", A + hook; hook = pi (r + phi/2) + 4 phi - (r + phi), rounded up to 5 mm (13 phi deformed, 9 phi mild) | IS 2502 |
| Drawing | the half circle on the bar's centre line and the 4 phi tail at each hooked end | |
| Footing | L_d <= a - c - (r + phi) + 8 phi with end bends; the plan grows until this holds | Cl. 34.2.4.3, 26.2.2.1(b) |

Worked examples:

* The simple beam's worked example (2-T16 on 230 mm supports, bent for Cl. 26.2.3.3(a)) now gives 1.3 M_1/V + L_0 = 1370 mm against L_d = 777 mm. At 0.4.0 it gave 1450 mm.
* The short, heavily loaded 250 x 600 beam keeps 7-T20 bent at the supports: 971 against 1106 mm, where 0.4.0 gave 1206.
* A 230 x 450 beam of 2 m span on 150 mm supports with T20 in M25 needs U-hooks. With the hook it gives 971 against 1127 mm; a bend would give 967 mm and fail. In M30 the bend suffices.
* The four-span continuous beam on 150 mm supports, 2.5 m spans, with 3-T20 hooked at the end supports, gives 971 against 1090 mm.

### 3. Tests

| Suite | Tests | Proves |
|---|---|---|
| `tests/unit/test_beam_curtailment.py` | 3 new, 1 changed | L_0 for each end detail and both steels; the hook allowance; the hook chosen where the bend fails (sheet step, schedule, drawing); the corrected worked example |
| `tests/unit/test_continuous_beam.py` | 1 new | the hook at the end supports: sheet, schedule, drawing |
| `tests/unit/test_footing.py` | 2 changed | the corrected bend in the bent-ends and enlarged-plan cases |
| `tests/handcheck/check_beam.py` | 2 cases, 1 stop | L_0 from the schedule's shape with the IS 2502 radius, and the hook allowance; 716 values over 27 cases agree |
| `tests/handcheck/check_continuous_beam.py` | 1 case | the same at the end supports; 767 values over 14 cases agree |
| `tests/handcheck/check_footing.py` | every bent case | the corrected bend, and that 50 mm less plan would not develop T10 |

## STR-039: curtailment kept off the compression steel of the supports (defect fixed)

**Found** while planning STR-036. Each support section of the continuous beam counts the bottom bars that run into it as compression steel, and is doubly reinforced where it needs them. Bottom-bar curtailment (STR-016) then stopped some of those bars short of the support without checking the support again. In 66 of 193 sampled designs the bars that still reached a support were fewer than its A_sc,req, so its moment of resistance was overstated. The hand check's T-beam floor case was one of them; the hand check did not test it.

**Fix.** Before stopping any bottom bars of a span, the engine recomputes each neighbouring support with only the continuing bars as compression steel. If that support would fall short of A_sc,req, become over-reinforced, or resist less than its moment, the span's bars are not curtailed, and the sheet says why. Code register interpretation 70a; continuous beam 1.5.0.

**Tests.** `test_curtailment_keeps_the_compression_steel_of_the_supports`. The hand check now recomputes every support with the bars that actually reach it from each side, by its own stress-block bisection. With the fix reverted it reports the T-beam floor case and the new shallow-beam case. With the fix, 897 values over 15 cases agree.

## STR-036: continuous beams of unequal spans and point loads, by elastic analysis

### 1. Requirements

**Goal.** Design a continuous beam whose spans differ, or that carries point loads, which the coefficients of Tables 12 and 13 cannot do (Cl. 22.5.1). Use an elastic analysis of the arrangements of Cl. 22.4.1, with the redistribution of moments that Cl. 22.7 allows by Cl. 37.1.1. Design, detail, curtail and draw every span and support, and check everything independently.

**Inputs.** The element's new `analysis` field picks the method. The elastic method takes:

* a table of spans (two to twelve): clear span, dead and imposed uniform load;
* a table of point loads: span, distance from the left face, dead and imposed load;
* the redistribution, up to 30 percent.

Section, materials, support width, bar sizes and stirrups are shared with the coefficient method.

### 2. Architecture

No new endpoint, table or screen. The registry pattern gained two general abilities:

* **Table fields.** A list of records in an input model reaches the client with its rows' schema inlined (`ElementSpec.input_schema()`). The property grid edits it as a table: cells validated against the schema, rows added by copying the last one, rows removed down to the minimum. The PDF report prints a line per row. Any element can now take tabular input.
* **Drawings of many views.** Where a drawing has more views than the two drawing panels, each panel offers a picker, and its tab title follows the view it shows.

| Layer | File | What |
|---|---|---|
| Kernel | `engineering/continuous.py` | `SpanLoad`, three-moment equation under any loads, free diagrams, `arrangements`, `redistribute` (one fraction or one per support), `envelopes` with stations either side of every point load |
| Domain | `continuous_elastic.py` | effective spans, the `Beam` design envelope, per-span and per-support bar selection with Cl. 37.1.1(d), the stepping down of redistribution, shear, deflection, extents, laps, the curtailment and stirrup plan, anchorage, charts |
| Domain | `continuous_elastic_detailing.py` | per-span layout of support bars and hangers, the merged schedule, quantities, an elevation per span and two cross-sections |
| Domain | `continuous_beam.py` | the `analysis`, `span_table`, `point_loads` and `redistribution_pct` inputs; dispatch to the elastic method |
| Client | `PropertyGrid.tsx`, `DesignWorkspacePage.tsx`, `ChartView.tsx` | table fields, the view picker, charts below zero |
| Export | `pdf_report.py` | list inputs, a line per row |

### 3. Engineering logic

| Step | Rule | Reference |
|---|---|---|
| Effective spans | Cl. 22.2(b) per span, with the greatest effective depth the bars allow (the longest spans) | Cl. 22.2 |
| Analysis | knife edges, end supports free; dead loads everywhere, each span's imposed loads by the arrangements (all, alternate, adjacent pairs) | Cl. 22.4.1 |
| Redistribution | each arrangement's hogging held to (1 - r) of the support's greatest elastic hogging; span moments by statics; r stepped down by 5 percent at a support that cannot meet (d) | Cl. 22.7, 37.1.1(a), (c) |
| Design envelope | max(redistributed, 0.7 elastic) everywhere | Cl. 37.1.1(b) |
| Sections | each span for its greatest sagging, each support for its hogging at the centre line with the lighter adjacent bottom bars as compression steel; x_u/d + dM/100 <= 0.6 where the resistance is below the elastic moment | Annex G, Cl. 37.1.1(d) |
| Shear | V at d from the face (at the face beside a point load within d); stirrup bands wherever the shear needs closer than the minimum-steel spacing | Cl. 22.6.2.1, 40.4, 26.5.1.5, 26.5.1.6 |
| Detailing | extents beyond the points of inflection, curtailment with Cl. 26.2.3.2, anchorage of Cl. 26.2.3.3(c) at the end supports (straight, bend or U-hook) and the points of inflection; top bars that meet within a span lap in tension, checked by developed resistance | Cl. 26.2.1, 26.2.3, 26.2.5.1 |

Worked example (the defaults of the span table): spans of 5.0, 6.5 and 4.5 m, a 40 + 30 kN point load 3.0 m into span 2, 15 percent redistribution, 300 x 500, M25 / Fe 500. Results:

* Supports 2 and 3 are designed for 270.9 and 252.2 kN m, against elastic greatest moments of 318.7 and 296.8 kN m.
* Span 2's moment rises from 280.0 to 292.5 kN m, keeping equilibrium.
* Bars: span 1 4-T16, span 2 4-T25 (doubly reinforced), span 3 5-T12; 9-T16 (6+3) over support 2 and 5-T20 over support 3.
* All 76 checks are OK; 351 kg of steel.

With 30 percent entered, support 2 takes 30 percent and support 3 takes 25, because at 30 percent no arrangement of top bars there keeps x_u/d within 0.3.

### 4. Validation

`tests/handcheck/check_continuous_elastic.py` works by a different route throughout:

* the arrangements by Hardy Cross moment distribution, with the fixed-end moments of uniform and point loads and the end spans released;
* the diagrams by statics from the left reaction;
* the steel by the stress block, with SP 16 Table A for compression steel;
* tau_c by the SP 16 closed form.

It checks:

* the effective spans, the elastic and design moments at every support and span, and the end shears;
* the steel against each moment, and Cl. 37.1.1(d);
* every stirrup gap against the shear there, and the extents of the top bars;
* every cut-off, moved back by d or 12 phi, against the bars that remain;
* the resistance diagram of the bars as detailed against the design envelope at 200 stations a span, which also covers 0.7 of the elastic envelope;
* the anchorage at the end supports and the points of inflection, and the deflection allowance.

936 values over 14 cases (two to five spans, T and L beams, wide supports, a short span between long ones, a point load beside a support, 0 to 30 percent redistribution, T32 bars governed by anchorage) and 2 stop states agree.

Four sabotaged engines each fail it:

* a point-load term taken from the wrong end;
* no cap on the support moments;
* anchorage at the points of inflection switched off;
* stirrups 10 percent wider.

A 0.6 floor in place of 0.7 changes no result in these cases (it cannot move a point of inflection), which is why the resistance-diagram check guards Cl. 37.1.1(b) directly.

### 5. Tests

| Suite | Tests | Proves |
|---|---|---|
| `tests/unit/test_continuous_elastic.py` | 14 | kernel against closed forms (3PL/16, a point load in one span, uniform loads as the coefficient routine); free diagrams; the redistribution cap; stations at point loads; the worked example; Cl. 37.1.1(d); no redistribution; two spans with a mirrored schedule; meeting top bars; shear at the face beside a point load; stops and input errors; the coefficient method unchanged; stepping redistribution down; a random sweep |
| `tests/api/test_structural.py` | 1 new | inlined table schemas, calculation, field errors inside a table (`span_table.1.clear_span_mm`), save, revise, PDF, Excel and DXF |
| `frontend/src/components/components.test.tsx` | 3 new | a table field validated row by row, edited, rows added and removed; a chart with negative values |
| `e2e/walkthrough.js` | 1 new leg | switch to the elastic method, edit the span table, add a span, pick a view, charts, save and export, 0 console errors |

## PLAT-021: writes committed before the response (defect fixed)

**Found** by the desktop smoke test. It created a design and at once fetched its report, and got "Design not found". The session dependency committed after `yield`, and with FastAPI's default dependency scope that code runs after the response has been sent. So every write in the API was committed after the client had its success response:

* a client reading straight away could miss its own write, as the UI could when it opens a design it has just saved;
* a commit that failed would have followed a success response.

TestClient waits for the whole exchange, so the tests could not see it.

**Fix.** Every route takes its session as `Depends(get_db, scope="function")`: the session ends with the path operation, before the response. `tests/api/test_sessions.py` walks every route, included routers too, and fails on any session with another scope (it fails without the fix).

## PLAT-010: the desktop app

### 1. Requirements

**Goal.** The whole platform on one computer, without a network, for Windows and Linux: one install, the data in the user's own folder, the same engines and documents as the web.

### 2. Architecture

| Part | File | What |
|---|---|---|
| Server entry | `backend/app/serve.py` | brings the database to the head of the one Alembic history, then serves API and client with uvicorn; `--parent-pid` stops it when the shell is gone |
| Shell | `desktop/main.js` | single instance; a starting page; the server started and waited for; the window locked to `127.0.0.1:<port>` (other links open in the browser); File, Edit, View and Help menus; `--smoke-test` |
| Launcher | `desktop/launcher.js` | paths (packaged or checkout), the server's environment (production, SQLite in the data folder, the bundled client, a signing key made once and kept private), a port kept from start to start, start with a log, health wait that fails early, stop (taskkill on Windows) |
| Bundle | `desktop/scripts/build_server.py` | PyInstaller, one folder: the backend with its migrations, fonts and data; PostgreSQL's driver and uvicorn's optional extras left out (about 160 MB) |
| Installers | `desktop/package.json` (`build`) | electron-builder: AppImage for Linux, NSIS for Windows (per-user, installation folder selectable, data kept on uninstall) |
| CI | `.github/workflows/civillabpro-desktop.yml` | client, bundle, launcher tests, package, smoke test of the packaged app, installers kept as artifacts, on Ubuntu and Windows |

Decisions:

* **The port is kept from start to start.** The window's origin carries the sign-in and the saved panel layouts in the browser storage; a new random port each start would lose them.
* **The server watches the shell.** If the shell is killed, its server would otherwise hold the port and the database.
* **The four-eyes rule stays on.** A single user adds a reviewer under Users and roles to approve designs.

### 3. Validation

* `tests/api/test_serve.py` (3):
  * a fresh SQLite file is migrated, and a second start changes nothing;
  * the server process migrates and serves both the API and the client routes;
  * it shuts down cleanly when the process it watches ends.
* `desktop/test/launcher.test.js` (8):
  * paths on both platforms, SQLite URLs, and the environment (it never takes the developer's own database);
  * the private key, and the kept port (moved on only when the port is taken);
  * the splash page, and the arguments passed to the server;
  * a real start on a fresh data folder;
  * a server that dies while starting is reported at once.
* The smoke test, run from a checkout, on the unpacked package and on the AppImage, all passing here. It signs up, makes a project, and designs the beam, both continuous beams, the column, the slab and the footing. It then fetches each design's report, schedule and drawing through the window, and recognises them as PDF, XLSX and DXF.
* With the packaged app running, the shell was killed with SIGKILL; its server logged a clean shutdown within three seconds.
* The Windows installer is built and smoke-tested by the CI workflow; it was not run here.
