# Release note 0.6.0: face moments, cantilever ends, backup and restore, combined footing

The next items after 0.5.0, built one at a time. This note grows with each item.

| Item | State | Engine |
|---|---|---|
| STR-040 support moments at the faces of monolithic supports | done | continuous beam 1.6.0 |
| STR-042 cantilevers at the ends of a continuous beam | in progress | |
| PLAT-018 backup and restore | not started | |
| STR-020 combined footing | not started | |

## STR-040: support moments at the faces of monolithic supports

**Goal.** Cl. 22.6.2: in monolithic construction, the members are designed for the moments at the faces of the supports. Until 0.6.0 the elastic method took the moment at each support's centre line, which is on the safe side but heavier.

**Input.** The elastic method's new `support_moments_at` field: "Centre lines of the supports" (the default, unchanged) or "Faces of the supports (monolithic, Cl. 22.6.2)".

**Logic.**

* Each support is designed for the greater of the design envelope's hogging at its two faces.
* Cl. 37.1.1(d) compares that moment with the elastic envelope at the same face.
* The redistribution is still worked at the supports' centre lines, and the extents and cut-offs of the top bars come from the envelope as before.
* The sheet states the clause and both moments at each support, and a note reminds the designer that the beam must be cast with its supports.

**Effect** on the worked example:

| | Centre lines | Faces |
|---|---|---|
| Support 2 (design moment) | 270.9 kN m | 246.6 kN m |
| Support 3 (design moment) | 252.2 kN m | 229.3 kN m |
| Top bars over support 2 | 9-T16 (6+3) | 5-T20 |
| Top bars over support 3 | 5-T20 | 3-T25 |
| Steel | 351.1 kg | 344.3 kg |

**Validation and tests.**

* The elastic hand check works out the face moments independently (by statics from the left reaction) and checks the support sections, and Cl. 37.1.1(d), against them. A new case, monolithic supports 450 wide, brings it to 1060 values over 15 cases.
* `test_monolithic_supports_are_designed_for_the_face_moments` checks the following:
  * the face moments are below the centre-line ones;
  * the analysis is unchanged;
  * Cl. 37.1.1(b) holds at the face;
  * the steel falls;
  * the sheet and the notes cite Cl. 22.6.2.
