# Release note 0.6.0: face moments, cantilever ends, backup and restore, combined footing

The next items after 0.5.0, built one at a time. This note grows with each item.

| Item | State | Engine |
|---|---|---|
| STR-040 support moments at the faces of monolithic supports | done | continuous beam 1.6.0 |
| STR-042 cantilevers at the ends of a continuous beam | done | continuous beam 1.6.0 |
| PLAT-018 backup and restore | done | platform |
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

## STR-042: cantilevers at the ends of a continuous beam

**Goal.** Balcony and canopy beams: a continuous beam that overhangs one or both of its end supports. This is part of the elastic method; the coefficients of Table 12 have no cantilever.

**Inputs.** For each end: the clear projection (0 for none, else at least 300 mm), dead and imposed uniform load, and a dead load at the tip (a parapet or wall).

**Logic.**

| Step | Rule | Reference |
|---|---|---|
| Length | to the centre of the support, the end of a continuous beam | Cl. 22.2(c) |
| Analysis | the cantilever's moment, (w_d + w_l) l^2/2 + P l, is a known end moment in the three-moment equation; each cantilever loaded and unloaded in every arrangement | Cl. 22.4.1 |
| Redistribution | none at a cantilever's support: its moment is statically determinate | Cl. 37.1.1 |
| Support | designed like an interior support; top bars run to the tip and bend down, and must develop L_d beyond the face (the selection passes over bars that would not) | Cl. 26.2.1, 26.2.2.1(b) |
| Cantilever | shear at d from the face with one stirrup spacing; deflection by the basic ratio 7 with k_t of the top bars | Cl. 22.6.2.1, 40.4, 23.2.1 |
| End span | its bottom bars meet no simple support next to a cantilever: anchored at the point of inflection instead | Cl. 26.2.3.3(c) |
| Uplift | a support whose reaction turns downward in any arrangement is flagged | |

**Found and fixed while building it.** With a left cantilever, span 1 sags less, so its bottom bars shrank. Support 2 then lacked the compression steel it needed, and the default beam stopped. The engine now gives a support more compression steel first, raising the bottom bars of the lighter span beside it. Only where no heavier bars help does it redistribute less. As a result, the 30 percent case of the worked example now keeps 30 percent at both supports (span 3's bottom bars rise to 6-T12) instead of taking 25 percent at support 3.

**Output.** Each cantilever gets:

* its own elevation, with the top bars bent down at the tip, the bottom bars and the stirrups;
* rows in the schedule: the top bars over the support and the cantilever (an L-bend at the tip), its bottom bars and its stirrups;
* its length in the quantities;
* its stretch in the envelope charts, x then measured from the left tip.

**Validation.** The elastic hand check now carries cantilevers:

* Hardy Cross with the cantilever's moment held at the end joint and half the change carried over;
* the arrangements with each cantilever loaded and unloaded;
* the cantilever's own face moment where the supports are monolithic.

On each cantilever it checks the length available to develop the top bars, the stirrup spacing the shear asks for, and the span/depth allowance. Two new cases (a cantilever at each end; a 2.5 m left cantilever with monolithic supports) bring it to 1223 values over 17 cases. With the cantilever's length shortened to its clear projection, it reports 47 disagreements.

**Tests.** `tests/unit/test_continuous_elastic.py`:

* the kernel with a known end moment;
* a cantilever at each end: lengths, moments, no redistribution at its support, its checks, no end details, schedule shapes, views, quantities, charts;
* a short cantilever taking smaller bars;
* compression steel raising a span's bars;
* input limits;
* redistribution kept by raising the compression steel, and stepped down where no heavier bars can help.

## PLAT-018: backup and restore, and moving projects

Three ways to keep or carry data, one for each need. The procedures are in `docs/OPERATIONS.md`.

| Need | How | Who |
|---|---|---|
| Carry one project to another installation or organisation | **Export project** saves a `.clp.json` archive; **Import project** makes a new project from it | export: anyone who reads designs; import: who may write projects and designs |
| Keep a copy of a desktop or small-server installation | **Download a backup** on Data and backup: a consistent copy of the SQLite file (`VACUUM INTO`), the server still running | the owner (`org:manage`), and only where the database holds that organisation alone |
| Go back to a backup on the desktop | File, **Restore from backup**: stop the server, keep the current file, put the backup in place, start (and migrate) | the person at the computer |

**The archive.** Format `civillabpro.project`, version 1: the app version and the organisation and person who exported it; the project's fields; and for each design its inputs, its full result, its engine version, its review state with the designer's and approver's names, and every earlier revision.

**Import.** The import makes a new project and keeps everything as it was calculated (D35). Nothing is recalculated, because a newer engine could change the numbers of an issued calculation. Revising a design afterwards recalculates it as usual and withdraws an approval as usual.

It also:

* gives the project a free job number (`-2`, `-3`, and so on) and says so;
* keeps people's names as text, linking no user accounts across organisations;
* refuses an element type this installation lacks, and a design whose result disagrees with its own record (status or engine version);
* writes the source to the audit trail.

The archive is not signed. A consistency check catches damage and careless edits, not a deliberate forgery: a calculation that arrives from outside is checked like any other.

**Backup.** The backup is refused on PostgreSQL (use `pg_dump`) and where other organisations share the database, so that an owner never downloads another tenant's rows. Each backup is in the audit trail.

**Restore on the desktop.** The shell stops its server and checks that the chosen file is an SQLite database. It moves the current database and its `-wal` and `-shm` files aside as `civillabpro.before-restore-<stamp>.db`, copies the backup in, and starts the server, which migrates an older backup. If the server does not come up, it puts the previous files back, starts again, and says what failed. The kept file restores the same way.

**Validation.**

* `tests/api/test_transfer.py`:
  * a project with a reviewed and revised design exported from one organisation and imported into another: inputs, results, revisions, approval record, audit;
  * a second import taking `-2`;
  * refusals of an unknown element, an altered result and a cross-tenant export;
  * the backup opened as a database, refused to a non-owner, and refused where two organisations share it.
* `desktop/test/launcher.test.js`: the file check, the swap with its kept files, and undo.
* The desktop smoke test, on each packaged app in CI, follows the whole cycle: back up, add a project, restore, then check the project is gone and the six designs are back.
* The browser walkthrough exports the project, imports it as `-2` with its six designs, and downloads a backup whose header it checks.

