"""MediaPipe -> her MetaHuman, the hybrid retarget (docs/MOCAP_PILOT.md §7; the orchestrator's design, 08 Nov):

ARMS: MediaPipe's pose WORLD landmarks give stable arm DIRECTIONS (no depth flips) but no reliable scale. So per frame
the upper arm and forearm directions, taken in one fixed body basis (shoulders, hips, nose; the camera is locked off),
are laid from HER shoulder with HER limb lengths. That gives a wrist goal relative to her sternum point (gesturekit's
HandPose.off), plus the palm's pronation and the wrist's extension from the hand landmarks' palm plane.
- Those goals become per-frame gesturekit events, so gesturekit's own fitting runs on them unchanged: the elevation
  caps (_fit_poses.fit), face-avoid (face_fit) and the mic rule (_mic_plan).
- The corrections (fitted - raw) are spread over time (a short dilation, then a Gaussian), so a correction eases in
  and out instead of jumping per frame.
- The stream then plays through a style hook (`hand`), so her arm IK, the elbow swivel/clearance, the desk rest and
  contact, and the left-hand mic limits all apply as for her generated performance.

HANDS: the 3D finger angles are NOT used (bone-length CV 0.3, hyperextension, spread noise). Each finger gives one
robust number, its closure: the angle between the palm direction (wrist -> its MCP) and the finger's chord
(MCP -> tip). From it:
- each frame's closures are classified into agent-08's anatomical named shapes (handshape.SHAPES: open, list,
  relaxed, point, pinch, soft_fist; rest at the desk), with a pinch test (thumb tip to index tip);
- the label is median-filtered (a dwell), and the blend weights are smoothed one-hots;
- one bounded curl scalar is added (the mean closure's offset from the chosen shape, +-8 %);
- the fingers trail the wrist in agent-08's cascade (gesture_style.LAG_S).
handshape's synergy and agent-08's finger_post (spread) do the rest.

TORSO: the turn and the shoulders' lift come from the shoulder line; the lean from the trunk's pitch. Each is taken
relative to the clip's median and clamped small.

OUTPUT: gesturekit.build's own doc (perform.py's WRITE format: {length_s, fps, n_keys, const, keyed}, her skeleton,
seatkit's seat and legs) with its summary (clearance, mic, face, desk, hands in frame), and the arm track
(gesturekit.track_doc) for agent-13's naturalness rows.

    python3 -m filmtools.mocap.mp2mh LANDMARKS.json --kit <repo>/films/host-studio/explainers --out DIR \
        [--who her] [--fps 24] [--cam CAM_MCU] [--t0 0] [--t1 10.0] [--lift 0]

Pure Python (no numpy), like gesturekit: the same code can run on a box. The kit's modules (seatkit, gesturekit,
handshape, gesture_style, perform) come from --kit at run time. They are on the r7 branches; this was written
against agent-08's r7-hands 928407cb.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

# MediaPipe pose indices
NOSE, SH_L, SH_R, EL_L, EL_R, WR_L, WR_R, HIP_L, HIP_R = 0, 11, 12, 13, 14, 15, 16, 23, 24
ARM_IDX = {"l": (SH_L, EL_L, WR_L), "r": (SH_R, EL_R, WR_R)}
# MediaPipe hand indices: (MCP, PIP, DIP, tip) per finger; the thumb (CMC, MCP, IP, tip)
HAND_IDX = {"thumb": (1, 2, 3, 4), "index": (5, 6, 7, 8), "middle": (9, 10, 11, 12), "ring": (13, 14, 15, 16),
            "pinky": (17, 18, 19, 20)}
FING4 = ("index", "middle", "ring", "pinky")
HAND_SRC = ("crop", "up2x", "full")  # the pilot's passes, best first (the 4x wrist crop found the most)

CLOSE_LO, CLOSE_HI = 12.0, 150.0  # deg (palm dir, finger chord) at closure 0 and 1
CANDIDATES = ("open", "list", "relaxed", "point", "pinch", "soft_fist")
SHAPE_SIGMA = 14.0   # % closure: the fit's width
PINCH_TIP = 0.45     # thumb tip to index tip under this x palm width, with a half-closed index: a pinch
DWELL_F = 9          # frames: the label's median filter (0.38 s at 24 fps)
BLEND_SIGMA_F = 5.0  # frames: the one-hots' Gaussian (a ~0.3 s blend between named shapes; 2.5 read as finger snaps,
#                      agent-13's finger_snap_per_min 12 against a line of 2)
EXT_K, EXT_MAX = 0.4, 25.0  # the wrist's extension from the palm plane, scaled and capped (MediaPipe's hand plane
#   over-reads it: p90 50-65 deg raw against agent-13's wrist_flexext_p90 line of 25)
HAND_ROT_LAG_S = 0.06  # s the hand's turn (pronation, extension) trails the forearm (proximal to distal; lag_hand_ms)
CURL_MAX = 8.0       # % the bounded curl scalar
ARM_SIGMA_F = 1.2    # frames: zero-phase smoothing of the arm directions (offline: no lag)
FEAT_SIGMA_F = 2.0   # frames: closures, palm normal, knuckle line
CORR_DILATE_F = 3    # frames each side: a correction starts this early and holds this long
CORR_SIGMA_F = 2.5
FLOOR_DILATE_F = 6   # frames each side: the fingers' raise plateau (a Gaussian on it then keeps its centre value)
DESK_PASSES = 3      # finger-dip passes (each adds the residual dip)
TURN_MAX, LIFT_MAX, LEAN_MAX = 8.0, 5.0, 6.0  # deg: the torso's turn, the shoulders' lift, the lean around the base
LOWHAND_Z = (6.0, 20.0)  # cm over the desk top: the swivel's bust line from the desk rest's (under) to the full (over)
FLOOR_MARGIN = 1.2  # cm over seatkit's desk.wrist line (desk top + forearm_clear - 0.3) for a hovering wrist goal
REST_NEAR_CM = 4.0   # a hand is AT REST when its wrist goal is within this of the desk floor,
REST_STILL_CM_S = 10.0  # slower than this,
REST_PALM_DEG = 40.0    # palm down within this,
REST_HOLD_S = 0.3       # for at least this long (else it is gesturing low: the pilot's performer works just over the
#   desk, and her hands' shapes and turns are the performance)


# ---------------------------------------------------------------------------------------------- vectors (pure)
def sub(a, b): return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
def add(a, b): return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
def mul(a, k): return [a[0] * k, a[1] * k, a[2] * k]
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def norm(a): return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    return [x / n for x in a] if n > 1e-12 else [0.0, 0.0, 0.0]


def ortho(a, d):
    """a without its component along unit d, normalised."""
    return unit(sub(a, mul(d, dot(a, d))))


def angle(a, b) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(unit(a), unit(b))))))


def mid(a, b):
    return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2]


def smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------------------------------------- series (pure)
def fill_gaps(xs: list) -> list:
    """None entries linearly interpolated (ends held): a hand missed for a few frames."""
    n = len(xs)
    idx = [i for i, x in enumerate(xs) if x is not None]
    if not idx:
        return xs
    out = list(xs)
    for i in range(n):
        if out[i] is not None:
            continue
        lo = max((j for j in idx if j < i), default=None)
        hi = min((j for j in idx if j > i), default=None)
        if lo is None:
            out[i] = xs[hi]
        elif hi is None:
            out[i] = xs[lo]
        else:
            u = (i - lo) / (hi - lo)
            a, b = xs[lo], xs[hi]
            out[i] = [a[k] + (b[k] - a[k]) * u for k in range(len(a))] if isinstance(a, list) else a + (b - a) * u
    return out


def gauss(xs: list, sigma: float) -> list:
    """Zero-phase Gaussian smoothing of a list of floats or of equal-length float lists (edges renormalised)."""
    if sigma <= 0 or len(xs) < 2:
        return list(xs)
    r = int(math.ceil(3 * sigma))
    w = [math.exp(-0.5 * (k / sigma) ** 2) for k in range(-r, r + 1)]
    vec = isinstance(xs[0], list)
    out = []
    for i in range(len(xs)):
        acc, tot = ([0.0] * len(xs[0]) if vec else 0.0), 0.0
        for k in range(-r, r + 1):
            j = i + k
            if 0 <= j < len(xs):
                wk = w[k + r]
                tot += wk
                if vec:
                    acc = [acc[m] + wk * xs[j][m] for m in range(len(acc))]
                else:
                    acc += wk * xs[j]
        out.append([a / tot for a in acc] if vec else acc / tot)
    return out


def dilate_signed(xs: list, r: int) -> list:
    """Per component, the value of largest magnitude within +-r frames (a correction starts early, holds late)."""
    out = []
    for i in range(len(xs)):
        win = xs[max(0, i - r):i + r + 1]
        out.append([max((v[m] for v in win), key=abs) for m in range(len(xs[i]))])
    return out


def median_labels(labels: list, k: int) -> list:
    """The most common label in a centred window of k frames (ties: the centre's own)."""
    h = k // 2
    out = []
    for i in range(len(labels)):
        win = labels[max(0, i - h):i + h + 1]
        best = max(set(win), key=lambda x: (win.count(x), x == labels[i]))
        out.append(best)
    return out


def unwrap(deg: list) -> list:
    out = [deg[0]]
    for x in deg[1:]:
        d = (x - out[-1] + 180.0) % 360.0 - 180.0
        out.append(out[-1] + d)
    return out


# ---------------------------------------------------------------------------------------------- MediaPipe -> actor
def body_basis(frames: list) -> tuple:
    """(fwd, right, up) unit vectors in MediaPipe world coordinates, from the clip's median shoulders, hips and nose:
    up = hips -> shoulders, right = her left shoulder -> her right one (off up), fwd = the side her nose is on. The
    handedness of MediaPipe's axes is not assumed: projecting onto these three gives the actor frame's (fwd, right,
    up) as physical directions."""
    def med_pt(k):
        cols = list(zip(*[f["pose_world"][k][:3] for f in frames]))
        return [sorted(c)[len(c) // 2] for c in cols]
    sl, sr, hl, hr, no = (med_pt(k) for k in (SH_L, SH_R, HIP_L, HIP_R, NOSE))
    up = unit(sub(mid(sl, sr), mid(hl, hr)))
    right = ortho(sub(sr, sl), up)
    fwd = unit(cross(right, up))
    if dot(sub(no, mid(sl, sr)), fwd) < 0:
        fwd = mul(fwd, -1.0)
    return fwd, right, up


def to_actor(v, basis) -> list:
    """A MediaPipe world vector -> actor axes (x fwd, y her right, z up)."""
    f, r, u = basis
    return [dot(v, f), dot(v, r), dot(v, u)]


def hand_of(frame: dict, side: str):
    """The best hand detection of her side ('L'/'R', assigned by the pose wrist in the pilot), or None."""
    for src in HAND_SRC:
        h = (frame.get(src) or {}).get(side)
        if h and h.get("world"):
            return h
    return None


def closures(Hw: list) -> dict:
    """{finger: closure 0..1} from 21 hand points (any frame: only directions and ratios are used). The angle between
    the palm direction (wrist -> the finger's MCP) and its chord (MCP -> tip); the thumb from its tip's distance to
    the index MCP over the palm width (0 out, 1 across the palm)."""
    w = Hw[0]
    out = {}
    for f in FING4:
        m, _, _, tip = HAND_IDX[f]
        a = angle(sub(Hw[m], w), sub(Hw[tip], Hw[m]))
        out[f] = max(-0.06, min(1.08, (a - CLOSE_LO) / (CLOSE_HI - CLOSE_LO)))
    pw = norm(sub(Hw[5], Hw[17])) or 1e-6
    out["thumb"] = max(0.0, min(1.0, 1.4 - norm(sub(Hw[4], Hw[5])) / pw))
    out["pinch_d"] = norm(sub(Hw[4], Hw[8])) / pw
    return out


def classify(c: dict, shapes: dict) -> tuple:
    """(label, {shape: fit weight}) for one frame's closures against the named shapes (closures in %)."""
    obs = [100.0 * c[f] for f in FING4]
    d = {}
    for k in CANDIDATES:
        s = shapes[k]
        d[k] = math.sqrt(sum((obs[i] - float(s[f])) ** 2 for i, f in enumerate(FING4)) / 4.0)
    if c.get("pinch_d", 9.0) < PINCH_TIP and 0.2 <= c["index"] <= 0.75:
        d["pinch"] *= 0.5  # the thumb meets the index: a pinch beats a similar relaxed curl
    else:
        d["pinch"] *= 1.5
    w = {k: math.exp(-0.5 * (v / SHAPE_SIGMA) ** 2) for k, v in d.items()}
    tot = sum(w.values()) or 1.0
    w = {k: v / tot for k, v in w.items()}
    return min(d, key=d.get), w


LIMB_MAX_Q = 0.97  # the quantile of a limb's projected image length taken as its true length (in the picture plane)


def lift_limb(img_a, img_b, world_a, world_b, basis, L_px: float, W: int, H: int) -> list:
    """One limb's unit direction, actor axes, from the PICTURE (locked-off, near-orthographic front camera) and its
    length: the lateral and vertical components are the image's, over the limb's own longest projection L_px; the depth
    component is what the unit length leaves, its sign from the world landmarks. MediaPipe's world z is a regression
    with the wrong slope (the pilot clip: forearms read 10-35 deg down where the picture shows them level, toward the
    lens), the picture is a measurement."""
    dx, dy = (img_b[0] - img_a[0]) * W, (img_b[1] - img_a[1]) * H
    f, r, u = basis
    # the picture's axes in actor terms: image x is the camera's right = her LEFT (she faces the lens), image y down
    lat = -dx / L_px
    vert = -dy / L_px
    rest = 1.0 - lat * lat - vert * vert
    wv = to_actor(sub(world_b, world_a), basis)
    fwd = math.copysign(math.sqrt(max(0.0, rest)), wv[0] if abs(wv[0]) > 1e-6 else 1.0)
    return unit([fwd, lat, vert])


def arm_series(frames: list, basis, W: int = 1280, H: int = 720) -> dict:
    """{side: {"u1": [...], "u2": [...]}} the upper arm and forearm unit directions, actor axes, smoothed (lift_limb).
    A limb's true length in pixels is its longest projection over the clip, the larger of the two sides (a forearm
    that always points at the lens never shows its length: the pilot's left, 88 px against the right's 138)."""
    def proj(i, j):
        px = sorted(math.hypot((f["pose_img"][j][0] - f["pose_img"][i][0]) * W,
                               (f["pose_img"][j][1] - f["pose_img"][i][1]) * H) for f in frames)
        return px[min(len(px) - 1, int(LIMB_MAX_Q * len(px)))]
    lens = {"u1": max(proj(SH_L, EL_L), proj(SH_R, EL_R)), "u2": max(proj(EL_L, WR_L), proj(EL_R, WR_R))}
    out = {}
    for s, (a, b, c) in ARM_IDX.items():
        u1, u2 = [], []
        for f in frames:
            I, P = f["pose_img"], f["pose_world"]
            u1.append(lift_limb(I[a], I[b], P[a][:3], P[b][:3], basis, lens["u1"], W, H))
            u2.append(lift_limb(I[b], I[c], P[b][:3], P[c][:3], basis, lens["u2"], W, H))
        out[s] = {"u1": [unit(v) for v in gauss(u1, ARM_SIGMA_F)], "u2": [unit(v) for v in gauss(u2, ARM_SIGMA_F)],
                  "len_px": lens}
    return out


def hand_series(frames: list, basis) -> dict:
    """{side: {"close": [{finger: c}], "palm": [n], "knuckle": [k], "hdir": [d], "found": [bool]}} actor axes."""
    out = {}
    for s, side in (("l", "L"), ("r", "R")):
        cl, palm, kn, hd, found = [], [], [], [], []
        for f in frames:
            h = hand_of(f, side)
            if h is None:
                cl.append(None), palm.append(None), kn.append(None), hd.append(None), found.append(False)
                continue
            Hw = [to_actor(p[:3], basis) for p in h["world"]]
            c = closures(Hw)
            cl.append([c[k] for k in (*FING4, "thumb", "pinch_d")])
            d = unit(sub(Hw[9], Hw[0]))                     # wrist -> middle MCP
            k_ = ortho(sub(Hw[17], Hw[5]), d)               # index MCP -> pinky MCP, off the hand's line
            # the palm side: right hand d x (index side) ... from anatomy in a right-handed actor frame
            thumb_side = mul(k_, -1.0)
            n = unit(cross(d, thumb_side)) if s == "r" else unit(cross(thumb_side, d))
            palm.append(n), kn.append(k_), hd.append(d), found.append(True)
        cl = gauss(fill_gaps(cl), FEAT_SIGMA_F)
        out[s] = {"close": [dict(zip((*FING4, "thumb", "pinch_d"), v)) for v in cl],
                  "palm": [unit(v) for v in gauss(fill_gaps(palm), FEAT_SIGMA_F)],
                  "knuckle": [unit(v) for v in gauss(fill_gaps(kn), FEAT_SIGMA_F)],
                  "hdir": [unit(v) for v in gauss(fill_gaps(hd), FEAT_SIGMA_F)], "found": found}
    return out


def pron_ext(fa, knuckle, hdir, palm, s: str) -> tuple:
    """(pronation, extension) deg in gesturekit's convention (hand_rot_p): across = flat cos(p) - up_ sin(p), where
    across is the knuckle line (index -> pinky), flat is the hand's own side off the fingers' line, up_ is world up off
    it. So p = atan2(-across.up_, across.flat): 0 palm down, 90 thumb up. Extension: the hand's line off the forearm's,
    + toward the back of the hand."""
    side = [0.0, 1.0, 0.0] if s == "r" else [0.0, -1.0, 0.0]
    fingers = unit(fa)
    flat = ortho(side, fingers)
    up_ = ortho([0.0, 0.0, 1.0], fingers) if abs(fingers[2]) < 0.98 else ortho([-1.0, 0.0, 0.0], fingers)
    a = ortho(knuckle, fingers)
    p = math.degrees(math.atan2(-dot(a, up_), dot(a, flat)))
    back = ortho(mul(palm, -1.0), fingers)       # the back of the hand, off the forearm's line
    lat = unit(cross(fingers, back))              # the wrist's flexion axis
    h = ortho(hdir, lat) if norm(lat) > 0.5 else unit(hdir)
    e = math.degrees(math.atan2(dot(h, back), dot(h, fingers)))
    return p, e


# ---------------------------------------------------------------------------------------------- the kit side
def load_kit(kit: str):
    sys.path.insert(0, str(Path(kit).resolve()))
    import gesture_style as GS  # noqa: E402
    import gesturekit as G  # noqa: E402
    import handshape as HS  # noqa: E402
    import perform as PF  # noqa: E402
    import seatkit as S  # noqa: E402
    return G, GS, HS, PF, S


class Mocap:
    """The clip in actor terms, independent of the performer: arms, hands, torso, labels."""

    def __init__(self, doc: dict, HS, t0: float = 0.0, t1: float | None = None):
        fps = float(doc["fps"])
        frames = [f for f in doc["frames"] if f["t_ms"] / 1000.0 >= t0 - 1e-6
                  and (t1 is None or f["t_ms"] / 1000.0 <= t1 + 1e-6)]
        self.fps, self.t0, self.n = fps, t0, len(frames)
        self.basis = body_basis(frames)
        self.arms = arm_series(frames, self.basis, int(doc.get("width", 1280)), int(doc.get("height", 720)))
        self.hands = hand_series(frames, self.basis)
        self.found = {s: sum(self.hands[s]["found"]) for s in "lr"}
        self._torso(frames)
        self._labels(HS)

    def _torso(self, frames):
        B = self.basis
        turn, lean, lift = [], [], {"l": [], "r": []}
        for f in frames:
            P = f["pose_world"]
            sl, sr = to_actor(P[SH_L][:3], B), to_actor(P[SH_R][:3], B)
            hm = to_actor(mid(P[HIP_L][:3], P[HIP_R][:3]), B)
            v = sub(sr, sl)
            turn.append(-math.degrees(math.atan2(v[0], v[1])))  # + toward her right: her right shoulder back
            tr = sub(mid(sl, sr), hm)
            lean.append(math.degrees(math.atan2(tr[0], tr[2])))  # + forward
            half = max(1e-6, norm(v) / 2.0)
            for s, p in (("l", sl), ("r", sr)):
                lift[s].append(math.degrees(math.atan2(p[2] - mid(sl, sr)[2], half)))
        def rel(xs, lo, hi):
            m = sorted(xs)[len(xs) // 2]
            return [max(lo, min(hi, x - m)) for x in gauss(xs, 3.0)]
        self.turn = rel(turn, -TURN_MAX, TURN_MAX)
        self.lean = rel(lean, -LEAN_MAX, LEAN_MAX)
        self.lift = {s: [max(0.0, min(LIFT_MAX, x)) for x in rel(v, -LIFT_MAX, LIFT_MAX)] for s, v in lift.items()}

    def _labels(self, HS):
        self.labels, self.shape_w, self.curl = {}, {}, {}
        for s in "lr":
            labs, curls = [], []
            for c in self.hands[s]["close"]:
                lab, _ = classify(c, HS.SHAPES)
                labs.append(lab)
            labs = median_labels(labs, DWELL_F)
            onehots = [{k: 1.0 if k == lab else 0.0 for k in CANDIDATES} for lab in labs]
            sm = gauss([[o[k] for k in CANDIDATES] for o in onehots], BLEND_SIGMA_F)
            ws = [{k: v for k, v in zip(CANDIDATES, row) if v > 0.02} for row in sm]
            for c, lab in zip(self.hands[s]["close"], labs):
                obs = sum(100.0 * c[f] for f in FING4) / 4.0
                ref = sum(float(HS.SHAPES[lab][f]) for f in FING4) / 4.0
                curls.append(max(-CURL_MAX, min(CURL_MAX, obs - ref)))
            self.labels[s], self.shape_w[s], self.curl[s] = labs, ws, gauss(curls, 4.0)

    def idx(self, t: float) -> tuple:
        x = max(0.0, min(self.n - 1.0, (t - self.t0) * self.fps))
        i = min(self.n - 2, int(x)) if self.n > 1 else 0
        return i, x - i


def shape_at(m: Mocap, HS, GS, s: str, t: float) -> dict:
    """The blended named shape at t: closures + thumb + opposition + spread, each finger lagging the wrist by agent-08's
    cascade (LAG_S); a bounded curl added to the four fingers."""
    out = {}
    lag = getattr(GS, "LAG_S", {})
    spread = getattr(GS, "SHAPE_SPREAD", {})
    for key in (*FING4, "thumb", "_opp", "_spread"):
        lk = lag.get(key, lag.get("index", 0.0)) if key in (*FING4, "thumb") else lag.get("middle", 0.0)
        i, u = m.idx(t - lk)
        val = 0.0
        for j, wj in ((i, 1.0 - u), (min(m.n - 1, i + 1), u)):
            w = m.shape_w[s][j]
            tot = sum(w.values()) or 1.0
            for k, wk in w.items():
                v = float(spread.get(k, 3.0)) if key == "_spread" else float(HS.full(k)[key])
                val += wj * wk / tot * v
            if key in FING4:
                val += wj * m.curl[s][j]
        out[key] = val
    return out


class MocapHook:
    """The style hook gesturekit calls (gesturekit.STYLE_HOOK): the whole hand track from the mocap. agent-08's
    finger_post (the spread) is delegated to gesture_style."""
    ROT_LAG_S = 0.0  # the take's own timing

    def __init__(self, m: Mocap, G, GS, HS, perf_geom: dict, lift: float = 0.0):
        self.m, self.G, self.GS, self.HS = m, G, GS, HS
        self.geom, self.lift = perf_geom, lift
        self.raw = {s: self._raw_side(s) for s in "lr"}  # per mocap frame: (HandPose, w)
        self.final = None
        self.extra_z = {s_: [0.0] * m.n for s_ in "lr"}  # build()'s pass 1: the raise that keeps the fingers over the desk
        self.log = {"desk_clamped": {"l": 0, "r": 0}, "corr_cm": {"l": [], "r": []}, "handover": [], "unresolved": 0}

    def _raw_side(self, s: str) -> list:
        G, m, g = self.G, self.m, self.geom
        sg = 1.0 if s == "r" else -1.0
        sh, st_pt = g["shoulder"][s], g["st_pt"]
        l1, l2 = g["A"][s]
        floor = g["desk_top"] + g["rest_wrist"]
        out, prons, wrs = [], [], []
        for i in range(m.n):
            u1, u2 = m.arms[s]["u1"][i], m.arms[s]["u2"][i]
            wr = add(add(sh, mul(u1, l1)), mul(u2, l2))
            wrs.append(wr)
            off = [wr[0] - st_pt[0], sg * (wr[1] - st_pt[1]), wr[2] - st_pt[2]]
            H = m.hands[s]
            p, e = pron_ext(u2, H["knuckle"][i], H["hdir"][i], H["palm"][i], s)
            prons.append(p)
            out.append([off, max(-15.0, min(EXT_MAX, EXT_K * e))])
        prons = gauss(unwrap(prons), 1.5)
        exts = gauss([x[1] for x in out], 1.5)
        # at rest: low, still, palm down, held (REST_*); everything else gestures (w 1)
        hold = max(1, int(round(REST_HOLD_S * m.fps)))
        cand = []
        for i, wr in enumerate(wrs):
            v = norm(sub(wrs[min(m.n - 1, i + 1)], wrs[max(0, i - 1)])) * m.fps / 2.0
            cand.append(wr[2] - floor < REST_NEAR_CM and v < REST_STILL_CM_S and abs(prons[i]) < REST_PALM_DEG)
        rest = [False] * m.n
        i = 0
        while i < m.n:
            if cand[i]:
                j = i
                while j < m.n and cand[j]:
                    j += 1
                if j - i >= hold:
                    rest[i:j] = [True] * (j - i)
                i = j
            else:
                i += 1
        ws = gauss([0.0 if r else 1.0 for r in rest], 3.0)
        lift = self.lift
        return [(G.HandPose((o[0][0], o[0][1], o[0][2] + lift * ws[i]), pron=prons[i], ext=exts[i], shape="relaxed"),
                 ws[i]) for i, o in enumerate(out)]

    # the events gesturekit fits (its own _fit_poses / _mic_plan), one per hand per mocap frame where the hand is up
    def events(self) -> list:
        G, out = self.G, []
        dt = 1.0 / self.m.fps
        for s in "lr":
            for i, (hp, w) in enumerate(self.raw[s]):
                if w < 0.05:
                    continue
                t = self.m.t0 + i * dt
                e = G.Event(hand=s, prep=t - dt, stroke=t, hold=0.0, pose_r=hp, pose_l=hp if s == "l" else None,
                            kind="mocap", retract=dt, detail=self.m.labels[s][i])  # agent-13's rows key on it
                e._mocap = (s, i)
                out.append(e)
        return out

    def _finalise(self, perf) -> None:
        """Fitted goals -> smoothed corrections on the raw stream (once, after gesturekit's _fit_poses ran). Two
        channels: the fits (face, mic) as a smoothed delta; the desk (the wrist floor and the fingers' raise from
        build()'s passes) as a smoothed per-frame FLOOR the wrist never goes under."""
        g = self.geom
        z_min = g["desk_top"] + g["rest_wrist"] - g["st_pt"][2]  # the wrist never under its desk-rest height
        fitted = {"l": {}, "r": {}}
        self.log = {"desk_clamped": {"l": 0, "r": 0}, "corr_cm": {"l": [], "r": []}, "handover": [], "unresolved": 0}
        for e in perf.plan.events:
            s, i = getattr(e, "_mocap", (None, None))
            if s is None:
                continue
            if e.hand != s:  # the mic rule handed the stroke over: keep the raw goal, count it
                self.log["handover"].append({"t": round(e.stroke, 2), "side": s})
                continue
            p = e.pose_l if s == "l" else e.pose_r
            fitted[s][i] = p.off
        self.log["unresolved"] = sum(1 for x in getattr(perf, "mic_log", []) if x.get("unresolved"))
        self.final = {}
        for s in "lr":
            raw = self.raw[s]
            deltas = [sub(list(fitted[s].get(i, hp.off)), list(hp.off)) for i, (hp, w) in enumerate(raw)]
            sm = gauss(dilate_signed(deltas, CORR_DILATE_F), CORR_SIGMA_F)
            extra = gauss([v[0] for v in dilate_signed([[x] for x in self.extra_z[s]], FLOOR_DILATE_F)], CORR_SIGMA_F)
            fin = []
            for i, (hp, w) in enumerate(raw):
                off = add(list(hp.off), sm[i])
                if off[2] < z_min:
                    off[2] = z_min
                    self.log["desk_clamped"][s] += 1
                off[2] += extra[i]  # the fingers' raise, on top of the corrected height
                self.log["corr_cm"][s].append(norm(sub(off, list(hp.off))))
                fin.append((replace(hp, off=tuple(off)), w))
            self.final[s] = fin

    def at(self, perf, s: str, t: float) -> tuple:
        if self.final is None:
            self._finalise(perf)
        i, u = self.m.idx(t)
        j = min(self.m.n - 1, i + 1)
        (a, wa), (b, wb) = self.final[s][i], self.final[s][j]
        off = tuple(a.off[k] + (b.off[k] - a.off[k]) * u for k in range(3))
        w = wa + (wb - wa) * u
        i2, u2 = self.m.idx(t - HAND_ROT_LAG_S)  # the hand's turn trails the forearm
        a2, b2 = self.final[s][i2][0], self.final[s][min(self.m.n - 1, i2 + 1)][0]
        pron = a2.pron + (b2.pron - a2.pron) * u2
        ext = a2.ext + (b2.ext - a2.ext) * u2
        sh = shape_at(self.m, self.HS, self.GS, s, t)
        rest = self.HS.full("rest")  # at the desk: toward agent-08's rest shape (palm down) by (1 - w)
        sh = {k: sh.get(k, 0.0) * w + float(rest.get(k, sh.get(k, 0.0))) * (1.0 - w) if k in rest else sh[k]
              for k in sh}
        hp = self.G.HandPose(off, pron=pron * w + self.G.REST_PRON * (1.0 - w),
                             ext=ext * w + self.G.REST_EXT * (1.0 - w), shape=sh)
        return hp, w

    # --- the hook API ---
    def hand(self, perf, s: str, t: float) -> tuple:
        hp, w = self.at(perf, s, t)
        big = w if abs(hp.off[1]) > 15.0 or hp.off[2] > 12.0 else 0.5 * w
        return hp, big

    def _tracks(self, perf) -> dict:
        hook = self

        class _T:
            def __init__(self, s):
                self.s = s

            def at(self, t):
                hp, w = hook.at(perf, self.s, t)
                return hp, {"mocap": w}
        return {s: _T(s) for s in "lr"}

    def weights(self, perf, t: float) -> dict:
        return {}  # the torso is the MocapPerformer's (turn and lift from the shoulders)

    def finger_post(self, perf, s, hp, W) -> None:
        self.GS.finger_post(perf, s, hp, W)

    def report(self, perf, length_s: float) -> dict:
        rows = {}
        for s in "lr":
            c = self.log["corr_cm"][s]
            if c:
                rows[f"mocap.correction_cm_{s}"] = {"p50": round(sorted(c)[len(c) // 2], 1),
                                                    "max": round(max(c), 1),
                                                    "frames_over_3cm": sum(1 for x in c if x > 3.0)}
            rows[f"mocap.desk_clamped_frames_{s}"] = self.log["desk_clamped"][s]
            ez = self.extra_z[s]
            rows[f"mocap.finger_desk_raise_cm_{s}"] = {"max": round(max(ez), 1), "frames": sum(1 for x in ez if x > 0)}
            labs = self.m.labels[s]
            rows[f"mocap.shapes_{s}"] = {k: labs.count(k) for k in CANDIDATES if labs.count(k)}
            rows[f"mocap.hand_found_frames_{s}"] = f"{self.m.found[s]}/{self.m.n}"
        rows["mocap.mic_handovers"] = len(self.log["handover"])
        rows["mocap.mic_unresolved"] = self.log["unresolved"]
        rows["mocap.face_fits"] = len(getattr(perf, "face_log", []))
        rows["mocap.elevation_fits"] = len(getattr(perf, "fit_log", []))
        return {"rows": rows, "issues": []}


def performer_class(G, m: Mocap, caps: bool = False):
    class MocapPerformer(G.Performer):
        """gesturekit's Performer with the torso's turn and the shoulders' lift from the take (the clip's own,
        relative to its median, clamped). caps=False: no upper-arm elevation caps (_fit_poses' 40/45/60 deg lines are
        style lines for GENERATED strokes; a real performer's open gestures lift the elbows to 50-78 deg, and the caps
        pulled her hands in by up to 22 cm). The face fit, the mic rule, the clearance swivel and the desk stay."""
        if not caps:
            ELEV_REST = ELEV_STROKE = ELEV_HIGH = 179.0

        def swivel(self, s, sh, wrist, l1, l2, pole, W, ws):
            """The elbow's swivel with the bust line by the HAND'S HEIGHT: a hand working just over the desk (the take's
            low gestures) uses the desk rest's line (the arm beside the chest, REST_BUST_WANT), one at the chest the full
            CLEAR_WANT. A low wrist near her midline has no elbow that clears 3.8 cm except one swung up and out (94 cm,
            near the shoulder: wings)."""
            z = self.actor(wrist)[2] - self.set.desk_top
            k = smoothstep((z - LOWHAND_Z[0]) / (LOWHAND_Z[1] - LOWHAND_Z[0]))
            old = self._wg.get(s)
            if old is not None:
                self._wg[s] = min(old, k)
            try:
                return super().swivel(s, sh, wrist, l1, l2, pole, W, ws)
            finally:
                if old is not None:
                    self._wg[s] = old

        def torso(self, t: float) -> tuple:
            i, u = m.idx(t)
            j = min(m.n - 1, i + 1)
            turn = m.turn[i] + (m.turn[j] - m.turn[i]) * u
            lift = {s: m.lift[s][i] + (m.lift[s][j] - m.lift[s][i]) * u for s in "lr"}
            return turn, lift
    return MocapPerformer


def plan_for(G, m: Mocap, hook: MocapHook, length_s: float, cam: str, base_lean: float = 4.0):
    lean = [(m.t0 + i / m.fps, base_lean + m.lean[i]) for i in range(0, m.n, max(1, int(m.fps // 4)))]
    return G.Plan(events=hook.events() if hook else [], speaking=[(0.0, length_s)], lean=lean, base_lean=base_lean,
                  on_cam=[[0.0, length_s + 1.0, cam]] if cam else [])


@contextlib.contextmanager
def patched(G, **kv):
    old = {k: getattr(G, k) for k in kv}
    for k, v in kv.items():
        setattr(G, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(G, k, v)


def geometry(G, S, sk, st, sy, m: Mocap, cam: str) -> dict:
    """Her shoulders, sternum point (gesturekit's: shoulders' midpoint + 8 fwd - 14 up), limb lengths, at the rest."""
    se, _ = S.autotune(sk, st, sy)
    with patched(G, STYLE_HOOK=None):
        perf = G.Performer(sk, st, se.sy, plan_for(G, m, None, 1.0, cam))
        F = perf.fk(perf.pose(0.0))
    shp = {s: perf.actor(F["upperarm_" + s][0]) for s in "lr"}
    st_pt = [(shp["l"][0] + shp["r"][0]) / 2 + 8.0, (shp["l"][1] + shp["r"][1]) / 2,
             (shp["l"][2] + shp["r"][2]) / 2 - 14.0]
    return {"shoulder": shp, "st_pt": st_pt, "A": dict(perf.A), "desk_top": st.desk_top,
            "rest_wrist": max(getattr(G.Performer, "REST_WRIST", 3.2), se.sy.forearm_clear + FLOOR_MARGIN)}


DESK_FINGER_MARGIN = 0.8  # cm: a finger joint or tip over the desk (x past its near edge) stays this far above its top


def finger_dips(G, perf, m: Mocap, const: dict, desk_top: float, desk_near: float) -> dict:
    """{side: [cm]} per mocap frame: how far that hand's finger joints (_02, _03) and tips dip under the desk top +
    DESK_FINGER_MARGIN where they are over it (seatkit's desk.finger looks at the joints; the tips are added)."""
    out = {s: [] for s in "lr"}
    for i in range(m.n):
        t = m.t0 + i / m.fps
        F = perf.fk({**const, **perf.pose(t)})
        A = {b: perf.actor(v[0]) for b, v in F.items()}
        tips = G.finger_tips(perf, F)
        for s in "lr":
            pts = [A[b] for b in A if b.endswith("_" + s) and (b[:-2].endswith("_02") or b[:-2].endswith("_03"))
                   and b.split("_")[0] in ("thumb", "index", "middle", "ring", "pinky")]
            pts += [p for k, p in tips.items() if k.endswith("_" + s)]
            z = min([p[2] for p in pts if p[0] >= desk_near] or [1e9])
            out[s].append(max(0.0, desk_top + DESK_FINGER_MARGIN - z))
    return out


def build(landmarks: dict, kit: str, who: str = "her", fps: int = 24, cam: str = "CAM_MCU", t0: float = 0.0,
          t1: float | None = None, track_out: str | None = None, lift: float = 0.0, caps: bool = False) -> tuple:
    """(doc, summary, mocap) for perform.py's WRITE: gesturekit.build with the mocap plan, performer and hook. Two
    passes: the first finds where the fingers would go into the desk (finger_dips), the second raises those wrist goals
    by that much, as a smoothed correction like the others."""
    G, GS, HS, PF, S = load_kit(kit)
    m = Mocap(landmarks, HS, t0, t1)
    length_s = round((m.n - 1) / m.fps, 4)
    data = json.loads((Path(kit) / "skeletons" / f"{who}_body_read.json").read_text())
    st = PF.set_of(who)
    sy = replace(PF.STYLE[who], **PF.PERFORM_STYLE)
    sk = S.Skeleton.from_read(data)
    geom = geometry(G, S, sk, st, sy, m, cam)
    hook = MocapHook(m, G, GS, HS, geom, lift)
    Perf = performer_class(G, m, caps)
    se, _ = S.autotune(sk, st, sy)
    const = {b: data["local"][b] for b in data["tracks"] if b in data["local"]}
    for _ in range(DESK_PASSES):  # the fingers' raise, the residual added each pass
        hook.final = None
        with patched(G, STYLE_HOOK=hook):
            perf1 = Perf(sk, st, se.sy, plan_for(G, m, hook, length_s, cam))
            dips = finger_dips(G, perf1, m, const, st.desk_top, st.desk_near)
        if max(max(v) for v in dips.values()) < 0.05:
            break
        hook.extra_z = {s: [a + b for a, b in zip(hook.extra_z[s], dips[s])] for s in "lr"}
    hook.final = None
    plan = plan_for(G, m, hook, length_s, cam)
    with patched(G, STYLE_HOOK=hook, Performer=Perf, plan_from_sheet=lambda *a, **k: plan):  # pass 2
        doc, summary = G.build(data, st, sy, {}, {}, [], length_s, fps, on_cam=plan.on_cam, track_out=track_out)
    summary["mocap"] = {"lift_cm": lift, "caps": caps,
                        "rest_frames": {s: sum(1 for _, w in hook.raw[s] if w < 0.5) for s in "lr"},
                        "frames": m.n, "fps_in": m.fps, "t0": t0, "length_s": length_s, "basis": m.basis,
                        "geom": {k: v for k, v in geom.items() if k != "A"}}
    return doc, summary, m


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("landmarks")
    ap.add_argument("--kit", required=True, help="films/host-studio/explainers of an r7 checkout")
    ap.add_argument("--out", required=True)
    ap.add_argument("--who", default="her")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--cam", default="CAM_MCU")
    ap.add_argument("--t0", type=float, default=0.0)
    ap.add_argument("--t1", type=float)
    ap.add_argument("--name", default="mocap")
    ap.add_argument("--caps", action="store_true", help="keep gesturekit's upper-arm elevation caps (style lines)")
    ap.add_argument("--lift", type=float, default=0.0, help="cm added to a gesturing wrist's height (a framing "
                    "variant: the faithful take is 0)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    lm = json.loads(Path(a.landmarks).read_text())
    track = out / f"{a.name}.arm_track.json"
    doc, summary, m = build(lm, a.kit, a.who, a.fps, a.cam, a.t0, a.t1, track_out=str(track), lift=a.lift, caps=a.caps)
    (out / f"{a.name}.doc.json").write_text(json.dumps(doc))
    (out / f"{a.name}.summary.json").write_text(json.dumps(summary, indent=1, default=str))
    labels = {"fps": m.fps, "t0": m.t0, "labels": m.labels, "weights": m.shape_w}
    (out / f"{a.name}.shapes.json").write_text(json.dumps(labels))
    print(json.dumps({"doc": str(out / f"{a.name}.doc.json"), "keys": doc["n_keys"], "pass": summary["pass"],
                      "n_issues": summary["n_issues"], "issues": summary["issues"][:8],
                      "rows": summary["rows"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
