"""karma_sign — the halo-lit word "karma" in Samarkan, matte black powder-coated metal letters.

Overall width 100 cm (Y); height as the font gives at that width. Letters 2.5 cm deep with a 1.5 mm
bevel on the front edges (0.5 mm on the back), floating 4 cm off the wall on 6 mm standoff pins
hidden behind the letters (2-4 per letter, placed where the letter is thickest).

Built from Blender's text object with the TTF: the glyphs are extruded, then unioned with the exact
boolean so the letters and the font's continuous headline bar are one clean solid (the font draws
the "r" body as its own piece hanging under the bar, so that piece stays separate with its own
pins), then bevelled, triangulated and joined with the pins.

Origin: bottom centre of the letters' BACK plane at the wall line: pin ends at x = 0, letters' back
face at x = 4 cm, front face at x = 6.5 cm.

Also writes karma_halo.png (2048 px wide orthographic silhouette from +X, white letters on black)
and karma_halo.json (the image's bounds in cm in the sign's coordinates) for the glow card, and
slat_sign_combo.png: the sign on the slat panel (from slat_panel.py), lit from behind.

The font (Samarkan, SAMAN___.ttf) is NOT in the repo (licence unclear). Pass it with --font, or it
is looked for in FONT_SEARCH below.

    blender -b --factory-startup -P films/host-studio/props/karma_sign.py -- \\
        --out films/host-studio/props/out --font /path/to/SAMAN___.ttf
"""
import argparse
import json
import math
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _studio as S  # noqa: E402
import slat_panel as SP  # noqa: E402

FONT_FILE = "SAMAN___.ttf"
FONT_SEARCH = [
    os.environ.get("KARMA_FONT", ""),
    os.path.join(HERE, FONT_FILE),                                         # next to the script (Mac tmp dir)
    "/tmp/fleet-agent-02-slat-sign/" + FONT_FILE,                         # the Mac run directory
    "/work/inbox/20261101-task-the-walnut-slat-6619/" + FONT_FILE,        # the agent's inbox
]

cm = 0.01
mm = 0.001
TEXT = "karma"
WIDTH = 100 * cm
DEPTH = 2.5 * cm
STANDOFF = 4.0 * cm
BEVEL_FRONT = 1.5 * mm
BEVEL_BACK = 0.5 * mm
PIN_R = 3.0 * mm
PIN_EMBED = 0.5 * mm        # pins reach 0.5 mm into the letters: no coplanar faces at the joint
CURVE_RES = 14              # text curve resolution (segments per bezier span)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--font", default=None, help="path to SAMAN___.ttf (Samarkan); else FONT_SEARCH")
    return ap.parse_args(argv)


def find_font(path):
    for p in ([path] if path else []) + FONT_SEARCH:
        if p and os.path.isfile(p):
            return p
    sys.exit(f"karma_sign: font {FONT_FILE} not found; pass --font (looked in {FONT_SEARCH})")


# --------------------------------------------------------------------------- text -> mesh

def text_bm(font, size, extrude):
    """The word as a bmesh in the text's own plane (x right, y up, extruded along z)."""
    cu = bpy.data.curves.new("karma_text", "FONT")
    cu.font = font
    cu.body = TEXT
    cu.size = size
    cu.extrude = extrude
    cu.resolution_u = CURVE_RES
    ob = bpy.data.objects.new("karma_text", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bm = bmesh.new()
    bm.from_mesh(me)
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    return bm


def text_contours(font, size):
    """The word's outline as closed 2D polylines (text plane), sampled from the font's beziers."""
    from mathutils.geometry import interpolate_bezier
    cu = bpy.data.curves.new("karma_text", "FONT")
    cu.font = font
    cu.body = TEXT
    cu.size = size
    ob = bpy.data.objects.new("karma_text", cu)
    bpy.context.scene.collection.objects.link(ob)
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.convert(target="CURVE")
    ob = bpy.context.view_layer.objects.active
    loops = []
    for sp in ob.data.splines:
        bp = sp.bezier_points
        pts = []
        for k in range(len(bp)):
            a, b = bp[k], bp[(k + 1) % len(bp)]
            straight = (a.handle_right - a.co).length < 1e-9 and (b.handle_left - b.co).length < 1e-9
            seg = [a.co, b.co] if straight else interpolate_bezier(a.co, a.handle_right, b.handle_left, b.co,
                                                                  CURVE_RES + 1)
            pts += [(p.x, p.y) for p in seg[:-1]]
        P = np.array(pts)
        keep = np.linalg.norm(P - np.roll(P, -1, axis=0), axis=1) > 1e-7     # drop repeated points
        loops.append(P[keep])
    data = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(data)
    return loops


def signed_area(P):
    return 0.5 * float(np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]))


