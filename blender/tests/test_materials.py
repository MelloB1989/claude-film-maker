import pytest

from lib import materials

# Linear values from the sRGB formula by hand (app/src/engine/look.test.ts has bone's red as 0.846873 too).


def test_linear_converts_srgb_hex_to_linear_light():
    assert materials.linear("#ede7ea") == pytest.approx((0.846873, 0.799103, 0.822786), abs=1e-6)
    assert materials.linear("#c22b45") == pytest.approx((0.539479, 0.024158, 0.059511), abs=1e-6)


def test_linear_uses_the_linear_toe_for_dark_values():
    assert materials.linear("#0a0a0a") == pytest.approx((0.0030353,) * 3, abs=1e-7)


def test_linear_takes_palette_names():
    assert materials.linear("bone") == materials.linear("#ede7ea")
    assert materials.linear("blood") == materials.linear("#c22b45")
    assert materials.linear("moss") == pytest.approx(materials.linear("#4aad63"))
    with pytest.raises(KeyError, match="teal"):
        materials.linear("teal")
