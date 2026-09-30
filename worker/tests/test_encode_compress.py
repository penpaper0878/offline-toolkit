import numpy as np
import pytest
from PIL import Image

from conftest import decode, quadrants
from otk_worker.common import metadata, units
from otk_worker.resizer import compress
from otk_worker.resizer.encode import EncodeSettings, Meta, encode, exact_palette, pad

KB = 1024


def settings(fmt, dpi=(200, 200), **kw):
    exif = metadata.build_exif(None, False, dpi, (1, 1), []).tobytes()
    return EncodeSettings(fmt=fmt, dpi=dpi, meta=Meta(exif=exif), **kw)


@pytest.fixture
def small_photo(photo):
    return photo.resize((240, 240), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------- DPI metadata
@pytest.mark.parametrize("dpi", [(72, 72), (200, 200), (300, 300), (1200, 1200), (199.81333333333333, 200.025)])
def test_jpeg_dpi_in_jfif_and_exif(small_photo, dpi):
    rb = metadata.readback(encode(small_photo, settings("jpeg", dpi)))
    assert rb["jfifDensity"] == [units.jfif_density(dpi[0]), units.jfif_density(dpi[1])]
    assert rb["exifDpi"] == pytest.approx(list(dpi), rel=1e-5)
    assert rb["orientation"] == 1


@pytest.mark.parametrize("dpi", [72, 200, 300, 600])
def test_png_dpi_in_phys(small_photo, dpi):
    rb = metadata.readback(encode(small_photo, settings("png", (dpi, dpi))))
    assert rb["pngPpm"] == [units.png_phys(dpi)] * 2
    assert rb["dpi"][0] == pytest.approx(dpi, abs=0.5 * 0.0254)  # pHYs stores whole px per metre


def test_webp_dpi_in_exif(small_photo):
    rb = metadata.readback(encode(small_photo, settings("webp", (300, 300))))
    assert rb["exifDpi"] == [300.0, 300.0]


def test_strip_keeps_only_resolution_and_keep_resets_orientation():
    src = Image.Exif()
    src[0x0112] = 6
    src[0x010F] = "Camera Maker"
    gps = src.get_ifd(0x8825)
    gps[1] = "N"
    warnings: list[str] = []
    stripped = metadata.build_exif(src, False, (200, 200), (10, 10), warnings)
    assert set(stripped.keys()) == {0x011A, 0x011B, 0x0128}
    kept = metadata.build_exif(src, True, (200, 200), (10, 10), warnings)
    assert kept[0x0112] == 1 and kept[0x010F] == "Camera Maker"
    assert dict(kept.get_ifd(0x8825)) == {1: "N"}


def test_xmp_orientation_reset():
    xmp = b'<rdf:Description tiff:Orientation="6"/><tiff:Orientation>8</tiff:Orientation>'
    assert metadata.clean_xmp(xmp) == b'<rdf:Description tiff:Orientation="1"/><tiff:Orientation>1</tiff:Orientation>'


# ---------------------------------------------------------------- lossless helpers
def test_exact_palette_is_lossless():
    img = quadrants(60, 40).convert("RGBA")
    img.putpixel((0, 0), (10, 20, 30, 128))
    pal = exact_palette(img)
    assert pal is not None
    data = encode(img, settings("png", palette="exact"))
    assert np.array_equal(np.asarray(decode(data).convert("RGBA")), np.asarray(img))


def test_exact_palette_refuses_many_colours(photo):
    assert exact_palette(photo) is None


@pytest.mark.parametrize("fmt", ["jpeg", "png", "webp"])
def test_padding_keeps_pixels_and_reaches_size(small_photo, fmt):
    data = encode(small_photo, settings(fmt, quality=80))
    goal = len(data) + 150_000   # also exercises multi-segment JPEG COM padding
    padded = pad(data, fmt, goal)
    assert len(padded) >= goal
    assert np.array_equal(np.asarray(decode(padded).convert("RGB")), np.asarray(decode(data).convert("RGB")))


def test_jpeg_buffer_retry_on_noise():
    noise = Image.fromarray(np.random.default_rng(3).integers(0, 255, (300, 300, 3), dtype=np.uint8))
    data = encode(noise, settings("jpeg", quality=100, subsampling="4:4:4", progressive=True))
    assert decode(data).size == (300, 300)


# ---------------------------------------------------------------- size targeting
@pytest.mark.parametrize("fmt", ["jpeg", "webp"])
def test_hits_20_to_50_kb(small_photo, fmt):
    out = compress.fit(small_photo, settings(fmt), compress.Target(20 * KB, 50 * KB), compress.Options())
    assert out.status in ("ok", "below_min")
    if out.status == "ok":
        assert 20 * KB <= len(out.data) <= 50 * KB
    assert decode(out.data).size == (240, 240)


def test_jpeg_prefers_highest_quality_that_fits(small_photo):
    out = compress.fit(small_photo, settings("jpeg"), compress.Target(None, 30 * KB), compress.Options())
    assert out.status == "ok" and len(out.data) <= 30 * KB
    q = out.settings.quality
    if q < 100:  # one step up must not fit with the same settings
        assert len(encode(small_photo, out.settings.with_(quality=q + 1))) > 30 * KB or \
            len(encode(small_photo, out.settings.with_(quality=min(100, q + 4)))) > 30 * KB


def test_png_lossless_then_quantize_only_if_allowed(small_photo):
    t = compress.Target(None, 40 * KB)
    refused = compress.fit(small_photo, settings("png"), t, compress.Options(allow_quantize=False))
    assert refused.status == "above_max" and refused.suggestions
    allowed = compress.fit(small_photo, settings("png"), t, compress.Options(allow_quantize=True))
    assert allowed.status == "ok" and len(allowed.data) <= 40 * KB
    assert allowed.settings.palette == "quantize" and allowed.warnings


def smallest_jpeg(img) -> int:
    return min(len(encode(img, settings("jpeg", quality=1, subsampling=ss, progressive=p)))
               for ss in ("4:2:0", "4:4:4") for p in (True, False))


def test_above_max_suggestions_are_real(small_photo):
    limit = smallest_jpeg(small_photo) - 1
    out = compress.fit(small_photo, settings("jpeg"), compress.Target(None, limit), compress.Options())
    assert out.status == "above_max"
    assert "not changed" in out.message
    kinds = {s["kind"] for s in out.suggestions}
    assert "smallest" in kinds
    dims = [s for s in out.suggestions if s["kind"] == "dimensions"]
    if dims:
        s = dims[0]
        small = small_photo.resize((s["width"], s["height"]), Image.Resampling.LANCZOS)
        assert len(encode(small, settings("jpeg", quality=compress.REFERENCE_QUALITY))) <= limit


def test_below_min_without_and_with_padding():
    flat = Image.new("RGB", (140, 60), (250, 250, 250))
    t = compress.Target(30 * KB, 50 * KB)
    no = compress.fit(flat, settings("jpeg"), t, compress.Options(allow_padding=False))
    assert no.status == "below_min" and len(no.data) < 30 * KB and "Pad to minimum" in no.message
    yes = compress.fit(flat, settings("jpeg"), t, compress.Options(allow_padding=True))
    assert yes.status == "ok_padded" and 30 * KB <= len(yes.data) <= 50 * KB and yes.padded_bytes > 0
    assert decode(yes.data).size == (140, 60)


def test_only_minimum(small_photo):
    out = compress.fit(small_photo, settings("jpeg"), compress.Target(5 * KB, None), compress.Options(quality=85))
    assert out.status == "ok" and len(out.data) >= 5 * KB


def test_no_target_uses_quality(small_photo):
    out = compress.fit(small_photo, settings("jpeg"), compress.Target(), compress.Options(quality=77))
    assert out.status == "no_target" and out.settings.quality == 77


def test_min_above_max_is_rejected(small_photo):
    with pytest.raises(ValueError):
        compress.fit(small_photo, settings("jpeg"), compress.Target(50 * KB, 20 * KB), compress.Options())


def test_greyscale_jpeg(small_photo):
    grey = small_photo.convert("L")
    out = compress.fit(grey, settings("jpeg"), compress.Target(None, 20 * KB), compress.Options())
    assert out.status == "ok" and decode(out.data).mode == "L"


def test_cancel_stops_search(small_photo):
    from otk_worker.errors import Cancelled
    calls = {"n": 0}

    def check():
        calls["n"] += 1
        if calls["n"] > 3:
            raise Cancelled()
    with pytest.raises(Cancelled):
        compress.fit(small_photo, settings("jpeg"), compress.Target(20 * KB, 50 * KB), compress.Options(), check)