def point_in(P, pt):
    x, y = pt
    xs, ys = P[:, 0], P[:, 1]
    xj, yj = np.roll(xs, 1), np.roll(ys, 1)
    dy = np.where(yj - ys == 0, 1e-15, yj - ys)
    return bool((((ys > y) != (yj > y)) & (x < (xj - xs) * (y - ys) / dy + xs)).sum() % 2)


def split_simple(P, depth=0):
    """Split a self-crossing closed polyline at its crossings into simple loops."""
    n = len(P)
    A, B = P, np.roll(P, -1, axis=0)
    for i in range(n):
        p, r = A[i], B[i] - A[i]
        q, sv = A[i + 2:], B[i + 2:] - A[i + 2:]
        if i == 0:
            q, sv = q[:-1], sv[:-1]             # the last segment touches segment 0
        if not len(q):
            continue
        den = r[0] * sv[:, 1] - r[1] * sv[:, 0]
        ok = np.abs(den) > 1e-18
        qp = q - p
        t = np.where(ok, (qp[:, 0] * sv[:, 1] - qp[:, 1] * sv[:, 0]) / np.where(ok, den, 1), -1)
        u = np.where(ok, (qp[:, 0] * r[1] - qp[:, 1] * r[0]) / np.where(ok, den, 1), -1)
        hit = np.nonzero(ok & (t > 1e-9) & (t < 1 - 1e-9) & (u > 1e-9) & (u < 1 - 1e-9))[0]
        if len(hit) and depth < 20:
            j = i + 2 + int(hit[0])
            X = p + t[hit[0]] * r
            one = np.vstack([X, P[i + 1:j + 1]])
            two = np.vstack([X, P[j + 1:], P[:i + 1]])
            return split_simple(one, depth + 1) + split_simple(two, depth + 1)
    return [P]


