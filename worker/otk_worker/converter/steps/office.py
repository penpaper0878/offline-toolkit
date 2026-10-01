"""LibreOffice steps: legacy Office to OOXML, Office to PDF and PDF/A, HTML to DOCX, spreadsheet HTML."""

from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path

from .. import libreoffice as lo
from .. import pdfa
from ..context import Artifact, StepContext
from . import step

_LEGACY_TARGET = {"doc": lo.DOCX, "xls": lo.XLSX, "ppt": lo.PPTX}


def macros_present(path: Path, fmt: str) -> bool:
    """VBA in the source (OOXML 'vbaProject.bin' or a legacy 'Macros'/'_VBA_PROJECT_CUR' storage)."""
    try:
        if fmt in ("docx", "xlsx", "pptx"):
            import zipfile
            with zipfile.ZipFile(path) as z:
                return any(n.lower().endswith("vbaproject.bin") for n in z.namelist())
        import olefile
        with olefile.OleFileIO(str(path)) as ole:
            names = {"/".join(s).lower() for s in ole.listdir()}
            return any(n.startswith(("macros", "_vba_project_cur", "vba")) for n in names)
    except Exception:
        return False


@step("legacy_to_ooxml")
def legacy_to_ooxml(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    ctx.progress(0.05, f"LibreOffice: {src.format.upper()} to {target.upper()}")
    if macros_present(src.path, src.format):
        ctx.expect("The VBA macros in the source are not carried into the macro-free file.")
    out = lo.convert(src.path, ctx.folder("lo"), _LEGACY_TARGET[src.format], check=ctx.check)
    return Artifact(target, [out])


@step("lo_to_pdf")
def lo_to_pdf(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    family = lo.FAMILY[src.format]
    ctx.progress(0.05, "LibreOffice: exporting PDF")
    filt = lo.pdf_filter(family, notes_pages=ctx.options.notes_pages)
    out = lo.convert(src.path, ctx.folder("lo"), filt, check=ctx.check)
    if family == "impress" and ctx.options.notes_pages:
        ctx.note("Each slide is followed by its notes page.")
    return Artifact("pdf", [out])


@step("lo_to_pdfa")
def lo_to_pdfa(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    family = lo.FAMILY[src.format]
    flavour = pdfa.FLAVOURS[target]
    ctx.progress(0.05, f"LibreOffice: exporting PDF/A-{flavour}")
    filt = lo.pdf_filter(family, pdfa=int(flavour[0]), notes_pages=ctx.options.notes_pages)
    out = lo.convert(src.path, ctx.folder("lo"), filt, check=ctx.check)
    if flavour == "3b" and ctx.options.pdfa_embed_source:
        attached = ctx.path(f"out-{flavour}.pdf")
        pdfa.finish(out, attached, flavour, source_file=ctx.source)
        ctx.note(f"The source file {ctx.source.name} is attached inside the PDF/A-3 file.")
        out = attached
    return Artifact(target, [out], {"pdfa": {"engine": "libreoffice"}})


@step("html_docx_lo")
def html_docx_lo(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    ctx.progress(0.05, "LibreOffice: HTML to DOCX")
    out = lo.convert(src.path, ctx.folder("lo"), lo.DOCX, infilter="HTML (StarWriter)", check=ctx.check)
    return Artifact("docx", [out])


@step("lo_calc_html")
def lo_calc_html(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    ctx.progress(0.05, "LibreOffice: spreadsheet to HTML")
    out = lo.convert(src.path, ctx.folder("lo"), lo.CALC_HTML, check=ctx.check)
    side = out.parent / f"{out.stem}_files"
    text = out.read_bytes().decode("utf-8", errors="replace")

    def inline(m):
        ref = m.group(2)
        for cand in (out.parent / ref, side / Path(ref).name):
            if cand.is_file():
                mime = mimetypes.guess_type(cand.name)[0] or "image/png"
                return f'{m.group(1)}="data:{mime};base64,{base64.b64encode(cand.read_bytes()).decode()}"'
        return m.group(0)

    text = re.sub(r'(src|href)="(?!data:|https?:|#|mailto:)([^"]+\.(?:png|jpg|jpeg|gif|svg))"', inline, text, flags=re.I)
    final = ctx.path("out.html")
    final.write_text(text, encoding="utf-8")
    return Artifact("html", [final])
