"""Shared helpers for the xfx-A signature transitions (eye_tunnel, symbiote, sling_ring, web_wipe).

Everything here only uses the stage contract (ctx, camlib) plus bpy. Conventions (EDIT.md "Card space"):
a card is a 1.92 x 1.08 m plane in its local XY, facing +Z, 1 px = 1 mm, card pixel (px, py) with y down maps to local
((px - 960) / 1000, (540 - py) / 1000, 0). The camera looks down its local -Z, so a camera showing State(s, cx, cy, r)
sits at local ((cx - 960) / 1000, (540 - cy) / 1000, FILL_DIST / s) rolled by +r about local Z (picture turns clockwise).
"""
import bisect
import json
import math
import os
import random

import bpy
from mathutils import Matrix, Quaternion, Vector

import camlib

FILL = camlib.FILL_DIST
W, H = 1920, 1080


# ------------------------------------------------------------------------------------------------- card space / camera
def px2local(px, py):
    return Vector(((px - W / 2) / 1000.0, (H / 2 - py) / 1000.0, 0.0))


def cam_local(st):
    """4x4 camera matrix in card-local space for a State (unscaled card)."""
    loc = Vector(((st.cx - W / 2) / 1000.0, (H / 2 - st.cy) / 1000.0, FILL / st.s))
    return Matrix.Translation(loc) @ Quaternion((0, 0, 1), math.radians(st.r)).to_matrix().to_4x4()


def cam_world(card_matrix, st):
    """Camera world matrix (unit scale) showing `st` on a card with world matrix `card_matrix` (uniform scale ok)."""
    m = card_matrix @ cam_local(st)
    loc, rot, _ = m.decompose()
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()


def state_from_cam(card_matrix, cam_m, r_hint=0.0):
    """Inverse of cam_world for a camera facing the card: returns (s, cx, cy, r) with r unwrapped near r_hint."""
    loc_l = card_matrix.inverted() @ cam_m.to_translation()
    sc = card_matrix.to_scale()[0]
    rel = (card_matrix.to_quaternion().inverted() @ cam_m.to_quaternion())
    r = math.degrees(rel.to_euler("XYZ").z)
    r += 360.0 * round((r_hint - r) / 360.0)
    return FILL / loc_l.z, loc_l.x * 1000 + W / 2, H / 2 - loc_l.y * 1000, r, sc


def mix_state(fn, t, h=0.02):
    """State at t with rates by forward difference (rates per frame, ds in d ln s). fn(t) -> (s, cx, cy, r)."""
    a, b = fn(t), fn(t + h)
    return camlib.State(a[0], a[1], a[2], a[3], ds=(math.log(b[0]) - math.log(a[0])) / h,
                        dcx=(b[1] - a[1]) / h, dcy=(b[2] - a[2]) / h, dr=(b[3] - a[3]) / h)


def mix_state_back(fn, t, h=0.02):
    a, b = fn(t - h), fn(t)
    return camlib.State(b[0], b[1], b[2], b[3], ds=(math.log(b[0]) - math.log(a[0])) / h,
                        dcx=(b[1] - a[1]) / h, dcy=(b[2] - a[2]) / h, dr=(b[3] - a[3]) / h)


def exit_rate(ctx, T, default=0.025):
    """Zoom rate (d ln s / f, > 0 = pushing in) to leave a window with: the magnitude of shot B's hold drift from the
    core (ctx.exit_state), kept pushing in so the zoom sign carries into the hold (REFS: keep the sign; holds 1.5-3.5 %/f)."""
    try:
        ex = ctx.exit_state(T)
        return max(0.015, min(0.035, abs(float(ex.ds)))) if ex is not None else default
    except Exception:  # noqa: BLE001 - harness / older ctx
        return default


def extrap(st, dt):
    """A State carried dt frames along its own rates (what a hold looks like right at the window edge)."""
    return camlib.State(st.s * math.exp(st.ds * dt), st.cx + st.dcx * dt, st.cy + st.dcy * dt, st.r + st.dr * dt,
                        st.ds, st.dcx, st.dcy, st.dr)


