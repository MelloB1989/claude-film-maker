"""Naturalness rows for the presenters' arms and hands (R7 movement director, agent-13).

Offline, numbers only: it reads an arm track (agent-01's r7/arm_track.py dump: per frame, in the actor frame x fwd,
y her right, z up, cm, the clavicle/shoulder/elbow/wrist/finger joint heads of both arms, the spine, gesture and speak
weights, the event list) and measures what makes code-made gestures read as human or robotic. The thresholds and their
sources are in NATURALNESS.md. Pure python (no numpy), so it runs on the boxes for his skeleton too.

    python3 r7/naturalness.py TRACK.json [--json OUT] [--rows]      # one take
    python3 r7/naturalness.py A.json B.json ...                       # side by side

Joint heads only: '_03' is the distal (DIP) joint, not the fingertip. 'Speaking' = speak_w > 0.5.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

FINGERS = ("index", "middle", "ring", "pinky")
SPEAK = 0.5
HIGH_APEX_CM = 16.0  # wrist over the sternum point that counts as an upper_chest-or-higher apex (APEX_Z 19, -3 slack)
TORSO_DEPTH = 11.0
STILL_CM_S = 2.5  # wrist speed under which a frame is still (a hold), not part of a movement
MIN_MOVES = 5  # wrist movements a hand needs before its path/speed fractions count  # cm from the spine_05 joint to the front of the chest/stomach (seated adult, either presenter)


# ---------- vectors ----------
def sub(a, b): return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
def add(a, b): return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
def mul(a, k): return [a[0] * k, a[1] * k, a[2] * k]
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def norm(a): return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    return [x / n for x in a] if n > 1e-9 else [0.0, 0.0, 0.0]


def perp(a, b):
    """a without its component along unit b, normalised."""
    return unit(sub(a, mul(b, dot(a, b))))


def ang(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(unit(a), unit(b))))))


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * q
    i = int(k)
    return xs[i] if i + 1 >= len(xs) else xs[i] + (xs[i + 1] - xs[i]) * (k - i)


def med(xs):
    return pct(xs, 0.5)


# ---------- per-frame anatomy ----------
def hand_frame(P, s):
    """(d fingers' direction, lat toward the index/radial side, n toward the palm) from the joint heads."""
    W, M, I, K = P["hand_" + s], P["middle_01_" + s], P["index_01_" + s], P["pinky_01_" + s]
    d = unit(sub(M, W))
    lat = perp(sub(I, K), d)
    n = cross(d, lat) if s == "r" else mul(cross(d, lat), -1.0)  # right: palm down, index medial -> d x lat = palm
    return d, lat, n


def wrist_angles(P, s):
    """(flexion +toward the palm / -extension, deviation +radial / -ulnar), deg, of the hand vs the forearm."""
    f = unit(sub(P["hand_" + s], P["lowerarm_" + s]))
    d, lat, n = hand_frame(P, s)
    n_ = perp(n, f)
    l_ = perp(perp(lat, f), n_)
    return (math.degrees(math.atan2(dot(d, n_), dot(d, f))), math.degrees(math.atan2(dot(d, l_), dot(d, f))))


def bend(a, b, lat, s):
    """signed bend from segment a to segment b about the finger's hinge (+ toward the palm), deg."""
    na = cross(unit(a), lat) if s == "r" else mul(cross(unit(a), lat), -1.0)
    bp = sub(b, mul(lat, dot(b, lat)))
    return math.degrees(math.atan2(dot(bp, na), dot(bp, unit(a))))


def finger_angles(P, s):
    """{finger: (MCP, PIP)} deg, + flexion, - hyperextension; and the thumb-index DIP-head distance."""
    _, lat, _ = hand_frame(P, s)
    W = P["hand_" + s]
    out = {}
    for fn in FINGERS:
        j1, j2, j3 = (P[f"{fn}_0{i}_{s}"] for i in (1, 2, 3))
        a, b, c = sub(j1, W), sub(j2, j1), sub(j3, j2)
        out[fn] = (bend(a, b, lat, s), bend(b, c, lat, s))
    pinch = norm(sub(P["thumb_03_" + s], P["index_03_" + s]))
    return out, pinch


def shape_class(fa, pinch):
    """one word per hand pose. claw: a finger hyperextended at a middle joint (PIP < -10) or MCP back with PIP curled
    (the intrinsic-minus claw); pinch: thumb and index DIP heads within 3.5 cm; point: index straight, 2+ others curled;
    fist; flat: every finger within +-8 deg at MCP and PIP (a mannequin hand); else relaxed."""
    if any(p < -10.0 for _, p in fa.values()) or any(m < -20.0 and p > 35.0 for m, p in fa.values()):
        return "claw"
    if pinch < 3.5:
        return "pinch"
    tot = {k: m + p for k, (m, p) in fa.items()}
    if tot["index"] < 30 and sum(1 for k in ("middle", "ring", "pinky") if tot[k] > 70) >= 2:
        return "point"
    if all(v > 110 for v in tot.values()):
        return "fist"
    if all(abs(m) <= 8 and abs(p) <= 8 for m, p in fa.values()):
        return "flat"
    return "relaxed"


# ---------- the take ----------
class Take:
    def __init__(self, d: dict, spans: list | None = None):
        self.d = d
        self.fps = float(d.get("fps", 30))
        self.F = d["frames"]
        self.dt = (self.F[1]["t"] - self.F[0]["t"]) if len(self.F) > 1 else 1 / self.fps
        self.ev = d.get("events", [])
        self.speak = [f["speak_w"] > SPEAK for f in self.F]
        if spans:  # only these frame ranges count (a shot): speaking frames, events by apex, movements by start
            self.inside = [any(a <= f["f"] <= b for a, b in spans) for f in self.F]
            self.speak = [x and y for x, y in zip(self.speak, self.inside)]
            self.ev = [e for e in self.ev if self.inside[self.apex(e)]]
        else:
            self.inside = [True] * len(self.F)
        self.wa = {s: [wrist_angles(f["p"], s) for f in self.F] for s in "lr"}
        self.fa = {s: [finger_angles(f["p"], s) for f in self.F] for s in "lr"}
        self.wr = {s: [f["p"]["hand_" + s] for f in self.F] for s in "lr"}
        self.v = {s: self._speed(self.wr[s]) for s in "lr"}

    def _speed(self, xs):
        n, dt = len(xs), self.dt
        v = [0.0] * n
        for i in range(n):
            a, b = max(0, i - 1), min(n - 1, i + 1)
            v[i] = norm(sub(xs[b], xs[a])) / ((b - a) * dt) if b > a else 0.0
        return v

    def idx(self, t):
        return max(0, min(len(self.F) - 1, int(round(t / self.dt))))

    def hands_of(self, e):
        return "lr" if e["hand"] == "both" else e["hand"]

    def apex(self, e):
        """mid-hold frame of an event."""
        return self.idx(e["stroke"] + 0.5 * min(e["hold"], 0.4))

    # --- rows ---
    def wrist(self):
        out = {}
        for s in "lr":
            fe = [self.wa[s][i][0] for i in range(len(self.F)) if self.speak[i]]
            dv = [self.wa[s][i][1] for i in range(len(self.F)) if self.speak[i]]
            out[s] = {"flexext_abs_p90": pct([abs(x) for x in fe], 0.9), "flexext_p50": med(fe),
                      "flex_max": max(fe), "ext_max": -min(fe),
                      "ulnar_p95": pct([-x for x in dv], 0.95), "radial_p95": pct(dv, 0.95), "dev_p50": med(dv)}
        return out

    def forearm(self):
        out = {s: {"elev": [], "elbow": [], "abd": [], "yaw": [], "hum": [], "drop": [], "flexn": [], "hi": [], "lo": [],
                   "abdo": []} for s in "lr"}
        for e in self.ev:
            if e["kind"] == "rest":
                continue
            i = self.apex(e)
            P = self.F[i]["p"]
            for s in self.hands_of(e):
                f = sub(P["hand_" + s], P["lowerarm_" + s])
                u = sub(P["lowerarm_" + s], P["upperarm_" + s])
                out[s]["elev"].append(math.degrees(math.asin(max(-1, min(1, f[2] / norm(f))))))
                out[s]["elbow"].append(180.0 - ang(u, f))  # the elbow's inside angle: 180 straight
                sg = 1.0 if s == "r" else -1.0  # out to that hand's side
                out[s]["abd"].append(math.degrees(math.atan2(sg * u[1], -u[2])))  # upper arm off vertical, frontal
                out[s]["yaw"].append(math.degrees(math.atan2(-sg * f[1], f[0])))  # forearm heading: + toward midline
                out[s]["hum"].append(math.degrees(math.acos(max(-1, min(1, -u[2] / norm(u))))))  # 0 = hanging
                out[s]["drop"].append(P["upperarm_" + s][2] - P["lowerarm_" + s][2])
                out[s]["flexn"].append(math.degrees(math.atan2(u[0], -u[2])))  # upper arm forward off vertical, sagittal
                # abduction = the upper arm out of the sagittal plane (pure flexion reads 0)
                out[s]["abdo"].append(math.degrees(math.asin(max(-1, min(1, sg * u[1] / norm(u))))))
                # the apex class (the orchestrator, 08 Nov): wrist at/above upper_chest (19 cm over the sternum
                # point, shoulders' mid height - 14; 3 cm slack for the reach cap pulling the wrist in) gets 60 deg
                stp = (P["upperarm_l"][2] + P["upperarm_r"][2]) / 2 - 14.0
                hum = out[s]["hum"][-1]
                (out[s]["hi"] if P["hand_" + s][2] - stp >= HIGH_APEX_CM else out[s]["lo"]).append(hum)
        r = {}
        for s in "lr":
            el = out[s]["elev"]
            r[s] = {"n": len(el), "elev_p50": med(el), "elev_p25": pct(el, 0.25),
                    "flat_frac": sum(1 for x in el if x < 10.0) / len(el) if el else float("nan"),
                    "elbow_inside_p50": med(out[s]["elbow"]), "abd_p50": med(out[s]["abd"]),
                    "forearm_in_p50": med(out[s]["yaw"]), "humerus_elev_p50": med(out[s]["hum"]),
                    "humerus_elev_p90": pct(out[s]["hum"], 0.9), "elbow_drop_p50": med(out[s]["drop"]),
                    "flexion_p50": med(out[s]["flexn"]), "abduction_p50": med(out[s]["abdo"]),
                    "abduction_p90": pct(out[s]["abdo"], 0.9),
                    "humerus_lo_p50": med(out[s]["lo"]), "humerus_hi_p50": med(out[s]["hi"]),
                    "humerus_lo_p90": pct(out[s]["lo"], 0.9), "humerus_hi_p90": pct(out[s]["hi"], 0.9),
                    "high_frac": len(out[s]["hi"]) / max(1, len(out[s]["hi"]) + len(out[s]["lo"]))}
        for s in "lr":  # the resting / between-gesture upper arm
            hum = [math.degrees(math.acos(max(-1, min(1, -(f["p"]["lowerarm_" + s][2] - f["p"]["upperarm_" + s][2]) /
                                                     norm(sub(f["p"]["lowerarm_" + s], f["p"]["upperarm_" + s]))))))
                   for i, f in enumerate(self.F) if self.inside[i] and f["gesture_w"][s] < 0.1]
            r[s]["humerus_rest_p50"] = med(hum)
        return r

    def shapes(self):
        per, bad, cnt = [], 0, {}
        for e in self.ev:
            i = self.apex(e)
            for s in self.hands_of(e):
                fa, pn = self.fa[s][i]
                c = shape_class(fa, pn)
                cnt[c] = cnt.get(c, 0) + 1
                wrong = c in ("claw", "pinch") and e["kind"] != "pinch" or (c == "flat")
                bad += wrong
                if wrong:
                    per.append({"f": i, "hand": s, "kind": e["kind"], "line": e.get("line", ""), "shape": c})
        frames = {s: [shape_class(*self.fa[s][i]) for i in range(len(self.F)) if self.speak[i]] for s in "lr"}
        claw = {s: sum(1 for c in frames[s] if c == "claw") / max(1, len(frames[s])) for s in "lr"}
        flat = {s: sum(1 for c in frames[s] if c == "flat") / max(1, len(frames[s])) for s in "lr"}
        # the relaxed cascade: at rest-like frames the pinky curls at least as much as the index
        casc = {}
        for s in "lr":
            ok = n = 0
            for i in range(len(self.F)):
                if self.F[i]["gesture_w"][s] < 0.2:
                    fa, _ = self.fa[s][i]
                    n += 1
                    ok += (fa["pinky"][0] + fa["pinky"][1]) >= (fa["index"][0] + fa["index"][1]) - 2.0
            casc[s] = ok / max(1, n)
        return {"wrong_strokes": bad, "classes": cnt, "claw_frac": claw, "flat_frac": flat, "cascade_frac": casc,
                "wrong": per[:20]}

    def body(self):
        """the wrist's distance in front of the torso (spine_05 + TORSO_DEPTH): strokes and 'stuck to the body'."""
        r = {}
        for s in "lr":
            near, n, ap = 0, 0, []
            for i, f in enumerate(self.F):
                P = f["p"]
                fwd = P["hand_" + s][0] - (P["spine_05"][0] + TORSO_DEPTH)
                lat = abs(P["hand_" + s][1] - P["spine_05"][1])
                if self.speak[i]:
                    n += 1
                    near += fwd < 8.0 and lat < 16.0
            for e in self.ev:
                if s in self.hands_of(e):
                    P = self.F[self.apex(e)]["p"]
                    ap.append(P["hand_" + s][0] - (P["spine_05"][0] + TORSO_DEPTH))
            r[s] = {"near_frac": near / max(1, n), "stroke_fwd_p50": med(ap), "stroke_fwd_p10": pct(ap, 0.1)}
        return r

    def segments(self, s):
        """wrist movements between speed minima: (i0, i1) with a chord >= 8 cm and a peak >= 20 cm/s."""
        v, n = self.v[s], len(self.v[s])
        mins = [0] + [i for i in range(1, n - 1) if v[i] <= v[i - 1] and v[i] < v[i + 1]] + [n - 1]
        segs = []
        for a, b in zip(mins, mins[1:]):
            pk = max(v[a:b + 1])
            if pk < 20.0 or norm(sub(self.wr[s][b], self.wr[s][a])) < 8.0:
                continue
            if max(v[a], v[b]) > 0.35 * pk:  # not a movement of its own (a wobble inside one)
                continue
            # trim still frames off both ends (< STILL_CM_S): a dead-still hold is not part of the movement, and
            # with the overshoot off (agent-01 7652457b) the next speed minimum sat at the hold's far end
            while a < b and v[a] < STILL_CM_S and v[a + 1] < STILL_CM_S:
                a += 1
            while b > a and v[b] < STILL_CM_S and v[b - 1] < STILL_CM_S:
                b -= 1
            if self.inside[a] and b - a >= 3:
                segs.append((a, b))
        return segs

    def kinematics(self):
        r = {}
        for s in "lr":
            curv, ratio, peaks = [], [], []
            for a, b in self.segments(s):
                X = self.wr[s][a:b + 1]
                ch = sub(X[-1], X[0])
                L = norm(ch)
                u = unit(ch)
                dev = max(norm(sub(sub(x, X[0]), mul(u, dot(sub(x, X[0]), u)))) for x in X)
                curv.append(dev / L)
                vv = self.v[s][a:b + 1]
                path = sum(norm(sub(X[k + 1], X[k])) for k in range(len(X) - 1))
                mean = path / ((b - a) * self.dt)
                ratio.append(max(vv) / mean)
                peaks.append(max(vv))
            nan = float("nan")
            r[s] = {"n": len(curv), "curv_p50": med(curv),
                    # a hand with fewer than MIN_MOVES movements has no say in the fraction rows (3 small echo
                    # moves of her left decided both rows on 0085e4d7)
                    "straight_frac": sum(1 for c in curv if c < 0.03) / len(curv) if len(curv) >= MIN_MOVES else nan,
                    "peak_mean_p50": med(ratio),
                    "bell_frac": sum(1 for x in ratio if 1.6 <= x <= 2.3) / len(ratio) if len(ratio) >= MIN_MOVES else nan,
                    "v_peak_p50": med(peaks), "v_peak_max": max(peaks or [0.0])}
        return r

    def _angspeed(self, vecs):
        n, dt = len(vecs), self.dt
        w = [0.0] * n
        for i in range(n):
            a, b = max(0, i - 1), min(n - 1, i + 1)
            w[i] = ang(vecs[a], vecs[b]) / ((b - a) * dt) if b > a else 0.0
        return w

    def _onset(self, w, a, b, frac=0.2):
        """sub-frame time where w first climbs past frac of its peak in [a, b]."""
        pk = max(w[a:b + 1])
        if pk < 1e-6:
            return None
        th = frac * pk
        for i in range(a, b + 1):
            if w[i] >= th:
                if i == a:
                    return a * self.dt
                return (i - 1 + (th - w[i - 1]) / max(1e-9, w[i] - w[i - 1])) * self.dt
        return None

    def lag(self):
        """proximal-to-distal onset: upper arm -> forearm -> hand (absolute orientation) -> fingers, per movement."""
        r = {}
        for s in "lr":
            up = self._angspeed([sub(f["p"]["lowerarm_" + s], f["p"]["upperarm_" + s]) for f in self.F])
            fo = self._angspeed([sub(f["p"]["hand_" + s], f["p"]["lowerarm_" + s]) for f in self.F])
            hd = self._angspeed([hand_frame(f["p"], s)[2] for f in self.F])
            fing = []
            for i in range(len(self.F)):
                fa = self.fa[s][i][0]
                fing.append([fa[k][j] for k in FINGERS for j in (0, 1)])
            fw = [0.0] * len(fing)
            for i in range(1, len(fing) - 1):
                fw[i] = sum(abs(x - y) for x, y in zip(fing[i + 1], fing[i - 1])) / (2 * self.dt * 8)
            lags, lag_f, order = [], [], 0
            segs = self.segments(s)
            for a, b in segs:
                a0 = max(0, a - 3)
                o = [self._onset(w, a0, b) for w in (up, fo, hd)]
                of = self._onset(fw, a0, b)
                if None in o:
                    continue
                lags.append(1000 * (o[2] - o[0]))
                if of is not None:
                    lag_f.append(1000 * (of - o[0]))
                order += o[0] <= o[1] + 1e-6 <= o[2] + 2e-6
            r[s] = {"n": len(lags), "hand_minus_upper_ms_p50": med(lags), "fingers_minus_upper_ms_p50": med(lag_f),
                    "ordered_frac": order / max(1, len(lags))}
        return r

    def asym(self):
        """two-hand events: the left wrist's velocity vs the right's mirrored (y flipped); 1.0 = a mirror copy."""
        cors, dons, amp = [], [], []
        for e in self.ev:
            if e["hand"] != "both":
                continue
            a, b = self.idx(e["prep"] - 0.1), self.idx(e["stroke"] + e["hold"] + 0.4)
            if b - a < 6:
                continue
            vr = [sub(self.wr["r"][i + 1], self.wr["r"][i]) for i in range(a, b)]
            vl = [sub(self.wr["l"][i + 1], self.wr["l"][i]) for i in range(a, b)]
            vl = [[x[0], -x[1], x[2]] for x in vl]
            num = sum(dot(x, y) for x, y in zip(vr, vl))
            den = math.sqrt(sum(dot(x, x) for x in vr) * sum(dot(y, y) for y in vl))
            if den < 1e-9:
                continue
            cors.append(num / den)
            on = [self._onset(self.v[s], a, b) for s in "lr"]
            if None not in on:
                dons.append(1000 * abs(on[0] - on[1]))
            pr = sum(norm(x) for x in vr)
            pl = sum(norm(y) for y in vl)
            amp.append(min(pr, pl) / max(pr, pl, 1e-9))
        return {"n": len(cors), "mirror_corr_p50": med(cors), "mirror_corr_max": max(cors or [float("nan")]),
                "onset_diff_ms_p50": med(dons), "amp_ratio_p50": med(amp)}

    def frozen(self):
        """speaking time whose fingers (8 MCP/PIP angles, both hands) move under 2 deg/s for >= 0.5 s."""
        r = {}
        for s in "lr":
            fing = [[self.fa[s][i][0][k][j] for k in FINGERS for j in (0, 1)] for i in range(len(self.F))]
            n = len(fing)
            w = [0.0] * n
            for i in range(1, n - 1):
                w[i] = sum(abs(x - y) for x, y in zip(fing[i + 1], fing[i - 1])) / (2 * self.dt * 8)
            still = [w[i] < 2.0 and self.speak[i] for i in range(n)]
            runs, k = [], 0
            for x in still + [False]:
                if x:
                    k += 1
                else:
                    if k:
                        runs.append(k * self.dt)
                    k = 0
            tot = sum(x for x in runs if x >= 0.5)
            spk = sum(self.speak) * self.dt
            r[s] = {"frozen_frac": tot / max(1e-9, spk), "frozen_max_s": max(runs or [0.0])}
        return r

    def holds(self):
        """wrist speed while she speaks OUTSIDE every movement (holds and rests), per hand: a live hold drifts
        0.5-1 cm/s (breath, micro-motion); 0 is a frozen, placed hand."""
        r = {}
        for s in "lr":
            inmove = [False] * len(self.F)
            for a, b in self.segments(s):
                for i in range(a, b + 1):
                    inmove[i] = True
            v = [self.v[s][i] for i in range(len(self.F)) if self.speak[i] and not inmove[i]]
            r[s] = {"n": len(v), "p10": pct(v, 0.1), "p50": med(v),
                    "frozen_frac": sum(1 for x in v if x < 0.1) / max(1, len(v))}
        return r

    def torso(self):
        """report only: does the chest/head move with the strokes? correlation of the spine_05 and head speeds with
        the right wrist's, and their mean speeds over speaking frames."""
        out = {}
        for b in ("spine_05", "head"):
            v = self._speed([f["p"][b] for f in self.F])
            idx = [i for i in range(len(self.F)) if self.speak[i]]
            a = [self.v["r"][i] for i in idx]
            c = [v[i] for i in idx]
            ma, mc = sum(a) / max(1, len(a)), sum(c) / max(1, len(c))
            num = sum((x - ma) * (y - mc) for x, y in zip(a, c))
            den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mc) ** 2 for y in c)) or float("nan")
            out[b] = {"corr_with_r_wrist": num / den, "mean_cm_s": mc}
        return out

    def travel(self):
        """report only: wrist travel per speaking second per hand (a dead hand reads as a prop)."""
        out = {}
        for s in "lr":
            d = sum(norm(sub(self.wr[s][i + 1], self.wr[s][i])) for i in range(len(self.F) - 1) if self.speak[i])
            out[s] = d / max(1e-9, sum(self.speak) * self.dt)
        out["l_over_r"] = out["l"] / max(1e-9, out["r"])
        return out

    def report(self):
        return {"wrist": self.wrist(), "forearm": self.forearm(), "shape": self.shapes(), "body": self.body(),
                "kin": self.kinematics(), "lag": self.lag(), "asym": self.asym(), "fingers": self.frozen(),
                "torso": self.torso(), "travel": self.travel(), "holds": self.holds()}


