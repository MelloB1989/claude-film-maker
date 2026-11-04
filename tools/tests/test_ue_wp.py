"""B37: World Partition ops (ops/wp.py) on the fake partition (fakeunreal/ext_wp.py), and the frustum math
(ops/_wp.py, pure)."""
from __future__ import annotations

import math

import pytest

from fakeunreal import pure, run_op

W = pure("ops/_wp.py")

ACTORS = [
    {"label": "Rock_Near", "bounds": [[900, -50, 0], [1100, 50, 100]]},
    {"label": "Tree_Far", "bounds": [[20000, -100, 0], [20200, 100, 800]]},
    {"label": "Tree_Behind", "bounds": [[-3000, -100, 0], [-2800, 100, 800]]},
    {"label": "Sky", "bounds": [[-1e5, -1e5, -1e5], [1e5, 1e5, 1e5]], "spatial": False, "loaded": True},
    {"label": "House", "bounds": [[2000, 2000, 0], [2600, 2600, 600]], "grid": "Buildings"},
]


def test_rot_axes_match_unreal():
    f, r, u = W.rot_axes(0, 90, 0)
    assert [round(x, 6) for x in f] == [0, 1, 0] and [round(x, 6) for x in r] == [-1, 0, 0]
    f, r, u = W.rot_axes(90, 0, 0)
    assert [round(x, 6) for x in f] == [0, 0, 1] and [round(x, 6) for x in u] == [-1, 0, 0]
    f, r, u = W.rot_axes(0, 0, 0)
    assert (f, r, u) == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def test_frustum_box():
    lo, hi = W.frustum_box([0, 0, 100], {"yaw": 0}, 90.0, 2.0, far_cm=1000, near_cm=10)
    assert hi[0] == pytest.approx(1000) and lo[0] == pytest.approx(10)
    assert hi[1] == pytest.approx(1000) and lo[1] == pytest.approx(-1000)  # tan 45 = 1
    assert hi[2] == pytest.approx(100 + 500) and lo[2] == pytest.approx(100 - 500)  # aspect 2
    lo2, hi2 = W.frustum_box([0, 0, 0], {"yaw": 180}, 60.0, far_cm=1000, pad_cm=10)
    assert hi2[0] == pytest.approx(0.0, abs=1e-6)  # the near plane at x = -10, padded by 10
    assert lo2[0] == pytest.approx(-1010)


def test_box_in_frustum():
    planes = W.frustum_planes([0, 0, 0], {"yaw": 0}, 60.0, 16 / 9, far_cm=5000)
    assert W.box_in_frustum([900, -50, 0], [1100, 50, 100], planes)            # ahead
    assert not W.box_in_frustum([2000, 2000, 0], [2600, 2600, 600], planes)    # off to the side
    assert not W.box_in_frustum([-3000, -100, 0], [-2800, 100, 800], planes)   # behind
    assert not W.box_in_frustum([6000, -10, 0], [6100, 10, 10], planes)         # beyond far
    assert W.box_in_frustum([-1e5, -1e5, -1e5], [1e5, 1e5, 1e5], planes)       # around the camera
    turned = W.frustum_planes([0, 0, 0], {"yaw": 45}, 60.0, 16 / 9, far_cm=5000)
    assert W.box_in_frustum([2000, 2000, 0], [2600, 2600, 600], turned)


def test_not_partitioned_is_fine(ue, fmb):
    ue.spawn("StaticMeshActor", label="A")
    d = run_op("wp.describe")
    assert d["partitioned"] is False and d["actors"] == 1
    r = run_op("wp.load", all=True)
    assert r["partitioned"] is False and r["changed"] is False
    assert run_op("wp.find")["actors"] == []


def test_describe_and_find(ue, fmb):
    ue.partition(ACTORS)
    d = run_op("wp.describe")
    assert d["partitioned"] and d["actors"] == 5 and d["loaded"] == 1 and d["always_loaded"] == 1
    assert d["grids"] == {"MainGrid": 4, "Buildings": 1} and d["editor_bounds"]["min"][0] == -1e5
    f = run_op("wp.find", contains="tree", loaded=False)
    assert [a["label"] for a in f["actors"]] == ["Tree_Far", "Tree_Behind"] and "guid_obj" not in f["actors"][0]


