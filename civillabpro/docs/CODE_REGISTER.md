# Code register

The standards the engines implement: their status, the clauses taken, every place where the text was interpreted, and what still has to be cross-checked against a printed copy. An engine is not released until its codes are entered here.

Status last checked: 16 November 2026. Column clauses added 17 November 2026; slab and footing clauses 18 November 2026; estimation rules 21 November 2026.

## IS 456:2000, Plain and reinforced concrete: code of practice (fourth revision)

| | |
|---|---|
| Publisher | Bureau of Indian Standards, CED 2 |
| Status | Current. Reaffirmed 2021. |
| Amendments | Nos. 1 to 6. Amendment No. 6 is dated April 2024 (published August 2024); the excerpt consulted changes Cl. 5.1 (cement references, including composite cement to IS 16415) and deletes Cl. 17.5 in favour of a load test under Cl. 17.6. None of the clauses listed below is touched by that excerpt. |
| Revision | A fifth revision ("Structural concrete") has been in draft; secondary sources report it was circulated for comment in 2025 and was still being processed in early 2026. IS 456:2000 remains the enforceable standard. Review this entry when the revision is published. |
| Used by | beam engine 1.3.0, continuous beam engine 1.3.0, column engine 1.0.0, slab engine 1.0.0, footing engine 1.0.0 |

### Clauses taken

| Clause | Subject | Where |
|---|---|---|
| Table 2, Cl. 6.1 | concrete grades; design rules hold to M55 | `is456.CONCRETE_GRADES` |
| Cl. 5.6.3 | Es = 200 000 N/mm2 | `is456.ES` |
| Table 5 | minimum grade for exposure | `min_grade` |
| Table 16, Cl. 26.4.1 | nominal cover; not less than the bar diameter | `nominal_cover`, beam check `cover_bar` |
| Table 18 | load factor 1.5 on DL + LL | beam input default |
| Cl. 22.2(a), (c) | effective span of simply supported beams and cantilevers | `beam.compute_forces` |
| Cl. 22.6.2.1 | critical section for shear at d from the face of the support | `beam.compute_forces` |
| Cl. 23.2.1, Fig. 4, Fig. 5 | span to effective depth ratios and modification factors | `tension_modification_factor`, `compression_modification_factor` |
| Cl. 23.3 | lateral stability limits | beam check `lateral` |
| Cl. 26.2.1, 26.2.1.1 | development length, design bond stress | `development_length`, `bond_stress` |
| Cl. 26.2.3.3(a) | one third of Ld into a simple support | bar schedule |
| Cl. 26.3.2 | minimum clear distance between bars | `min_clear_bar_spacing_*` |
| Cl. 26.3.3, Table 15 | maximum clear distance between tension bars | `max_clear_bar_spacing` |
| Cl. 26.5.1.1 | minimum and maximum tension steel | `min_tension_steel`, `max_steel` |
| Cl. 26.5.1.3, 26.5.1.7(b) | side face reinforcement | `beam_detailing.side_face_bars` |
| Cl. 26.5.1.5, 26.5.1.6, 26.5.1.7(a) | stirrup spacing limits, minimum shear steel | beam shear section |
| Cl. 29 | deep beams (definition only: the engine stops) | beam stop state |
| Cl. 38.1, Fig. 21, Fig. 23 | assumptions for flexure, stress block, steel stress-strain curves | `xu_max_ratio`, `steel_design_stress`, `moment_capacity` |
| Cl. 40.1 to 40.4, Table 19, Table 20 | shear | `tau_c`, `tau_c_max`, `stirrup_spacing_for_shear` |
| Cl. 41.3, 41.4 | torsion: equivalent shear and moment, transverse steel | `beam.compute_forces`, beam shear section |
| Annex G-1.1, G-1.2 | moments of resistance of rectangular sections | `limiting_moment`, `design_rectangular` |

### Interpretations

1. **Neutral-axis limit, Cl. 38.1(f).** The engine uses the strain condition itself, xu,max/d = 0.0035 / (0.0055 + 0.87 fy/Es), unrounded (0.531, 0.479, 0.456 for Fe 250, 415, 500). The note to the clause prints 0.53, 0.48, 0.46. The unrounded value holds for every grade, reproduces the limiting-moment factors of SP 16 Table E (0.149, 0.138, 0.133) and is lower than the rounded value for Fe 415 and Fe 500.
2. **Singly reinforced steel, Annex G-1.1(b).** Solved in the form printed in SP 16, with 4.6 for 4/0.87. The provided bars are then checked independently against the stress block of Cl. 38.1 (lever arm d - 0.42 xu). The code's two expressions differ by up to 0.4 % because G-1.1(b) rounds the lever-arm factor 1.015 to 1; the bars are selected to satisfy both.
3. **Compression steel, Annex G-1.2.** The concrete displaced by the compression bars is deducted (fsc - 0.446 fck), following SP 16 Cl. 2.3.2. The code's expression omits the deduction; deducting is on the safe side.
4. **Steel curve for HYSD bars.** Fig. 23A is generated from 0.87 fy at the stress levels 0.80 to 1.0 with inelastic strains 0, 0.0001, 0.0003, 0.0007, 0.0010, 0.0020, interpolated linearly. Used for Fe 415, Fe 500 and Fe 550.
5. **Table 19 between rows and columns.** Linear interpolation in pt; grades above M40 take the M40 column; grades between columns take the lower column.
6. **Table 15 for Fe 550.** The table lists Fe 250, 415 and 500 (300, 180, 150 mm), which equal 75 000 / fy. That relation is used for Fe 550 (136 mm).
7. **Fig. 4 and Fig. 5.** Taken as the expressions in SP 24: kt = 1 / (0.225 + 0.00322 fs + 0.625 log10 pt) not above 2.0; kc = 1 + pc / (3 + pc) not above 1.5. Hanger bars are not counted as compression steel.
8. **Shear in cantilevers.** The face shear is used without the reduction of Cl. 22.6.2.1, because the support may be indirect.
9. **Torsion stirrups.** Only the outer closed hoop (two legs) is counted in Cl. 41.4.3; x1 and y1 are taken to the stirrup centre line.
10. **Table 16 notes.** The reductions in cover allowed by the notes to the table are not taken.
11. **Fe 550.** Designed with the same rules as Fe 500 (IS 1786 grades; Cl. 40.4 still limits stirrup strength to 415 N/mm2).

### To cross-check against a printed copy of the code with all six amendments

The values below were transcribed from the 2000 text as commonly published. Each is guarded by a test, but a printed, amended copy is the authority.

* Table 19, all 78 values (test: each within 0.011 N/mm2 of the SP 16 closed form).
* Table 20; Table 16; Table 5; Table 15.
* Cl. 26.2.1.1 bond stresses for M20 to M40 (test: the familiar multiples 47d, 40d, 57d, 45d).
* Whether Amendments 1 to 5 alter any clause in the table above. Their text was not read when this entry was written; Table 16 and Table 5 (durability) are the first to confirm.
* Cl. 23.3 limits (60 b or 250 b^2/d; 25 b or 100 b^2/d).

### Beam engine 1.1.0: flanged sections (T and L)

The code text was not read (as for the column); the effective-width formulas, Annex G-2 and the 60 percent rule of Cl. 23.1.1 were corroborated by secondary sources.

| Clause | Subject | Where |
|---|---|---|
| Cl. 23.1.1(b) | transverse reinforcement over the beam when the slab spans parallel to it | flag |
| Cl. 23.1.2(a) to (d) | effective width of T, L, isolated T and isolated L flanges, not more than the width available | `is456.effective_flange_width` |
| Annex G-2.1 | neutral axis in the flange: a rectangle b_f wide | `is456.design_flanged` |
| Annex G-2.2, G-2.2.1, G-2.2.2 | neutral axis in the web: web rectangle plus outstands at 0.45 f_ck over y_f; x_u for x_u,max below the limit | `is456.flanged_concrete`, `design_flanged`, `moment_capacity_flanged` |
| Cl. 23.2.1(e), Fig. 6 | span/depth reduction for flanged beams; percentages on b_f d | `is456.flanged_reduction_factor`, beam deflection section |
| Cl. 40.1 | shear on the web width | beam shear section |
| Cl. 26.5.1.1 | minimum and maximum steel on the web width | beam flexure section |
| Cl. 23.3 | lateral stability with b the breadth of the compression face (the flange) | beam check `lateral` |

### Beam engine: flanged interpretations

