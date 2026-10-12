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


# ------------------------------------------------------------------------------------------ the macro rope

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


# ------------------------------------------------------------------------------------------ the strand thread

REPO = Path(__file__).resolve().parents[2]
ENGINE_TS = REPO / "app/src/engine/thread3d.ts"
WANT = {"lay_deg": 14, "strand_dye": 0.03, "strand_scale": 0.62, "glow": 3.6, "rest": 0.15, "flare_lead": 0.05,
        "flare_decay": 0.6}


def _engine_look(key: str):
    """A number, or a list of them, from the engine's THREAD_LOOK (app/src/engine/thread3d.ts)."""
    src = ENGINE_TS.read_text()
    block = src[src.index("export const THREAD_LOOK = {"):]
    block = block[:block.index("} as const;")]
    m = re.search(rf"\b{key}: (\[[^\]]*\]|[-\d.]+),", block)
    assert m, f"THREAD_LOOK.{key} not found"
    v = m.group(1)
    return [float(x) for x in v.strip("[]").split(",")] if v.startswith("[") else float(v)


def _hex_linear(h: str):
    return [(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) for c in (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))]


def _look(**d):
    return {"diffThread": {"layDeg": 14, "strandDye": 0.03, "strandScale": 0.62, "glow": 3.6, "rest": 0.15,
                           "flare": {"lead": 0.05, "decay": 0.6}, **d}}


def test_the_strand_threads_defaults_are_the_engines_numbers():
    assert thread.STRAND_DEFAULTS == WANT


def test_the_preset_reads_the_engines_file_and_a_film_may_override_it(tmp_path):
    engine = tmp_path / "thread-look.json"
    assert thread.strand_preset(engine_file=engine) == WANT  # no engine file in the checkout: the defaults
    engine.write_text(json.dumps(_look(glow=4.0, flare={"lead": 0.1, "decay": 0.5})))
    assert thread.strand_preset(engine_file=engine) == {**WANT, "glow": 4.0, "flare_lead": 0.1, "flare_decay": 0.5}
    film = tmp_path / "films" / "demo"
    (film / "data" / "look").mkdir(parents=True)
    assert thread.strand_preset(film, engine_file=engine)["glow"] == 4.0  # the film has no look of its own yet
    (film / "data" / "look" / "thread.json").write_text(json.dumps({"strandThread": {"layDeg": 20, "flare": {"decay": 1}}}))
    got = thread.strand_preset(film, engine_file=engine)  # a film's file overrides only what it gives
    assert got == {**WANT, "glow": 4.0, "flare_lead": 0.1, "lay_deg": 20.0, "flare_decay": 1.0}
    assert thread.strand_preset(type("Film", (), {"root": film})(), engine_file=engine) == got  # a Film works too
    with pytest.raises(ValueError, match="strandThread"):
        thread.parse_strand_look({"thread": {}})


@pytest.mark.skipif(not thread.LOOK_FILE.exists(), reason="the engine's thread-look.json is not in this checkout")
def test_the_default_preset_is_the_engines_file():
    d = json.loads(thread.LOOK_FILE.read_text())
    assert thread.STRAND_THREAD == {**thread.STRAND_DEFAULTS, **thread.parse_strand_look(d)}


@pytest.mark.skipif(not ENGINE_TS.exists(), reason="the engine's thread3d.ts is not in this checkout")
def test_the_mirror_carries_the_engines_thread_look():
    assert thread.LOOK["ply_radius"] == _engine_look("plyRadius")[2]
    assert thread.LOOK["ply_offset"] == _engine_look("plyOffset")[2]
    assert thread.LOOK["lay_deg"] == _engine_look("helixDeg")  # the macro rope's own lay
    assert thread.LOOK["worm_radius"] == _engine_look("wormRadius")
    assert thread.LOOK["dye"] == _engine_look("dye")
    assert list(thread.LOOK["glow_falloff"]) == _engine_look("glowFalloff")
    assert thread.LOOK["glow_soft"] == _engine_look("glowSoft")
    for py, ts in (("roughness", "roughness"), ("specular", "specular"), ("ior", "ior"), ("sheen", "sheen"),
                   ("sheen_roughness", "sheenRoughness")):
        assert thread.LOOK[py] == _engine_look(ts), py


def test_the_strand_threads_lay_is_the_presets():
    R = 0.0042
    # a 14 degree lay at the plies' offset: tan 14° / (2π · R/2) turns per unit length
    preset = {**thread.STRAND_DEFAULTS}
    assert thread.strand_twist(R, preset) == pytest.approx(math.tan(math.radians(14)) / (2 * math.pi * 0.5 * R), rel=1e-12)
    assert thread.strand_twist(R, {**preset, "lay_deg": 32}) == pytest.approx(thread.lay_turns(32, 0.5 * R))


