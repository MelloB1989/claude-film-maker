"""Offline checks of the explainer set's plan: python3 -m pytest films/host-studio/explainers/test_setplan.py"""
import importlib.util
import json
from pathlib import Path

import setplan as P

HERE = Path(__file__).resolve().parent


def _set():
    spec = importlib.util.spec_from_file_location("expset", HERE / "set.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_framing_rules_pass_for_both():
    for who in ("her", "him"):
        bad = [r for r in P.check(who) if not r[1]]
        assert not bad, bad


def test_project_centre_and_sides():
    cam = {"loc": [300, 0, 120], "look_at": [0, 0, 120], "focal": 50, "filmback": [36, 20.25]}
    u, v, z = P.project(cam, (0, 0, 120))
    assert abs(u - 0.5) < 1e-9 and abs(v - 0.5) < 1e-9 and abs(z - 300) < 1e-9
    assert P.project(cam, (0, 50, 120))[0] < 0.5   # +Y is screen-left looking down -X
    assert P.project(cam, (0, 0, 160))[1] < 0.5    # up is up


def test_mcu_l_moves_her_left_only():
    c = P.cameras("her")
    assert c["CAM_MCU_L"]["loc"] == c["CAM_MCU"]["loc"]
    e = P.face("her")["eyes"]
    assert abs(P.project(c["CAM_MCU_L"], e)[0] - 0.27) < 0.01


def test_drift_is_subtle():
    cam = P.cameras("her")["CAM_CU"]
    for _, loc, at in P.drift(cam, 0, 1427, seed=3):
        assert max(abs(a - b) for a, b in zip(loc, cam["loc"])) <= 0.41
        assert max(abs(a - b) for a, b in zip(at, cam["look_at"])) <= 0.31


def test_edl_cuts_and_render_plan():
    S = _set()
    edl = {"frames": 300, "shots": [
        {"n": 1, "kind": "pres", "f0": 0, "f1": 100, "camera": "CAM_MCU"},
        {"n": 2, "kind": "gfx", "f0": 100, "f1": 150, "camera": None},
        {"n": 3, "kind": "panel", "f0": 150, "f1": 250, "camera": "CAM_MCU"},
        {"n": 4, "kind": "pres", "f0": 250, "f1": 300, "camera": "CAM_CU"}]}
    assert S.edl_cuts(edl) == [["CAM_MCU", 0], ["CAM_MCU_L", 150], ["CAM_CU", 250]]
    assert S.render_plan(edl) == [[1, "CAM_MCU", 0, 106], [3, "CAM_MCU_L", 144, 256], [4, "CAM_CU", 244, 300]]
    json.dumps(P.spec("him"))
