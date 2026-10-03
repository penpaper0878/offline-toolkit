#!/usr/bin/env python3
"""Fetch the bundled fonts into fonts/ (build time only; the app never downloads).

    python scripts/fetch_fonts.py                 # download and verify against scripts/fonts.lock.json
    python scripts/fetch_fonts.py --update-lock   # after changing FAMILIES or COMMIT: rewrite the lock

Every file comes from the google/fonts repository at a pinned commit and is checked against the SHA-256
in scripts/fonts.lock.json. The result is fonts/<dir>/<files>, the licence of each family, and
fonts/fonts.json: the catalogue the worker (font matching, exports) and the app (editor) read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "9710da1eacb3be272583c3224dcb70f9da6eadbb"   # google/fonts main, 2026-10-03
RAW = f"https://raw.githubusercontent.com/google/fonts/{COMMIT}"
LOCK = ROOT / "scripts" / "fonts.lock.json"

# (repository directory, role). Roles group the families in the editor's font menu; matching uses all.
FAMILIES: list[tuple[str, str]] = [
    # Sans serif
    ("ofl/roboto", "sans"), ("ofl/opensans", "sans"), ("ofl/lato", "sans"), ("ofl/montserrat", "sans"),
    ("ofl/poppins", "sans"), ("ofl/inter", "sans"), ("ofl/raleway", "sans"), ("ofl/nunito", "sans"),
    ("ofl/sourcesans3", "sans"), ("ofl/ptsans", "sans"), ("ofl/worksans", "sans"), ("ofl/josefinsans", "sans"),
    ("ofl/quicksand", "sans"), ("ufl/ubuntu", "sans"), ("ofl/firasans", "sans"), ("ofl/barlow", "sans"),
    ("ofl/rubik", "sans"), ("ofl/dmsans", "sans"), ("ofl/manrope", "sans"), ("ofl/notosans", "sans"),
    ("ofl/arimo", "sans"), ("ofl/carlito", "sans"), ("ofl/archivo", "sans"), ("ofl/kanit", "sans"),
    # Serif
    ("ofl/playfairdisplay", "serif"), ("ofl/merriweather", "serif"), ("ofl/ebgaramond", "serif"),
    ("ofl/lora", "serif"), ("ofl/librebaskerville", "serif"), ("apache/robotoslab", "serif"), ("ofl/ptserif", "serif"),
    ("ofl/notoserif", "serif"), ("ofl/tinos", "serif"), ("ofl/caladea", "serif"), ("ofl/crimsontext", "serif"),
    ("ofl/bitter", "serif"), ("ofl/cormorantgaramond", "serif"),
    # Display
    ("ofl/oswald", "display"), ("ofl/bebasneue", "display"), ("ofl/anton", "display"), ("ofl/abrilfatface", "display"),
    ("ofl/cinzel", "display"), ("ofl/lobster", "display"), ("ofl/alfaslabone", "display"), ("ofl/archivoblack", "display"),
    ("ofl/righteous", "display"),
    # Script and handwriting
    ("ofl/greatvibes", "script"), ("ofl/dancingscript", "script"), ("ofl/pacifico", "script"), ("ofl/caveat", "script"),
    ("apache/satisfy", "script"), ("ofl/allura", "script"), ("ofl/kaushanscript", "script"),
    # Monospace
    ("ofl/robotomono", "mono"), ("ofl/cousine", "mono"), ("ofl/sourcecodepro", "mono"),
    # Indic, Arabic, Hebrew (Latin families above cover the rest)
    ("ofl/mukta", "sans"), ("ofl/hind", "sans"), ("ofl/baloo2", "display"), ("ofl/notosansdevanagari", "sans"),
    ("ofl/notoserifdevanagari", "serif"), ("ofl/notosansbengali", "sans"), ("ofl/notosansgujarati", "sans"),
    ("ofl/notosansgurmukhi", "sans"), ("ofl/notosanstamil", "sans"), ("ofl/notosanstelugu", "sans"),
    ("ofl/notosanskannada", "sans"), ("ofl/notosansmalayalam", "sans"), ("ofl/notosansoriya", "sans"),
    ("ofl/notosansarabic", "sans"), ("ofl/notonaskharabic", "serif"), ("ofl/notonastaliqurdu", "serif"),
    ("ofl/notosanshebrew", "sans"),
]

# Unicode ranges used to label which scripts a font covers (a family "covers" a script when it maps
# at least 80% of these characters).
SCRIPTS = {
    "latin": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
    "devanagari": "अआइईउऊएऐओऔकखगघचछजझटठडढणतथदधनपफबभमयरलवशषसह्ािीुूेैोौंः",
    "bengali": "অআইঈউঊএঐওঔকখগঘচছজঝটঠডঢণতথদধনপফবভমযরলশষসহ্ািীুূেৈোৌ",
    "gujarati": "અઆઇઈઉઊએઐઓઔકખગઘચછજઝટઠડઢણતથદધનપફબભમયરલવશષસહ્ાિીુૂેૈોૌ",
    "gurmukhi": "ਅਆਇਈਉਊਏਐਓਔਕਖਗਘਚਛਜਝਟਠਡਢਣਤਥਦਧਨਪਫਬਭਮਯਰਲਵਸਹ੍ਾਿੀੁੂੇੈੋੌ",
    "tamil": "அஆஇஈஉஊஎஏஐஒஓஔகஙசஞடணதநபமயரலவழளறன்ாிீுூெேைொோௌ",
    "telugu": "అఆఇఈఉఊఎఏఐఒఓఔకఖగఘచఛజఝటఠడఢణతథదధనపఫబభమయరలవశషసహ్ాిీుూెేైొోౌ",
    "kannada": "ಅಆಇಈಉಊಎಏಐಒಓಔಕಖಗಘಚಛಜಝಟಠಡಢಣತಥದಧನಪಫಬಭಮಯರಲವಶಷಸಹ್ಾಿೀುೂೆೇೈೊೋೌ",
    "malayalam": "അആഇഈഉഊഎഏഐഒഓഔകഖഗഘചഛജഝടഠഡഢണതഥദധനപഫബഭമയരലവശഷസഹ്ാിീുൂെേൈൊോൌ",
    "oriya": "ଅଆଇଈଉଊଏଐଓଔକଖଗଘଚଛଜଝଟଠଡଢଣତଥଦଧନପଫବଭମଯରଲଶଷସହ୍ାିୀୁୂେୈୋୌ",
    "arabic": "ابتثجحخدذرزسشصضطظعغفقكلمنهوي",
    "hebrew": "אבגדהוזחטיכלמנסעפצקרשת",
}


def keep(f: dict) -> bool:
    """Static families ship up to 18 weights; light, regular, bold and black (italics for regular and bold)
    cover what posters and documents use. Variable fonts hold every weight in one file and are kept."""
    if "[" in f["file"]:
        return True
    return f["weight"] in (300, 400, 700, 900) and (f["style"] == "normal" or f["weight"] in (400, 700))


def log(msg: str) -> None:
    print(f"[fonts] {msg}", flush=True)


def get(url: str, attempts: int = 5) -> bytes:
    import urllib.error

    for i in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except Exception as exc:  # network hiccup: retry with backoff (a 404 will not get better)
            if i == attempts - 1 or isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
                raise RuntimeError(f"download failed: {url}: {exc}") from exc
            time.sleep(2 ** (i + 1))
    raise AssertionError


def parse_metadata(text: str) -> dict:
    """The parts of a google/fonts METADATA.pb (protobuf text format) the catalogue needs."""
    meta = {"name": re.search(r'^name:\s*"([^"]+)"', text, re.M).group(1),
            "category": (re.search(r'^category:\s*"([^"]+)"', text, re.M) or [None, ""])[1],
            "fonts": [], "axes": {}}
    for block in re.findall(r"^fonts\s*\{(.*?)^\}", text, re.M | re.S):
        f = dict(re.findall(r'^\s*(\w+):\s*"?([^"\n]+)"?', block, re.M))
        meta["fonts"].append({"file": f["filename"], "style": f.get("style", "normal"), "weight": int(f.get("weight", 400))})
    for block in re.findall(r"^axes\s*\{(.*?)^\}", text, re.M | re.S):
        a = dict(re.findall(r'^\s*(\w+):\s*"?([^"\n]+)"?', block, re.M))
        meta["axes"][a["tag"]] = [float(a["min_value"]), float(a["max_value"])]
    return meta


def coverage(path: Path) -> list[str]:
    from fontTools.ttLib import TTFont

    cmap = TTFont(path, lazy=True).getBestCmap() or {}
    out = []
    for script, chars in SCRIPTS.items():
        if sum(ord(c) in cmap for c in chars) >= 0.8 * len(chars):
            out.append(script)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-lock", action="store_true")
    ap.add_argument("--dest", default=str(ROOT / "fonts"))
    args = ap.parse_args()
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    lock = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.exists() and not args.update_lock else {}
    if lock and lock.get("commit") != COMMIT:
        sys.exit("fonts.lock.json is for another commit: run with --update-lock")
    new_lock = {"commit": COMMIT, "files": {}}
    catalogue = []
    for d, role in FAMILIES:
        meta = parse_metadata(get(f"{RAW}/{d}/METADATA.pb").decode("utf-8"))
        fam_dir = dest / Path(d).name
        fam_dir.mkdir(exist_ok=True)
        files = []
        for f in meta["fonts"]:
            if not keep(f):
                continue
            rel = f"{d}/{f['file']}"
            target = fam_dir / f["file"]
            want = lock.get("files", {}).get(rel)
            if target.exists() and want and hashlib.sha256(target.read_bytes()).hexdigest() == want:
                data = target.read_bytes()
            else:
                data = get(f"{RAW}/{rel}")
            digest = hashlib.sha256(data).hexdigest()
            if want and digest != want:
                sys.exit(f"SHA-256 mismatch for {rel}")
            if not want and lock:
                sys.exit(f"{rel} is not in fonts.lock.json: run with --update-lock")
            target.write_bytes(data)
            new_lock["files"][rel] = digest
            files.append({"file": f"{fam_dir.name}/{f['file']}", "style": f["style"], "weight": f["weight"]})
        licence = next((n for n in ("OFL.txt", "LICENSE.txt", "UFL.txt") if _exists(f"{RAW}/{d}/{n}")), None)
        if licence:
            (fam_dir / licence).write_bytes(get(f"{RAW}/{d}/{licence}"))
        # One file per (style, weight) for static families; a variable family lists each file once
        # with the weight range of its wght axis.
        uniq = {}
        for f in files:
            uniq.setdefault(f["file"], {"file": f["file"], "style": f["style"], "weights": []})["weights"].append(f["weight"])
        entries = []
        for f in uniq.values():
            w = meta["axes"].get("wght")
            entries.append({"file": f["file"], "style": f["style"],
                            "weight": [int(w[0]), int(w[1])] if w and "[" in f["file"] else [min(f["weights"]), max(f["weights"])]})
        catalogue.append({"family": meta["name"], "dir": fam_dir.name, "role": role, "category": meta["category"],
                          "licence": {"ofl": "OFL-1.1", "apache": "Apache-2.0", "ufl": "UFL-1.0"}[d.split("/")[0]],
                          "licenceFile": f"{fam_dir.name}/{licence}" if licence else None,
                          "scripts": coverage(dest / entries[0]["file"]), "axes": meta["axes"], "files": entries})
        log(f"{meta['name']}: {len(entries)} file(s), {', '.join(catalogue[-1]['scripts'])}")
    (dest / "fonts.json").write_text(json.dumps({"source": f"https://github.com/google/fonts/tree/{COMMIT}",
                                                 "families": catalogue}, indent=1, ensure_ascii=False), encoding="utf-8")
    if args.update_lock:
        LOCK.write_text(json.dumps(new_lock, indent=1, sort_keys=True), encoding="utf-8")
        log(f"wrote {LOCK}")
    total = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    log(f"{len(catalogue)} families, {total / 1e6:.0f} MB in {dest}")


def _exists(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30):
            return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