def test_the_strands_lie_in_the_grooves_of_the_plies_slimmed_and_touching_both_neighbours():
    tubes = thread.strand_tubes(0.62)
    assert [t["color"] for t in tubes] == ["fg", "fg", "fg", "accent", "accent2"]
    for k, t in enumerate(tubes[:3]):
        assert (t["r"], t["d"]) == (0.5, 0.5) and t["phase"] == pytest.approx(k / 3)
    rw = 0.2 * 0.62
    D = 0.25 + math.sqrt((0.5 + rw) ** 2 - (0.5 * math.sin(math.pi / 3)) ** 2)  # deeper in the groove than 0.8
    accent, accent2 = tubes[3], tubes[4]
    for s in (accent, accent2):
        assert s["r"] == pytest.approx(rw, abs=1e-15) and s["d"] == pytest.approx(D, abs=1e-15)
        c = s["d"] * np.exp(2j * np.pi * s["phase"])
        gaps = sorted(abs(c - 0.5 * np.exp(2j * np.pi * k / 3)) for k in range(3))
        np.testing.assert_allclose(gaps[:2], 0.5 + rw, atol=1e-12)  # touching the plies either side
    # the accent a groove ahead of the accent2: at half a turn, the accent2 at a sixth
    assert accent["phase"] == 0.5 and accent2["phase"] == pytest.approx(1 / 6)


def test_strand_thread_paths_wind_every_tube_at_its_offset_with_the_lay():
    R = 0.01
    paths = thread.strand_thread_paths([(0, 0, 0), (0.5, 0, 0), (1, 0, 0)], R)
    assert [p[0]["color"] for p in paths] == ["fg", "fg", "fg", "accent", "accent2"]
    twist = thread.strand_twist(R)
    ang = {}
    for tube, P, r in paths:
        assert r == pytest.approx(tube["r"] * R)
        np.testing.assert_allclose(np.hypot(P[:, 1], P[:, 2]), tube["d"] * R, atol=1e-12)
        assert P[0, 0] == pytest.approx(0) and P[-1, 0] == pytest.approx(1)
        a = np.unwrap(np.arctan2(P[:, 1], P[:, 2]))
        np.testing.assert_allclose(np.abs(a - a[0]), 2 * np.pi * twist * P[:, 0], atol=1e-6)  # the lay's turns
        ang[tube["color"]] = a
    # along the thread the accent strand is a third of a turn ahead of the accent2
    np.testing.assert_allclose(np.mod(np.abs(ang["accent"] - ang["accent2"]), 2 * np.pi), 2 * np.pi / 3, atol=1e-6)


def test_the_strands_colour_is_the_engines_dyed_fibre_and_their_glow_its_emission(noir):
    # dyed 82% of the way to the role's dim shade (THREAD_LOOK.dye), then near black (strand_dye 0.03): the engine's
    # uColors. noir: accent #c22b45 (dim #8e1f35), accent2 #4aad63 (dim #1c3324)
    for color, base, dim in (("accent", "#c22b45", "#8e1f35"), ("accent2", "#4aad63", "#1c3324")):
        want = [(x + (y - x) * 0.82) * 0.03 for x, y in zip(_hex_linear(base), _hex_linear(dim))]
        np.testing.assert_allclose(thread.strand_albedo(color, 0.03), want, rtol=1e-9)
    np.testing.assert_allclose(thread.strand_albedo("accent", 1.0), [0.319, 0.0156, 0.0399], atol=5e-4)
    # the emission: the role's colour with its brightest channel 1, at strength = the glow level, is look.ts glow():
    # the engine's thread test pins these at level 2.5
    np.testing.assert_allclose(np.multiply(thread.glow_color("accent"), 2.5), [2.5, 0.1119488, 0.2757808], atol=1e-6)
    np.testing.assert_allclose(np.multiply(thread.glow_color("accent2"), 2.5), [0.4096711, 2.5, 0.7464482], atol=1e-6)
    # and across the strand, a filament over a soft base: 0.8 (N·V)^28 + 0.2 (N·V)^3
    assert thread.glow_profile(1.0) == pytest.approx(1.0)
    assert thread.glow_profile(0.9) == pytest.approx(0.8 * 0.9 ** 28 + 0.2 * 0.9 ** 3)
    assert thread.glow_profile(0.0) == 0.0


