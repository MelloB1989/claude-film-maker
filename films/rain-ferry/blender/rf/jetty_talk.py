"""The talk on the jetty: shots 9-12 (demand, tap, look, draw), one scene cut four ways. Tsuru sits on a low crate
near the jetty's end, turned out past its last post toward the open river, her pipe in her hand; Shinza stands two
paces behind her right shoulder, his nodachi sheathed across his back and his kasa hanging off it. Every camera stays
on the river side of the line between them (-y of it: rf/sets.py's world), so he is always at the left of the frame
and she at the right, as in the standoff that follows.

`stage(ctx, ...)` builds what the four share: the crossing (rf/sets.py), the light and rain of the shot's place in
the look schedule (ctx.look_at), the 3D cast (rf/vroid_cast.py) taken out of the standoff's poses and put into this
scene's (`seat_tsuru`, `stand_shinza`), painted as the standoff paints them (shots/standoff.py TONES3D), and the
compositing. A shot then keys its performance frame by frame through the `Stage` (`pose`, `grip`, `hang`, `face`),
its camera (`Stage.camera`, from `Shot` keys) and its looks (`Stage.composite`).

The performance is timed to the dialogue (data/dialogue_timing.json, `Stage.line`) and to the sound cues (data/mix.json:
the pipe's taps at 42.05 s, the draw's steel at 51.95 s). The pure halves (easing, keys, the mouth, blinks, the
camera's breath) need no Blender.

Stand-ins until the cast and core land theirs: the kiseru, the scabbard and the kasa are built here (`kiseru`,
`back_gear`); the cast's own sword-on-the-back variant and the anim agent's keyed performances replace them.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------------------------------- the staging

# where each stands (world x, y: the jetty along x, its end at +x, the river beyond toward +y) and which way they face
# (degrees from +x toward +y). She is turned out past the end post (her pipe's post); he faces her
TSURU_AT, TSURU_FACING = (7.0, -0.45), -70.0
SHINZA_AT = (5.45, -0.8)
SHINZA_FACING = math.degrees(math.atan2(TSURU_AT[1] - SHINZA_AT[1], TSURU_AT[0] - SHINZA_AT[0]))
POST = "pier-post5-1"       # rf/sets.py's pier: the last post on the -y side, the one she knocks her pipe on
# her seat: a low crate under her hips (its top, metres), and how she sits on it (her frame: x her left, y her back):
# the hips down onto it and back over it, her feet planted forward and a little apart
SEAT = 0.40
TS_HIPS = (0.0, 0.1, -0.29)
TS_FEET = {"left": (0.11, -0.28), "right": (-0.12, -0.24)}
# his stance: weight on his back (left) foot, the right a little forward and out
SH_FEET = {"left": (0.12, 0.05, 6.0), "right": (-0.13, -0.08, -14.0)}

# ---- his gear on his back (his frame, metres as he stands): the scabbard across it from over the right shoulder to
# the left hip, the hilt standing up past his right ear; the kasa hanging off his back at the left, under it
SAYA_MOUTH = np.array((-0.12, 0.15, 1.43))
SAYA_FOOT = np.array((0.19, 0.19, 0.55))
HILT, BLADE = 0.30, 0.86            # a nodachi: a long hilt and a long blade
KASA = dict(center=(0.13, 0.25, 0.98), radius=0.27, rise=0.12, tilt=(70.0, 0.0, 18.0))

# ---- the kiseru (a long thin pipe): brass mouthpiece and bowl on a dark bamboo stem (m)
PIPE = dict(mouth=0.05, stem=0.2, bowl=0.055, cup=0.011)
GRIP_ALONG = 0.085                 # where her fist holds it, from the mouthpiece's end

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


def mouth(t: float, spans, *, rate: float = 7.0, seed: int = 1) -> tuple[float, int]:
    """How open the mouth is at t (0..1) while speaking in `spans` [(start, end), ...] s, and which vowel (0..2): a
    syllable every 1/rate s, each opening by its own amount, shut at the span's ends and between spans."""
    for k, (a, b) in enumerate(spans):
        if a <= t < b:
            u = (t - a) * rate
            i = int(u)
            rng = np.random.default_rng(seed * 1000 + k * 97 + i)
            amp = rng.uniform(0.45, 1.0)
            vowel = int(rng.integers(0, 3))
            env = min(1.0, (t - a) / 0.06, (b - t) / 0.08)
            return float(amp * math.sin(math.pi * (u - i)) ** 0.7 * env), vowel
    return 0.0, 0


