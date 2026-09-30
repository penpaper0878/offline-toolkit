"""Physical size <-> pixel conversion.

px = inches x DPI, with 1 in = 2.54 cm = 25.4 mm. Everything stays in exact
floats until one final half-up rounding to whole pixels, and every result
carries its rounding error so the UI can show it (e.g. 3 cm @ 200 DPI =
236.22 px -> 236 px, -0.22 px = -0.028 mm).

src/shared/units.ts mirrors this module; both are tested against
tests/vectors/units.json.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

UNITS = ("px", "cm", "mm", "in")
PER_INCH = {"in": 1.0, "cm": 2.54, "mm": 25.4}
DPI_MIN = 72
DPI_MAX = 1200
_EPS = 1e-9  # absorbs float noise such as 2.54 cm @ 100 DPI = 100.00000000000001


class UnitError(ValueError):
    pass


def _check_unit(unit: str) -> None:
    if unit not in UNITS:
        raise UnitError(f"unknown unit {unit!r}; expected one of {', '.join(UNITS)}")


def _check_dpi(dpi: float) -> None:
    if not (isinstance(dpi, (int, float)) and math.isfinite(dpi) and dpi > 0):
        raise UnitError(f"DPI must be a positive number, got {dpi!r}")


def round_px(value: float) -> int:
    """Half-up rounding to a whole pixel (Python's round() is half-to-even)."""
    return int(math.floor(value + 0.5 + _EPS))


def length_to_px(value: float, unit: str, dpi: float) -> float:
    """Exact (unrounded) pixel count for a length."""
    _check_unit(unit)
    if unit == "px":
        return float(value)
    _check_dpi(dpi)
    return value / PER_INCH[unit] * dpi


def px_to_length(px: float, unit: str, dpi: float) -> float:
    _check_unit(unit)
    if unit == "px":
        return float(px)
    _check_dpi(dpi)
    return px / dpi * PER_INCH[unit]


def convert_length(value: float, from_unit: str, to_unit: str, dpi: float) -> float:
    return px_to_length(length_to_px(value, from_unit, dpi), to_unit, dpi)


@dataclass(frozen=True)
class Axis:
    requested: float        # what the user typed, in `unit`
    unit: str
    exact_px: float         # unrounded pixels
    px: int                 # pixels actually produced
    dpi: float              # density stored for this axis
    error_px: float         # px - exact_px
    actual: float           # physical length of `px` at `dpi`, in `unit` (px unit: == px)
    error: float            # actual - requested, in `unit`
    actual_mm: float        # physical length of `px` at `dpi` in mm
    error_mm: float


@dataclass(frozen=True)
class SizeResult:
    width: Axis
    height: Axis

    @property
    def px(self) -> tuple[int, int]:
        return self.width.px, self.height.px

    @property
    def dpi(self) -> tuple[float, float]:
        return self.width.dpi, self.height.dpi

    def to_dict(self) -> dict:
        """camelCase, the shape src/shared/units.ts produces too."""
        return {"width": _camel(asdict(self.width)), "height": _camel(asdict(self.height))}


def _camel(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        head, *rest = k.split("_")
        out[head + "".join(p.capitalize() for p in rest)] = v
    return out


def _axis(value: float, unit: str, dpi: float, fit_dpi: bool) -> Axis:
    if not (isinstance(value, (int, float)) and math.isfinite(value) and value > 0):
        raise UnitError(f"size must be a positive number, got {value!r}")
    _check_dpi(dpi)
    exact = length_to_px(value, unit, dpi)
    px = round_px(exact) if unit != "px" else round_px(value)
    if unit == "px" and abs(px - value) > _EPS:
        raise UnitError(f"pixel sizes must be whole numbers, got {value!r}")
    if px < 1:
        raise UnitError(f"{value} {unit} at {dpi} DPI is less than one pixel")
    axis_dpi = dpi
    if fit_dpi and unit != "px":
        # Keep the rounded pixel count and adjust the stored density so the
        # physical size comes out exact.
        axis_dpi = px / (value / PER_INCH[unit])
    actual = px_to_length(px, unit, axis_dpi) if unit != "px" else float(px)
    actual_mm = px / axis_dpi * 25.4
    requested_mm = value / PER_INCH[unit] * 25.4 if unit != "px" else actual_mm
    return Axis(
        requested=float(value), unit=unit, exact_px=exact, px=px, dpi=axis_dpi,
        error_px=px - exact, actual=actual, error=actual - value,
        actual_mm=actual_mm, error_mm=actual_mm - requested_mm,
    )


def resolve_size(width: float, height: float, unit: str, dpi: float, fit_dpi: bool = False) -> SizeResult:
    """Target pixel size and stored DPI for a requested width/height.

    fit_dpi=False: the requested DPI is stored and pixels are rounded (the
    physical size is then off by the rounding error, reported per axis).
    fit_dpi=True: pixels are rounded the same way, but each axis stores the
    density that makes the physical size exact.
    """
    _check_unit(unit)
    return SizeResult(_axis(width, unit, dpi, fit_dpi), _axis(height, unit, dpi, fit_dpi))


def jfif_density(dpi: float) -> int:
    """JPEG's JFIF header stores whole dots per inch."""
    return round_px(dpi)


def png_phys(dpi: float) -> int:
    """PNG's pHYs chunk stores whole pixels per metre (Pillow rounds the same way)."""
    return int(dpi / 0.0254 + 0.5)


def png_phys_dpi(ppm: int) -> float:
    """DPI a reader recovers from a pHYs value."""
    return ppm * 0.0254


def bytes_from(value: float, unit: str, base: int = 1024) -> int:
    """File-size field -> bytes. KB/MB use base 1024 by default (as Windows shows sizes)."""
    factors = {"B": 1, "KB": base, "MB": base * base}
    if unit not in factors:
        raise UnitError(f"unknown size unit {unit!r}")
    if not (isinstance(value, (int, float)) and math.isfinite(value) and value >= 0):
        raise UnitError(f"file size must be a non-negative number, got {value!r}")
    return int(math.floor(value * factors[unit] + _EPS))
