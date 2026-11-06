"""Host_Op look sheets (round 4, look round 5): headshots of N look variants under a neutral key, for the
orchestrator's picks. The variants are shown on a scratch copy of the character through a live MetaHuman preview
(mh.preview: no rig, no build), so a sheet costs seconds per variant, not a build each.

PRIVATE: every still is face data. Stills, sheets and the capture frame stay on the box; this driver prints only
paths, settings and numbers. The sheet goes to private/renders/r4/review/ with KMS (the `upload` line it prints).

Three steps, one decision per sheet (hair, iris, skin, facial, body; shape compares the solve with the capture):

    # 1. kali (the bridge client, like hair_teal_ab.py; mutating: agent-06 runs it)
    cd tools && uv run python ../films/host-studio/reel/look_sheet.py list            # the installed grooms (read-only)
    cd tools && uv run python ../films/host-studio/reel/look_sheet.py render hair --out /srv/ue/reel/r4/look
    #    (render iris --grid 5 first prints iris numbers only, to choose the iris candidates)
    # 2. the box (pillow + numpy): measure and lay out the sheet; prints only numbers
    film-ue sh "cd $R/tools && uv run --with pillow --with numpy python ../films/host-studio/reel/look_sheet.py \\
        compose /srv/ue/reel/r4/look/hair"
    # 3. the box: the sheet to private/ (KMS) and its head-object check (the compose output prints both lines)

`render` leaves the level as it found it: it hides the level's lights, sky, fog and post volumes while it shoots,
then shows them again (also on an error). If a run dies mid-sheet, `look_sheet.py restore --out ...` puts them back
from the state file. Do not save the level while a sheet renders. `teardown` removes the scratch character.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

CHAR = "/Game/Host/Host_Op"
DUP = "/Game/Host/LookLab/Host_OpLook"
BP_OP = "/Game/Host/Unpacked/Host_Op/BP_Host_Op"
PREVIEW = "LookLab_Op"
LAB = [0.0, 30000.0, 0.0]  # far from the set (the studio is within a few metres of the origin)
CHIP_TARGET = 118  # the 18% grey chip under the key, sRGB: the sheet's exposure
GREY = "/Game/FM/Materials/MI_LookLab_Grey18"
BG = "/Game/FM/Materials/MI_LookLab_Bg"

# the starting look: round 4's values, the brief's hair colour. A sheet's variants go over it (and over --base)
BASE = {"grooms": {"Hair": "WI_Hair_S_SlickBack", "Eyebrows": "WI_Eyebrows_M_Full", "Mustache": "WI_Mustache_M_Stubble",
                   "Beard": "none"},
        "hair_color": {"melanin": 1.0, "redness": 0.08}, "skin": {"u": 0.62, "v": 0.58}, "iris": {"u": 0.92, "v": 0.12}}
# his body now (bodies.py "op") and the slim one the photos show: 180 cm, narrow shoulders, lean, not muscular. The
# neck stays (40/38): the face mesh's neck already stands 0.4-2.3 cm out of the tee below the collar (agent-02, r4), so
# a narrower body neck would widen that step
BODY_NOW = {"Height": 180, "Across Shoulder": 45, "Front Interscye Length": 40, "Chest": 100, "Waist": 75,
            "High Hip": 80, "Hip": 92, "Neck Base": 40, "Neck": 38, "Bicep": 31.5, "Forearm": 27.5, "Thigh": 56,
            "Knee": 34, "Calf": 37, "Fat": -1.4, "Muscularity": 0.7, "Masculine/Feminine": -1.5}
BODY_SLIM = {**BODY_NOW, "Across Shoulder": 41, "Front Interscye Length": 37, "Chest": 92, "Waist": 72, "High Hip": 78,
             "Hip": 89, "Bicep": 27, "Forearm": 25, "Thigh": 50, "Knee": 33, "Calf": 34,
             "Fat": -1.2, "Muscularity": -0.3}
BODY_SLIMMER = {**BODY_SLIM, "Across Shoulder": 40, "Chest": 89, "Waist": 70, "Bicep": 25.5, "Thigh": 48,
                "Muscularity": -0.8}

# the target (the orchestrator's read of the operator's photos): what the hair names are matched against
HAIR_WANT = ("fringe", "bang", "messy", "side", "swept", "straight", "shag", "mop", "tousle", "part", "crop", "_m_")
HAIR_NOT = ("curl", "afro", "braid", "bun", "slick", "buzz", "bald", "dread", "cornrow", "ponytail", "mohawk",
            "wavy", "coil", "kink", "pony", "updo", "_l_", "long")

SHEETS = ("hair", "iris", "skin", "facial", "body", "shape")


def ok(res):
    if not res.get("ok"):
        raise SystemExit(json.dumps({"error": res.get("error"), "stdout": (res.get("stdout") or "")[-2000:]}))
    return res.get("result")


def client():
    from filmtools.unreal import client as c
    return c


def ex(code: str, **g):
    """Run `code` in the editor with these globals (literals); its `result`."""
    head = "".join(f"{k} = {v!r}\n" for k, v in g.items())
    return ok(client().exec_code(head + code))


def op(op_name, /, **args):
    return ok(client().op(op_name, timeout=1800, **args))


# --- editor side ---------------------------------------------------------------------------------------------------

GEO = r"""
import unreal
import importlib
_b = importlib.import_module("fmbridge.ops.mh.build")  # (fmbridge.ops.mh re-exports a build function)
a = _b._PREVIEWS.get(LABEL)
if a is None:
    raise RuntimeError("no preview " + LABEL + ": run look_sheet.py render (it spawns it)")
def sock(n):
    for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
        if c.does_socket_exist(n):
            v = c.get_socket_location(n)
            return [v.x, v.y, v.z]
    return None
eL, eR, head = sock("FACIAL_L_Eye"), sock("FACIAL_R_Eye"), sock("head")
if not (eL and eR and head):
    raise RuntimeError("no eye/head sockets on the preview: " + str([c.get_name() for c in a.get_components_by_class(unreal.SkeletalMeshComponent)]))