def blink(t: float, times, *, close: float = 0.05, hold: float = 0.03, open_: float = 0.09) -> float:
    """How shut the eyes are at t (0..1) for blinks starting at `times`: shut fast, open slower."""
    v = 0.0
    for b in times:
        u = t - b
        if 0 <= u < close:
            v = max(v, u / close)
        elif close <= u < close + hold:
            v = 1.0
        elif close + hold <= u < close + hold + open_:
            v = max(v, 1.0 - ease((u - close - hold) / open_))
    return v


def breath(t: float, amount: float, *, seed: int = 3) -> np.ndarray:
    """A camera's breath: a slow wander (metres) of a few incommensurate sines, a handheld operator's at rest."""
    rng = np.random.default_rng(seed)
    out = np.zeros(3)
    for axis in range(3):
        for f, w in ((0.13, 1.0), (0.31, 0.45), (0.71, 0.18)):
            out[axis] += w * math.sin(2 * math.pi * f * t * rng.uniform(0.8, 1.25) + rng.uniform(0, 2 * math.pi))
    return out * amount / 1.63


def kick(t: float, at: float, amount: float, *, decay: float = 0.22, freq: float = 11.0, seed: int = 5) -> np.ndarray:
    """A jolt at `at` s (metres): a damped shake, sharp then settling over `decay` s."""
    u = t - at
    if u < 0:
        return np.zeros(3)
    rng = np.random.default_rng(seed)
    d = rng.normal(0, 1, 3)
    d /= np.linalg.norm(d)
    return d * amount * math.exp(-u / decay) * math.sin(2 * math.pi * freq * u + 0.6)


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


@dataclass
class Shot:
    """A camera's keys over a shot: [(t, (x, y, z) at, (x, y, z) aim)], the lens (mm) and f-stop as keys too, its
    breath (m) and its jolts [(t, metres)]."""
    path: list
    lens: list
    fstop: list
    breath: float = 0.004
    kicks: list = field(default_factory=list)

    def at(self, t: float):
        cam = np.array(keys_at([(k, c) for k, c, _ in self.path], t))
        aim = np.array(keys_at([(k, a) for k, _, a in self.path], t))
        wob = breath(t, self.breath) + sum((kick(t, at, amt) for at, amt in self.kicks), np.zeros(3))
        return cam + wob, aim + wob * 0.6, keys_at(self.lens, t), keys_at(self.fstop, t)


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


