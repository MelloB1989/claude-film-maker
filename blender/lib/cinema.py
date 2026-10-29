"""Cinema: the camera a shot is filmed with, one way for the whole film. A shot is a few setups (the wide, his close-up,
hers), cut at given times; each setup is a camera move (held, pushed in, dollied along a path, craned, orbited, drifting),
eased, over its own window, through a lens chosen by intent, with its focus on a point, an object or a bone (and racked
from one to another), a handheld shake (a breath, hard on an impact), a dutch roll and motion blur when it wants them.

    from lib import cinema
    rig = cinema.film(ctx, [
        cinema.Setup("wide", 0.0, cinema.push((0.2, -6.9, 1.1), (0.0, 0.0, 1.0), 0.6), lens="wide", fstop=5.6,
                     shake=cinema.Shake(breath=0.05)),
        cinema.Setup("mcu", 1.5, cinema.hold(*cinema.frame_on((-2.3, 0.0, 1.55), 0.24, share=0.5, lens=85, bearing=30)),
                     lens=85, fstop=2.8, focus=shinza.armature_head, racks=[cinema.Rack(2.4, lantern, 0.5)]),
    ])
    rig.camera, rig.setup_at(f), rig.pose(f), rig.cuts      # what else a shot keys per setup: rig.per_setup(...)

Times are seconds from the shot's first frame (ctx.f0); a setup runs from its `at` to the next one's (the last to the
shot's end). Inside its window a move runs over `span` (seconds into the setup, default all of it), held before and after
(a held breath before the action), eased by `ease`. Every frame of the shot is keyed; a cut's two sides are held, never
tweened, so the cut lands on its frame (and motion blur, its shutter opening on the frame, never smears across it).

World axes are the film's: z up; a bearing is degrees from -y toward +x (the camera's side of a set that faces -y). The
camera is the engine's (lib/rig.py engine_camera: a 20.25 mm gate fit vertically), so a lens means the same as the
engine's. The moves, the shake, the framing and the focus's weights are numpy only (tests: blender/tests/test_cinema.py);
`film` and `Rig` need Blender.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .rig import SENSOR_H_MM, catmull_rom

GATE_H = SENSOR_H_MM
# lenses by intent (mm on the engine's gate): an establishing wide, a mid two-shot, a close-up, an insert
LENSES = {"ultra": 18.0, "wide": 26.0, "mid": 40.0, "medium": 50.0, "close": 85.0, "tight": 105.0, "insert": 135.0}


# ---------------------------------------------------------------------------------------------------- easing

def ease(u: float, kind: str = "sine") -> float:
    """u (clamped 0..1) eased: "linear", "sine" (in-out), "cubic" (in-out), "quint" (in-out: a slow start and settle),
    "in" (accelerating: a camera gathering speed), "out" (decelerating: arriving and settling)."""
    u = min(1.0, max(0.0, float(u)))
    if kind == "linear":
        return u
    if kind == "sine":
        return 0.5 - 0.5 * math.cos(math.pi * u)
    if kind == "cubic":
        return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2
    if kind == "quint":
        return 16 * u ** 5 if u < 0.5 else 1 - (-2 * u + 2) ** 5 / 2
    if kind == "in":
        return u ** 3
    if kind == "out":
        return 1 - (1 - u) ** 3
    raise ValueError(f"cinema: unknown ease {kind!r} (linear, sine, cubic, quint, in, out)")


def lens_of(lens) -> float:
    """A lens (mm) from a number or an intent (LENSES)."""
    if isinstance(lens, str):
        if lens not in LENSES:
            raise ValueError(f"cinema: unknown lens {lens!r} ({', '.join(LENSES)})")
        return LENSES[lens]
    return float(lens)


def _v(p) -> np.ndarray:
    return np.asarray(p, float).reshape(3)


# ---------------------------------------------------------------------------------------------------- moves

@dataclass(frozen=True)
class Move:
    """A camera move: `at(u)` -> (camera, aim) world points at progress u (0..1, already eased)."""
    fn: object

    def at(self, u: float) -> tuple[np.ndarray, np.ndarray]:
        c, a = self.fn(float(u))
        return _v(c), _v(a)


def hold(cam, aim) -> Move:
    """A locked-off frame."""
    c, a = _v(cam), _v(aim)
    return Move(lambda u: (c, a))


def line(cam_from, cam_to, aim_from, aim_to=None) -> Move:
    """The camera from one point to another, its aim from one to another (or kept): a dolly, a truck, a crane."""
    c0, c1, a0 = _v(cam_from), _v(cam_to), _v(aim_from)
    a1 = a0 if aim_to is None else _v(aim_to)
    return Move(lambda u: (c0 + (c1 - c0) * u, a0 + (a1 - a0) * u))


def push(cam, aim, by: float, *, aim_by: float = 0.0) -> Move:
    """In toward the aim by `by` metres (negative pulls out), the aim itself creeping `aim_by` the same way."""
    c, a = _v(cam), _v(aim)
    d = (a - c) / max(np.linalg.norm(a - c), 1e-9)
    return line(c, c + d * by, a, a + d * aim_by)


def truck(cam, aim, by) -> Move:
    """Camera and aim moved together by `by` (x, y, z metres): a truck sideways, a crane straight up, a track along."""
    b = _v(by)
    return line(cam, _v(cam) + b, aim, _v(aim) + b)


def crane(cam, aim, rise: float, *, aim_rise: float = 0.0, toward: float = 0.0) -> Move:
    """Up by `rise` metres (down when negative), the aim rising `aim_rise`, moving `toward` metres in along the ground."""
    c, a = _v(cam), _v(aim)
    flat = a - c
    flat[2] = 0.0
    flat /= max(np.linalg.norm(flat), 1e-9)
    return line(c, c + flat * toward + (0.0, 0.0, rise), a, a + (0.0, 0.0, aim_rise))


def path(cams, aims) -> Move:
    """Along a smooth path through `cams` (Catmull-Rom, through every point), the aim along `aims` (one point: held)."""
    C = [_v(p) for p in cams]
    A = [_v(p) for p in aims] if np.ndim(aims) == 2 else [_v(aims)]
    if len(C) < 2:
        raise ValueError("cinema.path: a path needs two points or more")

    def along(P, u):
        if len(P) == 1:
            return P[0]
        n = len(P) - 1
        s = min(u * n, n - 1e-9)
        i = int(s)
        pick = lambda j: P[min(max(j, 0), n)]  # noqa: E731 - the ends repeat: the path starts and stops on its points
        return catmull_rom(pick(i - 1), pick(i), pick(i + 1), pick(i + 2), s - i)

    return Move(lambda u: (along(C, u), along(A, u)))


def orbit(center, radius: float, height: float, bearing_from: float, bearing_to: float, *, aim=None) -> Move:
    """Round `center` at `radius` (m) and `height` over it, from one bearing to another (degrees from -y toward +x),
    aimed at `center` (or `aim`)."""
    o = _v(center)
    a = o if aim is None else _v(aim)

    def at(u):
        b = math.radians(bearing_from + (bearing_to - bearing_from) * u)
        return o + (radius * math.sin(b), -radius * math.cos(b), height), a

    return Move(at)


def drift(move: Move, amount: float = 0.04, *, seed: int = 1, cycles: float = 0.6) -> Move:
    """`move` with a slow wander on top (camera `amount` metres, the aim a little less): a camera that is never quite
    still. `cycles`: how many slow swings over the move."""
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 2 * math.pi, (2, 3))
    fr = rng.uniform(0.7, 1.3, (2, 3)) * cycles

    def at(u):
        c, a = move.at(u)
        w = np.sin(2 * math.pi * fr * u + ph)
        return c + w[0] * amount, a + w[1] * amount * 0.6

    return Move(at)


def frame_on(subject, height: float, *, share: float = 0.5, lens=50.0, bearing: float = 0.0, rise: float = 0.0,
             third: float = 0.0, headroom: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """(camera, aim) that frame `subject` (a world point: between the eyes, a figure's middle) so something `height`
    metres tall there fills `share` of the frame's height through `lens`, the camera at `bearing` (degrees from -y
    toward +x) and `rise` metres above the subject. `third`: where the subject sits across the frame (-1 the left third,
    +1 the right: leave room on the side they look to); `headroom`: how far above the frame's middle it sits (frame
    heights, + up). A close-up of a face: height chin to crown, share 0.4-0.6, 85 mm."""
    s = _v(subject)
    h = height / max(share, 1e-6)                     # the frame's height at the subject (m)
    d = h * lens_of(lens) / GATE_H
    b = math.radians(bearing)
    back = np.array([math.sin(b), -math.cos(b), 0.0])   # from the subject toward the camera
    flat = math.sqrt(max(d * d - rise * rise, 1e-9))
    cam = s + back * flat + (0.0, 0.0, rise)
    right = np.array([-back[1], back[0], 0.0])
    aim = s - right * third * (h * 16 / 9) / 6 - (0.0, 0.0, headroom * h)
    return cam, aim


def distance_for(height: float, share: float, lens) -> float:
    """How far a lens must stand for something `height` tall to fill `share` of the frame's height."""
    return height / max(share, 1e-6) * lens_of(lens) / GATE_H


