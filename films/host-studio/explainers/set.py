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
# one level per presenter, each saved from the Studio (which holds that presenter's dressed instance): her finished
# level is never touched by his replay, and box B can run both
LEVELS = {"her": "/Game/Explainer/ExplainerSet", "him": "/Game/Explainer/ExplainerSet_Him"}
LEVEL = LEVELS["her"]  # kept for older callers
FOLDER = "/Game/Explainer"
PROPS_DIR = f"{FOLDER}/Props"
BUCKET = "s3://rf-render-788655295054-aps1/ue-linux"
PROPS_S3 = f"{BUCKET}/props/explainer/"
BOX_PROPS = "/srv/ue/explainer/props"
REVIEW_S3 = f"{BUCKET}/private/renders/r6/review/explain/"
ACTOR = {"her": "Presenter", "him": "Host"}
SEQ = {"her": f"{FOLDER}/SEQ_Explain_Her", "him": f"{FOLDER}/SEQ_Explain_Him"}
STEPS = ["level", "props", "dressing", "light", "cameras", "seq", "garments", "dress", "save"]
# the presenter's dress pass (leaders, hair look, accessories; saves the level) and what she wears, per presenter
# his dress_him.py also rewrites the reel's SEQ_Reel: for him the level part alone (mh.leader) is what the set needs
DRESS = {"her": HERE.parent / "props/her_outfit_ue/dress_her.py", "him": None}
client = None  # filmtools.unreal.client, imported once FILM_UE_BOX is set


def ok(res: dict):
    if not res.get("ok"):
        raise SystemExit("box said: " + (res.get("stdout", "") + res.get("error", ""))[-2000:])
    return res.get("result")


def op(op_name, /, **kw):
    return ok(client.op(op_name, **kw))


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
    level = LEVELS[who]
    exists = ex(f"import unreal\nresult = unreal.EditorAssetLibrary.does_asset_exist({level!r})")
    if not exists:
        # save-as from the open Studio: assets.duplicate of the loaded map, then level.open of the copy, kills the
        # editor (EditorServer.cpp:2544, the old world still referenced) every time (box B, 16:47 and 16:48 IST)
        op("level.open", path=STUDIO)
        ex("import unreal\nw = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()\n"
           f"result = unreal.EditorLoadingAndSavingUtils.save_map(w, {level!r})")
        print(f"saved {STUDIO} as {level}")
    op("level.open", path=level)
    labels = [a[0] for a in op("level.actors")]
    other = ACTOR["him" if who == "her" else "her"]
    gone = [lab for lab in labels if lab in P.STUDIO_HOST_LIGHTS or lab in P.STUDIO_CAMS or lab == other
            or lab.startswith(("Reel_", "Test_", "FMQA_"))]  # Test_perf_*: the reel's parked test copies (a full
    # BP_Host_Op among them, box B 18:05), FMQA_*: QA temporaries — never in a presenter level
    if other == "Presenter":  # her hoops and watch ride her bones as separate actors
        gone += [lab for lab in labels if lab in ("HerEarL", "HerEarR", "HerWatch")]
    if gone:
        op("level.delete", labels=gone)
    print("deleted:", gone)
    # the sign (and its halo card and LEDs) at the studio's height + SIGN_DROP: each actor's studio z is kept in a tag
    # the first time, so a re-run with another drop moves it from there, not from where the last run left it
    print("sign:", ex(f"""import unreal
moved = {{}}
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    lab = a.get_actor_label()
    if lab in ("Sign", "SignHalo") or (lab.startswith("Halo") and lab[4:].isdigit()):
        p = a.get_actor_location()
        tags = [str(t) for t in a.tags]
        orig = next((float(t.split("=")[1]) for t in tags if t.startswith("exp_studio_z=")), None)
        if orig is None:
            # round 6's first run tagged exp_sign_drop after moving it down 78 cm
            orig = p.z + 78.0 if "exp_sign_drop" in tags else p.z
            a.tags = [unreal.Name(t) for t in tags if t != "exp_sign_drop"] + [unreal.Name(f"exp_studio_z={{orig:.3f}}")]
        a.set_actor_location(unreal.Vector(p.x, p.y, orig + {P.SIGN_DROP}), False, False)
        moved[lab] = round(orig + {P.SIGN_DROP}, 2)
result = moved"""))
    # the window's garden card dimmed in this level only (its own instance; the studio's MI_K_Outside is shared)
    op("look.material", name="MI_Exp_Outside", kind="Screen", texture="/Game/Studio/Textures/T_Outside",
       intensity=6.0, roughness=1.0, folder=f"{FOLDER}/Materials")
    op("look.apply", label="Outside", material=f"{FOLDER}/Materials/MI_Exp_Outside", slot=0)
    who_actor = ACTOR[who]
    op("level.move", label=who_actor, loc=list(P.MARK), rot_={"pitch": 0.0, "yaw": P.YAW, "roll": 0.0})
    print("presenter:", ex(f"""from fmbridge.ops import level as L
a = L.actor({who_actor!r})
a.set_actor_hidden_in_game(False)
a.set_is_temporarily_hidden_in_editor(False)
p, r = a.get_actor_location(), a.get_actor_rotation()
result = [round(p.x, 2), round(p.y, 2), round(p.z, 2), round(r.yaw, 2)]"""))