def post_top(name: str = POST) -> np.ndarray:
    """(x, y, top z) of a post of the pier, from its mesh."""
    import bpy

    ob = bpy.data.objects[name]
    co = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
    return np.array([co[:, 0].mean(), co[:, 1].mean(), co[:, 2].max()])


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

    # ---- the performance
    def pose(self, who: str, f: int, turns: dict, hips=None) -> None:
        from lib import vrm

        ch = self.cast[who]["vrm"]
        vrm.pose(ch, turns, hips=hips, frame=f)

    def grip(self, who: str, side: str, f: int, point, knuckles, palm, pole, *, local_frame: bool = True) -> None:
        """Key the `side` hand closed round something through `point` (its knuckles along `knuckles`, palm facing
        `palm`), the elbow toward `pole`: all in the character's frame unless local_frame is False (world)."""
        ch = self.cast[who]["vrm"]
        if not local_frame:
            point, pole = local(ch, point), local(ch, pole)
            knuckles, palm = local_dir(ch, knuckles), local_dir(ch, palm)
        turn = hand_turn(ch, side, knuckles, palm)
        self._key_hand(ch, side, f, fist_wrist(ch, side, point, turn), turn, pole)

    def hang(self, who: str, side: str, f: int, wrist, knuckles, palm, pole) -> None:
        """Key the `side` hand's wrist at `wrist`, turned to knuckles and palm, the elbow toward `pole` (his frame)."""
        ch = self.cast[who]["vrm"]
        self._key_hand(ch, side, f, np.asarray(wrist, float), hand_turn(ch, side, knuckles, palm), pole)

    def hand(self, who: str, side: str, f: int, wrist, turn, pole) -> None:
        """Key the `side` hand's wrist at `wrist` turned by `turn` (vrm.align), the elbow toward `pole` (their frame)."""
        self._key_hand(self.cast[who]["vrm"], side, f, np.asarray(wrist, float), turn, pole)

    def _key_hand(self, ch, side, f, wrist, turn, pole) -> None:
        from lib import vrm

        bone = f"{side}Hand"
        c = vrm.reach(ch, bone, wrist, pole=pole, bend=0.0)
        vrm.hold(ch, bone, turn)
        for key in ("target", "pole"):
            ch.handles[f"{bone}-{key}"].keyframe_insert("location", frame=f)
        h = ch.handles[f"{bone}-hold"]
        h.keyframe_insert("rotation_quaternion", frame=f)
        h.keyframe_insert("location", frame=f)
        c.keyframe_insert("pole_angle", frame=f)

    def face(self, who: str, f: int, weights: dict) -> None:
        from lib import vrm

        vrm.express(self.cast[who]["vrm"], weights, frame=f)

    # ---- the camera
    def camera(self, shot: Shot, focus) -> None:
        """Key the camera through `shot` every frame, its focus on `focus(f)` (world point)."""
        cam, aim, foc = self.cam, self.aim, self.focus
        for f in self.frames():
            c, a, lens, fstop = shot.at(self.t(f))
            cam.location, aim.location = tuple(c), tuple(a)
            cam.data.lens = lens
            cam.data.dof.aperture_fstop = fstop
            foc.location = tuple(focus(f))
            cam.keyframe_insert("location", frame=f)
            aim.keyframe_insert("location", frame=f)
            foc.keyframe_insert("location", frame=f)
            cam.data.keyframe_insert("lens", frame=f)
            cam.data.dof.keyframe_insert("aperture_fstop", frame=f)

    def head_at(self, who: str, f: int) -> np.ndarray:
        """Between the character's eyes at film frame f, as keyed."""
        self.ctx.scene.frame_set(f)
        return np.array(self.cast[who]["vrm"].face())

    def tracked_focus(self, who: str, every: int = 6):
        """focus(f): the character's eyes, sampled every few frames as the performance keyed them, eased between."""
        fs = list(range(self.ctx.f0 - 1, self.ctx.f1 + 1, every)) + [self.ctx.f1]
        pts = [(f, tuple(self.head_at(who, f))) for f in fs]
        self.ctx.scene.frame_set(self.ctx.f0)
        return lambda f: np.array(keys_at(pts, f))

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


