# Release note 0.4.0 (in progress): beam extensions STR-014 to STR-017

The items that close phase 1, built one at a time on the existing beam engine. Each is a change to the beam's domain module, its detailing, its hand check and its tests; none needs a new endpoint, table, migration or screen. This note grows with each item.

| Item | State | Beam engine |
|---|---|---|
| STR-014 flanged sections (T and L) | done | 1.1.0 |
| STR-015 continuous beams by Tables 12 and 13 | next | |
| STR-016 curtailment and stirrup zones | planned | |
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
