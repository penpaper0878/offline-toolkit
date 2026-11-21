"""Quantity estimation: schedules of rates, rate analyses and estimates, for the caller's organisation only."""

from __future__ import annotations

import base64
import binascii
import csv
import io
import re
import uuid
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import utcnow
from app.core.errors import Conflict, Invalid, NotFound
from app.modules.estimation.domain.abstract import DESIGN_QUANTITIES, Addition, abstract, amount, unit_factor
from app.modules.estimation.domain.measure import MeasureLine, item_quantity, line_quantity
from app.modules.estimation.domain.money import dec
from app.modules.estimation.domain.progress import item_progress
from app.modules.estimation.domain.rates import AnalysisLine, analyse
from app.modules.estimation.models import Estimate, MbEntry, RateAnalysis, SorBook, SorItem
from app.modules.estimation.schemas import EstimateDoc, EstimateSave, MbEntryIn, Measurement, RateAnalysisIn, SorBookImport
from app.modules.identity.models import User
from app.modules.identity.service import audit
from app.modules.projects.service import get_project
from app.modules.structural import service as structural
from app.modules.structural.domain.registry import element_title

MAX_SOR_ITEMS = 50_000
THREE = Decimal("0.001")


def paise(rupees: Decimal) -> int:
    return int((rupees * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def rupees(p: int) -> float:
    return p / 100.0


# ----------------------------------------------------------------------------- schedules of rates

_HEADERS = {
    "code": {"code", "item code", "item no", "item number", "itemno", "sr no", "s no", "sl no", "serial no", "no"},
    "description": {"description", "description of item", "item description", "particulars", "description of work", "item"},
    "unit": {"unit", "units", "uom", "unit of measurement"},
    "rate": {"rate", "rate rs", "rate in rs", "rate inr", "rate rupees", "rate in rupees", "rate per unit"},
    "chapter": {"chapter", "section", "sub head", "subhead", "head", "chapter name"},
}


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(text or "").lower())).strip()


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _rows(data: SorBookImport) -> list[list[str]]:
    name = data.filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl

        if not data.content_base64:
            raise Invalid("An Excel file is sent as base64.")
        try:
            raw = base64.b64decode(data.content_base64, validate=True)
            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        except (binascii.Error, ValueError, OSError, KeyError) as e:
            raise Invalid(f"The file could not be read as an Excel workbook: {e}") from e
        ws = wb.worksheets[0]
        return [[_cell(v) for v in row] for row in ws.iter_rows(values_only=True)]
    if name.endswith((".csv", ".txt")):
        if data.content is None:
            raise Invalid("A CSV file is sent as text.")
        return [[c.strip() for c in row] for row in csv.reader(io.StringIO(data.content))]
    raise Invalid("Import a CSV file or an Excel workbook (.xlsx).")