def key_matrix(ctx, f, m, lens=None):
    loc, rot, _ = m.decompose()
    ctx.key_cam(f, loc, rot, lens=lens) if lens is not None else ctx.key_cam(f, loc, rot)


def key_dof(ctx, f, focus_m, fstop):
    """Real camera depth of field (REFS: B's first frames are rack-defocused). Uses ctx.key_dof when the core offers
    it; otherwise keys the scene camera's DOF directly (focus distance in metres, f-stop)."""
    if hasattr(ctx, "key_dof"):
        ctx.key_dof(f, focus_m, fstop)
        return
    cam = bpy.context.scene.camera.data
    cam.dof.use_dof = True
    cam.dof.focus_distance = focus_m
    cam.dof.aperture_fstop = fstop
    cam.dof.keyframe_insert("focus_distance", frame=f)
    cam.dof.keyframe_insert("aperture_fstop", frame=f)


def key_path(ctx, w0, w1, fn, teleports=(), lens_fn=None, sub=2, dof_fn=None):
    """Key the camera on every 1/sub frame of [w0, w1). fn(t) -> world Matrix. At a teleport half frame th the camera is
    keyed just before (old set) and just after (new set) instead of at th, so no shutter (<= 0.95 f) sees the jump."""
    for th in teleports:
        ctx.teleport(th)
    n = int(round((w1 - w0) * sub))
    for i in range(n):
        t = w0 + i / sub
        hit = [th for th in teleports if abs(t - th) < 1e-6]
        ts = (t - 0.02, t + 0.02) if hit else (t,)
        for tt in ts:
            key_matrix(ctx, tt, fn(tt), lens_fn(tt) if lens_fn else None)
            if dof_fn:
                key_dof(ctx, tt, *dof_fn(tt))
    if dof_fn:  # sharp again at the window exit (f/64 at the card distance)
        key_dof(ctx, w1, dof_fn(w1 - 0.01)[0], 64.0)


# ------------------------------------------------------------------------------------------------- 1D profiles
class Speed:
    """A speed v(t) through keypoints [(t, v), ...] with monotone cubic interpolation (Fritsch-Carlson) and optional end
    slopes; x(t) = integral of v from the first keypoint (fine trapezoids). Smooth, C1, never overshoots."""

    def __init__(self, pts, m0=None, m1=None, step=1.0 / 64):
        self.t = [p[0] for p in pts]
        self.v = [p[1] for p in pts]
        n = len(pts)
        d = [(self.v[i + 1] - self.v[i]) / (self.t[i + 1] - self.t[i]) for i in range(n - 1)]
        m = [0.0] * n
        for i in range(1, n - 1):
            m[i] = 0.0 if d[i - 1] * d[i] <= 0 else 2.0 / (1.0 / d[i - 1] + 1.0 / d[i])
        m[0] = d[0] if m0 is None else m0
        m[-1] = d[-1] if m1 is None else m1
        self.m = m
        self.step = step
        self.cum_t = []
        self.cum_x = []
        tt, x = self.t[0] - 8.0, 0.0
        while tt <= self.t[-1] + 8.0:
            self.cum_t.append(tt)
            self.cum_x.append(x)
            x += 0.5 * (self.vel(tt) + self.vel(tt + step)) * step
            tt += step
        self.x0 = self.x_raw(self.t[0])

    def vel(self, t):
        T, V, M = self.t, self.v, self.m
        if t <= T[0]:
            return V[0] + M[0] * (t - T[0])
        if t >= T[-1]:
            return V[-1] + M[-1] * (t - T[-1])
        i = bisect.bisect_right(T, t) - 1
        h = T[i + 1] - T[i]
        return camlib.hermite(V[i], M[i] * h, V[i + 1], M[i + 1] * h, (t - T[i]) / h)

    def x_raw(self, t):
        k = (t - self.cum_t[0]) / self.step
        i = max(0, min(len(self.cum_t) - 2, int(k)))
        u = k - i
        return self.cum_x[i] + (self.cum_x[i + 1] - self.cum_x[i]) * u

    def x(self, t):
        return self.x_raw(t) - self.x0


