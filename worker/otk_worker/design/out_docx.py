"""Word: the design on one page, every layer a separately editable object.

Background and photos -> floating pictures; shapes -> Word shapes; graphics -> a group of freeform
shapes, one per colour; text -> text boxes with the matched font, size, colour, style and alignment;
tables -> floating native tables. The fonts are embedded in the file (Word's obfuscated TrueType), so
the document shows the right typefaces on a computer that does not have them.

Text placement: with exact line spacing (what this writer sets) a word-processor text frame puts the
first baseline at 80% of the line pitch below its top, for every font (measured in LibreOffice; Word
splits an exact line 80/20 the same way). The frame is placed from that rule. Text boxes wrap
(wrap="square") and get spare width away from their alignment edge: the lines are broken already, and
LibreOffice 26 moves centred text in non-wrapping (auto-growing) Word text boxes by the box's offset.
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

from ..converter.ooxml import XMLNS, attr, next_id
from . import fonts_out, layout
from .out_pptx import _custgeom
from .vectorize import parse_path

EMU_PER_PT = 12700
DOCX_FIRST_BASELINE = 0.8       # share of the line pitch above the first baseline
WPG = "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"
WPS_URI = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
PIC_URI = "http://schemas.openxmlformats.org/drawingml/2006/picture"
NS = f'{XMLNS} xmlns:wpg="{WPG}"'
FONT_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
FONT_CT = "application/vnd.openxmlformats-officedocument.obfuscatedFont"


class _Units:
    def __init__(self, k: float):
        self.k = k

    def emu(self, px: float) -> int:
        return int(round(px * self.k * EMU_PER_PT))

    def pt(self, px: float) -> float:
        return px * self.k

    def tw(self, px: float) -> int:
        return int(round(px * self.k * 20))


def _clr(hex_color: str, alpha: float = 1.0) -> str:
    a = "" if alpha >= 0.999 else f'<a:alpha val="{int(round(max(0.0, alpha) * 100000))}"/>'
    return f'<a:srgbClr val="{hex_color.lstrip("#").upper()}">{a}</a:srgbClr>'


def _rot(deg: float) -> str:
    return f' rot="{int(round(deg * 60000)) % 21600000}"' if deg else ""


def _anchor(u: _Units, inner: str, x, y, w, h, *, z: int, behind: bool, name: str, uri: str) -> str:
    did = next_id()
    return (f'<wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="{max(2, z)}" '
            f'behindDoc="{1 if behind else 0}" locked="0" layoutInCell="1" allowOverlap="1">'
            f'<wp:simplePos x="0" y="0"/><wp:positionH relativeFrom="page"><wp:posOffset>{u.emu(x)}</wp:posOffset></wp:positionH>'
            f'<wp:positionV relativeFrom="page"><wp:posOffset>{u.emu(y)}</wp:posOffset></wp:positionV>'
            f'<wp:extent cx="{max(1, u.emu(w))}" cy="{max(1, u.emu(h))}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:wrapNone/><wp:docPr id="{did}" name="{attr(name)}"/><wp:cNvGraphicFramePr/>'
            f'<a:graphic><a:graphicData uri="{uri}">{inner}</a:graphicData></a:graphic></wp:anchor>')


def _run(drawing: str, requires: str | None) -> str:
    body = f"<w:drawing>{drawing}</w:drawing>"
    if requires:
        body = f'<mc:AlternateContent><mc:Choice Requires="{requires}">{body}</mc:Choice><mc:Fallback/></mc:AlternateContent>'
    return f"<w:r><w:rPr><w:noProof/></w:rPr>{body}</w:r>"


def picture(u: _Units, rid: str, lyr: dict, *, z: int, behind: bool) -> str:
    x, y, w, h = lyr["box"]
    pid = next_id()
    alpha = f'<a:alphaModFix amt="{int(lyr["opacity"] * 100000)}"/>' if lyr.get("opacity", 1.0) < 0.999 else ""
    inner = (f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{pid}" name="{attr(lyr["name"])}"/><pic:cNvPicPr/></pic:nvPicPr>'
             f'<pic:blipFill><a:blip r:embed="{rid}">{alpha}</a:blip><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
             f'<pic:spPr><a:xfrm{_rot(lyr.get("rotation", 0.0))}><a:off x="0" y="0"/><a:ext cx="{max(1, u.emu(w))}" cy="{max(1, u.emu(h))}"/></a:xfrm>'
             f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>')
    return _run(_anchor(u, inner, x, y, w, h, z=z, behind=behind, name=lyr["name"], uri=PIC_URI), None)


def _ln(u: _Units, lyr: dict) -> str:
    if lyr.get("stroke") and lyr.get("strokeWidth"):
        return (f'<a:ln w="{max(1, int(round(u.pt(lyr["strokeWidth"]) * EMU_PER_PT)))}">'
                f'<a:solidFill>{_clr(lyr["stroke"], lyr.get("opacity", 1.0))}</a:solidFill><a:miter lim="800000"/></a:ln>')
    return "<a:ln><a:noFill/></a:ln>"


def shape(u: _Units, lyr: dict, *, z: int, behind: bool) -> str:
    if lyr["shape"] == "line":
        x0, y0, x1, y1 = layout.line_points(lyr)
        x, y, w, h = min(x0, x1), min(y0, y1), max(0.01, abs(x1 - x0)), max(0.01, abs(y1 - y0))
        flips = (' flipH="1"' if x1 < x0 else "") + (' flipV="1"' if y1 < y0 else "")
        sp = (f'<wps:wsp><wps:cNvCnPr/><wps:spPr><a:xfrm{flips}><a:off x="0" y="0"/><a:ext cx="{max(1, u.emu(w))}" '
              f'cy="{max(1, u.emu(h))}"/></a:xfrm><a:prstGeom prst="line"><a:avLst/></a:prstGeom>{_ln(u, lyr)}</wps:spPr>'
              f'<wps:bodyPr/></wps:wsp>')
        return _run(_anchor(u, sp, x, y, w, h, z=z, behind=behind, name=lyr["name"], uri=WPS_URI), "wps")
    x, y, w, h, r = layout.shape_outline(lyr)
    geom = {"rect": "rect", "rounded": "roundRect", "ellipse": "ellipse"}.get(lyr["shape"], "rect")
    av = (f'<a:gd name="adj" fmla="val {int(round(min(50000, r / max(1e-6, min(w, h)) * 100000)))}"/>'
          if geom == "roundRect" else "")
    fill = f'<a:solidFill>{_clr(lyr["fill"], lyr.get("opacity", 1.0))}</a:solidFill>' if lyr.get("fill") else "<a:noFill/>"
    sp = (f'<wps:wsp><wps:cNvSpPr/><wps:spPr><a:xfrm{_rot(lyr.get("rotation", 0.0))}><a:off x="0" y="0"/>'
          f'<a:ext cx="{max(1, u.emu(w))}" cy="{max(1, u.emu(h))}"/></a:xfrm><a:prstGeom prst="{geom}"><a:avLst>{av}</a:avLst>'
          f'</a:prstGeom>{fill}{_ln(u, lyr)}</wps:spPr><wps:bodyPr/></wps:wsp>')
    return _run(_anchor(u, sp, x, y, w, h, z=z, behind=behind, name=lyr["name"], uri=WPS_URI), "wps")


def vector(u: _Units, lyr: dict, *, z: int, behind: bool) -> str:
    x, y, w, h = lyr["box"]
    nw, nh = lyr.get("natural") or (w, h)
    cx, cy = max(1, u.emu(w)), max(1, u.emu(h))
    kids = []
    for p in lyr["paths"]:
        segs = parse_path(p["d"])
        if segs:
            kids.append(f'<wps:wsp><wps:cNvSpPr/><wps:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
                        f'{_custgeom([segs], nw, nh)}<a:solidFill>{_clr(p["fill"], lyr.get("opacity", 1.0))}</a:solidFill>'
                        f'<a:ln><a:noFill/></a:ln></wps:spPr><wps:bodyPr/></wps:wsp>')
    grp = (f'<wpg:wgp><wpg:cNvGrpSpPr/><wpg:grpSpPr><a:xfrm{_rot(lyr.get("rotation", 0.0))}><a:off x="0" y="0"/>'
           f'<a:ext cx="{cx}" cy="{cy}"/><a:chOff x="0" y="0"/><a:chExt cx="{cx}" cy="{cy}"/></a:xfrm></wpg:grpSpPr>'
           f'{"".join(kids)}</wpg:wgp>')
    return _run(_anchor(u, grp, x, y, w, h, z=z, behind=behind, name=lyr["name"], uri=WPG), "wpg")


def run_props(u: _Units, family: str, weight: int, italic: bool, size_px: float, color: str, *, underline=False,
              rtl=False) -> str:
    face, bold, it = fonts_out.office_name(family, weight, italic)
    sz = max(2, int(round(u.pt(size_px) * 2)))
    p = [f'<w:rFonts w:ascii="{attr(face)}" w:hAnsi="{attr(face)}" w:eastAsia="{attr(face)}" w:cs="{attr(face)}"/>']
    if bold:
        p += ["<w:b/>", "<w:bCs/>"]
    if it:
        p += ["<w:i/>", "<w:iCs/>"]
    p.append(f'<w:color w:val="{color.lstrip("#").upper()}"/>')
    # Word sizes text in half points; where that rounding changes the size by 0.5% or more, the
    # characters are scaled back horizontally so a long line keeps its length.
    scale = int(round(100 * u.pt(size_px) * 2 / sz))
    if scale != 100:
        p.append(f'<w:w w:val="{scale}"/>')
    p.append('<w:kern w:val="2"/>')   # pair kerning from 1 pt up, as the design draws it (Word's default is none)
    p += [f'<w:sz w:val="{sz}"/>', f'<w:szCs w:val="{sz}"/>']
    if underline:
        p.append('<w:u w:val="single"/>')
    if rtl:
        p.append("<w:rtl/>")
    return f'<w:rPr>{"".join(p)}</w:rPr>'


def _para(text: str, rpr: str, *, jc: str, spacing: str, rtl: bool) -> str:
    bidi = "<w:bidi/>" if rtl else ""
    run = f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>' if text else ""
    return f'<w:p><w:pPr>{bidi}{spacing}<w:jc w:val="{jc}"/>{rpr}</w:pPr>{run}</w:p>'


def textbox(u: _Units, lyr: dict, *, z: int, behind: bool) -> str:
    st = lyr["style"]
    x, y, w, h = lyr["box"]
    g = layout.text_geometry(lyr)
    pitch = g["pitch"]
    top = g["baselines"][0] - DOCX_FIRST_BASELINE * pitch
    fh = max(2 * (y + h / 2 - top), pitch * len(g["lines"]))
    jc = {"left": "left", "center": "center", "right": "right", "justify": "both"}.get(g["align"], "left")
    if g["rtl"]:
        jc = {"left": "right", "right": "left"}.get(jc, jc)   # Word mirrors start/end in right-to-left paragraphs
    rpr = run_props(u, st["family"], st["weight"], st["italic"], g["size"], st["color"],
                    underline=st.get("underline", False), rtl=g["rtl"])
    spacing = f'<w:spacing w:before="0" w:after="0" w:line="{max(1, u.tw(pitch))}" w:lineRule="exact"/>'
    paras = "".join(_para(t, rpr, jc=jc, spacing=spacing, rtl=g["rtl"]) for t in g["lines"])
    # Spare width so a line drawn a little wider than measured does not wrap, added away from the alignment
    # edge; the centre moves along the box's rotated x axis so the text stays where it is.
    spare = max(0.1 * w, 1.5 * g["size"])
    edge = g["align"] if g["align"] != "justify" else ("right" if g["rtl"] else "left")
    grow_l, grow_r = {"left": (0.0, spare), "right": (spare, 0.0)}.get(edge, (spare / 2, spare / 2))
    a = math.radians(lyr.get("rotation", 0.0))
    shift = (grow_r - grow_l) / 2
    w2 = w + grow_l + grow_r
    x2 = x + w / 2 + shift * math.cos(a) - w2 / 2
    top2 = top + shift * math.sin(a)
    sp = (f'<wps:wsp><wps:cNvSpPr txBox="1"/><wps:spPr><a:xfrm{_rot(lyr.get("rotation", 0.0))}><a:off x="0" y="0"/>'
          f'<a:ext cx="{max(1, u.emu(w2))}" cy="{max(1, u.emu(fh))}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
          f'<a:noFill/><a:ln><a:noFill/></a:ln></wps:spPr><wps:txbx><w:txbxContent>{paras}</w:txbxContent></wps:txbx>'
          f'<wps:bodyPr rot="0" vert="horz" wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" anchor="t" anchorCtr="0">'
          f'<a:noAutofit/></wps:bodyPr></wps:wsp>')
    return _run(_anchor(u, sp, x2, top2, w2, fh, z=z, behind=behind, name=lyr["name"], uri=WPS_URI), "wps")


def table(u: _Units, lyr: dict) -> str:
    """A floating table placed on the page. Word (and LibreOffice reading DOCX) put the table's position
    at the first cell's text, so the left cell margin is added to it."""
    st, border = lyr["style"], lyr["border"]
    x, y, w, h = lyr["box"]
    xs, ys = layout.table_grid(lyr)
    pad = lyr.get("padding") or [6, 2, 6, 2]
    rows, cols = len(ys) - 1, len(xs) - 1
    bw8 = max(2, int(round(u.pt(border["width"]) * 8)))    # eighths of a point
    bc = border["color"].lstrip("#").upper()
    edge = f'w:val="single" w:sz="{bw8}" w:space="0" w:color="{bc}"'
    borders = "".join(f"<w:{t} {edge}/>" for t in ("top", "left", "bottom", "right", "insideH", "insideV"))
    grid: dict[tuple[int, int], dict] = {}
    for c in lyr["cells"]:
        for r in range(c["row"], min(rows, c["row"] + c.get("rowSpan", 1))):
            for k in range(c["col"], min(cols, c["col"] + c.get("colSpan", 1))):
                grid[(r, k)] = c
    trs = []
    for r in range(rows):
        tcs = []
        k = 0
        while k < cols:
            c = grid.get((r, k))
            span = c.get("colSpan", 1) if c is not None and c["col"] == k else 1
            width = xs[k + span] - xs[k]
            pr = [f'<w:tcW w:w="{u.tw(width)}" w:type="dxa"/>']
            if span > 1:
                pr.append(f'<w:gridSpan w:val="{span}"/>')
            if c is not None and c.get("rowSpan", 1) > 1:
                pr.append('<w:vMerge w:val="restart"/>' if r == c["row"] else "<w:vMerge/>")
            if c is not None and c.get("fill"):
                pr.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{c["fill"].lstrip("#").upper()}"/>')
            pr.append(f'<w:vAlign w:val="{ {"top": "top", "bottom": "bottom"}.get((c or {}).get("valign", "middle"), "center")}"/>')
            paras = []
            if c is not None and r == c["row"] and c["text"]:
                jc = {"left": "left", "center": "center", "right": "right"}.get(c.get("align", "left"), "left")
                rpr = run_props(u, st["family"], c.get("weight", 400), c.get("italic", False), st["size"],
                                c.get("color") or st["color"])
                for t in c["text"].split("\n"):
                    paras.append(_para(t, rpr, jc=jc, rtl=False,
                                       spacing='<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'))
            if not paras:
                paras = ['<w:p><w:pPr><w:spacing w:before="0" w:after="0"/><w:rPr><w:sz w:val="2"/></w:rPr></w:pPr></w:p>']
            tcs.append(f'<w:tc><w:tcPr>{"".join(pr)}</w:tcPr>{"".join(paras)}</w:tc>')
            k += span
        trs.append(f'<w:tr><w:trPr><w:trHeight w:val="{u.tw(ys[r + 1] - ys[r])}" w:hRule="exact"/></w:trPr>{"".join(tcs)}</w:tr>')
    grid_cols = "".join(f'<w:gridCol w:w="{u.tw(b - a)}"/>' for a, b in zip(xs, xs[1:]))
    mar = (f'<w:tblCellMar><w:top w:w="{u.tw(pad[1])}" w:type="dxa"/><w:left w:w="{u.tw(pad[0])}" w:type="dxa"/>'
           f'<w:bottom w:w="{u.tw(pad[3])}" w:type="dxa"/><w:right w:w="{u.tw(pad[2])}" w:type="dxa"/></w:tblCellMar>')
    return (f'<w:tbl {XMLNS}><w:tblPr><w:tblpPr w:leftFromText="0" w:rightFromText="0" w:topFromText="0" w:bottomFromText="0" '
            f'w:vertAnchor="page" w:horzAnchor="page" w:tblpX="{u.tw(x + pad[0])}" w:tblpY="{u.tw(y)}"/>'
            f'<w:tblOverlap w:val="overlap"/><w:tblW w:w="{u.tw(w)}" w:type="dxa"/><w:tblInd w:w="0" w:type="dxa"/>'
            f'<w:tblBorders>{borders}</w:tblBorders><w:tblLayout w:type="fixed"/>{mar}'
            f'<w:tblLook w:val="0000" w:firstRow="0" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" w:noHBand="1" w:noVBand="1"/>'
            f'</w:tblPr><w:tblGrid>{grid_cols}</w:tblGrid>{"".join(trs)}</w:tbl>')


