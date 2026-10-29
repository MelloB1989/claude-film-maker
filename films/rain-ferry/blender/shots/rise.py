"""Tsuru rises. Over Shinza's right shoulder (his back and his drawn blade a dark soft mass at the left of the frame),
the old woman sits on a crate at the jetty's end, her hand on the bamboo pole whose foot lies in the moored boat. A
held breath; then she stands, leaning into it, and draws the pole up out of the boat, her hand sliding down it as it
comes upright, and sets its foot on the deck beside her. Upright, she lifts her eyes to him: "So young." (line 10,
+1.2 s to +3.2 s), the corner of her mouth going up after it. The camera creeps in and rises with her.

    blender -b -P blender/render.py -- --film rain-ferry --shot rise --mode look --engine eevee \\
        --frames 1335,1370,1400,1430 --res 960x540
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

SHOT = {"scene": "rise"}

# the camera: over his right shoulder (world), creeping in and rising with her; what it looks at follows her head
CAM_FROM, CAM_TO = (-3.2, -0.82, 1.38), (-2.85, -0.74, 1.5)
LENS = (58.0, 66.0)
FSTOP = 3.2
AIM_DROP = 0.2                  # m: the aim this far under her eyes (her head in the frame's upper third)
# the rise (s into the shot): held, then up, leaning into it; the pole drawn up and planted
RISE = (0.35, 1.55)
POLE = (0.45, 1.9)
LOOK_UP = (1.85, 2.5, 7.0)      # her head lifting to him: from, to (s), degrees
LINE = (1.2, 3.21)              # data/dialogue_timing.json L10, s into the shot (56.8 - 58.81)
SMILE = (3.15, 3.7, 0.45)
# seated: the hips this far back and down (her frame) on a crate this tall, the left hand on her thigh, the right on
# the pole (her frame), the feet a little forward
SEAT = dict(hips=(0.0, 0.1, -0.31), crate=0.4, left=(-0.08, -0.12, -0.18), feet=(0.0, -0.06, 0.0), lean=7.0)
GRIP0 = (-0.21, -0.3, 0.5)
POLE_FOOT0 = (3.4, 1.72, -0.22)   # world: in the boat's bow, under the gunwale
LOOK = dict(rims=[((-1.0, 0.4), (0.95, 0.58, 0.26), 0.18, 0.0025, 0.9), ((0.6, 1.0), (0.6, 0.68, 0.85), 0.3, 0.003, 0.9)],
            para_from=(0.3, 0.9), para_to=(0.85, 0.1), para_amount=0.35)
KEYS = {"shinza": (1.0, -0.6, 0.7), "tsuru": (-1.0, -0.5, 0.7)}


def build(ctx):
    import bpy
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import satsuei, shapes, vrm, vrm_rig
    from rf import duel
    from rf.vroid_common import to_frame
    from rf import duel_motion as dm

    st = duel.stage(ctx)
    ts, sh = st.bodies["tsuru"], st.bodies["shinza"]
    ch = st.ch("tsuru")
    cam, aim = duel.camera(ctx, lens=LENS[0], fstop=FSTOP)

    # her face while she speaks: the calm eyes without its shut mouth, the mouth shut apart (vrm_rig.compose)
    vrm_rig.compose(ch, "tsuru-eyes", {"tsuru-hood": 0.75, "tsuru-brow-low": 0.6, "Fcl_EYE_Close": 0.05,
                                       "Fcl_BRW_Angry": 0.1})
    vrm_rig.compose(ch, "tsuru-shut", {"Fcl_MTH_Close": 1.0, "tsuru-press": 0.5})
    vrm_rig.compose(ch, "tsuru-smile", {"tsuru-sneer": 1.0})
    syl = dm.syllables(*LINE, ["aa", "aa", ("ih", 0.5), ("ee", 0.55), ("ee", 0.35)], hold_last=2.2, openness=0.6)

    # the crate she sits on, under her seated hips
    hips_rest = np.array(ch.rest("hips")) + np.array((0.0, 0.05, -0.045))     # rf/vroid_tsuru.py's TS_HIPS
    seat = hips_rest + np.array(SEAT["hips"])
    c = ch.world((seat[0], seat[1] + 0.02, SEAT["crate"] / 2))
    shapes.box("crate", tuple(c), (0.42, 0.34, SEAT["crate"]), material=st.crossing["materials"]["plank"],
               coll=st.crossing["near"], rot_z=ch.root.rotation_euler[2] + 0.15)

    # the pole: carried by a pivot at its foot, turned from lying out of the boat to upright
    shaft = st.actors["tsuru"]["parts"]["pole"][0]             # the handle and the cord ride on it
    foot1 = np.array(shaft.matrix_world.translation)            # the pole's foot as built: on the deck by her
    pivot = bpy.data.objects.new("pole-pivot", None)
    st.cast.objects.link(pivot)
    pivot.location = tuple(foot1)
    pivot.rotation_mode = "QUATERNION"
    bpy.context.view_layer.update()
    w = shaft.matrix_world.copy()
    shaft.parent, shaft.parent_type = pivot, "OBJECT"
    shaft.matrix_world = w
    grip1 = np.array(ch.world((-0.24, -0.2, 0.98)))              # her hand on it as built (rf/vroid_tsuru.py)
    grip0 = np.array(ch.world(GRIP0))
    foot0 = np.array(POLE_FOOT0)
    up = np.array([0.0, 0.0, 1.0])
    dir0 = (grip0 - foot0) / np.linalg.norm(grip0 - foot0)
    along0, along1 = float(np.linalg.norm(grip0 - foot0)), float(grip1[2] - foot1[2])

    head_z = {}
    comp = satsuei.setup(ctx.scene, st.cast)
    n = ctx.f1 - ctx.f0
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        r = dm.span(t, *RISE)                  # 0 seated .. 1 standing
        lean = SEAT["lean"] * (1 - r) + 18.0 * math.sin(math.pi * dm.span(t, RISE[0], RISE[1] + 0.15))
        look_up = LOOK_UP[2] * dm.span(t, LOOK_UP[0], LOOK_UP[1])
        p = dm.span(t, *POLE)
        # the pole: its foot swung up out of the boat and over the deck's edge to beside her, its top coming upright
        foot = foot0 + (foot1 - foot0) * p + up * 0.35 * math.sin(math.pi * p)
        d = dm.slerp_dir(dir0, up, dm.ease_out(p))
        pivot.rotation_quaternion = Vector((0.0, 0.0, 1.0)).rotation_difference(Vector(d))
        pivot.location = tuple(foot)
        pivot.keyframe_insert("location", frame=f)
        pivot.keyframe_insert("rotation_quaternion", frame=f)
        grip = foot + d * (along0 + (along1 - along0) * p)
        vrm.grasp(ch, "right", to_frame(ch, grip), duel.dir_to_frame(ch, d), (1.0, 0.0, 0.0), pole=(-0.5, 0.4, 0.6),
                  amount=0.95, bend=70.0)
        s = 1.0 - r
        moves = {"leftHand-target": tuple(np.array(SEAT["left"]) * s),
                 "leftFoot-target": tuple(np.array(SEAT["feet"]) * s),
                 "rightFoot-target": tuple(np.array(SEAT["feet"]) * s)}
        turns = duel.add(duel.breathing(t, 0.22, 0.8),
                         {"spine": (lean * 0.4, 0.0, 0.0), "chest": (lean * 0.35, 0.0, 0.0),
                          "head": (-look_up - 0.5 * lean, 0.0, -2.0 * dm.envelope(t, *LINE, LINE[1] + 0.6) )})
        ts.key(f, turns, hips=tuple(np.array(SEAT["hips"]) * s + np.array((0.0, -0.06, 0.02)) * math.sin(math.pi * r)),
               moves=moves, keep=("rightHand-target", "rightHand-hold"),
               chains=ts.sway(t, amount=5.0, cloth=3.0, toward=(0.0, 1.0, 0.0), seed=7))
        mouth = dm.mouth(t, syl)
        opened = max(mouth.values())
        smile = SMILE[2] * dm.span(t, SMILE[0], SMILE[1])
        vrm.express(ch, {"tsuru-eyes": 1.0, "tsuru-shut": 1.0 - min(1.0, opened / 0.4), "tsuru-smile": smile,
                         **{k: v for k, v in mouth.items() if v > 0}}, frame=f)
        # Shinza, his back to us: hard breaths
        sh.key(f, duel.breathing(t, 0.45, 1.8), chains=sh.sway(t, amount=9.0, cloth=4.0, toward=(0.0, -1.0, 0.0), seed=1))

        bpy.context.view_layer.update()
        head_z[f] = float(ch.face().z)
        u = dm.ease(t / (n / ctx.fps))
        cam_at = np.array(dm.lerp(CAM_FROM, CAM_TO, u)) + duel.shake(t, 0.01)
        lens = LENS[0] + (LENS[1] - LENS[0]) * u
        eyes = ch.face()
        duel.key_camera(cam, aim, f, cam_at, (eyes.x, eyes.y, eyes.z - AIM_DROP), lens=lens)
        duel.key_lines(st, f, cam_at, lens)
        duel.key_light(st, f, KEYS)
        duel.swing_lantern(st, f, t)
        comp.key(f, duel.look(st, f, LOOK))
    comp.hold()
    print(f"rise: her eyes from {min(head_z.values()):.2f} to {max(head_z.values()):.2f} m")