def test_load_camera_frustum_waits_and_converges(ue, fmb):
    ue.partition(ACTORS)
    cam = ue.spawn("CineCameraActor", label="Cam", location=ue.Vector(0, 0, 50))
    comp = cam.get_component_by_class(ue.CameraComponent)
    comp.set_editor_property("field_of_view", 60.0)
    comp.set_editor_property("aspect_ratio", 16 / 9)
    r = run_op("wp.load", camera="Cam", far_cm=5000, pad_cm=0)
    assert r["changed"] and r["newly_loaded"] == 1 and r["missing"] == []  # Rock_Near; Sky already; Far/Behind out
    assert ue.actor("Rock_Near") is not None and ue.actor("Tree_Far") is None and ue.actor("Tree_Behind") is None
    again = run_op("wp.load", camera="Cam", far_cm=5000, pad_cm=0)
    assert again["changed"] is False and again["already_loaded"] == again["requested"]


def test_load_labels_box_around_all_and_unload(ue, fmb):
    from fmbridge.errors import OpError
    ue.partition(ACTORS)
    assert run_op("wp.load", labels=["House"])["newly_loaded"] == 1
    assert run_op("wp.load", around=[20100, 0, 0], radius_cm=500)["newly_loaded"] == 1
    assert run_op("wp.load", box=[[-3500, -500, 0], [-2500, 500, 500]])["newly_loaded"] == 1
    with pytest.raises(OpError, match="exactly one"):
        run_op("wp.load", labels=["House"], all=True)
    with pytest.raises(OpError) as e:
        run_op("wp.load", labels=["Hous"])
    assert e.value.code == "not_found" and e.value.candidates == ["House"]
    u = run_op("wp.unload", labels=["House", "Sky"])
    assert u["unloaded"] == 1 and u["kept"] == ["Sky"] and ue.actor("House") is None
    assert run_op("wp.unload", all=True)["unloaded"] == 2
    assert run_op("wp.unload", all=True)["changed"] is False


def test_load_reports_actors_that_never_appear(ue, fmb):
    ue.partition([{"label": "Broken", "bounds": [[0, 0, 0], [10, 10, 10]], "never_loads": True}])
    r = run_op("wp.load", all=True, timeout_s=0.0)
    assert r["missing"] == ["Broken"] and r["changed"] is False


def test_bad_box_and_non_camera(ue, fmb):
    from fmbridge.errors import OpError
    ue.partition(ACTORS)
    with pytest.raises(OpError, match="min is above max"):
        run_op("wp.load", box=[[10, 0, 0], [0, 10, 10]])
    ue.spawn("StaticMeshActor", label="NotCam")
    with pytest.raises(OpError, match="no camera component"):
        run_op("wp.load", camera="NotCam")


def test_load_through_a_shot(ue, fmb, monkeypatch):
    ue.partition(ACTORS + [{"label": "CamB", "bounds": [[0, 0, 0], [10, 10, 10]], "cls": "CineCameraActor"}])
    ca = ue.spawn("CineCameraActor", label="CamA", location=ue.Vector(0, 0, 50))
    ca.get_component_by_class(ue.CameraComponent).set_editor_property("field_of_view", 60.0)
    ue.add_sequence("/Game/S/Seq", 0, 48, 24)
    monkeypatch.setattr(fmb.seq, "cut_camera", lambda path, f: "CamA" if f < 24 else "CamB")
    gen = fmb.call("wp.load", sequence="/Game/S/Seq", frames=[0, 48], every=12, far_cm=5000, pad_cm=0)
    from fakeunreal import drive

    def turn_b(_dt):  # CamB arrives as the descriptor's actor: aim it at the house
        b = ue.actor("CamB")
        if b is not None and not getattr(b, "_aimed", False):
            object.__setattr__(b, "_aimed", True)
            b.set_actor_rotation(ue.Rotator(yaw=45))
            b.get_component_by_class(ue.CameraComponent).set_editor_property("field_of_view", 60.0)
    ue.register_slate_post_tick_callback(turn_b)
    r, _ = drive(gen)
    assert r["cameras"] == ["CamA", "CamB"] and ue.actor("Rock_Near") is not None and ue.actor("House") is not None
    assert ue.actor("Tree_Behind") is None
    assert ue.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence() is None  # closed again
