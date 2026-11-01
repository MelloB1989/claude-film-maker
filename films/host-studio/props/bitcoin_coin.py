"""bitcoin_coin — a 60 mm gold display coin standing in a slotted walnut block.

The coin: 60 mm across, 4.8 mm thick (the 40 mm design scaled 1.5x, relief included): a lathe
with a raised rim on both faces, small chamfers and a finely reeded (milled) edge as real
geometry (216 reeds). Obverse: a flat field with, in relief, a bitcoin "B" (a B with two
short vertical strokes through its top and bottom, tilted 14 degrees clockwise) standing 0.6 mm
proud with filleted edges, and around it a subtle circuit-trace pattern (traces, pads and vias,
0.18 mm proud) running out to a thin raised ring inside the rim. The B is our own geometric
construction (a stem, two D-shaped bowls with counters, serifs and two bar pairs), not traced
from any logo artwork. The relief is cut into the field with a constrained Delaunay
triangulation of the outlines, so the coin stays one closed, manifold shell.

The stand: a walnut block 80 x 40 x 20 mm (Y x X x Z), every edge rounded (1.5 mm), with a
router-cut slot 5.4 mm wide, 46 mm long with round ends and 9 mm deep, cut leaning back 10
degrees. The coin stands in it, its rim resting on the slot floor, leaning back 10 degrees and
facing +X with the B upright and unmirrored.

Origin: bottom centre of the stand. Slots: M_Gold, M_Walnut. UVs: the coin's faces planar
(0..1 across the diameter), its edge cylindrical; the walnut box-projected (1 UV = 1 m) with
the grain along the block (Y).

    blender -b --factory-startup -P films/host-studio/props/bitcoin_coin.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.geometry import delaunay_2d_cdt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as M  # noqa: E402
import _furniture as F  # noqa: E402

NAME = "bitcoin_coin"
MM = M.MM
TAU = M.TAU

R = 20.0            # radius, mm
T = 3.2             # thickness
SEG = 216           # segments of the plain rings
REEDS = 216         # reeds on the edge (2 vertices each: ridge, groove)
REED_DEPTH = 0.15
FIELD_R = 18.15     # obverse field radius
FIELD_Z = 2.75      # obverse field height (the rim stands to 3.2)
B_RELIEF = 0.40
TRACE_RELIEF = 0.12
B_FILLET = 0.09

# (r, z, kind) mm, from the reverse centre out over the edge and back in to the obverse field.
# kind: "p" plain ring (SEG), "r" reeded (2 * REEDS, full depth), "h" reeded at half depth
PROFILE = [
    (0.0, 0.30, "p"),
    (17.85, 0.30, "p"), (18.30, 0.08, "p"), (18.62, 0.0, "p"),
    (19.48, 0.0, "p"), (19.76, 0.06, "p"),
    (19.93, 0.20, "h"), (20.0, 0.38, "r"), (20.0, 2.82, "r"), (19.93, 3.00, "h"),
    (19.76, 3.14, "p"), (19.48, 3.20, "p"), (18.78, 3.20, "p"), (18.55, 3.14, "p"),
    (18.40, 3.00, "p"), (18.30, 2.82, "p"), (FIELD_R, FIELD_Z, "p"),
]


# --------------------------------------------------------------------------- body

def ring_radii(r, kind):
    if kind == "p":
        return [r] * SEG
    depth = REED_DEPTH if kind == "r" else REED_DEPTH * 0.5
    return [r if j % 2 == 0 else r - depth for j in range(2 * REEDS)]


def body(bm):
    rings = []
    for r, z, kind in PROFILE:
        if r <= 0:
            rings.append([bm.verts.new((0, 0, z * MM))])
            continue
        radii = ring_radii(r, kind)
        n = len(radii)
        rings.append([bm.verts.new((rr * MM * math.cos(TAU * k / n), rr * MM * math.sin(TAU * k / n), z * MM))
                      for k, rr in enumerate(radii)])
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1:
            for k in range(len(b)):
                bm.faces.new((a[0], b[k], b[(k + 1) % len(b)]))
        elif len(a) == len(b):
            n = len(a)
            for k in range(n):
                bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))
        else:                                   # bridge a 2N ring and an N ring (either order)
            big, small, flip = (a, b, False) if len(a) > len(b) else (b, a, True)
            n = len(small)
            for k in range(n):
                k1 = (k + 1) % n
                tris = ((big[2 * k], big[2 * k + 1], small[k]),
                        (big[2 * k + 1], small[k1], small[k]),
                        (big[2 * k + 1], big[(2 * k + 2) % (2 * n)], small[k1]))
                for t in tris:
                    bm.faces.new(tuple(reversed(t)) if flip else t)
    return rings[-1]


# --------------------------------------------------------------------------- 2D shapes (mm)

def ccw(poly):
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]))
    return poly if area > 0 else list(reversed(poly))


def circle(cx, cy, r, n):
    return [(cx + r * math.cos(TAU * k / n), cy + r * math.sin(TAU * k / n)) for k in range(n)]


def rect(x0, x1, y0, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def d_shape(x0, xa, y0, y1, n=18):
    """A rectangle from x0 to xa closed on the right by a half circle (a B's bowl)."""
    r, yc = (y1 - y0) / 2, (y0 + y1) / 2
    pts = [(x0, y0)]
    for k in range(n + 1):
        a = -math.pi / 2 + math.pi * k / n
        pts.append((xa + r * math.cos(a), yc + r * math.sin(a)))
    pts.append((x0, y1))
    return pts


def b_symbol():
    """The B as solids [(outline, [holes])] in its own units (cap height ~13.2, bars to +-8.8)."""
    els = [
        (rect(-4.4, -1.9, -6.6, 6.6), []),                                   # stem
        (d_shape(-4.0, 0.6, -1.0, 6.6), [d_shape(-2.0, 0.6, 1.0, 4.3, 14)]),     # upper bowl + counter
        (d_shape(-4.0, 1.3, -6.6, 1.0), [d_shape(-2.0, 1.3, -4.3, -1.0, 14)]),   # lower bowl + counter
        (rect(-5.8, -4.2, 4.3, 6.6), []),                                     # top serif
        (rect(-5.8, -4.2, -6.6, -4.3), []),                                   # bottom serif
    ]
    for x0 in (-3.4, -0.6):                                                  # the two strokes
        els.append((rect(x0, x0 + 1.2, 6.0, 8.8), []))
        els.append((rect(x0, x0 + 1.2, -8.8, -6.0), []))
    return els


def b_to_coin(p, scale=1.08, tilt=-14.0, shift=0.35):
    """B units -> coin mm: centred, tilted clockwise, the B's up mapped to -X, its right to +Y."""
    x, y = p[0] + shift, p[1]
    a = math.radians(tilt)
    x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
    return (-y * scale, x * scale)


def thick_line(pts, w):
    """A polyline of width w as a polygon (mitred joints)."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    left, right = [], []
    for i in range(n):
        d0 = (pts[i] - pts[i - 1]).normalized() if i > 0 else None
        d1 = (pts[i + 1] - pts[i]).normalized() if i < n - 1 else None
        d = (d0 + d1).normalized() if d0 is not None and d1 is not None else (d0 or d1)
        nrm = Vector((-d.y, d.x))
        miter = 1.0
        if d0 is not None and d1 is not None:
            miter = 1.0 / max(0.3, nrm.dot(Vector((-d0.y, d0.x))))
        left.append(tuple(pts[i] + nrm * (w / 2) * miter))
        right.append(tuple(pts[i] - nrm * (w / 2) * miter))
    return right + list(reversed(left))


def polar(r, deg):
    a = math.radians(deg)
    return (r * math.cos(a), r * math.sin(a))


def circuit():
    """Traces, pads and vias in the ring between the B and the rim, plus the thin outer ring."""
    els = []
    W = 0.30
    ring_in, ring_out = 16.95, 17.30
    els.append((circle(0, 0, ring_out, 100), [circle(0, 0, ring_in, 100)]))
    n = 20
    for i in range(n):
        a = 360.0 * i / n + 4.5
        kind = i % 4
        if kind == 0:      # pad near the B, out, jog, into the ring
            path = [polar(11.0, a), polar(12.8, a), polar(14.0, a + 4.5), polar(17.1, a + 4.5)]
            pads = [(path[0], False)]
        elif kind == 1:    # floating trace between two pads
            path = [polar(12.3, a), polar(14.2, a), polar(15.2, a - 4.0), polar(15.9, a - 4.0)]
            pads = [(path[0], False), (path[-1], True)]
        elif kind == 2:    # a via straight into the ring
            path = [polar(13.6, a), polar(17.1, a)]
            pads = [(path[0], True)]
        else:              # long trace with a jog, from a pad to a via
            path = [polar(10.9, a), polar(11.9, a), polar(12.8, a + 4.0), polar(15.0, a + 4.0)]
            pads = [(path[0], False), (path[-1], True)]
        els.append((thick_line(path, W), []))
        for (px, py), via in pads:
            if via:
                els.append((circle(px, py, 0.52, 8), [circle(px, py, 0.2, 6)]))
            else:
                els.append((circle(px, py, 0.45, 8), []))
    return els


# --------------------------------------------------------------------------- the face

def face(bm, field_ring):
    """Triangulate the field with the B and circuit outlines as constraints, then raise them."""
    verts, faces = [], []

    def add(poly):
        poly = ccw([(x * MM, y * MM) for x, y in poly])
        i0 = len(verts)
        verts.extend(poly)
        faces.append(list(range(i0, i0 + len(poly))))
        return len(faces) - 1

    # the field disc uses the body's own last ring, so the seam welds exactly
    disc = [(v.co.x / MM, v.co.y / MM) for v in field_ring]
    add(disc)
    layers = {"B": [], "T": []}
    for outline, holes in b_symbol():
        layers["B"].append((add([b_to_coin(p) for p in outline]), [add([b_to_coin(p) for p in h]) for h in holes]))
    for outline, holes in circuit():
        layers["T"].append((add(outline), [add(h) for h in holes]))

    out_v, _e, out_f, _ov, _oe, out_of = delaunay_2d_cdt(verts, [], faces, 0, 1e-9, True)
    z = FIELD_Z * MM
    bv = [bm.verts.new((x, y, z)) for x, y in out_v]
    groups = {"B": [], "T": [], "F": []}
    for f, orig in zip(out_f, out_of):
        o = set(orig)
        if 0 not in o:
            continue                            # outside the disc (there should be none)
        which = "F"
        for key in ("B", "T"):
            if any(sol in o and not (o & set(hs)) for sol, hs in layers[key]):
                which = key
                break
        groups[which].append(bm.faces.new([bv[i] for i in f]))
    # weld the disc rim onto the body's ring
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-7)

    raise_region(bm, groups["T"], TRACE_RELIEF * MM, fillet=0.0)
    raise_region(bm, groups["B"], B_RELIEF * MM, fillet=B_FILLET * MM)


def raise_region(bm, faces, h, fillet):
    faces = [f for f in faces if f.is_valid]
    ret = bmesh.ops.extrude_face_region(bm, geom=faces)
    top_verts = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
    top_faces = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMFace)]
    bmesh.ops.translate(bm, vec=(0, 0, h), verts=top_verts)
    bmesh.ops.delete(bm, geom=[f for f in faces if f.is_valid], context="FACES")
    if fillet <= 0:
        return
    top = set(top_faces)
    edges = set()
    for f in top_faces:
        for e in f.edges:
            if any(lf not in top for lf in e.link_faces):
                edges.add(e)                       # the relief's top edge
                for lf in e.link_faces:
                    if lf not in top:              # the wall: its bottom edge too
                        for e2 in lf.edges:
                            if e2 not in f.edges and abs(e2.verts[0].co.z - e2.verts[1].co.z) < 1e-9 \
                                    and e2.verts[0].co.z < FIELD_Z * MM + 1e-7:
                                edges.add(e2)
    bmesh.ops.bevel(bm, geom=list(edges), offset=fillet, offset_type="OFFSET", segments=2,
                    profile=0.5, affect="EDGES", clamp_overlap=True)


def coin_uvs(bm):
    uvl = bm.loops.layers.uv.new("UVMap")
    D = 2 * R * MM
    for f in bm.faces:
        if abs(f.normal.z) > 0.5:
            for loop in f.loops:
                co = loop.vert.co
                u = co.y / D + 0.5
                loop[uvl].uv = (u if f.normal.z > 0 else 1 - u, -co.x / D + 0.5)
        else:
            ths = [math.atan2(l.vert.co.y, l.vert.co.x) for l in f.loops]
            if max(ths) - min(ths) > math.pi:
                ths = [t + TAU if t < 0 else t for t in ths]
            for loop, th in zip(f.loops, ths):
                loop[uvl].uv = (th / TAU, loop.vert.co.z / D)


def gold_material():
    """Preview gold: a satin-polished field (a mirror field flares white on the shelf), frosted
    relief (read from the Relief colour attribute), faint wear in the roughness."""
    m = S.material("M_Gold", (0.70, 0.42, 0.12), 0.12, metallic=1.0)
    nt = m.node_tree
    b = M.principled(m)
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "Relief"
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 300.0
    nz.inputs["Detail"].default_value = 4.0
    wear = nt.nodes.new("ShaderNodeMapRange")
    wear.inputs["To Min"].default_value = 0.16
    wear.inputs["To Max"].default_value = 0.28
    nt.links.new(nz.outputs["Fac"], wear.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "FLOAT"
    nt.links.new(attr.outputs["Fac"], mix.inputs["Factor"])
    nt.links.new(wear.outputs["Result"], mix.inputs[2])
    mix.inputs[3].default_value = 0.45
    nt.links.new(mix.outputs[0], b.inputs["Roughness"])
    return m


def relief_colors(ob):
    """Colour attribute "Relief": white on the raised B, 40 % grey on the circuit, black
    elsewhere, so a material can frost the relief against a polished field (proof finish)."""
    me = ob.data
    ca = me.color_attributes.new("Relief", "BYTE_COLOR", "CORNER")
    top = (FIELD_Z + 0.02) * MM
    b_top = (FIELD_Z + 0.2) * MM
    for p in me.polygons:
        zmin = min(me.vertices[v].co.z for v in p.vertices)
        raised = zmin > top and p.center.length < FIELD_R * MM
        k = (1.0 if zmin > b_top else 0.4) if raised else 0.0   # the circuit only half-frosted
        c = (k, k, k, 1.0)
        for li in p.loop_indices:
            ca.data[li].color = c
    me.update()


def build_coin():
    """The coin as designed (40 mm), lying flat, face up (+Z), the B's top towards -X."""
    gold = gold_material()
    bm = bmesh.new()
    field_ring = body(bm)
    face(bm, field_ring)
    loose = [e for e in bm.edges if not e.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="EDGES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_edges], context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    coin_uvs(bm)
    return M.obj(bm, NAME + "_coin", [gold])


# ---- display (mm)
SCALE = 1.5                 # 40 mm design -> 60 mm display coin
BLOCK = (40.0, 80.0, 20.0)  # X (depth) x Y (width) x Z (height)
BLOCK_R = 1.5               # edge rounding
SLOT_W = 5.4                # coin is 4.8 thick
SLOT_L = 46.0
SLOT_D = 9.0                # depth along the slot axis
SLOT_X = 3.0                # slot centre (top surface), in front of the block centre
LEAN = 10.0                 # degrees back from vertical


def walnut():
    return F.wood("M_Walnut", (0.36, 0.225, 0.14), (0.16, 0.085, 0.045), roughness=0.5, ring=14.0, seed=0.7)


def axis():
    a = math.radians(LEAN)
    return Vector((-math.sin(a), 0.0, math.cos(a)))


def stand(mat):
    bx, by, bz = (v * MM for v in BLOCK)
    blk = S.box("stand", (-bx / 2, -by / 2, 0), (bx / 2, by / 2, bz), mat)
    bev = blk.modifiers.new("Bevel", "BEVEL")
    bev.width = BLOCK_R * MM
    bev.segments = 4
    bev.limit_method = "ANGLE"
    blk = M.bake(blk)
    ax = axis()
    top = Vector((SLOT_X * MM, 0, bz))
    p0 = top - ax * (SLOT_D * MM / ax.z)        # the floor, SLOT_D below the top along the slot
    p1 = top + ax * 6 * MM
    outline = S.rounded_rect(SLOT_W * MM, SLOT_L * MM, SLOT_W * MM / 2 * 0.999, segs=10)
    cutter = S.prism("slot", outline, p0, p1, mat, up=(1, 0, 0))
    boo = blk.modifiers.new("Slot", "BOOLEAN")
    boo.operation = "DIFFERENCE"
    boo.solver = "EXACT"
    boo.object = cutter
    blk = M.bake(blk)
    bpy.data.objects.remove(cutter, do_unlink=True)
    rim = blk.modifiers.new("SlotRim", "BEVEL")    # soften the slot's cut edges
    rim.width = 0.45 * MM
    rim.segments = 2
    rim.limit_method = "ANGLE"
    rim.angle_limit = math.radians(50)
    rim.harden_normals = False
    blk = M.bake(blk)
    bm = bmesh.new()
    bm.from_mesh(blk.data)
    M.box_uv(bm, grain=1)
    bm.to_mesh(blk.data)
    bm.free()
    return blk, p0


def build():
    coin = build_coin()
    relief_colors(coin)                         # in coin space, before it is moved
    blk, floor = stand(walnut())
    ax = axis()
    me = coin.data
    me.transform(Matrix.Translation((0, 0, -T / 2 * MM)))
    me.transform(Matrix.Scale(SCALE, 4))
    me.transform(Matrix.Rotation(math.radians(90 - LEAN), 4, "Y"))
    centre = floor + ax * (R * SCALE * MM + 0.05 * MM)
    me.transform(Matrix.Translation(centre))
    me.update()
    return [blk, coin]


def flat_normals(ob):
    """Custom normals: on the gold, faces square to the coin's axis (field, relief tops, rim
    tops) keep their own normal at every corner, so the fillets' smoothing cannot bleed across
    the long field triangles; the reeds, chamfers and fillets keep their smooth normals."""
    me = ob.data
    face_n = Matrix.Rotation(math.radians(90 - LEAN), 3, "Y") @ Vector((0, 0, 1))
    gold = [i for i, m in enumerate(me.materials) if m.name == "M_Gold"][0]
    normals = []
    for p in me.polygons:
        flat = p.material_index == gold and abs(p.normal.dot(face_n)) > 0.999
        for li in p.loop_indices:
            normals.append(tuple(p.normal) if flat else tuple(me.corner_normals[li].vector))
    me.normals_split_custom_set(normals)
    me.update()


if __name__ == "__main__":
    args = S.parse_args(__file__)
    S.reset_scene()
    lo, hi = Vector((-0.03, -0.042, 0.0)), Vector((0.03, 0.042, 0.075))
    M.finish(NAME, build(), args, origin=(0, 0, 0), sharp_angle=55, post=flat_normals, glossy=True, views=[
        ("", (1.0, 0.75, 0.85), 70, 1.12),
        ("_front", (1.0, 0.0, 0.10), 70, 1.12),
        ("_close", (1.0, 0.25, 0.35), 100, 1.05, (Vector((-0.012, -0.032, 0.012)), Vector((0.012, 0.032, 0.072)))),
    ])
