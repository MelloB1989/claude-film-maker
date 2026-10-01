"""B03, the re-form (scene `her`, spec §4 03): the thread that snapped in the cold open is drawn back together, and is
born again as the diff thread. The film's turning point, inside "Not me.".

The same rope and the same camera as B01 (b01_thread.py): its bone 3-ply, fibre by fibre at a 24 degree lay, the same
seed (so these are the very ends that broke), an 85 mm lens wide open on ink, a warm-neutral key raking in from the upper
left, a soft top light and a hard rim from behind. The world is `her`'s (data/look/b03_reform.json): the thread lies on
her engine thread's line, at its radius, and B03's camera is her shot 1's camera rig, so the plate hands off to the
engine thread inside the whip on the downbeat, with nothing to match by eye.

  - The cut in (the scene's first beat): the two frayed ends glide in from off frame, one from each side, rim-lit
    brushes of broken fibre, their tips still drooping from the fall; the key comes up on them as the camera eases in.
  - The draw: they slow as they near, straighten as the tension comes back, and hang a breath apart, the brushes
    gathering toward each other, while a point of blood light kindles in the gap between them.
  - "Not": they snap together onto it. The ends twist into each other, the brushes interleave and close, the cores
    reconnect, the fray heals, and the light is born as the blood strand: a hot tip racing out along its groove both ways
    from the join, the moss strand a beat behind it, dark. As they lay in, the rope's lay draws out from 24 degrees to
    DIFF_THREAD's 14 (the visible transformation): the stripes stretch away from the join. A tension ripple runs out
    along the rope, and it hums like a plucked string.
  - "me.": it hums again, softer, and settles to the diff thread's rest look, the blood dying back to a dark seam
    (DIFF_THREAD's strand_glow, the engine's envelope), the camera drawing back to show the thread whole.
  - The whip on the downbeat is the engine's: the plate's last frame is the one before it starts, its camera, thread
    and lay the engine's own there (her.ts).

Everything is a pure function of the film frame (+ subframe) and the seeded rope: a frame_change_pre handler poses the
rope, the strands, the camera and the light at every motion-blur step. Tracked, for the engine: `join`, where the ends
meet (fixed in the world, so it also proves the plate's camera is her rig: her-reform.test.ts), and the two break ends
`end_l`, `end_r` as they come in.

  Blender -b -P blender/render.py -- --shot b03_reform --mode look            (the key moments, 960x540)
  Blender -b -P blender/render.py -- --shot b03_reform --mode preview         (the window: proxies + track)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
SPEC_FILE = REPO / "data" / "look" / "b03_reform.json"
SPEC = json.loads(SPEC_FILE.read_text())


# ------------------------------------------------------------------------------------------------ the world
#
# her's world is the engine's: metres, y up. Blender's is z up. (x, y, z) in the engine is (x, -z, y) in Blender: a
# proper rotation, so cross products, handedness and the thread's twist carry over unchanged.

ENGINE_TO_BLENDER = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])


def to_blender(v) -> np.ndarray:
    return ENGINE_TO_BLENDER @ np.asarray(v, float)


class World:
    """her's thread line in engine coordinates: from A to B, radius R, its direction d, the horizontal square to it on
    the viewer's side n (her.ts `side`), world up Y, and the join point J at arc fraction `join` (where the camera looks
    and the ends meet). `at(off)` turns offsets in thread radii along (d, n, Y) from J into points. (Plain classes:
    render.py loads a shot without registering its module, which dataclasses need.)"""

    def __init__(self, A, B, R: float, u_join: float):
        self.A, self.B, self.R, self.u_join = np.asarray(A, float), np.asarray(B, float), float(R), float(u_join)

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.B - self.A))

    @property
    def d(self) -> np.ndarray:
        return (self.B - self.A) / self.length

    @property
    def n(self) -> np.ndarray:
        d = self.d
        v = np.array([-d[2], 0.0, d[0]])
        return v / np.linalg.norm(v)

    @property
    def J(self) -> np.ndarray:
        return self.A + self.u_join * (self.B - self.A)

    def at(self, off) -> np.ndarray:
        """J + R (a d + b n + c Y) for off = (a, b, c)."""
        a, b, c = off
        return self.J + self.R * (a * self.d + b * self.n + c * np.array([0.0, 1.0, 0.0]))


WORLD = World(np.array(SPEC["thread"]["a"], float), np.array(SPEC["thread"]["b"], float), SPEC["thread"]["radius"],
              SPEC["join"])


# ------------------------------------------------------------------------------------------------ time

class Cues:
    """The shot's times, from the data (her.ts timesOf): the scene's start, the onsets of "Not" and "me." (L06), the
    downbeat after "me." (the whip's centre), and the hand-off: the whip's first instant, where the engine takes over."""

    def __init__(self, timing):
        self.start = timing.scene("her")[0]
        self.not_ = timing.word("L06", 0).start
        self.me = timing.word("L06", 1).start
        self.down = next(d for d in timing.audio["downbeats"] if d > self.me)
        self.hand = self.down - SPEC["whip"] / 2

    def cue(self, name: str) -> float:
        return {"start": self.start, "not": self.not_, "me": self.me, "down": self.down, "hand": self.hand}[name]


def _shot_frames() -> list[int]:
    """The plate's film frames [f0, f1): from her's first frame to the first one the whip touches (the engine's)."""
    from lib import timing

    t = timing.film()
    return [t.scene_frames("her")[0], timing.first_frame_from(Cues(t).hand)]


# ------------------------------------------------------------------------------------------------ the camera
#
# her's CameraRig (app/src/engine/stage.ts), ported: keys at cue times with a position, a target, a vertical fov and a
# roll; between keys the position and target follow a centripetal Catmull-Rom through all of them, fov and roll
# interpolate, each segment timed by the ease of the key it heads to. her.ts builds the same rig from the same keys
# (her-reform.ts), so the plate and the engine see through one camera; her-reform.test.ts checks the tracked join
# against the engine's projection of it.

def _in_out_cubic(x):
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


EASE = {
    "linear": lambda x: x,
    "inQuad": lambda x: x * x,
    "outQuad": lambda x: 1 - (1 - x) ** 2,
    "inOutQuad": lambda x: 2 * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 2 / 2,
    "inCubic": lambda x: x ** 3,
    "outCubic": lambda x: 1 - (1 - x) ** 3,
    "inOutCubic": _in_out_cubic,
    "outQuart": lambda x: 1 - (1 - x) ** 4,
    "inOutQuart": lambda x: 8 * x ** 4 if x < 0.5 else 1 - (-2 * x + 2) ** 4 / 2,
}


def _catmull_rom(p0, p1, p2, p3, u: float) -> np.ndarray:
    """stage.ts catmullRom: centripetal (Barry-Goldman) between p1 and p2; a missing or coincident neighbour mirrored."""
    p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
    d12 = float(np.linalg.norm(p1 - p2))
    if d12 < 1e-9:
        return p1.copy()
    if p0 is None or np.linalg.norm(np.asarray(p0) - p1) < 1e-9:
        p0 = 2 * p1 - p2
    if p3 is None or np.linalg.norm(p2 - np.asarray(p3)) < 1e-9:
        p3 = 2 * p2 - p1
    p0, p3 = np.asarray(p0, float), np.asarray(p3, float)
    t1 = math.sqrt(np.linalg.norm(p0 - p1))
    t2 = t1 + math.sqrt(d12)
    t3 = t2 + math.sqrt(np.linalg.norm(p2 - p3))
    t = t1 + u * (t2 - t1)
    a1 = ((t1 - t) * p0 + t * p1) / t1
    a2 = ((t2 - t) * p1 + (t - t1) * p2) / (t2 - t1)
    a3 = ((t3 - t) * p2 + (t - t2) * p3) / (t3 - t2)
    b1 = ((t2 - t) * a1 + t * a2) / t2
    b2 = ((t3 - t) * a2 + (t - t1) * a3) / (t3 - t1)
    return ((t2 - t) * b1 + (t - t1) * b2) / (t2 - t1)


class Pose:
    """A camera in engine coordinates: position, target, vertical fov and roll (degrees)."""

    def __init__(self, pos, target, fov: float, roll: float):
        self.pos, self.target = np.asarray(pos, float), np.asarray(target, float)
        self.fov, self.roll = float(fov), float(roll)

    def basis(self) -> np.ndarray:
        """The camera's axes (columns x, y, z; it looks down -z) as three's lookAt (up y) then rotateZ(roll) set them."""
        z = self.pos - self.target
        z = z / np.linalg.norm(z) if np.linalg.norm(z) > 0 else np.array([0.0, 0.0, 1.0])
        up = np.array([0.0, 1.0, 0.0])
        x = np.cross(up, z)
        if np.linalg.norm(x) < 1e-12:  # looking straight up or down: three nudges z
            z = z + np.array([1e-4, 0.0, 0.0])
            z /= np.linalg.norm(z)
            x = np.cross(up, z)
        x /= np.linalg.norm(x)
        y = np.cross(z, x)
        r = math.radians(self.roll)
        c, s = math.cos(r), math.sin(r)
        return np.column_stack([x, y, z]) @ np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])

    def depth(self, p) -> float:
        """A point's depth along the view axis (stage.ts depthOf: what the focus distance is measured in)."""
        return float(-(self.basis()[:, 2] @ (np.asarray(p, float) - self.pos)))

    def project(self, p, aspect: float = 16 / 9) -> tuple[float, float]:
        """A point's place on the film's logical 1920x1080 frame (px from the top left)."""
        b = self.basis()
        v = b.T @ (np.asarray(p, float) - self.pos)
        ty = math.tan(math.radians(self.fov) / 2)
        x, y = v[0] / (-v[2] * ty * aspect), v[1] / (-v[2] * ty)
        return 960 * (1 + x), 540 * (1 - y)


