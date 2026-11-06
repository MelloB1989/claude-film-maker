"""The cast gate (round 3, the orchestrator's rule): nothing with presenters goes to the operator until these pass,
with numbers. Two halves:

  engine (agent-07 runs it on the box, after the re-place runbook, before the cast preview renders):
    cd tools && uv run python ../films/host-studio/reel/cast_gate.py engine --out /tmp/cast_gate.json
  frames (on the GPU box, next to the frames: only DIR comes down):
    uv run --with pillow --with numpy python reel/cast_gate.py frames FRAMES_DIR --engine cast_gate.json --out DIR
  hair (gate c on S16-framed stills, e.g. hair_teal_ab.py's A/B; on the box):
    uv run --with pillow --with numpy python reel/cast_gate.py hair STILLS_DIR --out DIR

Checks:
  a. lips: each speaker's face animation moves the jaw on their lines and is still between them (jawOpen per frame
     from the composed face animation, by the line windows of cues.json); and on the frames, the mouth moves on the
     lines (close shots: mouth-box change on vs off the lines).
  b. garments: no skin through her Top/Trousers/Overshirt (or his garments) from the shot's camera at the start,
     middle and end of every presenter shot (qa.penetration); and her watch on her left wrist (cm from the forearm
     bone it rides) at the same frames.
  c. hair: her hair's ends are not greener than its roots (S16 close-up: chromaticity ends minus crown).
  d. alive: anim.check on each presenter's composed face (blink rate/regularity, head motion, gaze).
  e. him too: the same checks on Host.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from shots import LINES, SHOTS  # noqa: E402

SEQ = "/Game/Reel/SEQ_Reel"
CAST = {"her": "Presenter", "him": "Host"}
HER_GARMENTS = ["Top", "Trousers", "Overshirt"]
# her watch: dress_her seats it 3.6 cm above the wrist, so it is measured from hand_l (cast2 read a steady 13 cm
# from lowerarm_twist_02_l, mid-forearm: riding the arm, the wrong reference), and must hold steady across the frames
WATCH, WATCH_BONE, WATCH_MAX_CM, WATCH_SPREAD_CM = "HerWatch", "hand_l", 8.0, 1.5
# round 4: the seat itself, after the scrub, at every sampled frame (dress_her's rule: 3.6 cm from hand_l; cast_op2-4
# rendered a stale 8.2 that the old <= 8.0 cap would have waved through at 7.9)
WATCH_CM, WATCH_TOL_CM = 3.6, 0.5
JAW_ON_OFF = 3.0       # the jaw moves at least this many times more on a speaker's lines than between them
PEN_MAX = 0.01         # at most 1% of a garment's pixels with skin through (qa.penetration's fraction)
LIPS_RATIO = 2.0      # frames: mouth-box change on the lines over off them (preview 1, no lip-sync: 1.55; r1: 2.37)
LIPS_SHIFT = 3        # px at 960 wide: the previous frame is lined up within this before the mouth's change is read
LIPS_EDGE = 3         # frames either side of a line that count as neither on nor silent (the mouth sets and closes)
LIPS_MIN_PX = 8       # a mouth box under this many pixels tall is not read on the frames (S17's 28 mm two-shot at
                      # 960x540: ~5 px, where one pixel of head motion moves the whole box); the engine's jaw decides


def presenter_shots():
    return [s for s in SHOTS if getattr(s, "cast", ())]


def windows(who: str) -> list:
    """[(line, first, last)] master frames of `who`'s lines: cues.json's placement when it is there, else LINES."""
    try:
        from perf import cues  # vo.py's cues (cues.json, else cues_v2.json)
        c = cues()
        out = []
        for k, w, f0, f1, _ in LINES:
            if w == who and k in c:
                x = c[k]
                out.append((k, int(x.get("start", f0)), int(x.get("end", f1))))
            elif w == who:
                out.append((k, f0, f1))
        return out
    except Exception:  # noqa: BLE001 - no cues here: the plan's windows
        return [(k, f0, f1) for k, w, f0, f1, _ in LINES if w == who]


# ------------------------------------------------------------------------------------------------- engine half
JAW = """
import unreal
AL = unreal.AnimationLibrary
a = unreal.load_asset(ANIM)
names = [str(n) for n in AL.get_animation_curve_names(a, unreal.RawCurveTrackTypes.RCT_FLOAT)]
jaw = next((n for n in names if n.lower().endswith("jawopen")), None)
t, v = (AL.get_float_keys(a, jaw) if jaw else ([], []))
result = {"curve": jaw, "t": [round(x, 4) for x in t], "v": [round(x, 4) for x in v],
          "rate": AL.get_frame_rate(a) if hasattr(AL, "get_frame_rate") else None,
          "length_s": AL.get_sequence_length(a)}
"""

PARTS = """
import unreal
a = next(x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
         if x.get_actor_label() == LABEL)
result = [c.get_name() for c in a.get_components_by_class(unreal.SkeletalMeshComponent)
          if c.get_name() not in ("Body", "Face")]
"""

WATCH_AT = """
import unreal
w = next(x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
         if x.get_actor_label() == WATCH)
p = w.get_actor_location()
result = [p.x, p.y, p.z]
"""


def _jaw_at(curve: dict, f: float, start: int, fps: float = 24.0) -> float:
    """jawOpen at master frame f of a section starting at `start` (linear between keys)."""
    t, v = curve["t"], curve["v"]
    if not t:
        return 0.0
    x = (f - start) / fps
    if x <= t[0]:
        return v[0]
    for k in range(1, len(t)):
        if x <= t[k]:
            a = (x - t[k - 1]) / max(1e-6, t[k] - t[k - 1])
            return v[k - 1] + (v[k] - v[k - 1]) * a
    return v[-1]


def lips(who: str, face: list, ok, client) -> dict:
    """Jaw activity on `who`'s lines vs between them, from the composed face animation(s) on the face track."""
    curves = {}
    for s in face or []:
        if s["anim"] and s["anim"] not in curves:
            curves[s["anim"]] = ok(client.exec_code(f"ANIM = {s['anim']!r}\n" + JAW))
    shots = [s for s in presenter_shots() if who in s.cast]
    span = [f for s in shots for f in range(s.start, s.end)]

    def jaw(f):
        sec = next((s for s in reversed(face or []) if s["anim"] and (s["start"] or 0) <= f
                    and (s["end"] is None or f < s["end"])), None)
        return _jaw_at(curves[sec["anim"]], f, sec["start"] or 0) if sec else 0.0

    vals = {f: jaw(f) for f in span}
    win = windows(who)
    on = [f for _, a, b in win for f in range(a, b) if f in vals]
    off = [f for f in span if f not in set(on)]
    act = lambda fs: sum(abs(vals[f] - vals.get(f - 1, vals[f])) for f in fs) / max(1, len(fs))  # noqa: E731
    per = {k: {"frames": [a, b], "jaw_max": round(max((vals[f] for f in range(a, b) if f in vals), default=0), 3),
               "activity": round(act([f for f in range(a, b) if f in vals]), 4)} for k, a, b in win}
    a_on, a_off = act(on), act(off)
    ratio = a_on / max(a_off, 1e-4)
    silent = [k for k, r in per.items() if r["jaw_max"] < 0.08]
    return {"pass": bool(on) and ratio >= JAW_ON_OFF and not silent, "on_lines": round(a_on, 4),
            "between": round(a_off, 4), "ratio": round(ratio, 1), "silent_lines": silent, "lines": per,
            "anims": {k: v.get("curve") for k, v in curves.items()}}


