import pytest

from otk_worker.common import units


def test_resolve_vectors(vectors):
    for case in vectors["resolve"]:
        a = case["in"]
        r = units.resolve_size(a["width"], a["height"], a["unit"], a["dpi"], fit_dpi=a.get("fitDpi", False)).to_dict()
        axes = (r["width"], r["height"])
        assert [ax["px"] for ax in axes] == case["px"], case["name"]
        for key in ("exactPx", "dpi", "errorMm", "actualMm"):
            if key in case:
                for ax, expected in zip(axes, case[key]):
                    assert ax[key] == pytest.approx(expected, abs=1e-6), f"{case['name']}: {key}"


def test_spec_examples_read_as_stated():
    # "3 cm at 200 DPI = 236.2 px, while 240 px at 200 DPI = 3.048 cm"
    assert round(units.length_to_px(3, "cm", 200), 1) == 236.2
    assert units.px_to_length(240, "cm", 200) == pytest.approx(3.048)


@pytest.mark.parametrize("key,fn", [
    ("pxToLength", lambda c: units.px_to_length(c["px"], c["unit"], c["dpi"])),
    ("lengthToPx", lambda c: units.length_to_px(c["value"], c["unit"], c["dpi"])),
])
def test_conversions(vectors, key, fn):
    for case in vectors[key]:
        assert fn(case) == pytest.approx(case["out"], abs=1e-9)


def test_png_and_jfif_precision(vectors):
    for c in vectors["pngPhys"]:
        assert units.png_phys(c["dpi"]) == c["ppm"]
        assert units.png_phys_dpi(c["ppm"]) == pytest.approx(c["readback"], abs=1e-4)
    for c in vectors["jfif"]:
        assert units.jfif_density(c["dpi"]) == c["out"]


def test_bytes(vectors):
    for c in vectors["bytes"]:
        assert units.bytes_from(c["value"], c["unit"], c["base"]) == c["out"]


def test_errors(vectors):
    for c in vectors["errors"]:
        a = c["in"]
        with pytest.raises(units.UnitError):
            units.resolve_size(a["width"], a["height"], a["unit"], a["dpi"])


def test_round_px_is_half_up():
    assert units.round_px(0.5) == 1
    assert units.round_px(1.5) == 2
    assert units.round_px(2.5) == 3  # round() would give 2
    assert units.round_px(2.4999) == 2


def test_round_trip_every_unit():
    for unit in ("cm", "mm", "in"):
        for dpi in (72, 96, 150, 200, 300, 600, 1200):
            v = 7.3
            assert units.px_to_length(units.length_to_px(v, unit, dpi), unit, dpi) == pytest.approx(v)