def stage(ctx, *, who=("shinza", "tsuru"), rain_box=((2.0, -4.5, -0.6), (10.0, 4.0, 4.0)), clear: float = 0.9,
          near: float = 3.0, ink: float = 0.0035, lantern_near: float | None = None) -> Stage:
    """The scene for one of the four shots: the crossing, its light and weather at the shot's place in the look
    schedule, the cast in `who` staged and painted, and a camera (keyed by the shot: Stage.camera). `rain_box` (world
    min, max) is where the rain falls (its count from the schedule's density over the standoff's volume), none within
    `clear` of the lens; `ink` is the near set's line art (m; 0 none); `lantern_near` dims the hut's lantern (an
    emission strength) for a shot it sits by a head in."""
    import sys

    import bpy
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import rig, toon, toon3d, vrm
    from rf import sets, vroid_cast

    scene = ctx.scene
    s = ctx.look_at(ctx.f0)
    scene.render.use_motion_blur = False
    scene.eevee.use_shadows = True
    scene.eevee.use_raytracing = True
    scene.view_settings.view_transform = "Standard"
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (*s.light.ambient, 1)

    look = toon.Look(fog=tuple(s.light.fog), fog_near=18.0, fog_far=480.0, fog_max=0.9, fog_power=0.65)
    crossing = sets.crossing(look)
    if ink:
        toon.ink("ink-near", crossing["near"], radius=ink, crease=150)
    if lantern_near is not None:
        crossing["materials"]["lantern"].node_tree.nodes["Emission"].inputs["Strength"].default_value = lantern_near

    sun = bpy.data.lights.new("key", "SUN")
    sun.angle = math.radians(3)
    sun.energy = 4.2 * s.light.key_strength
    sun.color = tuple(s.light.key)
    key = bpy.data.objects.new("key", sun)
    scene.collection.objects.link(key)
    key.rotation_euler = Vector((0.55, 0.45, -0.7)).to_track_quat("-Z", "Y").to_euler()

    # the rain: the schedule's drops per the standoff's box, in this shot's box
    r = s.rain
    lo, hi = np.array(rain_box[0], float), np.array(rain_box[1], float)
    count = round(r.drops * np.prod(hi - lo) / (13.0 * 15.6 * 6.1))
    rain = toon.rain("rain", tuple(lo), tuple(hi), count=max(count, 1), speed=r.speed, wind=r.wind, length=r.length,
                     width=r.width, color=tuple(r.color), alpha=r.alpha, seed=4, near=near, clear=clear)
    toon.splashes("splash-deck", (sets.SPAN[0], -sets.HALF + 0.05, 0.004), (sets.SPAN[1], sets.HALF - 0.05, 0.004),
                  count=round(240 * r.density / 0.8), size=0.08, seed=5)
    toon.splashes("splash-river", (lo[0], lo[1], sets.WATER_Z + 0.002), (hi[0], hi[1], sets.WATER_Z + 0.002),
                  count=round(300 * r.density / 0.8), size=0.11, alpha=0.45, seed=9)

    cast_coll = toon.collection("cast")
    toon.move_to(key, toon.collection("world-light"))
    cast_look = toon.Look(fog=look.fog, fog_near=look.fog_near, fog_far=look.fog_far, fog_max=look.fog_max,
                          fog_power=look.fog_power)
    so = _standoff()
    cast = {}
    for name in who:
        built = getattr(vroid_cast, name)(cast_coll, cast_look)
        cast[name] = built
        if name == "tsuru":
            seat_tsuru(built, cast_coll, crossing)
        else:
            stand_shinza(built, cast_coll, cast_look)
        built["key"] = toon3d.key(f"{name}-key", [built["root"], *built["root"].children_recursive], (1.0, -0.3, 0.8),
                                  coll=cast_coll, angle=so.KEY3D_ANGLE, color=tuple(s.light.key))
        tones = {p: toon3d.Tone(**{**kw, **so.TONES3D_OF.get(name, {}).get(p, {})}) for p, kw in so.TONES3D.items()}
        vrm.anime(built["vrm"], tones, built["key"])
        vrm.smooth(built["vrm"])
    if cast:
        rain_cast = rain.copy()
        rain_cast.name = "rain-cast"
        cast_coll.objects.link(rain_cast)

    cam = rig.engine_camera("camera", fstop=4.0, size=ctx.size)
    cam.data.clip_end = 3000.0
    scene.camera = cam
    aim = bpy.data.objects.new("aim", None)
    scene.collection.objects.link(aim)
    c = cam.constraints.new("TRACK_TO")
    c.target, c.track_axis, c.up_axis = aim, "TRACK_NEGATIVE_Z", "UP_Y"
    focus = bpy.data.objects.new("focus", None)
    scene.collection.objects.link(focus)
    cam.data.dof.focus_object = focus

    st = Stage(ctx, crossing=crossing, cast=cast, cast_coll=cast_coll, sun=sun, rain=rain, cam=cam, aim=aim,
               focus=focus, look=look, standoff=so)
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


def outline(st: Stage, shot: Shot, frac: float = 0.0018) -> None:
    """Every character's outline a width on screen (frame heights) as `shot` moves, keyed per frame."""
    from lib import vrm

    faces = {name: st.head_at(name, st.ctx.f0) for name in st.cast}
    for f in st.frames():
        c, _, lens, _ = shot.at(st.t(f))
        for name, built in st.cast.items():
            d = float(np.linalg.norm(np.asarray(c) - faces[name]))
            vrm.key_outline(built["vrm"], vrm.outline_width(frac, d, lens), f)


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

def _remove(obs) -> None:
    import bpy

    for ob in obs:
        bpy.data.objects.remove(ob, do_unlink=True)


def _place(built, at, facing: float) -> None:
    import bpy

    built["root"].location = (at[0], at[1], 0.0)
    built["root"].rotation_euler = (0.0, 0.0, math.radians(facing))
    bpy.context.view_layer.update()


