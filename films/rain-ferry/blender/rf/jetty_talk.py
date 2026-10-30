"""The talk on the jetty: shots 9-12 (demand, tap, look, draw), one scene cut four ways. Tsuru sits on a low crate
near the jetty's end, turned out past its last post toward the open river, her kiseru in her left hand; Shinza stands
two paces behind her right shoulder, his nodachi sheathed across his back and his kasa hanging on it. Every camera
stays on the river side of the line between them (-y of it: rf/sets.py's world), so he is always at the left of the
frame and she at the right, as in the standoff that follows.

`stage(ctx, ...)` builds what the four share: the world (rf/set_world.py) lit at the shot's place in the look schedule
(ctx.look_at), the 3D cast (rf/vroid_cast.py's variants: Shinza standing with his sword and kasa on
his back, Tsuru seated with her pipe in hand and her pole laid in the boat), placed (`place_cast`) and painted as the
standoff paints them (shots/standoff.py TONES3D), and the compositing. A shot then keys its performance frame by frame
through the `Stage` (`pose`, `grip`, `hand`, `face`, `say`: blender/lib/vrm_anim.py Performances, `bake`d), films it
(`Stage.film`: blender/lib/cinema.py setups and weather.storm's rain round them) and composites it (`Stage.composite`).

The performance is timed to the dialogue (data/dialogue_timing.json, `Stage.line`) and to the sound cues (data/mix.json:
the pipe's taps at 42.05 s, the draw's steel at 51.95 s). The pure halves (easing, keys, the camera's breath) need no Blender.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------------------------------- the staging

# where each stands (world x, y: the jetty along x, its end at +x, the river beyond toward +y) and which way they face
# (degrees from +x toward +y). She is turned out past the end post, which stands before her left knee (her pipe's
# post); he faces her
TSURU_AT, TSURU_FACING = (7.08, -0.7), -100.0     # the post at her front left, clear of her knees, in her pipe's reach
SHINZA_AT = (5.45, -0.82)
SHINZA_FACING = math.degrees(math.atan2(TSURU_AT[1] - SHINZA_AT[1], TSURU_AT[0] - SHINZA_AT[0]))
CRATE = (0.42, 0.34)        # her seat's width and depth (its height is rf/vroid_tsuru.py's SEAT); its middle behind her
CRATE_BACK = 0.14           # ... feet (m)
BOAT_POLE = ((4.05, 2.32, -0.13), (1.0, 0.03, 0.04))   # her pole laid in the boat: its foot, its way (world)

# the cast's variants in this scene (rf/vroid_cast.py)
VARIANT = {"shinza": dict(kasa="back", sword="back", pose="stand"),
           "tsuru": dict(pipe="hand", pole="boat", seated=True)}

LINES = Path(__file__).resolve().parents[2] / "data" / "dialogue_timing.json"


# ---------------------------------------------------------------------------------------------------- pure halves

def ease(u: float) -> float:
    """In-out sine on 0..1, held outside it."""
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def ramp(t: float, a: float, b: float) -> float:
    """0 before a, 1 after b, eased between."""
    return ease((t - a) / (b - a)) if b > a else float(t >= a)


def keys_at(keys, t: float):
    """A value from [(t, value), ...] (times rising; a value is a number or a tuple), eased in-out between keys and
    held before the first and after the last."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            k = ease((t - t0) / (t1 - t0)) if t1 > t0 else 1.0
            if isinstance(v0, (int, float)):
                return v0 + (v1 - v0) * k
            return tuple(a + (b - a) * k for a, b in zip(v0, v1))
    return keys[-1][1]


def bearing(a, b) -> float:
    """Degrees from +x toward +y of the way from a to b (x, y)."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def side_of_line(p, a=SHINZA_AT, b=TSURU_AT) -> float:
    """Which side of the line from a to b the point p lies: negative on the river cameras' side (-y of it)."""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def line_spans(shot_start: float, ids, path: Path = LINES) -> dict:
    """{line id: (start, end)} s from the shot's start, from the film's dialogue timing."""
    rows = {r["id"]: r for r in json.loads(Path(path).read_text())}
    return {i: (rows[i]["start"] - shot_start, rows[i]["end"] - shot_start) for i in ids}


def glide(keys, t: float) -> tuple:
    """A point from [(t, (x, y, z)), ...] (times rising) on a smooth path through every key: easing out of the first
    and into the last, but carried through the ones between without stopping (a hand's arc, not keys_at's stop at
    each). Cubic Hermite with time-scaled tangents (C1); held outside the keys."""
    if t <= keys[0][0]:
        return tuple(keys[0][1])
    if t >= keys[-1][0]:
        return tuple(keys[-1][1])
    ts = [k[0] for k in keys]
    ps = [np.asarray(k[1], float) for k in keys]
    n = len(keys)

    def tangent(i):
        if i == 0 or i == n - 1:
            return np.zeros_like(ps[i])
        return (ps[i + 1] - ps[i - 1]) / (ts[i + 1] - ts[i - 1])

    i = max(j for j in range(n - 1) if ts[j] <= t)
    h = ts[i + 1] - ts[i]
    u = (t - ts[i]) / h
    h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
    p = h00 * ps[i] + h10 * h * tangent(i) + h01 * ps[i + 1] + h11 * h * tangent(i + 1)
    return tuple(float(v) for v in p)


