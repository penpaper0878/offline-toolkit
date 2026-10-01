"""LibreOffice (headless) with a private, locked-down profile.

The profile turns off the update check, crash reporter, usage data and
macros, points every proxy at a dead port, and recalculates spreadsheets on
load (files written by other tools often have no cached formula results).
One conversion runs at a time per profile.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Callable

from . import engines

_LOCK = threading.Lock()

_REGISTRY = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="FirstStartWizardCompleted" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="CollectUsageInformation" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="CrashReport" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="ShowTipOfTheDay" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Jobs/Jobs/org.openoffice.Office.Jobs:Job['UpdateCheck']/Arguments"><prop oor:name="AutoCheckEnabled" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Recovery/RecoveryInfo"><prop oor:name="Enabled" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Recovery/AutoSave"><prop oor:name="Enabled" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Inet/Settings"><prop oor:name="ooInetProxyType" oor:op="fuse"><value>2</value></prop></item>
<item oor:path="/org.openoffice.Inet/Settings"><prop oor:name="ooInetHTTPProxyName" oor:op="fuse"><value>127.0.0.1</value></prop></item>
<item oor:path="/org.openoffice.Inet/Settings"><prop oor:name="ooInetHTTPProxyPort" oor:op="fuse"><value>9</value></prop></item>
<item oor:path="/org.openoffice.Inet/Settings"><prop oor:name="ooInetHTTPSProxyName" oor:op="fuse"><value>127.0.0.1</value></prop></item>
<item oor:path="/org.openoffice.Inet/Settings"><prop oor:name="ooInetHTTPSProxyPort" oor:op="fuse"><value>9</value></prop></item>
<item oor:path="/org.openoffice.Inet/Settings"><prop oor:name="ooInetNoProxy" oor:op="fuse"><value></value></prop></item>
</oor:items>
"""

# Filter names for --convert-to. No shell is involved, so no quotes around names with spaces.
DOCX = "docx:MS Word 2007 XML"
XLSX = "xlsx:Calc MS Excel 2007 XML"
PPTX = "pptx:Impress MS PowerPoint 2007 XML"
DOC = "doc:MS Word 97"
XLS = "xls:MS Excel 97"
PPT = "ppt:MS PowerPoint 97"
CALC_HTML = "html:HTML (StarCalc)"
PDF_EXPORT = {"writer": "writer_pdf_Export", "calc": "calc_pdf_Export", "impress": "impress_pdf_Export", "draw": "draw_pdf_Export"}
FAMILY = {"docx": "writer", "doc": "writer", "odt": "writer", "rtf": "writer",
          "xlsx": "calc", "xls": "calc", "ods": "calc",
          "pptx": "impress", "ppt": "impress", "odp": "impress"}


_profile: Path | None = None


def profile_dir() -> Path:
    """A private profile per worker process: LibreOffice locks its profile, and the app runs two workers."""
    global _profile
    if _profile is None:
        import atexit

        base = Path(os.environ.get("OTK_CACHE") or tempfile.gettempdir())
        _profile = base / f"lo-profile-{os.getpid()}"
        atexit.register(shutil.rmtree, _profile, True)
    reg = _profile / "user" / "registrymodifications.xcu"
    if not reg.exists():
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text(_REGISTRY, encoding="utf-8")
    return _profile


def pdf_filter(family: str, *, pdfa: int = 0, notes_pages: bool = False, lossless_images: bool = True,
               single_page_sheets: bool = False) -> str:
    """writer/calc/impress PDF export with explicit options (JSON syntax, LibreOffice >= 7.4)."""
    opts: dict = {
        "ExportBookmarks": {"type": "boolean", "value": "true"},
        "ExportBookmarksToPDFDestination": {"type": "boolean", "value": "false"},
        "UseTaggedPDF": {"type": "boolean", "value": "true"},
        "SelectPdfVersion": {"type": "long", "value": str(pdfa)},
        "ReduceImageResolution": {"type": "boolean", "value": "false"},
        "UseLosslessCompression": {"type": "boolean", "value": "true" if lossless_images else "false"},
        "EmbedStandardFonts": {"type": "boolean", "value": "true"},
        "ExportNotes": {"type": "boolean", "value": "false"},
        "IsSkipEmptyPages": {"type": "boolean", "value": "false"},
        "ExportFormFields": {"type": "boolean", "value": "true"},
    }
    if family == "impress":
        opts["ExportNotesPages"] = {"type": "boolean", "value": "true" if notes_pages else "false"}
    if family == "calc" and single_page_sheets:
        opts["SinglePageSheets"] = {"type": "boolean", "value": "true"}
    return f"pdf:{PDF_EXPORT[family]}:{json.dumps(opts, separators=(',', ':'))}"