def seat_tsuru(built, coll, crossing) -> None:
    """Tsuru out of the standoff's stance and onto her crate by the end post: her pole laid in the boat, her pipe in
    her right hand, her feet planted forward. Her hands and head are keyed by the shot."""
    from lib import shapes, vrm

    from .vroid_common import plant

    ch = built["vrm"]
    _place(built, TSURU_AT, TSURU_FACING)
    # the pole: out of her hand, lying along the boat's thwarts
    pole = [ob for ob in built["props"] if "-pole" in ob.name or "-node" in ob.name or "-cord" in ob.name]
    for ob in pole:
        ob.parent = None
    _lay_pole(pole)
    # her crate, under her hips
    back = _turn_z(TSURU_FACING) @ np.array([-1.0, 0.0, 0.0])
    cx, cy = np.array(TSURU_AT) + back[:2] * 0.1
    m = crossing["materials"]
    shapes.box("crate", (cx, cy, SEAT / 2 - 0.01), (0.42, 0.36, SEAT), material=m["plank"], coll=crossing["near"],
               rot_z=math.radians(TSURU_FACING) + 0.08)
    # seated: the hips down on the crate, the knees bent forward over her planted feet
    vrm.pose(ch, {"spine": (8.0, 0.0, 0.0), "chest": (10.0, 0.0, 0.0), "upperChest": (8.0, 0.0, 0.0),
                  "neck": (10.0, 0.0, 0.0), "head": (-20.0, 0.0, 0.0)}, hips=TS_HIPS)
    sole = ch.rest("leftFoot")[2]
    plant(ch, {side: ((x, y, sole), (x * 1.5, -1.0, 0.45), (0.0, 0.0, 8.0 if side == "left" else -8.0))
               for side, (x, y) in TS_FEET.items()})
    built["pipe"] = kiseru("tsuru-kiseru", coll)


def _lay_pole(obs) -> None:
    """The ferry pole's pieces (built standing) laid down in the boat, along it."""
    import bpy
    from mathutils import Matrix

    from . import sets

    foot = np.array(obs[0].data.vertices[0].co) if obs else np.zeros(3)
    m = (Matrix.Translation((4.1, 2.35, sets.WATER_Z + 0.32)) @ Matrix.Rotation(math.radians(91.0), 4, "Y")
         @ Matrix.Rotation(math.radians(4.0), 4, "Z") @ Matrix.Translation(tuple(-foot)))
    for ob in obs:
        ob.matrix_world = m @ ob.matrix_world
    bpy.context.view_layer.update()


def kiseru(name: str, coll) -> list:
    """A long thin pipe along +x from its mouthpiece's end at the origin: the brass mouthpiece, the dark bamboo stem and
    the brass bowl turned up at its end. Returns [mouthpiece, stem, bowl, cup]."""
    from lib import shapes, toon

    from .vroid_common import COLORS

    brass = toon.cel(f"{name}-brass", *COLORS["brass"], cut=0.5)
    stem = toon.cel(f"{name}-stem", (0.06, 0.035, 0.022), (0.014, 0.009, 0.006), cut=0.45)
    p = PIPE
    a, b = p["mouth"], p["mouth"] + p["stem"]
    end = b + p["bowl"]
    obs = [shapes.loft(f"{name}-mouth", [(0, 0, 0), (a * 0.6, 0, 0), (a, 0, 0)], [0.0035, 0.0042, 0.0048], material=brass,
                       coll=coll, n=10, subsurf=0),
           shapes.cylinder(f"{name}-stem", (a - 0.003, 0, 0), (b + 0.003, 0, 0), 0.0045, material=stem, coll=coll, n=10),
           shapes.loft(f"{name}-bowl", [(b, 0, 0), (end - 0.012, 0, 0.0), (end - 0.004, 0, 0.004), (end, 0, 0.012)],
                       [0.0048, 0.0045, 0.0055, 0.0065], material=brass, coll=coll, n=10, subsurf=0),
           shapes.lathe(f"{name}-cup", [(0.0, -0.002), (p["cup"] * 0.6, 0.0), (p["cup"], 0.008), (p["cup"] * 0.8, 0.0085)],
                        material=brass, coll=coll, n=14, center=(end, 0, 0.012))]
    return obs


def hold_pipe(st: Stage, f: int, point, along, up=(0.0, 0.0, 1.0)) -> None:
    """Key Tsuru's right fist round her pipe through `point` along `along` (bowl-ward; world), its palm toward her
    and down."""
    ch = st.cast["tsuru"]["vrm"]
    p, d = local(ch, point), local_dir(ch, along)
    d = d / np.linalg.norm(d)
    palm = np.cross(d, local_dir(ch, up))
    if palm[0] < 0:     # toward her middle, from the right hand
        palm = -palm
    palm = palm * 0.6 + np.array((0.0, 0.0, -0.4))
    st.grip("tsuru", "right", f, p, -d, palm, (-0.45, 0.25, 0.75))


