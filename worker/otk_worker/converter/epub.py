"""EPUB 3: a fixed-layout writer (one page per spine item) and a reader for joining a book into one HTML file."""

from __future__ import annotations

import base64
import html
import mimetypes
import posixpath
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from lxml import etree

XHTML = "http://www.w3.org/1999/xhtml"
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"


@dataclass
class FxlPage:
    svg: str                         # inline SVG markup for the page
    width: float                     # CSS px
    height: float
    resources: list[tuple[str, bytes]] = field(default_factory=list)   # (href inside OEBPS, bytes)


def write_fixed_layout(out: Path, pages: list[FxlPage], *, title: str, language: str = "en",
                       toc: list[list] | None = None) -> Path:
    """Fixed-layout EPUB 3 (rendition:layout pre-paginated): page n is spine item n."""
    book_id = f"urn:uuid:{uuid.uuid4()}"
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest, spine, files = [], [], []
    for i, pg in enumerate(pages, start=1):
        name = f"page{i:04d}.xhtml"
        body = re.sub(r"^<\?xml[^>]*>\s*", "", pg.svg.strip())
        doc = (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
               f'<html xmlns="{XHTML}" xmlns:epub="http://www.idpf.org/2007/ops" lang="{language}" xml:lang="{language}">'
               f'<head><meta charset="utf-8"/><title>{html.escape(title)} – {i}</title>'
               f'<meta name="viewport" content="width={int(round(pg.width))}, height={int(round(pg.height))}"/>'
               f'<style>html,body{{margin:0;padding:0}} svg{{display:block;width:{pg.width:.2f}px;height:{pg.height:.2f}px}}</style>'
               f'</head><body>{body}</body></html>')
        files.append((name, doc.encode("utf-8")))
        props = ' properties="svg"' if "<svg" in body else ""
        manifest.append(f'<item id="p{i}" href="{name}" media-type="application/xhtml+xml"{props}/>')
        spine.append(f'<itemref idref="p{i}"/>')
        for href, data in pg.resources:
            mime = mimetypes.guess_type(href)[0] or "application/octet-stream"
            rid = f"r{len(files)}"
            files.append((href, data))
            manifest.append(f'<item id="{rid}" href="{href}" media-type="{mime}"/>')
    nav_items = ""
    if toc:
        nav_items = "".join(f'<li><a href="page{max(1, int(t[2])):04d}.xhtml">{html.escape(str(t[1]))}</a></li>'
                            for t in toc if int(t[2]) >= 1)
    if not nav_items:
        nav_items = "".join(f'<li><a href="page{i:04d}.xhtml">Page {i}</a></li>' for i in range(1, len(pages) + 1))
    nav = (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="{XHTML}" '
           f'xmlns:epub="http://www.idpf.org/2007/ops" lang="{language}"><head><meta charset="utf-8"/><title>Contents</title></head>'
           f'<body><nav epub:type="toc" id="toc"><h1>Contents</h1><ol>{nav_items}</ol></nav></body></html>')
    files.append(("nav.xhtml", nav.encode("utf-8")))
    manifest.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
    opf = (f'<?xml version="1.0" encoding="utf-8"?>\n<package xmlns="{OPF}" version="3.0" unique-identifier="bookid" '
           f'prefix="rendition: http://www.idpf.org/vocab/rendition/#">'
           f'<metadata xmlns:dc="{DC}"><dc:identifier id="bookid">{book_id}</dc:identifier>'
           f'<dc:title>{html.escape(title)}</dc:title><dc:language>{language}</dc:language>'
           f'<meta property="dcterms:modified">{modified}</meta>'
           f'<meta property="rendition:layout">pre-paginated</meta><meta property="rendition:spread">none</meta>'
           f'</metadata><manifest>{"".join(manifest)}</manifest><spine>{"".join(spine)}</spine></package>')
    container = ('<?xml version="1.0" encoding="utf-8"?><container version="1.0" '
                 'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                 '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        for name, data in files:
            z.writestr(f"OEBPS/{name}", data, compress_type=zipfile.ZIP_DEFLATED)
    return out


# ------------------------------------------------------------------ reading
@dataclass
class Book:
    title: str
    language: str
    spine: list[str]                   # zip paths of the content documents in reading order
    zf: zipfile.ZipFile
    opf_dir: str
    nav: list[tuple[str, str]] = field(default_factory=list)   # (title, href)
    nav_path: str | None = None


def open_book(path: Path) -> Book:
    zf = zipfile.ZipFile(path)
    container = etree.fromstring(zf.read("META-INF/container.xml"))
    rootfile = container.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile").get("full-path")
    opf = etree.fromstring(zf.read(rootfile))
    opf_dir = posixpath.dirname(rootfile)
    items = {it.get("id"): it for it in opf.iter(f"{{{OPF}}}item")}
    spine = []
    for ref in opf.iter(f"{{{OPF}}}itemref"):
        it = items.get(ref.get("idref"))
        if it is not None and ref.get("linear", "yes") != "no":
            spine.append(posixpath.normpath(posixpath.join(opf_dir, unquote(it.get("href")))))
    title = (opf.findtext(f".//{{{DC}}}title") or "").strip()
    lang = (opf.findtext(f".//{{{DC}}}language") or "").strip()
    book = Book(title, lang, spine, zf, opf_dir)
    nav_item = next((it for it in items.values() if "nav" in (it.get("properties") or "").split()), None)
    if nav_item is not None:
        nav_path = posixpath.normpath(posixpath.join(opf_dir, unquote(nav_item.get("href"))))
        book.nav_path = nav_path
        try:
            nav = etree.fromstring(zf.read(nav_path), etree.XMLParser(recover=True))
            for a in nav.iter(f"{{{XHTML}}}a"):
                book.nav.append(("".join(a.itertext()).strip(), a.get("href") or ""))
        except Exception:
            pass
    return book


def data_uri(zf: zipfile.ZipFile, zpath: str) -> str | None:
    try:
        data = zf.read(zpath)
    except KeyError:
        return None
    mime = mimetypes.guess_type(zpath)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"
