"""The explainers' heads (round 6, agent-04): one presenter seated, talking to the lens for ~60 s, intercut with
graphics. What makes a to-camera head read as a person and not a puppet, and the numbers that say so.

Rules (round 5's, kept): the head never moves with a blink (blink_head still, the solve's head replaced), no blink on a
gaze move (the "turn blinks"), no periodic motion. On top of them, for a talking head:
- small nods on the stressed words (perfkit's beat nods on 1 in 2), a slow drift and breathing in every hold;
- the eyes on the lens with fixational micro-saccades (perfkit's "lens" scan);
- a few thinking glances off the lens and back: just before a new phrase, 8-13 deg to one side (people favour one),
  mostly up a little, 0.6-1.1 s, the head following ~30 %; about one per 12 s of screen time, never across a cut.

    python head.py plan CUE.json > face_args.json      perf.face's arguments (the driver adds anim/out/wav/signs)
    python head.py plan audio/whatsapp/cues.json --edl edl/whatsapp.json --who him   (agent-11's files as the cue)
    python head.py sample CUE.json --seq /Game/.../SEQ --label Host_Op [--out DIR]   (on the editor: two ops)
    python head.py judge CUE.json --head head.json --eyes eyes.json [--gate numbers.json]

CUE.json (agent-11's cue sheet, the bits this needs): {"fps": 24, "start": <master frame of t=0>, "length_s",
"words": [{"w", "t0", "t1"}] (s, the VO), "on_cam": [[t0, t1, "<camera label>"], ...] (s: the presenter on screen),
"think": [t, ...] (optional: phrase starts the script marks as a thinking beat; else they are picked),
"cams": {"<camera label>": [yaw, pitch]} (optional: each lens's direction from the seated eyes, deg, the
character's frame; glances are offsets off the active lens)}.
Engine-free: plan and judge run anywhere; sample needs the bridge (filmtools.unreal.client).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import numpy as np

SEED = {"him": 61, "her": 62}
PRESET = "presenter_calm"
HEAD_STYLE = {"micro_deg": 0.4, "breath_deg": 0.2, "breath_hz": 0.21, "speech_gain": 0.8, "gain": 0.9,
              # r6: no roll until a roll test on the archetype face (the shared signs file writes roll on HeadPitch,
              # and her K2c "yourself" tilt measured as a 5 deg chin dip): no rest tilt, no lean into the glances
              "rest_roll_deg": 0.0, "lean": 0.0}
ROLL_OK = False  # set once agent-01's roll test passes: a seeded rest tilt of up to 1.2 deg comes back
GLANCE_EVERY_S = (9.0, 16.0)  # the gap between thinking glances (screen time)
GLANCE_YAW = (8.0, 13.0)      # deg off the lens, to one side
GLANCE_DUR = (0.6, 1.1)       # s off the lens
GLANCE_LEAD = 0.35            # s before the phrase's first word: the look away comes as the thought forms
GLANCE_HEAD = 0.3             # the head's share of a glance
CUT_MARGIN = 0.6              # s a glance keeps from either end of an on-camera span
BLINK_GUARD = (0.15, 0.45)    # s before / after a gaze move with no blink (no turn blinks)

# The judge's lines (to-camera, seated; screen time only). Sources: blinks-head-stability.md; fixational saccades
# ~1-2/s at 0.1-1 deg (Martinez-Conde 2004); a talking head's 1/f drift 0.3-0.6 deg.
LINES = {
    "head.blink_nod_deg": ("<=", 0.6),
    "head.blink_locked_deg": ("<=", 0.3),
    "head.buzz_rms_deg": ("<=", 0.08),
    "head.drift_deg": ("range", (0.15, 1.5)),     # median 2 s spread of the slow head (alive, not wandering)
    "head.frozen_s": ("<=", 1.5),                 # longest hold under 0.25 deg/s on the smoothed head
    "head.nods_per_min": ("range", (3.0, 24.0)),  # pitch dips >= 0.7 deg
    "eyes.on_lens_share": (">=", 0.75),           # eyes within 3 deg of the lens
    "eyes.saccades_per_s": ("range", (0.4, 3.0)),  # on-lens steps 0.1-1.5 deg in a frame
    "eyes.glances_per_min": ("range", (2.0, 8.0)),  # off the lens > 5 deg for 0.25-2.5 s, then back
    "blinks.per_min": ("range", (10.0, 30.0)),
}


REAIM_MIN_DEG = 3.0   # a camera change smaller than this keeps the gaze where it is
REAIM_HEAD_CUT = 0.3  # the head's share of a re-aim on a direct cut (the eyes do the rest)
CUT_NO_BLINK_F = 6  # frames after a cut with no blink (agent-11's edit rule)


def cue_from_edl(cues: dict, edl: dict, start: int = 0) -> dict:
    """This module's cue from agent-11's audio/<film>/cues.json and edl/<film>.json: every word of every line (s),
    and the presenter's screen time = the "pres" and "panel" shots (each its own span: a camera change is a cut)."""
    fps = cues["fps"]
    words = [{"w": w["w"], "t0": w["start"], "t1": w["end"]} for ln in cues["lines"] for w in ln["words"]]
    on_cam = [[s["f0"] / fps, s["f1"] / fps, s.get("camera", "")] for s in edl["shots"] if s["kind"] in ("pres", "panel")]
    return {"fps": fps, "start": start, "length_s": cues["duration"], "words": words, "on_cam": on_cam,
            "film": cues.get("film", ""), "presenter": cues.get("presenter", "")}


