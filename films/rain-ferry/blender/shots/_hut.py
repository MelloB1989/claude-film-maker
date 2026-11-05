"""A look at the ferry hut (rf/set_jetty.py, lib/minka.py) from all round, for checking it (not a shot of the film):
one still per frame from the ferry's first frame (516), in the rain: 516-523 orbit it at 7 m (from the jetty first,
then round its -y side, behind it and back), 524 its door close, 525 the lantern close, 526 the eave's corner from
under it, 527 the crow's view, 528 the ferry's, 529 the jetty_low view.
"""
from __future__ import annotations

SHOT = {"scene": "ferry"}


def build(ctx):
    import math
    import sys
    from pathlib import Path

    import bpy
    import numpy as np

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import rig, toon
    from rf import set_world, sets

    scene = ctx.scene
    scene.render.use_motion_blur = False
    world = set_world.build(ctx)
    views = set_world.views()
    w = world["weather"]
    toon.ink("ink-near", world["near"], radius=0.0042, crease=150)
    hx, hy, hz = sets.HUT
    c = np.array([hx, hy, hz + 1.4])
    shots = []
    for k in range(8):                  # 0: from +x (the jetty, the door side), then round by -y
        a = -k * math.tau / 8
        shots.append(((hx + 7.0 * math.cos(a), hy + 7.0 * math.sin(a), hz + 1.6), tuple(c), 28.0))
    door = (hx + 1.6, hy - 0.45, hz + 1.0)
    shots.append(((hx + 4.2, hy - 2.4, hz + 1.3), door, 35.0))
    lantern = tuple(set_world.anchor(world, "lantern"))
    shots.append(((lantern[0] + 1.6, lantern[1] - 1.3, lantern[2] - 0.2), lantern, 50.0))
    shots.append(((hx + 2.4, hy - 2.2, hz + 0.9), (hx + 1.5, hy - 1.4, hz + 2.4), 22.0))
    shots += [views["crow"], views["ferry"], views["jetty_low"]]
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
    for k, (cam_at, aim_at, lens) in enumerate(shots):
        f = ctx.f0 + k
        cam.location, target.location, cam.data.lens = cam_at, aim_at, lens
        cam.keyframe_insert("location", frame=f)
        target.keyframe_insert("location", frame=f)
        cam.data.keyframe_insert("lens", frame=f)
    for ob in (cam, target, cam.data):
        for fc in toon._fcurves(ob.animation_data.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
    if w.rain > 0.02:
        drops = toon.rain("rain-hut", (hx - 12.0, hy - 12.0, hz - 3.0), (hx + 12.0, hy + 12.0, hz + 8.0),
                          count=int(9000 * w.rain), speed=9.5, wind=1.8, length=0.34, width=0.0055,
                          color=(0.78, 0.81, 0.86), alpha=0.3, seed=4, near=3.5, clear=0.8)
