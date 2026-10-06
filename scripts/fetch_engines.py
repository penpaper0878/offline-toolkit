#!/usr/bin/env python3
"""Fetch the document-conversion engines into engines/<platform>/ (build time only; the app never downloads).

    python scripts/fetch_engines.py --platform win-x64      # everything, for the Windows build
    python scripts/fetch_engines.py --platform linux-x64    # pandoc, veraPDF, resvg (CI installs the rest with apt)
    python scripts/fetch_engines.py --platform win-x64 --relock   # maintainers: resolve new releases, rewrite the lock

Every download is pinned in scripts/engines.lock.json (URL + SHA-256) and checked before it is used, so two
builds from the same lock bundle the same files. `--relock` looks up the current releases of the engines that
follow upstream (LibreOffice, Ghostscript, Tesseract, the Java runtime, tessdata_fast), downloads everything,
checks the publishers' own checksums where they publish them, and writes the new URLs and SHA-256 sums; it
installs nothing (the `[relock]` CI job runs it). Pandoc, veraPDF, resvg and Python stay at the versions below
because the tests depend on their exact behaviour.

On Windows the official installers of LibreOffice (MSI), Ghostscript and Tesseract (NSIS) are run silently into
build/engine-install (admin rights needed, as on GitHub's runners) and their program folders copied. The Java
runtime is cut from the Temurin JDK with jlink down to the modules veraPDF needs. The versions found are written
to manifest.json, which docs/ENGINES.md and Settings read.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "scripts" / "engines.lock.json"
CACHE = ROOT / "build" / "cache" / "engines"
INSTALL = ROOT / "build" / "engine-install"

PYTHON_EMBED = "3.11.9"                        # last 3.11 release with Windows binaries (scripts/bundle-python-win.mjs)
PANDOC_WHEEL = ("pypandoc_binary", "1.16.2")   # official pandoc 3.8.2.1 build (data files embedded: works with --sandbox)
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
# The modules veraPDF's jars use (jdeps --print-module-deps over them), plus naming, scripting and the extra
# charsets, which its parsers can load by reflection. A runtime cut to these gives the same PDF/A reports as a
# full JDK (docs/ENGINES.md §0d).
JRE_MODULES = ["java.base", "java.compiler", "java.datatransfer", "java.desktop", "java.logging", "java.management",
               "java.naming", "java.scripting", "java.sql", "java.xml", "jdk.charsets", "jdk.unsupported"]
# Lite bundle (docs/ARCHITECTURE.md D2): compact tessdata_fast models.
TESS_LANGS = ["eng", "osd", "hin", "mar", "san", "nep", "ben", "guj", "pan", "tam", "tel", "kan", "mal", "ori", "urd",
              "ara", "heb"]

# The mature LibreOffice series (TDF's "still" branch), the one the converter's tests were tuned on; a new feature
# series (x.8.0, x.2.0) waits until it has had its bug-fix releases.
LIBREOFFICE_SERIES = "26.2"
TDF_ARCHIVE = "https://downloadarchive.documentfoundation.org/libreoffice/old/"
ADOPTIUM = ("https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows"
            "&vendor=eclipse")


def log(msg: str) -> None:
    print(f"[engines] {msg}", flush=True)


# --- downloads --------------------------------------------------------------------------------------------------

def _open(url: str, attempts: int = 6):
    headers = {"User-Agent": "offline-toolkit-build"}
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    for i in range(attempts):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=600)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            code = getattr(exc, "code", None)
            if i == attempts - 1 or code in (403, 404):
                raise
            wait = int(getattr(exc, "headers", {}).get("Retry-After", 0) or 0) if code == 429 else 0
            wait = max(wait, 2 ** (i + 1))
            log(f"  {exc}; retrying in {wait} s")
            time.sleep(wait)
    raise AssertionError("unreachable")


def text(url: str) -> str:
    with _open(url) as r:
        return r.read().decode("utf-8", "replace")


def download(url: str, target: Path, attempts: int = 4) -> tuple[str, str]:
    """Stream `url` into `target`; returns its (sha256, sha1)."""
    log(f"download {url}")
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    for i in range(attempts):
        h256, h1 = hashlib.sha256(), hashlib.sha1()
        try:
            with _open(url) as r, part.open("wb") as out:
                while chunk := r.read(1 << 20):
                    h256.update(chunk)
                    h1.update(chunk)
                    out.write(chunk)
            part.replace(target)
            return h256.hexdigest(), h1.hexdigest()
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            part.unlink(missing_ok=True)
            if i == attempts - 1 or getattr(exc, "code", None) in (403, 404):
                raise
            log(f"  {exc}; retrying")
            time.sleep(2 ** (i + 2))
    raise AssertionError("unreachable")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def get(file: dict) -> Path:
    """A locked file: from the download cache when its SHA-256 matches, else downloaded and checked."""
    target = CACHE / f"{file['sha256'][:16]}-{file['name']}"
    if target.exists() and sha256_of(target) == file["sha256"]:
        return target
    digest, _ = download(file["url"], target)
    if digest != file["sha256"]:
        target.unlink(missing_ok=True)
        raise SystemExit(f"SHA-256 mismatch for {file['url']}: got {digest}, the lock says {file['sha256']}")
    return target


# --- what to download (--relock) ---------------------------------------------------------------------------------
# Each resolver returns the version and the files: name, URL and, where the publisher states one, its checksum.

Resolved = tuple[str, list[dict]]


def _vkey(name: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", name))


def _github_latest(repo: str, pattern: str) -> tuple[dict, dict]:
    """The highest-numbered file matching `pattern` among the repository's published (non-draft, non-pre-) releases."""
    found = []
    for rel in json.loads(text(f"https://api.github.com/repos/{repo}/releases?per_page=100")):
        hits = [a for a in rel.get("assets", []) if re.fullmatch(pattern, a["name"])]
        log(f"  {repo} {rel.get('tag_name')}: {'draft ' if rel.get('draft') else ''}"
            f"{'pre-release ' if rel.get('prerelease') else ''}{', '.join(a['name'] for a in hits) or '-'}")
        if not (rel.get("draft") or rel.get("prerelease")):
            found += [(rel, a) for a in hits]
    if not found:
        raise SystemExit(f"no release of {repo} has a file matching {pattern}")
    return max(found, key=lambda ra: _vkey(ra[1]["name"]))


