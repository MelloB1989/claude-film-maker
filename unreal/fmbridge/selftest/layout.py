"""WP6 layout, set dressing and scene specs on a real level: level.find/get/describe/tag/folder/material,
layout.drop (bounds and trace)/relative/array/scatter/align/distribute/snap/remove (with qa.overlaps), and scene
state/plan/apply/describe/list/remove, with idempotency re-runs and a still of the dressed set from above and
from a camera. Proves that bounds-based placement agrees with the engine's real bounds (rotated meshes included) and
that a line trace finds the same table top. Also runs layout.settle (Simulate in Editor: the open question for an offscreen -unattended editor) and
checks that data layers refuse a non-partitioned level. Takes ~1.5 min (two stills, 3 s of physics). Needs: GPU for the stills (the rest runs
without one).
"""
from __future__ import annotations

REQUIRES = ["gpu"]  # the stills and physics; on -nullrhi the harness skips it
AREAS = ["level", "layout", "scene"]
NEEDS_LEVEL = True
TIMEOUT = 600

CUBE, CYL = "/Engine/BasicShapes/Cube", "/Engine/BasicShapes/Cylinder"


def run(t):
    p = t.prefix
    # --- level basics -------------------------------------------------------------------------------------------
    t.op("level.spawn", label=p + "Floor", shape="plane", loc=[0, 0, 0], size=[2000, 2000, 100])
    t.op("level.spawn", label=p + "Table", shape="cube", loc=[0, 0, 400], size=[200, 100, 75])
    t.op("level.spawn", label=p + "Cup", shape="cylinder", loc=[30, 10, 900], size=[10, 10, 12])
    found = t.op("level.find", label=p + "T*")
    t.check("level.find by glob", [f["label"] for f in found], [p + "Table"])
    t.check("bounds size of a 200x100x75 cube", found[0]["bounds"]["size"], [200, 100, 75], tol=0.5)
    t.raises("missing label suggests", "level.get", code="not_found", label=p + "Tabel")
    t.op("level.tag", labels=[p + "Table"], add=["st.hero"])
    t.check("level.find by tag", [f["label"] for f in t.op("level.find", tag="st.hero")], [p + "Table"])
    t.op("level.folder", labels=[p + "Table"], path="Selftest/Layout")
    t.check("folder", t.op("level.get", label=p + "Table")["folder"], "Selftest/Layout")
    d = t.op("level.describe")
    t.ok("level.describe counts actors", d["count"] >= 3)

    # --- drop (bounds) then trace agrees ------------------------------------------------------------------------
    r = t.op("layout.drop", labels=[p + "Table", p + "Cup"])
    t.check("table rests on the floor", t.op("level.get", label=p + "Table")["bounds"]["min"][2], 0, tol=0.5)
    t.check("cup rests on the table top", t.op("level.get", label=p + "Cup")["bounds"]["min"][2], 75, tol=0.5)
    t.idempotent("drop converges", "layout.drop", labels=[p + "Table", p + "Cup"])
    t.op("level.move", label=p + "Cup", loc=[30, 10, 300])
    r = t.op("layout.drop", labels=[p + "Cup"], mode="trace")
    t.metric("trace_cup_bottom_cm", t.op("level.get", label=p + "Cup")["bounds"]["min"][2])
    t.check("a line trace finds the same table top", t.op("level.get", label=p + "Cup")["bounds"]["min"][2], 75,
            tol=1.0)

    # --- rotated bounds: a table turned 90 degrees has a swapped footprint ---------------------------------------
    t.op("level.move", label=p + "Table", rot_={"yaw": 90})
    size = t.op("level.get", label=p + "Table")["bounds"]["size"]
    t.check("rotated table footprint swaps X and Y", size[:2], [100, 200], tol=1.0)
    t.op("level.move", label=p + "Table", rot_={"yaw": 0})

    # --- relative, patterns -----------------------------------------------------------------------------------------
    t.op("level.spawn", label=p + "Chair", shape="cube", loc=[0, 0, 500], size=[45, 45, 90])
    r = t.op("layout.relative", label=p + "Chair", of=p + "Table", offset_cm=[110, 0, 0], face="toward")
    t.check("chair in front of the table", r["loc"][:2], [110, 0], tol=0.5)
    t.check("chair faces the table", r["rot"]["yaw"], 180, tol=0.5)
    t.idempotent("relative converges", "layout.relative", label=p + "Chair", of=p + "Table", offset_cm=[110, 0, 0])
    r = t.op("layout.array", prefix=p + "Stool", shape="cylinder", pattern="circle", count=6, center=[0, 0, 0],
             radius_cm=250, face="center", scale=[0.4, 0.4, 0.5], drop=True)
    t.check("circle made 6", len(r["made"]), 6)
    t.idempotent("array converges", "layout.array", prefix=p + "Stool", shape="cylinder", pattern="circle", count=6,
                 center=[0, 0, 0], radius_cm=250, face="center", scale=[0.4, 0.4, 0.5], drop=True)
    r = t.op("layout.array", prefix=p + "Stool", shape="cylinder", pattern="circle", count=4, center=[0, 0, 0],
             radius_cm=250, face="center", scale=[0.4, 0.4, 0.5], drop=True)
    t.check("array shrinks to 4", len(t.op("level.find", label=p + "Stool_*")), 4)
    r = t.op("layout.scatter", prefix=p + "Rock", shape="sphere", count=25, region=[[-900, -900], [900, 900]],
             min_dist_cm=150, seed=5, avoid=[p + "Table"], scale_range=[0.3, 0.8])
    t.metric("scatter_placed", r["placed"])
    t.idempotent("scatter converges for a seed", "layout.scatter", prefix=p + "Rock", shape="sphere", count=25,
                 region=[[-900, -900], [900, 900]], min_dist_cm=150, seed=5, avoid=[p + "Table"],
                 scale_range=[0.3, 0.8])
    ov = t.op("qa.overlaps", labels=[f["label"] for f in t.op("level.find", label=p + "Rock_*")])
    t.check("scattered rocks do not interpenetrate (qa.overlaps)", ov["pass"], True)
    t.op("layout.align", labels=[p + "Stool_00", p + "Stool_01"], axis="z", to="min", ref_cm=0)
    t.op("layout.snap", labels=[p + "Chair"], grid_cm=10, yaw_step_deg=15)
    t.op("layout.distribute", labels=[p + "Stool_00", p + "Stool_01", p + "Stool_02"], axis="z", gap_cm=0)
    t.op("layout.remove", prefix=p + "Stool")
    t.check("layout.remove", len(t.op("level.find", label=p + "Stool_*")), 0)

    # --- scene spec ---------------------------------------------------------------------------------------------
    spec = {"kind": "scene", "version": 1, "name": "st_office", "folder": "Selftest/Office", "actors": [
        {"label": p + "S_Desk", "shape": "cube", "size": [160, 80, 75], "loc": [600, 0, 0], "rot": {"yaw": 90},
         "drop": True, "tags": ["hero"]},
        {"label": p + "S_Chair", "shape": "cube", "size": [50, 50, 90],
         "relative": {"of": p + "S_Desk", "offset_cm": [80, 0, 0], "face": "toward"}, "drop": True},
        {"label": p + "S_Lamp", "shape": "cylinder", "size": [20, 20, 45], "loc": [600, 20, 300], "drop": True},
        {"label": p + "S_Key", "class": "RectLight", "loc": [750, 120, 230], "rot": {"pitch": -30, "yaw": -140}},
    ]}
    r = t.op("scene.apply", spec=spec)
    t.check("scene.apply converged in one pass", r["remaining"], [])
    t.check("scene.plan is empty after apply", t.op("scene.plan", spec=spec)["converged"], True)
    t.idempotent("scene.apply converges", "scene.apply", spec=spec)
    t.check("lamp rests on the desk", t.op("level.get", label=p + "S_Lamp")["bounds"]["min"][2], 75, tol=0.5)
    back = t.op("scene.describe", name="st_office", folder="Selftest/Office")
    t.check("described spec has 4 actors", len(back["actors"]), 4)
    t.check("described spec applies as a no-op", t.op("scene.plan", spec=back)["converged"], True)
    t.op("level.move", label=p + "S_Key", loc=[0, 0, 0])
    t.check("drift is planned back", [s["op"] for s in t.op("scene.plan", spec=spec)["steps"]], ["level.move"])
    t.op("scene.apply", spec=spec)
    t.check("scene.list", t.op("scene.list").get("st_office"), 4)

    # --- physics settle (B38): does Simulate in Editor run in this editor (offscreen, -unattended)? -----------------
    t.op("level.spawn", label=p + "Crate", shape="cube", loc=[-600, 0, 300], size=[40, 40, 40],
         rot_={"pitch": 20, "roll": 15})
    r = yield from t.op("layout.settle", labels=[p + "Crate"], seconds=3)
    z = t.op("level.get", label=p + "Crate")["bounds"]["min"][2]
    t.metric("settle_crate_bottom_cm", z)
    t.check("a dropped crate lands on the floor under physics", z, 0, tol=3.0)
    t.ok("settle reports the crate moved", p + "Crate" in r.get("moved", {}))

    # --- data layers (B44): partitioned levels only -------------------------------------------------------------
    t.note("data layers: level.layer_* need a World Partition level; the scratch level is not one, so only the "
           "refusal is checked here")
    t.raises("data layers refuse a non-partitioned level", "level.layer_add", code="unsupported",
             name="ST_Layer", labels=[p + "Table"])

    # --- pictures ------------------------------------------------------------------------------------------------
    t.op("level.spawn", label=p + "Sun", cls="DirectionalLight", loc=[0, 0, 1000], rot_={"pitch": -50, "yaw": 30})
    t.op("level.spawn", label=p + "Sky", cls="SkyLight", loc=[0, 0, 500])
    t.op("level.spawn", label=p + "Top", cls="CineCameraActor", loc=[200, 0, 2200], rot_={"pitch": -89.9})
    t.op("level.spawn", label=p + "Cam", cls="CineCameraActor", loc=[1300, -700, 350])
    t.op("level.move", label=p + "Cam", look_at=[400, 0, 60])
    yield from t.still("set_from_above", camera=p + "Top")
    yield from t.still("set_from_camera", camera=p + "Cam")
    t.op("scene.remove", name="st_office")
    t.check("scene.remove", t.op("scene.list").get("st_office"), None)
    return {"rocks": r if isinstance(r, dict) else None}
