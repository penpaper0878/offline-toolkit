"""Running conversion jobs: pre-flight, passwords, safe copies, steps, PDF/A proof, verification, packaging.

Each job has a folder (jobs/<jobId>/) with a journal. Every finished step is
recorded with the SHA-256 of its outputs, so a resumed job (after a cancel or
a crash) skips finished files and finished steps. The user's files are never
modified: the job works on copies, and outputs are written to the output
folder under names that never overwrite anything.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable

from ..common.paths import safe_stem, unique_path
from ..errors import Cancelled, InputError, ToolkitError, UnsupportedFormat
from ..resources import resources_dir
from . import engines, formats, htmlprep, ocr, pdfa
from .context import Artifact, Host, Options, StepContext
from .planner import Catalog, NoRouteError, Route
from .steps import load_all

JOURNAL_VERSION = 1


@lru_cache(maxsize=1)
def catalog() -> Catalog:
    return Catalog.from_dir(resources_dir() / "defaults" / "conversion")


# Engines each planner engine id needs at run time.
ENGINE_NEEDS = {"libreoffice": ["soffice"], "pandoc": ["pandoc"], "ghostscript": ["gs"], "resvg": ["resvg"],
                "ocr": ["tesseract"], "ocrmypdf": ["tesseract", "gs"], "chromium": []}


class PasswordNeeded(ToolkitError):
    code = "password_needed"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ pre-flight
def source_format(det: formats.Detected) -> str:
    return det.format


def plan_for(det: formats.Detected, target: str, mode: str) -> Route:
    cat = catalog()
    src = source_format(det)
    if src == target or (src.startswith("pdfa") and target == src):
        raise NoRouteError("The file is already in that format.")
    return cat.plan(src, target, mode)


def preflight(path: str, target: str, mode: str, password: str | None = None, options: dict | None = None) -> dict:
    """What will happen to one file: detected format, route, engines, expected losses, problems."""
    p = Path(path)
    out: dict = {"path": path, "name": p.name, "size": p.stat().st_size if p.exists() else None}
    try:
        det = formats.detect(p, password)
    except UnsupportedFormat as exc:
        out.update(ok=False, error=exc.message, code=exc.code)
        return out
    except FileNotFoundError:
        out.update(ok=False, error="The file does not exist.", code="not_found")
        return out
    out["detected"] = det.to_dict()
    if det.encrypted and det.base != "pdf":
        out["needsPassword"] = not _office_password_ok(p, password)
    elif det.encrypted and det.pages is None:
        out["needsPassword"] = True
    if out.get("needsPassword"):
        out.update(ok=False, code="password_needed",
                   error="This file is protected with a password." if not password else "The password is not correct.")
        return out
    try:
        route = plan_for(det, target, mode)
    except NoRouteError as exc:
        out.update(ok=False, error=str(exc), code="no_route")
        return out
    cat = catalog()
    out["route"] = route_dict(route)
    out["mode"] = route.mode
    out["losses"] = [{"feature": loss.feature, "label": loss.label, "level": loss.level}
                     for loss in cat.potential_losses(route)]
    out["stepLosses"] = cat.step_losses(route)
    problems = []
    for step in route.steps:
        for need in ENGINE_NEEDS.get(step.engine, []):
            if not engines.find(need):
                problems.append(f"{engines._HINT.get(need, need)} is missing (needed for {step.summary.split(':')[0]}).")
    opts = Options.from_dict(options)
    if any(s.engine in ("ocr", "ocrmypdf") for s in route.steps) or (det.scanned_pages and opts.ocr):
        have = set(ocr.languages_available())
        missing = [lg for lg in opts.ocr_languages if lg not in have]
        if missing:
            problems.append(f"OCR language(s) not installed: {', '.join(missing)}.")
    if target in pdfa.FLAVOURS and not engines.verapdf_classpath():
        problems.append("veraPDF is missing, so PDF/A compliance cannot be proven (the file would be saved as NOT-PDFA).")
    out["problems"] = problems
    out["ok"] = not problems
    out["notes"] = det.notes
    return out


def route_dict(route: Route) -> dict:
    cat = catalog()
    return {"source": route.source, "target": route.target, "mode": route.mode, "chain": route.chain,
            "cost": route.cost, "override": route.override_reason,
            "steps": [{"edge": s.id, "from": s.src, "to": s.dst, "engine": s.engine,
                       "engineLabel": cat.engines.get(s.engine, {}).get("label", s.engine), "summary": s.summary}
                      for s in route.steps]}


def _office_password_ok(path: Path, password: str | None) -> bool:
    if not password:
        return False
    try:
        import io

        import msoffcrypto
        with open(path, "rb") as fh:
            of = msoffcrypto.OfficeFile(fh)
            of.load_key(password=password)
            of.decrypt(io.BytesIO())
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ safe copies
def safe_copy(src: Path, det: formats.Detected, work: Path, password: str | None) -> tuple[Path, list[str]]:
    """ASCII-named copy inside the job folder, decrypted when a password was given."""
    ext = formats.OUTPUT_EXT.get(det.base) or {"doc": ".doc", "xls": ".xls", "ppt": ".ppt"}.get(det.base) or src.suffix
    if det.base in ("svg",) and src.suffix.lower() == ".svgz":
        ext = ".svgz"
    dest = work / f"source{ext}"
    notes: list[str] = []
    if det.encrypted:
        if det.base == "pdf":
            import pikepdf
            try:
                with pikepdf.open(src, password=password or "") as pdf:
                    pdf.save(dest)
            except pikepdf.PasswordError as exc:
                raise PasswordNeeded("The password is not correct." if password else
                                     "This PDF is protected with a password.") from exc
        else:
            import msoffcrypto
            try:
                with open(src, "rb") as fin, open(dest, "wb") as fout:
                    of = msoffcrypto.OfficeFile(fin)
                    of.load_key(password=password or "")
                    of.decrypt(fout)
            except Exception as exc:
                dest.unlink(missing_ok=True)
                raise PasswordNeeded("The password is not correct." if password else
                                     "This file is protected with a password.") from exc
        notes.append("The file was opened with its password; the converted file is not password-protected.")
    else:
        shutil.copyfile(src, dest)
    return dest, notes


def prepare_source(ctx: StepContext, copy: Path, fmt: str) -> Path:
    """HTML and SVG sources: make them self-contained (resources resolved next to the ORIGINAL file)."""
    if fmt == "html":
        out = ctx.work / "source-prepared.html"
        prep = htmlprep.prepare_html(copy, out, base_dir=ctx.source.parent)
    elif fmt == "svg":
        out = ctx.work / "source-prepared.svg"
        prep = htmlprep.prepare_svg(copy, out, base_dir=ctx.source.parent)
    else:
        return copy
    for n in prep.notes():
        ctx.note(n)
    if prep.blocked:
        ctx.expect("Remote resources were not loaded (the app works offline); they are listed in the report.")
    return out


# ------------------------------------------------------------------ journal
class Journal:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.data: dict = {"version": JOURNAL_VERSION, "files": {}}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                pass

    def file(self, key: str) -> dict:
        return self.data["files"].setdefault(key, {"steps": [], "status": "pending"})

    def save(self) -> None:
        with self.lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)


def _ctx_state(ctx: StepContext) -> dict:
    return {"notes": ctx.notes, "expected": ctx.expected, "addedText": ctx.added_text,
            "lowConfidence": ctx.low_confidence, "expectedChecks": ctx.expected_checks}


def _restore_ctx(ctx: StepContext, st: dict) -> None:
    ctx.notes[:] = st.get("notes", [])
    ctx.expected[:] = st.get("expected", [])
    ctx.added_text[:] = st.get("addedText", [])
    ctx.low_confidence[:] = st.get("lowConfidence", [])
    ctx.expected_checks.update(st.get("expectedChecks", {}))


# ------------------------------------------------------------------ one file
@dataclass
class FileResult:
    source: str
    status: str                       # done | failed | needs_password | cancelled | skipped
    output: str | None = None
    outputs: list[str] = field(default_factory=list)
    report: str | None = None
    report_json: str | None = None
    verdict: str | None = None        # perfect | expected | review
    message: str = ""
    code: str | None = None
    route: dict | None = None
    seconds: float = 0.0
    work: str | None = None
    final_format: str | None = None
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"source": self.source, "status": self.status, "output": self.output, "outputs": self.outputs,
                "report": self.report, "reportJson": self.report_json, "verdict": self.verdict,
                "message": self.message, "code": self.code, "route": self.route, "seconds": round(self.seconds, 2),
                "summary": self.summary, "finalFormat": self.final_format}


def run_steps(ctx: StepContext, route: Route, start: Artifact, jfile: dict, journal: Journal | None,
              progress: Callable[[float, str], None]) -> Artifact:
    steps = load_all()
    art = start
    done = {s["index"]: s for s in jfile.get("steps", [])}
    n = len(route.steps)
    for i, edge in enumerate(route.steps):
        ctx.check()
        rec = done.get(i)
        if rec and rec.get("edge") == edge.id and _outputs_intact(rec):
            art = Artifact.from_dict(rec["artifact"])
            _restore_ctx(ctx, rec.get("ctx", {}))
            continue
        label = f"Step {i + 1}/{n}: {edge.summary.split(':')[0].split(';')[0]}"
        progress(i / n, label)
        ctx.report_progress = lambda f, m, i=i: progress((i + max(0.0, min(1.0, f))) / n, f"{label} — {m}" if m else label)
        art = steps[edge.id](ctx, art, edge.dst)
        if journal is not None:
            jfile["steps"] = [s for s in jfile.get("steps", []) if s["index"] < i]
            jfile["steps"].append({"index": i, "edge": edge.id, "artifact": art.to_dict(),
                                   "sha256": [sha256(p) for p in art.paths if p.is_file()], "ctx": _ctx_state(ctx)})
            journal.save()
    return art


def _outputs_intact(rec: dict) -> bool:
    try:
        paths = [Path(p) for p in rec["artifact"]["paths"]]
        hashes = rec.get("sha256", [])
        files = [p for p in paths if p.is_file()]
        return len(files) == len(paths) and [sha256(p) for p in files] == hashes
    except (KeyError, OSError):
        return False


def _pdfa_retry(ctx: StepContext, target: str, src_copy: Path, src_fmt: str, art: Artifact) -> Artifact | None:
    """Second route when veraPDF rejects the first file."""
    flavour = pdfa.FLAVOURS[target]
    steps = load_all()
    try:
        if art.info.get("pdfa", {}).get("engine") == "libreoffice":
            ctx.note("LibreOffice's PDF/A did not pass veraPDF; retrying through Ghostscript.")
            plain = steps["lo_to_pdf"](ctx, Artifact(src_fmt, [src_copy]), "pdf")
            return steps["gs_pdfa"](ctx, plain, target)
        # Ghostscript (or a metadata-only upgrade) failed: let pikepdf repair the original instead.
        ctx.note("The first PDF/A attempt did not pass veraPDF; retrying with pikepdf's PDF/A repair.")
        base = src_copy if src_fmt in ("pdf", "pdfa1b", "pdfa2b", "pdfa3b", "pdf_scanned") else art.path
        out = ctx.path(f"retry-{flavour}.pdf")
        pdfa.finish(base, out, flavour, source_file=ctx.source if ctx.options.pdfa_embed_source else None)
        return Artifact(target, [out])
    except ToolkitError as exc:
        ctx.note(f"The PDF/A retry failed: {exc.message}")
        return None


def convert_file(source: Path, target: str, options: Options, work: Path, out_dir: Path, *,
                 password: str | None = None, host: Host | None = None, check: Callable[[], None] = lambda: None,
                 progress: Callable[[float, str], None] = lambda f, m: None, journal: Journal | None = None,
                 key: str | None = None, verify: bool = True) -> FileResult:
    t0 = time.monotonic()
    key = key or str(source)
    jfile = journal.file(key) if journal is not None else {"steps": []}
    work.mkdir(parents=True, exist_ok=True)
    result = FileResult(source=str(source), status="failed", work=str(work))
    if jfile.get("status") == "done" and jfile.get("result") and all(Path(p).exists() for p in jfile["result"].get("outputs", [])):
        r = jfile["result"]
        res = FileResult(source=str(source), status="done", output=r.get("output"), outputs=r.get("outputs", []),
                         report=r.get("report"), report_json=r.get("reportJson"), verdict=r.get("verdict"),
                         message="Already converted (resumed job).", route=r.get("route"), summary=r.get("summary", {}),
                         final_format=r.get("finalFormat"))
        return res
    try:
        progress(0.0, "Checking the file")
        det = formats.detect(source, password)
        if det.encrypted and det.base == "pdf" and det.pages is None and not password:
            raise PasswordNeeded("This PDF is protected with a password.")
        if det.encrypted and det.base != "pdf" and not password:
            raise PasswordNeeded("This file is protected with a password.")
        route = plan_for(det, target, options.mode)
        result.route = route_dict(route)
        copy, notes = safe_copy(source, det, work, password)
        if det.encrypted and det.base == "pdf":
            det = formats.pdf_details(copy)
            route = plan_for(det, target, options.mode)
            result.route = route_dict(route)
        ctx = StepContext(work=work / "steps", options=options, source=source, source_format=det.format, check=check,
                          host=host, password=None, scanned_pages=list(det.scanned_pages))
        ctx.work.mkdir(parents=True, exist_ok=True)
        for n in notes + det.notes:
            ctx.note(n)
        prepared = prepare_source(ctx, copy, det.base)
        art = run_steps(ctx, route, Artifact(det.format, [prepared]), jfile, journal, lambda f, m: progress(0.05 + 0.7 * f, m))
        validation = None
        final_target = target
        if target in pdfa.FLAVOURS:
            progress(0.78, "veraPDF: checking PDF/A compliance")
            validation = pdfa.verapdf(art.path, pdfa.FLAVOURS[target], check=check)
            if not validation.compliant and validation.available:
                retry = _pdfa_retry(ctx, target, copy, det.format, art)
                if retry is not None:
                    v2 = pdfa.verapdf(retry.path, pdfa.FLAVOURS[target], check=check)
                    if v2.compliant:
                        art, validation = retry, v2
                    else:
                        validation.failed_rules = validation.failed_rules or v2.failed_rules
        report_data = None
        if verify:
            from .verify import verify_conversion
            progress(0.82, "Verifying the result")
            report_data = verify_conversion(ctx, source=copy, source_format=det.format, output=art,
                                            target=target, route=route, validation=validation, catalog=catalog())
        progress(0.95, "Saving")
        result.outputs, result.output = package(art, out_dir, source, target, validation)
        result.final_format = art.format
        if report_data is not None:
            from .verify import report as report_mod
            report_data["outputs"] = result.outputs
            report_data["seconds"] = round(time.monotonic() - t0, 2)
            html_path, json_path = report_mod.write(report_data, Path(result.output))
            result.report, result.report_json = str(html_path), str(json_path)
            result.verdict = report_data["verdict"]
            result.summary = report_data.get("summary", {})
        result.status = "done"
        result.message = "Converted" if validation is None or validation.compliant else \
            "Converted, but the file is NOT PDF/A compliant (saved with .NOT-PDFA in its name)."
        if validation is not None and not validation.compliant:
            result.verdict = "review"
    except Cancelled:
        result.status, result.message, result.code = "cancelled", "Cancelled", "cancelled"
    except PasswordNeeded as exc:
        result.status, result.message, result.code = "needs_password", exc.message, exc.code
    except NoRouteError as exc:
        result.status, result.message, result.code = "failed", str(exc), "no_route"
    except ToolkitError as exc:
        result.status, result.message, result.code = "failed", exc.message, exc.code
    except Exception as exc:  # report per file; the batch goes on
        import traceback
        result.status, result.message, result.code = "failed", f"Unexpected error: {exc}", "internal"
        (work / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
    result.seconds = time.monotonic() - t0
    if journal is not None:
        jfile["status"] = result.status
        if result.status == "done":
            jfile["result"] = result.to_dict()
        journal.save()
    return result


def _final_name(source: Path, target: str) -> str:
    return safe_stem(source.stem, "converted")


def package(art: Artifact, out_dir: Path, source: Path, target: str, validation) -> tuple[list[str], str]:
    """Copy the result into the output folder (never overwriting); several page files become one ZIP."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _final_name(source, target)
    ext = formats.OUTPUT_EXT[target]
    if validation is not None and not validation.compliant:
        stem += ".NOT-PDFA"
    if len(art.paths) == 1:
        dest = unique_path(out_dir, stem, ext)
        _copy_atomic(art.path, dest)
        return [str(dest)], str(dest)
    dest = unique_path(out_dir, f"{stem}-pages", ".zip")
    tmp = dest.with_name(dest.name + ".part")
    width = max(3, len(str(len(art.paths))))
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED if ext in (".png", ".jpg") else zipfile.ZIP_DEFLATED) as zf:
        for i, p in enumerate(art.paths, start=1):
            zf.write(p, arcname=f"{stem}-p{i:0{width}d}{ext}")
    os.replace(tmp, dest)
    return [str(dest)], str(dest)


