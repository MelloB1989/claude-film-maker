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
TSURU_AT, TSURU_FACING = (7.1, -0.8), -70.0      # the post within her pipe's reach
SHINZA_AT = (5.45, -0.82)
SHINZA_FACING = math.degrees(math.atan2(TSURU_AT[1] - SHINZA_AT[1], TSURU_AT[0] - SHINZA_AT[0]))
POST_RADIUS = 0.14          # rf/set_jetty.py's end posts: the one on the -y side is the one she knocks her pipe on
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
    """Where her pipe knocks: the end post's crown (rf/set_jetty.py's staved post on the -y side), its edge toward
    her (world)."""
    post = st.crossing["jetty"]["posts"]["end"]
    top = np.array(post["anchors"]["top"].matrix_world.translation)
    toward = np.array((*TSURU_AT, top[2])) - top
    toward[2] = 0.0
    return top + toward / np.linalg.norm(toward) * POST_RADIUS * 0.55


class Stage:
    """What `stage` built: the scene's pieces, the cast, the camera; keying the performance and the camera."""

    def __init__(self, ctx, **kw):
        self.ctx = ctx
        self.__dict__.update(kw)
        self.start, _ = ctx.timing.scene(ctx.shot if ctx.look is None else ctx.look.scene)
        self.held = []

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

    def grip(self, who: str, side: str, f: int, point, knuckles, palm, pole, *, local_frame: bool = True) -> None:
        """Key the `side` hand closed round something through `point` (its knuckles along `knuckles`, palm facing
        `palm`), the elbow toward `pole`: all in the character's frame unless local_frame is False (world)."""
        ch = self.cast[who]["vrm"]
        if not local_frame:
            point, pole = local(ch, point), local(ch, pole)
            knuckles, palm = local_dir(ch, knuckles), local_dir(ch, palm)
        turn = hand_turn(ch, side, knuckles, palm)
        self.hand(who, side, f, fist_wrist(ch, side, point, turn), turn, pole)

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
        for p in self.perf.values():
            p.bake(self.ctx.f0 - 1, self.ctx.f1 + 1)
        self.ctx.scene.frame_set(self.ctx.f0)

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
        self.sky = weather.storm(self.ctx, self.rig, **storm)
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
        comp = satsuei.setup(self.ctx.scene, self.cast_coll)
        for f in self.frames():
            s = self.ctx.look_at(f)
            own = setup(f)
            own["rims"] = tuple(satsuei.Rim(*r) for r in own.get("rims", ()))
            comp.key(f, s.look(**own))
        comp.hold()


def stage(ctx, *, who=("shinza", "tsuru"), ink: float = 0.0035, lantern_near: float | None = None, variant: dict | None = None,
          place: dict | None = None) -> Stage:
    """The scene for one of the four shots: the world lit at the shot's place in the look schedule, the cast in `who`
    staged and painted (the camera and the weather come after the performance: Stage.film); `ink` is the near set's
    line art (m; 0 none); `lantern_near` dims the hut's lantern (an
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

    br = math.sin(2 * math.pi * t / 3.4)
    legs = {k: v for k, v in STAND_POSE.items() if "Leg" in k or k == "hips"}
    return {
        **legs,
        "spine": (-2.0 + 0.6 * br, 0.0, 3.0),
        "chest": (-3.0 + 0.8 * br, 0.0, -7.0 * reach),
        "upperChest": (-2.0, 0.0, -4.0 * reach),
        "neck": (6.0 - 4.0 * look_out - 3.0 * chin, 0.0, 10.0 * look_out),
        "head": (12.0 - 9.0 * look_out - 3.0 * reach - 6.0 * chin, -1.5 * gust, 22.0 * look_out - 3.0 * reach),
        "leftEye": (7.0 - 9.0 * look_out, 0.0, 12.0 * look_out),
        "rightEye": (7.0 - 9.0 * look_out, 0.0, 12.0 * look_out),
        "rightShoulder": (0.0, 9.0 * reach, 0.0),
    }


def hilt_grip(st: Stage, along: float = 0.06) -> tuple:
    """(wrist, turn) of his right fist on the hilt standing over his right shoulder, `along` up it from the guard: its
    knuckles up the hilt and its palm to the blade's flat (against his back), his frame."""
    ch = st.cast["shinza"]["vrm"]
    guard, u = hilt_axis(st)
    turn = hand_turn(ch, "right", u, flat_palm(u, (0.25, 1.0, 0.0)))
    return fist_wrist(ch, "right", guard + u * along, turn), turn


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


def hold_pipe(st: Stage, f: int, point, along) -> None:
    """Key Tsuru's left fist round her pipe through `point` along `along` (bowl-ward), her frame: the palm in toward
    her and up a little, as rf/vroid_tsuru.py's builder closed it."""
    d = np.asarray(along, float) / np.linalg.norm(along)
    st.grip("tsuru", "left", f, point, -d, flat_palm(d, (-0.5, 0.0, 0.8)), (0.3, 0.6, 0.45))   # the elbow back, by her side


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
    pose = {**tsuru_sit(t, **sit), **fingers("left", 0.85), **fingers("right", 0.35)}
    hips = tsuru_hips(st, t)
    hold = pipe_at_lips(st, pose, hips) if smoking else TS_PIPE_LAP
    st.pose("tsuru", f, pose, hips=hips)
    hold_pipe(st, f, *hold)
    knee_hand(st, f)
    st.face("tsuru", f, {"s4-calm": 1.0})


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
    """His sword out of its scabbard into his right fist, as it is on the shot's first frame (the draw)."""
    import bpy

    from lib import vrm

    st.ctx.scene.frame_set(st.ctx.f0)
    bpy.context.view_layer.update()
    vrm.attach(st.cast["shinza"]["parts"]["sword"][0], st.cast["shinza"]["vrm"], "rightHand")


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
