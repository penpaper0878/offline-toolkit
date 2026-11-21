# Module note: quantity estimation (EST-001 to EST-004)

Built 21 November 2026, for 0.8.0. The first module of phase 2 beyond the platform: an estimate priced from the organisation's schedules of rates and rate analyses, with quantities measured or taken from the project's designs, worked out by the server, issued by a second person and carried with the project. The measurement book (EST-004) records the work done against an issued estimate; bills (EST-005) follow.

| Item | State |
|---|---|
| EST-001 schedules of rates: import from CSV or Excel, search | done |
| EST-002 rate analysis in the CPWD form | done |
| EST-003 estimates: items, measurements, quantities from designs, additions, abstract, issue, revisions, Excel and PDF, project archives | done |
| EST-004 measurement book: entries checked by a second person, progress per item, PDF, project archives | done |

The rules are interpretations 111 to 118 in [CODE_REGISTER.md](../CODE_REGISTER.md); the decision is D38 in [PROJECT_MEMORY.md](../PROJECT_MEMORY.md).

## Schedules of rates (EST-001)

No schedule is shipped: schedules are the departments' copyright and change every year or two. An organisation imports its own on the **Quantity estimation** page (permission `rates:manage`: engineers, administrators, owners), from a CSV file or the first sheet of an Excel workbook:

```
Code,Description,Unit,Rate
,Chapter 5: Concrete work,,
5.1,"Providing and laying in position cement concrete of specified grade, excluding centering and shuttering",,
5.1.2,M20 grade,cum,"7,240.00"
5.22,"Steel reinforcement for R.C.C. work including straightening, cutting, bending, placing in position and binding",kg,96.75
```

* A header row in the first 15 rows names the columns code, description, unit and rate (common spellings such as "Item No.", "Particulars", "Rate (Rs)" are recognised); a chapter column is optional. Rows above the header (a title) are ignored.
* A row with a code and a description but no unit or rate is a heading. It is put before the items whose codes start with its code and a dot (the longest such heading), so 5.1.2 reads "Providing and laying ... : M20 grade".
* A row with only a description starts a chapter.
* Rates may carry "Rs", "₹" and thousands separators. A row without a code, description, unit or a numeric rate, or with a repeated code, is skipped and reported by its row number; the rest import.
* Keep item codes as text in Excel, so that 5.10 stays 5.10.

The import stores the rates in paise. A schedule is searched by code and words (every word must match the code, description or chapter). Deleting a schedule leaves the estimates priced from it as they are: an item keeps its rate, the schedule's title and the item code.

## Rate analysis (EST-002)

For an item not in the schedule, or to check one. The lines are materials, labour, plant and carriage, and sundries, each quantity x rate (rounded to the paisa). Cost is their sum; water charges are a percentage of the cost (1 by default); overheads and profit a percentage of cost plus water charges (15 by default); the rate is the total over the output quantity (the quantity of the item the lines produce), rounded to the paisa. The server works the rate out as the lines are typed (`POST /rate-analyses/calculate`), so the screen and the saved rate cannot differ.

Worked example (the hand check): cost 7702.42, water charges 77.02, overheads and profit 1166.92, total 8946.36 for an output of 1, rate 8946.36.

## Estimates (EST-003)

An estimate belongs to a project. **New estimate** on the project's page or on the Quantity estimation page opens the editor.

**Items** come from a schedule (searched in a picker; several can be added in a row), from a rate analysis, as a quantity from a design, or blank. Each has a number (automatic unless entered), a description, a unit, a rate, and its quantity from one of three sources:

* **Measured**: lines of description, number, length, breadth and depth; a blank dimension is not measured; each line is rounded to 0.01 and the item is their sum; a deduction is a negative line (interpretation 111).
* **From a design**: concrete (m3), formwork (m2) or reinforcement steel (kg) of a design of the project, converted to the item's unit where it differs (kg to tonne or quintal). The design's revision and value are recorded when the link is made. A later revision of the design marks the item stale: the estimate keeps the recorded quantity, shows the design's new figure, and is not issued until **Take the current quantities** is chosen (interpretation 114). The client cannot alter a recorded value: an unchanged link keeps what the server recorded, whatever is sent.
* **Entered**: a quantity typed in.

Editing a schedule item's rate makes it an entered rate (the code is kept). **Additions** are percentages of the cost of the items: contingencies, work-charged establishment, a cost index, a tax (interpretation 113). The abstract is the cost of the items, each addition, the total and the figure carried, rounded to the rupee.

Every figure on screen comes from the server: as the estimate is edited the client sends the document to `POST /estimates/{id}/preview`, which works it out without saving (D38). Ctrl S saves.

**Issue** (permission `estimate:issue`: reviewers, administrators, owners) needs a saved estimate with items and no stale quantities, and someone other than the preparer (unless `CLP_ALLOW_SELF_APPROVAL`). An issued estimate is not changed or deleted; **Revise** reopens it as the next R number.

**Outputs.** Excel: an abstract with live formulas (`ROUND(quantity * rate, 2)`, the sub-total, each addition, the total, `ROUND(total, 0)`) and the details of measurement; the formulas give the same figures as the PDF. PDF: the shared title block (estimate, preparer, issuer, revision), the abstract, then the details of measurement with each design-linked quantity's source and revision.

**Projects travel with their estimates.** The project archive is format version 2: each design carries its reference and each estimate its document; on import the links are remapped to the imported designs and a link to a design the file does not hold is refused. Version 1 files still import. Schedules and analyses belong to the organisation and do not travel; an estimate keeps its rates.

