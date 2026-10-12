import pytest

from lib import materials, theme

# Materials colour by palette role through the theme in use (lib/theme.py; test_theme.py covers the resolution).


def test_linear_takes_roles_of_the_theme_in_use(noir):
    assert materials.linear("fg") == pytest.approx((0.846873, 0.799103, 0.822786), abs=1e-6)  # noir's #ede7ea
    assert materials.linear("accent") == materials.linear("#c22b45")
    assert materials.linear("accent2") == pytest.approx(materials.linear("#4aad63"))


def test_linear_rejects_what_is_not_a_role_or_a_hex(noir):
    with pytest.raises(KeyError, match="teal"):
        materials.linear("teal")
    with pytest.raises(theme.ThemeError):
        materials.linear("#12345")
