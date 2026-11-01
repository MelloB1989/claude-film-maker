"""hoop_earring — one small polished 18k gold hinged-clicker hoop: 16 mm outer diameter, 1.6 mm round wire.

The hoop lies in the XZ plane (it faces +-Y) and hangs toward -Z. Origin: the piercing point, i.e. the
wire's centreline at the top of the hoop (the wire there runs along X, through the lobe).

The clicker: the top arc (from the hinge at 10 o'clock, seen from +Y, to the catch at 2 o'clock)
is the hinged post that swings open. Hairline seams cut the wire at both ends of it, and the hinge
is a small three-knuckle barrel (pin axis along Y) on the inside of the hoop at 10 o'clock.

One material: M_Gold. UVs: U along the wire, V round it (1 UV unit = 1 m).

    blender -b --factory-startup -P films/host-studio/props/hoop_earring.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as SM  # noqa: E402
import _accessories as A  # noqa: E402

MMv = A.MM
args = A.parse_args(__file__)
S.reset_scene()

GOLD = S.material("M_Gold", (0.98, 0.74, 0.38), 0.10, metallic=1.0)
SM.roughness_noise(GOLD, 0.07, 0.14, scale=2500.0)

# --------------------------------------------------------------------------- dimensions (mm)
OD = 16.0
WIRE_R = 0.8
RC = OD / 2 - WIRE_R              # 7.2: radius of the wire's centreline
CENTRE = Vector((0.0, 0.0, -RC))  # the hoop's centre; the top of the centreline is the origin
HINGE = math.radians(-60.0)       # angle from the top, positive towards +X
CATCH = math.radians(55.0)
SEAM_HALF = 0.05 / RC             # half-width of a seam (angle): ~0.11 mm wide on the outside
SEAM_DEPTH = 0.07
PROFILE_SEGS = 18
BASE_STEPS = 80


def at(th):
    """Centreline point and outward radial direction at angle th (0 = top)."""
    n = Vector((math.sin(th), 0.0, math.cos(th)))
    return CENTRE + RC * n, n


# ring angles: an even spread, plus six rings per seam
angles = []
for k in range(BASE_STEPS):
    th = -math.pi + 2 * math.pi * k / BASE_STEPS
    if min(abs(th - s) for s in (HINGE, CATCH)) > 3.0 * SEAM_HALF + math.radians(1.5):
        angles.append((th, 0.0))
for s in (HINGE, CATCH):
    # steep walls (sharp edges) and a support ring each side, so the seam stays a crisp hairline
    angles += [(s - 3.0 * SEAM_HALF, 0.0), (s - 1.0 * SEAM_HALF, 0.0), (s - 0.4 * SEAM_HALF, SEAM_DEPTH),
               (s + 0.4 * SEAM_HALF, SEAM_DEPTH), (s + 1.0 * SEAM_HALF, 0.0), (s + 3.0 * SEAM_HALF, 0.0)]
angles.sort()

pts, frames, depth = [], [], []
Y = Vector((0, 1, 0))
for th, d in angles:
    p, n = at(th)
    t = Vector((math.cos(th), 0.0, -math.sin(th)))
    pts.append(p)
    frames.append((t, n, Y))
    depth.append(d)


def wire_profile(i):
    r = WIRE_R - depth[i]
    return [(r * math.cos(A.TAU * k / PROFILE_SEGS), r * math.sin(A.TAU * k / PROFILE_SEGS))
            for k in range(PROFILE_SEGS)]


hoop = A.tube("hoop", pts, frames, wire_profile, [GOLD], closed_path=True, caps=False)

# --------------------------------------------------------------------------- hinge barrel
# Pin axis along Y, on the inside of the wire at the hinge; it stands 0.3 mm proud of the inner
# face and 0.15 mm past each side of the wire, split into three knuckles by two fine grooves.
BR = 0.5
hp, hn = at(HINGE)
bc = CENTRE + (RC - 0.62) * hn
barrel_prof = [  # (radius, y)
    (0.0, -0.69), (0.17, -0.69), (0.20, -0.71), (0.40, -0.71), (0.47, -0.68), (0.50, -0.61),
    (0.50, -0.27), (0.47, -0.235), (0.50, -0.20),
    (0.50, 0.20), (0.47, 0.235), (0.50, 0.27),
    (0.50, 0.61), (0.47, 0.68), (0.40, 0.71), (0.20, 0.71), (0.17, 0.69), (0.0, 0.69),
]
SEGS_B = 20
bm, uvl = A.new_bm()
rings = []
for r, y in barrel_prof:
    if r < 1e-9:
        rings.append([bm.verts.new(bc + Vector((0, y, 0)))])
    else:
        rings.append([bm.verts.new(bc + Vector((r * math.cos(A.TAU * k / SEGS_B), y,
                                                 r * math.sin(A.TAU * k / SEGS_B)))) for k in range(SEGS_B)])
s_prof = A.arc_len(barrel_prof)
for i in range(len(rings) - 1):
    a, b = rings[i], rings[i + 1]
    for k in range(SEGS_B):
        k2 = (k + 1) % SEGS_B
        u0, u1 = k / SEGS_B * A.TAU * BR * MMv, (k + 1) / SEGS_B * A.TAU * BR * MMv
        v0, v1 = s_prof[i] * MMv, s_prof[i + 1] * MMv
        if len(a) == 1:
            A.face(bm, uvl, (a[0], b[k2], b[k]), ((u0, v0), (u1, v1), (u0, v1)))
        elif len(b) == 1:
            A.face(bm, uvl, (a[k], a[k2], b[0]), ((u0, v0), (u1, v0), (u0, v1)))
        else:
            A.face(bm, uvl, (a[k], a[k2], b[k2], b[k]), ((u0, v0), (u1, v0), (u1, v1), (u0, v1)))
barrel = A.to_obj(bm, "barrel", [GOLD])

ob = A.finish("hoop_earring", [hoop, barrel], args, origin=(0, 0, 0), sharp_angle=40)
lo, hi = S.bbox(ob)
print(f"hoop_earring: outer diameter (Z extent of the ring) {(0.0008 - lo.z) * 1000:.2f} mm")


# --------------------------------------------------------------------------- previews
def ear_standin():
    """A lobe, the lower ear and the side of a head, for the close-up (preview only)."""
    skin = A.skin_material()
    parts = []
    for name, centre, radii, rot in (
            ("_lobe", (0.0, -0.8, 0.6), (2.3, 9.0, 6.8), 0.0),
            ("_ear", (-0.6, -3.0, 22.0), (3.4, 14.0, 24.0), -0.18),
            ("_helix", (-0.9, -6.5, 20.0), (4.2, 10.5, 22.0), -0.25)):
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=32, radius=1.0)
        for v in bm.verts:
            v.co = Vector((v.co.x * radii[0], v.co.y * radii[1], v.co.z * radii[2]))
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0),
                         matrix=Matrix.Rotation(rot, 3, "X"))
        bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(centre))
        for f in bm.faces:
            f.smooth = True
        parts.append(A.to_obj(bm, name, [skin]))
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=96, v_segments=64, radius=80.0)
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((-92.0, 6.0, 26.0)))
    for f in bm.faces:
        f.smooth = True
    parts.append(A.to_obj(bm, "_head", [skin]))
    A.hide_stage()


V34 = (1.0, 0.8, 0.7)
close_box = (Vector((-0.004, -0.010, lo.z - 0.001)), Vector((0.004, 0.010, 0.006)))
if not args.no_render:
    A.render_views(ob, args.out, args.samples, [
        ("hoop_earring.png", V34, 70, 1.15, None, None),
        ("hoop_earring_front.png", (1.0, 0.0, 0.05), 70, 1.15, None, None),
        ("hoop_earring_side.png", (0.0, 1.0, 0.05), 70, 1.15, None, None),
        ("hoop_earring_seam.png", (0.35, 1.0, 0.55), 70, 1.0,
         ((Vector(at(HINGE)[0]) - Vector((1.6, 1.0, 1.6))) * MMv, (Vector(at(HINGE)[0]) + Vector((1.6, 1.0, 1.6))) * MMv),
         None),
        ("hoop_ear.png", (1.0, 0.75, 0.10), 70, 1.05, close_box, ear_standin),
    ])