def engine(out: str, stills: str = "") -> dict:
    from filmtools.unreal import client

    def ok(res):
        if not res.get("ok"):
            raise SystemExit(res.get("stdout", "") + res.get("error", ""))
        return res.get("result")

    rep = {"sequence": SEQ, "people": {}, "shots": {}}
    for who, lab in CAST.items():
        d = ok(client.op("perf.describe", sequence=SEQ, label=lab))
        face = d.get("face") or []
        anims = sorted({s["anim"] for s in face if s["anim"]})
        checks = {a: ok(client.op("anim.check", anim=a)) for a in anims}
        rep["people"][who] = {
            "label": lab, "face_sections": face, "body_sections": d.get("body"),
            "lips": lips(who, face, ok, client) if face else {"pass": False, "why": "no face animation on the track"},
            "alive": {a: {"pass": c.get("pass"), "failed": c.get("failed"), "blinks": c.get("blinks")}
                      for a, c in checks.items()},
            "garments": ok(client.exec_code(f"LABEL = {lab!r}\n" + PARTS)) if lab != "Presenter" else HER_GARMENTS,
        }
    for s in presenter_shots():
        r = {}
        for f in (s.start + 2, (s.start + s.end) // 2, s.end - 3):
            fr = {}
            for who in s.cast:
                lab = CAST[who]
                p = ok(client.op("qa.penetration", label=lab, body=["Body", "Face"],
                                 garments=rep["people"][who]["garments"], sequence=SEQ, frame=f, size_px=384,
                                 out_dir=f"{stills}/pen_{s.id}_{f}_{who}" if stills else ""))
                fr[who] = {"pass": p.get("pass"), "worst_fraction": p["metrics"].get("worst_fraction")}
            if "her" in s.cast:
                ok(client.op("seq.scrub", path=SEQ, frame=f))
                bone = ok(client.op("level.bone", label="Presenter", component="Body", bones=[WATCH_BONE]))
                b = bone[WATCH_BONE] if isinstance(bone, dict) else bone[0]
                w = ok(client.exec_code(f"WATCH = {WATCH!r}\n" + WATCH_AT))
                cm = sum((x - y) ** 2 for x, y in zip(w, b)) ** 0.5
                fr["watch_cm"] = round(cm, 1)
            r[f] = fr
        rep["shots"][s.id] = r
    rep["summary"] = summary(rep)
    Path(out).write_text(json.dumps(rep, indent=1, default=str))
    return rep["summary"]


def summary(rep: dict) -> dict:
    s = {}
    for who, p in rep["people"].items():
        s[f"a.lips.{who}"] = p["lips"].get("pass")
        s[f"d.alive.{who}"] = all(c["pass"] for c in p["alive"].values()) if p["alive"] else False
    pen = [(sid, f, who, v) for sid, r in rep["shots"].items() for f, fr in r.items() for who, v in fr.items()
           if isinstance(v, dict)]
    s["b.garments"] = all(v["pass"] and (v["worst_fraction"] or 0) <= PEN_MAX for *_, v in pen)
    s["b.garments_worst"] = sorted(pen, key=lambda x: -(x[3]["worst_fraction"] or 0))[:3]
    w = [(sid, f, fr["watch_cm"]) for sid, r in rep["shots"].items() for f, fr in r.items() if "watch_cm" in fr]
    cms = [cm for *_, cm in w]
    s["b.watch"] = bool(cms) and all(abs(cm - WATCH_CM) <= WATCH_TOL_CM for cm in cms)
    s["b.watch_cm"] = [min(cms), max(cms)] if cms else None
    s["b.watch_off"] = [[sid, f, cm] for sid, f, cm in w if abs(cm - WATCH_CM) > WATCH_TOL_CM]
    return s


# ------------------------------------------------------------------------------------------------- lipgap (engine)
# The frames' lips measure reads a moving head as a moving mouth: in a silence where the performance turns or lifts
# the head (S13's head up, S17's glance, after S16's line) the pixels change as much as on the line. The lips' own
# gap, upper to lower lip bone in cm on the evaluated face (seq.scrub, level.bone), moves only with the mouth.
LIP_GAP = ("FACIAL_C_LipUpper", "FACIAL_C_LipLower")
GAP_RATIO = 2.0   # the frames' line: the gap moves at least twice as much on the line as in the speaker's silence
GAP_MIN_CM = 0.3  # and opens by at least this much on the line (a mouth that reads; a closed jaw jitters ~0.05)


def lipgap(out: str, win: int = 24) -> dict:
    from filmtools.unreal import client
    sys.path.insert(0, str(HERE / "r4"))
    from lip_stills import windows as stills_windows

    def ok(res):
        if not res.get("ok"):
            raise SystemExit(res.get("stdout", "") + res.get("error", ""))
        return res.get("result")
    res = {}
    for sid, d in stills_windows(win).items():
        s = next(x for x in SHOTS if x.id == sid)
        whos = [w for w in s.cast if any(a < s.end and b > s.start for _, a, b in windows(w))]
        gaps = {w: {} for w in whos}
        for f in d["frames"]:
            ok(client.op("seq.scrub", path=SEQ, frame=f))
            for w in whos:
                b = ok(client.op("level.bone", label=CAST[w], component="Face", bones=list(LIP_GAP)))
                u, lo = b[LIP_GAP[0]], b[LIP_GAP[1]]
                gaps[w][f] = sum((x - y) ** 2 for x, y in zip(u, lo)) ** 0.5
        for w in whos:
            g = gaps[w]
            act = lambda fs: [abs(g[f] - g[f - 1]) for f in fs if f in g and f - 1 in g]  # noqa: E731
            sil = d["silence"].get(w)
            off = act(range(sil[0], sil[1])) if sil else []
            for k, a, b in windows(w):
                if k not in d["lines"]:
                    continue
                lo_, hi_ = d["lines"][k]
                on = act(range(lo_, hi_))
                rng = [g[f] for f in range(lo_, hi_) if f in g]
                m_on = sum(on) / len(on) if on else 0.0
                m_off = sum(off) / len(off) if off else 0.0
                r = m_on / max(m_off, 1e-3)
                span = (max(rng) - min(rng)) if rng else 0.0
                res[f"{sid}:{w} {k}"] = {"on_cm": round(m_on, 4), "off_cm": round(m_off, 4), "ratio": round(r, 2),
                                         "open_cm": round(span, 3), "frames": [lo_, hi_], "silence": sil,
                                         "pass": r >= GAP_RATIO and span >= GAP_MIN_CM}
    rep = {"lines": res, "pass": bool(res) and all(v["pass"] for v in res.values()), "ratio_min": GAP_RATIO,
           "open_min_cm": GAP_MIN_CM}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(rep, indent=1))
    return rep


