"""perform.blend_eyes on key-reduced curves (the engine drops keys where a curve is linear): the result must follow
the lock's aim inside the locked spans and keep the face's own eyes outside (07 Nov: a key-reduced grid missed it)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import perform as PF  # noqa: E402


def curves(fn, times):
    out = {}
    for e in "LR":
        for pos, neg in (("Left", "Right"), ("Up", "Down")):
            v = np.array([fn(t, pos) for t in times])
            out[f"CTRL_expressions_eyeLook{pos}{e}"] = [list(times), list(np.clip(v, 0, 1))]
            out[f"CTRL_expressions_eyeLook{neg}{e}"] = [list(times), list(np.clip(-v, 0, 1))]
    return out


def test_follows_the_lock_on_sparse_keys():
    face = curves(lambda t, k: 0.01, [0.0, 3.0, 20.0])            # 3 keys only: flat, slightly up
    lock = curves(lambda t, k: (-0.03 if k == "Up" else 0.02) if 8 <= t * 24 <= 12 * 24 else 0.01,
                  list(np.arange(0, 20, 1 / 12)))
    out, _ = PF.blend_eyes(face, lock, [[8 * 24, 12 * 24, "CAM"]])
    t = np.array(out["CTRL_expressions_eyeLookUpL"][0])
    up = np.array(out["CTRL_expressions_eyeLookUpL"][1]) - np.array(out["CTRL_expressions_eyeLookDownL"][1])
    mid = (t > 9) & (t < 11)
    assert abs(np.median(up[mid]) - (-0.03)) < 0.002
    assert abs(np.median(up[t > 15]) - 0.01) < 1e-6
    assert np.median(np.diff(t)) < 0.034  # a uniform 30 fps grid, not the face's 3 keys
