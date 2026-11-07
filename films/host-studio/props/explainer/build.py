"""The explainer props, textured: a podcast lounge chair, a small walnut desk, a broadcast dynamic mic on a desk boom
arm (posed for the explainer set, with its cable) and a snake plant in a ceramic pot. Original designs, no marks.

Each asset: one mesh with PBR material slots (_pbr.py's drawn 2K sets), UV0 world-scale tiled + UV1 lightmap,
UCX_ convex collision, pivot at its base, FBX in cm; plus a 3/4 preview render, and one render of the whole set as
the explainer layout places it. Writes <out>/fbx, <out>/textures, <out>/preview, <out>/props.json.

    blender -b --factory-startup -t 6 -P films/host-studio/props/explainer/build.py -- --out /srv/ue/props_r6/out

Layout (agent-07's studio frame, Unreal cm; presenter faces +X): chair at (20, -20, 0) yaw 0; desk centre
(78, -20, 0) yaw 0 (110 along Y, 55 along X, top z 74); mic clamp on the desk's +Y edge at MIC_CLAMP_UE, yaw -90
(the asset's +X, into the desk, is the set's -Y), capsule front at MIC_CAPSULE_UE aimed at MOUTH_UE.
"""
import argparse
import math
import os
import sys
import time

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import _pbr as P  # noqa: E402
import _studio as S  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--samples", type=int, default=128)
ap.add_argument("--res", type=int, default=1400)
ap.add_argument("--only", default="", help="comma list of assets (chair,desk,mic,plant)")
ap.add_argument("--no-render", action="store_true")
ap.add_argument("--tex-size", type=int, default=P.N)
args = ap.parse_args(argv)

MIC_CLAMP_UE = Vector((70.0, 32.6, 74.0))     # clamp origin; the desk's +Y edge is at y 35, the clamp spine outside it
MIC_CAPSULE_UE = Vector((44.0, -6.0, 99.0))   # front of the grille
MOUTH_UE = Vector((32.0, -20.0, 113.0))
CHAIR_UE = Vector((20.0, -20.0, 0.0))
DESK_UE = Vector((78.0, -20.0, 0.0))

X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def ue_to_mic_local(p_ue):
    """A set point (UE cm) -> the mic asset's Blender-local metres (clamp at origin, actor yaw -90)."""
    d = (Vector(p_ue) - MIC_CLAMP_UE) / 100.0
    return Vector((-d.y, -d.x, d.z))


def rot_about_z(ob, angle, pivot=(0, 0, 0)):
    pv = Vector(pivot)
    m = Matrix.Translation(pv) @ Matrix.Rotation(angle, 4, "Z") @ Matrix.Translation(-pv)
    ob.data.transform(m)
    return ob


def subsurf(ob, levels=1):
    mod = ob.modifiers.new("Subsurf", "SUBSURF")
    mod.levels = mod.render_levels = levels
    return ob


def bevel(ob, width, segments=3, angle=35):
    return S.bevel(ob, width, segments=segments, angle=angle)


