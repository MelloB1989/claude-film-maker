"""WP3 MetaHuman creation, end to end on the box. Part 1 (no cloud): presets, a character from a preset and a blank one,
body measurements (constraint copies, range warnings, idempotent), face blend of two presets and a landmark move
(applied once), skin/freckles/texture resolution, eyes, eyelashes, teeth, makeup, the hair groom with melanin and
redness and its instance parameters, slots, describe/export, a variant copy, actionable errors, the live preview actor
and a still of it, mh.apply on a spec twice (second run changes nothing). Part 2 (only with the Epic sign-in, else
noted and skipped): the cloud rig (multi-tick, ~30 s) and its up-to-date skip, the textures (~20 s), the cinematic
build (~3 min on an L4, the editor blocks), the built Blueprint placed, a garment of its own dressed on it with leader
pose (checked on the bones), a prop riding a bone, the clipping check, stills. Takes ~2 min without the cloud, ~6 min
with it. Needs: the MetaHuman Creator core data (presets); GPU for the stills; the Epic sign-in for part 2
(film-ue epic-login once per box).
"""
from __future__ import annotations

AREAS = ["mh"]
NEEDS_LEVEL = True
TIMEOUT = 1500


def run(t):
    p = t.prefix
    s = t.scratch
    presets = t.op("mh.presets")
    t.ok("presets ship with the engine (Creator core data)", len(presets) >= 2, detail=str(presets[:6]))
    if len(presets) < 2:
        t.skip("no MetaHuman presets: the MetaHumanCharacter plugin's Optional content is missing")
    a, b = presets[0], presets[1]
    ch = f"{s}/MH_{p}A"

    # --- create -------------------------------------------------------------------------------------------------
    r = t.op("mh.add", path=ch, preset=a)
    t.ok("mh.add from a preset", r["changed"], detail=str(r))
    t.idempotent("mh.add converges", "mh.add", path=ch, preset=a)
    t.raises("a wrong preset suggests the right one", "mh.add", code="not_found", path=f"{s}/MH_{p}X",
             preset=a[:-1] + "x")
    blank = t.op("mh.add", path=f"{s}/MH_{p}Blank", blank=True)
    t.check("a blank character", blank["from"], "blank")

    # --- body ---------------------------------------------------------------------------------------------------
    cons = t.op("mh.body_constraints", path=ch)
    t.ok("body constraints listed with ranges", "Height" in cons and "Waist" in cons, detail=str(list(cons)[:12]))
    r = t.op("mh.body", character=ch, measurements={"Height": 172, "Waist": 66})
    t.check("body measurements set", [r["body"]["Height"], r["body"]["Waist"]], [172, 66], tol=0.5)
    t.idempotent("mh.body converges", "mh.body", character=ch, measurements={"Height": 172, "Waist": 66})
    got = t.op("mh.body_constraints", path=ch)
    t.check("the solver holds the targets", [got["Height"]["value"], got["Waist"]["value"]], [172, 66], tol=0.5)
    t.raises("an unknown constraint suggests", "mh.body", code="bad_args", character=ch, measurements={"Wiast": 60})

    # --- face ---------------------------------------------------------------------------------------------------
    r = t.op("mh.face", path=ch, blend={a: 0.6, b: 0.4})
    t.ok("face blend of two presets changes the face", r["changed"] and r["max_delta"] > 0, detail=str(r))
    t.idempotent("the same blend again changes nothing", "mh.face", path=ch, blend={a: 0.6, b: 0.4})
    lm = t.op("mh.face_landmarks", path=ch)
    t.ok("face landmarks listed", lm["count"] > 0, detail=str(lm["count"]))
    if lm["count"]:
        before = lm["landmarks"][0]
        t.op("mh.face", path=ch, landmarks={"0": [0, 0, 0.3]})
        t.op("mh.face", path=ch, landmarks={"0": [0, 0, 0.3]})  # applied once
        after = t.op("mh.face_landmarks", path=ch)["landmarks"][0]
        t.metric("landmark0_dz_cm", round(after[2] - before[2], 3), "cm")
        t.ok("a landmark delta applies once, not twice", abs(after[2] - before[2]) < 0.6,
             detail=f"{before} -> {after}")

    # --- skin, eyes, head model, makeup ----------------------------------------------------------------------------
    r = t.op("mh.skin", character=ch, u=0.62, v=0.44, settings={"freckles": {"density": 0.4, "mask": "Type1"}},
             texture_resolution="2k")
    t.check("skin tone", [r["u"], r["v"]], [0.62, 0.44], tol=1e-3)
    t.check("freckle mask by name", r["skin_settings"]["freckles"]["mask"], "TYPE1")
    t.idempotent("mh.skin converges (no needless commit: it would drop the cloud textures)", "mh.skin",
                 character=ch, u=0.62, v=0.44)
    t.raises("a misspelt skin field suggests", "mh.skin", code="bad_args", character=ch, settings={"freckels": {}})
    r = t.op("mh.eyes", path=ch, both={"iris": {"iris_pattern": "Iris003", "primary_color_u": 0.25}})
    t.check("iris pattern", r["eyes_settings"]["eye_left"]["iris"]["iris_pattern"], "IRIS003")
    r = t.op("mh.eyelashes", path=ch, settings={"type": "LongCurl", "melanin": 0.85})
    t.check("eyelashes", [r["eyelashes"]["type"], r["eyelashes"]["melanin"]], ["LONG_CURL", 0.85], tol=1e-3)
    r = t.op("mh.teeth", path=ch, settings={"overbite": 0.2, "worn_down": 0.1})
    t.check("teeth", r["teeth"]["overbite"], 0.2, tol=1e-3)
    r = t.op("mh.makeup", path=ch, settings={"lips": {"type": "Natural", "color": [0.3, 0.06, 0.05]}})
    t.check("lip makeup", r["makeup_settings"]["lips"]["type"], "NATURAL")
    t.raises("a wrong enum lists the valid ones", "mh.makeup", code="bad_args", path=ch,
             settings={"lips": {"type": "Glossy"}})
    fields = t.op("mh.settings_fields", path=ch, which="makeup")
    t.ok("settings fields readable", "lips" in fields)

    # --- wardrobe -------------------------------------------------------------------------------------------------
    hair = [x for x in t.op("mh.wardrobe", kind="Hair")]
    t.ok("hair grooms in the wardrobe", bool(hair), detail=str(hair[:3]))
    if hair:
        r = t.op("mh.groom", character=ch, slot="Hair", item=hair[0], melanin=0.95, redness=0.05)
        t.ok("hair worn", r["changed"], detail=str(r))
        t.check("hair colour set", [r["params"]["Melanin"], r["params"]["Redness"]], [0.95, 0.05], tol=1e-3)
        t.idempotent("the same groom again changes nothing (no second palette entry)", "mh.groom", character=ch,
                     slot="Hair", item=hair[0], melanin=0.95, redness=0.05)
        ip = t.op("mh.item_params", character=ch, slot="Hair")
        t.ok("groom parameters listed", "Melanin" in ip["params"], detail=str(sorted(ip["params"])))
        t.raises("a misspelt parameter suggests", "mh.item_set", code="bad_args", character=ch, slot="Hair",
                 params={"Melanine": 0.5})
    t.op("mh.clear_slot", character=ch, slot="Beard")
    pal = t.op("mh.palette", character=ch)
    t.ok("palette lists slots", "Hair" in pal["slots"], detail=str(pal["slots"]))

    # --- describe, export, variant ------------------------------------------------------------------------------
    d = t.op("mh.describe", path=ch)
    t.check("describe: body", d["body"].get("Height"), 172, tol=0.5)
    spec = t.op("mh.export", path=ch)
    t.check("export is a character spec", spec["kind"], "character")
    import json
    with open(t.path("mh_export.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=1)
    t.artifact(t.path("mh_export.json"))
    v = t.op("mh.duplicate", source=ch, path=f"{s}/MH_{p}Variant")
    t.ok("a variant copy", v["changed"])
    t.check("the variant keeps the body", t.op("mh.describe", path=v["path"])["body"].get("Height"), 172, tol=0.5)
    cb = t.op("mh.can_build", path=ch)
    t.ok("can_build explains what is missing", cb["can_build"] or bool(cb["hint"]), detail=str(cb))

    # --- preview and a still ------------------------------------------------------------------------------------
    prev = t.op("mh.preview", path=ch, label=p + "Preview", loc=[0, 0, 0], yaw_deg=180)
    t.idempotent("preview converges on its label", "mh.preview", path=ch, label=p + "Preview", loc=[0, 0, 0],
                 yaw_deg=180)
    t.op("look.camera", label=p + "Cam", loc=[160, 0, 165], look_at=[0, 0, 160], focal=50.0, pilot=False)
    yield from t.still("preview_face", camera=p + "Cam")
    t.note(f"preview actor {prev['label']}")

    # --- a spec, applied twice ---------------------------------------------------------------------------------------
    sp = {"kind": "character", "version": 1, "name": p + "Spec", "asset": f"{s}/MH_{p}Spec", "from": {"preset": b},
          "body": {"Height": 176}, "skin": {"u": 0.4}, "eyelashes": {"type": "ShortFine"}, "rig": "none",
          "build": False}
    r1 = yield from t.op("mh.apply", spec=sp)
    r2 = yield from t.op("mh.apply", spec=sp)
    t.ok("mh.apply makes the character", r1["changed"])
    t.ok("mh.apply again changes nothing", not r2["changed"],
         detail=str([x["op"] for x in r2["steps"] if x["changed"]]))

    # --- part 2: the cloud ------------------------------------------------------------------------------------------
    caps = t.box.get("capabilities", {})
    if not caps.get("mh_cloud"):
        t.note("part 2 skipped: no Epic sign-in on this box (film-ue epic-login, then run again)")
        return {"cloud": False}
    r = yield from t.op("mh.rig", character=ch)
    t.ok("cloud rig", r["changed"], detail=str(r))
    t.metric("rig_s", r["seconds"], "s")
    r = yield from t.op("mh.rig", character=ch)
    t.ok("rig again: up to date, no request", not r["changed"])
    r = yield from t.op("mh.textures", character=ch)
    t.ok("cloud textures", r["has_high_res_textures"])
    t.metric("textures_s", r["seconds"], "s")
    r = t.op("mh.build", character=ch, bp_name=p + "A")
    t.ok("build makes the Blueprint", bool(r["bp"]), detail=str(r))
    t.metric("build_s", r["seconds"], "s")
    t.idempotent("build again: up to date", "mh.build", character=ch, bp_name=p + "A")
    d = t.op("mh.describe", path=ch)
    t.ok("describe: built and not stale", not d["build"]["stale"] and not d["rig_stale"], detail=str(d["build"]))

    # placed, dressed in a garment of its own (its own built-in garment mesh reused as the 'custom' one)
    label = p + "Placed"
    t.op("level.spawn", label=label, asset=r["bp"], loc=[0, 300, 0])
    comps = t.op("mh.components", label=label)
    t.ok("assembled actor has Body and Face", "Body" in comps and "Face" in comps, detail=str(list(comps)))
    if "Body" not in comps:
        return {"cloud": True, "bp": d["build"]["bp"], "placed": False}
    garment = next((v["mesh"] for k, v in comps.items() if k not in ("Body", "Face") and v["mesh"]), None)
    if garment:
        r = t.op("mh.dress", label=label, garments={"Extra": {"mesh": garment.split(".")[0]}})
        t.ok("dressed, leader pose on every garment", r["ok"], detail=str(r["garments"]))
        lc = t.op("mh.leader_check", label=label)
        t.ok("garments sit on the body's bones", lc["pass"], detail=lc["why"])
        t.metric("garment_bone_gap_cm", lc["metric"], "cm")
        t.idempotent("dress converges", "mh.dress", label=label, garments={"Extra": {"mesh": garment.split(".")[0]}})
        try:
            cc = yield from t.op("mh.clip_check", label=label, garment="Extra")
            t.metric("clip_poke_fraction", cc["metric"])
            t.note(f"clip_check: {cc['why']} (max {cc['max_cm']} cm)")
        except Exception as e:  # experimental: record, do not fail the area
            t.note(f"clip_check could not run: {e}")
    t.op("level.spawn", label=p + "Watch", shape="cube", loc=[0, 300, 100], size=[4, 4, 1])
    r = t.op("mh.attach", label=label, prop=p + "Watch", bone="hand_l")
    t.ok("a prop rides a bone", r["changed"])
    t.idempotent("attach converges", "mh.attach", label=label, prop=p + "Watch", bone="hand_l")
    t.op("look.camera", label=p + "Cam2", loc=[260, 300, 120], look_at=[0, 300, 110], focal=35.0, pilot=False)
    yield from t.still("built_dressed", camera=p + "Cam2")
    return {"cloud": True, "bp": d["build"]["bp"]}