42. **y_f in the web range.** y_f = min(0.15 x_u + 0.65 D_f, D_f) is used for every neutral axis below the flange. It equals D_f exactly when D_f <= 3/7 x_u, the condition the code states as D_f/d <= 0.2 at x_u,max. With x_u below x_u,max (G-2.2 lets x_u replace x_u,max) the literal G-2.2.1 would keep D_f even where the flange reaches below the uniform part of the stress block; using y_f there is on the safe side and keeps the compression continuous at x_u = D_f (0.45 x 0.8 = 0.36). Same reading as Pillai and Menon.
43. **Neutral axis in the flange** when M_u <= 0.36 f_ck b_f D_f (d - 0.42 D_f), or when D_f >= x_u,max; then G-1.1(b) with b = b_f.
44. **Compression steel in a flanged section** carries M_u - M_u,lim with M_u,lim from G-2.2 at x_u,max, as in G-1.2 (concrete displaced deducted, interpretation 3).
45. **l_0** is the effective span unless entered; for continuous beams the user enters it (about 0.7 l, Cl. 23.1.2 note).
46. **Flange in tension** (a cantilever's support): the web is designed as a rectangle; Fig. 6 still reduces the span/depth ratio, with p_t on b_w d (on the safe side).
47. **Self-weight** of a flanged beam is the rib below the slab, b_w (D - D_f); the slab is part of the dead load entered. Quantities measure the rib, and an L-beam's outer face is formed to the full depth.
48. **Maximum steel** 0.04 b_w D (Cl. 26.5.1.1(b) printed as 0.04 b D).

### Beam engine: flanged, to cross-check against a printed copy

* Fig. 6: the curve's end points (0.8 up to b_w/b_f = 0.3, linear to 1.0). One handbook tabulates 0.82 at 0.3 and 0.80 at 0.1, which no straight line through those points matches; BS 8110 Table 3.9, from which the figure appears to derive, gives 0.8 up to 0.3 with linear interpolation.
* Cl. 23.1.2(c), (d): the isolated-beam expressions, and whether b is the actual flange width (as used).
* Cl. 23.1.1(b): the extent of the transverse bars (the corroborating sources give the 60 percent but not the extent).
* Annex G-2.2: the wording that lets x_u replace x_u,max.

### Beam engine 1.2.0: curtailment and stirrup zones (STR-016)

| Clause | Subject | Where |
|---|---|---|
| Cl. 26.2.3.1 | bars extend beyond the point where they are no longer needed by the greater of d and 12 phi | `beam.curtail_and_zones` |
| Cl. 26.2.1 | development length either side of the section of maximum stress | the same |
| Cl. 26.2.3.2(a), (b), (c) | bars stopped in a tension zone: shear at most 2/3 of the resistance; or closer stirrups along the stopped bars; or twice the steel needed and shear at most 3/4 | the same |
| Cl. 26.2.3.3(a) | a third of the positive steel to the supports of simple members | `beam.split_for_curtailment` |
| Cl. 40.4, 26.5.1.5, 26.5.1.6 | stirrup spacing by the shear diagram; minimum shear steel, 0.75 d, 300 mm | stirrup zones |

### Beam engine: curtailment interpretations

59. **Which bars stop.** The second layer, or alternate bars of a single layer; at least two bars (the corners, which carry the stirrups) and a third of the area continue. A single layer of two bars is not curtailed.
60. **Where.** From the factored load's moment diagram (simple span w x (l - x)/2 between centre lines, cantilever w (l - x)^2/2), the resistance of the continuing bars with the other face's bars as compression steel. Cut-offs are set out in 50 mm steps towards the supports (away from the support on a cantilever).
61. **Condition (b)** takes the excess as the stirrup area above the larger of the shear demand at the cut-off and the minimum of Cl. 26.5.1.6, over 3/4 d along each stopped bar, at no more than d/(8 beta_b); f_y in 0.4 b s/f_y is that of the stirrups.
62. **Not worth it.** No curtailment when the cut-off falls within d of a support, or when the closer stirrups of condition (b) weigh as much as the steel the stopped bars save. The sheet says which.
63. **Stirrup zones.** The spacing designed at the critical section is kept from each support to where the shear falls to the resistance at the wider spacing (minimum shear steel, 0.75 d or 300 mm), with tau_c of the bars that run to the support. Every gap between stirrups is the least spacing required anywhere over it.
64. **Forces entered** give no diagram: no curtailment and one spacing, as before.

### Continuous beam engine 1.1.0: curtailment and stirrup zones (STR-016)

65. **Diagrams.** The moment and shear along each span are the elastic envelope of the Cl. 22.4.1 arrangements (`engineering/continuous.py`), scaled up per span (sagging) and per support end (hogging, shear) wherever their peaks fall below the Table 12 and 13 values the sections were designed for; never scaled down.
66. **Top bars over a support.** As for the simple beam, a third of the area and at least two bars (the long bars) run to the point of inflection and beyond (Cl. 26.2.3.4, interpretation 54); the others stop beyond the point where the long bars suffice by the greater of d and 12 phi, and at least L_d from the face. Cl. 26.2.3.2 is applied at each cut-off. Over the C supports every distinct side is checked (span 2's end, span 3's start, a span between two C supports) and the farthest cut-off governs.
67. **Bottom bars.** A third of the area and the corner bars run into the supports (the code asks a quarter at continuous supports, Cl. 26.2.3.3(b); a third is used throughout). The others stop the greater of d and 12 phi short of where the continuing bars suffice, and at least L_d either side of the section of greatest moment, taken as the whole region within 0.5 percent of the peak (pattern loading moves the peak off mid-span and flattens it).
68. **One schedule for every interior span.** The governing cut-offs (the longest stopped bars) and the longest stirrup zones over all interior spans, made symmetric; condition (b) bands on both sides.
69. **Stirrup zones** use tau_c with the least tension steel and the least d among the span's mid-span and support sections.
70. **Not worth it** as for the simple beam: no curtailment within d of a support, or where (b)'s stirrups weigh as much as the steel saved.
70a. **Compression steel at the supports.** A support section designed with the bottom bars as compression steel counts only the bars that reach it. Bottom bars are not curtailed where the continuing bars alone would leave a neighbouring support short of A_sc,req, over-reinforced, or below its moment. *Added in continuous beam 1.5.0: until then curtailment could stop bars the support relied on (found in 66 of 193 sampled designs, the T-beam floor case of the hand check among them).*

### Anchorage at simple supports and points of inflection (STR-017)

| Clause | Subject | Where |
|---|---|---|
| Cl. 26.2.3.3(c) | L_d <= M_1/V + L_0, M_1/V raised 30 percent where a compressive reaction confines the bar ends; at a point of inflection L_0 is the greater of d and 12 phi | `beam.anchorage_ok`, `anchorage_check` |
| Cl. 26.2.2.1(b) | anchorage value of a 90 degree bend, 8 phi; of a standard U-type hook, 16 phi | `beam.BEND_90_ANCHORAGE`, `beam.HOOK_ANCHORAGE` |
| IS 2502 | internal radius of bends and hooks, 2 phi (mild steel) and 4 phi (deformed bars); a U-hook's 4 phi straight tail | `rebar.bend_radius`, `beam_detailing.hook_allowance` |

71. **M_1** is computed with all the bars that reach the point at f_d and the neutral axis from equilibrium, without the x_u,max limit ("assuming all reinforcement at the section to be stressed to f_d"); a compression flange counts where there is one, compression steel does not (on the safe side).
72. **V** at a simple support is the shear at the face (the simple beam's w_u l_c/2, the continuous beam's Table 13 value at the end support); at a point of inflection, the scaled shear envelope there.
73. **L_0** at a simple support is the straight bar beyond the centre of the support, plus the anchorage value of a bend or hook at its end. A straight bar ends at cover from the far face: w_s/2 - cover. A bent or hooked bar's straight part ends where the bend starts, r + phi inside the bar's outer face (r the IS 2502 radius): w_s/2 - cover - (r + phi), plus 8 phi for a 90 degree bend or 16 phi for a U-hook. *Corrected in beam 1.4.0 and continuous beam 1.4.0 (STR-037): until then the bend's 8 phi was added to the full w_s/2 - cover, which counted the r + phi of bar inside the bend twice (5 phi for deformed bars, 3 phi for mild steel, on the unsafe side).* The 1.3 factor is taken at every simple support (the beam bears on a wall or column); not at points of inflection.
74. **Enforced, not only checked.** Both beams' bar selection rejects bottom bars that fail the clause even with a U-hook (the continuous beam at its end supports and its points of inflection, with a 2 percent margin on the shears because the final check uses the spans of the bars chosen); curtailment is withdrawn where the continuing bars alone would fail. If nothing passes, the design stops with that reason.
76. **End detail, the least that serves.** Straight, then a 90 degree bend, then a standard U-hook, the first that meets Cl. 26.2.3.3(c); bars that Cl. 26.2.3.3(a) already bends (the support shorter than L_d/3) start from the bend. The sheet states each step up. The hook is scheduled as "U-hook both ends" (simple beam) or "U-hook at the end support" (continuous beam's end spans), cutting length A plus the hook allowance per hook, pi (r + phi/2) + 4 phi - (r + phi), rounded up to 5 mm: about 13 phi for deformed bars and 9 phi for mild steel (the arc on the centre line and the tail, less the straight part the hook replaces, measured to the outside of the bar).
77. **A hook must fit.** Its outside height is 2 r + 2 phi (10 phi for deformed bars). As with the 90 degree bend's leg, the engine does not check that it clears the top bars; with the bar sizes the selection reaches (up to T32) and beams deep enough to carry them this holds, and the drawing shows it.
75. **Points of inflection of the bottom bars** in a continuous beam: where the greatest moment of the scaled envelope turns positive next to an interior support; the check uses the larger shear of the span sides concerned.

### Continuous beam engine 1.0.0: clauses taken

The code text was not read. Table 12 and the end-support value of Table 13 were corroborated; the rest of Table 13 and the wording of Cl. 22.2(b), 22.4.1 and 26.2.3.4 are as commonly published.

| Clause | Subject | Where |
|---|---|---|
| Cl. 22.2(b) | effective span of continuous beams: narrow supports as 22.2(a); wide supports: end span l_c + min(d/2, w_s/2), interior spans l_c | `continuous_beam.effective_spans` |
| Cl. 22.4.1 | arrangements of imposed load: on adjacent spans, on alternate spans | `engineering/continuous.load_arrangements` |
| Cl. 22.5.1, Table 12 | moments of continuous beams over three or more spans within 15 percent; average of the two values at a support between unequal spans; no redistribution | `span_moment`, `support_moment` |
| Cl. 22.5.1, Table 13 | shears at the end support, either side of the support next to the end, and other interior supports | `support_shear` |
| Cl. 22.6.2.1 | shear at d from the face | shear section |
| Cl. 23.1.2, note | l_0 = 0.7 l for continuous beams | `make_flange` |
| Cl. 23.2.1(a) | basic span/depth 26 for continuous beams | deflection section |
| Cl. 26.2.3.3 | positive steel into the end supports (one third of L_d) | schedule |
| Cl. 26.2.3.4 | negative steel beyond the point of inflection by the greatest of d, 12 phi, l_n/16 | extents of the top bars |
| Cl. 26.2.5.1(c), (d) | laps in tension (L_d, at least 30 phi) and in compression (L_d,c, at least 24 phi) | `continuous_beam_detailing.layout` |
| Cl. 29 | deep beams: a continuous beam with l/D below 2.5 stops | stop state |

### Continuous beam engine: interpretations

49. **One design for the whole beam.** Equal spans and one section; the end spans and the interior spans, the supports next to the ends (B) and the other interior supports (C) are designed separately. Spans that differ within 15 percent are entered as the longest, on the safe side.
50. **Dead load fixed, imposed load not fixed** (the two columns of Tables 12 and 13), each factored by the entered load factor.
51. **Table 13 shear** is taken at the face of the support and reduced to d from the face by (w_d + w_l) d (Cl. 22.6.2.1), as for the simple beam. Each span type takes the worse of its two ends, each with its own tension steel for tau_c (bottom steel at the end support, top steel at the interior supports).
52. **Support sections** are rectangles of the web width (the flange is in tension) with the lighter of the two adjacent spans' bottom bars as compression steel; where it is needed, those bars continue past the far face of the support by the development length in compression.
53. **Points of inflection** come from an elastic analysis (three-moment equation, knife-edge supports, the end supports free) of every arrangement of Cl. 22.4.1 (imposed load on all spans, on alternate spans, on each pair of adjacent spans); the design moments stay those of Table 12. The analysis runs between centre lines and the extents are set out from the faces.
54. **All top bars over a support** run beyond the furthest point of inflection by the greatest of d, 12 phi and l_c/16, and at least L_d from the face; the code asks this of one third of them (Cl. 26.2.3.4). Partial curtailment is STR-016.
55. **Support bars that meet** (no room for a hanger lapped at both ends) run to mid-span and lap there in tension; the hogging there under the elastic envelope is checked against the weaker of the two sets, their compression steel ignored. In an end span they run on to the end support instead.
56. **Hangers** lap with the support bars in compression (they lie beyond the point of inflection).
57. **The end spans** take the continuous basic ratio 26 (Cl. 23.2.1(a) lists only simply supported, continuous and cantilever).
58. **Cl. 29** for continuous beams: deep when the effective span is less than 2.5 D (2.0 for a simple span).

### Continuous beam engine: to cross-check against a printed copy

* Table 13: every value except the 0.40 at the end support; whether the coefficient multiplies the total load on the effective or the clear span (the effective span is used).
* Cl. 22.2(b): the 1/12 and 600 mm thresholds and the end-span rule.
* Cl. 22.4.1: the two arrangements of imposed load.
* Cl. 26.2.3.4: d, 12 phi, l_n/16, and the one third.
* Cl. 29: 2.5 for continuous beams.
* Cl. 26.2.3.2: the three conditions, and whether f_y in 0.4 b s/f_y is that of the stirrups (as used).
* Cl. 26.2.3.3(b): a quarter of the positive steel into continuous supports (a third is used).
* Cl. 26.2.3.3(c): the wording of M_1 ("all reinforcement at the section stressed to f_d"), the 30 percent increase, and L_0 at a point of inflection.

### Continuous beam engine 1.5.0: elastic analysis with redistribution (STR-036)

The second method of the continuous beam element (`analysis = "elastic"`). The code text was not read; the wording of Cl. 37.1.1 below is as commonly published.

| Clause | Subject | Where |
|---|---|---|
| Cl. 22.2(b) | effective span of each span: narrow supports as 22.2(a); wide supports: end spans l_c + min(d/2, w_s/2), interior spans l_c | `continuous_elastic.effective_spans` |
| Cl. 22.4.1 | arrangements of imposed load with any loads: all spans, alternate spans, each pair of adjacent spans | `engineering/continuous.arrangements` |
| Cl. 22.6.2 | moments at the face of monolithic supports: an option (`support_moments_at`); otherwise the centre line, on the safe side | `continuous_elastic.design` |
| Cl. 22.6.2.1 | shear at d from the face; at the face where a point load lies within d of it | shear section, stirrup bands |
| Cl. 22.7 | redistribution with an elastic analysis by 37.1.1; none with the coefficients | the two methods |
| Cl. 37.1.1(a) | equilibrium: the span moments of every arrangement follow by statics from the modified support moments | `engineering/continuous.redistribute`, `envelopes` |
| Cl. 37.1.1(b) | resistance nowhere below 70 percent of the elastic envelope | `continuous_elastic.Beam` (design envelope) |
| Cl. 37.1.1(c) | no moment reduced by more than 30 percent of the numerically largest elastic moment in the member | check `redistribution_<support>` |
| Cl. 37.1.1(d) | x_u/d + dM/100 <= 0.6 where the resistance is below the elastic moment | bar selection, check `xu_redistribution_<section>` |
| Cl. 26.2.1, 26.2.5.1(c) | top bars of two supports that meet within a span: tension lap, and each set developed in proportion to its embedment | `continuous_elastic_detailing.layout`, `meet_resistance` |

### Continuous beam engine: elastic interpretations

78. **One element, two methods.** The continuous beam element takes `analysis`: Tables 12 and 13 (equal spans, uniform load, unchanged) or elastic analysis. The elastic method takes a table of spans (clear span, dead and imposed uniform load each), a table of point loads (span, distance from the left face, dead and imposed), and a redistribution percentage.
79. **The model.** Knife-edge supports, the end supports free, one EI. Each span runs between the ends of its effective span (Cl. 22.2(b)), worked out with the greatest effective depth the bars allow (one layer of T12, or of the bar size entered); that gives the longest spans, on the safe side. The faces lie (l - l_c)/2 inside each end, and point loads are placed from the left face. Point loads lie within the clear span.
80. **Loads.** Dead loads (uniform and point, with the self-weight) on every span; each span's imposed loads (uniform and point together) placed by the arrangements of interpretation 53. Everything is factored by the one load factor entered.
81. **Redistribution.** In every arrangement the hogging at each interior support is held to (1 - r) of the greatest elastic hogging there; moments below that are left as they are. The span moments follow by statics. The value entered is the most applied. Where a support's section cannot meet it (its moment, or Cl. 37.1.1(d)), the engine first gives it more compression steel, raising the bottom bars of the lighter span beside it to their next arrangement (continuous beam 1.6.0). Only where no heavier bars help does that support take 5 percent less redistribution, with the envelope worked out again. The sheet and the summary say which.
82. **Design envelope** = max(redistributed, 0.7 x elastic) at every section, for sagging and hogging (37.1.1(b)). A support's design moment is therefore (1 - r) M_e, never below 0.7 M_e; a span's is the greatest of its design envelope.
83. **Condition (c)** is checked at each support as r M_e <= 0.3 x the largest elastic moment anywhere in the beam; with r <= 30 percent it always holds, and the check states it.
84. **Condition (d).** dM = 100 (1 - M_d / M_e) for the section's design moment against its greatest elastic moment. It applies where the resistance provided is below M_e, with x_u of the bars provided (the compression steel counted). The bar selection passes over arrangements that fail it.
85. **Support moments at the centre lines** of the supports (the analysis nodes) by default: on the safe side, and right where the supports are walls. With `support_moments_at = "faces"` (monolithic construction, Cl. 22.6.2, continuous beam 1.6.0) each support is designed for the greater of the design envelope's hogging at its two faces, and Cl. 37.1.1(d) compares that with the elastic envelope at the same face. The redistribution itself is still worked at the nodes (interpretation 81), and the extents and cut-offs of the top bars come from the envelope as before.
86. **Shear.** V from the redistributed envelope (equilibrium), at d from the face, or at the face where a point load lies within d of it. At each end, tau_c takes the bars certain to reach that section: the first layer, or the continuing part of a single layer. Along the span, closer stirrups go wherever the shear needs a spacing below that of minimum shear steel (0.75 d, 300 mm), with tau_c of the least such steel and the least d of the span and its supports. Every gap between stirrups is the least spacing required anywhere over it.
87. **Sections.** Each span is designed for its own greatest sagging, each interior support for its own hogging. The support takes the lighter of its two spans' bottom bars as compression steel; curtailment keeps those bars (interpretation 70a).
88. **Top bars that meet within a span** (no room for a hanger lapped at both ends) each run at least past mid-span, overlapping by a tension lap. At every section of that span the hogging is checked against the bars developed there, each set in proportion to its embedment beyond the section up to L_d, at the centroid of those bars, with the continuing bottom bars as compression steel.
89. **Deflection** for each span with its own l/d, basic ratio 26. A span with no sagging takes k_t = 2 (Fig. 4 tops out there).
90. **The schedule** merges alike rows (same role, shape, size, lengths and count) across spans and supports. The drawing has an elevation of every span and cross-sections of the heaviest span and support. The workspace's drawing panels pick among the views when there are more than two.

91. **Cantilevers at the ends** (continuous beam 1.6.0, the elastic method). A cantilever's length is taken to the centre of its support (Cl. 22.2(c), the end of a continuous beam), and its moment there, (w_d + w_l) l^2/2 + P l, is a known end moment in the three-moment equation. Each cantilever is loaded and unloaded with every arrangement of Cl. 22.4.1 (dead load always, at the same factor). Its moment is statically determinate, so it is never redistributed.
92. **The cantilever's support** is designed like an interior support: top bars for the greater moment (the centre line, or the faces where monolithic), the bottom bars of the end span as compression steel. Every top bar runs to the tip less cover and is bent down there to the bottom bars. Its L_d must fit between the face and the start of the bend, plus 8 phi; the bar selection passes over bars that would not. The bars run into the span to their extent, uncurtailed. The cantilever's bottom bars are two of the hanger size, from the tip into the support.
93. **The cantilever's checks.** Shear at d from the face, with tau_c of its top bars, sets one stirrup spacing along it; tau_c,max is checked there too. Deflection uses the basic ratio 7 (Cl. 23.2.1), with the length to the centre of the support over d, k_t of the top bars, and no flange factor (the flange is in tension). Next to a cantilever, the end span's bottom bars meet no simple support: no end detail, and Cl. 26.2.3.3(c) is checked at the point of inflection instead.
94. **Uplift.** Every support's reaction is worked out in every arrangement. Where one turns downward (a long cantilever beside a light span), a warning says the beam must be held down there; the analysis assumes it is.
94a. **Supports of their own widths** (continuous beam 1.7.0, STR-041, the elastic method). A table gives each support its width; left empty, every support takes the one support width. A span follows Cl. 22.2(a) only where both its supports are narrower than l_c/12 and 600 mm: l_c + d, not more than its centre-to-centre distance l_c + (w_left + w_right)/2. An end span's allowance l_c + min(d/2, w/2) takes the width of its discontinuous support, and a cantilever's length runs to the centre of its own support. The faces still lie (l - l_c)/2 inside each end of the analysis span (interpretation 79). The bars' lengths, the anchorage at each end support, the quantities and the drawing take each support's width.

### Continuous beam engine: elastic, to cross-check against a printed copy

* Cl. 37.1.1: the 30 percent and its base ("the numerically largest moment given anywhere by the elastic maximum moments diagram for the particular member"); (b) 70 percent; (d) x_u/d + dM/100 <= 0.6 and the meaning of dM.
* Cl. 22.7: redistribution by 37.1.1 with an elastic analysis; none with the coefficients.
* Cl. 22.6.2: the face moments for monolithic construction, and whether the greater of the two faces is meant where they differ (used).
* Cl. 22.4.1, note: the arrangement of imposed load on all spans where it does not exceed three quarters of the dead load (all arrangements are used regardless).
* Cl. 22.2(c): the effective length of a cantilever at the end of a continuous beam (to the centre of the support, as used).
* Cl. 23.2.1(a): the basic ratio 7 for cantilevers, and whether the length is the effective one (used).

### Column engine 1.0.0: clauses taken

**Read this first.** The text of IS 456:2000 could not be read while the column engine was built. The public copy at law.resource.org was outside the reach of the session's page-fetching tool, and a direct download was declined by the session's permission check. The clauses below are implemented from the code as commonly published, and the key rules were corroborated against secondary sources (listed at the end). Until a printed, fully amended copy has been compared, treat every item in "To cross-check" below as open.

| Clause | Subject | Where |
|---|---|---|
| Cl. 25.1.2 | short when both effective-length ratios are less than 12 | `column.axis_geometry` |
| Cl. 25.2, Table 28 | effective length from end restraint (recommended values) | `column.TABLE_28` |
| Cl. 25.3.1 | unsupported length not more than 60 times the least lateral dimension | check `l_max` |
| Cl. 25.3.2 | one end unrestrained: l not more than 100 b^2/D | check `l_cantilever_*` |
| Cl. 25.4 and note | minimum eccentricity l/500 + D/30, at least 20 mm; about one axis at a time | `column.design_moments` |
| Cl. 26.2.5.1(d) | lap in compression: development length in compression, not less than 24 d | lap length |
| Cl. 26.3.2(a) | minimum clear distance between bars | `column.candidates` |
| Cl. 26.4.2.1 | cover to longitudinal bars 40 mm and not less than the bar; 25 mm for small columns with small bars | `column.min_longitudinal_cover` |
| Cl. 26.5.3.1 (a), (c), (d), (g) | 0.8 to 6 percent; at least four bars; at least 12 mm; at most 300 mm along the periphery | `column.candidates`, checks |
| Cl. 26.5.3.2 (b), (c) | tie arrangement (corner and alternate bars, 75 mm); tie pitch and diameter | `column.restrained_bars`, `column.tie_spacing` |
| Cl. 32.1 | a member longer than four times its thickness is a wall | input validation |
| Cl. 38.1(f) | limiting neutral-axis depth, used for the balanced load P_b | `rc_section.balanced` |
| Cl. 39.1, Fig. 21, Fig. 23 | strain compatibility, including the rule for a neutral axis outside the section | `app/engineering/rc_section.py` |
| Cl. 39.3 | short column with only minimum eccentricity: 0.4 fck Ac + 0.67 fy Asc | `column.evaluate` |
| Cl. 39.6 | biaxial interaction, P_uz = 0.45 fck Ac + 0.75 fy Asc, alpha_n from P_u/P_uz | `column.evaluate`, `column.alpha_n` |
| Cl. 39.7.1 and note 1 | additional moments; initial moment of braced columns | `column.axis_geometry` |
| Cl. 39.7.1.1 | reduction factor k = (P_uz - P_u)/(P_uz - P_b), not more than 1 | `column.evaluate` |

### Column engine: interpretations

12. **Stress block in the section analysis.** The column analysis integrates Fig. 21 exactly (0.67 fck / 1.5 = 0.4467 fck; resultant 0.3616 fck b x_u at 0.416 x_u). The beam engine uses the code-rounded 0.36 and 0.42 of Annex G. The two differ by less than 0.5 percent; a test pins the difference. SP 16's column charts use the exact block.
13. **Displaced concrete.** A bar in the compressed concrete is credited with its steel stress less the concrete stress at its strain, as in SP 16.
14. **Balanced load P_b.** Computed by strain compatibility at the limiting neutral-axis depth of Cl. 38.1(f), measured to the extreme tension row of the actual bars, not from the coefficients of SP 16 Table 60.
15. **Additional moments** are applied only about an axis whose ratio is 12 or more. A ratio of exactly 12 is slender ("short" needs less than 12).
16. **Minimum eccentricity with slenderness.** Per axis: the initial moment, raised to P_u e_min on the axis that takes the minimum eccentricity in that load case, plus k M_a, and never less than the larger end moment. Two load cases, minimum eccentricity about x and then about y (Cl. 25.4, note).
17. **Cl. 39.3** is used only when both axes are short, there are no end moments, and e_min is not more than 0.05 times the dimension on both axes. Otherwise the column is checked for bending, and the sheet says why.
18. **Table 28** is offered as its seven rows with the recommended factors, plus an entered factor. Rows (d) to (g) are treated as sway, (a) to (c) as braced; an entered factor states sway or not. Cl. 25.3.2 is applied to row (g) only, the one end neither held in position nor restrained.
19. **Ties.** Corner bars are held by the perimeter tie. Where bars on a face are 75 mm or less apart, centre to centre, alternate intermediate bars get a cross-tie; otherwise every intermediate bar does. Cross-ties are single legs with 135 degree hooks. The rule allowing open ties between bars tied in two directions at not more than 48 tie diameters is not used, which gives more ties, not fewer. Tie diameter at least a quarter of the largest bar and 6 mm; pitch the least of the least lateral dimension, 16 times the smallest bar and 300 mm, rounded down to 25 mm.
20. **Cover.** With no entry, cover to the ties is the larger of Table 16 and 40 mm less the tie diameter, so the main bars get the 40 mm of Cl. 26.4.2.1.
21. **Two values of the axial capacity.** P_uz of Cl. 39.6 (0.45 and 0.75) is used for alpha_n, for k and for the check P_u <= P_uz. The uniaxial capacities and the interaction diagrams use strain compatibility, whose squash load (0.4467 fck and the steel stress at 0.002) differs slightly.
22. **Bar selection** minimises the mass of main bars, ties and cross-ties per metre of height among symmetric arrangements that meet the detailing rules and pass every strength check. Main steel alone favours many small bars, which tighten the tie pitch and add cross-ties.
23. **Scope**: rectangular tied columns; forces from an external analysis; one lift. Circular and helically reinforced columns (Cl. 39.4), Annex E stiffness-based effective lengths and IS 13920 detailing are not covered.

### Column engine: to cross-check against a printed copy

* Table 28: every row's wording and recommended factor (0.65, 0.80, 1.00, 1.20, 1.50, 2.00, 2.00). No secondary source found confirmed all seven.
* Cl. 39.7.1, note 1 (initial moment 0.4 M_u1 + 0.6 M_u2, not less than 0.4 M_u2; total not less than M_u2): corroborated by two secondary sources; confirm the wording and the sign convention.
* Whether Cl. 39.7.1 intends additional moments about both axes once either ratio reaches 12 (interpretation 15).
* Cl. 26.5.3.2(b): whether "spaced not more than 75 mm" is clear or centre to centre, and the exact wording of the 48 tie-diameter rule.
* Cl. 26.4.2.1: the small-column exception (25 mm where the column is 200 mm or less and the bars 12 mm or less).
* Cl. 26.2.5.1(d): 24 diameters as the minimum lap in compression.
* Cl. 25.3.2: 100 b^2/D for an unrestrained end.
* Cl. 39.3: the condition for using the axial formula.
* Whether Amendments 1 to 6 change any of the clauses above.

### Slab engine 1.0.0: clauses taken

The code text was not read for the slab either (same reason as the column). Table 27 was verified by derivation; the other values are as commonly published and the corroborated ones are listed under "Sources consulted".

| Clause | Subject | Where |
|---|---|---|
| Cl. 22.2 | effective span: clear span plus d, not more than centre to centre of supports | `slab._plan` |
| Cl. 22.5.1, Table 12, Table 13 | moment and shear coefficients for continuous one-way strips | `is456_slabs.TABLE_12`, `TABLE_13` |
| Cl. 22.6.2.1 | shear at d from the face of the support | `slab._plan` |
| Cl. 23.2.1, Fig. 4 | span to effective depth with the tension steel factor | slab check `deflection` |
| Cl. 24.1, note 2 | span to overall depth for two-way slabs (l_x up to 3.5 m, imposed load up to 3 kN/m2) | `two_way_span_depth_note2` |
| Cl. 24.4, Annex D-1.1, Table 26 | two-way panels with corners held down | `TABLE_26`, `case_26`, `coefficients_26` |
| Annex D-2, Table 27 | simply supported panels with corners free to lift | `rankine_grashoff`, `TABLE_27_X`, `TABLE_27_Y` |
| Annex D-1.2 to D-1.7 | middle and edge strips; moments to the middle strips; bottom and top steel extents; top steel at discontinuous edges; edge strip steel | `slab_detailing` |
| Annex D-1.8 to D-1.10 | torsion steel at corners: 3/4 of the mid-span steel over l_x/5; half where one edge is continuous; none where both are | `slab._plan`, `TORSION_*` |
| Annex D-1.11 | one-way when l_y/l_x is more than 2 | `slab._plan` |
| Cl. 26.3.3(b) | spacing: main bars 3d or 300 mm; distribution bars 5d or 450 mm | `max_spacing_main`, `max_spacing_distribution` |
| Cl. 26.5.2.1, 26.5.2.2 | minimum steel 0.15 / 0.12 percent; bar not larger than D/8 | `min_steel`, `max_bar_diameter` |
| Cl. 40.2.1.1 | k for solid slabs by overall depth (1.30 at 150 mm or less to 1.00 at 300 mm or more) | `shear_factor_k` |
| Cl. 40.2.3.1 | nominal shear in slabs not more than half of Table 20 | slab check `shear_max` |

### Slab engine: interpretations

24. **Table 27 by formula.** Generated from alpha_x = r^4 / (8 (1 + r^4)) and alpha_y = r^2 / (8 (1 + r^4)) and rounded to three decimals; a test compares the result with the printed values for r up to 2.
25. **Table 26 case from the edges.** The case follows from the number of discontinuous long and short edges (`case_26`); with three discontinuous edges, cases 7 and 8 are told apart by which edge is continuous. Linear interpolation in l_y/l_x; the end values beyond 1.0 and 2.0.
26. **Table 27 is used only** when all four edges are discontinuous and the corners are free. A panel with any continuous edge, or held-down corners, uses Table 26. Corners free with a continuous edge are designed as held down, and the sheet says so.
27. **One-way continuous strips.** An end span (one long edge discontinuous) takes the end-span coefficients of Table 12; an interior span the interior-span ones (1/16 dead, 1/12 imposed). The support moment is the "support next to the end support" value (1/10, 1/9) for both, the larger of the two support rows; shear is the next-to-end value for the side of the support concerned. Tables 12 and 13 assume three or more nearly equal spans (Cl. 22.5.1); the registry entry says so.
28. **Shear in two-way panels.** A strip spanning the short way: V_u = w_u (l_x/2 - d) per metre, on the safe side of the load-sharing of Table 26.
29. **Deflection.** Note 2 of Cl. 24.1 is used where it applies (Fe 415 or mild steel, two-way, l_x up to 3.5 m, imposed load up to 3 kN/m2). Otherwise Cl. 23.2.1 on the short span: basic 20 when both long edges are discontinuous, 26 when either is continuous.
30. **Top steel over continuous edges** extends 0.3 l on each side of the support, where l is the span in the bars' direction (l_x for bars over the long edges). The code lets half the bars stop at 0.15 l; all bars are scheduled to 0.3 l. Bars over a shared support are scheduled whole with this panel: the adjacent panel's schedule must leave them out (the schedule notes say so).
31. **Top steel at discontinuous edges** is half the mid-span steel, 0.1 l into the span, an L-bar down into the support (Annex D-1.6, applied whatever the restraint the support gives).
32. **Bottom bars** run the full span to the far face of the supports less cover, more than the 0.25 l / 0.15 l of Annex D-1.4 asks.
33. **Torsion steel** is detailed as four mats per corner (top and bottom, both ways) of l_x/5; half the area at corners with one continuous edge. Distribution bars under top bars are at the minimum steel.
34. **One bar size per panel**: the smallest that gives spacings of at least 100 mm everywhere (75 mm if none does).

### Slab engine: to cross-check against a printed copy

* Table 26: every row other than those corroborated (case 1 both rows; case 2 negative; case 7 positive; case 9; the first four values of case 5 positive and the first six of case 6 positive). Tests hold the structure (rising with l_y/l_x; negative over positive between 1.27 and 1.40; a negative coefficient exactly where an edge is continuous) and the hand check enters the table independently.
* Table 13: no secondary source reproduced all eight values.
* Annex D-1.4 to D-1.6: the 0.25 l / 0.15 l bottom extents, the 0.15 l / 0.3 l top extents and the 0.1 l at discontinuous edges; whether l is the span in the bars' direction (interpretation 30).
* Cl. 24.1, note 2: the values 35 and 40 and the factor 0.8 for Fe 415.

### Footing engine 1.0.0: clauses taken

As for the slab, the code text was not read; Cl. 34.1.2, 34.3.1, 34.4 and 26.4.2.2 were corroborated by secondary sources.

| Clause | Subject | Where |
|---|---|---|
| Cl. 26.4.2.2 | cover in footings at least 50 mm | `effective_cover`, check `cover` |
| Cl. 34.1.2 | thickness at the edge at least 150 mm on soil | check `edge` |
| Cl. 34.2.3.1, 34.2.3.2 | bending moment at the face of the column, over the whole width | `trial` |
| Cl. 34.2.4.1(a), Table 19 | one-way shear at d from the face | `trial`, checks `shear_L`, `shear_B` |
| Cl. 34.2.4.1(b), Cl. 31.6 | punching at d/2; k_s tau_c with k_s = 0.5 + beta_c not more than 1 and tau_c = 0.25 sqrt(f_ck) | `trial`, check `punching` |
| Cl. 34.2.4.3, Cl. 26.2.1 | development length within the projection | `trial` (`ok_anchorage`) |
| Cl. 26.2.2.1(b) | anchorage value of a 90 degree bend: 8 diameters | `BEND_90_VALUE` |
| Cl. 34.3.1(a), (b) | steel uniform across the width; in the short direction 2/(beta + 1) of it in the central band | `bars_short_direction`, check `band` |
| Cl. 34.4 | bearing 0.45 f_ck sqrt(A_1/A_2), not more than twice; A_1 within a 1 in 2 frustum | check `bearing` |
| Cl. 34.4.3 | column bars or dowels at least 0.5 percent of the column area | step `dowels` |
| Cl. 26.5.2.1 | minimum steel in each direction, as for slabs | `trial` |

### Footing engine: interpretations

35. **Pressure for design.** The largest factored pressure, from the column load and moments only (own weight acts against its own reaction), is applied uniformly over the whole footing for bending and shear. On the safe side with moments; the sheet says so.
36. **Plan size** with equal projections from the column faces, in 25 mm steps of projection and 50 mm steps of plan, smallest that keeps the service pressure within the safe bearing pressure and the least pressure not negative. The own weight is an entered percentage of the column load.
37. **Development length.** Straight bars at any depth are preferred; bars with a 90 degree bend at each end (anchorage value 8 diameters, leg 12 diameters) are used only when no straight bar develops within the projection at any depth. With a bend, the straight part runs from the column face to where the bend starts, r + phi inside the bar's outer face (IS 2502 radius r): L_d <= a - c - (r + phi) + 8 phi. *Corrected in footing 1.1.0, as interpretation 73: 1.0.0 added the 8 phi to the full a - c.* When even 10 mm bars with bends cannot develop, an automatically sized plan grows in 50 mm steps until they can (a flag gives the bearing size and the larger one); an entered plan stops with that remedy.
38. **One-way shear** uses tau_c of Table 19 without the slab factor k of Cl. 40.2.1.1, on the safe side.
39. **Bearing area A_1.** The lower base of the largest frustum similar to the column, wholly within the footing, sides 1 vertical to 2 horizontal: each side grows by at most 2 D. sqrt(A_1/A_2) is then min(L/D_c, B/b_c, 1 + 4 D / max(b_c, D_c), 2).
40. **Central band.** When the band spacing already covers the whole length (nearly square footings), the bars are spread uniformly; otherwise band and outer parts have their own spacings.
41. **Cover** at least 50 mm whatever Table 16 gives for the exposure (larger values from Table 16 govern, 75 mm for extreme).

### Footing engine: to cross-check against a printed copy

* Cl. 34.2.4.3 wording on development length at the face and the use of bends.
* Cl. 34.4 wording on A_1 for footings of uniform depth (the frustum is printed for sloped and stepped footings).
* Cl. 31.6.3.1: k_s and 0.25 sqrt(f_ck).
* Whether Amendments 1 to 6 change any of the clauses above.

### Combined footing engine 1.0.0: clauses taken (STR-020)

IS 456 has no clause for combined footings as such. Section 34 is applied to them as to any footing, and the gaps are interpretations 95 to 103.

| Clause | Subject | Where |
|---|---|---|
| Cl. 26.4.2.2 | cover in footings at least 50 mm | `effective_cover`, check `cover` |
| Cl. 34.1.2 | thickness at the edge at least 150 mm on soil | check `edge` |
| Cl. 34.2.3.2 | bending at the faces of the columns, along and across | `Statics`, `trial`, checks `mulim_*` |
| Cl. 34.2.4.1(a), Table 19 | one-way shear at d from the faces of the columns, along and in the bands across | `trial`, checks `shear_<x>`, `shear_band<i>` |
| Cl. 34.2.4.1(b), Cl. 31.6.1, 31.6.3.1 | punching at d/2; k_s 0.25 sqrt(f_ck) | `punching_zones`, checks `punching_<columns>` |
| Cl. 26.2.1, 34.2.4.3 | development of every set at the stress of its critical sections | checks `anchor_bottom_<x>`, `anchor_top`, `anchor_band<i>` |
| Cl. 26.2.2.1(b) | anchorage value of a 90 degree bend: 8 diameters | `footing.bent_value` |
| Cl. 26.5.2.1, 26.3.3(b), 26.3.2(a) | minimum steel each way; spacing at most 3 d and 300 mm; clear spacing | `trial`, checks `as_*`, `spacing_*` |
| Cl. 34.4, 34.4.3 | bearing at the base of each column; dowels at least 0.5 percent | checks `bearing<i>`, steps |
| Table 18 | the load factor for the design of the concrete | `Statics` |

### Combined footing engine: interpretations

95. **Rigid footing.** The net factored pressure, from the column loads only (the own weight acts against its own reaction), varies linearly along the footing so that it balances them, and is uniform across. The service pressures add the own-weight allowance at the centre. Along, the footing is a beam carrying that pressure up and each column's load down, spread over the column's depth (outside the columns this is the same as a point load at the centre).
96. **Bands across.** IS 456 sets no width for the steel across under a column. The engine takes the column's depth along the footing plus 0.75 d each side, cut at the footing's ends and at the middle of the gap between the columns. References use from b + d to b + 2d; this is the middle of that range. The column's factored load is spread across the width, giving M = (P_u / B) a^2 / 2 at the face of the column. Outside the bands the steel across is the minimum of Cl. 26.5.2.1, at the spacing for main bars.
97. **Plan.**
    * The left end may be entered, for example at a property line; the length is then centred on the resultant, rounded up to 50 mm.
    * With the length entered, the left end centres it, to 25 mm. With both entered they are kept, and the pressure varies as it must.
    * With neither, the engine takes the left end, on a 25 mm grid, whose greatest sagging and hogging along are nearest equal (the classic economy). It first keeps to plans no wider than they are long, so that close columns still get a footing along their line.
    * The width is the least, in 50 mm steps and at least 50 mm beyond the wider column each side, that keeps the service pressure within the safe bearing pressure with no loss of contact. It grows in 50 mm steps where the bars across cannot be developed. A heavier column at a restricted end, which no centred rectangle can carry, is refused with the remedy (STR-044).
98. **Development at the stress of the section.** Each set is developed at its critical sections at the stress there: L_d x A_s for the moment / A_s provided (Cl. 26.2.1 defines L_d with sigma_s at the section). The sections are:
    * for the bottom bars along, each column face where the footing sags, to the nearer end;
    * for the top bars, each side of the greatest hogging;
    * for the bars across, the column faces.

    Bends of 8 diameters are used where straight bars fall short. This differs from the isolated footing, which takes the full stress (interpretation 37): at a property line the full stress would ask for anchorage of bars that carry no moment there.
99. **Bars.**
    * Every set takes the smallest bar size that fits at a practical spacing (100 mm or more) and develops, straight bars before bent ones.
    * The bars along run the full length, uncurtailed, bottom and top, each at least the minimum of Cl. 26.5.2.1 over B x D.
    * Layers: the bars across lowest, the bars along the bottom resting on them, the top bars at the cover.
100. **One-way shear along** at d from each column face: outer faces with d of the bottom bars, inner faces with d of the top bars. tau_c is that of the bars in tension at the section, found by the sign of the moment there. A section beyond the footing's end, or past the other column's face where the gap is less than d, is not checked. **Across**, in each band at d from the column face, over the band's width.
101. **Punching** on the perimeter at d/2 from the column faces, with d the mean of the two bottom layers. Sides that would fall on or outside the footing's edges are dropped, so a column at a property line has three. Where the two columns' perimeters overlap, they are checked as one outline round both, with both loads, the pressure within the outline and the lesser k_s.
102. **Bearing** A_1 at each column: the base of the largest frustum concentric and similar to the column within the footing at 1 in 2. sqrt(A_1/A_2) = min(2 min(x, L - x)/D_c, B/b_c, 1 + 4 D/max(b_c, D_c), 2).
103. **Depth**: the least in 50 mm steps that needs no compression steel and no shear reinforcement. An entered depth is checked as it is.
104. **Column moments along** (combined footing 1.1.0, STR-045).
    * Each column may carry a service moment in the plane of the footing's length, clockwise positive with column 1 on the left. It moves the resultant: x_r = (P_2 s + M_1 + M_2) / (P_1 + P_2). The plan is centred on that, so a constant moment gives uniform pressure again.
    * For design, each moment is factored by the one load factor and enters the statics as a couple at its column, spread over the column's depth (outside the column, the same as at its centre). The pressure that balances the loads and couples varies linearly.
    * One load case: moments that reverse, as wind and earthquake do, need a design for each sense, and the sheet says so. Moments across the footing and horizontal loads are not covered (STR-046).

### Strap footing engine 1.0.0: clauses taken (STR-044)

IS 456 has no clause for strap footings; the statics are the standard ones, and Section 34 and the beam clauses apply to the parts.

| Clause | Subject | Where |
|---|---|---|
| Cl. 26.4.2.2 | cover in footings at least 50 mm, for the strap too | `effective_cover`, check `cover` |
| Cl. 34.1.2 | edge thickness of the pads | checks `edge_1`, `pad2_edge` |
| Cl. 34.2.3.2, Annex G | bending of pad 1 at the faces of the strap; the strap's hogging | checks `mulim_pad1`, `mulim_strap`, `as_*` |
| Cl. 34.2.4.1(a), Table 19 | one-way shear in pad 1 at d from the strap | check `shear_pad1` |
| Cl. 40.1, 40.2.3, Table 20, 40.4(a), 26.5.1.5, 26.5.1.6 | the strap's shear, tau_c,max at the face of column 1, stirrups, their spacing and minimum | checks `tcmax_strap`, `sv_pad`, `sv_span` |
| Cl. 26.5.1.1, 26.5.1.3 | the strap's least and most tension steel; side-face bars where deeper than 750 mm | checks `as_strap`, `asmax_strap`, step |
| Cl. 26.2.1, 26.2.2.1(b), 26.2.3.1 | development of the strap's top bars and of pad 1's bars at the stress of the section, bends; the top bars past column 2 by d or 12 phi | checks `anchor_strap`, `anchor_pad1`, `extend_strap` |
| Cl. 34.4, 34.4.3 | bearing at both columns with their whole loads; dowels | checks `bearing1`, `bearing2` |
| Section 34 (the isolated footing engine) | pad 2 | checks `pad2_*` |

### Strap footing engine: interpretations

105. **Pad 1's plan.** Pad 1 starts at the property line. The engine takes the least length along the strap, in 50 mm steps from 100 mm beyond the inner face of column 1, whose width across (the least in 50 mm steps for the bearing pressure, and at least 100 mm beyond the column and the strap each side) is no more than twice the length. Without a limit on its shape the least eccentricity always wants the shortest and widest pad; twice is a common proportion, and an entered size is kept.
106. **Statics.** The strap is rigid, so each pad bears uniformly. With e = L_1/2 - a, the reactions are R_1 = P_1 s / (s - e) (moments about column 2) and R_2 = P_1 + P_2 - R_1. A light interior column that would be pulled up (R_2 not positive) is refused. Pads that would meet are refused too, with a combined footing as the remedy. The strap is kept off the soil between the pads. Its own weight is within the sizing allowance and left out of its design, which is on the safe side for its hogging.
107. **The strap's section.**
    * Width: column 1's, at least 300 mm. Where that suits no depth, the widest pad 1 allows less 100 mm each side, in 50 mm steps, and of those the width with the least cross-section, so the section stays in proportion.
    * Depth: the least in 50 mm steps, not less than either pad, that needs no compression steel.
    * The section is the strap alone, rectangular: pad 1 as a flange is ignored, on the safe side.
    * One layer of top bars, the effective depth allowing for a 12 mm stirrup. The top bars are developed toward the property line at the stress of the section (bent down at the end where needed), and run past column 2 by d or 12 phi.
108. **The strap's shear.** Over pad 1, the design shear is taken at d from the inner face of column 1, whose load introduces compression into the strap as a support reaction would (the reasoning of Cl. 22.6.2.1). tau_c,max is checked at the face itself. Between the pads the shear is constant. Two-legged stirrups for each zone follow Cl. 40.4(a) where tau_v exceeds tau_c, the minimum of Cl. 26.5.1.6 otherwise, and Cl. 26.5.1.5, with tau_c from the top bars (in tension everywhere the strap hogs).
109. **Pad 1** is a slab cantilevering across from the faces of the strap under its uniform factored pressure, over its whole length. Its one-way shear is at d from the strap's faces; it carries the strap along its length, so punching does not apply. Its bars along are the minimum of Cl. 26.5.2.1.
110. **Pad 2** is designed by the isolated footing engine for R_2, centred under column 2 (interpretations 35 to 41). The bearing at each column takes the column's whole factored load: column 2 on pad 2 by the isolated footing's frustum, and column 1 on the strap's top with sqrt(A_1/A_2) = min(2a/D_1, b_s/b_1, 1 + 4 D_s/max(b_1, D_1), 2), not less than 1.

### Strap footing engine: to cross-check against a printed copy

* That IS 456 has no clause for strap footings (the statics and the parts' clauses are used).
* Whether the strap's critical shear may be taken at d from the column face over pad 1 (Cl. 22.6.2.1 is written for supports).

### Combined footing engine: to cross-check against a printed copy

* That IS 456 indeed has no rule for the width of the band across under a column of a combined footing (Cl. 34.3.1 covers isolated footings).
* Cl. 26.2.1: sigma_s "at the section considered" for the development length, as used for the stress at each section.
* Cl. 34.2.4.1(b) applied to a perimeter cut by the footing's edge.

## SP 16:1980, Design aids for reinforced concrete to IS 456:1978

Handbook, not a code; still the standard reference for IS 456:2000 flexure and shear aids. Used for: Table A (steel stress at strain, in both hand checks), Table E (limiting moment factors, in tests), Table F (compression steel stress, in tests), Cl. 2.3.2 (doubly reinforced sections), Cl. 4.1 (closed form behind Table 19, in tests and the hand check).

## SP 24:1983, Explanatory handbook on IS 456:1978

Used for the expressions behind Fig. 4 and Fig. 5.

## IS 2502:1963, Code of practice for bending and fixing of bars for concrete reinforcement

Used for the bar schedule conventions: outside dimensions, deduction of 2d per 90 degree bend and 3d per 135 degree bend, lengths rounded up to 5 mm; internal radii of bends and hooks 2 phi for mild steel and 4 phi for deformed bars; the standard U-hook with a 4 phi straight tail (interpretation 76). These deductions are site practice consistent with the code's bending radii; the schedule states them in its notes so a fixer can adjust to the organisation's own rule. To cross-check: the code's tabulated bend and hook allowances against these deductions.

## IS 1786:2008, High strength deformed steel bars and wires for concrete reinforcement

Used for nominal bar sizes and unit mass (7850 kg/m3).

## IS 875 (Part 1):1987, Dead loads

Used for the default unit weight of reinforced concrete, 25 kN/m3 (an input).

## IS 1200, Method of measurement of building and civil engineering works; CPWD analysis of rates (estimation, EST-001 to EST-003)

| | |
|---|---|
| Publisher | IS 1200: Bureau of Indian Standards, in parts by trade (Part 1 earthwork, Part 2 concrete work, Part 5 formwork, and so on). Analysis of rates: Central Public Works Department (Delhi Analysis of Rates, published with the Delhi Schedule of Rates); state departments publish their own schedules and analyses in the same form. |
| Status | IS 1200 parts are current in their latest revisions; the edition of each part was not checked. Schedules of rates are revised every year or two by each department. |
| Used by | estimation module (`app/modules/estimation/domain/`): measurement, rate analysis, abstract of cost |
| Not shipped | No schedule of rates and no analysis is shipped: schedules are copyright of their departments and go out of date. An organisation imports its own (CSV or Excel, format in `docs/modules/08-estimation.md`); the test and walkthrough schedules are made up and say so. |

### Estimation: interpretations

111. **Measurement.** Each line is number x length x breadth x depth, a blank dimension not entering the product, so one form serves numbers, lengths, areas and volumes. Each line's quantity is rounded to 0.01 of the item's unit, half up, and the item's quantity is the sum of its lines; a deduction is a negative line. Dimensions are taken as entered. This follows the general rules repeated in the parts of IS 1200 (dimensions to the nearest 0.01 m; areas and cubic contents worked out to the nearest 0.01 m2 and 0.01 m3), applied to every unit alike.
112. **Rate analysis**, in the CPWD form: cost = materials + labour + plant and carriage + sundries; water charges are a percentage of the cost (default 1); overheads and profit a percentage of cost plus water charges (default 15); the rate is the total divided by the quantity of the item the lines produce, rounded to 0.01 (a paisa). Each line's amount is quantity x rate rounded to 0.01. The percentages are inputs, since departments and years differ.
113. **Abstract of cost.** Each item's amount is its quantity x rate rounded to 0.01. Percentage additions (contingencies, work-charged establishment, a cost index, a tax) are each taken on the cost of the items, not compounded, each rounded to 0.01; the total is the sum, and the figure carried ("say") is the total rounded to the rupee, half up. A department that compounds an addition (a tax on cost plus contingencies, say) enters the compounded percentage.
114. **Quantities from designs.** An item may take concrete (m3), formwork (m2) or reinforcement steel (kg) from a design of the same project: the design's own take-off, as its report states it, not a re-measurement to IS 1200. The design's revision and value are recorded when the link is made or refreshed; a later revision of the design, or a change of its value, marks the item stale, and a stale estimate is not issued. Units convert by factor: m3 and m2 to themselves, kg to kg, tonne (0.001) or quintal (0.01), whatever the schedule's spelling (cum, sqm, MT, qtl); a unit that does not convert from the design's is refused. The quantity is rounded to 0.001 of the item's unit.
115. **Money** is worked in exact decimals (a rate entered as 96.75 is taken as exactly 96.75), and schedule rates, analysed rates and totals are stored in paise (integers). Amounts are not re-rounded once computed, so the workbook's live formulas (`ROUND(quantity * rate, 2)`) reproduce the PDF to the paisa.
116. **Issue.** An estimate is issued by someone other than its preparer (unless the organisation allows self-approval, as for designs); an issued estimate is not changed but revised, as R+1.

### Estimation: to cross-check against a printed copy

* The IS 1200 clause numbers of the rounding rules in each part used (Parts 1, 2 and 5 at least), and whether any part asks for a different rounding of a quantity in kg or in numbers.
* The CPWD analysis's order of percentages (water on cost; overheads and profit on cost plus water) against the current Delhi Analysis of Rates, and whether 1 and 15 percent are still its figures.

## Sources consulted for status

Column clauses (secondary sources; the code text was not read):

* Long column notes and worked examples: https://www.scribd.com/document/511953450/Long-column, https://www.scribd.com/document/794122889/Long-Column-Example
* Bentley RAM / STAAD.Pro documentation of IS 456 slenderness: https://communities.bentley.com/products/ram-staad/w/structural_analysis_and_design__wiki/22926/concrete-design-as-per-is-456-2000-code-technical-details-for-the-bracing-parameter/revision/3, https://docs.bentley.com/LiveContent/web/STAAD.Pro%20Help-v2024/en/topics/Design_Codes/Indian_Codes/c-stpst_IS456_Slenderness_Effects.html
* Transverse reinforcement rules: https://civilengineeringweb.com/?p=3349, https://www.scribd.com/document/700539417/Columns
* Biaxial bending and P_uz: https://www.scribd.com/document/130508541/m10l26, https://infralens.in/term/biaxial-bending
* Effective length: https://infralens.in/handbook/effective-length-factors (one page there labels theoretical factors as Table 28: not relied on)

Flanged beam clauses (secondary sources; the code text was not read):

* Effective width and Annex G-2: https://engineeringhulk.com/civil/rcc-design/t-beam-l-beam/, https://limitstatelessons.blogspot.com/2015/09/Effective-flange-width-of-T-beams-and-L-beams.html, https://limitstatelessons.blogspot.com/2015/09/chapter-9-cont3.html, https://rcet.org.in/uploads/academics/rohini_65680000162.pdf, https://www.scribd.com/doc/316351967/m5l10
* Fig. 6 (conflicting): https://infralens.in/handbook/slab-span-depth-ratios
* Cl. 23.1.1: https://es.scribd.com/document/236237374/FLANGED-BEAMS, https://limitstatelessons.blogspot.com/2015/10/Deflection-control-preliminary-dimensions-of-flanged-beams-T-beams.html

Continuous beam clauses (secondary sources; the code text was not read):

* Cl. 22.2(b): https://www.pcepurnia.org/wp-content/uploads/2020/03/lec14-1.pdf, https://www.scribd.com/document/439952155/lec14-pdf, https://ce-deepanshu.github.io/RCC-Design.github.io/Continous_Beam.html
* Tables 12 and 13: https://limitstatelessons.blogspot.com/2015/08/chapter-7-cont3-analysis-of-continuous.html, https://cec.nic.in/webpath/curriculum/Module/Arch/Paper16/22/downloads/faq.pdf

Slab and footing clauses (secondary sources; the code text was not read):

* Tables 26 and 27 and Annex D: https://archive.nptel.ac.in/content/storage2/courses/105105104/pdf/m8l19.pdf, https://limitstatelessons.blogspot.com/2015/04/chapter-17-cont7-coefficients-from-code.html, https://www.ktunotes.in/wp-content/uploads/2018/05/DCS-M5-Ktunotes.in_.pdf, https://engineeringhulk.com/civil/rcc-design/two-way-slab/, https://theconstructor.org/structural-engg/design-example-two-way-continuous-slab/239998/
* Tables 12 and 13: https://limitstatelessons.blogspot.com/2015/08/chapter-7-cont3-analysis-of-continuous.html, https://engineeringhulk.com/civil/rcc-design/formulas/
* Cl. 40.2.1.1 (k) and Annex D-1.8: https://cec.nic.in/webpath/curriculum/Module/Arch/Paper16/31/downloads/summary.pdf, https://engineeringhulk.com/civil/rcc-design/one-way-slab/
* Footings, Cl. 34: https://theconstructor.org/structural-engg/design-reinforced-concrete-footings/7325/, https://engineeringhulk.com/civil/rcc-design/isolated-footing/, https://www.ideastatica.com/support-center/support-center-knowledge-base/check-of-concrete-block-according-to-is

IS 456 status:

* BIS services portal, draft and amendment documents: https://services.bis.gov.in/tmp/CED19013804_03062024_1.pdf
* Listing of IS 456:2000 (R2021) and Amendment 6: https://shop.standards.ie/en-ie/standards/is-456-2000-r2021--184374_saig_bis_bis_3449967 and https://shop.standards.ie/en-ie/standards/is-456-amd-6-2024-184374_saig_bis_bis_3450013
* Report on the draft revision: https://pcci-website.pages.dev/insights/is-456-2025-revision-dam-engineers (secondary source; the BIS dashboard entry was not found)
