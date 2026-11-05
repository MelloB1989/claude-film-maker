"""The file inbox (SSM's fallback, and how `film-ue install` swaps the bridge) writes what /exec answers, not the
bare value: install reads {"ok", "stdout"} from it (day 1: it wrote null and install crashed)."""
import importlib

import pytest


@pytest.fixture
def inbox(fmb):
    return importlib.import_module("fmbridge.inbox")


def test_a_printing_file_gives_ok_and_its_stdout(inbox):
    r = inbox.run_file("print('bridge 2 up')", "install")
    assert r == {"ok": True, "result": None, "stdout": "bridge 2 up\n"}


def test_result_is_kept(inbox):
    assert inbox.run_file("result = {'a': 1}", "q")["result"] == {"a": 1}


def test_an_error_is_reported_not_raised(inbox):
    r = inbox.run_file("print('half'); raise ValueError('boom')", "bad")
    assert r["ok"] is False and "ValueError: boom" in r["error"] and r["stdout"] == "half\n"
