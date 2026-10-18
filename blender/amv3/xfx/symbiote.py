"""symbiote (C04, S04 gold bokeh -> S05 black suit lens, window 139-161, cut 151).

Glossy black symbiote goo crawls in from the frame edges over Tobey (fingers/tendrils reaching ahead of a wet rolled
lip), thickens and bulges up at the camera while the camera pushes into it, swallows the whole frame on the cut, and
peels back outward to the edges revealing the black suit lens (S05) already moving, the camera pulling out of it.

The goo is a height field over a private copy of the S04 card, computed in numpy (deterministic sums of sines, no
simulation) and stored as one shape key per frame blended linearly, so Cycles gets real deformation motion blur.
Wet look: black clear-coated principled shader, sharp highlights from camera-invisible softboxes and point lights
in the act colours, subtle purple-white fresnel rim. The S04 copy is swapped for the S05 copy (coplanar, scaled so
the camera path is one continuous curve) while the goo covers the frame.
Teleports: home S04 -> private set at w0 + 0.5, private set -> home S05 at w1 - 0.5 (goo already off screen).
"""
import math
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.append(_here)
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402

import _xfxa as X  # noqa: E402
import camlib  # noqa: E402

FILL = X.FILL
_PLAN = {}
GX, GY = 448, 252  # goo grid (vertices), ~4.3 px per cell on the card, subdivided once at render


def _plan(T, ctx):
    key = (T["id"], T["w0"], T["w1"], T["f"])
    if key in _PLAN:
        return _PLAN[key]
    w0, w1, cut = T["w0"], T["w1"], T["f"]
    a, b = T["a"]["id"], T["b"]["id"]
    p = T.get("p", {})
    P = dict(w0=w0, w1=w1, cut=cut, a=a, b=b)
    s0, ds0 = float(p.get("s0", 1.08)), float(p.get("ds0", 0.02))
    r0, dr0 = float(p.get("r0", -0.6)), float(p.get("dr0", -0.08))
    # zoom rate (d ln s / f) on the S04 copy: expo push into the goo, the turn hidden under full cover, then B's pull-out
    # landing that decays ~0.8 / f (REFS) into S05's out-drift
    # zoom rate (d ln s / f) on the S04 copy: expo push into the goo, peak on the cut under full cover, then S05 keeps
    # pushing in, decaying ~0.8 / f (REFS: keep the zoom sign) into its hold drift
    ds_end = X.exit_rate(ctx, T, 0.022)
    dsp = X.Speed([(w0, ds0), (w0 + 4, 0.032), (w0 + 7, 0.06), (w0 + 9, 0.115), (cut - 1.5, 0.21), (cut - 0.5, 0.27),
                   (cut + 0.5, 0.23), (cut + 1.5, 0.19), (cut + 3, 0.14), (cut + 5, 0.095), (cut + 7, 0.06),
                   (w1, ds_end)], m0=0.002)
    rsp = X.Speed([(w0, dr0), (w0 + 5, -0.6), (w0 + 9, -3.0), (cut - 0.5, -7.0), (cut + 1, -6.0), (cut + 4, -2.0),
                   (cut + 7, -0.6), (w1, -0.2)], m0=0.0)
    lnS = lambda t: math.log(s0) + dsp.x(t)  # noqa: E731
    roll = lambda t: r0 + rsp.x(t)  # noqa: E731
    P["sA"] = lambda t: math.exp(lnS(t))  # noqa: E731
    P["roll"] = roll
    cA = (960.0, 540.0)
    P["cA"] = cA
    O = ctx.new_set("symbiote")
    P["O"] = O
    P["MA"] = Matrix.Translation(O)
    # S05 copy: coplanar (a hair behind), scaled kB about the camera axis so S05 ends at s_end on its focus (kB < 1)
    s_end = 1.10
    kB = s_end / P["sA"](w1)  # a card k x bigger at the same distance shows at k x the scale
    focB = X.track(ctx, b, w1, (1029, 510))
    lim = 960 - 960 / s_end - 14
    fx = 960 + max(-lim, min(lim, focB[0] - 960))
    limy = 540 - 540 / s_end - 8
    fy = 540 + max(-limy, min(limy, focB[1] - 540))
    P["cB"] = (fx, fy)
    theta = roll(w1) - 0.0  # S05 copy turned so the camera ends level on it
    axis = X.px2local(*cA)
    MB_local = (Matrix.Translation(Vector((axis.x, axis.y, -0.0015)))
                @ Quaternion((0, 0, 1), math.radians(theta)).to_matrix().to_4x4()
                @ Matrix.Scale(kB, 4) @ Matrix.Translation(-X.px2local(fx, fy)))
    P["MB"] = Matrix.Translation(O) @ MB_local
    P["kB"], P["theta"] = kB, theta

    def m_set(t):
        return X.cam_world(P["MA"], camlib.State(P["sA"](t), cA[0], cA[1], roll(t)))

    P["m_set"] = m_set
    P["a_state"] = lambda t: (P["sA"](t), cA[0], cA[1], roll(t))  # noqa: E731

    def b_state(t):
        s, cx, cy, r, _ = X.state_from_cam(P["MB"], m_set(t), r_hint=roll(t) - theta)
        return (s, cx, cy, r)

    P["b_state"] = b_state
    _PLAN[key] = P
    return P


