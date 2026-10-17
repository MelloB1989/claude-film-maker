import numpy as np

from filmtools.amv2 import mix, prep


def test_plan_frames_holds_across_cut_and_keeps_4k():
    d = np.full(9, 5.0)
    p = prep.plan_frames(10, [3], d, dedup=False)
    assert len(p) == 40
    assert all(p[4 * k] == (k, k, 0.0) for k in range(10))
    assert p[8:12] == [(2, 2, 0.0)] * 4 and p[12] == (3, 3, 0.0)   # the cut sits on frame 12, nothing blended into it
    assert p[5] == (1, 2, 0.25) and p[39] == (9, 9, 0.0)         # clip end holds


def test_plan_frames_dedup_crosses_repeated_frames():
    d = np.array([0.0, 5.0, 0.0, 5.0])                          # frames 0=1, 2=3 repeat, 4 new
    p = prep.plan_frames(5, [], d, dedup=True)
    assert p[0][2] == 0.0 and p[4] == (0, 2, 0.5)           # frame 1 sits half way to the next distinct picture


def test_lufs_and_true_peak_of_a_sine():
    t = np.arange(mix.SR * 3) / mix.SR
    x = np.stack([0.1 * np.sin(2 * np.pi * 1000 * t)] * 2, 1)
    assert abs(mix.lufs(x) - (-20.0)) < 0.1      # 0.1 peak sine, both channels: -20 LUFS (K-weighting is +0.7 dB at 1 kHz)
    assert abs(mix.true_peak_db(x) - (-20.0)) < 0.1


def test_limiter_respects_ceiling_and_duck_env_is_smooth():
    x = np.zeros((mix.SR, 2))
    x[20000, :] = 1.0
    y = mix.limit(x, -6.0)
    assert mix.true_peak_db(y) <= -5.9
    env = mix.duck_env(mix.SR * 2, [(mix.SR // 2, mix.SR, -6.0)])
    assert env.min() == np.float64(10 ** (-6 / 20)) and np.abs(np.diff(env)).max() < 1e-3
