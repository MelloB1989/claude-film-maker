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
SET = S.Set(seat_top=45.0, seat_front=24.5, desk_top=74.0, desk_near=18.0, desk_far=73.0, desk_under=63.4,
            mic=[24.0, -14.0, 99.0], mic_radius=9.0,
            boom=[[50.0, -52.6, 74.0], [43.8, -42.9, 119.3], [29.5, -20.4, 103.4], [24.0, -14.0, 99.0]])
# ^ agent-07's set after the orchestrator's r3 notes (07 Nov ~18:3x IST): desk in (studio x 38..93), the mic mirrored
#   to the presenter's LEFT (studio -Y), the cameras on her right (studio +Y, azimuth +17..+24)
# How each sits (seatkit.Style). The cameras are at studio +Y (azimuth +17..+24): facing +X in Unreal that is the
# presenter's RIGHT-front (the mic is on their left). The chest
# turns a little toward them, the head and eyes do the rest (face + gaze).
STYLE = {  # forearms resting on the desk (the orchestrator, r3 stills): elbows planted ~2 cm in from the near edge,
    #          the chest square to the desk (a turn pulls the camera-side elbow off it), hands on their little-finger
    #          edge, shoulders down
    "her": S.Style(lean=19.0, twist=0.0, hip_above_seat=11.0, knee_out=3.0, foot_out=6.0, pronation=75.0, shin_tilt=6.0, elbow_out=3.0,
                   clavicle_fwd=4.0, clavicle_drop=4.0),
    "him": S.Style(lean=18.0, twist=0.0, knee_out=8.0, foot_out=9.0, pronation=72.0, elbow_out=3.0,
                   clavicle_fwd=5.0, clavicle_drop=3.0),
}

# The line solves' moods (speech.to_face): measured and calm, a little brighter on the hook and the close.
MOOD = {"hook": ("CONFIDENCE", 0.8), "close": ("CONFIDENCE", 0.8)}
MOOD_DEFAULT = ("CONFIDENCE", 0.65)
SPEECH_GAIN = {"him": 1.7, "her": 1.0}  # the reel's: his rig gives little mouth travel (r4)
# Each line's mouth is placed this many frames BEFORE its WAV's place: the solver opens the jaw 0.04-0.09 s AFTER the
# first sound (box B, her 16 lines alone vs their own WAVs), people open it 100-300 ms before (Chandrasekaran 2009);
# the orchestrator's bar is 0-2 frames before. Measured on her 16 composed lines (compose's 3-frame fade-in delays
# the rise ~1 f): lead 0 -> 0.9-2.2 f LATE, 3 -> 0.9-2.2 f early, 2.5 -> ~0.4-1.7 f early.
LEAD_FRAMES = 2.5
# body life on a seated body: calm breathing that shows (agent-09's breath rows: 8-22 /min, >= 2 mm sternum rise),
# almost no weight shift (the seat holds the pelvis), no torso follow (r5: it rode the blinks)
LIFE = {"state": "talk", "breath_deg": 1.35, "clavicle_deg": 1.0, "shift_cm": 0.25, "follow": 0.0}
# (box B, 07 Nov: breath_deg 0.9 / clavicle 0.8 gave 14.1 breaths/min at 1.6 mm sternum rise; agent-09's line is >= 2)


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
                  "missing": r.get("missing_options"), "sha256": __import__("hashlib").sha256(
                      (HERE / ln["file"]).read_bytes()).hexdigest()}
        if not (r.get("timing") or {}).get("ok", False):
            print(f"WARNING {k}: timing {r.get('timing')}", file=sys.stderr)
        if r.get("missing_options"):
            print(f"WARNING {k}: missing {r.get('missing_options')} (full-face solve? compose keeps only speech)",
                  file=sys.stderr)
        print(k, json.dumps(out[k]), flush=True)
    old = json.loads((OUT / who / "solve.json").read_text()) if (OUT / who / "solve.json").exists() else {}
    keep(who, "solve", {**old, **out})
    return out


def lines_of(who: str) -> list:
    """lipsync.check's lines: speech onset/offset frames on the sequence clock."""
    return [{"id": ln["id"], "f0": ln["start_f"], "f1": ln["end_f"]} for ln in cues(who)["lines"]]


