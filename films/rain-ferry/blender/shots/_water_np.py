"""_water without the water's sphere probe (an A/B of its cost and what it adds), not a shot of the film."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SHOT = {"scene": "standoff"}


def build(ctx):
    import bpy

    spec = importlib.util.spec_from_file_location("_water", Path(__file__).with_name("_water.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.build(ctx)
    bpy.data.objects.remove(bpy.data.objects["water-probe"])
