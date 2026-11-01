"""Check the sequencer ops in the running editor: build a throwaway sequence over a few throwaway actors with every
key op, scrub it, and read back what the engine actually evaluates (focus distance, light intensity and colour,
visibility, a material parameter, a transform hold, animation sections, audio, the edit, stills through the cut, a
gaze lock toward a point). Everything it makes is prefixed and is deleted with --clean.

    cd tools && uv run python ../unreal/test_seqops.py [--gaze] [--stills DIR] [--clean]

It touches nothing in the level but its own actors; the presenter (Host) is only bound in its own sequence, which
is closed at the end, so the level shows as before."""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import tempfile
import wave
from pathlib import Path

from filmtools.unreal import client

P = "Test_agent-09_"
DIR = "/Game/Test_agent-09"
SEQ = f"{DIR}/{P}Seq"
CAM_A, CAM_B, LIGHT, BOX, KID, POST = (P + n for n in ("CamA", "CamB", "Light", "Box", "Kid", "Post"))
IDLE = "/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"
FACE = "/Game/Speech/Anim/AS_line1_body"  # shot.py's talking face, baked onto the body's skeleton
PROJECT = r"C:\UEProjects\HostStudio"
results: list = []


def ok(res: dict):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return res.get("result")


def op(name: str, **kw):
    return ok(client.op(name, **kw))


def check(what: str, got, want, tol: float = 1e-3) -> bool:
    if isinstance(want, (list, tuple)):
        good = len(got) == len(want) and all(abs(g - w) <= tol for g, w in zip(got, want))
    elif isinstance(want, float):
        good = abs(got - want) <= tol
    else:
        good = got == want
    results.append([("PASS" if good else "FAIL"), what, got, want])
    print(f"{'PASS' if good else 'FAIL'}  {what}: got {got!r}, want {want!r}", flush=True)
    return good


READ = '''
import unreal
from fmbridge.ops.level import actor
def comp(label, cls):
    return actor(label).get_component_by_class(getattr(unreal, cls))
box = actor("{BOX}")
light = comp("{LIGHT}", "PointLightComponent")
c = light.get_editor_property("light_color")
mesh = comp("{BOX}", "StaticMeshComponent")
mat = mesh.get_material(0)
p = box.get_actor_location()
result = {{
  "focus": comp("{CAM_A}", "CineCameraComponent").get_editor_property("focus_settings").get_editor_property("manual_focus_distance"),
  "intensity": light.get_editor_property("intensity"),
  "temperature": light.get_editor_property("temperature"),
  "color": [c.r, c.g, c.b],
  "bias": actor("{POST}").get_editor_property("settings").get_editor_property("auto_exposure_bias"),
  "box_hidden": [box.is_hidden_ed(), box.get_editor_property("hidden")],
  "kid_hidden": [actor("{KID}").is_hidden_ed(), actor("{KID}").get_editor_property("hidden")],
  "box_z": p.z, "box_yaw": box.get_actor_rotation().yaw,
  "mat": mat.get_class().get_name(),
  "glow": mat.get_scalar_parameter_value("Intensity") if hasattr(mat, "get_scalar_parameter_value") else None,
  "tint": (lambda v: [v.r, v.g, v.b])(mat.get_vector_parameter_value("Color")) if hasattr(mat, "get_vector_parameter_value") else None,
}}
'''.format(BOX=BOX, LIGHT=LIGHT, CAM_A=CAM_A, POST=POST, KID=KID)


def read(frame: int) -> dict:
    op("seq.scrub", path=SEQ, frame=frame)
    ok(client.exec_code("pass"))  # one more editor tick for the evaluation to land
    return ok(client.exec_code(READ))


def tone(path: Path, seconds: float = 2.0, hz: float = 440.0, rate: int = 48000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * hz * i / rate)))
                               for i in range(int(seconds * rate))))