def step_props(who: str) -> None:
    """agent-05's props: sync, a PBR instance per texture set (props.json: base colour, DirectX normal, packed ORM,
    tile_m), import each FBX, place it, dress its slots by name."""
    got = ex(f"""import subprocess, glob, os, json
os.makedirs({BOX_PROPS!r}, exist_ok=True)
r = subprocess.run(["aws", "s3", "sync", {PROPS_S3!r}, {BOX_PROPS!r}, "--only-show-errors"], capture_output=True, text=True)
pj = os.path.join({BOX_PROPS!r}, "props.json")
result = {{"rc": r.returncode, "err": r.stderr[-500:], "props": json.load(open(pj)) if os.path.exists(pj) else None,
          "fbx": sorted(glob.glob({BOX_PROPS!r} + "/**/*.fbx", recursive=True))}}""")
    if got["rc"] or not got["props"]:
        raise SystemExit(f"props sync failed or no props.json: {got['err']}")
    meta, by_name = got["props"], {Path(f).stem: f for f in got["fbx"]}
    print("props on the box:", sorted(by_name))
    mats = {}
    for slot, t in meta.get("textures", {}).items():
        mi = f"{PROPS_DIR}/Materials/MI_Exp_{slot[2:]}"
        tiling = 1.0 / t["tile_m"] if P.UV_METRES and t.get("tile_m") else 1.0
        tx = f"{BOX_PROPS}/textures"
        op("mat.pbr", path=mi, maps={"base_color": f"{tx}/{t['BaseColor']}", "normal": f"{tx}/{t['Normal_DirectX']}",
                                     "orm": f"{tx}/{t['ORM']}"},
           texture_dest=f"{PROPS_DIR}/Textures", params={"Tiling": round(tiling, 4)})
        mats[slot] = mi
    print("materials:", sorted(mats))
    # the lamp's shade glows through (thin linen lit from inside), its bulb is emissive
    mats["M_ShadeLinen"] = (op("look.material", name="MI_Exp_ShadeLinen", kind="Sheer",
                                       color=[0.78, 0.72, 0.62], transmission=[1.0, 0.75, 0.5], glow=0.6,
                                       folder=f"{PROPS_DIR}/Materials"))
    mats["M_LampBulb"] = (op("look.material", name="MI_Exp_LampBulb", kind="Emissive", color=[1.0, 0.72, 0.42],
                                     intensity=12.0, folder=f"{PROPS_DIR}/Materials"))
    desk_panel = P.DESK_PANEL in by_name
    for label, (name, loc, yaw, scale) in P.PROPS.items():
        if label == "ExpDesk" and desk_panel:
            name = P.DESK_PANEL  # agent-05's desk with the modesty panel replaces the walnut slab
        if name not in by_name:
            print(f"MISSING {label}: no {name}.fbx under {PROPS_S3} (agent-05)")
            continue
        # the plan's transform (r3: the boom mirrored to the -Y side; agent-05's props.json placement is the unmirrored
        # one it was posed for)
        paths = op("assets.import", files=[by_name[name]], dest=PROPS_DIR, replace=True, combine=True, kind="static",
                   nanite=False, collision="none", materials=False, textures=False, name=name)
        mesh = next((x for x in paths if x.split("/")[-1].split(".")[0] == name), paths[0] if paths else "")
        if not mesh:
            raise SystemExit(f"{name}: import returned nothing")
        op("level.spawn", label=label, asset=mesh.split(".")[0], loc=list(loc),
           rot_={"pitch": 0.0, "yaw": yaw, "roll": 0.0}, scale=scale or [1.0, 1.0, 1.0], replace=True)
        slots = op("look.slots", label=label) or {}
        want = {sl: mats[sl] for sl in slots if sl in mats}
        if want:
            op("look.slots", label=label, materials=want)
        print(f"{label}: {mesh} at {list(loc)} yaw {yaw} scale {scale}; slots {sorted(slots)}; undressed {sorted(set(slots) - set(want))}")
    placed = [lab for lab in P.PROPS if any(a[0] == lab for a in op("level.actors", contains=lab))]
    op("look.channels", labels=placed, channels=[0, 1])
    if desk_panel:
        op("level.delete", labels=["ExpModesty"])
    if "ExpLamp" in placed:  # the lamp's bulb: a warm practical on the set's channel
        x, y, _ = P.PROPS["ExpLamp"][1]
        b = P.LAMP_BULB
        op("look.light", label="ExpLampBulb", kind=b["kind"], loc=[x, y, b["z"]], intensity=b["intensity"],
           temperature=b["temperature"], radius=b["radius"], shadows=True, volumetric=0.0)
        op("look.channels", labels=["ExpLampBulb"], channels=[0])


