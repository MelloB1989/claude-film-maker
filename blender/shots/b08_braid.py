"""B08, the braid (scene `braid`, spec §4 08): "Your words. What you meant. How you'd ask... braided into one answer."
GitLoom's retrieval: three arms searched at once (lexical BM25 on her words, body vectors on what was meant, cue vectors
on how it would be asked), fused into one ranking, expanded along the graph, in milliseconds and with no model call.

A dark void hung with glass commit beads, out of focus at their depths (the rest of memory). Three diff threads
(DIFF_THREAD, the film's thread: bone at rest, its blood and moss strands dark) race in from the left, the top and the
right, each landing on her first word for it, their whipped tips hovering GAP short of one point (P0), apart:
  - lexical, "Your words.": dead straight and fast, an exact line;
  - body, "What you meant.": in a long, slow bow from above;
  - cues, "How you'd ask...": from the right with a wave running down it, the way a question lilts.
Each lands with a hit: it twangs like a plucked string and its own light flares and settles. They hang there, apart,
breathing, while the camera pushes in.

"braided": the tips close and the three are plaited (lib/braid.py: a flat three-strand plait, each strand over one
neighbour and under the other) and the plait is pulled toward the camera as a braiding machine pulls it, its pattern
travelling with it, new plait forming at P0 where the arms whip round each other in their figures of eight; its head is a
braid's tail, the three strands gathered to a point. The arms are drawn in, their shapes pulled straight; the head flies
at the lens, bowing as it goes, while the camera swings back and out to the side to watch it come (the head holds its
place in frame as the world recedes behind it). "into": side threads shoot off the plait through the bores of three
neighbouring beads (graph expansion), each bead taking the hit and a glint; the one in the focal plane shows its etched
hash. "one": the head lands on the card's hinge (data/look/b08_braid.json) and the rope pulls taut: the bow snaps
straight, overshoots and settles, and a tension ring runs back through the plait; on the downbeat of "answer" a light
runs down the plait to the head. The engine swings the result card open on the rope's end and sets the labels and the
type (app/src/scenes/braid.ts).

One world, one camera, shared with the engine: data/look/b08_braid.json holds the thread's radius, P0, the plait's axis
and length, the card's hinge, facing and up, and the camera's keys (cue times from the data, positions in the engine's
metres, y up), which both renderers read (lib/rig.py is the Python port of the engine's CameraRig). Everything is a
pure function of the film frame (and sub-frame): a frame_change_pre handler poses every thread (hair curves with the
no-op deform modifier, so Cycles blurs what moves, the plies' stripes running along with the material), the beads, the
camera and the lights at every motion-blur step. Tracked for the engine: a label anchor on each arm (`lbl_<arm>`), P0
(`p0`), the plait's head (`head`) and the card's hinge (`hinge`, fixed in the world: it proves the plate's camera is the
engine's, braid.test.ts).

  Blender -b -P blender/render.py -- --shot b08_braid --mode look            (the key moments, 960x540)
  Blender -b -P blender/render.py -- --shot b08_braid --mode preview         (the window: proxies + track)
  Blender -b -P blender/render.py -- --shot b08_braid --mode final --res 1920x1080 --samples 64 [--frames a-b]
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
SPEC = json.loads((REPO / "data" / "look" / "b08_braid.json").read_text())
STRINGS = json.loads((REPO / "app" / "src" / "scenes" / "braid.strings.json").read_text())
HASHES = STRINGS[9:]  # the beads' engravings (the neighbours', then the void's): illustrative commit hashes, checked
# with the scene's strings (braid.ts draws the strings before them)


def unit(v) -> np.ndarray:
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


# ------------------------------------------------------------------------------------------------ the world
#
# The engine's coordinates (metres, y up; lib/rig.py turns them into Blender's). R is the diff thread's radius, her
# thread's scale.

R = float(SPEC["radius"])
P0 = np.array(SPEC["p0"], float)
AXIS = unit(SPEC["axis"])  # the plait's axis, from P0 toward the camera
LENGTH = float(SPEC["length"])  # how far the plait's head goes along it: onto the card's hinge
HINGE = np.array(SPEC["card"]["hinge"], float)
ARMS = ("lexical", "body", "cues")  # the order she names them; strand k of the plait is ARMS[k]
# where each arm comes in from, off frame (the end framing put them past the left, top and right edges)
ENTRY = {"lexical": (-0.26585, 0.16879, 0.04958), "body": (0.01966, 0.44909, -0.36397),
         "cues": (1.37323, 0.2304, -0.05477)}
# the neighbouring beads (graph expansion), placed round the plait as the camera sees it land: one beside its head in
# the focal plane (its hash reads), one by the lens under it (out of focus), one above it; their side threads leave
# the plait from the material nearest them
BEADS = {"b1": (-0.04602, -0.07839, 0.36492), "b2": (-0.13672, -0.04366, 0.47044), "b3": (0.03178, -0.00254, 0.27224)}
# beads that hang in the void beyond (the rest of memory, which the search passes over): placed in the arrival framing,
# far behind P0, out of focus; each turns slowly about the vertical
AMBIENT = {"a1": (-0.18477, -0.3162, -1.08818), "a2": (0.70819, 0.00468, -1.32621), "a3": (0.2443, -0.24054, -0.60676)}
BEAD_R, BEAD_BORE, BEAD_CHAMFER = 4.0, 0.8, 0.35
SIDE_R = 0.5  # the side threads' radius (x R)
SIDE_DU = 0.25  # material between a side thread's samples (x R)
SIDE_FLIGHT = 0.3  # a side thread's flight from the plait out through its bead (s)
SIDE_BEYOND = 0.7  # how far it runs on past its bead (x the bead's radius)
LEAN = {"b1": 0.7, "b2": 0.6, "b3": 0.5}  # a side thread peels off the plait leaning along it (+: with the flow)
LEVEL = {"b1": 1.0, "b2": 0.0, "b3": 0.35}  # how level across the frame it runs through its bead (b1 is in focus)
DU = 0.4  # material between samples along a thread (x R)
CORNER = 5.0  # the bend from an arm into the plait (x R)
SWEEP_DUR = 0.36  # the light that runs down the plait as the answer lands takes this long (s)
TIP_LEN = 2.6  # a free end tapers to a point over this much of its material (x R)
FUZZ_CLEAR = 7.0  # and carries no fuzz this near its tip (x R)
HEAD_POINT = 15.0  # the plait's head gathers its three strands to a point over this length (x R): a braid's tail
GAP = 4.5  # the landed arms' tips hover this far short of P0, apart (x R)
CLOSE = 0.14  # and close the gap as the plait starts (s)
PEAK = {"lexical": 2.6, "body": 2.2, "cues": 4.0}  # where an arm's shape and twang peak: v^p = 1/2 (in frame)
LBL_BACK = {"lexical": 0.09, "body": 0.1, "cues": 0.13}  # a label's anchor: this far (m) back up its arm from P0


# ------------------------------------------------------------------------------------------------ time

def clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def smooth(x: float) -> float:
    x = clip01(x)
    return x * x * (3 - 2 * x)


def in_out_cubic(x: float) -> float:
    x = clip01(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def out_expo(x: float, k: float = 9.0) -> float:
    """outExpo normalised to end exactly on 1."""
    x = clip01(x)
    return (1 - 2 ** (-k * x)) / (1 - 2 ** (-k))


def spring(t: float, freq: float = 5.0, damping: float = 0.6) -> float:
    """motion.ts spring: the house step response."""
    if t <= 0:
        return 0.0
    w = 2 * math.pi * freq
    a = damping * w
    if a * t > 40:
        return 1.0
    b = w * math.sqrt(1 - damping * damping)
    return 1 - math.exp(-a * t) * (math.cos(b * t) + (a / b) * math.sin(b * t))


def gather(b) -> np.ndarray:
    """The plait's head: its three strands drawn together to a point on its axis over the last HEAD_POINT of it (b: plait
    material from the head, m), the way a braid's end is whipped."""
    x = np.clip(np.asarray(b, float) / (HEAD_POINT * R), 0.0, 1.0)
    return (0.05 + 0.95 * np.sin(0.5 * np.pi * x) ** 1.5)[..., None]


