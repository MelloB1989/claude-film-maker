import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

from lib import thread

# Plies that just touch inside a thread of radius R: n circles of radius r on a ring of radius R - r, neighbours
# touching when (R - r) sin(pi / n) = r, so r = R s / (1 + s) and the ring is R / (1 + s), s = sin(pi / n).
R = 0.01
S3 = math.sin(math.pi / 3)
RP3 = R * S3 / (1 + S3)  # 0.004641016
RO3 = R / (1 + S3)  # 0.005358984


def _dist_to_x_axis(p):
    return np.hypot(p[:, 1], p[:, 2])


def test_three_plies_touch_inside_the_thread_radius():
    plies, rp = thread.ply_paths([(0, 0, 0), (1, 0, 0)], R, plies=3, twist=10)
    assert len(plies) == 3
    assert rp == pytest.approx(0.004641016, abs=1e-9)
    for p in plies:
        np.testing.assert_allclose(_dist_to_x_axis(p), 0.005358984, atol=1e-8)
        assert p[0, 0] == pytest.approx(0) and p[-1, 0] == pytest.approx(1)


def test_plies_sit_a_third_of_a_turn_apart_and_twist_along_the_thread():
    twist = 10  # turns per unit length: half a turn by x = 0.05
    plies, _ = thread.ply_paths([(0, 0, 0), (1, 0, 0)], R, plies=3, twist=twist)
    ang = [np.arctan2(p[:, 2], p[:, 1]) for p in plies]
    x = plies[0][:, 0]
    for k in (1, 2):  # ply k leads ply 0 by k/3 of a turn everywhere
        d = np.angle(np.exp(1j * (ang[k] - ang[0])))
        np.testing.assert_allclose(np.mod(d, 2 * np.pi), 2 * np.pi * k / 3, atol=1e-6)
    # ply 0 turns 2 pi * twist * x
    turned = np.unwrap(ang[0]) - ang[0][0]
    np.testing.assert_allclose(np.abs(turned), 2 * np.pi * twist * x, atol=1e-6)


def test_the_centreline_passes_through_every_point():
    pts = [(0, 0, 0), (1, 1, 0), (2, 0, 0)]
    c = thread.centreline(pts, 0.02)
    for q in pts:
        assert np.min(np.linalg.norm(c - np.array(q, float), axis=1)) < 1e-9
    steps = np.linalg.norm(np.diff(c, axis=0), axis=1)
    assert steps.max() <= 0.02 * 1.05  # sampled at most ~0.02 apart


def test_one_ply_is_the_thread_itself():
    plies, rp = thread.ply_paths([(0, 0, 0), (1, 0, 0)], R, plies=1, twist=10)
    assert rp == pytest.approx(R)
    np.testing.assert_allclose(_dist_to_x_axis(plies[0]), 0, atol=1e-12)


# ------------------------------------------------------------------------------------------ the macro rope (B01)

def test_the_lay_matches_the_engines_thread_look():
    # THREAD_LOOK: plies of 0.5 R on a circle of 0.5 R, a 32 degree lay = 0.199 turns per R (5.03 R per turn)
    assert thread.LOOK["ply_radius"] == 0.5 and thread.LOOK["ply_offset"] == 0.5 and thread.LOOK["lay_deg"] == 32
    assert thread.lay_turns(32, 0.5) == pytest.approx(math.tan(math.radians(32)) / math.pi, rel=1e-12)
    assert 1 / thread.lay_turns(32, 0.5) == pytest.approx(5.03, abs=0.01)


def test_a_fray_untwists_the_middle_and_puts_the_twist_back_on_its_shoulders():
    s = np.linspace(-40, 40, 8001)
    u = thread.untwisted(s, 0.0, 5.0, 1.0, 1.35)
    far = np.abs(s) >= 15  # beyond three spans the rope never turns
    np.testing.assert_allclose(u[far], s[far], atol=1e-9)
    rate = np.gradient(u, s)
    assert rate[4000] == pytest.approx(1 - 1.35 + 1.35 / 3, abs=1e-3)  # 10% of the twist at the middle
    assert np.all(np.diff(u) > 0)  # and it still turns the same way everywhere


