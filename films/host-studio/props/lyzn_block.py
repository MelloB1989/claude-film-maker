"""lyzn_block — a frosted acrylic block, 4 (X, depth) x 10 (Y) x 10 (Z) cm, 3 mm rounded edges.

The word "lyzn" is engraved on the front (+X) face. The engraving is a decal: a quad of its own
slot, M_Label_Lyzn, 0.3 mm in front of the flat front face, covering the whole flat area inside
the rounded edges (9.4 x 9.4 cm), UV 0..1 filling it (U to screen-right = +Y, V up = +Z).
Origin: bottom centre. Slots: M_Acrylic, M_Label_Lyzn.

    blender -b --factory-startup -P films/host-studio/props/lyzn_block.py -- --out films/host-studio/props/out
"""
import os
import sys

import bmesh
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as M  # noqa: E402

NAME = "lyzn_block"
CM, MM = M.CM, M.MM
DX, DY, DZ = 4.0 * CM, 10.0 * CM, 10.0 * CM
R = 3.0 * MM
DECAL_OFFSET = 0.3 * MM


def build():
    acrylic = S.material("M_Acrylic", (0.93, 0.92, 0.90), 0.45)
    M.glassy(acrylic, roughness=0.35, ior=1.49, frost=0.62, frost_color=(0.90, 0.88, 0.84), backfaces=False)
    label = M.label_material("M_Label_Lyzn")

    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, 0, DZ / 2)) @ Matrix.Diagonal((DX, DY, DZ, 1)))
    bmesh.ops.bevel(bm, geom=list(bm.edges) + list(bm.verts), offset=R, offset_type="OFFSET",
                    segments=4, profile=0.5, affect="EDGES", clamp_overlap=True)
    M.box_uv(bm, scale=1.0, grain=1)
    block = M.obj(bm, "block", [acrylic])

    # the engraving decal on the flat part of the front face
    x = DX / 2 + DECAL_OFFSET
    y0, y1 = -DY / 2 + R, DY / 2 - R
    z0, z1 = R, DZ - R
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    vs = [bm.verts.new(co) for co in ((x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1))]
    f = bm.faces.new(vs)                       # counter-clockwise seen from +X: normal +X
    for loop, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uvl].uv = uv
    decal = M.obj(bm, "decal", [label])
    return [block, decal]


def face_front(ob):
    """tidy() recalculates normals per island; make sure the lone decal quad still faces +X."""
    me = ob.data
    slot = [m.name for m in me.materials].index("M_Label_Lyzn")
    for p in me.polygons:
        if p.material_index == slot and p.normal.x < 0:
            p.flip()
    me.update()


if __name__ == "__main__":
    args = S.parse_args(__file__)
    S.reset_scene()
    M.finish(NAME, build(), args, origin=(0, 0, 0), sharp_angle=40, post=face_front)
