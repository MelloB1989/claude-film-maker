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
JAW_ON_OFF = 3.0       # the jaw moves at least this many times more on a speaker's lines than between them
PEN_MAX = 0.01         # at most 1% of a garment's pixels with skin through (qa.penetration's fraction)
LIPS_RATIO = 2.0      # frames: mouth-box change on the lines over off them (preview 1, no lip-sync: 1.55; r1: 2.37)


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
    s["b.watch"] = bool(cms) and max(cms) <= WATCH_MAX_CM and max(cms) - min(cms) <= WATCH_SPREAD_CM
    s["b.watch_cm"] = [min(cms), max(cms)] if cms else None
    return s


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


def mouth(out: str, shots: list | None = None, step: int = 12) -> dict:
    from filmtools.unreal import client

    def ok(res):
        if not res.get("ok"):
            raise SystemExit(res.get("stdout", "") + res.get("error", ""))
        return res.get("result")

    res = {}
    for sid in shots or list(MOUTH):
        s = next(x for x in SHOTS if x.id == sid)
        lab = CAST[s.cast[0]]
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
            res[sid] = {"who": s.cast[0], "box": None, "why": "no lip or eye bone projected into the frame"}
            continue
        w, h = max(us) - min(us), max(vs) - min(vs)
        mw, mh = max(0.01, w * MOUTH_MARGIN), max(0.01, h * MOUTH_MARGIN)
        box = [max(0.0, min(us) - mw), max(0.0, min(vs) - mh), min(1.0, max(us) + mw), min(1.0, max(vs) + mh)]
        res[sid] = {"who": s.cast[0], "label": lab, "box": [round(x, 4) for x in box], "from": sorted(used),
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
    boxes = dict(MOUTH)
    boxes.update({k: tuple(v["box"]) for k, v in (mouths or {}).items() if v.get("box")})
    res["mouth_boxes"] = boxes
    for sid, box in boxes.items():
        s = next(x for x in SHOTS if x.id == sid)
        who = s.cast[0]
        on = {f for _, a, b in windows(who) for f in range(a, b)}
        d = {}
        for f in range(s.start + 1, s.end):
            if f in fr and f - 1 in fr:
                d[f] = float(np.mean(np.abs(crop(f, box, "L") - crop(f - 1, box, "L"))))
        a_on = [v for f, v in d.items() if f in on]
        a_off = [v for f, v in d.items() if f not in on]
        if a_on and a_off:
            r = (sum(a_on) / len(a_on)) / max(1e-3, sum(a_off) / len(a_off))
            res["lips"][sid] = {"who": who, "on": round(sum(a_on) / len(a_on), 3),
                                "off": round(sum(a_off) / len(a_off), 3), "ratio": round(r, 2), "pass": r >= LIPS_RATIO}
        else:
            res["lips"][sid] = {"who": who, "pass": None, "why": "no speaking (or no silent) frames in this shot"}
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


def hue_of(im, box) -> dict | None:
    import numpy as np
    w, h = im.size
    c = np.asarray(im.crop((round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h))), np.float32)
    v = lab(c).reshape(-1, 3)
    v = v[(v[:, 0] > 2.0) & (v[:, 0] < HUE_L_MAX)]
    if len(v) < 30:
        return None
    a, b = float(np.median(v[:, 1])), float(np.median(v[:, 2]))
    return {"L": round(float(np.median(v[:, 0])), 1), "a": round(a, 2), "b": round(b, 2),
            "C": round((a * a + b * b) ** 0.5, 2), "green_px": round(float(np.mean(v[:, 1] < -4.0)), 3),
            "n": int(len(v))}


def hue(paths: list, out: str, frames_: list | None = None, regions: dict | None = None) -> dict:
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
    for name, f in files:
        im = Image.open(f).convert("RGB")
        r = {k: hue_of(im, b) for k, b in regions.items()}
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
           "green_px_max": HUE_GREEN_MAX, "images": res}
    (o / "hue.json").write_text(json.dumps(rep, indent=1))
    return res


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
    u.add_argument("--region", action="append", default=[],
                   help="name=x0,y0,x1,y1 (fractions; crown and ends_* names), replaces the default regions")
    a = ap.parse_args()
    if a.cmd == "hue":
        reg = {k: tuple(float(x) for x in v.split(",")) for k, v in (s.split("=", 1) for s in a.region)} or None
        r = hue(a.paths, a.out, [int(x) for x in a.frames.split(",")] if a.frames else None, reg)
    elif a.cmd == "mouth":
        r = mouth(a.out, a.shots.split(",") if a.shots else None)
    elif a.cmd == "frames":
        r = frames(a.root, a.engine or None, a.out, json.loads(Path(a.mouth).read_text()) if a.mouth else None)
    else:
        r = engine(a.out, a.stills) if a.cmd == "engine" else hair(a.paths, a.out)
    print(json.dumps(r, indent=1, default=str))


if __name__ == "__main__":
    main()
