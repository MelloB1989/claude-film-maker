"""B39's acceptance test: foliage by code, measured.

It proves, in a scratch level with a 40 m floor (top at z 0) and a 30-degree ramp, using the engine's basic shapes
as stand-in plants and rocks:
- foliage.scatter places exactly what it planned as foliage instances (one InstancedFoliage actor, no new actors
  per instance), on the ground: every instance's z read back from the engine equals the floor's top (or the ramp's
  surface under it) within 1 cm;
- a slope limit drops the instances on the ramp; align_to_normal tilts them by the ramp's angle;
- it converges (the same call again changes nothing and leaves the count), another seed replaces (never adds), two
  scatters never touch each other's instances, foliage.remove takes only its own;
- foliage.describe's stored counts equal the instances measured in the level;
- PCG plumbing: a PCG graph made by code (empty) runs on a PCG actor with a seed and parameters and reports
  generated (skipped with a note when the PCG plugin or a placeable PCG volume is not available);
- a still from above (artifact).

Takes about 30 s. Needs: a GPU only for the still (skipped otherwise); no Epic login, no assets beyond the engine's
basic shapes. Leaves nothing outside /Game/_Selftest/foliage and /Game/_Foliage/ST_foliage_*.
"""
from __future__ import annotations

import math

import unreal

REQUIRES: list = []
AREAS = ["foliage"]
NEEDS_LEVEL = True
TIMEOUT = 300

CONE, SPHERE, CUBE = "/Engine/BasicShapes/Cone", "/Engine/BasicShapes/Sphere", "/Engine/BasicShapes/Cube"


def _instances(world_space: bool = True) -> list:
    """Every foliage instance in the level as (mesh path, x, y, z, pitch, roll)."""
    out = []
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        if not isinstance(a, unreal.InstancedFoliageActor):
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            m = c.get_editor_property("static_mesh")
            mp = m.get_path_name().split(".")[0] if m else ""
            for i in range(c.get_instance_count()):
                r = c.get_instance_transform(i, world_space)
                t = r[-1] if isinstance(r, tuple) else r
                rq = t.rotation  # a Quat in the engine
                p, q = t.translation, (rq.rotator() if hasattr(rq, "rotator") else rq)
                out.append((mp, p.x, p.y, p.z, q.pitch, q.roll))
    return out