def run(src: Path, work: Path, convert_to: str, *, infilter: str | None = None,
        check: Callable[[], None] = lambda: None, timeout: float | None = None):
    """Run one --convert-to into the (empty) folder `work`."""
    soffice = engines.require("soffice")
    work.mkdir(parents=True, exist_ok=True)
    cmd = [soffice, f"-env:UserInstallation={profile_dir().as_uri()}", "--headless", "--invisible", "--nologo",
           "--nodefault", "--norestore", "--nolockcheck", "--nofirststartwizard"]
    if infilter:
        cmd.append(f"--infilter={infilter}")
    cmd += ["--convert-to", convert_to, "--outdir", str(work), str(src)]
    if timeout is None:
        timeout = 300 + src.stat().st_size / 1_000_000 * 20
    with _LOCK:
        return engines.run(cmd, check=check, timeout=timeout, what="LibreOffice")


def sheet_csvs(src: Path, out_dir: Path, sheet_names: list[str], *, check: Callable[[], None] = lambda: None,
               separator: int = 9) -> dict[str, Path]:
    """Every sheet as CSV/TSV with the values *as shown* (number formats applied, formulas recalculated)."""
    work = out_dir / f"csv-{uuid.uuid4().hex[:8]}"
    # separator, quote ", UTF-8, first line 1, no formats, lang, quoted-as-text, special numbers,
    # save-as-shown=true, formulas=false, trim=false, all sheets (-1)
    opts = f"{separator},34,76,1,,0,false,true,true,false,false,-1"
    run(src, work, f"csv:Text - txt - csv (StarCalc):{opts}", check=check)
    files = {p.name: p for p in work.iterdir() if p.suffix.lower() == ".csv"}
    out: dict[str, Path] = {}
    for name in sheet_names:
        hit = files.get(f"{src.stem}-{name}.csv")
        if hit is None and len(sheet_names) == 1:
            hit = files.get(f"{src.stem}.csv") or next(iter(files.values()), None)
        if hit is not None:
            out[name] = hit
    return out


def convert(src: Path, out_dir: Path, convert_to: str, *, infilter: str | None = None,
            check: Callable[[], None] = lambda: None, timeout: float | None = None) -> Path:
    """Convert one file; returns the output path. Output extension = text before ':' in convert_to."""
    ext = convert_to.split(":", 1)[0]
    work = out_dir / f"lo-{uuid.uuid4().hex[:8]}"
    res = run(src, work, convert_to, infilter=infilter, check=check, timeout=timeout)
    produced = work / f"{src.stem}.{ext}"
    if not produced.exists():
        found = [p for p in work.iterdir() if p.suffix.lower() == f".{ext}"]
        if not found:
            raise engines.EngineFailed(
                f"LibreOffice could not convert {src.name} to {ext.upper()}. {res.stderr.strip()[-400:]}".strip())
        produced = found[0]
    final = out_dir / produced.name
    if final.exists():
        final = out_dir / f"{produced.stem}-{uuid.uuid4().hex[:6]}{produced.suffix}"
    shutil.move(str(produced), final)
    # Keep side files (e.g. images written next to an HTML export) together with the output.
    side = [p for p in work.iterdir()]
    if side:
        side_dir = out_dir / f"{final.stem}_files"
        side_dir.mkdir(exist_ok=True)
        for p in side:
            shutil.move(str(p), side_dir / p.name)
    shutil.rmtree(work, ignore_errors=True)
    return final
