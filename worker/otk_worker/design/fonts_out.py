"""Fonts for the exported files.

Office applications pick fonts by family name plus bold/italic, so every other weight is a family of its
own there ("Inter SemiBold", "Lato Light"). The bundled variable fonts are therefore cut into static
instances named that way, which the PPTX and DOCX writers refer to, DOCX embeds, the app can install for
the user, and the SVG and HTML writers subset and embed (WOFF2). One static instance per weight also
keeps every output on the same outlines: other axes (optical size, width) stay at their defaults.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import tempfile
import threading
import uuid
from pathlib import Path

from . import assets

WEIGHT_NAMES = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold",
                700: "Bold", 800: "ExtraBold", 900: "Black"}

_lock = threading.Lock()
logging.getLogger("fontTools").setLevel(logging.ERROR)


def cache_dir() -> Path:
    d = Path(os.environ.get("OTK_CACHE") or Path(tempfile.gettempdir()) / "otk-cache") / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def snap_weight(weight: int) -> int:
    return max(100, min(900, int(round(weight / 100.0)) * 100))


def office_name(family: str, weight: int, italic: bool) -> tuple[str, bool, bool]:
    """(typeface, bold, italic) as Office names the face: 400 and 700 are the family itself, plain or
    bold; any other weight is a family of its own named after the weight."""
    w = snap_weight(weight)
    if w in (400, 700):
        return family, w == 700, italic
    return f"{family} {WEIGHT_NAMES[w]}", False, italic


def static_font(family: str, weight: int, italic: bool) -> Path | None:
    """A static TrueType file of the face, named the Office way (see office_name)."""
    face = assets.face(family, weight, italic)
    if face is None:
        return None
    w = snap_weight(face.weight)
    if not face.variable:
        return face.path
    key = hashlib.sha1(f"{face.path.name}|{face.path.stat().st_size}|{w}|{italic}".encode()).hexdigest()[:12]
    out = cache_dir() / f"{family.replace(' ', '')}-{w}{'i' if face.italic else ''}-{key}.ttf"
    with _lock:
        if out.is_file():
            return out
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer

        tt = TTFont(str(face.path))
        axes = {a.axisTag: (w if a.axisTag == "wght" else a.defaultValue) for a in tt["fvar"].axes}
        if "wght" in axes:
            lo, hi = next((a.minValue, a.maxValue) for a in tt["fvar"].axes if a.axisTag == "wght")
            axes["wght"] = max(lo, min(hi, w))
        inst = instancer.instantiateVariableFont(tt, axes, inplace=False)
        _rename(inst, family, w, face.italic)
        tmp = out.with_suffix(".tmp")
        inst.save(str(tmp))
        tmp.replace(out)
    return out


def _rename(tt, family: str, weight: int, italic: bool) -> None:
    """Name tables, weight class and style bits for a static instance (RIBBI naming for Office)."""
    typeface, bold, _ = office_name(family, weight, italic)
    sub = ("Bold " if bold else "") + ("Italic" if italic else "")
    sub = sub.strip() or "Regular"
    typo_sub = WEIGHT_NAMES[weight] if not italic else ("Italic" if weight == 400 else f"{WEIGHT_NAMES[weight]} Italic")
    full = f"{family} {typo_sub}" if typo_sub != "Regular" else family
    ps = (family + "-" + typo_sub).replace(" ", "")
    name = tt["name"]
    for rec in list(name.names):
        if rec.nameID in (1, 2, 3, 4, 6, 16, 17, 21, 22, 25) or rec.nameID >= 256:
            name.removeNames(nameID=rec.nameID)
    for nid, val in ((1, typeface), (2, sub), (3, f"{ps};otk"), (4, full), (6, ps[:63]), (16, family), (17, typo_sub)):
        name.setName(val, nid, 3, 1, 0x409)
        name.setName(val, nid, 1, 0, 0)
    if "fvar" in tt:
        del tt["fvar"]
    for tag in ("STAT",):
        if tag in tt:
            del tt[tag]
    os2 = tt["OS/2"]
    os2.usWeightClass = weight
    sel = os2.fsSelection & ~(0b1100001)          # clear ITALIC, BOLD, REGULAR
    if italic:
        sel |= 1
    if bold:
        sel |= 1 << 5
    if not italic and not bold:
        sel |= 1 << 6
    os2.fsSelection = sel
    tt["head"].macStyle = (1 if bold else 0) | (2 if italic else 0)


def faces_used(scene: dict) -> list[tuple[str, int, bool]]:
    """(family, weight, italic) of every text and table in the scene, in first-use order."""
    seen: list[tuple[str, int, bool]] = []

    def add(f, w, i):
        key = (f, snap_weight(w), bool(i))
        if key not in seen:
            seen.append(key)

    for lyr in scene["layers"]:
        if lyr["type"] == "text":
            st = lyr["style"]
            add(st["family"], st["weight"], st["italic"])
        elif lyr["type"] == "table":
            for c in lyr["cells"]:
                add(lyr["style"]["family"], c.get("weight", 400), c.get("italic", False))
    return seen


def export_files(scene: dict, dest: Path) -> list[Path]:
    """Copy a static font file for every face the scene uses into `dest` (for installing, or for an
    application that is not given the fonts inside the file)."""
    import shutil

    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for fam, w, it in faces_used(scene):
        src = static_font(fam, w, it)
        if src is None:
            continue
        face, bold, ital = office_name(fam, w, it)
        style = ("Bold" if bold else "") + ("Italic" if ital else "")
        target = dest / f"{face.replace(' ', '')}-{style or 'Regular'}{src.suffix}"
        shutil.copyfile(src, target)
        out.append(target)
    return out


def fontconfig_env(font_dir: Path) -> dict:
    """Environment that makes fontconfig programs (LibreOffice on Linux) see the fonts in `font_dir` too."""
    conf = font_dir / "fonts.conf"
    conf.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
                    '<include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
                    f"<dir>{font_dir.resolve()}</dir><cachedir>{(font_dir / '.fc-cache').resolve()}</cachedir>"
                    "</fontconfig>", encoding="utf-8")
    return {"FONTCONFIG_FILE": str(conf.resolve())}


def text_used(scene: dict, family: str, weight: int, italic: bool) -> str:
    chars: set[str] = set()
    for lyr in scene["layers"]:
        if lyr["type"] == "text":
            st = lyr["style"]
            if (st["family"], snap_weight(st["weight"]), bool(st["italic"])) == (family, snap_weight(weight), italic):
                chars.update(lyr["text"])
        elif lyr["type"] == "table" and lyr["style"]["family"] == family:
            for c in lyr["cells"]:
                if (snap_weight(c.get("weight", 400)), bool(c.get("italic", False))) == (snap_weight(weight), italic):
                    chars.update(c["text"])
    return "".join(sorted(chars))


def woff2_subset(path: Path, text: str) -> bytes:
    """The font cut down to `text` (all layout features kept, so Indic and Arabic still shape), as WOFF2."""
    from fontTools import subset
    from fontTools.ttLib import TTFont

    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.glyph_names = False
    opts.hinting = False
    opts.flavor = "woff2"
    tt = TTFont(str(path))
    sub = subset.Subsetter(opts)
    sub.populate(text=text + " ")
    sub.subset(tt)
    buf = io.BytesIO()
    tt.flavor = "woff2"
    tt.save(buf)
    return buf.getvalue()


def obfuscate(data: bytes, key: str) -> bytes:
    """ECMA-376 font obfuscation for fonts embedded in DOCX: the first 32 bytes XOR the key's bytes."""
    guid = uuid.UUID(key)
    k = bytes(reversed(guid.bytes))   # the GUID's hex digits read right to left
    head = bytes(data[i] ^ k[i % 16] for i in range(32))
    return head + data[32:]