def _asset(asset: dict) -> dict:
    out = {"name": asset["name"], "url": asset["browser_download_url"]}
    if str(asset.get("digest") or "").startswith("sha256:"):
        out["publisher_sha256"] = asset["digest"].split(":", 1)[1]
    return out


def resolve_python(plat: str) -> Resolved:
    name = f"python-{PYTHON_EMBED}-embed-amd64.zip"
    return f"CPython {PYTHON_EMBED} embeddable", [{"name": name, "url": f"https://www.python.org/ftp/python/{PYTHON_EMBED}/{name}"}]


def resolve_pandoc(plat: str) -> Resolved:
    project, version = PANDOC_WHEEL
    tag = "win_amd64" if plat.startswith("win") else "manylinux2014_x86_64"
    meta = json.loads(text(f"https://pypi.org/pypi/{project}/{version}/json"))
    wheel = next(u for u in meta["urls"] if u["packagetype"] == "bdist_wheel" and tag in u["filename"])
    return f"{project} {version}", [{"name": wheel["filename"], "url": wheel["url"],
                                     "publisher_sha256": wheel["digests"]["sha256"]}]


def resolve_verapdf(plat: str) -> Resolved:
    files = []
    for group, artifact, version in VERAPDF_JARS:
        url = f"{MAVEN}/{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.jar"
        files.append({"name": f"{artifact}-{version}.jar", "url": url,
                      "publisher_sha1": text(url + ".sha1").split()[0].strip()})
    return f"veraPDF {VERAPDF}", files


def resolve_resvg(plat: str) -> Resolved:
    asset = "resvg-win64.zip" if plat.startswith("win") else "resvg-linux-x86_64.tar.gz"
    return f"resvg {RESVG}", [{"name": asset,
                               "url": f"https://github.com/linebender/resvg/releases/download/v{RESVG}/{asset}"}]


