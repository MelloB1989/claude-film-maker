"""The explainers' performances (round 6, agent-01): one presenter SEATED in agent-07's chair, talking to the lens into
the studio mic, forearms on the desk, a hand lifting on the emphasis words; the face from per-line MetaHuman audio
solves of agent-11's VO (mouth only), alive by agent-04's head plan, the eyes locked on each shot's camera.

Him (Host, "How WhatsApp delivers ...") runs on box A, her (Presenter, "How Netflix streams ...") on box B. The box's
driver runs every step from the kali driver tree (`tools/`, FILM_UE_CONF_DIR for the box), in order:

    cd tools && P=../films/host-studio/explainers/perform.py
    uv run python $P push --who her           # line WAVs + vo.wav -> <project>/Saved/Import/explain/<film>/
    uv run python $P solve --who her          # one mouth-only speech.to_face per line (head off, blinks off)
    uv run python $P bias --who her           # each solve against its own WAV (onset, silence): exit 1 on a fail
    uv run python $P compose --who her        # -> /Game/Explainer/Perf/AS_exp_her_solve (lines at their frames)
    uv run python $P check --who her --stage solve      # lipsync.check vs vo.wav + the line solves: exit 1 on fail
    uv run python $P workseq --who her        # SEQ_Explain_Her -> SEQ_Perf_Her (the bakes' sequence; cameras kept)
    uv run python $P cams --who her           # each camera's direction from the seated eyes (character frame)
    uv run python $P body --who her           # the seated body -> AS_exp_her_seat (+ its numeric check)
    uv run python $P life --who her           # breathing additive -> AS_exp_her_life (calibrate_body once first)
    uv run python $P face --who her           # perf.face with agent-04's plan, turned to each shot's camera
    uv run python $P check --who her --stage face
    uv run python $P sync --who her           # face and body one skeleton; the planned head turn onto the body
    uv run python $P gaze --who her           # eyes locked on each on-camera span's camera
    uv run python $P check --who her --stage final
    uv run python $P place --who her          # onto SEQ_Explain_Her: Body seat+life, Face final
    uv run python $P check --who her --stage placed
    uv run python $P bodycheck --who her      # what the sequence plays: hands/elbows/knees vs desk, seat, mic; breath

`all --who her --from <step>` runs them in that order and stops at the first failure. Every step prints JSON and keeps
it under out/explainers/perf/<who>/. Nothing here renders (the driver renders the review stills / clips).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "reel"))
sys.path.insert(0, str(ROOT / "tools"))
import seatkit as S  # noqa: E402

FILM = {"him": "whatsapp", "her": "netflix"}
LABEL = {"him": "Host", "her": "Presenter"}
SEQ = {"him": "/Game/Explainer/SEQ_Explain_Him", "her": "/Game/Explainer/SEQ_Explain_Her"}
WORK = {"him": "/Game/Explainer/Perf/SEQ_Perf_Him", "her": "/Game/Explainer/Perf/SEQ_Perf_Her"}
ANIM = "/Game/Explainer/Perf"
SPEECH = "/Game/Speech"
FPS = 24
IDLE = "/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"
OUT = ROOT / "out" / "explainers" / "perf"
SEED = {"him": 71, "her": 72}

# The set (agent-07 / agent-05's props.json, 07 Nov 17:0x IST), in the ACTOR's frame: x forward (to camera), y the presenter's right, z up
# from the floor; the actor root sits on the chair mark (studio (20, -20, 0), yaw 0: studio +X forward, studio +Y the
# presenter's LEFT). Studio -> actor: x - 20, -(y + 20), z.
SET = S.Set(seat_top=45.0, seat_front=24.5, desk_top=74.0, desk_near=30.5, desk_far=85.5, desk_under=63.4,
            mic=[24.0, 14.0, 99.0], mic_radius=9.0,
            boom=[[50.0, 52.6, 74.0], [43.8, 42.9, 119.3], [24.0, 14.0, 99.0]])  # agent-05 props.json (16:5x IST)
# How each sits (seatkit.Style). The cameras are to the presenter's right-front (-20 deg MCU/CU, -8 WIDE): the chest
# turns a little toward them, the head and eyes do the rest (face + gaze).
STYLE = {
    "her": S.Style(lean=12.0, twist=6.0, knee_out=4.0, foot_out=6.0, wrist_in=5.0, pronation=52.0, heel_lift=5.0,
                   shin_tilt=3.0,
                   clavicle_fwd=5.0),
    "him": S.Style(lean=14.0, twist=6.0, knee_out=8.0, foot_out=9.0, wrist_in=3.0, pronation=48.0,
                   clavicle_fwd=6.0),
}
# The line solves' moods (speech.to_face): measured and calm, a little brighter on the hook and the close.
MOOD = {"hook": ("CONFIDENCE", 0.8), "close": ("CONFIDENCE", 0.8)}
MOOD_DEFAULT = ("CONFIDENCE", 0.65)
SPEECH_GAIN = {"him": 1.7, "her": 1.0}  # the reel's: his rig gives little mouth travel (r4)
# body life on a seated body: calm breathing that shows (agent-09's breath rows: 8-22 /min, >= 2 mm sternum rise),
# almost no weight shift (the seat holds the pelvis), no torso follow (r5: it rode the blinks)
LIFE = {"state": "talk", "breath_deg": 0.9, "clavicle_deg": 0.8, "shift_cm": 0.25, "follow": 0.0}


def ok(res: dict):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return res.get("result")


def client():
    from filmtools.unreal import client as c
    return c


def box(who: str, *parts: str) -> str:
    from filmtools.unreal import workstation as ws
    from filmtools.unreal.boxpaths import BoxPaths
    return BoxPaths.current().join(ws.project(), "Saved", "Import", "explain", FILM[who], *parts)


def run(code: str, params: dict, timeout: float = 900):
    return ok(client().exec_code(f"PARAMS = {json.dumps(json.dumps(params))}\n" + code, timeout=timeout))


def keep(who: str, name: str, data) -> Path:
    p = OUT / who / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1))
    return p


def cues(who: str) -> dict:
    return json.loads((HERE / "audio" / FILM[who] / "cues.json").read_text())


def cue_sheet(who: str) -> dict:
    """agent-04's CUE format (cues/<who>.json: words, on_cam spans with their camera, think beats)."""
    return json.loads((HERE / "cues" / f"{who}.json").read_text())


