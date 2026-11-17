"""Runs every independent hand check as part of the test suite."""

import importlib.util
import pathlib

import pytest

CHECKS = sorted(pathlib.Path(__file__).parent.glob("check_*.py"))


@pytest.mark.parametrize("path", CHECKS, ids=lambda p: p.stem)
def test_hand_check_passes(path, capsys):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0, capsys.readouterr().out
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("OK:")
