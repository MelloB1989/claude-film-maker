import math

import numpy as np
import pytest

from lib import vrm_skin as sk


def _quad(size: float = 1.0, uv_scale: float = 1.0) -> sk.Surface:
    """A square `size` metres in the x-z plane (facing -y, like a VRM's face) mapped onto UV [0, uv_scale]."""
    a, b, c, d = (0, 0, 0), (size, 0, 0), (size, 0, size), (0, 0, size)
    ua, ub, uc, ud = (0, 0), (uv_scale, 0), (uv_scale, uv_scale), (0, uv_scale)
    return sk.Surface([[a, b, c], [a, c, d]], [[ua, ub, uc], [ua, uc, ud]])


def _blank(h: int = 64, w: int = 64, v: float = 0.8) -> np.ndarray:
    px = np.full((h, w, 4), v, np.float32)
    px[..., 3] = 1.0
    return px


def test_catmull_rom_runs_through_its_points():
    pts = np.array([[0, 0], [1, 1], [2, 0], [3, 1.0]])
    c = sk.catmull_rom(pts, n=8)
    assert len(c) == 3 * 8 + 1
    for p in pts:
        assert np.min(np.linalg.norm(c - p, axis=1)) < 1e-9
    assert sk.catmull_rom([[1, 2, 3]]).tolist() == [[1, 2, 3]]


def test_closest_on_triangles_inside_edge_and_corner():
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 0, 1.0]]])
    idx, bary, d = sk.closest_on_triangles([[0.25, -0.3, 0.25]], tri)
    assert idx[0] == 0 and d[0] == pytest.approx(0.3)
    assert bary[0] == pytest.approx([0.5, 0.25, 0.25])
    _, bary, d = sk.closest_on_triangles([[0.5, 0.0, -0.2]], tri)            # beyond the edge a-b
    assert bary[0] == pytest.approx([0.5, 0.5, 0.0]) and d[0] == pytest.approx(0.2)
    _, bary, d = sk.closest_on_triangles([[-1.0, 0.0, -1.0]], tri)           # past the corner a
    assert bary[0] == pytest.approx([1, 0, 0]) and d[0] == pytest.approx(math.sqrt(2))


def test_closest_on_triangles_picks_the_nearest():
    far = [[0, 5, 0], [1, 5, 0], [0, 5, 1.0]]
    near = [[0, 1, 0], [1, 1, 0], [0, 1, 1.0]]
    idx, _, d = sk.closest_on_triangles([[0.2, 0.0, 0.2], [0.2, 6.0, 0.2]], [far, near])
    assert idx.tolist() == [1, 0] and d == pytest.approx([1.0, 1.0])


def test_surface_projects_to_uv_and_says_how_far_a_metre_goes():
    s = _quad(0.5, 1.0)
    uv, dens = s.project([[0.125, -0.01, 0.25], [0.4, 0.02, 0.1]])
    assert uv[0] == pytest.approx([0.25, 0.5]) and uv[1] == pytest.approx([0.8, 0.2])
    assert dens == pytest.approx([2.0, 2.0])           # half a metre spans the whole UV


def test_composite_blends():
    px = _blank(4, 4, 0.8)
    mask = np.ones((2, 2), np.float32)
    sk.composite(px, mask, (0, 2, 0, 2), (0.0, 0.0, 0.0), 0.5, "multiply")
    assert px[0, 0, :3] == pytest.approx([0.4] * 3) and px[3, 3, :3] == pytest.approx([0.8] * 3)
    sk.composite(px, mask, (2, 4, 2, 4), (0.2, 0.2, 0.2), 1.0, "mix")
    assert px[3, 3, :3] == pytest.approx([0.2] * 3)
    sk.composite(px, mask, (0, 2, 2, 4), (1.0, 1.0, 1.0), 0.5, "screen")
    assert px[0, 3, 0] == pytest.approx(0.9)
    px[..., 3] = 0.2
    sk.composite(px, mask, (0, 2, 0, 2), (0.7,), 1.0, "max", channels=slice(3, 4))
    assert px[0, 0, 3] == pytest.approx(0.7) and px[3, 3, 3] == pytest.approx(0.2)
    with pytest.raises(ValueError, match="blend"):
        sk.composite(px, mask, (0, 2, 0, 2), (0, 0, 0), 1.0, "burn")


