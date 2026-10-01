"""PDF/A: making files (Ghostscript, pikepdf) and proving them (veraPDF).

A file is only called PDF/A when veraPDF says it complies with the requested
flavour. The runner saves anything else as `name.NOT-PDFA.pdf`.
"""

from __future__ import annotations

import json
import mimetypes
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import engines

FLAVOURS = {"pdfa1b": "1b", "pdfa2b": "2b", "pdfa3b": "3b"}


def srgb_icc() -> Path:
    import pikepdf

    p = Path(pikepdf.__file__).parent / "pdfa" / "data" / "sRGB.icc"  # ICC v2 (PDF/A-1 rejects v4)
    if p.is_file():
        return p
    import ocrmypdf
    return Path(ocrmypdf.__file__).parent / "data" / "sRGB.icc"


def _ps_string(s: str) -> str:
    return s.replace("\\", "/").replace("(", "\\(").replace(")", "\\)")


def _pdfa_def(work: Path, icc: Path, title: str) -> Path:
    local_icc = work / "srgb.icc"
    shutil.copyfile(icc, local_icc)
    ps = f"""%!
[ /Title ({_ps_string(title)}) /DOCINFO pdfmark
/ICCProfile ({_ps_string(str(local_icc))}) def
[/_objdef {{icc_PDFA}} /type /stream /OBJ pdfmark
[{{icc_PDFA}} << /N 3 >> /PUT pdfmark
[{{icc_PDFA}} ICCProfile (r) file /PUT pdfmark
[/_objdef {{OutputIntent_PDFA}} /type /dict /OBJ pdfmark
[{{OutputIntent_PDFA}} <<
  /Type /OutputIntent
  /S /GTS_PDFA1
  /DestOutputProfile {{icc_PDFA}}
  /OutputConditionIdentifier (sRGB IEC61966-2.1)
  /Info (sRGB IEC61966-2.1)
>> /PUT pdfmark
[{{Catalog}} << /OutputIntents [ {{OutputIntent_PDFA}} ] >> /PUT pdfmark
"""
    p = work / "PDFA_def.ps"
    p.write_text(ps, encoding="latin-1", errors="replace")
    return p


def ghostscript(src: Path, out: Path, flavour: str, work: Path, *, title: str = "",
                check: Callable[[], None] = lambda: None) -> Path:
    """Ghostscript pdfwrite to PDF/A-1b/2b/3b: fonts embedded, sRGB output intent, images not re-compressed."""
    gs = engines.require("gs")
    level = flavour[0]
    work.mkdir(parents=True, exist_ok=True)
    defs = _pdfa_def(work, srgb_icc(), title)
    cmd = [gs, f"-dPDFA={level}", "-dBATCH", "-dNOPAUSE", "-dNOOUTERSAVE", "-dSAFER", "-dQUIET",
           f"--permit-file-read={str(work).replace(chr(92), '/')}/",
           "-sColorConversionStrategy=RGB", "-sDEVICE=pdfwrite", "-dPDFACompatibilityPolicy=1",
           "-dPassThroughJPEGImages=true", "-dPassThroughJPXImages=true",
           "-dAutoFilterColorImages=false", "-dAutoFilterGrayImages=false",
           "-dColorImageFilter=/FlateEncode", "-dGrayImageFilter=/FlateEncode",
           "-dDownsampleColorImages=false", "-dDownsampleGrayImages=false", "-dDownsampleMonoImages=false",
           "-dEmbedAllFonts=true", "-dSubsetFonts=true", "-dAutoRotatePages=/None",
           f"-sOutputFile={out}", str(defs), str(src)]
    engines.run(cmd, check=check, timeout=600 + src.stat().st_size / 1_000_000 * 30, what="Ghostscript")
    if not out.exists() or out.stat().st_size == 0:
        raise engines.EngineFailed("Ghostscript did not produce a PDF/A file.")
    return out


def finish(src: Path, out: Path, flavour: str, *, source_file: Path | None = None, title: str | None = None) -> dict:
    """pikepdf pass: PDF/A declaration and repairs (pikepdf.pdfa), optional source attachment for 3b.

    Returns what was changed (for the report)."""
    import pikepdf

    info: dict = {"attached": None, "pikepdfValidator": None}
    with pikepdf.open(src) as pdf:
        if source_file is not None and flavour == "3b":
            _attach_source(pdf, source_file)
            info["attached"] = source_file.name
        if title:
            with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
                if not meta.get("dc:title"):
                    meta["dc:title"] = title
        try:
            from pikepdf import pdfa as pk_pdfa
            report = pk_pdfa.save(pdf, out, flavour, output_intent="sRGB")
            info["pikepdfValidator"] = "pass"
            prepared = getattr(report, "prepared", None)
            if prepared is not None and prepared.changed:
                info["repairs"] = _describe_prepare(prepared)
        except Exception as exc:  # pikepdf's allowlist validator is strict; veraPDF has the last word
            info["pikepdfValidator"] = f"not approved: {str(exc)[:300]}"
            if isinstance(exc, ImportError) and flavour == "3b":
                _associate_embedded_files(pdf)
            with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
                meta["pdfaid:part"] = flavour[0]
                meta["pdfaid:conformance"] = "B"
            pdf.save(out)
    return info