def follow(t: float, a: float, b: float, *, lag: float = 0.06, over: float = 0.12) -> float:
    """0 before a, 1 after b like `ramp`, but dragging `lag` s behind and swinging `over` past 1 as it arrives, back
    on 1 half the move's length later: a wrist or fingers following the arm that carries them (overlap and
    follow-through). Smooth (C1) all through."""
    if b <= a:
        return float(t >= a + lag)
    u = (t - a - lag) / (b - a)
    bump = math.sin(math.pi * (u - 0.5)) ** 2 if 0.5 < u < 1.5 else 0.0
    return ease(u) + over * bump


def relaxed(side: str, amount: float = 1.0) -> dict:
    """A hand at rest, not a mannequin's flat one: each finger curled a little more than the one before it (index
    least, little most), the thumb soft beside the index, by `amount` (vrm.pose's turns, from a T-pose's flat hand)."""
    s = 1.0 if side == "left" else -1.0
    out = {}
    for finger, (p, i, d) in {"Index": (14.0, 18.0, 10.0), "Middle": (20.0, 26.0, 14.0),
                              "Ring": (26.0, 31.0, 17.0), "Little": (32.0, 36.0, 20.0)}.items():
        for joint, deg in (("Proximal", p), ("Intermediate", i), ("Distal", d)):
            out[f"{side}{finger}{joint}"] = (0.0, s * deg * amount, 0.0)
    out[f"{side}ThumbMetacarpal"] = (0.0, s * 6.0 * amount, s * 16.0 * amount)
    out[f"{side}ThumbProximal"] = (0.0, s * 12.0 * amount, s * 6.0 * amount)
    out[f"{side}ThumbDistal"] = (0.0, s * 16.0 * amount, 0.0)
    return out


def blend_hand(a: dict, b: dict, k: float) -> dict:
    """Between two hands' finger poses (each {bone: (x, y, z)}), by k (k past 1 overshoots: a hand closing hard)."""
    out = {}
    for name in set(a) | set(b):
        va, vb = np.asarray(a.get(name, (0.0, 0.0, 0.0)), float), np.asarray(b.get(name, (0.0, 0.0, 0.0)), float)
        out[name] = tuple(float(v) for v in va + (vb - va) * k)
    return out


# ---------------------------------------------------------------------------------------------------- Blender

def _standoff():
    """shots/standoff.py, for the 3D cast's paint (TONES3D, TONES3D_OF): one look for the cast across the film."""
    import importlib.util

    p = Path(__file__).resolve().parents[1] / "shots" / "standoff.py"
    spec = importlib.util.spec_from_file_location("shots.standoff", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _turn_z(deg: float) -> np.ndarray:
    a = math.radians(deg)
    return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])


def local(ch, p) -> np.ndarray:
    """A world point in the character's frame (Character.world's inverse)."""
    import bpy
    from mathutils import Vector

    bpy.context.view_layer.update()
    a = ch.armature.matrix_world.inverted() @ Vector(tuple(float(v) for v in p))
    return ch.frame.T @ np.array(a) * ch.scale


def local_dir(ch, d) -> np.ndarray:
    """A world direction in the character's frame."""
    o = local(ch, (0.0, 0.0, 0.0))
    return local(ch, d) - o


def hand_turn(ch, side: str, knuckles, palm) -> np.ndarray:
    """The turn (character frame) taking the hand at rest to knuckles running along `knuckles` (index to little) with
    its palm facing `palm`."""
    from lib import vrm

    k0, p0, _ = vrm.hand_rest(ch, side)
    return vrm.align(k0, p0, knuckles, palm)


def fist_wrist(ch, side: str, point, turn, depth: float = 0.028) -> np.ndarray:
    """Where the wrist goes for the fist (turned by `turn`) to hold something through `point` (vrm.grasp's hole)."""
    from lib import vrm

    _, p0, r0 = vrm.hand_rest(ch, side)
    return np.asarray(point, float) - turn @ (r0 * 0.85 + p0 * depth)


def post_top(st) -> np.ndarray:
    """Where her pipe knocks: the tap post's crown at its rim on her side (rf/set_jetty.py's "tap_post" anchor: the
    staved post at the -y end of the jetty), world."""
    from . import set_world

    return np.array(set_world.anchor(st.crossing, "tap_post"))