def load_cue(path: str, edl: str | None = None, start: int = 0) -> dict:
    d = json.loads(Path(path).read_text())
    return cue_from_edl(d, json.loads(Path(edl).read_text()), start) if edl else d


# --------------------------------------------------------------------------------------------------------- plan

def phrase_starts(words: list, gap: float = 0.3) -> list:
    """Times (s) of the words after a pause of `gap` s or more (and the first)."""
    out = []
    for i, w in enumerate(words):
        if i == 0 or w["t0"] - words[i - 1]["t1"] >= gap:
            out.append(float(w["t0"]))
    return out


def _span_of(t: float, on_cam: list):
    for s in on_cam:
        if s[0] <= t <= s[1]:
            return s
    return None


def glances(cue: dict, who: str) -> list:
    """The thinking glances: [{"t" (away), "back", "yaw", "pitch"}], seeded per presenter."""
    rng = random.Random(SEED[who])
    side = 1.0 if rng.random() < 0.5 else -1.0  # the side this person favours
    on_cam = cue["on_cam"]
    cands = [float(t) for t in cue.get("think") or phrase_starts(cue["words"])]
    out, last = [], -1e9
    want = rng.uniform(*GLANCE_EVERY_S) * 0.6  # the first one comes a little sooner
    for t in sorted(cands):
        dur = rng.uniform(*GLANCE_DUR)
        sp = _span_of(t, on_cam) or _span_of(t - GLANCE_LEAD, on_cam)
        if sp is None:
            continue
        # just before the phrase, or as it starts when a cut is right before it (agent-11's think beats sit ~0.4 s
        # after a cut): never within CUT_MARGIN of either end of the shot
        away = max(t - GLANCE_LEAD, sp[0] + CUT_MARGIN)
        dur = min(dur, sp[1] - CUT_MARGIN - away)
        if dur < GLANCE_DUR[0] - 0.1:
            continue
        if not cue.get("think") and away - last < want:
            continue
        s = side if rng.random() < 0.7 else -side
        if len(sp) > 2 and str(sp[2]).endswith("_L"):  # a panel shot (framed left, the graphic screen right = the
            s = 1.0                                     # presenter's left): the glance goes toward the panel
        up = rng.random() < 0.65
        out.append({"t": round(away, 3), "back": round(away + dur, 3), "yaw": round(s * rng.uniform(*GLANCE_YAW), 1),
                    "pitch": round(rng.uniform(3.0, 6.0) if up else -rng.uniform(2.0, 4.0), 1)})
        last, want = away, rng.uniform(*GLANCE_EVERY_S)
    return out


def lens_dir(cue: dict, cam: str) -> tuple:
    """The lens's direction (yaw, pitch; deg, the character's frame) from the seated eyes: cue["cams"][cam], or
    straight ahead when the cue has none."""
    y, p = (cue.get("cams") or {}).get(cam, (0.0, 0.0))
    return float(y), float(p)


def reaims(cue: dict) -> list:
    """Where the lens changes direction (> REAIM_MIN_DEG): [{"t", "yaw", "pitch", "head", "on_screen"}]. After a
    graphics shot the eyes and head move in the middle of it, off screen; on a direct presenter-to-presenter cut the
    eyes jump on the cut frame and the head follows only REAIM_HEAD_CUT of it (a big head swing just after a cut
    reads as caught looking at the wrong camera)."""
    out, spans = [], cue["on_cam"]
    for i in range(1, len(spans)):
        a, b = lens_dir(cue, spans[i - 1][2] if len(spans[i - 1]) > 2 else ""), \
            lens_dir(cue, spans[i][2] if len(spans[i]) > 2 else "")
        if math.hypot(b[0] - a[0], b[1] - a[1]) <= REAIM_MIN_DEG:
            continue
        gap = spans[i][0] - spans[i - 1][1]
        direct = gap < 1.0 / cue["fps"]
        t = spans[i][0] if direct else spans[i - 1][1] + gap / 2.0
        out.append({"t": round(t, 3), "yaw": b[0], "pitch": b[1], "head": REAIM_HEAD_CUT if direct else 1.0,
                    "on_screen": direct, "deg": round(math.hypot(b[0] - a[0], b[1] - a[1]), 1)})
    return out