def _describe_prepare(p) -> list[str]:
    out = []
    if p.annotations_removed:
        out.append(f"removed hidden annotations: {dict(p.annotations_removed)}")
    if p.document_javascript_removed:
        out.append("removed document JavaScript")
    if p.interpolation_removed:
        out.append(f"removed image interpolation flags ({p.interpolation_removed})")
    if p.output_intent_replaced:
        out.append("set the sRGB output intent")
    if p.xmp_dropped:
        out.append(f"dropped XMP properties PDF/A does not allow: {', '.join(p.xmp_dropped)}")
    return out


def _attach_source(pdf, source: Path) -> None:
    """Embed the source as an associated file (/AFRelationship /Source), as PDF/A-3 allows."""
    import pikepdf
    from pikepdf import AttachedFileSpec, Name

    mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    fs = AttachedFileSpec.from_filepath(pdf, source, description="Source document", relationship=Name.Source)
    pdf.attachments[source.name] = fs
    fs.obj.EF.F.Subtype = Name("/" + mime)


def _associate_embedded_files(pdf) -> None:
    """PDF/A-3: every embedded file must be listed in the catalog's /AF array (pikepdf.pdfa does this too)."""
    import pikepdf

    af = pdf.Root.get("/AF")
    if af is None:
        af = pdf.Root.AF = pikepdf.Array()
    listed = {o.objgen for o in af if o.is_indirect}
    for name, fs in pdf.attachments.items():
        if fs.obj.is_indirect and fs.obj.objgen in listed:
            continue
        af.append(fs.obj)


def upgrade(src: Path, out: Path, flavour: str) -> None:
    """PDF/A-1b -> 2b/3b etc.: only the declaration changes; the content is untouched."""
    import pikepdf

    with pikepdf.open(src) as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta["pdfaid:part"] = flavour[0]
            meta["pdfaid:conformance"] = "B"
        pdf.save(out)


def strip_declaration(src: Path, out: Path) -> None:
    """PDF/A -> plain PDF when asked to drop the PDF/A identification."""
    import pikepdf

    with pikepdf.open(src) as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            for k in ("pdfaid:part", "pdfaid:conformance", "pdfaid:amd"):
                if k in meta:
                    del meta[k]
        pdf.save(out)


# ------------------------------------------------------------------ veraPDF
@dataclass
class Validation:
    flavour: str
    compliant: bool
    available: bool = True
    failed_rules: list[dict] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict:
        return {"flavour": self.flavour, "compliant": self.compliant, "available": self.available,
                "failedRules": self.failed_rules, "message": self.message}


def verapdf(path: Path, flavour: str, *, check: Callable[[], None] = lambda: None) -> Validation:
    cp = engines.verapdf_classpath()
    java = engines.find("java")
    if not cp or not java:
        return Validation(flavour, False, available=False,
                          message="veraPDF is not installed with this copy of the app, so PDF/A could not be proven.")
    cmd = [java.path, *engines.java_net_blockers(), "-Xss4m", "-cp", cp, "org.verapdf.apps.GreenfieldCliWrapper",
           "--flavour", flavour, "--format", "json", "--maxfailuresdisplayed", "5", str(path)]
    res = engines.run(cmd, check=check, timeout=600, what="veraPDF", ok_codes=(0, 1))
    try:
        start = res.stdout.index("{")
        data = json.loads(res.stdout[start:])
        vr = data["report"]["jobs"][0]["validationResult"][0]
    except (ValueError, KeyError, IndexError) as exc:
        return Validation(flavour, False, message=f"veraPDF report could not be read: {exc}. {res.stderr[-300:]}")
    failed = []
    for rule in vr.get("details", {}).get("ruleSummaries", []) or []:
        if rule.get("ruleStatus", rule.get("status", "FAILED")) in ("FAILED", "failed") or rule.get("failedChecks"):
            failed.append({"clause": rule.get("clause"), "test": rule.get("testNumber"),
                           "description": rule.get("description"), "failedChecks": rule.get("failedChecks"),
                           "specification": rule.get("specification")})
    return Validation(flavour, bool(vr.get("compliant")), failed_rules=failed, message=vr.get("statement", ""))