class Stage:
    """What `stage` built: the scene's pieces, the cast, the camera; keying the performance and the camera."""

    def __init__(self, ctx, **kw):
        import time

        self.ctx = ctx
        self._t0 = self._t = time.time()
        self.__dict__.update(kw)
        self.start, _ = ctx.timing.scene(ctx.shot if ctx.look is None else ctx.look.scene)
        self.held = []

    def tick(self, what: str) -> None:
        """Log how long the build's last step took (the build is budgeted: about a minute a shot)."""
        import time

        now = time.time()
        print(f"[{self.ctx.shot}] {what}: {now - self._t:.1f}s (build {now - self._t0:.1f}s)", flush=True)
        self._t = now

    # ---- time
    def t(self, f: int) -> float:
        """Seconds into the shot at film frame f."""
        return f / self.ctx.fps - self.start

    def frames(self):
        """Every film frame keyed: the shot's and one either side."""
        return range(self.ctx.f0 - 1, self.ctx.f1 + 1)

    def line(self, *ids) -> dict:
        return line_spans(self.start, ids)

    # ---- the performance (blender/lib/vrm_anim.py: one Performance a character, keyed here, baked by `bake`)
    def pose(self, who: str, f: int, turns: dict, hips=None) -> None:
        """Key the character's whole body at film frame f (vrm.pose's turns; held linearly to the next key)."""
        self.perf[who].pose(f, turns, hips=hips, ease="linear")

    def grip(self, who: str, side: str, f: int, point, knuckles, palm, pole, *, local_frame: bool = True,
             depth: float = 0.028) -> None:
        """Key the `side` hand closed round something through `point` (its knuckles along `knuckles`, palm facing
        `palm`), the elbow toward `pole`: all in the character's frame unless local_frame is False (world); `depth`
        how far out from the palm the thing held runs (vrm.grasp's: a hilt's; less for a thin stem)."""
        ch = self.cast[who]["vrm"]
        if not local_frame:
            point, pole = local(ch, point), local(ch, pole)
            knuckles, palm = local_dir(ch, knuckles), local_dir(ch, palm)
        turn = hand_turn(ch, side, knuckles, palm)
        self.hand(who, side, f, fist_wrist(ch, side, point, turn, depth), turn, pole)

    def hand(self, who: str, side: str, f: int, wrist, turn, pole) -> None:
        """Key the `side` hand's wrist at `wrist` turned by `turn` (vrm.align), the elbow toward `pole` (their frame)."""
        self.perf[who].reach(f, f"{side}Hand", ("char", tuple(float(v) for v in wrist)), pole=pole, turn=turn,
                             ease="linear")

    def face(self, who: str, f: int, weights: dict) -> None:
        """Key the character's expressions at film frame f (every one not named back to 0)."""
        self.perf[who].express(f, weights, ease="linear", full=True)

    def say(self, who: str, line: str, text: str, **kw) -> None:
        """Lip-sync a line of data/dialogue_timing.json (its romaji reading) on the character."""
        a, b = self.line(line)[line]
        self.perf[who].say(self.start + a, self.start + b, text, **kw)

    def blinks(self, who: str, times) -> None:
        """Blinks at these times (s into the shot), and none else."""
        for t in times:
            self.perf[who].blink_at(self.ctx.f0 + t * self.ctx.fps)

    def bake(self) -> None:
        """Write every performance as keys over the shot (and a frame either side)."""
        self.tick("performance keyed")
        for p in self.perf.values():
            p.bake(self.ctx.f0 - 1, self.ctx.f1 + 1)
        self.ctx.scene.frame_set(self.ctx.f0)
        self.tick("performances baked")

    # ---- the camera and the weather (blender/lib/cinema.py, weather.py)
    def film(self, setups, **storm):
        """The shot's camera through `setups` (cinema.Setup) and its weather round them (weather.storm: the look
        schedule's rain and mist, splashing on the deck, ringing the river); the drops in the cast's layer too, so those
        in front of a face stay in front of it. Call it once the performance is baked. Returns the cinema.Rig."""
        from lib import cinema, weather

        from . import sets

        self.rig = cinema.film(self.ctx, setups)
        deck = ((sets.SPAN[0], -sets.HALF + 0.05, 0.004), (sets.SPAN[1], sets.HALF - 0.05, 0.004))
        storm = {"splashes": [deck], "waters": self.crossing["waters"], "floor": sets.WATER_Z,
                 "lights": [self.crossing["key"]], **storm}
        self.tick("camera")
        self.sky = weather.storm(self.ctx, self.rig, **storm)
        self.tick("weather")
        if self.sky.rain is not None:
            for d in self.sky.rain.drops.values():
                self.cast_coll.objects.link(d.ob)
        return self.rig

    def head_at(self, who: str, f: int) -> np.ndarray:
        """Between the character's eyes at film frame f, as keyed."""
        self.ctx.scene.frame_set(f)
        return np.array(self.cast[who]["vrm"].face())

    # ---- the compositing
    def composite(self, setup) -> None:
        """The cast over the world through the look schedule's Look and the shot's own (`setup(f)`: rims, para)."""
        from lib import satsuei, toon

        for ob in self.held:
            ad = getattr(ob, "animation_data", None)
            if ad is not None and ad.action is not None:
                for fc in toon._fcurves(ad.action):
                    for kp in fc.keyframe_points:
                        kp.interpolation = "CONSTANT"
        self.tick("before compositing")
        comp = satsuei.setup(self.ctx.scene, self.cast_coll)
        for f in self.frames():
            s = self.ctx.look_at(f)
            own = setup(f)
            own["rims"] = tuple(satsuei.Rim(*r) for r in own.get("rims", ()))
            comp.key(f, s.look(**own))
        comp.hold()
        self.tick("composited")


