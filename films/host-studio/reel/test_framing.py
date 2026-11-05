"""framing.py's rules on the reel's shot table, and his shots following his eyes for another body. No Unreal.

    cd tools && uv run --with pytest pytest ../films/host-studio/reel/test_framing.py
"""
import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import framing as F  # noqa: E402
import shots as S  # noqa: E402

HIS = ("S13", "S15")  # the shots that follow his eyes (shots.lifted)


def body_of(height: float) -> tuple:
    """Another him: the shot table re-framed for a body `height` cm tall (eyes in v2's proportion), and its body."""
    eyes = height * S.EYES_HIM / S.TOP_HIM
    dz = eyes - S.EYES_HIM
    shots = [dataclasses.replace(s, keys=S.lifted(s.keys, dz)) if s.id in HIS else s for s in S.SHOTS]
    body = dict(F.BODY, him=(S.MARK_HIM, eyes, height, height * 0.28))
    return shots, body


def test_the_table_keeps_the_rules():
    assert F.problems() == []


def test_v2_frames_unchanged_for_the_v2_body():
    assert S.lifted([[0, [1, 2, 3], [4, 5, 6]]], 0.0) == [[0, [1, 2, 3], [4, 5, 6]]]
    if S.EYES_HIM == S.EYES_HIM_V2:
        s13 = next(s for s in S.SHOTS if s.id == "S13")
        assert s13.keys[0] == [0, [230, 70, 188], [30, 40, 168]]


@pytest.mark.parametrize("height", [165, 170, 175, 178, 182, 186])
def test_his_eyes_hold_their_place_and_the_rules_hold(height):
    shots, body = body_of(height)
    assert F.problems(shots, body) == []
    for sid in HIS:
        new = F.worst(next(s for s in shots if s.id == sid), body)["him"]["eyes"]
        old = F.worst(next(s for s in S.SHOTS if s.id == sid))["him"]["eyes"]
        assert new == pytest.approx(old, abs=1e-6)


def test_a_knee_in_frame_is_caught():
    shots, body = body_of(182)
    low = [dataclasses.replace(s, keys=S.lifted(s.keys, -60.0)) if s.id == "S17" else s for s in shots]
    assert any(p[0] == "S17" and "knee" in p[2] for p in F.problems(low, body))


def test_projection_centre_and_edges():
    # a camera at the origin looking down +X (yaw 0): +Y is screen-right, the frame's top edge at the half-height angle
    assert F.project((0, 0, 0), 0.0, 0.0, 36.0, (100, 0, 0))[:2] == pytest.approx((0.0, 0.0))
    assert F.project((0, 0, 0), 0.0, 0.0, 36.0, (100, 50, 0))[0] == pytest.approx(1.0)
    assert F.project((0, 0, 0), 0.0, 0.0, 36.0, (100, 0, 100 * 10.125 / 36))[1] == pytest.approx(1.0)
