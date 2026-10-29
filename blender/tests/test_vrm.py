import math

import numpy as np
import pytest

from lib import vrm


def test_humanoid_names_any_spelling_and_mirrored():
    assert len(vrm.HUMANOID) == 55 and len(set(vrm.HUMANOID)) == 55
    for s in ("leftUpperArm", "left_upper_arm", "LeftUpperArm", "left-upper-arm"):
        assert vrm.canonical(s) == "leftUpperArm"
    assert vrm.canonical("upper_chest") == "upperChest"
    with pytest.raises(KeyError, match="leftUpperArm"):
        vrm.canonical("leftUpperArmm")
    assert vrm.mirror_name("rightThumbMetacarpal") == "leftThumbMetacarpal"
    assert vrm.mirror_name("left_foot") == "rightFoot"
    assert vrm.mirror_name("head") == "head"


def test_material_kind_from_vroid_names():
    assert vrm.kind("N00_007_02_Tops_01_CLOTH (Instance)") == "cloth"
    assert vrm.kind("N00_000_Hair_00_HAIR (Instance).001") == "hair"
    assert vrm.kind("N00_000_00_HairBack_00_HAIR") == "hair"
    assert vrm.kind("N00_000_00_Face_00_SKIN (Instance)") == "skin"
    assert vrm.kind("N00_000_00_FaceBrow_00_FACE (Instance)") == "face"
    assert vrm.kind("N00_000_00_EyeIris_00_EYE (Instance)") == "eye"
    assert vrm.kind("MToon Outline (thing)") is None and vrm.kind("Material") is None


def test_material_part_tells_the_faces_skin_from_the_bodys():
    assert vrm.part("N00_000_00_Face_00_SKIN (Instance)") == "face_skin"
    assert vrm.part("N00_000_00_Face_00_SKIN (Instance).001") == "face_skin"
    assert vrm.part("N00_000_00_Body_00_SKIN (Instance)") == "skin"
    assert vrm.part("N00_000_00_FaceBrow_00_FACE (Instance)") == "face"
    assert vrm.part("N00_007_02_Tops_01_CLOTH (Instance)") == "cloth"


def test_euler_turns_about_fixed_axes_x_first():
    # the character's frame: x its left, y its back, z up; it faces -y
    front, up, left = np.array([0, -1.0, 0]), np.array([0, 0, 1.0]), np.array([1.0, 0, 0])
    assert vrm.euler((30, 0, 0)) @ front == pytest.approx([0, -math.cos(math.pi / 6), -0.5])   # x+: bends forward
    assert vrm.euler((0, 30, 0)) @ up == pytest.approx([0.5, 0, math.cos(math.pi / 6)])        # y+: tips to its left
    assert vrm.euler((0, 90, 0)) @ left == pytest.approx([0, 0, -1])                           # ... the left arm down
    assert vrm.euler((0, 0, 90)) @ front == pytest.approx(left)                                # z+: turns to its left
    a, b = vrm.euler((20, 0, 0)), vrm.euler((0, 0, 35))
    assert vrm.euler((20, 0, 35)) == pytest.approx(b @ a)


def test_body_frame_and_facing():
    f = vrm.body_frame((0.085, 0.0, 0.97), (-0.085, 0.0, 0.97))
    assert f == pytest.approx(np.eye(3))
    assert vrm.facing_turn(f) == pytest.approx(math.pi / 2)            # facing -y: a quarter turn to face +x
    # a file facing +x already, its left at +y
    g = vrm.body_frame((0.0, 0.1, 1.0), (0.0, -0.1, 0.9))
    assert g[:, 0] == pytest.approx([0, 1, 0]) and g[:, 2] == pytest.approx([0, 0, 1])
    assert np.linalg.det(g) == pytest.approx(1.0)
    assert vrm.facing_turn(g) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        vrm.body_frame((0, 0, 1), (0, 0, 0.5))


def _rot(axis, deg):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    a = math.radians(deg)
    return np.eye(3) + math.sin(a) * k + (1 - math.cos(a)) * k @ k


