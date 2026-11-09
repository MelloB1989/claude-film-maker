"""looks.py on shots.py's stage: the looks at the partner turn towards them, in the frame and in 3D (round 4)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import looks as LK  # noqa: E402


def test_left_is_minus_y_facing_plus_x():
    assert LK.left_of([1.0, 0.0, 0.0]) == [0.0, -1.0, 0.0]


def test_partner_sides():
    st = LK.Stage()
    assert LK.look("him", 1170, 0.76, st)["true_yaw"] > 90   # she is behind him on his left
    her = LK.look("her", 1110, 1.0, st)
    assert -60 < her["true_yaw"] < -40 and her["pitch"] > 0  # he is ahead on her right, his eyes higher


def test_reach_caps_his_look():
    lk = LK.look("him", 1170, 0.76, LK.Stage())
    assert lk["yaw"] == lk["reach"] and abs(lk["reach"] * 0.76 - LK.HEAD_MAX) < 0.5


def test_screen_side():
    st = LK.Stage()
    me, them = st.pose("him", 1170), st.pose("her", 1170)
    cam = st.camera("S15", 1170)
    assert LK.screen_x(cam, them["eyes"]) > LK.screen_x(cam, me["eyes"])  # she is screen right of him


def test_wrong_way_fails():
    st = LK.Stage()
    assert not LK.check("him", 1170, "S15", [-65.0, 0.0], [-85.0, -5.0], st)["ok"]
    assert LK.check("him", 1170, "S15", [65.0, -3.0], [85.0, -5.0], st)["ok"]
    assert LK.check("her", 1110, "S15", [-32.0, 3.0], [-50.0, 5.0], st)["ok"]


def test_torso_turn_goes_and_settles_back():
    m = LK.torso_moves([{"t": 2.0, "until": 8.0, "yaw": 30.0, "kind": "big"}])
    assert LK.torso_yaw(m, 2.1) == 0.0                        # after the head, not with it
    assert abs(LK.torso_yaw(m, 4.0) - 30.0) < 0.5             # held
    assert abs(LK.torso_yaw(m, 10.0)) < 0.2                   # back after the head lets go


def test_torso_takes_off_the_neck():
    st = LK.Stage()
    a, b = LK.look("him", 1170, 0.76, st), LK.look("him", 1170, 0.76, st, torso=30.0)
    assert b["torso_yaw"] == 30.0 and b["yaw"] <= a["yaw"]
