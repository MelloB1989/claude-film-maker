"""stool — a solid-walnut counter stool with a sculpted saddle seat (as in the concept's wide shot).

Seat height 65 cm (lowest point of the seat top); the seat is a rounded superellipse 32 cm deep
(X) x 38 cm wide (Y), dished and saddle-shaped (its sides rise ~1.5 cm, the front rolls off),
with a generous round-over on top and a small one underneath. Four round legs, splayed both
ways, taper from 3.4 cm under the seat to 2.4 cm at the floor; a ring of four rails at 25 cm.
All solid walnut (M_Walnut); UVs world-scale (1 unit = 1 m), grain along U: across the seat
(along Y) and along each leg and rail. Origin: bottom centre (between the feet, on the floor).

    blender -b --factory-startup -P films/host-studio/props/stool.py -- --out films/host-studio/props/out

Writes <out>/stool.fbx, stool.png (3/4) and stool_front.png.
"""
import math
import os
import sys

from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _furniture as F  # noqa: E402

NAME = "stool"
cm = 0.01

SEAT_H = 65 * cm             # lowest point of the seat top (its centre)
SEAT_A = 16 * cm             # half depth (X)
SEAT_B = 19 * cm             # half width (Y)
SEAT_N = 2.6                 # superellipse exponent: a soft rounded rectangle
SEAT_BOT = 60.7 * cm         # flat underside
SIDE_RISE = 1.6 * cm         # saddle: the sides rise this much at the edge
FRONT_DROP = 1.0 * cm        # front edge rolls off
BACK_RISE = 0.4 * cm
DISH = 0.4 * cm              # central dish
R_TOP = 1.4 * cm             # round-over on the top edge
R_BOT = 0.8 * cm             # round-over under the seat
SEGS = 112                   # around the seat

LEG_TOP = (9.5 * cm, 11.5 * cm)    # |x|, |y| of the leg axes under the seat
LEG_FOOT = (18.5 * cm, 21.5 * cm)  # |x|, |y| of the leg axes on the floor
LEG_R_TOP = 1.7 * cm
LEG_R_FOOT = 1.2 * cm
LEG_SEGS = 32
RAIL_Z = 25 * cm
RAIL_R = 0.95 * cm


def walnut():
    return F.wood("M_Walnut", (0.50, 0.34, 0.23), (0.27, 0.16, 0.10), roughness=0.55, ring=9.0, seed=0.4)


def z_top(x, y):
    """Height of the seat's top surface."""
    u, v = x / SEAT_A, y / SEAT_B
    r2 = min(1.0, u * u + v * v)
    z = SEAT_H + DISH * r2 + SIDE_RISE * v * v
    z -= FRONT_DROP * max(0.0, u) ** 2
    z += BACK_RISE * max(0.0, -u) ** 2
    return z


def outline():
    """Superellipse points and outward normals (2D)."""
    pts = []
    for i in range(SEGS):
        t = 2 * math.pi * i / SEGS
        c, s = math.cos(t), math.sin(t)
        pts.append(Vector((SEAT_A * math.copysign(abs(c) ** (2 / SEAT_N), c),
                           SEAT_B * math.copysign(abs(s) ** (2 / SEAT_N), s))))
    nrm = []
    for i in range(SEGS):
        tg = pts[(i + 1) % SEGS] - pts[i - 1]
        n = Vector((tg.y, -tg.x)).normalized()
        if n.dot(pts[i]) < 0:
            n = -n
        nrm.append(n)
    return pts, nrm


def seat(mat):
    pts, nrm = outline()
    rings = []        # each ring: list of SEGS (x, y, z), or a single pole

    def ring(fn):
        rings.append([fn(p, n) for p, n in zip(pts, nrm)])

    # top: rings from the centre out to where the round-over starts
    rings.append([(0.0, 0.0, z_top(0, 0))])
    for k in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.69, 0.77, 0.84, 0.9, 0.95, 1.0):
        ring(lambda p, n, k=k: (*(k * (p - R_TOP * n)), z_top(*(k * (p - R_TOP * n)))))
    # round-over to the vertical edge
    for j in range(1, 7):
        phi = math.pi / 2 * j / 6

        def f(p, n, phi=phi):
            q = p - R_TOP * n
            ze = z_top(*q)
            return (*(q + R_TOP * math.sin(phi) * n), ze - R_TOP * (1 - math.cos(phi)))
        ring(f)
    # the vertical edge, then the small round under the seat
    ring(lambda p, n: (*p, (z_top(*(p - R_TOP * n)) - R_TOP + SEAT_BOT + R_BOT) / 2))
    for j in range(0, 5):
        phi = math.pi / 2 * j / 4
        ring(lambda p, n, phi=phi: (*(p - R_BOT * n + R_BOT * math.cos(phi) * n),
                                    SEAT_BOT + R_BOT - R_BOT * math.sin(phi)))
    # flat underside
    for k in (0.8, 0.5, 0.2):
        ring(lambda p, n, k=k: (*(k * (p - R_BOT * n)), SEAT_BOT))
    rings.append([(0.0, 0.0, SEAT_BOT)])

    verts, faces, idx = [], [], []
    for r in rings:
        idx.append(list(range(len(verts), len(verts) + len(r))))
        verts += r
    for a, b in zip(idx, idx[1:]):
        for i in range(SEGS):
            j = (i + 1) % SEGS
            if len(a) == 1:
                faces.append((a[0], b[i], b[j]))
            elif len(b) == 1:
                faces.append((a[i], b[0], a[j]))
            else:
                faces.append((a[i], b[i], b[j], a[j]))
    ob = F.mesh("seat", verts, faces, [mat])
    return F.uv_box(ob, "y", offset=(0.21, 0.63))


