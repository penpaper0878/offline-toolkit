# Release note 0.7.0: column moments on combined footings, strap footings, sections per span

The next items after 0.6.0, built one at a time. This note grows with each item.

| Item | State | Engine |
|---|---|---|
| STR-045 column moments along a combined footing | done | combined footing 1.1.0 |
| STR-044 strap footing | done | strap footing 1.0.0 |
| STR-041 a support width and a section per span of a continuous beam | not started | |

## STR-045: column moments along a combined footing

A frame analysis gives each column a moment at its base. In the plane of the footing's length (the plane of the two columns) that moment now enters the design.

**Plan.** Each service moment moves the resultant by M / (P_1 + P_2): x_r = (P_2 s + M_1 + M_2) / (P_1 + P_2), clockwise positive with column 1 on the left. The plan centres on that resultant as before, so a constant moment leaves the pressure uniform. With the plan entered, the pressure varies along the footing as the moments make it.

**Design.** Each moment is factored and acts on the footing as a couple at its column, spread over the column's depth (outside the column the same as at its centre). The linear pressure balances loads and couples, so the statics still close at the far end. The bending jumps by the couple across each column. The faces and the gap are designed exactly as before.

The sheet shows the moments in the resultant and the factored couples. A flag says that the moments are one load case: moments that reverse (wind, earthquake) need a design for each sense.

**Validation.**

* The hand check takes each moment as a point couple at the column centre, against the engine's spread couple. It moves its own resultant and balances its own left end. Four new cases: a moment at column 2, moments of both signs, a moment against a property line, and moments on an entered plan. In all, 1746 values over 25 cases agree.
* Three sabotaged engines each fail it, with 9 to 29 disagreements: couples left out of the bending, couples in the wrong sense, and a plan not shifted by the moments.
* A unit test checks:
  * the shifted resultant and the centred plan;
  * the harder pressure on the side the moment pushes down;
  * the statics closing;
  * the jump in bending across a column equal to the factored couple.

**Limits.** Moments across the footing and horizontal loads (sliding, the moment of the base shear) are STR-046.

## STR-044: strap footing

A new element, `strap_footing`: the usual answer when the heavier load is at a property line, the case the combined footing refuses. Column 1 stands at the line on pad 1, which can only extend inward, so its reaction is eccentric. A strap beam ties it to column 2 on pad 2, carrying the eccentricity's moment, and both pads then bear uniformly.

**Statics.** With e = L_1/2 - a, R_1 = P_1 s / (s - e) by moments about column 2, and R_2 = P_1 + P_2 - R_1. The engine refuses two cases, each with its remedy:

* a light interior column that would be pulled up;
* pads that would meet, where a combined footing suits better.

**Plan.**

* Pad 1 is the shortest along the strap whose width for the bearing pressure is no more than twice its length (interpretation 105). Without such a limit the least eccentricity always wants the shortest, widest pad.
* Pad 2 is an isolated footing for R_2, designed by the isolated footing engine itself. Its sheet joins this one, without its bearing.

**The strap** is a rectangular beam from the property line into pad 2.

* Its hogging is greatest over pad 1, where the shear is nil. It is designed for one layer of top bars, developed toward the property line at the stress there (bent down at the end where needed), running past column 2 by d or 12 phi.
* Shear over pad 1 is taken at d from column 1's face, with tau_c,max checked at the face. Between the pads the shear is constant. Two-legged stirrups for each zone; bottom bars as hangers, or for sagging where column 1 is set back from the line; side-face bars below 750 mm depth.
* Its width is column 1's (at least 300). Where no depth suits that, it is widened to the least cross-section pad 1 allows.

**Pad 1** cantilevers across from the strap's faces, with one-way shear at d and the minimum steel along. **Bearing** takes each column's whole load: column 1 on the strap, column 2 on pad 2.

**Output.**

* Charts of the strap's bending and shear.
* A schedule of the strap's bars and stirrups, pad 1's bars and pad 2's rows.
* Quantities, with the strap's volume over and between the pads.
* A plan with the property line, a section along the strap with its stirrup zones, and a section across pad 1.

**Found and fixed while building it.** A sweep of 144 inputs found two defects, both fixed:

* The strap's top bars stopped short past column 2 where pad 2 was small, because the strap ended at pad 2's edge. The strap now runs as far as its bars need.
* A strap of column 1's width suited no depth up to 3 m under heavy loads. The first widening rule, the narrowest width that worked, gave a 350 x 2600 strap. The rule became the least cross-section, which gives 550 x 1600 for the same case.

**Validation.**

* `tests/handcheck/check_strap_footing.py` works by its own routes:
  * the reactions by moments about pad 1's centre;
  * column 1 as a point load, with the greatest hogging in closed form;
  * steel areas by bisection of the stress block, and SP 16's tau_c;
  * the stirrup spacings recomputed;
  * pad 2 by the isolated footing's own hand check.

  It agrees on 63 values of the worked example and 826 values over 14 cases, with 4 stops.
* Five sabotaged engines each fail it, with 5 to 539 disagreements:
  * the reaction by moments about the wrong point;
  * the strap's shear at the face instead of at d;
  * pad 1 cantilevering from the column, not the strap;
  * the hogging taken at the end of pad 1;
  * the minimum shear steel left out of the spacing limit.
* `tests/unit/test_strap_footing.py` covers:
  * the statics closing at column 2;
  * pad 1's proportion rule;
  * pad 2 equal to the isolated footing for R_2, and bearing for the whole load;
  * the shear zones;
  * sagging under a set-back column, and bent top bars;
  * every validation and stop;
  * the outputs;
  * the widening rule;
  * a sweep of 144 inputs, which fail only on bearing under small, heavily loaded columns (reported with the remedy) or by the two stops.
* An API life-cycle test, the browser walkthrough and the desktop smoke test design one.

**Limits.** Axial loads, one case. Rigid strap of one section with one layer of top bars. Uniform pads without shear reinforcement.

