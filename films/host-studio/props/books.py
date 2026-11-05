"""books: the books on the studio shelves, three arrangements, one mesh each.

  books_main   one row (~67 cm): 5 plain books, the owner's 7 dark-green hardcovers (a label slot
               on each spine, M_Label_Spine1..7, left to right), 6 cream books, the last leaning left.
  books_low    a looser row of 16 assorted books for the lowest shelf (~50 cm), the last two leaning.
  books_stack  three hardcovers lying flat, largest at the bottom.

Books stand on z = 0 with their spines facing +X. The rows' origin is at the bottom, at the row's
centre in Y, with the books' back edges (fore-edges) at x = 0; the stack's at its bottom centre.

Every book is built the same way: a cover "case" (boards + spine, one closed C-shaped cross-section
extruded up the book) around a separate page block. Hardcovers have 2.5 mm boards overhanging the
page block by 3 mm, a slightly rounded spine, hinge grooves and a concave fore-edge; paperbacks have
a thin flush cover and a flat spine. The page block's top and fore-edge carry faint page lines
(tiny per-leaf offsets). Every hard edge gets a 0.8 mm bevel (page blocks 0.6 mm).

    blender -b --factory-startup -P films/host-studio/props/books.py -- --out films/host-studio/props/out
    (--only books_main to build one of them)
"""
import argparse
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

CM = 0.01
BEVEL = 0.08        # cm, covers
BEVEL_PAGES = 0.06  # cm, page blocks
SHARP = 12          # degrees: bevel facets are hard, curved spines / grooves / page lines smooth

FULL = {"spine": 12, "groove": 10, "pitch": 0.10, "segs": 3}
STACK = dict(FULL, segs=2)    # fits the 5k budget

PROPS = ("books_main", "books_low", "books_stack")


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="books")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--samples", type=int, default=48)
    ap.add_argument("--only", choices=PROPS, action="append")
    ap.add_argument("--debug", action="store_true", help="extra detail renders (_debug_*.png)")
    return ap.parse_args(argv)


# --------------------------------------------------------------------------- materials

COVER_COLOURS = {   # linear base colour, roughness
    "cream": ((0.74, 0.655, 0.50), 0.72),
    "white": ((0.83, 0.81, 0.76), 0.65),
    "grey": ((0.20, 0.196, 0.18), 0.88),
    "black": ((0.022, 0.022, 0.024), 0.62),
    "navy": ((0.018, 0.030, 0.062), 0.80),
    "sage": ((0.29, 0.35, 0.235), 0.80),
    "green": ((0.026, 0.062, 0.040), 0.80),
    "terracotta": ((0.42, 0.105, 0.048), 0.78),
}
CLOTH = (0.019, 0.050, 0.030)   # the owner's dark bottle-green cloth
PAGES = (0.76, 0.68, 0.53)


def add_grain(m, scale, strength):
    """Preview only: a fine noise bump so cloth and paper don't look like plastic."""
    try:
        nt = m.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = scale
        nz.inputs["Detail"].default_value = 3.0
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = strength
        if "Distance" in bump.inputs:
            bump.inputs["Distance"].default_value = 0.0002
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    except Exception as e:  # never fail a build over preview shading
        print("grain:", e)
    return m


def page_lines(m):
    """Preview only: fine leaf lines across the page block (the mesh has coarser ones built in)."""
    try:
        nt = m.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        tc = nt.nodes.new("ShaderNodeTexCoord")
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.bands_direction = "Y"
        wave.inputs["Scale"].default_value = 1500
        wave.inputs["Distortion"].default_value = 2.0
        ramp = nt.nodes.new("ShaderNodeMapRange")
        ramp.inputs["To Min"].default_value = 0.88
        ramp.inputs["To Max"].default_value = 1.0
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs["A"].default_value = (*PAGES, 1)
        nt.links.new(tc.outputs["UV"], wave.inputs["Vector"])
        nt.links.new(wave.outputs["Fac"], ramp.inputs["Value"])
        nt.links.new(ramp.outputs["Result"], mix.inputs["B"])
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    except Exception as e:
        print("page_lines:", e)
    return m


_mats = {}


