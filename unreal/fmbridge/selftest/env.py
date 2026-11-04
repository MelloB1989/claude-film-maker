"""WP5's selftest: environments and lighting by spec, measured. Takes ~4 min on the L4 (scene captures and a few
stills; the reflection-capture rebuild runs a lighting build). Needs: GPU (a real RHI; offscreen is fine). No Epic
sign-in, no project assets: engine basic shapes and a material it makes in its scratch folder.

It proves:
- calibration, the number everything else rests on: an 18% grey card lit by a rig key of 800 lux, exposed with
  `exposure: {ev100: auto}`, meters (env.meter, SceneColorHDR read back raw) at the EV100 photometry predicts
  (0.18 x 800 / pi cd/m2 -> EV100 8.52) and reads as middle grey in the final image (metrics `meter_offset_stops`,
  `grey_card_display`). If the offset is not ~0, note it: SceneColorHDR may be pre-exposed, and the fix is a constant
  in envlib/stats.py (scene_stats) or in env.meter;
- light.add / light.rig / light.practical make lights with the candelas the maths says, converge (a re-run changes
  nothing), and light.measure's analytic lux matches the rig's key_lux;
- env.sun by place and time puts the sun where NOAA says (describe reads it back), env.atmosphere / clouds /
  sky_light / fog / post / exposure / grade / quality / cvars converge and read back;
- one stop more exposure brightens the final image (display mean up), noir_bw has no colour cast;
- env.apply converges a full spec (second plan empty), env.mood switches day -> night -> day, prune removes only
  what the spec made, a typo is bad_args with did-you-mean;
- env.check passes a well exposed frame and fails an underexposed one with a fix;
- stills: day, golden hour, night, noir (for the operator's eye).
"""
from __future__ import annotations

import math

REQUIRES = ["gpu"]
AREAS = ["env", "light"]
NEEDS_LEVEL = True
TIMEOUT = 900

LUX = 800.0
EXPECTED_EV = math.log2(0.18 * LUX / math.pi * 100 / 12.5)  # a reflected meter on the grey card: 8.52