# ------------------------------------------------------------------------------------------------- lod0 (read-only)
# build.py --lod0 pins the presenters to LOD 0 (LODSync forced_lod 0 drives the grooms; skeletal meshes
# forced_lod_model 1). A blueprint re-instance leaves stale TRASH_* components on the actor, and a pin (or
# drive_faces, or the dressing) that lands on those does nothing to what renders. The gate: no TRASH_ component on
# either presenter at all, and every live LODSync and skeletal mesh pinned.
LOD0_PROBE = """
import unreal
out = {}
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    lab = a.get_actor_label()
    if lab not in LABELS:
        continue
    r = out.setdefault(lab, {"class": a.get_class().get_name(), "components": []})
    for c in a.get_components_by_class(unreal.ActorComponent):
        n, k = c.get_name(), c.get_class().get_name()
        row = {"name": n, "class": k, "trash": n.startswith("TRASH_")}
        try:
            if isinstance(c, unreal.SkeletalMeshComponent):
                row["forced_lod_model"] = c.get_editor_property("forced_lod_model")
            elif k == "LODSyncComponent":
                row["forced_lod"] = c.get_editor_property("forced_lod")
            elif isinstance(c, unreal.GroomComponent):
                row["groom"] = True
            else:
                continue
        except Exception as e:
            row["error"] = str(e)[:120]
        r["components"].append(row)
result = out
"""


def lod0(out: str) -> dict:
    from filmtools.unreal import client
    r = client.exec_code(f"LABELS = {list(CAST.values())!r}\n" + LOD0_PROBE)
    if not r.get("ok"):
        raise SystemExit(r.get("stdout", "") + r.get("error", ""))
    rep = lod0_judge(r["result"])
    Path(out).write_text(json.dumps(rep, indent=1))
    return {k: v for k, v in rep.items() if k != "actors"}


def lod0_judge(actors: dict) -> dict:
    bad = []
    for lab in CAST.values():
        a = actors.get(lab)
        if not a:
            bad.append(f"{lab}: not in the level")
            continue
        comps = a["components"]
        bad += [f"{lab}: {c['name']} (stale TRASH_ {c['class']})" for c in comps if c["trash"]]
        live = [c for c in comps if not c["trash"]]
        syncs = [c for c in live if "forced_lod" in c]
        if not syncs:
            bad.append(f"{lab}: no live LODSync (the grooms are not pinned)")
        bad += [f"{lab}: {c['name']} LODSync forced_lod {c['forced_lod']} (want 0)" for c in syncs if c["forced_lod"] != 0]
        bad += [f"{lab}: {c['name']} forced_lod_model {c['forced_lod_model']} (want 1 = LOD 0)" for c in live
                if "forced_lod_model" in c and c["forced_lod_model"] != 1]
        bad += [f"{lab}: {c['name']} {c['error']}" for c in live if "error" in c]
    return {"pass": not bad, "failed": bad, "actors": actors}


# ------------------------------------------------------------------------------------------------- frames half
# Boxes (fractions of the 16:9 frame, x0,y0,x1,y1) per shot, set on round 3's preview framings: the speaker's mouth
# in the close shots, and her hair. Wider shots are judged on the engine numbers and by eye on the sheets.
MOUTH = {"S16": (0.48, 0.57, 0.56, 0.66), "S13": (0.47, 0.48, 0.53, 0.53)}
# her hair in S16 (the close-up): the crown (roots) and the lengths beside her shoulders (ends). The defect is the
# ends turning green/teal against the roots, so the measure is the ends' chromaticity minus the roots'.
HAIR_ROOTS = (0.44, 0.21, 0.56, 0.28)
HAIR_ENDS = [(0.38, 0.62, 0.44, 0.76), (0.56, 0.62, 0.62, 0.76)]
TEAL_MAX = 0.02  # ends' (g - r) / (r + g + b) over the roots' at most this


# The mouth box for any presenter, no eyes on the frame (face rule): the speaker's lip bones projected through the
# shot's camera at frames across the shot (cam.project), their extent plus a margin. MetaHuman face bones; when a face
# has none of them, from the eyes (the mouth sits ~1 eye-span under their midpoint).
LIP_BONES = ["FACIAL_C_LipUpper", "FACIAL_C_LipLower", "FACIAL_L_LipCorner", "FACIAL_R_LipCorner", "FACIAL_C_Jaw"]
EYE_BONES = ["FACIAL_L_Eye", "FACIAL_R_Eye"]
MOUTH_MARGIN = 0.5  # of the lips' extent, each side (the jaw drops ~that far on an open vowel)


def speakers(shots: list | None = None) -> list:
    """[(shot id, who)] for every presenter with a line in the shot (round 4: every spoken line, not only S13/S16's
    leads): S13 him, S15 him + her, S16 her, S17 him + her."""
    out = []
    for s in presenter_shots():
        if shots and s.id not in shots:
            continue
        for who in s.cast:
            if any(a < s.end and b > s.start for _, a, b in windows(who)):
                out.append((s.id, who))
    return out


def mouth(out: str, shots: list | None = None, step: int = 12) -> dict:
    """mouth.json keyed "<shot>:<who>" (a bare "<shot>" is its first cast, round 3's form)."""
    from filmtools.unreal import client

    def ok(res):
        if not res.get("ok"):
            raise SystemExit(res.get("stdout", "") + res.get("error", ""))
        return res.get("result")

    res = {}
    for sid, who in speakers(shots):
        key = f"{sid}:{who}"
        s = next(x for x in SHOTS if x.id == sid)
        lab = CAST[who]
        us, vs, used, per = [], [], set(), {}
        for f in sorted(set(range(s.start + 2, s.end - 2, step)) | {s.end - 3}):
            ok(client.op("seq.scrub", path=SEQ, frame=f))
            pts = {}
            for b in LIP_BONES + EYE_BONES:
                r = client.op("cam.project", camera=f"Reel_{sid}", points={b: f"{lab}:Face:{b}"})
                if r.get("ok"):
                    pts[b] = r["result"]["points"][b]
            lips = {b: p for b, p in pts.items() if b in LIP_BONES and p.get("visible")}
            if lips:
                fu, fv = [p["u"] for p in lips.values()], [p["v"] for p in lips.values()]
                used |= set(lips)
            elif all(b in pts for b in EYE_BONES):
                el, er = pts[EYE_BONES[0]], pts[EYE_BONES[1]]
                span = max(1e-3, ((el["u"] - er["u"]) ** 2 + (el["v"] - er["v"]) ** 2) ** 0.5)
                cu, cv = (el["u"] + er["u"]) / 2, (el["v"] + er["v"]) / 2 + span * 16 / 9  # v is in frame heights
                fu, fv = [cu - span * 0.5, cu + span * 0.5], [cv - span * 0.25, cv + span * 0.25]
                used.add("eyes")
            else:
                continue
            per[f] = [round(min(fu), 4), round(min(fv), 4), round(max(fu), 4), round(max(fv), 4)]
            us += fu
            vs += fv
        if not us:
            res[key] = {"who": who, "box": None, "why": "no lip or eye bone projected into the frame"}
            continue
        w, h = max(us) - min(us), max(vs) - min(vs)
        mw, mh = max(0.01, w * MOUTH_MARGIN), max(0.01, h * MOUTH_MARGIN)
        box = [max(0.0, min(us) - mw), max(0.0, min(vs) - mh), min(1.0, max(us) + mw), min(1.0, max(vs) + mh)]
        res[key] = {"who": who, "label": lab, "box": [round(x, 4) for x in box], "from": sorted(used),
                    "per_frame": per}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(res, indent=1))
    return {k: {x: v[x] for x in ("who", "box", "from") if x in v} for k, v in res.items()}