def resolve_libreoffice(plat: str) -> Resolved:
    """The newest release of the LIBREOFFICE_SERIES in The Document Foundation's archive (permanent URLs, unlike
    the mirrors, which drop a release when the next one comes out)."""
    found = re.findall(r'href="(\d+\.\d+\.\d+\.\d+)/"', text(TDF_ARCHIVE))
    series = tuple(int(p) for p in LIBREOFFICE_SERIES.split("."))
    candidates = {tuple(int(p) for p in v.split(".")) for v in found}
    for v in sorted((c for c in candidates if c[:2] == series), reverse=True)[:6]:
        ver = ".".join(map(str, v))
        folder = f"{TDF_ARCHIVE}{ver}/win/x86_64/"
        try:
            listing = text(folder)
        except urllib.error.HTTPError:
            continue
        m = re.search(r'href="(LibreOffice_[\d.]+_Win_x86-64\.msi)"', listing)
        if m:
            return f"LibreOffice {ver}", [{"name": m.group(1), "url": folder + m.group(1)}]
    raise SystemExit(f"no LibreOffice {LIBREOFFICE_SERIES} MSI found in the archive")


def resolve_ghostscript(plat: str) -> Resolved:
    rel, asset = _github_latest("ArtifexSoftware/ghostpdl-downloads", r"gs\d+w64\.exe")
    m = re.search(r"(\d+\.\d+\.\d+)", rel.get("name") or "")
    if m:
        ver = m.group(1)
    else:
        digits = re.search(r"gs(\d+)w64", asset["name"]).group(1)
        ver = f"{digits[:-3]}.{digits[-3:-1]}.{digits[-1]}"
    return f"Ghostscript {ver}", [_asset(asset)]


def resolve_tesseract(plat: str) -> Resolved:
    _, asset = _github_latest("UB-Mannheim/tesseract", r"tesseract-ocr-w64-setup-[\w.\-]+\.exe")
    ver = re.search(r"setup-([\w.\-]+)\.exe", asset["name"]).group(1)
    return f"Tesseract {ver} (UB Mannheim)", [_asset(asset)]


