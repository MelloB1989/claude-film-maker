# B08, the braid (blender/shots/b08_braid.py): its pure half, outside Blender. Every time comes from the data: each arm
# lands on her word for it, the plait starts on "braided" and its head lands on the card's hinge on "one"; the world and
# the camera are the ones the engine reads (data/look/b08_braid.json); the side threads leave the plait only where it
# exists and reach their beads before "answer"; nothing passes through the lens.
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from lib import braid, thread, timing

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("b08_braid", REPO / "blender" / "shots" / "b08_braid.py")
b08 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b08)

T = timing.film()
C = b08.Cues(T)
S = b08.Story(C)
TH = b08.Threads(S)
F0, F1 = T.scene_frames("braid")
FRAMES = np.arange(F0, F1)


def test_the_plate_is_the_scene_window_and_tracks_what_the_engine_needs():
    assert b08.SHOT["frames"] == "scene"
    assert all(F0 <= int(f) < F1 for f in b08.SHOT["look"].split(","))
    assert set(b08.SHOT["track"]) == {"lbl_lexical", "lbl_body", "lbl_cues", "p0", "head", "hinge"}


def test_the_cues_are_her_words():
    words = [w["w"] for w in next(l for l in json.loads((REPO / "data" / "vo.json").read_text())["lines"]
                                   if l["id"] == "L19")["words"]]
    assert words[:3] == ["Your", "words.", "What"] and words[5] == "How" and words[8:] == ["braided", "into", "one", "answer."]
    assert (C.your, C.what, C.how) == tuple(T.word("L19", i).start for i in (0, 2, 5))
    assert (C.braided, C.into, C.one, C.answer) == tuple(T.word("L19", i).start for i in (8, 9, 10, 11))
    assert C.land == {"lexical": C.your, "body": C.what, "cues": C.how}  # in the order she names them


def test_the_world_is_the_one_the_engine_reads():
    spec = json.loads((REPO / "data" / "look" / "b08_braid.json").read_text())
    assert b08.R == spec["radius"]
    assert np.allclose(b08.HINGE, b08.P0 + b08.LENGTH * b08.AXIS, atol=2e-5)  # the head lands on the card's hinge
    keys = b08.camera_keys(C)
    assert [k["t"] for k in keys] == pytest.approx([C.start, C.braided - 0.08, C.one, C.end])
    assert keys[0]["fov"] == 24


def test_each_arm_flies_in_from_off_frame_and_lands_on_her_word_short_of_the_others():
    for k in b08.ARMS:
        land = C.land[k]
        X, u = TH.arm(k, land - C.RACE - 0.01)
        px = S.rig.at(land - C.RACE).project_many(X[::10])
        inside = (px[:, 0] > 0) & (px[:, 0] < 1920) & (px[:, 1] > 0) & (px[:, 1] < 1080)
        assert not inside.any()  # nothing of it in frame before its flight
        L = np.linalg.norm(TH.braiding_point(k, land) - S.entry[k])
        assert S.tip_back(k, land, L, TH.h0[k]) == pytest.approx(b08.GAP * b08.R, abs=0.002)  # landed on the word
        assert S.tip_back(k, land - 0.1, L, TH.h0[k]) > b08.GAP * b08.R + 0.002  # still flying a beat before
        X, u = TH.arm(k, land + 0.2)
        assert np.linalg.norm(X[-1] - b08.P0) == pytest.approx(b08.GAP * b08.R, abs=1.5 * b08.R)  # hovering, apart
    # until "braided" the three tips hang apart; they close as the plait starts
    tips = [TH.arm(k, C.braided - 0.3)[0][-1] for k in b08.ARMS]
    assert min(np.linalg.norm(tips[i] - tips[j]) for i in range(3) for j in range(i + 1, 3)) > 3 * b08.R


def test_the_plait_starts_on_braided_and_its_head_lands_on_the_hinge_on_one():
    assert S.zip(C.braided - 0.1) == 0.0
    assert S.zip(C.braided + 0.1) > 0.0
    assert S.zip(C.one) == pytest.approx(b08.LENGTH)
    assert np.allclose(S.head(C.one), b08.HINGE, atol=1e-4)
    zs = [S.zip(t) for t in np.linspace(C.zip0, C.one, 50)]
    assert np.all(np.diff(zs) >= 0)  # it only ever runs toward the camera
    # after it lands it fetches up and settles on the hinge: within a radius, and still by the cut
    assert all(abs(S.zip(t) - b08.LENGTH) < b08.R for t in np.linspace(C.one, C.end, 30))
    assert S.sag(C.one + 0.6) == pytest.approx(0.0, abs=2e-4)  # pulled taut


