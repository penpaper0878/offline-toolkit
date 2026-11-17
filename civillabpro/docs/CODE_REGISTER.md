# Code register

The standards the engines implement: their status, the clauses taken, every place where the text was interpreted, and what still has to be cross-checked against a printed copy. An engine is not released until its codes are entered here.

Status last checked: 16 November 2026. Column clauses added 17 November 2026.

## IS 456:2000, Plain and reinforced concrete: code of practice (fourth revision)

| | |
|---|---|
| Publisher | Bureau of Indian Standards, CED 2 |
| Status | Current. Reaffirmed 2021. |
| Amendments | Nos. 1 to 6. Amendment No. 6 is dated April 2024 (published August 2024); the excerpt consulted changes Cl. 5.1 (cement references, including composite cement to IS 16415) and deletes Cl. 17.5 in favour of a load test under Cl. 17.6. None of the clauses listed below is touched by that excerpt. |
| Revision | A fifth revision ("Structural concrete") has been in draft; secondary sources report it was circulated for comment in 2025 and was still being processed in early 2026. IS 456:2000 remains the enforceable standard. Review this entry when the revision is published. |
| Used by | beam engine 1.0.0, column engine 1.0.0 |

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

## SP 16:1980, Design aids for reinforced concrete to IS 456:1978

Handbook, not a code; still the standard reference for IS 456:2000 flexure and shear aids. Used for: Table A (steel stress at strain, in both hand checks), Table E (limiting moment factors, in tests), Table F (compression steel stress, in tests), Cl. 2.3.2 (doubly reinforced sections), Cl. 4.1 (closed form behind Table 19, in tests and the hand check).

## SP 24:1983, Explanatory handbook on IS 456:1978

Used for the expressions behind Fig. 4 and Fig. 5.

## IS 2502:1963, Code of practice for bending and fixing of bars for concrete reinforcement

Used for the bar schedule conventions: outside dimensions, deduction of 2d per 90 degree bend and 3d per 135 degree bend, lengths rounded up to 5 mm. These deductions are site practice consistent with the code's bending radii; the schedule states them in its notes so a fixer can adjust to the organisation's own rule. To cross-check: the code's tabulated bend and hook allowances against these deductions.

## IS 1786:2008, High strength deformed steel bars and wires for concrete reinforcement

Used for nominal bar sizes and unit mass (7850 kg/m3).

## IS 875 (Part 1):1987, Dead loads

Used for the default unit weight of reinforced concrete, 25 kN/m3 (an input).

## Sources consulted for status

Column clauses (secondary sources; the code text was not read):

* Long column notes and worked examples: https://www.scribd.com/document/511953450/Long-column, https://www.scribd.com/document/794122889/Long-Column-Example
* Bentley RAM / STAAD.Pro documentation of IS 456 slenderness: https://communities.bentley.com/products/ram-staad/w/structural_analysis_and_design__wiki/22926/concrete-design-as-per-is-456-2000-code-technical-details-for-the-bracing-parameter/revision/3, https://docs.bentley.com/LiveContent/web/STAAD.Pro%20Help-v2024/en/topics/Design_Codes/Indian_Codes/c-stpst_IS456_Slenderness_Effects.html
* Transverse reinforcement rules: https://civilengineeringweb.com/?p=3349, https://www.scribd.com/document/700539417/Columns
* Biaxial bending and P_uz: https://www.scribd.com/document/130508541/m10l26, https://infralens.in/term/biaxial-bending
* Effective length: https://infralens.in/handbook/effective-length-factors (one page there labels theoretical factors as Table 28: not relied on)

IS 456 status:

* BIS services portal, draft and amendment documents: https://services.bis.gov.in/tmp/CED19013804_03062024_1.pdf
* Listing of IS 456:2000 (R2021) and Amendment 6: https://shop.standards.ie/en-ie/standards/is-456-2000-r2021--184374_saig_bis_bis_3449967 and https://shop.standards.ie/en-ie/standards/is-456-amd-6-2024-184374_saig_bis_bis_3450013
* Report on the draft revision: https://pcci-website.pages.dev/insights/is-456-2025-revision-dam-engineers (secondary source; the BIS dashboard entry was not found)