def bounds(T, ctx):
    P = _plan(T, ctx)
    return {"A": X.mix_state(P["a_state"], P["w0"]), "B": X.mix_state_back(P["b_state"], P["w1"])}


# ------------------------------------------------------------------------------------------------- goo field
class _Noise:
    """Smooth deterministic pseudo-noise: a sum of random plane waves (numpy)."""

    def __init__(self, seed, n=7, k=(2.0, 9.0), w=(0.04, 0.18)):
        r = np.random.default_rng(seed)
        ang = r.uniform(0, 2 * np.pi, n)
        kk = r.uniform(*k, n) * (0.7 ** np.arange(n))[::-1].clip(0.35)
        self.kx, self.ky = kk * np.cos(ang), kk * np.sin(ang)
        self.w = r.uniform(*w, n) * r.choice([-1, 1], n)
        self.ph = r.uniform(0, 2 * np.pi, n)
        self.a = 1.0 / (1.0 + np.arange(n) * 0.6)
        self.a /= self.a.sum()

    def __call__(self, x, y, t):
        out = np.zeros_like(x)
        for i in range(len(self.a)):
            out += self.a[i] * np.sin(self.kx[i] * x + self.ky[i] * y + self.w[i] * t * 6.0 + self.ph[i])
        return out


def _np_sstep(a, b, x):
    u = np.clip((x - a) / (b - a), 0.0, 1.0)
    return u * u * (3 - 2 * u)


