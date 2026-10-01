"""Make an HTML or SVG file self-contained before any engine sees it.

Local images, stylesheets and fonts are read from disk (relative to the
ORIGINAL file's folder) and embedded as data: URIs. Anything remote
(http, https, ftp, protocol-relative //) is removed and listed in the report;
no engine is ever given a URL it could fetch. Scripts are dropped: no output
format runs them, and the renderer has JavaScript switched off anyway.
"""

from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

from lxml import etree
from lxml import html as lhtml

REMOTE = re.compile(r"^\s*(https?:|ftp:|//)", re.I)
_CSS_URL = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""", re.I)
_CSS_IMPORT = re.compile(r"""@import\s+(?:url\()?\s*['"]?([^'");]+)['"]?\s*\)?\s*([^;]*);""", re.I)
_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([A-Za-z0-9_\-:.]+)""", re.I)
MAX_EMBED = 200 * 1024 * 1024
# Shown where a remote image was: a small grey box with a cross (24x24 PNG), so the gap stays visible.
PLACEHOLDER_PNG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAIAAABvFaqvAAAAjElEQVR42tXUUQqAMAgGYJMd0NN5Do/YQzDGnL9GI8rHsA/"
    "SPw9VpR3ViEhEHipmxrSpfgGZWTqRHLqagBU1zFDf4NLqD/2iF58WWUAJh+0trKCtjVaqJOufXsM/wCuBjIZ9DxrngjOBID/d1OJ66rDF9exii+sK"
    "ttg3pQdz2cY4hMWsfvJCtspJrNQJ5sVVBqA2fuUAAAAASUVORK5CYII=")


@dataclass
class Prepared:
    path: Path
    blocked: list[str] = field(default_factory=list)       # remote URLs removed
    missing: list[str] = field(default_factory=list)       # local files that do not exist
    embedded: list[str] = field(default_factory=list)      # local files inlined
    scripts_removed: int = 0
    encoding: str = "utf-8"

    def notes(self) -> list[str]:
        out = []
        if self.blocked:
            out.append(f"{len(self.blocked)} remote resource(s) were not loaded (offline): " + ", ".join(self.blocked[:10])
                       + (" …" if len(self.blocked) > 10 else ""))
        if self.missing:
            out.append(f"{len(self.missing)} local file(s) referenced by the page were not found: "
                       + ", ".join(self.missing[:10]))
        if self.scripts_removed:
            out.append(f"{self.scripts_removed} script(s) were removed (scripts do not run in converted documents).")
        return out


def decode_bytes(data: bytes, declared: str | None = None) -> tuple[str, str]:
    """(text, encoding): BOM, then the declared charset, then strict UTF-8, then detection."""
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        if data.startswith(bom):
            return data[len(bom):].decode(enc, errors="replace"), enc
    if declared:
        try:
            return data.decode(declared), declared.lower()
        except (LookupError, UnicodeDecodeError):
            pass
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    from charset_normalizer import from_bytes

    best = from_bytes(data).best()
    if best is not None:
        return str(best), best.encoding
    return data.decode("cp1252", errors="replace"), "cp1252"