class Rig:
    """stage.ts CameraRig from SPEC['camera'] keys: each {cue, dt, eye, look, roll, fov?, ease?}, eye and look being
    offsets from the join in thread radii along (d, n, Y), the key's time its cue's + dt."""

    def __init__(self, cues: Cues, keys=None, world: World = WORLD):
        ks = []
        fov, roll = None, 0.0
        for k in sorted(keys or SPEC["camera"], key=lambda k: cues.cue(k["cue"]) + k.get("dt", 0.0)):
            fov = k.get("fov", fov)
            roll = k.get("roll", roll)
            if fov is None:
                raise ValueError("the first camera key needs a fov")
            ks.append({"t": cues.cue(k["cue"]) + k.get("dt", 0.0), "pos": world.at(k["eye"]),
                       "target": world.at(k["look"]), "fov": fov, "roll": roll, "ease": EASE[k.get("ease", "inOutCubic")]})
        self.keys = ks

    def at(self, t: float) -> Pose:
        ks, n = self.keys, len(self.keys)
        i = 0
        while i < n and ks[i]["t"] <= t:
            i += 1
        if i == 0 or i == n or ks[i - 1]["t"] == t:
            k = ks[max(0, i - 1)]
            return Pose(k["pos"].copy(), k["target"].copy(), k["fov"], k["roll"])
        a, b = ks[i - 1], ks[i]
        e = b["ease"]((t - a["t"]) / (b["t"] - a["t"]))
        nb = lambda j: ks[j]["pos"] if 0 <= j < n else None  # noqa: E731
        nt = lambda j: ks[j]["target"] if 0 <= j < n else None  # noqa: E731
        return Pose(_catmull_rom(nb(i - 2), a["pos"], b["pos"], nb(i + 1), e),
                    _catmull_rom(nt(i - 2), a["target"], b["target"], nt(i + 1), e),
                    a["fov"] + (b["fov"] - a["fov"]) * e, a["roll"] + (b["roll"] - a["roll"]) * e)