def _field(P, X0, Y0, t, N1, N2, N3):
    """Goo surface at frame t: returns (x, y, z) arrays in A-copy local metres."""
    w0, cut = P["w0"], P["cut"]
    s, roll = P["sA"](t), math.radians(P["roll"](t))
    cx, cy = P["cA"]
    # vertex -> screen (px from frame centre); picture roll r clockwise => rotate by -r
    px = X0 * 1000.0
    py = -Y0 * 1000.0
    dx, dy = (px - (cx - 960)), (py - (cy - 540))
    c, sn = math.cos(roll), math.sin(roll)
    qx = (c * dx - sn * dy) * s
    qy = (sn * dx + c * dy) * s
    rho = ((np.abs(qx) / 960.0) ** 4 + (np.abs(qy) / 540.0) ** 4) ** 0.25  # 0 centre, 1 frame border
    th = np.arctan2(qy / 540.0, qx / 960.0)
    # front progress from the border inward: crawl in (accelerating), full cover through the cut, peel back out
    u_in = X._sstep(w0 + 0.5, cut - 1.0, t)
    F = -0.25 + 1.45 * (u_in ** 1.5)
    F -= 1.75 * X._sstep(cut + 0.8, P["w1"] - 1.6, t) ** 0.9
    n1 = N1(X0 * 3.0, Y0 * 3.0, t)
    n2 = N2(np.cos(th) * 2.0, np.sin(th) * 2.0, t)
    peel = X._sstep(cut + 0.5, cut + 2.5, t)
    # irregular tendrils: two incommensurate finger sets, each finger's reach and width wandering with noise
    f1 = np.maximum(0.0, np.sin(7.0 * th + 3.0 * n2 + 0.5 * t * (1 - 2 * peel))) ** 9
    f2 = np.maximum(0.0, np.sin(4.3 * th - 2.2 * n2 + 1.7 - 0.35 * t)) ** 14
    fingers = (f1 * (0.6 + 0.4 * np.sin(3.1 * th + 1.3)) + 0.8 * f2) * (0.75 + 0.5 * n2)
    reach = 0.20 * (1.0 - X._sstep(cut - 2.0, cut, t)) + 0.16 * peel * (1 - X._sstep(P["w1"] - 3, P["w1"] - 1, t))
    rad = np.sqrt(qx ** 2 + qy ** 2) / 760.0
    rho = 0.55 * rho + 0.45 * np.minimum(rad / 1.25, 1.2)  # rounder front, still born at the frame edges
    cov = rho - (1.0 - F) + 0.10 * n1 + reach * fingers * _np_sstep(0.18, 0.55, rho)
    # thickness: thin wet film at first, a thick rolled lip, then a bulge that rises at the camera on the cut
    thick = 0.024 + 0.03 * X._sstep(w0 + 2, cut - 2, t) - 0.012 * peel
    dist = FILL / s
    bulge = (1.0 + 0.35 * n1) * 0.55 * dist * X.bump(t, cut - 4.0, cut + 3.5) * np.exp(-(rad ** 2) / 0.45)
    lip = np.sin(0.5 * np.pi * np.clip(cov / 0.12, 0.0, 1.0)) ** 0.7  # a rounded bead, not a cliff
    rip = 1.0 + 0.35 * N3(X0 * 8.0, Y0 * 8.0, t)
    z = np.where(cov > 0, thick * lip * rip + bulge * np.clip(cov / 0.25, 0, 1), -0.004)
    # slight flow of the surface toward the centre while crawling, outward while peeling
    flow = 0.012 * np.clip(cov, 0, 1) * (1 - 2 * peel)
    rr = np.sqrt(X0 ** 2 + Y0 ** 2) + 1e-6
    return X0 - flow * X0 / rr, Y0 - flow * Y0 / rr, z


def _goo_mesh(P, ctx, coll):
    w0, w1 = P["w0"], P["w1"]
    xs = np.linspace(-0.98, 0.98, GX)
    ys = np.linspace(-0.56, 0.56, GY)
    X0, Y0 = np.meshgrid(xs, ys)
    X0, Y0 = X0.ravel(), Y0.ravel()
    faces = []
    for j in range(GY - 1):
        base = j * GX
        for i in range(GX - 1):
            a = base + i
            faces.append((a, a + 1, a + GX + 1, a + GX))
    verts = [(float(x), float(y), -0.004) for x, y in zip(X0, Y0)]
    ob = X.mesh_obj("XA_sym_goo", verts, faces, coll, smooth=True)
    ob.matrix_world = P["MA"]
    N1, N2, N3 = _Noise(151), _Noise(152, k=(1.0, 3.0)), _Noise(153, k=(6.0, 14.0), w=(0.1, 0.3))
    ob.shape_key_add(name="Basis", from_mix=False)
    frames = list(range(w0 - 1, w1 + 1))
    for f in frames:
        x, y, z = _field(P, X0, Y0, float(f), N1, N2, N3)
        kb = ob.shape_key_add(name=f"f{f}", from_mix=False)
        co = np.stack([x, y, z], axis=1).astype(np.float32).ravel()
        kb.data.foreach_set("co", co)
        for ff, v in ((f - 1, 0.0), (f, 1.0), (f + 1, 0.0)):
            kb.value = v
            kb.keyframe_insert("value", frame=ff)
        kb.value = 0.0
    X.set_linear(ob.data.shape_keys)
    sub = ob.modifiers.new("sub", "SUBSURF")
    sub.levels, sub.render_levels = 0, 1
    return ob