def step_dressing(who: str) -> None:
    """The WIDE's right side (the -Y wall): copies of the studio's dressed actors, a warm grazing light on the new slats;
    the desk's modesty panel (a walnut slab until agent-05's panelled desk)."""
    print("copies:", ex(f"""import unreal
from fmbridge.ops import level as L
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
out = {{}}
for new, (src, loc, yaw) in {P.DRESSING!r}.items():
    for a in EAS.get_all_level_actors():
        if a.get_actor_label() == new:
            EAS.destroy_actor(a)
    d = EAS.duplicate_actor(L.actor(src))
    d.set_actor_label(new)
    d.set_actor_location(unreal.Vector(*loc), False, False)
    d.set_actor_rotation(unreal.Rotator(0.0, 0.0, yaw), False)  # Rotator(roll, pitch, yaw)
    p = d.get_actor_location()
    out[new] = [round(p.x, 1), round(p.y, 1), round(p.z, 1), round(d.get_actor_rotation().yaw, 1)]
result = out"""))
    g = P.SIDE_GRAZER
    op("look.light", label="ExpSideGrazer", volumetric=0.0, shadows=True,
       **{k: (list(v) if isinstance(v, tuple) else v) for k, v in g.items()})
    op("look.channels", labels=["ExpSideGrazer"], channels=[0])
    if any(a[0] == "ExpDesk" for a in op("level.actors", contains="ExpDesk")) and \
            "Panel" in json.dumps(op("level.get", label="ExpDesk", components=True)):
        return print("desk has its own modesty panel")
    m = P.MODESTY
    op("level.spawn", label="ExpModesty", shape="cube", loc=list(m["loc"]), size=list(m["size"]), replace=True)
    op("look.apply", label="ExpModesty", material=f"{PROPS_DIR}/Materials/MI_Exp_Walnut", slot=0)
    op("look.channels", labels=["ExpModesty"], channels=[0, 1])


def step_light(who: str) -> None:
    rig = P.lights(who)
    for label, L in rig.items():
        kw = {k: v for k, v in L.items() if k in ("kind", "loc", "look_at", "intensity", "temperature", "width",
                                                  "height", "barn_angle", "specular", "shadows")}
        op("look.light", label=label, volumetric=0.0, **{k: (list(v) if isinstance(v, tuple) else v)
                                                         for k, v in kw.items()})
    op("look.channels", labels=list(rig), channels=[1])
    op("level.set", label="FM_Sun", component="DirectionalLightComponent", props={"intensity": P.SUN_LUX})
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
    """The focus track is the actor plus an offset taken from the pose at the time: scrub the sequence first so it is
    the SEATED eye (box B: unscrubbed, the offset was her standing eye, 30 cm high: ~2.7 cm of focus error at the CU's
    ±1.2 cm depth of field)."""
    actor = ACTOR[who]
    if ex(f"import unreal\nresult = unreal.EditorAssetLibrary.does_asset_exist({SEQ[who]!r})"):
        op("seq.scrub", path=SEQ[who], frame=60)
    for name, c in P.cameras(who).items():
        op("cam.add", label=name, loc=c["loc"], look_at=c["look_at"], focal_mm=c["focal"], aperture=c["aperture"],
           sensor_mm=c["filmback"])
        op("cam.focus", label=name, mode="track", target=f"{actor}:Face:{c['focus']}")
        print(name, c["loc"], "->", c["look_at"], f"{c['focal']} mm f/{c['aperture']}")


def shot_camera(s: dict) -> str | None:
    """A shot's camera: agent-11's PANEL shots (her in the left half, a graphic panel on the right) use CAM_MCU_L."""
    cam = s.get("camera")
    if not cam or s.get("kind") == "gfx":
        return None
    return "CAM_MCU_L" if s.get("kind") == "panel" and cam == "CAM_MCU" else cam