def test_stroke_darkens_along_its_line_only():
    px = _blank()
    sk.stroke(px, [[10, 32], [54, 32]], 4.0, (0.0, 0.0, 0.0), 1.0)
    assert px[32, 30, 0] == pytest.approx(0.0, abs=1e-6)     # on the line (row = y)
    assert px[31, 30, 0] < 0.05                              # within its 4 px
    assert px[36, 30, 0] == pytest.approx(0.8)               # clear of it
    assert px[32, 4, 0] == pytest.approx(0.8)                # past its end
    # a thinner end draws less
    px = _blank()
    sk.stroke(px, [[10, 32], [54, 32]], [6.0, 0.5], (0.0, 0.0, 0.0), 1.0)
    assert px[34, 12, 0] < 0.2 and px[32, 52, 0] > 0.3


def test_spot_is_round_solid_inside_and_clear_outside():
    px = _blank()
    sk.spot(px, (32, 32), 10.0, (0.0, 0.0, 0.0), 1.0, hardness=0.5)
    assert px[32, 32, 0] == pytest.approx(0.0, abs=1e-6)
    assert px[32, 45, 0] == pytest.approx(0.8) and px[45, 32, 0] == pytest.approx(0.8)
    assert 0.0 < px[32, 40, 0] < 0.8
    px = _blank()
    sk.spot(px, (32, 32), 6.0, (0.0, 0.0, 0.0), 1.0, stretch=3.0, angle=0.0)
    assert px[32, 46, 0] < 0.8 and px[46, 32, 0] == pytest.approx(0.8)     # long along x


def test_profile_tapers_both_ends():
    t = np.array([0.0, 0.5, 1.0])
    assert sk.profile(t, (0.2, 0.6)) == pytest.approx([0.2, 1.0, 0.6])


def test_paint_puts_a_mark_where_its_3d_points_fall():
    s = _quad(0.5, 1.0)                    # a 0.5 m square on the whole texture: 128 px per metre at 64 px
    px = _blank()
    line = sk.Mark([[0.1, 0.0, 0.25], [0.25, 0.0, 0.25], [0.4, 0.0, 0.25]], width=0.03, color=(0, 0, 0),
                   strength=1.0, taper=(1.0, 1.0))
    sk.paint(px, s, [line])
    assert px[32, 32, 0] == pytest.approx(0.0, abs=1e-3)    # z 0.25 of 0.5: row 32
    assert px[32, 4, 0] == pytest.approx(0.8)               # x 0.03: short of its start
    assert px[38, 32, 0] == pytest.approx(0.8)              # 3 cm wide is ~4 px: row 38 is clear
    px = _blank()
    sk.paint(px, s, [sk.Mark([[0.125, 0.0, 0.375]], width=0.06, color=(0, 0, 0), strength=1.0, soft=0.5)])
    assert px[48, 16, 0] == pytest.approx(0.0, abs=1e-3) and px[48, 30, 0] == pytest.approx(0.8)


def test_paint_breaks_a_stroke_across_a_seam():
    # two squares side by side in 3D whose UVs are apart: a line across both must not streak across the texture
    a = _quad(0.5, 0.25)
    b = sk.Surface(a.tris + np.array([0.5, 0, 0]), a.uvs + np.array([0.75, 0.0]))
    s = sk.Surface(np.concatenate([a.tris, b.tris]), np.concatenate([a.uvs, b.uvs]))
    px = _blank()
    sk.paint(px, s, [sk.Mark([[0.3, 0, 0.1], [0.7, 0, 0.1]], width=0.1, color=(0, 0, 0), strength=1.0,
                             taper=(1, 1))], seam=0.1)
    assert px[3, 32, 0] == pytest.approx(0.8)               # the gap between the islands untouched (row 3: v 0.05)
    assert px[3, 12, 0] < 0.5 and px[3, 52, 0] < 0.5


