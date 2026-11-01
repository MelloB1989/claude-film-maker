"""_accessories — helpers shared by the presenter's worn props (hoop_earring.py, smartwatch.py).

Geometry is built in millimetres (these props are tiny) and scaled to metres by `mm_obj`, so every
UV written here is already in metres (1 UV unit = 1 m) unless it is a label UV (0..1).
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as SM  # noqa: E402

MM = 0.001
TAU = 2 * math.pi


# --------------------------------------------------------------------------- mesh building

def new_bm():
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    return bm, uvl


def to_obj(bm, name, mats, scale=MM):
    """bmesh in mm -> object in metres (UVs untouched: write them in metres already)."""
    bm.transform(Matrix.Scale(scale, 4))
    return SM.obj(bm, name, mats)


def face(bm, uvl, verts, uvs, slot=0):
    f = bm.faces.new(verts)
    f.material_index = slot
    for loop, uv in zip(f.loops, uvs):
        loop[uvl].uv = uv
    return f


def cap(bm, uvl, ring, flip=False, slot=0, uv_of=None):
    vs = list(reversed(ring)) if flip else list(ring)
    uvs = [uv_of(v.co) if uv_of else (v.co.x * MM, v.co.y * MM) for v in vs]
    return face(bm, uvl, vs, uvs, slot)


def arc_len(pts, closed=False):
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + (Vector(b) - Vector(a)).length)
    if closed:
        s.append(s[-1] + (Vector(pts[0]) - Vector(pts[-1])).length)
    return s


def resample(pts, step, closed=False):
    """Even arc-length resampling of a polyline (keeps the ends of an open one)."""
    pts = [Vector(p) for p in pts]
    if closed:
        pts = pts + [pts[0]]
    s = arc_len(pts)
    total = s[-1]
    n = max(2, int(round(total / step)))
    out, j = [], 0
    for i in range(n if closed else n + 1):
        t = total * i / n
        while j < len(s) - 2 and s[j + 1] < t:
            j += 1
        seg = s[j + 1] - s[j]
        f = 0.0 if seg < 1e-12 else (t - s[j]) / seg
        out.append(pts[j].lerp(pts[j + 1], f))
    return out


def rmf_frames(pts, closed=False, hint=(0, 1, 0)):
    """Tangents and rotation-minimising normals along a polyline."""
    n = len(pts)
    tans = []
    for i in range(n):
        if closed:
            t = pts[(i + 1) % n] - pts[i - 1]
        else:
            t = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        tans.append(t.normalized())
    nrm = Vector(hint) - Vector(hint).dot(tans[0]) * tans[0]
    nrm.normalize()
    frames = []
    for t in tans:
        nrm = (nrm - nrm.dot(t) * t).normalized()
        frames.append((t, nrm, t.cross(nrm)))
    return frames


def tube(name, pts, frames, profile_at, mats, closed_path=False, caps=True, slot_at=None, u_scale=MM):
    """Sweep: ring i is profile_at(i) -> [(a, b)] placed at pts[i] + a * frame.n + b * frame.b.
    UV: U = arc length along the path, V = arc length round the profile (both in metres)."""
    bm, uvl = new_bm()
    rings, uvs = [], []
    s_path = arc_len(pts, closed_path)
    for i, (p, (t, nn, bb)) in enumerate(zip(pts, frames)):
        prof = profile_at(i)
        rings.append([bm.verts.new(p + a * nn + b * bb) for a, b in prof])
        sv = arc_len(prof, closed=True)
        uvs.append([(s_path[i] * u_scale, v * u_scale) for v in sv])
    if closed_path:
        uvs.append([(s_path[-1] * u_scale, uv[1]) for uv in uvs[0]])
    n = len(rings)
    m = len(rings[0])
    for i in range(n if closed_path else n - 1):
        i2 = (i + 1) % n
        ui, ui2 = uvs[i], uvs[i + 1]
        slot = slot_at(i) if slot_at else 0
        for k in range(m):
            k2 = k + 1
            face(bm, uvl, (rings[i][k], rings[i][k2 % m], rings[i2][k2 % m], rings[i2][k]),
                 (ui[k], ui[k2], ui2[k2], ui2[k]), slot)
    if caps and not closed_path:
        c0 = [Vector(q) for q in profile_at(0)]
        c1 = [Vector(q) for q in profile_at(n - 1)]
        face(bm, uvl, list(reversed(rings[0])), [(q.x * u_scale, q.y * u_scale) for q in reversed(c0)],
             slot_at(0) if slot_at else 0)
        face(bm, uvl, rings[-1], [(q.x * u_scale, q.y * u_scale) for q in c1],
             slot_at(n - 2) if slot_at else 0)
    return to_obj(bm, name, mats)


def rrect(w, h, r, segs):
    """Rounded rectangle centred on 0, w along the first axis, as [(a, b)] counter-clockwise."""
    return S.rounded_rect(w, h, max(r, 1e-4), segs)


def superellipse(a, b, n, segs, phase=0.0):
    pts = []
    for k in range(segs):
        t = TAU * k / segs + phase
        c, s = math.cos(t), math.sin(t)
        pts.append((a * math.copysign(abs(c) ** (2 / n), c), b * math.copysign(abs(s) ** (2 / n), s)))
    return pts


# --------------------------------------------------------------------------- finishing

def parse_args(script_file):
    return S.parse_args(script_file)


def finish(name, parts, args, origin, sharp_angle=40):
    """Join, put `origin` (metres) at 0, tidy, check UVs, export the FBX and print the stats."""
    ob = S.join(name, parts) if len(parts) > 1 else SM.bake(parts[0])
    ob.name = ob.data.name = name
    S.set_origin(ob, origin)
    S.tidy(ob, sharp_angle)
    if not ob.data.uv_layers:
        raise RuntimeError(f"{name}: no UVs")
    os.makedirs(args.out, exist_ok=True)
    S.export_fbx(ob, os.path.join(args.out, name + ".fbx"))
    SM.report(ob)
    return ob


# --------------------------------------------------------------------------- preview materials

def skin_material(name="_PreviewSkin"):
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    m = S.material(name, (0.50, 0.255, 0.155), 0.48)
    b = SM.principled(m)
    SM.set_input(b, ["Subsurface Weight", "Subsurface"], 0.35)
    SM.set_input(b, "Subsurface Radius", (1.0, 0.45, 0.25))
    SM.set_input(b, "Subsurface Scale", 0.0025)
    SM.set_input(b, ["Specular IOR Level", "Specular"], 0.45)
    nt = m.node_tree
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 900.0
    nz.inputs["Detail"].default_value = 4.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.05
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def hide_stage():
    for nm in ("_board", "_wall"):
        ob = bpy.data.objects.get(nm)
        if ob is not None:
            ob.hide_render = True


def render_views(ob, out, samples, views, extras=None):
    """Stage (oak board, plaster wall, HDRI, warm lights) and a list of
    (file, view_dir, lens, margin, box or None, setup or None) shots, rendered in order."""
    lo, hi = S.bbox(ob)
    SM.stage(lo, hi)
    for fname, vd, lens, margin, box, setup in views:
        if setup:
            setup()
        b = box or (lo, hi)
        SM.shoot(os.path.join(out, fname), Vector(b[0]), Vector(b[1]), vd, lens=lens, margin=margin,
                 samples=samples)
