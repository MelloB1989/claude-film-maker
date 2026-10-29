"""The standoff (shots/standoff.py) with its cast in 3D: Shinza and Tsuru from their VRoid Studio models
(rf/vroid_cast.py) instead of the drawn cels. A shot of its own so its plates are its own
(out/rain-ferry/plates/standoff_vroid/), leaving the cel plates be.

    blender -b -P blender/render.py -- --film rain-ferry --shot standoff_vroid --mode look --engine eevee \\
        --frames 1450,1483,1497,1535 --res 1280x720
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("shots.standoff", Path(__file__).with_name("standoff.py"))
standoff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(standoff)

SHOT = dict(standoff.SHOT)


def build(ctx):
    standoff.build(ctx, cast_kind="vroid")
