"""Small edits to DOCX files after conversion."""

from __future__ import annotations

import copy
import re
import unicodedata
from pathlib import Path


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip().casefold()


def _split_after_first_line(p) -> bool:
    """Split a paragraph at its first manual line break; the rest moves to a new paragraph right after it."""
    from docx.oxml.ns import qn

    p_el = p._p
    children = [c for c in p_el if c.tag != qn("w:pPr")]
    for ci, child in enumerate(children):
        runs = [child] if child.tag == qn("w:r") else list(child.iter(qn("w:r")))
        for run in runs:
            parts = list(run)
            brs = [i for i, x in enumerate(parts) if x.tag == qn("w:br") and x.get(qn("w:type")) in (None, "textWrapping")]
            if not brs:
                continue
            bi = brs[0]
            new_p = copy.deepcopy(p_el)
            for x in list(new_p):
                if x.tag != qn("w:pPr"):
                    new_p.remove(x)
            # The run's content after the break, then every later sibling, go to the new paragraph.
            tail = parts[bi + 1:]
            if any(x.tag != qn("w:rPr") for x in tail):
                new_run = copy.deepcopy(run)
                for x in list(new_run):
                    if x.tag != qn("w:rPr"):
                        new_run.remove(x)
                for x in tail:
                    new_run.append(x)
                new_p.append(new_run)
            run.remove(parts[bi])
            if child is run:
                later = children[ci + 1:]
            else:
                later = children[ci + 1:]
            for x in later:
                new_p.append(x)
            p_el.addnext(new_p)
            return True
    return False


def apply_outline(docx_path: Path, toc: list[list]) -> int:
    """Give the paragraphs that match the PDF's bookmarks an outline level (Word's navigation pane and
    PDF bookmarks use it); their formatting is not touched. A bookmark title that is the first line of a
    longer paragraph is split off into its own paragraph first. Returns how many bookmarks were placed."""
    if not toc:
        return 0
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    doc = Document(str(docx_path))
    pos, placed, changed = 0, 0, False
    for entry in toc:
        level, title = int(entry[0]), _norm(str(entry[1]))
        if not title:
            continue
        paras = list(doc.paragraphs)
        for i in range(pos, len(paras)):
            text = paras[i].text
            hit = _norm(text) == title
            if not hit and "\n" in text and _norm(text.split("\n", 1)[0]) == title:
                hit = _split_after_first_line(paras[i])
                changed = True
            if hit:
                ppr = paras[i]._p.get_or_add_pPr()
                for old in ppr.findall(qn("w:outlineLvl")):
                    ppr.remove(old)
                el = OxmlElement("w:outlineLvl")
                el.set(qn("w:val"), str(max(0, min(8, level - 1))))
                ppr.append(el)
                pos = i + 1
                placed += 1
                break
    if placed or changed:
        doc.save(str(docx_path))
    return placed


def simplify_font_lists(docx_path: Path) -> int:
    """LibreOffice keeps a CSS font list as one name ("Noto Sans;sans-serif"); Word needs a single family.
    The first family is kept. Returns how many names changed."""
    import zipfile

    from lxml import etree

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    changed = 0
    parts: dict[str, bytes] = {}
    with zipfile.ZipFile(docx_path) as z:
        infos = z.infolist()
        for info in infos:
            data = z.read(info.filename)
            if info.filename in ("word/document.xml", "word/styles.xml", "word/fontTable.xml", "word/numbering.xml") \
                    or info.filename.startswith(("word/header", "word/footer")):
                root = etree.fromstring(data)
                touched = False
                for el in root.iter(f"{{{W}}}rFonts", f"{{{W}}}font"):
                    for attr, val in list(el.attrib.items()):
                        if ";" in val and attr.split("}")[-1] in ("ascii", "hAnsi", "cs", "eastAsia", "name"):
                            el.set(attr, val.split(";")[0].strip().strip("'\""))
                            changed += 1
                            touched = True
                if touched:
                    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            parts[info.filename] = data
    if changed:
        tmp = docx_path.with_suffix(".tmp.docx")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for info in infos:
                z.writestr(info, parts[info.filename])
        tmp.replace(docx_path)
    return changed