def test_fill_paints_a_triangle_and_a_little_round_it():
    px = _blank()
    sk.fill(px, [[[0.25, 0.25], [0.75, 0.25], [0.25, 0.75]]], (0.1, 0.1, 0.1), grow=1.5)
    assert px[20, 20, 0] == pytest.approx(0.1)
    assert px[16, 30, 0] == pytest.approx(0.1)             # on its bottom edge (row 16)
    assert px[14, 30, 0] == pytest.approx(0.8)             # well below it
    assert px[45, 45, 0] == pytest.approx(0.8)             # past its long side


def test_replace_and_lighten():
    px = _blank(8, 8, 0.2)
    px[3, 3, :3] = 0.95
    sk.replace(px, sk.luma(px) > 0.5, (0.2, 0.2, 0.2), grow=1)
    assert px[3, 3, :3] == pytest.approx([0.2] * 3) and px[3, 3, 3] == 1.0
    px = _blank(2, 2, 0.5)
    px[..., 0] = 0.9
    sk.lighten(px, saturation=0.0)
    assert px[0, 0, 0] == pytest.approx(px[0, 0, 1]) == pytest.approx(px[0, 0, 2])
    sk.lighten(px, lift=1.0)
    assert px[0, 0, :3] == pytest.approx([1.0] * 3)


def test_box_blur_keeps_the_mean_and_smooths_a_step():
    a = np.zeros((40, 40), np.float32)
    a[:, 20:] = 1.0
    b = sk.box_blur(a, 3)
    assert b.mean() == pytest.approx(a.mean(), abs=0.01)
    row = b[20]
    assert np.all(np.diff(row) >= -1e-6) and 0.0 < row[19] < 1.0 and row[0] == 0.0 and row[-1] == 1.0


def test_soften_turns_a_zigzag_edge_into_a_smooth_soft_one():
    h, w = 64, 64
    px = _blank(h, w)
    px[..., :3] = (0.5, 0.5, 0.5)
    ys, xs = np.mgrid[0:h, 0:w]
    teeth = 30 + 6 * np.abs(((xs % 8) - 4) / 4.0)        # the edge zigzags between rows 30 and 36
    px[..., 3] = (ys < teeth).astype(np.float32)
    px[ys >= teeth] = (1.0, 1.0, 1.0, 0.0)                 # VRoid's clear part: white
    sk.soften(px, radius=4, feather=0.3, bleed=6)
    edge = [np.argmax(px[:, x, 3] < 0.5) for x in range(8, 56)]
    assert max(edge) - min(edge) <= 1                       # no teeth left
    assert 0.05 < px[edge[0], 8, 3] < 0.95 or 0.05 < px[edge[0] - 1, 8, 3] < 0.95   # soft, not cut
    assert px[34, 20, :3] == pytest.approx([0.5] * 3, abs=0.02)   # the hair's colour, not white


def test_strands_reach_across_the_edge():
    h, w = 64, 64
    px = _blank(h, w)
    px[..., 3] = np.clip((40 - np.mgrid[0:h, 0:w][0]) / 8.0, 0, 1)    # solid below row 32, clear above row 40
    before = px[..., 3].copy()
    sk.strands(px, 20, 10.0, 1.5, rng=np.random.default_rng(1))
    grew = px[..., 3] - before
    assert grew.max() > 0.3 and (grew[:30] <= 1e-6).all()   # only on and past the edge, nothing deep inside


def _face_points():
    rng = np.random.default_rng(0)
    eye = []
    for s in (1, -1):
        for a in np.linspace(0, 2 * math.pi, 24, endpoint=False):
            eye.append((s * (0.04 + 0.022 * math.cos(a)), -0.05, 1.33 + 0.012 * math.sin(a)))
    brow = [(s * x, -0.06, 1.36) for s in (1, -1) for x in (0.02, 0.04, 0.06)]
    mouth = [(x, -0.06, z) for x in np.linspace(-0.022, 0.022, 9) for z in (1.27, 1.28)]
    skin = rng.uniform((-0.1, -0.05, 1.24), (0.1, 0.05, 1.46), (3000, 3))
    skin = np.concatenate([skin, [(0.0, -0.08, 1.3), (0.0, -0.045, 1.243), (0.0, 0.04, 1.2)]])
    return eye, brow, mouth, skin