def mat(key):
    """Material by key: a COVER_COLOURS name, 'cloth', 'pages' or 'label1'..'label7'."""
    if key in _mats:
        return _mats[key]
    if key in COVER_COLOURS:
        col, rough = COVER_COLOURS[key]
        m = add_grain(S.material("M_Book_" + key.capitalize(), col, rough), 1800, 0.025)
    elif key == "cloth":
        m = add_grain(S.material("M_GreenCloth", CLOTH, 0.78), 3000, 0.18)
    elif key == "pages":
        m = page_lines(S.material("M_Pages", PAGES, 0.85))
    elif key.startswith("label"):
        # In the preview the label slots look like the cloth they will be printed on.
        m = add_grain(S.material("M_Label_Spine" + key[5:], CLOTH, 0.78), 3000, 0.18)
    else:
        raise KeyError(key)
    _mats[key] = m
    return m


# --------------------------------------------------------------------------- one book

class Book:
    """A book standing on z = 0, back (fore-edge) at local x = 0, spine at x = d, centred on y = 0.

    Sizes in cm. kind 'hard' (boards, rounded spine, grooves) or 'paper'. label: 1..7 for a label
    slot on the spine. bands: [(z0, z1, cover key)] spine bands in another tone."""

    def __init__(self, cover, h, d, t, kind="hard", label=None, bands=(), x=0.0):
        self.cover, self.h, self.d, self.t, self.kind = cover, h, d, t, kind
        self.label, self.bands, self.x = label, list(bands), x


def case_outline(b, res):
    """Closed C-shaped cross-section (x, y) of the cover: boards + spine, outer then inner path."""
    D, t = b.d, b.t / 2
    if b.kind == "hard":
        bt, sag, csp, groove = 0.25, 0.13, 0.20, True
    else:
        bt, sag, csp, groove = 0.06, 0.03, 0.08, False
    ns = res["spine"]

    def side(sign):
        pts = [(0.0, sign * t)]
        if groove:   # hinge groove: a soft dip in the board just behind the spine
            xg, gw, gd = D - sag - 0.75, 0.24, 0.10
            ng = res["groove"]
            for k in range(ng + 1):
                x = xg - gw + 2 * gw * k / ng
                pts.append((x, sign * (t - gd * 0.5 * (1 + math.cos(math.pi * (x - xg) / gw)))))
        pts.append((D - sag, sign * t))
        return pts

    out = side(-1)
    for k in range(1, ns):
        y = -t + 2 * t * k / ns
        out.append((D - sag * (y / t) ** 2, y))
    out += list(reversed(side(1)))
    ti = t - bt
    inner = [(0.0, ti)]
    for k in range(ns + 1):
        y = ti - 2 * ti * k / ns
        inner.append((D - csp - sag * (y / ti) ** 2, y))
    inner.append((0.0, -ti))
    geo = dict(sag=sag, ti=ti, xin=D - csp, ov=0.30 if b.kind == "hard" else 0.03,
               gap=0.04 if b.kind == "hard" else 0.02)
    return out + inner, geo


def add_case(bm, b, res):
    outline, geo = case_outline(b, res)
    zs = sorted({0.0, b.h} | {z for z0, z1, _ in b.bands for z in (z0, z1)})
    rings = [[bm.verts.new((x, y, z)) for x, y in outline] for z in zs]
    n = len(outline)
    for a, c in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], c[j], c[i])).material_index = 0
    bm.faces.new(list(reversed(rings[0]))).material_index = 0
    bm.faces.new(rings[-1]).material_index = 0
    return geo


def add_pages(bm, b, geo, res, rng):
    """Page block as columns across the thickness; each leaf group is nudged a hair in or out."""
    pw = geo["ti"] - 0.03
    ov, sag, ti = geo["ov"], geo["sag"], geo["ti"]
    conc = sag if b.kind == "hard" else 0.0      # rounded back -> concave fore-edge
    n = max(6, int(round((2 * pw - 0.4) / res["pitch"])))
    ys = [-pw] + [-pw + 0.2 + (2 * pw - 0.4) * k / n for k in range(n + 1)] + [pw]
    amp = 0.011
    z0, z1 = ov, b.h - ov
    cols = []
    for i, y in enumerate(ys):
        edge = i in (0, len(ys) - 1)
        r = 0.0 if edge else amp * rng.uniform(-1, 1)
        xf = ov + conc * (1 - (y / pw) ** 2) + r + amp
        xb = geo["xin"] - sag * (y / ti) ** 2 - geo["gap"]
        zt = z1 - amp - (0.0 if edge else 0.7 * abs(r))
        cols.append((bm.verts.new((xf, y, z0)), bm.verts.new((xf, y, zt)),
                     bm.verts.new((xb, y, zt)), bm.verts.new((xb, y, z0))))
    for a, c in zip(cols, cols[1:]):
        for k in range(4):
            k2 = (k + 1) % 4
            bm.faces.new((a[k], a[k2], c[k2], c[k])).material_index = 1
    bm.faces.new(cols[0]).material_index = 1
    bm.faces.new(list(reversed(cols[-1]))).material_index = 1


