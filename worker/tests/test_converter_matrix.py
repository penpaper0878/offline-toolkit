"""Route matrix: convert the sample corpus along the planner's routes and check every verification verdict.

By default a representative set runs (one route per step family). Set OTK_FULL_MATRIX=1 to run every
source x target x mode route the planner offers (about 270 with the samples; ~15 minutes). A route
may end "needs review" only if it is listed in KNOWN_REVIEW with the reason; anything else fails.
Results are written to test-results/converter-matrix.json for docs/TEST_REPORT.md.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest
from conftest_converter import HAVE_ALL, needs_all

from otk_worker.converter import runner
from otk_worker.converter.context import Options

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_FOR = {"pdf": "pdf_lo", "pdf_scanned": "pdf_scanned", "pdfa2b": "pdfa2b", "docx": "docx", "doc": "doc",
              "xlsx": "xlsx", "xls": "xls", "pptx": "pptx", "ppt": "ppt", "html": "html", "txt": "txt",
              "epub": "epub", "png": "png", "jpeg": "jpeg", "svg": "svg"}

REPRESENTATIVE = [
    ("pdf", "docx", "exact"), ("pdf", "docx", "editable"), ("pdf", "pptx", "exact"), ("pdf", "pptx", "editable"),
    ("pdf", "xlsx", "editable"), ("pdf", "html", "editable"), ("pdf", "html", "exact"), ("pdf", "txt", "exact"),
    ("pdf", "png", "exact"), ("pdf", "svg", "exact"), ("pdf", "svg", "editable"), ("pdf", "epub", "exact"),
    ("pdf", "pdfa2b", "exact"), ("pdfa2b", "pdfa3b", "exact"), ("pdf_scanned", "docx", "exact"),
    ("pdf_scanned", "docx", "editable"), ("pdf_scanned", "txt", "exact"), ("pdf_scanned", "pdf", "exact"),
    ("png", "pdf", "exact"), ("png", "xlsx", "editable"), ("jpeg", "png", "exact"), ("docx", "pdf", "exact"),
    ("docx", "html", "editable"), ("docx", "xlsx", "editable"), ("docx", "epub", "editable"), ("docx", "txt", "exact"),
    ("xlsx", "html", "editable"), ("xlsx", "txt", "exact"), ("xlsx", "pdf", "exact"), ("xls", "xlsx", "exact"),
    ("pptx", "pdf", "exact"), ("pptx", "docx", "editable"), ("pptx", "html", "exact"), ("ppt", "pptx", "exact"),
    ("html", "pdf", "exact"), ("html", "docx", "editable"), ("html", "xlsx", "editable"), ("txt", "docx", "exact"),
    ("txt", "pptx", "exact"), ("epub", "html", "editable"), ("svg", "png", "exact"), ("svg", "docx", "exact"),
    ("svg", "pdf", "exact"),
]

# Routes whose honest verdict is "needs review" on the sample corpus, and why. Keep this list short:
# each entry is a real limitation, documented in docs/TEST_REPORT.md.
KNOWN_REVIEW: dict[str, str] = {}


def all_routes() -> list[tuple[str, str, str]]:
    cat = runner.catalog()
    out = []
    for src in SAMPLE_FOR:
        for tgt in cat.targets():
            for mode in ("exact", "editable"):
                if cat.effective_mode(tgt, mode) != mode:
                    continue
                try:
                    cat.plan(src, tgt, mode)
                except Exception:
                    continue
                out.append((src, tgt, mode))
    return out


ROUTES = all_routes() if os.environ.get("OTK_FULL_MATRIX") == "1" else REPRESENTATIVE
_results: list[dict] = []


@pytest.fixture(scope="module", autouse=True)
def write_results():
    yield
    if _results:
        out = ROOT / "test-results" / "converter-matrix.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(_results, ensure_ascii=False, indent=1), encoding="utf-8")


@needs_all
@pytest.mark.parametrize("src,target,mode", ROUTES, ids=[f"{s}-{t}-{m}" for s, t, m in ROUTES])
def test_route(samples, tmp_path, src, target, mode):
    sample = samples.get(SAMPLE_FOR[src])
    if sample is None:
        pytest.skip(f"no {src} sample (needs LibreOffice to make it)")
    key = f"{src}-{target}-{mode}"
    t0 = time.monotonic()
    r = runner.convert_file(sample, target, Options.from_dict({"mode": mode}), tmp_path / "work", tmp_path / "out")
    row = {"route": key, "status": r.status, "verdict": r.verdict, "seconds": round(time.monotonic() - t0, 2),
           "message": r.message, "chain": (r.route or {}).get("chain")}
    if r.report_json:
        report = json.loads(Path(r.report_json).read_text(encoding="utf-8"))
        row["checks"] = {c["id"]: c["status"] for c in report["checks"]}
        row["failed"] = [f"{c['label']}: {c['summary']}" for c in report["checks"] if c["status"] == "fail"]
    _results.append(row)
    assert r.status == "done", r.message
    assert Path(r.output).exists() and Path(r.report).exists()
    if r.verdict == "review":
        if key not in KNOWN_REVIEW:  # keep the report (with its before/after crops) in the CI artifact
            keep = ROOT / "test-results" / "matrix-failures"
            keep.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(r.report, keep / f"{key}.report.html")
            print(_diagnose(sample, Path(r.output), target, json.loads(Path(r.report_json).read_text(encoding="utf-8"))))
        assert key in KNOWN_REVIEW, f"{key} needs review: {row.get('failed')}"


def _diagnose(sample: Path, output: Path, target: str, report: dict) -> str:
    """For an exact Office output that looks different: the text spans around each changed area, in the source
    and in LibreOffice's rendering of the output (font, size, baseline), so a CI log shows what moved."""
    app = next((c for c in report["checks"] if c["id"] == "appearance" and c["status"] == "fail"), None)
    if app is None or target not in ("docx", "pptx") or sample.suffix.lower() != ".pdf":
        return ""
    import pymupdf

    from otk_worker.converter import libreoffice as lo

    lines = []
    try:
        rendered = lo.convert(output, output.parent / "diagnose", lo.pdf_filter("writer" if target == "docx" else "impress"))
    except Exception as exc:
        return f"diagnose: could not render the output: {exc}"
    for page, regions in (app["details"].get("changedRegions") or {}).items():
        for reg in regions[:4]:
            lines.append(f"page {page} region x={reg['x']} y={reg['y']} w={reg['w']} h={reg['h']} px={reg['pixels']}")
            for label, path in (("source", sample), ("output", rendered)):
                with pymupdf.open(path) as doc:
                    pg = doc[int(page) - 1]
                    for b in pg.get_text("dict")["blocks"]:
                        for ln in b.get("lines", []):
                            x0, y0, x1, y1 = ln["bbox"]
                            if y1 < reg["y"] - 4 or y0 > reg["y"] + reg["h"] + 4:
                                continue
                            for sp in ln["spans"]:
                                lines.append(f"  {label}: font={sp['font']} size={sp['size']:.2f} origin=({sp['origin'][0]:.2f},"
                                             f"{sp['origin'][1]:.2f}) bbox=({sp['bbox'][0]:.1f},{sp['bbox'][2]:.1f}) "
                                             f"text={sp['text'][:40]!r}")
    return "\n".join(lines)


def test_matrix_has_routes():
    assert len(all_routes()) > 250 or not HAVE_ALL