def reference(who: str) -> list:
    """Each line's own solve where the face plays it (its WAV's place, LEAD_FRAMES earlier): the strict reference."""
    return [{"anim": line_anim(ln["id"]), "frame": ln["file_start_f"] - LEAD_FRAMES} for ln in cues(who)["lines"]]


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
    parts = reference(who)
    r = ok(client().op("lipsync.compose", parts=parts, out=f"{ANIM}/AS_exp_{who}_solve", start_frame=0,
                       length_frames=frames(who), fps=FPS, skeleton=mesh_of(who, "Face"), fade_frames=3.0,
                       timeout=1800))
    keep(who, "compose", r)
    return r


CHECK = r"""
import json, sys, importlib.util
import fmbridge.ops.lipsync as OL
P = json.loads(PARAMS)
spec = importlib.util.spec_from_file_location("fmbridge.perfkit.lipsync_r6", P["kit"])
m = importlib.util.module_from_spec(spec)
m.__package__ = "fmbridge.perfkit"
spec.loader.exec_module(m)
old = OL.LS
OL.LS = m  # this one call only: the bridge's own perfkit is left as installed
try:
    result = OL.check(**P["args"])
finally:
    OL.LS = old
"""


def lipcheck(who: str, **args) -> dict:
    """lipsync.check with this tree's perfkit.lipsync (pushed beside the WAVs): r6's onset window stops at the line
    before (0.34 s gaps read the previous line's mouth as this one opening 1.0 s early: box B, 07 Nov). Until the core
    fix is installed on the boxes; then it is the same as client.op("lipsync.check")."""
    client().push(str(ROOT / "unreal" / "fmbridge" / "perfkit" / "lipsync.py"), box(who, "kit", "lipsync_r6.py"))
    return run(CHECK, {"kit": box(who, "kit", "lipsync_r6.py"), "args": args}, 900)


STAGE_ANIM = {"solve": "AS_exp_{w}_solve", "face": "AS_exp_{w}_face", "final": "AS_exp_{w}_gaze"}


def cmd_check(who: str, stage: str) -> dict:
    if stage == "placed":
        r = lipcheck(who, sequence=SEQ[who], label=LABEL[who], wav=box(who, "vo.wav"), lines=lines_of(who), fps=FPS,
                     reference=reference(who))
    else:
        anim = f"{ANIM}/" + STAGE_ANIM[stage].format(w=who)
        r = lipcheck(who, anim=anim, anim_frame=0, wav=box(who, "vo.wav"), wav_frame=0, lines=lines_of(who), fps=FPS,
                     reference=reference(who))
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
keep_ = set(b for b in names if b in tracks or b in set(P["world"]))
parent = {}
for b in names:
    p = str(comp.get_parent_bone(b))
    parent[b] = p if p and p != "None" else None
for b in list(keep_):  # every ancestor too: the pose is put together by FK from the root
    p = parent.get(b)
    while p and p not in keep_:
        keep_.add(p)
        p = parent.get(p)
# r6: the idle's ROTATIONS on the MESH's own bone lengths (its reference translations). AnimPose evaluates on the
# skeleton asset's reference, whose bones are shorter than this body's (her thigh 40.2 vs 43.5 cm); the rendered
# body keeps its own lengths, and adds (mesh ref - skeleton ref) to the pelvis's animated translation (box B,
# 07 Nov: commanded 57.48 + 7.48 = 64.96 measured). seatkit.build writes every translation as wanted - that.
local, skel_t = {}, {}
for b in names:
    if b not in keep_:
        continue
    t = APE.get_bone_pose(pose, b, unreal.AnimPoseSpaces.LOCAL)
    r = comp.get_ref_pose_transform(comp.get_bone_index(b))
    local[b] = {"t": list(r.translation.to_tuple()), "q": [t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w],
                "s": [t.scale3d.x, t.scale3d.y, t.scale3d.z]}
    skel_t[b] = list(APE.get_ref_bone_pose(pose, b, unreal.AnimPoseSpaces.LOCAL).translation.to_tuple())