def bevelled(bm, nmats, width, segs=2, angle=30):
    """Run a Bevel modifier over the bmesh (via a temporary object); returns a new bmesh."""
    me = bpy.data.meshes.new("_tmp")
    bm.to_mesh(me)
    bm.free()
    for _ in range(nmats):
        me.materials.append(None)
    ob = bpy.data.objects.new("_tmp", me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = segs
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(angle)
    mod.use_clamp_overlap = True
    dg = bpy.context.evaluated_depsgraph_get()
    me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(me)
    out = bmesh.new()
    out.from_mesh(me2)
    bpy.data.meshes.remove(me2)
    return out


def build_book(b, res, rng):
    """The book as a bmesh in local cm, bevelled, with material indices into the returned keys."""
    case = bmesh.new()
    geo = add_case(case, b, res)
    case = bevelled(case, 1, BEVEL, res["segs"])
    pages = bmesh.new()
    add_pages(pages, b, geo, res, rng)
    pages = bevelled(pages, 2, BEVEL_PAGES)

    keys = ["cloth" if b.label else b.cover, "pages"]
    bm = bmesh.new()
    for part in (case, pages):     # merge the two islands
        me = bpy.data.meshes.new("_tmp")
        part.to_mesh(me)
        part.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)

    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4],
                          quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    # Spine faces: the label slot, or bands.
    spine_x = b.d - geo["sag"] - 0.2
    band_idx = []
    for z0, z1, key in b.bands:
        if key not in keys:
            keys.append(key)
        band_idx.append((z0, z1, keys.index(key)))
    label_idx = None
    if b.label:
        keys.append("label%d" % b.label)
        label_idx = len(keys) - 1
    label_faces = []
    for f in bm.faces:
        if f.material_index != 0 or f.normal.x < 0.55:
            continue
        c = f.calc_center_median()
        if c.x < spine_x:
            continue
        if label_idx is not None:
            f.material_index = label_idx
            label_faces.append(f)
            continue
        for z0, z1, idx in band_idx:
            if z0 < c.z < z1:
                f.material_index = idx

    # UVs: world-scale box projection (1 UV = 1 m) in the book's own frame; label 0..1 on its face;
    # on the page edges (top, bottom, fore-edge) V always runs across the leaves.
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            if f.material_index == 1 and ax != 1:   # page edges: V across the leaves, U along them
                lp[uv].uv = ((p.z if ax == 0 else p.x) * CM, p.y * CM)
            elif ax == 0:
                lp[uv].uv = (p.y * CM, p.z * CM)
            elif ax == 1:
                lp[uv].uv = (p.x * CM, p.z * CM)
            else:
                lp[uv].uv = (p.x * CM, p.y * CM)
    label_size = None
    if label_faces:
        vs = {v for f in label_faces for v in f.verts}
        y0, y1 = min(v.co.y for v in vs), max(v.co.y for v in vs)
        z0, z1 = min(v.co.z for v in vs), max(v.co.z for v in vs)
        for f in label_faces:
            for lp in f.loops:
                p = lp.vert.co
                lp[uv].uv = ((p.y - y0) / (y1 - y0), (p.z - z0) / (z1 - z0))   # U -> +Y (screen right), V up
        label_size = (y1 - y0, z1 - z0)
    return bm, keys, label_size