def bump(t, a, b):
    """0 outside [a, b], smooth hump (sin^2) inside, peak 1 at the middle."""
    if t <= a or t >= b:
        return 0.0
    return math.sin(math.pi * (t - a) / (b - a)) ** 2


def sstep(a, b, x):
    return _sstep(a, b, x)


def _sstep(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def lerp(a, b, u):
    return a + (b - a) * u


def lerp3(a, b, u):
    return tuple(a[i] + (b[i] - a[i]) * u for i in range(3))


# ------------------------------------------------------------------------------------------------- plates
def plate_dir(ctx, sid):
    return os.path.join(ctx.data, "plates", sid)


def plate_range(ctx, sid):
    """[lo, hi) comp frames of the plate on disk."""
    d = plate_dir(ctx, sid)
    pj = os.path.join(d, "plate.json")
    if os.path.exists(pj):
        j = json.load(open(pj))
        return int(j["lo"]), int(j["hi"])
    fs = sorted(int(f[2:7]) for f in os.listdir(d) if f.startswith("f_") and f.endswith(".jpg"))
    return fs[0], fs[-1] + 1


def plate_moving_frames(ctx, sid):
    """Frames of the plate that are not holds (plate.json 'held' flag)."""
    lo, hi = plate_range(ctx, sid)
    pj = os.path.join(plate_dir(ctx, sid), "plate.json")
    if not os.path.exists(pj):
        return list(range(lo, hi))
    fr = json.load(open(pj)).get("frames", {})
    return [f for f in range(lo, hi) if not fr.get(str(f), {}).get("held", False)] or list(range(lo, hi))


def plate_image(ctx, sid):
    lo, hi = plate_range(ctx, sid)
    path = os.path.join(plate_dir(ctx, sid), f"f_{lo:05d}.jpg")
    name = f"xfxa_plate_{sid}"
    img = bpy.data.images.get(name)
    if img is None:
        img = bpy.data.images.load(path)
        img.name = name
        img.source = "SEQUENCE"
    return img


def plate_node(nt, ctx, sid, f_at=None, frame0=None, loop=None):
    """Image Texture node playing the plate. Default: comp time (image number = scene frame, held outside the plate).
    With frame0/f_at: image f_at shows on scene frame frame0 and the plate plays forward from there. loop=(a, b) makes
    it cycle inside [a, b) (only moving frames), for decor cards that must keep moving whatever the comp frame."""
    lo, hi = plate_range(ctx, sid)
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = plate_image(ctx, sid)
    n.extension = "EXTEND"
    iu = n.image_user
    iu.use_auto_refresh = True
    if loop:
        a, b = loop
        a, b = max(a, lo), min(b, hi)
        iu.frame_duration = b - a
        iu.frame_offset = a - 1
        start_img = f_at if f_at is not None else a
        iu.frame_start = frame0 - (start_img - a)
        iu.use_cyclic = True
    elif f_at is not None:
        iu.frame_duration = hi - lo
        iu.frame_offset = lo - 1
        iu.frame_start = frame0 - (f_at - lo)
        iu.use_cyclic = False
    else:
        iu.frame_duration = hi - lo
        iu.frame_offset = lo - 1
        iu.frame_start = lo
        iu.use_cyclic = False
    return n


def copy_card(ctx, sid, name, matrix, frames=None, hole=None, tile=3):
    """A private-set copy of a shot's card: same plate in comp time and the same depth displacement as the home card
    (so a teleport between them is invisible), rendered only on `frames` = (f0, f1)."""
    depth = float((ctx.shot(sid).get("move") or {}).get("depth", 0.0) or 0.0)
    kw = dict(matrix=matrix)
    if hole:
        kw["hole"] = hole
    try:  # tile=3: mirror-tiled beyond the card edges, exactly like the core's home cards
        ob = ctx.make_card(sid, name, depth=depth, frames=frames, tile=tile, **kw)
    except TypeError:  # an older ctx without frames= / tile=
        ob = ctx.make_card(sid, name, depth=depth, **kw)
        if frames:
            key_hide(ob, [frames])
    return ob


# ------------------------------------------------------------------------------------------------- objects
def link(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def mesh_obj(name, verts, faces, coll, uvs=None, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    if uvs is not None:
        uv = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li in poly.loop_indices:
                uv.data[li].uv = uvs[me.loops[li].vertex_index]
    if smooth:
        me.shade_smooth()
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def plane_obj(name, w, h, coll, nx=1, ny=1):
    vs, uvs, fs = [], [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            u, v = i / nx, j / ny
            vs.append(((u - 0.5) * w, (v - 0.5) * h, 0.0))
            uvs.append((u, v))
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            fs.append((a, a + 1, a + nx + 2, a + nx + 1))
    return mesh_obj(name, vs, fs, coll, uvs)


def annulus_obj(name, r0, r1, coll, n=128, nr=1):
    vs, uvs, fs = [], [], []
    for j in range(nr + 1):
        r = r0 + (r1 - r0) * j / nr
        for i in range(n + 1):
            a = 2 * math.pi * i / n
            vs.append((r * math.cos(a), r * math.sin(a), 0.0))
            uvs.append((i / n, j / nr))
    for j in range(nr):
        for i in range(n):
            a = j * (n + 1) + i
            fs.append((a, a + 1, a + n + 2, a + n + 1))
    return mesh_obj(name, vs, fs, coll, uvs)


def tube_obj(name, ring_fn, zs, coll, n=96):
    """A tube along -Z: ring_fn(z, angle) -> (x, y). UV u = angle / 2pi, v = index along zs / (len - 1)."""
    vs, uvs, fs = [], [], []
    for j, z in enumerate(zs):
        for i in range(n + 1):
            a = 2 * math.pi * i / n
            x, y = ring_fn(z, a)
            vs.append((x, y, z))
            uvs.append((i / n, j / (len(zs) - 1)))
    for j in range(len(zs) - 1):
        for i in range(n):
            a = j * (n + 1) + i
            fs.append((a, a + n + 1, a + n + 2, a + 1))
    return mesh_obj(name, vs, fs, coll, uvs, smooth=True)


def curve_obj(name, pts, coll, bevel=0.004, taper=None, res=12, closed=False):
    """A NURBS curve through pts (list of Vector) with round bevel; taper = [(u, radius_scale), ...] along it."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = bevel
    cu.bevel_resolution = 2
    cu.resolution_u = res
    cu.use_fill_caps = True
    sp = cu.splines.new("NURBS")
    sp.points.add(len(pts) - 1)
    for p, q in zip(sp.points, pts):
        p.co = (q[0], q[1], q[2], 1.0)
        p.radius = 1.0
    sp.order_u = min(4, len(pts))
    sp.use_endpoint_u = not closed
    sp.use_cyclic_u = closed
    if taper:
        for i, p in enumerate(sp.points):
            u = i / max(1, len(pts) - 1)
            p.radius = _interp(taper, u)
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    return ob


def _interp(tab, u):
    if u <= tab[0][0]:
        return tab[0][1]
    for (a, va), (b, vb) in zip(tab, tab[1:]):
        if u <= b:
            return va + (vb - va) * (u - a) / (b - a)
    return tab[-1][1]


def key_hide(ob, shown):
    """shown = [(f_on, f_off), ...] half-open frame ranges where the object renders; CONSTANT keys."""
    ob.hide_render = True
    ob.keyframe_insert("hide_render", frame=-10000)
    for a, b in shown:
        ob.hide_render = False
        ob.keyframe_insert("hide_render", frame=a)
        ob.hide_render = True
        ob.keyframe_insert("hide_render", frame=b)
    for fc in fcurves_of(ob):
        if fc.data_path == "hide_render":
            for k in fc.keyframe_points:
                k.interpolation = "CONSTANT"


def fcurves_of(idblock):
    """All F-curves of an ID's action (Blender 4.4+ layered actions and the legacy list)."""
    ad = idblock.animation_data
    if not ad or not ad.action:
        return []
    act = ad.action
    out = []
    if hasattr(act, "layers") and len(act.layers):
        for layer in act.layers:
            for strip in layer.strips:
                for cb in getattr(strip, "channelbags", []):
                    out.extend(cb.fcurves)
    elif hasattr(act, "fcurves"):
        out.extend(act.fcurves)
    return out


def set_linear(idblock):
    for fc in fcurves_of(idblock):
        for k in fc.keyframe_points:
            if k.interpolation != "CONSTANT":
                k.interpolation = "LINEAR"


def vis_camera_off(ob):
    ob.visible_camera = False


# ------------------------------------------------------------------------------------------------- materials
def _nodes(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    return m, nt, out


def mat_emit(name, rgb, strength=1.0, alpha=None):
    m, nt, out = _nodes(name)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*rgb, 1.0)
    e.inputs["Strength"].default_value = strength
    if alpha is None:
        nt.links.new(e.outputs[0], out.inputs["Surface"])
    else:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mx = nt.nodes.new("ShaderNodeMixShader")
        mx.inputs[0].default_value = alpha
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(e.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return m


def node(nt, kind, **inputs):
    n = nt.nodes.new(kind)
    for k, v in inputs.items():
        if k.startswith("_"):
            setattr(n, k[1:], v)
        else:
            n.inputs[k].default_value = v
    return n


def math_node(nt, op, a=None, b=None, clamp=False):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def key_value(nt, label, keys, default=0.0):
    """A Value node animated through [(frame, value), ...] (linear). Returns its output socket."""
    v = nt.nodes.new("ShaderNodeValue")
    v.name = v.label = label
    v.outputs[0].default_value = default
    for f, x in keys:
        v.outputs[0].default_value = x
        v.outputs[0].keyframe_insert("default_value", frame=f)
    return v.outputs[0]


def rng(seed):
    return random.Random(seed)


# ------------------------------------------------------------------------------------------------- tracks
_TRACKS = {}


def track(ctx, sid, f, default=None):
    """Tracked focus point (plate px) of a shot at comp frame f (float ok; clamped to the tracked range).
    Falls back to the EDL focus, then `default`, then the frame centre."""
    if sid not in _TRACKS:
        p = os.path.join(ctx.data, "tracks", f"{sid}.json")
        tr = None
        if os.path.exists(p):
            fr = json.load(open(p)).get("frames", {})
            tr = sorted((int(k), v) for k, v in fr.items() if v)
        _TRACKS[sid] = tr
    tr = _TRACKS[sid]
    if not tr:
        foc = ctx.shot(sid).get("focus")
        return tuple(foc) if foc else (default or (W / 2, H / 2))
    ks = [k for k, _ in tr]
    if f <= ks[0]:
        return tuple(tr[0][1])
    if f >= ks[-1]:
        return tuple(tr[-1][1])
    i = bisect.bisect_right(ks, f) - 1
    (k0, a), (k1, b) = tr[i], tr[i + 1]
    u = (f - k0) / (k1 - k0)
    return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)


def depth_fog(nt, color, fog_rgb, k=3.0, near=0.0):
    """Mix a colour socket toward fog_rgb with camera distance (1 - exp(-(d - near) / k)): atmospheric depth.
    Returns (color socket, keep factor socket) - keep = 1 near the camera, -> 0 far."""
    cd = nt.nodes.new("ShaderNodeCameraData")
    d = math_node(nt, "MAXIMUM", math_node(nt, "SUBTRACT", cd.outputs["View Distance"], near), 0.0)
    keep = math_node(nt, "EXPONENT", math_node(nt, "DIVIDE", d, -k))
    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    nt.links.new(keep, mx.inputs[0])
    mx.inputs[6].default_value = (*fog_rgb, 1)
    nt.links.new(color, mx.inputs[7])
    return mx.outputs[2], keep


def mat_emit_fog(name, rgb, strength, fog_rgb, k=3.0, near=0.0):
    """Emission that fades into the fog with distance (light rings, strands, glints)."""
    m, nt, out = _nodes(name)
    rgbn = nt.nodes.new("ShaderNodeRGB")
    rgbn.outputs[0].default_value = (*rgb, 1)
    col, keep = depth_fog(nt, rgbn.outputs[0], fog_rgb, k, near)
    e = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, e.inputs["Color"])
    nt.links.new(math_node(nt, "MULTIPLY", keep, strength), e.inputs["Strength"])
    nt.links.new(e.outputs[0], out.inputs["Surface"])
    return m
