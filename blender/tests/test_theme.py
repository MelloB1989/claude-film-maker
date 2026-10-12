# lib/theme.py: film.json's `theme` resolved as the engine resolves it (palette.ts resolveTheme), and its colours in
# linear light. Linear values come from the sRGB formula by hand (look.test.ts has #ede7ea's red as 0.846873 too).
import json
import re
from pathlib import Path

import pytest

from lib import materials, theme

from conftest import PRESETS

REPO = Path(__file__).resolve().parents[2]


def test_a_presets_name_resolves_to_its_colours():
    t = theme.resolve("noir", PRESETS)
    assert t.name == "noir" and t.kind == "dark"
    assert set(t.colors) == set(theme.ROLES)
    assert t["accent"] == "#c22b45" and t.hex("bg") == "#110d10"


def test_an_object_extends_a_preset_and_overrides_its_roles():
    t = theme.resolve({"extends": "paper", "accent": "#123ABC", "kind": "light"}, PRESETS)
    assert t.name == "paper*" and t.kind == "light"
    assert t["accent"] == "#123abc"  # overridden (stored lower case)
    assert t["accent2"] == PRESETS["paper"]["accent2"]  # the rest are the preset's
    # an object without `extends` extends the default preset, as the engine's does
    assert theme.DEFAULT_PRESET == "noir"
    assert theme.resolve({"fg": "#ffffff"}, PRESETS)["bg"] == PRESETS["noir"]["bg"]
    assert theme.resolve(None, PRESETS) == theme.resolve("noir", PRESETS)
    # keys that are not roles pass through, as the engine lets them
    assert theme.resolve({"extends": "noir", "note": "warmer"}, PRESETS)["fg"] == PRESETS["noir"]["fg"]


@pytest.mark.parametrize("spec, message", [
    ("sepia", "unknown theme 'sepia'.*noir, paper"),
    ({"extends": "sepia"}, "unknown theme"),
    ({"accent": "#abc"}, "accent must be a #rrggbb"),
    ({"fg": "white"}, "fg must be a #rrggbb"),
    ({"bg2": None}, "bg2 must be a #rrggbb"),
    ({"kind": "dim"}, "kind is 'dark' or 'light'"),
    (42, "preset's name or an object"),
])
def test_a_theme_that_does_not_resolve_says_why(spec, message):
    with pytest.raises(theme.ThemeError, match=message):
        theme.resolve(spec, PRESETS)


def test_hex_to_linear_is_the_srgb_transfer():
    assert theme.hex_to_linear("#ede7ea") == pytest.approx((0.846873, 0.799103, 0.822786), abs=1e-6)
    assert theme.hex_to_linear("#c22b45") == pytest.approx((0.539479, 0.024158, 0.059511), abs=1e-6)
    assert theme.hex_to_linear("#0a0a0a") == pytest.approx((0.0030353,) * 3, abs=1e-7)  # the linear toe
    assert theme.hex_to_linear("#000000") == (0.0, 0.0, 0.0) and theme.hex_to_linear("#ffffff") == pytest.approx((1, 1, 1))
    for bad in ("ede7ea", "#ede7e", "#ggg000", "", None):
        with pytest.raises(theme.ThemeError):
            theme.hex_to_linear(bad)


def test_roles_are_linear_through_the_theme_in_use(noir):
    assert theme.current() is noir
    assert theme.linear("fg") == theme.hex_to_linear("#ede7ea")
    assert theme.linear("#4aad63") == theme.hex_to_linear("#4aad63")  # a hex works wherever a role does
    assert theme.rgba("accent", 0.5) == (*theme.hex_to_linear("#c22b45"), 0.5)
    assert materials.linear("accent2") == theme.hex_to_linear("#4aad63")  # materials colour through the theme
    with pytest.raises(KeyError, match="teal.*roles: bg, bg2"):
        theme.linear("teal")


def test_switching_the_theme_recolours_every_role(noir):
    theme.use(theme.resolve("paper", PRESETS))
    assert materials.linear("bg") == theme.hex_to_linear(PRESETS["paper"]["bg"])
    with pytest.raises(TypeError):
        theme.use("paper")  # a resolved Theme, not a spec


def test_a_role_needs_a_theme_in_use_but_a_hex_does_not():
    keep = theme._current
    theme._current = None
    try:
        with pytest.raises(RuntimeError, match="no theme in use"):
            theme.linear("fg")
        assert theme.linear("#ffffff") == pytest.approx((1, 1, 1))
    finally:
        theme._current = keep


def test_presets_load_from_the_engines_file(tmp_path):
    f = tmp_path / "themes.json"
    f.write_text(json.dumps(PRESETS))
    assert theme.load_presets(f) == PRESETS
    with pytest.raises(theme.ThemeError, match="no theme presets"):
        theme.load_presets(tmp_path / "missing.json")


ENGINE_PRESETS = REPO / "app/src/engine/themes.json"
ENGINE_PALETTE = REPO / "app/src/engine/palette.ts"


@pytest.mark.skipif(not ENGINE_PRESETS.exists(), reason="the engine's themes.json is not in this checkout")
def test_every_engine_preset_resolves():
    presets = theme.load_presets(ENGINE_PRESETS)
    assert theme.DEFAULT_PRESET in presets
    for name in presets:
        t = theme.resolve(name, presets)
        assert t.kind in ("dark", "light") and set(t.colors) == set(theme.ROLES)


def test_the_roles_and_the_default_preset_are_the_engines():
    src = ENGINE_PALETTE.read_text() if ENGINE_PALETTE.exists() else ""
    m = re.search(r"export const ROLES = \[(.*?)\] as const;", src, re.S)
    if not m:
        pytest.skip("this checkout's engine has no palette.ts ROLES to compare with")
    assert tuple(re.findall(r"'(\w+)'", m.group(1))) == theme.ROLES
    assert f"export const DEFAULT_THEME = '{theme.DEFAULT_PRESET}';" in src
