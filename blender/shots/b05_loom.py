"""B05, the loom (scene `loom`, spec §4 05): "Facts I keep." / "Incidents… I let go." / "Rules I never break." /
"Skills, only when you need them." GitLoom's four memory tiers, woven.

A real loom, seen low on its cloth side. Four warp lanes, the tiers (facts / incidents / rules / skills from the left,
each a tape of its own), run from under the lens through the woven cloth to the fell, then open into the shed and
stretch away into the dark toward the back beam. A glass shuttle carrying the diff thread (DIFF_THREAD,
data/look/thread.json: a pirn of it wound inside the glass) flies across on every beat: the shed opens after each beat,
the shuttle lands in its box on the next, the reed beats its row into the fell, the cloth is taken up one pick toward
the camera (the fabric grows toward it) and the warps change over for the next row (lib/weave.py WeaveClock). The cloth
is weft-faced, its face the diff thread's rows; each row commits as it is beaten in, its moss strand flaring and dying
back (strand_glow) as the cloth carries it toward the lens.

The tiers behave as she names them, every time from the data (vo.json onsets, audio.json beats):
  - "Facts" (L11): long-term. Their cloth runs on back past the lens, all of it kept; a soft light settles on it as she
    says "Facts" and holds, steady, while everything else moves.
  - "Incidents…" (L12): ttl. Their cloth is a short patch at the fell, the bare warps running on to the lens. From
    "Incidents…" its three oldest rows fray (plies loosening and untwisting, fibres standing up, their blood strands
    warming, a blood light inside them); across "let go" they let go one after another, lifting out of the weave and
    breaking into pieces that rise away into the dark and thin to nothing, the blood strands burning, the warps under
    them straightening (the engine stamps `gc: expire 3 incidents` there).
  - "Rules" (L13): loaded whole. Their warps hang slack and wavy beyond the fell until she names them, then pull tight
    in one snap (a spring that overshoots and settles) under a hard light of their own; on "break" they take a pluck
    and ring, and hold.
  - "Skills" (L14): lazy. Their warps lie dim and unwoven out of the shed, and the shuttle turns back short of them,
    until the first left-to-right pass after she names them: the warps rise into the shed on the beat before (on
    demand), and as the shuttle flies into their lane they light, a light running along them into the dark, and are
    woven from then on.

The camera (CameraRig) is a low macro tour along the fell: it holds on each tier while she names it, drifting, and snaps
across to the next on the beat before her next line (the plate's motion blur streaks the snap like a whip). Focus is on
the subject it frames, and on the expiring rows while they fray and let go. The key is a pool that follows the camera's
subject. A frame_change_pre handler poses every thread at every motion-blur step (hair curves with the no-op deform
modifier, so Cycles blurs what moves) and moves the shuttle, the camera and the lights. Tracked for the engine (loom.ts):
a label anchor per lane at the fell (`lbl_<tier>`), the expiring rows (`gc`), the shuttle and the skills lane's edge on
its race (`shuttle`, `reach`: the engine reads the moment the shuttle reaches skills off them), and the fell's ends.

  Blender -b -P blender/render.py -- --shot b05_loom --mode look            (the key moments, 960x540)
  Blender -b -P blender/render.py -- --shot b05_loom --mode preview         (the window: proxies + track)
  Blender -b -P blender/render.py -- --shot b05_loom --mode final --res 1920x1080 --samples 64 [--frames a-b]
"""
from __future__ import annotations

import math

import numpy as np

# ------------------------------------------------------------------------------------------------ the loom
#
# Loom units (lib/weave.py coordinates): x across, y along the warps (the cloth toward -y, the fell at 0), z up. One
# unit is U metres: the weft (the diff thread) has radius RF, the bone warps RW.

U = 0.01
LANES = ("facts", "incidents", "rules", "skills")
COUNTS = (8, 7, 5, 6)
PITCH = 2.6  # warp pitch across
PICK = 2.0  # pick pitch along: one row per beat (the rows packed, the cloth weft-faced: the diff thread is its face)
GAP = 10.0  # more than a pitch between the lanes' edge warps
RW, RF = 0.5, 0.95  # warp and weft radii
AW, AF = 0.55, 0.6  # crimp: the warp's and the weft's (at a crossing they press together)
WARP_LAY = 30.0  # the bone warps' lay (degrees); the weft is DIFF_THREAD's 14
OVER = 1.25  # how far a row runs past its lane's edge warps
RACE = 12.0  # where the shuttle flies (beyond the fell), and the row it lays waits to be beaten in
HEDDLE, BEAM, SHED_H = 70.0, 330.0, 5.5  # the shed: open SHED_H either side of the cloth's plane at the heddles
NEAR = -175.0  # the warps' near end (behind the frame's bottom edge)
HISTORY = 64  # rows woven before the cut in facts and rules (row 0 was beaten in on the cut)
TTL_ROWS = 12  # incidents rows standing at the cut (the oldest -11)
EXPIRE = 3  # the three oldest go on "let go"
BOX = 7.0  # the shuttle boxes beyond the lanes' edges; it turns back TURN past the rules lane until it reaches skills
TURN = 3.5
SH_LEN, SH_R = 13.0, 1.9  # the shuttle: a glass spindle, length and girth
STEP = 0.3  # sample spacing along threads in the cloth and at the fell

SEED = 5
FZ_PTS = 5  # points per fuzz fibre
FZ_WARP, FZ_WEFT = 3.2, 4.0  # fuzz fibres per unit of length of a warp, of a row
FZ_R = 0.011  # their radius


# ------------------------------------------------------------------------------------------------ time

def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def smooth(x: float) -> float:
    x = _clip01(x)
    return x * x * (3 - 2 * x)


def out_cubic(x: float) -> float:
    return 1 - (1 - _clip01(x)) ** 3