def render_plan(edl: dict, handles: int = 6) -> list:
    """Every presenter shot as [n, camera, first, end) with ±handles, clamped to the sequence."""
    end = int(edl.get("frames") or max(s["f1"] for s in edl["shots"]))
    return [[s["n"], shot_camera(s), max(0, s["f0"] - handles), min(end, s["f1"] + handles)]
            for s in edl["shots"] if shot_camera(s)]


def edl_cuts(edl: dict) -> list:
    """agent-11's EDL → [[camera, first frame], …] over the presenter shots; graphics ranges hold the camera before
    them (they are never rendered from the presenter sequence)."""
    cuts = []
    for s in sorted(edl["shots"], key=lambda s: s["f0"]):
        cam = shot_camera(s)
        if cam and (not cuts or cuts[-1][0] != cam):
            cuts.append([cam, int(s["f0"])])
    if cuts:
        cuts[0][1] = 0
    return cuts


def step_seq(who: str, edl_path: str | None, length: int) -> None:
    seq, actor = SEQ[who], ACTOR[who]
    edl = json.loads(Path(edl_path).read_text()) if edl_path else None
    end = int(edl.get("frames") or max(s["f1"] for s in edl["shots"])) if edl else length
    op("seq.new", path=seq, start=0, end=end, fps=24)
    op("seq.bind", path=seq, label=actor)
    op("seq.key_visible", path=seq, label=actor, keys=[[0, True]], attached=True)
    for k, (name, c) in enumerate(P.cameras(who).items()):
        op("seq.bind", path=seq, label=name)
        op("seq.key_transform", path=seq, label=name, keys=P.drift(c, -24, end + 24, seed=k + 1), interp="auto")
    cuts = edl_cuts(edl) if edl else [["CAM_MCU", 0], ["CAM_CU", 96], ["CAM_WIDE", 168]]
    op("seq.camera_cuts", path=seq, cuts=cuts)
    print(f"{seq}: 0-{end}, cuts {cuts}")


def step_garments(who: str) -> None:
    """The seated garment cuts: each component back on its original mesh, then body.hide_under in order (each cut
    is a copy named <mesh>_Under_<garment>; the originals and the studio are untouched)."""
    src = P.GARMENT_SRC[who]
    if not src:
        return print("no garment cuts for", who)
    print("reset:", ex(f"""import unreal
from fmbridge.ops import level as L
out = {{}}
for c in L.actor({ACTOR[who]!r}).get_components_by_class(unreal.SkeletalMeshComponent):
    m = {src!r}.get(c.get_name())
    if m:
        c.set_skeletal_mesh_asset(unreal.load_asset(m))
        out[c.get_name()] = m
result = out"""))
    for comp, over, reach in P.GARMENT_HIDES[who]:
        r = op("body.hide_under", label=ACTOR[who], body=comp, garment=over, reach_cm=reach, apply=True)
        print(f"{comp} under {over} (reach {reach}): hidden {r.get('hidden')} ({r.get('fraction')}) → {r.get('mesh')}")


def step_dress(who: str) -> None:
    """Leaders back on every garment (any step that touches her components drops them: box B after agent-01's body
    step), her hair look and accessories, the groom lock (render cvars) — then the leaders check must pass."""
    if DRESS[who]:
        ok(client.exec_code(DRESS[who].read_text()))
    else:
        op("mh.leader", label=ACTOR[who])
    op("groom.lock", labels=[ACTOR[who]])
    lead = op("mh.leader_check", label=ACTOR[who])
    if not lead.get("pass"):
        raise SystemExit(f"leaders: {lead}")
    print("dressed, leaders pass, groom locked")


def step_save() -> None:
    op("level.save")
    print("saved:", op("assets.save", folder=FOLDER).get("saved"))


# ------------------------------------------------------------------------------------------------ check and stills

def check(who: str) -> int:
    """Read-only: the live set against the plan, and the mic vs her mouth through each camera on the real pose."""
    bad = 0
    actor = ACTOR[who]
    live = {c["label"]: c for c in (op("cam.describe") or {}).get("cameras", [])}
    for name, c in P.cameras(who).items():
        lc = live.get(name)
        if not lc:
            print(f"BAD {name}: missing"); bad += 1; continue
        d = max(abs(a - b) for a, b in zip(lc["loc"], c["loc"]))  # the drift keys move it ≤0.4 cm
        f = abs(lc["focal"] - c["focal"])
        ft = (lc.get("focus_track") or {}).get("offset") or [0, 0, 0]
        print(f"{'ok ' if d < 1.0 and f < 0.05 else 'BAD'} {name}: loc off {d:.2f} cm, focal off {f:.2f} mm, "
              f"focus track offset z {ft[2]:.1f} (the seated eye ~{P.face(who)['eyes'][2]:.0f})")
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


