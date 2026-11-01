"""_labels — the six small 'label' props of the host studio, and their combo preview.

These objects carry text or pictures: the orchestrator textures their M_Label_* slots, so every
label face has exactly the size the brief gives, UV 0..1 over the face, and reads upright from the
front (U to screen-right = +Y, V up).

    nameplate         walnut block, engraved-name decal on the front            M_Label_Name
    desk_calendar     wire-o flip calendar on a black easel                      M_Label_Calendar
    terminal_display  slim ticker display, screen behind a glass pane            M_Label_Terminal
    polaroid          instant-film print, bowed 2 mm                            M_Label_Polaroid
    sticky_note       sticky note, adhesive strip at the top, curled bottom     M_Label_Sticky
    framed_print      light-oak frame, mat, glass and the print                 M_Label_Print

Each prop has its own script (nameplate.py, ...) that calls run(name); labels_combo.py puts all six
on a light-oak surface. Geometry is built in cm, then scaled to metres before the UVs and export.
The previews put a UV test image (coloured borders, an arrow and the word UP) on the label slots.

    blender -b --factory-startup -P films/host-studio/props/nameplate.py -- --out films/host-studio/props/out
"""
import argparse
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

CM = 0.01
X, Y, Z = 0, 1, 2
VIEW_34 = (1.0, 0.8, 0.62)        # front-right-above
LABEL = "M_Label"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--close", action="store_true", help="also render a close-up, where the prop has one")
    ap.add_argument("--check", help="extra view direction x,y,z rendered to <name>_check.png (for review)")
    return ap.parse_args(argv)


# --------------------------------------------------------------------------- materials

def _bsdf(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def wood(name, base, dark, light, roughness, scale):
    """Wood whose preview grain runs along U (so the preview also shows the grain direction)."""
    m = S.material(name, base, roughness)
    nt = m.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.05, 1.0, 1.0)      # stretch the figure along the grain
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Y"                                # bands vary with V: lines along U
    wave.inputs["Scale"].default_value = scale
    wave.inputs["Distortion"].default_value = 12.0
    wave.inputs["Detail"].default_value = 4.0
    wave.inputs["Detail Scale"].default_value = 1.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].color = (*light, 1)
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[1].position = 0.95
    nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], _bsdf(m).inputs["Base Color"])
    return m


def glass(name):
    m = S.material(name, (0.02, 0.022, 0.022), 0.03, specular=0.5)
    _bsdf(m).inputs["Alpha"].default_value = 0.04
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    return m


