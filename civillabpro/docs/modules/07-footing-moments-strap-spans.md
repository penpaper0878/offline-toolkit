# Release note 0.7.0: column moments on combined footings, strap footings, sections per span

The next items after 0.6.0, built one at a time. This note grows with each item.

| Item | State | Engine |
|---|---|---|
| STR-045 column moments along a combined footing | done | combined footing 1.1.0 |
| STR-044 strap footing | not started | |
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
