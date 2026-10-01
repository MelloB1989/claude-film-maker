# B05, the loom (blender/shots/b05_loom.py): its pure half, outside Blender. A pass lands on every beat of the window,
# each row is laid in flight, beaten in on its beat and taken up toward the camera; the shuttle reaches the skills lane
# only on the first left-to-right pass after she names them; the incidents' three oldest rows let go across "let go";
# the rules warps snap taut as she names them; and the camera brings each tier into frame as she does.
import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

from lib import thread, timing, weave

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("b05_loom", REPO / "blender" / "shots" / "b05_loom.py")
b05 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b05)

T = timing.film()
C = b05.Cues(T)
S = b05.Story(C)


def test_the_plate_is_the_scene_window_and_the_look_frames_lie_in_it():
    assert b05.SHOT["frames"] == "scene"
    f0, f1 = T.scene_frames("loom")
    assert all(f0 <= int(f) < f1 for f in b05.SHOT["look"].split(","))
    assert {"lbl_facts", "lbl_incidents", "lbl_rules", "lbl_skills", "gc", "shuttle", "reach"} <= set(b05.SHOT["track"])


def test_a_pass_lands_on_every_beat_of_the_window_the_last_on_the_cut():
    beats = [b for b in T.audio["beats"] if C.start < b <= C.end + 1e-6]
    assert [p.land for p in S.clock.passes] == beats
    assert C.before == max(b for b in T.audio["beats"] if b <= C.start + 1e-6)  # row 0 went in on the cut's beat
    assert S.clock.passes[-1].land == pytest.approx(C.end)  # the cut to `diff` is a beat: the last pass lands on it
    assert [p.start for p in S.clock.passes[:4]] == [-1, 1, -1, 1]


def test_a_row_is_laid_in_flight_beaten_in_on_its_beat_and_taken_up_toward_the_camera():
    for p in S.clock.passes[:6]:
        r = p.row
        assert S.row_state("facts", r, p.depart - 0.01) is None  # not yet laid
        y, k, drawn = S.row_state("facts", r, p.depart + 0.85 * (p.land - p.depart))
        assert (y, k) == (b05.RACE, 0.0) and drawn[1] > drawn[0]  # in flight: straight, at the race, drawn behind it
        y, k, drawn = S.row_state("facts", r, p.land + S.clock.settle + 1e-6)
        assert y == pytest.approx(0.0, abs=1e-9) and k == 1.0 and drawn is None  # in the fell
        nxt = S.clock.passes[p.k + 1]
        assert S.row_state("facts", r, nxt.land + S.clock.settle + 1e-6)[0] == pytest.approx(-b05.PICK)
    # nothing of a lane is drawn until the shuttle reaches it (it flies from the right on odd passes)
    p = S.clock.passes[1]
    x0, x1 = S.row_state("facts", p.row, p.depart + 0.05)[2]
    assert x1 < x0
    # a row is drawn from the side its pass started, up to the shuttle
    p = S.clock.passes[0]
    t = p.depart + 0.6 * (p.land - p.depart)
    a, b = S.row_state("facts", 1, t)[2]
    assert a == pytest.approx(S.lane["facts"].x0 - b05.OVER) and b <= S.shuttle_x(t) + 1e-9


def test_rows_woven_before_the_cut_went_in_beat_by_beat_and_rest_dark():
    assert S.commit(0) == C.before
    assert S.commit(-1) == pytest.approx(C.before - (C.beats[0] - C.before))
    for r in range(-40, 0):  # only the cut's own row still glows from its commit as the shot opens
        assert thread.strand_glow(C.start, S.commit(r)) == pytest.approx(b05.DIFF_REST)
    assert thread.strand_glow(C.start, S.commit(0)) > b05.DIFF_REST
    assert b05.DIFF_REST == thread.DIFF_THREAD["rest"]


