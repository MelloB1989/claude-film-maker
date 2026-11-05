import pytest

from lib import satsuei


def test_shift_brings_each_pixel_its_width_toward_the_light():
    # a light to the left: the cast shifted right, so its left edge is what the shift leaves
    assert satsuei.shift((-1, 0), 0.01, (1920, 1080)) == pytest.approx((10.8, 0.0))
    x, y = satsuei.shift((3, 4), 0.01, (1000, 500))
    assert (x, y) == pytest.approx((-3.0, -4.0))
    with pytest.raises(ValueError):
        satsuei.shift((0, 0), 0.01, (10, 10))


def test_para_axis_runs_zero_to_one_between_its_points():
    origin, ax = satsuei.axis((0.2, 0.9), (0.6, 0.1))
    for p, want in (((0.2, 0.9), 0.0), ((0.6, 0.1), 1.0), ((0.4, 0.5), 0.5)):
        t = (p[0] - origin[0]) * ax[0] + (p[1] - origin[1]) * ax[1]
        assert t == pytest.approx(want)
    with pytest.raises(ValueError):
        satsuei.axis((0.5, 0.5), (0.5, 0.5))


def test_default_look_changes_nothing():
    v = satsuei.values(satsuei.Look(), (960, 540))
    assert v[("sat", 2)] == 1.0 and v[("gain", 7)] == (1.0, 1.0, 1.0, 1.0)
    assert v[("haze", 0)] == 0.0 and v[("para_amount", 1)] == 0.0 and v[("wrap", 0)] == 0.0
    assert v[("flash", 0)] == 0.0
    assert all(v[(f"rim{i}", 0)] == 0.0 for i in range(satsuei.RIMS))


def test_values_pad_the_rims_scale_them_to_the_render_and_clamp():
    rim = satsuei.Rim(toward=(0, 1), color=(1.0, 0.5, 0.2), strength=1.5, width=0.01, soft=0.5)
    look = satsuei.Look(rims=(rim,), haze_amount=1.4, para_amount=-0.2)
    v = satsuei.values(look, (2560, 1440))
    assert v[("rim0_shift", 1)] == pytest.approx(0.0) and v[("rim0_shift", 2)] == pytest.approx(-14.4)
    assert v[("rim0_blur", 1)] == pytest.approx((7.2, 7.2))
    assert v[("rim0", 0)] == 1.5 and v[("rim0_color", 7)] == (1.0, 0.5, 0.2, 1.0)
    assert v[("rim1", 0)] == 0.0 and v[("rim2", 0)] == 0.0
    assert v[("haze", 0)] == 1.0 and v[("para_amount", 1)] == 0.0
    with pytest.raises(ValueError):
        satsuei.values(satsuei.Look(rims=(rim,) * (satsuei.RIMS + 1)), (10, 10))
