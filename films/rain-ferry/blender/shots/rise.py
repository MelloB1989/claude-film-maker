"""Shot 13, rise (55.6-59.6 s): from where draw left them (rf/jetty_talk.py's marks: Tsuru on her crate at the
jetty's end, her pipe over her left knee, her head turned up to him; Shinza over her with the nodachi out in one hand,
its point down toward her). A held breath; then she stands, unhurried, her back straightening, and turns from him as
if he were not there: "So young." (line 10, +1.2 to +3.2 s), said over her shoulder as she takes two short steps to
the jetty's edge by the boat. Her pole lies out of the boat against the tap post; she takes it, lifts it up out of the
boat, upright, and sets its foot down on the deck at her right side (+3.1 s). Only then does she come round to him,
her body twisting from her planted feet, the pole in her fist, her head turning back to him, the corner of her mouth
going up.

The camera is on the river side (-y): the two of them whole at first, he at the left with his blade's point down
toward her; it creeps in and turns with her to the edge, leaving him at the frame's left, and she is in back
three-quarters as she goes, her face coming round to us over her shoulder at the end.

Her performance is lib/vrm_anim.py's (stand, walk, grasp, carry, look, say); his is draw's last pose held, breathing
(rf/jetty_talk.py's helpers, as shots/draw.py keys it).

    blender -b -P blender/render.py -- --film rain-ferry --shot rise --mode look --engine eevee \\
        --frames 1335,1365,1390,1415,1430 --res 960x540
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rf import jetty_talk as jt  # noqa: E402

SHOT = {"scene": "rise"}

# her acting (s into the shot)
HOLD = 0.3              # the held breath
UP = (0.3, 1.1)         # standing: the hips up over her feet ...
FORWARD = 0.36          # ... the root this far forward over them (m)
WALK = 1.1              # two short steps to the edge by the boat, turning to it
EDGE = (7.12, 0.42)     # where she stops (world), facing the pole (degrees)
EDGE_YAW = 72.0
GRAB = (2.15, 2.5)      # bending to the pole and taking it
LIFT = (2.5, 3.1)       # up out of the boat, upright; its foot down on the deck at her right side
TURN = (3.05, 3.7)      # then, the pole held, her body twisting round toward him (her frame's turns, + to her left)
TWIST = {"spine": (0.0, 0.0, 18.0), "chest": (0.0, 0.0, 18.0), "upperChest": (0.0, 0.0, 14.0), "neck": (0.0, 0.0, 12.0)}
TURN_BACK = 3.05        # her head back to him
SMILE = (3.45, 3.95)
LINE = "L10"
# the pole leaning out of the boat against the tap post (world): its foot in the boat, where it lies on the post;
# where she takes it (along it from the foot, m), and where its foot comes down by her (world)
POLE_FOOT0 = (6.78, 2.02, -0.24)
POLE_REST = (7.36, 1.17, 0.72)
GRIP_ALONG = 1.0
POLE_FOOT1 = (7.42, 0.45, 0.0)
# half way up (world): the foot clear of the boat's side and the deck's edge, the pole tipping toward upright
GRIP_MID, WAY_MID = (7.32, 0.85, 1.05), (0.1, -0.35, 0.93)
# her body getting up (her frame's turns, added to the stoop she stands in): leaning over her feet
LEAN = {"spine": (22.0, 0.0, 0.0), "chest": (12.0, 0.0, 0.0), "neck": (-6.0, 0.0, 0.0)}
BEND = {"spine": (20.0, 0.0, 0.0), "chest": (20.0, 0.0, -6.0), "upperChest": (18.0, 0.0, -4.0), "neck": (14.0, 0.0, 0.0),
        "head": (-40.0, 0.0, 0.0)}
# her pipe hand once she is up: the fist at her hip, the bowl forward and down (her frame: fist, along)
PIPE_UP = ((0.15, -0.17, 0.9), (-0.25, -1.0, -0.35))
# the camera on the -y side: first the two of them whole, his blade's point down toward her; it creeps in and turns
# with her to the edge, leaving him at the frame's left (world: at, aim)
CAMERA = [((5.9, -3.6, 1.25), (6.55, -0.9, 1.12)),
          ((5.95, -3.48, 1.27), (6.72, -0.55, 1.2)),
          ((6.05, -3.3, 1.3), (6.88, 0.2, 1.32))]
LENS = (30.0, 34.0)
GRIP = jt.HILT_GRIP     # his fist on the hilt from its guard, as draw closes it
# draw's last frame (shots/draw.py SWING[-1]): his blade's way, his fist, his palm (his frame)
DRAWN = ((0.2, -0.78, -0.58), (-0.3, -0.38, 1.33), (1.0, 0.0, -0.3))


def build(ctx):
    import bpy

    from lib import cinema, vrm_anim as va
    from rf import vroid_tsuru
    from rf.vroid_common import move

    st = jt.stage(ctx)
    jt.compose_faces(st)
    ts, sh = st.cast["tsuru"], st.cast["shinza"]
    tch, sch = ts["vrm"], sh["vrm"]
    fps = ctx.fps

    def F(s):
        """Shot seconds to a film frame."""
        return ctx.f0 + s * fps

    # ---- him: draw's last frame held, breathing; his eyes follow her up
    b = np.asarray(DRAWN[0]) / np.linalg.norm(DRAWN[0])
    turn = jt.hand_turn(sch, "right", -b, jt.flat_palm(b, DRAWN[2]))
    for f in st.frames():
        t = st.t(f) + 3.8
        st.hand("shinza", "right", f, jt.fist_wrist(sch, "right", DRAWN[1], turn), turn, (-0.55, 0.25, 1.05))
        body = jt.shinza_stand(t, reach=0.0, chin=-0.3)
        body["spine"] = (body["spine"][0] + 7.0, 0.0, body["spine"][2] - 8.0)
        follow = jt.ramp(st.t(f), UP[0], UP[1] + 0.3)
        body["head"] = (body["head"][0] - 14.0 * follow, 0.0, body["head"][2])
        st.pose("shinza", f, {**body, **jt.fingers("right", 1.0), **jt.fingers("left", 0.9)}, hips=jt.shinza_hips(t))
        st.hand("shinza", "left", f, jt.HANG["left"], jt.hand_turn(sch, "left", (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),
                (0.3, 0.5, 1.2))
        st.face("shinza", f, {"glare": 0.4, "s4-grin": 1.0 - 0.6 * jt.ramp(st.t(f), 1.4, 2.6), "narrow": 0.7})

    # ---- the pole: out of the boat, leaning on the tap post
    shaft = ts["parts"]["pole"][0]
    # its handle (the cord, the hidden blade) rides on the shaft from here, so the pole moves and is carried whole
    bpy.context.view_layer.update()
    for handle in ts["parts"]["handle"][:1]:
        keep = handle.matrix_world.copy()
        handle.parent = shaft
        handle.matrix_world = keep
    foot0 = np.array(POLE_FOOT0)
    way0 = np.array(POLE_REST) - foot0
    way0 /= np.linalg.norm(way0)
    co = np.array([shaft.matrix_world @ v.co for v in shaft.data.vertices])
    lo, hi = co[co[:, 2].argmin()], co[co[:, 2].argmax()]
    move(shaft, lo, hi - lo, foot0, way0)
    p = st.perf["tsuru"]
    p.carry(shaft, F(0) - 1, None)          # left where it lies as she walks (not carried by her root)
    grip0 = foot0 + way0 * GRIP_ALONG
    grip1 = np.array(POLE_FOOT1) + np.array((0.0, 0.0, GRIP_ALONG))
    way_mid = np.asarray(WAY_MID) / np.linalg.norm(WAY_MID)

    # ---- her performance (lib/vrm_anim.py, the stage's), from the builder's seated pose
    root0 = np.array(ts["root"].location)
    yaw0 = math.degrees(ts["root"].rotation_euler[2])
    ahead = np.array((math.cos(math.radians(yaw0)), math.sin(math.radians(yaw0)), 0.0))
    p.root(F(0), root0, yaw=yaw0)
    p.plant_feet(F(0))
    p.look(F(0), st.perf["shinza"].face_at)
    # seated as draw left her (jetty_talk.tsuru_rest: her pipe over her left knee, her right hand on her knee)
    for f in st.frames():
        if st.t(f) <= HOLD:
            jt.tsuru_rest(st, f, st.t(f))
    p.root(F(HOLD), root0, yaw=yaw0)
    # standing: up over her feet into the stoop she stands in, leaning into it on the way
    stand = {k: v for k, v in vroid_tsuru.TS_POSE.items() if not any(n in k for n in ("Index", "Middle", "Ring", "Little"))}
    lean = {**stand, **{k: tuple(a + c for a, c in zip(stand.get(k, (0, 0, 0)), v)) for k, v in LEAN.items()}}
    p.pose(F((UP[0] + UP[1]) / 2), lean, hips=(0.0, -0.06, -0.12), ease="in", full=False)
    p.pose(F(UP[1]), stand, hips=vroid_tsuru.TS_HIPS, ease="out", full=False)
    p.root(F(UP[1]), root0 + ahead * FORWARD, yaw=yaw0)
    # her hands as she comes up: the pipe to her hip, the right hand off her knee to hang
    for f in (F(UP[1]), ctx.f1 + 1):
        jt.hold_pipe(st, f, *PIPE_UP)
    st.hand("tsuru", "right", F(UP[1]), jt.HANG["right"],
            jt.hand_turn(tch, "right", (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)), (-0.3, 0.5, 1.2))
    # she looks away from him as she turns to go: dismissed
    p.look(F(WALK), None)
    end = p.walk([tuple(EDGE)], F(WALK), gait=va.GAITS["old"].but(stride=0.42), pose=stand, end_pose=stand,
                 end_yaw=EDGE_YAW, swing=(0.0, 0.4))
    print(f"rise: her walk to the edge ends at +{(end - ctx.f0) / fps:.2f} s (she takes the pole at +{GRAB[0]} s)")
    # bent to the pole and taking it, lifting it upright, setting it down beside her
    p.pose(F(GRAB[1]), {**stand, **BEND}, hips=(0.0, 0.06, -0.12), full=False)
    p.pose(F(LIFT[1]), stand, hips=vroid_tsuru.TS_HIPS, ease="out", full=False)

    def char(w, s):
        root, yaw = p.root_at(F(s))
        return va.to_char(np.asarray(w, float), root, yaw)

    def char_dir(d, s):
        root, yaw = p.root_at(F(s))
        return va.to_char(root + np.asarray(d, float), root, yaw) - va.to_char(root, root, yaw)

    palm, elbow = (1.0, 0.0, 0.0), (-0.5, 0.3, 0.6)
    p.grasp(F(GRAB[0]), "right", char(grip0 + np.array((0.0, -0.25, 0.25)), GRAB[0]), char_dir(way0, GRAB[0]), palm,
            pole=elbow, amount=0.4)
    p.grasp(F(GRAB[1]), "right", char(grip0, GRAB[1]), char_dir(way0, GRAB[1]), palm, pole=elbow)
    p.carry(shaft, F(GRAB[1]), "rightHand")
    t_mid = (LIFT[0] + LIFT[1]) / 2
    p.grasp(F(t_mid), "right", char(GRIP_MID, t_mid), char_dir(way_mid, t_mid), palm, pole=elbow, ease="in")
    p.grasp(F(LIFT[1]), "right", char(grip1, LIFT[1]), (0.0, 0.0, 1.0), palm, pole=(-0.5, 0.4, 0.6), ease="settle")
    # then round toward him, her feet planted, the pole in her fist
    twisted = {**stand, **{k: tuple(a + c for a, c in zip(stand.get(k, (0, 0, 0)), v)) for k, v in TWIST.items()}}
    p.pose(F(TURN[0]), stand, hips=vroid_tsuru.TS_HIPS, full=False)
    p.pose(F(TURN[1]), twisted, hips=vroid_tsuru.TS_HIPS, ease="out", full=False)
    # and her head back to him
    p.look(F(TURN_BACK), st.perf["shinza"].face_at, lag=1.4)
    # her face: calm; the line said over her shoulder; the smile after it
    line = st.line(LINE)[LINE]
    p.express(F(0), {"s4-calm": 1.0, "s4-smile": 0.0})
    p.say(st.start + line[0], st.start + line[1], "wakai neee", energy=0.75)
    p.express(F(SMILE[0]), {"s4-smile": 0.0})
    p.express(F(SMILE[1]), {"s4-smile": 0.8})
    p.blinks(seed=5, mean=3.2)
    p.breathe(rate=0.22, depth=0.8)
    st.bake()
    sword_in_fist(st, b)

    # ---- the camera (lib/cinema.py) and the weather, the lines, the light
    st.film([cinema.Setup("rise", 0.0, cinema.path([c for c, _ in CAMERA], [a for _, a in CAMERA]), lens=LENS,
                          fstop=3.2, focus=(tch, "head"),
                          shake=cinema.Shake(breath=0.06, hits=((LIFT[1] - 0.05, 0.25),)))])
    jt.outline(st)
    jt.key_light(st, "tsuru", (-0.9, -0.7, 0.7))
    jt.key_light(st, "shinza", (0.6, -1.0, 0.75))
    st.composite(lambda f: dict(rims=[((-1.0, 0.4), (0.95, 0.58, 0.26), 0.2, 0.0025, 0.9),
                                      ((0.6, 1.0), (0.6, 0.68, 0.85), 0.3, 0.003, 0.9)],
                                para_from=(0.3, 0.95), para_to=(0.85, 0.05)))
    bpy.context.view_layer.update()


def sword_in_fist(st, blade) -> None:
    """His nodachi out of its scabbard and in his right fist as draw ends (its hilt GRIP into the fist, the blade along
    `blade`, his frame), carried by the hand from the shot's first frame (as baked)."""
    import bpy
    from mathutils import Matrix, Vector

    from lib import vrm

    st.ctx.scene.frame_set(st.ctx.f0)
    bpy.context.view_layer.update()
    ch = st.cast["shinza"]["vrm"]
    sword = st.cast["shinza"]["parts"]["sword"][0]
    guard, u = jt.hilt_axis(st)                       # as sheathed (his frame)
    want_u = -np.asarray(blade, float)
    want = np.asarray(DRAWN[1], float) - want_u * GRIP
    g0, g1 = np.array(ch.world(guard)), np.array(ch.world(want))
    u0, u1 = np.array(ch.world(guard + u)) - g0, np.array(ch.world(want + want_u)) - g1
    turn = Vector(tuple(u0)).rotation_difference(Vector(tuple(u1))).to_matrix().to_4x4()
    sword.matrix_world = (Matrix.Translation(Vector(tuple(g1))) @ turn @ Matrix.Translation(Vector(tuple(-g0)))
                          @ sword.matrix_world)
    vrm.attach(sword, ch, "rightHand")
