"""pose.* (B31): the pose library and its closed-loop solve. The library (ops/_pose.py) is pure; the ops run on
the fake engine with a fake Control Rig whose controls move their bones (ext_pose)."""
import math

import pytest

from fakeunreal import pure, run_op

P = pure("ops/_pose.py")

# a standing figure facing +X (its right is +Y), pelvis at 95 cm
BONES = {"pelvis": (0, 0, 95), "spine_05": (0, 0, 140), "head": (0, 0, 160), "neck_01": (0, 0, 150),
         "clavicle_l": (0, -15, 145), "clavicle_r": (0, 15, 145), "upperarm_l": (0, -18, 143),
         "upperarm_r": (0, 18, 143), "hand_l": (0, -25, 85), "hand_r": (0, 25, 85), "foot_l": (0, -10, 9),
         "foot_r": (0, 10, 9), "ball_l": (12, -10, 3), "ball_r": (12, 10, 3)}


def test_body_frame_faces_where_the_clavicles_say():
    f = P.body_frame(BONES)
    assert f["forward"] == pytest.approx((1, 0, 0)) and f["right"] == pytest.approx((0, 1, 0))
    turned = {k: (-v[1], v[0], v[2]) for k, v in BONES.items()}  # the figure turned 90 deg: facing +Y
    g = P.body_frame(turned)
    assert g["forward"] == pytest.approx((0, 1, 0)) and g["right"] == pytest.approx((-1, 0, 0))
    with pytest.raises(ValueError, match="pelvis"):
        P.body_frame({"head": (0, 0, 1)})


def test_goals_in_the_body_frame():
    g = P.goals_world("hands_on_hips", BONES)
    assert g["hand_l"] == pytest.approx([2, -24, 101]) and g["hand_r"] == pytest.approx([2, 24, 101])
    assert g["foot_l"] == pytest.approx([0, -10, 9])  # kept
    sit = P.goals_world("sit", BONES, {"drop_cm": 40})
    assert sit["pelvis"] == pytest.approx([-5, 0, 55])
    custom = P.goals_world({"hand_r": {"anchor": "head", "offset": [10, 0, 0]}, "hand_l": [1, 2, 3]}, BONES)
    assert custom == {"hand_r": pytest.approx([10, 0, 160]), "hand_l": [1.0, 2.0, 3.0]}
    for name in P.POSES:
        assert P.goals_world(name, BONES)
    with pytest.raises(ValueError, match="unknown pose"):
        P.goals_world("moonwalk", BONES)
    with pytest.raises(ValueError, match="effector"):
        P.goals_world({"tail": [0, 0, 0]}, BONES)


def test_errors_and_controls():
    e = P.errors({"hand_l": [0, -25, 95]}, BONES)
    assert e["hand_l"][0] == pytest.approx(10) and e["hand_l"][1] == pytest.approx([0, 0, 10])
    controls = ["root_ctrl", "body_ctrl", "hand_l_ik_ctrl", "hand_r_ik_ctrl", "hand_l_fk_ctrl", "foot_l_ik_ctrl",
                "foot_r_ik_ctrl", "spine_05_fk_ctrl", "head_fk_ctrl"]
    found, missing = P.resolve_controls(controls, ["hand_l", "hand_r", "foot_l", "pelvis", "chest", "head"])
    assert found == {"hand_l": "hand_l_ik_ctrl", "hand_r": "hand_r_ik_ctrl", "foot_l": "foot_l_ik_ctrl",
                     "pelvis": "body_ctrl", "chest": "spine_05_fk_ctrl", "head": "head_fk_ctrl"} and not missing
    found, missing = P.resolve_controls(["CTRL_A", "CTRL_B"], ["hand_l"], {"hand_l": "CTRL_C"})
    assert not found and "hand_l" in missing
    other = P.resolve_controls(["LeftHandIK", "l_hand_ik_goal"], ["hand_l"])[0]
    assert other == {"hand_l": "l_hand_ik_goal"}