def test_local_rotation_turns_the_bone_in_the_characters_frame_whatever_its_roll():
    frame = np.eye(3)
    # an upper arm along +x rolled two ways: its own y along the bone, x and z wherever the file put them
    for rest in (np.column_stack([[0, 0, -1.0], [1.0, 0, 0], [0, -1.0, 0]]),
                 np.column_stack([[0, 1.0, 0], [1.0, 0, 0], [0, 0, -1.0]])):
        local = vrm.local_rotation(rest, frame, (0, 60, 0))
        bone_dir = rest @ local @ np.array([0, 1.0, 0])     # the posed bone's y in armature space
        assert bone_dir == pytest.approx([0.5, 0, -math.sin(math.pi / 3)])  # down 60 degrees, either roll
        assert np.linalg.det(local) == pytest.approx(1.0)
    # in a turned frame (a file facing +x) the same pose does the same to the character
    turned = _rot((0, 0, 1), 90)
    rest = turned @ np.column_stack([[0, 0, -1.0], [1.0, 0, 0], [0, -1.0, 0]])
    d = rest @ vrm.local_rotation(rest, turned, (0, 60, 0)) @ np.array([0, 1.0, 0])
    assert turned.T @ d == pytest.approx([0.5, 0, -math.sin(math.pi / 3)])
    # a matrix is taken as it is
    assert vrm.local_rotation(np.eye(3), frame, _rot((1, 0, 0), 15)) == pytest.approx(vrm.euler((15, 0, 0)))


def test_hips_offset_in_the_bones_own_space():
    rest = np.column_stack([[1.0, 0, 0], [0, -0.13, 0.99], [0, -0.99, -0.13]])   # VRoid's hips
    rest /= np.linalg.norm(rest, axis=0)
    loc = vrm.offset_local(rest, np.eye(3), (0.0, -0.05, -0.15))
    assert rest @ loc == pytest.approx([0.0, -0.05, -0.15])


def test_mirror_and_blend():
    p = {"leftUpperArm": (10, 70, -20), "head": (5, 3, 12)}
    m = vrm.mirror(p)
    assert m["rightUpperArm"] == (10, -70, 20) and m["head"] == (5, -3, -12)
    assert vrm.mirror(m) == {k: tuple(float(x) for x in v) for k, v in p.items()}
    b = vrm.blend({"spine": (10, 0, 0)}, {"spine": (30, 0, 0), "neck": (0, 0, 20)}, 0.25)
    assert b["spine"] == pytest.approx((15, 0, 0)) and b["neck"] == pytest.approx((0, 0, 5))


def test_align_takes_a_hand_to_its_grip():
    # a right hand at rest: knuckles index to little toward its back (+y), palm down; closed on an upright pole, index
    # on top, palm toward its left
    k0, p0 = (0, 1.0, 0), (0, 0, -1.0)
    q = vrm.align(k0, p0, (0, 0, -1.0), (1.0, 0, 0))
    assert q @ np.array(k0) == pytest.approx([0, 0, -1]) and q @ np.array(p0) == pytest.approx([1, 0, 0])
    assert q @ q.T == pytest.approx(np.eye(3)) and np.linalg.det(q) == pytest.approx(1.0)
    # the fingers (k x p for a right hand) then point forward, round the pole
    assert q @ np.cross(k0, p0) == pytest.approx([0, -1, 0])
    # a palm given at a slant is squared to the knuckles
    q2 = vrm.align(k0, p0, (0, 0, -1.0), (1.0, 0, 0.5))
    assert q2 == pytest.approx(q)
    with pytest.raises(ValueError):
        vrm.align(k0, p0, (0, 0, 1.0), (0, 0, 2.0))


def test_grip_pose_curls_toward_the_palm_on_either_hand():
    left, right = vrm.grip_pose("left", 1.0), vrm.grip_pose("right", 1.0)
    assert right == vrm.mirror(left)
    # a left finger along +x curls down (its palm's side), a right one along -x too
    tip_l = vrm.euler(left["leftIndexProximal"]) @ np.array([1.0, 0, 0])
    tip_r = vrm.euler(right["rightIndexProximal"]) @ np.array([-1.0, 0, 0])
    assert tip_l[2] < -0.8 and tip_r[2] < -0.8
    assert vrm.grip_pose("left", 0.0)["leftMiddleDistal"] == (0.0, 0.0, 0.0)


