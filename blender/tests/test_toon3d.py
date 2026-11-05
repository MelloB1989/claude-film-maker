import math

import numpy as np
import pytest

from lib import toon3d
from lib.toon3d import Tone


def test_smoothstep_is_blenders_smoothstep():
    assert toon3d.smoothstep(0.0, 1.0, -0.5) == 0.0 and toon3d.smoothstep(0.0, 1.0, 1.5) == 1.0
    assert toon3d.smoothstep(0.0, 1.0, 0.5) == pytest.approx(0.5)
    assert toon3d.smoothstep(-0.1, 0.1, 0.05) == pytest.approx(0.84375)
    assert toon3d.smoothstep(0.2, 0.2, 0.2) == 1.0 and toon3d.smoothstep(0.2, 0.2, 0.1) == 0.0


def test_facing_drops_where_the_key_is_shadowed_and_in_creases():
    t = Tone(cast=-0.3, bias=0.0, crease=0.4)
    # seen by the key: the facing as it is
    assert toon3d.facing(0.7, 1.0, t) == pytest.approx(0.7)
    # in a cast shadow: down to the tone's cast, never up
    assert toon3d.facing(0.7, 0.0, t) == pytest.approx(-0.3)
    assert toon3d.facing(-0.6, 0.0, t) == pytest.approx(-0.6)
    assert toon3d.facing(0.7, 0.5, t) == pytest.approx(0.2)
    # occluded: lowered by the crease; biased
    assert toon3d.facing(0.7, 1.0, t, occlusion=0.5) == pytest.approx(0.5)
    assert toon3d.facing(0.2, 1.0, Tone(bias=0.15)) == pytest.approx(0.35)


def test_shades_band_the_light_into_base_first_and_deep():
    t = Tone(shade=(0.5, 0.5, 0.8), deep=(0.25, 0.25, 0.5), cut=0.0, soft=0.1, deep_cut=-0.5, deep_soft=0.1)
    c = (0.8, 0.6, 0.4)
    assert toon3d.shades(0.9, c, t) == pytest.approx(c)
    assert toon3d.shades(-0.25, c, t) == pytest.approx((0.4, 0.3, 0.32))
    assert toon3d.shades(-0.9, c, t) == pytest.approx((0.2, 0.15, 0.2))
    # a soft edge: halfway at the cut
    mid = toon3d.shades(0.0, c, t)
    assert mid == pytest.approx(tuple((a + b) / 2 for a, b in zip(c, (0.4, 0.3, 0.32))))
    # the tone's grade on the base, and an unshaded part (eyes) the same lit or not
    assert toon3d.shades(0.9, c, Tone(lit=(0.5, 1.0, 1.0))) == pytest.approx((0.4, 0.6, 0.4))
    flat = Tone(shaded=False)
    assert toon3d.shades(-1.0, c, flat) == toon3d.shades(1.0, c, flat) == pytest.approx(c)


def test_a_flash_whitens_the_lit_side_and_sinks_the_shade():
    t = Tone(flash=0.8, sink=0.3)
    c, white = (0.4, 0.3, 0.3), (0.85, 0.9, 1.0)
    lit = toon3d.shades(1.0, c, t, flash=1.0, flash_color=white)
    assert lit == pytest.approx(tuple(a + (w - a) * 0.8 for a, w in zip(c, white)))
    shade = toon3d.shades(-0.3, c, t)
    assert toon3d.shades(-0.3, c, t, flash=1.0) == pytest.approx(tuple(s * 0.7 for s in shade))
    assert toon3d.shades(1.0, c, t, flash=0.0) == pytest.approx(c)


def test_lines_are_a_dark_tint_of_their_surface_never_black():
    t = Tone(line_mul=0.2, line_add=(0.005, 0.006, 0.015))
    assert toon3d.line((0.5, 0.4, 0.3), t) == pytest.approx((0.105, 0.086, 0.075))
    black = toon3d.line((0.0, 0.0, 0.0), t)
    assert black == pytest.approx((0.005, 0.006, 0.015)) and black[2] > black[0]


@pytest.mark.parametrize("toward", [(1.0, -0.3, 0.8), (-1.0, 0.35, 0.75), (0.0, 0.0, 1.0), (0.2, 0.1, -1.0),
                                    (0.0, -1.0, 0.0), (3.0, 4.0, 0.0)])
def test_a_sun_aimed_from_a_direction_shines_from_it(toward):
    e = toon3d.toward_euler(toward)
    want = np.asarray(toward, float) / np.linalg.norm(toward)
    assert toon3d.light_axis(e) == pytest.approx(tuple(want), abs=1e-9)
    # the drivers' expressions are the same function of the angles
    names = {"x": e[0], "y": e[1], "z": e[2], "cos": math.cos, "sin": math.sin}
    assert tuple(eval(ex, {}, names) for ex in toon3d.AXIS_EXPR) == pytest.approx(toon3d.light_axis(e))


def test_a_sun_keeps_its_up_toward_the_sky():
    # its +Y (the to_track_quat('-Z', 'Y') up) leans to world up, so a key never rolls
    rx, ry, rz = toon3d.toward_euler((1.0, -0.3, 0.8))
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    y_axis = (cz * sy * sx - sz * cx, sz * sy * sx + cz * cx, cy * sx)
    assert y_axis[2] > 0.5
    with pytest.raises(ValueError):
        toon3d.toward_euler((0.0, 0.0, 0.0))