def mesh_from(name, verts, faces, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.validate()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def wall_sweep(name, path, sec_w, z_lo, z_top, mat, corner=0.03, ring=20, recline=None):
    """An upholstered wall: at each plan sample (point, outward normal) a rounded-rect section `sec_w` thick from
    z_lo(i) to z_top(i); recline(i, z) shifts a point back along -X. Ends capped."""
    verts, faces, rings = [], [], []
    for i, (p, n) in enumerate(path):
        h = z_top(i) - z_lo(i)
        sec = S.rounded_rect(sec_w, h, min(corner, h / 2 - 1e-4, sec_w / 2 - 1e-4), segs=max(2, ring // 4 - 1))
        zc = (z_top(i) + z_lo(i)) / 2
        ids = []
        for a, b in sec:
            z = zc + b
            q = Vector((p.x, p.y, 0)) + n * a
            if recline is not None:
                q.x -= recline(i, z)
            ids.append(len(verts))
            verts.append((q.x, q.y, z))
        rings.append(ids)
    m = len(rings[0])
    for i in range(len(rings) - 1):
        a, c = rings[i], rings[i + 1]
        for k in range(m):
            k2 = (k + 1) % m
            faces.append((a[k], a[k2], c[k2], c[k]))
    faces.append(tuple(reversed(rings[0])))
    faces.append(tuple(rings[-1]))
    ob = mesh_from(name, verts, faces, mat)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def beam(name, p0, p1, w0, h0, w1, h1, mat):
    """A tapered rectangular beam from p0 to p1 (horizontal-ish), widths across in the XY plane, heights in Z."""
    p0, p1 = Vector(p0), Vector(p1)
    d = (p1 - p0)
    side = Vector((-d.y, d.x, 0)).normalized()
    verts = []
    for p, w, h in ((p0, w0, h0), (p1, w1, h1)):
        for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append(p + side * (w / 2) * sx + Z * (h / 2) * sz)
    faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    ob = mesh_from(name, verts, faces, mat)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


# =========================================================================== chair

def build_chair(M):
    """Modern swivel lounge chair: an upholstered tub (back wrapping into the arms), a loose seat cushion and back
    pillow, a powder-black seat pan and tilt block, a brushed-aluminium 5-star base on rubber glides."""
    parts = []
    SEAT_TOP, ARM_TOP, BACK_TOP, TUB_LO = 0.45, 0.63, 0.86, 0.36
    R_OUT, HALF_T = 0.30, 0.045                     # tub path radius / half thickness
    ARM_FRONT, ARC_C = 0.22, -0.05

    # plan path: right arm front -> back arc -> left arm front, with outward normals; s = signed angle from the rear
    path, ang = [], []
    for k in range(10):                            # right arm (y = -R), front to back
        x = ARM_FRONT + (ARC_C - ARM_FRONT) * k / 10
        path.append((Vector((x, -R_OUT, 0)), Vector((0, -1, 0))))
        ang.append(-math.pi / 2)
    for k in range(41):                            # rear arc, from -90 deg (right) to +90 deg (left)
        a = -math.pi / 2 + math.pi * k / 40
        n = Vector((-math.cos(a), math.sin(a), 0))
        path.append((Vector((ARC_C, 0, 0)) + n * R_OUT, n))
        ang.append(a)
    for k in range(1, 11):                         # left arm, back to front
        x = ARC_C + (ARM_FRONT - ARC_C) * k / 10
        path.append((Vector((x, R_OUT, 0)), Vector((0, 1, 0))))
        ang.append(math.pi / 2)

    def top(i):
        c = max(0.0, math.cos(ang[i]))
        t = ARM_TOP + (BACK_TOP - ARM_TOP) * c ** 1.6
        if abs(ang[i]) >= math.pi / 2 - 1e-6:     # arms: a slight fall to the front
            x = path[i][0].x
            t -= 0.02 * max(0.0, (x - ARC_C) / (ARM_FRONT - ARC_C))
        return t

    def recline(i, z):
        return max(0.0, math.cos(ang[i])) * max(0.0, z - 0.40) * math.tan(math.radians(9))

    tub = wall_sweep("tub", path, 2 * HALF_T, lambda i: TUB_LO, top, M["ChairFabric"], corner=0.035, ring=24,
                     recline=recline)
    parts.append(subsurf(tub, 2))

    # back pillow inside the rear arc
    pil, pang = [], []
    R_P = R_OUT - HALF_T - 0.034
    for k in range(25):
        a = math.radians(-62 + 124 * k / 24)
        n = Vector((-math.cos(a), math.sin(a), 0))
        pil.append((Vector((ARC_C, 0, 0)) + n * R_P, n))
        pang.append(a)
    pillow = wall_sweep("pillow", pil, 0.068, lambda i: SEAT_TOP - 0.005,
                        lambda i: 0.80 - 0.05 * (1 - math.cos(pang[i])) * 2.2, M["ChairFabric"], corner=0.03, ring=20,
                        recline=lambda i, z: math.cos(pang[i]) * max(0.0, z - 0.40) * math.tan(math.radians(9)))
    parts.append(subsurf(pillow, 2))

    # seat cushion: D-shaped plan (straight front, rear following the tub's inner arc)
    R_IN = R_OUT - HALF_T
    outline = []
    for k in range(25):
        a = -math.pi / 2 + math.pi * k / 24
        outline.append((ARC_C - R_IN * math.cos(a) * 0.995, -R_IN * math.sin(a) * 0.995))
    outline = outline[::-1]
    fr = 0.05
    for cx, cy, a0 in ((0.245 - fr, R_IN - fr - 0.002, 90), (0.245 - fr, -R_IN + fr + 0.002, 0)):
        pts = [(cx + fr * math.cos(math.radians(a0 - 90 * j / 6)), cy + fr * math.sin(math.radians(a0 - 90 * j / 6)))
               for j in range(7)]
        outline += pts
    bm = bmesh.new()
    lo_ring = [bm.verts.new((x, y, TUB_LO - 0.005)) for x, y in outline]
    hi_ring = [bm.verts.new((x, y, SEAT_TOP - 0.008)) for x, y in outline]
    n = len(outline)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo_ring[i], lo_ring[j], hi_ring[j], hi_ring[i]))
    bm.faces.new(list(reversed(lo_ring)))
    bm.faces.new(hi_ring)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    cushion = S.obj_from_bm(bm, "cushion", M["ChairFabric"])
    bevel(cushion, 0.028, segments=4, angle=30)
    parts.append(subsurf(cushion, 1))

    # seat pan and tilt block
    pan = S.prism("pan", S.rounded_rect(0.50, 0.52, 0.08, 4), (ARC_C + 0.03, 0, TUB_LO - 0.025), (ARC_C + 0.03, 0, TUB_LO),
                  M["PowderBlack"], up=(1, 0, 0))
    parts.append(bevel(pan, 0.006, 2))
    block = S.box("tilt_block", (-0.13, -0.09, 0.285), (0.09, 0.09, TUB_LO - 0.025), M["PowderBlack"])
    parts.append(bevel(block, 0.008, 3))
    parts.append(S.cylinder("lever", (0.0, -0.09, 0.305), (0.0, -0.20, 0.300), 0.006, M["PowderBlack"], segs=16))
    parts.append(S.lathe("lever_knob", [(0, -0.012), (0.011, -0.01), (0.012, 0.0), (0.011, 0.012), (0, 0.016)],
                         [M["Rubber"]], segs=24, matrix=Matrix.Translation((0.0, -0.212, 0.300)) @
                         Matrix.Rotation(math.radians(90), 4, "X")))

    # gas lift: black shroud + steel piston
    parts.append(S.cylinder("shroud", (0, 0, 0.10), (0, 0, 0.215), 0.029, M["PowderBlack"], segs=40))
    parts.append(S.cylinder("piston", (0, 0, 0.21), (0, 0, 0.29), 0.0145, M["Steel"], segs=32))

    # 5-star base, a leg straight forward (+X) and the hub
    parts.append(S.lathe("hub", [(0, 0.055), (0.040, 0.055), (0.046, 0.062), (0.046, 0.098), (0.040, 0.112),
                                 (0.030, 0.115), (0, 0.115)], [M["BrushedAlu"]], segs=48))
    glide = []
    for k in range(5):
        a = 2 * math.pi * k / 5
        dvec = Vector((math.cos(a), math.sin(a), 0))
        leg = beam(f"leg{k}", dvec * 0.03 + Z * 0.083, dvec * 0.325 + Z * 0.046, 0.058, 0.052, 0.040, 0.028,
                   M["BrushedAlu"])
        parts.append(subsurf(bevel(leg, 0.009, 3, angle=30), 1))
        tip = dvec * 0.31
        parts.append(S.lathe(f"glide{k}", [(0, 0.0), (0.018, 0.0), (0.024, 0.004), (0.026, 0.012), (0.024, 0.026),
                                            (0.017, 0.034), (0, 0.034)], [M["Rubber"]], segs=32,
                             matrix=Matrix.Translation((tip.x, tip.y, 0))))
        glide.append(tip)

    ob = S.join("SM_PodcastChair", parts)
    hulls = [P.cyl_pts((0, 0), 0.335, 0.0, 0.115, 10),
             P.cyl_pts((0, 0), 0.03, 0.10, TUB_LO),
             P.box_pts((ARC_C - R_OUT - HALF_T - 0.06, -R_OUT - HALF_T, TUB_LO - 0.03),
                       (ARM_FRONT + HALF_T, R_OUT + HALF_T, ARM_TOP)),
             P.box_pts((ARC_C - R_OUT - HALF_T - 0.08, -0.26, ARM_TOP), (ARC_C - 0.12, 0.26, BACK_TOP))]
    info = {"origin": "floor, centre under the seat (the swivel axis)", "faces": "+X",
            "seat_top_cm": round(SEAT_TOP * 100, 1), "seat_front_edge_x_cm": 24.5,
            "seat_rear_x_cm": round((ARC_C - R_IN) * 100, 1),
            "armrest_top_cm": ARM_TOP * 100, "armrest_inner_y_cm": round(R_IN * 100, 1),
            "armrest_outer_y_cm": round((R_OUT + HALF_T) * 100, 1), "armrest_front_x_cm": round((ARM_FRONT + HALF_T) * 100, 1),
            "back_top_cm": BACK_TOP * 100, "back_recline_deg": 9}
    return ob, hulls, [], info


# =========================================================================== desk

def build_desk(M):
    """A small mid-century walnut desk: 110 x 55 cm top 3 cm thick with an undercut edge, a 7 cm apron, four round
    tapered legs splayed 5 deg, black glides."""
    parts = []
    W, D, TOP, TH = 1.10, 0.55, 0.74, 0.03
    top = S.prism("top", S.rounded_rect(D, W, 0.012, 4), (0, 0, TOP - TH), (0, 0, TOP), M["Walnut"], up=(1, 0, 0))
    bevel(top, 0.004, 3, angle=50)
    parts.append(top)
    lip = S.prism("top_under", S.rounded_rect(D - 0.03, W - 0.03, 0.01, 3), (0, 0, TOP - TH - 0.006), (0, 0, TOP - TH + 0.001),
                  M["Walnut"], up=(1, 0, 0))
    parts.append(lip)
    ap_h, ap_t, inset = 0.07, 0.022, 0.06
    ax, ay = D / 2 - inset, W / 2 - inset
    z1 = TOP - TH - 0.006
    aprons = [S.box("apron_f", (ax - ap_t, -ay, z1 - ap_h), (ax, ay, z1), M["Walnut"]),
              S.box("apron_b", (-ax, -ay, z1 - ap_h), (-ax + ap_t, ay, z1), M["Walnut"]),
              S.box("apron_l", (-ax + ap_t, ay - ap_t, z1 - ap_h), (ax - ap_t, ay, z1), M["Walnut"]),
              S.box("apron_r", (-ax + ap_t, -ay, z1 - ap_h), (ax - ap_t, -ay + ap_t, z1), M["Walnut"])]
    for a in aprons:
        bevel(a, 0.002, 2)
    parts += aprons
    legs, hulls = [], []
    for sx in (-1, 1):
        for sy in (-1, 1):
            t = Vector((sx * (ax - 0.03), sy * (ay - 0.035), z1 - 0.005))
            b = Vector((sx * (ax - 0.03 + 0.055), sy * (ay - 0.035 + 0.055), 0.008))
            leg = S.cylinder(f"leg{sx}{sy}", b, t, 0.0145, M["Walnut"], segs=32, r2=0.025)
            P.uv_grain_box(leg, 2, P.TILE_M["Walnut"])
            legs.append(leg)
            parts.append(S.lathe(f"foot{sx}{sy}", [(0, 0), (0.013, 0), (0.0145, 0.003), (0.0145, 0.009), (0, 0.009)],
                                 [M["Rubber"]], segs=24, matrix=Matrix.Translation((b.x, b.y, 0))))
            hulls.append(P.cyl_pts((b.x, b.y), 0.016, 0.0, 0.01, 8) + P.cyl_pts((t.x, t.y), 0.026, t.z - 0.01, t.z, 8))
    # UVs on the walnut parts, grain along each part's length, before the bevels are applied
    baked = []
    for p in parts:
        if p.data.materials[0] == M["Walnut"] and p not in legs:
            bp = S._bake(p)
            dims = [max(v.co[i] for v in bp.data.vertices) - min(v.co[i] for v in bp.data.vertices) for i in range(3)]
            P.uv_grain_box(bp, max(range(3), key=lambda i: dims[i]), P.TILE_M["Walnut"])
            baked.append(bp)
        else:
            baked.append(p)
    ob = S.join("SM_WalnutDesk", baked)
    hulls = [P.box_pts((-D / 2, -W / 2, TOP - TH - 0.006 - ap_h), (D / 2, W / 2, TOP))] + hulls
    info = {"origin": "floor, centre of the top", "faces": "+X (long side along Y)", "top_cm": [W * 100, D * 100],
            "top_height_cm": TOP * 100, "top_thickness_cm": TH * 100, "apron_underside_cm": round((z1 - ap_h) * 100, 1),
            "knee_clearance_cm": round((z1 - ap_h) * 100, 1)}
    return ob, hulls, [], info


# =========================================================================== mic on boom

def build_mic(M):
    """Broadcast dynamic mic (end-address, woven-wire grille, no marks) in a U yoke, on a two-section spring boom
    on a desk clamp, posed from the set's numbers; the XLR cable runs along the arm and off the desk edge.
    Origin: the clamp, on the desk surface (z 0 = desk top); the desk is on +X, the clamp spine on -X."""
    parts = []
    BLK, ALU, STL, RUB, GRL = M["PowderBlack"], M["BrushedAlu"], M["Steel"], M["Rubber"], M["Grille"]
    nose = ue_to_mic_local(MIC_CAPSULE_UE)
    mouth = ue_to_mic_local(MOUTH_UE)
    D = (mouth - nose).normalized()
    NOSE_L = 0.106                                   # grille front ahead of the mic's pivot
    MIC_C = nose - D * NOSE_L
    YOKE_TOP = 0.060
    J0 = Vector((0, 0, 0.165))
    J2 = MIC_C + Z * (YOKE_TOP + 0.048)
    L1 = L2 = 0.31
    horiz = Vector((J2.x, J2.y, 0))
    psi = math.atan2(J2.y, J2.x)
    J2c = Vector((horiz.length, 0, J2.z))
    d = J2c - J0
    dist = d.length
    if dist > L1 + L2 - 0.02:
        raise SystemExit(f"mic pose out of reach: {dist:.3f} m")
    a = (L1 * L1 - L2 * L2 + dist * dist) / (2 * dist)
    h = math.sqrt(L1 * L1 - a * a)
    u = d.normalized()
    perp = Vector((-u.z, 0.0, u.x))
    if perp.z < 0:
        perp = -perp
    J1c = J0 + u * a + perp * h

    # ---- clamp (fixed, not yawed)
    cl = [S.box("clamp_top", (-0.036, -0.025, 0.0), (0.046, 0.025, 0.012), BLK),
          S.box("clamp_spine", (-0.036, -0.022, -0.064), (-0.024, 0.022, 0.010), BLK),
          S.box("clamp_low", (-0.030, -0.0215, -0.0635), (0.036, 0.0215, -0.053), BLK)]
    for b in cl:
        bevel(b, 0.0025, 2)
    parts += cl
    parts.append(S.box("clamp_pad_top", (-0.022, -0.023, -0.003), (0.044, 0.023, 0.0), RUB))
    parts.append(S.cylinder("clamp_screw", (0.020, 0, -0.092), (0.020, 0, -0.042), 0.0045, STL, segs=16))
    parts.append(S.cylinder("clamp_pad", (0.020, 0, -0.045), (0.020, 0, -0.040), 0.013, RUB, segs=24))
    parts.append(S.prism("clamp_handle", S.knurl_outline(0.017, teeth=14, depth=0.12),
                         (0.020, 0, -0.100), (0.020, 0, -0.088), RUB))
    parts.append(S.cylinder("mast_collar", (0, 0, 0.012), (0, 0, 0.034), 0.016, BLK, segs=32))
    parts.append(S.cylinder("mast", (0, 0, 0.030), J0, 0.0105, BLK, segs=24))

    # ---- arm, built in the XZ plane then yawed by psi
    arm = [S.cylinder("mast_head", J0 - Z * 0.03, J0, 0.0135, BLK, segs=24)]
    HUB_R, HUB_W = 0.017, 0.017

    def joint(name, p):
        out = [S.cylinder(name + "_hub", p - Y * HUB_W, p + Y * HUB_W, HUB_R, BLK, segs=32)]
        out.append(S.cylinder(name + "_stem", p + Y * HUB_W, p + Y * (HUB_W + 0.006), 0.005, STL, segs=12))
        out.append(S.prism(name + "_knob", S.knurl_outline(0.0155, teeth=18, depth=0.07),
                           p + Y * (HUB_W + 0.005), p + Y * (HUB_W + 0.018), RUB))
        out.append(S.cylinder(name + "_nut", p - Y * HUB_W, p - Y * (HUB_W + 0.005), 0.010, STL, segs=6))
        return out

    for name, p in (("j0", J0), ("j1", J1c), ("j2", J2c)):
        arm += joint(name, p)
    TUBE_R, TUBE_OFF = 0.0055, 0.011
    SPRING_Y, COIL_R, WIRE_R, PITCH = 0.027, 0.0058, 0.0011, 0.0042

    def section(name, pa, pb):
        out = []
        dd = (pb - pa).normalized()
        nn = Vector((-dd.z, 0.0, dd.x))
        for s in (-1, 1):
            out.append(S.cylinder(f"{name}_tube{s}", pa + nn * TUBE_OFF * s, pb + nn * TUBE_OFF * s, TUBE_R, BLK, segs=16))
        length = (pb - pa).length
        pin_a, pin_b = pa + dd * 0.035, pb - dd * 0.035
        for pin in (pin_a, pin_b):
            out.append(S.cylinder(f"{name}_pin", pin - Y * (SPRING_Y + 0.006), pin + Y * (SPRING_Y + 0.006), 0.0024,
                                  STL, segs=10))
        sa, sb = pa + dd * 0.12 * length, pb - dd * 0.12 * length
        turns = (sb - sa).length / PITCH
        steps = int(turns * 10)
        e2 = dd.cross(Y)
        for side in (-1, 1):
            off = Y * SPRING_Y * side
            coil = [sa + (sb - sa) * (i / steps) + off + (Y * math.cos(2 * math.pi * turns * i / steps)
                                                          + e2 * math.sin(2 * math.pi * turns * i / steps)) * COIL_R
                    for i in range(steps + 1)]
            pth = [pin_a + off, sa + off - dd * 0.004] + coil + [sb + off + dd * 0.004, pin_b + off]
            out.append(S.sweep(f"{name}_spring{side}", pth, S.circle_outline(WIRE_R, 6), STL, hint=Y))
        return out

    arm += section("arm1", J0, J1c)
    arm += section("arm2", J1c, J2c)
    for o in arm:
        rot_about_z(o, psi)
    parts += arm
    J1 = Matrix.Rotation(psi, 3, "Z") @ J1c

    # ---- drop rod and swivel (vertical, at J2)
    yoke_top = MIC_C + Z * YOKE_TOP
    parts.append(S.cylinder("drop_rod", J2, yoke_top + Z * 0.008, 0.0048, STL, segs=16))
    parts.append(S.cylinder("swivel", J2 - Z * 0.034, J2 - Z * 0.022, 0.0095, BLK, segs=24))
    parts.append(S.cylinder("yoke_mount", yoke_top - Z * 0.002, yoke_top + Z * 0.010, 0.0085, BLK, segs=24))

    # ---- yoke + mic, built pointing +X (pitched by theta) at MIC_C, then yawed by phi about the drop rod
    phi = math.atan2(D.y, D.x)
    theta = math.atan2(D.z, math.hypot(D.x, D.y))
    DIRc = Vector((math.cos(theta), 0, math.sin(theta)))
    ym = []
    ARM_Y, CR = 0.041, 0.018
    pts = []
    for k in range(5):
        pts.append((-ARM_Y, -0.006 + (YOKE_TOP - CR + 0.006) * k / 4))
    for k in range(1, 9):
        a_ = math.pi - (math.pi / 2) * k / 8
        pts.append((-ARM_Y + CR + CR * math.cos(a_), YOKE_TOP - CR + CR * math.sin(a_)))
    pts += [(-ARM_Y + CR + 0.01, YOKE_TOP), (ARM_Y - CR - 0.01, YOKE_TOP)]
    for k in range(8):
        a_ = (math.pi / 2) - (math.pi / 2) * k / 8
        pts.append((ARM_Y - CR + CR * math.cos(a_), YOKE_TOP - CR + CR * math.sin(a_)))
    for k in range(5):
        pts.append((ARM_Y, YOKE_TOP - CR - (YOKE_TOP - CR + 0.006) * k / 4))
    strap = []
    for k in range(16):
        t = 2 * math.pi * k / 16
        c, s_ = math.cos(t), math.sin(t)
        strap.append((0.007 * math.copysign(abs(c) ** 0.5, c), 0.0022 * math.copysign(abs(s_) ** 0.5, s_)))
    ym.append(S.sweep("yoke", [MIC_C + Vector((0, y, z)) for (y, z) in pts], strap, BLK, hint=X))
    for side in (-1, 1):
        ym.append(S.cylinder(f"yoke_spacer{side}", MIC_C + Y * 0.027 * side, MIC_C + Y * (ARM_Y + 0.001) * side,
                             0.0065, STL, segs=16))
        ym.append(S.prism(f"yoke_knob{side}", S.knurl_outline(0.0125, teeth=10, depth=0.15),
                          MIC_C + Y * (ARM_Y + 0.002) * side, MIC_C + Y * (ARM_Y + 0.015) * side, RUB))
    mic_m = Matrix.Translation(MIC_C) @ DIRc.to_track_quat("Z", "Y").to_matrix().to_4x4()
    ym.append(S.lathe("mic_body", [(0.0, -0.090), (0.0265, -0.090), (0.0292, -0.087), (0.0300, -0.082),
                                   (0.0300, 0.022), (0.0292, 0.027), (0.0, 0.027)], [BLK], segs=64, matrix=mic_m))
    ym.append(S.lathe("mic_endcap", [(0.0, -0.0955), (0.0255, -0.0955), (0.0292, -0.0935), (0.0303, -0.0905),
                                     (0.0303, -0.0840), (0.0296, -0.0835), (0.0, -0.0835)], [ALU], segs=64, matrix=mic_m))
    ym.append(S.lathe("mic_xlr", [(0.0, -0.0975), (0.0108, -0.0975), (0.0112, -0.0952), (0.0, -0.0952)], [RUB],
                      segs=32, matrix=mic_m))
    ym.append(S.lathe("mic_trim", [(0.0, 0.020), (0.0308, 0.020), (0.0312, 0.023), (0.0312, 0.031),
                                   (0.0306, 0.033), (0.0, 0.033)], [ALU], segs=64, matrix=mic_m))
    grille = [(0.0, 0.031), (0.0302, 0.031), (0.0305, 0.040), (0.0305, 0.074), (0.0300, 0.084), (0.0285, 0.092),
              (0.0258, 0.098), (0.0215, 0.1025), (0.0155, 0.1050), (0.0080, 0.1058), (0.0, 0.106)]
    ym.append(S.lathe("mic_grille", grille, [GRL], segs=64, matrix=mic_m))
    ym.append(S.lathe("mic_grille_ring", [(0.0, 0.0545), (0.0309, 0.0545), (0.0311, 0.0565), (0.0309, 0.0585),
                                          (0.0, 0.0585)], [ALU], segs=64, matrix=mic_m))
    # XLR plug + strain relief behind the mic
    rear = MIC_C - DIRc * 0.0975
    ym.append(S.cylinder("xlr_plug", rear, rear - DIRc * 0.042, 0.0098, STL, segs=24))
    ym.append(S.cylinder("xlr_boot", rear - DIRc * 0.042, rear - DIRc * 0.068, 0.0085, RUB, segs=24, r2=0.0045))
    for o in ym:
        rot_about_z(o, phi - 0.0, pivot=MIC_C)
    parts += ym
    Rphi = Matrix.Rotation(phi, 3, "Z")
    plug_end = MIC_C + Rphi @ ((rear - DIRc * 0.068) - MIC_C)
    plug_dir = Rphi @ (-DIRc)

    # ---- cable: plug -> sag -> along arm2 / arm1 on the outer side -> down the mast -> over the clamp -> off the desk
    side = Matrix.Rotation(psi, 3, "Z") @ Vector((0, -0.036, 0))       # the knob-free side of the arm
    Jc0, Jc1, Jc2 = J0, J1, J2

    def along(p, q, t, sag):
        return p + (q - p) * t + side - Z * sag

    ctrl = [plug_end, plug_end + plug_dir * 0.025 - Z * 0.03,
            (plug_end + Jc2) / 2 - Z * 0.085 + side * 0.5,
            Jc2 + side - Z * 0.02,
            along(Jc2, Jc1, 0.33, 0.016), along(Jc2, Jc1, 0.66, 0.014), Jc1 + side * 1.1 - Z * 0.012,
            along(Jc1, Jc0, 0.33, 0.016), along(Jc1, Jc0, 0.66, 0.014),
            Jc0 + side * 0.9 - Z * 0.035, Vector((0, 0, 0.09)) + side * 0.7, Vector((-0.005, 0, 0.03)) + side * 0.8,
            Vector((-0.045, side.y * 0.6, 0.004)), Vector((-0.07, side.y * 0.5, -0.04)), Vector((-0.075, side.y * 0.4, -0.30))]
    cable = S.sweep("cable", S.catmull_rom(ctrl, per_seg=14), S.circle_outline(0.0032, 10), RUB, hint=Z)
    parts.append(cable)

    ob = S.join("SM_MicBoom", parts)
    hulls = [P.box_pts((-0.037, -0.026, -0.10), (0.047, 0.026, 0.035)),
             P.cyl_pts((0, 0), 0.017, 0.03, J0.z)]
    for pa, pb in ((J0, J1), (J1, J2)):
        hulls.append([pa + v for v in P.box_pts((-0.02, -0.02, -0.02), (0.02, 0.02, 0.02))]
                     + [pb + v for v in P.box_pts((-0.02, -0.02, -0.02), (0.02, 0.02, 0.02))])
    hulls.append([MIC_C + Rphi @ (DIRc * ax + Vector((0, sy, sz))) for ax in (-0.10, 0.106)
                  for sy in (-0.045, 0.045) for sz in (-0.032, 0.032)] + [yoke_top, J2])
    socks = [P.socket("Capsule", nose, D), P.socket("MicCentre", MIC_C, D)]
    to_ue = lambda v: [round(MIC_CLAMP_UE.x + (-v.y) * 100, 1), round(MIC_CLAMP_UE.y + (-v.x) * 100, 1),
                       round(MIC_CLAMP_UE.z + v.z * 100, 1)]
    info = {"origin": "the clamp on the desk surface (z 0 = desk top); clamp spine at local -X, the desk on +X",
            "placement_ue": {"location": [MIC_CLAMP_UE.x, MIC_CLAMP_UE.y, MIC_CLAMP_UE.z], "yaw": -90},
            "posed": True, "sockets": ["SOCKET_Capsule (+X = the mic's aim)", "SOCKET_MicCentre"],
            "capsule_set_cm": to_ue(nose), "aim_target_set_cm": [MOUTH_UE.x, MOUTH_UE.y, MOUTH_UE.z],
            "elbow_set_cm": to_ue(J1), "arm_tip_set_cm": to_ue(J2),
            "cable": "hangs 30 cm below the desk top behind the clamp; trim in shot if needed"}
    log(f"mic: nose {tuple(round(c*100,1) for c in nose)} cm local, dist J0-J2 {dist*100:.1f}, elbow set {info['elbow_set_cm']}")
    return ob, hulls, socks, info


# =========================================================================== plant

def build_plant(M):
    """A snake plant (sansevieria): eight banded blades in a satin off-white stoneware pot, 12 cm across."""
    import random
    rnd = random.Random(7)
    parts = []
    pot = [(0.0, 0.0), (0.050, 0.0), (0.054, 0.002), (0.056, 0.006), (0.0605, 0.060), (0.0635, 0.118),
           (0.0640, 0.123), (0.0625, 0.126), (0.0575, 0.126), (0.0565, 0.122), (0.0535, 0.060), (0.047, 0.012),
           (0.0, 0.012)]
    parts.append(S.lathe("pot", pot, [M["Ceramic"]], segs=72))
    parts.append(S.lathe("soil", [(0.0, 0.108), (0.0560, 0.108), (0.0566, 0.104), (0.0, 0.104)], [M["Soil"]], segs=48))
    leaves = []
    for i in range(8):
        a = 2 * math.pi * i / 8 + rnd.uniform(-0.3, 0.3)
        rr = rnd.uniform(0.008, 0.026)
        base = Vector((rr * math.cos(a), rr * math.sin(a), 0.095))
        L = rnd.uniform(0.24, 0.40)
        W = rnd.uniform(0.032, 0.046)
        lean = rnd.uniform(0.08, 0.22) * (0.6 + rr / 0.026 * 0.4)
        twist = rnd.uniform(-0.6, 0.6)
        face = a + rnd.uniform(-0.8, 0.8)
        NL, NW = 28, 6
        verts, uvs = [], []
        for j in range(NL + 1):
            t = j / NL
            if t < 0.85:
                w = W * max(math.sin(math.pi * t), 0.55) ** 0.5
            else:
                w = W * math.sin(math.pi * 0.85) ** 0.5 * (1 - (t - 0.85) / 0.15) + 0.0004
            ctr = base + Vector((math.cos(a), math.sin(a), 0)) * (lean * L * t * t) + Z * (L * t)
            ang = face + twist * t
            across = Vector((-math.sin(ang), math.cos(ang), 0))
            fold = Vector((math.cos(ang), math.sin(ang), 0))
            for k in range(NW + 1):
                s = k / NW * 2 - 1
                verts.append(ctr + across * (s * w / 2) + fold * (0.18 * w * (1 - s * s) - 0.08 * w))
                uvs.append((0.5 + s * w / 2 / P.TILE_M["Leaf"] + i * 0.37, (L * t) / P.TILE_M["Leaf"] + i * 0.21))
        faces = [(j * (NW + 1) + k, j * (NW + 1) + k + 1, (j + 1) * (NW + 1) + k + 1, (j + 1) * (NW + 1) + k)
                 for j in range(NL) for k in range(NW)]
        ob = mesh_from(f"leaf{i}", verts, faces, M["Leaf"])
        uvl = ob.data.uv_layers.new(name="UVMap")
        for poly in ob.data.polygons:
            for li in poly.loop_indices:
                uvl.data[li].uv = uvs[ob.data.loops[li].vertex_index]
        sol = ob.modifiers.new("Solid", "SOLIDIFY")
        sol.thickness = 0.0025
        sol.offset = 0.0
        subsurf(ob, 1)
        leaves.append(ob)
    parts += leaves
    ob = S.join("SM_DeskPlant", parts)
    hulls = [P.cyl_pts((0, 0), 0.064, 0.0, 0.126, 12)]
    info = {"origin": "bottom centre of the pot", "pot_diameter_cm": 12.8, "pot_height_cm": 12.6}
    return ob, hulls, [], info


# =========================================================================== previews

def preview_stage(lo, hi, view_dir, path, lens=55, res=None, aim=None, margin=1.08, key_side=1.0, aspect=(1, 1)):
    sc = bpy.context.scene
    for o in [o for o in bpy.data.objects if o.name.startswith("_pv")]:
        bpy.data.objects.remove(o, do_unlink=True)
    centre = (lo + hi) / 2 if aim is None else aim
    size = max((hi - lo).length, 0.3)
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.035, 0.033, 0.032, 1)
    bg.inputs["Strength"].default_value = 1.0
    fm = bpy.data.materials.get("_pvFloor") or S.material("_pvFloor", (0.10, 0.095, 0.09), 0.75)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size * 15, matrix=Matrix.Translation((centre.x, centre.y, min(lo.z, 0.0) - 0.0004)))
    S.obj_from_bm(bm, "_pvfloor", fm)
    v = Vector(view_dir).normalized()
    side = v.cross(Z).normalized()

    def area(name, direction, power, scale, color=(1, 1, 1)):
        light = bpy.data.lights.new(name, "AREA")
        light.shape = "DISK"
        light.size = size * scale
        light.energy = power * size * size
        light.color = color
        lo_ = bpy.data.objects.new(name, light)
        sc.collection.objects.link(lo_)
        dd = Vector(direction).normalized()
        lo_.location = centre + dd * size * 2.0
        lo_.rotation_euler = (-dd).to_track_quat("-Z", "Y").to_euler()

    area("_pvkey", v * 0.7 + side * 0.9 * key_side + Z * 0.8, 260, 1.2, (1.0, 0.93, 0.85))
    area("_pvfill", v * 0.9 - side * 0.8 * key_side + Z * 0.2, 55, 2.0, (0.9, 0.95, 1.0))
    area("_pvrim", -v * 1.0 - side * 0.5 * key_side + Z * 0.9, 220, 0.8, (0.85, 0.9, 1.0))
    cam_d = bpy.data.cameras.new("_pvcam")
    cam_d.lens = lens
    cam = bpy.data.objects.new("_pvcam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.rotation_euler = (-v).to_track_quat("-Z", "Y").to_euler()
    r = res or args.res
    sc.render.resolution_x = int(r * aspect[0] / max(aspect))
    sc.render.resolution_y = int(r * aspect[1] / max(aspect))
    corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    dg = bpy.context.evaluated_depsgraph_get()
    co, _ = cam.camera_fit_coords(dg, [c for p in corners for c in p])
    cam.location = centre + (Vector(co) - (lo + hi) / 2) * margin if aim is None else Vector(co) * margin + centre * (1 - margin)
    cam_d.clip_start = 0.01
    cam_d.dof.use_dof = False
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = args.samples
    sc.cycles.use_denoising = True
    sc.render.threads_mode = "FIXED"
    sc.render.threads = 6
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    log(f"preview {os.path.basename(path)}")


def hide(obs, flag):
    for o in obs:
        o.hide_render = flag


# =========================================================================== main

def main():
    out = args.out
    for sub in ("fbx", "textures", "preview"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)
    S.reset_scene()
    paths = P.write_textures(os.path.join(out, "textures"), n=args.tex_size)
    log("textures written")
    M = {k: P.pbr_material(k, p) for k, p in paths.items()}
    builders = {"chair": build_chair, "desk": build_desk, "mic": build_mic, "plant": build_plant}
    only = [s for s in args.only.split(",") if s] or list(builders)
    manifest = {"units": "FBX in cm; Blender (x, y, z) -> Unreal (x, -y, z)", "textures": {}, "assets": {}}
    for k, p in paths.items():
        manifest["textures"]["M_" + k] = {"BaseColor": os.path.basename(p["BC"]), "Normal_DirectX": os.path.basename(p["N"]),
                                          "ORM": os.path.basename(p["ORM"]), "tile_m": P.TILE_M[k], "uv": "UV0 (UVMap)"}
    built = {}
    for key in only:
        ob, hulls, socks, info = builders[key](M)
        S.tidy(ob, 40)
        ob.matrix_world = Matrix.Identity(4)
        walnut_slot = {i for i, m in enumerate(ob.data.materials) if m and m.name in ("M_Walnut", "M_Leaf")}
        P.uv_finish(ob, P.TILE_M, skip_slots=walnut_slot)
        cols = P.ucx(ob.name, hulls)
        fbx = os.path.join(out, "fbx", ob.name + ".fbx")
        P.export_fbx(fbx, [ob] + cols + socks)
        entry = P.manifest_entry(ob, fbx, info)
        ok, dims = P.check_fbx(fbx, entry["size_cm"])
        entry["fbx_reimport_cm"] = dims
        entry["fbx_scale_ok"] = ok
        entry["collision"] = [c.name for c in cols]
        manifest["assets"][ob.name] = entry
        log(f"{ob.name}: size {entry['size_cm']} cm, {entry['triangles']} tris, reimport {dims} ok={ok}")
        built[key] = (ob, cols, socks)
        for c in cols:
            c.hide_render = True
    P.write_json(os.path.join(out, "props.json"), manifest)
    if args.no_render:
        return
    allobs = [b[0] for b in built.values()]
    views = {"chair": (1.0, -0.75, 0.42), "desk": (1.0, -0.8, 0.55), "mic": (0.35, -1.0, 0.25), "plant": (1.0, -0.6, 0.35)}
    for key, (ob, _, _) in built.items():
        hide(allobs, True)
        ob.hide_render = False
        lo, hi = S.bbox(ob)
        preview_stage(lo, hi, views[key], os.path.join(out, "preview", f"{ob.name}.png"), lens=60)
        if key == "chair":
            preview_stage(lo, hi, (-0.9, 0.7, 0.35), os.path.join(out, "preview", f"{ob.name}_back.png"), lens=60)
        if key == "mic":
            mc = [o for o in built["mic"][2] if o.name == "SOCKET_MicCentre"][0].matrix_world.translation
            preview_stage(mc - Vector((0.13, 0.13, 0.13)), mc + Vector((0.13, 0.13, 0.13)), (0.2, -1.0, 0.15),
                          os.path.join(out, "preview", f"{ob.name}_closeup.png"), lens=85)
        if key == "chair":
            preview_stage(Vector((-0.05, -0.08, 0.40)), Vector((0.25, 0.08, 0.47)), (1.0, -0.4, 0.5),
                          os.path.join(out, "preview", f"{ob.name}_fabric.png"), lens=85)
        if key == "desk":
            preview_stage(Vector((0.1, -0.3, 0.70)), Vector((0.28, 0.0, 0.745)), (0.8, -0.5, 0.6),
                          os.path.join(out, "preview", f"{ob.name}_grain.png"), lens=85)
    # the set as laid out (Blender frame = set frame with y negated; Unreal yaw psi = Blender rotation -psi)
    if len(built) == 4:
        hide(allobs, False)
        place = {"chair": (CHAIR_UE, 0), "desk": (DESK_UE, 0), "mic": (MIC_CLAMP_UE, -90),
                 "plant": (Vector((100.0, 25.0, 74.0)), 0)}
        for key, (loc, yaw) in place.items():
            ob = built[key][0]
            ob.matrix_world = Matrix.Translation((loc.x / 100, -loc.y / 100, loc.z / 100)) @ Matrix.Rotation(math.radians(-yaw), 4, "Z")
        mouth = Vector((MOUTH_UE.x / 100, -MOUTH_UE.y / 100, MOUTH_UE.z / 100))
        lo, hi = Vector((-0.4, -0.5, 0.0)), Vector((1.1, 0.8, 1.35))
        preview_stage(lo, hi, (1.0, 0.25, 0.18), os.path.join(out, "preview", "SET_explainer_camera.png"), lens=40,
                      res=1920, aspect=(16, 9), margin=1.0)
        preview_stage(lo, hi, (0.7, -0.9, 0.45), os.path.join(out, "preview", "SET_explainer_three_quarter.png"), lens=35,
                      res=1920, aspect=(16, 9), margin=1.02)
        log(f"set: mouth marker at {tuple(round(c, 3) for c in mouth)} (not rendered)")


main()
log("done")