# ---------- the gate rows ----------
# key: (value from the report, op, line, unit, what). Each row takes the worse hand where both apply.
def _worst(rep, path, worse):
    top = rep[path[0]]
    if "l" in top:  # {hand: {key: v}}
        a, b = top["l"], top["r"]
        for k in path[1:]:
            a, b = a[k], b[k]
    else:  # {key: {hand: v}}
        a, b = top[path[1]]["l"], top[path[1]]["r"]
    vals = [x for x in (a, b) if x == x]
    return worse(vals) if vals else float("nan")


ROWS = {
    "move.humerus_elev_stroke_deg": (lambda r: r["forearm"]["r"]["humerus_lo_p50"], "<=", 45.0, "deg",
                                     "median upper-arm elevation off hanging (shoulder->elbow vs straight down) at "
                                     "the right hand's stroke apexes below upper_chest"),
    "move.humerus_elev_high_deg": (lambda r: r["forearm"]["r"]["humerus_hi_p50"], "<=", 60.0, "deg",
                                   "the same at apexes at/above upper_chest (wrist >= 16 cm over the sternum point; the "
                                   "orchestrator's 60 deg, 08 Nov)"),
    "move.upperarm_abduction_deg": (lambda r: _worst(r, ("forearm", "abduction_p50"), max), "<=", 35.0, "deg",
                                    "median upper-arm abduction (out of the sagittal plane) at stroke apexes, worse "
                                    "hand: the elevation must be mostly flexion, toward the camera"),
    "move.humerus_elev_rest_deg": (lambda r: _worst(r, ("forearm", "humerus_rest_p50"), max), "<=", 30.0, "deg",
                                   "median upper-arm elevation while that hand is at rest (gesture_w < 0.1), worse "
                                   "hand: resting elbows hang"),
    "move.forearm_elev_deg": (lambda r: r["forearm"]["r"]["elev_p50"], ">=", 15.0, "deg",
                              "median forearm elevation (elbow->wrist above horizontal) at the right hand's stroke "
                              "apexes: horizontal = 'typing in the air'"),
    "move.wrist_flexext_p90_deg": (lambda r: _worst(r, ("wrist", "flexext_abs_p90"), max), "<=", 25.0, "deg",
                                   "p90 over speaking frames of |wrist flexion/extension| (3rd metacarpal vs the "
                                   "forearm), worse hand"),
    "move.wrist_ulnar_p95_deg": (lambda r: _worst(r, ("wrist", "ulnar_p95"), max), "<=", 25.0, "deg",
                                 "p95 over speaking frames of ulnar deviation, worse hand"),
    "move.wrist_radial_p95_deg": (lambda r: _worst(r, ("wrist", "radial_p95"), max), "<=", 15.0, "deg",
                                  "p95 over speaking frames of radial deviation, worse hand"),
    "move.shape_wrong_strokes": (lambda r: r["shape"]["wrong_strokes"], "==", 0, "count",
                                 "stroke apexes whose hand is a claw, a pinch outside a 'pinch' gesture, or flat"),
    "move.shape_claw_frac": (lambda r: _worst(r, ("shape", "claw_frac"), max), "<=", 0.02, "fraction",
                             "speaking frames with a claw hand (a finger bent back at a middle joint), worse hand"),
    "move.path_straight_frac": (lambda r: _worst(r, ("kin", "straight_frac"), max), "<=", 0.30, "fraction",
                                "wrist movements (>= 8 cm) whose path strays < 3 % of its chord: straight lines"),
    "move.vel_bell_frac": (lambda r: _worst(r, ("kin", "bell_frac"), min), ">=", 0.60, "fraction",
                           "wrist movements with a peak/mean speed of 1.6-2.3 (minimum jerk 1.875), worse hand"),
    "move.lag_hand_ms": (lambda r: r["lag"]["r"]["hand_minus_upper_ms_p50"], ">=", 30.0, "ms",
                         "median onset of the hand's rotation after the upper arm's, per movement (right hand): "
                         "proximal leads, distal follows"),
    "move.two_hand_amp_ratio": (lambda r: r["asym"]["amp_ratio_p50"], ">=", 0.5, "ratio",
                                "two-hand strokes: median wrist travel of the lesser hand over the greater's (a "
                                "two-hand gesture with one hand parked reads as one hand and a prop)"),
    "move.hold_min_speed": (lambda r: _worst(r, ("holds", "p10"), min), ">=", 0.3, "cm/s",
                            "p10 of the wrist speed while speaking outside every movement (holds, rests), worse hand: "
                            "a live hold drifts (the orchestrator, 08 Nov); 0 = frozen"),
    "move.mirror_corr_p50": (lambda r: r["asym"]["mirror_corr_p50"], "<=", 0.95, "corr",
                             "GUARD: two-hand strokes, median correlation of the left wrist velocity with the right's "
                             "mirrored (1.0 = a mirror copy)"),
    "move.fingers_frozen_frac": (lambda r: _worst(r, ("fingers", "frozen_frac"), max), "<=", 0.15, "fraction",
                                 "GUARD: speaking time inside >= 0.5 s runs with the fingers under 2 deg/s, worse hand"),
}