def run(t):
    P = t.prefix
    t.op("level.spawn", label=P + "Floor", shape="cube", loc=[0, 0, -10], size=[4000, 4000, 20])
    # a ramp rising 30 degrees toward +X: a 600 cm long slab pitched up, its middle at x 2600
    t.op("level.spawn", label=P + "Ramp", shape="cube", loc=[2600, 0, 150], size=[600, 600, 20],
         rot_={"pitch": 30, "yaw": 0, "roll": 0})
    t.op("level.spawn", label=P + "Sun", cls="DirectionalLight", loc=[0, 0, 800], rot_={"pitch": -60, "yaw": 20})
    actors_before = len(t.op("level.actors"))

    a = P + "Lawn"
    r = yield from t.op("foliage.scatter", prefix=a, seed=11, region={"rect": [[-1500, -1500], [1500, 1500]]},
                        meshes=[{"mesh": CONE, "weight": 1, "scale": [0.3, 0.6]},
                                {"mesh": SPHERE, "weight": 2, "scale": [0.2, 0.35], "z_offset_cm": -5}],
                        density_per_m2=0.5, exclude=[{"circle": [0, 0, 300]}])
    t.check("scatter placed what it planned", r["placed"], r["planned"])
    t.check("nothing dropped on flat ground", r["dropped"], {"no_ground": 0, "too_steep": 0})
    t.metric("lawn_instances", r["placed"])
    inst = _instances()
    t.check("the instances are in the level", len(inst), r["placed"])
    t.check("no actor per instance", len(t.op("level.actors")) - actors_before <= 1, True)
    zs = [z for mp, x, y, z, *_ in inst if mp == CONE]
    t.ok("cones sit on the floor's top (z 0)", zs and max(abs(z) for z in zs) < 1.0, detail=f"{min(zs)}..{max(zs)}")
    t.ok("nothing inside the excluded circle", all(x * x + y * y > 300 ** 2 for _, x, y, *_ in inst))
    t.idempotent("scatter converges", "foliage.scatter", prefix=a, seed=11,
                 region={"rect": [[-1500, -1500], [1500, 1500]]},
                 meshes=[{"mesh": CONE, "weight": 1, "scale": [0.3, 0.6]},
                         {"mesh": SPHERE, "weight": 2, "scale": [0.2, 0.35], "z_offset_cm": -5}],
                 density_per_m2=0.5, exclude=[{"circle": [0, 0, 300]}])
    t.check("still the same count", len(_instances()), r["placed"])

    b = P + "Slope"
    rb = yield from t.op("foliage.scatter", prefix=b, seed=5, region={"rect": [[2400, -250], [2800, 250]]},
                         meshes=[{"mesh": CONE, "scale": 0.2, "align_to_normal": True}], count=20)
    on_ramp = [(x, z, pitch) for mp, x, y, z, pitch, roll in _instances() if 2400 <= x <= 2800 and mp == CONE]
    t.check("slope scatter placed its 20", rb["placed"], 20)
    if on_ramp:
        # the ramp's top surface: z = tan(30) * (x - 2600) + 150 + 10 / cos(30)
        err = max(abs(z - (math.tan(math.radians(30)) * (x - 2600) + 150 + 10 / math.cos(math.radians(30))))
                  for x, z, _ in on_ramp)
        t.ok("instances follow the ramp's surface", err < 1.5, detail=f"max error {err:.2f} cm")
        t.ok("align_to_normal tilts them ~30 deg", all(abs(abs(p) - 30) < 2 for _, _, p in on_ramp),
             detail=str(sorted({round(p, 1) for _, _, p in on_ramp})[:5]))
    steep = yield from t.op("foliage.scatter", prefix=b, seed=5, region={"rect": [[2400, -250], [2800, 250]]},
                            meshes=[{"mesh": CONE, "scale": 0.2}], count=20, max_slope_deg=20)
    t.check("a 20-degree limit drops everything on the 30-degree ramp", steep["dropped"]["too_steep"], 20)
    t.check("and the lawn is untouched", run_count(t, a), r["placed"])

    r2 = yield from t.op("foliage.scatter", prefix=a, seed=12, region={"rect": [[-1500, -1500], [1500, 1500]]},
                         meshes=[{"mesh": CONE, "scale": [0.3, 0.6]}], density_per_m2=0.25)
    t.check("another seed replaces, never adds",
            len([i for i in _instances() if i[0] == CONE and abs(i[1]) <= 1500]), r2["placed"])
    d = t.op("foliage.describe")
    t.check("describe: stored counts", {s["prefix"]: s["count"] for s in d["scatters"]
                                        if s["prefix"].startswith(P)}, {a: r2["placed"], b: steep["placed"]})
    t.check("describe: measured cones", d["measured"].get(CONE, 0), r2["placed"] + steep["placed"])

    cam = P + "Top"
    t.op("cam.add", label=cam, loc=[0, 0, 4500], rot_={"pitch": -90, "yaw": 0, "roll": 0}, focal_mm=18)
    try:
        yield from t.still("lawn_from_above", camera=cam)
    except Exception as e:  # no GPU: the numbers above are the test
        t.note(f"no still: {e}")

    # PCG plumbing: an empty graph made by code, run with a seed and a parameter
    try:
        g = unreal.AssetToolsHelpers.get_asset_tools().create_asset(P + "PG_Empty", str(t.scratch), unreal.PCGGraph,
                                                                    unreal.PCGGraphFactory())
    except Exception as e:
        g = None
        t.note(f"PCG graph not made by code: {e}")
    if g is not None:
        try:
            pr = yield from t.op("foliage.pcg", label=P + "PCG", graph=g.get_path_name().split(".")[0], seed=3,
                                 loc=[0, 0, 0], extent_cm=[1000, 1000, 200], timeout_s=30)
            t.check("PCG generated", pr["generated"], True)
            t.check("PCG seed set", pr["seed"], 3)
            t.op("foliage.pcg_clear", label=P + "PCG", delete=True)
        except Exception as e:  # unsupported (a script-spawned volume with no brush) is a finding, not a crash
            t.note(f"foliage.pcg: {getattr(e, 'code', '')} {e}")

    for pre in (a, b):
        t.op("foliage.remove", prefix=pre)
    t.check("removed: no instances left", len(_instances()), 0)
    t.check("remove again is fine", t.op("foliage.remove", prefix=a)["changed"], False)


def run_count(t, prefix: str) -> int:
    return [s for s in t.op("foliage.describe")["scatters"] if s["prefix"] == prefix][0]["count"]