def _embed_fonts(doc, scene: dict) -> list[str]:
    """Put the scene's fonts into the file (Word's obfuscated TrueType parts)."""
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part
    from docx.oxml import parse_xml
    from docx.oxml.ns import qn

    pkg = doc.part.package
    table_part = next((p for p in pkg.iter_parts() if str(p.partname) == "/word/fontTable.xml"), None)
    if table_part is None:
        return ["The fonts could not be embedded (the document template has no font table)."]
    from lxml import etree

    root = etree.fromstring(table_part.blob)
    slots = {(False, False): "embedRegular", (True, False): "embedBold", (False, True): "embedItalic",
             (True, True): "embedBoldItalic"}
    entries: dict[str, etree._Element] = {}
    for i, (fam, w, it) in enumerate(fonts_out.faces_used(scene), start=1):
        path = fonts_out.static_font(fam, w, it)
        if path is None or path.suffix.lower() != ".ttf":
            continue
        face, bold, ital = fonts_out.office_name(fam, w, it)
        key = "{" + str(uuid.uuid4()).upper() + "}"
        part = Part(PackURI(f"/word/fonts/font{i}.odttf"), FONT_CT, fonts_out.obfuscate(path.read_bytes(), key), pkg)
        rid = table_part.relate_to(part, FONT_REL)
        font = entries.get(face)
        if font is None:
            for old in root.findall(qn("w:font")):
                if old.get(qn("w:name")) == face:
                    root.remove(old)
            font = etree.SubElement(root, qn("w:font"))
            font.set(qn("w:name"), face)
            etree.SubElement(font, qn("w:charset")).set(qn("w:val"), "00")
            etree.SubElement(font, qn("w:family")).set(qn("w:val"), "auto")
            etree.SubElement(font, qn("w:pitch")).set(qn("w:val"), "variable")
            entries[face] = font
        emb = etree.SubElement(font, qn(f"w:{slots[(bold, ital)]}"))
        emb.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", rid)
        emb.set(qn("w:fontKey"), key)
    table_part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    settings = doc.settings.element
    if settings.find(qn("w:embedTrueTypeFonts")) is None:
        settings.insert(0, parse_xml(f'<w:embedTrueTypeFonts {XMLNS}/>'))
    return []