def plan(cue: dict, who: str) -> dict:
    """perf.face's arguments for the presenter's whole take (t = 0 at cue["start"]); the driver adds anim, out, wav
    and the face's signs. With cue["cams"] every gaze is on (or off, for a glance) the active shot's lens."""
    rng = random.Random(SEED[who] * 7)
    gl = glances(cue, who)
    spans = cue["on_cam"]
    y0, p0 = lens_dir(cue, spans[0][2] if spans and len(spans[0]) > 2 else "")
    gaze = [{"t": 0.0, "yaw": y0, "pitch": p0, "scan": "lens", "head": 1.0}]
    avoid, moves = [], []
    for g in gl:
        sp = _span_of(g["t"], spans)
        ly, lp = lens_dir(cue, sp[2] if sp and len(sp) > 2 else "")
        gaze.append({"t": g["t"], "yaw": round(ly + g["yaw"], 1), "pitch": round(lp + g["pitch"], 1), "scan": "still",
                     "head": GLANCE_HEAD})
        gaze.append({"t": g["back"], "yaw": ly, "pitch": lp, "scan": "lens", "head": 1.0})
        moves += [g["t"], g["back"]]
    ra = reaims(cue)
    for r in ra:
        gaze.append({"t": r["t"], "yaw": r["yaw"], "pitch": r["pitch"], "scan": "lens", "head": r["head"]})
        moves.append(r["t"])
    gaze.sort(key=lambda g: g["t"])
    for m in moves:  # no blink on a gaze move
        avoid.append([round(m - BLINK_GUARD[0], 3), round(m + BLINK_GUARD[1], 3)])
    fps = cue["fps"]
    for a, *_ in spans:  # no blink on a cut's first frames
        if a > 0:
            avoid.append([round(a, 3), round(a + CUT_NO_BLINK_F / fps, 3)])
    avoid.sort()
    roll = round(rng.uniform(-1.2, 1.2), 2)
    head = {**HEAD_STYLE, "seed": SEED[who], **({"rest_roll_deg": roll, "lean": 0.12} if ROLL_OK else {})}
    return {"preset": PRESET, "solver_head": "replace", "blink_head": "still", "blink_mode": "replace",
            "blink_state": "talk", "beat_every": 2, "emphasis": "auto", "start_gaze": [y0, p0], "lead": "eyes",
            "gaze": gaze, "head": head, "avoid_blinks": avoid, "seed": SEED[who], "glances": gl, "reaims": ra}


def face_args(cue: dict, who: str) -> dict:
    """plan() without its own notes (what perf.face takes)."""
    return {k: v for k, v in plan(cue, who).items() if k not in ("glances", "reaims")}


# ------------------------------------------------------------------------------------------------------- sample

def on_cam_frames(cue: dict) -> list:
    """[[f0, f1, camera], ...] master frames (f1 exclusive) of the on-camera spans."""
    fps, s0 = cue["fps"], cue["start"]
    return [[s0 + int(round(a * fps)), s0 + int(round(b * fps)), (c[0] if c else "")]
            for a, b, *c in cue["on_cam"]]


def sample(cue: dict, seq: str, label: str, out: Path) -> dict:
    """On the editor: qa.head_stability over the take (head bone + blink curves, saved on the box and pulled) and
    seq.sample of the head and both eyes with the shot's camera, span by span -> out/head.json, out/eyes.json."""
    from filmtools.unreal import client

    def ok(r):
        if not r.get("ok"):
            raise SystemExit(r.get("stdout", "") + r.get("error", ""))
        return r.get("result")
    spans = on_cam_frames(cue)
    out.mkdir(parents=True, exist_ok=True)
    remote = f"/tmp/explainer_head_{label}.json"
    ok(client.op("qa.head_stability", sequence=seq, label=label, start=spans[0][0], end=spans[-1][1] - 1,
                 out=remote, timeout=3600))
    client.pull(remote, str(out / "head.json"))
    eyes = {"spans": []}
    for f0, f1, cam in spans:
        r = ok(client.op("seq.sample", path=seq, actor_label=label, component="Face",
                         bones=["head", "FACIAL_L_Eye", "FACIAL_R_Eye"], frames=list(range(f0, f1)), ticks=2,
                         camera=cam, timeout=3600))
        eyes["spans"].append({"frames": r["frames"], "camera": cam, "cam": r["camera"], "bones": r["bones"]})
    (out / "eyes.json").write_text(json.dumps(eyes))
    return {"head": str(out / "head.json"), "eyes": str(out / "eyes.json")}


