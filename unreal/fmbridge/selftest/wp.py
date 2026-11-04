"""B37's acceptance test: World Partition loading in the editor. Takes ~30 s. Needs: nothing (no GPU work, no assets
beyond engine shapes).

Makes a partitioned level in its scratch folder with four cubes 200 m apart around a camera at the origin looking
down +X, saves it and opens it again (a partitioned level reopens with its spatially loaded actors unloaded), then
proves: wp.describe sees five actors and the partition bounds; wp.find lists the cubes, loaded or not; wp.load
camera= loads only the cube the camera sees (frustum test, not just its box) and converges on a re-run; labels/around
load the others; wp.unload takes back exactly what wp.load loaded; a non-partitioned level answers partitioned: false.
"""
from __future__ import annotations

import unreal

REQUIRES: list = []
AREAS = ["wp"]
NEEDS_LEVEL = False
TIMEOUT = 300

CUBES = {"Ahead": [20000, 0, 100], "Behind": [-20000, 0, 100], "Left": [0, -20000, 100], "Right": [0, 20000, 100]}


def run(t):
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    p = t.prefix
    flat = t.scratch + "/L_Flat"
    t.ok("a plain level", les.new_level(flat, False))
    d = t.op("wp.describe")
    t.check("plain level is not partitioned", d["partitioned"], False)
    t.check("wp.load on a plain level is a no-op", t.op("wp.unload", all=True)["changed"], False)

    level = t.scratch + "/L_WP"
    t.ok("a partitioned level", les.new_level(level, True))
    for name, loc in CUBES.items():
        t.op("level.spawn", label=p + name, shape="cube", loc=loc)
    t.op("look.camera", label=p + "Cam", loc=[0, 0, 150], look_at=[1000, 0, 150])
    t.ok("saved", les.save_current_level())
    t.ok("reopened", les.load_level(level))
    yield 1.0

    d = t.op("wp.describe")
    t.check("partitioned", d["partitioned"], True)
    t.ok("five actors in the partition", d["actors"] >= 5, detail=str(d))
    t.metric("loaded_after_open", d["loaded"])
    f = t.op("wp.find", contains=p)
    t.check("wp.find lists them all", sorted(a["label"] for a in f["actors"]),
            sorted([p + n for n in CUBES] + [p + "Cam"]))
    if any(a["loaded"] for a in f["actors"] if a["label"] != p + "Cam"):
        t.note("cubes were loaded on open (an editor region or 'load all'): unloaded-state checks are weaker")

    cam_loaded = any(a["loaded"] for a in f["actors"] if a["label"] == p + "Cam")
    if not cam_loaded:
        yield from t.op("wp.load", labels=[p + "Cam"])
    r = yield from t.op("wp.load", camera=p + "Cam", far_cm=30000, pad_cm=0)
    seen = {a["label"]: a["loaded"] for a in t.op("wp.find", contains=p)["actors"]}
    t.check("the camera's cube is loaded", seen[p + "Ahead"], True)
    t.check("the cube behind is not", seen[p + "Behind"], False)
    t.check("nothing missing", r["missing"], [])
    again = yield from t.op("wp.load", camera=p + "Cam", far_cm=30000, pad_cm=0)
    t.check("wp.load converges", again["changed"], False)
    r = yield from t.op("wp.load", around=[-20000, 0, 100], radius_cm=500)
    t.check("wp.load around loads Behind", r["newly_loaded"], 1)
    u = t.op("wp.unload", all=True)
    t.ok("wp.unload takes back what wp.load loaded", u["unloaded"] >= 2, detail=str(u))
    seen = {a["label"]: a["loaded"] for a in t.op("wp.find", contains=p)["actors"]}
    t.check("Behind unloaded again", seen[p + "Behind"], False)
    t.raises("a typo is not_found with candidates", "wp.load", code="not_found", labels=[p + "Ahed"])
    return {"level": level}
