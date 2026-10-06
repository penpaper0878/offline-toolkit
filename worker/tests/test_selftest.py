"""The full offline self-test's worker part: every module's check passes here with the network guard on
(the PDF printed by the app's Chromium needs the app, so outside it that one check says so and fails)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from otk_worker import netguard, selftest

ROOT = Path(__file__).resolve().parents[2]


def test_every_module_works_offline(tmp_path):
    from conftest_converter import HAVE_GS, HAVE_LO, HAVE_PANDOC, HAVE_RESVG, HAVE_TESS, HAVE_VERAPDF

    if not all((HAVE_LO, HAVE_PANDOC, HAVE_GS, HAVE_TESS, HAVE_VERAPDF, HAVE_RESVG)):
        pytest.skip("conversion engines not installed")
    netguard.install()
    progress: list[str] = []
    res = selftest.run({"workDir": str(tmp_path / "st"), "resourcesDir": str(ROOT / "resources")},
                       lambda p: progress.append(p["message"]))
    by = {c["name"]: c for c in res["checks"]}
    assert len(by) == len(selftest.CHECKS) == 10
    chromium = by.pop("Web page to PDF")
    assert not chromium["passed"] and "Chromium" in chromium["detail"]
    assert [n for n, c in by.items() if not c["passed"]] == [], {n: c["detail"] for n, c in by.items() if not c["passed"]}
    assert progress[-1] == "Done" and len(progress) == len(selftest.CHECKS) + 1
    assert not (tmp_path / "st").exists() or not any((tmp_path / "st").iterdir())      # nothing left behind


def test_a_failing_check_is_reported_and_the_rest_still_run(tmp_path, monkeypatch):
    def broken(env):
        raise selftest.Failed("made to fail")

    monkeypatch.setattr(selftest, "CHECKS", [selftest.Check("resizer", "Broken", broken), selftest.CHECKS[0]])
    res = selftest.run({"workDir": str(tmp_path / "st"), "resourcesDir": str(ROOT / "resources")}, lambda p: None)
    assert [c["passed"] for c in res["checks"]] == [False, True] and not res["passed"]
    assert res["checks"][0]["detail"] == "Failed: made to fail"


def test_cancel_stops_between_checks(tmp_path):
    from otk_worker.errors import Cancelled

    ev = threading.Event()
    ev.set()
    with pytest.raises(Cancelled):
        selftest.run({"workDir": str(tmp_path / "st"), "resourcesDir": str(ROOT / "resources")}, lambda p: None, ev)
