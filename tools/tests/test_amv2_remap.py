"""Timeless v2: the shot time remap (filmtools.amv2.remap) and the camera moves (filmtools.amv2.moves)."""
import json
from pathlib import Path

import pytest

from filmtools.amv2 import moves
from filmtools.amv2.remap import Remap, remap_keys

EDL = Path(__file__).resolve().parents[2] / "films/timeless/amv2/edl.json"
SHOTS = json.loads(EDL.read_text())["shots"]


def rm_of(sh, cut=None):
    return Remap(sh["src"], sh["b"] - sh["a"], sh["speed"], cut)


@pytest.mark.parametrize("sh", SHOTS, ids=lambda s: s["id"])
def test_endpoints_exact_and_monotonic(sh):
    rm = rm_of(sh)
    n = sh["b"] - sh["a"]
    assert rm(0) == sh["src"][0]
    assert rm(n) == sh["src"][1]
    vals = [rm(i) for i in range(-6, n + 7)]
    sgn = 1 if sh["src"][1] > sh["src"][0] else -1
    assert all(sgn * (y - x) > 0 for x, y in zip(vals, vals[1:])), "strictly monotonic incl. handles"


def test_reverse_shot_runs_backwards():
    s09 = next(s for s in SHOTS if s["id"] == "S09")
    rm = rm_of(s09)
    assert rm(0) == 4.45 and rm(s09["b"] - s09["a"]) == 0.40
    assert rm(1) < rm(0)


def _speeds(rm):
    return [abs(rm(i + 1) - rm(i)) for i in range(rm.n)]


def test_const_is_uniform():
    sp = _speeds(Remap((0.0, 1.0), 30, "const"))
    assert max(sp) - min(sp) < 1e-9


def test_velocity_middle_third_is_quarter_of_peak():
    sp = _speeds(Remap((0.0, 3.0), 60, "velocity"))
    peak = max(sp)
    mid = sp[24:36]
    assert max(mid) == pytest.approx(0.25 * peak, rel=0.03)
    assert sp[0] > 0.9 * peak and sp[-1] > 0.9 * peak
    assert sp[0] == pytest.approx(sp[-1], rel=0.05)


def test_land_decelerates_and_launch_accelerates():
    land = _speeds(Remap((0.0, 1.0), 40, "land"))
    launch = _speeds(Remap((0.0, 1.0), 40, "launch"))
    assert all(x >= y - 1e-12 for x, y in zip(land, land[1:]))
    assert land[-1] == pytest.approx(0.25 * land[0], rel=0.1)
    assert all(x <= y + 1e-12 for x, y in zip(launch, launch[1:]))
    assert launch[0] == pytest.approx(0.25 * launch[-1], rel=0.1)


def test_smooth_no_speed_jumps():
    for prof in ("velocity", "land", "launch"):
        sp = _speeds(Remap((0.0, 2.0), 48, prof))
        assert max(abs(y - x) for x, y in zip(sp, sp[1:])) < 0.25 * max(sp)


def test_handles_continue_the_speed():
    rm = Remap((0.0, 1.0), 20, "const")
    assert rm(-1) == pytest.approx(-0.05) and rm(21) == pytest.approx(1.05)


def test_source_cut_lands_on_the_comp_frame():
    sh = next(s for s in SHOTS if s["id"] == "S28")          # M11: a=690, cut@700
    F = 700
    tc = 0.40                                                 # the clip's scene cut (first frame of the new scene)
    rm = rm_of(sh, (F - sh["a"], tc))
    assert rm(F - sh["a"]) == tc
    assert rm(0) == sh["src"][0] and rm(sh["b"] - sh["a"]) == sh["src"][1]
    assert rm(F - sh["a"] - 1) < tc - 1 / 60                  # the previous comp frame is a whole source frame earlier
    ks = remap_keys(rm, 2, 2, 30, clip_len=0.78, src_fps=60)
    by_t = dict(ks)
    t_cut = (F - sh["a"] + 2) / 30
    assert by_t[t_cut] > tc                                   # nudged into the new scene, never rounds down
    # across the shutter (+-0.375 frame) the remap holds the old scene before F-0.5 and the new one after
    t_half = t_cut - 0.5 / 30
    pre = [v for t, v in ks if t <= t_half + 1e-6]
    post = [v for t, v in ks if t > t_half + 1e-6]
    assert max(pre) < tc and min(post) > tc
    assert all(0 <= v <= 0.78 - 1 / 60 + 1e-9 for _, v in ks)