def test_the_rotation_minimising_frame_does_not_turn_on_a_straight_line():
    X = np.column_stack([np.linspace(0, 1, 50), np.zeros(50), np.zeros(50)])
    for rev in (False, True):
        T, N, B = thread.rmf(X, [0.0, 0.3, 1.0], reverse=rev)
        n = np.array([0.0, 0.3, 1.0]) / np.hypot(0.3, 1.0)
        np.testing.assert_allclose(N, np.tile(n, (50, 1)), atol=1e-12)
        np.testing.assert_allclose(np.einsum("ij,ij->i", T, N), 0, atol=1e-12)


def test_the_fibre_rope_is_seeded():
    a = thread.fibre_rope(0.01, 0.2, seed=3, fibres=12, fuzz_per_R=4)
    b = thread.fibre_rope(0.01, 0.2, seed=3, fibres=12, fuzz_per_R=4)
    c = thread.fibre_rope(0.01, 0.2, seed=4, fibres=12, fuzz_per_R=4)
    for k in ("fib_phi", "fib_rho", "fib_break", "fz_s", "fz_len", "fib_crimp", "fib_frayloop"):
        np.testing.assert_array_equal(getattr(a, k), getattr(b, k))
    assert not np.array_equal(a.fib_phi, c.fib_phi)


def _whole(rope, side):
    s = thread.half_samples(rope, side)
    X = np.column_stack([s - rope.break_at, np.zeros_like(s), np.zeros_like(s)])
    _, N, _ = thread.rmf(X, [0.0, 0.0, 1.0], reverse=side == "right")
    return thread.still_pose(rope, s, X, N)


def test_the_halves_of_a_whole_rope_meet_fibre_for_fibre():
    R = 0.01
    rope = thread.fibre_rope(R, 40 * R, seed=5, fibres=16, fuzz_per_R=2)
    geo = {}
    for side in ("left", "right"):
        topo = thread.half_topology(rope, side)
        geo[side] = (topo, thread.rope_geometry(rope, _whole(rope, side), topo, fray_centre=rope.break_at, fray_amount=0))
    (tl, gl), (tr, gr) = geo["left"], geo["right"]
    ends = np.cumsum(gl.fibre_counts) - 1  # each left fibre's last point, each right fibre's first
    starts = np.concatenate([[0], np.cumsum(gr.fibre_counts)[:-1]])
    np.testing.assert_allclose(gl.fibre_pts[ends], gr.fibre_pts[starts], atol=1e-9)
    for k in range(3):  # the cores meet ring for ring at each ply's parting
        np.testing.assert_allclose(gl.cores[k][-1], gr.cores[k][0], atol=1e-9)
        # and a ply's centre sits THREAD_LOOK's 0.5 R off the axis (the parting ring, between samples, on a chord of the
        # helix: within 0.3%)
        centre = gl.cores[k].mean(axis=1)
        np.testing.assert_allclose(np.hypot(centre[:, 1], centre[:, 2]), 0.5 * R, rtol=3e-3)


# ------------------------------------------------------------------------------------------ the diff thread (E3)

REPO = Path(__file__).resolve().parents[2]
ENGINE = (REPO / "app/src/engine/thread3d.ts").read_text()


def _engine_look(key: str):
    """A number, or a list of them, from the engine's THREAD_LOOK (app/src/engine/thread3d.ts)."""
    block = ENGINE[ENGINE.index("export const THREAD_LOOK = {"):]
    block = block[:block.index("} as const;")]
    m = re.search(rf"\b{key}: (\[[^\]]*\]|[-\d.]+),", block)
    assert m, f"THREAD_LOOK.{key} not found"
    v = m.group(1)
    return [float(x) for x in v.strip("[]").split(",")] if v.startswith("[") else float(v)


def _hex_linear(h: str):
    return [(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) for c in (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))]