def fit_pipe(st: Stage, point, along) -> None:
    """Build the pipe into her right fist as posed (at the current frame) through `point` along `along` (world), and
    carry it with her hand from then on."""
    from lib import vrm

    d = np.asarray(along, float) / np.linalg.norm(along)
    origin = np.asarray(point, float) - d * GRIP_ALONG
    up = np.array((0.0, 0.0, 1.0))
    side = np.cross(up, d)
    side /= np.linalg.norm(side)
    up = np.cross(d, side)
    from mathutils import Matrix

    m = Matrix(((d[0], side[0], up[0], origin[0]), (d[1], side[1], up[1], origin[1]), (d[2], side[2], up[2], origin[2]),
                (0, 0, 0, 1)))
    for ob in st.cast["tsuru"]["pipe"]:
        ob.matrix_world = m
        vrm.attach(ob, st.cast["tsuru"]["vrm"], "rightHand")


def pipe_bowl(st: Stage) -> np.ndarray:
    """The pipe's bowl (world), as posed now."""
    import bpy

    bpy.context.view_layer.update()
    cup = next(ob for ob in st.cast["tsuru"]["pipe"] if ob.name.endswith("-cup"))
    return np.array(cup.matrix_world.translation)


def stand_shinza(built, coll, look) -> None:
    """Shinza out of the standoff's guard: standing two paces behind her, his sword sheathed across his back (the
    standoff's drawn katana gone), his kasa hanging off it. His hands and head are keyed by the shot."""
    from lib import vrm

    from .vroid_common import plant

    ch = built["vrm"]
    _remove(built["props"])
    _place(built, SHINZA_AT, SHINZA_FACING)
    vrm.pose(ch, {}, hips=(0.0, 0.0, -0.01))
    sole = ch.rest("leftFoot")[2]
    plant(ch, {side: ((x, y, sole), (x * 1.6, -1.0, 0.5), (0.0, 0.0, turn)) for side, (x, y, turn) in SH_FEET.items()})
    built.update(back_gear(ch, coll, look))


def saya_axis() -> np.ndarray:
    """Up along the scabbard toward its mouth (his frame)."""
    u = SAYA_MOUTH - SAYA_FOOT
    return u / np.linalg.norm(u)


def back_gear(ch, coll, look) -> dict:
    """His nodachi in its scabbard across his back and his kasa hanging off it, carried by his upper chest:
    {"saya": [..], "sword": [blade, collar, guard, hilt, cap], "kasa": [..]}. Built at rest in his frame."""
    from lib import anime, props, shapes, vrm

    from .vroid_common import COLORS

    m = anime.palette(COLORS, look, prefix="shinza-gear", cuts={"steel": 0.55})
    u = saya_axis()
    W = lambda p: tuple(ch.world(p))  # noqa: E731
    pommel = SAYA_MOUTH + u * HILT
    sword = props.katana("shinza-nodachi", m, W(pommel), tuple(np.array(W(SAYA_MOUTH)) - np.array(W(pommel))),
                         hilt=HILT, blade=BLADE, coll=coll, side=tuple(np.array(W((1, 0, 0))) - np.array(W((0, 0, 0)))))
    # the scabbard: black lacquer, its mouth a ring of horn, its foot capped
    path = [SAYA_MOUTH - u * k for k in np.linspace(0.0, BLADE + 0.04, 6)]
    saya = [shapes.loft("shinza-saya", [W(p) for p in path], [0.021, 0.02, 0.019, 0.018, 0.017, 0.015],
                        [0.014, 0.0135, 0.013, 0.0125, 0.012, 0.011], material=m["lacquer"], coll=coll, n=12, subsurf=0,
                        up=tuple(np.array(W((0, 1, 0))) - np.array(W((0, 0, 0))))),
            shapes.cylinder("shinza-koiguchi", W(SAYA_MOUTH - u * 0.03), W(SAYA_MOUTH + u * 0.002), 0.0225,
                            material=m["wrap"], coll=coll, n=12)]
    # its cord over his left shoulder and across his chest to the right hip (his frame), a rope as the cels draw it
    cord = [(0.03, 0.17, 1.2), (0.12, 0.1, 1.46), (0.14, -0.06, 1.42), (0.06, -0.135, 1.27), (-0.07, -0.13, 1.08),
            (-0.15, -0.09, 0.96), (-0.17, 0.0, 0.92)]
    saya.append(shapes.loft("shinza-sageo", [W(p) for p in cord], 0.006, material=m["rope"], coll=coll, n=6,
                            subsurf=1))
    k = KASA
    R = _euler(k["tilt"])
    r, h = k["radius"], k["rise"]
    prof = [(r, 0.0), (r * 0.95, h * 0.12), (r * 0.6, h * 0.55), (r * 0.25, h * 0.88), (0.0, h)]
    kasa = [shapes.lathe("shinza-kasa", [(rr, z) for rr, z in prof], material=m["straw"], coll=coll, n=28,
                         center=(0, 0, 0), rot=None)]
    kasa.append(shapes.lathe("shinza-kasa-under", [(r * 0.97, 0.002), (r * 0.6, h * 0.5), (0.0, h * 0.95)],
                             material=m["straw_dark"], coll=coll, n=28))
    from mathutils import Matrix

    world_R = np.array(ch.armature.matrix_world.to_3x3().normalized()) @ ch.frame @ R
    c = W(k["center"])
    mw = Matrix([[*world_R[0], c[0]], [*world_R[1], c[1]], [*world_R[2], c[2]], [0, 0, 0, 1]])
    for ob in kasa:
        ob.matrix_world = mw
    kasa.append(shapes.loft("shinza-kasa-cord", [W(p) for p in ((0.1, 0.2, 1.15), (0.06, 0.12, 1.35),
                                                                (0.07, 0.04, 1.47))], 0.003, material=m["rope"],
                            coll=coll, n=5, subsurf=0))
    for ob in (*saya, *kasa):
        vrm.attach(ob, ch, "upperChest" if ch.has("upperChest") else "chest")
    for ob in sword:
        vrm.attach(ob, ch, "upperChest" if ch.has("upperChest") else "chest")
    return {"saya": saya, "sword": sword, "kasa": kasa, "gear_m": m}


