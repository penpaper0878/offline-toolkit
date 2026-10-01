"""Verification report: a self-contained HTML page (no external assets) plus the same data as JSON."""

from __future__ import annotations

import html
import json
import os
from datetime import datetime
from pathlib import Path

from ... import __version__

VERDICT = {
    "perfect": ("Perfect", "Every check passed and nothing was changed.", "#1a7f37"),
    "expected": ("Converted with expected changes", "Nothing failed; the differences below are ones this route is "
                 "known to cause.", "#9a6700"),
    "review": ("Needs review", "At least one check failed. Look at the failed checks before using the file.", "#cf222e"),
}
STATUS = {"pass": ("Pass", "#1a7f37"), "expected": ("Expected change", "#9a6700"), "fail": ("Fail", "#cf222e"),
          "skipped": ("Not checked", "#6e7781")}


def _esc(v) -> str:
    return html.escape(str(v))


def _details(check: dict) -> str:
    d = check.get("details") or {}
    rows = []
    if check["id"] == "text":
        rows.append(f"<p>Words: source {d.get('sourceWords', 0)}, output {d.get('outputWords', 0)}; "
                    f"similarity {d.get('similarity', 1):.2%}.</p>" if "similarity" in d else "")
        for key, title in (("missing", "Missing from the output"), ("extra", "Only in the output")):
            items = d.get(key) or []
            if items:
                rows.append(f"<h4>{title} ({d.get(key + 'Count', len(items))})</h4><table><tr><th>Word</th><th>×</th><th>Context</th></tr>"
                            + "".join(f"<tr><td><code>{_esc(i['token'])}</code></td><td>{i['count']}</td>"
                                      f"<td>{_esc(i['context'])}</td></tr>" for i in items) + "</table>")
        if d.get("ignored"):
            rows.append(f"<p class='muted'>Ignored decorations added by the engine: {_esc(' '.join(d['ignored']))}</p>")
    elif check["id"] == "pdfa":
        for r in d.get("failedRules") or []:
            rows.append(f"<li>{_esc(r.get('specification') or '')} clause {_esc(r.get('clause'))} test {_esc(r.get('test'))}: "
                        f"{_esc(r.get('description'))} ({_esc(r.get('failedChecks'))} occurrence(s))</li>")
        if rows:
            rows = ["<ul>"] + rows + ["</ul>"]
    elif check["id"] == "ocr":
        words = d.get("words") or []
        rows.append("<table><tr><th>Page</th><th>Word</th><th>Confidence</th></tr>" + "".join(
            f"<tr><td>{_esc(w.get('page') or '')}</td><td>{_esc(w['text'])}</td><td>{w['confidence']:.0%}</td></tr>"
            for w in words[:300]) + "</table>")
    elif check["id"] == "appearance" and d.get("ssim"):
        rows.append("<p>SSIM per page (1.0 = identical, needs ≥ 0.98): "
                    + ", ".join(f"{i + 1}: {s:.3f}" for i, s in enumerate(d["ssim"])) + "</p>")
        regions = d.get("changedRegions") or {}
        if regions:
            rows.append("<h4>Areas with ink on one side only</h4><ul>" + "".join(
                f"<li>Page {_esc(pg)}: {len(rs)} area(s), e.g. at {rs[0]['x']:.0f}, {rs[0]['y']:.0f} pt "
                f"({rs[0]['w']:.0f} × {rs[0]['h']:.0f} pt)</li>" for pg, rs in regions.items()) + "</ul>")
        for snap in d.get("snapshots") or []:
            rows.append(f"<figure><img alt='Source above, output below, page {_esc(snap['page'])}' "
                        f"src='data:image/png;base64,{snap['png']}' style='max-width:100%;border:1px solid #ccc'/>"
                        f"<figcaption>Page {_esc(snap['page'])} at {snap['x']:.0f}, {snap['y']:.0f} pt: "
                        "source above, output below.</figcaption></figure>")
    else:
        if d:
            rows.append(f"<pre>{_esc(json.dumps(d, ensure_ascii=False, indent=1)[:6000])}</pre>")
    return "".join(rows)


