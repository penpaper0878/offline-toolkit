"""Identify a file by its content (not its extension), and detect scans and encryption."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import UnsupportedFormat

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

EXT_TO_FORMAT = {
    ".pdf": "pdf", ".docx": "docx", ".docm": "docx", ".dotx": "docx", ".doc": "doc", ".dot": "doc",
    ".xlsx": "xlsx", ".xlsm": "xlsx", ".xltx": "xlsx", ".xls": "xls", ".xlt": "xls",
    ".pptx": "pptx", ".pptm": "pptx", ".potx": "pptx", ".ppsx": "pptx", ".ppt": "ppt", ".pps": "ppt", ".pot": "ppt",
    ".html": "html", ".htm": "html", ".xhtml": "html", ".txt": "txt", ".text": "txt", ".epub": "epub",
    ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".jpe": "jpeg", ".jfif": "jpeg", ".svg": "svg", ".svgz": "svg",
}

OUTPUT_EXT = {
    "pdf": ".pdf", "pdfa1b": ".pdf", "pdfa2b": ".pdf", "pdfa3b": ".pdf", "docx": ".docx", "xlsx": ".xlsx",
    "pptx": ".pptx", "html": ".html", "txt": ".txt", "epub": ".epub", "png": ".png", "jpeg": ".jpg", "svg": ".svg",
}


@dataclass
class Detected:
    format: str                    # planner source id (pdf, pdf_scanned, pdfa2b, docx, doc, ...)
    base: str                      # file family: pdf, docx, doc, xlsx, ...
    encrypted: bool = False
    pages: int | None = None
    scanned_pages: list[int] = field(default_factory=list)   # 0-based
    pdfa: str | None = None        # "1b" / "2b" / "3b" when the file claims PDF/A
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"format": self.format, "base": self.base, "encrypted": self.encrypted, "pages": self.pages,
                "scannedPages": self.scanned_pages, "pdfa": self.pdfa, "notes": self.notes}


def _ooxml_kind(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "mimetype" in names and z.read("mimetype").strip() == b"application/epub+zip":
                return "epub"
            if "word/document.xml" in names:
                return "docx"
            if "xl/workbook.xml" in names:
                return "xlsx"
            if "ppt/presentation.xml" in names:
                return "pptx"
            if "META-INF/container.xml" in names:
                return "epub"
    except zipfile.BadZipFile:
        return None
    return None


def _ole_kind(path: Path) -> tuple[str | None, bool]:
    """Legacy binary Office, or an encrypted OOXML file (both are OLE compound files)."""
    try:
        import olefile  # installed with msoffcrypto-tool
        with olefile.OleFileIO(str(path)) as ole:
            streams = {"/".join(s) for s in ole.listdir()}
            if "EncryptionInfo" in streams and "EncryptedPackage" in streams:
                return None, True  # encrypted OOXML; kind known only after decryption
            if "WordDocument" in streams:
                kind = "doc"
            elif "Workbook" in streams or "Book" in streams:
                kind = "xls"
            elif "PowerPoint Document" in streams:
                kind = "ppt"
            else:
                return None, False
    except Exception:
        return None, False
    encrypted = False
    try:
        import msoffcrypto
        with open(path, "rb") as fh:
            encrypted = msoffcrypto.OfficeFile(fh).is_encrypted()
    except Exception:
        pass
    return kind, encrypted


def _looks_text(head: bytes) -> bool:
    if head.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf")):
        return True
    return head.count(b"\x00") < max(1, len(head) // 100)


def sniff(path: Path) -> str:
    """Base format from the file's bytes; the extension only breaks ties for plain text."""
    with open(path, "rb") as fh:
        head = fh.read(4096)
    ext = path.suffix.lower()
    if head.startswith(b"%PDF-") or b"%PDF-" in head[:1024]:
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"PK\x03\x04"):
        kind = _ooxml_kind(path)
        if kind:
            return kind
        raise UnsupportedFormat(f"{path.name} is a ZIP archive, not a document this app can convert.")
    if head.startswith(OLE_MAGIC):
        kind, encrypted = _ole_kind(path)
        if kind:
            return kind
        if encrypted:
            return EXT_TO_FORMAT.get(ext, "docx") if EXT_TO_FORMAT.get(ext) in ("docx", "xlsx", "pptx") else "ooxml-encrypted"
        raise UnsupportedFormat(f"{path.name} is an Office file of a kind this app does not support.")
    if head[:2] == b"\x1f\x8b" and ext == ".svgz":
        return "svg"
    text = head.lstrip(b"\xef\xbb\xbf").lstrip().lower()
    if text.startswith(b"<?xml") or text.startswith(b"<svg") or text.startswith(b"<!doctype") or text.startswith(b"<html"):
        if b"<svg" in head.lower() and (ext in (".svg", ".svgz") or b"<html" not in head.lower()):
            return "svg"
        if b"<html" in head.lower() or text.startswith(b"<!doctype html"):
            return "html"
    if ext in (".html", ".htm", ".xhtml") and _looks_text(head):
        return "html"
    if _looks_text(head) and ext in (".txt", ".text", ".md", ".csv", ".log", ""):
        return "txt"
    if _looks_text(head) and ext not in EXT_TO_FORMAT:
        return "txt"
    known = EXT_TO_FORMAT.get(ext)
    if known and known not in ("docx", "xlsx", "pptx", "epub", "pdf", "png", "jpeg"):
        return known
    raise UnsupportedFormat(f"{path.name} is not a format this app can convert.")