def parse_sor(rows: list[list[str]]) -> tuple[list[dict[str, Any]], int, list[str]]:
    """The items of a schedule from its rows: a header row naming the columns (code, description, unit, rate; chapter optional), then
    items. A row with a code and a description but no unit or rate is a heading, prefixed to the items whose codes start with its code
    and a dot; a row with only a description starts a chapter. Returns the items, the number of headings and the rows skipped."""
    head_i, cols = None, {}
    for i, row in enumerate(rows[:15]):
        found = {}
        for j, c in enumerate(row):
            n = _norm(c)
            for key, names in _HEADERS.items():
                if n in names and key not in found:
                    found[key] = j
        if {"code", "description", "unit", "rate"} <= set(found):
            head_i, cols = i, found
            break
    if head_i is None:
        raise Invalid("No header row naming the columns code, description, unit and rate was found in the first 15 rows.")
    items: list[dict[str, Any]] = []
    headings: dict[str, str] = {}
    chapter = ""
    skipped: list[str] = []
    seen: set[str] = set()

    def get(row: list[str], key: str) -> str:
        j = cols.get(key)
        return row[j].strip() if j is not None and j < len(row) else ""

    for i, row in enumerate(rows[head_i + 1:], start=head_i + 2):
        code, desc, unit, rate_s = get(row, "code"), get(row, "description"), get(row, "unit"), get(row, "rate")
        chapter = get(row, "chapter") or chapter
        if not (code or desc or unit or rate_s):
            continue
        if not code and desc and not unit and not rate_s:
            chapter = desc[:200]
            continue
        if code and desc and not unit and not rate_s:
            headings[code] = desc
            continue
        reason = ("no code" if not code else "no description" if not desc else "no unit" if not unit else "no rate" if not rate_s else "")
        if reason:
            skipped.append(f"row {i}: {reason}")
            continue
        try:
            rate = Decimal(re.sub(r"(?i)rs\.?|inr|₹|,|\s", "", rate_s))
            if rate < 0 or not rate.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            skipped.append(f"row {i}: the rate {rate_s!r} is not a number")
            continue
        if code in seen:
            skipped.append(f"row {i}: code {code} repeated")
            continue
        seen.add(code)
        parent = max((h for h in headings if code.startswith(h + ".")), key=len, default=None)
        full = f"{headings[parent]}: {desc}" if parent else desc
        items.append({"item_code": code[:40], "chapter": chapter[:200], "description": full, "unit": unit[:20], "rate_paise": paise(rate),
                      "seq": len(items)})
        if len(items) > MAX_SOR_ITEMS:
            raise Invalid(f"A schedule may hold at most {MAX_SOR_ITEMS} items.")
    if not items:
        raise Invalid("No items were found below the header row" + (f" ({len(skipped)} rows skipped: {'; '.join(skipped[:3])})" if skipped else "") + ".")
    return items, len(headings), skipped


def import_sor(db: Session, actor: User, data: SorBookImport) -> tuple[SorBook, int, int, list[str]]:
    title = data.title.strip()
    if db.scalar(select(SorBook.id).where(SorBook.org_id == actor.org_id, func.lower(SorBook.title) == title.lower())):
        raise Conflict(f"A schedule called {title} is already imported: give this one another title, or delete that one first.")
    items, headings, skipped = parse_sor(_rows(data))
    book = SorBook(org_id=actor.org_id, title=title, authority=data.authority.strip(), state=data.state.strip(), year=data.year,
                   source_name=data.filename[:200], created_by=actor.id)
    db.add(book)
    db.flush()
    db.add_all(SorItem(book_id=book.id, **it) for it in items)
    db.flush()
    audit(db, actor, "sor_book.imported", "sor_book", book.id, f"Schedule of rates {title} imported with {len(items)} items",
          {"file": data.filename, "skipped": len(skipped)})
    return book, len(items), headings, skipped


def get_book(db: Session, org_id: uuid.UUID, book_id: uuid.UUID) -> SorBook:
    book = db.get(SorBook, book_id)
    if book is None or book.org_id != org_id:
        raise NotFound("Schedule of rates not found.")
    return book


def list_books(db: Session, org_id: uuid.UUID) -> list[tuple[SorBook, int]]:
    counts = dict(db.execute(select(SorItem.book_id, func.count()).join(SorBook, SorBook.id == SorItem.book_id)
                             .where(SorBook.org_id == org_id).group_by(SorItem.book_id)).all())
    books = db.scalars(select(SorBook).where(SorBook.org_id == org_id).order_by(SorBook.title))
    return [(b, counts.get(b.id, 0)) for b in books]