# ------------------------------------------------------------------------------------------------- build
def build(T, ctx):
    P = _plan(T, ctx)
    w0, w1, cut, O = P["w0"], P["w1"], P["cut"], P["O"]
    a, b = P["a"], P["b"]
    plate_c, light_c = ctx.coll("plate"), ctx.coll("light")
    pal = ctx.palette(ctx.act_at(cut))
    X.copy_card(ctx, a, "XA_sym_S04", P["MA"], frames=(w0 - 1, cut))
    X.copy_card(ctx, b, "XA_sym_S05", P["MB"], frames=(cut, w1 + 1))
    goo = _goo_mesh(P, ctx, plate_c)
    goo.data.materials.append(_goo_mat(pal))
    _lights(P, ctx, pal, plate_c)
    _cam_light(P, plate_c)
    # no act void here: the frame is always covered (card or goo), and the void's warm haze reflected in the wet coat
    # turned the goo brown. A near-black violet dome instead, so the goo reflects darkness + the highlight strips.
    _dome(O, plate_c)

    homeA = ctx.card(a).matrix_world.copy()
    homeB = ctx.card(b).matrix_world.copy()
    t_in, t_out = w0 + 0.5, w1 - 0.5
    to_homeA = homeA @ P["MA"].inverted()
    to_homeB = homeB @ P["MB"].inverted()

    def fn(t):
        m = P["m_set"](t)
        if t < t_in:
            return _norm(to_homeA @ m)
        if t > t_out:
            return _norm(to_homeB @ m)
        return m

    def dof(t):
        """Rack defocus as S05 is revealed: focus pulled short of the card, racking onto it."""
        d = FILL / P["sA"](t)
        if t > t_out:
            d /= P["kB"]
        u = X._sstep(cut + 1.0, cut + 8.0, t)
        k = X._sstep(cut - 1.0, cut + 0.5, t)
        return d * X.lerp(0.45, 1.0, u), X.lerp(64.0, X.lerp(1.2, 64.0, u), k)

    X.key_path(ctx, w0, w1, fn, teleports=(t_in, t_out), dof_fn=dof)
    ctx.log(f"symbiote: s peak {P['sA'](cut):.2f}, roll {P['roll'](w1) - P['roll'](w0):.0f} deg, S05 copy x{P['kB']:.2f}")


def _norm(m):
    loc, rot, _ = m.decompose()
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()