def setup():
    op("seq.close")
    op("look.camera", label=CAM_A, loc=[300, -35, 172], look_at=[-260, 15, 140], focal=28.0, aperture=5.6, pilot=False)
    op("look.camera", label=CAM_B, loc=[175, 58, 172], look_at=[0, 0, 165], focal=65.0, aperture=2.0, pilot=False)
    op("look.light", label=LIGHT, kind="point", loc=[120, -80, 120], intensity=0.0, radius=150.0)
    mat = op("look.material", name=f"MI_{P}Glow", kind="Emissive", color=[1.0, 0.5, 0.2], intensity=1.0, folder=DIR)
    op("level.spawn", label=BOX, shape="cube", loc=[80, -80, 50], size=[20, 20, 20], material=mat)
    op("level.spawn", label=KID, shape="sphere", loc=[80, -80, 70], size=[8, 8, 8])
    op("level.spawn", label=POST, cls="PostProcessVolume", loc=[2000, 2000, -2000])  # bounded, far away: affects nothing
    kids = ok(client.exec_code(f'from fmbridge.ops.level import actor\nR = unreal.AttachmentRule.KEEP_WORLD\n'
                               f'actor("{KID}").attach_to_actor(actor("{BOX}"), "", R, R, R, False)\n'
                               f'result = [a.get_actor_label() for a in actor("{BOX}").get_attached_actors()]'))
    check("kid attached to box", kids, [KID])
    wav = Path(tempfile.mkdtemp()) / "test_agent-09.wav"
    tone(wav)
    remote = rf"{PROJECT}\Saved\Import\test_agent-09.wav"
    client.push(str(wav), remote)
    return op("assets.import", files=[remote], dest=DIR)[0].split(".")[0]


def build(sound: str):
    a = op("seq.new", path=SEQ, start=-12, end=120, fps=24, replace=True)
    check("seq.new creates", a["created"], True)
    b = op("seq.new", path=SEQ, start=-12, end=132)
    check("seq.new keeps an existing sequence", [b["created"], b["end"]], [False, 132])
    op("seq.key_float", path=SEQ, label=CAM_A, component="CameraComponent", prop="FocusSettings.ManualFocusDistance",
       keys=[[0, 100.0, "linear"], [48, 300.0]])
    op("seq.key_float", path=SEQ, label=LIGHT, prop="Intensity", keys=[[0, 0.0, "constant"], [24, 50.0]])
    op("seq.key_float", path=SEQ, label=LIGHT, prop="temperature", keys=[[0, 2000.0, "linear"], [48, 6000.0]])
    op("seq.key_float", path=SEQ, label=POST, prop="Settings.AutoExposureBias", keys=[[0, 1.0, "linear"], [48, 3.0]])
    op("seq.key_color", path=SEQ, label=LIGHT, prop="LightColor", keys=[[0, [1.0, 0.0, 0.0], "constant"], [48, [0.0, 0.5, 1.0]]])
    op("seq.key_visible", path=SEQ, label=BOX, keys=[[0, True], [30, False], [60, True]], attached=True)
    op("seq.key_material", path=SEQ, label=BOX, param="Intensity", keys=[[0, 0.0, "linear"], [24, 10.0, "constant"], [48, 20.0]])
    op("seq.key_material", path=SEQ, label=BOX, param="Color", keys=[[0, [1.0, 0.0, 0.0]], [48, [0.0, 0.0, 1.0]]])
    op("seq.key_material", path=SEQ, label=BOX, param="Intensity", keys=[[0, 0.0, "linear"], [24, 10.0, "constant"], [48, 20.0]])
    op("seq.key_transform", path=SEQ, label=BOX, keys=[[0, [80, -80, 50], {"yaw": 0}, "constant"], [24, [80, -80, 80], {"yaw": 45}]])
    s = op("seq.anim", path=SEQ, label="Host", component="Body", sections=[
        {"anim": IDLE, "start": 0, "end": 72, "blend_out": 12},
        {"anim": IDLE, "start": 60, "end": 132, "offset": 1.0, "blend_in": 12, "rate": 0.9}])
    check("seq.anim rows (overlap on its own row)", [r[3] for r in s], [0, 1], 0)
    au = op("seq.audio", path=SEQ, track="VO", clips=[{"sound": sound, "start": 10, "offset": 0.5, "volume": 0.5}, [sound, 40]])
    check("seq.audio ranges (2 s tone, 0.5 s in)", [[r[1], r[2], r[3]] for r in au], [[10, 46, 0], [40, 88, 1]], 0)
    op("seq.camera_cuts", path=SEQ, cuts=[[CAM_A, -12], [CAM_B, 60]])
    check("seq.cuts reads the edit", op("seq.cuts", path=SEQ), [[CAM_A, -12, 60], [CAM_B, 60, 132]], 0)
    check("seq.rebind", op("seq.rebind", path=SEQ, labels=[CAM_A, BOX, "Nobody"]), {CAM_A: "ok", BOX: "ok", "Nobody": "missing"})
    tr = op("seq.tracks", path=SEQ)
    print(json.dumps(tr, indent=1))
    return tr


