"""drone_remote — the drone's generic handheld controller, lying flat face up. No logos or text anywhere.

~15 (Y) x 10 (X) x 4 cm: a dark grey body with two grips toward the front (+X), two thumbsticks screwed in,
a three-position mode switch, power and return buttons, a row of battery dots, a folded phone clamp along
the back edge, a gimbal dial and a shutter button on the back shoulders, a USB-C port between the grips.
Modelled in cm. Origin: bottom centre of the footprint.

    blender -b --factory-startup -P films/host-studio/props/drone_remote.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _drone_kit as K  # noqa: E402

Z0, Z1 = 1.1, 3.3               # body underside / face
STICKS = [(0.9, -4.1), (0.9, 4.1)]


def outline():
    half = [(-3.3, 0), (-3.3, 5.6), (-3.15, 6.8), (-2.6, 7.35), (-1.7, 7.5), (2.0, 7.5), (4.2, 7.2), (5.2, 6.2), (5.3, 4.8),
            (4.8, 3.6), (3.9, 2.8), (3.6, 1.5), (3.6, 0)]
    pts = half + [(x, -y) for x, y in reversed(half[1:-1])]
    return K.ccw(K.chaikin(pts, 3))


def add_slab(bm, out, z0, z1, rb, rt, steps=5, slot=0):
    prof = [(rb + 0.06, z0)]          # narrow flat bands keep the caps' normals straight
    for k in range(steps + 1):
        a = k / steps * math.pi / 2
        prof.append((rb * (1 - math.sin(a)), z0 + rb * (1 - math.cos(a))))
    for k in range(steps + 1):
        a = k / steps * math.pi / 2
        prof.append((rt * (1 - math.cos(a)), z1 - rt + rt * math.sin(a)))
    prof.append((rt + 0.06, z1))
    rings = [[(x, y, z) for x, y in K.inset(out, d)] for d, z in prof]
    K.add_grid(bm, rings, "ngon", "ngon", slot)


def build():
    M = K.materials()
    CTRL, DARK = M["ctrl"], M["dark"]
    parts = []

    # ---- face plate (crisp edges) over a lower shell (inset 0.6 mm: the parting line), recesses cut through the
    #      plate (stick wells, mode-switch slot, button rings) and the shell (USB-C), lined in M_DroneDark
    out = outline()
    bm = bmesh.new()
    ZS = Z1 - 0.95                                       # parting line
    add_slab(bm, out, ZS, Z1, 0.04, 0.28, steps=4)
    low = bmesh.new()
    add_slab(low, K.inset(out, 0.06), Z0, ZS + 0.1, 0.6, 0.02, steps=4)
    cut = bmesh.new()
    for x, y in STICKS:
        K.add_lathe(cut, [(0, 2.95), (1.22, 2.95), (1.22, 4.0), (0, 4.0)], Matrix.Translation((x, y, 0)), segs=40,
                    slot=1)
    K.add_prism(cut, S.rounded_rect(0.55, 1.5, 0.25, 4), (1.0, 0, 3.05), (1.0, 0, 4.0), up=(1, 0, 0), slot=1)
    for y in (-1.0, 1.0):
        K.add_lathe(cut, [(0, 3.12), (0.44, 3.12), (0.44, 4.0), (0, 4.0)], Matrix.Translation((2.6, y, 0)),
                    segs=28, slot=1)
    lcut = bmesh.new()
    K.add_prism(lcut, S.rounded_rect(0.88, 0.3, 0.14, 4), (3.0, 0, 1.85), (5.0, 0, 1.85), up=(0, 1, 0), slot=1)
    parts.append(K.mk("body", bm, [CTRL, DARK], cut=cut))
    parts.append(K.mk("lower_shell", low, [CTRL, DARK], cut=lcut))

    # ---- grips: moulded lobes under the front corners, each with a ribbed rubber pad on its outer flank
    grips = bmesh.new()
    lobe = K.ccw(K.chaikin([(1.3, -1.6), (4.6, -1.7), (5.0, -0.6), (4.7, 1.7), (1.6, 1.8), (1.0, 0.4)], 3))
    for s in (1, -1):
        add_slab(grips, [(x, s * 5.15 + y) for x, y in lobe], 0.0, Z0 + 0.3, 0.6, 0.02, steps=5)

    # ---- folded phone clamp along the back edge, with a seam gap and a rubber strip on top
    clamp = bmesh.new()
    add_slab(clamp, K.ccw(S.rounded_rect(1.62, 12.5, 0.5, 6)), 0.0, 3.15, 0.45, 0.22)
    bmesh.ops.translate(clamp, verts=clamp.verts, vec=(-4.19, 0, 0))
    darkb = bmesh.new()
    K.add_prism(darkb, S.rounded_rect(0.7, 10.4, 0.3, 4), (-4.19, 0, 2.9), (-4.19, 0, 3.19), up=(1, 0, 0))
    for s in (1, -1):    # clamp jaws at the ends
        K.add_prism(darkb, S.rounded_rect(1.1, 0.5, 0.2, 3), (-4.19, s * 6.0, 1.0), (-4.19, s * 6.0, 3.22),
                    up=(1, 0, 0))

    # ---- sticks: rubber boot, stem, knurled cap
    dark = bmesh.new()
    for x, y in STICKS:
        m = Matrix.Translation((x, y, 0))
        K.add_lathe(dark, K.fillet([(0, 2.9), (1.14, 2.9), (1.14, 3.04), (0.9, 3.17), (0.4, 3.24), (0, 3.25)],
                                   [0, 0, 0.05, 0.08, 0.05, 0], 2), m, segs=32)
        K.add_lathe(dark, K.fillet([(0, 3.2), (0.21, 3.2), (0.2, 3.9), (0, 3.9)], [0, 0, 0.03, 0], 2), m, segs=16)
        K.add_lathe(dark, K.fillet([(0, 3.86), (0.5, 3.86), (0.56, 3.95), (0.56, 4.2), (0.5, 4.28), (0.3, 4.24),
                                    (0, 4.21)], [0, 0.04, 0.04, 0.04, 0.03, 0.05, 0], 2), m, segs=32,
                    rmod=lambda r, z, a: r * (1 + 0.035 * math.cos(16 * a)) if r > 0.53 else r)

    # ---- mode switch toggle, power and return buttons, battery dots
    K.add_box(darkb, (0.84, -0.6, 3.0), (1.16, -0.18, 3.42))
    for y in (-1.0, 1.0):
        K.add_lathe(dark, K.fillet([(0, 3.05), (0.35, 3.05), (0.35, 3.33), (0.26, 3.4), (0, 3.41)],
                                   [0, 0, 0.04, 0.05, 0], 3), Matrix.Translation((2.6, y, 0)), segs=28)
    for k in range(4):
        K.add_lathe(dark, K.fillet([(0, 3.2), (0.07, 3.2), (0.07, 3.315), (0, 3.32)], [0, 0, 0.02, 0], 2),
                    Matrix.Translation((1.85, -0.45 + 0.3 * k, 0)), segs=12)

    # ---- shoulders on the back edge: gimbal dial (left) and shutter button (right)
    K.add_lathe(dark, K.fillet([(0, -0.22), (0.62, -0.22), (0.62, 0.22), (0, 0.22)], 0.05, 2),
                Matrix.Translation((-3.15, -6.75, 2.25)) @ Matrix.Rotation(math.radians(90), 4, "X"), segs=36,
                rmod=lambda r, z, a: r * (1 + 0.03 * math.cos(18 * a)) if r > 0.6 else r)
    K.add_lathe(dark, K.fillet([(0, 0), (0.36, 0), (0.36, 0.42), (0.3, 0.5), (0, 0.51)], [0, 0, 0.04, 0.04, 0], 3),
                Matrix.Translation((-3.0, 6.75, 2.25)) @ Matrix.Rotation(math.radians(-90), 4, "Y"), segs=24)

    gr = K.mk("grips", grips, CTRL)
    parts.append(gr)
    gbvh = K.bvh_of([gr])
    for s in (1, -1):
        for k in range(9):
            x = 1.9 + 0.3 * k
            K.conform_strip(gbvh, [(x, s * 12, 0.25 + 0.1 * j) for j in range(9)], (0, -s, 0),
                            [(0.03 * math.cos(a), 0.07 * math.sin(a)) for a in
                             [2 * math.pi * i / 8 for i in range(8)]], dark)
    parts.append(K.mk("clamp", clamp, CTRL))
    parts.append(K.mk("dark_boxes", darkb, DARK, bevel=0.04, segs=2, angle=40))
    parts.append(K.mk("dark_parts", dark, DARK))
    return parts


def main():
    args = S.parse_args(__file__)
    S.reset_scene()
    ob, _origin = K.assemble("drone_remote", build(), sharp_angle=40)
    K.export(ob, args)
    if not args.no_render:
        S.render_preview(ob, os.path.join(args.out, "drone_remote.png"), (1.0, -0.75, 0.85), args.samples, lens=60)


if __name__ == "__main__":
    main()