def test_colour_grades():
    assert vrm.tinted((0.5, 0.4, 0.2, 1.0), (0.5, 1.0, 2.0)) == pytest.approx((0.25, 0.4, 0.4, 1.0))
    assert vrm.tinted((1.0, 1.0, 1.0), (0.6, 0.65, 0.7)) == pytest.approx((0.6, 0.65, 0.7))
    px = np.array([[0.8, 0.2, 0.1, 0.5], [0.3, 0.3, 0.3, 1.0]], np.float32)
    g = vrm.grade(px, 0.0)
    luma = 0.8 * 0.2126 + 0.2 * 0.7152 + 0.1 * 0.0722
    assert g[0, :3] == pytest.approx([luma] * 3, abs=1e-6) and g[0, 3] == 0.5
    assert g[1] == pytest.approx(px[1])                          # a grey stays
    assert vrm.grade(px, 1.0) == pytest.approx(px)
    half = vrm.grade(px, 0.5)
    assert half[0, 0] == pytest.approx((0.8 + luma) / 2, abs=1e-6)
    assert vrm.grade(px, 3.0).max() <= 1.0 and vrm.grade(px, 3.0).min() >= 0.0
    assert px[0, 0] == pytest.approx(0.8)                        # not in place


def test_sizes():
    # 0.2% of the frame's height, 2.66 m from an 85 mm lens on the 20.25 mm gate: 0.63 m of frame, so 1.27 mm
    assert vrm.outline_width(0.002, 2.66, 85.0) == pytest.approx(0.002 * 2.66 * 20.25 / 85.0)
    assert vrm.outline_width(0.002, 5.32, 85.0) == pytest.approx(2 * vrm.outline_width(0.002, 2.66, 85.0))
    with pytest.raises(ValueError):
        vrm.outline_width(0.002, 0.0, 85.0)
    assert vrm.height_scale(1.762, 1.78) == pytest.approx(1.78 / 1.762)
    with pytest.raises(ValueError):
        vrm.height_scale(0.0, 1.7)


def test_fold_starts_an_elbow_forward_and_a_knee_back():
    assert vrm.fold("leftLowerArm") == (0.0, 0.0, -vrm.FOLD)
    assert vrm.fold("right_lower_arm", 70.0) == (0.0, 0.0, 70.0)
    assert vrm.fold("leftLowerLeg", 15.0) == vrm.fold("rightLowerLeg", 15.0) == (15.0, 0.0, 0.0)
    # forward for either forearm: the turns mirror
    assert vrm.mirror({"leftLowerArm": vrm.fold("leftLowerArm")}) == {"rightLowerArm": vrm.fold("rightLowerArm")}
    with pytest.raises(ValueError):
        vrm.fold("leftUpperArm")


def test_a_band_wraps_tight_over_the_dips_of_a_cross_section():
    n = 48
    th = 2 * np.pi * np.arange(n) / n
    # a round body with folds pressed in (every 4th direction 3 cm short) and one spike out
    r = np.full(n, 0.15)
    r[::4] = 0.12
    r[10] = 0.2
    out = vrm.wrap(r, smooth=0)
    assert (out >= r - 1e-12).all()
    chord = 0.15 * np.cos(np.pi / n * 2)                    # a dip bridged by the chord over its neighbours
    assert out[28] == pytest.approx(chord) and out[40] == pytest.approx(chord)
    assert out[8] > out[28]                                  # on the way up to the spike
    assert out[10] == pytest.approx(0.2)                                                          # the spike kept
    # a circle stays a circle; easing never goes inside
    assert vrm.wrap(np.full(n, 0.1)) == pytest.approx(np.full(n, 0.1), abs=1e-3)
    eased = vrm.wrap(r, smooth=2)
    assert (eased >= r - 1e-12).all() and np.ptp(eased[20:40]) < 1e-3