def tip_scale(m) -> np.ndarray:
    """A free end, whipped to a point: the scale on a thread's plies and strands (their offsets from its centreline and
    their radii) at material m (m) behind its tip: 0.22 at the tip, 1 from TIP_LEN back."""
    x = np.clip(np.asarray(m, float) / (TIP_LEN * R), 0.0, 1.0)
    return 0.22 + 0.78 * x * x * (3 - 2 * x)


def ring(t: float, at: float, freq: float, tau: float) -> float:
    """A plucked string's swing after a hit at `at`: sin, decaying (0 before it)."""
    d = t - at
    return 0.0 if d <= 0 else math.exp(-d / tau) * math.sin(2 * math.pi * freq * d)


def flash(t: float, at: float, rise: float = 0.03, tau: float = 0.28) -> float:
    """A light hit on `at`: up over `rise`, dying away."""
    if t < at - rise:
        return 0.0
    if t < at:
        return smooth((t - (at - rise)) / rise)
    return math.exp(-(t - at) / tau)


class Cues:
    """The shot's times, from the data: the scene's window, her words (L19), the landings, the zip and the beats."""

    RACE = 0.34  # an arm's flight, landing on its word
    ZIP_LEAD = 0.06  # the plait starts this much before "braided"

    def __init__(self, timing):
        self.start, self.end = timing.scene("braid")
        w = lambda i: timing.word("L19", i).start  # noqa: E731
        self.your, self.words, self.what, self.meant = w(0), w(1), w(2), w(4)
        self.how, self.ask, self.braided, self.into, self.one, self.answer = w(5), w(7), w(8), w(9), w(10), w(11)
        self.land = {"lexical": self.your, "body": self.what, "cues": self.how}
        self.zip0 = self.braided - self.ZIP_LEAD
        self.beats = [b for b in timing.audio["beats"] if self.start - 1e-6 <= b <= self.end + 1e-6]
        self.downbeats = [b for b in timing.audio["downbeats"] if self.start - 1e-6 <= b <= self.end + 1e-6]

    def cue(self, name: str) -> float:
        return {"start": self.start, "your": self.your, "what": self.what, "how": self.how, "braided": self.braided,
                "into": self.into, "one": self.one, "answer": self.answer, "end": self.end}[name]


