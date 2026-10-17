"""Unit tests of the AE effect stand-ins (tools/filmtools/amv/layerfx.py): identity at zero, symmetry, known values."""
import numpy as np
import pytest

from filmtools.amv import layerfx as fx
from filmtools.amv import plan as planmod

rng = np.random.default_rng(1)


@pytest.fixture(autouse=True)
def full_length_rfb(monkeypatch):
    """The RFB tests are written for ray length = amount % of the distance, whatever the calibrated constant is."""
    monkeypatch.setattr(fx, "RFB_LENGTH", 1.0)


def noise(h=64, w=96, c=3):
    return rng.random((h, w, c), dtype=np.float32)


def test_exposure_identity_and_stops():
    img = noise()
    assert np.array_equal(fx.exposure(img, 0), img)
    lin = fx.srgb_to_linear(np.full((2, 2, 3), 0.2, np.float32))
    out = fx.exposure(np.full((2, 2, 3), 0.2, np.float32), 1.0)
    np.testing.assert_allclose(fx.srgb_to_linear(out), lin * 2, rtol=1e-4)
    assert fx.exposure(np.ones((2, 2, 3), np.float32), 1.0).max() == 1.0      # clips
    assert fx.exposure(img, -2).mean() < img.mean()


def test_exposure_keeps_alpha():
    img = noise(c=4)
    np.testing.assert_array_equal(fx.exposure(img, 0.7)[..., 3], img[..., 3])


def test_hue_sat():
    img = noise()
    assert np.array_equal(fx.hue_sat_master(img, 0), img)
    grey = fx.hue_sat_master(img, -100)
    assert np.ptp(grey, axis=2).max() < 1e-5
    mid = fx.hue_sat_master(img, -12)
    # saturation (max - min at fixed lightness) shrinks by exactly 12 %
    d0, d1 = np.ptp(img, axis=2), np.ptp(mid, axis=2)
    np.testing.assert_allclose(d1, d0 * 0.88, atol=1e-5)
    L0, L1 = (img.max(2) + img.min(2)) / 2, (mid.max(2) + mid.min(2)) / 2
    np.testing.assert_allclose(L0, L1, atol=1e-5)
    boosted = fx.hue_sat_master(img, 50)
    assert np.ptp(boosted, axis=2).mean() > np.ptp(img, axis=2).mean()
    g = np.full((4, 4, 3), 0.4, np.float32)
    np.testing.assert_allclose(fx.hue_sat_master(g, 80), g)


def test_motion_tile_canvas_matches_plan_and_mirrors():
    img = np.arange(6 * 10 * 3, dtype=np.float32).reshape(6, 10, 3) / 180
    out = fx.motion_tile(img, 200, 200)
    assert out.shape[:2] == (12, 20)
    cw, ch, ox, oy = fx.tile_canvas(10, 6, 200, 200)
    assert (ox, oy) == (5, 3)
    np.testing.assert_array_equal(out[oy:oy + 6, ox:ox + 10], img)
    # mirrored: the pixel left of the cell is the cell's first column, the one before is the second
    np.testing.assert_array_equal(out[oy:oy + 6, ox - 1], img[:, 0])
    np.testing.assert_array_equal(out[oy:oy + 6, ox - 2], img[:, 1])
    np.testing.assert_array_equal(out[oy - 1, ox:ox + 10], img[0])
    assert fx.motion_tile(img, 100, 100) is img


@pytest.mark.parametrize("tile", [(110, 110), (135, 110), (130, 155), (155, 245), (100, 100)])
def test_canvas_round_trips_with_shot(tile):
    shot = planmod.Shot(0, {"name": "x", "tile": list(tile)})
    cw, ch, ox, oy = shot.canvas
    assert fx.tile_canvas(planmod.W, planmod.H, *tile) == shot.canvas
    img = np.zeros((16, 32, 3), np.float32)
    out = fx.motion_tile(img, *tile)
    assert out.shape[:2] == fx.tile_canvas(32, 16, *tile)[1::-1]


def test_rfb_identity_and_centre_fixed():
    img = noise()
    assert fx.radial_fast_blur(img, 0, (48, 32)) is img
    flat = np.full((64, 96, 3), 0.37, np.float32)
    for mode in ("standard", "brightest", "darkest"):
        np.testing.assert_allclose(fx.radial_fast_blur(flat, 40, (48.0, 32.0), mode)[8:-8, 8:-8], 0.37, atol=1e-5)
    # a ramp that is constant along rays stays put at the centre pixels, whatever the blur
    ys, xs = np.mgrid[0:64, 0:96].astype(np.float32)
    ramp = np.repeat((xs / 96)[..., None], 3, axis=2)
    out = fx.radial_fast_blur(ramp, 40, (48.0, 32.0), "standard")
    np.testing.assert_allclose(out[31:33, 47:49], ramp[31:33, 47:49], atol=0.03)


def test_rfb_symmetry_and_modes():
    img = np.zeros((65, 65, 3), np.float32)
    img[32, 52] = 1.0                                           # one bright pixel right of centre
    c = (32.5, 32.5)
    b = fx.radial_fast_blur(img, 40, c, "brightest")
    s = fx.radial_fast_blur(img, 40, c, "standard")
    # a bright point smears along the ray (the row) and nowhere else
    assert b[32].max() > 0.5 and b[:25].max() < 0.05
    assert b.max() >= s.max()
    # standard conserves little: it dims; darkest of a dark image with one bright point removes it
    assert fx.radial_fast_blur(img, 40, c, "darkest").max() < 0.05
    # 90-degree symmetry: rotating input and centre rotates output
    rot = np.rot90(img)
    np.testing.assert_allclose(np.rot90(b), fx.radial_fast_blur(rot, 40, c, "brightest"), atol=0.05)


