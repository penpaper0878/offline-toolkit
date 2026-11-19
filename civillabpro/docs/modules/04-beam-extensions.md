# Release note 0.4.0: beam extensions STR-014 to STR-017

The items that close phase 1, built one at a time. STR-014 extends the beam element; STR-015 adds a continuous beam element on the registry, reusing the beam's section routines. None needs a new endpoint, table, migration or screen. This note grows with each item.

| Item | State | Beam engine |
|---|---|---|
| STR-014 flanged sections (T and L) | done | 1.1.0 |
| STR-015 continuous beams by Tables 12 and 13 | done | continuous beam 1.0.0 (new element) |
| STR-016 curtailment and stirrup zones | done | beam 1.2.0, continuous beam 1.1.0 |
| STR-017 anchorage at simple supports | done | beam 1.3.0, continuous beam 1.2.0 |

## STR-014: flanged sections (T and L)

### 1. Requirements

**Goal.** Let the slab act as the compression flange of a beam cast with it, as IS 456 allows, so that floor beams are designed for the section they really have.

**In scope.** T-beams (slab on both sides) and L-beams (slab on one side), within a continuous slab or isolated; effective flange width; flexure with the neutral axis in the flange or in the web, singly or doubly reinforced; shear on the web; deflection with the flanged-beam reduction; self-weight and quantities of the rib below the slab; a section drawing with the flange.

**Out of scope.** Design of the slab's own steel (the slab element does that); the transverse steel of Cl. 23.1.1(b) is a flag, not a schedule item.

### 2. Architecture

| Layer | Change |
|---|---|
| Engineering kernel (`is456.py`) | `effective_flange_width`, `flange_depth_yf`, `flanged_concrete`, `limiting_moment_flanged`, `design_flanged`, `moment_capacity_flanged`, `flanged_reduction_factor`; `moment_capacity` now shares one equilibrium solver (`_capacity`) with the flanged one |
| Beam domain | inputs `section`, `flange_thickness_mm`, `flange_width_mm`, `isolated_flange`, `l0_mm`; `flange_of`, `flexure_design`, `flexure_capacity`; flange steps in the sheet |
| Beam detailing | rib quantities; section drawn with the flange (broken off when wide) and chained depth dimensions; slab soffit in the elevation |
| Property grid and PDF | `show_if` accepts a list of values, so the flange rows show for T and L only |

No database, migration or endpoint change.

### 3. Engineering logic

| Step | Rule | Reference |
|---|---|---|
| l_0 | the effective span, or as entered (about 0.7 l for continuous beams) | Cl. 23.1.2 |
| Effective width | T: l_0/6 + b_w + 6 D_f; L: l_0/12 + b_w + 3 D_f; isolated T: l_0/(l_0/b + 4) + b_w; isolated L: half the first term; not more than the width available | Cl. 23.1.2(a) to (d) |
| Neutral axis in the flange | M_u <= 0.36 f_ck b_f D_f (d - 0.42 D_f): a rectangle b_f wide | Annex G-2.1, G-1.1(b) |
| Neutral axis in the web | M_u = 0.36 f_ck b_w x_u (d - 0.42 x_u) + 0.45 f_ck (b_f - b_w) y_f (d - y_f/2), y_f = min(0.15 x_u + 0.65 D_f, D_f); A_st balances the compression | Annex G-2.2, G-2.2.1, G-2.2.2 |
| Above the limit | compression steel for M_u - M_u,lim | Annex G-1.2 |
| Flange in tension | a cantilever's support: a rectangle b_w wide | Annex G-1 |
| Shear, steel limits | on the web width | Cl. 40.1, 26.5.1.1 |
| Deflection | percentages on b_f d; Fig. 6: 0.8 up to b_w/b_f = 0.3, linear to 1.0 | Cl. 23.2.1(e) |
| Lateral stability | b is the flange, the compression face | Cl. 23.3 |
| Self-weight | the rib below the slab | IS 875 (Part 1) |