def camera_keys(cues: Cues) -> list[dict]:
    """The camera's keys (data/look/b08_braid.json) at their cue times, as lib/rig.py and stage.ts CameraRig take them."""
    out = []
    for k in SPEC["camera"]:
        key = {"t": cues.cue(k["cue"]) + k.get("dt", 0.0), "pos": k["eye"], "target": k["look"]}
        for f in ("fov", "roll", "ease"):
            if f in k:
                key[f] = k[f]
        out.append(key)
    return out


# ------------------------------------------------------------------------------------------------ the story

class Story:
    """The choreography (pure; tested without Blender). Times in song seconds, lengths in metres."""

    def __init__(self, cues: Cues):
        from lib import braid, rig

        self.c = cues
        self.rig = rig.Rig(camera_keys(cues))
        self.plait = braid.Plait(R)
        end_eye = np.array(next(k for k in SPEC["camera"] if k["cue"] == "one")["eye"], float)
        right_end = self.rig.at(cues.one).basis()[:, 0]  # the frame's right as the camera lands
        mid = P0 + 0.5 * LENGTH * AXIS
        v = end_eye - mid
        self.ey = unit(v - AXIS * (v @ AXIS))  # the plait's face, toward the camera that sees it land
        self.ex = np.cross(self.ey, AXIS)  # across its face
        g = np.array([0.0, -1.0, 0.0])
        self.sag_dir = unit(g - AXIS * (g @ AXIS))
        start = self.rig.at(cues.start)
        self.view = unit(P0 - start.pos)
        self.entry = {k: np.array(v, float) for k, v in ENTRY.items()}
        # each arm's directions: across the screen (its twang and its wave), and the body arm's bow
        self.across = {}
        for k in ARMS:
            d = unit(P0 - self.entry[k])
            self.across[k] = unit(np.cross(d, self.view))
        side = np.array([-1.0, 0.0, 0.3])
        d = unit(P0 - self.entry["body"])
        self.bow_dir = unit(side - d * (side @ d))
        # the beads and their side threads: each leaves the plait at the material (from its head) nearest its bead
        # once the plait has landed, out of the plait's side toward it, and runs through the bead's bore
        self.beads = {}
        for i, (name, g) in enumerate(BEADS.items()):
            g = np.array(g, float)
            a = float(np.clip((g - P0) @ AXIS, 0.12 * LENGTH, 0.92 * LENGTH))
            root_end = P0 + a * AXIS
            out = g - root_end
            out = unit(out - AXIS * (out @ AXIS))
            lv = unit(out + LEAN[name] * AXIS)  # how it leaves the plait
            bore = unit(g - (root_end + lv * 0.5 * np.linalg.norm(g - root_end)))  # and arrives: an arc,
            to_cam = unit(end_eye - g)
            bore = unit(bore - to_cam * (bore @ to_cam))  # through the bead square to the lens: its hash faces it
            # and, for the bead in focus, level across the frame as the camera lands, so its hash reads straight
            level = right_end * (1.0 if bore @ right_end >= 0 else -1.0)
            bore = unit(bore + (level - bore) * LEVEL[name])
            bore = unit(bore - to_cam * (bore @ to_cam))
            # the engraving reads left to right as the camera lands: the bead's own x along the bore, the way the frame's
            # right is (a bead is the same either way along its bore)
            text_x = bore if bore @ right_end >= 0 else -bore
            self.beads[name] = {"g": g, "b": LENGTH - a, "out": out, "leave": lv, "bore": bore, "text_x": text_x,
                                "hash": HASHES[i], "i": i}
        # the side threads launch on "into" and the 16ths after it, nearest the head first
        order = sorted(self.beads, key=lambda n: self.beads[n]["b"])
        step = 60 / 100 / 4
        for j, n in enumerate(order):
            self.beads[n]["launch"] = cues.into - 0.04 + j * step
        self.face = {n: unit(end_eye - b["g"]) for n, b in self.beads.items()}

    # ---- the arms

    def arrival(self, k: str) -> float:
        return self.c.land[k]

    def taut(self, t: float) -> float:
        """0 while the arms hang in their own shapes, 1 once the plait pulls them straight."""
        return smooth((t - (self.c.zip0 - 0.05)) / 0.4)

    def snap(self, t: float) -> float:
        """The rope pulled taut on "one": a spring from slack (0) to straight (1) that overshoots and settles."""
        return spring(t - (self.c.one - 0.045), freq=4.6, damping=0.38)

    def shape(self, k: str, v: np.ndarray, t: float) -> np.ndarray:
        """An arm's offset from its straight line at fractions v from its entry to P0: its own shape, its twang on
        landing and on the snap, and a breath of sway. (n, 3)."""
        p = PEAK[k]
        env = np.sin(np.pi * v ** p)[:, None]  # peaks at v = 0.5^(1/p): on the part of the arm in frame
        land = self.arrival(k)
        loose = 1.0 - self.taut(t)
        off = np.zeros((len(v), 3))
        across = self.across[k]
        if k == "body":
            off += env * self.bow_dir * 0.06 * (0.2 + 0.8 * loose)
        if k == "cues":
            amp = 0.009 * (0.4 + 0.6 * math.exp(-max(0.0, t - land) / 0.9)) * loose
            wave = np.sin(2 * np.pi * (6.0 * v ** p - 1.4 * (t - land)))
            off += (wave * np.sin(np.pi * v ** p) ** 0.8)[:, None] * across * amp
        twang = 2.6 * R * ring(t, land, 7.0, 0.2) + 1.1 * R * ring(t, self.c.one, 9.0, 0.16)
        twang += 0.6 * R * ring(t, land, 14.0, 0.08)  # the second harmonic: a bright edge on the hit
        sway = 0.5 * R * math.sin(2 * math.pi * 0.31 * t + ARMS.index(k) * 2.1) * loose
        off += env * across * (twang + sway)
        return off

    def arm_path(self, k: str, t: float, Q: np.ndarray, n: int = 220) -> np.ndarray:
        """The arm from its entry to Q at t: (n, 3)."""
        E = self.entry[k]
        v = np.linspace(0.0, 1.0, n)
        return E + (Q - E) * v[:, None] + self.shape(k, v, t)

    def tip_back(self, k: str, t: float, L: float, h0: float) -> float:
        """How far back along its path the arm's tip is from where the plait begins (m): flying in from h0 along the
        arm (just off frame) on outExpo, landing on its word GAP short of P0 (the three hover apart), closing the gap
        as the plait starts, and then riding the plait's head (0). L is the arm's length."""
        land = self.arrival(k)
        x = (t - (land - self.c.RACE)) / self.c.RACE
        if x <= 0:
            return L - (h0 - 0.05)
        if t < self.c.zip0:
            h = h0 + (L - GAP * R - h0) * out_expo(x)
            return L - h
        return GAP * R * (1.0 - smooth((t - self.c.zip0) / CLOSE))

    # ---- the plait

    def zip(self, t: float) -> float:
        """The plait's head: its axial distance from P0 (m). 0 until the zip; flying on inOutCubic onto the hinge on
        "one", then a small recoil as the rope fetches up."""
        c = self.c
        if t <= c.zip0:
            return 0.0
        if t <= c.one:
            return LENGTH * in_out_cubic((t - c.zip0) / (c.one - c.zip0))
        return LENGTH + 0.7 * R * ring(t, c.one, 6.5, 0.07)

    def sag(self, t: float) -> float:
        """The plait's bow (m at its middle): slack as it flies, snapped straight on "one" (overshooting)."""
        a = self.zip(t) / LENGTH
        return 0.038 * min(1.0, a) * (1.0 - self.snap(t))

    def plait_point(self, k: int, b, t: float) -> np.ndarray:
        """Strand k's centre at plait material b (m from its head) at t: (n, 3)."""
        b = np.asarray(b, float)
        ah = self.zip(t)
        axial = ah - b
        o = self.plait.offset(k, b) * R * gather(b)
        bow = self.sag(t) * np.sin(np.pi * np.clip(axial / max(ah, 1e-6), 0.0, 1.0))
        bow += 1.4 * R * ring(t, self.c.one, 9.0, 0.14) * np.sin(2 * np.pi * np.clip(axial / LENGTH, 0, 1))
        return (P0 + axial[:, None] * AXIS + o[:, :1] * self.ex + o[:, 1:] * self.ey + bow[:, None] * self.sag_dir)

    def head(self, t: float) -> np.ndarray:
        """The plait's head: the middle of its three tips (before the zip, P0)."""
        return P0 + self.zip(t) * AXIS

    # ---- the side threads and the beads

    def side_tip(self, name: str, t: float, L: float) -> float:
        """How far a side thread's tip is along its path (m from its root): out on outExpo over SIDE_FLIGHT."""
        b = self.beads[name]
        x = (t - b["launch"]) / SIDE_FLIGHT
        return -1.0 if x <= 0 else L * out_expo(x, 7.0)

    def bead_kick(self, name: str, t: float) -> float:
        """The bead's jolt along its bore as the thread runs through it (m), from when the tip reaches its centre
        (Threads finds it on the path)."""
        hit = self.beads[name].get("hit")
        return 0.0 if hit is None else 1.1 * R * ring(t, hit, 3.2, 0.22)

    # ---- the camera and the light

    def focus_point(self, t: float) -> np.ndarray:
        """Focus: on P0 while the arms land and hang, riding the plait's head as it flies, on the hinge as it lands."""
        c = self.c
        p = P0 + (self.head(t) - P0) * smooth((t - c.zip0) / 0.3)
        return p + (HINGE - p) * smooth((t - (c.one - 0.4)) / 0.4)

    def kicker(self, k: str, t: float) -> float:
        """Each arm's own light: dark until it lands, a hit on the landing, then a low glow on it; the snap re-lights."""
        land = self.arrival(k)
        base = 0.12 * smooth((t - land + 0.02) / 0.12)
        return base + 1.0 * flash(t, land) + 0.12 * flash(t, self.c.one, tau=0.22)

    def sweep(self, t: float) -> tuple[float, float]:
        """A light running down the plait as the answer lands: (how far along it from P0, 0..1; its level, 0..1). It
        sets off as the matched row is called and reaches the head on the downbeat of "answer"."""
        down = min((d for d in self.c.downbeats if d >= self.c.answer - 0.1), default=self.c.answer)
        x = (t - (down - SWEEP_DUR)) / SWEEP_DUR
        return smooth(x), math.sin(math.pi * clip01(x)) ** 0.7

    def glint(self, name: str, t: float) -> float:
        hit = self.beads[name].get("hit")
        return 0.0 if hit is None else flash(t, hit, rise=0.02, tau=0.3)