mid = [(p + q) / 2 for p, q in zip(eL, eR)]
f = [mid[0] - head[0], mid[1] - head[1], 0.0]
n = (f[0] ** 2 + f[1] ** 2) ** 0.5 or 1.0
f = [f[0] / n, f[1] / n, 0.0]
o, e = a.get_actor_bounds(False)
cheeks = {}
for side in ("L", "R"):
    for nm in ("FACIAL_%s_CheekOuter" % side, "FACIAL_%s_CheekInner" % side, "FACIAL_%s_Cheek" % side):
        s = sock(nm)
        if s:
            cheeks[side] = s
            break
result = {"eyeL": eL, "eyeR": eR, "head": head, "mid": mid, "facing": f, "floor": a.get_actor_location().z,
          "top": o.z + e.z, "cheeks": cheeks,
          "grooms": [c.get_name() for c in a.get_components_by_class(unreal.GroomComponent)]}
"""

SETUP = r"""
import json, os, unreal
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
state = {"vis": [], "ppv": [], "cvars": {}}
for a in eas.get_all_level_actors():
    lab = a.get_actor_label()
    if lab.startswith("LookLab_"):
        continue
    if isinstance(a, unreal.PostProcessVolume) and a.get_editor_property("enabled"):
        a.set_editor_property("enabled", False)
        state["ppv"].append(lab)
    for cls in (unreal.LightComponentBase, unreal.ExponentialHeightFogComponent, unreal.SkyAtmosphereComponent,
                unreal.VolumetricCloudComponent):
        for c in a.get_components_by_class(cls):
            if c.is_visible():
                c.set_visibility(False, False)
                state["vis"].append([lab, c.get_name()])
os.makedirs(os.path.dirname(STATE), exist_ok=True)
with open(STATE, "w") as fh:
    json.dump(state, fh)
def spawn(cls, label, loc, rot):
    for x in eas.get_all_level_actors():
        if x.get_actor_label() == label:
            eas.destroy_actor(x)
    x = eas.spawn_actor_from_class(cls, unreal.Vector(*loc), rot)
    x.set_actor_label(label)
    return x
def aim(src, dst):
    return unreal.MathLibrary.find_look_at_rotation(unreal.Vector(*src), unreal.Vector(*dst))
mid, f = G["mid"], G["facing"]
side = [f[1], -f[0], 0.0]  # his left: UE is left-handed (X forward, Y right, Z up)
ks = 1.0 if KEY_SIDE == "left" else -1.0
def at(fw, sd, up, d):
    return [mid[0] + d * (fw * f[0] + sd * ks * side[0]), mid[1] + d * (fw * f[1] + sd * ks * side[1]), mid[2] + up]
lights = {"LookLab_Key": (at(0.77, 0.64, 0, 170)[:2] + [mid[2] + 45], 1.0), "LookLab_Fill": (at(0.82, -0.57, 0, 190)[:2] + [mid[2] + 10], FILL)}
for lab, (loc, k) in lights.items():
    x = spawn(unreal.RectLight, lab, loc, aim(loc, mid))
    c = x.get_editor_property("rect_light_component")
    for p, v in (("intensity_units", unreal.LightUnits.CANDELAS), ("intensity", KEY_CD * k), ("use_temperature", True),
                 ("temperature", 5600.0), ("source_width", 120.0), ("source_height", 120.0), ("barn_door_angle", 88.0),
                 ("light_color", unreal.Color(255, 255, 255, 255)), ("cast_shadows", True)):
        try:
            c.set_editor_property(p, v)
        except Exception:
            pass
# the 18% grey chip beside the jaw on the key side, facing between the front camera and the key; the backdrop behind
plane = unreal.load_asset("/Engine/BasicShapes/Plane")
def card(lab, loc, normal, size_cm, mi):
    x = spawn(unreal.StaticMeshActor, lab, loc, unreal.MathLibrary.make_rot_from_z(unreal.Vector(*normal)))
    m = x.get_editor_property("static_mesh_component")
    m.set_mobility(unreal.ComponentMobility.MOVABLE)
    m.set_static_mesh(plane)
    m.set_material(0, unreal.load_asset(mi))
    x.set_actor_scale3d(unreal.Vector(size_cm / 100.0, size_cm / 100.0, 1.0))
    return x