def render_html(r: dict) -> str:
    title, blurb, color = VERDICT[r["verdict"]]
    checks = []
    for c in r["checks"]:
        label, col = STATUS[c["status"]]
        det = _details(c)
        checks.append(f"<tr><td>{_esc(c['label'])}</td><td><span class='badge' style='background:{col}'>{label}</span></td>"
                      f"<td>{_esc(c['summary'])}{f'<details><summary>Details</summary>{det}</details>' if det else ''}</td></tr>")
    steps = "".join(f"<li><b>{_esc(s['engine'])}</b>: {_esc(s['summary'])}</li>" for s in r["route"]["steps"])
    losses = "".join(f"<li>{_esc(x['label'])}: {_esc(x['level'])}</li>" for x in r.get("plannedLosses", [])) + \
        "".join(f"<li>{_esc(x)}</li>" for x in r.get("stepLosses", []))
    expected = "".join(f"<li>{_esc(x)}</li>" for x in r.get("expectedChanges", []))
    notes = "".join(f"<li>{_esc(x)}</li>" for x in r.get("notes", []))
    outputs = "".join(f"<li><code>{_esc(Path(p).name)}</code></li>" for p in r.get("outputs", []))
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conversion report – {_esc(r['source']['name'])}</title>
<style>
:root{{--bg:#fff;--fg:#1f2328;--muted:#656d76;--line:#d0d7de;--card:#f6f8fa}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d1117;--fg:#e6edf3;--muted:#8d96a0;--line:#30363d;--card:#161b22}}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,'Noto Sans',sans-serif;margin:0;padding:24px;max-width:1100px}}
h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:16px;margin:24px 0 8px}} h4{{margin:12px 0 4px}}
.verdict{{border-left:6px solid {color};background:var(--card);padding:12px 16px;border-radius:6px}}
.verdict b{{color:{color};font-size:18px}}
table{{border-collapse:collapse;width:100%}} td,th{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}
.badge{{color:#fff;border-radius:10px;padding:1px 8px;font-size:12px;white-space:nowrap}}
.muted{{color:var(--muted)}} code,pre{{font-family:ui-monospace,Consolas,monospace;font-size:12px}} pre{{white-space:pre-wrap}}
ul{{margin:4px 0;padding-left:20px}}
</style></head><body>
<h1>{_esc(r['source']['name'])} → {_esc(r['target']['label'])}</h1>
<p class="muted">{_esc(r['source']['label'])} to {_esc(r['target']['label'])}, {_esc(r['mode'])} mode ·
{_esc(r.get('created', ''))} · Offline Toolkit {_esc(r.get('version', ''))} · {r.get('seconds', 0)} s</p>
<div class="verdict"><b>{title}</b><br>{blurb}</div>
<h2>Output</h2><ul>{outputs}</ul>
<h2>Checks</h2>
<table><tr><th>Check</th><th>Result</th><th>Details</th></tr>{''.join(checks)}</table>
<h2>Route</h2><p class="muted">{' → '.join(_esc(x) for x in r['route']['chain'])}</p><ol>{steps}</ol>
{f"<p class='muted'>Route chosen by an override: {_esc(r['route']['override'])}</p>" if r['route'].get('override') else ''}
{f'<h2>Expected changes</h2><ul>{expected}</ul>' if expected else ''}
{f'<h2>What this route cannot keep</h2><ul>{losses}</ul>' if losses else ''}
{f'<h2>Notes</h2><ul>{notes}</ul>' if notes else ''}
</body></html>
"""


def write(r: dict, output: Path) -> tuple[Path, Path]:
    r = dict(r)
    r["created"] = datetime.now().astimezone().isoformat(timespec="seconds")
    r["version"] = __version__
    base = output.with_name(output.name + ".report")
    html_path = base.with_name(base.name + ".html")
    json_path = base.with_name(base.name + ".json")
    for path, data in ((html_path, render_html(r)), (json_path, json.dumps(r, ensure_ascii=False, indent=1))):
        tmp = path.with_name(f".{path.name}.part")
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, path)
    return html_path, json_path
