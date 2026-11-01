"""vase_black — a 16 cm black moon jar: a full, round body, a short neck and a rolled lip.

Premium studio ceramic for close-ups: a smooth, finely tessellated thrown profile (adaptive
rings, ~200 columns) with only a trace of out-of-round, a rounded lip slightly thicker than the
neck wall and the inside of the neck modelled (it reads dark in the mouth). A glossy black glaze
(M_CeramicBlack) stops ~1.6 cm above the foot on a soft rolled bead with two gentle drips and a
little pooling where the shoulder turns into the neck; below it a crisp trimmed foot ring in raw
buff stoneware (M_ClayFoot) with a recessed base. Colour attribute "Glaze": R = glaze build-up,
G = thin glaze over the lip (where a black glaze breaks to brown), B = cavity (inside the
neck). Origin: bottom centre.

    blender -b --factory-startup -P films/host-studio/props/vase_black.py -- --out films/host-studio/props/out
"""
import os
import sys

from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as M  # noqa: E402

NAME = "vase_black"

UNDER = M.foot_ring(0.30, 3.70, 4.22, 0.45, 0.18, (4.70, 0.86))
OUTER = [
    (4.70, 0.86), (5.12, 1.30), (5.78, 2.12), (6.55, 3.25), (7.28, 4.65), (7.86, 6.3), (8.18, 8.0),
    (8.24, 9.4), (8.02, 10.75), (7.45, 12.0), (6.55, 13.08), (5.42, 13.95), (4.32, 14.6), (3.48, 15.0),
    (3.02, 15.26), (2.82, 15.48), (2.79, 15.66),
] + M.lip_roll(2.88, 2.42, 16.0)[:1]
INNER = M.lip_roll(2.88, 2.42, 16.0)[1:] + [
    (2.40, 15.6), (2.40, 15.38), (2.58, 15.12), (3.0, 14.86), (3.85, 14.4), (4.95, 13.7), (6.0, 12.75),
    (6.9, 11.5), (7.5, 10.1), (7.72, 8.6), (7.62, 6.9), (7.2, 5.25), (6.5, 3.85), (5.6, 2.7),
    (4.6, 1.85), (3.3, 1.22), (1.6, 1.02), (0.0, 0.98),
]
GLAZE_Z = 2.2
DRIPS = [(20.0, 0.62, 0.62), (52.0, 0.36, 0.5)]   # (theta deg, length, width) cm


def materials():
    glaze = M.glaze_material("M_CeramicBlack", (0.014, 0.0135, 0.013), 0.09,
                             thin=(0.075, 0.036, 0.018), pooled=(0.006, 0.006, 0.006))
    return glaze, M.clay_foot_material()


def build():
    glaze, clay = materials()
    return [M.glazed_vase(NAME, UNDER, OUTER, INNER, [glaze, clay], GLAZE_Z, DRIPS, segs=160, seed=23, wobble=0.0035,
                          pool=(14.4, 15.4, 0.03))]


VIEWS = M.VASE_VIEWS + [("_close", (1.0, 0.35, 0.12), 85, 1.05, (Vector((-0.06, -0.06, 0.0)),
                                                               Vector((0.06, 0.06, 0.05))))]

if __name__ == "__main__":
    args = S.parse_args(__file__)
    S.reset_scene()
    M.finish(NAME, build(), args, sharp_angle=60, views=VIEWS, glossy=True)