def test_the_shuttle_lands_in_a_box_on_every_beat_and_first_reaches_skills_after_she_names_them():
    for p in S.clock.passes:
        assert S.shuttle_x(p.land) == pytest.approx(S.ends(p.k)[1])
    reach = S.clock.passes[S.reach]
    assert reach.start == -1 and reach.land >= C.skills
    assert all(p.land < C.skills for p in S.clock.passes[:S.reach] if p.start == -1)
    edge = S.lane["skills"].x0 - b05.RW
    ts = np.linspace(C.start, C.end, 6000)
    xs = np.array([S.shuttle_x(t) for t in ts])
    first = ts[np.argmax(xs >= edge)]
    assert first > C.skills
    assert first == pytest.approx(S.skills_reached(), abs=2e-3)
    assert S.skills_light(S.skills_reached() - 0.01) == 0 and S.skills_light(S.skills_reached() + 0.4) == 1


def test_the_skills_warps_rise_into_the_shed_on_the_change_over_before_the_reach():
    p = S.clock.passes[S.reach]
    assert S.skills_shed(S.clock.passes[S.reach - 1].land - 0.01) == 0
    assert S.skills_shed(p.depart) == pytest.approx(1)
    # out of the shed they lie in the cloth's plane
    cen, *_ = b05.warp_pose(S, "skills", C.start + 0.5)
    beyond = cen[:, :, 1] > 1.0
    assert np.allclose(cen[:, :, 2][beyond], 0.0)


def test_the_three_oldest_incidents_fray_from_incidents_and_let_go_across_let_go():
    assert S.release[0] == C.let and S.release[-1] == pytest.approx(C.go)
    for i in range(b05.EXPIRE):
        assert S.fray(i, C.incidents - 0.1) == 0
        assert S.fray(i, S.release[i]) == pytest.approx(1)
    e = b05.Expiring(S)
    before = e.pose(S.release[0] - 0.01)
    after = e.pose(S.release[-1] + 1.4)
    # in place until they go, then risen away and thinned to nothing
    assert np.max(before["bone"][0][:, 2]) < 3.0
    assert np.mean(after["bone"][0][:, 2]) > 5.0
    assert np.max(after["bone"][1]) < 1e-6
    # their blood strands burn as they go; moss stays at rest
    assert np.max(e.pose(S.release[0] + 0.2)["blood"][2]) > 2.0
    # the incidents warps lose their crimp under each row as it goes
    rho = np.array([float(e.rows[0])])
    assert b05.lane_mask(S, "incidents", rho, S.release[0] - 0.01)[0] == 1
    assert b05.lane_mask(S, "incidents", rho, S.release[0] + 0.5)[0] == 0


def test_the_rules_warps_hang_slack_until_she_names_them_then_snap_taut_and_ring_on_break():
    assert S.slack(C.rules - 0.05) == 1.0
    assert abs(S.slack(C.rules + 0.6)) < 0.02
    assert S.pluck(C.brk - 0.01) == 0.0 and abs(S.pluck(C.brk + 0.04)) > 0.3
    late = b05.warp_pose(S, "rules", C.rules + 0.8)[0]
    beyond = (late[:, :, 1] > 0) & (late[:, :, 1] < b05.HEDDLE)
    x0 = np.array(S.lane["rules"].xs)[:, None]
    assert np.max(np.abs(late[:, :, 0] - x0)[beyond]) < 0.05  # taut: straight to the heddles


def test_the_camera_brings_each_tier_into_frame_as_she_names_it():
    rig = b05.CameraRig(S, b05.Expiring(S))
    for lane, at in (("facts", C.facts), ("incidents", C.incidents), ("rules", C.rules), ("skills", C.skills)):
        x, y = rig.project(at + 0.2, b05.label_anchor(S, lane))
        assert 200 < x < 1500 and 250 < y < 900, (lane, x, y)
    # focus on the expiring rows as they let go
    gc = np.array([S.lane["incidents"].centre, b05.Expiring(S).row_y(1, C.go), 0.3])
    assert np.allclose(rig.focus_point(C.go), gc)


def test_the_weave_crosses_warp_and_weft_on_opposite_sides():
    for r in range(3):
        for j in range(4):
            assert np.sign(weave.warp_crimp(r, j, b05.AW)) == -np.sign(weave.weft_crimp(j, r, b05.AF))