def frames(who: str) -> int:
    return int(cues(who)["frames"])


def length_s(who: str) -> float:
    return frames(who) / FPS


def line_anim(k: str) -> str:
    return f"{SPEECH}/Anim/AS_exp_{k}"


def mesh_of(who: str, comp: str) -> str:
    got = run(r"""
import json, unreal
from fmbridge.ops.seq import component_of
P = json.loads(PARAMS)
m = component_of(P["label"], P["comp"]).get_skeletal_mesh_asset()
result = m.get_path_name().split(".")[0] if m else ""
""", {"label": LABEL[who], "comp": comp})
    if not got:
        raise SystemExit(f"{LABEL[who]} has no {comp} mesh in the level: is the explainer set open with the presenter?")
    return got


# ------------------------------------------------------------------------------------------------------- lips

def cmd_push(who: str) -> list:
    d = HERE / "audio" / FILM[who]
    files = [d / "vo.wav"] + [HERE / ln["file"] for ln in cues(who)["lines"]]
    return [client().push(str(p), box(who, p.name)) for p in files]


def cmd_solve(who: str, only=None) -> dict:
    mesh = mesh_of(who, "Face")
    out = {}
    for ln in cues(who)["lines"]:
        k = ln["id"]
        if only and k not in only:
            continue
        mood, inten = MOOD.get(ln["beat"], MOOD_DEFAULT)
        r = ok(client().op("speech.to_face", wav=box(who, Path(ln["file"]).name), name=f"exp_{k}", face_mesh=mesh,
                           mood=mood, intensity=inten, process_mask="mouth", head=False, blinks=False,
                           fallback=False, timeout=1800))
        out[k] = {"anim": r["anim"], "timing": r.get("timing"), "options": r.get("options"),
                  "missing": r.get("missing_options")}
        if not (r.get("timing") or {}).get("ok", False):
            print(f"WARNING {k}: timing {r.get('timing')}", file=sys.stderr)
        if r.get("missing_options"):
            print(f"WARNING {k}: missing {r.get('missing_options')} (full-face solve? compose keeps only speech)",
                  file=sys.stderr)
        print(k, json.dumps(out[k]), flush=True)
    keep(who, "solve", out)
    return out


def lines_of(who: str) -> list:
    """lipsync.check's lines: speech onset/offset frames on the sequence clock."""
    return [{"id": ln["id"], "f0": ln["start_f"], "f1": ln["end_f"]} for ln in cues(who)["lines"]]


def reference(who: str) -> list:
    return [{"anim": line_anim(ln["id"]), "frame": ln["file_start_f"]} for ln in cues(who)["lines"]]


def cmd_bias(who: str) -> dict:
    out, bad = {}, []
    for ln in cues(who)["lines"]:
        ref = [{"anim": line_anim(ln["id"]), "frame": ln["file_start_f"]}]
        r = ok(client().op("lipsync.check", anim=line_anim(ln["id"]), anim_frame=ln["file_start_f"],
                           wav=box(who, Path(ln["file"]).name), wav_frame=ln["file_start_f"],
                           lines=[{"id": ln["id"], "f0": ln["start_f"], "f1": ln["end_f"]}], fps=FPS, reference=ref,
                           timeout=600))
        out[ln["id"]] = r["lines"].get(ln["id"])
        if not r["pass"]:
            bad.append({ln["id"]: [i["message"] for i in r["issues"]]})
    lags = [v.get("raw_lag_s", 0.0) for v in out.values() if v]
    res = {"lines": out, "mean_lag_s": round(sum(lags) / max(1, len(lags)), 4), "fails": bad, "pass": not bad}
    keep(who, "bias", res)
    return res