def resolve_tessdata(plat: str) -> Resolved:
    sha = json.loads(text("https://api.github.com/repos/tesseract-ocr/tessdata_fast/commits/main"))["sha"]
    return f"tessdata_fast@{sha[:12]}", [
        {"name": f"{lang}.traineddata", "url": f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{sha}/{lang}.traineddata"}
        for lang in TESS_LANGS]


def resolve_jdk(plat: str) -> Resolved:
    """The Temurin 21 JDK zip (it carries jlink and the module files) from the Adoptium API."""
    pkg = json.loads(text(ADOPTIUM))[0]
    return f"Temurin {pkg['release_name']}", [{"name": pkg["binary"]["package"]["name"],
                                                "url": pkg["binary"]["package"]["link"],
                                                "publisher_sha256": pkg["binary"]["package"]["checksum"]}]


RESOLVERS: dict[str, Callable[[str], Resolved]] = {
    "python": resolve_python, "pandoc": resolve_pandoc, "verapdf": resolve_verapdf, "resvg": resolve_resvg,
    "libreoffice": resolve_libreoffice, "ghostscript": resolve_ghostscript, "tesseract": resolve_tesseract,
    "tessdata": resolve_tessdata, "jre": resolve_jdk,
}
LOCKED = {"win-x64": ["python", "pandoc", "verapdf", "resvg", "libreoffice", "ghostscript", "tesseract", "tessdata", "jre"],
          "linux-x64": ["pandoc", "verapdf", "resvg"]}


def relock(plat: str, names: list[str]) -> None:
    names = [n for n in names if n in LOCKED[plat]]
    if not names:
        return
    lock = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.exists() else {}
    section = lock.setdefault(plat, {})
    for name in names:
        version, files = RESOLVERS[name](plat)
        log(f"{name}: {version}")
        pinned = []
        for f in files:
            target = CACHE / "relock" / f["name"]
            digest, sha1 = download(f["url"], target)
            if f.get("publisher_sha256") and f["publisher_sha256"].lower() != digest:
                raise SystemExit(f"{f['url']}: SHA-256 {digest} differs from the publisher's {f['publisher_sha256']}")
            if f.get("publisher_sha1") and f["publisher_sha1"].lower() != sha1:
                raise SystemExit(f"{f['url']}: SHA-1 {sha1} differs from the publisher's {f['publisher_sha1']}")
            pinned.append({"name": f["name"], "url": f["url"], "sha256": digest, "size": target.stat().st_size})
            target.unlink()
        section[name] = {"version": version, "files": pinned}
    lock["about"] = ("Pinned build-time downloads of the bundled engines and the Windows Python: scripts/fetch_engines.py "
                     "and scripts/bundle-python-win.mjs check every file against its SHA-256. "
                     "Rewrite with `python scripts/fetch_engines.py --platform <p> --relock`.")
    lock.setdefault("resolved", {})[plat] = dt.date.today().isoformat()
    lock[plat] = dict(sorted(section.items()))
    LOCK.write_text(json.dumps(dict(sorted(lock.items())), indent=1) + "\n", encoding="utf-8")
    log(f"lock written: {LOCK}")


# --- installing --------------------------------------------------------------------------------------------------

def run(cmd: list[str], **kw) -> None:
    log("> " + " ".join(cmd))
    subprocess.run(cmd, check=True, **kw)


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    log(f"copy {src} -> {dst}")
    shutil.copytree(src, dst)


def _version(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return (r.stdout or r.stderr).strip().splitlines()[0]
    except Exception as exc:
        return f"unknown ({exc})"


def _fresh(path: Path) -> Path:
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def _found(root: Path, name: str, what: str) -> Path:
    hit = next(iter(sorted(root.rglob(name))), None)
    if not hit:
        raise SystemExit(f"{what}: {name} not found under {root}")
    return hit


def install_pandoc(dest: Path, plat: str, entry: dict, files: list[Path]) -> str:
    with zipfile.ZipFile(files[0]) as z:
        name = "pypandoc/files/pandoc.exe" if plat.startswith("win") else "pypandoc/files/pandoc"
        out = dest / "pandoc" / Path(name).name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(z.read(name))
    out.chmod(0o755)
    return _version([str(out), "--version"])


def install_verapdf(dest: Path, plat: str, entry: dict, files: list[Path]) -> str:
    lib = _fresh(dest / "verapdf" / "lib")
    for f, meta in zip(files, entry["files"]):
        shutil.copyfile(f, lib / meta["name"])
    return entry["version"]


def install_resvg(dest: Path, plat: str, entry: dict, files: list[Path]) -> str:
    out_dir = dest / "resvg"
    out_dir.mkdir(parents=True, exist_ok=True)
    if files[0].name.endswith(".zip"):
        with zipfile.ZipFile(files[0]) as z:
            member = next(n for n in z.namelist() if n.endswith("resvg.exe"))
            (out_dir / "resvg.exe").write_bytes(z.read(member))
    else:
        with tarfile.open(files[0]) as t:
            member = next(m for m in t.getmembers() if m.name.endswith("resvg"))
            (out_dir / "resvg").write_bytes(t.extractfile(member).read())
            (out_dir / "resvg").chmod(0o755)
    return entry["version"]


def install_libreoffice(dest: Path, plat: str, entry: dict, files: list[Path]) -> str:
    target = _fresh(INSTALL / "libreoffice")
    # Documented MSI properties: no desktop icon, no file associations, no update checks, no quick starter.
    run(["msiexec", "/i", str(files[0]), "/qn", "/norestart", f"INSTALLLOCATION={target}", "CREATEDESKTOPLINK=0",
         "REGISTER_ALL_MSO_TYPES=0", "REGISTER_NO_MSO_TYPES=1", "ISCHECKFORPRODUCTUPDATES=0", "QUICKSTART=0",
         "UI_LANGS=en_US", "/l*v", str(INSTALL / "libreoffice-msi.log")])
    root = _found(target, "soffice.com", "LibreOffice").parent.parent
    copy_tree(root, dest / "libreoffice")
    # Help and the dictionaries for typing are not needed for conversion.
    for sub in ("help", "share/extensions/dict-en", "share/extensions/dict-es", "share/extensions/dict-fr"):
        shutil.rmtree(dest / "libreoffice" / sub, ignore_errors=True)
    return _version([str(dest / "libreoffice" / "program" / "soffice.com"), "--version"])


def _nsis(installer: Path, target: Path) -> None:
    # NSIS wants /D= last and unquoted, so the command line is passed as is and the folder may not contain spaces.
    if " " in str(target):
        raise SystemExit(f"the install folder must not contain spaces: {target}")
    log(f"> {installer.name} /S /D={target}")
    subprocess.run(f'"{installer}" /S /D={target}', check=True)


def install_ghostscript(dest: Path, plat: str, entry: dict, files: list[Path]) -> str:
    target = _fresh(INSTALL / "ghostscript")
    _nsis(files[0], target)
    root = _found(target, "gswin64c.exe", "Ghostscript").parent.parent
    copy_tree(root, dest / "ghostscript")
    for sub in ("doc", "examples"):
        shutil.rmtree(dest / "ghostscript" / sub, ignore_errors=True)
    return "Ghostscript " + _version([str(dest / "ghostscript" / "bin" / "gswin64c.exe"), "--version"])


def install_tesseract(dest: Path, plat: str, entry: dict, files: list[Path]) -> str:
    target = _fresh(INSTALL / "tesseract")
    _nsis(files[0], target)
    copy_tree(_found(target, "tesseract.exe", "Tesseract").parent, dest / "tesseract")
    return _version([str(dest / "tesseract" / "tesseract.exe"), "--version"])


def install_tessdata(dest: Path, plat: str, entry: dict, files: list[Path]) -> str:
    td = dest / "tesseract" / "tessdata"
    td.mkdir(parents=True, exist_ok=True)
    for old in td.glob("*.traineddata"):
        old.unlink()
    for f, meta in zip(files, entry["files"]):
        shutil.copyfile(f, td / meta["name"])
    return f"{entry['version']}: {', '.join(m['name'].split('.')[0] for m in entry['files'])}"


def install_jre(dest: Path, plat: str, entry: dict, files: list[Path]) -> str:
    jdk = _fresh(INSTALL / "jdk")
    with zipfile.ZipFile(files[0]) as z:
        z.extractall(jdk)
    jlink = _found(jdk, "jlink.exe" if plat.startswith("win") else "jlink", "the JDK")
    out = dest / "jre"
    shutil.rmtree(out, ignore_errors=True)
    run([str(jlink), "--module-path", str(jlink.parent.parent / "jmods"), "--add-modules", ",".join(JRE_MODULES),
         "--strip-debug", "--no-man-pages", "--no-header-files", "--compress=zip-6", "--output", str(out)])
    java = out / "bin" / ("java.exe" if plat.startswith("win") else "java")
    return f"{_version([str(java), '-version'])} (jlink: {len(JRE_MODULES)} modules)"


INSTALLERS = {"pandoc": install_pandoc, "verapdf": install_verapdf, "resvg": install_resvg,
              "libreoffice": install_libreoffice, "ghostscript": install_ghostscript, "tesseract": install_tesseract,
              "tessdata": install_tessdata, "jre": install_jre}
DEFAULTS = {"win-x64": ["pandoc", "verapdf", "resvg", "libreoffice", "ghostscript", "tesseract", "tessdata", "jre"],
            "linux-x64": ["pandoc", "verapdf", "resvg"]}


def locked(plat: str, name: str) -> dict:
    lock = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.exists() else {}
    entry = lock.get(plat, {}).get(name)
    if not entry or not entry.get("files") or not all(f.get("sha256") for f in entry["files"]):
        raise SystemExit(f"{name} ({plat}) is not in {LOCK.name}: run with --relock first")
    return entry


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True, choices=sorted(DEFAULTS))
    ap.add_argument("--components", help="comma-separated subset of " + ",".join(RESOLVERS))
    ap.add_argument("--dest", help="default: engines/<platform>")
    ap.add_argument("--relock", action="store_true", help="resolve current releases and rewrite the lock (installs nothing)")
    args = ap.parse_args()
    if args.relock:
        relock(args.platform, args.components.split(",") if args.components else LOCKED[args.platform])
        return
    dest = Path(args.dest) if args.dest else ROOT / "engines" / args.platform
    dest.mkdir(parents=True, exist_ok=True)
    manifest_path = dest / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    for name in (args.components.split(",") if args.components else DEFAULTS[args.platform]):
        log(f"--- {name}")
        entry = locked(args.platform, name)
        files = [get(f) for f in entry["files"]]
        manifest[name] = INSTALLERS[name](dest, args.platform, entry, files)
        log(f"{name}: {manifest[name]}")
        manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    total = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    log(f"engines in {dest}: {total / 1e6:.0f} MB")


if __name__ == "__main__":
    sys.exit(main())
