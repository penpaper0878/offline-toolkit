# Code register

The standards the engines implement: their status, the clauses taken, every place where the text was interpreted, and what still has to be cross-checked against a printed copy. An engine is not released until its codes are entered here.

Status last checked: 16 November 2026.

## IS 456:2000, Plain and reinforced concrete: code of practice (fourth revision)

| | |
|---|---|
| Publisher | Bureau of Indian Standards, CED 2 |
| Status | Current. Reaffirmed 2021. |
| Amendments | Nos. 1 to 6. Amendment No. 6 is dated April 2024 (published August 2024); the excerpt consulted changes Cl. 5.1 (cement references, including composite cement to IS 16415) and deletes Cl. 17.5 in favour of a load test under Cl. 17.6. None of the clauses listed below is touched by that excerpt. |
| Revision | A fifth revision ("Structural concrete") has been in draft; secondary sources report it was circulated for comment in 2025 and was still being processed in early 2026. IS 456:2000 remains the enforceable standard. Review this entry when the revision is published. |
| Used by | beam engine 1.0.0 |

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

## SP 16:1980, Design aids for reinforced concrete to IS 456:1978

Handbook, not a code; still the standard reference for IS 456:2000 flexure and shear aids. Used for: Table A (steel stress at strain, in the hand check), Table E (limiting moment factors, in tests), Table F (compression steel stress, in tests), Cl. 2.3.2 (doubly reinforced sections), Cl. 4.1 (closed form behind Table 19, in tests and the hand check).

## SP 24:1983, Explanatory handbook on IS 456:1978

Used for the expressions behind Fig. 4 and Fig. 5.

## IS 2502:1963, Code of practice for bending and fixing of bars for concrete reinforcement

Used for the bar schedule conventions: outside dimensions, deduction of 2d per 90 degree bend and 3d per 135 degree bend, lengths rounded up to 5 mm. These deductions are site practice consistent with the code's bending radii; the schedule states them in its notes so a fixer can adjust to the organisation's own rule. To cross-check: the code's tabulated bend and hook allowances against these deductions.

## IS 1786:2008, High strength deformed steel bars and wires for concrete reinforcement

Used for nominal bar sizes and unit mass (7850 kg/m3).

## IS 875 (Part 1):1987, Dead loads

Used for the default unit weight of reinforced concrete, 25 kN/m3 (an input).

## Sources consulted for status

* BIS services portal, draft and amendment documents: https://services.bis.gov.in/tmp/CED19013804_03062024_1.pdf
* Listing of IS 456:2000 (R2021) and Amendment 6: https://shop.standards.ie/en-ie/standards/is-456-2000-r2021--184374_saig_bis_bis_3449967 and https://shop.standards.ie/en-ie/standards/is-456-amd-6-2024-184374_saig_bis_bis_3450013
* Report on the draft revision: https://pcci-website.pages.dev/insights/is-456-2025-revision-dam-engineers (secondary source; the BIS dashboard entry was not found)
