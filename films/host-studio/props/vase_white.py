"""vase_white — a 22 cm white porcelain bottle vase: a slender neck over a soft, high shoulder.

Premium studio ceramic for close-ups: a smooth, finely tessellated thrown profile (adaptive
rings, ~190 columns) with only a trace of out-of-round, a rounded lip slightly thicker than the
neck wall, the inside of the neck modelled (it reads dark in the mouth). A glossy glaze
(M_CeramicWhite) stops ~1.7 cm above the foot on a soft rolled bead with two gentle drips and a
little pooling where the shoulder turns into the neck; below it a crisp trimmed foot ring in raw
buff stoneware (M_ClayFoot) with a recessed base. Colour attribute "Glaze": R = glaze build-up,
G = thin glaze over the lip, B = cavity (inside the neck). Origin: bottom centre.

    blender -b --factory-startup -P films/host-studio/props/vase_white.py -- --out films/host-studio/props/out
"""
import os
import sys

from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as M  # noqa: E402

NAME = "vase_white"

UNDER = M.foot_ring(0.30, 2.62, 3.12, 0.42, 0.16, (3.50, 0.66))
OUTER = [
    (3.50, 0.66), (3.72, 1.0), (4.0, 1.7), (4.3, 2.9), (4.56, 4.6), (4.76, 6.6), (4.86, 8.6),
    (4.84, 10.2), (4.66, 11.6), (4.24, 12.9), (3.56, 14.05), (2.70, 15.0), (1.92, 15.8), (1.42, 16.6),
    (1.18, 17.5), (1.09, 18.5), (1.10, 19.6), (1.18, 20.5), (1.31, 21.15), (1.47, 21.6),
] + M.lip_roll(1.58, 1.12, 22.0)[:1]
INNER = M.lip_roll(1.58, 1.12, 22.0)[1:] + [
    (1.10, 21.55), (1.0, 21.0), (0.88, 20.3), (0.80, 19.4), (0.78, 18.5), (0.84, 17.5), (1.02, 16.6),
    (1.5, 15.8), (2.3, 14.95), (3.15, 13.95), (3.85, 12.75), (4.28, 11.5), (4.48, 10.1), (4.5, 8.6),
    (4.4, 6.6), (4.2, 4.6), (3.9, 2.9), (3.45, 1.75), (2.6, 1.15), (1.3, 1.0), (0.0, 0.97),
]
GLAZE_Z = 1.75
DRIPS = [(14.0, 0.62, 0.58), (47.0, 0.36, 0.48)]   # (theta deg, length, width) cm


def materials():
    glaze = M.glaze_material("M_CeramicWhite", (0.885, 0.875, 0.845), 0.09,
                             thin=(0.80, 0.70, 0.56), pooled=(0.80, 0.82, 0.83), subsurface=0.08)
    return glaze, M.clay_foot_material()


def build():
    glaze, clay = materials()
    return [M.glazed_vase(NAME, UNDER, OUTER, INNER, [glaze, clay], GLAZE_Z, DRIPS, segs=152, seed=37,
                          pool=(15.2, 17.2, 0.03))]


VIEWS = M.VASE_VIEWS + [("_close", (1.0, 0.35, 0.16), 85, 1.05, (Vector((-0.05, -0.05, 0.0)),
                                                              Vector((0.05, 0.05, 0.06))))]

if __name__ == "__main__":
    args = S.parse_args(__file__)
    S.reset_scene()
    M.finish(NAME, build(), args, sharp_angle=60, views=VIEWS, glossy=True)
