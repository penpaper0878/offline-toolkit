"""Design projects on disk, the .otkd project file, exports, and installing the fonts a design uses.

A project is a folder: scene.json, assets/ (pictures the layers use, the original and the prepared
picture) and cache/ (analysis results that can be rebuilt). The .otkd file is that folder zipped
without the cache, so it opens on another computer exactly as it was saved.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import uuid
import zipfile
from pathlib import Path

from ..errors import InputError
from . import fonts_out, scene as sc

OTKD_MAGIC = "otk-design"
MAX_ASSET_BYTES = 200 * 1024 * 1024
FORMATS = ("pptx", "docx", "svg", "html", "otkd")


def load(project: Path) -> dict:
    p = project / "scene.json"
    if not p.is_file():
        raise InputError("This design has no scene file; analyse the picture again.")
    scene = sc.load(p)
    if scene.get("version", 0) > sc.VERSION:
        raise InputError("This design was saved by a newer version of the app.")
    return scene


def _safe_asset(project: Path, rel: str) -> Path:
    p = (project / rel).resolve()
    if not str(p).startswith(str(project.resolve()) + os.sep):
        raise InputError(f"A layer refers to a file outside the design: {rel}")
    return p


def validate(scene: dict, project: Path) -> None:
    """Refuse a scene that is malformed or points outside its project."""
    if scene.get("format") != sc.FORMAT or not isinstance(scene.get("layers"), list):
        raise InputError("Not an Offline Toolkit design.")
    ids = set()
    for lyr in scene["layers"]:
        if not isinstance(lyr, dict) or lyr.get("type") not in ("image", "shape", "vector", "text", "table"):
            raise InputError("The design has a layer of an unknown kind.")
        if lyr.get("id") in ids:
            raise InputError(f"Two layers share the id {lyr.get('id')!r}.")
        ids.add(lyr.get("id"))
        box = lyr.get("box")
        if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)):
            raise InputError(f"Layer {lyr.get('name')!r} has no valid position.")
        if lyr["type"] == "image":
            path = _safe_asset(project, lyr.get("asset", ""))
            if not path.is_file():
                raise InputError(f"The picture of layer {lyr.get('name')!r} is missing ({lyr.get('asset')}).")


def save(project: Path, scene: dict) -> dict:
    validate(scene, project)
    tmp = project / "scene.json.tmp"
    sc.save(scene, tmp)
    tmp.replace(project / "scene.json")
    return {"saved": True}


def import_image(project: Path, path: str) -> dict:
    """Copy a picture into the project's assets (for replacing a photo or adding one)."""
    from PIL import Image

    from ..common import imageio

    src = Path(path)
    if not src.is_file():
        raise InputError("That picture was not found.")
    if src.stat().st_size > MAX_ASSET_BYTES:
        raise InputError("That picture is too large (over 200 MB).")
    loaded = imageio.open_image(str(src))
    img = loaded.image
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    name = f"assets/import-{uuid.uuid4().hex[:8]}.png"
    out = project / name
    (img.convert("RGBA") if has_alpha else img.convert("RGB")).save(out)
    with Image.open(out) as im:
        w, h = im.size
    return {"asset": name, "width": w, "height": h}


def cutout(project: Path, asset: str, mode: str = "auto") -> dict:
    """Cut the subject out of a layer's picture; writes a new RGBA asset and leaves the old one."""
    import numpy as np
    from PIL import Image

    from . import cutout as cut

    src = _safe_asset(project, asset)
    img = Image.open(src)
    rgb = np.asarray(img.convert("RGB"))
    res = cut.cutout(rgb, mode)
    alpha = res.alpha
    if img.mode == "RGBA":   # keep what was already transparent
        alpha = np.minimum(alpha, np.asarray(img)[..., 3])
    name = f"assets/{Path(asset).stem}-cutout-{uuid.uuid4().hex[:6]}.png"
    Image.fromarray(np.dstack([rgb, alpha]), "RGBA").save(project / name)
    return {"asset": name, "method": res.method, "coverage": round(res.coverage, 4)}


