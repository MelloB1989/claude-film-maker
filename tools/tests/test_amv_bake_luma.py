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