# ------------------------------------------------------------------------------------------------ the story
#
# Lengths in thread radii R unless named in metres; times in film seconds. Every amount is a pure function of t.

SEED = 7  # b01_thread.py's: the same rope, so these are the very ends that broke
LENGTH_R = 80.0
LAY_FROM = 24.0  # B01's lay; DIFF_THREAD's 14 is where it goes
FRAY_SPAN = 4.5  # B01's fray, open as the snap left it (x 1.3)
UNRAVEL, SPLAY, BRUSH = 0.25, 0.45, 0.18  # B01's broken ends as the snap left them
# the draw
GAP_START, GAP_HOVER = 40.0, 9.0  # apart as it opens, and as they hang (the brushes' longest fibres just reach each
# other: a fibre parts up to 4.2 R past the break)
HANG, PULL = 0.25, 4.0  # they hang from this long before "Not", drawn together like magnets: the gap closes as
# (1 - x^PULL) of the hang, all but still at first, then faster and faster, shut on "Not"
CURL0, CURL_LEN = math.radians(26), 4.0  # how far a free end still droops as it comes in, and over what length
GATHER = 0.5  # how far the brushes draw in toward each other as they hang (a fraction of their spread)
# the birth
SEED_R, KINDLE, BEAD = 0.45, 0.13, 1.5  # the strand is born this long each way on "Not", BEAD x its radius at the join
# (it slims to the strand as it lays in); before it, over KINDLE s, only its light: the facing fibre tips blush red
SPARK_W, TIP_W, BLUSH = 0.012, 0.0012, 1.0  # the light it sheds on the fibres round it (W): at the join, and riding
# each blood tip; before "Not" the join's light rises to BLUSH of it, from nothing you can see
STRANDS = {"blood": {"lag": 0.0, "v0": 72.0, "tau": 0.3, "cue": "not"},  # races out from the join, R/s, slowing
           "moss": {"lag": 0.05, "v0": 64.0, "tau": 0.3, "cue": "down"}}  # a beat behind it (glows on the bead)