# ------------------------------------------------------------------ .otkd
def pack(project: Path, scene: dict, out: Path) -> Path:
    validate(scene, project)
    used = {lyr["asset"] for lyr in scene["layers"] if lyr["type"] == "image"}
    used |= set((scene.get("assets") or {}).values())
    used |= {lyr.get("source", {}).get("pixels") for lyr in scene["layers"] if lyr["type"] == "vector"} - {None}
    tmp = out.with_name(out.name + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", OTKD_MAGIC, compress_type=zipfile.ZIP_STORED)
        z.writestr("scene.json", json.dumps(scene, indent=1, ensure_ascii=False))
        for rel in sorted(used):
            p = _safe_asset(project, rel)
            if p.is_file():
                z.write(p, rel, compress_type=zipfile.ZIP_STORED if p.suffix.lower() in (".png", ".jpg", ".jpeg") else zipfile.ZIP_DEFLATED)
    tmp.replace(out)
    return out


_SAFE_NAME = re.compile(r"^assets/[A-Za-z0-9._-]+$")


def unpack(path: Path, project: Path) -> dict:
    """Open a .otkd file into an empty project folder."""
    if not zipfile.is_zipfile(path):
        raise InputError("This is not an Offline Toolkit design file (.otkd).")
    project.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "scene.json" not in names or (("mimetype" in names) and z.read("mimetype").decode(errors="replace") != OTKD_MAGIC):
            raise InputError("This is not an Offline Toolkit design file (.otkd).")
        total = sum(i.file_size for i in z.infolist())
        if total > 4 * MAX_ASSET_BYTES:
            raise InputError("The design file is too large to open.")
        (project / "assets").mkdir(exist_ok=True)
        for info in z.infolist():
            if info.filename in ("scene.json", "mimetype") or info.is_dir():
                continue
            if not _SAFE_NAME.match(info.filename):
                raise InputError(f"The design file contains an unexpected entry: {info.filename}")
            with z.open(info) as src, open(project / info.filename, "wb") as dst:
                shutil.copyfileobj(src, dst)
        scene = json.loads(z.read("scene.json").decode("utf-8"))
    validate(scene, project)
    if scene.get("version", 0) > sc.VERSION:
        raise InputError("This design was saved by a newer version of the app.")
    sc.save(scene, project / "scene.json")
    return scene


# ------------------------------------------------------------------ exports
def export(project: Path, scene: dict, fmt: str, out: Path, *, fonts_folder: bool = False) -> dict:
    """Write the design as `fmt` to `out`. Returns {path, notes, fonts}."""
    from . import out_docx, out_html, out_pptx, out_svg

    validate(scene, project)
    if fmt not in FORMATS:
        raise InputError(f"Unknown export format: {fmt}")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.stem}.part{out.suffix}")
    notes: list[str] = []
    if fmt == "pptx":
        _, notes = out_pptx.write(scene, project, tmp)
        notes.append("PowerPoint shows the matched fonts once they are installed (Install fonts, in the export panel).")
    elif fmt == "docx":
        _, notes = out_docx.write(scene, project, tmp)
    elif fmt == "svg":
        out_svg.write(scene, project, tmp)
    elif fmt == "html":
        out_html.write(scene, project, tmp)
    else:
        pack(project, scene, tmp)
    tmp.replace(out)
    fonts = []
    if fonts_folder and fmt in ("pptx", "docx", "svg"):
        fonts = [str(p) for p in fonts_out.export_files(scene, out.parent / f"{out.stem} fonts")]
    return {"path": str(out), "notes": notes, "fonts": fonts}


def install_fonts(scene: dict) -> dict:
    """Install the design's fonts for the current user (no administrator rights needed)."""
    faces = fonts_out.faces_used(scene)
    if sys.platform == "win32":
        import winreg

        base = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Windows" / "Fonts"
        base.mkdir(parents=True, exist_ok=True)
        done = []
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts")
        try:
            for fam, w, it in faces:
                src = fonts_out.static_font(fam, w, it)
                if src is None:
                    continue
                face, bold, ital = fonts_out.office_name(fam, w, it)
                style = " ".join(s for s in ("Bold" if bold else "", "Italic" if ital else "") if s)
                target = base / f"OTK-{face.replace(' ', '')}{'-' + style.replace(' ', '') if style else ''}.ttf"
                shutil.copyfile(src, target)
                winreg.SetValueEx(key, f"{face}{' ' + style if style else ''} (TrueType)", 0, winreg.REG_SZ, str(target))
                done.append(f"{face}{' ' + style if style else ''}")
        finally:
            winreg.CloseKey(key)
        _broadcast_font_change()
        return {"installed": done, "where": str(base)}
    dest = Path.home() / ".local" / "share" / "fonts" / "offline-toolkit"
    files = fonts_out.export_files(scene, dest)
    return {"installed": [p.stem for p in files], "where": str(dest)}


def _broadcast_font_change() -> None:
    try:
        import ctypes

        HWND_BROADCAST, WM_FONTCHANGE = 0xFFFF, 0x001D
        ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0, 0x0002, 1000, None)
    except Exception:
        pass