def test_landmarks_of_a_face():
    lm = sk.landmarks(*_face_points())
    assert lm["left"]["outer"][0] == pytest.approx(0.062) and lm["left"]["inner"][0] == pytest.approx(0.018)
    assert lm["right"]["outer"][0] == pytest.approx(-0.062)
    assert lm["left"]["top"][2] == pytest.approx(1.342) and lm["left"]["bottom"][2] == pytest.approx(1.318)
    assert lm["left"]["middle"] == pytest.approx([0.04, -0.05, 1.33])
    assert lm["left"]["brow_inner"][0] == pytest.approx(0.02) and lm["right"]["brow_outer"][0] == pytest.approx(-0.06)
    assert lm["nose"] == pytest.approx([0.0, -0.08, 1.3])
    assert lm["mouth_left"][0] == pytest.approx(0.022) and lm["mouth_right"][0] == pytest.approx(-0.022)
    assert lm["chin"] == pytest.approx([0.0, -0.045, 1.243])      # not the neck behind it


def test_displace_eases_to_nothing_at_the_radius():
    co = np.array([[0, 0, 0], [0.5, 0, 0], [1.0, 0, 0], [2.0, 0, 0]])
    off = sk.displace(co, [((0, 0, 0), (0, 0, -0.1), 1.0)])
    assert off[0] == pytest.approx([0, 0, -0.1]) and off[2] == pytest.approx([0, 0, 0]) and off[3] == pytest.approx([0, 0, 0])
    assert -0.1 < off[1][2] < 0
    two = sk.displace(co, [((0, 0, 0), (0, 0, -0.1), 1.0), ((0, 0, 0), (0.1, 0, 0), 1.0)])
    assert two[0] == pytest.approx([0.1, 0, -0.1])


def test_cast_finds_the_first_surface_along_a_line():
    front = [[0, 0, 0], [1, 0, 0], [0, 0, 1.0]]
    back = [[0, 0.5, 0], [1, 0.5, 0], [0, 0.5, 1.0]]
    idx, bary, ok = sk.cast([[0.2, -3.0, 0.3], [0.2, 0.2, 0.3], [5.0, 0.0, 5.0]], (0, 1, 0), [back, front])
    assert ok.tolist() == [True, True, False]
    assert idx[0] == 1 and idx[1] == 1               # from far back along the line: the front one first
    assert bary[0] == pytest.approx([0.5, 0.2, 0.3])


def test_project_along_a_view_reaches_a_slanted_side():
    # a face turning away: a mark placed on its front view lands where the view's line meets it, not on the
    # nearest place to the point
    side = sk.Surface([[[0, 0, 0], [1, 1, 0], [1, 1, 1.0]], [[0, 0, 0], [1, 1, 1], [0, 0, 1.0]]],
                      [[[0, 0], [1, 0], [1, 1]], [[0, 0], [1, 1], [0, 1]]])
    p = [[0.8, -1.0, 0.5]]
    uv_view, _ = side.project(p, along=(0, 1, 0))
    uv_near, _ = side.project(p)
    assert uv_view[0] == pytest.approx([0.8, 0.5]) and uv_near[0][0] < 0.2


def test_drape_falls_from_the_widest_reach_above():
    zs = [0.0, 0.5, 1.0, 1.5]
    # a body narrow at the waist (z 0.5), wide at the shoulders (z 1.0), the head above narrow again
    radii = np.array([[0.15] * 8, [0.1] * 8, [0.2] * 8, [0.05] * 8])
    radii[2, 2] = 0.3                                     # an arm out toward +y at shoulder height
    d = sk.Drape(zs, radii)
    assert d(1.5, 0.0) == pytest.approx(0.05)
    assert d(1.0, 0.0) == pytest.approx(0.2)
    assert d(0.5, 0.0) == pytest.approx(0.2)              # the waist under the shoulders: hangs from them
    assert d(0.0, 0.0) == pytest.approx(0.2)              # the hips are narrower than the shoulders
    assert d(0.5, math.pi / 2) == pytest.approx(0.3)      # under the arm
    assert d(0.75, 0.0) == pytest.approx(0.2)
    assert d(1.25, 0.0) == pytest.approx(0.125)           # between shoulder and head: eased
    assert d(1.0, math.pi / 4 * 1.5) == pytest.approx(0.25)   # between two directions
    assert d(1.0, -2 * math.pi) == pytest.approx(d(1.0, 0.0))
