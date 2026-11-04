"""foliage.* (B39): seeded scatters as foliage instances, converging per prefix + seed, and PCG with parameters.
The planner (ops/_foliage.py) is pure; the ops run on the fake engine (ext_foliage; traces from ext_qa)."""
import math

import pytest

from fakeunreal import pure, run_op

F = pure("ops/_foliage.py")

GRASS, ROCK = "/Game/Env/SM_Grass", "/Game/Env/SM_Rock"


def args(**kw):
    a = {"seed": 7, "region": {"rect": [[-500, -500], [500, 500]]}, "meshes": [{"mesh": GRASS}],
         "density_per_m2": 2.0}
    a.update(kw)
    return a


# --- the planner --------------------------------------------------------------------------------------------------

def test_same_seed_same_plan_other_seed_other_plan():
    a, b, c = F.plan(args()), F.plan(args()), F.plan(args(seed=8))
    assert a == b and a != c
    assert a["target"] == 200 and len(a["instances"]) == 200 and a["short"] == 0


def test_spacing_regions_and_exclusions():
    p = F.plan(args(count=60, min_dist_cm=60, region={"circle": [0, 0, 500]},
                    exclude=[{"rect": [[-100, -100], [100, 100]]}]))
    pts = [(i["x"], i["y"]) for i in p["instances"]]
    assert all(x * x + y * y <= 500 ** 2 for x, y in pts)
    assert not any(-100 <= x <= 100 and -100 <= y <= 100 for x, y in pts)
    assert min(math.dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1:]) >= 60 - 1e-6
    ring = F.plan(args(count=40, region={"ring": [0, 0, 300, 500]}))
    assert all(300 ** 2 <= i["x"] ** 2 + i["y"] ** 2 <= 500 ** 2 for i in ring["instances"])
    tri = F.plan(args(count=30, region={"polygon": [[0, 0], [800, 0], [0, 800]]}))
    assert all(i["x"] + i["y"] <= 800 + 1e-6 and i["x"] >= 0 and i["y"] >= 0 for i in tri["instances"])
    assert tri["area_m2"] == pytest.approx(32.0)


def test_weights_scale_yaw_tilt():
    p = F.plan(args(count=400, min_dist_cm=10, region={"rect": [[0, 0], [3000, 3000]]},
                    meshes=[{"mesh": GRASS, "weight": 3, "scale": [0.5, 0.7], "yaw": [10, 20], "tilt_deg": 4},
                            {"mesh": ROCK, "weight": 1, "scale": 2.0, "yaw": 90}]))
    assert p["counts"][0] + p["counts"][1] == 400 and 2.3 < p["counts"][0] / p["counts"][1] < 3.9
    for i in p["instances"]:
        if i["mesh"] == 0:
            assert 0.5 <= i["scale"][0] <= 0.7 and 10 <= i["yaw"] <= 20 and max(map(abs, i["tilt"])) <= 4
        else:
            assert i["scale"] == [2.0, 2.0, 2.0] and i["yaw"] == 90 and i["tilt"] == [0.0, 0.0]


def test_patchiness_clumps_but_keeps_count():
    flat = F.plan(args(count=150, region={"rect": [[0, 0], [2000, 2000]]}))
    clumpy = F.plan(args(count=150, region={"rect": [[0, 0], [2000, 2000]]}, patchiness=0.9, patch_cm=500))
    assert len(clumpy["instances"]) == 150 and clumpy["instances"] != flat["instances"]


def test_errors_and_helpers():
    with pytest.raises(ValueError, match="count or density"):
        F.plan({"region": {"rect": [[0, 0], [1, 1]]}, "meshes": [{"mesh": GRASS}]})
    with pytest.raises(ValueError, match="region"):
        F.plan(args(region={"blob": 1}))
    with pytest.raises(ValueError, match="meshes"):
        F.plan(args(meshes=[]))
    assert F.slope_deg((0, 0, 1)) == 0 and F.slope_deg((1, 0, 1)) == pytest.approx(45)
    pitch, roll = F.normal_rotation((math.sin(math.radians(10)), 0, math.cos(math.radians(10))))
    assert pitch == pytest.approx(-10) and roll == pytest.approx(0)
    assert F.asset_name("Lawn", 0, "/Game/Env/SM_Grass.SM_Grass") == "FT_Lawn_0_SM_Grass"
    assert F.args_hash(args()) == F.args_hash(args()) != F.args_hash(args(seed=1))


# --- the ops ------------------------------------------------------------------------------------------------------

@pytest.fixture
def stage(ue, fmb):
    ue.add_asset(GRASS, "StaticMesh")
    ue.add_asset(ROCK, "StaticMesh")
    ue.spawn("StaticMeshActor", "Floor", location=ue.Vector(0, 0, -10), extent=(1000, 1000, 10))  # top at z = 0
    return ue


