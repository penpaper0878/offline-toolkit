#!/usr/bin/env python3
"""Collect the licence of everything the app bundles into build/licenses/ (build time; read by Settings → About).

    node scripts/run-python.mjs scripts/collect_licenses.py           # this machine's build (worker venv, engines/<os>)
    python scripts/collect_licenses.py --platform win-x64 \\
        --site-packages build/python-win/Lib/site-packages --python-root build/python-win   # the Windows release

Writes
    build/licenses/third-party.json        every component: kind, version, SPDX licence, copyleft level, licence files
    build/licenses/texts/...               the licence texts (each package's own files; SPDX texts where it ships none)
    build/licenses/THIRD-PARTY-NOTICES.txt the copyleft summary, the list and every distinct licence text once

Covers the Electron runtime (Chromium, Node.js, FFmpeg), the JavaScript bundled into the app (from the build's
bundled-packages.json and package.json's dependencies), the Python runtime and every Python distribution shipped
with the worker, the native libraries inside them that carry their own (L)GPL licence, the conversion engines
and the libraries inside those, veraPDF's jars, the Java runtime, the tessdata models, the fonts and the models.
Fails when a component's licence cannot be determined, so a new dependency cannot slip in unlisted.

Copyleft levels: "network" (AGPL), "strong" (GPL), "weak" (LGPL, MPL, CDDL, EPL, GPL with the Classpath
exception), "none". For dual licences the most permissive open option counts; commercial options don't.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata as md
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPDX_DIR = ROOT / "scripts" / "licenses" / "spdx"
LEVELS = ["none", "weak", "strong", "network"]
LICENCE_FILE = re.compile(r"^(licen[cs]e|copying|notice|copyright|third.?party.?notices|licenses?_bundled|legal)", re.I)

# --- SPDX expressions ----------------------------------------------------------------------------------------------

ALIASES = {
    "mit license": "MIT", "mit": "MIT", "bsd": "BSD-3-Clause", "bsd license": "BSD-3-Clause", "bsd-3-clause": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause", "3-clause bsd license": "BSD-3-Clause", "new bsd license": "BSD-3-Clause",
    "apache 2.0": "Apache-2.0", "apache-2.0": "Apache-2.0", "apache license 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0", "apache license, version 2.0": "Apache-2.0", "psfl": "PSF-2.0",
    "python software foundation license": "PSF-2.0", "mpl-2.0": "MPL-2.0", "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "gnu lesser general public license v3 (lgplv3)": "LGPL-3.0-or-later", "isc license (iscl)": "ISC",
    "ufl-1.0": "Ubuntu-font-1.0", "mpl-2.0 and mit": "MPL-2.0 AND MIT",
}


def _single(lic: str) -> int:
    if " WITH " in lic:
        base, exc = lic.split(" WITH ", 1)
        if exc.startswith("GCC-exception"):
            return 0                        # the runtime library exception: no obligations on the program
        if exc.startswith("Classpath-exception"):
            return 1
        lic = base
    if lic.startswith("AGPL"):
        return 3
    if lic.startswith("GPL"):
        return 2
    if lic.startswith(("LGPL", "MPL", "CDDL", "EPL")):
        return 1
    return 0


def copyleft(expr: str) -> str:
    """The copyleft level of an SPDX expression (most permissive open alternative of an OR)."""
    best = None
    for alt in re.split(r"\s+OR\s+", expr.replace("(", " ").replace(")", " ").strip()):
        if re.search(r"LicenseRef-\S*Commercial", alt):
            continue
        worst = max((_single(p.strip()) for p in re.split(r"\s+AND\s+", alt.strip()) if p.strip()), default=0)
        best = worst if best is None else min(best, worst)
    return LEVELS[best or 0]


def spdx_ids(expr: str) -> list[str]:
    ids = re.findall(r"[A-Za-z0-9.\-+]+(?:\s+WITH\s+[A-Za-z0-9.\-]+)?", expr.replace("(", " ").replace(")", " "))
    out = []
    for i in ids:
        if i in ("AND", "OR") or i.startswith("LicenseRef-"):
            continue
        base, _, exc = i.partition(" WITH ")
        out.append(re.sub(r"-or-later$|\+$", "", base))
        if exc:
            out.append(exc.strip())
    return out


def spdx_text_file(lic: str) -> Path | None:
    for cand in (lic, f"{lic}-only", lic.replace("-or-later", "-only"), lic.replace("-only", "")):
        p = SPDX_DIR / f"{cand}.txt"
        if p.exists():
            return p
    return None


# --- components ----------------------------------------------------------------------------------------------------

class Collector:
    def __init__(self, out: Path, platform: str):
        self.out, self.platform = out, platform
        self.components: list[dict] = []
        self.unknown: list[str] = []

    def add(self, kind: str, cid: str, name: str, version: str, license: str, *, files: list[Path] = (),
            note: str = "", where: str = "", homepage: str = "", part_of: str = "", spdx_fallback: bool = True) -> dict:
        if not license or license == "UNKNOWN":
            self.unknown.append(f"{kind}:{name}")
            license = "UNKNOWN"
        texts, seen = [], set()
        for f in files:
            if f.is_file() and f.stat().st_size < 3_000_000:
                data = f.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                rel = Path("texts") / kind / _slug(cid) / f.name
                if f.suffix.lower() not in (".txt", ".md", ".rst", ".html", ".htm"):
                    rel = rel.with_name(f.name + ".txt")
                (self.out / rel).parent.mkdir(parents=True, exist_ok=True)
                (self.out / rel).write_bytes(data)
                texts.append(rel.as_posix())
        if not texts and spdx_fallback and license != "UNKNOWN":
            for lic in spdx_ids(license):
                src = spdx_text_file(lic)
                if src:
                    rel = Path("texts") / "spdx" / src.name
                    (self.out / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, self.out / rel)
                    texts.append(rel.as_posix())
        comp = {"id": cid, "kind": kind, "name": name, "version": version, "license": license,
                "copyleft": copyleft(license) if license != "UNKNOWN" else "none", "files": texts}
        for k, v in (("note", note), ("where", where), ("homepage", homepage), ("partOf", part_of)):
            if v:
                comp[k] = v
        self.components.append(comp)
        return comp


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")[:80]


def licence_files_in(folder: Path, depth: int = 1) -> list[Path]:
    out = []
    if not folder.is_dir():
        return out
    for p in sorted(folder.iterdir()):
        if p.is_file() and LICENCE_FILE.match(p.name):
            out.append(p)
        elif p.is_dir() and depth > 0 and LICENCE_FILE.match(p.name):
            out += [f for f in sorted(p.rglob("*")) if f.is_file()][:40]
    return out


# Native libraries inside wheels and engines that carry their own copyleft licence (file name → library, licence).
NATIVE = [
    (r"(^|[^a-z])(avcodec|avformat|avutil|swscale|swresample|avfilter|avdevice)[-.\d]|opencv_videoio_ffmpeg|^(lib)?ffmpeg\.(dll|so)",
     "FFmpeg", "LGPL-2.1-or-later"),
    (r"(^|[^a-z_])(lib)?geos(_c)?[-.\d]", "GEOS", "LGPL-2.1-only"),
    (r"libheif", "libheif", "LGPL-3.0-or-later"),
    (r"libde265", "libde265", "LGPL-3.0-or-later"),
    (r"fribidi", "FriBiDi", "LGPL-2.1-or-later"),
    (r"(glib|gobject|gio|gmodule|gthread)-2\.0", "GLib", "LGPL-2.1-or-later"),
    (r"pango(cairo|ft2|win32)?-1\.0", "Pango", "LGPL-2.1-or-later"),
    (r"(^|[^a-z])(lib)?cairo[-.\d]", "cairo", "LGPL-2.1-only OR MPL-1.1"),
    (r"libintl", "GNU gettext runtime (libintl)", "LGPL-2.1-or-later"),
    (r"libiconv", "GNU libiconv", "LGPL-2.1-or-later"),
    (r"libquadmath", "libquadmath", "LGPL-2.1-or-later"),
    (r"libgfortran|libgcc_s|libstdc\+\+|libgomp", "GCC runtime libraries", "GPL-3.0-or-later WITH GCC-exception-3.1"),
]


def natives(paths: list[str]) -> dict[str, tuple[str, list[str]]]:
    found: dict[str, tuple[str, list[str]]] = {}
    for p in paths:
        name = Path(p).name.lower()
        if not re.search(r"\.(dll|so(\.[\d.]+)?|dylib|pyd)$", name):
            continue
        for pattern, lib, lic in NATIVE:
            if re.search(pattern, name):
                found.setdefault(lib, (lic, []))[1].append(Path(p).name)
                break
    return found


def add_natives(c: Collector, parent_kind: str, parent: dict, paths: list[str], parent_dir_files: list[Path]) -> None:
    for lib, (lic, names) in sorted(natives(paths).items()):
        if copyleft(lic) == "none" and lic.find("GCC-exception") < 0:
            continue
        c.add("native", f"{parent['id']}/{lib}", lib, "", lic, part_of=parent["name"],
              note=f"Inside {parent['name']}, as separate replaceable libraries: {', '.join(sorted(set(names))[:6])}",
              where=parent.get("where", ""), files=[f for f in parent_dir_files if lib.lower().split()[0] in f.name.lower()])


# --- the Electron runtime and JavaScript ---------------------------------------------------------------------------

def collect_electron(c: Collector) -> None:
    el = ROOT / "node_modules" / "electron"
    version = json.loads((el / "package.json").read_text())["version"]
    dist = el / "dist"
    c.add("runtime", "electron", "Electron", version, "MIT", files=[dist / "LICENSE"], homepage="https://www.electronjs.org",
          where="the app itself", note="The application shell; its licence file ships next to the app as LICENSE.electron.txt.")
    c.add("runtime", "chromium", "Chromium (inside Electron)", version, "BSD-3-Clause",
          note="Chromium and its hundreds of third-party libraries: their notices ship next to the app as "
               "LICENSES.chromium.html (20 MB, not repeated here).", where="the app itself", spdx_fallback=True)
    c.add("runtime", "nodejs", "Node.js (inside Electron)", "", "MIT", where="the app itself",
          note="Node.js and its bundled libraries (OpenSSL Apache-2.0, libuv MIT, ICU Unicode-3.0 and others); "
               "listed in LICENSES.chromium.html.")
    libs = [p.name for p in dist.iterdir() if p.is_file()] if dist.is_dir() else []
    if any(re.search(r"^(lib)?ffmpeg\.(dll|so)$", n) for n in libs) or c.platform.startswith("win"):
        c.add("native", "electron/ffmpeg", "FFmpeg (Electron's media library)", "", "LGPL-2.1-or-later", part_of="Electron",
              where="the app itself", note="ffmpeg.dll next to the app: Chromium's audio/video decoding, a separate "
              "replaceable library built without GPL parts.")
    if c.platform.startswith("win"):
        c.add("runtime", "d3dcompiler", "Direct3D shader compiler (d3dcompiler_47.dll)", "47",
              "LicenseRef-Microsoft-Redistributable", spdx_fallback=False, where="the app itself",
              note="Microsoft's redistributable shader compiler, shipped with every Electron app for WebGL on Windows.")


def _npm_info(pkg_dir: Path) -> tuple[str, str, str, list[Path]]:
    pj = json.loads((pkg_dir / "package.json").read_text(encoding="utf-8"))
    lic = pj.get("license") or ""
    if isinstance(lic, dict):
        lic = lic.get("type", "")
    if not lic and isinstance(pj.get("licenses"), list):
        lic = " OR ".join(x.get("type", "") for x in pj["licenses"])
    files = [p for p in sorted(pkg_dir.iterdir()) if p.is_file() and LICENCE_FILE.match(p.name)]
    return pj["name"], pj.get("version", ""), lic, files


def collect_npm(c: Collector) -> None:
    nm = ROOT / "node_modules"
    names: dict[str, str] = {}
    # Runtime dependencies (in the app archive) and their own dependencies.
    todo = list(json.loads((ROOT / "package.json").read_text())["dependencies"])
    while todo:
        n = todo.pop()
        if n in names:
            continue
        names[n] = "main process (app archive)"
        todo += list(json.loads((nm / n / "package.json").read_text()).get("dependencies", {}))
    # What the build bundled into the UI and the main process (electron.vite.config.ts writes these lists).
    lists = sorted((ROOT / "out").glob("*/bundled-packages.json"))
    if not lists:
        raise SystemExit("out/*/bundled-packages.json missing: run `npm run build` first")
    for f in lists:
        for n in json.loads(f.read_text(encoding="utf-8")):
            names.setdefault(n, "user interface (bundled)" if f.parent.name == "renderer" else f"{f.parent.name} (bundled)")
    for n, where in sorted(names.items()):
        name, version, lic, files = _npm_info(nm / n)
        c.add("javascript", f"npm:{name}", name, version, ALIASES.get(lic.lower(), lic) if lic else "UNKNOWN",
              files=files, where=where)


# --- Python --------------------------------------------------------------------------------------------------------

# Where a distribution's metadata is missing, vague or leaves out what its wheel bundles.
PY_OVERRIDES = {
    "pymupdf": ("AGPL-3.0-only", "Or an Artifex commercial licence. Imported into the worker, so the worker is a combined "
                "work with it (docs/ENGINES.md §3)."),
    "pdf2docx": ("MIT", "Uses PyMuPDF (AGPL-3.0)."),
    "pypdfium2": ("Apache-2.0 OR BSD-3-Clause", "Includes PDFium (BSD-3-Clause) and PDFium's third-party libraries "
                  "(FreeType, libjpeg-turbo, OpenJPEG, lcms2, zlib, ICU: permissive)."),
    "shapely": ("BSD-3-Clause", ""),
    "pi-heif": ("BSD-3-Clause", "Its wheel contains libheif and libde265 (LGPL-3.0) as separate libraries; no x265 encoder."),
    "opencv-contrib-python-headless": ("Apache-2.0", "Third-party parts are listed in LICENSE-3RD-PARTY.txt."),
    "antlr4-python3-runtime": ("BSD-3-Clause", ""),
    "omegaconf": ("BSD-3-Clause", ""),
    "olefile": ("BSD-2-Clause", ""),
    "xlrd": ("BSD-3-Clause", ""),
    "defusedxml": ("PSF-2.0", ""),
    "flatbuffers": ("Apache-2.0", ""),
    "protobuf": ("BSD-3-Clause", ""),
    "onnxruntime": ("MIT", "Third-party parts are listed in ThirdPartyNotices.txt."),
    "img2pdf": ("LGPL-3.0-or-later", "Pure Python module, replaceable."),
    "uharfbuzz": ("Apache-2.0", "Includes HarfBuzz (MIT)."),
    "requests": ("Apache-2.0", "Imported by RapidOCR but never used to download; the network guard blocks it."),
    "colorama": ("BSD-3-Clause", ""),
    "numpy": (None, "Its wheel includes OpenBLAS (BSD-3-Clause) and the GCC runtime libraries (GPL-3.0 with the runtime "
              "library exception), listed in its LICENSE.txt."),
}


def _requirement(line: str):
    try:
        from packaging.requirements import Requirement
    except ImportError:  # pip always vendors it
        from pip._vendor.packaging.requirements import Requirement
    return Requirement(line)


def _norm(n: str) -> str:
    return re.sub(r"[-_.]+", "-", n).lower()


def python_dists(site_packages: Path | None, platform: str) -> list[md.Distribution]:
    if site_packages:
        dists = {_norm(d.metadata["Name"]): d for d in md.distributions(path=[str(site_packages)])}
        return [dists[k] for k in sorted(dists)]
    # This machine's worker environment: the closure of the worker's requirements (dev tools left out).
    env = ({"sys_platform": "win32", "platform_system": "Windows", "os_name": "nt", "platform_machine": "AMD64"}
           if platform.startswith("win") else {})
    lines = [ln.split("#")[0].strip() for f in ("requirements.txt", "requirements-nodeps.txt")
             for ln in (ROOT / "worker" / f).read_text().splitlines()]
    nodeps = {_norm(_requirement(ln.split("#")[0].strip()).name)
              for ln in (ROOT / "worker" / "requirements-nodeps.txt").read_text().splitlines() if ln.split("#")[0].strip()}
    todo = [_requirement(ln) for ln in lines if ln]
    seen: dict[str, md.Distribution] = {}
    while todo:
        req = todo.pop()
        n = _norm(req.name)
        if n in seen:
            continue
        try:
            d = md.distribution(req.name)
        except md.PackageNotFoundError:
            continue                      # a dependency for another platform (colorama on Windows)
        seen[n] = d
        if n in nodeps:
            continue
        for r in d.requires or []:
            rr = _requirement(r)
            if rr.marker and not any(rr.marker.evaluate({**env, "extra": e}) for e in (req.extras or {""})):
                continue
            todo.append(rr)
    return [seen[k] for k in sorted(seen)]


def dist_licence(d: md.Distribution) -> tuple[str, str]:
    name = _norm(d.metadata["Name"])
    over, note = PY_OVERRIDES.get(name, (None, ""))
    if over:
        return over, note
    m = d.metadata
    if m.get("License-Expression"):
        return m["License-Expression"], note
    lic = (m.get("License") or "").strip()
    if lic and "\n" not in lic and len(lic) < 60:
        return ALIASES.get(lic.lower(), lic), note
    for cl in m.get_all("Classifier") or []:
        if cl.startswith("License ::") and not cl.endswith("OSI Approved"):
            last = cl.split("::")[-1].strip()
            return ALIASES.get(last.lower(), last), note
    return "UNKNOWN", note


def collect_python(c: Collector, site_packages: Path | None, python_root: Path | None) -> None:
    if python_root and (python_root / "LICENSE.txt").exists():
        ver = next((m.group(1) for m in [re.search(r"CPython ([\d.]+)", (python_root / "OTK_BUNDLE.txt").read_text())]
                    if m), "3.11") if (python_root / "OTK_BUNDLE.txt").exists() else "3.11"
        c.add("runtime", "cpython", "CPython", ver, "PSF-2.0", files=[python_root / "LICENSE.txt"], where="worker",
              note="The embeddable Python; its LICENSE.txt includes the libraries it is built with (OpenSSL, libffi, "
                   "zlib, bzip2, xz, SQLite, expat, mpdecimal).", homepage="https://www.python.org")
        fribidi = [p for p in python_root.glob("*fribidi*")]
        if fribidi:
            c.add("native", "fribidi", "FriBiDi", "1.0.17", "LGPL-2.1-or-later", where="worker (Pillow's text shaping)",
                  files=[p for p in python_root.glob("*") if p.is_file() and "fribidi" in p.name.lower() and not p.suffix == ".dll"],
                  note="fribidi-0.dll next to python.exe (conda-forge build), loaded by Pillow at run time; replaceable.")
    else:
        lic = Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "LICENSE.txt"
        c.add("runtime", "cpython", "CPython", sys.version.split()[0], "PSF-2.0", files=[lic], where="worker",
              note="This machine's Python (the Windows build bundles the official embeddable package).")
    for d in python_dists(site_packages, c.platform):
        lic, note = dist_licence(d)
        files = [Path(d.locate_file(f)) for f in (d.files or [])
                 if LICENCE_FILE.match(Path(str(f)).name) and len(Path(str(f)).parts) <= 4
                 and not re.search(r"(^|/)(tests?|testing)/", str(f))][:12]
        name = d.metadata["Name"]
        comp = c.add("python", f"py:{_norm(name)}", name, d.version, lic, files=files, note=note, where="worker")
        add_natives(c, "python", comp, [str(f) for f in (d.files or [])], files)


# --- engines, fonts, models ----------------------------------------------------------------------------------------

ENGINES = {
    "libreoffice": ("LibreOffice", "MPL-2.0", "https://www.libreoffice.org",
                    "Separate program. Its own third-party components are listed in the licence files copied here."),
    "pandoc": ("Pandoc", "GPL-2.0-or-later", "https://pandoc.org", "Separate program, run as a process (aggregation)."),
    "ghostscript": ("Ghostscript", "AGPL-3.0-or-later", "https://www.ghostscript.com",
                    "Or an Artifex commercial licence. Separate program, run as a process (aggregation)."),
    "tesseract": ("Tesseract OCR", "Apache-2.0", "https://github.com/tesseract-ocr/tesseract",
                  "Separate program; the Windows build includes Leptonica (BSD-2-Clause) and image libraries."),
    "tessdata": ("tessdata_fast language models", "Apache-2.0", "https://github.com/tesseract-ocr/tessdata_fast", ""),
    "jre": ("Eclipse Temurin Java runtime (cut with jlink)", "GPL-2.0-only WITH Classpath-exception-2.0",
            "https://adoptium.net", "Separate runtime that runs veraPDF; its legal/ notices are copied here."),
    "resvg": ("resvg", "Apache-2.0 OR MIT", "https://github.com/linebender/resvg", "Separate program."),
}
VERAPDF_VERSION = "1.28.2"
VERAPDF_LICENCES = {  # checked against each artifact's POM on Maven Central
    "greenfield-apps": "GPL-3.0-or-later OR MPL-2.0", "gui": "GPL-3.0-or-later OR MPL-2.0",
    "core": "GPL-3.0-or-later OR MPL-2.0", "feature-reporting": "GPL-3.0-or-later OR MPL-2.0",
    "metadata-fixer": "GPL-3.0-or-later OR MPL-2.0", "parser": "GPL-3.0-or-later OR MPL-2.0",
    "pdf-model": "GPL-3.0-or-later OR MPL-2.0", "validation-model": "GPL-3.0-or-later OR MPL-2.0",
    "verapdf-xmp-core": "BSD-3-Clause", "jackson-annotations": "Apache-2.0", "jackson-core": "Apache-2.0",
    "jackson-databind": "Apache-2.0", "javax.activation-api": "CDDL-1.1 OR GPL-2.0-only WITH Classpath-exception-2.0",
    "jaxb-api": "CDDL-1.1 OR GPL-2.0-only WITH Classpath-exception-2.0",
    "jaxb-core": "CDDL-1.1 OR GPL-2.0-only WITH Classpath-exception-2.0", "jaxb-impl": "BSD-3-Clause",
    "jcommander": "Apache-2.0", "rhino": "MPL-2.0", "stax-utils": "BSD-2-Clause",
}


def _tool_version(folder: Path, key: str) -> str:
    """For a build without manifest.json (fetched before it existed): ask the program."""
    import subprocess

    exe = next((p for p in (folder / key, folder / f"{key}.exe") if p.is_file()), None)
    if not exe:
        return ""
    try:
        r = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=60)
        return (r.stdout or r.stderr).strip().splitlines()[0][:80]
    except (OSError, subprocess.SubprocessError, IndexError):
        return ""


def collect_engines(c: Collector, engines: Path) -> None:
    manifest = json.loads((engines / "manifest.json").read_text(encoding="utf-8")) if (engines / "manifest.json").exists() else {}
    for key, (name, lic, home, note) in ENGINES.items():
        folder = engines / ("tesseract" if key == "tessdata" else key)
        if key not in manifest and not folder.exists():
            continue
        if key == "tessdata" and not (folder / "tessdata").exists():
            continue
        files = [] if key == "tessdata" else licence_files_in(folder, depth=1)
        if key == "jre":
            files = [f for f in sorted((folder / "legal" / "java.base").glob("*")) if f.is_file()] + files
        if key == "tesseract":
            files += licence_files_in(folder / "doc", depth=0)
        if key == "ghostscript":
            files += [f for f in (folder / "doc").glob("COPYING*")] if (folder / "doc").exists() else []
        version = str(manifest.get(key, "")).split("\n")[0][:80] or _tool_version(folder, key)
        if key != "tessdata" and (m := re.search(r"\d+(?:\.\d+)+", version)):
            version = m.group(0)
        elif key == "tessdata":
            version = version.split(":")[0].replace("tessdata_fast", "").strip("@ ")
        comp = c.add("engine", f"engine:{key}", name, version, lic, files=files, note=note, homepage=home,
                     where="separate program")
        if folder.exists() and key in ("tesseract", "libreoffice", "ghostscript"):
            add_natives(c, "engine", comp, [str(p) for p in folder.rglob("*") if p.is_file()], [])
    gs_bin = engines / "ghostscript" / "bin"
    if gs_bin.exists() and any(p.name.lower() == "vcruntime140.dll" for p in gs_bin.iterdir()):
        c.add("runtime", "vc-runtime", "Microsoft Visual C++ runtime (msvcp140, vcruntime140)", "14",
              "LicenseRef-Microsoft-Redistributable", spdx_fallback=False, where="Ghostscript",
              note="App-local copies next to Ghostscript, which needs them; Microsoft allows redistributing these DLLs "
                   "with an application. The Java runtime and LibreOffice ship the same files.")
    lib = engines / "verapdf" / "lib"
    if lib.exists():
        c.add("engine", "engine:verapdf", "veraPDF (PDF/A validator)", str(manifest.get("verapdf", VERAPDF_VERSION)).replace("veraPDF ", ""),
              "GPL-3.0-or-later OR MPL-2.0", homepage="https://verapdf.org", where="separate program (Java)",
              note="Dual-licensed; used under MPL-2.0. Its jars are listed below.")
        for jar in sorted(lib.glob("*.jar")):
            art, _, ver = jar.stem.rpartition("-")
            lic = VERAPDF_LICENCES.get(art, "UNKNOWN")
            c.add("java", f"jar:{art}", art, ver, lic, part_of="veraPDF (PDF/A validator)", where="separate program (Java)")


def collect_fonts(c: Collector, fonts: Path) -> None:
    cat = json.loads((fonts / "fonts.json").read_text(encoding="utf-8"))
    for fam in cat["families"]:
        lic = ALIASES.get(fam["licence"].lower(), fam["licence"])
        c.add("font", f"font:{fam['dir']}", fam["family"], "", lic, files=[fonts / fam["licenceFile"]],
              where="design module and its exports", homepage="https://fonts.google.com",
              note="Embedded (subset) in the PDF, SVG, Word and PowerPoint files the design module exports, as the licence allows.")


MODEL_COPYRIGHT = {
    "superres": "Copyright (c) 2021, Xintao Wang (Real-ESRGAN).",
    "person": "Copyright Google LLC (MediaPipe).",
    "faceDetector": "Copyright (c) 2020 Shiqi Yu and the OpenCV model zoo contributors (YuNet).",
    "faceLandmarks": "Copyright Google LLC (MediaPipe).",
}


def collect_models(c: Collector, models: Path) -> None:
    man = json.loads((models / "manifest.json").read_text(encoding="utf-8"))
    for key, m in man.items():
        if not isinstance(m, dict) or "licence" not in m:
            continue
        c.add("model", f"model:{key}", m["model"], "", m["licence"], where="worker",
              note=MODEL_COPYRIGHT.get(key, "") + (f" Source: {m['source']}" if m.get("source") else ""))
    c.add("model", "model:pp-ocr", "PP-OCR text detection and recognition models (inside RapidOCR)", "", "Apache-2.0",
          where="worker", note="Copyright PaddlePaddle Authors; shipped inside the rapidocr package.")


# --- output --------------------------------------------------------------------------------------------------------

SECTION = {"runtime": "Application runtime", "javascript": "JavaScript libraries", "python": "Python packages (worker)",
           "native": "Native libraries inside other components", "engine": "Conversion engines",
           "java": "veraPDF's Java libraries", "font": "Fonts", "model": "Models"}
WHAT_IT_MEANS = {
    "network": "If you give the app to others you must offer them the complete corresponding source under AGPL "
               "terms (for PyMuPDF that means the worker, realistically the whole app), or buy a commercial licence.",
    "strong": "If you give the app to others, include the licence and offer this component's source code "
              "(it is a separate program here, so the rest of the app is not affected).",
    "weak": "If you give the app to others, include the licence, keep the library replaceable (it is a separate file here) and offer the source of the library itself, "
            "including any changes made to it (none were).",
}


def write_outputs(c: Collector, app_version: str) -> dict:
    comps = sorted(c.components, key=lambda x: (list(SECTION).index(x["kind"]), x["name"].lower()))
    flagged = [x for x in comps if x["copyleft"] != "none"]
    summary = {
        "total": len(comps),
        "byKind": {k: sum(1 for x in comps if x["kind"] == k) for k in SECTION if any(x["kind"] == k for x in comps)},
        "byCopyleft": {lvl: sum(1 for x in comps if x["copyleft"] == lvl) for lvl in LEVELS},
    }
    doc = {"app": {"name": "Offline Toolkit", "version": app_version}, "platform": c.platform,
           "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "summary": summary,
           "meaning": WHAT_IT_MEANS, "components": comps}
    (c.out / "third-party.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")

    lines = [f"Offline Toolkit {app_version}: third-party software notices",
             f"Build for {c.platform}, generated {doc['generated']}. {len(comps)} components.", "",
             "This copy is for personal use. Copyleft licences place obligations only on someone who gives the app",
             "to others; running it yourself triggers none of them. They are listed first so the picture is clear.", ""]
    lines += ["=" * 100, "COPYLEFT COMPONENTS (matter only if the app is redistributed)", "=" * 100]
    for lvl in ("network", "strong", "weak"):
        group = [x for x in flagged if x["copyleft"] == lvl]
        if not group:
            continue
        lines += ["", f"[{lvl}] {WHAT_IT_MEANS[lvl]}"]
        for x in group:
            lines.append(f"  - {x['name']} {x['version']}".rstrip() + f": {x['license']}"
                         + (f" (part of {x['partOf']})" if x.get("partOf") else "") + (f". {x['note']}" if x.get("note") else ""))
    lines += ["", "=" * 100, "ALL COMPONENTS", "=" * 100]
    text_ids: dict[str, str] = {}
    texts: list[tuple[str, str, list[str]]] = []
    for x in comps:
        refs = []
        for rel in x["files"]:
            data = (c.out / rel).read_bytes()
            key = hashlib.sha256(re.sub(rb"\s+", b" ", data)).hexdigest()
            if key not in text_ids:
                text_ids[key] = f"T{len(text_ids) + 1}"
                texts.append((text_ids[key], rel, []))
            tid = text_ids[key]
            next(t for t in texts if t[0] == tid)[2].append(x["name"])
            refs.append(tid)
        x["textIds"] = refs
    kind = None
    for x in comps:
        if x["kind"] != kind:
            kind = x["kind"]
            lines += ["", f"--- {SECTION[kind]} ---"]
        lines.append(f"{x['name']} {x['version']}".strip() + f" | {x['license']} | copyleft: {x['copyleft']}"
                     + (f" | texts: {', '.join(x['textIds'])}" if x["textIds"] else "")
                     + (f" | {x['note']}" if x.get("note") else ""))
    lines += ["", "=" * 100, "LICENCE TEXTS (each distinct text once)", "=" * 100]
    for tid, rel, users in texts:
        body = (c.out / rel).read_bytes().decode("utf-8", "replace")
        shown = ", ".join(users[:12]) + (f" and {len(users) - 12} more" if len(users) > 12 else "")
        lines += ["", "-" * 100, f"{tid}: {Path(rel).name}, used by {shown}", "-" * 100, body.rstrip()]
    (c.out / "THIRD-PARTY-NOTICES.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for x in comps:
        del x["textIds"]
    return doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", default="win-x64" if sys.platform == "win32" else "linux-x64")
    ap.add_argument("--site-packages", type=Path, help="the bundled site-packages (every distribution in it is listed)")
    ap.add_argument("--python-root", type=Path, help="the bundled Python folder (LICENSE.txt, FriBiDi)")
    ap.add_argument("--engines", type=Path, help="default: engines/<platform>")
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "licenses")
    args = ap.parse_args()
    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)
    c = Collector(args.out, args.platform)
    collect_electron(c)
    collect_npm(c)
    collect_python(c, args.site_packages, args.python_root)
    collect_engines(c, args.engines or ROOT / "engines" / args.platform)
    if (ROOT / "fonts" / "fonts.json").exists():
        collect_fonts(c, ROOT / "fonts")
    if (ROOT / "models" / "manifest.json").exists():
        collect_models(c, ROOT / "models")
    if c.unknown:
        raise SystemExit("licence unknown for: " + ", ".join(c.unknown) + " (add it to the overrides in this script)")
    doc = write_outputs(c, json.loads((ROOT / "package.json").read_text())["version"])
    s = doc["summary"]
    size = sum(f.stat().st_size for f in args.out.rglob("*") if f.is_file())
    print(f"[licences] {s['total']} components ({', '.join(f'{k} {v}' for k, v in s['byKind'].items())}); copyleft: "
          f"{', '.join(f'{k} {v}' for k, v in s['byCopyleft'].items())}; {size / 1e6:.1f} MB in {args.out}")
    for x in doc["components"]:
        if x["copyleft"] in ("network", "strong"):
            print(f"[licences]   {x['copyleft']}: {x['name']} {x['version']} ({x['license']})")


if __name__ == "__main__":
    main()