# -------------------------------------------------------------------------------------------------------- judge

def _unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def eye_metrics(eyes: dict, fps: float) -> dict:
    """From seq.sample of both eyes + the camera: the angle (deg) of each eye's gaze off its line to the lens, per
    frame. The gaze axis is the eye bone's axis that points most at the lens over the span (signed)."""
    off_all, sacc, glance_n, dur_s = [], 0, 0, 0.0
    for sp in eyes["spans"]:
        cam = np.asarray(sp["cam"], float)
        offs = []
        for e in ("FACIAL_L_Eye", "FACIAL_R_Eye"):
            b = np.asarray(sp["bones"][e], float)
            to_cam = _unit(cam - b[:, :3])
            axes = [b[:, 3 + 3 * k:6 + 3 * k] for k in range(3)]
            score = [float(np.mean(np.sum(a * to_cam, axis=1))) for a in axes]
            k = int(np.argmax(np.abs(score)))
            g = _unit(axes[k] * math.copysign(1.0, score[k]))
            offs.append(g)
        g = _unit(offs[0] + offs[1])
        mid = np.mean([np.asarray(sp["bones"][e], float)[:, :3] for e in ("FACIAL_L_Eye", "FACIAL_R_Eye")], axis=0)
        to_cam = _unit(cam - mid)
        off = np.degrees(np.arccos(np.clip(np.sum(g * to_cam, axis=1), -1, 1)))
        step = np.degrees(np.arccos(np.clip(np.sum(g[1:] * g[:-1], axis=1), -1, 1)))
        on = off < 3.0
        sacc += int(np.sum((step >= 0.1) & (step <= 1.5) & on[1:] & on[:-1]))
        # glances: runs off the lens by > 5 deg lasting 0.25-2.5 s that end back on it
        run = 0
        for i, o in enumerate(off):
            if o > 5.0:
                run += 1
            else:
                if 0.25 * fps <= run <= 2.5 * fps and i < len(off):
                    glance_n += 1
                run = 0
        off_all.append(off)
        dur_s += len(off) / fps
    off = np.concatenate(off_all) if off_all else np.zeros(0)
    on_s = float(np.sum(off < 3.0)) / fps
    return {"eyes.on_lens_share": round(float(np.mean(off < 3.0)), 3) if len(off) else None,
            "eyes.saccades_per_s": round(sacc / on_s, 2) if on_s else None,
            "eyes.glances_per_min": round(glance_n / dur_s * 60.0, 2) if dur_s else None,
            "eyes.off_lens_p95_deg": round(float(np.percentile(off, 95)), 2) if len(off) else None}


