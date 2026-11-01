"""vase_black — a round matte-black ceramic vase, 16 cm tall, 15 cm across, small mouth.

Thrown on a lathe profile with a little out-of-round; hollow, with a short neck, a rolled lip
and the inner neck modelled. Origin: bottom centre. Slot: M_CeramicBlack.

    blender -b --factory-startup -P films/host-studio/props/vase_black.py -- --out films/host-studio/props/out
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as M  # noqa: E402

NAME = "vase_black"

OUTER = [
    (0.0, 0.2), (3.5, 0.2), (3.78, 0.1), (3.95, 0.02), (4.15, 0.0), (4.45, 0.05), (4.75, 0.22),
    (5.6, 0.85), (6.5, 1.9), (7.15, 3.4), (7.48, 5.2), (7.48, 7.0), (7.12, 9.0), (6.25, 11.0),
    (4.95, 12.65), (3.55, 13.85), (2.45, 14.6), (1.98, 15.05), (1.86, 15.45), (1.90, 15.75),
    (1.86, 15.93), (1.75, 16.0), (1.62, 15.98), (1.53, 15.88),
]
INNER = [   # the inside: the neck matters (it shows in the mouth); the belly is never seen
    (1.49, 15.6), (1.47, 15.15), (1.62, 14.65), (2.5, 13.95), (4.2, 12.6), (6.1, 10.2),
    (6.95, 7.0), (6.7, 3.6), (5.4, 1.5), (3.2, 0.8), (0.0, 0.75),
]


def build():
    mat = M.S.material("M_CeramicBlack", (0.022, 0.021, 0.020), 0.62)
    M.roughness_noise(mat, 0.56, 0.64, scale=220.0)
    return [M.vase(NAME, OUTER, INNER, mat, seed=23, amp=0.006, lean=0.0012)]


if __name__ == "__main__":
    args = S.parse_args(__file__)
    S.reset_scene()
    M.finish(NAME, build(), args, sharp_angle=60)
