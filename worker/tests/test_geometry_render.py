import numpy as np
import pytest
from PIL import Image

from conftest import quadrants
from otk_worker.errors import InputError
from otk_worker.resizer import geometry, render


def test_default_crop_is_centred_with_exact_aspect():
    r = geometry.default_crop((1200, 900), (240, 240))
    assert (r.w, r.h) == (900, 900)
    assert (r.x, r.y) == (150, 0)
    r = geometry.default_crop((900, 1200), (140, 60))
    assert r.w / r.h == pytest.approx(140 / 60)
    assert r.w == 900


def test_normalise_crop_forces_aspect_and_clamps():
    r = geometry.normalise_crop({"x": -50, "y": 10, "w": 500, "h": 300}, (1000, 800), (200, 200))
    assert r.w / r.h == pytest.approx(1.0)
    assert r.x >= 0 and r.y >= 0 and r.x + r.w <= 1000 and r.y + r.h <= 800
    big = geometry.normalise_crop({"x": 0, "y": 0, "w": 5000, "h": 5000}, (1000, 800), (400, 300))
    assert big.w <= 1000 and big.h <= 800
    assert big.w / big.h == pytest.approx(400 / 300)
    with pytest.raises(InputError):
        geometry.normalise_crop({"x": 0, "y": 0, "w": 0, "h": 10}, (100, 100), (10, 10))


@pytest.mark.parametrize("mode", ["crop", "pad", "stretch"])
@pytest.mark.parametrize("target", [(240, 240), (140, 60), (1, 1), (3000, 2000)])
def test_every_fit_mode_gives_exact_pixels(mode, target):
    img = quadrants(400, 300)
    plan = geometry.plan_fit(img.size, target, mode)
    out = render.render(img, plan, "#123456")
    assert out.size == target


def test_crop_window_selects_the_region():
    img = quadrants(400, 300)  # top-left quadrant is red, 200x150
    plan = geometry.plan_fit(img.size, (100, 75), "crop", {"x": 0, "y": 0, "w": 200, "h": 150})
    out = np.asarray(render.render(img, plan))
    inner = out[3:-3, 3:-3]   # away from the resampled border
    assert (np.abs(inner.astype(int) - [255, 0, 0]) <= 2).all()


def test_pad_centres_and_uses_colour():
    img = quadrants(400, 200)
    plan = geometry.plan_fit(img.size, (200, 200), "pad")
    assert plan.inner == (200, 100) and plan.offset == (0, 50)
    out = render.render(img, plan, "#00FF7F")
    assert out.getpixel((100, 5)) == (0, 255, 127)
    assert out.getpixel((100, 195)) == (0, 255, 127)


def test_transparent_padding_keeps_alpha():
    img = quadrants(400, 200)
    out = render.render(img, geometry.plan_fit(img.size, (200, 200), "pad"), "#FFFFFF00")
    assert out.mode == "RGBA" and out.getpixel((100, 5))[3] == 0


def test_stretch_reports_distortion():
    plan = geometry.plan_fit((400, 300), (400, 400), "stretch")
    assert plan.distortion == pytest.approx(0.75 - 1)
    assert any("proportions" in w for w in geometry.plan_warnings(plan))


def test_upscale_warning():
    plan = geometry.plan_fit((100, 100), (600, 600), "crop")
    assert any("enlarged" in w for w in geometry.plan_warnings(plan))


def test_premultiplied_resize_has_no_dark_fringe():
    # Transparent pixels are black (0,0,0,0); without premultiplication they bleed into the edge.
    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    img.paste((255, 0, 0, 255), (50, 50, 150, 150))
    out = render.render(img, geometry.plan_fit(img.size, (37, 37), "stretch"))
    arr = np.asarray(out)
    edge = arr[(arr[..., 3] > 0) & (arr[..., 3] < 255)]
    assert len(edge) > 0
    assert (edge[:, 0] >= 250).all(), "partially transparent edge pixels should stay red"


def test_flatten():
    img = Image.new("RGBA", (10, 10), (0, 0, 255, 0))
    flat, had = render.flatten(img, "#FF0000")
    assert had and flat.mode == "RGB" and flat.getpixel((0, 0)) == (255, 0, 0)
    opaque, had = render.flatten(Image.new("RGBA", (4, 4), (1, 2, 3, 255)))
    assert not had and opaque.mode == "RGB"


def test_parse_color_rejects_garbage():
    with pytest.raises(ValueError):
        render.parse_color("red")