kd = [0.77 * f[0] + 0.64 * ks * side[0], 0.77 * f[1] + 0.64 * ks * side[1], 0.0]
nrm = [f[0] + kd[0], f[1] + kd[1], 0.25]
chip = [mid[0] + 16 * ks * side[0] + 4 * f[0], mid[1] + 16 * ks * side[1] + 4 * f[1], mid[2] - 9]
card("LookLab_Chip", chip, nrm, 7.0, GREY)
card("LookLab_Bg", [mid[0] - 110 * f[0], mid[1] - 110 * f[1], (G["floor"] + G["top"]) / 2], f, 600.0, BG)
ppv = spawn(unreal.PostProcessVolume, "LookLab_PPV", mid, unreal.Rotator(0, 0, 0))
ppv.set_editor_property("unbound", True)
ppv.set_editor_property("priority", 1000.0)
s = ppv.get_editor_property("settings")
for p, v in (("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL), ("auto_exposure_bias", EV),
             ("auto_exposure_apply_physical_camera_exposure", False), ("white_temp", 5600.0), ("white_tint", 0.0),
             ("vignette_intensity", 0.0), ("bloom_intensity", 0.0), ("film_grain_intensity", 0.0),
             ("motion_blur_amount", 0.0), ("lens_flare_intensity", 0.0), ("depth_of_field_focal_distance", 0.0),
             ("depth_of_field_fstop", 32.0), ("color_saturation", unreal.Vector4(1, 1, 1, 1))):
    try:
        s.set_editor_property("override_" + p, True)
        s.set_editor_property(p, v)
    except Exception as e:
        state.setdefault("ppv_skipped", []).append(p)
ppv.set_editor_property("settings", s)
result = {"hidden": len(state["vis"]), "ppv_off": state["ppv"], "chip": chip, "ppv_skipped": state.get("ppv_skipped", [])}
"""

SET_EV = r"""
import unreal
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ppv = next(x for x in eas.get_all_level_actors() if x.get_actor_label() == "LookLab_PPV")
s = ppv.get_editor_property("settings")
s.set_editor_property("auto_exposure_bias", EV)
ppv.set_editor_property("settings", s)
result = EV
"""

RESTORE = r"""
import json, os, unreal
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
got = {"shown": 0, "ppv_on": 0, "removed": []}
for x in list(eas.get_all_level_actors()):
    if x.get_actor_label().startswith("LookLab_"):
        got["removed"].append(x.get_actor_label())
        eas.destroy_actor(x)
if os.path.exists(STATE):
    st = json.load(open(STATE))
    want = {}
    for lab, comp in st["vis"]:
        want.setdefault(lab, set()).add(comp)
    for a in eas.get_all_level_actors():
        lab = a.get_actor_label()
        if lab in st["ppv"]:
            a.set_editor_property("enabled", True)
            got["ppv_on"] += 1
        if lab in want:
            for c in a.get_components_by_class(unreal.ActorComponent):
                if c.get_name() in want[lab] and isinstance(c, unreal.SceneComponent):
                    c.set_visibility(True, False)
                    got["shown"] += 1
    os.rename(STATE, STATE + ".restored")
    got["expected"] = len(st["vis"])
import importlib
_b = importlib.import_module("fmbridge.ops.mh.build")  # (fmbridge.ops.mh re-exports a build function)
p = _b._PREVIEWS.pop(LABEL, None)
if p is not None:
    try:
        p.destroy_actor()
        got["removed"].append(LABEL)
    except Exception:
        pass
importlib.import_module("fmbridge.ops.view").remove_rig()
result = got
"""

HAIR_COLOR = r"""
import unreal
import importlib
_b = importlib.import_module("fmbridge.ops.mh.build")  # (fmbridge.ops.mh re-exports a build function)
G_ = importlib.import_module("fmbridge.ops.groom")
a = _b._PREVIEWS[LABEL]
out = {}
for c in a.get_components_by_class(unreal.GroomComponent):
    if c.get_name().lower().startswith(("eyelash", "peach")):
        continue
    out[c.get_name()] = bool(G_._set_params(c, {G_.PARAMS[k]: float(v) for k, v in COLOR.items()}, {}))
result = out
"""

CHIP = r"""
from fmbridge.qa import image as I
im = I.read(PATH)
x, y, r = XYR
vals = []
for j in range(int(y - r), int(y + r) + 1):
    for i in range(int(x - r), int(x + r) + 1):
        if 0 <= i < im.w and 0 <= j < im.h and (i - x) ** 2 + (j - y) ** 2 <= r * r:
            k = (j * im.w + i) * im.c
            vals.append(sum(im.data[k:k + 3]) / 3.0)
vals.sort()
result = vals[len(vals) // 2] if vals else None
"""

SPAWN_BP = r"""
import importlib, unreal
_b = importlib.import_module("fmbridge.ops.mh.build")
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for x in eas.get_all_level_actors():
    if x.get_actor_label() == LABEL:
        eas.destroy_actor(x)
cls = unreal.EditorAssetLibrary.load_blueprint_class(BP)
a = eas.spawn_actor_from_class(cls, unreal.Vector(*LOC), unreal.Rotator(0, 0, 0))
a.set_actor_label(LABEL)
_b._PREVIEWS[LABEL] = a
result = {"label": LABEL, "comps": len(a.get_components_by_class(unreal.ActorComponent))}
"""

# the built character's eye material (MI_Eye{L,R}_Baked): mh.eyes' iris primary_color_u/v are its "Iris Primary Color
# Hue"/"Value" (and secondary the same), read on BP_Host_Op r4. The live preview ignores mh.eyes (r4: 25 iris cells,
# one image), so the iris is judged on a spawned copy of the built Blueprint with these set on dynamic instances
EYE_SET = r"""
import importlib, unreal
_b = importlib.import_module("fmbridge.ops.mh.build")
a = _b._PREVIEWS[LABEL]
done = []
for c in a.get_components_by_class(unreal.SkinnedMeshComponent):
    for i, m in enumerate(c.get_materials()):
        if m is None or "eye" not in m.get_name().lower():
            continue
        names = [str(n) for n in unreal.MaterialEditingLibrary.get_scalar_parameter_names(
            m if not isinstance(m, unreal.MaterialInstanceDynamic) else m.get_editor_property("parent"))]
        if "Iris Primary Color Hue" not in names:
            continue
        mid = m if isinstance(m, unreal.MaterialInstanceDynamic) else c.create_dynamic_material_instance(i, m, "FMQA_Eye%d" % i)
        for k, v in P.items():
            mid.set_scalar_parameter_value(k, float(v))
        done.append(c.get_name() + ":" + str(i))
result = done
"""

# --- client side ---------------------------------------------------------------------------------------------------

def rot_axes(rot: dict):
    p, y = math.radians(rot["pitch"]), math.radians(rot["yaw"])
    fw = (math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p))
    rt = (-math.sin(y), math.cos(y), 0.0)
    up = (-math.sin(p) * math.cos(y), -math.sin(p) * math.sin(y), math.cos(p))
    return fw, rt, up


def project(pt, cam: dict, w: int, h: int):
    """World point -> pixel (x, y) and the pixels per cm at its depth, for a still's camera_info (horizontal fov)."""
    fw, rt, up = rot_axes(cam["rot"])
    d = [a - b for a, b in zip(pt, cam["loc"])]
    z = sum(a * b for a, b in zip(d, fw))
    k = (w / 2) / math.tan(math.radians(cam["fov"]) / 2)
    return [w / 2 + k * sum(a * b for a, b in zip(d, rt)) / z, h / 2 - k * sum(a * b for a, b in zip(d, up)) / z, k / z]


def add(p, v, s=1.0):
    return [a + s * b for a, b in zip(p, v)]


def turn(f, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [f[0] * c - f[1] * s, f[0] * s + f[1] * c, 0.0]


def views(g: dict, sheet: str, a) -> dict:
    """The cameras: {name: (loc, look_at, fov, w, h)}. Heads: front and a three-quarter from the key side."""
    mid, f = g["mid"], g["facing"]
    ks = 1 if a.key_side == "left" else -1
    if sheet == "body":
        top, floor = g["top"], g["floor"]
        c = [mid[0], mid[1], (top + floor) / 2]
        d = 520.0
        return {"front": (add(c, f, d), c, 2 * math.degrees(math.atan((top - floor) * 0.56 / d)), 768, 1024)}
    if sheet == "shape":
        d = a.capture_dist
        return {"front": (add(mid, f, d), mid, a.capture_hfov, 720, 1280)}
    look = add(mid, [0, 0, -4.0])
    d = 130.0
    fov = 2 * math.degrees(math.atan(a.frame_cm / 2 / d))
    return {"front": (add(look, f, d), look, fov, a.px, a.px),
            "tq": (add(look, turn(f, -38 * ks), d), look, fov, a.px, a.px)}


def points(g: dict, sheet: str, a) -> dict:
    """The world points measured on the stills: the irises (just in front of each eyeball's centre), the cheeks
    (the cheek joints when the face has them, else below and outside each eye), the grey chip."""
    f = g["facing"]
    side = [f[1], -f[0], 0.0]  # his left
    pts = {}
    for s, e in (("L", g["eyeL"]), ("R", g["eyeR"])):
        pts["iris" + s] = (add(e, f, 1.1), 0.55)
        sgn = 1 if s == "L" else -1
        ch = g["cheeks"].get(s) or add(add(e, [0, 0, -3.6]), side, 1.2 * sgn)
        pts["cheek" + s] = (add(ch, f, 1.5), 0.7)
    pts["chip"] = (g["chip"], 2.4)
    pts["crown"] = (add(add(g["mid"], [0, 0, 11.0]), f, 3.0), 1.2)  # the hair above the forehead (diag)
    return pts


def variants_for(sheet: str, a, wardrobe: dict) -> list:
    if a.variants:
        return json.loads(open(a.variants).read() if os.path.exists(a.variants) else a.variants)
    if sheet == "hair":
        items = a.items.split(",") if a.items else pick_hair(wardrobe.get("Hair", []))[:6]
        return [{"label": i.removeprefix("WI_Hair_"), "grooms": {"Hair": i}} for i in items]
    if sheet == "iris" and a.target in ("bp", "build"):
        uv = [tuple(map(float, x.split(":"))) for x in a.items.split(",")] if a.items else [
            (0.06, 0.20), (0.06, 0.30), (0.08, 0.25), (0.08, 0.35), (0.10, 0.30), (0.92, 0.12)]
        return [{"label": f"iris hue {u:.2f} value {v:.2f}", "eye": {"hue": u, "value": v}} for u, v in uv]
    if sheet == "iris":
        uv = [tuple(map(float, x.split(":"))) for x in a.items.split(",")] if a.items else [
            (0.92, 0.12), (0.95, 0.05), (0.85, 0.15), (0.92, 0.25), (0.75, 0.10), (0.98, 0.20)]
        return [{"label": f"iris {u:.2f}/{v:.2f}", "iris": {"u": u, "v": v}} for u, v in uv]
    if sheet == "skin":
        uv = [tuple(map(float, x.split(":"))) for x in a.items.split(",")] if a.items else [
            (0.62, 0.58), (0.55, 0.50), (0.50, 0.45), (0.58, 0.45), (0.50, 0.55)]
        return [{"label": f"skin {u:.2f}/{v:.2f}", "skin": {"u": u, "v": v}} for u, v in uv]
    if sheet == "facial":
        return facial_combos(wardrobe, a.items)
    if sheet == "body":
        return [{"label": "now (bodies.py op)", "body": BODY_NOW}, {"label": "slim", "body": BODY_SLIM},
                {"label": "slimmer", "body": BODY_SLIMMER}]
    return [{"label": "current solve (neutral)"}]


def short(p: str) -> str:
    return p.rsplit("/", 1)[-1].split(".")[0]


def pick_hair(items: list) -> list:
    names = [short(p) for p in items]
    good = [n for n in names if not any(x in n.lower() for x in HAIR_NOT)]
    return sorted(good, key=lambda n: -sum(x in n.lower() for x in HAIR_WANT))


def facial_combos(wardrobe: dict, items: str) -> list:
    """Three combinations of mustache, chin hair and stubble (the Beard slot holds one item: chin or stubble).
    `--items "M1+B1,M2+B2,..."` names them; by default the thinnest mustache with the chin/goatee and stubble beards."""
    if items:
        out = []
        for combo in items.split(","):
            m, _, b = combo.partition("+")
            out.append({"label": f"{m.removeprefix('WI_Mustache_')} + {b.removeprefix('WI_Beard_') or 'none'}",
                        "grooms": {"Mustache": m or "none", "Beard": b or "none"}})
        return out
    ms = [short(p) for p in wardrobe.get("Mustaches", [])]
    bs = [short(p) for p in wardrobe.get("Beards", [])]

    def first(names, *words):
        return next((n for w in words for n in names if w in n.lower()), "")
    thin = first(ms, "thin", "pencil", "fine", "light", "_s_") or (ms[0] if ms else "")
    stub_m = first(ms, "stubble") or thin
    chin = first(bs, "soul", "chin", "goatee", "patch")
    stub_b = first(bs, "stubble", "shadow", "5oclock", "light")
    combos = [(thin, chin), (stub_m, stub_b), (thin, stub_b)]
    return [{"label": f"{m.removeprefix('WI_Mustache_')} + {b.removeprefix('WI_Beard_') or 'none'}",
             "grooms": {"Mustache": m or "none", "Beard": b or "none"}} for m, b in combos]


def wardrobe() -> dict:
    out = {}
    for kind in ("Hair", "Eyebrows", "Mustaches", "Beards", "Peachfuzz"):
        try:
            out[kind] = op("mh.wardrobe", kind=kind)
        except SystemExit as e:
            out[kind] = ["ERR " + str(e)[:200]]
    return out


def apply_look(look: dict, label: str, skip_eye: bool = False) -> dict:
    """A look onto the scratch character (its preview follows): grooms, skin, iris, body; the hair colour onto the
    preview's groom components (the character's own colours need a built collection: docs/unreal/metahuman.md)."""
    done = {}
    for slot, item in (look.get("grooms") or {}).items():
        r = op("mh.groom", character=DUP, slot=slot, item=item, save=False)
        done[slot] = r.get("changed") if isinstance(r, dict) else r
    if look.get("skin"):
        done["skin"] = op("mh.skin", character=DUP, save=False, **look["skin"]).get("changed")
    if look.get("iris"):
        u, v = look["iris"]["u"], look["iris"]["v"]
        done["iris"] = op("mh.eyes", path=DUP, save=False, both={"iris": {
            "primary_color_u": u, "primary_color_v": v, "secondary_color_u": u, "secondary_color_v": v}}).get("changed")
    if look.get("eye") and not skip_eye:  # on a built Blueprint (--target bp|build): the eye material's parameters
        h, v = look["eye"]["hue"], look["eye"]["value"]
        p = {"Iris Primary Color Hue": h, "Iris Primary Color Value": v, "Iris Secondary Color Hue": h,
             "Iris Secondary Color Value": v, **look["eye"].get("params", {})}
        done["eye"] = ex(EYE_SET, LABEL=label, P=p)
    if look.get("body"):
        done["body"] = op("mh.body", character=DUP, measurements=look["body"]).get("changed")
    return done


def build_spawn(a, look: dict, rep: dict) -> dict:
    """--target build: the scratch copy built (textures again after a skin change, a rig after a body change) and its
    Blueprint spawned in the lab as PREVIEW; the hair colour and the eye parameters on that copy."""
    t0 = time.time()
    steps = ([("mh.rig", {"character": DUP})] if look.get("body") else []) + (
        [("mh.textures", {"character": DUP})] if (look.get("skin") or look.get("body") or a._need_tex) else []) + [
        ("mh.build", {"character": DUP, "name": "Host_OpLook", "force": True})]
    out = {}
    for step, args in steps:
        for _ in range(18):  # refused for a few ticks while a cloud request finishes (round 3)
            res = client().op(step, timeout=3600, **args)
            why = (res.get("error", "") or "") + (res.get("stdout", "") or "")
            if res.get("ok") or "cloud request is still running" not in why:
                break
            time.sleep(10)
        out[step] = ok(res)
    a._need_tex = False
    bp = out["mh.build"]["bp"]
    out["spawn"] = ex(SPAWN_BP, LABEL=PREVIEW, BP=bp, LOC=LAB)
    out["s"] = round(time.time() - t0)
    return out


def settle(a, extra: float = 0.0):
    time.sleep(a.settle + extra)


def merge(base: dict, over: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in over.items():
        out[k] = {**out.get(k, {}), **v} if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def render(a) -> None:
    sheet = a.sheet
    out = os.path.join(a.out, a.topic or sheet)
    state = os.path.join(a.out, ".lab_state.json")
    ward = wardrobe() if sheet in ("hair", "facial") else {}
    base = merge(BASE, json.loads(a.base) if a.base else {})
    vs = variants_for(sheet, a, ward)
    if not vs:
        raise SystemExit(json.dumps({"error": "no variants", "wardrobe": ward}))
    if a.grid and a.target in ("bp", "build"):  # the iris on the built eye: hue (u) over the browns x value (v)
        n = a.grid
        hs = [round(0.02 + 0.11 * i / (n - 1), 3) for i in range(n)]
        vals = [round(0.10 + 0.45 * j / (n - 1), 3) for j in range(n)]
        vs = [{"label": f"iris {h:.2f}/{v:.2f}", "eye": {"hue": h, "value": v}} for h in hs for v in vals]
    elif a.grid:  # iris or skin: a grid over the palette, numbers only (choose the sheet's candidates from it)
        n, k = a.grid, ("skin" if sheet == "skin" else "iris")
        vs = [{"label": f"{k} {u:.2f}/{v:.2f}", k: {"u": round(u, 3), "v": round(v, 3)}}
              for u in [i / (n - 1) for i in range(n)] for v in [j / (n - 1) for j in range(n)]]
    rep = {"sheet": sheet, "out": out, "base": base, "variants": [], "wardrobe": ward if sheet in ("hair", "facial") else {}}
    if a.target == "bp":  # the built Blueprint as it is: no character edits (grooms, skin, body) apply
        base = {k: v for k, v in base.items() if k in ("hair_color", "eye")}
    elif not a.no_dup:
        rep["dup"] = op("mh.duplicate", source=CHAR, path=DUP, overwrite=True)
    for mi, col in ((GREY, 0.18), (BG, 0.22)):
        op("look.material", name=short(mi), color=[col, col, col], roughness=0.95, specular=0.0)
    a._need_tex = False
    if a.target == "bp":
        rep["spawn"] = ex(SPAWN_BP, LABEL=PREVIEW, BP=BP_OP, LOC=LAB)
        rep["base_applied"] = apply_look(base, PREVIEW)
    elif a.target == "build":  # the base onto the copy; the first variant's build spawns it
        rep["can_build"] = op("mh.can_build", path=DUP)
        a._need_tex = not rep["can_build"]["can_build"]
        rep["base_applied"] = apply_look(base, PREVIEW, skip_eye=True)
        first = {k: x for k, x in vs[0].items() if k != "label"}
        rep["first_build"] = build_spawn(a, merge(base, first) if a._need_tex else first, rep)
        rep["base_eye"] = apply_look({"eye": base["eye"]}, PREVIEW) if base.get("eye") else None
    else:
        op("mh.preview", path=DUP, label=PREVIEW, loc=LAB, yaw_deg=0.0)
        rep["base_applied"] = apply_look(base, PREVIEW)
    settle(a, 4)
    if base.get("hair_color"):
        rep["hair_color"] = ex(HAIR_COLOR, LABEL=PREVIEW, COLOR=base["hair_color"])
    g = ex(GEO, LABEL=PREVIEW)
    g["chip"] = None
    ev = a.ev if a.ev is not None else 0.0
    try:
        setup = ex(SETUP, G=g, KEY_SIDE=a.key_side, STATE=state, KEY_CD=a.key_cd, FILL=a.fill, EV=ev, GREY=GREY, BG=BG)
        g["chip"] = setup["chip"]
        rep["setup"] = setup
        # (no capture frames from the editor: the identity's footage needs Capture Manager's media, which a restored
        # box lacks; asking for a frame's path then asserts and kills the editor, r4 03:14 UTC. compose takes them
        # from the raw take with ffmpeg instead)
        for i, v in enumerate(vs):
            change = {k: x for k, x in v.items() if k != "label"}
            look = merge(base, change)
            if a.target == "build":
                row = {"label": v["label"], "look": change}
                if i > 0:
                    row["applied"] = apply_look(change, PREVIEW, skip_eye=True)
                    row["build"] = build_spawn(a, change, rep)
                else:
                    row["applied"] = apply_look(change, PREVIEW, skip_eye=True)
                    row["build"] = rep["first_build"]
                if look.get("eye"):
                    row["eye"] = apply_look({"eye": look["eye"]}, PREVIEW)
                print(json.dumps({"built": v["label"], "s": row["build"].get("s")}), file=sys.stderr)
            else:
                row = {"label": v["label"], "look": change, "applied": apply_look(change, PREVIEW)}
            settle(a, 6 if v.get("body") or v.get("grooms") else 0)
            if look.get("hair_color") and (v.get("grooms") or i == 0 or a.target == "build"):
                ex(HAIR_COLOR, LABEL=PREVIEW, COLOR=look["hair_color"])
            gv = ex(GEO, LABEL=PREVIEW)
            gv["chip"] = g["chip"]
            row["geo"] = {k: gv[k] for k in ("eyeL", "eyeR", "floor", "top")}
            cams = views(gv, sheet, a)
            if a.grid:
                cams = {"front": cams["front"]}
            if i == 0 and a.ev is None:  # the exposure: the grey chip to CHIP_TARGET, then fixed for the sheet
                hv = views(gv, "hair", a)["front"]
                lin = lambda s_: ((s_ / 255 + 0.055) / 1.055) ** 2.4
                for _ in range(3):
                    r = op("view.still", out=f"{out}/_ev.png", loc=hv[0], look_at=hv[1], fov_deg=hv[2], width_px=hv[3],
                           height_px=hv[4], warmup=a.warmup)
                    x, y, k = project(g["chip"], r["camera_info"], hv[3], hv[4])
                    med = ex(CHIP, PATH=f"{out}/_ev.png", XYR=[x, y, max(2.0, k * 2.4)])
                    rep.setdefault("exposure", []).append({"chip": med, "ev": ev})
                    if not med or abs(med - CHIP_TARGET) <= 4:
                        break
                    ev = round(ev + math.log2(lin(CHIP_TARGET) / max(lin(med), 1e-4)), 2)
                    ex(SET_EV, EV=ev)
            row["stills"] = {}
            for name, (loc, at, fov, w, h) in cams.items():
                path = f"{out}/{i:02d}_{name}.png"
                r = op("view.still", out=path, loc=loc, look_at=at, fov_deg=fov, width_px=w, height_px=h,
                       warmup=a.warmup)
                cam = r["camera_info"]
                pts = {k: project(p, cam, w, h) + [rad] for k, (p, rad) in points(gv, sheet, a).items()}
                row["stills"][name] = {"path": path, "w": w, "h": h, "camera": cam, "points": pts}
            rep["variants"].append(row)
            print(json.dumps({"done": v["label"], "applied": row["applied"]}), file=sys.stderr)
        rep["ev"] = ev
    finally:
        rep["restore"] = ex(RESTORE, STATE=state, LABEL=PREVIEW)
    meta = json.dumps({**rep, "key_side": a.key_side, "key": "5600 K rect key + white fill (1:%s), WB 5600 K, manual exposure EV %s, chip 18%% -> sRGB %d"
                       % (a.fill, ev, CHIP_TARGET), "frames": {}})
    ex("import os\nos.makedirs(OUT, exist_ok=True)\nopen(OUT + '/meta.json', 'w').write(META)\nresult = OUT + '/meta.json'",
       OUT=out, META=meta)
    print(json.dumps({"meta": out + "/meta.json", "ev": ev, "exposure": rep.get("exposure"),
                      "variants": [{"label": r["label"], "applied": r["applied"]} for r in rep["variants"]],
                      "restore": rep["restore"], "setup": rep.get("setup"),
                      "capture": rep.get("capture", {}).get("calibration")}, indent=1))
    if a.grid:  # numbers only, measured on the box by compose --numbers-only
        print("next (box): look_sheet.py compose " + out + " --numbers-only")


# --- box side: measure and lay out (pillow + numpy) ----------------------------------------------------------------

def _disc(arr, x, y, r, lo=0.0, hi=1.0, lower_only=False):
    import numpy as np
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx - x, yy - y)
    m = (d <= r * hi) & (d >= r * lo)
    if lower_only:
        m &= yy >= y - 0.25 * r  # the lid hides the iris's top: keep the lower part
    return arr[m]


def _hsv(rgb):
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*[c / 255 for c in rgb])
    return [round(h * 360), round(s, 3), round(v, 3)]


def measure(im, pts: dict) -> dict:
    """Iris: the mean of the ring between pupil and limbus (no highlights, no pupil, no lid). Cheeks and the chip:
    the median of a small disc."""
    import numpy as np
    arr = np.asarray(im.convert("RGB")).astype(float)
    out = {}
    for s in ("L", "R"):
        x, y, k, rad = pts["iris" + s]
        px = _disc(arr, x, y, k * rad, 0.38, 0.88, lower_only=True)
        v = px.max(axis=1) if len(px) else px
        keep = px[(v > 12) & (v < 215)] if len(px) else px
        if len(keep) >= 6:
            m = keep.mean(axis=0)
            out["iris" + s] = {"srgb": [round(c) for c in m], "hsv": _hsv(m), "px": int(len(keep))}
        else:
            out["iris" + s] = {"px": int(len(keep)), "note": "too few iris pixels (closed eye or too small)"}
    for name in ("cheekL", "cheekR", "chip"):
        x, y, k, rad = pts[name]
        px = _disc(arr, x, y, max(2.0, k * rad))
        if len(px):
            out[name] = [round(c) for c in np.median(px, axis=0)]
    if "irisL" in out and "srgb" in out["irisL"] and "srgb" in out.get("irisR", {}):
        m = [(a + b) / 2 for a, b in zip(out["irisL"]["srgb"], out["irisR"]["srgb"])]
        out["iris"] = {"srgb": [round(c) for c in m], "hsv": _hsv(m)}
    return out


def _font(size):
    from PIL import ImageFont
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def compose(a) -> None:
    from PIL import Image, ImageDraw
    d = a.dir
    meta = json.load(open(os.path.join(d, "meta.json")))
    nums, cols = [], []
    for i, row in enumerate(meta["variants"]):
        cells, m = {}, {}
        for name, st in row["stills"].items():
            im = Image.open(st["path"])
            if name in ("front",):
                m = measure(im, st["points"])
            cells[name] = (im, st)
        nums.append({"label": row["label"], "look": row["look"], **m})
        cols.append((row["label"], cells, m))
    if a.diag:  # numbers only: are the stills different, and what is around each iris point (7x5 cells of 2 iris radii)
        import hashlib
        import numpy as np
        rows = []
        for row in meta["variants"]:
            st = row["stills"]["front"]
            arr = np.asarray(Image.open(st["path"]).convert("RGB")).astype(float)
            e = {"label": row["label"], "md5": hashlib.md5(arr.tobytes()).hexdigest()[:10],
                 "mean": [round(c) for c in arr.reshape(-1, 3).mean(axis=0)], "pts": {}}
            for k in ("irisL", "cheekL", "chip", "crown"):
                x, y, kk, rad = st["points"][k]
                r = max(2.0, kk * rad)
                grid = []
                for j in range(-2, 3):
                    line = []
                    for i in range(-3, 4):
                        cx, cy = int(x + i * 2 * r), int(y + j * 2 * r)
                        patch = arr[max(0, cy - int(r)):cy + int(r) + 1, max(0, cx - int(r)):cx + int(r) + 1]
                        line.append([round(c) for c in patch.reshape(-1, 3).mean(axis=0)] if patch.size else None)
                    grid.append(line)
                e["pts"][k] = {"xy": [round(x), round(y)], "r_px": round(r, 1), "grid": grid}
            rows.append(e)
        print(json.dumps(rows[:a.diag]))
        return
    if a.numbers_only:
        print(json.dumps(nums, indent=1))
        return
    sheet = meta["sheet"]
    cw = a.cell
    first = cols[0][1]["front"][0]
    ch = round(cw * first.height / first.width)
    rows = ["front"] + (["tq"] if "tq" in cols[0][1] else [])
    eyes = sheet == "iris"
    # the capture column: the front frame (and the turned one beside the three-quarter), cropped to the same framing
    frames = dict(meta.get("frames") or {})
    if not frames:
        frames = take_frames(a.take, d)
    cap = []
    for k in ("front", "left" if meta.get("key_side", "left") == "left" else "right"):
        p = frames.get(k)
        cap.append(Image.open(p).convert("RGB") if p and os.path.exists(p) else None)
    ncol = len(cols) + (1 if cap[0] is not None else 0)
    head, foot, eyeh = 70, 30 * (6 if sheet in ("iris", "skin") else 4), (cw // 3 if eyes else 0)
    W, H = ncol * cw, head + len(rows) * ch + eyeh + foot + 60
    out = Image.new("RGB", (W, H), (30, 30, 30))
    dr = ImageDraw.Draw(out)
    f1, f2 = _font(max(16, cw // 30)), _font(max(14, cw // 40))
    dr.text((10, H - 50), f"{sheet}: {meta['key']}. Iris = mean sRGB of the lower iris ring (front), cheeks = median "
            f"sRGB (front). Target lit cheek ~(205,143,116), shaded ~(110,75,55) in overcast daylight.", fill=(220, 220, 220), font=f2)
    x0 = 0
    if cap[0] is not None:
        for r, im in enumerate(cap[:len(rows)]):
            if im is None:
                continue
            fit = _fit_capture(im, cw / ch, a.capture_box if r == 0 else "")
            out.paste(fit.resize((cw, ch)), (0, head + r * ch))
        dr.text((10, 10), "capture (front" + (", turned" if len(rows) > 1 else "") + ")", fill=(255, 220, 120), font=f1)
        x0 = cw
    for c, (label, cells, m) in enumerate(cols):
        x = x0 + c * cw
        dr.text((x + 10, 10), f"{chr(65 + c)}  {label}", fill=(255, 255, 255), font=f1)
        for r, name in enumerate(rows):
            if name in cells:
                out.paste(cells[name][0].convert("RGB").resize((cw, ch)), (x, head + r * ch))
        if eyes:  # the eyes, enlarged: a band across both irises of the front still
            im, st = cells["front"]
            pl, pr = st["points"]["irisL"], st["points"]["irisR"]
            cx, cy = (pl[0] + pr[0]) / 2, (pl[1] + pr[1]) / 2
            half = abs(pl[0] - pr[0]) * 0.95
            band = im.convert("RGB").crop((int(cx - half), int(cy - half / 3), int(cx + half), int(cy + half / 3)))
            out.paste(band.resize((cw, eyeh)), (x, head + len(rows) * ch))
        y = head + len(rows) * ch + eyeh + 8
        lines = _lines(sheet, m, meta.get("key_side", "left"))
        for ln in lines:
            dr.text((x + 10, y), ln, fill=(230, 230, 230), font=f2)
            y += 30
    path = a.jpg or os.path.join(d, f"look_{os.path.basename(d.rstrip('/'))}.jpg")
    q = 88
    while True:
        out.save(path, "JPEG", quality=q, optimize=True)
        if os.path.getsize(path) <= a.max_mb * 1e6 or q <= 60:
            break
        q -= 6
    json.dump(nums, open(os.path.join(d, "numbers.json"), "w"), indent=1)
    print(json.dumps({"sheet": path, "bytes": os.path.getsize(path), "quality": q, "size": [W, H], "numbers": nums}, indent=1))
    key = f"renders/r4/review/{os.path.basename(path)}"
    print(f"upload (box): aws s3 cp {path} s3://rf-render-788655295054-aps1/ue-linux/private/{key} --sse aws:kms "
          f"&& aws s3api head-object --bucket rf-render-788655295054-aps1 --key ue-linux/private/{key} "
          f"--query '[ServerSideEncryption,ContentLength]'")


def _lines(sheet: str, m: dict, key_side: str = "left") -> list:
    out = []
    if "iris" in m:
        out.append(f"iris sRGB {tuple(m['iris']['srgb'])}  HSV {m['iris']['hsv'][0]}deg "
                   f"{m['iris']['hsv'][1]:.2f} {m['iris']['hsv'][2]:.2f}")
        out.append(f"  L {tuple(m['irisL']['srgb'])} R {tuple(m['irisR']['srgb'])}  px {m['irisL']['px']}/{m['irisR']['px']}")
    lit = "L" if key_side == "left" else "R"
    for k, name in (("cheek" + lit, "cheek lit"), ("cheek" + ("R" if lit == "L" else "L"), "cheek shaded")):
        if k in m:
            out.append(f"{name} sRGB {tuple(m[k])}")
    if "chip" in m:
        out.append(f"grey chip sRGB {tuple(m['chip'])}")
    return out


TAKE = "/srv/ue/projects/HostStudio/Capture/operator-face/MySlate_3"  # operator_mh.py TAKE_DIR (private/operator-face/)
TAKE_TIMES = {"front": 1.0, "left": 6.0, "right": 11.5}  # operator_mh.py FRAMES at 60 fps: 60, 360, 690


def take_frames(take: str, out: str) -> dict:
    """The capture's front and turned frames from the raw take's video, with ffmpeg (on the box: the static >= 5.1
    build or the system one; the rotation tag is applied). {} when the take is not on this box."""
    import glob
    import shutil
    import subprocess
    movs = [m for m in glob.glob(os.path.join(take, "**", "*.mov"), recursive=True) if "depth" not in m.lower()]
    ff = next((p for p in ("/srv/ue/tools/ffmpeg/bin/ffmpeg", shutil.which("ffmpeg")) if p and os.path.exists(p)), "")
    if not (movs and ff):
        print(json.dumps({"capture": "no take or no ffmpeg", "take": take, "movs": len(movs)}), file=sys.stderr)
        return {}
    got = {}
    for k, t in TAKE_TIMES.items():
        p = os.path.join(out, f"_capture_{k}.png")
        r = subprocess.run([ff, "-v", "error", "-y", "-ss", str(t), "-i", sorted(movs, key=os.path.getsize)[-1],
                            "-frames:v", "1", p], capture_output=True)
        if r.returncode == 0 and os.path.exists(p):
            got[k] = p
    return got


def _fit_capture(im, aspect: float, box: str):
    """The capture frame cropped to the render's aspect: `box` x,y,w (pixels; h from the aspect), else the frame's
    upper-centre (the take is a portrait selfie with the face in its upper middle)."""
    w, h = im.size
    if box:
        x, y, cw = [int(v) for v in box.split(",")]
    else:
        cw = int(min(w, h * aspect) * 0.92)
        x, y = (w - cw) // 2, int(h * 0.12)
    chh = int(cw / aspect)
    return im.crop((x, y, x + cw, min(h, y + chh)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the grooms installed (mh.wardrobe), and the hair the brief's description matches")
    r = sub.add_parser("render", help="the stills of one sheet's variants (mutating: agent-06 runs it)")
    r.add_argument("sheet", choices=SHEETS)
    r.add_argument("--out", default="/srv/ue/reel/r4/look", help="the box directory (a folder per sheet)")
    r.add_argument("--topic", default="", help="the folder and sheet name (default: the sheet)")
    r.add_argument("--items", default="", help="hair: item names; iris/skin: u:v,u:v; facial: M+B,M+B")
    r.add_argument("--variants", default="", help="a JSON list (or a file) of {label, grooms, skin, iris, body}")
    r.add_argument("--base", default="", help="JSON over the base look (earlier picks), e.g. '{\"grooms\": {\"Hair\": \"WI_Hair_M_X\"}}'")
    r.add_argument("--target", choices=("preview", "bp", "build"), default="build",
                   help="build (default): the scratch copy rebuilt per variant and its Blueprint spawned (textured, groomed, "
                        "~2-3 min a variant); bp: a spawned copy of BP_Host_Op as built (the iris by its eye material's "
                        "hue/value, seconds); preview: the live preview (untextured, bald, ignores eye/wardrobe edits: r4)")
    r.add_argument("--grid", type=int, default=0, help="iris or skin: an NxN palette grid, numbers only")
    r.add_argument("--px", type=int, default=1024)
    r.add_argument("--frame-cm", type=float, default=40.0, help="the headshot's frame width at the face")
    r.add_argument("--key-side", choices=("left", "right"), default="left", help="his side the key is on")
    r.add_argument("--key-cd", type=float, default=40.0)
    r.add_argument("--fill", type=float, default=0.3, help="fill / key")
    r.add_argument("--ev", type=float, default=None, help="exposure bias (default: set from the grey chip)")
    r.add_argument("--warmup", type=int, default=24)
    r.add_argument("--settle", type=float, default=2.0, help="seconds after a change before shooting")
    r.add_argument("--capture-dist", type=float, default=35.0, help="shape: the capture camera's distance, cm")
    r.add_argument("--capture-hfov", type=float, default=50.0, help="shape: the capture camera's horizontal fov")
    r.add_argument("--no-dup", action="store_true", help="reuse the scratch character as it is (a sheet after a pick)")
    s = sub.add_parser("restore", help="show the level's lights again and remove the lab (after a crashed render)")
    s.add_argument("--out", default="/srv/ue/reel/r4/look")
    sub.add_parser("teardown", help="remove the scratch character")
    c = sub.add_parser("compose", help="ON THE BOX: measure the stills and lay out the sheet (pillow, numpy)")
    c.add_argument("dir")
    c.add_argument("--cell", type=int, default=1024)
    c.add_argument("--jpg", default="")
    c.add_argument("--max-mb", type=float, default=3.0)
    c.add_argument("--capture-box", default="", help="x,y,w of the face in the capture's front frame")
    c.add_argument("--take", default=TAKE, help="the operator's take on the box (its video gives the capture column)")
    c.add_argument("--numbers-only", action="store_true")
    c.add_argument("--diag", type=int, default=0, help="numbers only: hashes and colour grids around the points, first N")
    a = ap.parse_args()
    if a.cmd == "list":
        w = wardrobe()
        print(json.dumps({"wardrobe": {k: [short(p) for p in v] for k, v in w.items()},
                          "hair_matching_brief": pick_hair(w.get("Hair", [])),
                          "facial_defaults": facial_combos(w, "")}, indent=1))
    elif a.cmd == "render":
        render(a)
    elif a.cmd == "restore":
        print(json.dumps(ex(RESTORE, STATE=os.path.join(a.out, ".lab_state.json"), LABEL=PREVIEW)))
    elif a.cmd == "teardown":
        print(json.dumps(op("mh.remove", path=DUP)))
    else:
        compose(a)


if __name__ == "__main__":
    main()
