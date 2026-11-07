"""The explainer set, built by script on a box: /Game/Explainer/ExplainerSet, the karma Studio duplicated as the
background with a podcast corner (the presenter seated in an upholstered chair behind a small walnut desk, a broadcast
mic on a desk boom from her left, low), the presenter's soft light, locked exposure and the cameras CAM_MCU, CAM_CU,
CAM_WIDE and CAM_MCU_L with a very subtle breathing drift. Every number is in setplan.py (offline-checked framing).

Run from a tree's tools/ (kali), naming the box twice so a command never reaches the wrong one:

    uv run python ../films/host-studio/explainers/set.py --box boxb --instance i-0123 --who her [--steps …]
    uv run python ../films/host-studio/explainers/set.py --box boxb --instance i-0123 --who her --check
    uv run python ../films/host-studio/explainers/set.py --box boxb --instance i-0123 --who her --stills r1 --frame 48

--instance must equal the profile's instance AND the instance the editor runs on (read from the box's metadata
service), else nothing runs. Steps (default all, in this order; each converges, re-running is harmless):

    level    duplicate /Game/Studio/Studio once, open it; delete the studio's standing-host lights and cameras and the
             other presenter; lower the sign; put the presenter on the chair mark, visible
    props    sync s3 …/props/explainer/ to the box, import each FBX into /Game/Explainer/Props, place chair/desk/mic
    light    the presenter's rig (channel 1), the presenter on channels 0+1, exposure locked (manual)
    cameras  the four cameras, focus tracking her camera-side eye
    seq      SEQ_Explain_<Who>: bind the presenter (visible) and the cameras, drift keys, camera cuts from the EDL
    save     save the level and /Game/Explainer

Face rule: every still made here has a presenter in it: it stays on the box and goes to s3 private/ only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import setplan as P  # noqa: E402

STUDIO = "/Game/Studio/Studio"
LEVEL = "/Game/Explainer/ExplainerSet"
FOLDER = "/Game/Explainer"
PROPS_DIR = f"{FOLDER}/Props"
STUDIO_M = "/Game/Studio/Materials"
BUCKET = "s3://rf-render-788655295054-aps1/ue-linux"
PROPS_S3 = f"{BUCKET}/props/explainer/"
BOX_PROPS = "/srv/ue/explainer/props"
REVIEW_S3 = f"{BUCKET}/private/renders/r6/review/explain/"
ACTOR = {"her": "Presenter", "him": "Host"}
SEQ = {"her": f"{FOLDER}/SEQ_Explain_Her", "him": f"{FOLDER}/SEQ_Explain_Him"}
STEPS = ["level", "props", "light", "cameras", "seq", "save"]
# the props' material slots dressed with the studio's own surfaces where the names say what they are (agent-05's FBX
# slot names; an unknown slot keeps the FBX's imported material and is reported)
SLOT_MI = {"M_Walnut": "MI_K_Walnut", "M_Oak": "MI_K_Oak", "M_Wool": "MI_K_Wool", "M_Linen": "MI_K_Linen",
           "M_Leather": "MI_K_Leather", "M_Felt": "MI_K_Felt"}

client = None  # filmtools.unreal.client, imported once FILM_UE_BOX is set


def ok(res: dict):
    if not res.get("ok"):
        raise SystemExit("box said: " + (res.get("stdout", "") + res.get("error", ""))[-2000:])
    return res.get("result")


def op(name, **kw):
    return ok(client.op(name, **kw))


def ex(code: str):
    return ok(client.exec_code(code))


# --------------------------------------------------------------------------------------------------------- guard

def guard(box: str, instance: str) -> None:
    """The profile and the editor must both be on `instance`."""
    conf = Path(os.environ.get("FILM_UE_CONF_DIR", Path.home() / ".config")) / f"film-ue.{box}.json"
    if not conf.exists():
        raise SystemExit(f"no profile {conf}")
    prof = json.loads(conf.read_text())
    if prof.get("instance") != instance:
        raise SystemExit(f"profile {box} is on {prof.get('instance')}, not {instance}: refusing")
    live = ex("import urllib.request as U\n"
              "t = U.urlopen(U.Request('http://169.254.169.254/latest/api/token', method='PUT',"
              " headers={'X-aws-ec2-metadata-token-ttl-seconds': '60'}), timeout=5).read().decode()\n"
              "result = U.urlopen(U.Request('http://169.254.169.254/latest/meta-data/instance-id',"
              " headers={'X-aws-ec2-metadata-token': t}), timeout=5).read().decode()")
    if live != instance:
        raise SystemExit(f"the editor behind profile {box} runs on {live}, not {instance}: refusing")
    print(f"box {box} = {instance} (profile and metadata agree)")


# --------------------------------------------------------------------------------------------------------- steps

def step_level(who: str) -> None:
    exists = ex(f"import unreal\nresult = unreal.EditorAssetLibrary.does_asset_exist({LEVEL!r})")
    if not exists:
        op("assets.duplicate", src=STUDIO, dst=LEVEL)
        print(f"duplicated {STUDIO} -> {LEVEL}")
    op("level.open", path=LEVEL)
    labels = [a[0] for a in op("level.actors")]
    other = ACTOR["him" if who == "her" else "her"]
    gone = [lab for lab in labels if lab in P.STUDIO_HOST_LIGHTS or lab in P.STUDIO_CAMS or lab == other
            or lab.startswith("Reel_")]
    if other == "Presenter":  # her hoops and watch ride her bones as separate actors
        gone += [lab for lab in labels if lab in ("HerEarL", "HerEarR", "HerWatch")]
    if gone:
        op("level.delete", labels=gone)
    print("deleted:", gone)
    # the sign (and its halo card and LEDs) comes down into the seated MCU's background, once (tagged)
    print("sign:", ex(f"""import unreal
