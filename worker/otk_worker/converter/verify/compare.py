"""Checks: source extract vs output extract.

Every check ends as pass, expected (a difference the route is known to cause:
a loss the planner listed, or one a step declared), fail, or skipped (cannot
be checked for this pair). A job is "perfect" only when no check failed, no
check is "expected", and no step declared an expected change.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from rapidfuzz.distance import LCSseq, Levenshtein

from .. import fontnames
from .extract import Extract, Img

PASS, EXPECTED, FAIL, SKIPPED = "pass", "expected", "fail", "skipped"

_BULLETS = re.compile(r"^[•●▪◦■□–—‣⁃∙·\-*•·◦▪➢✓✔→]+$")
_DECOR = re.compile(r"^[|+\-=:_~`\[\]]{1,}$")   # table borders and empty brackets plain-text writers draw
_LISTNUM = re.compile(r"^\(?([0-9]{1,3}|[a-zA-Z]|[ivxlcdmIVXLCDM]{1,5})[.)]$")
_RTL = re.compile("[֐-ࣿיִ-﷿ﹰ-ﻼ]")
_GENERIC = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif", "ui-serif",
            "ui-monospace", "emoji", "math", "inherit", "initial", "-apple-system", "blinkmacsystemfont"}


@dataclass
class Check:
    id: str
    label: str
    status: str
    summary: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "status": self.status, "summary": self.summary,
                "details": self.details}


@dataclass
class Situation:
    """What the comparison needs to know about the route."""
    source_format: str
    target: str
    mode: str
    lost: dict[str, str]                      # feature -> "lost" | "reduced" (planner)
    target_caps: dict[str, str]
    expected_checks: dict[str, str]
    added_text: list[str]
    expected_notes: list[str]
    ocr_route: bool = False
    notes_pages: bool = False


# ------------------------------------------------------------------ text
def _dedupe_marks(t: str) -> str:
    """The same combining mark twice in a row (e.g. two anusvaras) never carries meaning; PDF readers
    sometimes report one twice when a cluster has both /ActualText and per-glyph Unicode."""
    out = []
    for ch in t:
        if out and ch == out[-1] and unicodedata.category(ch) in ("Mn", "Mc"):
            continue
        out.append(ch)
    return "".join(out)


def normalize(text: str) -> str:
    t = _dedupe_marks(unicodedata.normalize("NFKC", text))
    t = t.replace("­", "").replace("​", "").replace("﻿", "").replace("⁠", "")
    t = re.sub(r"-[ \t]*\r?\n[ \t]*", "-", t)          # a hyphen at a line end joins the next line (kept)
    t = re.sub(r"[\s  -   　]+", " ", t)
    return t.strip()


def tokens(text: str) -> list[str]:
    n = normalize(text)
    return n.split(" ") if n else []


def _canonical(seq: list[str]) -> list[str]:
    """Runs of right-to-left words are compared as sets: PDF extractors return them in visual or logical order."""
    out, run = [], []
    for t in seq:
        if _RTL.search(t):
            run.append(t)
        else:
            if run:
                out.extend(sorted(run))
                run = []
            out.append(t)
    out.extend(sorted(run))
    return out


def _remove_once(counter: Counter, items: list[str]) -> None:
    for t in items:
        if counter.get(t, 0) > 0:
            counter[t] -= 1


def _context(tok: str, text_tokens: list[str], width: int = 5) -> str:
    try:
        i = text_tokens.index(tok)
    except ValueError:
        return tok
    return " ".join(text_tokens[max(0, i - width): i + width + 1])


def check_text(src: Extract, out: Extract, sit: Situation) -> Check:
    first = _check_text(src.text, out.text, src, out, sit)
    if first.status == PASS or (src.second_text is None and out.second_text is None):
        return first
    # PDF readers differ on complex scripts (ActualText, glyph order). Ask the second reader before failing.
    s2 = src.second_text() if src.second_text else src.text
    o2 = out.second_text() if out.second_text else out.text
    second = _check_text(s2, o2, src, out, sit)
    if second.status == PASS:
        second.summary += " (confirmed with the second PDF reader; the first reader, pdfium, read some text differently)"
        second.details["firstReader"] = {"summary": first.summary, "missing": first.details.get("missing", [])[:20],
                                         "extra": first.details.get("extra", [])[:20]}
        return second
    better = second if second.details.get("similarity", 0) > first.details.get("similarity", 0) else first
    better.details["readers"] = {"pdfium": first.summary, "mupdf": second.summary}
    return better


def _check_text(src_text: str, out_text: str, src: Extract, out: Extract, sit: Situation) -> Check:
    label = "Text"
    st, ot = tokens(src_text), tokens(out_text)
    added: list[str] = []
    for a in sit.added_text:
        added.extend(tokens(a))
    if not st and not ot:
        return Check("text", label, SKIPPED, "Neither file contains text.")
    if not st and ot:
        status = EXPECTED if sit.ocr_route else FAIL
        return Check("text", label, status, f"The source has no text layer; {len(ot)} words were recognised by OCR."
                     if sit.ocr_route else f"The output has {len(ot)} words the source does not have.",
                     {"sourceWords": 0, "outputWords": len(ot)})
    if sit.target_caps.get("text") == "none":
        return Check("text", label, EXPECTED, f"{len(st)} words became pixels (the target format holds no text).",
                     {"sourceWords": len(st)})
    oc = Counter(ot)
    _remove_once(oc, added)
    oc = +oc
    sc = Counter(st)
    missing = sc - oc
    extra = oc - sc
    # Decorations engines add (bullets, list numbers, repeated headers/footers) are not content changes.
    notes = Counter(t for n in (src.notes or []) for t in tokens(n))  # checked by the notes check
    allowed = {t: (min(n, notes[t]) if t in notes and not _DECOR.match(t) and t not in src.repeatable else n)
               for t, n in extra.items()
               if _BULLETS.match(t) or _DECOR.match(t) or (src.has_lists and _LISTNUM.match(t))
               or t in src.repeatable or t in notes}
    extra = extra - Counter(allowed)
    src_seq = _canonical(st)
    out_seq = list(ot)
    for t in added:  # labels the writer added (sheet names, "Slide 3") are not source words
        if t in out_seq:
            out_seq.remove(t)
    out_seq = _canonical(out_seq)
    # In order = every source word appears in the output in the same order (extra words may sit in between).
    in_order = LCSseq.similarity(src_seq, out_seq) == len(src_seq)
    sim = Levenshtein.normalized_similarity(src_seq, out_seq)
    details = {
        "sourceWords": len(st), "outputWords": len(ot), "similarity": round(sim, 4),
        "missing": [{"token": t, "count": n, "context": _context(t, st)} for t, n in missing.most_common(50)],
        "extra": [{"token": t, "count": n, "context": _context(t, ot)} for t, n in extra.most_common(50)],
        "missingCount": sum(missing.values()), "extraCount": sum(extra.values()),
        "ignored": sorted(allowed)[:30], "inOrder": in_order,
    }
    if not missing and not extra and in_order:
        return Check("text", label, PASS, f"All {len(st)} words are present, in the same order.", details)
    reason = sit.expected_checks.get("text")
    if reason:
        return Check("text", label, EXPECTED, reason, details)
    if sit.ocr_route:
        return Check("text", label, EXPECTED,
                     f"Text comes from OCR: {sum(missing.values())} source word(s) differ, similarity {sim:.1%}.", details)
    if sit.lost.get("text"):
        return Check("text", label, EXPECTED, f"The route keeps text only {sit.lost['text']}; similarity {sim:.1%}.", details)
    if not missing and not extra:
        if sit.target == "xlsx" or any("order" in n for n in sit.expected_notes):
            return Check("text", label, EXPECTED, f"All {len(st)} words are present; their order changed "
                         f"(tables and text are on separate sheets). Order score {sim:.1%}.", details)
        return Check("text", label, FAIL, f"All words are present but in a different order (order score {sim:.1%}).", details)
    return Check("text", label, FAIL, f"{sum(missing.values())} word(s) missing and {sum(extra.values())} extra; "
                 f"similarity {sim:.1%}.", details)


# ------------------------------------------------------------------ images
def _visually_same(a: Img, b: Img) -> bool:
    if a.thumb is None or b.thumb is None:
        return False
    return float(np.mean(np.abs(a.thumb - b.thumb))) < 3.0


def check_images(src: Extract, out: Extract, sit: Situation) -> Check:
    label = "Images"
    if src.images is None or out.images is None:
        return Check("images", label, SKIPPED, "Images cannot be read from one of the files.")
    if not src.images:
        if out.images and sit.target not in ("png", "jpeg"):
            return Check("images", label, PASS, f"No images in the source; the output has {len(out.images)}.")
        return Check("images", label, SKIPPED, "The source has no images.")
    if sit.target in ("png", "jpeg") and sit.source_format not in ("png", "jpeg"):
        return Check("images", label, SKIPPED, "Every page became an image; see the appearance check.")
    if sit.target_caps.get("images") == "none":
        return Check("images", label, EXPECTED, f"{len(src.images)} image(s) cannot be kept in {sit.target.upper()}.")
    remaining = list(out.images)
    exact, similar, unmatched = 0, 0, []
    for im in src.images:
        hit = next((o for o in remaining if o.digest == im.digest), None)
        if hit is not None:
            remaining.remove(hit)
            exact += 1
            continue
        hit = next((o for o in remaining if (o.width, o.height) == (im.width, im.height) and _visually_same(im, o)), None)
        if hit is None:
            hit = next((o for o in remaining if _visually_same(im, o)), None)
            if hit is not None:
                remaining.remove(hit)
                unmatched.append({"width": im.width, "height": im.height, "outputWidth": hit.width,
                                  "outputHeight": hit.height, "issue": "resized"})
                continue
        if hit is not None:
            remaining.remove(hit)
            similar += 1
            continue
        unmatched.append({"width": im.width, "height": im.height, "issue": "missing"})
    details = {"source": len(src.images), "output": len(out.images), "identical": exact, "reEncoded": similar,
               "problems": unmatched, "extraInOutput": len(remaining)}
    if not unmatched and not remaining and similar == 0:
        return Check("images", label, PASS, f"All {exact} image(s) are present with identical pixels.", details)
    reason = sit.expected_checks.get("images")
    if reason:
        return Check("images", label, EXPECTED, reason, details)
    if sit.lost.get("images"):
        return Check("images", label, EXPECTED, f"Images are kept only {sit.lost['images']} on this route.", details)
    if not unmatched and not remaining:
        return Check("images", label, EXPECTED if sit.target == "jpeg" else PASS,
                     f"All {len(src.images)} image(s) are present; {similar} were re-encoded and look the same.", details)
    missing = sum(1 for u in unmatched if u["issue"] == "missing")
    resized = sum(1 for u in unmatched if u["issue"] == "resized")
    parts = []
    if missing:
        parts.append(f"{missing} missing")
    if resized:
        parts.append(f"{resized} resized")
    if remaining:
        parts.append(f"{len(remaining)} extra")
    return Check("images", label, FAIL, f"Images differ: {', '.join(parts)} (source {len(src.images)}, output {len(out.images)}).", details)


# ------------------------------------------------------------------ structure
def check_tables(src: Extract, out: Extract, sit: Situation) -> Check:
    label = "Tables"
    if src.tables is None or out.tables is None:
        which = "source" if src.tables is None else "output"
        return Check("tables", label, SKIPPED, f"Table structure cannot be read from the {which} ({(src if which == 'source' else out).format.upper()}).")
    if not src.tables:
        return Check("tables", label, SKIPPED, "The source has no tables.")
    sdesc = [(t.rows, t.cols, len(t.merges)) for t in src.tables]
    odesc = [(t.rows, t.cols, len(t.merges)) for t in out.tables]
    if out.format == "xlsx" and src.format not in ("xlsx", "xls"):
        # Each table becomes a sheet; other sheets (Text, Slides, Original) hold the rest.
        pool = list(out.tables)
        unmatched = []
        for t in src.tables:
            hit = next((o for o in pool if (o.rows, o.cols, sorted(o.merges)) == (t.rows, t.cols, sorted(t.merges))), None)
            if hit is None:
                unmatched.append((t.rows, t.cols, len(t.merges)))
            else:
                pool.remove(hit)
        details = {"source": [{"rows": r, "cols": c, "merged": m} for r, c, m in sdesc], "unmatched": unmatched}
        if not unmatched:
            return Check("tables", label, PASS, f"Each of the {len(src.tables)} table(s) is a sheet with the same rows, "
                         "columns and merged cells.", details)
        if sit.expected_checks.get("tables") or sit.lost.get("tables") or sit.lost.get("merged_cells"):
            return Check("tables", label, EXPECTED, sit.expected_checks.get("tables") or "Table structure is kept only partly.", details)
        return Check("tables", label, FAIL, f"{len(unmatched)} table(s) have no sheet with the same structure: {unmatched}.", details)
    details = {"source": [{"rows": r, "cols": c, "merged": m} for r, c, m in sdesc],
               "output": [{"rows": r, "cols": c, "merged": m} for r, c, m in odesc]}
    same = len(src.tables) == len(out.tables) and all(
        (a.rows, a.cols, sorted(a.merges)) == (b.rows, b.cols, sorted(b.merges)) for a, b in zip(src.tables, out.tables))
    if same:
        return Check("tables", label, PASS, f"{len(src.tables)} table(s) with the same rows, columns and merged cells.", details)
    reason = sit.expected_checks.get("tables")
    if reason or sit.lost.get("tables") or sit.lost.get("merged_cells"):
        return Check("tables", label, EXPECTED, reason or "Table structure is kept only partly on this route.", details)
    return Check("tables", label, FAIL, f"Tables differ (source {len(src.tables)}: {sdesc}; output {len(out.tables)}: {odesc}).", details)


def check_links(src: Extract, out: Extract, sit: Situation) -> Check:
    label = "Hyperlinks"
    if src.links is None or out.links is None:
        return Check("links", label, SKIPPED, "Links cannot be read from one of the files.")
    if not src.links:
        return Check("links", label, SKIPPED, "The source has no web links.")
    missing = sorted(src.links - out.links)
    extra = sorted(out.links - src.links)
    details = {"source": sorted(src.links), "missing": missing, "extra": extra}
    if not missing:
        return Check("links", label, PASS, f"All {len(src.links)} link(s) are present.", details)
    if sit.lost.get("hyperlinks") or sit.expected_checks.get("links"):
        return Check("links", label, EXPECTED, sit.expected_checks.get("links") or
                     f"{len(missing)} link(s) cannot be kept as links in {sit.target.upper()}.", details)
    return Check("links", label, FAIL, f"{len(missing)} of {len(src.links)} link(s) are missing.", details)


def _norm_title(t: str) -> str:
    return normalize(t).casefold()


def check_bookmarks(src: Extract, out: Extract, sit: Situation) -> Check:
    label = "Bookmarks / headings"
    if src.bookmarks is None or out.bookmarks is None:
        return Check("bookmarks", label, SKIPPED, "Bookmarks cannot be read from one of the files.")
    if not src.bookmarks:
        return Check("bookmarks", label, SKIPPED, "The source has no bookmarks or headings.")
    missing = [t for t in src.bookmarks if _norm_title(t) not in {_norm_title(x) for x in out.bookmarks}]
    details = {"source": src.bookmarks[:100], "output": out.bookmarks[:100], "missing": missing[:100]}
    if not missing:
        return Check("bookmarks", label, PASS, f"All {len(src.bookmarks)} bookmark(s)/heading(s) are present.", details)
    if sit.target_caps.get("bookmarks") in ("none", "partial") or sit.lost.get("bookmarks") or sit.expected_checks.get("bookmarks"):
        return Check("bookmarks", label, EXPECTED, sit.expected_checks.get("bookmarks") or
                     f"{len(missing)} bookmark(s) have no equivalent in {sit.target.upper()}.", details)
    return Check("bookmarks", label, FAIL, f"{len(missing)} of {len(src.bookmarks)} bookmark(s)/heading(s) are missing.", details)


def check_notes(src: Extract, out: Extract, sit: Situation) -> Check:
    label = "Speaker notes"
    if not src.notes:
        return Check("notes", label, SKIPPED, "The source has no speaker notes.")
    out_norm = normalize(out.text + "\n" + "\n".join(out.notes or []))
    missing = [n for n in src.notes if normalize(n) and normalize(n) not in out_norm]
    details = {"source": src.notes[:50], "missing": missing[:50]}
    if not missing:
        return Check("notes", label, PASS, f"All {len(src.notes)} note(s) are present.", details)
    if sit.target in ("pdf", "pdfa1b", "pdfa2b", "pdfa3b") and not sit.notes_pages:
        return Check("notes", label, EXPECTED, "Speaker notes are not printed unless 'notes pages' is switched on.", details)
    if sit.target_caps.get("slide_notes") == "none" or sit.lost.get("slide_notes"):
        return Check("notes", label, EXPECTED, f"Speaker notes cannot be kept in {sit.target.upper()}.", details)
    return Check("notes", label, FAIL, f"{len(missing)} speaker note(s) are missing.", details)


def check_units(src: Extract, out: Extract, sit: Situation) -> Check:
    label = "Pages / slides / sheets"
    s_kind = next(iter(src.units), None)
    o_kind = next(iter(out.units), None)
    if s_kind is None or o_kind is None:
        return Check("units", label, SKIPPED, "Page counts are not defined for this pair (one side reflows).")
    if sit.source_format in ("png", "jpeg") and sit.target not in ("pdf", "pdfa1b", "pdfa2b", "pdfa3b", "pptx", "svg", "epub"):
        return Check("units", label, SKIPPED, "Not applicable.")
    if s_kind == "sheets" and o_kind != "sheets":
        return Check("units", label, SKIPPED, "Sheets have no pages.")
    if o_kind == "sheets" and s_kind != "sheets":
        return Check("units", label, SKIPPED, "Sheets are organised differently from pages.")
    sn, on = src.units[s_kind], out.units[o_kind]
    if s_kind == "slides" and o_kind == "pages" and sit.notes_pages:
        sn = sn * 2
    details = {"source": {s_kind: src.units[s_kind]}, "output": {o_kind: on}}
    if sn == on:
        return Check("units", label, PASS, f"{src.units[s_kind]} {s_kind} → {on} {o_kind}.", details)
    reason = sit.expected_checks.get("units")
    if reason:
        return Check("units", label, EXPECTED, reason, details)
    return Check("units", label, FAIL, f"{src.units[s_kind]} {s_kind} in the source but {on} {o_kind} in the output.", details)


def check_cells(src: Extract, out: Extract, sit: Situation) -> Check:
    label = "Spreadsheet cells"
    if src.cells is None or out.cells is None:
        return Check("cells", label, SKIPPED, "Only compared between spreadsheets.")
    problems = []
    if list(src.cells) != list(out.cells):
        problems.append({"issue": "sheet names", "source": list(src.cells), "output": list(out.cells)})
    compared = 0
    for sheet, cells in src.cells.items():
        oc = out.cells.get(sheet, {})
        for coord, (shown, formula, fmt) in cells.items():
            compared += 1
            o = oc.get(coord)
            if o is None:
                problems.append({"sheet": sheet, "cell": coord, "issue": "missing", "source": shown})
                continue
            if shown != o[0]:
                problems.append({"sheet": sheet, "cell": coord, "issue": "value", "source": shown, "output": o[0]})
            if formula and o[1] and formula.replace(" ", "") != o[1].replace(" ", ""):
                problems.append({"sheet": sheet, "cell": coord, "issue": "formula", "source": formula, "output": o[1]})
            elif formula and not o[1]:
                problems.append({"sheet": sheet, "cell": coord, "issue": "formula lost", "source": formula})
            if fmt and o[2] and fmt != o[2] and not _same_format(fmt, o[2]):
                problems.append({"sheet": sheet, "cell": coord, "issue": "number format", "source": fmt, "output": o[2]})
        if src.merges and out.merges and sorted(src.merges.get(sheet, [])) != sorted(out.merges.get(sheet, [])):
            problems.append({"sheet": sheet, "issue": "merged cells", "source": src.merges.get(sheet), "output": out.merges.get(sheet)})
    details = {"compared": compared, "problems": problems[:200], "problemCount": len(problems)}
    if not problems:
        return Check("cells", label, PASS, f"All {compared} cell(s): values, formulas and number formats match.", details)
    return Check("cells", label, FAIL, f"{len(problems)} difference(s) in {compared} cell(s).", details)


def _same_format(a: str, b: str) -> bool:
    return a.replace("\\", "").replace('"', "").lower() == b.replace("\\", "").replace('"', "").lower()


def _families(names) -> set[str]:
    out = set()
    for n in names:
        for part in str(n).split(","):
            p = part.strip().strip("'\"")
            if p and p.lower() not in _GENERIC:
                out.add(p)
    return out


def check_fonts(src: Extract, out: Extract, sit: Situation) -> Check:
    label = "Fonts"
    pdf_out = sit.target in ("pdf", "pdfa1b", "pdfa2b", "pdfa3b")
    office_exact = sit.target in ("docx", "pptx") and sit.mode == "exact"
    if not (pdf_out or office_exact):
        return Check("fonts", label, SKIPPED, f"In {sit.target.upper()} the viewer chooses the fonts; only PDF and "
                     "exact-mode Word/PowerPoint output are checked.")
    if out.fonts_used is None:
        return Check("fonts", label, SKIPPED, f"Fonts cannot be read from {out.format.upper()}.")
    if sit.expected_checks.get("fonts"):
        return Check("fonts", label, SKIPPED, sit.expected_checks["fonts"])
    unembedded = sorted(f for f, emb in out.fonts_used.items() if not emb)
    requested = _families(src.fonts_requested or [])
    used = {fontnames.norm(f): f for f in out.fonts_used}
    used.update({k.replace(" ", ""): v for k, v in list(used.items())})
    installed = fontnames.installed_families()
    if installed is not None:
        installed = installed | {n.replace(" ", "") for n in installed}
    subs = []
    for fam in sorted(requested):
        n = fontnames.norm(fam)
        if n in used or n.replace(" ", "") in {u.replace(" ", "") for u in used}:
            continue
        compat = next((c for c in fontnames.METRIC_COMPATIBLE.get(n, ()) if c in used or c.replace(" ", "") in used), None)
        if compat:
            subs.append({"requested": fam, "used": used.get(compat) or used.get(compat.replace(" ", "")), "kind": "metric-compatible"})
        elif pdf_out and installed is not None and (n in installed or n.replace(" ", "") in installed):
            subs.append({"requested": fam, "used": None, "kind": "fallback for missing characters"})
        elif pdf_out:
            subs.append({"requested": fam, "used": None, "kind": "not installed"})
        else:
            subs.append({"requested": fam, "used": None, "kind": "not referenced"})
    if office_exact and installed is not None:
        missing_here = sorted(f for f in out.fonts_used if fontnames.norm(f) not in installed
                              and fontnames.norm(f).replace(" ", "") not in installed
                              and not any(c in installed for c in fontnames.METRIC_COMPATIBLE.get(fontnames.norm(f), ())))
    else:
        missing_here = []
    details = {"requested": sorted(requested), "output": sorted(out.fonts_used), "notEmbedded": unembedded,
               "substitutions": subs, "notInstalledHere": missing_here}
    if pdf_out and unembedded:
        return Check("fonts", label, FAIL, f"Not embedded in the PDF: {', '.join(unembedded)}.", details)
    hard = [s for s in subs if s["kind"] in ("not installed", "not referenced")]
    soft = [s for s in subs if s not in hard]
    if hard:
        return Check("fonts", label, FAIL, "Requested font(s) not available, replaced by fonts with different widths: "
                     + ", ".join(s["requested"] for s in hard) + ". Install them, or expect different line breaks.", details)
    if missing_here:
        return Check("fonts", label, EXPECTED, "The output names font(s) that are not installed on this computer: "
                     + ", ".join(missing_here) + "; Word/PowerPoint substitutes them when they are missing.", details)
    if soft:
        parts = [f"{s['requested']} → {s['used']}" if s["used"] else f"{s['requested']} (fallback for some characters)"
                 for s in soft]
        return Check("fonts", label, EXPECTED, "Substitution: " + ", ".join(parts) + ".", details)
    if not requested:
        return Check("fonts", label, PASS, "All fonts are embedded." if pdf_out else "Fonts are referenced as in the source.", details)
    return Check("fonts", label, PASS, f"All {len(requested)} requested font(s) are used"
                 + (" and embedded." if pdf_out else "."), details)


def check_appearance(src: Extract, out: Extract, sit: Situation, out_render=None, dpi: int = 100) -> Check:
    from ...common.ssim import ssim

    label = "Appearance (rendered pages)"
    render_out = out_render or out.render
    if sit.mode != "exact":
        return Check("appearance", label, SKIPPED, "Only checked in exact mode.")
    if src.render is None or render_out is None:
        return Check("appearance", label, SKIPPED, "The source has no fixed page layout to compare against.")
    if sit.expected_checks.get("appearance_skip"):
        return Check("appearance", label, SKIPPED, sit.expected_checks["appearance_skip"])
    a = src.render(dpi)
    b = render_out(dpi)
    if len(a) != len(b):
        return Check("appearance", label, FAIL, f"{len(a)} source page(s) but {len(b)} rendered output page(s).",
                     {"sourcePages": len(a), "outputPages": len(b)})
    scores, shifts = [], []
    for x, y in zip(a, b):
        if x.size != y.size:
            if abs(x.width - y.width) > 0.03 * x.width or abs(x.height - y.height) > 0.03 * x.height:
                scores.append(0.0)
                shifts.append(None)
                continue
            y = y.resize(x.size)
        score, shift = _aligned_ssim(x, y, ssim)
        scores.append(round(score, 4))
        shifts.append(shift)
    worst = min(scores) if scores else 1.0
    details = {"ssim": scores, "threshold": 0.98, "dpi": dpi, "alignment": shifts}
    if worst >= 0.98:
        return Check("appearance", label, PASS, f"Every page looks the same (lowest SSIM {worst:.3f}).", details)
    reason = sit.expected_checks.get("appearance")
    if reason:
        return Check("appearance", label, EXPECTED, reason, details)
    bad = [i + 1 for i, s in enumerate(scores) if s < 0.98]
    return Check("appearance", label, FAIL, f"Page(s) {', '.join(map(str, bad[:20]))} look different "
                 f"(lowest SSIM {worst:.3f}, needs ≥ 0.98).", details)


def _soften(img):
    """A light blur: renderers place edges with different sub-pixel rounding; that is not a visible change."""
    from PIL import ImageFilter
    return img.filter(ImageFilter.GaussianBlur(0.7))


def _aligned_ssim(x, y, ssim_fn, radius: int = 2):
    """SSIM after the best whole-pixel alignment within ±radius (renderers round positions differently)."""
    x, y = _soften(x), _soften(y)
    base = ssim_fn(x, y)
    if base >= 0.98:
        return base, (0, 0)
    ax = np.asarray(x.convert("L"), dtype=np.float32)
    ay = np.asarray(y.convert("L"), dtype=np.float32)
    h, w = ax.shape
    best, best_shift = None, (0, 0)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            a_part = ax[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)]
            b_part = ay[max(0, -dy):h + min(0, -dy), max(0, -dx):w + min(0, -dx)]
            diff = float(np.mean(np.abs(a_part - b_part)))
            if best is None or diff < best:
                best, best_shift = diff, (dx, dy)
    if best_shift == (0, 0):
        return base, (0, 0)
    dx, dy = best_shift
    box_a = (max(0, dx), max(0, dy), w + min(0, dx), h + min(0, dy))
    box_b = (max(0, -dx), max(0, -dy), w + min(0, -dx), h + min(0, -dy))
    return max(base, ssim_fn(x.crop(box_a), y.crop(box_b))), best_shift


def verdict(checks: list[Check], expected_notes: list[str]) -> str:
    statuses = {c.status for c in checks}
    if FAIL in statuses:
        return "review"
    if EXPECTED in statuses or expected_notes:
        return "expected"
    return "perfect"