# ------------------------------------------------------------------------------------------------ the threads (pure)

class Threads:
    """Every thread's centreline at a time, sampled along its material, and the side threads'."""

    def __init__(self, story: Story):
        from lib import braid

        self.s = story
        self.braid = braid
        self.U, self.M, self.h0 = {}, {}, {}
        rest = story.rig.at(story.c.start)
        for k in ARMS:
            E = story.entry[k]
            L_arm = float(np.linalg.norm(P0 - E))
            Ls = story.plait.arc(ARMS.index(k), LENGTH)
            self.U[k] = L_arm + Ls + 0.12
            self.M[k] = int(math.ceil(self.U[k] / (DU * R))) + 1
            # the arm flies in from just off frame: the last point of its straight line outside the frame at the start
            v = np.linspace(0, 1, 400)
            px = rest.project_many(E + (P0 - E) * v[:, None])
            inside = (px[:, 0] > -40) & (px[:, 0] < 1960) & (px[:, 1] > -40) & (px[:, 1] < 1120)
            first = int(np.argmax(inside)) if inside.any() else 0
            self.h0[k] = max(0.0, v[max(0, first - 1)] * L_arm - 0.02)
        # the side threads: enough material for the longest path, and when each tip reaches its bead's centre (the
        # bead takes the hit then: Story.bead_kick)
        longest = 0.0
        for name, bd in story.beads.items():
            t_mid = bd["launch"] + 0.4 * SIDE_FLIGHT
            _, sa, s_g, _ = self.side_path(name, t_mid)
            longest = max(longest, float(sa[-1]))
            f = min(0.999, s_g / float(sa[-1]))
            x = -math.log2(1 - f * (1 - 2 ** -7.0)) / 7.0  # out_expo(x, 7) = f
            bd["hit"] = bd["launch"] + SIDE_FLIGHT * x
        self.NS = int(math.ceil(1.15 * longest / (SIDE_DU * R))) + 1
        self.Uside = self.NS * SIDE_DU * R

    def braiding_point(self, k: str, t: float) -> np.ndarray:
        """Where arm k joins the plait at t: strand k's centre where the plait is being made (its material ah from the
        head), on the plait's cross-section at P0."""
        s = self.s
        ah = np.array([max(s.zip(t), 0.0)])
        o = (s.plait.offset(ARMS.index(k), ah) * R * gather(ah))[0]
        return P0 + o[0] * s.ex + o[1] * s.ey

    def arm(self, k: str, t: float):
        """Thread k at t: (X (M, 3) from its far end to its tip, u (M,) its material there, increasing to the tip).
        Material at distance m behind the tip sits at sigma = tip_back + m along the path that runs back from the plait's
        head through the plait to the braiding point and up the arm to its entry (and on past it, off frame)."""
        s, b = self.s, self.braid
        ki = ARMS.index(k)
        ah = s.zip(t)
        M = self.M[k]
        m = np.arange(M) * DU * R
        A = s.arm_path(k, t, self.braiding_point(k, t))
        sa = b.polyline_arc(A)
        L_arm = float(sa[-1])
        sigma = s.tip_back(k, t, L_arm, self.h0[k]) + m
        sb = float(s.plait.arc(ki, ah)) if ah > 0 else 0.0
        X = np.empty((M, 3))
        inb = sigma <= sb
        if inb.any():
            X[inb] = s.plait_point(ki, s.plait.b_of_arc(ki, sigma[inb], ah), t)
        X[~inb] = b.at_arc(A, sa, L_arm - (sigma[~inb] - sb))
        if ah > 0:
            X = b.round_corner(X, sigma, sb, CORNER * R)
        u = self.U[k] - m
        return X[::-1].copy(), u[::-1].copy()

    def side_path(self, name: str, t: float):
        """A side thread's path at t: out of the plait's side (its root rides the plait), curving into its bead's bore,
        through it and on. (points (n, 3), their arc lengths, the arc length at the bead's centre, the root)."""
        s, b = self.s, self.braid
        bd = s.beads[name]
        ah = s.zip(t)
        axial = ah - bd["b"]
        bow = s.sag(t) * math.sin(math.pi * clip01(axial / max(ah, 1e-6)))
        root = P0 + axial * AXIS + bow * s.sag_dir + bd["out"] * 1.6 * R
        g = bd["g"] + bd["bore"] * s.bead_kick(name, t)
        w = bd["bore"]
        L0 = float(np.linalg.norm(g - root))
        c1, c2 = root + bd["leave"] * L0 * 0.5, g - w * L0 * 0.4
        u = np.linspace(0.0, 1.0, 200)[:, None]
        curve = (1 - u) ** 3 * root + 3 * (1 - u) ** 2 * u * c1 + 3 * (1 - u) * u ** 2 * c2 + u ** 3 * g
        beyond = g + w * np.linspace(0.0, SIDE_BEYOND * BEAD_R * R, 30)[1:, None]
        P = np.vstack([curve, beyond])
        sa = b.polyline_arc(P)
        return P, sa, float(sa[len(curve) - 1]), root

    def side(self, name: str, t: float):
        """A side thread at t, sampled along its material from root to tip: (X (NS, 3), u (NS,), shown (NS,) bool: the
        material out of the plait), or None before it leaves the plait. Its material is fixed from its tip back."""
        s, b = self.s, self.braid
        bd = s.beads[name]
        if t < bd["launch"] or s.zip(t) < bd["b"]:
            return None
        P, sa, _, root = self.side_path(name, t)
        h = s.side_tip(name, t, float(sa[-1]))
        m = np.arange(self.NS) * SIDE_DU * R
        X = b.at_arc(P, sa, h - m)
        shown = (h - m) >= 0.0
        X[~shown] = root
        u = self.Uside - m
        return X[::-1].copy(), u[::-1].copy(), shown[::-1].copy()

    def label_anchor(self, k: str, t: float) -> np.ndarray:
        """A point on arm k, LBL_BACK up it from where it joins the plait (on the thread, riding its twang)."""
        b = self.braid
        A = self.s.arm_path(k, t, self.braiding_point(k, t))
        sa = b.polyline_arc(A)
        return b.at_arc(A, sa, np.array([sa[-1] - LBL_BACK[k]]))[0]