def test_rfb_smooth_no_ghosts():
    img = np.zeros((101, 401, 3), np.float32)
    img[:, 300:303] = 1.0
    out = fx.radial_fast_blur(img, 60, (0.5, 50.5), "standard")[50, :, 0]
    # a line at x = 300 smears outward over x = 300 .. 400 (it reaches pixel p from 0.4 p .. p): a smooth ramp,
    # no zero gaps and no jumps between neighbours (stepped ghost copies would show as steps)
    span = out[301:400]
    assert span.min() > 0.0
    assert np.abs(np.diff(span)).max() < 0.05


def test_directional_blur():
    img = np.zeros((9, 41, 3), np.float32)
    img[4, 20] = 1.0
    assert fx.directional_blur(img, 90, 0) is img
    out = fx.directional_blur(img, 90, 10)
    np.testing.assert_allclose(out[4, 14:26].sum(axis=0), 1.0, atol=1e-5)    # energy conserved
    assert out[3].max() == 0                                                  # horizontal only
    np.testing.assert_allclose(out[4, 20 - 3], out[4, 20 + 3], atol=1e-6)     # symmetric
    v = fx.directional_blur(np.pad(img, ((10, 10), (0, 0), (0, 0))), 0, 10)
    assert v[:, 20, 0].sum() == pytest.approx(1.0, abs=1e-5) and v[14, 21].max() == 0     # vertical only
    d = fx.directional_blur(np.pad(img, ((10, 10), (0, 0), (0, 0))), 45, 9)
    assert d.sum() == pytest.approx(1.0 * 3, rel=0.05)


def test_directional_blur_edge_is_transparent():
    img = np.ones((9, 41, 4), np.float32)
    out = fx.directional_blur(img, 90, 20)
    # straight colour stays 1 even where coverage falls off at the border
    assert np.allclose(out[4, :, :3], 1.0, atol=1e-4)
    assert out[4, 0, 3] < 0.7 and out[4, 20, 3] == pytest.approx(1.0)


def test_optics_identity_symmetry_and_bulge():
    img = noise(80, 160)
    assert fx.optics_compensation(img, 0) is img
    grid = np.zeros((81, 161, 3), np.float32)
    grid[::10] = 1
    grid[:, ::10] = 1
    out = fx.optics_compensation(grid, 45, center=(80.5, 40.5))
    # symmetric about the centre
    np.testing.assert_allclose(out[:, :, 0], out[::-1, ::-1, 0], atol=0.2)
    # centre is a fixed point
    assert out[40, 80, 0] == pytest.approx(grid[40, 80, 0], abs=0.3)
    # reverse lens distortion pulls the outskirts in: the image shrinks, so the corner pixel is now transparent
    assert out[0, 0, 3] == 0 and out[40, 80, 3] == 1


def test_optics_radius_is_monotone_and_small_fov_is_small():
    r = np.linspace(0, 500, 50)
    big = fx.optics_source_radius(r, 30, 1080, True)
    small = fx.optics_source_radius(r, 3, 1080, True)
    assert np.all(np.diff(big) > 0) and np.all(big >= r - 1e-6)
    assert np.abs(small - r).max() < np.abs(big - r).max() / 10
    fwd = fx.optics_source_radius(big, 30, 1080, False)
    np.testing.assert_allclose(fwd, r, rtol=1e-3, atol=1e-2)                 # forward undoes reverse


def test_glow():
    img = np.zeros((64, 64, 3), np.float32)
    img[30:34, 30:34] = 1.0
    out = fx.glow(img, 55, 6, 0.6)
    assert np.array_equal(fx.glow(img, 55, 6, 0.0), img)
    assert out[20, 32, 0] > 0 and out[32, 32, 0] == 1.0 and out.max() <= 1.0
    dark = np.full((16, 16, 3), 0.3, np.float32)
    np.testing.assert_allclose(fx.glow(dark, 55, 6, 0.6), dark)               # under the threshold: nothing
    a = fx.glow(np.dstack([img, np.ones((64, 64, 1), np.float32)]), 55, 6, 0.6)
    assert a.shape[2] == 4 and (a[..., 3] == 1).all()


def test_hole_mask():
    a = np.ones((100, 200), np.float32)
    out = fx.hole_mask(a, 100, 50, 30, 20, 0, 0)
    assert out[50, 100] == 0 and out[50, 140] == 1 and out[10, 100] == 1
    grown = fx.hole_mask(a, 100, 50, 30, 20, 0, 10)
    assert (grown == 0).sum() > (out == 0).sum()
    assert grown[50, 100 + 38] == 0 and grown[50, 100 + 42] == 1                # 10 px expansion on the x axis
    soft = fx.hole_mask(a, 100, 50, 30, 20, 20, 0)
    row = soft[50, 100:]
    assert row[0] == 0 and row[60] == 1 and np.all(np.diff(row) >= -1e-6)
    assert 0.2 < soft[50, 100 + 30] < 0.8                                       # edge half way, feather straddles it
    # symmetric about the centre
    np.testing.assert_allclose(soft[50, 100:130], soft[50, 99:69:-1], atol=0.05)
    a2 = np.full((100, 200), 0.5, np.float32)
    assert fx.hole_mask(a2, 100, 50, 30, 20, 0, 0)[10, 10] == 0.5               # keeps existing alpha


def test_premultiply_roundtrip_and_over():
    img = noise(c=4)
    np.testing.assert_allclose(fx.unpremultiply(fx.premultiply(img)), img, atol=1e-4)
    top = np.zeros((2, 2, 4), np.float32)
    top[..., 0] = 1
    top[..., 3] = 0.5
    out = fx.over(top, np.zeros((2, 2, 3), np.float32))
    np.testing.assert_allclose(out[0, 0], [0.5, 0, 0])