def _goo_mat(pal):
    m, nt, out = X._nodes("XA_sym_goo_m")
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bs.inputs["Base Color"].default_value = (0.003, 0.003, 0.005, 1)
    bs.inputs["Roughness"].default_value = 0.10
    bs.inputs["Specular IOR Level"].default_value = 0.5
    bs.inputs["Coat Weight"].default_value = 1.0
    bs.inputs["Coat Roughness"].default_value = 0.02
    bs.inputs["Coat IOR"].default_value = 1.6
    # micro ripples in the coat normal for crawling highlights
    tc = nt.nodes.new("ShaderNodeTexCoord")
    no = X.node(nt, "ShaderNodeTexNoise", Scale=60.0, Detail=3.0)
    nt.links.new(tc.outputs["Object"], no.inputs["Vector"])
    bump = X.node(nt, "ShaderNodeBump", Strength=0.08, Distance=0.002)
    nt.links.new(no.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs[0], bs.inputs["Coat Normal"])
    # subtle purple-white rim at grazing angles
    lw = X.node(nt, "ShaderNodeLayerWeight", Blend=0.12)
    rim = X.math_node(nt, "POWER", lw.outputs["Facing"], 3.0)
    em = X.node(nt, "ShaderNodeEmission", Color=(0.62, 0.48, 1.0, 1))
    nt.links.new(X.math_node(nt, "MULTIPLY", rim, 0.35), em.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(bs.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return m


def _dome(O, coll, R=6.0, n=32):
    vs, fs = [], []
    for j in range(n // 2 + 1):
        th = math.pi * j / (n // 2)
        for i in range(n + 1):
            ph = 2 * math.pi * i / n
            vs.append(O + Vector((R * math.sin(th) * math.cos(ph), R * math.sin(th) * math.sin(ph), R * math.cos(th))))
    for j in range(n // 2):
        for i in range(n):
            a = j * (n + 1) + i
            fs.append((a, a + n + 1, a + n + 2, a + 1))
    ob = X.mesh_obj("XA_sym_dome", vs, fs, coll)
    ob.data.materials.append(X.mat_emit("XA_sym_dome_m", (0.012, 0.008, 0.02), 1.0))
    ob.visible_shadow = False
    return ob


def _cam_light(P, coll):
    """A small key light riding just above and behind the camera: the goo facing the lens always carries a live wet
    highlight, sliding as the surface ripples and the camera rolls."""
    ld = bpy.data.lights.new("XA_sym_camkey", "AREA")
    ld.energy = 22.0
    ld.size = 0.025
    ld.color = (0.95, 0.9, 1.0)
    lo = bpy.data.objects.new("XA_sym_camkey", ld)
    lo.visible_camera = False
    coll.objects.link(lo)
    for i in range(2 * (P["w1"] - P["w0"] + 2) + 1):
        t = P["w0"] - 1 + 0.5 * i
        m = P["m_set"](t) @ Matrix.Translation(Vector((0.18, 0.22, 0.12)))
        lo.matrix_world = m
        lo.keyframe_insert("location", frame=t)
        lo.keyframe_insert("rotation_quaternion" if lo.rotation_mode == "QUATERNION" else "rotation_euler", frame=t)
    X.set_linear(lo)
    # a sweep light crossing the frame while the goo covers it: one wet highlight travelling over the surface
    sd = bpy.data.lights.new("XA_sym_sweep", "AREA")
    sd.energy = 40.0
    sd.size = 0.02
    sd.color = (0.85, 0.8, 1.0)
    so = bpy.data.objects.new("XA_sym_sweep", sd)
    so.visible_camera = False
    coll.objects.link(so)
    cut = P["cut"]
    for i in range(2 * (P["w1"] - P["w0"] + 2) + 1):
        t = P["w0"] - 1 + 0.5 * i
        u = (t - (cut - 4.0)) / 8.0
        m = P["m_set"](t) @ Matrix.Translation(Vector((-0.9 + 1.8 * u, 0.45 - 0.5 * u, 0.25)))
        so.matrix_world = m
        so.keyframe_insert("location", frame=t)
        so.keyframe_insert("rotation_euler", frame=t)
    X.set_linear(so)


def _lights(P, ctx, pal, coll):
    """Reflection sources for the wet goo: softbox strips and small hot lights, invisible to the camera, placed
    around the camera path so the highlights slide over the goo as the camera pushes and rolls."""
    O = P["O"]
    gold = ctx.palette(ctx.act_at(P["w0"]))["key"]
    boxes = [((-0.9, 0.75, 1.3), (1.0, 0.86, 0.62), 1.2, (1.6, 0.05)),
             ((1.1, -0.55, 1.1), (0.70, 0.62, 1.0), 1.0, (1.2, 0.04)),
             ((0.2, 1.0, 0.7), gold, 0.9, (0.9, 0.035)),
             ((-0.6, -0.9, 0.9), (0.9, 0.95, 1.0), 0.7, (1.0, 0.03))]
    for i, (pos, col, st, (w, h)) in enumerate(boxes):
        bx = X.plane_obj(f"XA_sym_box{i}", w, h, coll)
        loc = O + Vector(pos)
        bx.location = loc
        bx.rotation_mode = "QUATERNION"
        bx.rotation_quaternion = (O - loc).to_track_quat("Z", "Y")
        bx.data.materials.append(X.mat_emit(f"XA_sym_box{i}_m", col, st * 6.0))
        bx.visible_camera = False
        bx.visible_shadow = False
    for i, (pos, col, pw) in enumerate([((0.35, 0.3, 0.6), (1.0, 0.9, 0.75), 18.0),
                                        ((-0.4, -0.2, 0.5), (0.75, 0.65, 1.0), 14.0)]):
        ld = bpy.data.lights.new(f"XA_sym_pt{i}", "POINT")
        ld.energy = pw
        ld.color = col
        ld.shadow_soft_size = 0.02
        lo = bpy.data.objects.new(f"XA_sym_pt{i}", ld)
        lo.visible_camera = False
        lo.location = O + Vector(pos)
        coll.objects.link(lo)