# ---------------------------------------------------------------------------------------------------- shake

def _noise(t: float, seed: int, freq: float) -> np.ndarray:
    """Smooth seeded noise (yaw, pitch, roll) in about -1..1 at time t (s): incommensurate sines per axis."""
    rng = np.random.default_rng(seed)
    f = rng.uniform(0.6, 1.6, (3, 3)) * freq * np.array([1.0, 2.13, 4.37])
    ph = rng.uniform(0, 2 * math.pi, (3, 3))
    amp = np.array([0.6, 0.3, 0.15])
    return (np.sin(2 * math.pi * f * t + ph) * amp).sum(axis=1)


@dataclass(frozen=True)
class Shake:
    """A handheld camera: a slow breath (`breath` degrees, at about `freq` Hz) and hits (`hits`: (s into the shot,
    degrees)) that jolt it hard and die away over `decay` (1/s), faster and jerkier than the breath. `roll` scales the
    roll axis (a hand rolls less than it pans), `travel`: metres of sway per degree."""
    breath: float = 0.0
    freq: float = 0.35
    hits: tuple = ()
    decay: float = 5.0
    hit_freq: float = 7.0
    roll: float = 0.5
    travel: float = 0.004
    seed: int = 3

    def at(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        """(yaw, pitch, roll) degrees and a (right, up, back) sway in metres at shot time t."""
        rot = _noise(t, self.seed, self.freq) * self.breath
        for i, (t0, deg) in enumerate(self.hits):
            x = t - t0
            if x < 0:
                continue
            env = deg * math.exp(-x * self.decay)
            # the first instant knocks it one way (a hit has a direction), then it rattles back
            kick = np.array([0.4, -1.0, 0.6]) * math.exp(-x * self.decay * 4) * (1 if i % 2 == 0 else -1)
            rot = rot + (_noise(t, self.seed + 31 * (i + 1), self.hit_freq) + kick) * env
        rot = rot * np.array([1.0, 1.0, self.roll])
        return rot, np.array([rot[0], rot[1], 0.0]) * self.travel


def shake_amplitude(shake: Shake, t: float) -> float:
    """How hard `shake` is at time t (degrees): its breath plus its hits' envelopes."""
    return shake.breath + sum(d * math.exp(-(t - t0) * shake.decay) for t0, d in shake.hits if t >= t0)


# ---------------------------------------------------------------------------------------------------- orientation

def look_at(cam, aim, roll_deg: float = 0.0) -> np.ndarray:
    """The camera's world rotation (3x3, columns its x right, y up, z back: Blender's camera looks down -z) aiming from
    `cam` at `aim` with z up, rolled `roll_deg` (positive turns the image counter-clockwise)."""
    f = _v(aim) - _v(cam)
    f /= max(np.linalg.norm(f), 1e-12)
    r = np.cross(f, (0.0, 0.0, 1.0))
    if np.linalg.norm(r) < 1e-9:        # straight down or up: any right will do
        r = np.array([1.0, 0.0, 0.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    if roll_deg:
        a = math.radians(roll_deg)
        r, u = r * math.cos(a) + u * math.sin(a), u * math.cos(a) - r * math.sin(a)
    return np.column_stack([r, u, -f])


def _rot(axis: int, deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    m = np.eye(3)
    i, j = [(1, 2), (2, 0), (0, 1)][axis]
    m[i, i], m[i, j], m[j, i], m[j, j] = c, -s, s, c
    return m


def shaken(R: np.ndarray, yaw: float, pitch: float, roll: float) -> np.ndarray:
    """R turned in the camera's own axes: yaw about its up, pitch about its right, roll about its view (degrees)."""
    return R @ _rot(1, yaw) @ _rot(0, pitch) @ _rot(2, roll)


# ---------------------------------------------------------------------------------------------------- setups

@dataclass(frozen=True)
class Rack:
    """A focus pull: at `at` (s into the shot) the focus starts moving to `to` (a target: see Setup.focus), arriving
    `over` seconds later."""
    at: float
    to: object
    over: float = 0.5
    ease: str = "sine"


@dataclass(frozen=True)
class Setup:
    """One camera setup, from `at` (s into the shot) to the next setup's `at`.

    move    a Move (hold, push, line, truck, crane, path, orbit, drift)
    span    (from, to): seconds into the setup the move runs over (default all of it; held before and after: a held
            breath before the action, a settle after it). `ease` eases it.
    lens    mm or an intent (LENSES); a pair (from, to) zooms over the span
    fstop   the aperture (small: shallow); a pair keys it over the span
    focus   what is sharp: "aim" (default, the move's aim), a distance (m), a world point, an object, or (object, bone
            name) / (vrm Character, humanoid bone name). `racks` pull it to others during the setup.
    shake   a Shake; `roll` degrees of dutch (a pair rolls over the span); `blur` the motion blur's shutter (frames,
            0 off: fast action wants 0.5)"""
    name: str
    at: float
    move: Move
    span: tuple | None = None
    ease: str = "sine"
    lens: object = "mid"
    fstop: object = 4.0
    focus: object = "aim"
    racks: tuple = ()
    shake: Shake | None = None
    roll: object = 0.0
    blur: float = 0.0


def _pair(v, k: float) -> float:
    if isinstance(v, (tuple, list)):
        return float(v[0]) + (float(v[1]) - float(v[0])) * k
    return float(v)


@dataclass(frozen=True)
class Pose:
    """The camera at an instant."""
    setup: str
    index: int
    position: np.ndarray
    aim: np.ndarray
    rotation: np.ndarray       # 3x3 world rotation (look_at, rolled and shaken)
    lens: float
    fstop: float
    blur: float

    @property
    def forward(self) -> np.ndarray:
        return -self.rotation[:, 2]

    def depth(self, p) -> float:
        """How far a world point lies in front of the camera, along its view (what focus distance means)."""
        return float((_v(p) - self.position) @ self.forward)

    def screen(self, p, aspect: float = 16 / 9) -> tuple[float, float]:
        """Where a world point lands on screen, (u, v) frame fractions from the bottom left."""
        rel = _v(p) - self.position
        d = rel @ self.forward
        h = d * GATE_H / self.lens
        return 0.5 + float(rel @ self.rotation[:, 0]) / (h * aspect), 0.5 + float(rel @ self.rotation[:, 1]) / h


class Shot:
    """A shot's setups over its `duration` (s): pure, so a shot can check its framing before Blender builds it."""

    def __init__(self, setups, duration: float):
        self.setups = sorted(setups, key=lambda s: s.at)
        if not self.setups:
            raise ValueError("cinema: a shot needs a setup")
        if self.setups[0].at > 1e-9:
            raise ValueError(f"cinema: the first setup must start at 0 s, not {self.setups[0].at}")
        names = [s.name for s in self.setups]
        if len(set(names)) != len(names):
            raise ValueError(f"cinema: setup names repeat: {names}")
        self.duration = float(duration)

    def index_at(self, t: float) -> int:
        i = 0
        for k, s in enumerate(self.setups):
            if t + 1e-9 >= s.at:
                i = k
        return i

    def window(self, i: int) -> tuple[float, float]:
        """Setup i's [start, end) in seconds."""
        end = self.setups[i + 1].at if i + 1 < len(self.setups) else self.duration
        return self.setups[i].at, end

    def progress(self, i: int, t: float) -> float:
        """How far setup i's move has got at time t (0..1, eased)."""
        s = self.setups[i]
        a, b = self.window(i)
        lo, hi = (0.0, b - a) if s.span is None else s.span
        return ease((t - a - lo) / max(hi - lo, 1e-9), s.ease)

    def pose(self, t: float) -> Pose:
        i = self.index_at(t)
        s = self.setups[i]
        k = self.progress(i, t)
        cam, aim = s.move.at(k)
        R = look_at(cam, aim, _pair(s.roll, k))
        if s.shake is not None:
            (yaw, pitch, roll), sway = s.shake.at(t)
            R = shaken(R, yaw, pitch, roll)
            cam = cam + R @ sway
        lens = (lens_of(s.lens[0]), lens_of(s.lens[1])) if isinstance(s.lens, (tuple, list)) else lens_of(s.lens)
        return Pose(s.name, i, cam, aim, R, _pair(lens, k), _pair(s.fstop, k), float(s.blur))

    def cuts(self) -> list[float]:
        """The times the picture cuts (every setup's start after the first)."""
        return [s.at for s in self.setups[1:]]

    # the focus: every target the shot is ever focused on, in order, and how much of each at an instant

    def focus_chain(self) -> list[tuple[int, object]]:
        """[(setup index, target)] in the order the shot focuses on them: each setup's focus, then its racks."""
        chain = []
        for i, s in enumerate(self.setups):
            chain.append((i, s.focus))
            for r in sorted(s.racks, key=lambda r: r.at):
                chain.append((i, r.to))
        return chain

    def focus_weights(self, t: float) -> list[float]:
        """The influence of each focus_chain target's constraint at time t: the chain blends in order (each constraint
        pulls the result toward its target by its influence), so the target before the current one is at 1 and the
        current one at how far its pull has got."""
        chain = self.focus_chain()
        i = self.index_at(t)
        first = next(j for j, (si, _) in enumerate(chain) if si == i)
        cur, k = first, 1.0
        for r in sorted(self.setups[i].racks, key=lambda r: r.at):
            if t + 1e-9 < r.at:
                break
            cur += 1
            k = ease((t - r.at) / max(r.over, 1e-9), r.ease)
        w = [0.0] * len(chain)
        if cur == first or k >= 1.0:
            w[cur] = 1.0
        else:
            w[cur - 1], w[cur] = 1.0, k
        return w


# ---------------------------------------------------------------------------------------------------- Blender

def _target(spec):
    """(object, bone name or "") a focus spec names; None for "aim" or a number or a point (the rig makes those)."""
    if spec == "aim" or isinstance(spec, (int, float)) or (isinstance(spec, (tuple, list)) and len(spec) == 3
                                                           and all(isinstance(x, (int, float)) for x in spec)):
        return None
    if isinstance(spec, (tuple, list)) and len(spec) == 2:
        ob, bone = spec
        if hasattr(ob, "armature") and hasattr(ob, "bones"):      # a vrm Character and a humanoid bone
            from .vrm import canonical
            return ob.armature, ob.bones[canonical(bone)]
        return ob, bone
    return spec, ""


class Rig:
    """The camera `film` built: `camera` (scene.camera), `aim` and `focus` (empties), the pure `shot`, and the shot's
    frames. `pose(f)` / `setup_at(f)` at a film frame; `per_setup(owner, path, {setup: value})` keys anything else that
    changes with the setup (a light, a line art's visibility) held across the cuts."""

    def __init__(self, ctx, shot: Shot, camera, aim, focus):
        self.ctx, self.shot, self.camera, self.aim, self.focus = ctx, shot, camera, aim, focus
        self.f0, self.f1 = ctx.f0, ctx.f1

    def time(self, f: int) -> float:
        return (f - self.f0) / self.ctx.fps

    def pose(self, f: int) -> Pose:
        return self.shot.pose(self.time(f))

    def setup_at(self, f: int) -> str:
        return self.shot.setups[self.shot.index_at(self.time(f))].name

    @property
    def frames(self) -> range:
        """Every frame keyed: the shot's, and one either side (motion blur and a handle for the edit)."""
        return range(self.f0 - 1, self.f1 + 1)

    @property
    def cuts(self) -> list[int]:
        """The film frames a new setup starts on."""
        return [self.f0 + round(t * self.ctx.fps) for t in self.shot.cuts()]

    def per_setup(self, owner, path: str, values: dict, default=None, index: int = -1) -> None:
        """Key `owner`.`path` to values[setup name] (else `default`) on every frame, held across the cuts."""
        for f in self.frames:
            v = values.get(self.setup_at(f), default)
            if v is None:
                continue
            _set_path(owner, path, v)
            owner.keyframe_insert(path, frame=f, index=index)
        hold_cuts(owner, self.cuts)


def _set_path(owner, path: str, v) -> None:
    if path.startswith("["):
        owner[path[2:-2]] = v
    else:
        setattr(owner, path, v)


def hold_cuts(owner, cuts) -> None:
    """Make `owner`'s keys on the frame before each cut constant, so nothing tweens across a cut (and a shutter that
    opens on that frame sees it held)."""
    from .toon import _fcurves

    ad = getattr(owner, "animation_data", None)
    if ad is None or ad.action is None:
        return
    before = {c - 1 for c in cuts}
    for fc in _fcurves(ad.action):
        for kp in fc.keyframe_points:
            if round(kp.co[0]) in before:
                kp.interpolation = "CONSTANT"


def film(ctx, setups, *, name: str = "camera", clip=(0.02, 3000.0), jitter: bool = True) -> Rig:
    """Build the shot's camera from `setups` (Setup) over ctx's frames, set it as scene.camera and return the Rig.
    Every frame is keyed (position and rotation computed here, never a constraint: the pose a frame renders is the pose
    `Rig.pose` gives); focus follows its targets live (the focus empty's constraints, blended by the rack weights)."""
    import bpy
    from mathutils import Euler, Matrix

    from .rig import engine_camera

    scene = ctx.scene
    shot = Shot(setups, (ctx.f1 - ctx.f0) / ctx.fps)
    cam = engine_camera(name, fstop=4.0, size=ctx.size)
    cam.data.clip_start, cam.data.clip_end = clip
    cam.rotation_mode = "XYZ"
    scene.camera = cam
    aim = bpy.data.objects.new(f"{name}-aim", None)
    focus = bpy.data.objects.new(f"{name}-focus", None)
    for ob in (aim, focus):
        ob.empty_display_size = 0.1
        scene.collection.objects.link(ob)
    cam.data.dof.focus_object = focus
    if jitter and hasattr(scene.eevee, "use_dof_jitter"):
        scene.eevee.use_dof_jitter = True     # physically sampled depth of field across the samples
    rig = Rig(ctx, shot, cam, aim, focus)

    # the focus: one Copy Location per target in the chain, blended by its weights
    chain = shot.focus_chain()
    cons = []
    for j, (si, spec) in enumerate(chain):
        t = _target(spec)
        if t is None:
            if spec == "aim":
                ob, bone = aim, ""
            elif isinstance(spec, (int, float)):
                ob = bpy.data.objects.new(f"{name}-focus{j}", None)       # a distance: an empty riding the camera
                scene.collection.objects.link(ob)
                ob.parent = cam
                ob.location = (0.0, 0.0, -float(spec))
                bone = ""
            else:
                ob = bpy.data.objects.new(f"{name}-focus{j}", None)       # a world point
                scene.collection.objects.link(ob)
                ob.location = tuple(float(x) for x in spec)
                bone = ""
        else:
            ob, bone = t
        c = focus.constraints.new("COPY_LOCATION")
        c.name = f"focus{j}"
        c.target = ob
        if bone:
            c.subtarget = bone
            c.head_tail = 0.5
        cons.append(c)

    blur_any = any(s.blur > 0 for s in shot.setups)
    r = scene.render
    r.use_motion_blur = blur_any
    if blur_any:
        r.motion_blur_position = "START"     # the shutter opens on the frame: a held cut stays clean
    prev = None
    for f in rig.frames:
        t = rig.time(f)
        p = shot.pose(t)
        e = Matrix([list(row) for row in p.rotation]).to_euler("XYZ", prev) if prev else \
            Matrix([list(row) for row in p.rotation]).to_euler("XYZ")
        prev = Euler(e)
        cam.location = tuple(p.position)
        cam.rotation_euler = e
        aim.location = tuple(p.aim)
        cam.data.lens = p.lens
        cam.data.dof.aperture_fstop = p.fstop
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
        aim.keyframe_insert("location", frame=f)
        cam.data.keyframe_insert("lens", frame=f)
        cam.data.dof.keyframe_insert("aperture_fstop", frame=f)
        for c, w in zip(cons, shot.focus_weights(t)):
            c.influence = w
            c.keyframe_insert("influence", frame=f)
        if blur_any:
            r.motion_blur_shutter = max(p.blur, 1e-3)
            scene.keyframe_insert("render.motion_blur_shutter", frame=f)
    for owner in (cam, aim, cam.data, focus) + ((scene,) if blur_any else ()):
        hold_cuts(owner, rig.cuts)
    print(f"cinema: {len(shot.setups)} setup(s) " + ", ".join(f"{s.name}@{s.at:.2f}s {shot.pose(s.at).lens:.0f}mm"
                                                            for s in shot.setups) + f"; cuts on film frames {rig.cuts}")
    return rig

