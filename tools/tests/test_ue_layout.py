"""WP6 layout, set dressing and scene specs on the fake engine: level.find/get/describe, layout.drop/relative/
array/scatter/align/distribute/snap/overlaps, and the scene spec (validate, plan, apply, converge, round trip)."""
from __future__ import annotations

import pytest

from fakeunreal import pure, run_op

L = pure("ops/_layout.py")
S = pure("ops/_scene.py")


def _shapes(ue):
    for s in ("Cube", "Sphere", "Cylinder", "Cone", "Plane"):
        ue.add_asset(f"/Engine/BasicShapes/{s}", "StaticMesh")
    ue.add_asset("/Game/Props/SM_Chair", "StaticMesh")
    ue.add_asset("/Game/Props/SM_Desk", "StaticMesh")
    ue.add_asset("/Game/M/MI_Oak", "MaterialInstanceConstant")


# ---- pure math

def test_poisson_is_deterministic_spaced_and_clear():
    a = L.poisson(40, [[0, 0], [1000, 1000]], 100, seed=3, exclude=[[[400, 400], [600, 600]]])
    assert a == L.poisson(40, [[0, 0], [1000, 1000]], 100, seed=3, exclude=[[[400, 400], [600, 600]]])
    assert a != L.poisson(40, [[0, 0], [1000, 1000]], 100, seed=4)
    assert len(a) == 40
    for i, p in enumerate(a):
        assert 0 <= p[0] <= 1000 and 0 <= p[1] <= 1000
        assert not (400 <= p[0] <= 600 and 400 <= p[1] <= 600)
        for q in a[i + 1:]:
            assert (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 >= 100 ** 2 - 1e-6


def test_poisson_stops_when_full():
    assert len(L.poisson(500, [[0, 0], [300, 300]], 100, seed=1)) < 500


def test_rest_z_picks_highest_support_below():
    cup = ((-5, -5, 200), (5, 5, 210))
    table = ((-50, -50, 0), (50, 50, 75))
    shelf = ((-50, -50, 300), (50, 50, 310))  # above the cup: ignored
    assert L.rest_z(cup, [table, shelf]) == pytest.approx(75 - 200)
    assert L.rest_z(((200, 200, 50), (210, 210, 60)), [table]) == pytest.approx(-50)  # floor
    assert L.rest_z(((200, 200, 50), (210, 210, 60)), [table], floor=None) is None


def test_patterns():
    assert L.row(3, [0, 0, 0], [10, 0, 0]) == [[0, 0, 0], [10, 0, 0], [20, 0, 0]]
    assert L.grid(4, [0, 0, 0], [10, 20, 0], 2)[3] == [10, 20, 0]
    c = L.circle(4, [0, 0, 0], 100)
    assert c[1] == pytest.approx([0, 100, 0], abs=1e-9)
    arc = L.circle(3, [0, 0, 0], 100, 0, 180)
    assert arc[2] == pytest.approx([-100, 0, 0], abs=1e-9)
    assert L.local_to_world([0, 0, 0], 90, [100, 0, 0]) == pytest.approx([0, 100, 0], abs=1e-9)
    assert L.match("Chair_03", "chair_*") and L.match("BigChair", "chair") and not L.match("Desk", "Chair")
    assert L.numbered("R", 3, 150) == "R_003" and L.numbered("R", 3, 5) == "R_03"


def test_align_and_distribute():
    b = {"a": ((0, 0, 0), (10, 10, 10)), "b": ((50, 5, 0), (70, 15, 10))}
    assert L.align(b, "x", "min") == {"a": 0, "b": -50}
    assert L.align(b, "y", "max", 20) == {"a": 10, "b": 5}
    d = L.distribute({**b, "c": ((200, 0, 0), (210, 10, 10))}, ["a", "b", "c"], "x")
    assert d["a"] == 0 and d["c"] == 0 and d["b"] == pytest.approx(105 - 60)
    g = L.distribute(b, ["a", "b"], "x", gap=5)
    assert g["b"] == pytest.approx((15 + 10) - 60)


# ---- level

def test_find_get_describe(ue):
    _shapes(ue)
    run_op("level.spawn", label="Desk", asset="/Game/Props/SM_Desk", loc=[0, 0, 0])
    run_op("level.spawn", label="Chair_00", asset="/Game/Props/SM_Chair", loc=[100, 0, 0])
    run_op("level.spawn", label="Chair_01", asset="/Game/Props/SM_Chair", loc=[500, 0, 0])
    run_op("level.spawn", label="Key", cls="RectLight", loc=[0, 0, 300])
    found = run_op("level.find", label="chair_*", near=[0, 0, 0], radius_cm=200)
    assert [f["label"] for f in found] == ["Chair_00"]
    assert found[0]["mesh"] == "/Game/Props/SM_Chair" and found[0]["bounds"]["size"] == [100, 100, 100]
    assert [f["label"] for f in run_op("level.find", cls="light")] == ["Key"]
    run_op("level.tag", labels=["Desk"], add=["hero"])
    assert [f["label"] for f in run_op("level.find", tag="hero")] == ["Desk"]
    run_op("level.folder", labels=["Desk"], path="Office")
    assert run_op("level.get", label="Desk")["folder"] == "Office"
    d = run_op("level.describe")
    assert d["count"] == 4 and d["lights"] == ["Key"] and d["by_class"]["StaticMeshActor"] == 3


def test_missing_actor_suggests(ue):
    _shapes(ue)
    run_op("level.spawn", label="Desk", shape="cube")
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("level.get", label="Dsk")
    assert e.value.code == "not_found" and e.value.candidates == ["Desk"]
    with pytest.raises(ValueError):  # still a ValueError for older callers
        run_op("level.move", label="Nope", loc=[0, 0, 0])


def test_spawn_without_source_is_actionable(ue):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("level.spawn", label="X")
    assert e.value.code == "bad_args"


# ---- layout

def test_drop_stacks_in_order(ue):
    _shapes(ue)
    run_op("level.spawn", label="Table", shape="cube", loc=[0, 0, 300], size=[200, 100, 80])
    run_op("level.spawn", label="Box", shape="cube", loc=[10, 0, 900], size=[20, 20, 20])
    r = run_op("layout.drop", labels=["Table", "Box"])
    assert r["changed"] and ue.actor("Table").get_actor_location().z == pytest.approx(40)
    assert ue.actor("Box").get_actor_location().z == pytest.approx(80 + 10)
    assert run_op("layout.drop", labels=["Table", "Box"])["changed"] is False


def test_relative_places_and_faces(ue):
    _shapes(ue)
    run_op("level.spawn", label="Desk", asset="/Game/Props/SM_Desk", loc=[0, 0, 50], rot_={"yaw": 90})
    run_op("level.spawn", label="Chair", asset="/Game/Props/SM_Chair", loc=[0, 0, 500])
    r = run_op("layout.relative", label="Chair", of="Desk", offset_cm=[80, 0, 0], face="toward")
    assert r["loc"][:2] == pytest.approx([0, 80], abs=1e-6)
    assert r["rot"]["yaw"] == pytest.approx(-90)
    assert r["loc"][2] == pytest.approx(50)  # resting on the floor (50 cm half height)
    assert run_op("layout.relative", label="Chair", of="Desk", offset_cm=[80, 0, 0])["changed"] is False


def test_array_converges_and_shrinks(ue):
    _shapes(ue)
    r = run_op("layout.array", prefix="Chair", asset="/Game/Props/SM_Chair", pattern="circle", count=6,
               center=[0, 0, 0], radius_cm=120, face="center")
    assert r["made"] == [f"Chair_0{k}" for k in range(6)]
    yaw = ue.actor("Chair_00").get_actor_rotation().yaw
    assert yaw == pytest.approx(180)
    again = run_op("layout.array", prefix="Chair", asset="/Game/Props/SM_Chair", pattern="circle", count=6,
                   center=[0, 0, 0], radius_cm=120, face="center")
    assert again["changed"] is False
    fewer = run_op("layout.array", prefix="Chair", asset="/Game/Props/SM_Chair", pattern="circle", count=4,
                   center=[0, 0, 0], radius_cm=120, face="center")
    assert sorted(fewer["removed"]) == ["Chair_04", "Chair_05"] and len(fewer["moved"]) == 3
    assert len(run_op("level.find", label="Chair_*")) == 4
    assert ue.dialogs == []
    assert run_op("layout.remove", prefix="Chair")["removed"] and not run_op("level.find", label="Chair_*")


def test_array_leaves_unowned_actors_alone(ue):
    _shapes(ue)
    run_op("level.spawn", label="Chair_09", asset="/Game/Props/SM_Chair")  # not made by the pattern
    run_op("layout.array", prefix="Chair", asset="/Game/Props/SM_Chair", count=2)
    assert ue.actor("Chair_09") is not None


def test_scatter_is_seeded_and_avoids(ue):
    _shapes(ue)
    run_op("level.spawn", label="Path", shape="cube", loc=[0, 0, 0], size=[1000, 100, 2])
    r = run_op("layout.scatter", prefix="Rock", shape="sphere", count=20, region=[[-500, -500], [500, 500]],
               min_dist_cm=120, seed=7, avoid=["Path"], scale_range=[0.5, 1.5])
    assert r["placed"] == 20
    locs = {f["label"]: f["loc"] for f in run_op("level.find", label="Rock_*")}
    assert all(abs(p[1]) > 50 + 60 for p in locs.values())
    again = run_op("layout.scatter", prefix="Rock", shape="sphere", count=20, region=[[-500, -500], [500, 500]],
                   min_dist_cm=120, seed=7, avoid=["Path"], scale_range=[0.5, 1.5])
    assert again["changed"] is False


def test_align_distribute_snap_then_qa_overlaps(ue):
    _shapes(ue)
    for i, x in enumerate((0, 37, 300)):
        run_op("level.spawn", label=f"B{i}", shape="cube", loc=[x, i * 13, 50])
    run_op("layout.align", labels=["B0", "B1", "B2"], axis="y", to="min")
    assert {round(ue.actor(f"B{i}").get_actor_location().y, 6) for i in range(3)} == {0}
    run_op("layout.distribute", labels=["B0", "B1", "B2"], axis="x", gap_cm=10)
    assert [ue.actor(f"B{i}").get_actor_location().x for i in range(3)] == pytest.approx([0, 110, 220])
    run_op("level.move", label="B1", loc=[63.7, 0, 50])
    run_op("layout.snap", labels=["B1"], grid_cm=10)
    assert ue.actor("B1").get_actor_location().x == pytest.approx(60)
    run_op("level.move", label="B2", loc=[30, 0, 50])
    ov = run_op("qa.overlaps", labels=["B0", "B2"])
    assert not ov["pass"] and ov["issues"]


# ---- scene spec

SPEC = {"kind": "scene", "version": 1, "name": "office", "folder": "Office", "actors": [
    {"label": "Desk", "asset": "/Game/Props/SM_Desk", "loc": [0, 0, 0], "rot": {"yaw": 90}, "drop": True,
     "material": "/Game/M/MI_Oak", "tags": ["hero"]},
    {"label": "Chair", "asset": "/Game/Props/SM_Chair", "relative": {"of": "Desk", "offset_cm": [80, 0, 0]},
     "drop": True},
    {"label": "Lamp", "shape": "cylinder", "loc": [0, 0, 400], "size": [20, 20, 60], "drop": True},
    {"label": "Key", "class": "RectLight", "loc": [150, 120, 230]},
]}


def test_scene_validate_catches_mistakes():
    assert S.validate(SPEC) == []
    bad = {**SPEC, "actors": [{"label": "A", "asset": "/Game/X", "shape": "cube", "rot": [0, 90, 0], "colour": 1},
                              {"label": "A", "class": "PointLight", "relative": {"of": "Nope"}}]}
    errs = " | ".join(S.validate(bad))
    for frag in ("exactly one of asset, shape, class", "never a list", "unknown key 'colour'", "appears twice",
                 "relative.of must name"):
        assert frag in errs


def test_scene_apply_converges_and_round_trips(ue):
    _shapes(ue)
    r = run_op("scene.apply", spec=SPEC)
    assert r["changed"] and r["remaining"] == []
    desk, chair, lamp = ue.actor("Desk"), ue.actor("Chair"), ue.actor("Lamp")
    assert desk.get_actor_location().z == pytest.approx(50)  # dropped onto the floor
    assert chair.get_actor_location().x == pytest.approx(0, abs=1e-6)
    assert chair.get_actor_location().y == pytest.approx(80)
    assert chair.get_actor_rotation().yaw == pytest.approx(-90)
    assert lamp.get_actor_scale3d().z == pytest.approx(0.6)
    assert desk.get_folder_path() == "Office" and "fm.scene:office" in [str(t) for t in desk.tags]
    assert run_op("scene.plan", spec=SPEC) == {"steps": [], "converged": True}
    assert run_op("scene.apply", spec=SPEC)["changed"] is False
    assert run_op("scene.list") == {"office": 4}
    back = run_op("scene.describe", name="office", folder="Office")
    assert S.validate(back) == []
    # the described spec, applied, changes nothing
    assert run_op("scene.plan", spec=back)["converged"]
    assert ue.dialogs == []


def test_scene_moves_what_drifted_and_prunes(ue):
    _shapes(ue)
    run_op("scene.apply", spec=SPEC)
    run_op("level.move", label="Key", loc=[0, 0, 0])
    steps = run_op("scene.plan", spec=SPEC)["steps"]
    assert [s["op"] for s in steps] == ["level.move"] and steps[0]["args"]["label"] == "Key"
    smaller = {**SPEC, "prune": True, "actors": SPEC["actors"][:2]}
    r = run_op("scene.apply", spec=smaller)
    assert r["steps"][-1]["op"] == "level.delete" and sorted(r["steps"][-1]["args"]["labels"]) == ["Key", "Lamp"]
    assert ue.actor("Lamp") is None and ue.actor("Desk") is not None


def test_scene_replaces_wrong_source(ue):
    _shapes(ue)
    run_op("level.spawn", label="Desk", shape="cube")
    steps = run_op("scene.plan", spec=SPEC)["steps"]
    assert steps[0]["op"] == "level.spawn" and steps[0]["args"]["asset"] == "/Game/Props/SM_Desk"


def test_scene_bad_spec_is_bad_args(ue):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("scene.apply", spec={"kind": "scene"})
    assert e.value.code == "bad_args" and e.value.details["errors"]


def test_schema_file_and_example_are_current():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    assert json.loads((root / "tools/filmtools/unreal/schemas/scene.schema.json").read_text()) == \
        json.loads(json.dumps(S.SCHEMA)), "regenerate scene.schema.json from ops/_scene.py SCHEMA"
    yaml = pytest.importorskip("yaml")
    for p in sorted((root / "examples/unreal/scene").glob("*.yaml")):
        assert S.validate(yaml.safe_load(p.read_text())) == [], p.name


def test_example_office_applies(ue):
    yaml = pytest.importorskip("yaml")
    from pathlib import Path
    _shapes(ue)
    spec = yaml.safe_load((Path(__file__).resolve().parents[2] / "examples/unreal/scene/office.yaml").read_text())
    r = run_op("scene.apply", spec=spec)
    assert r["remaining"] == [] and ue.actor("Lamp").get_actor_location().z == pytest.approx(75 + 22.5)


def test_settle_bakes_where_physics_left_them(ue):
    _shapes(ue)
    run_op("level.spawn", label="Book", shape="cube", loc=[0, 0, 300], size=[20, 30, 4])
    run_op("level.spawn", label="Mug", shape="cylinder", loc=[100, 0, 5], size=[8, 8, 10])
    comp = ue.actor("Book").static_mesh_component
    comp._props["mobility"] = "STATIC"

    def physics(world):  # the book falls and tips; the mug stays
        book = next(a for a in world.actors() if a.get_actor_label() == "Book")
        book.set_actor_location(ue.Vector(3, -2, 2))
        book.set_actor_rotation(ue.Rotator(roll=0, pitch=0, yaw=37))
    ue.on_simulate = physics
    r = run_op("layout.settle", labels=["Book", "Mug"], seconds=0)
    assert set(r["moved"]) == {"Book"} and r["still"] == ["Mug"]
    assert r["moved"]["Book"]["loc"] == [3, -2, 2] and r["moved"]["Book"]["rot"]["yaw"] == 37
    assert ue.pie is False and comp.is_simulating_physics() is False and comp._props["mobility"] == "STATIC"


def test_settle_refuses_during_play(ue):
    _shapes(ue)
    run_op("level.spawn", label="Book", shape="cube")
    ue.pie = True
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("layout.settle", labels=["Book"])
    assert e.value.code == "conflict"


def test_data_layers(ue):
    _shapes(ue)
    for lab in ("Lamp", "Candle", "Desk"):
        run_op("level.spawn", label=lab, shape="cube")
    r = run_op("level.layer_add", name="Night", labels=["Lamp", "Candle"])
    assert r == {"changed": True, "created": True, "added": ["Lamp", "Candle"]}
    assert "/Game/DataLayers/Night" in ue.assets
    assert run_op("level.layer_add", name="Night", labels=["Lamp", "Candle"])["changed"] is False
    assert run_op("level.layers")["layers"] == [{"name": "Night", "visible": True, "initially_visible": True,
                                                  "runtime": False, "actors": ["Candle", "Lamp"]}]
    assert run_op("level.layer_set", name="Night", visible=False)["set"] == ["visible"]
    assert run_op("level.layer_set", name="Night", visible=False)["changed"] is False
    assert run_op("level.layer_remove", name="Night", labels=["Lamp", "Desk"])["removed"] == ["Lamp"]
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("level.layer_set", name="Nite", visible=True)
    assert e.value.candidates == ["Night"]


def test_data_layers_need_a_partitioned_level(ue):
    ue.partitioned = False
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("level.layer_add", name="Night")
    assert e.value.code == "unsupported"