# ------------------------------------------------------------------------------------------------ the shot

def _look_frames() -> str:
    """The key moments: each arm landing, the arms apart, the plait flying, its landing, the card."""
    from lib import timing

    c = Cues(timing.film())
    ts = [c.your + 0.12, c.what + 0.12, c.how + 0.15, c.braided - 0.3, c.into + 0.05, c.one + 0.04, c.end - 0.12]
    return ",".join(str(timing.frame(x)) for x in ts)


SHOT = {"scene": "braid", "frames": "scene", "look": _look_frames(),
        "track": ["lbl_lexical", "lbl_body", "lbl_cues", "p0", "head", "hinge"]}


def build(ctx):
    import bpy
    from mathutils import Matrix, Vector

    from lib import bead as beadlib
    from lib import braid, lights, rig, thread

    scene, coll = ctx.scene, ctx.scene.collection
    cues = Cues(ctx.timing)
    story = Story(cues)
    th = Threads(story)
    B = rig.to_blender

    # ---- materials: the bone plies, the strands at the diff thread's rest (their level a per-curve `lit`), the fuzz
    bone = thread.ply_material("braid_bone")
    strand = {c: thread.strand_material(c, name=f"braid_{c}", heat_attr="lit") for c in ("blood", "moss")}
    for m in strand.values():
        thread.glow_socket(m).default_value = 0.0
    fibre = thread.fibre_material("braid_fibre", sheen=0.5)
    glass = beadlib.glass_material("braid_glass")
    etch = beadlib.etch_material("braid_etch")
    rest = thread.DIFF_THREAD["rest"]

    objs: dict[str, object] = {}

    def curves(name, counts, material, lit=None):
        ob = thread._new_curves(name, counts, np.ones(len(counts)), material, coll, None)
        if lit is not None:
            a = ob.data.attributes.new("lit", "FLOAT", "CURVE")
            a.data.foreach_set("value", np.full(len(counts), lit, np.float32))
        objs[name] = ob
        return ob

    fuzz = {}
    for k in ARMS:
        M = th.M[k]
        curves(f"{k}.bone", [M] * 3, bone)
        curves(f"{k}.blood", [M], strand["blood"], rest)
        curves(f"{k}.moss", [M], strand["moss"], rest)
        fuzz[k] = braid.FuzzTable(th.U[k], R, per_R=1.3, seed=11 + ARMS.index(k), pts=4,
                                  u_min=th.U[k] - (th.M[k] - 1) * DU * R)
        curves(f"{k}.fuzz", [fuzz[k].pts] * fuzz[k].n, fibre)
    NS = th.NS
    names = list(BEADS)
    curves("side.bone", [NS] * (3 * len(names)), bone)
    curves("side.blood", [NS] * len(names), strand["blood"], rest)
    curves("side.moss", [NS] * len(names), strand["moss"], rest)

    # ---- the beads: glass, bore along their side thread, the hash etched on the face the camera sees them land from
    bead_obs = {}
    for name, bd in story.beads.items():
        me = beadlib.bead_mesh(f"bead.{name}", BEAD_R * R, BEAD_BORE * R, BEAD_CHAMFER * R, glass)
        ob = bpy.data.objects.new(f"bead.{name}", me)
        coll.objects.link(ob)
        em = beadlib.etch_mesh(f"etch.{name}", bd["hash"], BEAD_R * R, etch)
        eo = bpy.data.objects.new(f"etch.{name}", em)
        eo.parent = ob
        coll.objects.link(eo)
        bead_obs[name] = (ob, eo)

    amb_obs = {}
    for j, (name, g) in enumerate(AMBIENT.items()):
        me = beadlib.bead_mesh(f"bead.{name}", BEAD_R * R, BEAD_BORE * R, BEAD_CHAMFER * R, glass)
        ob = bpy.data.objects.new(f"bead.{name}", me)
        coll.objects.link(ob)
        em = beadlib.etch_mesh(f"etch.{name}", HASHES[len(BEADS) + j], BEAD_R * R, etch)
        eo = bpy.data.objects.new(f"etch.{name}", em)
        eo.parent = ob
        coll.objects.link(eo)
        amb_obs[name] = (ob, eo, np.array(g, float), 1.7 * j + 0.4)

    def place_ambient(t):
        start = story.rig.at(cues.start).pos
        for name, (ob, _, g, ph) in amb_obs.items():
            a = ph + 0.22 * (t - cues.start)  # a slow turn about the vertical: its highlights travel round it
            face = unit(start - g)
            bore = unit(np.cross(np.array([0.0, 1.0, 0.0]), face))
            c, s_ = math.cos(a), math.sin(a)
            bore = unit(bore * c + face * s_ * 0.5)
            Mw = np.eye(4)
            Mw[:3, :3] = rig.ENGINE_TO_BLENDER @ beadlib.bead_basis(bore, face)
            Mw[:3, 3] = B(g + np.array([0.0, 0.002 * math.sin(1.3 * t + ph), 0.0]))
            ob.matrix_world = Matrix(Mw.tolist())

    def place_bead(name, t):
        bd = story.beads[name]
        rot = beadlib.bead_basis(bd["text_x"], story.face[name])
        g = bd["g"] + bd["bore"] * story.bead_kick(name, t)
        Mw = np.eye(4)
        Mw[:3, :3] = rig.ENGINE_TO_BLENDER @ rot
        Mw[:3, 3] = B(g)
        bead_obs[name][0].matrix_world = Matrix(Mw.tolist())

    # ---- anchors for the engine
    anchors = {}
    for name in SHOT["track"]:
        e = bpy.data.objects.new(name, None)
        e.empty_display_size = 0.01
        coll.objects.link(e)
        anchors[name] = e
    anchors["p0"].location = Vector(B(P0))
    anchors["hinge"].location = Vector(B(HINGE))

    # ---- the camera: the engine's rig on the engine's gate
    cam = rig.engine_camera("camera", fstop=SPEC["fstop"], collection=coll)
    scene.camera = cam

    # ---- the light: a soft warm-neutral key from the upper left and in front, a hard rim from behind on the right that
    # draws the arms as lines in the dark and rings the glass, a soft top; each arm's own kicker (light-linked to it),
    # and a glint on each bead (linked to it)
    lights.world_color("ink")
    rigl = {}

    def light(name, kind, power, pos, aim, **kw):
        ob = _light(name, kind, power, Vector(B(pos)), Vector(B(aim)), **kw)
        coll.objects.link(ob)
        rigl[name] = (ob, power)
        return ob

    f0 = story.focus_point(cues.start)
    key = light("key", "SPOT", LIGHT["key"], f0 + KEY_FROM, f0, spot=math.radians(34), soft=0.05, temperature=5600,
                blend=0.85)
    rim = light("rim", "SPOT", LIGHT["rim"], f0 + RIM_FROM, f0, spot=math.radians(36), soft=0.008, temperature=6500,
                blend=0.6)
    top = light("top", "AREA", LIGHT["top"], f0 + TOP_FROM, f0, size=0.3, temperature=6200)
    follow = [(key, KEY_FROM), (rim, RIM_FROM), (top, TOP_FROM)]
    kick = {}
    for k in ARMS:
        E = story.entry[k]
        aim = P0 + 0.14 * (E - P0)
        kick[k] = light(f"kick.{k}", "SPOT", LIGHT["kick"], aim + np.array(KICK_OFF[k]), aim, spot=math.radians(50),
                        soft=0.015, temperature=6000, blend=0.7)
        _link(kick[k], [objs[f"{k}.{c}"] for c in ("bone", "blood", "moss", "fuzz")], "INCLUDE")
    sweep = light("sweep", "AREA", LIGHT["sweep"], P0 + np.array(SWEEP_OFF), P0, size=0.035, temperature=6200)
    _link(sweep, [objs[f"{k}.{c}"] for k in ARMS for c in ("bone", "blood", "moss", "fuzz")], "INCLUDE")
    void = light("void", "AREA", LIGHT["void"], (0.3, 0.9, -2.2), (0.3, -0.1, -0.9), size=0.8, temperature=6500)
    _link(void, [o for v in amb_obs.values() for o in v[:2]], "INCLUDE")
    glint = {}
    for name, bd in story.beads.items():
        at = bd["g"] + unit(story.face[name] + np.array([-0.4, 0.5, 0.0])) * 0.09
        glint[name] = light(f"glint.{name}", "AREA", LIGHT["glint"], at, bd["g"], size=0.03, temperature=6000)
        _link(glint[name], list(bead_obs[name]), "INCLUDE")

    def set_curves(name, pts, rad, lit=None):
        ob = objs[name]
        thread._set_curves(ob, B(np.asarray(pts).reshape(-1, 3)), np.asarray(rad).reshape(-1))
        if lit is not None:
            ob.data.attributes["lit"].data.foreach_set("value", np.asarray(lit, np.float32))

    def whipped(X, tubes, sc):
        """The tubes drawn in toward the centreline and thinned near the tip: [(points, radii)]."""
        return [(X + (P - X) * sc[:, None], r * sc) for _, P, r in tubes]

    def pose(sc, *_):
        t = (sc.frame_current + sc.frame_subframe) / 30.0
        for k in ARMS:
            X, u = th.arm(k, t)
            tubes = whipped(X, braid.tubes_along(X, u, R, story.across[k]), tip_scale(th.U[k] - u))
            set_curves(f"{k}.bone", np.stack([P for P, _ in tubes[:3]]), np.concatenate([r for _, r in tubes[:3]]))
            set_curves(f"{k}.blood", tubes[3][0], tubes[3][1])
            set_curves(f"{k}.moss", tubes[4][0], tubes[4][1])
            T, N, Bn = braid.frames_along(X, story.across[k])
            fp, fr = braid.fuzz_along(fuzz[k], X, u, T, N, Bn)
            fr[fuzz[k].u > th.U[k] - FUZZ_CLEAR * R] = 0.0
            set_curves(f"{k}.fuzz", fp, fr)
        sb, sbl, smo = [], [], []
        rb, rbl, rmo = [], [], []
        for name in names:
            out = th.side(name, t)
            if out is None:
                bd = story.beads[name]
                hide = np.repeat(bd["g"][None], NS, 0)
                sb += [hide] * 3
                sbl.append(hide)
                smo.append(hide)
                z = np.zeros(NS)
                rb += [z] * 3
                rbl.append(z)
                rmo.append(z)
                continue
            X, u, shown = out
            sc = tip_scale((th.Uside - u) / SIDE_R)  # its own tip, whipped to a point at its own scale
            tubes = whipped(X, braid.tubes_along(X, u, SIDE_R * R, story.beads[name]["out"]), sc)
            vis = shown.astype(float)
            for P, r in tubes[:3]:
                sb.append(P)
                rb.append(r * vis)
            sbl.append(tubes[3][0])
            rbl.append(tubes[3][1] * vis)
            smo.append(tubes[4][0])
            rmo.append(tubes[4][1] * vis)
        set_curves("side.bone", np.stack(sb), np.stack(rb))
        set_curves("side.blood", np.stack(sbl), np.stack(rbl))
        set_curves("side.moss", np.stack(smo), np.stack(rmo))
        for name in names:
            place_bead(name, t)
        place_ambient(t)
        # anchors
        for k in ARMS:
            anchors[f"lbl_{k}"].location = Vector(B(th.label_anchor(k, t)))
        anchors["head"].location = Vector(B(story.head(t)))
        # the camera
        p = story.rig.at(t)
        rig.place_camera(cam, p, p.depth(story.focus_point(t)))
        # the light: key, rim and top follow the subject (the focus point); each arm's kicker; the beads' glints
        f = story.focus_point(t)
        for ob, off in follow:
            ob.location = Vector(B(f + np.array(off)))
            ob.rotation_euler = (Vector(B(f)) - ob.location).to_track_quat("-Z", "Y").to_euler()
        for k in ARMS:
            kick[k].data.energy = rigl[f"kick.{k}"][1] * story.kicker(k, t)
        u_sw, lvl = story.sweep(t)
        at = story.head(t) * u_sw + P0 * (1 - u_sw)
        sweep.location = Vector(B(at + np.array(SWEEP_OFF)))
        sweep.rotation_euler = (Vector(B(at)) - sweep.location).to_track_quat("-Z", "Y").to_euler()
        sweep.data.energy = rigl["sweep"][1] * lvl
        for name in names:
            glint[name].data.energy = rigl[f"glint.{name}"][1] * (0.06 + story.glint(name, t))

    bpy.app.handlers.frame_change_pre.append(pose)
    scene.frame_set(ctx.f0)