TIP_HEAT, TIP_LEN, TIP_FADE = 1.6, 1.4, 0.3  # the blood strand's tip burns hotter as it lays in
SPARK_HEAT, SPARK_LEN, SPARK_FADE = 2.6, 0.9, 0.14  # and the join flashes as it's born
# the hum and the ripple
HUM, HUM_HZ, HUM_DECAY = 0.12, 7.5, 0.13
RIPPLE, RIPPLE_SPEED = 0.35, 150.0


def clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def smooth(x: float) -> float:
    x = clip01(x)
    return x * x * (3 - 2 * x)


def prog(t: float, a: float, b: float, ease: str = "linear") -> float:
    return EASE[ease](clip01((t - a) / (b - a)))


class Story:
    """The shot's choreography (pure; tested without Blender)."""

    def __init__(self, cues: Cues, R: float):
        self.c, self.R = cues, R
        self.hover = cues.not_ - HANG  # they hang a breath apart from here, drawn shut on "Not"

    def gap(self, t: float) -> float:
        """How far apart the two broken ends are, along the line (m)."""
        c = self.c
        e = prog(t, c.start - 0.05, self.hover, "outQuad")  # in from off frame, slowing into the hover
        x = clip01((t - self.hover) / (c.not_ - self.hover))
        return (GAP_START + (GAP_HOVER - GAP_START) * e) * (1 - x ** PULL) * self.R  # then drawn shut on "Not"

    def curl(self, t: float) -> float:
        """How far a free end still droops (radians): straightening as the tension comes back."""
        return CURL0 * (1 - smooth((t - self.c.start) / (self.hover - self.c.start)))

    def gather(self, t: float) -> float:
        """0..1: the brushes drawing in toward each other as the ends hang apart."""
        return smooth((t - (self.hover - 0.08)) / (HANG + 0.02))

    def knit(self, t: float) -> dict:
        """0..1 per part of the re-form, from the contact on "Not": the ends twist back into each other, the cores
        reconnect, the plies close, the brushes interleave and lie down, the fibres thicken, the fray heals, the strands
        rise into their grooves at the join, and the lay draws out from 24 to 14 degrees."""
        d = t - self.c.not_
        return {"twist": prog(d, 0.0, 0.18, "outCubic"), "core": prog(d, 0.0, 0.1, "outQuad"),
                "splay": prog(d, 0.0, 0.2, "outCubic"), "brush": prog(d, -0.01, 0.24, "outQuad"),
                "broken": prog(d, 0.02, 0.24), "fray": prog(d, 0.02, 0.34, "inOutCubic"),
                "depth": prog(d, 0.06, 0.3, "inOutCubic"), "lay": prog(d, 0.04, 0.46, "inOutCubic")}

    def extent(self, t: float, strand: str) -> float:
        """How far a strand reaches from the join, each way (m): the blood strand a bead of light kindling in the gap
        between the ends, then both racing out along their grooves from the contact and slowing."""
        p = STRANDS[strand]
        at = self.c.not_ + p["lag"]
        if t < at:
            return 0.0
        return (SEED_R + p["v0"] * p["tau"] * (1 - math.exp(-(t - at) / p["tau"]))) * self.R

    def heat(self, strand: str, x, t: float, e: float):
        """Glow added along a strand (on top of its level) at |distance from the join| x (m, an array): the blood
        strand's hot tip as it lays in, and the flash at the join where it's born. The moss strand is born dark."""
        x = np.asarray(x, float)
        if strand != "blood" or e <= 0:
            return np.zeros_like(x)
        R = self.R
        tip = TIP_HEAT * self.tip(t) * np.exp(-np.maximum(e - x, 0.0) / (TIP_LEN * R))
        return np.where(x <= e, tip + SPARK_HEAT * self.spark(t) * np.exp(-x / (SPARK_LEN * R)), 0.0)

    def spark(self, t: float) -> float:
        """0..1: the light at the join: rising unseen in the gap before "Not" (the facing tips blush, to BLUSH), flashing
        as the ends close on it, then fading as the strands carry it away."""
        d = t - self.c.not_
        return BLUSH * smooth((d + KINDLE) / KINDLE) ** 2 if d < 0 else math.exp(-d / SPARK_FADE)

    def tip(self, t: float) -> float:
        """0..1: how hot the blood strand's tips burn as they race out (cooling as they slow)."""
        d = t - self.c.not_
        return math.exp(-d / TIP_FADE) if d > 0 else 0.0

    def bead(self, t: float) -> float:
        """How much fatter than the strand the light is at the join: a bead before the contact, a strand after."""
        return 1 + (BEAD - 1) * (1 - prog(t - self.c.not_, 0.0, 0.12, "outQuad"))

    def hum(self, x, t: float):
        """The rope's displacement square to it (m) at distance x from the join (m, an array): it hums like a plucked
        string from the contact, again softer on "me.", and the impact runs out both ways as a ripple."""
        x = np.abs(np.asarray(x, float))
        R, c = self.R, self.c
        y = np.zeros_like(x)
        for at, amp in ((c.not_, 1.0), (c.me, 0.45)):
            d = t - at
            if d > 0:
                y = y + amp * HUM * R * (1 - math.exp(-d / 0.01)) * math.exp(-d / HUM_DECAY) * math.sin(
                    2 * math.pi * HUM_HZ * d)
        d = t - c.not_
        if d > 0:
            y = y + RIPPLE * R * math.exp(-d / 0.1) * np.exp(-((x - RIPPLE_SPEED * R * d) / (4 * R)) ** 2)
        return y

    def light(self, t: float) -> dict:
        """Each light's share of its power: the rim draws the ends first as they come in, the key comes up on them;
        on the contact the key dips as the blood light is born and comes back as it spreads."""
        on = t - self.c.start
        d = t - self.c.not_
        # the key held a little low while the bare ends hang (the brushes keep their modelling), then dipping hard as the
        # light is born so the join burns blood, not pink, and coming back as it spreads
        dip = 0.7 * smooth((d + 0.04) / 0.04) * math.exp(-max(d, 0.0) / 0.22)
        hang = 0.85 + 0.15 * smooth(d / 0.3)
        return {"rim": smooth(on / 0.04), "key": (0.2 + 0.8 * smooth((on - 0.04) / 0.35)) * hang * (1 - dip),
                "top": smooth((on - 0.04) / 0.35) * hang * (1 - 0.6 * dip)}

    def lift(self, t: float) -> float:
        """The fuzz bristles on the impact and settles (extra lift, radians)."""
        d = t - self.c.not_
        return 0.3 * math.exp(-d / 0.15) if d > 0 else 0.0