def frames(root: str, eng: str | None, out: str, mouths: dict | None = None) -> dict:
    import numpy as np
    from PIL import Image
    from qa_review import frames as find
    fr = find(root)
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)

    def crop(f, box, mode="RGB"):
        im = Image.open(fr[f]).convert(mode)
        w, h = im.size
        return np.asarray(im.crop((round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h))),
                          np.float32)

    res = {"lips": {}, "hair": {}}
    boxes = {} if mouths else dict(MOUTH)  # round 3's fixed boxes only when no projected box is given
    for k, v in (mouths or {}).items():
        if v.get("box"):
            boxes[k] = tuple(v["box"])
    res["mouth_boxes"] = boxes
    first = next(iter(fr.values()), None)
    W, H = Image.open(first).size if first else (0, 0)
    for key, box in boxes.items():
        sid, _, who = key.partition(":")
        s = next(x for x in SHOTS if x.id == sid)
        who = who or s.cast[0]
        mine = [(k, max(a, s.start + 1), min(b, s.end)) for k, a, b in windows(who) if a < s.end and b > s.start]
        near = {f for _, a, b in windows(who) for f in range(a - LIPS_EDGE, b + LIPS_EDGE)}
        per = {int(k): v for k, v in ((mouths or {}).get(key) or {}).get("per_frame", {}).items()}

        def box_at(f):  # the lips' own box, interpolated between the projected frames (every 12th: the nearest
            if not per:  # one lags a moving head by up to 6 frames), a quarter wider each side
                return box
            ks = sorted(per)
            lo = max([k for k in ks if k <= f], default=ks[0])
            hi = min([k for k in ks if k >= f], default=ks[-1])
            t = 0.0 if hi == lo else (f - lo) / (hi - lo)
            b = [per[lo][i] + (per[hi][i] - per[lo][i]) * t for i in range(4)]
            mw, mh = (b[2] - b[0]) * 0.25 + 0.005, (b[3] - b[1]) * 0.25 + 0.005
            return (b[0] - mw, b[1] - mh, b[2] + mw, b[3] + mh)

        def change(f, bx):
            """Mean abs luma change in the box from f-1 to f, with f-1 shifted up to LIPS_SHIFT px to line up with f
            first: the head's own move through the box (S13: head down -> up to the lens in silence) is not the
            mouth's. The mouth's opening and closing does not line up by a shift, so it stays."""
            a = crop(f, bx, "L")
            r = max(1, round(LIPS_SHIFT * W / 960))
            p0 = (bx[0] - r / W, bx[1] - r / H, bx[2] + r / W, bx[3] + r / H)
            b0 = crop(f - 1, p0, "L")
            h, w = a.shape
            best = None
            for dy in range(0, b0.shape[0] - h + 1):
                for dx in range(0, b0.shape[1] - w + 1):
                    v = float(np.mean(np.abs(a - b0[dy:dy + h, dx:dx + w])))
                    best = v if best is None or v < best else best
            return best if best is not None else float(np.mean(np.abs(a - crop(f - 1, bx, "L"))))
        d = {}
        for f in range(s.start + 1, s.end):
            if f in fr and f - 1 in fr:
                d[f] = change(f, box_at(f))
        # the speaker's silence in this shot: off every line of theirs, LIPS_EDGE frames clear (co-articulation)
        off = [v for f, v in d.items() if f not in near]
        mean = lambda xs: sum(xs) / len(xs)  # noqa: E731
        px = round(min((box_at(f)[3] - box_at(f)[1]) * H for f in d), 1) if d else 0
        lines = {}
        for k, a, b in mine:
            on = [d[f] for f in range(a, b) if f in d]
            if not on or not off:
                lines[k] = {"frames": [a, b], "pass": None, "why": "no frames on the line" if not on else
                            "no silent frames of the speaker in this shot", "n_on": len(on), "n_off": len(off)}
                continue
            r = mean(on) / max(1e-3, mean(off))
            lines[k] = {"frames": [a, b], "on": round(mean(on), 3), "off": round(mean(off), 3), "ratio": round(r, 2),
                        "pass": r >= LIPS_RATIO if px >= LIPS_MIN_PX else None}
            if px < LIPS_MIN_PX:
                lines[k]["why"] = f"mouth box {px} px tall (< {LIPS_MIN_PX}): judged on the engine's jaw per line"
        a_on = [v for f, v in d.items() if f in near]
        r = mean(a_on) / max(1e-3, mean(off)) if a_on and off else None
        res["lips"][key] = {"who": who, "shot": sid, "box_px_min": px, "ratio": round(r, 2) if r else None,
                            "lines": lines, "pass": None if not lines else
                            all(v["pass"] is not False for v in lines.values())}
    s16 = next(x for x in SHOTS if x.id == "S16")

    def chroma(c):
        lum = c.sum(axis=2)
        m = (lum > 24) & (lum < 240)  # the hair: dark, not the black of a gap
        if m.sum() < 30:
            return None
        r, g, b = (c[..., i][m].sum() for i in range(3))
        t = r + g + b
        return (g - r) / t, (b - r) / t

    vals = []
    for f in range(s16.start, s16.end, 8):
        if f not in fr:
            continue
        root = chroma(crop(f, HAIR_ROOTS))
        ends = [chroma(crop(f, b)) for b in HAIR_ENDS]
        ends = [e for e in ends if e]
        if root and ends:
            g = sum(e[0] for e in ends) / len(ends) - root[0]
            b = sum(e[1] for e in ends) / len(ends) - root[1]
            vals.append({"frame": f, "teal_g": round(float(g), 4), "teal_b": round(float(b), 4)})
    worst = max(vals, key=lambda v: v["teal_g"], default=None)
    res["hair"]["S16"] = {"pass": worst is not None and worst["teal_g"] <= TEAL_MAX, "worst": worst, "n": len(vals),
                          "threshold": TEAL_MAX}
    # the hue measure (Lab on the hair's own pixels) on the same frames: gate c's number
    from PIL import Image
    hv = {}
    for f in range(s16.start, s16.end, 8):
        if f in fr:
            im = Image.open(fr[f]).convert("RGB")
            r = {k: hue_of(im, b) for k, b in HUE_REGIONS.items()}
            crown, ends = r["crown"], [v for k, v in r.items() if k.startswith("ends") and v]
            r["pass"] = bool(crown and ends and crown["green_px"] <= HUE_GREEN_MAX and all(
                v["a"] >= HUE_A_MIN and v["C"] - crown["C"] <= HUE_C_OVER and v["green_px"] <= HUE_GREEN_MAX
                for v in ends))
            hv[f] = r
    res["hair"]["S16_hue"] = {"pass": bool(hv) and all(v["pass"] for v in hv.values()),
                              "failed": [f for f, v in hv.items() if not v["pass"]],
                              "worst_a": min((v["a"] for r in hv.values() for k, v in r.items()
                                              if k.startswith("ends") and v), default=None), "frames": hv}
    if eng:
        res["engine"] = json.loads(Path(eng).read_text()).get("summary")
    (o / "cast_gate_frames.json").write_text(json.dumps(res, indent=1))
    return res