Worked example (T-beam): web 300 x 550, slab 120 mm, beams at 3 m, clear span 6.0 m on 300 mm supports, M25 / Fe 500, dead load 30 kN/m (including the slab) and imposed 15 kN/m. Effective span 6300 mm; b_f = 6300/6 + 300 + 720 = 2070 mm; rib self-weight 3.23 kN/m; M_u 358.9 kN m; the neutral axis lies in the flange (x_u below 120 mm), A_st,req 1732 mm2: 9-T16 in two layers; k_f 0.8; 15 of 15 checks.

The same beam designed as a rectangle 300 x 550 (full-depth self-weight, no flange) needs A_st,req 2043 mm2, 18 percent more, and 182 kg of steel against 121 kg; its allowable span/depth ratio is 19.6 against 24.7, because the low steel percentage on b_f d more than offsets the 0.8 of Fig. 6.

### 4. Validation

| Input | Rule |
|---|---|
| Section | rectangular, T or L |
| Flange thickness | 50 to 500 mm, and at least 100 mm less than the overall depth |
| Flange width available | 150 to 20 000 mm, more than the web width |
| l_0 | blank, or more than 0 up to 60 m |

### 5. Tests

| Suite | Tests | Proves |
|---|---|---|
| `tests/unit/test_is456.py` | 6 new | the four width rules and the cap; y_f; continuity at x_u = D_f; design reduces to the rectangle when b_f = b_w and to G-1.1(b) with the axis in the flange; capacity round trip; Fig. 6 |
| `tests/unit/test_beam_flanged.py` | 14 | the T-beam worked example; axis in the web; y_f branch; L and isolated widths; entered l_0 and the cap; cantilever; flange inputs ignored for rectangles; validation; rib quantities; drawing; schema; a sweep of 256 flanged beams |
| `tests/handcheck/check_beam.py` | 8 new cases | effective width recomputed; x_u from the closed-form root of the G-2.2.1 quadratic, or false position where y_f < D_f (engine: bisection); Fig. 6 from its two lines; 501 values over 25 cases agree |
| `tests/api/test_structural.py` | 1 new | a T-beam through the generic endpoint; the list condition in the schema; an invalid flange width |
| `frontend/src/components/components.test.tsx` | 1 new | a row shown for any of several values |

## STR-015: continuous beams by Tables 12 and 13

### 1. Requirements and the decision behind the element

**Goal.** Design a beam continuous over three or more spans by the coefficients IS 456 provides for it (Cl. 22.5.1), and issue one calculation, one schedule and one drawing for the whole beam.

**Why a new element and not a "continuous" option of the beam.** Tables 12 and 13 describe a whole beam: an end span, the support next to it, interior spans and interior supports. Designed one span at a time, the top bars over a shared support would either be scheduled twice (once by each span) or stop at the face of the support without development. One design of the whole beam has one set of bars over each support, centred on it. The element reuses the beam's section routines (bar candidates, flexure of rectangles and flanges, the flange steps), so the engineering is shared.

**In scope.** 3 to 12 equal spans; rectangular, T or L section; dead and imposed load; effective spans of Cl. 22.2(b); moments and shears of Tables 12 and 13; four design sections; shear per span type; deflection per span type; extents of the top bars; hangers lapped with them; schedule, quantities and drawing for the whole beam.

**Out of scope.** Unequal spans beyond 15 percent, point loads, frames (use the beam with forces from an analysis); curtailment of the bottom bars and stirrup zones (STR-016); torsion.

### 2. Architecture

| Layer | Addition |
|---|---|
| Engineering kernel | `continuous.py`: three-moment equation (tridiagonal), the load arrangements of Cl. 22.4.1, points of inflection, moment envelope |
| Structural domain | `continuous_beam.py` (inputs, spans, coefficients, section selection, sheet), `continuous_beam_detailing.py` (layout of top bars and hangers, schedule, quantities, drawing); one registry entry |
| Beam modules | section helpers made public (`tension_candidates`, `other_candidates`, `practical_spacing`, `flange_steps`, `flanged_flexure_steps`); the cross-section drawing extracted to `beam_detailing.cross_section` so two sections can share a view |
| Report | the quantities heading is kept with its table |

### 3. Engineering logic

