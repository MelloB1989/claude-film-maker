"""Before the talk on the jetty: shots 6-8 (ferry, ask, refuse). Tsuru sits smoking where rf/jetty_talk.py seats her
(its stage builds the world, the cast and the compositing for these shots too, so the scene is one from the wide to
the draw); Shinza comes down the bank and up the jetty to his mark behind her, and stops. What these shots add to
that stage is here: his walk to his mark timed to stop when the shot needs him still (`arrives`: a lib/vrm_anim.py
Performance) and the smoke she lets out of her lips
(`lips_source`, `breath`).
"""
from __future__ import annotations

import math

import numpy as np

from . import jetty_talk as jt

# where Shinza walks from in ask (world x, y: up the jetty from its middle) to his mark (jetty_talk's)
ASK_FROM = (1.2, -0.62)
SMOKE = 1.4         # the smoke's colour: the fog's (the look schedule's light) lifted this much


def lips_source(st, pose: dict, hips):
    """A function of the film frame giving where Tsuru's lips are (world), carried by her head: where
    jetty_talk.pipe_at_lips puts the pipe's mouthpiece, with her head as `pose` holds it. Smoke let out of them."""
    from mathutils import Vector

    ch = st.cast["tsuru"]["vrm"]
    fist, way = jt.pipe_at_lips(st, pose, hips)            # (it poses her so: the head is where `pose` has it)
    lips = np.asarray(fist) - np.asarray(way) * 0.09
    p = Vector(ch.world(lips))
    local = (ch.armature.matrix_world @ ch.bone("head").matrix).inverted() @ p

    def at(_frame):
        return np.array(ch.armature.matrix_world @ ch.bone("head").matrix @ local)
    return at


def breath(st, emit, source, *, push: float = 0.3, seed: int = 8, width=(0.008, 0.08),
           opacity: float = 0.55):
    """Smoke let out of her lips (`source`: lips_source) in the windows `emit` (s into the shot), pushed out ahead of
    her, the rain beating it down (lib/smoke.py); bake it last."""
    from lib import smoke

    s = st.ctx.look_at(st.ctx.f0)
    f = np.array((math.cos(math.radians(jt.TSURU_FACING)), math.sin(math.radians(jt.TSURU_FACING)), 0.0))
    wisp = smoke.Wisp(rain=min(1.0, s.rain.density), wind=(0.05, 0.03, 0.0), push=tuple(f * push + (0.0, 0.0, 0.03)),
                      width=width, life=2.2, rise=0.11, curl=0.07, opacity=opacity, rate=48.0,
                      emit=tuple((st.start + a, st.start + b) for a, b in emit), seed=seed)
    return smoke.ribbon("breath", wisp, source=source, coll=st.crossing["near"], also=(st.cast_coll,),
                        color=tuple(np.array(s.light.fog) * SMOKE))


# ---------------------------------------------------------------------------------------------------- acting (lib/vrm_anim.py)

# Shinza walking: leaning into his stride under the kasa, his head down; stopped: upright, his chin up to her
WALK_POSE = {"spine": (5.0, 0.0, 0.0), "chest": (2.0, 0.0, 0.0), "neck": (4.0, 0.0, 0.0), "head": (6.0, 0.0, 0.0)}
STOP_POSE = {"spine": (0.0, 0.0, 0.0), "chest": (-2.0, 0.0, 0.0), "neck": (2.0, 0.0, 0.0), "head": (2.0, 0.0, 0.0)}


