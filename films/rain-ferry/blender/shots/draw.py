"""Shot 12, draw (51.8-55.6 s): Shinza from low at her side, his right fist on the hilt over his shoulder as demand left
it. A grin; and he draws, slowly, the long blade sliding up out of the scabbard on his back (the steel's long ring
from 51.95 s, data/mix.json sword_draw) while he says "Then..."; it clears with the ring's peak and whips up over his
head and down, his wrist rolling it, to one hand out in front of him, its point down toward her: "...you'll do." The
camera eases in, jolts as the blade clears, and holds on the grin and the wet steel.

The sword leaves the scabbard (rf/vroid_shinza.py parts: carried by the sheath) for his right hand on the shot's first
frame (jetty_talk.draw_sword); the scabbard is drawn down its own length a little as the blade comes out (the left
shoulder dropping), as a long blade must be drawn from the back.

    blender -b -P blender/render.py -- --film rain-ferry --shot draw --mode look --engine eevee \\
        --frames 1250,1268,1280,1300 --res 960x540
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import cinema  # noqa: E402
from rf import jetty_talk as jt  # noqa: E402

SHOT = {"scene": "draw"}

# the camera: low at her side, three-quarters on him (world: its bearing from him, degrees, and distance; height)
BEARING, DIST, HEIGHT = -38.0, (2.35, 1.95), (1.08, 1.12)
LENS = (32.0, 35.0)
GRIN = (0.0, 0.5)
PULL = (0.15, 1.24)          # the slow draw up out of the scabbard (from the steel's onset)
PULL_LEN, SLIDE = 0.42, 0.24  # how far his fist travels up the scabbard's line (short of a locked arm), and the scabbard down its own
CLEAR = 1.3                  # the tip clears: the ring's peak, the jolt
# the blade's way (his frame: x his left, y his back, z up) and his fist's place through the swing over and down, and
# the way his palm faces (the blade's flat); the first comes from the scabbard
SWING = [(1.36, (0.15, 0.85, 0.5), (-0.33, 0.05, 1.93), (0.4, 0.3, 0.0)),
         (1.46, (0.0, 0.1, 1.0), (-0.31, -0.1, 1.84), (0.9, 0.0, 0.1)),
         (1.57, (0.1, -0.9, 0.3), (-0.33, -0.3, 1.6), (1.0, 0.0, -0.1)),
         (1.68, (0.24, -0.72, -0.66), (-0.36, -0.42, 1.2), (1.0, 0.0, -0.3)),
         (1.9, (0.2, -0.78, -0.58), (-0.36, -0.4, 1.16), (1.0, 0.0, -0.3))]
# his left hand on the scabbard: it takes it low behind his hip (this far down it from the guard, m) as the draw
# starts and pulls it down its own line with the blade coming out (the long blade's draw from the back), then lets go
# and comes back to his side, half closed
SAYA_HOLD, LEFT_TAKE, LEFT_FREE = 0.72, (0.0, 0.3), (CLEAR + 0.25, CLEAR + 0.75)
SAYA_POLE = np.array((0.5, 0.35, 1.0))     # its elbow out and back the while
NARROW = (1.7, 2.0)
BLINKS = (0.55, 3.1)


def build(ctx):
    st = jt.stage(ctx, who=("shinza",), ink=0.0)     # set line art costs ~10 s a frame; his own outline stays
    jt.compose_faces(st)
    perform(st)
    st.say("shinza", "L09", "nara... anta de ii", energy=0.9)
    st.blinks("shinza", BLINKS)
    jt.draw_sword(st)
    st.bake()
    slide_scabbard(st)
    face = st.head_at("shinza", ctx.f0)
    b = math.radians(jt.SHINZA_FACING + BEARING)
    out = np.array((math.cos(b), math.sin(b), 0.0))
    move = cinema.line((*(face[:2] + out[:2] * DIST[0]), HEIGHT[0]), (*(face[:2] + out[:2] * DIST[1]), HEIGHT[1]),
                       face - (0, 0, 0.12), face - (0, 0, 0.1))
    st.film([cinema.Setup("draw", 0.0, move, lens=LENS, fstop=2.8, focus=(st.cast["shinza"]["vrm"], "head"),
                          shake=cinema.Shake(breath=0.08, hits=((CLEAR, 0.9),)))])
    jt.outline(st)
    jt.key_light(st, "shinza", (0.6, -1.0, 0.75))
    st.composite(lambda f: dict(rims=[((-1.0, 0.3), (1.0, 0.5, 0.18), 0.35, 0.004, 0.9),
                                      ((0.4, 1.0), (0.6, 0.68, 0.85), 0.3, 0.003, 0.9)],
                                para_from=(0.5, 0.95), para_to=(0.5, 0.05)))


def perform(st):
    from lib import vrm

    ch = st.cast["shinza"]["vrm"]
    # the hilt as his body holds it at the end of demand (the chest turned to the reach): measured there
    vrm.pose(ch, jt.shinza_stand(0.0, reach=1.0), hips=jt.shinza_hips(0.0))
    guard, u = jt.hilt_axis(st)
    grip = guard + u * jt.HILT_GRIP
    d = -u                                            # the blade's way, sheathed
    start_palm = (0.25, 1.0, 0.0)
    keys_b = [(PULL[1], tuple(d))] + [(t, tuple(np.asarray(b) / np.linalg.norm(b))) for t, b, _, _ in SWING]
    keys_p = [(PULL[1], tuple(grip + u * PULL_LEN))] + [(t, p) for t, _, p, _ in SWING]
    keys_palm = [(PULL[1], start_palm)] + [(t, q) for t, _, _, q in SWING]
    poles = [(0.0, jt.HILT_POLE), (PULL[1], (-0.8, 0.0, 1.9)), (SWING[2][0], (-0.7, -0.1, 1.5)),
             (SWING[-1][0], (-0.6, 0.25, 1.0))]
    saya = guard - u * SAYA_HOLD
    saya_turn = jt.hand_turn(ch, "left", -u, jt.flat_palm(-u, (-0.6, 0.7, 0.0)))
    side_turn = jt.hand_turn(ch, "left", jt.SIDE["knuckles"], jt.SIDE["palm"])
    for f in st.frames():
        t = st.t(f)
        if t <= PULL[1]:
            p = grip + u * PULL_LEN * jt.ease(jt.ramp(t, *PULL))     # slow, then quicker as it comes
            b, palm = d, start_palm
        else:
            # the swing in one arc over and down (jt.glide: carried through its keys, not stopping at each), the
            # blade's way and the palm's turn a beat behind the fist (the wrist rolling it through)
            p = np.array(jt.glide(keys_p, t))
            b = np.array(jt.glide(keys_b, t - 0.03))
            palm = jt.glide(keys_palm, t - 0.04)
        b = b / np.linalg.norm(b)
        turn = jt.hand_turn(ch, "right", -b, jt.flat_palm(b, palm))
        st.hand("shinza", "right", f, jt.fist_wrist(ch, "right", p, turn), turn, jt.keys_at(poles, t))
        swing = jt.ramp(t, CLEAR - 0.05, SWING[-2][0])
        body = jt.shinza_stand(t, reach=1.0 - swing, chin=0.6 * jt.ramp(t, *PULL) - 0.9 * jt.ramp(t, *NARROW))
        body["spine"] = (body["spine"][0] + 7.0 * swing, 0.0, body["spine"][2] - 8.0 * swing)
        body["leftShoulder"] = (0.0, -6.0 * jt.ramp(t, *PULL) * (1 - swing), 0.0)   # dropping: the scabbard drawn down
        # his left hand: from his side back to the scabbard, drawing it down with the pull, and away again
        on = jt.ramp(t, *LEFT_TAKE) * (1 - jt.ramp(t, *LEFT_FREE))
        slide = SLIDE * jt.ramp(t, *PULL) * (1 - jt.ramp(t, CLEAR + 0.2, CLEAR + 0.9))
        held = jt.fist_wrist(ch, "left", saya - u * slide, saya_turn)
        side_w = np.asarray(jt.SIDE["wrist"]) + (0.0, 0.04 * jt.ramp(t, *LEFT_FREE), 0.0)
        # (off the scabbard it swings out a little on its way, the path bowed away from his hip)
        bow = np.array((0.06, 0.0, 0.03)) * np.sin(np.pi * on)
        st.hand("shinza", "left", f, tuple(side_w + (held - side_w) * on + bow),
                jt.slerp_turn(side_turn, saya_turn, on), np.asarray(jt.SIDE["pole"]) * (1 - on) + SAYA_POLE * on)
        curl = 0.55 + 0.15 * jt.follow(t, *LEFT_FREE, lag=0.05, over=0.15)     # (demand left it half closed)
        left = jt.blend_hand(jt.blend_hand(jt.relaxed("left"), jt.fingers("left", 0.8), curl), jt.fingers("left", 0.95),
                             jt.follow(t, LEFT_TAKE[1] - 0.05, LEFT_TAKE[1] + 0.05, lag=0.0, over=0.1)
                             * (1 - jt.ramp(t, LEFT_FREE[0] - 0.05, LEFT_FREE[0] + 0.1)))
        st.pose("shinza", f, {**body, **jt.fingers("right", 1.0), **left}, hips=jt.shinza_hips(t))
        st.face("shinza", f, {"glare": 0.4, "s4-grin": jt.ramp(t, *GRIN), "narrow": 0.7 * jt.ramp(t, *NARROW)})


def slide_scabbard(st):
    """The scabbard drawn down its own line by SLIDE as the blade comes up out of it (carried by his upper chest: its
    offset keyed in that bone's space), and back up after."""
    from mathutils import Vector

    sheath = st.cast["shinza"]["parts"]["sheath"][0]
    st.ctx.scene.frame_set(st.ctx.f0)
    m = sheath.matrix_world @ sheath.matrix_basis.inverted()
    ch = st.cast["shinza"]["vrm"]
    guard, u = jt.hilt_axis(st)
    down_world = np.array(ch.world(guard - u)) - np.array(ch.world(guard))
    down_local = np.array(m.to_3x3().inverted() @ Vector(tuple(down_world)))
    base = np.array(sheath.location)
    for f in st.frames():
        t = st.t(f)
        k = SLIDE * jt.ramp(t, *PULL) * (1 - jt.ramp(t, CLEAR + 0.2, CLEAR + 0.9))
        sheath.location = tuple(base + down_local * k)
        sheath.keyframe_insert("location", frame=f)
