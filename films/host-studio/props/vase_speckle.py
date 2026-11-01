"""vase_speckle — a cream speckled stoneware bottle vase, 24 cm tall, 11 cm across, 3 cm neck.

Thrown on a lathe profile with a little out-of-round, lean and throwing lines; hollow, with a
rounded lip and the inner neck modelled so the mouth reads from above.
Origin: bottom centre. Slot: M_Stoneware.

    blender -b --factory-startup -P films/host-studio/props/vase_speckle.py -- --out films/host-studio/props/out
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as M  # noqa: E402

NAME = "vase_speckle"

# (r, z) cm: foot centre, up the outside, over the lip ...
OUTER = [
    (0.0, 0.22), (2.8, 0.22), (3.08, 0.12), (3.3, 0.03), (3.5, 0.0), (3.76, 0.05), (3.98, 0.22),
    (4.35, 0.75), (4.82, 1.9), (5.22, 3.8), (5.45, 6.2), (5.50, 8.7), (5.38, 11.1), (4.98, 13.4),
    (4.15, 15.4), (3.05, 16.95), (2.1, 18.15), (1.64, 19.25), (1.50, 20.4), (1.52, 21.6),
    (1.62, 22.65), (1.74, 23.45), (1.79, 23.78), (1.75, 23.94), (1.66, 24.0), (1.55, 23.98), (1.46, 23.87),
]
# ... and down the inside of the neck to the inner floor.
INNER = [
    (1.40, 23.55), (1.24, 22.65), (1.12, 21.6), (1.10, 20.4), (1.22, 19.25), (1.62, 18.15),
    (2.55, 16.95), (3.62, 15.4), (4.75, 12.4), (5.0, 8.7), (4.75, 4.0), (4.0, 1.6), (2.5, 0.84), (0.0, 0.78),
]


def build():
    mat = M.speckle_material("M_Stoneware", (0.72, 0.63, 0.49), (0.20, 0.13, 0.08), 0.48,
                             fine=(380.0, 0.66), coarse=(130.0, 0.75))
    return [M.vase(NAME, OUTER, INNER, mat, seed=11, amp=0.009, lean=0.0018)]


if __name__ == "__main__":
    args = S.parse_args(__file__)
    S.reset_scene()
    M.finish(NAME, build(), args, sharp_angle=60)
