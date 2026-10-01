"""Font names: PDF base-font names to family + style, and substitution labels."""

from __future__ import annotations

import re

_SUBSET = re.compile(r"^[A-Z]{6}\+")
_STYLE_WORDS = ("bolditalic", "boldoblique", "semibold", "demibold", "extrabold", "black", "heavy", "bold",
                "italic", "oblique", "regular", "roman", "book", "medium", "light", "thin", "condensed", "narrow",
                "mt", "ps", "psmt", "ms")

# PostScript names -> the family name Office uses.
_PS_FAMILIES = {
    "arialmt": "Arial", "arial": "Arial", "helvetica": "Arial", "timesnewromanpsmt": "Times New Roman",
    "timesnewroman": "Times New Roman", "times": "Times New Roman", "timesroman": "Times New Roman",
    "couriernewpsmt": "Courier New", "couriernew": "Courier New", "courier": "Courier New",
    "calibri": "Calibri", "cambria": "Cambria", "georgia": "Georgia", "verdana": "Verdana", "tahoma": "Tahoma",
    "symbol": "Symbol", "zapfdingbats": "Wingdings", "segoeui": "Segoe UI", "consolas": "Consolas",
    "liberationsans": "Liberation Sans", "liberationserif": "Liberation Serif", "liberationmono": "Liberation Mono",
    "dejavusans": "DejaVu Sans", "dejavuserif": "DejaVu Serif", "dejavusansmono": "DejaVu Sans Mono",
    "carlito": "Carlito", "caladea": "Caladea", "mangal": "Mangal", "nirmalaui": "Nirmala UI",
}

# Requested font -> metric-compatible substitute (same widths, so layout does not change).
METRIC_COMPATIBLE = {
    "calibri": "carlito", "cambria": "caladea", "arial": "liberation sans", "helvetica": "liberation sans",
    "times new roman": "liberation serif", "times": "liberation serif", "courier new": "liberation mono",
    "courier": "liberation mono", "georgia": "gelasio", "arial narrow": "liberation sans narrow",
}


def strip_subset(name: str) -> str:
    return _SUBSET.sub("", name or "")


def split(name: str) -> tuple[str, bool, bool]:
    """'ABCDEF+Calibri-BoldItalic' -> ('Calibri', True, True)."""
    raw = strip_subset(name)
    low = raw.lower()
    bold = any(w in low for w in ("bold", "black", "heavy", "semibold", "demi"))
    italic = "italic" in low or "oblique" in low
    base = re.split(r"[-,]", raw, maxsplit=1)[0]
    key = re.sub(r"[^a-z0-9]", "", base.lower())
    if key in _PS_FAMILIES:
        return _PS_FAMILIES[key], bold, italic
    for w in _STYLE_WORDS:
        if key.endswith(w) and len(key) > len(w) + 2 and key[: -len(w)] in _PS_FAMILIES:
            return _PS_FAMILIES[key[: -len(w)]], bold, italic
    # Split CamelCase ("NotoSansDevanagari" -> "Noto Sans Devanagari") and drop trailing MT/PS markers.
    base = re.sub(r"(PSMT|MT|PS)$", "", base)
    family = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base).strip() or raw
    return family, bold, italic


def family(name: str) -> str:
    return split(name)[0]


def norm(name: str) -> str:
    return re.sub(r"\s+", " ", family(name).lower()).strip()


def substitution_kind(requested: str, used: str) -> str:
    """'same', 'metric-compatible' or 'different metrics'."""
    r, u = norm(requested), norm(used)
    if r == u or r.replace(" ", "") == u.replace(" ", ""):
        return "same"
    if METRIC_COMPATIBLE.get(r) == u:
        return "metric-compatible"
    return "different metrics"