def test_the_plaits_strands_never_cut_through_each_other():
    pl = S.plait
    b = np.linspace(b08.HEAD_POINT * b08.R, b08.LENGTH, 600)  # past the tail, where the strands are full width
    pts = [S.plait_point(k, b, C.one + 0.5) for k in range(3)]
    gap = min(np.linalg.norm(pts[i][:, None] - pts[j][None, ::3], axis=-1).min() for i in range(3) for j in range(i + 1, 3))
    assert gap > 1.9 * b08.R
    assert braid.min_gap(pl) > 1.95 * b08.R


def test_material_rides_the_threads_and_the_tips_are_at_the_head():
    for k in b08.ARMS:
        X, u = TH.arm(k, C.one)
        assert np.all(np.diff(u) > 0) and u[-1] == pytest.approx(TH.U[k])
        assert np.linalg.norm(X[-1] - b08.HINGE) < 1.5 * b08.R  # every tip ends in the plait's tail, on the hinge
        steps = np.linalg.norm(np.diff(X, axis=0), axis=1)
        assert steps.max() < 3 * b08.DU * b08.R  # one unbroken thread, arm into plait
        # the far end of its material is still off frame when the plait has drawn it all in
        px = S.rig.at(C.end).project_many(X[:1])
        assert not ((0 < px[0, 0] < 1920) and (0 < px[0, 1] < 1080))


def test_the_side_threads_leave_the_plait_where_it_is_and_reach_their_beads_before_answer():
    for name, bd in S.beads.items():
        assert S.zip(bd["launch"]) >= bd["b"]  # its root's material is already plaited when it leaves
        assert TH.side(name, bd["launch"] - 0.01) is None
        assert bd["launch"] < bd["hit"] < C.answer
        assert S.bead_kick(name, bd["hit"] - 0.01) == 0.0 and S.glint(name, bd["hit"] - 0.05) == 0.0
        X, u, shown = TH.side(name, bd["hit"] + 0.01)
        assert shown.any()
        assert np.linalg.norm(X[shown][-1] - bd["g"]) < b08.BEAD_R * b08.R * 1.2  # its tip at the bead as it hits
        X, u, shown = TH.side(name, C.end)
        g = bd["g"] + bd["bore"] * S.bead_kick(name, C.end)
        d = np.linalg.norm(X[shown] - g, axis=1)
        assert d.min() < 0.3 * b08.BEAD_R * b08.R  # threaded through the bore
        assert np.linalg.norm(X[shown][-1] - g) < (b08.SIDE_BEYOND + 0.2) * b08.BEAD_R * b08.R  # just poking out


def test_nothing_passes_through_the_lens_and_the_head_stays_in_frame():
    for f in FRAMES[::3]:
        t = f / 30
        pose = S.rig.at(t)
        for k in b08.ARMS:
            X, _ = TH.arm(k, t)
            X = X[::10]
            assert np.linalg.norm(X - pose.pos, axis=1).min() > 0.3  # never near the lens (its far end runs off beside it)
            px = pose.project_many(X)
            seen = (px[:, 0] > 0) & (px[:, 0] < 1920) & (px[:, 1] > 0) & (px[:, 1] < 1080)
            assert all(pose.depth(q) > 0.3 for q in X[seen])  # (an arm still off frame before its flight has none)
        for name, bd in S.beads.items():
            assert np.linalg.norm(bd["g"] - pose.pos) > 0.1
    for t in np.linspace(C.zip0, C.end, 30):
        x, y = S.rig.at(t).project(S.head(t))
        assert 300 < x < 1700 and 200 < y < 900


def test_focus_is_on_p0_while_they_land_and_on_the_hinge_when_the_rope_does():
    assert np.allclose(S.focus_point(C.how), b08.P0)
    assert np.allclose(S.focus_point(C.one), b08.HINGE)
    assert np.allclose(S.focus_point(C.end), b08.HINGE)


def test_the_strands_rest_at_the_diff_threads_level_and_the_beads_hashes_are_the_scenes_strings():
    strings = json.loads((REPO / "app" / "src" / "scenes" / "braid.strings.json").read_text())
    assert [bd["hash"] for bd in S.beads.values()] == strings[9:9 + len(b08.BEADS)]
    assert b08.HASHES == strings[9:] and len(b08.HASHES) == len(b08.BEADS) + len(b08.AMBIENT)
    for h in b08.HASHES:  # illustrative commit hashes (spec 11.10): seven hex with a digit and a letter
        assert len(h) == 7 and all(c in "0123456789abcdef" for c in h)
        assert any(c.isdigit() for c in h) and any(c.isalpha() for c in h)
    assert thread.DIFF_THREAD["rest"] == 0.15


def test_lights_hit_on_the_landings():
    for k in b08.ARMS:
        land = C.land[k]
        assert S.kicker(k, land - 0.2) == 0.0
        assert S.kicker(k, land) > 1.0 > S.kicker(k, land + 0.8)
