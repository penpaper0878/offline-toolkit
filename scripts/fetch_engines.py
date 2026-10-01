#!/usr/bin/env python3
"""Fetch the document-conversion engines into engines/<platform>/ (build time only; the app never downloads).

    python scripts/fetch_engines.py --platform win-x64      # everything, for the Windows build
    python scripts/fetch_engines.py --platform linux-x64    # pandoc, veraPDF, resvg (CI installs the rest with apt)

Pinned, checksummed downloads where the source publishes checksums (Maven, PyPI). On Windows, LibreOffice,
Ghostscript, Tesseract and the Java runtime are installed with Chocolatey (preinstalled on GitHub's
runners) and their program folders are copied; the versions found are written to manifest.json, which
docs/ENGINES.md and the About box read.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PANDOC_WHEEL = "pypandoc_binary==1.16.2"   # official pandoc 3.8.2.1 build (data files embedded: works with --sandbox)
RESVG = "0.45.1"
VERAPDF = "1.28.2"
MAVEN = "https://repo1.maven.org/maven2"
VERAPDF_JARS = [
    ("org.verapdf.apps", "greenfield-apps", VERAPDF), ("org.verapdf.apps", "gui", VERAPDF),
    ("org.verapdf", "core", VERAPDF), ("org.verapdf", "feature-reporting", VERAPDF),
    ("org.verapdf", "metadata-fixer", VERAPDF), ("org.verapdf", "parser", VERAPDF), ("org.verapdf", "pdf-model", VERAPDF),
    ("org.verapdf", "validation-model", VERAPDF), ("org.verapdf", "verapdf-xmp-core", VERAPDF),
    ("com.fasterxml.jackson.core", "jackson-annotations", "2.15.0"), ("com.fasterxml.jackson.core", "jackson-core", "2.15.0"),
    ("com.fasterxml.jackson.core", "jackson-databind", "2.15.0"), ("javax.activation", "javax.activation-api", "1.2.0"),
    ("javax.xml.bind", "jaxb-api", "2.3.1"), ("com.sun.xml.bind", "jaxb-core", "2.3.0.1"),
    ("com.sun.xml.bind", "jaxb-impl", "2.3.2"), ("com.beust", "jcommander", "1.81"), ("org.mozilla", "rhino", "1.7.13"),
    ("net.java.dev.stax-utils", "stax-utils", "20070216"),
]
# Lite bundle (docs/ARCHITECTURE.md D2): compact tessdata_fast models.
TESS_LANGS = ["eng", "osd", "hin", "mar", "san", "nep", "ben", "guj", "pan", "tam", "tel", "kan", "mal", "ori", "urd",
              "ara", "heb"]
TESSDATA = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{lang}.traineddata"


def log(msg: str) -> None:
    print(f"[engines] {msg}", flush=True)


def download(url: str, *, sha1: str | None = None, attempts: int = 6) -> bytes:
    import time
    import urllib.error

    log(f"download {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "offline-toolkit-build"})
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                data = r.read()
            break
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            code = getattr(exc, "code", None)
            if i == attempts - 1 or code in (403, 404):
                raise
            wait = int(getattr(exc, "headers", {}).get("Retry-After", 0) or 0) if code == 429 else 0
            wait = max(wait, 2 ** (i + 1))
            log(f"  {exc}; retrying in {wait} s")
            time.sleep(wait)
    if sha1 and hashlib.sha1(data).hexdigest() != sha1:
        raise SystemExit(f"checksum mismatch for {url}")
    return data


def fetch_pandoc(dest: Path, plat: str) -> str:
    tag = "win_amd64" if plat.startswith("win") else "manylinux2014_x86_64"
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:", "--platform", tag,
                        "-d", tmp, PANDOC_WHEEL], check=True)
        wheel = next(Path(tmp).glob("*.whl"))
        with zipfile.ZipFile(wheel) as z:
            name = "pypandoc/files/pandoc.exe" if plat.startswith("win") else "pypandoc/files/pandoc"
            out = dest / "pandoc" / Path(name).name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read(name))
    out.chmod(0o755)
    return subprocess.run([str(out), "--version"], capture_output=True, text=True).stdout.splitlines()[0]


def fetch_verapdf(dest: Path, plat: str) -> str:
    lib = dest / "verapdf" / "lib"
    lib.mkdir(parents=True, exist_ok=True)
    for group, artifact, version in VERAPDF_JARS:
        base = f"{MAVEN}/{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.jar"
        target = lib / f"{artifact}-{version}.jar"
        if target.exists():
            continue
        sha1 = download(base + ".sha1").decode().split()[0].strip()
        target.write_bytes(download(base, sha1=sha1))
    return f"veraPDF {VERAPDF}"


def fetch_resvg(dest: Path, plat: str) -> str:
    asset = "resvg-win64.zip" if plat.startswith("win") else "resvg-linux-x86_64.tar.gz"
    data = download(f"https://github.com/linebender/resvg/releases/download/v{RESVG}/{asset}")
    out_dir = dest / "resvg"
    out_dir.mkdir(parents=True, exist_ok=True)
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            member = next(n for n in z.namelist() if n.endswith("resvg.exe"))
            (out_dir / "resvg.exe").write_bytes(z.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            member = next(m for m in t.getmembers() if m.name.endswith("resvg"))
            (out_dir / "resvg").write_bytes(t.extractfile(member).read())
            (out_dir / "resvg").chmod(0o755)
    return f"resvg {RESVG}"


def choco(package: str) -> None:
    subprocess.run(["choco", "install", package, "-y", "--no-progress", "--limit-output"], check=True)


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    log(f"copy {src} -> {dst}")
    shutil.copytree(src, dst)


def _program_files() -> Path:
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files"))


def _version(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return (r.stdout or r.stderr).strip().splitlines()[0]
    except Exception as exc:
        return f"unknown ({exc})"


def fetch_libreoffice(dest: Path, plat: str) -> str:
    choco("libreoffice-fresh")
    src = _program_files() / "LibreOffice"
    copy_tree(src, dest / "libreoffice")
    # Help and the dictionaries for typing are not needed for conversion.
    for sub in ("help", "share/extensions/dict-en", "share/extensions/dict-es", "share/extensions/dict-fr"):
        shutil.rmtree(dest / "libreoffice" / sub, ignore_errors=True)
    return _version([str(dest / "libreoffice" / "program" / "soffice.com"), "--version"])


def fetch_ghostscript(dest: Path, plat: str) -> str:
    choco("ghostscript")
    root = next((_program_files() / "gs").glob("gs*"))
    copy_tree(root, dest / "ghostscript")
    for sub in ("doc", "examples"):
        shutil.rmtree(dest / "ghostscript" / sub, ignore_errors=True)
    return "Ghostscript " + _version([str(dest / "ghostscript" / "bin" / "gswin64c.exe"), "--version"])


def fetch_tesseract(dest: Path, plat: str) -> str:
    choco("tesseract")
    copy_tree(_program_files() / "Tesseract-OCR", dest / "tesseract")
    return _version([str(dest / "tesseract" / "tesseract.exe"), "--version"])


def fetch_tessdata(dest: Path, plat: str) -> str:
    td = dest / "tesseract" / "tessdata"
    td.mkdir(parents=True, exist_ok=True)
    for old in td.glob("*.traineddata"):
        old.unlink()
    for lang in TESS_LANGS:
        (td / f"{lang}.traineddata").write_bytes(download(TESSDATA.format(lang=lang)))
    return f"tessdata_fast: {', '.join(TESS_LANGS)}"


def fetch_jre(dest: Path, plat: str) -> str:
    choco("temurin21jre")
    root = next((_program_files() / "Eclipse Adoptium").glob("jre-21*"))
    copy_tree(root, dest / "jre")
    return _version([str(dest / "jre" / "bin" / "java.exe"), "-version"])


COMPONENTS = {"pandoc": fetch_pandoc, "verapdf": fetch_verapdf, "resvg": fetch_resvg, "libreoffice": fetch_libreoffice,
              "ghostscript": fetch_ghostscript, "tesseract": fetch_tesseract, "tessdata": fetch_tessdata,
              "jre": fetch_jre}
DEFAULTS = {"win-x64": ["pandoc", "verapdf", "resvg", "libreoffice", "ghostscript", "tesseract", "tessdata", "jre"],
            "linux-x64": ["pandoc", "verapdf", "resvg"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True, choices=sorted(DEFAULTS))
    ap.add_argument("--components", help="comma-separated subset of " + ",".join(COMPONENTS))
    ap.add_argument("--dest", help="default: engines/<platform>")
    args = ap.parse_args()
    dest = Path(args.dest) if args.dest else ROOT / "engines" / args.platform
    dest.mkdir(parents=True, exist_ok=True)
    manifest_path = dest / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    for name in (args.components.split(",") if args.components else DEFAULTS[args.platform]):
        log(f"--- {name}")
        manifest[name] = COMPONENTS[name](dest, args.platform)
        log(f"{name}: {manifest[name]}")
        manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    total = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    log(f"engines in {dest}: {total / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