def solid_from_loops(outer, holes, z0, z1):
    """Fill an outer loop with holes and extrude it from z0 to z1 (closed, outward normals)."""
    bm = bmesh.new()
    edges = []
    for L in [outer] + holes:
        vs = [bm.verts.new((x, y, z0)) for x, y in L]
        edges += [bm.edges.new((vs[k], vs[(k + 1) % len(vs)])) for k in range(len(vs))]
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
    ext = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
    bmesh.ops.translate(bm, vec=(0, 0, z1 - z0), verts=[g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def contour_solids(font, size, z0, z1):
    """One closed solid per simple outer loop of the text (with the holes inside it).

    The font's "a" is drawn with a self-crossing outer contour and its glyphs overlap at the
    headline bar; filled as-is that gives overlapping, non-manifold faces. So: split every
    contour at its crossings, classify the pieces by winding (outer vs hole), fill and
    extrude each outer piece with its holes, and leave the union to the boolean."""
    raw = text_contours(font, size)
    outer_sign = np.sign(signed_area(max(raw, key=lambda P: abs(signed_area(P)))))
    pieces = []
    for P in raw:
        parts = split_simple(P)
        for Q in parts:
            if abs(signed_area(Q)) > 1e-9:
                # a crossing turns part of an outer contour around: nonzero fill still fills it
                pieces.append((Q, np.sign(signed_area(P)) == outer_sign))
        if len(parts) > 1:
            print(f"karma_sign: a contour crossed itself; split into {len(parts)} loops")
    outers = [Q if signed_area(Q) * outer_sign > 0 else Q[::-1] for Q, is_outer in pieces if is_outer]
    holes = [Q for Q, is_outer in pieces if not is_outer]
    holes_of = {i: [] for i in range(len(outers))}
    for H in holes:
        around = [i for i, O in enumerate(outers) if point_in(O, H.mean(0)) and point_in(O, H[0])]
        if around:
            holes_of[min(around, key=lambda i: abs(signed_area(outers[i])))].append(H)
    solids = [solid_from_loops(O, holes_of[i], z0, z1) for i, O in enumerate(outers)]
    print(f"karma_sign: {len(raw)} contours -> {len(outers)} outer loops, {len(holes)} holes")
    return solids


def islands(bm):
    """Connected groups of faces."""
    bm.faces.index_update()
    seen, out = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        comp, stack = [], [f]
        seen.add(f.index)
        while stack:
            g = stack.pop()
            comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        out.append(comp)
    return out


def bm_from_faces(faces):
    """A new bmesh holding a copy of `faces`."""
    nb = bmesh.new()
    vmap = {}
    for f in faces:
        for v in f.verts:
            if v not in vmap:
                vmap[v] = nb.verts.new(v.co)
        nb.faces.new([vmap[v] for v in f.verts])
    return nb


def union_solids(bms, mat):
    """Union closed solids with the exact boolean; returns one bmesh."""
    obs = [S.obj_from_bm(b, f"glyph_{i}", mat) for i, b in enumerate(bms)]
    base, rest = obs[0], obs[1:]
    if rest:
        coll = bpy.data.collections.new("glyph_ops")
        bpy.context.scene.collection.children.link(coll)
        for o in rest:
            bpy.context.scene.collection.objects.unlink(o)
            coll.objects.link(o)
        mod = base.modifiers.new("union", "BOOLEAN")
        mod.operation = "UNION"
        mod.operand_type = "COLLECTION"
        mod.collection = coll
        solvers = [e.identifier for e in mod.bl_rna.properties["solver"].enum_items]
        # Manifold (Blender 4.5+) is robust on the coplanar front/back faces; Exact is the fallback
        mod.solver = "MANIFOLD" if "MANIFOLD" in solvers else "EXACT"
        if mod.solver == "EXACT":
            mod.use_self = True
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(base.evaluated_get(dg))
    bm = bmesh.new()
    bm.from_mesh(me)
    for o in obs:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.meshes.remove(me)
    if rest:
        bpy.data.collections.remove(coll)
    return bm


# --------------------------------------------------------------------------- pin placement

def island_geometry(faces):
    """(triangles (T,3,2), boundary segments (E,2,2), area) of a flat island, in the text plane."""
    nb = bm_from_faces(faces)
    bmesh.ops.triangulate(nb, faces=nb.faces)
    tris = np.array([[(v.co.x, v.co.y) for v in f.verts] for f in nb.faces])
    segs = np.array([[(e.verts[0].co.x, e.verts[0].co.y), (e.verts[1].co.x, e.verts[1].co.y)]
                     for e in nb.edges if len(e.link_faces) == 1])
    area = sum(f.calc_area() for f in nb.faces)
    nb.free()
    return tris, segs, area


def inside(pts, tris):
    res = np.zeros(len(pts), bool)
    for a, b, c in tris:
        v0, v1 = c - a, b - a
        v2 = pts - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        d20, d21 = v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-18:
            continue
        u = (d11 * d20 - d01 * d21) / den
        v = (d00 * d21 - d01 * d20) / den
        res |= (u >= 0) & (v >= 0) & (u + v <= 1)
    return res


def seg_dist(pts, segs):
    a, b = segs[:, 0], segs[:, 1]
    ab = b - a
    ll = np.maximum((ab * ab).sum(1), 1e-18)
    ap = pts[:, None, :] - a[None]
    t = np.clip((ap * ab[None]).sum(2) / ll[None], 0, 1)
    d = ap - t[..., None] * ab[None]
    return np.sqrt((d * d).sum(2)).min(1)


def candidates(faces, step):
    tris, segs, area = island_geometry(faces)
    lo, hi = tris.reshape(-1, 2).min(0), tris.reshape(-1, 2).max(0)
    xs = np.arange(lo[0], hi[0], step)
    ys = np.arange(lo[1], hi[1], step)
    pts = np.array([(x, y) for x in xs for y in ys])
    pts = pts[inside(pts, tris)]
    return pts, seg_dist(pts, segs), area


def pick(pts, clear, n, others, min_clear):
    """Farthest-point picks among points with clearance >= min_clear (relaxed if none qualify)."""
    for thr in (min_clear, min_clear * 0.8, min_clear * 0.6):
        ok = clear >= thr
        if ok.sum() >= n:
            break
    P = pts[ok]
    chosen = []
    if not len(P):
        return chosen
    ref = list(others)
    if ref:
        d = np.min(np.linalg.norm(P[:, None] - np.array(ref)[None], axis=2), axis=1)
    else:
        d = np.linalg.norm(P - P.mean(0), axis=1)
    for _ in range(n):
        i = int(np.argmax(d))
        chosen.append(P[i])
        d = np.minimum(d, np.linalg.norm(P - P[i], axis=1))
    return chosen


# --------------------------------------------------------------------------- build

def build(font_path):
    font = bpy.data.fonts.load(font_path)
    black = S.material("M_LetterBlack", (0.018, 0.018, 0.019), 0.55, specular=0.4)   # matte powder coat
    steel = S.material("M_Metal", (0.62, 0.62, 0.64), 0.32, metallic=1.0)           # zinc-plated steel

    # measure the word at size 1, then rebuild at the size that makes it 100 cm wide
    flat = text_bm(font, 1.0, 0.0)
    xs = [v.co.x for v in flat.verts]
    flat.free()
    size = WIDTH / (max(xs) - min(xs))
    flat = text_bm(font, size, 0.0)
    fx = [v.co.x for v in flat.verts]
    fy = [v.co.y for v in flat.verts]
    x_mid, y_min = (min(fx) + max(fx)) / 2, min(fy)
    # text plane -> sign coordinates: text x -> Y, text y -> Z, text z -> X (back face at STANDOFF)
    to_sign = Matrix(((0, 0, 1, STANDOFF + DEPTH / 2),
                      (1, 0, 0, -x_mid),
                      (0, 1, 0, -y_min),
                      (0, 0, 0, 1)))

    # --- the letters: one solid per glyph island, unioned
    parts = contour_solids(font, size, -DEPTH / 2, DEPTH / 2)
    parts.sort(key=lambda b: -sum(f.calc_area() for f in b.faces))
    bm = union_solids(parts, black)
    bm.transform(to_sign)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.05), use_dissolve_boundaries=False,
                             verts=list(bm.verts), edges=list(bm.edges))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    nm = [e for e in bm.edges if not e.is_manifold]
    print(f"karma_sign: union -> {len(islands(bm))} solid piece(s), {len(nm)} non-manifold edges")

    def cap_edges(sign):
        out = []
        for e in bm.edges:
            if len(e.link_faces) != 2:
                continue
            a, b = e.link_faces
            ca, cb = a.normal.x * sign > 0.999, b.normal.x * sign > 0.999
            if ca != cb:
                out.append(e)
        return out

    bmesh.ops.bevel(bm, geom=cap_edges(+1), offset=BEVEL_FRONT, offset_type="OFFSET", segments=3,
                    profile=0.5, affect="EDGES", clamp_overlap=True, loop_slide=True)
    bmesh.ops.bevel(bm, geom=cap_edges(-1), offset=BEVEL_BACK, offset_type="OFFSET", segments=1,
                    profile=0.5, affect="EDGES", clamp_overlap=True, loop_slide=True)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4],
                          quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.normal_update()
    bad = [e for e in bm.edges if not e.is_manifold]
    flipped = sum(1 for f in bm.faces if abs(f.normal.x) > 0.999 and (f.normal.x > 0) != (f.calc_center_median().x > STANDOFF + DEPTH / 2))
    print(f"karma_sign: letters after bevel: {len(bad)} non-manifold edges, {flipped} flipped caps, "
          f"{sum(1 for f in bm.faces if f.calc_area() < 1e-12)} degenerate faces")
    SP.box_uv(bm, grain_axis=1)
    letters = SP.bm_object(bm, "letters", black, round_test=lambda f: abs(f.normal.x) < 0.999)

    # --- standoff pins: 2-4 per glyph island, where the letter is thickest
    flat_isl = islands(flat)
    info = []
    for isl in flat_isl:
        pts, clear, area = candidates(isl, 1.5 * mm)
        info.append((isl, pts, clear, area, len({v for f in isl for v in f.verts})))
    big = sorted(i[3] for i in info if i[4] > 8)
    median = big[len(big) // 2]
    pins_2d = []
    for isl, pts, clear, area, nverts in sorted(info, key=lambda i: min(v.co.x for f in i[0] for v in f.verts)):
        n = 1 if nverts <= 8 else int(min(4, max(2, round(3 * area / median))))
        got = pick(pts, clear, n, pins_2d, 7 * mm)
        print(f"karma_sign: island area {area*1e4:.0f} cm2 -> {len(got)} pins, "
              f"clearance {[round(float(seg_dist(np.array([g]), island_geometry(isl)[1])[0]) * 1000, 1) for g in got]} mm")
        pins_2d += got
    flat.free()

    pins = []
    prof = [(0.0, 0.0), (PIN_R - 0.6 * mm, 0.0), (PIN_R, 0.6 * mm), (PIN_R, STANDOFF + PIN_EMBED),
            (0.0, STANDOFF + PIN_EMBED)]
    for i, (px, py) in enumerate(pins_2d):
        y, z = px - x_mid, py - y_min
        m = Matrix.Translation((0, y, z)) @ Matrix.Rotation(math.pi / 2, 4, "Y")
        pins.append(S.lathe(f"pin_{i}", prof, [steel], segs=16, matrix=m))
    for p in pins:
        bm = bmesh.new()
        bm.from_mesh(p.data)
        SP.box_uv(bm, grain_axis=0)
        bm.to_mesh(p.data)
        bm.free()

    ob = S.join("karma_sign", [letters] + pins)
    SP.shade(ob, sharp_angle=40)
    return ob, len(pins_2d)


# --------------------------------------------------------------------------- rendering

def set_eevee(samples):
    sc = bpy.context.scene
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    sc.eevee.taa_render_samples = samples
    for attr in ("use_shadows", "use_raytracing"):
        if hasattr(sc.eevee, attr):
            setattr(sc.eevee, attr, True)
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.resolution_x = sc.render.resolution_y = 1200
    sc.render.resolution_percentage = 100


def set_world(color, strength=1.0):
    sc = bpy.context.scene
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    world.color = color
    if not world.node_tree:
        world.use_nodes = True
    bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is not None:
        bg.inputs["Color"].default_value = (*color, 1)
        bg.inputs["Strength"].default_value = strength


def camera(loc, target, lens=50, ortho=None):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("_cam")
    cd.lens = lens
    cd.clip_start = 0.01
    cd.clip_end = 100
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
        cd.sensor_fit = "HORIZONTAL"
    cam = bpy.data.objects.new("_cam", cd)
    sc.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    return cam


def fit(cam, lo, hi, margin=1.1):
    """Slide the camera along its view axis so the box lo..hi fills the frame."""
    corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    dg = bpy.context.evaluated_depsgraph_get()
    co, _ = cam.camera_fit_coords(dg, [c for p in corners for c in p])
    centre = (lo + hi) / 2
    cam.location = centre + (Vector(co) - centre) * margin


def area_light(name, loc, target, energy, size, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = "DISK"
    ld.size = size
    ld.energy = energy
    ld.color = color
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def point_light(name, loc, energy, radius, color):
    ld = bpy.data.lights.new(name, "POINT")
    ld.energy = energy
    ld.color = color
    ld.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    return ob


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def halo(ob, out_dir, pad=6 * cm, width_px=2048):
    """White-on-black orthographic silhouette from +X and its bounds in cm."""
    sc = bpy.context.scene
    lo, hi = S.bbox(ob)
    y0, y1 = lo.y - pad, hi.y + pad
    w = y1 - y0
    h_px = int(round(width_px * (hi.z - lo.z + 2 * pad) / w))
    h = h_px * w / width_px
    zc = (lo.z + hi.z) / 2
    z0, z1 = zc - h / 2, zc + h / 2
    cam = camera(((hi.x + 1.0), (y0 + y1) / 2, zc), (0, (y0 + y1) / 2, zc), ortho=w)
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "FLAT"
    sh.color_type = "SINGLE"
    sh.single_color = (1, 1, 1)
    sh.show_shadows = False
    sh.show_cavity = False
    sh.show_object_outline = False
    sc.display.render_aa = "8"
    set_world((0, 0, 0))
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.film_transparent = False
    sc.render.resolution_x = width_px
    sc.render.resolution_y = h_px
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "BW"
    render(os.path.join(out_dir, "karma_halo.png"))
    sc.render.image_settings.color_mode = "RGB"
    meta = {
        "image": "karma_halo.png", "width_px": width_px, "height_px": h_px,
        "view": "orthographic from +X (Y to image right, Z up); white = letters",
        "units": "cm, in karma_sign's own coordinates (origin: bottom centre of the letters' back plane at the wall)",
        "y0": round(y0 * 100, 3), "y1": round(y1 * 100, 3), "z0": round(z0 * 100, 3), "z1": round(z1 * 100, 3),
        "letters_bbox_cm": {"y": [round(lo.y * 100, 3), round(hi.y * 100, 3)],
                            "z": [round(lo.z * 100, 3), round(hi.z * 100, 3)]},
        "x_letter_back_cm": STANDOFF * 100, "x_letter_front_cm": (STANDOFF + DEPTH) * 100, "x_wall_cm": 0.0,
        "padding_cm": pad * 100,
    }
    with open(os.path.join(out_dir, "karma_halo.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    bpy.data.objects.remove(cam, do_unlink=True)
    return meta


def clear_helpers():
    for o in list(bpy.data.objects):
        if o.name.startswith("_"):
            bpy.data.objects.remove(o, do_unlink=True)


def wall(x, y0, y1, z0, z1, color=(0.36, 0.34, 0.32), name="_wall"):
    m = S.material("_PreviewWall", color, 0.85)
    return S.box(name, (x - 0.02, y0, z0), (x - 0.0003, y1, z1), m)


def previews(ob, args):
    lo, hi = S.bbox(ob)
    c = (lo + hi) / 2
    set_eevee(args.samples)
    set_world((0.18, 0.18, 0.18))
    wall(0.0, lo.y - 1.5, hi.y + 1.5, lo.z - 1.0, hi.z + 1.0)

    def lights():
        area_light("_key", c + Vector((1.2, 0.9, 0.9)), c, 50, 1.0)
        area_light("_fill", c + Vector((1.4, -1.0, 0.2)), c, 14, 1.6)
        area_light("_top", c + Vector((0.5, 0.0, 1.4)), c, 14, 1.0)

    # 3/4 from front-right-above
    lights()
    cam = camera(c + Vector((1.0, 0.75, 0.45)) * 2.0, c, lens=50)
    fit(cam, lo, hi, 1.12)
    render(os.path.join(args.out, "karma_sign.png"))
    clear_helpers()
    wall(0.0, lo.y - 1.5, hi.y + 1.5, lo.z - 1.0, hi.z + 1.0)
    # front, level with the letters
    lights()
    cam = camera(c + Vector((2.0, 0, 0)), c, lens=50)
    fit(cam, lo, hi, 1.12)
    render(os.path.join(args.out, "karma_sign_front.png"))
    clear_helpers()
    wall(0.0, lo.y - 1.5, hi.y + 1.5, lo.z - 1.0, hi.z + 1.0)
    # oblique close-up of the "k" from the left: bevel, depth and standoffs
    tgt = Vector((0.045, lo.y + 0.10, lo.z + 0.09))
    area_light("_key", tgt + Vector((0.45, -0.30, 0.40)), tgt, 9, 0.4)
    area_light("_fill", tgt + Vector((0.6, 0.4, 0.0)), tgt, 3, 0.8)
    area_light("_rim", tgt + Vector((0.10, -0.5, 0.25)), tgt, 4, 0.2)
    camera(tgt + Vector((0.19, -0.21, 0.07)), tgt, lens=50)
    render(os.path.join(args.out, "karma_sign_close.png"))
    clear_helpers()


def combo(ob, args, glow_pts):
    """The sign on the slat panel, centred at 230 cm, warm LEDs between the letters and the slats."""
    set_eevee(args.samples)
    set_world((0.020, 0.016, 0.012))
    panel = SP.make_panel("_panel")
    slat_front = SP.FELT_T + SP.SLAT_D
    lo, hi = S.bbox(ob)
    ob.location = (slat_front, 0.0, 2.30 - (hi.z - lo.z) / 2 - lo.z)
    plaster = S.material("_Plaster", (0.62, 0.52, 0.40), 0.9)
    S.box("_wall", (-0.05, -3.0, 0.0), (-0.0003, 3.0, 3.0), plaster)
    oak = S.material("_Floor", (0.30, 0.19, 0.11), 0.5)
    S.box("_floor", (-0.05, -3.0, -0.02), (5.0, 3.0, -0.0003), oak)
    ceil = S.material("_Ceiling", (0.7, 0.66, 0.6), 0.9)
    S.box("_ceiling", (-0.05, -3.0, 3.0003), (5.0, 3.0, 3.03), ceil)
    if hasattr(bpy.context.scene.eevee, "shadow_pool_size"):
        bpy.context.scene.eevee.shadow_pool_size = "1024"
    warm = (1.0, 0.56, 0.24)
    x_led = slat_front + STANDOFF - 6 * mm      # LEDs on the letters' backs, facing the slats
    for i, (y, z) in enumerate(glow_pts):
        point_light(f"_led{i}", (x_led, y, ob.location.z + z), 1.3, 0.012, warm)
    area_light("_window", (2.2, -3.2, 2.2), (0.0, 0.0, 1.6), 130, 2.5, (1.0, 0.86, 0.72))
    area_light("_fill", (3.5, 1.5, 1.8), (0.0, 0.0, 1.8), 25, 2.0, (1.0, 0.8, 0.6))
    cam = camera((2.9, 0.65, 1.7), (0.0, 0.0, 1.95), lens=32)
    cam.data.sensor_width = 36
    render(os.path.join(args.out, "slat_sign_combo.png"))
    # a closer look at the halo
    clear_helpers_but = [o for o in bpy.data.objects if o.name.startswith("_cam")]
    for o in clear_helpers_but:
        bpy.data.objects.remove(o, do_unlink=True)
    camera((1.35, 0.35, 2.10), (0.0, 0.0, 2.28), lens=40)
    render(os.path.join(args.out, "slat_sign_combo_close.png"))


def glow_points(ob, n=34):
    """Spread points over the letters' silhouette (sign coordinates, y/z) for the preview LEDs."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    back = [f for f in bm.faces if f.normal.x < -0.999 and f.calc_center_median().x > STANDOFF - 1e-4]
    pts = []
    for f in back:
        for _ in range(max(1, int(f.calc_area() / 2e-5))):
            pts.append(f.calc_center_median())
    bm.free()
    P = np.array([(p.y, p.z) for p in pts])
    chosen = []
    d = np.full(len(P), np.inf)
    i = int(np.argmin(P[:, 0]))
    for _ in range(n):
        chosen.append(tuple(P[i]))
        d = np.minimum(d, np.linalg.norm(P - P[i], axis=1))
        i = int(np.argmax(d))
    return chosen


# --------------------------------------------------------------------------- main

if __name__ == "__main__":
    args = parse_args()
    font_path = find_font(args.font)
    print(f"karma_sign: font {font_path}")
    S.reset_scene()
    ob, n_pins = build(font_path)
    os.makedirs(args.out, exist_ok=True)
    fbx = os.path.join(args.out, "karma_sign.fbx")
    S.export_fbx(ob, fbx)
    lo, hi = S.bbox(ob)
    print("=" * 60)
    print(f"karma_sign: exported {fbx}")
    print(f"karma_sign: materials {[m.name for m in ob.data.materials]}")
    print(f"karma_sign: triangles {S.tri_count(ob)}  pins {n_pins}")
    print(f"karma_sign: bbox cm  X {lo.x*100:.2f}..{hi.x*100:.2f}  Y {lo.y*100:.2f}..{hi.y*100:.2f}"
          f"  Z {lo.z*100:.2f}..{hi.z*100:.2f}")
    print("=" * 60)
    meta = halo(ob, args.out)
    print(f"karma_sign: halo {meta['width_px']}x{meta['height_px']} y {meta['y0']}..{meta['y1']}"
          f" z {meta['z0']}..{meta['z1']} cm")
    if not args.no_render:
        pts = glow_points(ob, 64)
        previews(ob, args)
        combo(ob, args, pts)