from fmbridge.ops import level as L
moved = []
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    lab = a.get_actor_label()
    if lab in ("Sign", "SignHalo") or (lab.startswith("Halo") and lab[4:].isdigit()):
        if "exp_sign_drop" in [str(t) for t in a.tags]:
            continue
        p = a.get_actor_location()
        a.set_actor_location(unreal.Vector(p.x, p.y, p.z + {P.SIGN_DROP}), False, False)
        a.tags = list(a.tags) + [unreal.Name("exp_sign_drop")]
        moved.append(lab)
result = moved"""))
    who_actor = ACTOR[who]
    op("level.move", label=who_actor, loc=list(P.MARK), rot_={"pitch": 0.0, "yaw": P.YAW, "roll": 0.0})
    print("presenter:", ex(f"""from fmbridge.ops import level as L
a = L.actor({who_actor!r})
a.set_actor_hidden_in_game(False)
a.set_is_temporarily_hidden_in_editor(False)
p, r = a.get_actor_location(), a.get_actor_rotation()
result = [round(p.x, 2), round(p.y, 2), round(p.z, 2), round(r.yaw, 2)]"""))


def step_props(who: str) -> None:
    files = ex(f"""import subprocess, glob, os
os.makedirs({BOX_PROPS!r}, exist_ok=True)
r = subprocess.run(["aws", "s3", "sync", {PROPS_S3!r}, {BOX_PROPS!r}, "--only-show-errors"], capture_output=True, text=True)
result = {{"rc": r.returncode, "err": r.stderr[-500:], "fbx": sorted(glob.glob({BOX_PROPS!r} + "/**/*.fbx", recursive=True))}}""")
    if files["rc"]:
        raise SystemExit(f"props sync failed: {files['err']}")
    by_name = {Path(f).stem: f for f in files["fbx"]}
    print("props on the box:", sorted(by_name))
    mic = P.mic(who)
    for label, (name, loc, yaw) in P.PROPS.items():
        if name not in by_name:
            print(f"MISSING {label}: no {name}.fbx under {PROPS_S3} (agent-05)")
            continue
        dest = f"{PROPS_DIR}/{name}"
        paths = op("assets.import", files=[by_name[name]], dest=dest, replace=True, combine=True, kind="static",
                   nanite=False, collision="none", materials=True, textures=True)
        mesh = next((p for p in paths if "StaticMesh" in p or p.split(".")[-1] == name), paths[0] if paths else "")
        if not mesh:
            raise SystemExit(f"{name}: import returned nothing")
        y = mic["yaw"] if yaw is None else yaw
        op("level.spawn", label=label, asset=mesh.split(".")[0], loc=list(loc),
           rot_={"pitch": 0.0, "yaw": y, "roll": 0.0}, replace=True)
        slots = op("look.slots", label=label) or {}
        want = {s: f"{STUDIO_M}/{SLOT_MI[s]}" for s in slots if s in SLOT_MI}
        if want:
            op("look.slots", label=label, materials=want)
        print(f"{label}: {mesh} at {loc} yaw {y:.1f}; slots {sorted(slots)} dressed {sorted(want)}")
    op("look.channels", labels=[lab for lab in P.PROPS], channels=[0, 1])


def step_light(who: str) -> None:
    rig = P.lights(who)
    for label, L in rig.items():
        kw = {k: v for k, v in L.items() if k in ("kind", "loc", "look_at", "intensity", "temperature", "width",
                                                  "height", "barn_angle", "specular", "shadows")}
        op("look.light", label=label, volumetric=0.0, **{k: (list(v) if isinstance(v, tuple) else v)
                                                         for k, v in kw.items()})
    op("look.channels", labels=list(rig), channels=[1])
    op("look.channels", labels=[ACTOR[who]], channels=[0, 1])
    # exposure LOCKED: manual, the studio's bias; nothing in the frame may pump it
    op("look.post", label="FM_Post", settings={
        "auto_exposure_method": "AutoExposureMethod.AEM_MANUAL", "auto_exposure_bias": P.EXPOSURE_BIAS,
        "auto_exposure_apply_physical_camera_exposure": False, "white_temp": 5600.0,
        "bloom_intensity": 0.2, "bloom_threshold": 1.0, "vignette_intensity": 0.22, "film_grain_intensity": 0.05,
        "scene_fringe_intensity": 0.0, "lumen_final_gather_quality": 4.0, "lumen_reflection_quality": 2.0,
        "lumen_scene_detail": 2.0, "lumen_scene_lighting_quality": 2.0, "lumen_max_trace_distance": 2000.0})
    e = P.face(who)["eyes"]
    m = op("light.measure", at=list(e), labels=list(rig), key="ExpKey", fill="ExpFill")
    print(f"light at the eyes: {m.get('lux')} lux, ev100 {m.get('ev100')}, key:fill {m.get('ratio')}")


def step_cameras(who: str) -> None:
    actor = ACTOR[who]
    for name, c in P.cameras(who).items():
        op("cam.add", label=name, loc=c["loc"], look_at=c["look_at"], focal_mm=c["focal"], aperture=c["aperture"],
           sensor_mm=c["filmback"])
        op("cam.focus", label=name, mode="track", target=f"{actor}:Face:{c['focus']}")
        print(name, c["loc"], "->", c["look_at"], f"{c['focal']} mm f/{c['aperture']}")


def edl_cuts(edl: dict) -> list:
    """agent-11's EDL → [[camera, first frame], …] over the presenter shots; graphics ranges hold the camera before
    them (they are never rendered from the presenter sequence)."""
    cuts = []
    for s in sorted(edl["shots"], key=lambda s: s["f0"]):
        cam = s.get("camera") or s.get("cam")
        if cam and cam.startswith("CAM_") and (not cuts or cuts[-1][0] != cam):
            cuts.append([cam, int(s["f0"])])
    if cuts:
        cuts[0][1] = 0
    return cuts


def step_seq(who: str, edl_path: str | None, length: int) -> None:
    seq, actor = SEQ[who], ACTOR[who]
    edl = json.loads(Path(edl_path).read_text()) if edl_path else None
    end = int(edl.get("total_frames") or max(s["f1"] for s in edl["shots"])) if edl else length
    op("seq.new", path=seq, start=0, end=end, fps=24)
    op("seq.bind", path=seq, label=actor)
    op("seq.key_visible", path=seq, label=actor, keys=[[0, True]], attached=True)
    for k, (name, c) in enumerate(P.cameras(who).items()):
        op("seq.bind", path=seq, label=name)
        op("seq.key_transform", path=seq, label=name, keys=P.drift(c, -24, end + 24, seed=k + 1), interp="auto")
    cuts = edl_cuts(edl) if edl else [["CAM_MCU", 0], ["CAM_CU", 96], ["CAM_WIDE", 168]]
    op("seq.camera_cuts", path=seq, cuts=cuts)
    print(f"{seq}: 0-{end}, cuts {cuts}")


def step_save() -> None:
    op("level.save")
    print("saved:", op("assets.save", folder=FOLDER).get("saved"))


# ------------------------------------------------------------------------------------------------ check and stills

def check(who: str) -> int:
    """Read-only: the live set against the plan, and the mic vs her mouth through each camera on the real pose."""
    bad = 0
    actor = ACTOR[who]
    live = {c["label"]: c for c in (op("cam.describe") or []) if isinstance(c, dict) and "label" in c}
    for name, c in P.cameras(who).items():
        lc = live.get(name)
        if not lc:
            print(f"BAD {name}: missing"); bad += 1; continue
        d = max(abs(a - b) for a, b in zip(lc.get("loc") or lc.get("location"), c["loc"]))
        f = abs((lc.get("focal_mm") or lc.get("focal")) - c["focal"])
        print(f"{'ok ' if d < 1.0 and f < 0.05 else 'BAD'} {name}: loc off {d:.2f} cm, focal off {f:.2f} mm")
        bad += not (d < 1.0 and f < 0.05)
    pos = ex(f"from fmbridge.ops import level as L\np = L.actor({actor!r}).get_actor_location()\n"
             "result = [p.x, p.y, p.z]")
    d = max(abs(a - b) for a, b in zip(pos, P.MARK))
    print(f"{'ok ' if d < 0.5 else 'BAD'} {actor} on the mark: off {d:.2f} cm"); bad += d >= 0.5
    if any(a[0] == "ExpMic" for a in op("level.actors", contains="ExpMic")):
        bmin, bmax = (lambda b: (b["min"], b["max"]))(op("level.find", label="ExpMic")[0]["bounds"])
        corners = {f"mic{i}": [(bmin, bmax)[i >> k & 1][k] for k in range(3)] for i in range(8)}
        for name in P.cameras(who):
            pr = op("cam.project", camera=name, points=corners, subjects=[actor])
            print(name, json.dumps(pr)[:600])
    lead = op("mh.leader_check", label=actor)
    print(f"{'ok ' if lead.get('pass') else 'BAD'} leaders: {lead.get('why') or lead.get('metric')}")
    bad += not lead.get("pass")
    return bad


def stills(who: str, tag: str, frame: int) -> None:
    out = f"/srv/ue/explainer/review/{tag}"
    seq = SEQ[who]
    for name in P.cameras(who):
        path = f"{out}/{who}_{name}_f{frame:04d}.png"
        op("seq.still", path=seq, frame=frame, camera=name, out=path, width=1920, height=1080, settle=48)
        print("still", path)
    r = ex(f"""import subprocess