## Measurement book (EST-004)

Once an estimate is issued, **Measurement book** on its page opens the book: work done is recorded against the items of the estimate's current revision, entry by entry (**Record a measurement**: the item, the date, the location, and the lines, measured as in the estimate, their quantities worked out by the server as they are typed).

* Entries are numbered in order. A recorded entry can be corrected or deleted; once **checked** (permission `estimate:issue`, by someone other than the one who measured it) it is kept as it is, and an error is put right by a further entry, which may be a deduction.
* Progress per item: estimated, measured to date, checked to date, balance, percentage done, and the excess beyond the estimated quantity, each valued at the estimate's rate (interpretation 117). The excess is shown, not judged: deviation limits are the department's.
* A revision of the estimate keeps the book. An item taken out of the current revision keeps its entries, shown apart (interpretation 118). An estimate with entries is not deleted.
* PDF: the progress table, then every entry with its lines, who measured it and who checked it.
* The book travels with its estimate in the project archive.

Worked example (the walkthrough): 2 x 1.8 x 1.8 x 0.45 = 2.916, entered as 2.92 cum of 5.83 estimated; 50.1 percent; balance 2.91; valued at 7240 = 21,140.80.

## API

| Route | Permission |
|---|---|
| `GET /sor-books`, `GET /sor-books/{id}/items?q=` | estimate:read |
| `POST /sor-books/import`, `DELETE /sor-books/{id}` | rates:manage |
| `GET /rate-analyses`, `GET /rate-analyses/{id}`, `POST /rate-analyses/calculate` | estimate:read |
| `POST /rate-analyses`, `PUT` and `DELETE /rate-analyses/{id}` | rates:manage |
| `GET /estimates`, `GET /projects/{id}/estimates`, `GET /projects/{id}/design-quantities`, `GET /estimates/{id}`, `POST /estimates/{id}/preview`, `GET /estimates/{id}/estimate.xlsx`, `GET /estimates/{id}/estimate.pdf` | estimate:read |
| `POST /projects/{id}/estimates`, `PUT /estimates/{id}`, `POST /estimates/{id}/refresh`, `POST /estimates/{id}/revise`, `DELETE /estimates/{id}` (drafts) | estimate:write |
| `POST /estimates/{id}/issue` | estimate:issue |
| `GET /estimates/{id}/measurement-book`, `GET /estimates/{id}/measurement-book.pdf`, `POST /measurement-book/calculate` | estimate:read |
| `POST /estimates/{id}/measurement-book`, `PUT` and `DELETE /mb-entries/{id}` (recorded entries) | estimate:write |
| `POST /mb-entries/{id}/check` | estimate:issue |

Every service filters by organisation; another tenant's schedule, analysis or estimate is "not found", and a design of another project cannot be linked.

## Code

* `backend/app/modules/estimation/domain/`: `money.py` (exact decimals, half-up rounding), `measure.py`, `rates.py` (the analysis), `abstract.py` (amounts, additions, design quantities and unit factors), `progress.py` (the measurement book against the estimate). Pure: no framework imports.
* `models.py`, migrations `0002_quantity_estimation.py` (`sor_books`, `sor_items`, `rate_analyses`, `estimates`) and `0003_measurement_book.py` (`mb_entries`); see DATABASE_SCHEMA.md.
* `service.py` (import parser, links, compute, issue), `exports.py`, `router.py`.
* Client: `pages/EstimationPage.tsx` (estimates, schedules, analyses), `pages/EstimatePage.tsx` (the editor), `components/Estimation.tsx` (schedule picker, import dialog, rate analysis dialog), `components/EstimateCommon.tsx`, `pages/MeasurementBookPage.tsx`; the Estimates card on the project page. Alt 4 opens the module.

## Validation

* Hand check `tests/handcheck/check_estimate.py`: 1185 values. Measurement lines, analyses, abstracts and progress worked in exact fractions with a half-up rounding of its own, against the engine's decimals: 60 random analyses, 200 random measurement lines, 40 random abstracts, 60 random items' progress, the worked analysis above, a worked measurement with a deduction (8.12 + 0.65 - 0.23 = 8.54) and a worked excess (14.97 of 10 cum: 4.97 x 6544.15 = 32,524.43, 149.7 percent). Two sabotaged progress engines (an excess not valued, a balance below zero) each fail it.
* Unit tests of the domain; API tests: import from CSV and Excel with skipped rows reported, analyses, the whole estimate flow (preview, stale design, refresh, four-eyes issue, revise, exports), tampered design links, tenant isolation, roles; project archives with estimates and design links remapped. Run on SQLite and PostgreSQL 16.
* The browser walkthrough imports a schedule, writes a rate analysis and an estimate with a measured item and a design quantity, saves it, downloads the Excel and PDF; adds a reviewer, who issues it in a second session; records a measurement, which the reviewer checks; downloads the measurement book; and exports the project with the estimate and its book. The figures on screen agree with a hand calculation (5.83 cum x 7240 = 42,209.20; 527.9 kg x 96.75 = 51,074.33; 3 percent of 93,283.53 = 2,798.51; say Rs 96,082).

## Not yet

EST-005 running and final bills, EST-006 analyses priced from a schedule's basic rates, EST-007 more quantities from designs (excavation, levelling course), EST-008 comparing revisions (the documents of earlier revisions are not yet kept).