def test_the_diff_thread_preset_is_the_engines_own_numbers():
    assert thread.DIFF_THREAD == {"lay_deg": 14, "strand_dye": 0.03, "strand_scale": 0.62, "glow": 3.6, "rest": 0.15,
                                  "flare_lead": 0.05, "flare_decay": 0.6}
    # read from the file the engine reads, and the engine builds its DIFF_THREAD from that file, not numbers of its own
    d = json.loads((REPO / "data/look/thread.json").read_text())["diffThread"]
    assert thread.DIFF_THREAD == {"lay_deg": d["layDeg"], "strand_dye": d["strandDye"], "strand_scale": d["strandScale"],
                                  "glow": d["glow"], "rest": d["rest"], "flare_lead": d["flare"]["lead"],
                                  "flare_decay": d["flare"]["decay"]}
    assert "import LOOK_DATA from '../../../data/look/thread.json';" in ENGINE
    assert "const DIFF = LOOK_DATA.diffThread;" in ENGINE
    for k in ("layDeg", "strandDye", "strandScale", "glow", "rest"):
        assert re.search(rf"^  {k}: DIFF\.{k},$", ENGINE, re.M), k
    assert "export const STRAND_FLARE = { lead: DIFF.flare.lead, decay: DIFF.flare.decay };" in ENGINE


def test_the_mirror_carries_the_engines_thread_look():
    assert thread.LOOK["ply_radius"] == _engine_look("plyRadius")[2]
    assert thread.LOOK["ply_offset"] == _engine_look("plyOffset")[2]
    assert thread.LOOK["lay_deg"] == _engine_look("helixDeg")  # the bone rope's own lay (B01)
    assert thread.LOOK["worm_radius"] == _engine_look("wormRadius")
    assert thread.LOOK["dye"] == _engine_look("dye")
    assert list(thread.LOOK["glow_falloff"]) == _engine_look("glowFalloff")
    assert thread.LOOK["glow_soft"] == _engine_look("glowSoft")
    for py, ts in (("roughness", "roughness"), ("specular", "specular"), ("ior", "ior"), ("sheen", "sheen"),
                   ("sheen_roughness", "sheenRoughness")):
        assert thread.LOOK[py] == _engine_look(ts), py


def test_the_diff_threads_lay_is_hers():
    R = 0.0042
    # her.ts before the preset: a 14 degree lay at the bone plies' offset, tan 14° / (2π · R/2) turns per unit length
    assert thread.diff_twist(R) == pytest.approx(math.tan(math.radians(14)) / (2 * math.pi * 0.5 * R), rel=1e-12)
    assert thread.diff_twist(R, {**thread.DIFF_THREAD, "lay_deg": 32}) == pytest.approx(thread.lay_turns(32, 0.5 * R))


def test_the_strands_lie_in_the_grooves_of_the_bone_plies_slimmed_and_touching_both_neighbours():
    tubes = thread.diff_tubes()
    assert [t["color"] for t in tubes] == ["bone", "bone", "bone", "blood", "moss"]
    for k, t in enumerate(tubes[:3]):
        assert (t["r"], t["d"]) == (0.5, 0.5) and t["phase"] == pytest.approx(k / 3)
    rw = 0.2 * 0.62
    D = 0.25 + math.sqrt((0.5 + rw) ** 2 - (0.5 * math.sin(math.pi / 3)) ** 2)  # deeper in the groove than 0.8
    blood, moss = tubes[3], tubes[4]
    for s in (blood, moss):
        assert s["r"] == pytest.approx(rw, abs=1e-15) and s["d"] == pytest.approx(D, abs=1e-15)
        c = s["d"] * np.exp(2j * np.pi * s["phase"])
        gaps = sorted(abs(c - 0.5 * np.exp(2j * np.pi * k / 3)) for k in range(3))
        np.testing.assert_allclose(gaps[:2], 0.5 + rw, atol=1e-12)  # touching the plies either side
    # the − a groove ahead of the +: blood at half a turn, moss at a sixth
    assert blood["phase"] == 0.5 and moss["phase"] == pytest.approx(1 / 6)


