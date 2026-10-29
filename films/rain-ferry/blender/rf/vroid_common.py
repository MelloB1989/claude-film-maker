"""What the Rain Ferry's VRoid cast (rf/vroid_shinza.py, rf/vroid_tsuru.py) shares: where the VRMs live, the
characters' heights, the props' toon colours and the planting of feet."""
from __future__ import annotations

from pathlib import Path

from lib import vrm

VROID = Path(__file__).resolve().parents[2] / "assets" / "vroid"
STANDIN = "base_masc"
HEIGHT = {"shinza": 1.76, "tsuru": 1.48}
# how far cloth whitens in a lightning flash (toon.cel's flash): the props of cloth as the painted clothes do
# (shots/standoff.py TONES3D's cloth), a dark kimono staying dark in the strike as the cels draw it
CLOTH_FLASH = 0.03
# the props' toon colours, linear (lit, shade)
COLORS = {
    "steel": ((0.85, 0.88, 0.92), (0.3, 0.32, 0.36)),
    "lacquer": ((0.04, 0.04, 0.045), (0.008, 0.008, 0.01)),
    "wrap": ((0.11, 0.1, 0.09), (0.025, 0.022, 0.02)),
    "brass": ((0.42, 0.32, 0.15), (0.12, 0.09, 0.04)),
    "obi": ((0.12, 0.115, 0.105), (0.03, 0.029, 0.027)),
    "band": ((0.42, 0.035, 0.022), (0.16, 0.012, 0.008)),      # red, darkened by the rain
    "bamboo": ((0.42, 0.36, 0.2), (0.14, 0.11, 0.065)),
    "cord": ((0.2, 0.13, 0.08), (0.06, 0.04, 0.025)),
    "straw": ((0.26, 0.205, 0.11), (0.05, 0.04, 0.022)),
    "straw_tip": ((0.4, 0.33, 0.19), (0.1, 0.075, 0.045)),
    "straw_dark": ((0.18, 0.14, 0.075), (0.04, 0.03, 0.018)),
    "rope": ((0.16, 0.12, 0.07), (0.04, 0.03, 0.018)),
}


def vrm_file(name: str) -> Path:
    path = VROID / f"{name}.vrm"
    if not path.exists():
        print(f"vroid_common: no {path.name} yet; {STANDIN}.vrm stands in for {name}")
        path = VROID / f"{STANDIN}.vrm"
    return path


def plant(ch, feet: dict) -> None:
    for side, (at, pole, turn) in feet.items():
        vrm.reach(ch, f"{side}Foot", at, pole=pole)
        vrm.hold(ch, f"{side}Foot", turn)