def uv_test_image(n=512):
    """Checker with coloured borders (top red, bottom blue, left green, right yellow), an up arrow and UP."""
    import numpy as np
    img = bpy.data.images.get("_UVTest")
    if img:
        return img
    a = np.ones((n, n, 4), np.float32)                     # row 0 = top while drawing
    yy, xx = np.mgrid[0:n, 0:n]
    chk = ((xx // (n // 8) + yy // (n // 8)) % 2)[..., None]
    a[..., :3] = np.where(chk == 0, (0.88, 0.88, 0.86), (0.62, 0.68, 0.78))
    b = n // 24
    a[:b, :, :3] = (0.85, 0.08, 0.06)          # top
    a[-b:, :, :3] = (0.08, 0.2, 0.85)          # bottom
    a[:, :b, :3] = (0.1, 0.7, 0.15)            # left
    a[:, -b:, :3] = (0.95, 0.8, 0.05)          # right
    ink = (0.05, 0.05, 0.05)
    # arrow: shaft and head, pointing up, in the upper half
    cx = n // 2
    a[int(0.24 * n):int(0.5 * n), cx - n // 32:cx + n // 32, :3] = ink
    for r in range(int(0.1 * n), int(0.26 * n)):
        half = int((r - 0.1 * n) * 0.55)
        a[r, cx - half:cx + half + 1, :3] = ink
    # "UP" in a 5x7 bitmap font, lower half
    glyphs = {"U": ["10001"] * 6 + ["01110"],
              "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"]}
    px = n // 22
    x0 = cx - (11 * px) // 2
    y0 = int(0.58 * n)
    for gi, ch in enumerate("UP"):
        for r, row in enumerate(glyphs[ch]):
            for c, bit in enumerate(row):
                if bit == "1":
                    xs = x0 + (gi * 6 + c) * px
                    a[y0 + r * px:y0 + (r + 1) * px, xs:xs + px, :3] = ink
    img = bpy.data.images.new("_UVTest", n, n)
    img.pixels.foreach_set(a[::-1].ravel())
    return img


def preview_labels():
    """Put the UV test image on every label slot (after the export: the FBX keeps plain materials)."""
    img = uv_test_image()
    for m in bpy.data.materials:
        if m.name.startswith(LABEL):
            nt = m.node_tree
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = img
            bsdf = _bsdf(m)
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            bsdf.inputs["Roughness"].default_value = 0.55
            bsdf.inputs["Metallic"].default_value = 0.0


# --------------------------------------------------------------------------- mesh helpers (cm)

def new_bm():
    bm = bmesh.new()
    return bm, bm.loops.layers.uv.new("UVMap")


def to_obj(bm, name, mats):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def uniq(vals, tol=1e-5):
    """Sorted values with near-duplicates dropped."""
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def corner_axis(lo, hi, r, n_corner, n_mid):
    """Grid coordinates from lo to hi with n_corner cells in each end band of width r."""
    out = [lo + r * k / n_corner for k in range(n_corner)] if r > 0 else []
    a, b = lo + r, hi - r
    out += [a + (b - a) * k / n_mid for k in range(n_mid + 1)]
    out += [hi - r + r * k / n_corner for k in range(1, n_corner + 1)] if r > 0 else []
    return out


def surf_fd(P, eps=1e-3):
    """Surface (a, b) -> (point, unit normal) from a point function, normal = dP/da x dP/db."""
    def f(a, b):
        da = Vector(P(a + eps, b)) - Vector(P(a - eps, b))
        db = Vector(P(a, b + eps)) - Vector(P(a, b - eps))
        return Vector(P(a, b)), da.cross(db).normalized()
    return f


def sheet(name, cols, rows, surf, t, mats, front=0, back=0, side=0, mask=None, corner_r=0.0,
          label_uv=None):
    """A sheet of thickness t on a grid (a = cols, b = rows) over a mid-surface.

    surf(a, b) -> (point, normal); the front face is on the +normal side. mask(i, j) drops cells
    (holes); corner_r rounds the four corners (the grid needs end bands of width corner_r).
    label_uv(a, b) -> (u, v) for the front face."""
    a0, a1, b0, b1 = cols[0], cols[-1], rows[0], rows[-1]

    def remap(a, b):
        if corner_r > 0:
            for cx, sx in ((a0 + corner_r, -1), (a1 - corner_r, 1)):
                for cy, sy in ((b0 + corner_r, -1), (b1 - corner_r, 1)):
                    px, py = a - cx, b - cy
                    if px * sx > 1e-9 and py * sy > 1e-9:     # square -> quarter disc
                        m = max(abs(px), abs(py))
                        ln = math.hypot(px, py)
                        return cx + px * m / ln, cy + py * m / ln
        return a, b

    bm, uvl = new_bm()
    nc, nr = len(cols) - 1, len(rows) - 1

    def inc(i, j):
        return 0 <= i < nc and 0 <= j < nr and (mask is None or mask(i, j))

    vf, vb, ab = {}, {}, {}

    def vert(k):
        if k not in vf:
            a, b = remap(cols[k[0]], rows[k[1]])
            p, n = surf(a, b)
            vf[k] = bm.verts.new(p + n * (t / 2))
            vb[k] = bm.verts.new(p - n * (t / 2))
            ab[k] = (a, b)

    for i in range(nc):
        for j in range(nr):
            if not inc(i, j):
                continue
            ring = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            for k in ring:
                vert(k)
            f = bm.faces.new([vf[k] for k in ring])
            f.material_index = front
            if label_uv:
                for loop, k in zip(f.loops, ring):
                    loop[uvl].uv = label_uv(*ab[k])
            bm.faces.new([vb[k] for k in reversed(ring)]).material_index = back
            for e, nb in enumerate(((i, j - 1), (i + 1, j), (i, j + 1), (i - 1, j))):
                if not inc(*nb):
                    p, q = ring[e], ring[(e + 1) % 4]
                    bm.faces.new((vf[q], vf[p], vb[p], vb[q])).material_index = side
    return to_obj(bm, name, mats)


def surface_grid(name, cols, rows, P, mat, label_uv):
    """A single-sided grid (a decal) facing dP/da x dP/db."""
    bm, uvl = new_bm()
    vs = [[None] * len(rows) for _ in cols]
    pos = {}
    for i, a in enumerate(cols):
        for j, b in enumerate(rows):
            co, (u, v) = P(a, b)
            vs[i][j] = bm.verts.new(co)
            pos[i, j] = (u, v)
    for i in range(len(cols) - 1):
        for j in range(len(rows) - 1):
            ring = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            f = bm.faces.new([vs[a][b] for a, b in ring])
            for loop, k in zip(f.loops, ring):
                loop[uvl].uv = pos[k]
    return to_obj(bm, name, [mat])


def bevel_sharp(ob, offset, segments, angle=60):
    """Bevel the edges sharper than `angle` degrees (bmesh, in place)."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    lim = math.radians(angle)
    edges = [e for e in bm.edges if e.is_manifold and e.calc_face_angle(0.0) > lim]
    bmesh.ops.bevel(bm, geom=edges, offset=offset, segments=segments, profile=0.5,
                    affect="EDGES", clamp_overlap=True)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def box_part(name, centre, axes, size, mat):
    """Box with full sizes along three unit axes, centred at `centre` (cm)."""
    bm = bmesh.new()
    cols = [Vector(ax) * s for ax, s in zip(axes, size)]
    m = Matrix(((cols[0].x, cols[1].x, cols[2].x, centre[0]),
                (cols[0].y, cols[1].y, cols[2].y, centre[1]),
                (cols[0].z, cols[1].z, cols[2].z, centre[2]),
                (0, 0, 0, 1)))
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)
    return S.obj_from_bm(bm, name, mat)


def fillet(pts, radii, segs, closed=False):
    """Round the corners of a 2D polyline (quadratic Bezier between the tangent points)."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    out = []
    for k in range(n):
        if not closed and k in (0, n - 1):
            out.append(pts[k])
            continue
        p, a, b = pts[k], pts[k - 1], pts[(k + 1) % n]
        r = radii[k]
        if r <= 0:
            out.append(p)
            continue
        da, db = (p - a).normalized(), (b - p).normalized()
        ang = math.acos(max(-1.0, min(1.0, (-da).dot(db))))
        d = min(r / math.tan(ang / 2), (p - a).length * 0.49, (b - p).length * 0.49)
        t1, t2 = p - da * d, p + db * d
        sg = segs if isinstance(segs, int) else segs[k]
        for s in range(sg + 1):
            t = s / sg
            out.append((1 - t) ** 2 * t1 + 2 * (1 - t) * t * p + t * t * t2)
    return out


def uv_box(ob, grain=None):
    """World-scale box projection (1 UV unit = 1 m) on every non-label face, U along the grain axis
    (an axis index, or a function of the face)."""
    me = ob.data
    names = [m.name for m in me.materials]
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    if grain is None:
        lo = [min(v.co[i] for v in bm.verts) for i in range(3)]
        hi = [max(v.co[i] for v in bm.verts) for i in range(3)]
        grain = max(range(3), key=lambda i: hi[i] - lo[i])
    for f in bm.faces:
        if names[f.material_index].startswith(LABEL):
            continue
        g = grain(f) if callable(grain) else grain
        n = f.normal
        dom = max(range(3), key=lambda i: abs(n[i]))
        if dom == g:
            ua, va = [i for i in range(3) if i != g]
        else:
            ua, va = g, 3 - dom - g
        for loop in f.loops:
            loop[uvl].uv = (loop.vert.co[ua], loop.vert.co[va])
    bm.to_mesh(me)
    bm.free()


def finalize(ob, grain=None):
    """Apply modifiers, scale cm -> m, box UVs on the non-label faces."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear()
    old = ob.data
    ob.data = me
    bpy.data.meshes.remove(old)
    me.transform(ob.matrix_world)
    ob.matrix_world = Matrix.Identity(4)
    me.transform(Matrix.Scale(CM, 4))
    uv_box(ob, grain)
    return ob


def transform(parts, m):
    for p in parts:
        p.data.transform(m)
        p.data.update()


# --------------------------------------------------------------------------- finishing

def tidy(ob, sharp_angle=40):
    """Outward normals on closed islands, smooth faces, sharp edges above `sharp_angle`.

    Open islands (decals, label quads) keep the winding they were built with."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    seen = set()
    for f0 in bm.faces:
        if f0.index in seen:
            continue
        island, stack = [], [f0]
        seen.add(f0.index)
        while stack:
            f = stack.pop()
            island.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
        if all(e.is_manifold for f in island for e in f.edges):
            bmesh.ops.recalc_face_normals(bm, faces=island)
    lim = math.radians(sharp_angle)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        e.smooth = e.is_manifold and e.calc_face_angle(0.0) <= lim
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def label_report(ob):
    """Size of each label slot along U and V (cm), its UV range and area."""
    me = ob.data
    uvd = me.uv_layers["UVMap"].data
    out = []
    for idx, m in enumerate(me.materials):
        if not m.name.startswith(LABEL):
            continue
        polys = [p for p in me.polygons if p.material_index == idx]
        loops = [k for p in polys for k in p.loop_indices]
        us = [uvd[k].uv.x for k in loops]
        vs = [uvd[k].uv.y for k in loops]
        # metres per UV unit from the largest polygon
        p0 = max(polys, key=lambda p: p.area)
        li = list(p0.loop_indices)
        P = [me.vertices[me.loops[k].vertex_index].co for k in li[:3]]
        U = [uvd[k].uv for k in li[:3]]
        e1, e2, d1, d2 = P[1] - P[0], P[2] - P[0], U[1] - U[0], U[2] - U[0]
        det = d1.x * d2.y - d1.y * d2.x
        dpdu = (e1 * d2.y - e2 * d1.y) / det
        dpdv = (e2 * d1.x - e1 * d2.x) / det
        area = sum(p.area for p in polys)
        out.append(f"{m.name}: {dpdu.length * 100:.2f} x {dpdv.length * 100:.2f} cm per UV 0..1, "
                   f"u {min(us):.3f}..{max(us):.3f} v {min(vs):.3f}..{max(vs):.3f}, area {area * 1e4:.1f} cm2, "
                   f"{len(polys)} faces")
    return out


def clear_rig():
    for o in list(bpy.data.objects):
        if o.name.startswith("_"):
            bpy.data.objects.remove(o, do_unlink=True)


def assemble(name, spec):
    """Join the parts, put the origin where the brief says, tidy."""
    ob = S.join(name, spec["parts"])
    lo, hi = S.bbox(ob)
    origin = spec.get("origin") or ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)
    S.set_origin(ob, origin)
    tidy(ob, spec.get("sharp", 40))
    return ob


def finish(name, spec, args):
    ob = assemble(name, spec)
    os.makedirs(args.out, exist_ok=True)
    fbx = os.path.join(args.out, name + ".fbx")
    S.export_fbx(ob, fbx)
    lo, hi = S.bbox(ob)
    print("=" * 60)
    print(f"{name}: exported {fbx}")
    print(f"{name}: materials {[m.name for m in ob.data.materials]}")
    print(f"{name}: triangles {S.tri_count(ob)}")
    print(f"{name}: bbox cm  X {lo.x*100:.2f}..{hi.x*100:.2f}  Y {lo.y*100:.2f}..{hi.y*100:.2f}"
          f"  Z {lo.z*100:.2f}..{hi.z*100:.2f}")
    d = (hi - lo) * 100
    print(f"{name}: size cm  {d.x:.2f} x {d.y:.2f} x {d.z:.2f}")
    for line in label_report(ob):
        print(f"{name}: {line}")
    print("=" * 60)
    if not args.no_render:
        preview_labels()
        views = [("", VIEW_34, spec.get("lens", 60), 1.12), ("_front", spec["front"], spec.get("lens", 60), 1.1)]
        if args.close and spec.get("close"):
            views.append(("_close",) + tuple(spec["close"]))
        if args.check:
            views.append(("_check", tuple(float(v) for v in args.check.split(",")), spec.get("lens", 60), 1.1))
        for suffix, view, lens, margin in views:
            S.render_preview(ob, os.path.join(args.out, name + suffix + ".png"), view, args.samples,
                             lens=lens, margin=margin)
            clear_rig()
    return ob


def run(name):
    args = parse_args()
    S.reset_scene()
    finish(name, BUILDERS[name](), args)


# =========================================================================== 1. nameplate

def build_nameplate():
    walnut = wood("M_Walnut", (0.13, 0.066, 0.036), dark=(0.085, 0.04, 0.02), light=(0.16, 0.085, 0.048),
                  roughness=0.42, scale=170)
    label = S.material("M_Label_Name", (0.55, 0.40, 0.26), 0.6)
    W, H, D, R = 12.0, 4.2, 3.4, 0.15          # Y, Z, X; round-over radius
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, 0, H / 2)) @ Matrix.Diagonal((D, W, H, 1)))
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=R, segments=5, profile=0.5, affect="EDGES",
                    clamp_overlap=True)
    block = S.obj_from_bm(bm, "block", walnut)

    # The name decal: the front face's 12 x 4.2 cm, 0.2 mm off the surface everywhere (it follows the
    # round-overs, so no edge of it floats); UV is the planar projection seen from the front.
    off = 0.02
    hx, hy, hz = D / 2, W / 2, H / 2
    n_edge = 6
    band = [R * math.sin(math.pi / 2 * k / n_edge) for k in range(n_edge + 1)]
    ys = [-hy + R - b for b in reversed(band)] + [0.0] + [hy - R + b for b in band]
    zs = [R - b for b in reversed(band)] + [hz] + [H - R + b for b in band]

    def P(y, z):
        dy = max(0.0, abs(y) - (hy - R))
        dz = max(0.0, abs(z - hz) - (hz - R))
        if dy > 0 and dz > 0:                     # corner: square -> quarter disc
            m, ln = max(dy, dz), math.hypot(dy, dz)
            dy, dz = dy * m / ln, dz * m / ln
            y = math.copysign(hy - R + dy, y)
            z = hz + math.copysign(hz - R + dz, z - hz)
        x = hx - R + math.sqrt(max(0.0, (R + off) ** 2 - dy * dy - dz * dz))
        return Vector((x, y, z)), ((y + hy) / W, z / H)

    decal = surface_grid("name", ys, zs, P, label, None)
    parts = [finalize(block, Y), finalize(decal)]
    return dict(parts=parts, front=(1, 0, 0.12), sharp=40)


