"""The film's palette for Blender: colours by role (docs/CONVENTIONS.md), resolved from film.json's `theme` exactly as the
engine resolves it (app/src/engine/palette.ts resolveTheme), and turned into the linear light Blender's shaders take.

A theme spec is a preset's name in app/src/engine/themes.json, or an object `{"extends": "<preset>", <role>: "#rrggbb",
"kind": "dark" | "light"}` whose roles override the preset's (`extends` defaults to DEFAULT_PRESET). Every role must end
up a `#rrggbb` colour and `kind` "dark" or "light"; anything else raises ThemeError. Keys that are not roles (a name,
notes) pass through, as the engine lets them.

The roles: bg, bg2 (the background, its lifted shade), surface, surface2 (panels), rule, ruleStrong (hairlines), fg,
fgDim, fgFaint (type and marks at three strengths), accent, accentBright, accentDim (the primary accent), accent2,
accent2Bright, accent2Dim (the secondary). Only the accents glow: a material in fg never emits.

render.py resolves the film's theme and makes it the one in use (`use`), so library code and shots name colours by role:
`linear("accent")`, `materials.satin("fg")`, `lights.studio(world="bg")`. A '#rrggbb' works anywhere a role does.

bpy-free (tested without Blender).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PRESETS_REL = Path("app/src/engine/themes.json")  # in a checkout
PRESETS_FILE = REPO / PRESETS_REL
DEFAULT_PRESET = "noir"
ROLES = ("bg", "bg2", "surface", "surface2", "rule", "ruleStrong", "fg", "fgDim", "fgFaint",
         "accent", "accentBright", "accentDim", "accent2", "accent2Bright", "accent2Dim")
GLOWING = ("accent", "accentBright", "accentDim", "accent2", "accent2Bright", "accent2Dim")  # look.ts glow() keys
_HEX = re.compile(r"#[0-9a-fA-F]{6}")


class ThemeError(ValueError):
    """A theme that does not resolve: an unknown preset, a missing role, a malformed colour or kind."""


def srgb_to_linear(c: float) -> float:
    """One sRGB channel (0..1) in linear light (the IEC 61966-2-1 transfer)."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_linear(hexa: str) -> tuple[float, float, float]:
    """An sRGB '#rrggbb' as linear RGB (Blender's working space, Linear Rec.709, is the engine's linear sRGB)."""
    if not isinstance(hexa, str) or not _HEX.fullmatch(hexa):
        raise ThemeError(f"not a #rrggbb colour: {hexa!r}")
    n = int(hexa[1:], 16)
    return tuple(srgb_to_linear(((n >> s) & 255) / 255) for s in (16, 8, 0))  # type: ignore[return-value]


@dataclass(frozen=True)
class Theme:
    """A resolved theme: every role's '#rrggbb', whether its background is dark or light, and its name (the preset's,
    or '<preset>*' for one with overrides, as the engine names it)."""
    name: str
    kind: str
    colors: dict = field(compare=True)

    def hex(self, color: str) -> str:
        """A role's '#rrggbb' (a '#rrggbb' is passed through)."""
        if isinstance(color, str) and color.startswith("#"):
            hex_to_linear(color)  # validates it
            return color
        try:
            return self.colors[color]
        except KeyError:
            raise KeyError(f"not a palette role: {color!r} (roles: {', '.join(ROLES)}; or a '#rrggbb')") from None

    def linear(self, color: str) -> tuple[float, float, float]:
        """A role (or a '#rrggbb') as linear RGB."""
        return hex_to_linear(self.hex(color))

    def rgba(self, color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
        """A role (or a '#rrggbb') as linear RGBA, for a shader socket."""
        return (*self.linear(color), float(alpha))

    def __getitem__(self, role: str) -> str:
        return self.hex(role)


def load_presets(path: str | Path = PRESETS_FILE) -> dict:
    """The engine's theme presets ({name: {kind, <role>: '#rrggbb'}}), from app/src/engine/themes.json."""
    path = Path(path)
    if not path.exists():
        raise ThemeError(f"no theme presets at {path}: the engine's themes.json is needed to resolve a preset's name")
    return json.loads(path.read_text())


def resolve(spec: str | dict | None = None, presets: dict | None = None) -> Theme:
    """A theme spec (film.json `theme`: a preset's name, or {"extends": preset, ...overrides}; None: DEFAULT_PRESET)
    resolved against `presets` (default: the engine's themes.json). Raises ThemeError as the engine's resolveTheme
    throws: an unknown preset, a role that is not '#rrggbb', a kind that is not 'dark' or 'light'."""
    spec = DEFAULT_PRESET if spec is None else spec
    if isinstance(spec, str):
        o: dict = {"extends": spec}
    elif isinstance(spec, dict):
        o = dict(spec)
    else:
        raise ThemeError(f"a theme is a preset's name or an object, not {spec!r}")
    name = o.pop("extends", None) or DEFAULT_PRESET
    presets = load_presets() if presets is None else presets
    base = presets.get(name)
    if not isinstance(base, dict):
        raise ThemeError(f"unknown theme {name!r} (presets: {', '.join(presets)})")
    t = {**base, **o}
    label = spec if isinstance(spec, str) else f"{name}*"
    for role in ROLES:
        if not isinstance(t.get(role), str) or not _HEX.fullmatch(t[role]):
            raise ThemeError(f"theme {label}: {role} must be a #rrggbb colour, got {t.get(role)!r}")
    if t.get("kind") not in ("dark", "light"):
        raise ThemeError(f"theme {label}: kind is 'dark' or 'light', got {t.get('kind')!r}")
    return Theme(label, t["kind"], {role: t[role].lower() for role in ROLES})


# ------------------------------------------------------------------------------------------------ the theme in use

_current: Theme | None = None


def use(theme: Theme) -> Theme:
    """Make `theme` the one library code and shots colour with (render.py does, from film.json, before build())."""
    global _current
    if not isinstance(theme, Theme):
        raise TypeError(f"use() takes a resolved Theme (theme.resolve), not {theme!r}")
    _current = theme
    return theme


def current() -> Theme:
    """The theme in use. Raises RuntimeError before render.py (or a test) has chosen one."""
    if _current is None:
        raise RuntimeError("no theme in use: render.py sets the film's (theme.use(film.theme)) before build()")
    return _current


def linear(color: str) -> tuple[float, float, float]:
    """A role of the theme in use, or a '#rrggbb', as linear RGB."""
    if isinstance(color, str) and color.startswith("#"):
        return hex_to_linear(color)
    return current().linear(color)


def rgba(color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """linear(color) with an alpha, for a shader socket."""
    return (*linear(color), float(alpha))