def read_html_text(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    m = _META_CHARSET.search(data[:4096])
    return decode_bytes(data, m.group(1).decode("ascii") if m else None)


class _Inliner:
    def __init__(self, base_dir: Path, prep: Prepared):
        self.base = base_dir
        self.prep = prep
        self.cache: dict[str, str | None] = {}

    def resolve(self, ref: str) -> Path | None:
        ref = ref.strip()
        if ref.lower().startswith("file:"):
            p = Path(unquote(urlparse(ref).path.lstrip("/") if re.match(r"^file:///[A-Za-z]:", ref) else urlparse(ref).path))
        else:
            ref = ref.split("#", 1)[0].split("?", 1)[0]
            p = Path(unquote(ref))
            if not p.is_absolute():
                p = self.base / p
        return p

    def data_uri(self, ref: str) -> str | None:
        """data: URI for a local reference; None (and recorded) when remote or missing."""
        ref = ref.strip()
        if not ref or ref.startswith(("data:", "#", "about:", "javascript:", "mailto:")):
            return ref if ref.startswith(("data:", "#")) else None
        if REMOTE.match(ref):
            if ref not in self.prep.blocked:
                self.prep.blocked.append(ref)
            return None
        if ref in self.cache:
            return self.cache[ref]
        p = self.resolve(ref)
        uri = None
        if p is not None and p.is_file() and p.stat().st_size <= MAX_EMBED:
            data = p.read_bytes()
            mime = mimetypes.guess_type(p.name)[0] or _sniff_mime(data)
            if mime == "text/css":
                text, _ = decode_bytes(data)
                data = self.css(text, p.parent).encode("utf-8")
                mime = "text/css;charset=utf-8"
            uri = f"data:{mime};base64,{base64.b64encode(data).decode()}"
            self.prep.embedded.append(str(p))
        else:
            self.prep.missing.append(ref)
        self.cache[ref] = uri
        return uri

    def css(self, text: str, base: Path | None = None) -> str:
        saved = self.base
        if base is not None:
            self.base = base

        def imp(m):
            ref = m.group(1).strip()
            if REMOTE.match(ref):
                self.prep.blocked.append(ref)
                return ""
            p = self.resolve(ref)
            if p and p.is_file():
                inner, _ = decode_bytes(p.read_bytes())
                css = self.css(inner, p.parent)
                media = m.group(2).strip()
                return f"@media {media} {{\n{css}\n}}" if media else css
            self.prep.missing.append(ref)
            return ""

        def url(m):
            ref = m.group(2)
            uri = self.data_uri(ref)
            return f'url("{uri}")' if uri else 'url("")'

        try:
            out = _CSS_URL.sub(url, _CSS_IMPORT.sub(imp, text))
        finally:
            self.base = saved
        return out


def _sniff_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if b"<svg" in data[:1024]:
        return "image/svg+xml"
    if data[:4] in (b"wOFF", b"wOF2"):
        return "font/woff2" if data[:4] == b"wOF2" else "font/woff"
    if data[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        return "font/ttf"
    return "application/octet-stream"


_URL_ATTRS = {"img": ["src"], "image": ["href", "{http://www.w3.org/1999/xlink}href"], "input": ["src"],
              "video": ["src", "poster"], "audio": ["src"], "source": ["src"], "track": ["src"], "embed": ["src"],
              "object": ["data"], "iframe": ["src"], "use": ["href", "{http://www.w3.org/1999/xlink}href"],
              "feImage": ["href", "{http://www.w3.org/1999/xlink}href"]}


def prepare_html(src: Path, out: Path, *, base_dir: Path | None = None) -> Prepared:
    """Self-contained UTF-8 copy of an HTML file."""
    text, enc = read_html_text(src)
    prep = Prepared(out, encoding=enc)
    doc = lhtml.document_fromstring(text)
    base_el = doc.find(".//base")
    base = base_dir or src.parent
    if base_el is not None:
        href = base_el.get("href") or ""
        if href and not REMOTE.match(href):
            base = (base / unquote(href)).resolve() if not Path(href).is_absolute() else Path(href)
        base_el.getparent().remove(base_el)
    inl = _Inliner(base, prep)
    for el in list(doc.iter("script")):
        if el.get("type", "").lower() in ("application/ld+json", "application/json", "text/template"):
            continue
        prep.scripts_removed += 1
        if REMOTE.match(el.get("src") or ""):
            prep.blocked.append(el.get("src"))
        el.getparent().remove(el)
    for el in list(doc.iter("link")):
        rel = (el.get("rel") or "").lower()
        href = el.get("href") or ""
        if "stylesheet" in rel:
            if REMOTE.match(href):
                prep.blocked.append(href)
                el.getparent().remove(el)
                continue
            p = inl.resolve(href)
            if p and p.is_file():
                css, _ = decode_bytes(p.read_bytes())
                style = etree.Element("style")
                style.text = inl.css(css, p.parent)
                if el.get("media"):
                    style.set("media", el.get("media"))
                el.addprevious(style)
            else:
                prep.missing.append(href)
            el.getparent().remove(el)
        elif rel.split() and set(rel.split()) & {"icon", "preload", "prefetch", "preconnect", "dns-prefetch", "manifest"}:
            if REMOTE.match(href):
                prep.blocked.append(href)
            el.getparent().remove(el)
    for el in doc.iter("style"):
        if el.text:
            el.text = inl.css(el.text)
    for el in doc.iter():
        if not isinstance(el.tag, str):
            continue
        style = el.get("style")
        if style and "url(" in style:
            el.set("style", inl.css(style))
        tag = etree.QName(el).localname if "}" in el.tag else el.tag
        for attr in _URL_ATTRS.get(tag, []):
            ref = el.get(attr)
            if ref is None:
                continue
            uri = inl.data_uri(ref)
            if uri is None:
                el.set(attr, PLACEHOLDER_PNG if tag in ("img", "image", "input") else "")
                el.set("data-otk-removed", ref[:200])
            else:
                el.set(attr, uri)
        srcset = el.get("srcset")
        if srcset is not None:
            # Keep the first local candidate only (the renderer never picks a remote one).
            first = srcset.split(",")[0].strip().split(" ")[0]
            uri = inl.data_uri(first) if first else None
            if uri:
                el.set("srcset", uri)
            else:
                del el.attrib["srcset"]
    head = doc.find("head")
    if head is None:
        head = etree.Element("head")
        doc.insert(0, head)
    for m in list(head.iter("meta")):
        if m.get("charset") or (m.get("http-equiv") or "").lower() == "content-type":
            head.remove(m)
    meta = etree.Element("meta")
    meta.set("charset", "utf-8")
    head.insert(0, meta)
    html_bytes = lhtml.tostring(doc, encoding="unicode", method="html", doctype="<!DOCTYPE html>")
    out.write_text(html_bytes, encoding="utf-8")
    return prep


def prepare_svg(src: Path, out: Path, *, base_dir: Path | None = None) -> Prepared:
    """Self-contained SVG (external images and stylesheets inlined, remote ones removed)."""
    import gzip

    data = src.read_bytes()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    prep = Prepared(out)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True, remove_blank_text=False)
    root = etree.fromstring(data, parser)
    inl = _Inliner(base_dir or src.parent, prep)
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        local = etree.QName(el).localname
        if local == "script":
            prep.scripts_removed += 1
            el.getparent().remove(el)
            continue
        if local == "style" and el.text:
            el.text = inl.css(el.text)
        style = el.get("style")
        if style and "url(" in style:
            el.set("style", inl.css(style))
        for attr in _URL_ATTRS.get(local, []):
            ref = el.get(attr)
            if ref is None or ref.startswith("#"):
                continue
            uri = inl.data_uri(ref)
            if uri is None:
                el.set(attr, "")
            else:
                el.set(attr, uri)
    for pi in root.xpath("//processing-instruction('xml-stylesheet')"):
        href = re.search(r'href="([^"]+)"', pi.text or "")
        if href and REMOTE.match(href.group(1)):
            prep.blocked.append(href.group(1))
        pi.getparent().remove(pi) if pi.getparent() is not None else None
    out.write_bytes(etree.tostring(root, xml_declaration=True, encoding="utf-8"))
    return prep


def svg_size_pt(path: Path) -> tuple[float, float]:
    """Physical size of an SVG in points (CSS px = 0.75 pt); falls back to the viewBox, then 300×150 px."""
    root = etree.parse(str(path), etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True)).getroot()
    units = {"px": 0.75, "pt": 1.0, "pc": 12.0, "mm": 72 / 25.4, "cm": 72 / 2.54, "in": 72.0, "": 0.75}

    def parse(v: str | None) -> float | None:
        if not v:
            return None
        m = re.match(r"^\s*([0-9.]+)\s*(px|pt|pc|mm|cm|in|)\s*$", v)
        return float(m.group(1)) * units[m.group(2)] if m else None

    w, h = parse(root.get("width")), parse(root.get("height"))
    vb = root.get("viewBox")
    if vb:
        parts = [float(x) for x in re.split(r"[\s,]+", vb.strip()) if x]
        if len(parts) == 4:
            vw, vh = parts[2] * 0.75, parts[3] * 0.75
            if w is None and h is None:
                w, h = vw, vh
            elif w is None:
                w = h * parts[2] / parts[3]
            elif h is None:
                h = w * parts[3] / parts[2]
    return (w or 225.0, h or 112.5)