def rows(rep):
    out = {}
    for k, (fn, op, line, unit_, what) in ROWS.items():
        v = fn(rep)
        ok = {"<=": v <= line, ">=": v >= line, "==": v == line}[op] if v == v else None  # None: nothing to measure
        out[k] = {"value": round(v, 3) if isinstance(v, float) else v, "op": op, "line": line, "unit": unit_,
                  "pass": ok if ok is None else bool(ok), "what": what}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("tracks", nargs="+")
    ap.add_argument("--json")
    ap.add_argument("--span", action="append", default=[], help="frames A-B (repeatable): only these count")
    ap.add_argument("--full", action="store_true", help="print the full report, not only the rows")
    a = ap.parse_args(argv)
    res = {}
    for p in a.tracks:
        spans = [tuple(int(x) for x in sp.split("-")) for sp in a.span]
        rep = Take(json.loads(Path(p).read_text()), spans or None).report()
        res[Path(p).stem] = {"rows": rows(rep), "report": rep}
    names = list(res)
    w = max(len(k) for k in ROWS) + 2
    print("row".ljust(w) + "line".ljust(10) + "".join(n[:16].ljust(18) for n in names))
    for k in ROWS:
        r0 = res[names[0]]["rows"][k]
        cells = "".join((f"{res[n]['rows'][k]['value']}" + {True: " ok", False: " FAIL", None: " n/a"}[res[n]["rows"][k]["pass"]]).ljust(18)
                        for n in names)
        print(k.ljust(w) + f"{r0['op']}{r0['line']}".ljust(10) + cells)
    if a.full:
        print(json.dumps({n: res[n]["report"] for n in names}, indent=1, default=str))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    sys.exit(main())