def _euler(deg) -> np.ndarray:
    x, y, z = (math.radians(v) for v in deg)
    Rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    Ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    Rz = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


# ---------------------------------------------------------------------------------------------------- performance

# where the hands hang at rest (each character's frame: x their left, y their back, z up; wrists)
HANG = {"right": (-0.21, -0.01, 0.97), "left": (0.21, -0.01, 0.97)}
TS_KNEE_HAND = (0.13, -0.22, 0.5)        # her left hand resting on her knee
TS_PIPE_LAP = ((-0.11, -0.27, 0.55), (-0.25, -1.0, -0.2))   # her pipe resting by her right knee: (fist, along)


def fingers(side: str, curl: float) -> dict:
    """The fingers of a hand curled by `curl` (0 open .. 1 a fist round a hilt)."""
    from lib import vrm

    return vrm.grip_pose(side, curl, thumb=0.15 + 0.5 * curl)


def shinza_hips(t: float) -> tuple:
    """His hips: his weight settled on his back (left) foot, breathing."""
    return (0.018, 0.0, -0.014 + 0.002 * math.sin(2 * math.pi * t / 3.4))


def shinza_stand(t: float, *, look_out: float = 0.0, reach: float = 0.0, gust: float = 0.0, chin: float = 0.0) -> dict:
    """His body standing over her (his frame's turns, vrm.pose): chest out, his head down to her (she sits below
    him); `look_out` turns his head and eyes out to the far shore (his left), `reach` turns his chest and lifts his
    right shoulder as the hand goes to the hilt, `gust` leans his head from the wind, `chin` lifts it (defiance)."""
    br = math.sin(2 * math.pi * t / 3.4)
    return {
        "spine": (-2.0 + 0.6 * br, 0.0, 3.0),
        "chest": (-3.0 + 0.8 * br, 0.0, -7.0 * reach),
        "upperChest": (-2.0, 0.0, -4.0 * reach),
        "neck": (6.0 - 4.0 * look_out - 3.0 * chin, 0.0, 10.0 * look_out),
        "head": (12.0 - 9.0 * look_out - 3.0 * reach - 6.0 * chin, -1.5 * gust, 22.0 * look_out - 3.0 * reach),
        "leftEye": (7.0 - 9.0 * look_out, 0.0, 12.0 * look_out),
        "rightEye": (7.0 - 9.0 * look_out, 0.0, 12.0 * look_out),
        "rightShoulder": (0.0, 9.0 * reach, 0.0),
    }