def in_out_cubic(x: float) -> float:
    x = _clip01(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def spring(t: float, freq: float = 5.0, damping: float = 0.6) -> float:
    """motion.ts spring: the house step response (0 at t <= 0, 9.5% overshoot at the defaults, settled by 250 ms)."""
    if t <= 0:
        return 0.0
    w = 2 * math.pi * freq
    a = damping * w
    if a * t > 40:
        return 1.0
    b = w * math.sqrt(1 - damping * damping)
    return 1 - math.exp(-a * t) * (math.cos(b * t) + (a / b) * math.sin(b * t))


class Cues:
    """The shot's times, from the data: the scene's window, the beat before its first frame (row 0 was beaten in on
    it), the beats the passes land on (to the cut, which the last one lands on), and her words."""

    def __init__(self, timing):
        self.start, self.end = timing.scene("loom")
        beats = timing.audio["beats"]
        self.before = max(b for b in beats if b <= self.start + 1e-6)
        self.beats = [b for b in beats if self.before < b <= self.end + 1e-6]
        self.downbeats = [b for b in timing.audio["downbeats"] if self.before < b <= self.end + 1e-6]
        w = timing.word
        self.facts, self.keep = w("L11", 0).start, w("L11", 2).start
        self.incidents = w("L12", 0).start
        self.incidents_end = w("L12", 0).end
        self.let, self.go = w("L12", 2).start, w("L12", 3).start
        self.rules, self.never, self.brk = w("L13", 0).start, w("L13", 2).start, w("L13", 3).start
        self.skills, self.need = w("L14", 0).start, w("L14", 4).start


# ------------------------------------------------------------------------------------------------ the story

class Story:
    """The choreography (pure; tested without Blender). Times in song seconds, lengths in loom units."""

    def __init__(self, cues: Cues):
        from lib import weave

        self.c = cues
        self.lanes = weave.layout(LANES, COUNTS, PITCH, GAP)
        self.lane = {l.name: l for l in self.lanes}
        self.clock = weave.WeaveClock(cues.beats, cues.before)
        # skills: the first left-to-right pass that lands after she names them flies on into their lane
        self.reach = next(p.k for p in self.clock.passes if p.start == -1 and p.land >= cues.skills)
        self.skills_row = self.reach + 1
        # incidents: the three oldest rows let go one after another across "let go"
        self.oldest = -(TTL_ROWS - 1)
        self.release = [cues.let + (cues.go - cues.let) * i / (EXPIRE - 1) for i in range(EXPIRE)]

    # ---- rows
    def rows(self, lane: str) -> range:
        """Every row that is ever in a lane during the shot (woven before it, or during it)."""
        last = self.clock.passes[-1].row
        first = {"facts": -HISTORY + 1, "rules": -HISTORY + 1, "incidents": self.oldest,
                 "skills": self.skills_row}[lane]
        return range(first, last + 1)

    def woven_in(self, lane: str, k: int) -> bool:
        """Does pass k weave this lane? Skills only from the reach on."""
        return lane != "skills" or k >= self.reach

    def row_state(self, lane: str, r: int, t: float):
        """(y, crimp 0..1, drawn) of row r at t: drawn is the stretch (x0, x1) a row in flight covers so far (empty until
        the shuttle reaches the lane), None for a whole row. None while the row does not exist (not yet laid, or an
        expiring incident: those are drawn as pieces, `Expiring`)."""
        clock = self.clock
        if lane == "incidents" and r < self.oldest + EXPIRE:
            return None
        if lane == "skills" and r < self.skills_row:
            return None
        if r <= 0:
            return PICK * (r - clock.taken(t)), 1.0, None
        p = clock.passes[r - 1]  # the pass that lays it
        if not self.woven_in(lane, p.k) or t < p.depart:
            return None
        if t < p.land - clock.lead:  # in flight: drawn behind the shuttle, waiting at the race
            return RACE, 0.0, self.drawn(lane, p, t)
        bu = clock.beat_up(t, p.land)
        if bu < 1.0:  # the reed beats it in
            return RACE * (1 - bu), bu, None
        return PICK * (r - clock.taken(t)), 1.0, None

    def drawn(self, lane: str, p, t: float) -> tuple[float, float]:
        """The stretch (x0, x1) of a lane a row in flight covers: from the side it started to the shuttle (the thread
        leaves it at its middle). Empty (x1 < x0) until the shuttle reaches the lane."""
        L = self.lane[lane]
        a, b = L.x0 - OVER, L.x1 + OVER
        x = self.shuttle_x(t)
        if p.start == -1:  # left to right
            return (a, a - 1.0) if x <= a else (a, min(b, x))
        return (b + 1.0, b) if x >= b else (max(a, x), b)

    def commit(self, r: int) -> float:
        """When row r was beaten in (its moss strand flares on it): a pass's beat, or for rows woven before the shot one
        beat apart back from row 0, which went in on the cut."""
        if r >= 1:
            return self.clock.passes[r - 1].land
        return self.c.before + r * (self.c.beats[0] - self.c.before)

    # ---- the shuttle
    def right_box(self, k: int) -> float:
        """Where pass k turns on the right: just past the rules lane (short of skills) until the reach, then the box
        beyond skills."""
        return self.lane["skills"].x1 + BOX if k >= self.reach else self.lane["rules"].x1 + TURN

    def ends(self, k: int) -> tuple[float, float]:
        """Pass k's start and landing x: even passes fly left to right, odd ones back from where the last one turned."""
        left = self.lane["facts"].x0 - BOX
        if self.clock.passes[k].start == -1:
            return left, self.right_box(k)
        return self.right_box(k - 1), left

    def shuttle_x(self, t: float) -> float:
        clock = self.clock
        p = clock.current(t)
        if p is None:  # after the last landing
            return self.ends(clock.passes[-1].k)[1]
        x0, x1 = self.ends(p.k)
        return x0 + (x1 - x0) * clock.flight(t, p)  # flight() is 0 until it departs: it waits in its box

    def shuttle_y(self, t: float) -> float:
        return RACE

    # ---- the tiers
    def facts_light(self, t: float) -> float:
        """0..1: the steady light settling on the facts lane as she names it, held."""
        return smooth((t - self.c.facts + 0.15) / 0.55)

    def fray(self, i: int, t: float) -> float:
        """0..1: how far expiring row i (0 the oldest) has frayed: from "Incidents…" to its release."""
        a = self.c.incidents - 0.05
        return smooth((t - a) / (self.release[i] - a)) ** 1.3

    def released(self, i: int, t: float) -> float:
        """Seconds since expiring row i let go (<= 0 before)."""
        return t - self.release[i]

    def slack(self, t: float) -> float:
        """The rules warps' slack, 1 until she names them, then snapped out on a spring (it overshoots: the warps
        bounce taut)."""
        return 1.0 - spring(t - self.c.rules + 0.02, freq=4.2, damping=0.45)

    def pluck(self, t: float) -> float:
        """The pluck on "break": a ringing displacement (loom units at the middle of the open warps)."""
        d = t - self.c.brk
        if d <= 0:
            return 0.0
        return 1.4 * (1 - math.exp(-d / 0.006)) * math.exp(-d / 0.32) * math.sin(2 * math.pi * 7.0 * d)

    def rules_light(self, t: float) -> float:
        """0..1: the hard light along the rules warps, coming up as they pull tight ("loaded whole")."""
        return smooth((t - self.c.rules) / 0.18) * (0.75 + 0.25 * math.exp(-max(0.0, t - self.c.rules) / 0.5))

    def skills_reached(self) -> float:
        """When the shuttle first crosses into the skills lane (song seconds)."""
        p = self.clock.passes[self.reach]
        x = self.lane["skills"].x0 - RW
        lo, hi = p.depart, p.land
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if self.shuttle_x(mid) < x:
                lo = mid
            else:
                hi = mid
        return hi

    def skills_light(self, t: float) -> float:
        """0..1: the skills lane's light, dim until the shuttle reaches it."""
        return out_cubic((t - self.skills_reached()) / 0.3)

    def skills_sweep(self, t: float) -> tuple[float, float]:
        """(y, 0..1): a light running along the skills warps from where the shuttle reached them into the dark beyond
        the fell, as they light (where it is aimed, and how bright)."""
        d = t - self.skills_reached()
        y = -18.0 + 150.0 * out_cubic(d / 0.7)
        level = smooth(d / 0.06) * (1 - smooth((d - 0.35) / 0.5))
        return y, level

    def skills_shed(self, t: float) -> float:
        """0..1: how far the skills warps have joined the shed: they rise into it on the change-over before the reach
        pass (loaded on demand)."""
        p = self.clock.passes[self.reach]
        before = self.clock.before if p.k == 0 else self.clock.passes[p.k - 1].land
        return smooth((t - before) / (p.depart - before))


# ------------------------------------------------------------------------------------------------ the shot

def _look_frames() -> str:
    """The key moments: "Facts I keep", the incidents fraying, letting go, the rules pulled tight, the skills lighting."""
    from lib import timing

    c = Cues(timing.film())
    s = Story(c)
    ts = [c.facts + 0.35, c.incidents + 0.6, s.release[1] + 0.12, c.rules + 0.3, s.skills_reached() + 0.12]
    return ",".join(str(timing.frame(x)) for x in ts)


SHOT = {"scene": "loom", "frames": "scene", "look": _look_frames(),
        "track": ["lbl_facts", "lbl_incidents", "lbl_rules", "lbl_skills", "gc", "shuttle", "reach", "fell_l", "fell_r"]}


# ------------------------------------------------------------------------------------------------ geometry (pure)
#
# A row's weft is the diff thread (lib/thread.py diff_tubes: three bone plies, the blood and the moss strand in their
# grooves) wound round its crimped centreline in the row's plane, its lay phase running on from row to row. Rows are
# built once in the row's own frame (at y = 0), crimped and straight (a row in flight lies straight in the open shed and
# takes its crimp as it is beaten in); a frame only moves them. Warps are posed whole every (sub)frame: their crimp
# travels with the cloth, they open into the shed, and the rules and skills warps do their own things.


def row_phase(r: int) -> float:
    """The diff thread's lay phase (turns) at the start of row r: it runs on from row to row (a golden-ratio step, so
    no two neighbours match)."""
    return (r * 0.6180339887) % 1.0


def weft_tubes(lane, r: int, crimp: float = 1.0, *, fray: float = 0.0):
    """Row r's weft across `lane` in its own frame (y = 0): [(color, points (m, 3), radius)] for the three bone plies
    and the blood and moss strands. `crimp` scales the over/under; `fray` (0..1) loosens it: the plies stand off and
    untwist, the row swells."""
    from lib import thread, weave

    x = np.arange(lane.x0 - OVER, lane.x1 + OVER + 1e-9, STEP)
    c = (x - lane.x0) / PITCH
    z = crimp * weave.weft_crimp(c, r, AF) * (1 - 0.35 * fray)
    centre = np.column_stack([x, np.zeros_like(x), z])
    twist = thread.diff_twist(RF) * (1 - 0.55 * fray)
    out = []
    for tube in thread.diff_tubes():
        d = tube["d"] * RF * (1 + 1.1 * fray)
        P = weave.ply_offsets(centre, (0.0, 1.0, 0.0), d, twist, phase=row_phase(r) + tube["phase"], plies=1)[0]
        out.append((tube["color"], P, tube["r"] * RF * (1 + 0.15 * fray)))
    return out


def warp_samples(y0: float) -> np.ndarray:
    """Where a warp is sampled, from its near end y0 to the back beam: STEP apart in the cloth and the shed's mouth,
    coarser past the heddles."""
    a = np.linspace(y0, 0.0, max(2, int(round(-y0 / STEP)) + 1))
    b = np.linspace(0.0, HEDDLE, int(HEDDLE / 0.5) + 1)[1:]
    c = np.linspace(HEDDLE, BEAM, 70)[1:]
    return np.concatenate([a, b, c])


N_WARP = None  # samples per warp (warp_samples(NEAR)); every warp keeps its count, the incidents' near end moving


def n_warp() -> int:
    global N_WARP
    if N_WARP is None:
        N_WARP = len(warp_samples(NEAR))
    return N_WARP


def resample_warp(y0: float) -> np.ndarray:
    """n_warp() samples from y0 to the back beam, spread like warp_samples(NEAR) (so a warp whose near end moves keeps
    its point count)."""
    ref = warp_samples(NEAR)
    cloth = ref <= 0
    out = np.empty_like(ref)
    out[cloth] = y0 + (0.0 - y0) * (ref[cloth] - NEAR) / (0.0 - NEAR)
    out[~cloth] = ref[~cloth]
    return out


def lane_mask(story: Story, lane: str, rho: np.ndarray, t: float = 0.0) -> np.ndarray:
    """0..1 along a lane's warps at row coordinate rho: 1 where its cloth is woven (the warps crimp), 0 where they run
    bare (skills before its first row; incidents past their oldest row, and straightening under each expiring row as
    it lifts away)."""
    rho = np.asarray(rho, float)
    if lane == "skills":
        return np.clip((rho - (story.skills_row - 0.5)) / 0.5, 0.0, 1.0)
    if lane == "incidents":
        m = np.clip((rho - (story.oldest - 0.5)) / 0.5, 0.0, 1.0)
        for i in range(EXPIRE):
            r = story.oldest + i
            gone = smooth(story.released(i, t) / 0.3)
            m = np.where(np.abs(rho - r) <= 0.5, m * (1 - gone), m)
        return m
    return np.ones_like(rho)


def warp_pose(story: Story, lane: str, t: float):
    """Every warp of a lane at t: (centrelines (count, M, 3), material coordinate (M,), splay (M,), taper (M,)).

    In the cloth (y <= 0) a warp crimps over and under the rows, the pattern travelling toward the camera with the take-up;
    beyond the fell it opens into the shed (blending from its crimp at the fell), up or down as the clock says. The
    incidents warps start at their near end (the oldest surviving row's edge; the expiring rows' warps are pieces) and
    splay into a brush there once the last of those has let go. The rules warps sag until she names them, snap taut, and
    ring on "break". The skills warps lie out of the shed until the pass before the reach."""
    from lib import weave

    c = story.c
    L = story.lane[lane]
    n = story.clock.taken(t)
    y0 = NEAR
    y = resample_warp(y0)
    rho = n + y / PICK
    m = PICK * rho  # material coordinate: fixed to the warp as the loom draws it toward the camera
    cloth = y <= 0
    woven = lane_mask(story, lane, rho, t)
    open_ = weave.shed_profile(y, HEDDLE, BEAM)
    span = np.sin(np.pi * np.clip(y / HEDDLE, 0.0, 1.0))  # the stretch between the fell and the heddles
    blend = 1 - np.clip(y / 4.0, 0.0, 1.0) ** 2
    shed_k = story.skills_shed(t) if lane == "skills" else 1.0
    out = np.empty((L.count, len(y), 3))
    for i, j in enumerate(L.warps()):
        zc = weave.warp_crimp(rho, j, AW)
        z = np.where(cloth, woven * zc, 0.0)
        zf = float(weave.warp_crimp(n, j, AW)) * float(lane_mask(story, lane, np.array([n]), t)[0])
        z = z + np.where(cloth, 0.0, zf * blend + story.clock.shed(t, j) * shed_k * SHED_H * open_)
        x = np.full_like(y, L.xs[i])
        if lane == "rules":
            k = story.slack(t)
            ph = 1.7 * i
            z = z - k * 2.6 * span + story.pluck(t) * (0.85 + 0.3 * math.sin(2.1 * i + 0.4)) * span
            x = x + k * 1.5 * np.sin(2 * np.pi * y / 24.0 + ph) * span
        out[i] = np.column_stack([x, y, z])
    splay = np.zeros_like(y)
    taper = np.ones_like(y)
    return out, m, splay, taper


def warp_plies(centres: np.ndarray, m: np.ndarray, splay: np.ndarray, phase0: float = 0.0):
    """The three bone plies round each warp centreline (count, M, 3): (plies (count, 3, M, 3))."""
    from lib import weave

    off = 0.5 * RW * (1 + splay)
    turns = weave.lay_turns(WARP_LAY, 0.5 * RW)
    out = np.empty((centres.shape[0], 3, centres.shape[1], 3))
    for i, c in enumerate(centres):
        T = np.gradient(c, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
        N = np.array([1.0, 0.0, 0.0]) - T * T[:, :1]
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
        B = np.cross(T, N)
        for k in range(3):
            th = (2 * np.pi * (phase0 + 0.29 * i + k / 3 + turns * m))[:, None]
            out[i, k] = c + off[:, None] * (np.cos(th) * N + np.sin(th) * B)
    return out


class Expiring:
    """The incidents' three oldest rows and the warps under them, as pieces (pure): in place they are the cloth (the
    regular objects leave them out), fraying from "Incidents…"; when a row lets go its pieces lift out of the weave one
    after another, fly up and tumble, thinning to nothing in the dark, its blood strand burning as it goes.

    Pieces are index ranges of a tube's points, each its own curve (the shared end point repeated), so the topology
    never changes. `pose(t)` gives every piece's points and radii, grouped by material ('bone', 'blood', 'moss')."""

    def __init__(self, story: Story):
        from lib import weave

        self.s = story
        rng = np.random.default_rng(SEED)
        L = story.lane["incidents"]
        self.rows = [story.oldest + i for i in range(EXPIRE)]
        self.tubes = {"bone": [], "blood": [], "moss": []}  # (row i, rest (m,3), frayed (m,3), radius, pieces)
        for i, r in enumerate(self.rows):
            rest = weft_tubes(L, r)
            fr = weft_tubes(L, r, fray=1.0)
            for (col, P0, rad), (_, P1, rad1) in zip(rest, fr):
                cuts = self._cuts(len(P0), rng, 6, 14)
                self.tubes[col].append((i, P0, P1, rad, cuts))
        # every piece's flight
        self.flights = {}
        for col, items in self.tubes.items():
            fl = []
            for (i, P0, _, _, cuts) in items:
                for a, b in cuts:
                    fl.append(self._flight(rng, i))
            self.flights[col] = fl
        # the fray's fibres: lying along the row's plies, lifting as it frays, then flying
        self.fibres = self._fibres(rng)

    @staticmethod
    def _cuts(m: int, rng, lo: int, hi: int):
        """Index ranges [a, b] (inclusive, sharing ends) splitting m points into pieces of lo..hi points."""
        out, a = [], 0
        while a < m - 1:
            b = min(m - 1, a + int(rng.integers(lo, hi + 1)))
            if m - 1 - b < lo // 2:
                b = m - 1
            out.append((a, b))
            a = b
        return out

    @staticmethod
    def _flight(rng, i: int) -> dict:
        ax = rng.normal(size=3)
        return {"row": i, "delay": float(rng.uniform(0.0, 0.16)),
                "v": np.array([rng.normal(0, 2.5), rng.uniform(1.0, 5.0), rng.uniform(5.0, 10.0)]),
                "drift": np.array([rng.normal(0, 0.8), rng.uniform(1.0, 3.0), rng.uniform(2.0, 4.0)]),
                "axis": ax / np.linalg.norm(ax), "spin": float(rng.uniform(0.6, 2.4) * rng.choice([-1, 1])),
                "drag": float(rng.uniform(0.25, 0.45)), "life": float(rng.uniform(0.55, 0.95))}

    def _fibres(self, rng) -> dict:
        n = 260
        L = self.s.lane["incidents"]
        rows = rng.integers(0, EXPIRE, n * EXPIRE)
        x = rng.uniform(L.x0 - OVER * 0.5, L.x1 + OVER * 0.5, len(rows))
        ang = rng.uniform(0, 2 * np.pi, len(rows))
        length = np.clip(rng.lognormal(math.log(0.9), 0.5, len(rows)), 0.3, 2.4)
        lean = rng.choice([-1.0, 1.0], len(rows)) * rng.uniform(0.2, 1.0, len(rows))
        ax = rng.normal(size=(len(rows), 3))
        return {"row": rows, "x": x, "ang": ang, "len": length, "lean": lean,
                "axis": ax / np.linalg.norm(ax, axis=1, keepdims=True),
                "spin": rng.uniform(2, 9, len(rows)) * rng.choice([-1, 1], len(rows)),
                "v": np.column_stack([rng.normal(0, 4, len(rows)), rng.uniform(1, 7, len(rows)),
                                      rng.uniform(6, 16, len(rows))]),
                "drift": np.column_stack([rng.normal(0, 1.5, len(rows)), rng.uniform(1, 4, len(rows)),
                                          rng.uniform(2, 5, len(rows))]),
                "delay": rng.uniform(0.0, 0.2, len(rows)), "life": rng.uniform(0.5, 1.1, len(rows)),
                "radius": 0.018 * rng.uniform(0.7, 1.3, len(rows)), "kink": rng.normal(0.0, 0.3, (len(rows), 2))}

    def row_y(self, i: int, t: float) -> float:
        """Where expiring row i lies (world y) while it is in the cloth: taken up with it."""
        return PICK * (self.rows[i] - self.s.clock.taken(t))

    def counts(self) -> dict:
        """Points per piece, by material (fixed)."""
        out = {}
        for col, items in self.tubes.items():
            out[col] = [b - a + 1 for (_, _, _, _, cuts) in items for a, b in cuts]
        return out

    def pose(self, t: float) -> dict:
        """{material: (points (P, 3), radii (P,), per-piece heat (pieces,))} at t."""
        s = self.s
        out = {}
        for col, items in self.tubes.items():
            pts, rads, heat = [], [], []
            fi = 0
            for (i, P0, P1, rad, cuts) in items:
                f = s.fray(i, t)
                P = P0 + (P1 - P0) * f
                P = P + np.array([0.0, self.row_y(i, t), 0.45 * f])
                for a, b in cuts:
                    fl = self.flights[col][fi]
                    fi += 1
                    seg = P[a:b + 1]
                    age = s.released(i, t) - fl["delay"]
                    r = np.full(len(seg), rad)
                    h = 0.0
                    if age > 0:
                        # broken, not cut: each piece thins to its ends as it comes away
                        arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(seg, axis=0), axis=1))])
                        to_end = np.minimum(arc, arc[-1] - arc) / 0.7
                        r = r * (1 - (1 - np.clip(to_end, 0.0, 1.0) ** 0.6) * smooth(age / 0.08))
                        c0 = seg.mean(axis=0)
                        dr = fl["drag"]
                        move = fl["v"] * dr * (1 - math.exp(-age / dr)) + fl["drift"] * age
                        seg = _rotate_about(seg - c0, fl["axis"], fl["spin"] * age) + c0 + move
                        r = r * (1 - smooth((age - 0.15 * fl["life"]) / fl["life"])) ** 1.5
                        if col == "blood":
                            h = 3.4 * math.exp(-age / 0.45)
                    if col == "blood":
                        h = h + s.fray(i, t) * 1.1 + 0.15
                    elif col == "moss":
                        h = 0.15 * (1 - smooth(age / 0.3)) if age > 0 else 0.15
                    pts.append(seg)
                    rads.append(r)
                    heat.append(h)
            out[col] = (np.vstack(pts), np.concatenate(rads), np.array(heat))
        return out

    def fibre_pose(self, t: float):
        """The fray's fibres: (points (n, 5, 3), radii (n, 5))."""
        s, F = self.s, self.fibres
        n = len(F["row"])
        k = np.linspace(0, 1, 5)
        f = np.array([s.fray(i, t) for i in range(EXPIRE)])[F["row"]]
        y = np.array([self.row_y(i, t) for i in range(EXPIRE)])[F["row"]]
        age = np.array([s.released(i, t) for i in range(EXPIRE)])[F["row"]] - F["delay"]
        # root on the row's surface, round it at `ang`; the fibre lies along the row, lifting toward the light as it frays
        root = np.column_stack([F["x"], y + RF * np.cos(F["ang"]) * 0.9, RF * np.sin(F["ang"]) * 0.9 + 0.45 * f])
        lift = 0.1 + 1.05 * f
        d = np.column_stack([F["lean"] * np.cos(lift), 0.25 * np.cos(F["ang"]) * np.sin(lift), np.sin(lift)])
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        L = F["len"] * (0.35 + 0.65 * f)
        pts = root[:, None, :] + d[:, None, :] * (L[:, None] * k[None, :])[..., None]
        pts[..., 2] += (0.12 * L[:, None] * k[None, :] ** 2)
        pts[..., 0] += F["kink"][:, 0:1] * L[:, None] * np.sin(np.pi * k[None, :]) * 0.6  # never straight
        pts[..., 1] += F["kink"][:, 1:2] * L[:, None] * k[None, :] ** 2
        grow = np.clip(f * 3.0, 0.0, 1.0)
        rad = (F["radius"] * grow)[:, None] * (1 - 0.6 * k[None, :])
        flying = age > 0
        if flying.any():
            a = np.maximum(age, 0.0)[:, None]
            move = F["v"] * 0.35 * (1 - np.exp(-a / 0.35)) + F["drift"] * a
            c0 = pts.mean(axis=1)
            rel = pts - c0[:, None, :]
            rel = _rotate_many(rel, F["axis"], F["spin"] * a[:, 0])
            moved = rel + (c0 + move)[:, None, :]
            pts = np.where(flying[:, None, None], moved, pts)
            fade = 1 - np.clip((age - 0.3 * F["life"]) / F["life"], 0.0, 1.0)
            rad = np.where(flying[:, None], rad * np.clip(fade, 0.0, 1.0)[:, None], rad)
        return pts, rad