def write(scene: dict, project: Path, out: Path, *, embed_fonts: bool = True) -> tuple[Path, list[str]]:
    from docx import Document
    from docx.oxml import parse_xml
    from docx.oxml.ns import qn
    from docx.shared import Twips

    k, note = layout.page_scale(scene, max_in=22, min_in=1)
    u = _Units(k)
    W, H = scene["page"]["width"], scene["page"]["height"]
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Twips(u.tw(W)), Twips(u.tw(H))
    sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Twips(0)
    sec.header_distance = sec.footer_distance = Twips(0)
    body = doc.element.body
    for p in list(body.findall(qn("w:p"))):
        body.remove(p)
    layers = layout.visible_layers(scene)
    first_table = next((i for i, lyr in enumerate(layers) if lyr["type"] == "table"), None)
    runs, tables = [], []
    for i, lyr in enumerate(layers):
        behind = first_table is not None and i < first_table or lyr.get("role") == "background"
        z = 10 + i
        t = lyr["type"]
        if t == "image":
            rid, _ = doc.part.get_or_add_image(str(project / lyr["asset"]))
            runs.append(picture(u, rid, lyr, z=z, behind=behind))
        elif t == "shape":
            runs.append(shape(u, lyr, z=z, behind=behind))
        elif t == "vector":
            runs.append(vector(u, lyr, z=z, behind=behind))
        elif t == "text":
            runs.append(textbox(u, lyr, z=z, behind=behind))
        elif t == "table":
            tables.append(table(u, lyr))
    sect = body.find(qn("w:sectPr"))
    for tb in tables:
        sect.addprevious(parse_xml(tb))
    para = parse_xml(f'<w:p {NS}><w:pPr><w:spacing w:before="0" w:after="0" w:line="20" w:lineRule="exact"/>'
                     f'<w:rPr><w:sz w:val="2"/></w:rPr></w:pPr>{"".join(runs)}</w:p>')
    sect.addprevious(para)
    notes = [note] if note else []
    if any(lyr["type"] == "text" and abs(lyr.get("rotation", 0.0)) > 0.05 for lyr in layers):
        notes.append("Rotated text boxes are rotated in Word, but LibreOffice Writer shows their text level; "
                     "the PowerPoint export keeps the rotation in both.")
    if embed_fonts:
        notes += _embed_fonts(doc, scene)
    doc.core_properties.title = scene["source"].get("name", "")
    doc.save(out)
    return out, notes