def test_diff_thread_paths_wind_every_tube_at_its_offset_with_the_lay():
    R = 0.01
    paths = thread.diff_thread_paths([(0, 0, 0), (0.5, 0, 0), (1, 0, 0)], R)
    assert [p[0]["color"] for p in paths] == ["bone", "bone", "bone", "blood", "moss"]
    twist = thread.diff_twist(R)
    ang = {}
    for tube, P, r in paths:
        assert r == pytest.approx(tube["r"] * R)
        np.testing.assert_allclose(np.hypot(P[:, 1], P[:, 2]), tube["d"] * R, atol=1e-12)
        assert P[0, 0] == pytest.approx(0) and P[-1, 0] == pytest.approx(1)
        a = np.unwrap(np.arctan2(P[:, 1], P[:, 2]))
        np.testing.assert_allclose(np.abs(a - a[0]), 2 * np.pi * twist * P[:, 0], atol=1e-6)  # the lay's turns
        ang[tube["color"]] = a
    # along the thread the blood strand is a third of a turn ahead of the moss
    np.testing.assert_allclose(np.mod(np.abs(ang["blood"] - ang["moss"]), 2 * np.pi), 2 * np.pi / 3, atol=1e-6)


def test_the_strands_colour_is_the_engines_dyed_fibre_and_their_glow_its_emission():
    # dyed 82% of the way to the dim shade (THREAD_LOOK.dye), then near ink (strand_dye 0.03): the engine's uColors
    for color, base, dim in (("blood", "#c22b45", "#8e1f35"), ("moss", "#4aad63", "#1c3324")):
        want = [(x + (y - x) * 0.82) * 0.03 for x, y in zip(_hex_linear(base), _hex_linear(dim))]
        np.testing.assert_allclose(thread.strand_albedo(color), want, rtol=1e-9)
    np.testing.assert_allclose(thread.strand_albedo("blood", 1.0), [0.319, 0.0156, 0.0399], atol=5e-4)  # report §4
    # the emission: the palette colour with its brightest channel 1, at strength = the glow level, is look.ts glow():
    # the engine's thread test pins these at level 2.5
    np.testing.assert_allclose(np.multiply(thread.glow_color("blood"), 2.5), [2.5, 0.1119488, 0.2757808], atol=1e-6)
    np.testing.assert_allclose(np.multiply(thread.glow_color("moss"), 2.5), [0.4096711, 2.5, 0.7464482], atol=1e-6)
    # and across the strand, a filament over a soft base: 0.8 (N·V)^28 + 0.2 (N·V)^3 (report §4)
    assert thread.glow_profile(1.0) == pytest.approx(1.0)
    assert thread.glow_profile(0.9) == pytest.approx(0.8 * 0.9 ** 28 + 0.2 * 0.9 ** 3)
    assert thread.glow_profile(0.0) == 0.0


def test_strand_flare_and_strand_glow_are_the_engines():
    at = 10.0
    assert thread.strand_flare(at - 0.2, at) == 0
    assert thread.strand_flare(at - 0.05, at) == 0
    assert thread.strand_flare(at - 0.025, at) == pytest.approx(0.5, abs=1e-9)
    assert thread.strand_flare(at, at) == 1
    assert thread.strand_flare(at + 0.15, at) == pytest.approx(0.5625, abs=1e-9)
    assert thread.strand_flare(at + 0.3, at) == pytest.approx(0.25, abs=1e-9)
    assert thread.strand_flare(at + 0.6, at) == 0
    assert thread.strand_flare(at + 0.3, [at, at + 0.3]) == 1
    assert thread.strand_flare(at, []) == 0
    assert thread.strand_flare(at + 0.5, at, decay=1.0) == pytest.approx(0.25, abs=1e-9)
    assert thread.strand_glow(0.0, 5.0) == 0.15
    assert thread.strand_glow(5.0, 5.0) == 3.6
    assert thread.strand_glow(5.3, [5.0]) == pytest.approx(0.15 + 0.25 * (3.6 - 0.15), abs=1e-9)
    assert thread.strand_glow(5.0, 5.0, rest=0.0, lit=2.0) == 2.0