def arrives(st, path, stop: float, *, gait: str = "heavy", end_yaw: float | None = None, ground=0.0,
            seed: int = 1):
    """Shinza's Performance (lib/vrm_anim.py) walking `path` (world x, y; from its first point) with `gait`, timed
    to stand still at `stop` (s into the shot), turning to `end_yaw` (degrees; default facing her mark from his), on
    `ground` (a height, or a function (x, y) -> z: every footfall lands on it).
    His builder's IK is let go first (the walk plants his feet), and the Performance made from there takes the stage's
    place (st.perf["shinza"], baked by st.bake). Returns (Performance, the film frame he stops on); the shot adds his
    look, face and line."""
    from lib import vrm, vrm_anim as va, vrm_rig

    ch = st.cast["shinza"]["vrm"]
    vrm.pose(ch, vrm_rig.release(ch))
    fps = st.ctx.fps
    p = st.perf["shinza"] = va.Performance(ch, fps=fps, seed=seed)
    pts = np.asarray(path, float)
    dist = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
    speed = va.gait_of(gait).scaled(p.height).speed
    stop_f = st.ctx.f0 + round(stop * fps)
    start_f = stop_f - round((dist / speed + 0.7) * fps)        # (its first step and its closing step take longer)
    way = pts[1] - pts[0]
    z0 = float(ground(*pts[0])) if callable(ground) else float(ground)
    p.root(start_f, (pts[0][0], pts[0][1], z0), yaw=math.degrees(math.atan2(way[1], way[0])), ease="hold")
    yaw = jt.SHINZA_FACING if end_yaw is None else end_yaw
    end = p.walk([tuple(q) for q in pts], start_f, gait=gait, pose={**va.STAND, **WALK_POSE},
                 end_pose={**va.STAND, **STOP_POSE}, end_yaw=yaw, ground=ground)
    print(f"jetty_arrive: Shinza sets off on {start_f}, stops on {end} (asked {stop_f})")
    return p, end



# the smoke off her pipe's bowl: thin, but light enough against the grey air to read as smoke (the fog lifted this much)
BOWL = dict(opacity=0.65, width=(0.003, 0.045))
BOWL_LIGHT = 1.45


def smoking(st, f: int, t: float, *, at_lips: float = 1.0, **sit) -> None:
    """Key Tsuru on her crate with the pipe at her lips (`at_lips` 1) or over her left knee (0), and between, the
    hand travelling out in front of her chin rather than through it, the elbow and palm turning from one hold to the
    other (jetty_talk's PIPE_ARM); her right hand on her knee, her face calm."""
    pose = {**jt.tsuru_sit(t, **sit), **jt.fingers("left", 0.85), **jt.fingers("right", 0.35)}
    hips = jt.tsuru_hips(st, t)
    lips, lips_way = jt.pipe_at_lips(st, pose, hips)
    lap, lap_way = (np.asarray(v, float) for v in jt.TS_PIPE_LAP)
    k = min(1.0, max(0.0, at_lips))
    point = lap + (np.asarray(lips) - lap) * k + np.array((0.03, -0.07, 0.0)) * math.sin(math.pi * k)
    along = lap_way + (np.asarray(lips_way) - lap_way) * k
    d = along / np.linalg.norm(along)
    pole0, palm0 = (np.asarray(v, float) for v in jt.PIPE_ARM["lap"])
    pole1, palm1 = (np.asarray(v, float) for v in jt.PIPE_ARM["lips"])
    st.pose("tsuru", f, pose, hips=hips)
    st.grip("tsuru", "left", f, point, -d, jt.flat_palm(d, palm0 + (palm1 - palm0) * k), pole0 + (pole1 - pole0) * k)
    jt.knee_hand(st, f)
    st.face("tsuru", f, {"s4-calm": 1.0})


def bowl_smoke(st, *, seed: int = 4, **wisp):
    """The thread off her pipe's bowl (lib/smoke.py), beaten down by the shot's rain, linked into the cast's layer
    too so it passes in front of her; `wisp` overrides BOWL and smoke.Wisp's own. Bake it last."""
    from lib import smoke

    bowl = st.cast["tsuru"]["parts"]["pipe"][-1]
    co = np.array([v.co for v in bowl.data.vertices])
    top = co[co[:, 2] >= co[:, 2].max() - 0.002].mean(axis=0)     # the bowl's mouth, in its own axes
    s = st.ctx.look_at(st.ctx.f0)
    w = smoke.Wisp(rain=min(1.0, s.rain.density), wind=(0.05, 0.03, 0.0), seed=seed, **{**BOWL, **wisp})
    return smoke.ribbon("pipe-smoke", w, source=bowl, offset=tuple(top), coll=st.crossing["near"],
                        also=(st.cast_coll,), color=tuple(np.minimum(np.array(s.light.fog) * BOWL_LIGHT, 1.0)))
