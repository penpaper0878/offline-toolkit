"""Estimation arithmetic and the schedule-of-rates parser."""

from decimal import Decimal

import pytest

from app.core.errors import Invalid
from app.modules.estimation.domain.abstract import Addition, abstract, canonical_unit, unit_factor
from app.modules.estimation.domain.measure import MeasureLine, item_quantity, line_quantity
from app.modules.estimation.domain.rates import AnalysisLine, analyse
from app.modules.estimation.service import parse_sor


def test_measurement_lines():
    assert line_quantity(MeasureLine("running", 3, 4.25)) == Decimal("12.75")  # nos x length: running metres
    assert line_quantity(MeasureLine("area", 2, 3.0, 2.505)) == Decimal("15.03")  # 15.03 exactly
    assert line_quantity(MeasureLine("volume", 1, 1.0, 1.0, 0.125)) == Decimal("0.13")  # 0.125 half up
    assert line_quantity(MeasureLine("opening", 2, 1.0, 0.9, 0.23, deduct=True)) == Decimal("-0.41")
    assert line_quantity(MeasureLine("count only", 7)) == Decimal("7.00")
    assert item_quantity([MeasureLine("a", 1, 2.0, 2.0, 2.0), MeasureLine("b", 1, 1.0, 1.0, 1.0, True)]) == Decimal("7.00")
    assert item_quantity([]) == Decimal(0)


def test_analysis_and_abstract():
    a = analyse([AnalysisLine("material", "x", "u", 1.0, 100.0), AnalysisLine("labour", "y", "u", 2.0, 50.0)], 4.0, 1.0, 15.0)
    assert (a.by_kind["material"], a.by_kind["labour"], a.cost, a.water, a.overheads_profit) == (100, 100, 200, 2, Decimal("30.30"))
    assert a.rate == Decimal("58.08")  # 232.30 / 4 = 58.075, half up
    with pytest.raises(ValueError, match="output quantity"):
        analyse([], 0.0)
    ab = abstract([Decimal("1000.00"), Decimal("234.56")], [Addition("Cost index", 12.5), Addition("Rebate", -2.0)])
    assert ab.subtotal == Decimal("1234.56") and [x[2] for x in ab.additions] == [Decimal("154.32"), Decimal("-24.69")]
    assert ab.total == Decimal("1364.19") and ab.rounded == Decimal("1364")


def test_units_as_schedules_write_them():
    assert [canonical_unit(u) for u in ("Cum", "cu. m", "m3", "Sqm", "sq.m", "MT", "Qtl", "kgs")] == ["m3", "m3", "m3", "m2", "m2", "t", "q", "kg"]
    assert unit_factor("kg", "MT") == Decimal("0.001") and unit_factor("kg", "qtl") == Decimal("0.01") and unit_factor("m3", "cum") == 1
    assert unit_factor("m3", "sqm") is None and unit_factor("kg", "cum") is None


def test_schedule_parser():
    rows = [["Schedule (illustrative)"], [], ["Sl No", "Particulars", "UOM", "Rate in Rs", "Head"],
            ["", "Chapter 13: Finishing", "", "", ""],
            ["13.1", "12 mm cement plaster of mix", "", "", ""],
            ["13.1.1", "1:4 (1 cement : 4 fine sand)", "sqm", "Rs. 1,045.20", ""],
            ["13.1.2", "1:6 (1 cement : 6 fine sand)", "sqm", "₹ 312", ""],
            ["13.1.2", "repeated", "sqm", "1", ""],
            ["13.2", "Something", "sqm", "twelve", ""],
            ["13.3", "", "sqm", "1", ""],
            ["", "", "", "", ""]]
    items, headings, skipped = parse_sor(rows)
    assert headings == 1 and [(i["item_code"], i["rate_paise"]) for i in items] == [("13.1.1", 104520), ("13.1.2", 31200)]
    assert items[0]["description"] == "12 mm cement plaster of mix: 1:4 (1 cement : 4 fine sand)" and items[0]["chapter"] == "Chapter 13: Finishing"
    assert skipped == ["row 8: code 13.1.2 repeated", "row 9: the rate 'twelve' is not a number", "row 10: no description"]
    with pytest.raises(Invalid, match="No header row"):
        parse_sor([["a", "b"]])
    with pytest.raises(Invalid, match="No items"):
        parse_sor([["Code", "Description", "Unit", "Rate"], ["1", "x", "m", ""]])
