"""B34: the SDK examples (examples/unreal/sdk) against the op schema, and example 1 end to end on the fake engine."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

from filmtools.unreal import schema, sdkcheck
from filmtools.unreal.sdk import Unreal

EX = Path(__file__).resolve().parents[2] / "examples" / "unreal" / "sdk"


def _load(name):
    sys.path.insert(0, str(EX))
    try:
        spec = importlib.util.spec_from_file_location(f"sdkex_{name}", EX / f"{name}.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.path.remove(str(EX))


def test_every_example_call_matches_the_schema():
    files = sorted(EX.glob("ex*.py"))
    assert len(files) == 5
    assert sdkcheck.check(files) == []


def test_sdkcheck_catches_drift(tmp_path):
    p = tmp_path / "s.py"
    p.write_text("ue.level.move(lable='A')\nue.level.mvoe(label='A')\nue.call('level.spawn', shape='cube')\n"
                 "ue.level.move(**kw)\nue.assets.import_(files=[], dest='/Game/x')\n")
    got = [x[3].split(" (")[0] for x in sdkcheck.check([p])]
    assert got == ["level.move takes no 'lable'", "level.move needs label", "no op level.mvoe", "level.spawn needs label"]


def test_examples_have_runnable_docstrings():
    for f in sorted(EX.glob("ex*.py")):
        m = _load(f.stem)
        assert "uv run python ../examples/unreal/sdk/" + f.name in m.__doc__ and "Expected:" in m.__doc__, f.name
        assert callable(m.main)


def test_example_1_on_the_fake_engine(fmb, ue):
    from test_ue_dx_e2e import FakeBridge
    m = _load("ex01_level")
    common = sys.modules["_common"]
    log = common.Log(quiet=True)
    res = m.main(Unreal(transport=FakeBridge(fmb)), types.SimpleNamespace(out="/tmp/x"), log)
    assert log.failed == [] and res["actors"] == ["SDK_Ball", "SDK_Box", "SDK_Floor", "SDK_Wall"]
    log2 = common.Log(quiet=True)
    res2 = m.main(Unreal(transport=FakeBridge(fmb)), types.SimpleNamespace(out="/tmp/x"), log2)
    assert log2.failed == [] and res2["changed"] is False   # the second run changes nothing
    assert ue.dialogs == []