def hilt_grip(ch) -> tuple:
    """(wrist, turn) of his right fist on the hilt standing over his right shoulder, its knuckles up the hilt and its
    palm to the blade's flat (his frame)."""
    u = saya_axis()
    turn = hand_turn(ch, "right", u, flat_palm(u))
    return fist_wrist(ch, "right", SAYA_MOUTH + u * 0.07, turn), turn


def tsuru_sit(t: float, *, turn: float = 0.0, down: float = 0.0, eyes=(0.0, 0.0), lean: float = 0.0) -> dict:
    """Her body seated (her frame's turns): the back rounded, the head forward on the neck; `turn` (degrees, + to her
    left) her head round, shared down her neck and back; `down` her head bowed (degrees); `eyes` (down, left) degrees;
    `lean` forward over her knees (degrees)."""
    br = math.sin(2 * math.pi * t / 4.1)
    return {
        "spine": (8.0 + lean * 0.5 + 0.4 * br, 0.0, turn * 0.12),
        "chest": (10.0 + lean * 0.5, 0.0, turn * 0.12),
        "upperChest": (8.0 + 0.5 * br, 0.0, turn * 0.1),
        "neck": (10.0 + down * 0.4, 0.0, turn * 0.26),
        "head": (-22.0 + down * 0.6, 0.0, turn * 0.4),
        "leftEye": (eyes[0], 0.0, eyes[1]),
        "rightEye": (eyes[0], 0.0, eyes[1]),
        "leftShoulder": (0.0, 5.0, -8.0),
        "rightShoulder": (0.0, -5.0, 8.0),
    }


def tsuru_hips(t: float) -> tuple:
    return (TS_HIPS[0], TS_HIPS[1], TS_HIPS[2] + 0.0015 * math.sin(2 * math.pi * t / 4.1))


def hold_pipe_local(st: Stage, f: int, point, along) -> None:
    """Key Tsuru's right fist round her pipe through `point` along `along` (bowl-ward), her frame: the palm in toward
    her and down. Remembers the hold, for `settle` to build the pipe into the fist."""
    d = np.asarray(along, float) / np.linalg.norm(along)
    palm = flat_palm(d, (0.7, 0.0, -0.7))
    st.grip("tsuru", "right", f, point, -d, palm, (-0.45, 0.3, 0.7))
    st.cast["tsuru"].setdefault("pipe_at", {})[f] = (np.asarray(point, float), d)


def tsuru_rest(st: Stage, f: int, t: float, **sit) -> None:
    """Tsuru still on her crate: her pipe resting by her right knee, her left hand on her knee."""
    ch = st.cast["tsuru"]["vrm"]
    st.pose("tsuru", f, {**tsuru_sit(t, **sit), **fingers("right", 0.75), **fingers("left", 0.35)}, hips=tsuru_hips(t))
    hold_pipe_local(st, f, *TS_PIPE_LAP)
    knee_hand(st, f)
    st.face("tsuru", f, {"s4-calm": 1.0})


def knee_hand(st: Stage, f: int) -> None:
    ch = st.cast["tsuru"]["vrm"]
    st.hand("tsuru", "left", f, TS_KNEE_HAND, hand_turn(ch, "left", (1.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
            (0.45, 0.25, 0.8))


def settle(st: Stage, *, sword_in_hand: bool = False) -> None:
    """Once the performance is keyed: her pipe built into her fist as it is on the shot's first frame, and (the draw)
    his sword taken off his back into his right fist there."""
    import bpy

    from lib import vrm

    f0 = st.ctx.f0
    st.ctx.scene.frame_set(f0)
    bpy.context.view_layer.update()
    if "tsuru" in st.cast and st.cast["tsuru"].get("pipe_at"):
        point, d = st.cast["tsuru"]["pipe_at"][f0]
        ch = st.cast["tsuru"]["vrm"]
        fit_pipe(st, ch.world(point), np.array(ch.world(point + d)) - np.array(ch.world(point)))
    if sword_in_hand:
        for ob in st.cast["shinza"]["sword"]:
            vrm.attach(ob, st.cast["shinza"]["vrm"], "rightHand")


# ---------------------------------------------------------------------------------------------------- faces

def mouth_weights(t: float, spans, seed: int, scale: float = 0.75) -> dict:
    """The VRM's mouth presets for speaking at t."""
    a, v = mouth(t, spans, seed=seed)
    name = ("aa", "oh", "ih")[v]
    return {name: a * scale} if a > 0 else {}


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