class Fuzz:
    """Loose fibres standing off the threads (pure): short kinked hair curves (FZ_PTS points) whose roots ride their
    thread. On the wefts they are fixed to their row (they travel with it, show with it, and are drawn on with it); on
    the warps they are fixed to the warp's material coordinate, so the loom draws them toward the camera and they ride
    the warps up and down in the shed. Seeded: the same every frame."""

    def __init__(self, story: Story, rows: dict, geo: dict):
        rng = np.random.default_rng(SEED + 1)
        self.s = story
        k = np.linspace(0.0, 1.0, FZ_PTS)
        # warps: material coordinates spanning every warp's whole run over the shot (it moves PICK per beat)
        span = (NEAR, BEAM + PICK * (len(story.clock.passes) + 1))
        self.warp = {}
        for lane in LANES:
            L = story.lane[lane]
            n = int(FZ_WARP * (span[1] - span[0]) * L.count)
            self.warp[lane] = {
                "i": rng.integers(0, L.count, n), "m": rng.uniform(*span, n), "a": rng.uniform(0, 2 * np.pi, n),
                "len": np.clip(rng.lognormal(math.log(0.5), 0.55, n), 0.15, 1.8),
                "lean": rng.uniform(-1.0, 1.0, n), "lift": rng.uniform(0.08, 0.7, n),
                "kink": rng.normal(0.0, 0.28, (n, 2)), "r": FZ_R * rng.uniform(0.7, 1.3, n)}
        # wefts: per lane, per row, in the row's own frame (x along it, round its crimped centreline)
        self.weft = {}
        for lane in LANES:
            L = story.lane[lane]
            nr = len(rows[lane])
            per = int(FZ_WEFT * (L.x1 - L.x0 + 2 * OVER))
            n = nr * per
            row = np.repeat(np.arange(nr), per)
            x = rng.uniform(L.x0 - OVER, L.x1 + OVER, n)
            a = rng.uniform(0, 2 * np.pi, n)
            c = (x - L.x0) / PITCH
            from lib import weave
            zc = np.array([float(v) for v in weave.weft_crimp(c, 0, AF)]) * np.where(
                np.array(rows[lane])[row] % 2 == 0, 1.0, -1.0)
            root = np.column_stack([x, RF * 0.92 * np.cos(a), zc + RF * 0.92 * np.sin(a)])
            out = np.column_stack([np.zeros(n), np.cos(a), np.sin(a)])
            lean = rng.uniform(-1.0, 1.0, n)
            lift = rng.uniform(0.08, 0.65, n)
            d = out * np.sin(lift)[:, None] + np.column_stack([lean, np.zeros(n), np.zeros(n)]) * np.cos(lift)[:, None]
            d /= np.linalg.norm(d, axis=1, keepdims=True)
            ln = np.clip(rng.lognormal(math.log(0.45), 0.55, n), 0.15, 1.6)
            kink = rng.normal(0.0, 0.28, (n, 2))
            side = np.cross(d, out)
            pts = (root[:, None, :] + d[:, None, :] * (ln[:, None] * k[None, :])[..., None]
                   + out[:, None, :] * (kink[:, 0:1] * ln[:, None] * k[None, :] ** 2)[..., None]
                   + side[:, None, :] * (kink[:, 1:2] * ln[:, None] * k[None, :] ** 2)[..., None])
            self.weft[lane] = {"row": row, "x": x, "pts": pts, "r": FZ_R * rng.uniform(0.7, 1.3, n)}
        self.k = k

    def counts(self, lane: str) -> tuple[int, int]:
        return len(self.warp[lane]["m"]), len(self.weft[lane]["row"])

    def warps(self, lane: str, centres: np.ndarray, t: float):
        """The fuzz on a lane's warps, given their centrelines (count, M, 3) at t: (points (n, FZ_PTS, 3), radii)."""
        F = self.warp[lane]
        n_taken = self.s.clock.taken(t)
        y = F["m"] - PICK * n_taken  # where each fibre's root is along its warp now
        ys = centres[0, :, 1]
        cx = np.empty_like(y)
        cz = np.empty_like(y)
        for i in range(centres.shape[0]):
            sel = F["i"] == i
            cx[sel] = np.interp(y[sel], ys, centres[i, :, 0])
            cz[sel] = np.interp(y[sel], ys, centres[i, :, 2])
        a = F["a"]
        out = np.column_stack([np.cos(a), np.zeros_like(a), np.sin(a)])
        root = np.column_stack([cx, y, cz]) + out * RW * 0.9
        d = out * np.sin(F["lift"])[:, None] + np.column_stack(
            [np.zeros_like(a), F["lean"], np.zeros_like(a)]) * np.cos(F["lift"])[:, None]
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        side = np.cross(d, out)
        k, ln = self.k, F["len"]
        pts = (root[:, None, :] + d[:, None, :] * (ln[:, None] * k[None, :])[..., None]
               + out[:, None, :] * (F["kink"][:, 0:1] * ln[:, None] * k[None, :] ** 2)[..., None]
               + side[:, None, :] * (F["kink"][:, 1:2] * ln[:, None] * k[None, :] ** 2)[..., None])
        live = (y >= ys[0]) & (y <= ys[-1])
        rad = (F["r"] * live)[:, None] * (1 - 0.6 * k[None, :])
        return pts, rad

    def wefts(self, lane: str, ys: np.ndarray, vis_rows: np.ndarray, drawn: list):
        """The fuzz on a lane's rows: each row's y, whether it shows, and the drawn stretch of a row in flight (or None
        for the whole row): (points, radii). A row in flight lies straight; its fibres keep their crimped places."""
        F = self.weft[lane]
        row = F["row"]
        pts = F["pts"].copy()
        pts[..., 1] += ys[row][:, None]
        show = vis_rows[row].astype(float)
        for idx, d in enumerate(drawn):
            if d is not None:
                sel = row == idx
                show[sel] *= ((F["x"][sel] >= d[0]) & (F["x"][sel] <= d[1])).astype(float)
        rad = (F["r"] * show)[:, None] * (1 - 0.6 * self.k[None, :])
        return pts, rad