def cmd_compose(who: str) -> dict:
    parts = [{"anim": line_anim(ln["id"]), "frame": ln["file_start_f"]} for ln in cues(who)["lines"]]
    r = ok(client().op("lipsync.compose", parts=parts, out=f"{ANIM}/AS_exp_{who}_solve", start_frame=0,
                       length_frames=frames(who), fps=FPS, skeleton=mesh_of(who, "Face"), fade_frames=3.0,
                       timeout=1800))
    keep(who, "compose", r)
    return r


STAGE_ANIM = {"solve": "AS_exp_{w}_solve", "face": "AS_exp_{w}_face", "final": "AS_exp_{w}_gaze"}


def cmd_check(who: str, stage: str) -> dict:
    if stage == "placed":
        r = ok(client().op("lipsync.check", sequence=SEQ[who], label=LABEL[who], wav=box(who, "vo.wav"),
                           lines=lines_of(who), fps=FPS, reference=reference(who), timeout=600))
    else:
        anim = f"{ANIM}/" + STAGE_ANIM[stage].format(w=who)
        r = ok(client().op("lipsync.check", anim=anim, anim_frame=0, wav=box(who, "vo.wav"), wav_frame=0,
                           lines=lines_of(who), fps=FPS, reference=reference(who), timeout=600))
    keep(who, f"lips_{stage}", r)
    s = {"stage": stage, "pass": r["pass"], "diagnosis": r.get("diagnosis"),
         "lines": {k: [v.get("ref_lag_frames"), v.get("ref_corr"), v.get("lag_frames"), v.get("corr"),
                       v.get("onset_lead_s")] for k, v in r["lines"].items()},
         "silence": r.get("silence") or r.get("silences"), "issues": [i["message"] for i in r["issues"]]}
    return s


# ------------------------------------------------------------------------------------------------------- the body

READ = r"""
import json, unreal
from fmbridge.ops.seq import component_of
APE, AL = unreal.AnimPoseExtensions, unreal.AnimationLibrary
P = json.loads(PARAMS)
comp = component_of(P["label"], "Body")
idle = unreal.load_asset(P["idle"])
pose = APE.get_anim_pose_at_time(idle, 0.0, unreal.AnimPoseEvaluationOptions())
names = [str(comp.get_bone_name(i)) for i in range(comp.get_num_bones())]
tracks = set(str(n) for n in AL.get_animation_track_names(idle))
want = set(P["world"])
parent, local, world = {}, {}, {}
for b in names:
    if b not in tracks and b not in want:
        continue
    p = str(comp.get_parent_bone(b))
    parent[b] = p if p and p != "None" else None
    t = APE.get_bone_pose(pose, b, unreal.AnimPoseSpaces.LOCAL)
    local[b] = {"t": [t.translation.x, t.translation.y, t.translation.z],
                "q": [t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w],
                "s": [t.scale3d.x, t.scale3d.y, t.scale3d.z]}
    w = APE.get_bone_pose(pose, b, unreal.AnimPoseSpaces.WORLD)
    world[b] = {"t": [w.translation.x, w.translation.y, w.translation.z],
                "q": [w.rotation.x, w.rotation.y, w.rotation.z, w.rotation.w]}
m = comp.get_skeletal_mesh_asset()
result = {"parent": parent, "local": local, "world": world, "tracks": sorted(tracks), "n_bones": len(names),
          "mesh": m.get_path_name().split(".")[0] if m else ""}
"""

def gestures(who: str) -> list:
    """The emphasis gestures (gestures.json: per line, the word (its index in the line, or its text) with a hand and
    kind), on the sequence clock in seconds."""
    spec = json.loads((HERE / "gestures.json").read_text())[who]
    by = {ln["id"]: ln for ln in cues(who)["lines"]}
    cs = []
    for g in spec:
        ln = by[g["line"]]
        ws = ln["words"]
        if isinstance(g["word"], int):
            w = ws[g["word"]]
        else:
            m = [x for x in ws if x["w"].strip(".,?!:;").lower() == g["word"].strip(".,?!:;").lower()]
            if not m:
                raise SystemExit(f"gestures.json: {g['word']!r} is not a word of {g['line']}: "
                                 f"{[x['w'] for x in ws]}")
            w = m[0]
        cs.append({"t": w["start"], "hand": g.get("hand"), "kind": g.get("kind", "lift"),
                   "size": g.get("size", 1.0), "hold": g.get("hold", max(0.3, w["end"] - w["start"]))})
    return S.gestures_from_cues(cs)