r = subprocess.run(["aws", "s3", "cp", "--recursive", "--sse", "aws:kms", {out!r}, {REVIEW_S3 + tag + '/'!r},
                    "--only-show-errors"], capture_output=True, text=True)
result = [r.returncode, r.stderr[-400:]]""")
    print("to s3:", REVIEW_S3 + tag + "/", "rc", r)


def main() -> int:
    global client
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--box", required=True, help="the film-ue profile (never the default)")
    ap.add_argument("--instance", required=True, help="the instance id the profile and the editor must be on")
    ap.add_argument("--who", required=True, choices=["her", "him"])
    ap.add_argument("--steps", default=",".join(STEPS))
    ap.add_argument("--edl", help="agent-11's edl/<film>.json (shots with f0, f1, camera)")
    ap.add_argument("--length", type=int, default=240, help="the sequence's length without an EDL")
    ap.add_argument("--check", action="store_true", help="read-only: the live set against the plan")
    ap.add_argument("--stills", metavar="TAG", help="stills through every camera to private/…/review/explain/TAG/")
    ap.add_argument("--frame", type=int, default=48)
    a = ap.parse_args()
    os.environ["FILM_UE_BOX"] = a.box
    from filmtools.unreal import client as c
    client = c
    guard(a.box, a.instance)
    if a.check:
        return 1 if check(a.who) else 0
    if a.stills:
        stills(a.who, a.stills, a.frame)
        return 0
    for s in a.steps.split(","):
        if s not in STEPS:
            raise SystemExit(f"step {s}: one of {STEPS}")
    for s in STEPS:
        if s in a.steps.split(","):
            print(f"== {s}")
            {"level": lambda: step_level(a.who), "props": lambda: step_props(a.who),
             "light": lambda: step_light(a.who), "cameras": lambda: step_cameras(a.who),
             "seq": lambda: step_seq(a.who, a.edl, a.length), "save": step_save}[s]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
