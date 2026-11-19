# Release note 0.5.0: anchorage completed, unequal spans, desktop shell

The items left open at 0.4.0, built one at a time: STR-038 and STR-037 finish the anchorage of beam bars, STR-036 extends the continuous beam to unequal spans and point loads, and PLAT-010 packages the platform as a desktop application. None needs a new endpoint, table, migration or screen. This note grows with each item.

| Item | State | Engine |
|---|---|---|
| STR-038 anchorage in the continuous beam's bar selection | done | continuous beam 1.3.0 |
| STR-037 U-hooks; L_0 measured to the start of the bend | done | beam 1.4.0, continuous beam 1.4.0, footing 1.1.0 |
| STR-039 curtailment kept off the compression steel of the supports (defect) | done | continuous beam 1.5.0 |
| STR-036 continuous beams of unequal spans and point loads | in progress | |
| PLAT-010 desktop shell | not started | |

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