def search_items(db: Session, org_id: uuid.UUID, book_id: uuid.UUID, q: str, limit: int, offset: int) -> tuple[list[SorItem], int]:
    get_book(db, org_id, book_id)
    stmt = select(SorItem).where(SorItem.book_id == book_id)
    for word in q.lower().split()[:6]:
        like = f"%{word}%"
        stmt = stmt.where(or_(func.lower(SorItem.item_code).like(like), func.lower(SorItem.description).like(like), func.lower(SorItem.chapter).like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    return list(db.scalars(stmt.order_by(SorItem.seq).limit(limit).offset(offset))), total


def delete_book(db: Session, actor: User, book_id: uuid.UUID) -> None:
    book = get_book(db, actor.org_id, book_id)
    audit(db, actor, "sor_book.deleted", "sor_book", book.id, f"Schedule of rates {book.title} deleted")
    db.delete(book)


# ----------------------------------------------------------------------------- rate analyses


def analysis_result(doc: dict[str, Any]) -> dict[str, Any]:
    lines = [AnalysisLine(ln["kind"], ln["description"], ln.get("unit", ""), ln["quantity"], ln["rate"]) for ln in doc.get("lines", [])]
    a = analyse(lines, doc["output_qty"], doc["water_pct"], doc["overheads_profit_pct"])
    return {**{k: float(v) for k, v in a.by_kind.items()}, "cost": float(a.cost), "water": float(a.water),
            "overheads_profit": float(a.overheads_profit), "total": float(a.total), "rate": float(a.rate), "lines": [float(x) for x in a.lines]}


def get_analysis(db: Session, org_id: uuid.UUID, analysis_id: uuid.UUID) -> RateAnalysis:
    a = db.get(RateAnalysis, analysis_id)
    if a is None or a.org_id != org_id:
        raise NotFound("Rate analysis not found.")
    return a


def list_analyses(db: Session, org_id: uuid.UUID) -> list[RateAnalysis]:
    return list(db.scalars(select(RateAnalysis).where(RateAnalysis.org_id == org_id).order_by(RateAnalysis.title)))


def save_analysis(db: Session, actor: User, data: RateAnalysisIn, analysis_id: uuid.UUID | None = None) -> RateAnalysis:
    doc = data.model_dump(exclude={"title", "unit"})
    res = analysis_result(doc)
    if analysis_id is None:
        a = RateAnalysis(org_id=actor.org_id, title=data.title.strip(), unit=data.unit.strip(), doc=doc, created_by=actor.id)
        db.add(a)
        db.flush()
    else:
        a = get_analysis(db, actor.org_id, analysis_id)
        a.title, a.unit, a.doc = data.title.strip(), data.unit.strip(), doc
    a.rate_paise = paise(Decimal(str(res["rate"])))
    audit(db, actor, "rate_analysis.saved", "rate_analysis", a.id, f"Rate analysis {a.title}: {res['rate']:.2f} per {a.unit}")
    return a


def delete_analysis(db: Session, actor: User, analysis_id: uuid.UUID) -> None:
    a = get_analysis(db, actor.org_id, analysis_id)
    audit(db, actor, "rate_analysis.deleted", "rate_analysis", a.id, f"Rate analysis {a.title} deleted")
    db.delete(a)


# ----------------------------------------------------------------------------- estimates


def get_estimate(db: Session, org_id: uuid.UUID, estimate_id: uuid.UUID) -> Estimate:
    e = db.get(Estimate, estimate_id)
    if e is None or e.org_id != org_id:
        raise NotFound("Estimate not found.")
    return e


def list_estimates(db: Session, org_id: uuid.UUID, project_id: uuid.UUID | None = None) -> list[Estimate]:
    stmt = select(Estimate).where(Estimate.org_id == org_id)
    if project_id is not None:
        get_project(db, org_id, project_id)
        stmt = stmt.where(Estimate.project_id == project_id)
    return list(db.scalars(stmt.order_by(Estimate.updated_at.desc())))


def create_estimate(db: Session, actor: User, project_id: uuid.UUID, title: str) -> Estimate:
    project = get_project(db, actor.org_id, project_id)
    e = Estimate(org_id=actor.org_id, project_id=project.id, title=title.strip(), doc=EstimateDoc().model_dump(mode="json"), created_by=actor.id,
                 prepared_by_name=actor.full_name)
    db.add(e)
    db.flush()
    audit(db, actor, "estimate.created", "estimate", e.id, f"Estimate {e.title} created in {project.code}")
    return e


def design_quantities(db: Session, org_id: uuid.UUID, project_id: uuid.UUID) -> list[dict[str, Any]]:
    """The quantities each design of the project reports, through the structural service."""
    out = []
    for d in structural.list_designs(db, org_id, project_id):
        q = (d.result or {}).get("quantities") or {}
        vals = {k: float(q[k]) for k in DESIGN_QUANTITIES if isinstance(q.get(k), int | float)}
        if vals:
            out.append({"design_id": d.id, "name": d.name, "element_type": d.element_type, "title": element_title(d.element_type),
                        "revision": d.revision, "status": d.status, "quantities": vals})
    return out


def _design_now(db: Session, org_id: uuid.UUID, project_id: uuid.UUID, design_id: uuid.UUID, key: str) -> tuple[int, float, str] | None:
    try:
        d = structural.get_design(db, org_id, design_id)
    except NotFound:
        return None
    q = (d.result or {}).get("quantities") or {}
    if d.project_id != project_id or not isinstance(q.get(key), int | float):
        return None
    return d.revision, float(q[key]), f"{element_title(d.element_type)} {d.name}"


def _check_links(db: Session, e: Estimate, doc: EstimateDoc, refresh: bool, old: dict[str, Any] | None) -> EstimateDoc:
    """Every design link points at a design of this project with that quantity, in a unit the item can take; a new or changed link,
    or every link when refreshing, takes the design's current revision and value."""
    before = {it["id"]: it.get("design") for it in (old or {}).get("items", [])}
    for it in doc.items:
        if it.quantity_mode != "design":
            continue
        if it.design is None:
            raise Invalid(f"Item {it.item_no or it.description[:40]}: choose the design its quantity comes from.")
        unit = DESIGN_QUANTITIES[it.design.key][1]
        if unit_factor(unit, it.unit) is None:
            raise Invalid(f"Item {it.item_no or it.description[:40]}: the design's {DESIGN_QUANTITIES[it.design.key][0].lower()} is in {unit}; "
                          f"the item's unit {it.unit} does not convert from it.")
        prev = before.get(it.id)
        same = prev is not None and str(prev.get("design_id")) == str(it.design.design_id) and prev.get("key") == it.design.key
        if refresh or not same or it.design.revision is None:
            now = _design_now(db, e.org_id, e.project_id, it.design.design_id, it.design.key)
            if now is None:
                raise Invalid(f"Item {it.item_no or it.description[:40]}: the design is not in this project, or reports no such quantity.")
            it.design.revision, it.design.value, it.design.label = now
        elif prev is not None:  # unchanged link: keep what was taken, whatever the client sent
            it.design.revision, it.design.value, it.design.label = prev.get("revision"), prev.get("value"), prev.get("label", "")
    return doc


def compute(db: Session, e: Estimate) -> dict[str, Any]:
    """Each item's quantity and amount, the measurement lines, design links whose design has since changed, and the abstract."""
    doc = EstimateDoc.model_validate(e.doc)
    out_items, amounts, stale = [], [], 0
    for k, it in enumerate(doc.items, start=1):
        entry: dict[str, Any] = {"id": it.id, "no": it.item_no or str(k), "stale": False}
        if it.quantity_mode == "measured":
            lines = [MeasureLine(m.description, m.nos, m.length, m.breadth, m.depth, m.deduct) for m in it.measurements]
            entry["lines"] = [float(line_quantity(ln)) for ln in lines]
            q = item_quantity(lines)
        elif it.quantity_mode == "design" and it.design is not None and it.design.value is not None:
            factor = unit_factor(DESIGN_QUANTITIES[it.design.key][1], it.unit) or Decimal(1)
            q = (dec(it.design.value) * factor).quantize(THREE, rounding=ROUND_HALF_UP)
            now = _design_now(db, e.org_id, e.project_id, it.design.design_id, it.design.key)
            if now is None or now[0] != it.design.revision or abs(now[1] - it.design.value) > 1e-9:
                entry["stale"] = True
                entry["design_now"] = None if now is None else {"revision": now[0], "value": now[1]}
                stale += 1
        else:
            q = dec(it.quantity).quantize(THREE, rounding=ROUND_HALF_UP)
        a = amount(q, it.rate)
        entry["quantity"], entry["amount"] = float(q), float(a)
        amounts.append(a)
        out_items.append(entry)
    ab = abstract(amounts, [Addition(a.label, a.pct) for a in doc.additions])
    return {"items": out_items, "stale": stale,
            "abstract": {"subtotal": float(ab.subtotal), "additions": [{"label": lb, "pct": p, "amount": float(v)} for lb, p, v in ab.additions],
                         "total": float(ab.total), "rounded": float(ab.rounded)}}


def save_estimate(db: Session, actor: User, estimate_id: uuid.UUID, data: EstimateSave, refresh: bool = False) -> Estimate:
    e = get_estimate(db, actor.org_id, estimate_id)
    if e.status == "issued":
        raise Conflict("An issued estimate is not changed: revise it first.")
    ids = [it.id for it in data.doc.items]
    if len(ids) != len(set(ids)):
        raise Invalid("Two items share an identifier.")
    doc = _check_links(db, e, data.doc, refresh, e.doc)
    e.title, e.notes, e.doc = data.title.strip(), data.notes, doc.model_dump(mode="json")
    e.total_paise = paise(Decimal(str(compute(db, e)["abstract"]["rounded"])))
    audit(db, actor, "estimate.saved", "estimate", e.id, f"Estimate {e.title} R{e.revision} saved: {len(doc.items)} items")
    return e


def preview(db: Session, org_id: uuid.UUID, estimate_id: uuid.UUID, doc: EstimateDoc) -> dict[str, Any]:
    """What a document would give, without saving it: the links checked and taken as a save would, on a copy."""
    e = get_estimate(db, org_id, estimate_id)
    draft = Estimate(org_id=e.org_id, project_id=e.project_id, title=e.title, doc={})
    draft.doc = _check_links(db, draft, doc.model_copy(deep=True), False, e.doc).model_dump(mode="json")
    return compute(db, draft)


def refresh_estimate(db: Session, actor: User, estimate_id: uuid.UUID) -> Estimate:
    e = get_estimate(db, actor.org_id, estimate_id)
    doc = EstimateDoc.model_validate(e.doc)
    return save_estimate(db, actor, estimate_id, EstimateSave(title=e.title, notes=e.notes, doc=doc), refresh=True)


def issue_estimate(db: Session, actor: User, estimate_id: uuid.UUID) -> Estimate:
    e = get_estimate(db, actor.org_id, estimate_id)
    if e.status == "issued":
        raise Conflict("The estimate is issued already.")
    res = compute(db, e)
    if not res["items"]:
        raise Conflict("An estimate without items is not issued.")
    if res["stale"]:
        raise Conflict(f"{res['stale']} item(s) take quantities from designs revised since: refresh them before issuing.")
    if e.created_by == actor.id and not get_settings().allow_self_approval:
        raise Conflict("An estimate is checked and issued by someone other than the one who prepared it.")
    e.status, e.issued_by_name, e.issued_at = "issued", actor.full_name, utcnow()
    audit(db, actor, "estimate.issued", "estimate", e.id, f"Estimate {e.title} R{e.revision} issued: Rs {res['abstract']['rounded']:,.0f}")
    return e


def revise_estimate(db: Session, actor: User, estimate_id: uuid.UUID) -> Estimate:
    e = get_estimate(db, actor.org_id, estimate_id)
    if e.status != "issued":
        raise Conflict("Only an issued estimate is revised; a draft is simply edited.")
    e.status, e.revision, e.issued_by_name, e.issued_at = "draft", e.revision + 1, "", None
    audit(db, actor, "estimate.revised", "estimate", e.id, f"Estimate {e.title} reopened as R{e.revision}")
    return e


def delete_estimate(db: Session, actor: User, estimate_id: uuid.UUID) -> None:
    e = get_estimate(db, actor.org_id, estimate_id)
    if e.status == "issued":
        raise Conflict("An issued estimate is kept: revise it, or keep it as the record.")
    if db.scalar(select(func.count()).select_from(MbEntry).where(MbEntry.estimate_id == e.id)):
        raise Conflict("The estimate has entries in its measurement book: it is kept as their record.")
    audit(db, actor, "estimate.deleted", "estimate", e.id, f"Estimate {e.title} deleted")
    db.delete(e)


# ----------------------------------------------------------------------------- measurement book


def mb_open(e: Estimate) -> bool:
    """Work is measured against an estimate once it has been issued: issued now, or a revision of an issued one."""
    return e.status == "issued" or e.revision > 0


def mb_quantities(lines: list[Measurement]) -> tuple[list[Decimal], Decimal]:
    """Each line's quantity and the entry's, by the estimate's rules of measurement (interpretation 111)."""
    qs = [line_quantity(MeasureLine(m.description, m.nos, m.length, m.breadth, m.depth, m.deduct)) for m in lines]
    return qs, sum(qs, Decimal(0))


def entry_out(m: MbEntry) -> dict[str, Any]:
    lines = [Measurement.model_validate(x) for x in m.lines]
    qs, total = mb_quantities(lines)
    return {"id": m.id, "entry_no": m.entry_no, "item_id": m.item_id, "measured_on": m.measured_on, "location": m.location, "lines": lines,
            "line_quantities": [float(q) for q in qs], "quantity": float(total), "status": m.status, "measured_by_name": m.measured_by_name,
            "checked_by_name": m.checked_by_name, "checked_at": m.checked_at, "updated_at": m.updated_at}


def list_entries(db: Session, e: Estimate) -> list[MbEntry]:
    return list(db.scalars(select(MbEntry).where(MbEntry.estimate_id == e.id, MbEntry.org_id == e.org_id).order_by(MbEntry.entry_no)))


def get_entry(db: Session, org_id: uuid.UUID, entry_id: uuid.UUID) -> MbEntry:
    m = db.get(MbEntry, entry_id)
    if m is None or m.org_id != org_id:
        raise NotFound("Measurement book entry not found.")
    return m


def measurement_book(db: Session, org_id: uuid.UUID, estimate_id: uuid.UUID) -> dict[str, Any]:
    """The entries in order, and each item's progress against the estimate (interpretation 117)."""
    e = get_estimate(db, org_id, estimate_id)
    res = {r["id"]: r for r in compute(db, e)["items"]}
    entries = list_entries(db, e)
    outs = [entry_out(m) for m in entries]
    per_item: dict[str, list[tuple[Decimal, bool]]] = {}
    for m, o in zip(entries, outs, strict=True):
        per_item.setdefault(m.item_id, []).append((dec(o["quantity"]), m.status == "checked"))
    items: list[dict[str, Any]] = []
    for it in e.doc.get("items", []):
        r = res[it["id"]]
        items.append(_progress_row(it["id"], r["no"], it["description"], it["unit"], it["rate"], True, r["quantity"], per_item.get(it["id"], [])))
    known = {it["id"] for it in e.doc.get("items", [])}
    for item_id, got in per_item.items():
        if item_id not in known:
            items.append(_progress_row(item_id, "-", "An item no longer in the estimate", "", 0.0, False, 0.0, got))
    return {"estimate_id": e.id, "open": mb_open(e), "entries": outs, "items": items,
            "value_measured": float(sum((dec(i["value_measured"]) for i in items), Decimal(0))),
            "value_checked": float(sum((dec(i["value_checked"]) for i in items), Decimal(0))),
            "value_excess": float(sum((dec(i["value_excess"]) for i in items), Decimal(0)))}


def _progress_row(item_id: str, no: str, description: str, unit: str, rate: float, in_estimate: bool, estimated: float,
                  got: list[tuple[Decimal, bool]]) -> dict[str, Any]:
    p = item_progress(estimated, got, rate)
    return {"item_id": item_id, "no": no, "description": description, "unit": unit, "rate": rate, "in_estimate": in_estimate,
            "estimated": float(p.estimated), "measured": float(p.measured), "checked": float(p.checked), "balance": float(p.balance),
            "excess": float(p.excess), "percent": None if p.percent is None else float(p.percent), "value_measured": float(p.value_measured),
            "value_checked": float(p.value_checked), "value_excess": float(p.value_excess), "entries": len(got)}


def _check_entry_input(e: Estimate, data: MbEntryIn) -> None:
    if data.item_id not in {it["id"] for it in e.doc.get("items", [])}:
        raise Invalid("The item is not in the estimate.")
    if data.measured_on > (utcnow() + timedelta(days=1)).date():
        raise Invalid("The date of measurement is in the future.")


def record_entry(db: Session, actor: User, estimate_id: uuid.UUID, data: MbEntryIn) -> MbEntry:
    e = get_estimate(db, actor.org_id, estimate_id)
    if not mb_open(e):
        raise Conflict("Work is measured against an issued estimate: issue this one first.")
    _check_entry_input(e, data)
    last = db.scalar(select(func.max(MbEntry.entry_no)).where(MbEntry.estimate_id == e.id)) or 0
    m = MbEntry(org_id=e.org_id, estimate_id=e.id, entry_no=last + 1, item_id=data.item_id, measured_on=data.measured_on,
                location=data.location.strip(), lines=[x.model_dump(mode="json") for x in data.lines], status="recorded",
                created_by=actor.id, measured_by_name=actor.full_name)
    db.add(m)
    db.flush()
    audit(db, actor, "mb.recorded", "estimate", e.id, f"Measurement book of {e.title}: entry {m.entry_no} recorded")
    return m


def update_entry(db: Session, actor: User, entry_id: uuid.UUID, data: MbEntryIn) -> MbEntry:
    m = get_entry(db, actor.org_id, entry_id)
    if m.status == "checked":
        raise Conflict("A checked entry is not changed: record a correcting entry instead.")
    e = get_estimate(db, actor.org_id, m.estimate_id)
    _check_entry_input(e, data)
    m.item_id, m.measured_on, m.location = data.item_id, data.measured_on, data.location.strip()
    m.lines = [x.model_dump(mode="json") for x in data.lines]
    audit(db, actor, "mb.changed", "estimate", e.id, f"Measurement book of {e.title}: entry {m.entry_no} changed")
    return m


def check_entry(db: Session, actor: User, entry_id: uuid.UUID) -> MbEntry:
    m = get_entry(db, actor.org_id, entry_id)
    if m.status == "checked":
        raise Conflict("The entry is checked already.")
    if m.created_by == actor.id and not get_settings().allow_self_approval:
        raise Conflict("An entry is checked by someone other than the one who measured it.")
    m.status, m.checked_by_name, m.checked_at = "checked", actor.full_name, utcnow()
    e = get_estimate(db, actor.org_id, m.estimate_id)
    audit(db, actor, "mb.checked", "estimate", e.id, f"Measurement book of {e.title}: entry {m.entry_no} checked")
    return m


def delete_entry(db: Session, actor: User, entry_id: uuid.UUID) -> None:
    m = get_entry(db, actor.org_id, entry_id)
    if m.status == "checked":
        raise Conflict("A checked entry is kept: record a correcting entry instead.")
    e = get_estimate(db, actor.org_id, m.estimate_id)
    audit(db, actor, "mb.deleted", "estimate", e.id, f"Measurement book of {e.title}: entry {m.entry_no} deleted")
    db.delete(m)
