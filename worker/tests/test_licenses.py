"""The third-party licence list (scripts/collect_licenses.py): copyleft levels of SPDX expressions, the copyleft
libraries found inside wheels and engines, and the worker's Python packages, fonts and models as bundled here."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
cl = importlib.import_module("collect_licenses")


@pytest.mark.parametrize("expr, level", [
    ("MIT", "none"),
    ("Apache-2.0 OR MIT", "none"),
    ("AGPL-3.0-only", "network"),
    ("AGPL-3.0-only OR LicenseRef-Artifex-Commercial", "network"),   # a paid alternative is not an option
    ("GPL-2.0-or-later", "strong"),
    ("GPL-3.0-or-later OR MPL-2.0", "weak"),                         # veraPDF: the most permissive open choice
    ("GPL-2.0-only WITH Classpath-exception-2.0", "weak"),
    ("CDDL-1.1 OR GPL-2.0-only WITH Classpath-exception-2.0", "weak"),
    ("GPL-3.0-or-later WITH GCC-exception-3.1", "none"),             # runtime library exception
    ("BSD-3-Clause AND LGPL-2.1-only", "weak"),
    ("MPL-2.0 AND MIT", "weak"),
    ("(LGPL-2.1-only OR MPL-1.1)", "weak"),
])
def test_copyleft_levels(expr: str, level: str) -> None:
    assert cl.copyleft(expr) == level


def test_finds_copyleft_libraries_inside_wheels_and_engines() -> None:
    found = cl.natives([
        "shapely.libs/geos-ae6efa07.dll", "shapely.libs/geos_c-072b7a92.dll", "shapely/_geos.cp311-win_amd64.pyd",
        "cv2/opencv_videoio_ffmpeg500_64.dll", "pi_heif.libs/libheif-7a3e919c.so.1.23.0", "libde265-0-aa06.dll",
        "numpy.libs/libquadmath-96973f99.so.0.0.0", "libglib-2.0-0.dll", "libpango-1.0-0.dll", "libcairo-2.dll",
        "README.txt", "cv2/cv2.pyd",
    ])
    assert set(found) == {"GEOS", "FFmpeg", "libheif", "libde265", "libquadmath", "GLib", "Pango", "cairo"}
    assert sorted(found["GEOS"][1]) == ["geos-ae6efa07.dll", "geos_c-072b7a92.dll"]   # not shapely's own extension


def test_spdx_texts_cover_the_licences_in_use() -> None:
    for lic in ("MIT", "Apache-2.0", "BSD-3-Clause", "GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0", "MPL-2.0",
                "OFL-1.1", "PSF-2.0", "Ubuntu-font-1.0", "CDDL-1.1", "Classpath-exception-2.0", "GCC-exception-3.1"):
        assert cl.spdx_text_file(lic) is not None, lic


def test_worker_packages_fonts_and_models(tmp_path: Path) -> None:
    c = cl.Collector(tmp_path, "linux-x64")
    cl.collect_python(c, None, None)
    if (ROOT / "fonts" / "fonts.json").exists():
        cl.collect_fonts(c, ROOT / "fonts")
    if (ROOT / "models" / "manifest.json").exists():
        cl.collect_models(c, ROOT / "models")
    assert c.unknown == []
    by_id = {x["id"]: x for x in c.components}
    # The requirements' closure: what the worker ships, not the test tools in the same environment.
    assert "py:pytest" not in by_id and "py:onnx" not in by_id
    assert by_id["py:pymupdf"]["copyleft"] == "network"
    assert by_id["py:pillow"]["copyleft"] == "none"
    assert by_id["py:img2pdf"]["copyleft"] == "weak"
    assert any(x["name"] == "GEOS" and x["partOf"] == "shapely" for x in c.components)
    for x in c.components:
        assert x["files"], f"{x['name']} has no licence text"
        for f in x["files"]:
            assert (tmp_path / f).is_file()
    if (ROOT / "fonts" / "fonts.json").exists():
        fonts = [x for x in c.components if x["kind"] == "font"]
        assert len(fonts) == 73
        tinos = (tmp_path / by_id["font:tinos"]["files"][0]).read_text(encoding="utf-8")
        assert "Tinos Project Authors" in tinos and "SIL OPEN FONT LICENSE" in tinos
