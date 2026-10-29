"""The flash (shots/flash.py) with its ink panel off: the lit picture the panel is thresholded from, to judge the
threshold and the staging by. A shot of its own so its plates are its own.

    blender -b -P blender/render.py -- --film rain-ferry --shot flash_color --mode look --engine eevee --frames 1806
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("shots.flash", Path(__file__).with_name("flash.py"))
flash = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(flash)

SHOT = dict(flash.SHOT)


def build(ctx):
    flash.build(ctx, only="color")