def _rotate_about(p: np.ndarray, axis: np.ndarray, ang: float) -> np.ndarray:
    """Rodrigues: points (m, 3) about a unit axis by ang."""
    c, s = math.cos(ang), math.sin(ang)
    return p * c + np.cross(axis, p) * s + axis[None, :] * (p @ axis)[:, None] * (1 - c)


def _rotate_many(p: np.ndarray, axis: np.ndarray, ang: np.ndarray) -> np.ndarray:
    """Rodrigues: points (n, k, 3) each set about its own unit axis (n, 3) by ang (n,)."""
    c, s = np.cos(ang)[:, None, None], np.sin(ang)[:, None, None]
    k = axis[:, None, :]
    return p * c + np.cross(k, p) * s + k * np.sum(k * p, axis=2, keepdims=True) * (1 - c)


def label_anchor(story: Story, lane: str) -> tuple[float, float, float]:
    """Where a tier's label hangs from (loom units): on its lane at the fell, a warp in from its left edge, on the
    newest row's crown. Fixed in the world: the cloth moves under it, the label doesn't."""
    L = story.lane[lane]
    return (L.x0 + PITCH, 0.0, RF + 0.4)


# ------------------------------------------------------------------------------------------------ the camera (pure)

class CameraRig:
    """Low on the cloth side, close to the fell: a macro tour of the tiers. It holds on each tier while she names it,
    drifting slowly (the camera's sultriness), and snaps across to the next on the beat before her next line, a slide
    eased in and out of the drifts either side (C1: the drift's own speed at both ends), so the plate's motion blur
    streaks it like a whip. Keys of eye and look in loom units. Focus is on the subject it looks at, and on the
    expiring rows while they fray and let go. Pure: tested without Blender."""

    FOV = 32.0  # vertical, degrees
    FSTOP = 2.2
    SLIDE = 0.3  # a snap's length (s): it lands just after its beat

    def __init__(self, story: Story, expiring: "Expiring | None" = None):
        c, s = story.c, story
        self.s, self.e = story, expiring
        L = story.lane
        fa, inc, ru, sk = (L[n].centre for n in LANES)
        # each snap lands (a hair after) the beat at or before the tier's word: "Incidents…" is on its beat, so the camera
        # arrives as she says it; the rules and skills snaps land a beat's fraction ahead, so their slack and their
        # dimness are seen first
        lands = [max(b for b in c.beats if b <= at + 1e-6) + 0.06 for at in (c.incidents, c.rules, c.skills)]
        a = [x - self.SLIDE for x in lands]
        # holds: (from, to, (eye, look) at its start, (eye, look) at its end)
        self.holds = [
            (c.start - 0.1, a[0], ((fa - 15.0, -47.0, 12.0), (fa + 1.5, 2.0, 0.0)),
             ((fa - 10.5, -48.0, 12.3), (fa + 4.0, 1.0, 0.0))),
            (lands[0], a[1], ((inc - 15.0, -67.0, 13.2), (inc + 0.5, -20.0, 0.0)),
             ((inc - 10.0, -69.0, 13.6), (inc + 2.0, -26.0, 0.0))),
            (lands[1], a[2], ((ru - 13.5, -45.0, 11.6), (ru + 0.5, 3.0, 0.0)),
             ((ru - 8.5, -46.0, 11.1), (ru + 4.0, 3.0, 0.0))),
            (lands[2], c.end + 0.1, ((sk - 16.0, -46.0, 11.3), (sk - 5.0, 4.0, 0.0)),
             ((sk - 9.5, -43.0, 10.6), (sk + 1.0, 4.0, 0.0))),
        ]
        self.rack = [(c.incidents - 0.1, c.incidents + 0.45), (c.go + 0.25, lands[1] - 0.05)]

    def _pose(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        hs = self.holds
        for i, (t0, t1, p0, p1) in enumerate(hs):
            if t <= t1 or i == len(hs) - 1:
                if t >= t0 or i == 0:  # in a hold: a straight, even drift
                    u = min(1.0, max(0.0, (t - t0) / (t1 - t0)))
                    return tuple(np.asarray(p0[k]) + (np.asarray(p1[k]) - np.asarray(p0[k])) * u for k in range(2))
                # a snap from the hold before: Hermite from its end to this one's start, at the drifts' speeds
                q0, q1, (s0, e0, a0, b0), (s1, e1, a1, b1) = hs[i - 1][1], t0, hs[i - 1], hs[i]
                h = q1 - q0
                u = (t - q0) / h
                h00, h10 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u
                h01, h11 = -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
                out = []
                for k in range(2):
                    pa, pb = np.asarray(b0[k], float), np.asarray(a1[k], float)
                    va = (pa - np.asarray(a0[k], float)) / (e0 - s0)
                    vb = (np.asarray(b1[k], float) - pb) / (e1 - s1)
                    out.append(h00 * pa + h10 * h * va + h01 * pb + h11 * h * vb)
                return out[0], out[1]
        raise AssertionError("unreachable")

    def at(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        eye, look = self._pose(t)
        return np.asarray(eye, float), np.asarray(look, float)

    def focus_point(self, t: float) -> np.ndarray:
        """Where focus is: on the subject the camera looks at (the featured lane's fell, so focus walks tier to tier with
        the slide), held exactly on the expiring rows from "Incidents…" until they have let go."""
        eye, look = self.at(t)
        if self.e is None:
            return look
        L = self.s.lane["incidents"]
        gc = np.array([L.centre, self.e.row_y(1, t), 0.3])
        (a0, a1), (b0, b1) = self.rack
        u = in_out_cubic((t - a0) / (a1 - a0)) * (1 - in_out_cubic((t - b0) / (b1 - b0)))
        return look + (gc - look) * u

    @staticmethod
    def basis(eye, look) -> np.ndarray:
        """Columns: the camera's right, up and backward axes (it looks down -z), up being world z."""
        back = np.asarray(eye, float) - np.asarray(look, float)
        back /= np.linalg.norm(back)
        right = np.cross(np.array([0.0, 0.0, 1.0]), back)
        right /= np.linalg.norm(right)
        up = np.cross(back, right)
        return np.column_stack([right, up, back])

    def depth(self, t: float, p) -> float:
        eye, look = self.at(t)
        return float(-(self.basis(eye, look)[:, 2] @ (np.asarray(p, float) - eye)))

    def project(self, t: float, p) -> tuple[float, float]:
        """A point's place on the film's logical 1920x1080 frame at t (px from the top left)."""
        eye, look = self.at(t)
        v = self.basis(eye, look).T @ (np.asarray(p, float) - eye)
        ty = math.tan(math.radians(self.FOV) / 2)
        return 960 * (1 + v[0] / (-v[2] * ty * 16 / 9)), 540 * (1 - v[1] / (-v[2] * ty))


# ------------------------------------------------------------------------------------------------ build

def build(ctx):
    import bpy
    from mathutils import Matrix, Vector

    from lib import lights, thread

    scene, coll = ctx.scene, ctx.scene.collection
    cues = Cues(ctx.timing)
    story = Story(cues)
    exp = Expiring(story)
    rig = CameraRig(story, exp)

    # ---- materials: the bone warps and plies (THREAD_LOOK's fibre surface), the strands (DIFF_THREAD; their level is
    # each curve's `heat`, so the Value node stays at 0), the fray's fibres, and glass
    warp_mat = thread.ply_material("loom_warp")
    bone_mat = thread.ply_material("loom_bone")
    strand_mat = {c: thread.strand_material(c, name=f"loom_{c}", heat_attr="lit") for c in ("blood", "moss")}
    for m in strand_mat.values():
        thread.glow_socket(m).default_value = 0.0
    fibre_mat = thread.fibre_material("loom_fibre")
    glass = _glass()

    objs: dict[str, object] = {}

    def curves(name, counts, material, heat=False):
        ob = thread._new_curves(name, counts, np.ones(len(counts)), material, coll, None)
        if heat:
            ob.data.attributes.new("lit", "FLOAT", "CURVE")
        objs[name] = ob
        return ob

    # ---- the warps, per lane
    M = n_warp()
    warp_ob = {}
    for lane in LANES:
        L = story.lane[lane]
        warp_ob[lane] = curves(f"warps.{lane}", [M] * (L.count * 3), warp_mat)

    # ---- the wefts, per lane: every row the shot ever shows, built once (crimped, and straight for a row in flight)
    rows = {lane: list(story.rows(lane)) for lane in LANES}
    geo = {}
    for lane in LANES:
        L = story.lane[lane]
        crimped = [weft_tubes(L, r) for r in rows[lane]]
        straight = [weft_tubes(L, r, crimp=0.0) for r in rows[lane]]
        arr = lambda tubes, k: np.stack([tb[k][1] for tb in tubes])  # noqa: E731  (rows, m, 3)
        g = {"x": crimped[0][0][1][:, 0].copy(), "m": len(crimped[0][0][1]),
             "bone": (np.stack([arr(crimped, k) for k in range(3)], 1), np.stack([arr(straight, k) for k in range(3)], 1)),
             "blood": (arr(crimped, 3), arr(straight, 3)), "moss": (arr(crimped, 4), arr(straight, 4)),
             "r": [crimped[0][k][2] for k in range(5)]}
        geo[lane] = g
        nr = len(rows[lane])
        curves(f"weft.{lane}.bone", [g["m"]] * (nr * 3), bone_mat)
        curves(f"weft.{lane}.blood", [g["m"]] * nr, strand_mat["blood"], heat=True)
        curves(f"weft.{lane}.moss", [g["m"]] * nr, strand_mat["moss"], heat=True)
    commit = {r: story.commit(r) for lane in LANES for r in rows[lane]}
    fuzz = Fuzz(story, rows, geo)
    for lane in LANES:
        nw, nf = fuzz.counts(lane)
        curves(f"fuzz.{lane}", [FZ_PTS] * (nw + nf), fibre_mat)

    # ---- the expiring incidents: pieces, and the fray's fibres
    ecounts = exp.counts()
    for col in ("bone", "blood", "moss"):
        curves(f"expire.{col}", ecounts[col], bone_mat if col == "bone" else strand_mat[col], heat=col != "bone")
    curves("expire.fibres", [5] * len(exp.fibres["row"]), fibre_mat)

    # ---- the shuttle: a glass spindle, flying on its race
    shuttle = _spindle("shuttle", glass)
    coll.objects.link(shuttle)
    inner = _spindle("shuttle.inner", glass, scale=0.86, flip=True)
    inner.parent = shuttle
    coll.objects.link(inner)
    pirn = _pirn(thread, bone_mat, strand_mat, shuttle, coll)

    # ---- anchors for the engine
    anchors = {}
    for name in SHOT["track"]:
        e = bpy.data.objects.new(name, None)
        e.empty_display_size = 0.02
        coll.objects.link(e)
        anchors[name] = e
    for lane in LANES:
        anchors[f"lbl_{lane}"].location = Vector(np.array(label_anchor(story, lane)) * U)
    anchors["reach"].location = Vector(np.array([story.lane["skills"].x0 - RW, RACE, 0.15]) * U)  # Story.skills_reached
    anchors["fell_l"].location = Vector(np.array([story.lane["facts"].x0 - RW, 0.0, 0.0]) * U)
    anchors["fell_r"].location = Vector(np.array([story.lane["skills"].x1 + RW, 0.0, 0.0]) * U)

    # ---- the camera: a 36 mm gate shooting 16:9, the engine's
    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    cam.data.sensor_fit = "VERTICAL"
    cam.data.sensor_height = 20.25
    cam.data.sensor_width = 36.0
    cam.data.lens = 10.125 / math.tan(math.radians(CameraRig.FOV) / 2)
    cam.data.clip_start, cam.data.clip_end = 0.02, 30.0
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = CameraRig.FSTOP
    cam.data.dof.aperture_blades = 7
    cam.data.dof.aperture_rotation = math.radians(12)
    coll.objects.link(cam)
    scene.camera = cam

    # ---- the light: a soft key raking in from the upper left and behind, a hard rim from far behind on the right that
    # draws the open warps as lines into the dark, a low fill from the camera's side; and the tiers' own lights, linked
    # to their lanes: a steady soft top light on facts, a hard rim along the rules warps, the skills lane's copies of
    # the key and rim (dim until reached: the main lights leave the skills warps out), and the expiring rows' blood
    lights.world_color("ink")
    rigl = {}

    def light(name, kind, power, pos, aim, **kw):
        ob = _light(name, kind, power, Vector(np.asarray(pos, float) * U), Vector(np.asarray(aim, float) * U), **kw)
        coll.objects.link(ob)
        rigl[name] = (ob, power)
        return ob

    F, R_, S = story.lane["facts"], story.lane["rules"], story.lane["skills"]
    key = light("key", "SPOT", LIGHT["key"], KEY_AT, KEY_AIM, spot=math.radians(KEY_CONE), soft=16 * U,
                temperature=5600, blend=0.9)
    pool = light("pool", "SPOT", LIGHT["pool"], KEY_AT, KEY_AIM, spot=math.radians(POOL_CONE), soft=10 * U,
                 temperature=5600, blend=0.85)
    rim = light("rim", "SPOT", LIGHT["rim"], RIM_AT, (0.0, -10.0, 0.0), spot=math.radians(24), soft=2 * U,
                temperature=6500)
    fill = light("fill", "AREA", LIGHT["fill"], (60.0, -220.0, 50.0), (0.0, -40.0, 0.0), size=120 * U,
                 temperature=6500)
    top = light("facts_top", "AREA", LIGHT["facts"], (F.centre, -50.0, 46.0), (F.centre, -50.0, 0.0), size=34 * U,
                size_y=170 * U, temperature=5200)
    rrim = light("rules_rim", "SPOT", LIGHT["rules"], (R_.centre + 14.0, 380.0, 9.0), (R_.centre, -30.0, 0.0),
                 spot=math.radians(8), soft=1.5 * U, temperature=6500)
    skey = light("skills_key", "SPOT", LIGHT["key"], KEY_AT, KEY_AIM, spot=math.radians(KEY_CONE),
                 soft=16 * U, temperature=5600, blend=0.9)
    spool = light("skills_pool", "SPOT", LIGHT["pool"], KEY_AT, KEY_AIM, spot=math.radians(POOL_CONE),
                  soft=10 * U, temperature=5600, blend=0.85)
    srim = light("skills_rim", "SPOT", LIGHT["rim"], RIM_AT, (0.0, -10.0, 0.0), spot=math.radians(24), soft=2 * U,
                 temperature=6500)
    kick = light("kicker", "AREA", LIGHT["kicker"], (0.0, -10.0, 30.0), (0.0, RACE, 0.0), size=14 * U,
                 temperature=6000)
    _link(kick, [shuttle, inner] + pirn, "INCLUDE")
    S_ = story.lane["skills"]
    sweep = light("skills_sweep", "SPOT", LIGHT["sweep"], (S_.centre - 6.0, -40.0, 26.0), (S_.centre, 0.0, 0.0),
                  spot=math.radians(14), soft=3 * U, temperature=6000, blend=0.7)
    sheen = _card("sheen", SHEEN_AT, SHEEN_SIZE, LIGHT["sheen"])
    coll.objects.link(sheen)
    blood_rgb = thread.glow_color("blood")
    embers = []
    for i in range(EXPIRE):
        ob = bpy.data.objects.new(f"ember{i}", bpy.data.lights.new(f"ember{i}", "POINT"))
        ob.data.color = blood_rgb
        ob.data.shadow_soft_size = 2.0 * U
        ob.data.energy = 0.0
        ob.visible_camera = False
        coll.objects.link(ob)
        embers.append(ob)

    lane_objs = {lane: [warp_ob[lane], objs[f"fuzz.{lane}"]] + [objs[f"weft.{lane}.{c}"] for c in ("bone", "blood", "moss")]
                 for lane in LANES}
    dim = [warp_ob["skills"], objs["fuzz.skills"]]  # the skills warps: dim until reached
    _link(key, dim, "EXCLUDE")
    _link(pool, dim, "EXCLUDE")
    _link(rim, dim, "EXCLUDE")
    _link(fill, dim, "EXCLUDE")
    _link(top, lane_objs["facts"], "INCLUDE")
    _link(rrim, lane_objs["rules"], "INCLUDE")
    _link(skey, dim, "INCLUDE")
    _link(spool, dim, "INCLUDE")
    _link(sweep, dim, "INCLUDE")
    _link(srim, dim, "INCLUDE")

    def set_curves(name, pts, rad, heat=None):
        ob = objs[name]
        thread._set_curves(ob, np.asarray(pts) * U, np.asarray(rad) * U)
        if heat is not None:
            ob.data.attributes["lit"].data.foreach_set("value", np.asarray(heat, np.float32))

    def pose(sc, *_):
        t = (sc.frame_current + sc.frame_subframe) / 30.0
        # warps
        warp_fuzz = {}
        for lane in LANES:
            cen, m, splay, taper = warp_pose(story, lane, t)
            P = warp_plies(cen, m, splay)
            rad = np.broadcast_to(0.5 * RW * taper, P.shape[:3])
            set_curves(f"warps.{lane}", P.reshape(-1, 3), rad.reshape(-1))
            warp_fuzz[lane] = fuzz.warps(lane, cen, t)
        # wefts
        for lane in LANES:
            g = geo[lane]
            nr = len(rows[lane])
            ys = np.zeros(nr)
            ks = np.zeros(nr)
            vis = np.zeros((nr, g["m"]))
            shown = np.zeros(nr, bool)
            drawns = [None] * nr
            for idx, r in enumerate(rows[lane]):
                st = story.row_state(lane, r, t)
                if st is None:
                    ys[idx] = RACE  # parked where a row first shows, unseen
                    continue
                y, k, drawn = st
                ys[idx], ks[idx], shown[idx], drawns[idx] = y, k, True, drawn
                if drawn is None:
                    vis[idx] = 1.0
                else:
                    vis[idx] = (g["x"] >= drawn[0] - 1e-6) & (g["x"] <= drawn[1] + 1e-6)
            fw, fwr = warp_fuzz[lane]
            ff, ffr = fuzz.wefts(lane, ys, shown, drawns)
            set_curves(f"fuzz.{lane}", np.concatenate([fw, ff]).reshape(-1, 3), np.concatenate([fwr, ffr]).reshape(-1))
            off = np.zeros((nr, 1, 3))
            off[:, 0, 1] = ys
            for col in ("bone", "blood", "moss"):
                Pc, Ps = g[col]
                if col == "bone":
                    P = Ps + (Pc - Ps) * ks[:, None, None, None] + off[:, None]
                    rad = np.broadcast_to(vis[:, None, :], P.shape[:3]) * g["r"][0]
                    set_curves(f"weft.{lane}.bone", P.reshape(-1, 3), rad.reshape(-1))
                else:
                    P = Ps + (Pc - Ps) * ks[:, None, None] + off
                    rad = vis * g["r"][3 if col == "blood" else 4]
                    if col == "moss":
                        heat = [thread.strand_glow(t, commit[r]) for r in rows[lane]]
                    else:
                        heat = [DIFF_REST] * nr
                    set_curves(f"weft.{lane}.{col}", P.reshape(-1, 3), rad.reshape(-1), heat)
        # the expiring incidents
        ep = exp.pose(t)
        for col in ("bone", "blood", "moss"):
            pts, rad, heat = ep[col]
            set_curves(f"expire.{col}", pts, rad, None if col == "bone" else heat)
        fp, fr = exp.fibre_pose(t)
        set_curves("expire.fibres", fp.reshape(-1, 3), fr.reshape(-1))
        for i, ob in enumerate(embers):
            a = story.released(i, t)
            L = story.lane["incidents"]
            c = np.array([L.centre, exp.row_y(i, t), 1.2 + 0.45 * story.fray(i, t)])
            if a > 0:
                c = c + np.array([0.0, -1.0, 12.0]) * 0.4 * (1 - math.exp(-a / 0.4)) + np.array([0.0, 0.0, 3.0]) * a
            ob.location = Vector(c * U)
            ob.data.energy = EMBER_W * (0.25 * story.fray(i, t) + (2.2 * math.exp(-a / 0.4) if a > 0 else 0.0))
        # the shuttle
        sx = story.shuttle_x(t)
        shuttle.location = Vector(np.array([sx, RACE, 0.15]) * U)
        kat = np.array([sx - 6.0, RACE - 16.0, 22.0])
        kick.location = Vector(kat * U)
        kick.rotation_euler = Vector((np.array([sx, RACE, 0.0]) - kat) * U).to_track_quat("-Z", "Y").to_euler()
        anchors["shuttle"].location = shuttle.location
        L = story.lane["incidents"]
        anchors["gc"].location = Vector(np.array([L.centre, exp.row_y(1, t), 1.0]) * U)
        # the camera
        eye, look = rig.at(t)
        b = CameraRig.basis(eye, look)
        cam.matrix_world = Matrix.Translation(Vector(eye * U)) @ Matrix(
            [[*b[0], 0.0], [*b[1], 0.0], [*b[2], 0.0], [0.0, 0.0, 0.0, 1.0]])
        cam.data.dof.focus_distance = rig.depth(t, rig.focus_point(t)) * U
        # the light: the pool follows the camera's subject, from the upper left and behind it
        aim = look + np.array([0.0, -3.0, 0.0])
        at = aim + np.array(POOL_FROM)
        for ob in (pool, spool):
            ob.location = Vector(at * U)
            ob.rotation_euler = Vector((aim - at) * U).to_track_quat("-Z", "Y").to_euler()
        key.data.energy = rigl["key"][1]
        pool.data.energy = rigl["pool"][1] * (0.5 + 0.5 * story.facts_light(t))
        top.data.energy = rigl["facts_top"][1] * story.facts_light(t)
        rrim.data.energy = rigl["rules_rim"][1] * story.rules_light(t)
        sk = 0.04 + 0.96 * story.skills_light(t)
        skey.data.energy = rigl["skills_key"][1] * sk
        spool.data.energy = rigl["skills_pool"][1] * sk
        srim.data.energy = rigl["skills_rim"][1] * (0.12 + 0.88 * story.skills_light(t))
        sy, sl = story.skills_sweep(t)
        sat = np.array([S_.centre - 6.0, sy - 34.0, 22.0])
        sweep.location = Vector(sat * U)
        sweep.rotation_euler = Vector((np.array([S_.centre, sy, 0.0]) - sat) * U).to_track_quat("-Z", "Y").to_euler()
        sweep.data.energy = rigl["skills_sweep"][1] * sl

    bpy.app.handlers.frame_change_pre.append(pose)
    scene.frame_set(ctx.f0)


DIFF_REST = 0.15  # DIFF_THREAD's rest level (data/look/thread.json), checked in the tests
# the light (W), and where the key and rim stand (loom units)
LIGHT = {"key": 85.0, "pool": 310.0, "rim": 220.0, "fill": 0.0, "facts": 0.9, "rules": 90.0, "sheen": 0.0,
         "kicker": 5.0, "sweep": 260.0}
LIGHT["facts"] = 3.2
POOL_FROM, POOL_CONE = (-84.0, 46.0, 22.0), 20.0
KEY_AT = (-175.0, 95.0, 46.0)
KEY_AIM, KEY_CONE = (0.0, -22.0, 0.0), 34.0
RIM_AT = (90.0, 430.0, 20.0)
EMBER_W = 0.022  # the expiring rows' blood light (W at full)


def _link(light, objects, state: str) -> None:
    """Light linking: the light lights only `objects` (INCLUDE) or everything but them (EXCLUDE)."""
    import bpy

    c = bpy.data.collections.new(f"ll_{light.name}")
    for ob in objects:
        c.objects.link(ob)
    light.light_linking.receiver_collection = c
    for co in c.collection_objects:
        co.light_linking.link_state = state


SHEEN_AT, SHEEN_SIZE = (0.0, 210.0, 34.0), (230.0, 46.0)


def _card(name: str, at, size, level: float):
    """A soft emissive card that only reflections see (no light on anything, no shadow), facing the cloth from beyond
    the fell: its glow falls off toward its edges, so the satin's sheen and the glass's catchlight are soft-edged."""
    import bpy

    w, h = size[0] / 2 * U, size[1] / 2 * U
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-w, 0, -h), (w, 0, -h), (w, 0, h), (-w, 0, h)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="uv")
    for li, co in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[li].uv = co
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "QUADRATIC_SPHERE"
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Location"].default_value = (-0.5, -0.5, 0.0)
    mp.inputs["Scale"].default_value = (1.9, 1.9, 1.0)
    nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], grad.inputs["Vector"])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 0.985, 0.97, 1.0)
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = level
    nt.links.new(grad.outputs["Fac"], mul.inputs[0])
    nt.links.new(mul.outputs[0], em.inputs["Strength"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = np.asarray(at, float) * U
    for k in ("visible_camera", "visible_diffuse", "visible_shadow", "visible_transmission", "visible_volume_scatter"):
        setattr(ob, k, False)
    return ob


def _glass():
    """The shuttle's glass, the commit bead's (engine/bead.ts): clear satin glass, IOR 1.5, a light clear coat."""
    import bpy

    mat = bpy.data.materials.new("loom_glass")
    if mat.node_tree is None:
        mat.use_nodes = True
    b = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.98, 0.965, 0.97, 1.0)
    b.inputs["Roughness"].default_value = 0.16
    b.inputs["IOR"].default_value = 1.5
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["Coat Weight"].default_value = 0.6
    b.inputs["Coat Roughness"].default_value = 0.06
    return mat


def _spindle(name: str, material, *, scale: float = 1.0, flip: bool = False):
    """The shuttle: a glass spindle along x, SH_LEN long and SH_R round at its waist, tapering to rounded points.
    `scale` and `flip` (normals in) make its inner wall: the shuttle is a hollow glass shell with the pirn inside."""
    import bpy

    nu, nv = 72, 40
    u = np.linspace(0.0, 1.0, nu)
    r = scale * SH_R * np.sin(np.pi * u) ** 0.62
    r[0] = r[-1] = 0.0
    x = (u - 0.5) * SH_LEN * (1 - (1 - scale) * 0.6)
    a = np.linspace(0, 2 * np.pi, nv, endpoint=False)
    verts = [(x[i], r[i] * math.cos(t), r[i] * 0.86 * math.sin(t)) for i in range(nu) for t in a]
    faces = []
    for i in range(nu - 1):
        for j in range(nv):
            j1 = (j + 1) % nv
            q = (i * nv + j, i * nv + j1, (i + 1) * nv + j1, (i + 1) * nv + j)
            faces.append(q[::-1] if flip else q)
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(np.array(v) * U) for v in verts], [], faces)
    me.shade_smooth()
    me.materials.append(material)
    me.validate()
    return bpy.data.objects.new(name, me)