def _smooth(x: np.ndarray, n: int) -> np.ndarray:
    if n <= 1 or len(x) < n:
        return x
    k = np.hanning(n + 2)[1:-1]
    k /= k.sum()
    pad = np.pad(x, (n // 2, n - 1 - n // 2), mode="edge")
    return np.convolve(pad, k, mode="valid")


def life_metrics(t: np.ndarray, yaw: np.ndarray, pitch: np.ndarray, seen: list, fps: float) -> dict:
    """The talking head's life on its screen time: drift (the median spread of the 0.25 s-smoothed head over 2 s
    windows), the longest frozen hold (smoothed speed under 0.25 deg/s), and nods (pitch dips of >= 0.7 deg)."""
    spreads, frozen, nods, seen_s = [], 0.0, 0, 0.0
    for a, b in seen:
        m = (t >= a) & (t < b)
        if m.sum() < fps:
            continue
        y, p = _smooth(yaw[m], int(0.25 * fps)), _smooth(pitch[m], int(0.25 * fps))
        seen_s += (b - a)
        w = int(2 * fps)
        for i in range(0, len(y) - w + 1, w // 2):
            spreads.append(math.hypot(np.ptp(y[i:i + w]), np.ptp(p[i:i + w])))
        sp = np.hypot(np.diff(y), np.diff(p)) * fps
        run = best = 0
        for v in sp:
            run = run + 1 if v < 0.25 else 0
            best = max(best, run)
        frozen = max(frozen, best / fps)
        # a nod: a local pitch minimum >= 0.7 deg under the max of the 0.5 s before and after
        h = int(0.5 * fps)
        for i in range(h, len(p) - h):
            if p[i] == p[i - h:i + h + 1].min() and min(p[i - h:i].max(), p[i + 1:i + h + 1].max()) - p[i] >= 0.7:
                nods += 1
    return {"head.drift_deg": round(float(np.median(spreads)), 3) if spreads else None,
            "head.frozen_s": round(frozen, 2),
            "head.nods_per_min": round(nods / seen_s * 60.0, 2) if seen_s else None}


def _pass(item: str, v) -> bool:
    if v is None:
        return False
    op, line = LINES[item]
    return v <= line if op == "<=" else v >= line if op == ">=" else line[0] <= v <= line[1]


def judge(cue: dict, head_path: str, eyes_path: str | None, who: str = "") -> dict:
    """Every line in LINES on the presenter's screen time. Returns {"pass", "gate": {id: {"value", "line", "pass",
    "where"}}, "failed"} (agent-09's contract: {"gate": {id: {"value", "where"}}})."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
    from filmtools.unreal import qa_head as QH
    ST = QH.stability()
    spans = on_cam_frames(cue)
    seen = [[a, b] for a, b, _ in spans]
    r = QH.samples(head_path, seen_frames=seen)
    d = json.loads(Path(head_path).read_text())["samples"]
    fps, f0 = d["fps"], d["frames"][0]
    h = ST.from_bones(d["frames"], fps, d["bone"], d["forward"])
    t = np.asarray(h["times"]) - h["times"][0]
    seen_t = [((a - f0) / fps, (b - f0) / fps) for a, b in seen]
    m = r["metrics"]
    worst = max(r["blinks"], key=lambda b: abs(b["nod_deg"]), default=None)
    vals = {"head.blink_nod_deg": round(abs(worst["nod_deg"]), 3) if worst else None,
            "head.blink_locked_deg": round(float(r["bta"].get("peak_deg", m.get("blink_locked", 0.0))), 3)
            if isinstance(r.get("bta"), dict) else m.get("blink_locked"),
            "head.buzz_rms_deg": m.get("head_buzz")}
    vals.update(life_metrics(t, np.asarray(h["yaw"]), np.asarray(h["pitch"]), seen_t, fps))
    seen_s = sum(b - a for a, b in seen_t)
    vals["blinks.per_min"] = round(len(r["blinks"]) / seen_s * 60.0, 2) if seen_s else None
    if eyes_path:
        vals.update(eye_metrics(json.loads(Path(eyes_path).read_text()), fps))
    where = f"{who or d.get('label', '')} on screen f{seen[0][0]}-{seen[-1][1]} ({len(seen)} spans)"
    gate = {k: {"value": v, "line": LINES[k][1], "pass": _pass(k, v), "where": where}
            for k, v in vals.items() if k in LINES}
    info = {k: v for k, v in vals.items() if k not in LINES}
    return {"pass": all(g["pass"] for g in gate.values()), "failed": [k for k, g in gate.items() if not g["pass"]],
            "gate": gate, "info": info, "worst_blink": worst, "unseen": r["unseen"]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["plan", "sample", "judge"])
    ap.add_argument("cue")
    ap.add_argument("--who", default="him", choices=list(SEED))
    ap.add_argument("--seq")
    ap.add_argument("--label")
    ap.add_argument("--out", default="out/explainers/head")
    ap.add_argument("--head")
    ap.add_argument("--eyes")
    ap.add_argument("--gate", help="judge: also write the gate numbers file here")
    ap.add_argument("--edl", help="CUE is agent-11's audio/<film>/cues.json and this its edl/<film>.json")
    ap.add_argument("--start", type=int, default=0, help="with --edl: the master frame of the VO's t=0")
    a = ap.parse_args()
    cue = load_cue(a.cue, a.edl, a.start)
    if a.cmd == "plan":
        print(json.dumps(face_args(cue, a.who), indent=1))
    elif a.cmd == "sample":
        print(json.dumps(sample(cue, a.seq, a.label, Path(a.out))))
    else:
        r = judge(cue, a.head, a.eyes, a.who)
        if a.gate:
            Path(a.gate).write_text(json.dumps({"gate": {k: {"value": g["value"], "where": g["where"]}
                                                         for k, g in r["gate"].items()}}, indent=1))
        print(json.dumps(r, indent=1, default=str))
        sys.exit(0 if r["pass"] else 1)


if __name__ == "__main__":
    main()