def ifa_count(ue):
    a = ue.actor("InstancedFoliageActor")
    return sum(c.get_instance_count() for c in a.get_components_by_class(ue.InstancedStaticMeshComponent)) if a else 0


def test_scatter_converges_and_sits_on_the_floor(stage):
    ue = stage
    r = run_op("foliage.scatter", prefix="Lawn", seed=3, meshes=[{"mesh": GRASS, "weight": 2}, {"mesh": ROCK}],
               region={"rect": [[-500, -500], [500, 500]]}, density_per_m2=1.0)
    assert r["changed"] and r["placed"] == r["planned"] == 100 and r["dropped"] == {"no_ground": 0, "too_steep": 0}
    assert ifa_count(ue) == 100
    zs = {round(t.translation.z, 3) for c in ue.actor("InstancedFoliageActor").get_components_by_class(
        ue.InstancedStaticMeshComponent) for t in c._props["instances"]}
    assert zs == {0.0}
    again = run_op("foliage.scatter", prefix="Lawn", seed=3, meshes=[{"mesh": GRASS, "weight": 2}, {"mesh": ROCK}],
                   region={"rect": [[-500, -500], [500, 500]]}, density_per_m2=1.0)
    assert again["changed"] is False and ifa_count(ue) == 100
    other = run_op("foliage.scatter", prefix="Lawn", seed=4, meshes=[{"mesh": GRASS}],
                   region={"rect": [[-500, -500], [500, 500]]}, density_per_m2=0.5)
    assert other["changed"] and ifa_count(ue) == 50  # replaced, not added; the rock type is gone
    assert run_op("foliage.describe", prefix="Lawn")["scatters"][0]["count"] == 50
    assert ue.dialogs == []


def test_scatters_do_not_touch_each_other_and_remove(stage):
    ue = stage
    run_op("foliage.scatter", prefix="A", seed=1, meshes=[{"mesh": GRASS}], region={"circle": [0, 0, 300]}, count=30)
    run_op("foliage.scatter", prefix="B", seed=1, meshes=[{"mesh": GRASS}], region={"circle": [0, 0, 300]}, count=20)
    assert ifa_count(ue) == 50
    d = run_op("foliage.describe")
    assert [s["prefix"] for s in d["scatters"]] == ["A", "B"] and d["measured"][GRASS] == 50
    gone = run_op("foliage.remove", prefix="A")
    assert gone["changed"] and ifa_count(ue) == 20
    assert run_op("foliage.remove", prefix="A")["changed"] is False
    assert [s["prefix"] for s in run_op("foliage.describe")["scatters"]] == ["B"]


def test_off_the_floor_and_excluded_actors(stage):
    ue = stage
    ue.spawn("StaticMeshActor", "Table", location=ue.Vector(0, 0, 40), extent=(100, 60, 40))
    r = run_op("foliage.scatter", prefix="Edge", seed=2, meshes=[{"mesh": GRASS}],
               region={"rect": [[500, -500], [1500, 500]]}, count=60, exclude_actors=["Table"])
    assert r["dropped"]["no_ground"] > 0 and r["placed"] + r["dropped"]["no_ground"] == r["planned"]
    r2 = run_op("foliage.scatter", prefix="Around", seed=2, meshes=[{"mesh": GRASS}],
                region={"rect": [[-400, -400], [400, 400]]}, count=80, exclude_actors=["Table"],
                exclude_margin_cm=20)
    pts = [(t.translation.x, t.translation.y) for c in ue.actor("InstancedFoliageActor").get_components_by_class(
        ue.InstancedStaticMeshComponent) for t in c._props["instances"]]
    assert r2["placed"] == 80 and len(pts) == r["placed"] + 80
    assert not any(-120 <= x <= 120 and -80 <= y <= 80 for x, y in pts)
    flat = run_op("foliage.scatter", prefix="Flat", seed=2, meshes=[{"mesh": GRASS}], surface="flat", z_cm=55,
                  region={"rect": [[5000, 5000], [5200, 5200]]}, count=5)
    assert flat["placed"] == 5


def test_scatter_errors(stage):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("foliage.scatter", prefix="X", meshes=[{"mesh": "/Game/Nope"}], region={"rect": [[0, 0], [1, 1]]},
               count=1)
    assert e.value.code == "not_found"
    with pytest.raises(OpError) as e:
        run_op("foliage.scatter", prefix="a/b", meshes=[{"mesh": GRASS}], region={"rect": [[0, 0], [1, 1]]}, count=1)
    assert e.value.code == "bad_args"
    with pytest.raises(OpError) as e:
        run_op("foliage.scatter", prefix="X", meshes=[{"mesh": GRASS}], region={"rect": [[0, 0], [1, 1]]})
    assert e.value.code == "bad_args"
    with pytest.raises(OpError) as e:
        run_op("foliage.describe", prefix="Nothing")
    assert e.value.code == "not_found"