| Step | Rule | Reference |
|---|---|---|
| Spans | narrow supports (w_s <= l_c/12 and 600 mm): min(l_c + d, l_c + w_s); wide: end l_c + min(d/2, w_s/2), interior l_c | Cl. 22.2(b) |
| Moments | end span (w_d/12 + w_l/10) l^2; support B (w_d/10 + w_l/9), averaged over the two spans; interior span (w_d/16 + w_l/12) l^2; support C (w_d/12 + w_l/9) l^2 | Table 12 |
| Shears | A (0.40, 0.45); B outer (0.60, 0.60), inner (0.55, 0.60); C (0.50, 0.60), times the load on the span; at d from the face | Table 13, Cl. 22.6.2.1 |
| Mid-span | bottom steel, least steel; T or L flange with l_0 = 0.7 l | Annex G, G-2, Cl. 23.1.2 |
| Supports | top steel on the web; the lighter adjacent bottom bars as compression steel | Annex G-1 |
| Deflection | basic 26 with k_t, k_c, Fig. 6 | Cl. 23.2.1 |
| Top bar extents | furthest point of inflection over the arrangements of Cl. 22.4.1 (elastic analysis), then the greatest of d, 12 phi, l_c/16; at least L_d | Cl. 22.4.1, 26.2.3.4 |
| Layout | hangers lap with the support bars in compression; support bars that meet lap at mid-span in tension, with the hogging there checked | Cl. 26.2.5.1 |

Worked example (the defaults): four spans of 5.0 m clear on 300 mm supports, 300 x 500, M25 / Fe 500, DL 25 + LL 15 kN/m plus self-weight. w_d = 43.125, w_l = 22.5 kN/m; l = 5300 mm (narrow supports); M_1 164.15, M_B 191.36, M_2 128.38, M_C 171.17 kN m. Bars: end spans 5-T16, interior spans 4-T16, over B 6-T16, over C 10-T12 (6 + 4); stirrups T8 at 150 (end spans) and 175 (interior). Points of inflection 1282 mm (B into the end span), 1870 (B into span 2) and 1393 (C) from the faces; the top bars over B run 1736 mm into the end span; in the interior spans the bars from B and C meet and lap at mid-span (each 2888 mm from its face), where the alternate-span arrangement still gives 36.4 kN m hogging against 181.4 kN m for the lapped 10-T12. Span/depth 11.7 against 24.9 and 28.0. 37 of 37 checks; 388.6 kg of steel for the whole beam, 3.23 m3 of concrete.

My first version placed the inflection with the Table 12 support moments at both ends of a span carrying dead load alone. Both peaks need that span loaded, so the case cannot occur, and it ran the top bars through every interior span (473.6 kg). The elastic analysis of the real arrangements replaced it before anything was committed.

### 4. Validation and stops

| Input | Rule |
|---|---|
| Spans | 3 to 12 |
| Clear span | 1 to 20 m; support width 100 to 2000 mm |
| Section | as the beam (flange at least 100 mm thinner than D, wider than the web) |
| Loads | some load, or the self-weight |

Stops: effective span less than 2.5 D (a continuous deep beam, Cl. 29); no bars within Cl. 26.5.1 for a span; no top bars for a support with the bottom bars as compression steel.

### 5. Tests

