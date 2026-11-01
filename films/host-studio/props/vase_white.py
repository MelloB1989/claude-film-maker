"""vase_white — a 20 cm white ceramic bud vase with a soft shoulder.

Thrown on a lathe profile with a little out-of-round; hollow. The body widens gently to a high,
rounded shoulder that rolls into a slim neck with a slightly flared, rounded lip; the inner neck
is modelled. Origin: bottom centre. Slot: M_CeramicWhite.

    blender -b --factory-startup -P films/host-studio/props/vase_white.py -- --out films/host-studio/props/out
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as M  # noqa: E402

NAME = "vase_white"

OUTER = [
    (0.0, 0.2), (2.8, 0.2), (3.05, 0.1), (3.2, 0.02), (3.4, 0.0), (3.62, 0.08), (3.78, 0.35),
    (3.92, 1.3), (4.08, 3.5), (4.25, 6.5), (4.40, 9.3), (4.45, 10.9), (4.38, 12.2), (4.05, 13.4),
    (3.35, 14.5), (2.4, 15.4), (1.6, 16.1), (1.25, 16.8), (1.17, 17.7), (1.22, 18.6), (1.38, 19.35),
    (1.55, 19.78), (1.60, 19.92), (1.53, 20.0), (1.43, 19.98), (1.34, 19.88),
]
INNER = [   # the inside: the neck matters (it shows in the mouth); the belly is never seen
    (1.27, 19.6), (1.08, 18.9), (0.86, 17.7), (0.90, 16.8), (1.25, 16.1), (2.0, 15.4), (3.0, 14.4),
    (3.9, 12.2), (3.98, 9.3), (3.6, 3.5), (3.3, 1.3), (2.6, 0.8), (0.0, 0.76),
]


def build():
    mat = M.S.material("M_CeramicWhite", (0.86, 0.85, 0.81), 0.22, specular=0.6)
    M.roughness_noise(mat, 0.16, 0.30, scale=40.0)
    return [M.vase(NAME, OUTER, INNER, mat, seed=37, amp=0.005, lean=0.0012)]


if __name__ == "__main__":
    args = S.parse_args(__file__)
    S.reset_scene()
    M.finish(NAME, build(), args, sharp_angle=60)