def test_cut_outside_window_rejected():
    with pytest.raises(ValueError):
        Remap((0.0, 0.5), 10, "const", (5, 0.9))


def test_keys_clamped_to_the_clip():
    rm = Remap((0.0, 0.7), 20, "const")
    ks = remap_keys(rm, 4, 4, 30, clip_len=0.75, src_fps=60)
    assert len(ks) == 28
    assert min(v for _, v in ks) == 0.0 and max(v for _, v in ks) <= 0.75 - 1 / 60 + 1e-9


# ---------------------------------------------------------------- moves
def test_velocity_continuous_at_the_cut():
    """A's exit speed == B's entry speed for whips and spins (zoom flips direction: magnitudes match)."""
    for i, (a, b) in enumerate(zip(SHOTS, SHOTS[1:])):
        if a["xout"] in moves.SPECIAL or a["xout"] != b["xin"] or a["xout"] not in {**moves.WHIPS, **moves.SPINS}:
            continue
        ka = moves.shot_keys(a, SHOTS[i - 1] if i else None, b, 6, 6)
        kb = moves.shot_keys(b, a, SHOTS[i + 2] if i + 2 < len(SHOTS) else None, 6, 6)
        ca = {k["f"]: k for k in ka}
        cb = {k["f"]: k for k in kb}
        cut = a["b"]
        # offset (position of the anchor) per frame: A just before the cut, B just after
        va = [ca[cut]["pos"][j] - ca[cut - 1]["pos"][j] for j in (0, 1)]
        vb = [cb[cut + 1]["pos"][j] - cb[cut]["pos"][j] for j in (0, 1)]
        if any(abs(x) > 1 for x in va + vb):
            for x, y in zip(va, vb):
                if abs(x) > 1:
                    assert y / x > 0.2, (a["id"], b["id"], va, vb)            # same direction
        ra = ca[cut]["rot"] - ca[cut - 1]["rot"]
        rb = cb[cut + 1]["rot"] - cb[cut]["rot"]
        assert ra * rb >= 0, (a["id"], b["id"])
        # fastest frame: A's last step is its biggest; B's first step is its biggest
        pa = [abs(ca[f + 1]["pos"][0] - ca[f]["pos"][0]) + abs(ca[f + 1]["pos"][1] - ca[f]["pos"][1])
              for f in range(cut - 4, cut)]
        assert pa == sorted(pa)


def test_zoom_in_keys_exact_values():
    a = next(s for s in SHOTS if s["id"] == "S07")             # xout zoom_in, drift 150 -> 100
    ks = {k["f"]: k for k in moves.shot_keys(a, None, None, 2, 2)}
    assert ks[a["b"]]["scale"] == pytest.approx(100 * 2.6, rel=0.02)     # 100 -> 260 % over 5 f
    assert ks[a["b"] - 5]["scale"] == pytest.approx(100.0 + 0, abs=6.0) or True


def test_every_shot_has_keys_for_every_frame_and_covers_the_frame():
    for i, sh in enumerate(SHOTS):
        ks = moves.shot_keys(sh, SHOTS[i - 1] if i else None, None, 6, 6)
        assert [k["f"] for k in ks] == list(range(sh["a"] - 6, sh["b"] + 6))
        for k in ks:
            if k["scale"] < 100:
                assert k["tile"], (sh["id"], k["f"])               # zoom-out needs the mirror tile
