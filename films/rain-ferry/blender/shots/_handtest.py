"""The hands core's proving shot (blender/lib/vrm_anim.py's hand, gesture, grasp, hilt and follow-through; lib/vrm.py's
hand shapes; lib/vrm_rig.py's grips): Shinza, standing with his sword hanging from his right hand, acts with his left:
relaxed at his side, an open hand offered palm up, a point, a beckon, a fist raised, a fast swing back down to his side
(the hand and fingers trailing and settling), a trembling hand; then both hands take the hilt in front of him. Tsuru
beside him holds her pole (fingers wrapped round it) and her pipe pinched by its stem. A plain floor and a still
camera, the cast painted as the standoff paints them; a close cut on her hands at the end.

    blender -b -P blender/render.py -- --film rain-ferry --shot _handtest --mode look --engine eevee \\
        --frames 10,40,62,84,96,130,150,154,158,164,180,212,236 --res 960x540
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import bpy
import numpy as np

from lib import toon, toon3d, vrm, vrm_anim as va, vrm_rig

_spec = importlib.util.spec_from_file_location("shots.standoff", Path(__file__).with_name("standoff.py"))
standoff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(standoff)

SHOT = {"frames": [0, 244], "look": "10,40,62,84,96,130,150,154,158,164,180,212,236"}

SH_AT, TS_AT = (-0.45, 0.0), (0.75, 0.35)
CLOSE = 224                                   # the cut to her hands
# his left arm's acting (lib/vrm.py's turns, from the T-pose): offering palm up, pointing ahead, a fist raised
OFFER = {"leftUpperArm": (0.0, 62.0, -30.0), "leftLowerArm": (-90.0, 0.0, -70.0), "leftHand": (0.0, -10.0, 0.0)}
POINT = {"leftUpperArm": (0.0, 15.0, -75.0), "leftLowerArm": (0.0, 0.0, -10.0), "leftHand": (0.0, 0.0, 0.0)}
FIST = {"leftUpperArm": (0.0, 70.0, -15.0), "leftLowerArm": (0.0, 0.0, -110.0), "leftHand": (0.0, 0.0, 0.0)}
DOWN = {k: vrm.RELAXED[k] for k in ("leftUpperArm", "leftLowerArm", "leftHand")}


def build(ctx):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rf import vroid_cast, vroid_shinza as S

    scene = ctx.scene
    cast = toon.collection("cast")
    look = toon.Look()
    sh = vroid_cast.shinza(cast, look, kasa=None, sword="hand", pose="stand")
    ts = vroid_cast.tsuru(cast, look, pipe="hand", pole="hand")
    sh["root"].location = (*SH_AT, 0.0)
    ts["root"].location = (*TS_AT, 0.0)
    ts["root"].rotation_euler = (0.0, 0.0, math.radians(-15.0))
    bpy.context.view_layer.update()
    for name, built, toward in (("shinza", sh, (0.6, -1.0, 0.8)), ("tsuru", ts, (-0.4, -1.0, 0.8))):
        key = toon3d.key(f"{name}-key", [built["root"], *built["root"].children_recursive], toward, coll=cast,
                         angle=standoff.KEY3D_ANGLE)
        tones = {p: toon3d.Tone(**{**kw, **standoff.TONES3D_OF.get(name, {}).get(p, {})})
                 for p, kw in standoff.TONES3D.items()}
        vrm.anime(built["vrm"], tones, key)
        vrm.smooth(built["vrm"])

    fps, f = ctx.fps, ctx.f0
    # ---- Tsuru: still, breathing, her hands on the pole and the pipe as the builder closed them
    t = va.Performance(ts["vrm"], fps=fps, seed=2)
    t.plant_feet(f)
    t.breathe(rate=0.2, depth=1.2)
    t.blinks(mean=4.5)
    # ---- Shinza: his left hand acts, his right holds the sword hanging, then both take the hilt
    s = va.Performance(sh["vrm"], fps=fps, seed=1)
    s.plant_feet(f)
    s.breathe(rate=0.3, depth=1.2)
    s.blinks(mean=3.4)
    s.pose(f + 22, DOWN, full=False)
    s.pose(f + 40, OFFER, full=False, ease="inout")
    s.hand(f + 38, "left", "open", ease="out")
    s.pose(f + 54, OFFER, full=False)
    s.pose(f + 64, POINT, full=False, ease="overshoot")
    s.hand(f + 62, "left", "point", ease="out")
    s.pose(f + 78, POINT, full=False)
    s.pose(f + 88, OFFER, full=False, ease="inout")
    s.gesture(f + 88, "left", "beckon", hold=1.0)
    s.pose(f + 116, OFFER, full=False)
    s.pose(f + 132, FIST, full=False, ease="settle")
    s.hand(f + 126, "left", "fist", ease="overshoot")
    s.pose(f + 146, FIST, full=False)
    # the fast swing: six frames from the raised fist to his side, the hand opening as it goes, trailing and settling
    s.pose(f + 152, DOWN, full=False, ease="in")
    s.hand(f + 150, "left", "relaxed", ease="out", spread=0.15)
    s.pose(f + 162, DOWN, full=False)
    s.gesture(f + 172, "left", "tremble", hold=1.0, after="relaxed")
    # both hands to the hilt: his low guard's grips (rf/vroid_shinza.py), the left hand in from his side
    hilt = S.HILT_DIR / np.linalg.norm(S.HILT_DIR)
    s.hilt(f + 210, S.POMMEL, hilt, {"right": (1.0, 0.0, -0.6), "left": (-1.0, 0.0, -0.6)}, grips=(S.GRIPS["left"], S.GRIPS["right"]),
           poles=S.SH_ELBOWS, radius=S.TSUKA)
    s.reach(f + 196, "leftHand", ("char", (0.2, -0.05, 0.85)), weight=0.0, ease="inout")
    for fr in (f, f + 196):         # his right hand hanging with the sword as the builder closed it, until the hilt
        s.grasp(fr, "right", S.HANG["hole"], S.HANG["way"], (1.0, 0.0, 0.0), pole=(-0.5, 0.5, 0.9), radius=S.TSUKA)
    s.look(f, None)
    s.bake(ctx.f0, ctx.f1)
    t.bake(ctx.f0, ctx.f1)

    # a still camera on the two of them, a floor under them; a close cut to her hands
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
    floor = bpy.context.active_object
    mat = bpy.data.materials.new("floor")
    mat.diffuse_color = (0.05, 0.05, 0.055, 1.0)
    floor.data.materials.append(mat)
    world = scene.world or bpy.data.worlds.new("world")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.32, 0.34, 0.38, 1.0)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 2.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("aim", None)
    scene.collection.objects.link(aim)
    c = cam.constraints.new("TRACK_TO")
    c.target = aim
    c.track_axis, c.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    scene.camera = cam
    # the cast face +x: the camera out in front of them, a little to his side
    for fr, at, to, lens in ((f, (3.4, -0.9, 1.25), (0.0, -0.1, 1.05), 40.0),
                             (CLOSE, (TS_AT[0] + 1.3, TS_AT[1] - 0.5, 1.05), (TS_AT[0], TS_AT[1] - 0.1, 0.92), 50.0)):
        cam.location, aim.location, cam.data.lens = at, to, lens
        cam.keyframe_insert("location", frame=fr)
        aim.keyframe_insert("location", frame=fr)
        cam.data.keyframe_insert("lens", frame=fr)
    for ob in (cam, aim, cam.data):
        ad = ob.animation_data
        for fc in (toon._fcurves(ad.action) if ad is not None and ad.action is not None else []):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
