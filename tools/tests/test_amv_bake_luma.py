"""The calibration knobs added to layerfx for `bake_luma` keep the shipped behaviour at their defaults."""
import numpy as np

from filmtools.amv import bake_luma, layerfx as fx


def plate():
    rng = np.random.default_rng(5)
    img = rng.random((54, 96, 3)).astype(np.float32) * 0.5
    img[20:24, 40:44] = 1.0
    return img


def test_defaults_are_the_calibrated_values():
    assert fx.RFB_BRIGHT_MIX == 1.0 and fx.DBLUR_SCALE == 1.0 and fx.GLOW_GAIN == 1.0 and fx.GLOW_PER_CHANNEL == 0
    assert fx.RFB_SELECT == "soft" and fx.RFB_BETA == 12.0 and fx.RFB_LENGTH == 0.07


def test_bright_mix_between_average_and_max(monkeypatch):
    img = plate()
    c = (48.0, 27.0)
    mx = fx.radial_fast_blur(img, 50, c, "brightest")
    monkeypatch.setattr(fx, "RFB_BRIGHT_MIX", 0.5)
    mid = fx.radial_fast_blur(img, 50, c, "brightest")
    avg = fx.radial_fast_blur(img, 50, c, "standard")
    assert mx.mean() >= mid.mean() >= avg.mean()
    assert np.allclose(mid, 0.5 * mx + 0.5 * avg, atol=1e-5)


def test_dblur_scale_lengthens_the_blur(monkeypatch):
    img = plate()
    a = fx.directional_blur(img, 90, 4)
    monkeypatch.setattr(fx, "DBLUR_SCALE", 2.0)
    assert np.allclose(fx.directional_blur(img, 90, 2), a, atol=1e-6)


def test_glow_per_channel_lights_a_red_face(monkeypatch):
    red = np.zeros((40, 40, 3), np.float32)
    red[..., 0] = 0.8
    luma_on = fx.glow(red, 55, 4, 0.6)
    monkeypatch.setattr(fx, "GLOW_PER_CHANNEL", 1)
    ch_on = fx.glow(red, 55, 4, 0.6)
    assert np.allclose(luma_on, red) and ch_on[..., 0].mean() > red[..., 0].mean()   # luma 0.17 < 0.55: no glow; R alone glows


def test_override_parser(monkeypatch):
    monkeypatch.setattr(fx, "RFB_LENGTH", 0.12)
    bake_luma.apply_overrides(["RFB_LENGTH=0.2"])
    assert fx.RFB_LENGTH == 0.2


def test_parse_frames():
    assert bake_luma.parse_frames("3-5,9") == [3, 4, 5, 9]


def test_shot_rfb_accessors_default_to_the_globals():
    from filmtools.amv import plan as planmod
    s = planmod.Shot(0, {"name": "x", "a": 0, "b": 5, "end": 5, "src": "c"})
    assert s.rfb_len == planmod.RFB_LEN == fx.RFB_LENGTH and s.rfb_mix == planmod.RFB_MIX == 1.0
    assert s.rfb_beta == planmod.RFB_BETA == fx.RFB_BETA
    s = planmod.Shot(0, {"name": "x", "a": 0, "b": 5, "end": 5, "src": "c", "rfb_len": 0.7, "rfb_mix": 0.5, "rfb_beta": 30})
    assert s.rfb_len == 0.7 and s.rfb_mix == 0.5 and s.rfb_beta == 30.0


def test_radial_blur_args_override_the_globals():
    img = plate()
    assert np.allclose(fx.radial_fast_blur(img, 40, (48, 27)), fx.radial_fast_blur(img, 40, (48, 27), length=fx.RFB_LENGTH, mix=1.0))
    assert not np.allclose(fx.radial_fast_blur(img, 40, (48, 27)), fx.radial_fast_blur(img, 40, (48, 27), length=0.5))


def test_the_plan_fields_are_read_by_bake(monkeypatch):
    from filmtools.amv import bake, plan as planmod
    seen = {}
    monkeypatch.setattr(bake.fx, "radial_fast_blur", lambda img, a, c, mode, length=None, mix=None, beta=None: seen.update(l=length, m=mix, b=beta) or img)
    monkeypatch.setattr(bake, "load_plate", lambda *a, **k: np.zeros((54, 96, 3), np.float32))
    raw = {"name": "x", "a": 0, "b": 5, "end": 5, "src": "c", "remap": [0.0] * 5, "px": [960] * 5, "py": [540] * 5, "s": [100] * 5,
           "rz": [0] * 5, "rfb": [[0, 40, 960, 540]], "rfb_len": 0.7, "rfb_beta": 33}
    shot = planmod.Shot(0, raw)
    bake.bake_frame(planmod.Plan(raw={"titles": []}, root=None), shot, 0, 0.05)
    assert seen == {"l": 0.7, "m": None, "b": 33}


def _red_blue():
    img = np.zeros((40, 96, 3), np.float32)
    img[:, :48, 0] = 0.6     # a red half (luma 0.13) ...
    img[:, 48:, 2] = 0.6     # ... next to a blue half (luma 0.04), rays running across the seam from the centre
    return img


def test_brightest_keeps_a_whole_pixel_instead_of_a_magenta_channel_mix(monkeypatch):
    img, c = _red_blue(), (0.0, 20.0)
    monkeypatch.setattr(fx, "RFB_SELECT", "channel")
    chan = fx.radial_fast_blur(img, 100, c, "brightest", length=0.5)
    monkeypatch.setattr(fx, "RFB_SELECT", "soft")
    soft = fx.radial_fast_blur(img, 100, c, "brightest", length=0.5)
    magenta = lambda x: np.minimum(x[..., 0], x[..., 2]).max()
    assert magenta(chan) > 0.5 and magenta(soft) < magenta(chan) - 0.15


def test_soft_brightest_is_finite_and_bounded_at_any_beta():
    img = plate()
    for beta in (0.0, 8.0, 60.0, 500.0):
        out = fx.radial_fast_blur(img, 60, (48, 27), "brightest", beta=beta)
        assert np.isfinite(out).all() and out.min() >= 0 and out.max() <= 1.0 + 1e-5
    assert np.allclose(fx.radial_fast_blur(img, 60, (48, 27), "brightest", beta=0.0),
                       fx.radial_fast_blur(img, 60, (48, 27), "standard"), atol=1e-4)    # beta 0 = the plain average
