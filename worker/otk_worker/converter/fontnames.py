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
    "symbol": "Symbol", "zapfdingbats": "Wingdings", "nimbussans": "Nimbus Sans", "nimbusroman": "Nimbus Roman", "nimbusmonops": "Nimbus Mono PS", "segoeui": "Segoe UI", "consolas": "Consolas",
    "liberationsans": "Liberation Sans", "liberationserif": "Liberation Serif", "liberationmono": "Liberation Mono",
    "dejavusans": "DejaVu Sans", "dejavuserif": "DejaVu Serif", "dejavusansmono": "DejaVu Sans Mono",
    "carlito": "Carlito", "caladea": "Caladea", "mangal": "Mangal", "nirmalaui": "Nirmala UI",
}

# Requested font -> metric-compatible substitute (same widths, so layout does not change).
METRIC_COMPATIBLE: dict[str, tuple[str, ...]] = {
    "calibri": ("carlito",), "cambria": ("caladea",), "georgia": ("gelasio",),
    "arial": ("liberation sans", "nimbus sans", "nimbus sans l", "arimo", "helvetica"),
    "helvetica": ("liberation sans", "nimbus sans", "nimbus sans l", "arimo", "arial"),
    "times new roman": ("liberation serif", "nimbus roman", "nimbus roman no9 l", "tinos", "times"),
    "times": ("liberation serif", "nimbus roman", "nimbus roman no9 l", "tinos", "times new roman"),
    "courier new": ("liberation mono", "nimbus mono ps", "nimbus mono l", "cousine", "courier"),
    "courier": ("liberation mono", "nimbus mono ps", "nimbus mono l", "cousine", "courier new"),
    "arial narrow": ("liberation sans narrow", "nimbus sans narrow"),
    "symbol": ("standard symbols ps",), "wingdings": ("d050000l",),
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
    if u in METRIC_COMPATIBLE.get(r, ()):
        return "metric-compatible"
    return "different metrics"


_installed: set[str] | None = None
_installed_done = False


def installed_families() -> set[str] | None:
    """Normalised family names of the fonts on this computer (None when they cannot be listed)."""
    global _installed, _installed_done
    if _installed_done:
        return _installed
    _installed_done = True
    names: set[str] = set()
    import os
    import shutil
    import subprocess
    if os.name == "nt":
        try:
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    key = winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
                except OSError:
                    continue
                i = 0
                while True:
                    try:
                        name, _, _ = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    i += 1
                    base = re.sub(r"\s*\((TrueType|OpenType|All res)\)\s*$", "", name)
                    for part in base.split("&"):
                        fam = re.sub(r"\s+(Bold|Italic|Bold Italic|Regular|Light|Semibold|Black|Medium)+$", "",
                                     part.strip(), flags=re.I)
                        names.add(re.sub(r"\s+", " ", fam.lower()).strip())
        except Exception:
            return None
    elif shutil.which("fc-list"):
        try:
            out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True, timeout=30).stdout
        except Exception:
            return None
        for line in out.splitlines():
            for fam in line.split(","):
                names.add(re.sub(r"\s+", " ", fam.strip().lower()))
    else:
        return None
    _installed = {n for n in names if n}
    return _installed
