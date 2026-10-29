"""A tour of the film's sets (rf/set_world.py): one still per location from its starting view, for checking the
sets themselves (not a shot of the film). The view and the weather come from the environment:

    RF_VIEW=ferry RF_WEATHER=rain blender -b -P blender/render.py -- --film rain-ferry --shot set_tour --mode look \\
        --engine eevee --frames 516 --res 960x540

RF_VIEW is a set_world.views() name, or several by commas (the shot's first frame shows the first, the next frame the
second, ...: render those frames to see them all from one build), optionally after a weather and a colon
("after:cross,valley") (open, valley, crow, step, walk, ferry, jetty_low, jetty_top, tap, cross; crossing, crossing_side and
crossing_jetty push the boat off to mid-river first);
RF_WEATHER rain, thinning or after (default: the look schedule's at the frame). The rain falls as the schedule's (none
after the rain), the near set is inked as the standoff inks it.
"""
from __future__ import annotations

SHOT = {"scene": "ferry"}


def build(ctx):
    import os
    import sys
    from pathlib import Path

    import bpy
    import numpy as np

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import rig, toon
    from rf import set_world

    spec = os.environ.get("RF_VIEW", "ferry")
    weather = os.environ.get("RF_WEATHER") or None
    if ":" in spec:                       # "after:cross,valley": the weather and the views in one variable
        weather, spec = spec.split(":", 1)
    names = spec.split(",")
    scene = ctx.scene
    scene.render.use_motion_blur = False
    world = set_world.build(ctx, weather=weather)
    views = set_world.views()
    if any(n.startswith("crossing") for n in names):     # the boat out on the river, at the crossing's far end
        set_world.push_off(world, ctx, t0=-60.0, t1=-30.0)
    w = world["weather"]
    toon.ink("ink-near", world["near"], radius=0.0042, crease=150)
    cam = rig.engine_camera("camera", fstop=5.6, size=ctx.size)
    cam.data.clip_end = 4000.0
    target = bpy.data.objects.new("aim", None)
    scene.collection.objects.link(target)
    tr = cam.constraints.new("TRACK_TO")
    tr.target = target
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    cam.data.dof.focus_object = target
    scene.camera = cam
    for k, name in enumerate(names):
        cam_at, aim_at, lens = views[name]
        f = ctx.f0 + k
        cam.location, target.location, cam.data.lens = cam_at, aim_at, lens
        cam.keyframe_insert("location", frame=f)
        target.keyframe_insert("location", frame=f)
        cam.data.keyframe_insert("lens", frame=f)
        print(f"set_tour: frame {f}: {name} in {w.name}: camera {cam_at} -> {aim_at}, {lens} mm")
    for ob in (cam, target, cam.data):
        for fc in toon._fcurves(ob.animation_data.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
    # the rain round each view's camera, falling along world -z (the cinema's to tune per shot: here the standoff's,
    # as heavy as the weather's)
    if w.rain > 0.02:
        for k, name in enumerate(names):
            c = np.array(views[name][0])
            drops = toon.rain(f"rain-{name}", tuple(c - (9.0, 9.0, 8.0)), tuple(c + (9.0, 9.0, 6.0)),
                              count=int(6000 * w.rain), speed=9.5, wind=1.8, length=0.34, width=0.0055,
                              color=(0.78, 0.81, 0.86), alpha=0.3, seed=4 + k, near=3.5, clear=0.8)
            for f in range(ctx.f0, ctx.f0 + len(names)):
                drops.hide_render = f != ctx.f0 + k
                drops.keyframe_insert("hide_render", frame=f)
