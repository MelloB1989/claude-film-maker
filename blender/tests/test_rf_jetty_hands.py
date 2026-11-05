"""The Rain Ferry's jetty hands (films/rain-ferry/blender/rf/jetty_talk.py): the hand's arc through its keys, the
wrist's follow-through, the relaxed hand, without Blender."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "films" / "rain-ferry" / "blender"))

from rf import jetty_talk as jt  # noqa: E402

KEYS = [(0.0, (0.0, 0.0, 0.0)), (1.0, (1.0, 0.0, 1.0)), (2.0, (2.0, 0.0, 0.0))]


def test_glide_passes_its_keys_and_holds_outside():
    for t, p in KEYS:
        assert jt.glide(KEYS, t) == pytest.approx(p)
    assert jt.glide(KEYS, -1.0) == pytest.approx(KEYS[0][1]) and jt.glide(KEYS, 5.0) == pytest.approx(KEYS[-1][1])


def test_glide_carries_through_a_middle_key_and_eases_at_the_ends():
    def speed(t, h=1e-3):
        return np.linalg.norm(np.subtract(jt.glide(KEYS, t + h), jt.glide(KEYS, t - h))) / (2 * h)
    assert speed(1.0) > 1.0                       # not stopped on the middle key (keys_at stops there)
    assert speed(0.001) < 0.05 and speed(1.999) < 0.05


def test_follow_lags_overshoots_and_settles():
    assert jt.follow(0.05, 0.0, 1.0, lag=0.1) == 0.0
    assert jt.follow(0.5, 0.0, 1.0, lag=0.1) < jt.ramp(0.5, 0.0, 1.0)
    peak = max(jt.follow(t, 0.0, 1.0, lag=0.1, over=0.1) for t in np.linspace(0, 3, 301))
    assert peak == pytest.approx(1.1, abs=0.01)
    assert jt.follow(3.0, 0.0, 1.0, lag=0.1) == pytest.approx(1.0)
    xs = [jt.follow(t, 0.0, 1.0) for t in np.linspace(0, 2, 401)]
    assert max(abs(b - a) for a, b in zip(xs, xs[1:])) < 0.02       # no jump


def test_relaxed_hand_curls_more_toward_the_little_finger_and_mirrors():
    r, l = jt.relaxed("right"), jt.relaxed("left")
    curl = [abs(l[f"left{f}Proximal"][1]) for f in ("Index", "Middle", "Ring", "Little")]
    assert curl == sorted(curl) and curl[0] > 0
    assert all(r[k.replace("left", "right")][1] == pytest.approx(-v[1]) for k, v in l.items())
    half = jt.blend_hand({}, l, 0.5)
    assert half["leftLittleProximal"][1] == pytest.approx(l["leftLittleProximal"][1] / 2)