BODY = r"""
import json, sys, importlib, unreal
from fmbridge.ops.anim import model_keys, new as anim_new
from fmbridge.ops.perf_body import _write_tracks
P = json.loads(PARAMS)
sys.path.insert(0, P["kit_dir"])
import seatkit as S
importlib.reload(S)
def job():
    g = {"PARAMS": json.dumps({"label": P["label"], "idle": P["idle"], "world": P["world"]})}
    exec(P["read"], g)  # one namespace: READ's comprehensions see its names
    data = g["result"]
    yield
    gs = [S.Gesture(**x) for x in P["gestures"]]
    doc, summary = S.build(data, S.Set(**P["set"]), S.Style(**P["style"]), gs, P["length_s"], P["fps"])
    yield
    if P.get("probe") or (not summary["pass"] and not P["force"]):  # probe: read and solve only, nothing written
        return {"pass": summary["pass"], "summary": summary, "written": False}
    anim_new(path=P["out"], skeleton=data["mesh"], length_s=doc["length_s"], fps=doc["fps"], replace=True)
    a = unreal.load_asset(P["out"])
    n = model_keys(a)
    tracks = {b: [(v["t"], v["q"], v["s"])] * n for b, v in doc["const"].items()}
    for b, ks in doc["keyed"].items():
        if len(ks) != n:
            ks = [ks[min(len(ks) - 1, int(round(i * (len(ks) - 1) / max(1, n - 1))))] for i in range(n)]
        tracks[b] = [(k["t"], k["q"], k["s"]) for k in ks]
    yield
    _write_tracks(a, tracks, n)
    unreal.EditorAssetLibrary.save_asset(P["out"])
    return {"pass": summary["pass"], "summary": summary, "written": True, "out": P["out"], "keys": n,
            "bones": len(tracks), "mesh": data["mesh"]}
result = job()
"""

WORLD_BONES = list(S.REQUIRED) + [f"{f}_{j}_{s}" for f in ("index", "middle", "ring", "pinky", "thumb")
                                  for j in ("01", "02", "03") for s in "lr"]


def body_params(who: str) -> dict:
    return {"set": dict(SET.__dict__), "style": {k: (list(v) if isinstance(v, tuple) else v)
                                                 for k, v in STYLE[who].__dict__.items()},
            "gestures": [g.__dict__ for g in gestures(who)], "length_s": length_s(who), "fps": 30}


def cmd_body(who: str, force: bool = False) -> dict:
    """The seated body, built ON THE BOX (seatkit pushed next to the WAVs): the skeleton read there, the pose solved
    and checked there, AS_exp_<who>_seat written; only the check's numbers come back."""
    kit = box(who, "kit")
    client().push(str(HERE / "seatkit.py"), box(who, "kit", "seatkit.py"))
    r = run(BODY, {"kit_dir": kit, "read": READ, "label": LABEL[who], "idle": IDLE, "world": WORLD_BONES,
                   "out": f"{ANIM}/AS_exp_{who}_seat", "force": force, **body_params(who)}, 1800)
    keep(who, "body_check", r["summary"])
    if not r.get("written"):
        raise SystemExit(f"the seated pose fails its own check (nothing written): {r['summary']['issues'][:5]} "
                         f"{r['summary']['rest']['issues'][:5]}")
    return {"anim": r["out"], "keys": r["keys"], "bones": r["bones"], "pass": r["pass"],
            "rest": {k: r["summary"]["rest"][k] for k in ("hips", "knees", "elbows", "wrists", "head", "issues")},
            "wrist_ext": r["summary"]["wrist_ext"], "yaw_off": r["summary"]["yaw_off"]}


def cmd_calibrate_body(who: str) -> dict:
    return ok(client().op("perf.calibrate_body", label=LABEL[who], timeout=900))


def cmd_life(who: str) -> dict:
    r = ok(client().op("anim.body_life", out=f"{ANIM}/AS_exp_{who}_life", body_mesh=mesh_of(who, "Body"),
                       length_s=round(length_s(who), 3), seed=SEED[who], timeout=600, **LIFE))
    keep(who, "life", r)
    return r


# ------------------------------------------------------------------------------------------------------- the stage

WORKSEQ = r"""
import json, unreal
from fmbridge.ops.assets import free
EAL = unreal.EditorAssetLibrary
LSE = unreal.LevelSequenceEditorBlueprintLibrary
P = json.loads(PARAMS)
if not EAL.does_asset_exist(P["src"]):
    raise RuntimeError(f"no {P['src']}: agent-07's explainer sequence must exist first")
if LSE.get_current_level_sequence():
    LSE.close_level_sequence()
if EAL.does_asset_exist(P["dst"]):
    if not P["fresh"]:
        result = {"sequence": P["dst"], "made": False}
    else:
        free(P["dst"])
if not EAL.does_asset_exist(P["dst"]):
    EAL.duplicate_asset(P["src"], P["dst"])
    EAL.save_asset(P["dst"])
    result = {"sequence": P["dst"], "made": True}
"""