m = comp.get_skeletal_mesh_asset()
result = {"parent": {b: parent[b] for b in local}, "local": local, "skel_t": skel_t, "tracks": sorted(tracks),
          "n_bones": len(names), "mesh": m.get_path_name().split(".")[0] if m else "", "world": None}
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
    # small settles where nothing is scripted for SETTLE_GAP s: a hand re-sets a little on the longest word there
    # (a seated speaker's hands are never frozen for long), alternating hands, the mic side smaller
    words = [w for ln in cues(who)["lines"] for w in ln["words"]]
    marks = sorted(c["t"] for c in cs)
    edges = [0.0] + marks + [length_s(who)]
    side = "l"
    for a, b in zip(edges, edges[1:]):
        t = a + SETTLE_GAP
        while t < b - 2.0:
            pool = [w for w in words if t - 1.5 <= w["start"] <= t + 1.5]
            if pool:
                w = max(pool, key=lambda w: w["end"] - w["start"])
                cs.append({"t": w["start"], "hand": side, "kind": "beat", "size": 0.35 if side == "r" else 0.25,
                           "hold": 0.3})
                side = "r" if side == "l" else "l"
            t += SETTLE_GAP
    return S.gestures_from_cues(cs)


SETTLE_GAP = 5.5


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


def set_of(who: str) -> S.Set:
    """The set for `who`: SET (her r3 set, agent-07) with any field overridden by set_<who>.json next to this file
    (agent-07 commits his: the mic is aimed at his mouth, so its capsule and arm move). Actor frame: x forward from the
    chair mark, y the presenter's right (studio y + 20), z up from the floor."""
    p = HERE / f"set_{who}.json"
    if not p.exists():
        return SET
    return S.Set(**{**SET.__dict__, **json.loads(p.read_text())})


