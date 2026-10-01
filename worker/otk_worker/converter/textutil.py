"""Small text helpers: scripts, fonts for complex scripts, HTML to text lines."""

from __future__ import annotations

import re

from lxml import etree

_RANGES = [
    ("arabic", "؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿"),
    ("hebrew", "֐-׿יִ-ﭏ"),
    ("devanagari", "ऀ-ॿ꣠-ꣿ"),
    ("bengali", "ঀ-৿"),
    ("gurmukhi", "਀-੿"),
    ("gujarati", "઀-૿"),
    ("oriya", "଀-୿"),
    ("tamil", "஀-௿"),
    ("telugu", "ఀ-౿"),
    ("kannada", "ಀ-೿"),
    ("malayalam", "ഀ-ൿ"),
    ("thai", "฀-๿"),
    ("cjk", "぀-ヿ㐀-䶿一-鿿가-힯豈-﫿"),
]
_COMPILED = [(name, re.compile(f"[{chars}]")) for name, chars in _RANGES]

# Fonts Windows ships for each script (used as the complex-script font in DOCX/PPTX).
CS_FONT = {"arabic": "Arial", "hebrew": "Arial", "devanagari": "Nirmala UI", "bengali": "Nirmala UI",
           "gurmukhi": "Nirmala UI", "gujarati": "Nirmala UI", "oriya": "Nirmala UI", "tamil": "Nirmala UI",
           "telugu": "Nirmala UI", "kannada": "Nirmala UI", "malayalam": "Nirmala UI", "thai": "Leelawadee UI",
           "cjk": "Microsoft YaHei"}
LANG_TAG = {"arabic": "ar-SA", "hebrew": "he-IL", "devanagari": "hi-IN", "bengali": "bn-IN", "tamil": "ta-IN",
            "telugu": "te-IN", "kannada": "kn-IN", "malayalam": "ml-IN", "gujarati": "gu-IN", "gurmukhi": "pa-IN",
            "oriya": "or-IN", "thai": "th-TH"}


def script_of(text: str) -> str | None:
    """The dominant non-Latin script of a string, or None."""
    best, count = None, 0
    for name, rx in _COMPILED:
        n = len(rx.findall(text))
        if n > count:
            best, count = name, n
    return best


def is_rtl_script(script: str | None) -> bool:
    return script in ("arabic", "hebrew")


BLOCK_TAGS = {"address", "article", "aside", "blockquote", "body", "caption", "dd", "details", "div", "dl", "dt",
              "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header",
              "hr", "li", "main", "nav", "ol", "p", "pre", "section", "summary", "table", "tbody", "td", "tfoot",
              "th", "thead", "title", "tr", "ul", "br"}
SKIP_TAGS = {"script", "style", "noscript", "template", "head"}


def html_lines(root, *, skip_tables: bool = False) -> list[str]:
    """Visible text of an HTML tree, one entry per block (whitespace collapsed, <pre> kept as is)."""
    lines: list[str] = []
    cur: list[str] = []

    def flush():
        text = "".join(cur)
        cur.clear()
        text = re.sub(r"[ \t\r\n\f]+", " ", text).strip() if "\x00pre" not in text else text.replace("\x00pre", "")
        if text:
            lines.append(text)

    def walk(el, in_pre=False):
        if not isinstance(el.tag, str):
            if el.tail:
                cur.append(el.tail)
            return
        tag = etree.QName(el).localname.lower() if "}" in el.tag else el.tag.lower()
        if tag in SKIP_TAGS or (skip_tables and tag == "table"):
            if el.tail:
                cur.append(el.tail)
            return
        block = tag in BLOCK_TAGS
        pre = in_pre or tag in ("pre", "textarea")
        if block:
            flush()
        if tag == "br":
            flush()
        elif tag == "img" and el.get("alt") is None:
            pass
        if el.text:
            cur.append(el.text if not pre else "\x00pre" + el.text)
        for child in el:
            walk(child, pre)
        if block:
            flush()
        if el.tail:
            cur.append(el.tail)

    walk(root)
    flush()
    return lines