def _pirn(thread, bone_mat, strand_mat, parent, coll) -> list:
    """The shuttle's pirn: the diff thread wound round a slim bone core inside the glass (lib/thread.py
    diff_thread_paths round a helix), as hair curves riding the shuttle. Its strands rest at DIFF_THREAD's level."""
    turns, r_coil, r_th = 11.0, 0.62 * SH_R, 0.2
    span = 0.62 * SH_LEN
    u = np.linspace(0.0, 1.0, 900)
    swell = 0.55 + 0.45 * np.sin(np.pi * u) ** 0.5  # wound fuller in the middle, like a pirn
    th = 2 * np.pi * turns * u
    helix = np.column_stack([(u - 0.5) * span, r_coil * swell * np.cos(th), 0.86 * r_coil * swell * np.sin(th)])
    out = []
    tubes = thread.diff_thread_paths(helix, r_th, up=(1.0, 0.0, 0.0))
    for col in ("bone", "blood", "moss"):
        sel = [(P, r) for tube, P, r in tubes if tube["color"] == col]
        mat = bone_mat if col == "bone" else strand_mat[col]
        ob = thread._new_curves(f"pirn.{col}", [len(P) for P, _ in sel], np.ones(len(sel)), mat, coll, parent)
        thread._set_curves(ob, np.vstack([P for P, _ in sel]) * U, np.concatenate([np.full(len(P), r) for P, r in sel]) * U)
        if col != "bone":
            a = ob.data.attributes.new("lit", "FLOAT", "CURVE")
            a.data.foreach_set("value", np.full(len(sel), DIFF_REST, np.float32))
        out.append(ob)
    core = thread._new_curves("pirn.core", [2], np.ones(1), bone_mat, coll, parent)
    thread._set_curves(core, np.array([[-0.5 * span - 0.4, 0, 0], [0.5 * span + 0.4, 0, 0]]) * U,
                       np.full(2, 0.32 * SH_R) * U)
    out.append(core)
    return out


def _light(name, kind, power, pos, target, *, size=None, size_y=None, spot=None, soft=None, temperature=None,
           blend=0.5):
    import bpy

    data = bpy.data.lights.new(name, kind)
    data.energy = power
    if temperature:
        data.use_temperature = True
        data.temperature = temperature
    if size is not None:
        if size_y is not None:
            data.shape, data.size, data.size_y = "RECTANGLE", size, size_y
        else:
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