# the light (W) and where it stands (engine metres): key, rim and top as offsets from the subject they follow
LIGHT = {"key": 22.0, "rim": 190.0, "top": 2.0, "kick": 10.0, "glint": 2.5, "sweep": 9.0, "void": 60.0}
SWEEP_OFF = (-0.05, 0.10, 0.08)  # the sweep's softbox, from the point of the plait it lights
KEY_FROM = (-0.55, 0.36, 0.10)
RIM_FROM = (0.32, 0.46, -0.56)
TOP_FROM = (0.05, 0.55, 0.08)
KICK_OFF = {"lexical": (0.10, -0.12, 0.30), "body": (0.22, 0.02, 0.30), "cues": (-0.05, -0.16, 0.30)}


def _link(light, objects, state: str) -> None:
    """Light linking: the light lights only `objects` (INCLUDE) or everything but them (EXCLUDE)."""
    import bpy

    c = bpy.data.collections.new(f"ll_{light.name}")
    for ob in objects:
        c.objects.link(ob)
    light.light_linking.receiver_collection = c
    for co in c.collection_objects:
        co.light_linking.link_state = state


def _light(name, kind, power, pos, target, *, size=None, spot=None, soft=None, temperature=None, blend=0.5):
    import bpy

    data = bpy.data.lights.new(name, kind)
    data.energy = power
    if temperature:
        data.use_temperature = True
        data.temperature = temperature
    if size is not None:
        data.shape, data.size = "DISK", size
    if spot is not None:
        data.spot_size = spot
        data.spot_blend = blend
    if soft is not None:
        data.shadow_soft_size = soft
    ob = bpy.data.objects.new(name, data)
    ob.location = pos
    ob.rotation_euler = (target - pos).to_track_quat("-Z", "Y").to_euler()
    return ob
