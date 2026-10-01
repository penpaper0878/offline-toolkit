"""What a conversion step receives and returns.

A step turns one Artifact into another. Artifacts are files inside the job's
work folder: one file for most formats, several for "one image per page"
outputs, and a JSON file (plus extracted images) for the internal document
and OCR models. Steps never touch the user's original file or output folder.
"""

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from ..errors import InputError


@dataclass
class Artifact:
    format: str                      # planner format id (pdf, docx, docmodel, ...)
    paths: list[Path]
    info: dict = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return self.paths[0]

    def to_dict(self) -> dict:
        return {"format": self.format, "paths": [str(p) for p in self.paths], "info": self.info}

    @classmethod
    def from_dict(cls, d: dict) -> "Artifact":
        return cls(d["format"], [Path(p) for p in d["paths"]], dict(d.get("info") or {}))


PAPER_MM = {"a4": (210.0, 297.0), "letter": (215.9, 279.4), "legal": (215.9, 355.6), "a3": (297.0, 420.0),
            "a5": (148.0, 210.0)}


@dataclass
class Options:
    """Per-job conversion options (camelCase keys over RPC)."""

    mode: str = "exact"
    dpi: int = 300                       # page images and raster output
    jpeg_quality: int = 92
    background: str = "#ffffff"          # flattening colour for JPEG output
    ocr: bool = True                     # recognise text on scanned pages when the target holds text
    ocr_languages: list[str] = field(default_factory=lambda: ["eng"])
    ocr_min_confidence: float = 0.80     # words below this are flagged in the report
    notes_pages: bool = False            # PPT/PPTX -> PDF: add notes pages
    pdfa_embed_source: bool = False      # PDF/A-3b: attach the source file
    keep_pdfa_id: bool = True            # PDF/A -> PDF: keep the file byte-for-byte
    paper: str = "a4"                    # HTML/TXT -> PDF page size
    txt_split_tabs: bool = False         # TXT -> XLSX: split lines on tabs
    txt_lines_per_slide: int = 20        # TXT -> PPTX
    verify_appearance: bool = True       # render-and-compare check in exact mode

    @classmethod
    def from_dict(cls, d: dict | None) -> "Options":
        d = d or {}
        o = cls()
        keys = {"mode": "mode", "dpi": "dpi", "jpegQuality": "jpeg_quality", "background": "background", "ocr": "ocr",
                "ocrLanguages": "ocr_languages", "ocrMinConfidence": "ocr_min_confidence",
                "notesPages": "notes_pages", "pdfaEmbedSource": "pdfa_embed_source", "keepPdfaId": "keep_pdfa_id",
                "paper": "paper", "txtSplitTabs": "txt_split_tabs", "txtLinesPerSlide": "txt_lines_per_slide",
                "verifyAppearance": "verify_appearance"}
        for k, attr in keys.items():
            if k in d and d[k] is not None:
                setattr(o, attr, d[k])
        if o.mode not in ("exact", "editable"):
            raise InputError(f"Unknown fidelity mode '{o.mode}'.")
        o.dpi = int(o.dpi)
        if not 36 <= o.dpi <= 1200:
            raise InputError("DPI must be between 36 and 1200.")
        o.jpeg_quality = int(o.jpeg_quality)
        if not 1 <= o.jpeg_quality <= 100:
            raise InputError("JPEG quality must be between 1 and 100.")
        if o.paper not in PAPER_MM:
            raise InputError(f"Unknown paper size '{o.paper}'.")
        o.ocr_languages = [str(x) for x in (o.ocr_languages or ["eng"])]
        o.txt_lines_per_slide = max(1, int(o.txt_lines_per_slide))
        return o

    def to_dict(self) -> dict:
        return {"mode": self.mode, "dpi": self.dpi, "jpegQuality": self.jpeg_quality, "background": self.background,
                "ocr": self.ocr, "ocrLanguages": self.ocr_languages, "ocrMinConfidence": self.ocr_min_confidence,
                "notesPages": self.notes_pages, "pdfaEmbedSource": self.pdfa_embed_source,
                "keepPdfaId": self.keep_pdfa_id, "paper": self.paper, "txtSplitTabs": self.txt_split_tabs,
                "txtLinesPerSlide": self.txt_lines_per_slide, "verifyAppearance": self.verify_appearance}


class Host(Protocol):
    """Services the app provides to the worker (Chromium lives in the Electron main process)."""

    def render_pdf(self, html_path: Path, pdf_path: Path, *, paper: str, allow_dir: Path,
                   page_size: tuple[float, float] | None = None) -> dict: ...


@dataclass
class StepContext:
    work: Path                           # this file's work folder
    options: Options
    source: Path                         # the user's original file (read-only: relative resources resolve here)
    source_format: str
    check: Callable[[], None] = lambda: None
    report_progress: Callable[[float, str], None] = lambda f, m: None
    host: Host | None = None
    password: str | None = None
    notes: list[str] = field(default_factory=list)        # shown in the report ("remote image blocked", ...)
    expected: list[str] = field(default_factory=list)     # changes the output is known to have
    added_text: list[str] = field(default_factory=list)   # labels a writer added (e.g. "rows 1-20")
    low_confidence: list[dict] = field(default_factory=list)
    expected_checks: dict[str, str] = field(default_factory=dict)   # verification check id -> why it differs
    scanned_pages: list[int] = field(default_factory=list)
    _counter: itertools.count = field(default_factory=itertools.count)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def path(self, name: str) -> Path:
        """A fresh path in the work folder (never reused)."""
        with self._lock:
            n = next(self._counter)
        p = self.work / f"s{n:02d}-{name}"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def folder(self, name: str) -> Path:
        p = self.path(name)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)

    def expect(self, text: str) -> None:
        if text not in self.expected:
            self.expected.append(text)

    def expect_check(self, check_id: str, reason: str) -> None:
        """A verification check that is known to differ for this route (shown as an expected change)."""
        self.expected_checks[check_id] = reason
        self.expect(reason)

    def progress(self, fraction: float, message: str = "") -> None:
        self.check()
        self.report_progress(max(0.0, min(1.0, fraction)), message)