def stage(ctx, *, who=("shinza", "tsuru"), ink: float = 0.0, lantern_near: float | None = None, variant: dict | None = None,
          place: dict | None = None) -> Stage:
    """The scene for one of the four shots: the world lit at the shot's place in the look schedule, the cast in `who`
    staged and painted (the camera and the weather come after the performance: Stage.film); `ink` is the near set's
    line art (m; 0, the default, none: it cost ~2/3 of a frame and the set
    carries its own painted edges; the cast keeps its outline); `lantern_near` dims the hut's lantern (an
    emission strength) for a shot it sits by a head in. `variant` ({name: {kwarg: value}}) changes a character's
    rf/vroid_cast.py variant over VARIANT's (ask: his kasa on, her pipe in her mouth); `place` ({name: (at, facing)
    or None}) stands a character elsewhere than this scene's mark, or (None) leaves it where it was built, for the
    shot to key (ask: he walks up)."""
    import sys

    import bpy
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import rig, toon, toon3d, vrm
    from rf import set_world, sets, vroid_cast

    scene = ctx.scene
    s = ctx.look_at(ctx.f0)
    scene.render.use_motion_blur = False
    # the world (rf/set_world.py): lit for the shot's place in the look schedule, its key sun in "world-light"
    crossing = set_world.build(ctx)
    look = crossing["look"]
    if ink:
        toon.ink("ink-near", crossing["near"], radius=ink, crease=150)
    if lantern_near is not None:
        crossing["materials"]["lantern"].node_tree.nodes["Emission"].inputs["Strength"].default_value = lantern_near
    key = crossing["key"]
    sun = key.data

    cast_coll = toon.collection("cast")
    cast_look = toon.Look(fog=look.fog, fog_near=look.fog_near, fog_far=look.fog_far, fog_max=look.fog_max,
                          fog_power=look.fog_power)
    so = _standoff()
    cast = {}
    for name in who:
        built = getattr(vroid_cast, name)(cast_coll, cast_look, **{**VARIANT[name], **(variant or {}).get(name, {})})
        cast[name] = built
        built["key"] = toon3d.key(f"{name}-key", [built["root"], *built["root"].children_recursive], (1.0, -0.3, 0.8),
                                  coll=cast_coll, angle=so.KEY3D_ANGLE, color=tuple(s.light.key))
        tones = {p: toon3d.Tone(**{**kw, **so.TONES3D_OF.get(name, {}).get(p, {})}) for p, kw in so.TONES3D.items()}
        vrm.anime(built["vrm"], tones, built["key"])
        vrm.smooth(built["vrm"])
    st = Stage(ctx, crossing=crossing, cast=cast, cast_coll=cast_coll, sun=sun, look=look, standoff=so)
    place_cast(st, place)
    st.tick("world and cast built")
    from lib import vrm_anim

    st.perf = {name: vrm_anim.Performance(built["vrm"], fps=ctx.fps, seed=11 + k) for k, (name, built) in
               enumerate(cast.items())}
    # the lantern swings in the wind all through
    lantern = crossing["lantern"]
    for f in st.frames():
        t = f / ctx.fps
        lantern.rotation_euler = (math.radians(4) * math.sin(2 * math.pi * 0.6 * t),
                                  math.radians(2) * math.sin(2 * math.pi * 0.45 * t + 1), 0)
        lantern.keyframe_insert("rotation_euler", frame=f)
    return st


def key_light(st: Stage, who: str, toward, f: int | None = None) -> None:
    """Aim a character's own key (world direction it shines from)."""
    from lib import toon3d

    toon3d.aim(st.cast[who]["key"], toward, frame=f)


def outline(st: Stage, frac: float = 0.0018) -> None:
    """Every character's outline a width on screen (frame heights) as the camera (st.rig) moves, keyed per frame."""
    from lib import vrm

    faces = {name: st.head_at(name, st.ctx.f0) for name in st.cast}
    for f in st.frames():
        pose = st.rig.pose(min(max(f, st.ctx.f0), st.ctx.f1 - 1))
        for name, built in st.cast.items():
            d = float(np.linalg.norm(np.asarray(pose.position) - faces[name]))
            vrm.key_outline(built["vrm"], vrm.outline_width(frac, d, pose.lens), f)


