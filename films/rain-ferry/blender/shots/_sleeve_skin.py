"""Test (never in the film): shots/fall.py with Shinza's SKIN outline modifier off, to see which outline makes the
sawtooth along his sleeves."""
import importlib.util
from pathlib import Path

SHOT = {"scene": "fall"}


def build(ctx):
    spec = importlib.util.spec_from_file_location("shots.fall_for_test", Path(__file__).with_name("fall.py"))
    fall = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fall)
    fall.build(ctx)
    import bpy

    for ob in bpy.data.objects:
        for md in getattr(ob, "modifiers", []):
            if md.type == "NODES" and "Outline" in md.name and "SKIN" in md.name and "shinza" in ob.name:
                md.show_render = md.show_viewport = False
                print(f"_sleeve: {ob.name} {md.name} off")