| Suite | Tests | Proves |
|---|---|---|
| `tests/unit/test_continuous.py` | 6 | two spans (-wL^2/8, inflection at L/4); three spans (0.1, 0.05, 1/15 and 1/60 coefficients); the three-moment equation for unequal spans; the arrangements; hogging throughout an unloaded middle span; the envelope brackets every arrangement |
| `tests/unit/test_continuous_beam.py` | 18 | the worked example to Tables 12 and 13; three spans without C; Cl. 22.2(b); compression steel at a support and its continuation; Cl. 26.2.3.4 extents; the mid-span lap and its check; hanger laps; schedule counts for 3, 4 and 7 spans; T-beam with 0.7 l and supports on the web; drawing; validation; stops; references; a sweep of 108 beams |
| `tests/handcheck/check_continuous_beam.py` | 37 base results, 368 values over 12 cases, 2 stops | Tables 12 and 13 typed again; flexure by stress-block bisection and the G-2.2.1 quadratic; SP 16 Table A; tau_c closed form; points of inflection by Hardy Cross moment distribution and a scan with bisection (they agree with the engine's three-moment solution to 0.1 mm) |
| `tests/api/test_structural.py` | 1 new, 1 changed | the element in the registry, calculate, save, revise, approve and the three exports |

## STR-016: curtailment and stirrup zones

### 1. Requirements

**Goal.** Stop the bars that are no longer needed and space the stirrups by the shear diagram, as IS 456 allows, in both beam elements; until now every bar ran the full length at one stirrup spacing.

**In scope.** The simple beam in load mode (simply supported and cantilever) and the continuous beam: tension bars curtailed by Cl. 26.2.3.1 to 26.2.3.4 with the three conditions of Cl. 26.2.3.2; stirrups at the designed spacing near the supports and at the minimum-steel spacing where the shear allows; closer stirrups along stopped bars where condition (b) is used; schedule, drawing and report.

**Out of scope.** Forces entered by the user (no diagram: everything as before); torsion; staggering bars of one layer at different points (one cut-off per set).

### 2. Architecture

| Layer | Change |
|---|---|
| Analysis kernel | `continuous.shear_envelope` |
| Beam domain | `split_for_curtailment`, `stirrup_positions` (symmetric, cantilever or unsymmetric spans, with any number of closer zones), `cutoff_condition` (Cl. 26.2.3.2, shared), `curtail_and_zones` |
| Continuous beam domain | `continuous_curtailment.py`: scaled diagrams, zones, top and bottom cut-offs, stirrup positions per span type |
| Detailing | continuing and curtailed bars as separate schedule items; stirrup counts from their positions; the stopped bars and the zones in the elevations |

### 3. Engineering logic

| Step | Rule | Reference |
|---|---|---|
| Which bars stop | the second layer, or alternate bars; a third of the area and the corner bars continue | Cl. 26.2.3.3, 26.2.3.4 |
| Where | beyond the point where the others suffice by the greater of d and 12 phi; L_d from the face (top bars) or either side of the greatest moment (bottom bars); 50 mm steps | Cl. 26.2.3.1, 26.2.1 |
| Stopped in a tension zone | (a) V <= 2/3 V_R; (c) twice the steel needed and V <= 3/4 V_R; (b) closer stirrups over 3/4 d along the stopped bars, excess >= 0.4 b s/f_y, spacing <= d/(8 beta_b) | Cl. 26.2.3.2 |
| Worth it | not within d of a support; not where (b)'s stirrups weigh as much as the steel saved | practice |
| Stirrup zones | designed spacing to where the shear falls to the resistance at the minimum-steel spacing | Cl. 40.4, 26.5.1.5, 26.5.1.6 |
| Diagrams | simple beam: the parabola of the factored load; continuous beam: the elastic envelope scaled to Tables 12 and 13 | Cl. 22.4.1 |

Results on the worked examples: the simple beam stops its middle T16 800 mm from each face (32.8 kg, from 36.3); the four-span continuous beam stops half the top bars over B 800 mm and 850 mm out, four of the ten T12 over C 600 mm out and half the interior spans' bottom bars 750 mm from each face; its end span keeps all five bottom bars because the cut-off near the end support would fall within d (300 mm against 454). 322.3 kg, from 388.6.

Two findings on the way. Condition (a) alone rejected most cut-offs in the test cases (the shear at a cut-off near a quarter of the span is often more than two thirds of the resistance); condition (b) is what designers use there; with it, and with the two rules on when curtailment is not worth it, 18 of the 22 hand-check beams in load mode are curtailed. And pattern loading moves the interior spans' greatest moment off mid-span and flattens it, so L_d is now measured from both edges of the region within 0.5 percent of the peak; the hand check found the case where a single peak point left 8 mm of margin.

### 4. Tests

| Suite | Tests | Proves |
|---|---|---|
| `tests/unit/test_beam_curtailment.py` | 8 | the split rule; stirrup positions (one spacing, zones, bands, cantilever); the worked example; condition (b) and its band; the reasons when nothing is curtailed; cantilever; zones against the shear; a sweep checking every cut-off against the diagram |
| `tests/unit/test_continuous_beam.py` | 2 new, 2 changed | the continuous worked example's cut-offs, zones and saving; both faces curtailed under heavy imposed load; schedule counts across continuing and curtailed items |
| `tests/unit/test_continuous.py` | 1 new | the shear envelope (3wL/8 and 5wL/8 for two spans) |
| `tests/handcheck/check_beam.py` | cut-offs and zones of every case | the resistance of the continuing bars (stress block, SP 16 Table A), the cut-off by bisection on M(x), condition (b) recomputed, every zone end within the shear resistance |
| `tests/handcheck/check_continuous_beam.py` | the same for the continuous beam | Hardy Cross envelopes scaled by the same rule; every cut-off, moved back by max(d, 12 phi), within the remaining bars; L_d; zone ends |

## STR-017: anchorage at simple supports and points of inflection

### 1. Requirements

**Goal.** Limit the diameter of the positive bars so that they can develop their stress where the moment falls to zero, as Cl. 26.2.3.3(c) requires: at simple supports and, in continuous beams, at the points of inflection.

### 2. Engineering logic

| Step | Rule | Reference |
|---|---|---|
| M_1 | all the bars that reach the point at f_d, neutral axis from equilibrium (no x_u,max limit), a compression flange where there is one | Cl. 26.2.3.3(c) |
| V | at the face of a simple support; at a point of inflection, from the scaled shear envelope | |
| L_0 | simple support: w_s/2 - cover, plus 8 phi with a 90 degree bend (corrected in 0.5.0: the straight part stops r + phi short, where the bend starts; see note 05); point of inflection: the greater of d and 12 phi | Cl. 26.2.3.3(c), 26.2.2.1(b) |
| Check | L_d <= 1.3 M_1/V + L_0 at simple supports (confined by the reaction); L_d <= M_1/V + L_0 at points of inflection | Cl. 26.2.3.3(c) |
| Enforcement | simple beam: bar selection rejects diameters that fail even with a bend, the schedule bends bars that need it, curtailment is withdrawn where the continuing bars alone would fail; continuous beam: curtailment withdrawn likewise, a bend added at the end supports, Not OK with the remedy otherwise | |

Worked examples: the simple beam's 2-T16 that reach the supports need L_d = 777 mm against 1.3 M_1/V + L_0 = 1450 mm; a short, heavily loaded 250 x 600 beam on 230 mm supports keeps 7-T20 but needs them bent at the supports (971 against 1206 mm, with the bend's 8 phi); the four-span continuous beam passes at the end supports (777 against 1632 mm) and at the points of inflection (777 against 1577 and 1027 mm).

