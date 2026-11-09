"""vase_speckle — a 24 cm cream speckled stoneware bottle vase, 11 cm across, 3.6 cm mouth.

The same form as before, refined to the premium-ceramic standard of the other vases: a smooth,
finely tessellated thrown profile with a trace of out-of-round, a rounded lip slightly thicker than
the neck wall and the inner neck modelled. A glossy speckled glaze (M_Stoneware) stops ~1.9 cm up
(~1.5 cm above the foot ring) on a soft rolled bead with two gentle drips and a little pooling at
the shoulder; below it a crisp trimmed foot ring in raw buff stoneware (M_ClayFoot) with a recessed
base. Colour attribute "Glaze": R = glaze build-up, G = thin glaze over the lip, B = cavity (inside
the neck). Origin: bottom centre.

    blender -b --factory-startup -P films/host-studio/props/vase_speckle.py -- --out films/host-studio/props/out
"""
import os
import sys

from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as M  # noqa: E402

NAME = "vase_speckle"

UNDER = M.foot_ring(0.30, 3.0, 3.50, 0.40, 0.18, (4.05, 0.72))
OUTER = [
    (4.05, 0.72), (4.42, 1.12), (4.84, 1.95), (5.22, 3.8), (5.45, 6.2), (5.50, 8.7), (5.38, 11.1),
    (4.98, 13.4), (4.15, 15.4), (3.05, 16.95), (2.1, 18.15), (1.64, 19.25), (1.50, 20.4), (1.52, 21.6),
    (1.61, 22.65), (1.72, 23.42),
] + M.lip_roll(1.82, 1.38, 24.0)[:1]
INNER = M.lip_roll(1.82, 1.38, 24.0)[1:] + [
    (1.36, 23.55), (1.27, 22.65), (1.15, 21.6), (1.12, 20.4), (1.24, 19.25), (1.64, 18.15),
    (2.57, 16.95), (3.64, 15.4), (4.5, 13.3), (4.98, 11.0), (5.08, 8.7), (4.96, 6.0), (4.62, 3.8),
    (4.08, 2.25), (3.15, 1.35), (1.6, 1.02), (0.0, 0.98),
]
GLAZE_Z = 1.9
DRIPS = [(10.0, 0.6, 0.66), (-58.0, 0.38, 0.52)]   # (theta deg, length, width) cm


def materials():
    base = (0.70, 0.62, 0.49)
    glaze = M.glaze_material("M_Stoneware", base, 0.11, orange_peel=0.008)
    for n in [n for n in glaze.node_tree.nodes if n.type in ("ATTRIBUTE", "SEPARATE_COLOR", "MIX", "MATH")]:
        glaze.node_tree.nodes.remove(n)          # rebuilt below on the speckled base
    nt = glaze.node_tree
    b = M.principled(glaze)
    specks = M.dot_speckle(glaze, base, (0.17, 0.10, 0.055),
                            layers=((650.0, 0.17, 0.30), (230.0, 0.13, 0.75), (90.0, 0.09, 0.93)))
    # thin glaze over the lip and the bead's build-up tint the speckled base (attribute "Glaze")
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "Glaze"
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(attr.outputs["Color"], sep.inputs["Color"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(sep.outputs["Green"], mix.inputs["Factor"])
    nt.links.new(specks, mix.inputs[6])
    mix.inputs[7].default_value = (0.60, 0.44, 0.28, 1)
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    M.cavity_darken(glaze, sep.outputs["Blue"])
    return glaze, M.clay_foot_material()


def build():
    glaze, clay = materials()
    return [M.glazed_vase(NAME, UNDER, OUTER, INNER, [glaze, clay], GLAZE_Z, DRIPS, segs=152, seed=11,
                          pool=(15.0, 17.5, 0.03))]


VIEWS = M.VASE_VIEWS + [("_close", (1.0, 0.35, 0.16), 85, 1.05, (Vector((-0.06, -0.06, 0.0)),
                                                              Vector((0.06, 0.06, 0.06))))]

if __name__ == "__main__":
    args = S.parse_args(__file__)
    S.reset_scene()
    M.finish(NAME, build(), args, sharp_angle=60, views=VIEWS, glossy=True)