def _copy_atomic(src: Path, dest: Path) -> None:
    tmp = dest.with_name(f".{dest.name}.part")
    shutil.copyfile(src, tmp)
    if dest.exists():
        tmp.unlink()
        raise FileExistsError(dest)
    os.replace(tmp, dest)


# ------------------------------------------------------------------ batch
def run_batch(params: dict, notify: Callable[[dict], None], cancel: threading.Event | None = None,
              host: Host | None = None) -> dict:
    files = params.get("files") or []
    if not files:
        raise InputError("No files to convert.")
    target = params["target"]
    if target not in catalog().targets():
        raise InputError(f"Unknown target format '{target}'.")
    options = Options.from_dict(params.get("options"))
    out_dir = Path(params["outputDir"])
    job_id = params.get("jobId") or "job"
    jobs_dir = Path(params.get("jobsDir") or (out_dir / ".otk-jobs"))
    job_dir = jobs_dir / safe_stem(job_id, "job")
    job_dir.mkdir(parents=True, exist_ok=True)
    journal = Journal(job_dir / "journal.json")
    journal.data.setdefault("params", {k: v for k, v in params.items() if k not in ("files",)})
    journal.data["params"]["files"] = [f["path"] for f in files]  # never the passwords
    journal.save()

    def check() -> None:
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    results: list[FileResult] = []
    total = len(files)
    for i, f in enumerate(files):
        src = Path(f["path"])
        key = f"{i}:{src}"

        def prog(frac: float, msg: str, i=i, name=src.name) -> None:
            notify({"index": i, "total": total, "file": str(src), "fraction": (i + frac) / total,
                    "fileFraction": frac, "message": f"{i + 1}/{total} {name}: {msg}"})
        if cancel is not None and cancel.is_set():
            results.append(FileResult(str(src), "cancelled", message="Not started (cancelled)", code="cancelled"))
            continue
        res = convert_file(src, target, options, job_dir / f"file{i + 1:03d}", out_dir, password=f.get("password"),
                           host=host, check=check, progress=prog, journal=journal, key=key,
                           verify=params.get("verify", True))
        results.append(res)
        notify({"index": i, "total": total, "file": str(src), "fraction": (i + 1) / total, "fileFraction": 1.0,
                "message": f"{i + 1}/{total} {src.name}: {res.status}", "result": res.to_dict()})
    merged = None
    if params.get("merge") and not (cancel is not None and cancel.is_set()):
        done = [r for r in results if r.status == "done" and r.output]
        if len(done) >= 2:
            from .merge import merge_outputs
            notify({"index": total, "total": total, "fraction": 1.0, "message": "Merging"})
            try:
                merged = merge_outputs([Path(r.output) for r in done], target, out_dir, params.get("mergeName") or "merged",
                                       work=job_dir / "merge", check=check)
            except ToolkitError as exc:
                merged = {"status": "failed", "message": exc.message}
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    all_done = all(r.status == "done" for r in results)
    if all_done and not params.get("keepJobFolder"):
        shutil.rmtree(job_dir, ignore_errors=True)
    notify({"index": total, "total": total, "fraction": 1.0, "message": "Done"})
    return {"results": [r.to_dict() for r in results], "counts": counts, "merged": merged,
            "outputDir": str(out_dir), "jobDir": None if all_done else str(job_dir)}