One correction made while building it: the first M_1 capped the neutral axis at x_u,max, as the moment checks do. For a heavily reinforced section that gives the concrete's capacity, not the "moment of resistance assuming all reinforcement stressed to f_d" the clause defines, and it rejected beams that pass. M_1 now follows the clause.

### 3. Tests

| Suite | Tests | Proves |
|---|---|---|
| `tests/unit/test_beam_curtailment.py` | 4 new | the check against a hand value; M_1 without the x_u,max limit; the bend added where straight bars fail; the stop message when nothing can be anchored |
| `tests/unit/test_continuous_beam.py` | 1 new, 1 changed | end supports with 1.3 and points of inflection without; curtailment withdrawn where the continuing bars could not be anchored |
| `tests/handcheck/check_beam.py` | every case | M_1 by equilibrium (bisection with a flange), L_0 from the schedule's bend, the check recomputed; 672 values over 25 cases agree |
| `tests/handcheck/check_continuous_beam.py` | every case | the same at the end supports and the points of inflection, from the Hardy Cross envelopes; 675 values over 12 cases agree |

## Release 0.4.0: phase 1 closed

With STR-017, phase 1's exit criterion and its last items are done: beams (rectangular, T, L; simple, cantilever, continuous), columns, slabs and isolated footings are designed, hand-checked and issued from one workspace. Still open from phase 1: STR-009, the comparison of the clauses with the printed code, which needs the code text.

Integration: no database change; deploy the new image or restart the single process. Saved designs keep the result they were made with; a revision recalculates with the new engines (beam 1.3.0, continuous beam 1.2.0).