def guard_scene(who: str, cam: str = "", frame: int | None = None) -> dict:
    """agent-06's pre-render guard: no Test_*/FMQA_* actor and no second presenter in the level, every garment led by
    Body, and (with cam/frame) her face lit in a still through that camera (mean luma 50..230 in a box round the
    eyes and mouth). Returns {"ok", "why", ...}."""
    actor = ACTOR[who]
    bad = [lab for lab, cls, _ in op("level.actors")
           if lab.startswith(("Test_", "FMQA_")) or (("BP_Host" in cls or "BP_Presenter" in cls) and lab != actor)]
    lead = op("mh.leader_check", label=actor)
    out = {"strays": bad, "leaders_ok": int(bool(lead.get("pass")))}
    if cam and frame is not None:
        path = f"/srv/ue/explainer/guard/{who}_{cam}_f{frame:04d}.png"
        op("seq.scrub", path=SEQ[who], frame=frame)
        eyes = op("level.bone", label=actor, component="Face", bones=["FACIAL_L_Eye", "FACIAL_R_Eye", "FACIAL_C_LipLower"])
        pts = op("cam.project", camera=cam, points={k: v for k, v in eyes.items()})["points"]
        us, vs = [p["u"] for p in pts.values()], [p["v"] for p in pts.values()]
        box = [max(0.0, min(us) - 0.01), max(0.0, min(vs) - 0.01), min(1.0, max(us) + 0.01), min(1.0, max(vs) + 0.02)]
        op("seq.still", path=SEQ[who], frame=frame, camera=cam, out=path, width=960, height=540, settle=24)
        face = op("qa.exposure", image=path, regions={"face": box})["metrics"]["regions"]["face"]["mean"]
        out.update(face_luma=round(face, 1), face_box=[round(x, 3) for x in box])
        out["face_ok"] = int(50 <= face <= 230)
    out["ok"] = not bad and out["leaders_ok"] and out.get("face_ok", 1)
    out["why"] = "; ".join(w for w, c in (("strays " + ",".join(bad), bad), ("leaders", not out["leaders_ok"]),
                                           (f"face luma {out.get('face_luma')}", not out.get("face_ok", 1))) if c)
    return out


def stills(who: str, tag: str, frame: int, edl_path: str | None, extra: list | None = None) -> None:
    """A still through each camera at `frame`. seq.still's `camera` does not beat the sequence's camera cut track
    (box B: MCU and WIDE stills were the same image), so each still is taken with the cut track set to that camera
    alone, and the edit is put back after."""
    out = f"/srv/ue/explainer/review/{tag}"
    seq = SEQ[who]
    cams = list(P.cameras(who)) + list(extra or [])
    try:
        for name in cams:
            op("seq.camera_cuts", path=seq, cuts=[[name, 0]])
            path = f"{out}/{who}_{name}_f{frame:04d}.png"
            op("seq.still", path=seq, frame=frame, camera=name, out=path, width=1920, height=1080, settle=48)
            print("still", path)
    finally:
        edl = json.loads(Path(edl_path).read_text()) if edl_path else None
        op("seq.camera_cuts", path=seq, cuts=edl_cuts(edl) if edl else [["CAM_MCU", 0]])
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
    ap.add_argument("--extra-cams", help="more cameras for --stills (e.g. CAM_SIDE)")
    a = ap.parse_args()
    os.environ["FILM_UE_BOX"] = a.box
    from filmtools.unreal import client as c
    client = c
    guard(a.box, a.instance)
    if a.check:
        return 1 if check(a.who) else 0
    if a.stills:
        stills(a.who, a.stills, a.frame, a.edl, [c for c in (a.extra_cams or "").split(",") if c])
        return 0
    for s in a.steps.split(","):
        if s not in STEPS:
            raise SystemExit(f"step {s}: one of {STEPS}")
    for s in STEPS:
        if s in a.steps.split(","):
            print(f"== {s}")
            {"level": lambda: step_level(a.who), "props": lambda: step_props(a.who), "dressing": lambda: step_dressing(a.who),
             "light": lambda: step_light(a.who), "cameras": lambda: step_cameras(a.who),
             "seq": lambda: step_seq(a.who, a.edl, a.length), "garments": lambda: step_garments(a.who), "dress": lambda: step_dress(a.who),
             "save": step_save}[s]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
