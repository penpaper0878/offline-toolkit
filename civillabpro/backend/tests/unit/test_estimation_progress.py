"""Progress of an item against its estimated quantity (interpretation 117)."""

from decimal import Decimal as D

from app.modules.estimation.domain.progress import item_progress


def test_progress_within_the_estimate():
    p = item_progress(10.0, [(D("5.83"), True), (D("2.10"), False)], 6544.15)
    assert (p.measured, p.checked, p.balance, p.excess, p.percent) == (D("7.93"), D("5.83"), D("2.07"), D("0"), D("79.3"))
    assert p.value_measured == D("51895.11") and p.value_checked == D("38152.39") and p.value_excess == D("0.00")  # 7.93 x 6544.15 = 51895.1095


def test_progress_beyond_the_estimate_and_with_a_correction():
    p = item_progress(4.5, [(D("5.20"), True), (D("-0.23"), True)], 5210.4)
    assert (p.measured, p.balance, p.excess) == (D("4.97"), D("0"), D("0.47")) and p.value_excess == D("2448.89")  # 0.47 x 5210.4 = 2448.888


def test_an_item_estimated_at_nothing_has_no_percentage():
    p = item_progress(0.0, [(D("1.00"), False)], 100.0)
    assert p.percent is None and p.excess == D("1.00") and p.value_excess == D("100.00")
    assert item_progress(3.0, [], 100.0).balance == D("3.0")