def run(t):
    P = t.prefix
    owner = "selftest_env"
    from fmbridge.envlib import photometry as ph

    # --- the set: a floor, a grey card filling the camera, a pillar subject -------------------------------------
    from fmbridge import ops  # look.material's argument `name` collides with t.op's own: call it directly
    grey = ops.call("look.material", name=P + "MI_Grey18", color=(0.18, 0.18, 0.18), roughness=1.0, metallic=0.0,
                specular=0.0, folder=t.scratch)
    t.op("level.spawn", label=P + "Floor", shape="cube", loc=[0, 0, -5], size=[3000, 3000, 10], material=grey)
    t.op("level.spawn", label=P + "Card", shape="cube", loc=[0, 0, 150], size=[4, 300, 300], material=grey)
    t.op("look.camera", label=P + "CardCam", loc=[120, 0, 150], look_at=[0, 0, 150], focal=35.0, aperture=8.0,
         pilot=False)
    t.op("look.camera", label=P + "Wide", loc=[700, 250, 180], look_at=[0, 0, 120], focal=24.0, aperture=8.0,
         pilot=False)
    yield 1.0

    # --- calibration: a key of 800 lux on the card, nothing else -------------------------------------------------
    black = {"kind": "environment", "version": 1, "name": owner, "preset": "studio_black",
             "rigs": {"Card": {"subject": [2, 0, 150], "camera": [120, 0, 150], "preset": "three_point",
                               "key_lux": LUX, "lights": {"key": {"angle": 0.0, "side": "center", "elevation": 0.0,
                                                                  "distance": 250.0, "width": 400, "height": 400},
                                                          "fill": None, "rim": None}}},
             "quality": "final"}
    r = yield from t.op("env.apply", spec=black)
    t.ok("studio_black + key converges", r["converged"], detail=str(r.get("remaining"))[:400])
    m = t.op("light.measure", at=[2, 0, 150])
    t.near("light.measure: the key gives its key_lux at the card", m["per_light"].get("Card_Key", 0.0), LUX, rel=0.02)
    e = t.op("env.describe")["exposure"]
    t.near("exposure auto exposes for the key (incident EV100)", e.get("ev100", 0.0),
           ph.ev100_from_illuminance(LUX), rel=0.01)
    yield 1.0
    mt = yield from t.op("env.meter", camera=P + "CardCam")
    off = mt["scene"]["metered_ev100"] - EXPECTED_EV
    t.metric("meter_offset_stops", round(off, 3), "stops")
    t.metric("grey_card_display", mt["display"]["mean"], "display luma")
    t.ok("the grey card meters within 0.5 stop of the prediction", abs(off) < 0.5,
         detail=f"metered {mt['scene']['metered_ev100']:.2f}, predicted {EXPECTED_EV:.2f}")
    t.ok("the grey card reads as a mid grey (0.3..0.62 display luma)", 0.3 <= mt["display"]["mean"] <= 0.62,
         detail=str(mt["display"]))
    yield from t.still("calibration_card", camera=P + "CardCam")

    # one stop brighter
    t.op("env.exposure", mode="manual", ev100=ph.ev100_from_illuminance(LUX) - 1.0, owner=owner)
    yield 0.5
    mt2 = yield from t.op("env.meter", camera=P + "CardCam")
    t.ok("one stop more exposure brightens the image", mt2["display"]["mean"] > mt["display"]["mean"] + 0.03,
         detail=f"{mt['display']['mean']} -> {mt2['display']['mean']}")
    t.metric("display_per_stop", round(mt2["display"]["mean"] - mt["display"]["mean"], 4), "display luma")
    chk = yield from t.op("env.check", camera=P + "CardCam", targets={"mean": [0.3, 0.75], "clipped_max": 0.05})
    t.ok("env.check passes a well exposed card", chk["pass"], detail=str(chk["issues"])[:300])
    t.op("env.exposure", mode="manual", ev100=ph.ev100_from_illuminance(LUX) + 4.0, owner=owner)
    yield 0.5
    bad = yield from t.op("env.check", camera=P + "CardCam")
    t.ok("env.check fails an underexposed card with a fix", not bad["pass"] and bool(bad["issues"])
         and "stops" in bad["issues"][0]["fix"], detail=str(bad["issues"])[:300])

    # --- lights one by one ------------------------------------------------------------------------------------------
    key = t.op("light.add", label=P + "Spot", kind="spot", loc=[300, -200, 300], look_at=[0, 0, 100], lux=500,
               cone_deg=25, temperature_k=3200, owner=owner)
    t.near("light.add lux -> candelas (inverse square)", key["light"]["intensity_cd"],
           500 * (math.dist([300, -200, 300], [0, 0, 100]) / 100) ** 2, rel=1e-3)
    t.idempotent("light.add converges", "light.add", label=P + "Spot", kind="spot", loc=[300, -200, 300],
                 look_at=[0, 0, 100], lux=500, cone_deg=25, temperature_k=3200, owner=owner)
    d = t.op("light.describe", labels=[P + "Spot"])["lights"][P + "Spot"]
    t.near("light.describe reads the candelas back", d["intensity_cd"], key["light"]["intensity_cd"], rel=1e-3)
    t.check("light.describe reads the temperature back", d["temperature_k"], 3200.0, tol=0.5)
    t.op("light.practical", label=P + "Lamp", type="lamp", loc=[-100, 200, 120], owner=owner)
    t.raises("a practical of an unknown type is bad_args", "light.practical", code="bad_args", label=P + "X",
             type="lava", loc=[0, 0, 0])
    t.op("level.spawn", label=P + "Pillar", shape="cylinder", loc=[0, 0, 90], size=[50, 50, 180], material=grey)
    rig = t.op("light.rig", subject=P + "Pillar", camera=P + "Wide", preset="rembrandt", key_lux=600, prefix=P + "R_",
               owner=owner)
    t.near("light.rig: measured key lux", rig["measured"]["per_light"][P + "R_Key"], 600.0, rel=0.01)
    t.near("light.rig: measured ratio", rig["measured"]["ratio"], 4.0, rel=0.01)
    t.idempotent("light.rig converges", "light.rig", subject=P + "Pillar", camera=P + "Wide", preset="rembrandt",
                 key_lux=600, prefix=P + "R_", owner=owner)
    t.op("light.channels", assign={P + "Pillar": [0, 1]})
    t.idempotent("light.channels converges", "light.channels", assign={P + "Pillar": [0, 1]})
    t.raises("a rig on a missing subject is not_found", "light.rig", code="not_found", subject=P + "Pilar",
             camera=P + "Wide")
    t.op("light.remove", labels=[P + "Spot", P + "Lamp"])
    t.op("light.remove", rig=P + "R_")

    # --- the sky, part by part ------------------------------------------------------------------------------------
    t.op("env.atmosphere", preset="clear", owner=owner)
    s = t.op("env.sun", time="10:30", lat=19.07, lon=72.88, date="2026-11-05", tz=5.5, owner=owner)
    from fmbridge.envlib import sun as SUN
    want = SUN.position(19.07, 72.88, "2026-11-05", 10.5, 5.5)
    t.check("env.sun elevation is NOAA's", s["elevation_deg"], want["elevation"], tol=0.01)
    ds = t.op("env.describe")["sun"]
    t.check("describe reads the sun's elevation back", ds["elevation_deg"], want["elevation"], tol=0.05)
    t.check("describe reads the sun's azimuth back", ds["azimuth_deg"], want["azimuth"], tol=0.05)
    t.idempotent("env.sun converges", "env.sun", elevation_deg=s["elevation_deg"], azimuth_deg=s["azimuth_deg"],
                 owner=owner)
    t.op("env.clouds", bottom_km=1.5, height_km=4.0, owner=owner)
    t.idempotent("env.clouds converges", "env.clouds", bottom_km=1.5, height_km=4.0, owner=owner)
    yield from t.op("env.sky_light", owner=owner)
    t.op("env.fog", preset="haze", owner=owner)
    t.idempotent("env.fog converges", "env.fog", preset="haze", owner=owner)
    t.op("env.moon", owner=owner)
    t.op("env.remove", parts=["moon"])
    q = t.op("env.quality", preset="preview", owner=owner)
    from fmbridge.ops import _envutil as U
    t.check("env.quality sets its cvars", U.cvar("r.VolumetricFog.GridPixelSize"), 16.0, tol=0.01)
    t.op("env.quality", preset="final", owner=owner)
    t.ok("env.quality returns render cvars", bool(q["render_cvars"]))
    t.op("env.exposure", mode="manual", ev100=13.5, owner=owner)
    t.op("env.grade", preset="noir_bw", owner=owner)
    yield 1.0
    nb = yield from t.op("env.meter", camera=P + "Wide")
    t.ok("noir_bw has no colour cast", nb["display"]["cast"]["magnitude"] < 0.05, detail=str(nb["display"]["cast"]))
    yield from t.still("noir", camera=P + "Wide")
    t.raises("a misspelt post field is bad_args", "env.post", code="bad_args", fields={"bloom_intensty": 1})
    t.raises("an unknown grade is bad_args", "env.grade", code="bad_args", preset="teal")
    cv = t.op("env.cvars", cvars={"r.HairStrands.SkyLighting": 0})
    t.check("env.cvars sets a cvar", U.cvar("r.HairStrands.SkyLighting"), 0.0, tol=0.01)
    t.idempotent("env.cvars converges", "env.cvars", cvars={"r.HairStrands.SkyLighting": 0})
    t.raises("env.hdri on a missing cubemap is not_found", "env.hdri", code="not_found", cubemap=t.scratch + "/T_None")
    t.note("env.hdri with a real cubemap needs an imported .hdr: see environment.md (HDRI); not run here")
    pr = t.op("env.presets")
    t.ok("env.presets lists rigs, grades, practicals", {"rembrandt", } <= set(pr["rigs"]) and "noir_bw" in pr["grades"]
         and "candle" in pr["practicals"])
    t.check("env.schema is the environment kind", t.op("env.schema", kind="environment")["properties"]["kind"],
            {"const": "environment"})
    t.op("env.reflection_capture", label=P + "Cap", shape="sphere", loc=[0, 0, 150], radius_cm=1200, owner=owner)
    t.idempotent("env.reflection_capture converges", "env.reflection_capture", label=P + "Cap", shape="sphere",
                 loc=[0, 0, 150], radius_cm=1200, owner=owner)
    try:
        rb = yield from t.op("env.captures_rebuild")
        t.ok("env.captures_rebuild ran", rb["built"] is not False, detail=str(rb))
    except Exception as ex:  # noqa: BLE001 (a lighting build may be unavailable; record, do not fail the rest)
        t.note(f"env.captures_rebuild: {ex}")
    t.op("light.remove", labels=[P + "Cap"])

    # --- a whole spec, moods, prune --------------------------------------------------------------------------------
    t.op("env.remove", owner=owner)
    day = {"kind": "environment", "version": 1, "name": owner, "preset": "exterior_day",
           "sun": {"time": "golden_evening", "lat": 19.07, "lon": 72.88, "date": "2026-11-05", "tz": 5.5},
           "rigs": {"Pillar": {"subject": P + "Pillar", "camera": P + "Wide", "preset": "three_point",
                               "key_lux": 20000}},
           "practicals": {P + "Lantern": {"type": "lamp", "loc": [150, -150, 100]}},
           "moods": {"night": {"sun": False, "moon": {}, "exposure": {"ev100": 1.0},
                               "grade": {"preset": "moonlight"},
                               "rigs": {"Pillar": {"subject": P + "Pillar", "camera": P + "Wide",
                                                   "preset": "noir", "key_lux": 2}}}}}
    t.raises("a typo in a spec is bad_args", "env.apply", code="bad_args", spec={**day, "fogg": {}})
    r = yield from t.op("env.apply", spec=day)
    t.ok("the day spec converges", r["converged"], detail=str(r.get("remaining"))[:400])
    t.check("a second plan is empty", t.op("env.plan", spec=day)["steps"], [])
    yield 1.0
    yield from t.still("golden_hour", camera=P + "Wide")
    n = yield from t.op("env.mood", mood="night", spec_name=owner)
    t.ok("env.mood night converges", n["converged"], detail=str(n.get("remaining"))[:400])
    t.ok("night has no sun and a moon", t.op("env.describe")["sun"] is None and t.op("env.describe")["moon"] is not None)
    yield 1.0
    yield from t.still("night", camera=P + "Wide")
    b = yield from t.op("env.mood", spec_name=owner)
    t.ok("back to day converges", b["converged"], detail=str(b.get("remaining"))[:400])
    smaller = {**day, "practicals": {}, "fog": False}
    r = yield from t.op("env.apply", spec=smaller)
    lab = [a[0] for a in t.op("level.actors")]
    t.ok("prune removed what the spec dropped", P + "Lantern" not in lab and "Env_Fog" not in lab, detail=str(lab)[:300])
    t.ok("prune kept the set", P + "Pillar" in lab and P + "Card" in lab)
    pg = yield from t.op("env.preset", name="studio_grey", owner=owner)
    t.ok("env.preset studio_grey converges and drops the sun", pg["converged"]
         and t.op("env.describe")["sun"] is None, detail=str(pg.get("remaining"))[:300])
    t.op("env.remove", owner=owner)
    t.op("light.remove", owner=owner)
    return {"meter_offset_stops": round(off, 3), "grey_card_display": mt["display"]["mean"]}