def test_strand_flare_and_strand_glow_are_the_engines():
    if thread.STRAND_THREAD != WANT:
        pytest.skip("the engine's thread-look.json has numbers of its own: the expectations below are the defaults'")
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


# ------------------------------------------------------------------------------------------ strands in the macro rope

def _straight(rope, s, n0=(0.0, 0.0, 1.0)):
    X = np.column_stack([s - rope.break_at, np.zeros_like(s), np.zeros_like(s)])
    _, N, _ = thread.rmf(X, list(n0))
    return thread.still_pose(rope, s, X, N)


def test_a_groove_strand_lies_between_two_plies_at_the_strand_offset():
    R = 0.01
    rope = thread.fibre_rope(R, 30 * R, seed=2, fibres=8, fuzz_per_R=1, lay_deg=14)
    s = rope.grid
    pose = _straight(rope, s)
    D = thread.strand_tubes()[3]["d"]
    for groove in (0.5, 1 / 6):
        P, out = thread.groove_path(rope, pose, groove, fray_centre=rope.break_at, fray_amount=0.0)
        np.testing.assert_allclose(np.hypot(P[:, 1], P[:, 2]), D * R, atol=1e-12)  # D R off the axis
        np.testing.assert_allclose(np.linalg.norm(out, axis=1), 1, atol=1e-12)
        # at the groove's phase: a sixth of a turn from each ply either side, winding with the lay
        # N is +z here and B = T x N is -y, so the angle round from N toward B is atan2(-y, z)
        want = 2 * np.pi * (groove + rope.twist * s)
        np.testing.assert_allclose(np.angle(np.exp(1j * (np.arctan2(-P[:, 1], P[:, 2]) - want))), 0, atol=1e-9)


def test_a_groove_strand_follows_the_poses_unravel_and_its_depth_can_vary():
    R = 0.01
    rope = thread.fibre_rope(R, 30 * R, seed=2, fibres=8, fuzz_per_R=1, lay_deg=24)
    s = rope.grid
    pose = _straight(rope, s)
    pose.unravel = np.full(len(s), 0.25)  # a quarter turn more everywhere
    P, _ = thread.groove_path(rope, pose, 0.5, fray_centre=rope.break_at, fray_amount=0.0)
    want = 2 * np.pi * (0.75 + rope.twist * s)
    np.testing.assert_allclose(np.angle(np.exp(1j * (np.arctan2(-P[:, 1], P[:, 2]) - want))), 0, atol=1e-9)
    depth = np.linspace(0, 0.7, len(s))  # rising out of the axis
    P2, _ = thread.groove_path(rope, pose, 0.5, depth=depth, fray_centre=rope.break_at, fray_amount=0.0)
    np.testing.assert_allclose(np.hypot(P2[:, 1], P2[:, 2]), depth * R, atol=1e-12)


def test_the_macro_ropes_strand_at_the_presets_lay_is_the_strand_threads_strand():
    # a fibre rope laid at the preset's 14 degrees, straight, carries its accent strand where strand_thread_paths puts it
    R = 0.01
    L = 20 * R
    rope = thread.fibre_rope(R, L, seed=2, fibres=8, fuzz_per_R=1, lay_deg=thread.STRAND_THREAD["lay_deg"])
    assert rope.twist == pytest.approx(thread.strand_twist(R), rel=1e-12)
    (tube, Q, r) = thread.strand_thread_paths([(-L / 2, 0, 0), (L / 2, 0, 0)], R)[3]
    assert tube["color"] == "accent"
    s = Q[:, 0] + L / 2  # the rope posed on the strand thread's own samples
    P, _ = thread.groove_path(rope, _straight(rope, s), 0.5, fray_centre=rope.break_at, fray_amount=0.0)
    np.testing.assert_allclose(P, Q, atol=1e-9 * R)


def test_tube_rings_are_round_square_to_the_path_and_vanish_at_radius_zero():
    t = np.linspace(0, 4 * np.pi, 200)
    P = np.column_stack([np.cos(t), np.sin(t), 0.3 * t])  # a helix
    r = np.linspace(0, 0.05, 200)
    rings = thread.tube_rings(P, r, seg=10)
    assert rings.shape == (200, 10, 3)
    T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    off = rings - P[:, None]
    np.testing.assert_allclose(np.linalg.norm(off, axis=2), np.repeat(r[:, None], 10, 1), atol=1e-12)
    np.testing.assert_allclose(np.einsum("mkj,mj->mk", off, T), 0, atol=1e-12)
    np.testing.assert_allclose(rings[0], np.repeat(P[:1], 10, 0), atol=0)  # radius 0: a point
