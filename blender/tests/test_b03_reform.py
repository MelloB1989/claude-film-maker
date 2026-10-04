# B03, the re-form (blender/shots/b03_reform.py): its pure half, outside Blender. Its frames and cues come from the data,
# its camera is her's CameraRig (ported), the ends meet exactly on "Not", the strands are born there, and the lay it
# draws out ends on the engine thread's own phase at the join, ply for ply and strand for strand.
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

from lib import thread, timing

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("b03_reform", REPO / "blender" / "shots" / "b03_reform.py")
b03 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b03)

T = timing.film()
C = b03.Cues(T)


def test_the_plate_covers_her_from_her_first_frame_to_the_one_before_the_whip():
    vo = json.loads((REPO / "data" / "vo.json").read_text())
    her = next(s for s in vo["scenes"] if s["id"] == "her")
    assert b03.SHOT["frames"][0] == T.scene_frames("her")[0] == math.ceil(her["start"] * 30)
    assert C.not_ == T.word("L06", 0).start and C.me == T.word("L06", 1).start
    assert C.down == min(d for d in T.audio["downbeats"] if d > C.me)
    assert C.hand == pytest.approx(C.down - b03.SPEC["whip"] / 2)
    f1 = b03.SHOT["frames"][1]
    assert (f1 - 1) / 30 + 0.5 / 60 < C.hand <= f1 / 30 + 0.5 / 60  # the last plate frame's shutter ends before the whip
    assert {int(f) for f in b03.SHOT["look"].split(",")} <= set(range(*b03.SHOT["frames"]))


def test_the_world_is_hers_and_converts_to_blender_by_a_proper_rotation():
    W = b03.WORLD
    assert np.allclose(W.J, W.A + b03.SPEC["join"] * (W.B - W.A))
    assert np.isclose(np.linalg.det(b03.ENGINE_TO_BLENDER), 1.0)
    assert np.allclose(b03.to_blender([0, 1, 0]), [0, 0, 1])  # the engine's up is Blender's
    assert np.isclose(W.n @ W.d, 0) and np.isclose(W.n[1], 0)  # the side is horizontal and square to the thread


def test_the_camera_port_frames_like_three():
    # three: a camera at +z looking at the origin, y up, has the identity basis; a roll turns it about its view axis
    p = b03.Pose([0, 0, 5], [0, 0, 0], 30, 0)
    assert np.allclose(p.basis(), np.eye(3))
    assert p.project([0, 0, 0]) == pytest.approx((960, 540))
    r = b03.Pose([0, 0, 5], [0, 0, 0], 30, 90).basis()
    assert np.allclose(r[:, 0], [0, 1, 0]) and np.allclose(r[:, 1], [-1, 0, 0])  # x turns to up: the picture clockwise
    assert p.depth([0, 0, -2]) == pytest.approx(7)
    # a point at the top edge of a 30 degree fov
    assert p.project([0, 5 * math.tan(math.radians(15)), 0])[1] == pytest.approx(0, abs=1e-9)


def test_the_rig_holds_its_keys_and_eases_between_them():
    rig = b03.Rig(C)
    for k in rig.keys:
        pose = rig.at(k["t"])
        assert np.allclose(pose.pos, k["pos"]) and np.allclose(pose.target, k["target"]) and pose.roll == k["roll"]
    assert np.allclose(rig.at(C.start - 1).pos, rig.keys[0]["pos"])  # held before the first key
    assert np.allclose(rig.at(C.down + 1).pos, rig.keys[-1]["pos"])  # and after the last
    a, b = rig.keys[0], rig.keys[1]
    mid = rig.at((a["t"] + b["t"]) / 2).pos
    assert np.linalg.norm(mid - a["pos"]) > 0 and np.linalg.norm(mid - b["pos"]) > 0
    # the join stays put in frame as the camera pushes in (her's framing, from data/look/b03_reform.json)
    for t in np.linspace(C.start, C.hand, 7):
        x, y = rig.at(t).project(b03.WORLD.J)
        assert abs(x - 960) < 25 and abs(y - 572) < 25


def test_the_ends_meet_exactly_on_not_and_are_drawn_shut_faster_and_faster():
    st = b03.Story(C, b03.WORLD.R)
    R = b03.WORLD.R
    assert st.gap(C.start) / R > 20  # off frame as the scene opens
    assert st.gap(C.not_) == 0 and st.gap(C.not_ + 0.2) == 0
    assert st.gap(C.not_ - 1 / 30) > 0
    ts = np.linspace(st.hover, C.not_, 40)
    g = np.array([st.gap(t) for t in ts])
    assert np.all(np.diff(g) <= 1e-12)  # drawn together, never apart
    assert -np.diff(g)[-1] > -np.diff(g)[len(g) // 2] * 4  # and faster at the end: the magnet's click
    assert st.curl(st.hover) == 0  # straight by the time they hang


def test_the_strands_are_born_on_not_the_blood_lit_and_the_moss_dark():
    st = b03.Story(C, b03.WORLD.R)
    assert st.extent(C.not_ - 0.01, "blood") == 0 and st.extent(C.not_, "blood") > 0
    assert st.extent(C.not_ + 0.01, "moss") == 0  # a beat behind
    x = np.linspace(0, 5 * b03.WORLD.R, 20)
    assert st.heat("moss", x, C.not_ + 0.2, st.extent(C.not_ + 0.2, "moss")).max() == 0
    assert st.heat("blood", x, C.not_ + 0.05, st.extent(C.not_ + 0.05, "blood")).max() > 1
    # the strand's glow is the engine's envelope: blood flares on "Not", moss on the downbeat, both at rest between
    assert thread.strand_glow(C.not_, C.not_) == thread.DIFF_THREAD["glow"]
    assert thread.strand_glow(C.hand - 0.02, C.down) == pytest.approx(thread.DIFF_THREAD["rest"])
    # and the light it sheds dies away before the hand-off
    assert st.spark(C.hand) < 0.03 and st.tip(C.hand) < 0.25


def test_the_rope_is_whole_at_the_diff_threads_lay_by_the_hand_off():
    st = b03.Story(C, b03.WORLD.R)
    k = st.knit(C.hand - 0.05)
    assert all(v == 1.0 for v in k.values())


def test_the_lay_ends_on_the_engine_threads_phase_at_the_join():
    R = b03.WORLD.R
    rope = thread.fibre_rope(R, b03.LENGTH_R * R, seed=b03.SEED, fibres=4, fuzz_per_R=1, lay_deg=b03.LAY_FROM)
    to = thread.diff_twist(R)
    fix, grooves = b03.relay(rope.twist, rope.break_at, to)
    assert abs(fix) <= 1 / 6 + 1e-12
    W = b03.WORLD
    engine = to * W.u_join * W.length  # the engine's ply 0 phase at the join (turns)
    ours = rope.twist * rope.break_at + fix  # B03's, once the lay has drawn out
    k = round(3 * (engine - ours))
    assert engine - ours == pytest.approx(k / 3, abs=1e-9)  # the plies coincide
    for c, g in (("blood", 0.5), ("moss", 1 / 6)):  # and each strand sits in the engine's groove for it
        off = ((grooves[c] + ours) - (g + engine)) % 1
        assert min(off, 1 - off) == pytest.approx(0, abs=1e-9)