def body_params(who: str) -> dict:
    return {"set": dict(set_of(who).__dict__), "style": {k: (list(v) if isinstance(v, tuple) else v)
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
            "wrist_ext": r["summary"]["wrist_ext"], "yaw_off": r["summary"]["yaw_off"],
            "tuned": r["summary"].get("tuned")}


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
from fmbridge.ops.seq import component_of
P = json.loads(PARAMS)
a = find_actor(P["label"])
if a is None:
    raise RuntimeError(f"no actor {P['label']}")
body = component_of(P["label"], "Body")
xf = body.get_world_transform()  # the body's component space = seatkit's frame (forward/right read from the bones)
out = {"actor": {"loc": list(a.get_actor_location().to_tuple()), "yaw": a.get_actor_rotation().yaw},
       "body": {"loc": list(xf.translation.to_tuple()), "yaw": xf.rotation.rotator().yaw}, "cams": {}}
for c in P["cams"]:
    x = find_actor(c)
    out["cams"][c] = list(xf.inverse_transform_location(x.get_actor_location()).to_tuple()) if x else None
result = out
"""


def cmd_cams(who: str) -> dict:
    """Each on-camera camera's direction from the seated eyes, in the character's frame (yaw + = their LEFT, as
    perf.face takes it; pitch + = up). The eyes: the seated head's actor-frame position (body_check) + 9 cm forward,
    3 up (round 4's mid-eye offset on these rigs, close enough: gaze_lock solves the eyes on the real bones)."""
    cams = sorted({c for *_, c in cue_sheet(who)["on_cam"]})
    got = run(CAMS, {"label": LABEL[who], "cams": cams})
    bc = json.loads((OUT / who / "body_check.json").read_text())
    fw, rt = bc["frame"]["fwd"], bc["frame"]["right"]
    h = bc["rest"]["head"]
    eye = [h[0] + 9.0, h[1], h[2] + 3.0]  # [forward, right, up]
    out = {}
    for c, p in got["cams"].items():
        if p is None:
            out[c] = None
            continue
        a_ = [S.dot(p, fw), S.dot(p, rt), p[2]]  # component-local -> [forward, right, up]
        d = [a_[0] - eye[0], a_[1] - eye[1], a_[2] - eye[2]]
        yaw = math.degrees(math.atan2(-d[1], d[0]))  # + = the presenter's LEFT (perf.face's convention)
        pitch = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
        out[c] = {"yaw": round(yaw, 2), "pitch": round(pitch, 2), "dist_cm": round(math.sqrt(sum(x * x for x in d)), 1),
                  "char": [round(x, 1) for x in a_]}
    res = {"eye_actor": eye, "cams": out, "actor": got["actor"]}
    missing = [c for c, v in out.items() if v is None]
    issues = [f"cameras not in the level: {missing}"] if missing else []
    # agent-04: a DIRECT cut (presenter to presenter) whose lens direction moves > 10 deg makes the eyes jump on
    # screen: move a camera instead (agent-07), before the face step
    on = cue_sheet(who)["on_cam"]
    jumps = []
    for (a0, b0, c0), (a1, b1, c1) in zip(on, on[1:]):
        if abs(b0 - a1) < 1e-3 and out.get(c0) and out.get(c1):
            d = math.hypot(out[c1]["yaw"] - out[c0]["yaw"], out[c1]["pitch"] - out[c0]["pitch"])
            jumps.append({"t": round(a1, 3), "from": c0, "to": c1, "deg": round(d, 1)})
    res["direct_cuts"] = jumps
    big = [j for j in jumps if j["deg"] > 10.0]
    if big:
        issues.append(f"direct cuts with a lens move > 10 deg (move a camera before the face step): {big}")
    if issues:
        res["issues"] = issues
    res["pass"] = not issues
    keep(who, "cams", res)
    return res


# ------------------------------------------------------------------------------------------------------- the face

def face_args(who: str) -> dict:
    """agent-04's head plan made camera-aware by head.py itself (cue["cams"] = cams step's directions from the seated
    eyes): glances off the active lens, re-aims mid-gap or on a direct cut, no blink on any gaze move. Nothing is added
    here but the mouth gain for him."""
    import head as HD
    cams = json.loads((OUT / who / "cams.json").read_text())["cams"]
    cue = {**cue_sheet(who), "cams": {c: [v["yaw"], v["pitch"]] for c, v in cams.items() if v}}
    args = HD.face_args(cue, who)
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
    res = {"follow_head": a, "body": b, "follow": d, "turn": e, "leaders": lead(who)}
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


def lead(who: str) -> dict:
    """Every garment back on leader pose to the body (they drop after sequence/animation work: box B, 07 Nov), then
    the check: exit on a garment that still does not follow."""
    ok(client().op("mh.leader", label=LABEL[who]))
    r = ok(client().op("mh.leader_check", label=LABEL[who]))
    if not r.get("pass"):
        raise SystemExit(f"garments not following {LABEL[who]}'s body: {r.get('why')}")
    return {"pass": True, "metric": r.get("metric")}


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
    r = ok(client().op("seq.anim", path=path, label=LABEL[who], component="Body", sections=secs))
    return {"sections": r, "leaders": lead(who)}


def cmd_place(who: str, seq: str = "") -> list:
    path = seq or SEQ[who]
    n = frames(who)
    c = client()
    out = [ok(c.op("seq.anim", path=path, label=LABEL[who], component="Face",
                   sections=[{"anim": f"{ANIM}/AS_exp_{who}_gaze", "start": 0, "end": n, "loop": False}])),
           ok(c.op("seq.anim", path=path, label=LABEL[who], component="Body", sections=[
               {"anim": f"{ANIM}/AS_exp_{who}_body", "start": 0, "end": n, "loop": False},
               {"anim": f"{ANIM}/AS_exp_{who}_life", "start": 0, "end": n, "loop": False, "row": 2}]))]
    res = {"sections": out, "leaders": lead(who)}
    keep(who, "place", res)
    return res


# ------------------------------------------------------------------------------------------------------- body check

BODY_BONES = ["pelvis", "thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r", "spine_05", "head",
              "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r", "middle_03_l",
              "middle_03_r", "index_03_l", "index_03_r", "thumb_03_l", "thumb_03_r"]


def breath(t: list, pts: list) -> dict:
    """Breaths per minute and the median rise (mm) of the sternum (spine_05, a list of [x, y, z] cm at times t): the
    trace projected on its main axis of motion after a 4 s trend is removed, band-passed to 0.13-0.37 Hz (agent-09's
    breathing band); the rate from the dominant frequency there, the rise from each cycle's peak-to-trough."""
    import numpy as np
    x = np.asarray(pts, float)
    t = np.asarray(t, float)
    if len(x) < 32:
        return {"per_min": None, "amp_mm": None, "error": "trace too short"}
    dt = float(np.median(np.diff(t)))
    k = max(3, int(round(4.0 / dt)) | 1)
    pad = np.pad(x, ((k // 2, k // 2), (0, 0)), mode="edge")
    trend = np.stack([np.convolve(pad[:, i], np.ones(k) / k, mode="valid") for i in range(3)], axis=1)
    d = x - trend[:len(x)]
    _, _, vt = np.linalg.svd(d - d.mean(0), full_matrices=False)
    y = d @ vt[0]
    f = np.fft.rfftfreq(len(y), dt)
    Y = np.fft.rfft(y - y.mean())
    band = (f >= 0.13) & (f <= 0.37)
    if not band.any():
        return {"per_min": None, "amp_mm": None, "error": "no band"}
    f0 = float(f[band][np.argmax(np.abs(Y[band]))])
    yb = np.fft.irfft(np.where(band | ((f > 0.08) & (f < 0.5)), Y, 0), len(y))
    per = 1.0 / f0
    step = max(1, int(per / dt))
    amps = []
    for i0 in range(0, len(yb) - step, step):
        seg = yb[i0:i0 + step]
        amps.append(float(seg.max() - seg.min()))
    return {"per_min": round(60.0 * f0, 2), "amp_mm": round(10.0 * float(np.median(amps)), 2) if amps else None,
            "cycles": len(amps), "axis": [round(float(v), 3) for v in vt[0]]}


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
    body = run(CAMS, {"label": LABEL[who], "cams": []})["body"]
    fr_ = json.loads((OUT / who / "body_check.json").read_text())["frame"]
    yaw = math.radians(body["yaw"])  # the component's world yaw
    cy, sy_ = math.cos(yaw), math.sin(yaw)

    def to_actor(p):  # world -> component-local -> [forward, right, up from the body's origin]
        dx, dy, dz = p[0] - body["loc"][0], p[1] - body["loc"][1], p[2] - body["loc"][2]
        lx, ly = dx * cy + dy * sy_, -dx * sy_ + dy * cy
        q = [lx, ly, dz]
        return [S.dot(q, fr_["fwd"]), S.dot(q, fr_["right"]), dz]

    st = set_of(who)
    issues, worst = [], {}
    sz = []
    for i, f in enumerate(fr):
        A = {b: to_actor(m["bones"][b][i][:3]) for b in BODY_BONES if b in m["bones"]}
        sz.append(A["spine_05"])
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
    where = f"{path} f0-{n - 1} every {every}"
    gate = {k: ({"value": v, "where": where} if v is not None else {"value": None, "error": br.get("error", "not measured")})
            for k, v in numbers.items()}
    (d / "body.json").write_text(json.dumps({"gate": gate, "source": f"perform.py bodycheck --who {who}"}, indent=1))
    return res


def cmd_rolltest(who: str, deg: float = 5.0) -> dict:
    """Which head curve does what on this face, on the live head bone (agent-04: her 'roll' read as pitch). Works
    before the performance exists: a 1 s probe animation on the face's skeleton with HeadPitch/HeadYaw/HeadRoll each
    at +-deg (the others 0) plays on the Face in a scratch sequence (/Game/Explainer/Perf/SEQ_RollTest_<who>); frame 12
    is sampled against all zero. Reported per curve, for each head-bone axis: the rotation [pitch about the body's
    right, yaw about up, roll about forward] in degrees (a rigid turn reads the same on all three axes). Touches only
    its own scratch assets, deleted at the end."""
    c = client()
    lab = LABEL[who]
    seq, probe = f"{ANIM}/SEQ_RollTest_{who}", f"{ANIM}/AS_exp_{who}_rollprobe"
    mesh = mesh_of(who, "Face")
    fr = json.loads((OUT / who / "body_check.json").read_text())["frame"] if (OUT / who / "body_check.json").exists() \
        else {"fwd": [0.0, 1.0, 0.0], "right": [-1.0, 0.0, 0.0]}
    body = run(CAMS, {"label": lab, "cams": []})["body"]  # the component's yaw turns its frame into the world's
    yw = math.radians(body["yaw"])

    def world(v):  # component direction -> world (yaw only)
        return [v[0] * math.cos(yw) - v[1] * math.sin(yw), v[0] * math.sin(yw) + v[1] * math.cos(yw), v[2]]

    R, U, F = world(fr["right"]), [0.0, 0.0, 1.0], world(fr["fwd"])

    def angles(row, row0):
        out = {}
        for k, (i0, i1) in {"x": (3, 6), "y": (6, 9), "z": (9, 12)}.items():
            ax = S.cross(row0[i0:i1], row[i0:i1])
            out[k] = [round(math.degrees(math.asin(max(-1.0, min(1.0, S.dot(ax, v))))), 2) for v in (R, U, F)]
        return out

    ok(c.op("seq.new", path=seq, start=0, end=24, fps=24, replace=True))
    rows = {}
    try:
        for name, val in ((None, 0.0), ("HeadPitch", deg), ("HeadPitch", -deg), ("HeadYaw", deg), ("HeadYaw", -deg),
                          ("HeadRoll", deg), ("HeadRoll", -deg)):
            ok(c.op("anim.new", path=probe, skeleton=mesh, length_s=1.0, fps=30, replace=True))
            ok(c.op("anim.write_curves", anim=probe, curves={n: [[0.0, 1.0], [val, val] if n == name else [0.0, 0.0]]
                                                              for n in ("HeadPitch", "HeadYaw", "HeadRoll")}))
            ok(c.op("seq.anim", path=seq, label=lab, component="Face", sections=[{"anim": probe, "start": 0,
                                                                                 "end": 24}]))
            m = ok(c.op("seq.sample", path=seq, actor_label=lab, component="Face", bones=["head"], frames=[12],
                        ticks=8))
            rows[f"{name}{val:+g}" if name else "zero"] = m["bones"]["head"][0]
    finally:
        ok(c.exec_code("import unreal\nfrom fmbridge.ops.assets import free\n"
                       f"[free(p) for p in ({seq!r}, {probe!r}) if unreal.EditorAssetLibrary.does_asset_exist(p)]\n"
                       "result = True"))
    z = rows.pop("zero")
    res = {k: angles(r, z) for k, r in rows.items()}
    keep(who, "rolltest", res)
    return {"deg": deg, "per_axis_pitch_yaw_roll": res,
            "read": "per curve, the largest of [pitch, yaw, roll] is what it does; all zero = the curves do not move "
                    "the head on the live face (it rides the body: 5.8)"}


LIP_GAP = ("FACIAL_C_LipUpper", "FACIAL_C_LipLower")


def cmd_numbers(who: str, seq: str = "") -> dict:
    """agent-09's lips rows for this film -> numbers/<film>/lips.json: the curve items from the placed check
    (lips_placed.json: lag vs each line's own solve, track r, onset lead, silences), lips.lead_in_cm from the lip gap
    on the evaluated face (cast_gate's lipgap: upper to lower lip bone, mean |change| per frame in the silence before
    each on-camera line, clipped to the gap after the line before has faded and ending before the approved
    LEAD_FRAMES anticipation; a gap with under 2 such frames is not judged), lips.cues_fresh from the WAVs' hashes at solve
    time vs now."""
    import hashlib
    from filmtools.unreal.cli_lipsync import gate_numbers
    rep = json.loads((OUT / who / "lips_placed.json").read_text())
    rep.setdefault("fps", FPS)
    g = gate_numbers({who: rep}, {}, None, {})["gate"]
    g.pop("lips.render_conclusive", None)
    g["lips.render_lag_frames"] = {"value": None, "error": "INFO: the render measure is invalid (07 Nov ruling)"}
    solved = json.loads((OUT / who / "solve.json").read_text())
    stale = [k for k, v in solved.items()
             if v.get("sha256") != hashlib.sha256((HERE / "audio" / FILM[who] / "lines" / f"{k}.wav").read_bytes()).hexdigest()]
    g["lips.cues_fresh"] = {"value": int(not stale), "where": "every line WAV = the one solved" if not stale
                            else f"changed since the solve: {stale}"}
    path = seq or SEQ[who]
    lines = cues(who)["lines"]
    on = [(int(round(a * FPS)), int(round(b * FPS))) for a, b, _ in cue_sheet(who)["on_cam"]]
    wins = []
    for i, ln in enumerate(lines):
        f0 = ln["start_f"]
        if not any(a <= f0 < b for a, b in on):
            continue
        # the silence proper: after the line before has faded out (compose fades 3 f past its last word) and before
        # the approved anticipation (the mouth opens LEAD_FRAMES + up to 1 f ahead of the sound: r5/lipsync.md)
        lo = max(f0 - 24, (lines[i - 1]["end_f"] + 4) if i else 0, 0)
        hi = f0 - int(math.ceil(LEAD_FRAMES)) - 1
        if hi - lo >= 2:
            wins.append((ln["id"], lo, hi))
    fr = sorted({f for _, lo, f0 in wins for f in range(lo - 1, f0)})
    if not fr:
        g["lips.lead_in_cm"] = {"value": None, "error": "no on-camera line with a silence before it"}
    else:
        m = ok(client().op("seq.sample", path=path, actor_label=LABEL[who], component="Face", bones=list(LIP_GAP),
                           frames=fr, ticks=2, timeout=3600))
        gap = {f: S.norm(S.sub(m["bones"][LIP_GAP[0]][i][:3], m["bones"][LIP_GAP[1]][i][:3])) for i, f in enumerate(fr)}
        worst = None
        for k, lo, f0 in wins:
            d = [abs(gap[f] - gap[f - 1]) for f in range(lo, f0) if f in gap and f - 1 in gap]
            v = sum(d) / len(d) if d else 0.0
            if worst is None or v > worst[0]:
                worst = (v, f"{k} f{lo}-{f0 - 1}")
        g["lips.lead_in_cm"] = {"value": round(worst[0], 4), "where": worst[1]}
    d = HERE / "numbers" / FILM[who]
    d.mkdir(parents=True, exist_ok=True)
    (d / "lips.json").write_text(json.dumps({"gate": g, "source": f"perform.py numbers --who {who} on {path}"},
                                            indent=1))
    return {"gate": g}


STEPS = ["body", "life", "preview", "push", "solve", "bias", "cams", "compose", "check:solve", "workseq", "face",
         "check:face", "sync", "gaze", "check:final", "place", "check:placed", "bodycheck", "numbers"]


def step(name: str, who: str, a) -> dict:
    if name.startswith("check:"):
        r = cmd_check(who, name.split(":")[1])
    else:
        r = {"push": lambda: cmd_push(who), "solve": lambda: cmd_solve(who, a.only), "bias": lambda: cmd_bias(who),
             "compose": lambda: cmd_compose(who), "workseq": lambda: cmd_workseq(who, a.fresh),
             "body": lambda: cmd_body(who, a.force), "cams": lambda: cmd_cams(who), "life": lambda: cmd_life(who),
             "face": lambda: cmd_face(who), "sync": lambda: cmd_sync(who), "gaze": lambda: cmd_gaze(who),
             "place": lambda: cmd_place(who, a.seq), "preview": lambda: cmd_preview(who, a.seq),
             "numbers": lambda: cmd_numbers(who, a.seq), "rolltest": lambda: cmd_rolltest(who), "bodycheck": lambda: cmd_bodycheck(who, a.seq),
             "calibrate_body": lambda: cmd_calibrate_body(who)}[name]()
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["push", "solve", "bias", "compose", "check", "workseq", "cams", "body", "life",
                                    "calibrate_body", "face", "sync", "gaze", "place", "preview", "numbers", "rolltest", "bodycheck", "all", "dry"])
    ap.add_argument("--who", required=True, choices=list(FILM))
    ap.add_argument("--stage", default="solve", choices=["solve", "face", "final", "placed"])
    ap.add_argument("--only", type=lambda s: s.split(","))
    ap.add_argument("--seq", default="")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--force", action="store_true", help="body: write even if the pose fails its own check")
    ap.add_argument("--from", dest="start", default="body")
    ap.add_argument("--to", dest="stop", default="numbers")
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
