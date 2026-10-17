"""Retime stage: time mapping, shutter sampling, mix weights, hold at the clip end, and a decode-to-PNG round trip."""
import json
import math
import subprocess

import numpy as np
import pytest

from filmtools.amv import plan as P
from filmtools.amv import retime as R


def make_shot(remap, a=10, slow=False):
    return P.Shot(0, {"name": "S", "src": "c", "a": a, "b": a + len(remap), "end": a + len(remap), "remap": remap,
                      "slow": slow})


def linear_shot(rate, n=20, a=10, t0=0.1):
    """Clip seconds advancing `rate` source frames (60 fps) per comp frame."""
    return make_shot([t0 + j * rate / 60.0 for j in range(n)], a=a)


def test_positions_follow_remap_and_shutter():
    shot = linear_shot(2.0)
    ps = R.source_positions(shot, 15, 4)
    times = P.shutter_times(15, 4)
    assert len(ps) == 4
    for p, t in zip(ps, times):
        assert p == pytest.approx((0.1 + (t - 10) * 2.0 / 60.0) * 60.0)
    # evenly spaced, 301/360 of a comp frame wide in total
    steps = np.diff(ps)
    assert np.allclose(steps, steps[0])
    assert steps[0] * 4 == pytest.approx(2.0 * 301 / 360)


def test_remap_is_linear_between_comp_frames():
    shot = linear_shot(1.0)
    assert shot.remap(12.5) * 60 == pytest.approx(6 + 2.5)


def test_auto_samples_keeps_substeps_under_a_quarter_frame():
    for rate, expect in ((0.84, 3), (1.6, 6), (2.3, 8)):
        shot = linear_shot(rate)
        k = R.auto_samples(shot, 14)
        assert k == expect
        ps = R.source_positions(shot, 14, k)
        assert max(np.diff(ps)) <= R.MAX_STEP + 1e-9


def test_auto_samples_clamped():
    assert R.auto_samples(linear_shot(0.0), 12) == R.K_MIN
    assert R.auto_samples(linear_shot(30.0), 12) == R.K_MAX


def test_mix_weights_are_ae_frame_mix():
    w = R.mix_weights([3.25], 10)
    assert w == {3: pytest.approx(0.75), 4: pytest.approx(0.25)}
    w = R.mix_weights([3.0, 4.5], 10)           # exact frame 3, and half of 4/5
    assert w == {3: pytest.approx(0.5), 4: pytest.approx(0.25), 5: pytest.approx(0.25)}
    assert sum(R.mix_weights([0.1, 2.9, 5.5], 10).values()) == pytest.approx(1.0)


def test_nearest_floor_with_epsilon():
    assert R.split_position(5.0 - 1e-9, 10) == (5, 0.0)      # float noise just under an integer is that frame
    assert R.split_position(5.4, 10)[0] == 5


def test_hold_last_frame_past_clip_end():
    assert R.split_position(12.0, 10) == (9, 0.0)
    assert R.mix_weights([12.0, 14.0], 10) == {9: pytest.approx(1.0)}
    assert R.clamp_position(12.0, 10) == (9.0, True)
    assert R.clamp_position(9.0, 10) == (9.0, False)
    assert R.clamp_position(-1.0, 10) == (0.0, False)


def test_srgb_roundtrip_is_identity():
    v = np.arange(256, dtype=np.uint8).reshape(1, 256, 1).repeat(3, 2)
    assert (R.to_srgb8(R.to_linear(v)) == v).all()


def test_mix_averages_in_linear_light():
    frames = np.zeros((2, 4, 4, 3), np.uint8)
    frames[1] = 255
    shot = make_shot([0.0, 0.5 / 60.0, 1.0 / 60.0], a=0)       # position 0.5 at comp frame 1 (one sample, centre)
    img, info = R.render_frame(frames, shot, 1, "mix", 2)
    # samples straddle p = 0.5 symmetrically: linear mean of black and white = 0.5 linear = sRGB 188
    assert abs(int(img[0, 0, 0]) - 188) <= 1
    assert not info.held


def test_render_frame_flags_hold():
    frames = np.zeros((3, 4, 4, 3), np.uint8)
    shot = linear_shot(1.0, n=6, t0=0.0)
    _, info = R.render_frame(frames, shot, 15, "mix", 3)        # position ~5 > last frame 2
    assert info.held


def test_retime_shot_end_to_end(tmp_path):
    cv2 = pytest.importorskip("cv2")
    ffmpeg = R.ffmpeg_bin()
    if not (subprocess.run([ffmpeg, "-version"], capture_output=True).returncode == 0):
        pytest.skip("no ffmpeg")
    film = tmp_path / "films" / "t"
    (film / "assets").mkdir(parents=True)
    clip = film / "assets" / "c.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=128x72:r=60:d=0.2", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-g", "1", str(clip)], check=True)
    remap = [0.0 + j * 2 / 60.0 for j in range(8)]                 # runs past the 12-frame clip's end
    plan = P.Plan(raw={"footage": {"c": "assets/c.mp4"}, "dur": 8, "fps": 30}, root=film)
    shot = P.Shot(0, {"name": "S", "src": "c", "a": 0, "b": 8, "end": 8, "remap": remap})
    plan.shots = [shot]
    held = R.retime_shot(plan, shot, tmp_path / "out", mode="mix", scale=0.5, log=lambda *_: None)
    img = cv2.imread(str(tmp_path / "out" / "S" / "0003.png"))
    assert img.shape == (36, 64, 3)
    meta = json.loads((tmp_path / "out" / "S" / "retime.json").read_text())
    assert meta["mode"] == "mix" and meta["clip_frames"] == 12 and "3" in meta["frames"]
    assert held and held[-1] == 7
    assert len(list((tmp_path / "out" / "S").glob("*.png"))) == 8