def book_object(name, bm, keys, matrix_cm):
    """Place the book (matrix in cm), convert to metres and make an object."""
    bm.transform(Matrix.Scale(CM, 4) @ matrix_cm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for k in keys:
        me.materials.append(mat(k))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def drop_to_floor(ob):
    zmin = min(v.co.z for v in ob.data.vertices)
    ob.data.transform(Matrix.Translation((0, 0, -zmin)))


# --------------------------------------------------------------------------- rows

def build_row(books, lean_deg, leaners, res, seed, gaps=(0.05, 0.12)):
    """Books left to right (Blender -Y to +Y). The last `leaners` books lean left at lean_deg,
    the first of them against the last standing book, the others against it (parallel)."""
    rng = random.Random(seed)
    th = math.radians(lean_deg)
    objs, info = [], {}
    y = 0.0
    standing = books[:len(books) - leaners]
    for i, b in enumerate(standing):
        bm, keys, lab = build_book(b, res, rng)
        if i:
            y += rng.uniform(*gaps)
        objs.append(book_object("book%02d" % i, bm, keys, Matrix.Translation((b.x, y + b.t / 2, 0))))
        if lab:
            info.setdefault("labels", {})[b.label] = (lab, y, y + b.t, b)
        y += b.t
    if leaners:
        prev = standing[-1]
        pivot = y + prev.h * math.tan(th) + 0.08 / math.cos(th)
        for j, b in enumerate(books[len(standing):]):
            bm, keys, _ = build_book(b, res, rng)
            m = Matrix.Translation((b.x, pivot, 0)) @ Matrix.Rotation(th, 4, "X") @ \
                Matrix.Translation((0, b.t / 2, 0))
            ob = book_object("lean%d" % j, bm, keys, m)
            drop_to_floor(ob)
            objs.append(ob)
            pivot += b.t / math.cos(th) + 0.06
    return objs, info


def bounds(objs):
    vs = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    return lo, hi


def main_row():
    plain = [
        Book("cream", 21.6, 14.6, 3.2, "paper", bands=[(18.4, 18.7, "white")]),
        Book("cream", 22.8, 15.2, 3.2, "paper"),
        Book("grey", 24.6, 16.8, 3.4, "hard", bands=[(1.5, 1.8, "black"), (22.6, 22.9, "black")]),
        Book("black", 23.8, 16.0, 3.0, "hard"),
        Book("white", 21.0, 14.0, 1.8, "paper", bands=[(2.0, 3.2, "cream")]),
    ]
    green = [Book("cloth", 24.0, 16.5, 3.6, "hard", label=k + 1, x=1.5 if k == 2 else 0.0) for k in range(7)]
    cream = [
        Book("cream", 22.6, 15.6, 3.8, "hard"),
        Book("white", 21.2, 14.0, 3.0, "paper", bands=[(16.8, 17.0, "sage")]),
        Book("cream", 20.4, 13.6, 3.4, "paper", x=0.2),
        Book("white", 22.0, 15.0, 4.0, "hard"),
        Book("cream", 19.4, 13.2, 3.0, "paper"),
        Book("cream", 22.8, 15.2, 3.4, "hard"),        # leans left
    ]
    return plain + green + cream


def low_row():
    rng = random.Random(11)
    spec = [
        ("cream", 20.5, 13.5, 2.6, "paper", []),
        ("white", 21.8, 14.2, 2.0, "paper", []),
        ("navy", 24.2, 16.2, 3.2, "hard", [(1.4, 1.6, "cream"), (22.6, 22.8, "cream")]),
        ("black", 23.0, 15.5, 2.8, "hard", []),
        ("cream", 19.0, 12.8, 2.2, "paper", [(15.5, 16.4, "terracotta")]),
        ("cream", 22.4, 15.0, 3.4, "hard", []),
        ("white", 20.2, 13.4, 1.6, "paper", []),
        ("green", 24.8, 16.8, 3.0, "hard", [(2.0, 2.2, "black")]),
        ("sage", 22.0, 15.2, 2.8, "hard", []),
        ("cream", 18.4, 12.6, 2.2, "paper", []),
        ("terracotta", 21.0, 14.0, 2.6, "paper", []),
        ("black", 19.6, 13.0, 1.8, "paper", []),
        ("cream", 23.4, 15.8, 3.6, "hard", [(20.0, 20.3, "navy")]),
        ("white", 20.8, 13.8, 2.6, "paper", []),
        ("navy", 22.6, 15.4, 2.8, "hard", []),         # leans left
        ("cream", 21.4, 14.4, 2.4, "paper", []),       # leans on it
    ]
    books = []
    for i, (c, h, d, t, k, bands) in enumerate(spec):
        books.append(Book(c, h, d, t, k, bands=bands, x=0.0 if i == 0 else round(rng.uniform(0.0, 0.7), 2)))
    return books


# --------------------------------------------------------------------------- previews

def clear_preview():
    for o in list(bpy.data.objects):
        if o.name.startswith("_"):
            bpy.data.objects.remove(o, do_unlink=True)


FONT = {
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
}


def test_image(n, w=144, h=960):
    """UV test card for label n: border, grid, an up arrow, 'UP', the number, a right arrow at the foot."""
    import numpy as np
    img = np.zeros((h, w, 4), np.float32)   # row 0 = top while drawing
    img[...] = (0.93, 0.92, 0.88, 1.0)
    img[::48, :, :3] = 0.65
    img[:, ::48, :3] = 0.65
    red, blue, dark = (0.85, 0.08, 0.06), (0.08, 0.22, 0.85), (0.05, 0.05, 0.05)
    for sl in (np.s_[:6, :], np.s_[-6:, :], np.s_[:, :6], np.s_[:, -6:]):
        img[sl][..., :3] = red
    cx = w // 2
    for r in range(24, 120):                  # up arrow
        half = int((r - 24) * 0.75) if r < 76 else 9
        img[r, cx - half:cx + half + 1, :3] = blue

    def text(s, top, scale, colour):
        width = (len(s) * 6 - 1) * scale
        left = (w - width) // 2
        for i, ch in enumerate(s):
            for ry, row in enumerate(FONT[ch]):
                for rx, bit in enumerate(row):
                    if bit == "1":
                        y0, x0 = top + ry * scale, left + (i * 6 + rx) * scale
                        img[y0:y0 + scale, x0:x0 + scale, :3] = colour

    text("UP", 140, 7, dark)
    text(str(n), (h - 7 * 18) // 2, 18, dark)
    for c in range(20, w - 20):               # right arrow (U direction) near the foot
        img[h - 70:h - 62, c, :3] = red
    for k in range(24):
        img[h - 66 - (24 - k):h - 66 + (24 - k), w - 44 + k, :3] = red
    im = bpy.data.images.new("_uvtest%d" % n, w, h, alpha=True)
    im.pixels.foreach_set(img[::-1].ravel())
    return im


def label_test_materials(ob):
    for m in ob.data.materials:
        if not m.name.startswith("M_Label_Spine"):
            continue
        n = int(m.name[len("M_Label_Spine"):])
        nt = m.node_tree
        bsdf = next(nd for nd in nt.nodes if nd.type == "BSDF_PRINCIPLED")
        for link in list(bsdf.inputs["Normal"].links):
            nt.links.remove(link)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = test_image(n)
        tex.interpolation = "Closest"
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.6


def render_close(path, cam_loc, target, lens, samples):
    """Straight-on close-up: same neutral look as S.render_preview but a fixed camera."""
    sc = bpy.context.scene
    fm = S.material("_PreviewFloor", (0.18, 0.18, 0.18), 0.8)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=5, matrix=Matrix.Translation((0, 0, -0.0005)))
    S.obj_from_bm(bm, "_floor", fm)
    cam_loc, target = Vector(cam_loc), Vector(target)

    def area(name, loc, energy, size):
        light = bpy.data.lights.new(name, "AREA")
        light.shape = "DISK"
        light.size = size
        light.energy = energy
        o = bpy.data.objects.new(name, light)
        sc.collection.objects.link(o)
        o.location = loc
        o.rotation_euler = (target - Vector(loc)).to_track_quat("-Z", "Y").to_euler()

    area("_key", target + Vector((0.6, 0.45, 0.55)), 16, 0.8)
    area("_fill", target + Vector((0.7, -0.6, 0.15)), 6, 1.0)
    cd = bpy.data.cameras.new("_cam")
    cd.lens = lens
    cd.clip_start = 0.01
    cam = bpy.data.objects.new("_cam", cd)
    sc.collection.objects.link(cam)
    cam.location = cam_loc
    cam.rotation_euler = (target - cam_loc).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.eevee.taa_render_samples = samples
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def debug_views(name, lo, hi):
    """Close looks at the construction (top corners, spines, the leaning end)."""
    c = (lo + hi) / 2
    top = Vector((hi.x - 0.02, c.y - 0.05, hi.z - 0.01))
    end = Vector((c.x, hi.y - 0.06, 0.12))
    return [(top, (0.16, 0.10, 0.14)), (Vector((hi.x - 0.01, c.y - 0.05, 0.03)), (0.20, 0.14, 0.03)),
            (end, (0.30, 0.20, 0.10)), (Vector((c.x, lo.y + 0.08, hi.z)), (-0.10, 0.05, 0.25))]


def make(name, objs, origin, args, close=None):
    quiet = argparse.Namespace(**{**vars(args), "no_render": True})
    ob = S.finish(name, objs, origin=origin, view_dir=(1, 0.8, 0.55), args=quiet, sharp_angle=SHARP)
    if args.no_render:
        return ob
    S.render_preview(ob, os.path.join(args.out, name + ".png"), (1, 0.8, 0.55), args.samples, lens=60)
    clear_preview()
    S.render_preview(ob, os.path.join(args.out, name + "_front.png"), (1, 0, 0.06), args.samples, lens=60)
    clear_preview()
    if args.debug:
        lo, hi = S.bbox(ob)
        for k, (tgt, off) in enumerate(debug_views(name, lo, hi)):
            render_close(os.path.join(args.out, "_debug_%s_%d.png" % (name, k)), Vector(tgt) + Vector(off), tgt,
                         50, samples=args.samples)
            clear_preview()
    if close:
        label_test_materials(ob)
        render_close(os.path.join(args.out, name + "_close.png"), *close, samples=args.samples)
        clear_preview()
    return ob


# --------------------------------------------------------------------------- props

def books_main(args):
    objs, info = build_row(main_row(), 12, 1, FULL, seed=3, gaps=(0.08, 0.20))
    lo, hi = bounds(objs)
    origin = Vector((0, (lo.y + hi.y) / 2, 0))
    labels = info["labels"]
    print("books_main: label slots (cm, face width x height):")
    for n in sorted(labels):
        (w, h), y0, y1, b = labels[n]
        print(f"  M_Label_Spine{n}: {w:.2f} x {h:.2f}  y {y0 - origin.y / CM:.2f}..{y1 - origin.y / CM:.2f}")
    ys = [labels[n][1] for n in labels] + [labels[n][2] for n in labels]
    gy = (min(ys) + max(ys)) / 2 * CM - origin.y
    spine = 16.5 * CM
    close = ((spine + 0.45, gy, 0.12), (spine, gy, 0.12), 45)
    make("books_main", objs, origin, args, close)


def books_low(args):
    objs, _ = build_row(low_row(), 14, 2, FULL, seed=5, gaps=(0.04, 0.25))
    lo, hi = bounds(objs)
    make("books_low", objs, Vector((0, (lo.y + hi.y) / 2, 0)), args)


def books_stack(args):
    rng = random.Random(7)
    spec = [   # cover, length (spine), depth, thickness, yaw deg, offset x/y cm
        ("cream", 22.0, 16.0, 3.2, -1.5, (0.0, 0.0)),
        ("grey", 20.0, 14.5, 2.8, 3.0, (0.35, -0.3)),
        ("black", 18.0, 13.0, 2.5, -1.8, (0.6, 0.4)),
    ]
    objs, z = [], 0.0
    for i, (c, h, d, t, yaw, (ox, oy)) in enumerate(spec):
        b = Book(c, h, d, t, "hard")
        bm, keys, _ = build_book(b, STACK, rng)
        m = Matrix.Translation((ox, oy, z + t / 2)) @ Matrix.Rotation(math.radians(yaw), 4, "Z") @ \
            Matrix.Rotation(math.radians(90), 4, "X") @ Matrix.Translation((-d / 2, 0, -h / 2))
        objs.append(book_object("stack%d" % i, bm, keys, m))
        z += t + 0.02
    lo, hi = bounds(objs)
    make("books_stack", objs, Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0)), args)


def main():
    args = parse_args()
    for name in args.only or PROPS:
        S.reset_scene()
        _mats.clear()
        for im in list(bpy.data.images):
            if im.name.startswith("_uvtest"):
                bpy.data.images.remove(im)
        globals()[name](args)


main()