def test_pcg_with_parameters(stage):
    ue = stage
    ue.add_asset("/Game/PCG/PG_Forest", "PCGGraph")
    r = run_op("foliage.pcg", label="PCG_Forest", graph="/Game/PCG/PG_Forest", seed=9, params={"Count": 40,
                                                                                              "Radius": 2.5},
               loc=[0, 0, 0], extent_cm=[1000, 1000, 200])
    assert r["generated"] and r["instances"] == 40 and r["seed"] == 9 and r["graph"] == "/Game/PCG/PG_Forest"
    comp = ue.actor("PCG_Forest").get_components_by_class(ue.PCGComponent)[0]
    assert comp._props["graph_instance"]._props["params"] == {"Count": 40, "Radius": 2.5}
    again = run_op("foliage.pcg", label="PCG_Forest", params={"Count": 12})
    assert again["instances"] == 12  # regenerated, not added
    assert run_op("foliage.pcg_clear", label="PCG_Forest", delete=True)["deleted"]
    assert ue.actor("PCG_Forest") is None
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("foliage.pcg", label="Floor")
    assert e.value.code == "bad_args"


class _T:
    """Just enough of WP11's selftest T to run selftest/foliage.py on the fake: results recorded, never raised."""

    def __init__(self, tmp):
        self.prefix, self.scratch, self.tmp = "ST_foliage_", "/Game/_Selftest/foliage", tmp
        self.results, self.notes = [], []

    def op(self, name, **args):
        from fmbridge import ops
        return ops.call(name, **args)

    def call(self, name, **args):
        from fakeunreal import drive
        return drive(self.op(name, **args))[0]

    def _add(self, name, ok):
        self.results.append((name, bool(ok)))

    def check(self, name, got, want, tol=1e-3):
        self._add(name, got == want)

    def ok(self, name, cond, detail=""):
        self._add(name, cond)

    def idempotent(self, name, op, **args):
        self.call(op, **args)
        self._add(name, self.call(op, **args).get("changed") is False)

    def still(self, name, camera=None, width=960, height=540):
        yield
        return str(self.tmp / f"{name}.png")

    def metric(self, *a, **k):
        pass

    def note(self, text):
        self.notes.append(text)


def test_selftest_runs_on_the_fake(stage, tmp_path):
    from fakeunreal import drive
    import importlib
    for shape in ("Cone", "Sphere", "Cube"):
        stage.add_asset(f"/Engine/BasicShapes/{shape}", "StaticMesh")
    st = importlib.import_module("fmbridge.selftest.foliage")
    t = _T(tmp_path)
    drive(st.run(t))
    res = dict(t.results)
    for n in ("scatter placed what it planned", "nothing dropped on flat ground", "the instances are in the level",
              "no actor per instance", "cones sit on the floor's top (z 0)", "nothing inside the excluded circle",
              "scatter converges", "still the same count", "slope scatter placed its 20",
              "another seed replaces, never adds", "describe: measured cones", "removed: no instances left",
              "remove again is fine", "PCG generated", "PCG seed set"):
        assert res.get(n) is True, (n, t.results, t.notes)
    assert stage.dialogs == []


# --- the spec kind ------------------------------------------------------------------------------------------------

def test_foliage_kind_plans_and_converges(stage):
    import yaml
    from pathlib import Path
    from filmtools.unreal import foliage_kind as K, spec
    docs = list(yaml.safe_load_all((Path(__file__).resolve().parents[2] / "examples/unreal/foliage/garden.yaml")
                                   .read_text()))
    kd = spec.kinds()["foliage"]
    for d in docs:
        assert spec.validate_doc(d, kd) == [], d["name"]
    lawn = {"kind": "foliage", "version": 1, "name": "Lawn", "seed": 3, "meshes": [{"mesh": GRASS}],
            "region": {"rect": [[-300, -300], [300, 300]]}, "count": 12}
    state = run_op("foliage.scatter", **K.scatter_args(lawn), dry_run=True)
    steps = K.plan(lawn, state)
    assert [s["op"] for s in steps] == ["foliage.scatter"] and "not in the level" in steps[0]["why"]
    assert ifa_count(stage) == 0  # a dry run changes nothing
    run_op(steps[0]["op"], **steps[0]["args"])
    assert K.plan(lawn, run_op("foliage.scatter", **K.scatter_args(lawn), dry_run=True)) == []
    moved = {**lawn, "seed": 4}
    assert "changed since" in K.plan(moved, run_op("foliage.scatter", **K.scatter_args(moved), dry_run=True))[0]["why"]