# --- the ops on the fake ------------------------------------------------------------------------------------------

CONTROLS = {"hand_l_ik_ctrl": "hand_l", "hand_r_ik_ctrl": "hand_r", "foot_l_ik_ctrl": "foot_l",
            "foot_r_ik_ctrl": "foot_r", "body_ctrl": "pelvis", "spine_05_fk_ctrl": "spine_05", "head_fk_ctrl": "head"}


@pytest.fixture
def host(ue, fmb):
    ue.spawn("SkeletalMeshActor", "Host")
    ue.pose("Host", {k: list(v) for k, v in BONES.items()})
    ue.add_asset("/Game/T/Seq", "LevelSequence")
    return ue.rig("Host", CONTROLS, gain=0.7)


def _bones(ue):
    return ue.actor("Host").get_components_by_class(ue.SkeletalMeshComponent)[0]._props["bones"]


def test_apply_solves_closed_loop(ue, host):
    r = run_op("pose.apply", label="Host", sequence="/Game/T/Seq", frame=48, pose="hands_on_hips")
    assert r["pass"] and r["iterations"] >= 2 and max(r["errors_cm"].values()) <= 1.0
    assert r["controls"]["hand_l"] == "hand_l_ik_ctrl" and r["controls"]["foot_l"] == "foot_l_ik_ctrl"
    assert _bones(ue)["hand_r"] == pytest.approx([2, 24, 101], abs=1.0)
    assert all(f == 48 for _, f in host.writes)
    chk = run_op("pose.check", label="Host", sequence="/Game/T/Seq", frame=48, pose="hands_on_hips")
    assert chk["pass"] and chk["issues"] == []
    again = run_op("pose.apply", label="Host", sequence="/Game/T/Seq", frame=48, pose="hands_on_hips")
    assert again["iterations"] == 0 and again["changed"] is False


def test_sit_keeps_the_feet(ue, host):
    r = run_op("pose.apply", label="Host", sequence="/Game/T/Seq", frame=10, pose="sit", params={"drop_cm": 40})
    b = _bones(ue)
    assert r["pass"] and b["pelvis"] == pytest.approx([-5, 0, 55], abs=1.0)
    assert b["foot_l"] == pytest.approx([0, -10, 9], abs=1.0)


def test_check_fails_off_pose_and_errors(ue, host):
    from fmbridge.errors import OpError
    chk = run_op("pose.check", label="Host", sequence="/Game/T/Seq", frame=0, pose="arms_crossed")
    assert not chk["pass"] and {i["code"] for i in chk["issues"]} == {"pose.effector_off"}
    with pytest.raises(OpError) as e:
        run_op("pose.apply", label="Host", sequence="/Game/T/Seq", frame=0, pose="moonwalk")
    assert e.value.code == "bad_args"
    with pytest.raises(OpError) as e:
        run_op("pose.apply", label="Host", sequence="/Game/T/Seq", frame=0, pose="wave",
               controls={"hand_r": "no_such_ctrl"})
    assert e.value.code == "not_found" and "hand_r_ik_ctrl" in e.value.details["controls"]
    lib = run_op("pose.library")
    assert "hands_on_hips" in lib["poses"] and run_op("pose.library", pose="sit")["params"] == {"drop_cm": "sit"}


def test_sit_reapplied_converges(ue, host):
    run_op("pose.apply", label="Host", sequence="/Game/T/Seq", frame=10, pose="sit")
    again = run_op("pose.apply", label="Host", sequence="/Game/T/Seq", frame=10, pose="sit")
    assert again["iterations"] == 0 and _bones(ue)["pelvis"] == pytest.approx([-5, 0, 50], abs=1.0)
    assert run_op("pose.check", label="Host", sequence="/Game/T/Seq", frame=10, pose="sit")["pass"]