def relay(twist_from: float, s_join: float, twist_to: float, world: World = WORLD) -> tuple[float, dict]:
    """How the lay draws out so the hand-off lines up ply for ply: the turns `fix` (|fix| <= 1/6) added at the join as
    the twist goes from `twist_from` to `twist_to` turns per metre, so the plies end on the engine thread's own phase
    there (turns x u at the join: twist_to x u_join x |AB|, the same three plies a third of a turn apart), and the
    strands' grooves (turns from ply 0), moved a groove over for each whole third of a turn left over, so the blood and
    the moss strand end where the engine's are (diff_tubes: blood at 1/2, moss at 1/6)."""
    delta = twist_to * world.u_join * world.length - twist_from * s_join
    thirds = round(3 * delta)
    return delta - thirds / 3, {"blood": (0.5 + thirds / 3) % 1, "moss": (1 / 6 + thirds / 3) % 1}


def _look_frames() -> str:
    """The key moments: the ends coming in, hanging apart, the contact, the strands laying in, the lay drawn out,
    "me.", and the hand-off (the plate's last frame)."""
    from lib import timing

    c = Cues(timing.film())
    f1 = _shot_frames()[1]
    ts = [c.start + 0.19, c.not_ - 0.2, c.not_ - 0.07, c.not_ - 0.008, c.not_ + 0.025, c.not_ + 0.09, c.not_ + 0.19,
          c.me]
    return ",".join(str(f) for f in sorted({timing.frame(x) for x in ts} | {f1 - 1}))