def leg_axis(sx, sy):
    top = Vector((sx * LEG_TOP[0], sy * LEG_TOP[1], SEAT_BOT))
    foot = Vector((sx * LEG_FOOT[0], sy * LEG_FOOT[1], 0.0))
    return top, foot


def axis_at(top, foot, z):
    return top + (top.z - z) / (top.z - foot.z) * (foot - top)


def leg(name, top, foot, mat, k=0):
    """Round tapered leg; its ends are cut level (into the seat's underside / onto the floor),
    with a slightly rounded foot."""
    d = (foot - top).normalized()
    e1 = d.cross(Vector((0, 0, 1))).normalized()
    e2 = d.cross(e1)
    seg = LEG_SEGS

    def ring_at(t, z_plane=None, shrink=0.0):
        c = top + t * (foot - top)
        r = LEG_R_TOP + (LEG_R_FOOT - LEG_R_TOP) * t - shrink
        out = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            p = c + r * (math.cos(a) * e1 + math.sin(a) * e2)
            if z_plane is not None:
                p = p + (z_plane - p.z) / d.z * d
            out.append(p)
        return out

    rings = [[top + (0.4 * cm) / -d.z * -d]]       # cap centre, 4 mm up inside the seat
    rings.append(ring_at(0.0, SEAT_BOT + 0.4 * cm))
    for t in (0.04, 0.2, 0.4, 0.6, 0.8, 0.96):
        rings.append(ring_at(t))
    rings.append(ring_at(1.0, 0.25 * cm))
    rings.append(ring_at(1.0, 0.06 * cm, shrink=0.12 * cm))
    rings.append(ring_at(1.0, 0.0, shrink=0.3 * cm))
    rings.append([foot])
    verts, faces, idx = [], [], []
    for r in rings:
        idx.append(list(range(len(verts), len(verts) + len(r))))
        verts += [tuple(p) for p in r]
    for a, b in zip(idx, idx[1:]):
        for i in range(seg):
            j = (i + 1) % seg
            if len(a) == 1:
                faces.append((a[0], b[j], b[i]))
            elif len(b) == 1:
                faces.append((a[i], a[j], b[0]))
            else:
                faces.append((a[i], a[j], b[j], b[i]))
    ob = F.mesh(name, verts, faces, [mat])
    return F.uv_tube(ob, top, foot, offset=(0.13 * k, 0.0), seam=(-foot.x, -foot.y, 0))


def build():
    mat = walnut()
    parts = [seat(mat)]
    corners = [(1, 1), (1, -1), (-1, -1), (-1, 1)]      # going round
    axes = {c: leg_axis(*c) for c in corners}
    for k, c in enumerate(corners):
        parts.append(leg(f"leg{k}", *axes[c], mat, k))
    for i, c in enumerate(corners):
        c2 = corners[(i + 1) % 4]
        p0 = axis_at(*axes[c], RAIL_Z)
        p1 = axis_at(*axes[c2], RAIL_Z)
        rail = S.cylinder(f"rail{i}", p0, p1, RAIL_R, mat, segs=20)
        parts.append(F.uv_tube(rail, p0, p1, offset=(0.3 * i, 0.0), seam=(0, 0, -1)))
    return parts


def main():
    args = S.parse_args(__file__)
    S.reset_scene()
    ob = F.finalize(NAME, build(), origin=(0, 0, 0), sharp_angle=50, weighted=False)
    F.export(ob, args)
    if args.no_render:
        return
    lo, hi = S.bbox(ob)
    F.stage(floor=True)
    out = args.out
    F.shoot(os.path.join(out, NAME + ".png"), (1.0, 0.75, 0.55), lo, hi, args.samples, lens=60, rim=25)
    F.shoot(os.path.join(out, NAME + "_front.png"), (1.0, 0.0, 0.12), lo, hi, args.samples, lens=60)


if __name__ == "__main__":
    main()