def cmd_workseq(who: str, fresh: bool = False) -> dict:
    return run(WORKSEQ, {"src": SEQ[who], "dst": WORK[who], "fresh": fresh})


CAMS = r"""
import json, unreal
from fmbridge.ops._util import find_actor
P = json.loads(PARAMS)
a = find_actor(P["label"])
if a is None:
    raise RuntimeError(f"no actor {P['label']}")
xf = a.get_actor_transform()
out = {"actor": {"loc": [xf.translation.x, xf.translation.y, xf.translation.z],
                 "yaw": a.get_actor_rotation().yaw}, "cams": {}}
for c in P["cams"]:
    x = find_actor(c)
    if x is None:
        out["cams"][c] = None
        continue
    l = xf.inverse_transform_location(x.get_actor_location())
    out["cams"][c] = [l.x, l.y, l.z]
result = out
"""


def cmd_cams(who: str) -> dict:
    """Each on-camera camera's direction from the seated eyes, in the character's frame (yaw + = their LEFT, as
    perf.face takes it; pitch + = up). The eyes: the seated head's actor-frame position (body_check) + 9 cm forward,
    3 up (round 4's mid-eye offset on these rigs, close enough: gaze_lock solves the eyes on the real bones)."""
    cams = sorted({c for *_, c in cue_sheet(who)["on_cam"]})
    got = run(CAMS, {"label": LABEL[who], "cams": cams})
    bc = json.loads((OUT / who / "body_check.json").read_text())
    h = bc["rest"]["head"]
    eye = [h[0] + 9.0, h[1], h[2] + 3.0]
    out = {}
    for c, p in got["cams"].items():
        if p is None:
            out[c] = None
            continue
        # actor-local from inverse_transform_location: x forward, y = the actor's +Y (the presenter's LEFT? see
        # SET: studio +Y is her left with yaw 0, and actor-local y follows it)
        d = [p[0] - eye[0], p[1] - (-eye[1]), p[2] - eye[2]]  # eye[1] is in "right" units: actor-local y = -right
        yaw = math.degrees(math.atan2(d[1], d[0]))  # + = toward actor +Y = the presenter's left
        pitch = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
        out[c] = {"yaw": round(yaw, 2), "pitch": round(pitch, 2), "dist_cm": round(math.hypot(*d), 1),
                  "local": [round(x, 1) for x in p]}
    res = {"eye_actor": eye, "cams": out, "actor": got["actor"]}
    missing = [c for c, v in out.items() if v is None]
    if missing:
        res["issues"] = [f"cameras not in the level: {missing}"]
    keep(who, "cams", res)
    return res


# ------------------------------------------------------------------------------------------------------- the face

HEAD_SHARE = 0.65  # of a camera's direction the head takes; the eyes the rest (gaze_lock makes them exact)


def face_args(who: str) -> dict:
    """agent-04's head plan (head_plans/<who>.json: yaw 0 = straight ahead) turned to each shot's camera: every gaze
    shift gets the camera direction of the on-camera span it falls in (or the next one: between spans the presenter
    is off screen), and a shift is added at each span start whose camera direction changes."""
    plan = json.loads((HERE / "head_plans" / f"{who}.json").read_text())
    cams = json.loads((OUT / who / "cams.json").read_text())["cams"]
    on = cue_sheet(who)["on_cam"]

    def cam_at(t):
        for a, b, c in on:
            if a <= t < b:
                return c
        later = [x for x in on if x[0] > t]
        return (later[0] if later else on[-1])[2]

    def dirn(c):
        v = cams.get(c) or cams.get(c.replace("_L", "")) or {"yaw": 0.0, "pitch": 0.0}
        return v["yaw"], v["pitch"]

    gaze = []
    for g in plan["gaze"]:
        y0, p0 = dirn(cam_at(g["t"]))
        gaze.append({**g, "yaw": round(g["yaw"] + y0, 2), "pitch": round(g["pitch"] + p0, 2),
                     "head": g.get("head", 1.0) * (HEAD_SHARE if g.get("scan") == "lens" else 1.0)})
    prev = None
    for a, b, c in on:
        d = dirn(c)
        if prev is not None and (abs(d[0] - prev[0]) > 1.5 or abs(d[1] - prev[1]) > 1.5):
            # turn over the off-screen gap if there is one, else on the cut (a presenter re-finding the lens)
            t = max(0.0, a - 0.5) if not any(x[1] == a for x in on) else a
            if not any(abs(x["t"] - t) < 0.3 for x in gaze):
                gaze.append({"t": round(t, 3), "yaw": d[0], "pitch": d[1], "scan": "lens", "head": HEAD_SHARE})
        prev = d
    gaze.sort(key=lambda x: x["t"])
    y, p = dirn(on[0][2])
    args = {k: v for k, v in plan.items() if k not in ("gaze", "start_gaze", "glances")}
    args.update({"gaze": gaze, "start_gaze": [y, p]})
    if SPEECH_GAIN.get(who, 1.0) != 1.0:
        args["speech_gain"] = [[0.0, round(length_s(who), 3), SPEECH_GAIN[who]]]
    return args


