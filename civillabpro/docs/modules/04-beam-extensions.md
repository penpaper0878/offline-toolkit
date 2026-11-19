# Release note 0.4.0 (in progress): beam extensions STR-014 to STR-017

The items that close phase 1, built one at a time. STR-014 extends the beam element; STR-015 adds a continuous beam element on the registry, reusing the beam's section routines. None needs a new endpoint, table, migration or screen. This note grows with each item.

| Item | State | Beam engine |
|---|---|---|
| STR-014 flanged sections (T and L) | done | 1.1.0 |
| STR-015 continuous beams by Tables 12 and 13 | done | continuous beam 1.0.0 (new element) |
| STR-016 curtailment and stirrup zones | next | |
| STR-017 anchorage at simple supports | planned | |

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