SHOT = {"scene": "her", "frames": _shot_frames(), "track": ["join", "end_l", "end_r"], "look": _look_frames()}


# ------------------------------------------------------------------------------------------------ build

def build(ctx):
    import bpy
    from mathutils import Matrix, Vector

    from lib import lights, thread

    scene, coll = ctx.scene, ctx.scene.collection
    cues = Cues(ctx.timing)
    W, R = WORLD, WORLD.R
    story = Story(cues, R)
    rig = Rig(cues)

    d = to_blender(W.d)
    J = to_blender(W.J)
    up = np.array([0.0, 0.0, 1.0])
    n0 = up - d * (up @ d)  # the engine's thread frame: world up square to the thread (her's RMF on a straight line)
    n0 /= np.linalg.norm(n0)

    rope = thread.fibre_rope(R, LENGTH_R * R, seed=SEED, fibres=72, fibre_radius=0.022, fuzz_per_R=48,
                             samples_per_R=10, fray_span=FRAY_SPAN, fray_per_R=34, lay_deg=LAY_FROM)
    rope.fray_separation, rope.fray_swell, rope.fray_untwist, rope.fray_loose = 1.0, 0.04, 0.7, 0.03  # B01's
    s_b = rope.break_at
    halves = {side: thread.half_samples(rope, side) for side in ("left", "right")}
    grid = rope.grid

    twist_to = thread.diff_twist(R)
    fix, grooves = relay(rope.twist, s_b, twist_to)
    depth_D = thread.diff_tubes()[3]["d"]
    strand_r = thread.diff_tubes()[3]["r"] * R

    fibre = thread.fibre_material("b03_fibre")
    core = thread.fibre_material("b03_core", core=True)
    mr = thread.MacroRope(rope, name="thread", fibre_mat=fibre, core_mat=core, collection=coll)
    mats = {c: thread.strand_material(c, name=f"b03_{c}", heat_attr="heat") for c in ("blood", "moss")}
    tubes = {c: thread.StrandTube(f"strand.{c}", len(grid), mats[c], collection=coll) for c in ("blood", "moss")}

    # the camera: her shot 1's rig (stage.ts CameraRig), engine coordinates turned to Blender's
    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    cam.data.sensor_fit = "VERTICAL"
    cam.data.sensor_height = 20.25  # the engine's DoF camera: a 36 mm gate shooting 16:9 (dof.ts DOF_SENSOR_H)
    cam.data.sensor_width = 36.0
    cam.data.clip_start, cam.data.clip_end = 0.005, 50.0
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = SPEC["fstop"]
    cam.data.dof.aperture_blades = 0
    coll.objects.link(cam)
    scene.camera = cam

    def place_camera(t: float) -> None:
        p = rig.at(t)
        rot = ENGINE_TO_BLENDER @ p.basis()
        m = Matrix([[*rot[0], 0.0], [*rot[1], 0.0], [*rot[2], 0.0], [0.0, 0.0, 0.0, 1.0]])
        cam.matrix_world = Matrix.Translation(Vector(to_blender(p.pos))) @ m
        cam.data.lens = 10.125 / math.tan(math.radians(p.fov) / 2)
        cam.data.dof.focus_distance = p.depth(W.J)

    # light: B01's rig (a warm-neutral key raking from the upper left and in front, a soft top light, a hard rim from
    # behind), set round the join in the camera's frame at "Not"
    p0 = rig.at(cues.not_)
    b0 = p0.basis()
    right = to_blender(b0[:, 0])
    fwd = to_blender(-b0[:, 2])
    fwd = fwd - up * (fwd @ up)
    fwd /= np.linalg.norm(fwd)
    ls = R / 0.005  # the rig was set up round a 5 mm thread: distances scale with R, power with its square
    P = Vector(J)
    kd = -0.75 * right + 0.5 * up - 0.35 * fwd
    kd /= np.linalg.norm(kd)
    key = _light("key", "SPOT", 45.0 * ls * ls / 5.76, P + Vector(kd * 0.5 * ls), P, spot=math.radians(50),
                 soft=0.08 * ls, temperature=5600)
    key.data.spot_blend = 0.85
    top = _light("top", "AREA", 0.6 * ls * ls, P + Vector((0.15 * fwd + 0.5 * up) * ls), P, size=0.3 * ls,
                 temperature=6200)
    rim = _light("rim", "SPOT", 200.0 * ls * ls, P + Vector((0.10 * right + 0.55 * fwd + 0.25 * up) * ls), P,
                 spot=math.radians(24), soft=0.003 * ls, temperature=6500)
    power = {ob.name: ob.data.energy for ob in (key, top, rim)}
    for ob in (key, top, rim):
        coll.objects.link(ob)
    lights.world_color("ink")
    hum_dir = to_blender(b0[:, 1]) - d * (to_blender(b0[:, 1]) @ d)  # the hum moves it up and down the frame
    # the blood light on the fibres round it: the strand's core is too slim to light them itself
    blood_rgb = thread.glow_color("blood")

    def _point(name):
        ob = bpy.data.objects.new(name, bpy.data.lights.new(name, "POINT"))
        ob.data.color = blood_rgb
        ob.data.shadow_soft_size = 0.12 * R
        ob.data.energy = 0.0
        ob.visible_camera = False  # its light on the fibres, never the light itself
        coll.objects.link(ob)
        return ob

    spark = _point("spark")
    tip_lights = [_point("tip_l"), _point("tip_r")]
    hum_dir /= np.linalg.norm(hum_dir)

    anchors = {}
    for name in ("join", "end_l", "end_r"):
        e = bpy.data.objects.new(name, None)
        e.empty_display_size = R
        coll.objects.link(e)
        anchors[name] = e
    anchors["join"].location = Vector(J)  # where the ends meet, fixed in the world (the engine's rig sees it there)

    def fields(side: str, s: np.ndarray, t: float, k: dict, F: float):
        """A half's fields over its samples: the broken end as the snap left it, closing as it knits, and the lay."""
        sign = -1.0 if side == "left" else 1.0
        q = sign * (s - s_b)
        x = s - s_b
        m = len(s)
        open_ = 1 - GATHER * story.gather(t)
        fray = F * thread.bump(x / (FRAY_SPAN * R))
        unravel = sign * UNRAVEL * np.exp(-np.maximum(q, 0) / (5 * R)) * (1 - k["twist"])
        unravel = unravel + ((twist_to - rope.twist) * x + fix) * k["lay"]
        splay, brush, taper = np.zeros((3, m)), np.zeros((3, m)), np.ones((3, m))
        for kk, c in enumerate(rope.ply_break):
            qk = sign * (s - c)
            splay[kk] = SPLAY * (1 + 0.25 * (kk - 1)) * np.exp(-np.maximum(qk, 0) / (3 * R)) * open_ * (1 - k["splay"])
            brush[kk] = BRUSH * R * np.clip(-qk / R + 0.6, 0, 4) ** 1.3 * open_ * (1 - k["brush"])
            tip = np.clip((qk - 1.1 * R) / (1.2 * R), 0, 1)
            taper[kk] = 1 - (1 - np.sqrt(tip)) * (1 - k["core"])
        return fray, unravel, splay, brush, taper

    def centre(side: str, s: np.ndarray, t: float, hum) -> np.ndarray:
        """A half's centreline: on the line, drawn back from the join by half the gap, its free end drooping by the
        curl (integrated from its far end, as B01 curled it), humming with the rest."""
        sign = -1.0 if side == "left" else 1.0
        X = J + ((s - s_b) + sign * story.gap(t) / 2)[:, None] * d
        th = story.curl(t)
        if th > 1e-6:
            q = sign * (s - s_b)
            alpha = np.minimum(th * np.exp(-np.maximum(q, -3 * R) / (CURL_LEN * R)), 1.6 * th)
            tang = np.cos(alpha)[:, None] * d + sign * np.sin(alpha)[:, None] * n0
            steps = (tang[1:] + tang[:-1]) / 2 * np.diff(s)[:, None]
            if side == "left":
                X = X[0] + np.concatenate([[np.zeros(3)], np.cumsum(steps, axis=0)])
            else:
                X = X[-1] - np.concatenate([np.cumsum(steps[::-1], axis=0)[::-1], [np.zeros(3)]])
        return X + hum[:, None] * hum_dir

    def normals(X: np.ndarray, s: np.ndarray) -> np.ndarray:
        T = np.gradient(X, s, axis=0)
        T /= np.linalg.norm(T, axis=1, keepdims=True)
        N = n0 - T * (T @ n0)[:, None]
        return N / np.linalg.norm(N, axis=1, keepdims=True)

    def pose(sc, *_):
        t = (sc.frame_current + sc.frame_subframe) / 30.0
        k = story.knit(t)
        F = 1.3 * (1 - k["fray"])  # the fray B01's snap left open (its fray at 1, x 1.3), healing
        poses = {}
        for side, s in halves.items():
            X = centre(side, s, t, story.hum(s - s_b, t))
            fray, unravel, splay, brush, taper = fields(side, s, t, k, F)
            poses[side] = thread.RopePose(s, X, normals(X, s), fray, unravel, splay, np.zeros((3, len(s))), brush,
                                          taper, lift=story.lift(t), broken=1 - k["broken"])
        mr.update(poses, fray_centre=s_b, fray_amount=F)

        # the strands, on the line where the halves meet, each side with its own half's fields
        hum = story.hum(grid - s_b, t)
        X = J + (grid - s_b)[:, None] * d + hum[:, None] * hum_dir
        left = grid < s_b
        fl, fr = fields("left", grid, t, k, F), fields("right", grid, t, k, F)
        fray, unravel, splay = (np.where(left, a, b) for a, b in zip(fl[:2], fr[:2])), None, None
        fray, unravel = list(fray)
        splay = np.where(left[None, :], fl[2], fr[2])
        sp = thread.RopePose(grid, X, normals(X, grid), fray, unravel, splay, np.zeros((3, len(grid))),
                             np.zeros((3, len(grid))), np.ones((3, len(grid))))
        x = np.abs(grid - s_b)
        depth = depth_D * (1 - (1 - np.clip((x - 0.3 * R) / (1.9 * R), 0, 1) ** 2) * (1 - k["depth"]))
        for c, tube in tubes.items():
            e = story.extent(t, c)
            Pc, out = thread.groove_path(rope, sp, grooves[c], depth=depth, fray_centre=s_b, fray_amount=F)
            radius = strand_r * np.sqrt(np.clip((e - x) / max(min(e, 0.9 * R), 1e-9), 0, 1))  # a bead, then a needle
            if c == "blood":
                radius = radius * (1 + (story.bead(t) - 1) * np.exp(-((x / (0.6 * R)) ** 2)))
                # the light it sheds: at the join (from before it is born), and riding each tip along its groove
                spark.location = Vector(J)
                spark.data.energy = SPARK_W * story.spark(t)
                for tl, side in zip(tip_lights, (-1, 1)):
                    j = int(np.argmin(np.abs((grid - s_b) - side * max(e - 0.4 * R, 0.0))))
                    tl.location = Vector(Pc[j] + out[j] * 0.5 * strand_r)
                    tl.data.energy = TIP_W * story.tip(t) * (e > 1.5 * R)
            tube.update(Pc, radius, story.heat(c, x, t, e), up=out)
            thread.glow_socket(mats[c]).default_value = thread.strand_glow(t, cues.cue(STRANDS[c]["cue"]))

        for name, side in (("end_l", "left"), ("end_r", "right")):
            p = poses[side]
            anchors[name].location = Vector(thread.interp_rows([s_b], p.s, p.X)[0])

        place_camera(t)
        lv = story.light(t)
        for ob in (key, top, rim):
            ob.data.energy = power[ob.name] * lv[ob.name]

    bpy.app.handlers.frame_change_pre.append(pose)
    pose(scene)


def _light(name, kind, power, pos, target, *, size=None, spot=None, soft=None, temperature=None):
    import bpy

    data = bpy.data.lights.new(name, kind)
    data.energy = power
    if temperature:
        data.use_temperature = True
        data.temperature = temperature
    if size is not None:
        data.shape = "DISK"
        data.size = size
    if spot is not None:
        data.spot_size = spot
        data.spot_blend = 0.6
    if soft is not None:
        data.shadow_soft_size = soft
    ob = bpy.data.objects.new(name, data)
    ob.location = pos
    ob.rotation_euler = (target - pos).to_track_quat("-Z", "Y").to_euler()
    return ob