def cmd_face(who: str) -> dict:
    args = face_args(who)
    keep(who, "face_args", args)
    r = ok(client().op("perf.face", anim=f"{ANIM}/AS_exp_{who}_solve", out=f"{ANIM}/AS_exp_{who}_face",
                       wav=box(who, "vo.wav"), timeout=1800, **args))
    keep(who, "face", r)
    return {"out": r.get("out"), "report": r.get("report"), "curves": r.get("curves")}


def cmd_sync(who: str) -> dict:
    """The reel's sync on the seated body: the face rides the body with its head control on, the body takes the head
    motion that makes, the shared skeleton is baked back onto the face; then perf.face's planned head turn goes on the
    body (on 5.8 the face takes its neck from the body)."""
    c = client()
    path, lab = WORK[who], LABEL[who]
    face, seat = f"{ANIM}/AS_exp_{who}_face", f"{ANIM}/AS_exp_{who}_seat"
    n = frames(who)
    ok(c.op("seq.anim", path=path, label=lab, component="Body", sections=[{"anim": seat, "start": 0, "end": n,
                                                                          "loop": False}]))
    ok(c.op("seq.anim", path=path, label=lab, component="Face", sections=[{"anim": face, "start": 0, "end": n,
                                                                          "loop": False}]))
    a = ok(c.op("anim.bake_follow", sequence=path, actor_label=lab, anim=face, out=f"{ANIM}/AS_exp_{who}_follow",
                head_control=True, timeout=3600))
    b = ok(c.op("anim.head_to_body", sequence=path, actor_label=lab, body_anim=seat, out=f"{ANIM}/AS_exp_{who}_body",
                timeout=3600))
    ok(c.op("seq.set_anim", path=path, component="Body", anim=f"{ANIM}/AS_exp_{who}_body", label=lab))
    d = ok(c.op("anim.bake_follow", sequence=path, actor_label=lab, anim=face, out=f"{ANIM}/AS_exp_{who}_follow",
                timeout=3600))
    e = ok(c.op("perf.turn_head", anim=f"{ANIM}/AS_exp_{who}_body", face_anim=face, timeout=900))
    ok(c.op("seq.set_anim", path=path, component="Face", anim=f"{ANIM}/AS_exp_{who}_follow", label=lab))
    res = {"follow_head": a, "body": b, "follow": d, "turn": e}
    keep(who, "sync", res)
    return res


def cmd_gaze(who: str) -> dict:
    """The eyes on each on-camera span's camera, one span at a time, each pass on the last one's output (in place
    after the first). Off-screen frames keep perf.face's eyes."""
    c = client()
    path, lab = WORK[who], LABEL[who]
    src, out = f"{ANIM}/AS_exp_{who}_follow", f"{ANIM}/AS_exp_{who}_gaze"
    ok(c.op("seq.set_anim", path=path, component="Face", anim=src, label=lab))
    res = []
    first = True
    for a, b, cam in cue_sheet(who)["on_cam"]:
        f0, f1 = int(round(a * FPS)), int(round(b * FPS)) - 1
        r = ok(c.op("anim.gaze_lock", sequence=path, actor_label=lab, anim=src if first else out, out=out,
                    target=cam, frames=[f0, f1], timeout=3600))
        first = False
        res.append({"span": [f0, f1], "camera": cam, "passes": r.get("passes"), "frames": r.get("frames"),
                    "head_to_lens": r.get("head_to_lens_deg")})
        print(json.dumps(res[-1]), flush=True)
    keep(who, "gaze", res)
    return {"spans": res}


def cmd_preview(who: str, seq: str = "") -> list:
    """Only the seated body on the sequence (for the set's first stills, before the face exists): Body = the seat
    animation (+ the life layer when it exists); the Face track is left as it is."""
    path = seq or SEQ[who]
    n = frames(who)
    life = f"{ANIM}/AS_exp_{who}_life"
    have = ok(client().exec_code(f"import unreal\nresult = unreal.EditorAssetLibrary.does_asset_exist({life!r})"))
    secs = [{"anim": f"{ANIM}/AS_exp_{who}_seat", "start": 0, "end": n, "loop": False}]
    if have:
        secs.append({"anim": life, "start": 0, "end": n, "loop": False, "row": 2})
    return ok(client().op("seq.anim", path=path, label=LABEL[who], component="Body", sections=secs))


def cmd_place(who: str, seq: str = "") -> list:
    path = seq or SEQ[who]
    n = frames(who)
    c = client()
    out = [ok(c.op("seq.anim", path=path, label=LABEL[who], component="Face",
                   sections=[{"anim": f"{ANIM}/AS_exp_{who}_gaze", "start": 0, "end": n, "loop": False}])),
           ok(c.op("seq.anim", path=path, label=LABEL[who], component="Body", sections=[
               {"anim": f"{ANIM}/AS_exp_{who}_body", "start": 0, "end": n, "loop": False},
               {"anim": f"{ANIM}/AS_exp_{who}_life", "start": 0, "end": n, "loop": False, "row": 2}]))]
    keep(who, "place", out)
    return out