def slerp_turn(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    """Between two turns (3x3), by k."""
    from mathutils import Matrix

    qa, qb = Matrix(a.tolist()).to_quaternion(), Matrix(b.tolist()).to_quaternion()
    return np.array(qa.slerp(qb, k).to_matrix())


def turn_keys(keys, t: float) -> np.ndarray:
    """A turn from [(t, 3x3), ...], eased between keys like keys_at."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, a), (t1, b) in zip(keys, keys[1:]):
        if t <= t1:
            return slerp_turn(a, b, ease((t - t0) / (t1 - t0)) if t1 > t0 else 1.0)
    return keys[-1][1]


def flat_palm(along, toward=(1.0, 0.0, 0.0)) -> np.ndarray:
    """A palm facing `toward` made square to `along` (a fist round a hilt faces the blade's flat)."""
    d = np.asarray(along, float) / np.linalg.norm(along)
    p = np.asarray(toward, float) - d * np.dot(toward, d)
    return p / np.linalg.norm(p)


# ---------------------------------------------------------------------------------------------------- the cast

def place_cast(st: Stage, place: dict | None = None) -> None:
    """The cast where this scene has them: her on her crate turned out past the post, her pole in the boat; him
    behind her right shoulder, facing her. `place` overrides a mark ({name: (at, facing)}) or skips it (None)."""
    import bpy

    from lib import shapes

    from .vroid_common import move
    from .vroid_tsuru import SEAT

    marks = {"tsuru": (TSURU_AT, TSURU_FACING), "shinza": (SHINZA_AT, SHINZA_FACING), **(place or {})}
    for name, mark in marks.items():
        if name in st.cast and mark is not None:
            at, facing = mark
            root = st.cast[name]["root"]
            root.location = (at[0], at[1], 0.0)
            root.rotation_euler = (0.0, 0.0, math.radians(facing))
    bpy.context.view_layer.update()
    if "tsuru" in st.cast:
        t_at, t_facing = marks["tsuru"] or (TSURU_AT, TSURU_FACING)
        back = _turn_z(t_facing) @ np.array([-1.0, 0.0, 0.0])
        cx, cy = np.array(t_at) + back[:2] * CRATE_BACK
        shapes.box("crate", (cx, cy, SEAT / 2 - 0.012), (*CRATE, SEAT), material=st.crossing["materials"]["plank"],
                   coll=st.crossing["near"], rot_z=math.radians(t_facing) + 0.08)
        pole = st.cast["tsuru"]["parts"]["pole"]
        if pole:
            ob = pole[0]
            co = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
            lo, hi = co[co[:, 2].argmin()], co[co[:, 2].argmax()]
            move(ob, lo, hi - lo, BOAT_POLE[0], BOAT_POLE[1])
    bpy.context.view_layer.update()


def part_center(ob) -> np.ndarray:
    """The middle of a prop's mesh (world)."""
    import bpy

    bpy.context.view_layer.update()
    co = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
    return co.mean(axis=0)


def hilt_axis(st: Stage) -> tuple:
    """(guard, up the hilt to its pommel) of his sheathed nodachi, his frame (props.katana's pieces: blade, collar,
    guard, hilt, cap)."""
    ch = st.cast["shinza"]["vrm"]
    sword = st.cast["shinza"]["parts"]["sword"]
    guard = local(ch, part_center(next(o for o in sword if o.name.endswith("tsuba"))))
    cap = local(ch, part_center(next(o for o in sword if o.name.endswith("kashira"))))
    u = cap - guard
    return guard, u / np.linalg.norm(u)


def pipe_bowl(st: Stage) -> np.ndarray:
    """Her pipe's bowl (world), as posed now (props.kiseru: [stem, mouthpiece, neck, bowl])."""
    return part_center(st.cast["tsuru"]["parts"]["pipe"][-1])



# ---------------------------------------------------------------------------------------------------- performance

# where the hands hang at rest (each character's frame: x their left, y their back, z up; wrists)
HANG = {"right": (-0.21, -0.01, 0.97), "left": (0.21, -0.01, 0.97)}
# a standing man's hand at his side, not a mannequin's: the wrist in by his thigh and a little forward of it, the
# elbow soft and back (its pole), the palm turned in to the thigh and a touch back (the thumb forward), the knuckles
# running from the front of the thigh to its back (wrist, palm, knuckles, elbow pole; his frame, the left's)
SIDE = dict(wrist=(0.185, -0.055, 0.99), palm=(-0.85, 0.5, -0.05), knuckles=(0.5, 0.86, -0.12), pole=(0.3, 0.65, 1.2))
TS_KNEE_HAND = (-0.13, -0.24, 0.56)      # her right hand resting on her knee
TS_PIPE_LAP = ((0.12, -0.25, 0.62), (-0.2, -1.0, 0.05))   # her pipe resting over her left knee: (fist, along)


def fingers(side: str, curl: float) -> dict:
    """The fingers of a hand curled by `curl` (0 open .. 1 a fist round a hilt)."""
    from lib import vrm

    return vrm.grip_pose(side, curl, thumb=0.15 + 0.5 * curl)


def shinza_hips(t: float) -> tuple:
    """His hips: his weight settled on his back (left) foot, breathing."""
    return (0.018, 0.0, -0.012 + 0.002 * math.sin(2 * math.pi * t / 3.4))


def shinza_stand(t: float, *, look_out: float = 0.0, reach: float = 0.0, gust: float = 0.0, chin: float = 0.0) -> dict:
    """His body standing over her (his frame's turns, vrm.pose; legs as rf/vroid_shinza.py's STAND_POSE): chest out,
    his head down to her (she sits below him); `look_out` turns his head and eyes out to the far shore (his left),
    `reach` turns his chest and lifts his right shoulder as the hand goes to the hilt, `gust` leans his head from the
    wind, `chin` lifts it (defiance)."""
    from .vroid_shinza import STAND_POSE

    from lib import vrm

    br = math.sin(2 * math.pi * t / 3.4)
    legs = {k: v for k, v in STAND_POSE.items() if "Leg" in k or k == "hips"}
    return {
        **legs,
        # the elbows keyed folded as the IK will want them (the right well in for the hilt over his shoulder), so the
        # solver starts near its answer: from a straight forearm it settles with the elbow at the target
        "rightLowerArm": vrm.fold("rightLowerArm", 25.0 + 105.0 * reach),
        "leftLowerArm": vrm.fold("leftLowerArm", 15.0),
        "spine": (-2.0 + 0.6 * br, 0.0, 3.0),
        "chest": (-3.0 + 0.8 * br, 0.0, -7.0 * reach),
        "upperChest": (-2.0, 0.0, -4.0 * reach),
        "neck": (6.0 - 4.0 * look_out - 3.0 * chin, 0.0, 10.0 * look_out),
        "head": (12.0 - 9.0 * look_out - 3.0 * reach - 6.0 * chin, -1.5 * gust, 22.0 * look_out - 3.0 * reach),
        "leftEye": (7.0 - 9.0 * look_out, 0.0, 12.0 * look_out),
        "rightEye": (7.0 - 9.0 * look_out, 0.0, 12.0 * look_out),
        "rightShoulder": (0.0, 9.0 * reach, 0.0),
    }


HILT_GRIP = 0.17     # where his right fist closes on the hilt, up from the guard (m): mid-hilt, where his arm reaches
# his elbow with the fist on the hilt over his shoulder: up and forward of his shoulder, so the forearm reads going
# back to the hilt and the fist shows on it, not flung out sideways with the hand lost behind his head
HILT_POLE = (-0.5, -0.6, 1.7)

def hilt_grip(st: Stage, along: float = HILT_GRIP) -> tuple:
    """(wrist, turn) of his right fist on the hilt standing over his right shoulder, `along` up it from the guard: its
    knuckles up the hilt and its palm to the blade's flat (against his back), his frame."""
    ch = st.cast["shinza"]["vrm"]
    guard, u = hilt_axis(st)
    turn = hand_turn(ch, "right", u, flat_palm(u, (0.25, 1.0, 0.0)))
    return fist_wrist(ch, "right", guard + u * along, turn), turn


def side_hand(st: Stage, who: str, side: str, f: int, t: float, *, curl: float = 0.0, out=(0.0, 0.0, 0.0)) -> dict:
    """Key the `side` hand hanging easy at the character's side (SIDE, mirrored for the right), its wrist breathing with
    the body, moved by `out` (m, their frame); returns its fingers' pose: relaxed, closed toward a loose fist by `curl`
    (0..1, past 1 a hard one). Pose them with the body at f."""
    ch = st.cast[who]["vrm"]
    m = np.array((1.0 if side == "left" else -1.0, 1.0, 1.0))
    br = math.sin(2 * math.pi * t / 3.4)
    wrist = np.asarray(SIDE["wrist"]) * m + (0.0, -0.004 * br, 0.003 * br) + np.asarray(out, float)
    turn = hand_turn(ch, side, np.asarray(SIDE["knuckles"]) * m, np.asarray(SIDE["palm"]) * m)
    st.hand(who, side, f, wrist, turn, np.asarray(SIDE["pole"]) * m)
    return blend_hand(relaxed(side), fingers(side, 0.8), curl)


def shinza_hold(st: Stage, f: int, t: float, *, narrow: float = 0.6) -> None:
    """Shinza as demand leaves him: standing over her, his right fist on the hilt over his shoulder, glaring (for a
    shot he is in the back of)."""
    ch = st.cast["shinza"]["vrm"]
    wrist, turn = st.cast["shinza"].setdefault("hilt_grip", None) or (None, None)
    if wrist is None:
        from lib import vrm

        vrm.pose(ch, shinza_stand(0.0, reach=1.0), hips=shinza_hips(0.0))
        wrist, turn = st.cast["shinza"]["hilt_grip"] = hilt_grip(st)
    left = side_hand(st, "shinza", "left", f, t, curl=0.45)      # his free hand half closed: he means it
    st.pose("shinza", f, {**shinza_stand(t, reach=1.0), **fingers("right", 1.0), **left}, hips=shinza_hips(t))
    st.hand("shinza", "right", f, wrist, turn, HILT_POLE)
    st.face("shinza", f, {"glare": 1.0, "narrow": narrow})


def tsuru_sit(t: float, *, turn: float = 0.0, down: float = 0.0, eyes=(0.0, 0.0), lean: float = 0.0) -> dict:
    """Her body seated (her frame's turns, on rf/vroid_tsuru.py's SEATED_POSE): `turn` (degrees, + to her left) her
    head round, shared down her neck and back; `down` her head bowed (degrees); `eyes` (down, left) degrees; `lean`
    forward over her knees (degrees)."""
    from .vroid_tsuru import SEATED_POSE

    br = math.sin(2 * math.pi * t / 4.1)
    sp, ch, uc, nk, hd = (SEATED_POSE[k] for k in ("spine", "chest", "upperChest", "neck", "head"))
    return {
        **SEATED_POSE,
        "spine": (sp[0] + lean * 0.5 + 0.4 * br, 0.0, turn * 0.12),
        "chest": (ch[0] + lean * 0.5, 0.0, turn * 0.12),
        "upperChest": (uc[0] + 0.5 * br, 0.0, turn * 0.1),
        "neck": (nk[0] + down * 0.4, 0.0, turn * 0.26),
        "head": (hd[0] + down * 0.6, 0.0, hd[2] + turn * 0.4),
        "leftEye": (eyes[0], 0.0, eyes[1]),
        "rightEye": (eyes[0], 0.0, eyes[1]),
    }


def tsuru_hips(st: Stage, t: float) -> tuple:
    """Her hips on the crate (rf/vroid_tsuru.py's seated hips), breathing."""
    from .vroid_tsuru import SEAT

    ch = st.cast["tsuru"]["vrm"]
    return (0.0, 0.0, SEAT + 0.07 - ch.rest("leftUpperLeg")[2] + 0.0015 * math.sin(2 * math.pi * t / 4.1))


# her pipe hand's elbow pole and palm (her frame): low and back by her side with the pipe over her knee; with it at
# her lips the elbow down by her side and a little forward (S3's rf/jetty_arrive.py SMOKING_POLE, SMOKING_PALM), not up
# beside her head
PIPE_ARM = {"lap": ((0.45, 0.35, 0.35), (-0.5, 0.0, 0.8)), "lips": ((0.32, -0.18, 0.35), (-0.7, 0.1, 0.35)),
            "knock": ((0.6, 0.1, 0.55), (-0.5, 0.0, 0.8))}


# her kiseru's thin stem (props.kiseru's 4.3 mm) held in close to the palm's crease, not a hilt's fist away from it
PIPE_DEPTH, PIPE_RADIUS = 0.017, 0.0045


def pipe_fingers(st: Stage, side: str = "left") -> dict:
    """Her fingers closed round the pipe's thin stem where hold_pipe puts it (vrm_rig.wrap: each finger curled until
    it lies on the stem), the index a little looser along it and the little finger tucked, the thumb over it; worked
    out once a shot (pure arithmetic on her rest pose)."""
    from lib import vrm_rig

    cache = st.cast["tsuru"].setdefault("pipe_fingers", {})
    if side not in cache:
        ch = st.cast["tsuru"]["vrm"]
        w = vrm_rig.wrap(ch, side, PIPE_RADIUS, depth=PIPE_DEPTH, slack=0.007, thumb=0.75)
        from lib import vrm_anim as va

        cache[side] = {k: (va.matrix(va.slerp((1.0, 0.0, 0.0, 0.0), va.quat(v), 0.8)) if "Index" in k else v)
                       for k, v in w.items()}
    return cache[side]


def hold_pipe(st: Stage, f: int, point, along, arm: str = "lap", palm_turn=None) -> None:
    """Key Tsuru's left fist round her pipe through `point` along `along` (bowl-ward), her frame, her elbow and palm as
    PIPE_ARM[arm] has them (or (pole, palm) given as `palm_turn`: between two holds)."""
    d = np.asarray(along, float) / np.linalg.norm(along)
    pole, palm = palm_turn or PIPE_ARM[arm]
    st.grip("tsuru", "left", f, point, -d, flat_palm(d, palm), pole, depth=PIPE_DEPTH)


def knee_fingers() -> dict:
    """Her right hand's fingers over her knee: relaxed, a little more curled round it."""
    return relaxed("right", 1.25)


def knee_hand(st: Stage, f: int) -> None:
    """Her right hand resting on her right knee."""
    ch = st.cast["tsuru"]["vrm"]
    st.hand("tsuru", "right", f, TS_KNEE_HAND, hand_turn(ch, "right", (-1.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
            (-0.5, 0.6, 0.9))


def pipe_at_lips(st: Stage, pose: dict, hips) -> tuple:
    """(fist, along) for her pipe's mouthpiece at her lips, her head as `pose` holds it (her frame): from the left
    corner of her mouth forward, down and out (rf/vroid_tsuru.py's PIPE_MOUTH), her fist on the stem."""
    from lib import vrm

    from .vroid_tsuru import PIPE_MOUTH

    ch = st.cast["tsuru"]["vrm"]
    vrm.pose(ch, pose, hips=hips)
    eyes = local(ch, ch.face())
    head = np.array(ch.point("head", tail=True)) - np.array(ch.point("head"))
    up = local_dir(ch, head / np.linalg.norm(head))
    fwd = np.cross(up, (1.0, 0.0, 0.0))                  # her face's forward (-y at rest), tipped with her head
    lips = eyes - up * 0.07 + fwd / np.linalg.norm(fwd) * 0.035 + np.array((0.012, 0.0, 0.0))
    way = np.asarray(PIPE_MOUTH["way"], float)
    way /= np.linalg.norm(way)
    return lips + way * 0.09, way


def tsuru_rest(st: Stage, f: int, t: float, *, smoking: bool = False, **sit) -> None:
    """Tsuru still on her crate: her pipe resting over her left knee (or at her lips, `smoking`), her right hand on
    her right knee."""
    pose = {**tsuru_sit(t, **sit), **pipe_fingers(st), **knee_fingers()}
    hips = tsuru_hips(st, t)
    hold = TS_PIPE_LAP
    if smoking:     # worked out once (her head barely moves while she sits smoking): re-posing a VRM is slow
        if "lips" not in st.cast["tsuru"]:
            st.cast["tsuru"]["lips"] = pipe_at_lips(st, pose, hips)
        hold = st.cast["tsuru"]["lips"]
    st.pose("tsuru", f, pose, hips=hips)
    hold_pipe(st, f, *hold, arm="lips" if smoking else "lap")
    knee_hand(st, f)
    st.face("tsuru", f, {"s4-calm": 1.0})


def bake_smoke(st: Stage, ribbon, until: float | None = None) -> None:
    """Bake a ribbon (it steps the scene through every frame it covers: slow with the cast in) only up to `until`
    seconds into the shot when its smoke is gone by then."""
    f1 = st.ctx.f1 if until is None else min(st.ctx.f1, st.ctx.f0 + round(until * st.ctx.fps))
    ribbon.bake(st.ctx.scene, st.ctx.f0, f1, st.ctx.fps)
    st.tick("smoke")


def pipe_smoke(st: Stage, *, emit=None, seed: int = 4):
    """The wisp off her pipe's bowl (lib/smoke.py), beaten down by the shot's rain, in front of her face where it
    passes it (linked into the cast's layer too). Bake it last (`Ribbon.bake`), once everything is keyed."""
    from lib import smoke

    bowl = st.cast["tsuru"]["parts"]["pipe"][-1]
    co = np.array([v.co for v in bowl.data.vertices])
    top = co[co[:, 2] >= co[:, 2].max() - 0.002].mean(axis=0)     # the bowl's mouth, in its own axes
    s = st.ctx.look_at(st.ctx.f0)
    wisp = smoke.Wisp(rain=min(1.0, s.rain.density), wind=(0.05, 0.03, 0.0), emit=emit, seed=seed)
    return smoke.ribbon("pipe-smoke", wisp, source=bowl, offset=tuple(top), coll=st.crossing["near"],
                        also=(st.cast_coll,), color=tuple(np.array(s.light.fog) * 1.15))


def draw_sword(st: Stage) -> None:
    """His sword out of its scabbard into his right fist from the shot's first frame (vrm_anim's carry: declare it
    before the bake), handed on from the scabbard that carries it."""
    st.perf["shinza"].carry(st.cast["shinza"]["parts"]["sword"][0], st.ctx.f0, "rightHand")


# ---------------------------------------------------------------------------------------------------- faces

def compose_faces(st: Stage) -> None:
    """The scene's own expressions, of the faces' shape keys (lib/vrm_rig.py compose): his grin (VRoid's fierce mouth
    under the glaring brows) and her calm without the shut mouth (so she can speak) and her faint smile."""
    from lib import vrm_rig

    if "shinza" in st.cast:
        vrm_rig.compose(st.cast["shinza"]["vrm"], "s4-grin", {"Fcl_MTH_Angry": 0.55, "Fcl_MTH_Fun": 0.3,
                                                              "Fcl_EYE_Angry": 0.3, "Fcl_BRW_Angry": 0.7})
    if "tsuru" in st.cast:
        ch = st.cast["tsuru"]["vrm"]
        have = vrm_rig.shape_keys(ch)
        own = {k: w for k, w in {"tsuru-hood": 0.75, "tsuru-brow-low": 0.6, "Fcl_EYE_Close": 0.05,
                                  "Fcl_BRW_Angry": 0.1}.items() if k in have}
        vrm_rig.compose(ch, "s4-calm", own)
        vrm_rig.compose(ch, "s4-smile", {k: w for k, w in {"Fcl_MTH_Fun": 0.35, "tsuru-sneer": 0.5,
                                                           "tsuru-press": 0.3}.items() if k in have})