# =========================================================================== 2. desk calendar

def build_desk_calendar():
    stand_m = S.material("M_CalStand", (0.018, 0.018, 0.02), 0.45, metallic=0.35)
    wire_m = S.material("M_Wire", (0.82, 0.82, 0.84), 0.2, metallic=1.0)
    paper = S.material("M_Paper", (0.84, 0.82, 0.78), 0.85)
    label = S.material("M_Label_Calendar", (0.92, 0.92, 0.9), 0.8)

    CW, CH = 10.0, 12.0                       # card width (Y) and height
    LEAN, LEG = math.radians(15), math.radians(20)
    R, WR, TW = 0.44, 0.04, 0.085             # wire-o ring radius, wire radius, twin half-spacing
    NH, PITCH = 11, 0.847                     # 3:1 pitch
    HW, HH, HTOP = 0.34, 0.30, 0.31           # hole width, height, gap above the hole
    TS = 0.12                                 # stand sheet thickness
    holes = [(i - (NH - 1) / 2) * PITCH for i in range(NH)]
    cols = [-CW / 2] + [y + s * HW / 2 for y in holes for s in (-1, 1)] + [CW / 2]
    rows = [0.0, CH - HTOP - HH, CH - HTOP, CH]
    bh = CH - HTOP - HH / 2                   # hole centre, from the card bottom

    def hole_mask(i, j):
        return not (j == 1 and i % 2 == 1)

    yax = Vector((0, 1, 0))

    def card(name, d, x_c, t, is_label):
        """A card hanging from the ring (axis = the origin, along Y): `d` is its downward direction,
        x_c its offset along the card normal; its holes sit on the ring."""
        d = Vector(d).normalized()
        n = yax.cross(-d)
        s_h = math.sqrt(R * R - x_c * x_c)

        def surf(a, b):
            return n * x_c + yax * a + d * (s_h + bh - b), n
        mats = [label, paper] if is_label else [paper]
        return sheet(name, cols, rows, surf, t, mats, front=0, back=len(mats) - 1, side=len(mats) - 1,
                     mask=hole_mask, label_uv=(lambda a, b: ((a + CW / 2) / CW, b / CH)) if is_label else None)

    d_pad = (math.sin(LEAN), 0, -math.cos(LEAN))
    d_leg = (-math.sin(LEG), 0, -math.cos(LEG))
    pad = [card("page_front", d_pad, 0.34, 0.03, True),
           card("pad_1", d_pad, 0.27, 0.09, False),
           card("pad_2", d_pad, 0.17, 0.09, False),
           card("pad_3", d_pad, 0.07, 0.09, False)]
    # flipped pages hang behind the stand's leg (their printed side towards it)
    flipped = [card(f"flipped_{k}", d_leg, -off, 0.03, False) for k, off in enumerate((0.21, 0.25, 0.29))]

    # lift everything so the lowest page stands 0.3 mm above the stand's base
    min_z = min(v.co.z for c in pad for v in c.data.vertices)
    z_ax = TS + 0.03 - min_z
    transform(pad + flipped, Matrix.Translation((0, 0, z_ax)))
    x_front = max(v.co.x for c in pad for v in c.data.vertices if v.co.z < 1.0)

    # ---- the stand: one bent sheet, lip -> base -> leg up into the ring
    leg_top = Vector((0.0, z_ax + 0.36))                   # (x, z), inside the ring
    x_foot = leg_top.x - (leg_top.y - TS / 2) * math.tan(LEG)
    x_lip = x_front + 0.05 + TS / 2
    corners = [(x_lip, 0.75), (x_lip, TS / 2), (x_foot, TS / 2), tuple(leg_top)]
    path = fillet(corners, [0, 0.15, 0.3, 0], [0, 5, 6, 0])
    lens_ = [0.0]
    for p, q in zip(path, path[1:]):
        lens_.append(lens_[-1] + (q - p).length)
    total = lens_[-1]
    nrm2 = []
    for k in range(len(path)):
        tng = (path[min(k + 1, len(path) - 1)] - path[max(k - 1, 0)]).normalized()
        nrm2.append(Vector((tng.y, -tng.x)))

    def surf_stand(a, b):
        b = max(0.0, min(total, b))
        k = max(i for i in range(len(lens_) - 1) if lens_[i] <= b + 1e-9) if b < total else len(lens_) - 2
        f = (b - lens_[k]) / max(lens_[k + 1] - lens_[k], 1e-9)
        p = path[k].lerp(path[k + 1], f)
        n = nrm2[k].lerp(nrm2[k + 1], f).normalized()
        return Vector((p.x, a, p.y)), Vector((n.x, 0, n.y))

    SW, CR = 10.6, 0.15                     # stand width, corner radius
    WIN = (total - 1.05, total - 0.5)       # window in the leg where the ring passes through it
    s_cols = corner_axis(-SW / 2, SW / 2, CR, 2, 1)
    s_cols = uniq(s_cols + [-4.55, 4.55])
    s_rows = uniq(lens_ + [CR / 2, CR, total - CR, total - CR / 2, WIN[0], WIN[1]], 1e-3)

    def win_mask(i, j):
        a = (s_cols[i] + s_cols[i + 1]) / 2
        b = (s_rows[j] + s_rows[j + 1]) / 2
        return not (abs(a) < 4.55 and WIN[0] < b < WIN[1])
    stand = sheet("stand", s_cols, s_rows, surf_stand, TS, [stand_m], mask=win_mask, corner_r=CR)
    bevel_sharp(stand, 0.035, 2)

    # ---- twin-loop wire: one continuous wire, two parallel loops per hole, tips and spine at the top
    th0, span, nseg, c = math.radians(110), math.radians(335), 12, 0.06

    def ring(w, y):                       # w = arc length round the ring from angle 0 (front)
        th = w / R
        return (R * math.cos(th), y, z_ax + R * math.sin(th))
    w0, w1 = R * th0, R * (th0 + span)
    pts = []
    for i, yc in enumerate(holes):
        yl, yr = yc - TW, yc + TW
        pts += [ring(w0 + (w1 - w0) * k / nseg, yl) for k in range(nseg + 1)]
        pts += [ring(w1 + TW * math.sin(math.pi * k / 4), yc - TW * math.cos(math.pi * k / 4)) for k in range(1, 4)]
        pts += [ring(w1 - (w1 - w0) * k / nseg, yr) for k in range(nseg + 1)]
        if i < NH - 1:
            yn = holes[i + 1] - TW
            for k in range(1, 3):        # quarter turn into the spine
                a = math.pi / 2 * k / 2
                pts.append(ring(w0 - c * math.sin(a), yr + c - c * math.cos(a)))
            for k in range(0, 2):        # quarter turn out of it
                a = math.pi / 2 * (1 - k / 2)
                pts.append(ring(w0 - c * math.sin(a), yn - c + c * math.cos(a)))
    prof = [(WR * math.cos(2 * math.pi * k / 6), WR * math.sin(2 * math.pi * k / 6)) for k in range(6)]
    wire = S.sweep("wire", pts, prof, wire_m, hint=(0, 1, 0))

    parts = [finalize(p) for p in pad + flipped] + [finalize(stand, Y), finalize(wire, Y)]
    return dict(parts=parts, front=(1, 0, 0.12), sharp=40, close=((1.0, 0.55, 0.9), 120, 1.0))