# ------------------------------------------------------------------------------------------------------- body check

BODY_BONES = ["pelvis", "thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r", "spine_05", "head",
              "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r", "middle_03_l",
              "middle_03_r", "index_03_l", "index_03_r", "thumb_03_l", "thumb_03_r"]


def breath(t: list, z: list) -> dict:
    """Breaths per minute and the median rise (mm) of a sternum height trace: peaks of the smoothed, detrended
    signal at least 1.6 s apart."""
    import numpy as np
    x = np.asarray(z, float)
    if len(x) < 10:
        return {"per_min": None, "amp_mm": None}
    k = 5
    xs = np.convolve(x, np.ones(k) / k, mode="same")
    trend = np.convolve(xs, np.ones(61) / 61, mode="same") if len(xs) > 61 else np.full_like(xs, xs.mean())
    y = xs - trend
    dt = (t[-1] - t[0]) / (len(t) - 1)
    gap = int(1.6 / dt)
    peaks, troughs = [], []
    for i in range(1, len(y) - 1):
        if y[i] >= y[i - 1] and y[i] > y[i + 1] and (not peaks or i - peaks[-1] >= gap):
            peaks.append(i)
    amps = []
    for a, b in zip(peaks, peaks[1:]):
        lo = int(np.argmin(y[a:b])) + a
        troughs.append(lo)
        amps.append((y[a] + y[b]) / 2 - y[lo])
    span = t[peaks[-1]] - t[peaks[0]] if len(peaks) > 1 else 0.0
    return {"per_min": round(60.0 * (len(peaks) - 1) / span, 2) if span > 0 else None,
            "amp_mm": round(10.0 * float(np.median(amps)), 2) if amps else None, "cycles": len(peaks) - 1}


def cmd_bodycheck(who: str, seq: str = "", every: int = 2) -> dict:
    """What the sequence plays, in the actor's frame: every BODY_BONES position against the desk, seat, floor and
    mic (seatkit.check's rules on the real bones), the posed hips/knees/wrists against seatkit's prediction (proves
    the conventions on this rig), and the breathing (sternum = spine_05 height) for agent-09's body rows."""
    path = seq or SEQ[who]
    n = frames(who)
    fr = list(range(0, n, every))
    c = client()
    m = ok(c.op("seq.sample", path=path, actor_label=LABEL[who], component="Body", bones=BODY_BONES, frames=fr,
                ticks=2, timeout=3600))
    act = run(CAMS, {"label": LABEL[who], "cams": []})["actor"]
    yaw = math.radians(act["yaw"])
    fx, fy = math.cos(yaw), math.sin(yaw)

    def to_actor(p):  # world -> [x forward, y RIGHT, z up from the actor origin]
        dx, dy, dz = p[0] - act["loc"][0], p[1] - act["loc"][1], p[2] - act["loc"][2]
        return [dx * fx + dy * fy, dx * -fy + dy * fx, dz]

    st = SET
    issues, worst = [], {}
    sz = []
    for i, f in enumerate(fr):
        A = {b: to_actor(m["bones"][b][i][:3]) for b in BODY_BONES if b in m["bones"]}
        sz.append(A["spine_05"][2])
        for s in "lr":
            for b in (f"hand_{s}", f"middle_03_{s}", f"index_03_{s}", f"thumb_03_{s}", f"lowerarm_{s}"):
                p = A.get(b)
                if p is None:
                    continue
                if st.desk_near <= p[0] <= st.desk_far and p[2] < st.desk_top + (0.4 if "_03_" in b else 2.0):
                    issues.append({"code": "desk.through", "frame": f, "bone": b, "z": round(p[2], 1)})
                if st.mic and S.norm(S.sub(p, st.mic)) < st.mic_radius:
                    issues.append({"code": "mic.hand", "frame": f, "bone": b})
                if st.boom and S.poly_dist(p, st.boom) < st.boom_radius:
                    issues.append({"code": "mic.boom", "frame": f, "bone": b})
            k = A[f"calf_{s}"]
            if k[2] > st.desk_under - 6.0 and k[0] > st.desk_near:
                issues.append({"code": "desk.knee", "frame": f, "bone": f"calf_{s}", "z": round(k[2], 1)})
        hips = [(A["thigh_l"][j] + A["thigh_r"][j]) / 2 for j in range(3)]
        worst["hip_z"] = [min(worst.get("hip_z", [1e9, 0])[0], hips[2]), max(worst.get("hip_z", [0, -1e9])[1], hips[2])]
    pred = json.loads((OUT / who / "body_check.json").read_text())["rest"]
    first = {b: to_actor(m["bones"][b][0][:3]) for b in BODY_BONES if b in m["bones"]}
    hips0 = [(first["thigh_l"][j] + first["thigh_r"][j]) / 2 for j in range(3)]
    vs = {"hips": [round(a - b, 1) for a, b in zip(hips0, pred["hips"])],
          "wrist_l": [round(a - b, 1) for a, b in zip(first["hand_l"], pred["wrists"]["l"])],
          "wrist_r": [round(a - b, 1) for a, b in zip(first["hand_r"], pred["wrists"]["r"])],
          "knee_l": [round(a - b, 1) for a, b in zip(first["calf_l"], pred["knees"]["l"])]}
    far = [k for k, v in vs.items() if max(abs(x) for x in v) > 3.0]
    if far:
        issues.append({"code": "body.not_as_solved", "message": f"{far} > 3 cm from seatkit's pose (breathing and the "
                       f"head turn move them by < 1 cm): a convention differs on this rig", "delta": vs})
    br = breath([f / FPS for f in fr], sz)
    numbers = {"body.breath_cycles_per_min": br["per_min"], "body.breath_amp_mm": br["amp_mm"],
               "body.desk_through": sum(1 for x in issues if x["code"] == "desk.through"),
               "body.mic_touch": sum(1 for x in issues if x["code"].startswith("mic.")),
               "body.knee_desk": sum(1 for x in issues if x["code"] == "desk.knee")}
    res = {"numbers": numbers, "vs_seatkit_cm": vs, "hip_z_range": worst.get("hip_z"), "breath": br,
           "issues": issues[:40], "n_issues": len(issues), "pass": not issues}
    keep(who, "bodycheck", res)
    d = HERE / "numbers" / FILM[who]
    d.mkdir(parents=True, exist_ok=True)
    (d / "body.json").write_text(json.dumps({"source": f"perform.py bodycheck --who {who} on {path}",
                                             "numbers": numbers}, indent=1))
    return res


