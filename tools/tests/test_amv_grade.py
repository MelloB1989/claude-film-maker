"""The numpy twin of the AMV grade: properties of each op, no Blender needed (the node group is tested in blender/tests)."""
import numpy as np

from filmtools.amv import grade_np as G

NEUTRAL = {"sharpen_amount": 0, "colorista": 0, "vig_amount": 0, "contrast": 0, "highlights": 0, "shadows": 0,
           "whites": 0, "blacks": 0, "saturation": 100, "bc_brightness": 0, "bc_contrast": 0, "cb": [0] * 9,
           "glow_intensity": 0}


def ramp(n=64):
    return np.linspace(0, 1, n, dtype=np.float32)[None, :, None].repeat(3, 2).repeat(8, 0)


def test_neutral_params_are_identity():
    x = np.random.default_rng(0).random((20, 30, 3)).astype(np.float32)
    # preserve-luminosity colour balance with zero offsets is the identity, as is every other neutral op
    assert np.abs(G.grade(x, NEUTRAL) - x).max() < 2e-3


def test_params_overrides_and_unknown_keys():
    p = G.params({"saturation": 120, "cb": [1] * 9, "nonsense": 3})
    assert p["saturation"] == 120 and p["cb"] == [1] * 9 and "nonsense" not in p
    assert G.params()["blacks"] == -12 and G.params()["saturation"] == 150  # the merge overrides, not the .ffx's 0 / 170


def test_output_is_clipped_and_finite():
    x = np.random.default_rng(1).random((24, 40, 3)).astype(np.float32) * 1.4 - 0.2
    y = G.grade(x)
    assert np.isfinite(y).all() and y.min() >= 0 and y.max() <= 1


def test_gaussian_matches_blender_convention():
    k = G.gauss_kernel(10)
    assert len(k) == 21 and abs(k.sum() - 1) < 1e-6
    sigma = np.sqrt((k * (np.arange(21) - 10) ** 2).sum())
    assert abs(sigma - 3.30) < 0.05           # measured on Blender's Blur node (size 10 -> 3.30)
    flat = np.full((16, 16, 3), 0.4, np.float32)
    assert np.abs(G.blur(flat, 6) - 0.4).max() < 1e-6   # edges extended, not darkened


def test_vignette_darkens_corners_not_centre():
    g = G.vignette_gain(54, 96, 0.345, 0.5)[..., 0]
    assert g[27, 48] == 1.0 and g[0, 0] < 0.7 and g[0, 0] < g[0, 48]


def test_lumetri_opens_shadows_and_keeps_black_and_white_ends_ordered():
    y = G.lumetri_tone(ramp(), G.params())[0, :, 0]
    x = ramp()[0, :, 0]
    assert y[16] > x[16]                       # shadows +45 lift the low mids
    assert (np.diff(y) >= -1e-6).all()         # still monotone
    assert y[0] < 0.02 and y[-1] > 0.98


def test_saturation_scales_chroma_not_luma():
    x = np.array([[[0.8, 0.4, 0.3]]], np.float32)
    y = G.saturate(x, 150)
    assert abs(G.luma(y)[0, 0] - G.luma(x)[0, 0]) < 1e-5 or y.max() >= 0.999
    assert (y[0, 0, 0] - y[0, 0, 2]) > (x[0, 0, 0] - x[0, 0, 2])


def test_color_balance_preserves_luminosity():
    x = np.random.default_rng(2).random((16, 16, 3)).astype(np.float32) * 0.8 + 0.1
    y = G.color_balance(x, [-10, 7, 10, -2, 4, -3, 12, 5, -12])
    assert np.abs(G.luma(y) - G.luma(x)).max() < 5e-3
    assert np.abs(y - x).max() > 1e-3


def test_glow_only_adds_and_only_near_bright_pixels():
    x = np.full((40, 80, 3), 0.3, np.float32)
    x[:, 60:] = 1.0
    y = G.glow(x, 0.84, 6, 0.25)
    assert (y >= x - 1e-6).all()
    assert abs(y[:, 0] - x[:, 0]).max() < 1e-4          # far from the bright area: untouched
    assert y[20, 58, 0] > x[20, 58, 0] + 0.01            # next to it: glow


def test_linear_wrapper_round_trips_neutral():
    x = np.random.default_rng(4).random((8, 8, 3)).astype(np.float32)
    assert np.abs(G.grade_linear(x, NEUTRAL) - x).max() < 2e-3


def test_lab_of_white_and_black():
    lab = G.rgb_to_lab(np.array([[[1, 1, 1], [0, 0, 0]]], np.float32))
    assert abs(lab[0, 0, 0] - 100) < 0.1 and abs(lab[0, 1, 0]) < 0.1 and abs(lab[0, 0, 1]) < 0.1


def test_trim_exposure_is_in_linear_light():
    x = np.full((2, 2, 3), 0.5, np.float32)
    y = G.trim(x, 1.0, 0)
    assert abs(G.srgb_to_linear(y)[0, 0, 0] - 2 * G.srgb_to_linear(x)[0, 0, 0]) < 1e-3


def test_rolloff_whitens_overexposure_and_keeps_in_range_pixels():
    x = np.array([[[0.4, 0.3, 0.2], [3.7, 1.9, 0.37], [1.0, 0.5, 0.1]]], np.float32)
    y = G.rolloff_in(x, 1.0)
    assert np.allclose(y[0, 0], x[0, 0]) and np.allclose(y[0, 2], x[0, 2])      # m <= 1: untouched
    assert y[0, 1].min() > 0.7 and y[0, 1].max() <= 1.0                          # blown: pale, not a saturated clip
    assert (y[0, 1, 0] - y[0, 1, 2]) < (1.0 - 0.37)                              # less chroma than the plain clip
    assert np.allclose(G.rolloff_in(x, 0.0), np.clip(x, 0, 1))                   # strength 0 = AE's clip