# =========================================================================== 3. terminal display

def build_terminal_display():
    case_m = S.material("M_Case", (0.016, 0.016, 0.018), 0.38, metallic=0.7)
    label = S.material("M_Label_Terminal", (0.02, 0.04, 0.03), 0.3)
    glass_m = glass("M_ScreenGlass")
    W, H, D, TILT = 24.0, 7.0, 6.0, math.radians(8)
    SW, SH = 21.0, 4.5
    xt = D / 2 - H * math.tan(TILT)          # the face's top edge; it leans back, looking slightly up
    prof = [(-D / 2, 0), (D / 2, 0), (xt, H), (-D / 2, H)]
    bm = bmesh.new()
    left = [bm.verts.new((x, -W / 2, z)) for x, z in prof]
    right = [bm.verts.new((x, W / 2, z)) for x, z in prof]
    for k in range(4):
        k2 = (k + 1) % 4
        bm.faces.new((left[k], left[k2], right[k2], right[k]))
    bm.faces.new(list(reversed(left)))
    bm.faces.new(right)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.22, segments=4, profile=0.5, affect="EDGES",
                    clamp_overlap=True)
    bm.normal_update()
    nface = Vector((math.cos(TILT), 0, math.sin(TILT)))
    up = Vector((-math.sin(TILT), 0, math.cos(TILT)))
    front = max((f for f in bm.faces if f.normal.dot(nface) > 0.999), key=lambda f: f.calc_area())
    c = front.calc_center_median()
    bmesh.ops.inset_individual(bm, faces=[front], thickness=0.6, depth=0.0)
    for v in front.verts:                    # the opening: exactly the screen, centred on the face
        rel = v.co - c
        v.co = c + Vector((0, math.copysign(SW / 2, rel.y), 0)) + math.copysign(SH / 2, rel.dot(up)) * up
    lip = list(front.edges)
    ret = bmesh.ops.extrude_face_region(bm, geom=[front])
    new_v = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
    new_f = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMFace)]
    if front.is_valid:
        bmesh.ops.delete(bm, geom=[front], context="FACES_ONLY")
    bmesh.ops.translate(bm, verts=new_v, vec=-nface * 0.12)       # screen 1.2 mm behind the bezel
    vset = set(new_v)
    screen = next(f for f in new_f if all(v in vset for v in f.verts))
    screen.material_index = 1
    sc = screen.calc_center_median()
    uvl = bm.loops.layers.uv.new("UVMap")
    for loop in screen.loops:
        rel = loop.vert.co - sc
        loop[uvl].uv = ((rel.y + SW / 2) / SW, (rel.dot(up) + SH / 2) / SH)
    bmesh.ops.bevel(bm, geom=[e for e in lip if e.is_valid], offset=0.03, segments=2, profile=0.5,
                    affect="EDGES", clamp_overlap=True)
    case = S.obj_from_bm(bm, "case", case_m)
    case.data.materials.append(label)
    # the glass pane: 0.4 mm thick, its back 0.5 mm in front of the screen, 0.3 mm short of the walls
    pane = box_part("pane", sc + nface * 0.07, ((0, 1, 0), up, nface), (SW - 0.06, SH - 0.06, 0.04), glass_m)
    parts = [finalize(case, Y), finalize(pane, Y)]
    return dict(parts=parts, front=(1, 0, 0.0), sharp=40)


