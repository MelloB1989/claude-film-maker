"""filmtools.mocap.mp2mh: the pure parts (series, closures and the named-shape fit, gesturekit's pronation convention,
the picture lift), and a kit run when an r7 checkout is given (MP2MH_KIT, MP2MH_LANDMARKS)."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from filmtools.mocap import mp2mh as M

SHAPES = {  # agent-08's handshape.SHAPES (closure %), the four fingers only
    "open": {"index": 3, "middle": 4, "ring": 6, "pinky": 9}, "list": {"index": 8, "middle": 10, "ring": 13, "pinky": 17},
    "relaxed": {"index": 22, "middle": 28, "ring": 34, "pinky": 40},
    "point": {"index": 3, "middle": 80, "ring": 84, "pinky": 86},
    "pinch": {"index": 46, "middle": 40, "ring": 46, "pinky": 52},
    "soft_fist": {"index": 66, "middle": 72, "ring": 76, "pinky": 80}}


def test_series_helpers():
    assert M.fill_gaps([None, 1.0, None, 3.0, None]) == [1.0, 1.0, 2.0, 3.0, 3.0]
    assert M.fill_gaps([[0.0, 0.0], None, [2.0, 4.0]])[1] == [1.0, 2.0]
    g = M.gauss([0.0] * 5 + [10.0] + [0.0] * 5, 1.0)
    assert abs(sum(g) - 10.0) < 0.5 and g[5] < 10.0 and g[4] == g[6]
    assert M.dilate_signed([[0.0], [-3.0], [1.0], [0.0]], 1) == [[-3.0], [-3.0], [-3.0], [1.0]]
    assert M.median_labels(["a", "a", "b", "a", "a"], 3) == ["a"] * 5
    assert M.unwrap([170.0, -175.0, -160.0]) == [170.0, 185.0, 200.0]


def _hand(curl_deg: float) -> list:
    """21 points: a flat hand in the x-y plane, fingers along +x, each finger's chord bent down by curl_deg."""
    pts = [[0.0, 0.0, 0.0]] + [[0.0, 0.0, 0.0]] * 20
    pts = [list(p) for p in pts]
    base = {"thumb": -3.0, "index": -2.0, "middle": 0.0, "ring": 2.0, "pinky": 4.0}
    for f, (m, p, d, tip) in M.HAND_IDX.items():
        y = base[f]
        pts[m] = [8.0, y, 0.0]
        a = math.radians(curl_deg)
        ux, uy = 8.0 / math.hypot(8.0, y), y / math.hypot(8.0, y)  # the chord bends down off the palm direction
        for k, j in enumerate((p, d, tip), 1):
            r = 2.5 * k
            pts[j] = [8.0 + r * math.cos(a) * ux, y + r * math.cos(a) * uy, -r * math.sin(a)]
    return pts


def test_closures_and_classify():
    c = M.closures(_hand(5.0))
    assert all(c[f] < 0.05 for f in M.FING4)
    assert M.classify(c, SHAPES)[0] in ("open", "list")
    c = M.closures(_hand(110.0))
    assert all(0.65 < c[f] < 0.8 for f in M.FING4)
    assert M.classify(c, SHAPES)[0] == "soft_fist"


def test_pron_convention():
    # gesturekit: 0 palm down, 90 thumb up; right hand, forearm forward, knuckle line index -> pinky
    fa, hd = [1.0, 0.0, 0.0], [1.0, 0.0, 0.0]
    p, e = M.pron_ext(fa, [0.0, 1.0, 0.0], hd, [0.0, 0.0, -1.0], "r")  # pinky out, palm down
    assert abs(p) < 1e-6 and abs(e) < 1e-6
    p, _ = M.pron_ext(fa, [0.0, 0.0, -1.0], hd, [0.0, -1.0, 0.0], "r")  # pinky down: thumb up
    assert abs(p - 90.0) < 1e-6
    p, _ = M.pron_ext(fa, [0.0, -1.0, 0.0], hd, [0.0, 0.0, -1.0], "l")  # left: pinky out (-y), palm down
    assert abs(p) < 1e-6
    # extension: the hand bent toward the back of the hand (palm down: up) by 30 deg
    up30 = [math.cos(math.radians(30)), 0.0, math.sin(math.radians(30))]
    _, e = M.pron_ext(fa, [0.0, 1.0, 0.0], up30, [0.0, 0.0, -1.0], "r")
    assert abs(e - 30.0) < 1e-6


def test_lift_limb_level_forearm_toward_the_lens():
    basis = ([0.0, 0.0, -1.0], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0])  # MediaPipe-like: fwd -z, her right -x, up -y
    # the picture shows a short drop (20 px of a 100 px limb), straight down; the world says forward
    u = M.lift_limb([0.5, 0.5], [0.5, 0.5 + 20 / 720], [0, 0, 0], [0, 0.05, -0.3], basis, 100.0, 1280, 720)
    assert u[0] > 0.95 and abs(u[1]) < 1e-9 and abs(u[2] + 0.2) < 1e-9


@pytest.mark.skipif(not (os.environ.get("MP2MH_KIT") and os.environ.get("MP2MH_LANDMARKS")),
                    reason="needs an r7 checkout (MP2MH_KIT) and a MediaPipe landmarks file (MP2MH_LANDMARKS)")
def test_kit_build():
    lm = json.loads(Path(os.environ["MP2MH_LANDMARKS"]).read_text())
    doc, summary, m = M.build(lm, os.environ["MP2MH_KIT"], fps=24)
    assert doc["n_keys"] == m.n and doc["fps"] == 24 and doc["keyed"]
    codes = {x["code"] for x in summary["issues"]}
    assert not any(c.startswith(("desk.", "mic.", "face.")) for c in codes), summary["issues"][:5]
