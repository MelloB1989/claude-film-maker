"""blender/lib/vrm_anim.py's proving shot: Shinza walks in along the jetty's line with his heavy stride and stops,
turns his head to Tsuru standing off to his left, blinks and says his first line; Tsuru, waiting on her pole, shifts
her weight from foot to foot, breathes, and watches him come. A plain floor and a fixed three-quarter camera, the cast
painted as the standoff paints them, so the motion is all there is to look at.

    blender -b -P blender/render.py -- --film rain-ferry --shot animtest --mode look --engine eevee \\
        --frames 0,4,8,...,148 --res 960x540
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

SHOT = {"frames": [0, 210], "look": "0,40,72,100,124,160,180,200"}

SH_FROM, SH_TO = (-3.6, 0.0), (-0.35, 0.0)
TS_AT, TS_YAW = (0.9, 1.35), 205.0          # off his left, turned to the line he walks
LINE = (3.9, 5.5, "tsuyoku naritai")         # L01 (seconds into this shot), as data/dialogue.json reads it


DRAW = (136, 150, 166, 182)                  # the hand leaves its side, takes the hilt, draws, comes round


def _centre(ob):
    bpy.context.view_layer.update()
    m = np.array(ob.matrix_world)
    co = np.array([v.co for v in ob.data.vertices])
    return co.mean(axis=0) @ m[:3, :3].T + m[:3, 3]


def _top(ob):
    """The middle of an object's top (its world vertices' highest few centimetres)."""
    bpy.context.view_layer.update()
    m = np.array(ob.matrix_world)
    co = np.array([v.co for v in ob.data.vertices]) @ m[:3, :3].T + m[:3, 3]
    return co[co[:, 2] > co[:, 2].max() - 0.04].mean(axis=0)


def _frame(ch, p):
    """A world point in the character's frame as it stands now."""
    m = np.array(ch.armature.matrix_world)
    return ch.frame.T @ (np.linalg.inv(m) @ np.append(p, 1.0))[:3] * ch.scale


def build(ctx):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rf import vroid_cast

    scene = ctx.scene
    cast = toon.collection("cast")
    look = toon.Look()
    sh = vroid_cast.shinza_back(cast, look)
    ts = vroid_cast.tsuru(cast, look)
    sh["root"].location = (*SH_FROM, 0.0)
    ts["root"].location = (*TS_AT, 0.0)
    ts["root"].rotation_euler = (0.0, 0.0, math.radians(TS_YAW))
    bpy.context.view_layer.update()

    keys = {}
    for name, built, toward in (("shinza", sh, (0.6, -1.0, 0.8)), ("tsuru", ts, (-0.4, -1.0, 0.8))):
        keys[name] = toon3d.key(f"{name}-key", [built["root"], *built["root"].children_recursive], toward, coll=cast,
                                angle=standoff.KEY3D_ANGLE)
        tones = {p: toon3d.Tone(**{**kw, **standoff.TONES3D_OF.get(name, {}).get(p, {})})
                 for p, kw in standoff.TONES3D.items()}
        vrm.anime(built["vrm"], tones, keys[name])
        vrm.smooth(built["vrm"])

    fps = ctx.fps
    f = ctx.f0
    # ---- Tsuru: still on her pole, her weight from one foot to the other, watching him come
    t = va.Performance(ts["vrm"], fps=fps, seed=2)
    t.plant_feet(f)
    t.breathe(rate=0.2, depth=1.2)
    t.shift(f + 34, "right", amount=0.8, over=0.9)
    t.shift(f + 96, "left", amount=0.9, over=1.1)
    t.blinks(mean=4.5)
    t.secondary(wind=(0.0, 1.5, 0.0))
    # her straw cape swings heavy from its collar
    mino = ts["parts"]["mino"]
    if mino:
        top = _top(mino[0])
        t.dangle(mino, top, length=0.35, stiffness=14.0, drag=0.12)

    # ---- Shinza: in with a heavy stride, stops, a held breath, turns his head to her, blinks, speaks
    vrm.pose(sh["vrm"], vrm_rig.release(sh["vrm"]))       # his builder's IK let go: the walk plants his feet
    s = va.Performance(sh["vrm"], fps=fps, seed=1)
    s.breathe(rate=0.3, depth=1.4)
    stop = s.walk([SH_FROM, SH_TO], f + 4, gait="heavy", pose=WALK, end_pose=STOP)
    s.look(f, None)
    s.look(stop + 10, t.face_at, ease="inout")
    s.settle(stop, 0.6)
    s.blinks(mean=3.2)
    s.blink_at(stop + 10)
    s.express(f, {"glare": 0.6})
    s.express(stop + 18, {"glare": 1.0})
    s.say(LINE[0] + f / fps, LINE[1] + f / fps, LINE[2], energy=0.8)
    s.secondary(wind=(0.0, 1.5, 0.0))
    # the headband's tails flutter from its knot
    band = sh["parts"]["headband"]
    if len(band) > 2:
        s.dangle(band[2:], _centre(band[1]), toward=_centre(band[2]) - _centre(band[1]), length=0.15, stiffness=5.0,
                 drag=0.06, wind_scale=1.5)
    # ... then his right hand goes over his shoulder for the hilt, takes it, and draws the nodachi up out of its
    # scabbard and round in front of him: the sword handed from the scabbard to his hand at the grasp
    sword = sh["parts"]["sword"]
    cap, guard = _centre(sword[4]), _centre(sword[2])
    along = (guard - cap) / np.linalg.norm(guard - cap)
    grip = _frame(sh["vrm"], cap + along * 0.1)
    up = _frame(sh["vrm"], cap) - _frame(sh["vrm"], guard)
    up /= np.linalg.norm(up)
    elbow = (-0.45, 0.2, 1.75)
    s.reach(DRAW[0], "rightHand", ("char", grip), ease="inout", weight=0.0, pole=elbow)
    s.reach(DRAW[1], "rightHand", ("char", grip), ease="inout", pole=elbow)
    s.pose(DRAW[1], vrm.grip_pose("right"), ease="inout", full=False)
    s.carry(sword[0], DRAW[1], "rightHand")
    s.reach(DRAW[2], "rightHand", ("char", grip + up * 0.55), ease="in", pole=elbow)
    s.reach(DRAW[3], "rightHand", ("char", (-0.18, -0.42, 1.12)), ease="settle", pole=(-0.6, 0.1, 0.9))
    s.settle(DRAW[3], 0.5)
    t.look(f, s.face_at, lag=1.4)
    t.bake(ctx.f0, ctx.f1)
    s.bake(ctx.f0, ctx.f1)

    # a still three-quarter camera on the jetty's line, a floor under them
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
    cam.data.lens = 30.0
    cam.location = (1.4, -5.2, 1.35)
    aim = bpy.data.objects.new("aim", None)
    scene.collection.objects.link(aim)
    aim.location = (-1.0, 0.5, 0.95)
    c = cam.constraints.new("TRACK_TO")
    c.target = aim
    c.track_axis, c.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    scene.camera = cam


# his carriage walking: the arms hanging easy, the chest set, the chin down a touch; and how he stands when he stops:
# square, the weight even, the hands loose at his sides
WALK = {**va.STAND, "spine": (4.0, 0.0, 0.0), "chest": (2.0, 0.0, 0.0), "neck": (2.0, 0.0, 0.0), "head": (2.0, 0.0, 0.0)}
STOP = {**va.STAND, "spine": (1.0, 0.0, 0.0), "head": (-2.0, 0.0, 0.0)}
