# The example shots (blender/examples/shots): each keeps the SHOT contract and imports without Blender (bpy is imported
# inside build()); hero_orbit's geometry and framing are checked by hand-worked rules.
import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

from lib import cli, film, rig, timing

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "shots"


def load(name):
    spec = importlib.util.spec_from_file_location(f"examples.{name}", EXAMPLES / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hero = load("hero_orbit")


@pytest.mark.parametrize("name", ["hero_orbit", "smoke_cube"])
def test_every_example_keeps_the_shot_contract(name):
    shot = cli.check_shot(load(name), name)
    assert shot["track"]


def test_the_hero_spans_its_scene_and_the_smoke_test_its_own_frames():
    t = timing.Timing([{"id": "hero", "start": 2.0, "end": 6.0}], fps=24)
    assert cli.shot_frames(load("hero_orbit").SHOT, t) == (48, 144)
    assert cli.shot_frames(load("smoke_cube").SHOT, timing.Timing()) == (40, 60)  # no timeline needed


def test_the_knot_is_a_closed_loop_round_its_torus():
    c, out = hero.torus_knot(n=600)
    R, r = hero.KNOT["R"], hero.KNOT["r"]
    # every point is r from the core circle of radius R, in the direction `out`
    core = np.column_stack([c[:, 0], c[:, 1], np.zeros(len(c))])
    core *= R / np.linalg.norm(core, axis=1, keepdims=True)
    np.testing.assert_allclose(c - core, r * out, atol=1e-12)
    np.testing.assert_allclose(np.linalg.norm(out, axis=1), 1, atol=1e-12)
    steps = np.linalg.norm(np.diff(np.vstack([c, c[:1]]), axis=0), axis=1)
    assert steps.max() < 1.5 * steps.mean()  # closed: the step from the last point back to the first is like the rest
    # a (2, 3) torus knot never meets itself: no two points far apart along it come within two tube radii
    d = np.linalg.norm(c[:, None] - c[None], axis=2)
    i, j = np.triu_indices(len(c), k=30)
    far_along = np.minimum(j - i, len(c) - (j - i)) >= 30
    assert d[i[far_along], j[far_along]].min() > 2 * hero.KNOT["tube"]


def test_the_tube_is_watertight_and_round():
    c, out = hero.torus_knot(n=120)
    verts, faces = hero.closed_tube(c, out, 0.1, seg=16)
    assert verts.shape == (120 * 16, 3)
    edges = {}
    for f in faces:
        for k in range(4):
            e = tuple(sorted((f[k], f[(k + 1) % 4])))
            edges[e] = edges.get(e, 0) + 1
    assert set(edges.values()) == {2}  # every edge between exactly two faces: closed, no seam
    rings = verts.reshape(120, 16, 3)
    np.testing.assert_allclose(np.linalg.norm(rings - c[:, None], axis=2), 0.1, atol=1e-12)


@pytest.mark.parametrize("fmt", list(film.FORMATS))
def test_the_orbit_keeps_the_whole_hero_in_every_format(fmt):
    W, H = film.FORMATS[fmt]
    look = hero.LOOK
    d = hero.fit_distance(hero.hero_radius(), look["fov"], W / H)
    c, out = hero.torus_knot(n=240)
    verts, _ = hero.closed_tube(c, out, hero.KNOT["tube"], seg=12)
    target = np.array([0.0, 0.0, hero.HEIGHT])
    for spin in (0.0, look["spinDeg"]):  # the knot as it turns, seen from either end of the orbit
        a = math.radians(spin)
        pts = verts @ np.array([[math.cos(a), math.sin(a), 0], [-math.sin(a), math.cos(a), 0], [0, 0, 1]]) + target
        for angle in (-look["orbitDeg"] / 2, 0.0, look["orbitDeg"] / 2):
            cam = hero.orbit_position(angle, look["elevationDeg"], d)
            assert np.linalg.norm(cam - target) == pytest.approx(d)
            # the engine's pinhole on this film's logical frame (Blender z up -> the engine's y up: (x, z, -y))
            to_engine = lambda p: np.asarray(p) @ np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])  # noqa: E731
            pose = rig.Pose(to_engine(cam), to_engine(target), look["fov"])
            xy = pose.project_many(to_engine(pts), size=(W, H))
            assert np.isfinite(xy).all()
            margin = 0.05 * min(W, H)
            assert xy[:, 0].min() > margin and xy[:, 0].max() < W - margin, fmt
            assert xy[:, 1].min() > margin and xy[:, 1].max() < H - margin, fmt
            assert pose.project(to_engine(target), (W, H)) == pytest.approx((W / 2, H / 2))  # the hero is centred


def test_the_horizon_stays_out_of_frame():
    # the camera looks down `elevationDeg`: the horizon sits that far above the frame's centre, past the half fov
    assert hero.LOOK["elevationDeg"] > hero.LOOK["fov"] / 2


def test_the_callout_sits_on_the_knots_outer_surface():
    p = hero.callout_point()
    R, r, tube = hero.KNOT["R"], hero.KNOT["r"], hero.KNOT["tube"]
    assert p == pytest.approx([R + r + tube, 0.0, 0.0])
    assert hero.hero_radius() == pytest.approx(R + r + tube)