# =========================================================================== 4. polaroid

def build_polaroid():
    label = S.material("M_Label_Polaroid", (0.9, 0.9, 0.88), 0.45)
    back = S.material("M_PolaroidBack", (0.035, 0.035, 0.038), 0.55)
    W, H, T, BOW, R = 8.8, 10.7, 0.08, 0.2, 0.15
    cols = corner_axis(-W / 2, W / 2, R, 2, 8)
    rows = corner_axis(0, H, R, 2, 1)

    def P(a, b):                            # bowed across its width, the middle 2 mm back
        return (-BOW * (1 - (2 * a / W) ** 2), a, b)
    ob = sheet("print", cols, rows, surf_fd(P), T, [label, back], front=0, back=1, side=1, corner_r=R,
               label_uv=lambda a, b: ((a + W / 2) / W, b / H))
    return dict(parts=[finalize(ob, Z)], front=(1, 0, 0.05), sharp=40, lens=70)


# =========================================================================== 5. sticky note

def build_sticky_note():
    label = S.material("M_Label_Sticky", (0.96, 0.84, 0.28), 0.7)
    back = S.material("M_StickyBack", (0.88, 0.74, 0.2), 0.75)
    A, T = 7.6, 0.01
    h = A / 2
    ADH, CURL, LIFT, SEP = 1.7, 3.0, 0.5, 0.03    # adhesive band, curl length, curl lift, gentle separation

    def curl_xz(s, k, n=48):
        """Arc length s into the curl -> (forward, down) with curvature growing linearly (phi = k s^2 / 2)."""
        x = z = 0.0
        ds = s / n
        for i in range(n):
            phi = k * ((i + 0.5) * ds) ** 2 / 2
            x += math.sin(phi) * ds
            z += math.cos(phi) * ds
        return x, z
    lo_k, hi_k = 0.0, 2.0
    for _ in range(40):                        # tune k so the bottom edge lifts LIFT
        mid = (lo_k + hi_k) / 2
        lo_k, hi_k = (mid, hi_k) if curl_xz(CURL, mid)[0] < LIFT else (lo_k, mid)
    k0 = (lo_k + hi_k) / 2
    top_flat, b_c = h - ADH, -h + CURL

    def P(a, b):
        x = 0.0
        if b < top_flat:                      # below the adhesive the paper stands off a little
            t = min(1.0, (top_flat - b) / (top_flat - b_c))
            x = SEP * t * t * (3 - 2 * t)
        if b < b_c:
            xs, zs = curl_xz(b_c - b, k0 * (1 + 0.18 * (a / h) ** 2))   # corners curl a touch more
            return (x + xs, a, b_c - zs)
        return (x, a, b)
    cols = [-h + A * k / 6 for k in range(7)]
    rows = uniq([b_c - CURL * (1 - k / 12) for k in range(12)] +
                [b_c + (top_flat - b_c) * k / 4 for k in range(5)] + [top_flat + ADH * k / 2 for k in range(3)])
    ob = sheet("note", cols, rows, surf_fd(P), T, [label, back], front=0, back=1, side=1,
               label_uv=lambda a, b: ((a + h) / A, (b + h) / A))
    return dict(parts=[finalize(ob, Z)], origin=(0, 0, 0), front=(1, 0, 0.0), sharp=40, lens=70)