def evaluate():
    f0, f12, f36, f90 = read(0), read(12), read(36), read(90)
    check("focus f0", f0["focus"], 100.0, 0.01)
    check("focus f12 (linear)", f12["focus"], 150.0, 0.01)
    check("light intensity f12 (constant hold)", f12["intensity"], 0.0)
    check("light intensity f36 (held after the last key)", f36["intensity"], 50.0)
    check("light temperature f12", f12["temperature"], 3000.0, 1.0)
    check("light colour f0 (sRGB red)", f0["color"], [255, 0, 0], 0)
    check("post bias f12", f12["bias"], 1.5, 0.01)
    check("box visible f12", f12["box_hidden"], [False, False])
    check("box hidden f36", f36["box_hidden"], [True, True])
    check("attached kid hidden f36", f36["kid_hidden"], [True, True])
    check("box visible again f90", f90["box_hidden"], [False, False])
    check("material is dynamic", f12["mat"], "MaterialInstanceDynamic")
    check("material Intensity f12 (linear)", f12["glow"], 5.0, 0.01)
    check("material Intensity f36 (constant)", f36["glow"], 10.0, 0.01)
    check("material Color f0", f0["tint"], [1.0, 0.0, 0.0], 0.01)
    check("transform hold f12", [f12["box_z"], f12["box_yaw"]], [50.0, 0.0], 0.01)
    check("transform f36", [f36["box_z"], f36["box_yaw"]], [80.0, 45.0], 0.01)
    op("seq.close")
    after = ok(client.exec_code(READ))
    check("level restored on close (box shown, light 0)", [after["box_hidden"], after["intensity"]], [[False, False], 0.0])


def stills(local: str):
    out = rf"{PROJECT}\Saved\Test_agent-09\stills"
    res = op("seq.stills", path=SEQ, frames=[0, 90], camera="", out_dir=out, width=640, height=360, timeout=600)
    check("seq.stills through the cut", [r[1] for r in res], [CAM_A, CAM_B])
    Path(local).mkdir(parents=True, exist_ok=True)
    for _, _, p in res:
        client.pull(p, str(Path(local) / Path(p.replace("\\", "/")).name))
    op("seq.close")


def gaze():
    op("seq.anim", path=SEQ, label="Host", component="Face", sections=[{"anim": FACE, "start": 12, "end": 108}])
    r = op("anim.gaze_lock", sequence=SEQ, actor_label="Host", anim=FACE, out=f"{DIR}/AS_{P}gaze", camera=CAM_B,
           target=[150, -150, 165], frames=[36, 72], every=4, iterations=1, timeout=1800)
    print(json.dumps(r, indent=1))
    check("gaze_lock solved inside the face section", r["range"][0] >= 12 and r["range"][1] < 108, True)
    check("gaze_lock error < 1 deg", r["passes"][-1]["err_mean_deg"] < 1.0, True)
    op("seq.close")


def clean():
    op("seq.close")
    op("level.delete", labels=[KID, BOX, LIGHT, CAM_A, CAM_B, POST])
    for _, path in op("assets.list", path=DIR):
        op("assets.delete", path=path)
    ok(client.exec_code(f'import unreal\nresult = unreal.EditorAssetLibrary.delete_directory("{DIR}")'))
    print("cleaned")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gaze", action="store_true", help="also gaze_lock the host toward a point (minutes)")
    ap.add_argument("--stills", metavar="DIR", help="also stills through the cut, brought back to DIR")
    ap.add_argument("--clean", action="store_true", help="only delete what the test made")
    a = ap.parse_args()
    if a.clean:
        clean()
        sys.exit(0)
    build(setup())
    evaluate()
    if a.stills:
        stills(a.stills)
    if a.gaze:
        gaze()
    bad = [r for r in results if r[0] == "FAIL"]
    print(f"{len(results) - len(bad)}/{len(results)} passed")
    sys.exit(1 if bad else 0)