def pdf_details(path: Path, password: str | None = None) -> Detected:
    """Encryption, PDF/A claim, page count and which pages are scans."""
    import pikepdf
    import pymupdf

    det = Detected(format="pdf", base="pdf")
    try:
        with pikepdf.open(path, password=password or "") as pdf:
            det.pages = len(pdf.pages)
            try:
                meta = pdf.open_metadata()
                part = meta.get("pdfaid:part")
                conf = (meta.get("pdfaid:conformance") or "").lower()
                if part in ("1", "2", "3") and conf in ("b", "a", "u"):
                    det.pdfa = f"{part}{'b' if conf in ('a', 'u', 'b') else conf}"
            except Exception:
                pass
            det.encrypted = pdf.is_encrypted
    except pikepdf.PasswordError:
        det.encrypted = True
        return det
    doc = pymupdf.open(path)
    if doc.needs_pass and not doc.authenticate(password or ""):
        det.encrypted = True
        return det
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        if len(text) >= 3:
            continue
        area = page.rect.width * page.rect.height
        covered = 0.0
        for info in page.get_image_info():
            b = info.get("bbox")
            if b:
                covered = max(covered, (b[2] - b[0]) * (b[3] - b[1]))
        if area and covered / area >= 0.5:
            det.scanned_pages.append(i)
    doc.close()
    if det.pdfa:
        det.format = f"pdfa{det.pdfa}" if det.pdfa in ("1b", "2b", "3b") else "pdf"
    if det.pages and len(det.scanned_pages) == det.pages:
        det.format = "pdf_scanned"
        det.notes.append("Every page is an image without a text layer (a scan).")
    elif det.scanned_pages:
        det.notes.append(f"{len(det.scanned_pages)} of {det.pages} pages are scans; they are OCR'd where text is needed.")
    return det


def detect(path: Path, password: str | None = None) -> Detected:
    base = sniff(path)
    if base == "pdf":
        return pdf_details(path, password)
    det = Detected(format=base, base=base)
    if base in ("doc", "xls", "ppt"):
        _, det.encrypted = _ole_kind(path)
    if base == "ooxml-encrypted" or (path.read_bytes()[:8] == OLE_MAGIC and base in ("docx", "xlsx", "pptx")):
        det.encrypted = True
        det.base = det.format = EXT_TO_FORMAT.get(path.suffix.lower(), "docx")
    return det