STEPS = ["push", "solve", "bias", "compose", "check:solve", "workseq", "body", "cams", "life", "face", "check:face",
         "sync", "gaze", "check:final", "place", "check:placed", "bodycheck"]


def step(name: str, who: str, a) -> dict:
    if name.startswith("check:"):
        r = cmd_check(who, name.split(":")[1])
    else:
        r = {"push": lambda: cmd_push(who), "solve": lambda: cmd_solve(who, a.only), "bias": lambda: cmd_bias(who),
             "compose": lambda: cmd_compose(who), "workseq": lambda: cmd_workseq(who, a.fresh),
             "body": lambda: cmd_body(who, a.force), "cams": lambda: cmd_cams(who), "life": lambda: cmd_life(who),
             "face": lambda: cmd_face(who), "sync": lambda: cmd_sync(who), "gaze": lambda: cmd_gaze(who),
             "place": lambda: cmd_place(who, a.seq), "preview": lambda: cmd_preview(who, a.seq), "bodycheck": lambda: cmd_bodycheck(who, a.seq),
             "calibrate_body": lambda: cmd_calibrate_body(who)}[name]()
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["push", "solve", "bias", "compose", "check", "workseq", "cams", "body", "life",
                                    "calibrate_body", "face", "sync", "gaze", "place", "preview", "bodycheck", "all", "dry"])
    ap.add_argument("--who", required=True, choices=list(FILM))
    ap.add_argument("--stage", default="solve", choices=["solve", "face", "final", "placed"])
    ap.add_argument("--only", type=lambda s: s.split(","))
    ap.add_argument("--seq", default="")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--force", action="store_true", help="body: write even if the pose fails its own check")
    ap.add_argument("--from", dest="start", default="push")
    ap.add_argument("--to", dest="stop", default="bodycheck")
    a = ap.parse_args()
    if a.cmd == "dry":  # engine-free: the seated pose on a saved read (body_read.json) + the face args
        data = json.loads((OUT / a.who / "body_read.json").read_text())
        bp = body_params(a.who)
        doc, summary = S.build(data, S.Set(**bp["set"]), S.Style(**bp["style"]),
                               [S.Gesture(**g) for g in bp["gestures"]], bp["length_s"], bp["fps"])
        print(json.dumps(summary, indent=1))
        return
    if a.cmd == "all":
        i0, i1 = STEPS.index(a.start), STEPS.index(a.stop)
        for name in STEPS[i0:i1 + 1]:
            r = step(name, a.who, a)
            print(name, json.dumps(r)[:2000], flush=True)
            if isinstance(r, dict) and r.get("pass") is False:
                raise SystemExit(f"{name} failed: see out/explainers/perf/{a.who}/")
        return
    if a.cmd == "check":
        r = cmd_check(a.who, a.stage)
        print(json.dumps(r, indent=1))
        raise SystemExit(0 if r["pass"] else 1)
    r = step(a.cmd, a.who, a)
    print(json.dumps(r, indent=1))
    if isinstance(r, dict) and r.get("pass") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