# =========================================================================== 6. framed print

def build_framed_print():
    oak = wood("M_Oak", (0.50, 0.34, 0.19), dark=(0.42, 0.27, 0.14), light=(0.58, 0.40, 0.235),
               roughness=0.5, scale=150)
    mat_m = S.material("M_Mat", (0.86, 0.855, 0.82), 0.9)
    glass_m = glass("M_Glass")
    label = S.material("M_Label_Print", (0.6, 0.5, 0.4), 0.7)
    W, H, D = 21.0, 26.0, 2.0
    FW, RAB, LIP = 1.4, 0.9, 0.6            # moulding face width, rabbet edge, lip depth before the glass
    AW, AH, ARAISE = 13.0, 18.0, 0.25       # artwork and how much its window sits above centre

    # moulding profile, (a = in from the outer edge, b = depth from the back), counter-clockwise
    pc = [(0, 0), (RAB, 0), (RAB, D - LIP), (FW, D - LIP), (FW, D), (0, D)]
    prof = fillet(pc, [0.05, 0.04, 0.02, 0.03, 0.09, 0.16], [2, 2, 1, 2, 4, 6], closed=True)
    bm = bmesh.new()
    outer = [(-W / 2, 0, 1, 1), (W / 2, 0, -1, 1), (W / 2, H, -1, -1), (-W / 2, H, 1, -1)]
    rings = [[bm.verts.new((b - D / 2, cy + a * dy, cz + a * dz)) for a, b in prof] for cy, cz, dy, dz in outer]
    n = len(prof)
    for k in range(4):
        r0, r1 = rings[k], rings[(k + 1) % 4]
        for i in range(n):
            i2 = (i + 1) % n
            bm.faces.new((r0[i], r0[i2], r1[i2], r1[i]))
    frame = S.obj_from_bm(bm, "frame", oak)

    # glass, mat, art, backing from the front back, in the rabbet
    PW, PH = W - 2 * RAB - 0.1, H - 2 * RAB - 0.1
    x_of = lambda b: b - D / 2                                           # noqa: E731
    zc = H / 2
    ax = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    glass_p = box_part("glass", (x_of(1.28), 0, zc), ax, (0.2, PW, PH), glass_m)
    backing = box_part("backing", (x_of(0.79), 0, zc), ax, (0.3, PW, PH), mat_m)
    az = zc + ARAISE
    bm = bmesh.new()
    M_FRONT, M_BACK, BEV = 1.15, 1.00, 0.15
    loops = []
    for b, hw, hh, cz in ((M_FRONT, PW / 2, PH / 2, zc), (M_FRONT, AW / 2 + BEV, AH / 2 + BEV, az),
                          (M_BACK, AW / 2, AH / 2, az), (M_BACK, PW / 2, PH / 2, zc)):
        loops.append([bm.verts.new((x_of(b), sy * hw, cz + sz * hh))
                      for sy, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    for l0, l1 in zip(loops, loops[1:] + loops[:1]):
        for k in range(4):
            k2 = (k + 1) % 4
            bm.faces.new((l0[k], l0[k2], l1[k2], l1[k]))
    mat_p = S.obj_from_bm(bm, "mat", mat_m)
    bm, uvl = new_bm()
    vs = [bm.verts.new((x_of(0.97), sy * AW / 2, az + sz * AH / 2)) for sy, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    f = bm.faces.new(vs)
    for loop, (u, v) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uvl].uv = (u, v)
    art = to_obj(bm, "art", [label])

    def member_grain(f):                     # top and bottom rails along Y, stiles along Z
        c = f.calc_center_median() / CM
        dist = (c.z, H - c.z, c.y + W / 2, W / 2 - c.y)
        return Y if min(range(4), key=lambda i: dist[i]) < 2 else Z
    parts = [finalize(frame, member_grain), finalize(glass_p), finalize(backing), finalize(mat_p), finalize(art)]
    transform(parts, Matrix.Rotation(math.radians(-8), 4, "Y"))     # lean back 8 degrees
    return dict(parts=parts, front=(1, 0, 0.1), sharp=40)


BUILDERS = {
    "nameplate": build_nameplate,
    "desk_calendar": build_desk_calendar,
    "terminal_display": build_terminal_display,
    "polaroid": build_polaroid,
    "sticky_note": build_sticky_note,
    "framed_print": build_framed_print,
}


# =========================================================================== combo

def run_combo():
    """All six at real scale on a light-oak surface."""
    args = parse_args()
    S.reset_scene()
    obs = {name: assemble(name, build()) for name, build in BUILDERS.items()}

    def place(name, loc, rz=0.0, extra=None):
        m = Matrix.Translation(Vector(loc) * CM) @ Matrix.Rotation(math.radians(rz), 4, "Z")
        if extra is not None:
            m = m @ extra
        obs[name].data.transform(m)
        obs[name].data.update()

    # the polaroid leans back 14 degrees against the display's face: fit it in the display's own frame
    pol, disp = obs["polaroid"].data, obs["terminal_display"].data
    pol.transform(Matrix.Translation((0, 0.05, 0)) @ Matrix.Rotation(math.radians(-14), 4, "Y"))
    pol.transform(Matrix.Translation((0, 0, -min(v.co.z for v in pol.vertices))))
    zt = max(v.co.z for v in pol.vertices)
    xb0 = min(v.co.x for v in pol.vertices if v.co.z < 0.001)
    xt0 = min(v.co.x for v in pol.vertices if v.co.z > zt - 0.001)

    def pol_back(z):                         # the polaroid's rearmost x at height z: its back is straight up its height
        return xb0 + (xt0 - xb0) * z / zt
    gap = max(v.co.x - pol_back(v.co.z) for v in disp.vertices if v.co.z > 0.02 and v.co.x > 0)
    pol.transform(Matrix.Translation((gap + 0.0008, 0, 0)))
    pol.update()
    place("framed_print", (-9, -17, 0), 6)
    place("terminal_display", (-10, 8, 0), -4)
    place("polaroid", (-10, 8, 0), -4)
    place("nameplate", (6, -8, 0), -10)
    place("desk_calendar", (4, 6, 0), -18)
    place("sticky_note", (9, 18, 0.005), 14, Matrix.Rotation(math.radians(-90), 4, "Y"))
    obs["sticky_note"].data.transform(Matrix.Translation(
        (0, 0, -min(v.co.z for v in obs["sticky_note"].data.vertices))))

    oak = wood("M_SurfaceOak", (0.52, 0.36, 0.2), dark=(0.42, 0.28, 0.15), light=(0.60, 0.42, 0.26),
               roughness=0.45, scale=110)
    slab = box_part("surface", (0, 0, -1.25), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (40, 64, 2.5), oak)
    S.bevel(slab, 0.2, 3)
    finalize(slab, Y)

    lo = Vector((min(S.bbox(o)[0][i] for o in obs.values()) for i in range(3)))
    hi = Vector((max(S.bbox(o)[1][i] for o in obs.values()) for i in range(3)))
    proxy = box_part("_frame", (lo + hi) / 2 / CM, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (hi - lo) / CM, oak)
    proxy.data.transform(Matrix.Scale(CM, 4))
    proxy.hide_render = True
    if not args.no_render:
        preview_labels()
        os.makedirs(args.out, exist_ok=True)
        S.render_preview(proxy, os.path.join(args.out, "labels_combo.png"), (1.0, 0.62, 0.62), args.samples,
                         lens=50, margin=1.05, floor=False)
