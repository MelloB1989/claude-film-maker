# The bpy-free halves of the anime look: an outline's on-screen width and its ink tone (lib/outline.py), and the
# shadow hues of an anime palette (toon.shadow_hue). Expected values are worked from the definitions.
import colorsys

import pytest

from lib import outline, toon


def lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def test_a_pixel_is_the_gate_over_the_lens_over_the_width_per_metre_away():
    # 36 mm across a 30 mm lens at 1920 px: 0.000625 m per px per metre; 2.2 px at 7 m is about 9.6 mm
    s = outline.pixel_scale(30.0, 36.0, 1920)
    assert s == pytest.approx(36.0 / (30.0 * 1920))
    assert 2.2 * s * 7.0 == pytest.approx(0.009625)
    assert outline.pixel_scale(85.0) < outline.pixel_scale(50.0)     # a longer lens: fewer metres a pixel


def test_an_ink_tone_keeps_the_hue_darker_and_more_saturated():
    red = (0.66, 0.05, 0.03)
    ink = outline.ink_tone(red)
    h0, s0, _ = colorsys.rgb_to_hsv(*red)
    h1, s1, v1 = colorsys.rgb_to_hsv(*ink)
    assert h1 == pytest.approx(h0, abs=1e-6)
    assert v1 == pytest.approx(0.012)
    assert s1 >= s0
    # a dark grey's ink is a near-neutral dark, no darker than it was
    grey = (0.009, 0.009, 0.012)
    g = outline.ink_tone(grey)
    assert max(g) <= max(grey) + 1e-12
    assert colorsys.rgb_to_hsv(*g)[1] <= colorsys.rgb_to_hsv(*grey)[1]


def test_shadow_hues_warm_skin_cool_cloth_and_keep_their_brightness():
    skin_lit, skin_shade = (0.42, 0.28, 0.19), (0.17, 0.1, 0.07)
    cloth_lit, cloth_shade = (0.085, 0.09, 0.105), (0.018, 0.019, 0.025)
    s = toon.shadow_hue(skin_lit, skin_shade, 1.0)
    c = toon.shadow_hue(cloth_lit, cloth_shade, 1.0)
    assert s[0] / s[2] > skin_shade[0] / skin_shade[2]                 # redder
    assert c[2] / c[0] > cloth_shade[2] / cloth_shade[0]               # bluer
    assert lum(s) == pytest.approx(lum(skin_shade), rel=1e-6)
    assert lum(c) == pytest.approx(lum(cloth_shade), rel=1e-6)
    assert toon.shadow_hue(skin_lit, skin_shade, 0.0) == skin_shade    # off: as given