def hair(paths: list, out: str) -> dict:
    """Gate c on stills framed as S16 (hair_teal_ab.py's A/B): the ends' teal over the roots per still, and one sheet
    of them, labelled, so only the sheet and the numbers leave the box."""
    import numpy as np
    from PIL import Image, ImageDraw
    files = []
    for p in paths:
        q = Path(p)
        files += sorted(q.glob("*.png")) + sorted(q.glob("*.jp*g")) if q.is_dir() else [q]
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)

    def chroma(im, box):
        w, h = im.size
        c = np.asarray(im.crop((round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h))),
                       np.float32)
        lum = c.sum(axis=2)
        m = (lum > 24) & (lum < 240)
        if m.sum() < 30:
            return None
        r, g, b = (c[..., i][m].sum() for i in range(3))
        return (g - r) / (r + g + b), (b - r) / (r + g + b)

    res, cells = {}, []
    for f in files:
        im = Image.open(f).convert("RGB")
        root = chroma(im, HAIR_ROOTS)
        ends = [e for e in (chroma(im, b) for b in HAIR_ENDS) if e]
        if root and ends:
            g = sum(e[0] for e in ends) / len(ends) - root[0]
            res[f.stem] = {"teal_g": round(float(g), 4), "pass": bool(g <= TEAL_MAX)}
        cell = im.resize((480, 270))
        ImageDraw.Draw(cell).text((6, 6), f"{f.stem} {res.get(f.stem, {}).get('teal_g')}", fill=(255, 255, 0))
        cells.append(cell)
    if cells:
        cols = 3
        sheet = Image.new("RGB", (cols * 484, ((len(cells) + cols - 1) // cols) * 274), (24, 24, 24))
        for k, c in enumerate(cells):
            sheet.paste(c, ((k % cols) * 484, (k // cols) * 274))
        sheet.save(o / "hair_sheet.jpg", quality=88)
    (o / "hair.json").write_text(json.dumps(res, indent=1))
    return res


# Gate c by hue, as the eye sees it (cc-64d05f6e, night1: teal_g's rgb ratio over boxes that may hold the overshirt
# did not say what the eye says): CIELAB a*/b* of the hair's own pixels (L* under HUE_L_MAX: the strands are near
# black, the olive overshirt and her skin are lighter), per region. a* < 0 is green, b* < 0 is blue: teal is both.
HUE_REGIONS = {"crown": HAIR_ROOTS, "ends_screen_left": HAIR_ENDS[0], "ends_screen_right": HAIR_ENDS[1]}
HUE_L_MAX = 30.0
HUE_A_MIN = -2.0      # an end's a* at least this (no green)
HUE_C_OVER = 3.0      # an end's chroma at most this over the crown's
HUE_GREEN_MAX = 0.05  # at most this share of a region's hair pixels green (a* < -4): the median hides green strands


def lab(rgb):
    """sRGB 0-255 (..., 3) -> CIELAB (..., 3), D65."""
    import numpy as np
    c = rgb / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = c @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


MASK_DIFF = 6.0  # with --mask: a pixel is hair when the hair-hidden still differs from it by more than this (0-255)


def hue_of(im, box, mask=None) -> dict | None:
    """Lab of the hair's pixels in box: dark ones (L* < HUE_L_MAX), and with `mask` (the same still with her hair
    hidden) only the ones the hair changes. Without a mask a dark green background between thin tips (the pothos,
    the overshirt in shadow) counts as green hair; with it only the strands do."""
    import numpy as np
    w, h = im.size
    xy = (round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h))
    c = np.asarray(im.crop(xy), np.float32)
    v = lab(c).reshape(-1, 3)
    keep = (v[:, 0] > 2.0) & (v[:, 0] < HUE_L_MAX)
    if mask is not None:
        m = np.asarray(mask.crop(xy), np.float32)
        keep &= (np.abs(c - m).mean(axis=2) > MASK_DIFF).reshape(-1)
    v = v[keep]
    if len(v) < 30:
        return None
    a, b = float(np.median(v[:, 1])), float(np.median(v[:, 2]))
    return {"L": round(float(np.median(v[:, 0])), 1), "a": round(a, 2), "b": round(b, 2),
            "C": round((a * a + b * b) ** 0.5, 2), "green_px": round(float(np.mean(v[:, 1] < -4.0)), 3),
            "n": int(len(v))}


def hue(paths: list, out: str, frames_: list | None = None, regions: dict | None = None, mask: str = "") -> dict:
    """Per image (frames of a shot, by master frame, or A/B stills): the hair regions' Lab, the ends against the
    crown, pass/fail, and one sheet of the regions at full size (only the sheet and the numbers leave the box)."""
    from PIL import Image, ImageDraw
    from qa_review import frames as find
    regions = regions or HUE_REGIONS
    files = []
    for p in paths:
        q = Path(p)
        if q.is_dir() and frames_:
            fr = find(str(q))
            files += [(f"f{f}", fr[f]) for f in frames_ if f in fr]
        elif q.is_dir():
            files += [(x.stem, x) for x in sorted(q.glob("*.png")) + sorted(q.glob("*.jp*g"))]
        else:
            files.append((q.stem, q))
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    res, rows = {}, []
    mk = Image.open(mask).convert("RGB") if mask else None
    files = [(n, f) for n, f in files if not mask or Path(f).resolve() != Path(mask).resolve()]
    for name, f in files:
        im = Image.open(f).convert("RGB")
        r = {k: hue_of(im, b, mk if mk and mk.size == im.size else None) for k, b in regions.items()}
        crown = r.get("crown")
        ends = {k: v for k, v in r.items() if k.startswith("ends") and v}
        r["pass"] = bool(crown and ends and crown["green_px"] <= HUE_GREEN_MAX and all(
            v["a"] >= HUE_A_MIN and v["C"] - crown["C"] <= HUE_C_OVER and v["green_px"] <= HUE_GREEN_MAX
            for v in ends.values()))
        res[name] = r
        w, h = im.size
        cells = []
        for k, b in regions.items():
            c = im.crop((round(b[0] * w), round(b[1] * h), round(b[2] * w), round(b[3] * h)))
            c = c.resize((240, max(1, round(240 * c.height / max(1, c.width)))))
            v = r.get(k)
            ImageDraw.Draw(c).text((4, 4), f"{name} {k}" + (f" a{v['a']} b{v['b']}" if v else ""), fill=(255, 255, 0))
            cells.append(c)
        rows.append(cells)
    if rows:
        cw, ch = 244, max(c.height for row in rows for c in row) + 4
        sheet = Image.new("RGB", (cw * max(len(r) for r in rows), ch * len(rows)), (24, 24, 24))
        for i, row in enumerate(rows):
            for j, c in enumerate(row):
                sheet.paste(c, (j * cw, i * ch))
        sheet.save(o / "hue_sheet.jpg", quality=90)
    rep = {"regions": regions, "L_max": HUE_L_MAX, "a_min": HUE_A_MIN, "C_over_crown": HUE_C_OVER,
           "green_px_max": HUE_GREEN_MAX, "mask": mask or None, "images": res}
    (o / "hue.json").write_text(json.dumps(rep, indent=1))
    return res


# ------------------------------------------------------------------------------------------------- sign (round 4)
# The round-4 gate on a cast preview, numbers only: every item passes or the gate refuses, listing what failed with
# its frames. The orchestrator's by-eye review runs alongside; both must pass before the presenter finals.
SHOTS_13 = ["V01", "V02", "V03", "V04", "V05", "S11", "S12", "N01", "S13", "S15", "S16", "S17", "S18"]
HUE_FRAMES = (1236, 1300)  # S16, where the screen-left ends read green (night1, cast_op3/4: green_px ~0.24)
# agent-02's clipping metric (r4/clip_pass.py): per (under>over) layer pair, the share of the over garment's pixels
# where the under layer pokes 0.3-3 cm through it at an intersection edge (openings and arms in front drop out).
CLIP_MAX = 0.001
CLIP_WHY = ("agent-02's cast_op4 pass: clean pairs read 0.0000 in every frame, the smallest real clip (the S18 hem, "
            "21 px of a 4400 px tee) 0.0047; 0.001 (~4 px) sits between with margin")


def _rows(x):
    """A list of dict rows from a report: a list, or the first list-valued field of a dict."""
    if isinstance(x, list):
        return x
    for k in ("beats", "rows", "items", "frames", "results"):
        if isinstance(x.get(k), list):
            return x[k]
    return []


def _lips(fr: dict, eng: dict | None, gap: dict | None = None) -> dict:
    """Per spoken line: the frames' ratio; a line the frames fail (or cannot read) passes on the lip bones' own gap
    (lipgap: the head's move in the silence is not in it), and says so."""
    bad, per = [], {}
    gl = (gap or {}).get("lines", {})
    lines = {k: (who, v) for who, p in ((eng or {}).get("people") or {}).items()
             for k, v in (p.get("lips") or {}).get("lines", {}).items()}
    spoken = {k for k, *_ in LINES}
    for key, r in (fr.get("lips") or {}).items():
        for k, v in (r.get("lines") or {}).items():
            spoken.discard(k)
            if v.get("pass") is None:  # too small or no silence on the frames: the engine's jaw on that line
                j = lines.get(k, (None, {}))[1]
                ok_ = bool(j) and j.get("jaw_max", 0) >= 0.08 and j.get("activity", 0) > 0
                per[f"{key} {k}"] = {"frames": v["frames"], "engine_jaw_max": j.get("jaw_max"), "pass": ok_,
                                     "why": v.get("why")}
            else:
                per[f"{key} {k}"] = {"frames": v["frames"], "ratio": v["ratio"], "pass": v["pass"]}
            gv = gl.get(f"{key} {k}")
            if not per[f"{key} {k}"]["pass"] and gv:
                per[f"{key} {k}"] = {**per[f"{key} {k}"], "pass": bool(gv["pass"]), "by": "lipgap",
                                     "gap_ratio": gv["ratio"], "gap_open_cm": gv["open_cm"]}
                if not gv["pass"]:
                    bad.append(f"{key} {k} f{v['frames'][0]}-{v['frames'][1]}: frames ratio {v.get('ratio')}, lip gap "
                               f"ratio {gv['ratio']} (>= {GAP_RATIO}), opens {gv['open_cm']} cm (>= {GAP_MIN_CM})")
                continue
            if not per[f"{key} {k}"]["pass"]:
                bad.append(f"{key} {k} f{v['frames'][0]}-{v['frames'][1]}: " + (
                    f"frames ratio {v['ratio']} < {LIPS_RATIO}" if v.get("pass") is False else
                    f"engine jaw_max {per[f'{key} {k}'].get('engine_jaw_max')} ({v.get('why')})"))
    bad += [f"{k}: no mouth box measured it" for k in sorted(spoken)]
    for who, p in ((eng or {}).get("people") or {}).items():
        lp = p.get("lips") or {}
        if not lp.get("pass"):
            bad.append(f"engine {who}: jaw on/off lines {lp.get('ratio')} (>= {JAW_ON_OFF}), silent {lp.get('silent_lines')}")
    return {"pass": not bad, "failed": bad, "lines": per}


def _watch(eng: dict | None) -> dict:
    if not eng:
        return {"pass": False, "failed": ["no engine report"]}
    w = [(sid, f, fr["watch_cm"]) for sid, r in eng["shots"].items() for f, fr in r.items() if "watch_cm" in fr]
    bad = [f"{sid} f{f}: {cm} cm" for sid, f, cm in w if abs(cm - WATCH_CM) > WATCH_TOL_CM]
    return {"pass": bool(w) and not bad, "failed": bad or ([] if w else ["no watch reading"]), "target_cm": WATCH_CM,
            "tol_cm": WATCH_TOL_CM, "range_cm": [min(c for *_, c in w), max(c for *_, c in w)] if w else None}


def _hue(h: dict | None, fr: dict | None) -> dict:
    imgs = (h or {}).get("images") or {}
    if not imgs and fr:  # the frames report's own S16 hue (every 8th frame)
        imgs = {f"f{k}": v for k, v in (((fr.get("hair") or {}).get("S16_hue") or {}).get("frames") or {}).items()}
    want = [f"f{f}" for f in HUE_FRAMES]
    bad = [f"{n}: not measured" for n in want if n not in imgs]
    for n, r in imgs.items():
        for k, v in r.items():
            if k == "pass" or not v:
                continue
            why = []
            if v["green_px"] > HUE_GREEN_MAX:
                why.append(f"green_px {v['green_px']}")
            if k.startswith("ends") and v["a"] < HUE_A_MIN:
                why.append(f"a* {v['a']}")
            if why:
                bad.append(f"{n} {k}: " + ", ".join(why))
    return {"pass": not bad, "failed": bad, "green_px_max": HUE_GREEN_MAX,
            "worst": max(((n, k, v["green_px"]) for n, r in imgs.items() for k, v in r.items()
                          if k != "pass" and v), key=lambda x: x[2], default=None)}


TURN_ERR_DEG, TURN_REACH_DEG, TURN_HEAD_MIN_DEG = 15.0, 100.0, 32.5  # agent-01's rule (fleet/agent-01/r4-look)
TURN_PLAN_TOL = 15.0  # and the head within 15 deg of its planned yaw (the orchestrator's +-15; agent-01 64161ac8): the
                      # beyond-reach clause alone passed his S15 head at 41 against 95 planned


def _turn_ok(r: dict) -> bool:
    """agent-01's pass rule, re-applied here: the head turns towards the partner on screen, and the gaze lands within
    15 deg of their face, or (the partner beyond neck + eye reach) the head is turned their way by >= 32.5 deg."""
    if r.get("screen_dir") is None or r.get("screen_dir") != r.get("partner_dir"):
        return False
    if r.get("head_vs_plan_deg") is None or abs(r["head_vs_plan_deg"]) > TURN_PLAN_TOL:
        return False
    if r.get("err_deg") is not None and r["err_deg"] <= TURN_ERR_DEG:
        return True
    ty, hy = r.get("true_yaw"), r.get("head_yaw")
    return ty is not None and hy is not None and abs(ty) > TURN_REACH_DEG and hy * ty > 0 and abs(hy) >= TURN_HEAD_MIN_DEG


def _turns(t) -> dict:
    """agent-01's looks_measured.json (perf.py looks --measured): one row per look beat x camera that sees it."""
    if t is None:
        return {"pass": False, "failed": ["no head-turn table (agent-01)"]}
    rows = _rows(t)
    bad = []
    for r in rows:
        fr_ = r.get("frames") or [r.get("f0"), r.get("f1")]
        where = f"{r.get('shot')} {r.get('who')} '{r.get('beat', '')}' f{fr_[0]}-{fr_[-1]} (hold f{r.get('frame')})"
        if "stage" in r and r["stage"] != "level":
            bad.append(f"{where}: measured on {r['stage']}, not the level")
        elif not (r.get("ok", r.get("pass")) and ("screen_dir" not in r or _turn_ok(r))):
            bad.append(f"{where}: head {r.get('head_yaw')} deg (plan {r.get('head_plan_yaw')}, off "
                       f"{r.get('head_vs_plan_deg')}) to screen {r.get('screen_dir')}, partner {r.get('partner_dir')}, "
                       f"gaze err {r.get('err_deg')} deg (true yaw {r.get('true_yaw')})")
    return {"pass": bool(rows) and not bad, "failed": bad or ([] if rows else ["the table has no beats"]),
            "beats": len(rows)}


CLIP_SHOTS = {"Host": ["S13", "S15", "S17", "S18"], "Presenter": ["S15", "S16", "S17", "S18"]}
CLIP_GATED = {"Host": ("Body>tee", "Body>Trousers", "Trousers>tee")}  # his screen pairs with an absolute line
# neck_px (agent-02, r4-clip 0b4347ed): per image column the collar rim is the tee's front-surface top edge (a tee
# pixel with no tee above it, or tee > 4 cm further: its inside back, and his face nearer there); the band is 1.0 cm
# under the rim at the rim's depth (a column without a rim takes the nearest within 24 px); neck_px counts the Face>tee
# clip pixels below the band. The clean neck seen above the collar stays out; the patch under it counts.
CLIP_HER_DRIFT = 0.01  # her pairs read 0.03-0.19 on clean frames (the scoop neck, the open overshirt): after vs before


def _clip(cs: list, eng: dict | None, before: dict | None = None) -> dict:
    """agent-02's clip.json (r4/clip_pass.py, one per presenter): shots -> frame -> "under>over" -> {fraction, raw,
    clusters}. Him: CLIP_GATED pairs <= CLIP_MAX, and "neck_px" (Face>tee pixels under the collar band's lower edge)
    0 every frame; Face>tee as a whole and the 3D "neck" are information only. Her: per (shot, pair)
    the worst fraction no more than CLIP_HER_DRIFT over `before` (her cast_op4 pass). A missing or errored shot
    refuses."""
    bad, worst, info = [], {}, {}
    cs = [c for c in cs or [] if c]
    if not cs and eng:
        for sid, r in eng["shots"].items():
            for f, fr_ in r.items():
                v = fr_.get("him")
                if isinstance(v, dict) and (v.get("worst_fraction") or 0) > CLIP_MAX:
                    bad.append(f"{sid} f{f} him: {v['worst_fraction']}")
        return {"pass": not bad, "failed": bad, "threshold": CLIP_MAX, "why": CLIP_WHY,
                "source": "engine qa.penetration (him only)"}
    if not cs:
        return {"pass": False, "failed": ["no clipping numbers"], "threshold": CLIP_MAX, "why": CLIP_WHY}

    def worst_of(c):
        w = {}
        for sid, per in (c.get("shots") or {}).items():
            sid = sid.removeprefix("Reel_")
            for f, fr_ in (per.items() if isinstance(per, dict) and "error" not in per else ()):
                for pair, v in fr_.items():
                    if isinstance(v, dict) and "fraction" in v and v["fraction"] >= w.get((sid, pair), (-1,))[0]:
                        w[(sid, pair)] = (v["fraction"], f)
        return w
    for c in cs:
        lab = c.get("label", "?")
        shots = {k.removeprefix("Reel_"): v for k, v in (c.get("shots") or {}).items()}  # clip_pass writes Reel_S13
        c = {**c, "shots": shots}
        for sid in CLIP_SHOTS.get(lab, []):
            if sid not in shots:
                bad.append(f"{lab} {sid}: not in the clip pass")
            elif not isinstance(shots[sid], dict) or "error" in shots[sid]:
                bad.append(f"{lab} {sid}: {shots[sid].get('error') if isinstance(shots[sid], dict) else shots[sid]}")
        w = worst_of(c)
        for (sid, pair), (v, f) in sorted(w.items()):
            worst[f"{lab} {sid} {pair}"] = {"fraction": v, "at": f}
        if lab == "Host":
            necks = 0
            for sid, per in shots.items():
                for f, fr_ in (per.items() if isinstance(per, dict) and "error" not in per else ()):
                    for pair, v in fr_.items():
                        if not (isinstance(v, dict) and "fraction" in v):
                            continue
                        if pair in CLIP_GATED["Host"] and v["fraction"] > CLIP_MAX:
                            cl = max(v.get("clusters") or [{}], key=lambda x: x.get("px", 0))
                            bad.append(f"Host {sid} f{f} {pair}: {v['fraction']} (> {CLIP_MAX}; worst cluster "
                                       f"{cl.get('px')} px, {cl.get('worst_cm')} cm)")
                        elif pair not in CLIP_GATED["Host"]:
                            info[f"Host {pair}"] = max(info.get(f"Host {pair}", 0), v["fraction"])
                    # the orchestrator's line (06 Nov): the PIXEL patch under his collar band, 0 px every frame; the
                    # 3D vertex count missed what the after renders still show, so it is information only
                    n = fr_.get("neck_px")
                    if isinstance(n, dict):
                        necks += 1
                        if n.get("px", 1) != 0:
                            bad.append(f"Host {sid} f{f} neck patch: {n.get('px')} px of face through the tee under "
                                       f"the collar band" + (f" (clusters {n.get('clusters')})" if n.get("clusters") else ""))
                    n3 = fr_.get("neck")
                    if isinstance(n3, dict):
                        info["Host neck 3D out (verts)"] = max(info.get("Host neck 3D out (verts)", 0), n3.get("out", 0))
            if not necks:
                bad.append("Host: no 'neck_px' (the pixel patch under the collar band) in the clip pass")
        elif lab == "Presenter":
            if not before:
                bad.append("Presenter: no before pass to compare with (--clip-before)")
                continue
            wb = worst_of(before)
            for (sid, pair), (v, f) in sorted(w.items()):
                b0 = wb.get((sid, pair))
                if b0 is None:
                    bad.append(f"Presenter {sid} {pair}: {v} at f{f}, not in the before pass")
                elif v > b0[0] + CLIP_HER_DRIFT:
                    bad.append(f"Presenter {sid} f{f} {pair}: {v} against {b0[0]} before (> +{CLIP_HER_DRIFT})")
    return {"pass": not bad, "failed": bad, "threshold": CLIP_MAX, "why": CLIP_WHY, "her_drift": CLIP_HER_DRIFT,
            "source": "agent-02 clip_pass", "info_only": info, "worst": worst}


def _cams(txt: str | None, framing: str | None) -> dict:
    bad = []
    if txt is None:
        bad.append("no probe_cam --check output")
    else:
        st = {}
        for line in txt.splitlines():
            w = line.split(None, 1)
            if len(w) == 2 and w[0] in SHOTS_13:
                st[w[0]] = w[1].strip()
        bad += [f"{sid}: {st.get(sid, 'not probed')}" for sid in SHOTS_13 if not st.get(sid, "").startswith("OK")]
    if framing is None:
        bad.append("no framing.py output")
    else:
        bad += [ln.strip() for ln in framing.splitlines() if ln.startswith("PROBLEM")]
    ok_n = len(SHOTS_13) - len([b for b in bad if b.split(":")[0] in SHOTS_13])
    return {"pass": not bad, "failed": bad, "cameras_ok": f"{ok_n}/{len(SHOTS_13)}" if txt is not None else None}


def sign(a) -> dict:
    rd = lambda p: json.loads(Path(p).read_text()) if p else None  # noqa: E731
    tx = lambda p: Path(p).read_text() if p else None  # noqa: E731
    eng, fr = rd(a.engine), rd(a.frames)
    items = {
        "a.lips": _lips(fr or {}, eng, rd(a.lipgap)) if fr else {"pass": False, "failed": ["no frames report"]},
        "b.watch": _watch(eng),
        "c.hair_hue": _hue(rd(a.hue), fr),
        "d.head_turns": _turns(rd(a.turns)),
        "e.clipping": _clip([rd(x) for x in a.clip], eng, rd(a.clip_before)),
        "f.cameras_framing": _cams(tx(a.cams), tx(a.framing)),
        "g.lod0_live": (lambda r: {"pass": r["pass"], "failed": r["failed"]})(
            rd(a.lod0) if a.lod0 else {"pass": False, "failed": ["no lod0 probe"]}),
    }
    waived = dict(w.split("=", 1) for w in a.waive)
    for k, why in waived.items():
        if k in items and not items[k]["pass"]:
            items[k]["waived"] = why
    blocking = [k for k, v in items.items() if not v["pass"] and "waived" not in v]
    rep = {"preview": a.name, "verdict": "SIGN" if not blocking else "REFUSE", "blocking": blocking, "items": items}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rep, indent=1, default=str))
    return rep


def sign_text(rep: dict) -> str:
    out = [f"agent-09 gate, {rep['preview']}: {rep['verdict']}"]
    for k, v in rep["items"].items():
        st = "PASS" if v["pass"] else ("WAIVED: " + v["waived"] if "waived" in v else "FAIL")
        out.append(f"  {k}: {st}" + (f" ({v['cameras_ok']})" if v.get("cameras_ok") else ""))
        out += [f"    - {b}" for b in v.get("failed", [])[:12]]
        if len(v.get("failed", [])) > 12:
            out.append(f"    ... {len(v['failed']) - 12} more in the json")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("engine")
    e.add_argument("--out", required=True)
    e.add_argument("--stills", default="", help="a directory ON THE BOX for qa.penetration's magenta stills")
    f = sub.add_parser("frames")
    f.add_argument("root")
    f.add_argument("--engine", default="")
    f.add_argument("--out", required=True)
    f.add_argument("--mouth", default="", help="mouth.json from `mouth`: its boxes replace MOUTH's per shot")
    m = sub.add_parser("mouth", help="the speaker's mouth box per shot, from the face's lip bones (engine)")
    m.add_argument("--out", required=True, help="mouth.json")
    m.add_argument("--shots", default="", help="S13,S16 (default: MOUTH's shots)")
    h = sub.add_parser("hair")
    h.add_argument("paths", nargs="+")
    h.add_argument("--out", required=True)
    u = sub.add_parser("hue", help="gate c by Lab hue: hair-only regions, the ends against the crown")
    u.add_argument("paths", nargs="+", help="frame dirs (with --frames) or stills")
    u.add_argument("--out", required=True)
    u.add_argument("--frames", default="", help="master frames, e.g. 1236,1300")
    u.add_argument("--mask", default="", help="the same still with her hair hidden: only the pixels the hair "
                   "changes are measured (hair_teal_ab.py's hair_hidden.png)")
    u.add_argument("--region", action="append", default=[],
                   help="name=x0,y0,x1,y1 (fractions; crown and ends_* names), replaces the default regions")
    g = sub.add_parser("sign", help="round 4: every item -> SIGN or REFUSE, with the failing frames")
    g.add_argument("--name", default="cast_op5")
    g.add_argument("--engine", default="", help="engine --out (with the post-scrub watch)")
    g.add_argument("--frames", default="", help="frames --mouth's cast_gate_frames.json")
    g.add_argument("--hue", default="", help=f"hue --frames {','.join(map(str, HUE_FRAMES))}'s hue.json")
    g.add_argument("--lipgap", default="", help="cast_gate.py lipgap's json: decides the lines the frames fail")
    g.add_argument("--turns", default="", help="agent-01's head-turn direction table (json)")
    g.add_argument("--clip", action="append", default=[], help="agent-02's clip.json, once per presenter "
                   "(r4/clip_pass.py); else the engine's qa.penetration")
    g.add_argument("--clip-before", default="", help="her clip.json before (cast_op4): her pairs are judged "
                   "against it")
    g.add_argument("--cams", default="", help="probe_cam.py <13 shots> --check's output (text)")
    g.add_argument("--framing", default="", help="framing.py's output (text)")
    g.add_argument("--lod0", default="", help="cast_gate.py lod0's json")
    g.add_argument("--waive", action="append", default=[], help="item=reason, only on the orchestrator's word")
    g.add_argument("--out", required=True)
    lg = sub.add_parser("lipgap", help="engine, read-only: the lip bones' gap on each line vs the speaker's silence")
    lg.add_argument("--out", required=True)
    o = sub.add_parser("lod0", help="read-only: no TRASH_ on the presenters, every live LODSync/mesh pinned")
    o.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "sign":
        rep = sign(a)
        print(sign_text(rep))
        sys.exit(0 if rep["verdict"] == "SIGN" else 1)
    if a.cmd == "lipgap":
        r = lipgap(a.out)
    elif a.cmd == "lod0":
        r = lod0(a.out)
    elif a.cmd == "hue":
        reg = {k: tuple(float(x) for x in v.split(",")) for k, v in (s.split("=", 1) for s in a.region)} or None
        r = hue(a.paths, a.out, [int(x) for x in a.frames.split(",")] if a.frames else None, reg, a.mask)
    elif a.cmd == "mouth":
        r = mouth(a.out, a.shots.split(",") if a.shots else None)
    elif a.cmd == "frames":
        r = frames(a.root, a.engine or None, a.out, json.loads(Path(a.mouth).read_text()) if a.mouth else None)
    else:
        r = engine(a.out, a.stills) if a.cmd == "engine" else hair(a.paths, a.out)
    print(json.dumps(r, indent=1, default=str))


if __name__ == "__main__":
    main()
