"""sling_ring (C24, S24 flying kick -> S25 shuriken, window 611-626, cut 620): a Doctor Strange sling ring.

A spark head whips round and draws an orange ring on S24 beside the kick; it spins open (sparks streaking in arcs with
real deformation motion blur, embers flung off tangentially, two counter-rotating sigil circles), and S25 is already playing inside it (a private set: the S25 copy waits deep behind a hole cut in
the S24 copy). The camera pans onto the ring and pushes through it; the ring blows past the frame edges, embers stream
past the lens, and S25 lands still pushing in (its own in-drift) with a rack focus.

Teleports: home S24 -> private set at w0 + 0.5 (identical copy), private set -> home S25 at HANDOFF (S25 copy fills
the frame, sparks behind the camera).
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
ORANGE = (1.0, 0.36, 0.04)
HOT = (1.0, 0.78, 0.38)


def _softclamp(x, L):
    return 0.0 if L <= 1e-6 else L * math.tanh(x / L)


def _plan(T, ctx):
    key = (T["id"], T["w0"], T["w1"], T["f"])
    if key in _PLAN:
        return _PLAN[key]
    w0, w1, cut = T["w0"], T["w1"], T["f"]
    a, b = T["a"]["id"], T["b"]["id"]
    p = T.get("p", {})
    P = dict(w0=w0, w1=w1, cut=cut, a=a, b=b)
    ring_px = tuple(p.get("ring", (1150.0, 505.0)))  # beside the kick, like a: 166-180
    R0 = float(p.get("radius", 225.0))
    P["ring_px"], P["R0"] = ring_px, R0
    s0, ds0 = float(p.get("s0", 1.08)), float(p.get("ds0", 0.015))
    z0 = FILL / s0
    # S25 lands zoomed in (+13 %/f decaying, REFS) and still pushing; the S25 copy is big and deep so its edges never
    # show once the camera is through the ring: s(cut) / s_end = d_end / (d_end + travel after the ring)
    s_end, ds_end = 1.35, X.exit_rate(ctx, T, 0.03)
    kB = 5.6
    v_end = (FILL * kB / s_end) * ds_end
    spd = X.Speed([(w0, z0 * ds0), (w0 + 3, 0.05), (w0 + 5, 0.12), (w0 + 6.5, 0.25), (cut - 1.5, 0.45),
                   (cut - 0.5, 0.75), (cut + 0.5, 0.70), (cut + 1.5, 0.40), (cut + 2.5, 0.20), (cut + 4, 0.08),
                   (w1, v_end)], m0=0.004)
    z = lambda t: z0 - spd.x(t)  # noqa: E731
    P["z"], P["spd"] = z, spd
    zB = z(w1) - FILL * kB / s_end
    P["zB"], P["kB"] = zB, kB
    rs = X.Speed([(w0, 0.0), (w0 + 4, -0.8), (w0 + 7, -2.5), (cut - 0.5, -6.0), (cut + 1, -5.0), (cut + 3, -1.6),
                  (w1, -0.12)], m0=0.0)
    roll = lambda t: rs.x(t)  # noqa: E731
    P["roll"] = roll
    O = ctx.new_set("sling_ring")
    P["O"] = O
    P["MA"] = Matrix.Translation(O)
    ax = X.px2local(*ring_px)
    P["axis"] = ax
    PB = tuple(p.get("b_axis", (800.0, 450.0)))  # S25 point on the ring axis, between his eye and the shuriken
    P["PB"] = PB
    theta = roll(w1) - 0.0
    MB_local = (Matrix.Translation(Vector((ax.x, ax.y, zB))) @ Quaternion((0, 0, 1), math.radians(theta)).to_matrix().to_4x4()
                @ Matrix.Scale(kB, 4) @ Matrix.Translation(-X.px2local(*PB)))
    P["MB"] = Matrix.Translation(O) @ MB_local
    P["theta"] = theta
    P["handoff"] = cut + 3.5
    P["lat0"] = cut + 0.5
    foc = PB  # no re-centring after the ring: S25 lands on the ring axis and the hold takes it from there

    def a_center(t):
        zt = z(t)
        if zt <= 0.03:
            return ring_px
        s = FILL / zt
        Lx, Ly = max(0.0, 960 - 960 / s - 12), max(0.0, 540 - 540 / s - 6)
        u = X._sstep(w0 - 1.0, cut - 0.5, t)  # pan onto the ring as it opens
        tx, ty = 960 + (ring_px[0] - 960) * u, 540 + (ring_px[1] - 540) * u
        return (960 + _softclamp(tx - 960, Lx), 540 + _softclamp(ty - 540, Ly))

    def b_state(t):
        s = FILL * kB / (z(t) - zB)
        Lx, Ly = max(0.0, 960 - 960 / s - 12), max(0.0, 540 - 540 / s - 6)
        u = X._sstep(P["lat0"] - 1.0, w1 - 0.5, t)
        tx, ty = PB[0] + (foc[0] - PB[0]) * u, PB[1] + (foc[1] - PB[1]) * u
        if p.get("tiled", True):  # copies are mirror-tiled like the home cards: no clamp, no pan left at the exit
            return (s, tx, ty, roll(t) - theta)
        return (s, 960 + _softclamp(tx - 960, Lx), 540 + _softclamp(ty - 540, Ly), roll(t) - theta)

    def m_set(t):
        if t >= P["lat0"]:
            return X.cam_world(P["MB"], camlib.State(*b_state(t)))
        ca = a_center(t)
        loc = O + Vector((ax.x + (ca[0] - ring_px[0]) / 1000.0, ax.y + (ring_px[1] - ca[1]) / 1000.0, z(t)))
        return Matrix.Translation(loc) @ Quaternion((0, 0, 1), math.radians(roll(t))).to_matrix().to_4x4()

    P["a_state"] = lambda t: (FILL / z(t), *a_center(t), roll(t))  # noqa: E731
    P["b_state"], P["m_set"] = b_state, m_set
    _PLAN[key] = P
    return P


def bounds(T, ctx):
    P = _plan(T, ctx)
    return {"A": X.mix_state(P["a_state"], P["w0"]), "B": X.mix_state_back(P["b_state"], P["w1"])}


# ------------------------------------------------------------------------------------------------- sparks
def _ring_radius(P, t):
    """Ring radius in metres: drawn open fast, breathing slightly, flaring as the camera passes."""
    w0 = P["w0"]
    R = P["R0"] / 1000.0
    u = X._sstep(w0 + 0.2, w0 + 3.2, t)
    return R * (0.15 + 0.85 * u ** 0.6) * (1 + 0.025 * math.sin(t * 1.9)) * (1 + 0.25 * X._sstep(P["cut"] - 1, P["w1"], t))


def _sparks(P, ctx, coll):
    """One mesh of streak-shaped sparks animated by half-frame shape keys (numpy, seeded)."""
    w0, w1, cut = P["w0"], P["w1"], P["cut"]
    rg = np.random.default_rng(620)
    NR, NE = 900, 700
    th0 = rg.uniform(0, 2 * np.pi, NR)
    om = np.radians(rg.uniform(16, 32, NR))  # clockwise on screen = negative angle in local XY
    rj = rg.normal(0, 0.016, NR)
    zj = rg.normal(0, 0.006, NR)
    sz = rg.uniform(0.0025, 0.006, NR)
    heat_r = rg.uniform(0.3, 1.0, NR)
    # embers: born on the ring, flung tangentially/outward and toward the camera, gravity, shrinking
    eb = rg.uniform(w0 + 1.0, cut + 1.5, NE)
    el = rg.uniform(3.0, 7.0, NE)
    eth = rg.uniform(0, 2 * np.pi, NE)
    ev = rg.uniform(0.012, 0.05, NE)
    eo = rg.uniform(-0.3, 0.6, NE)  # outward share
    ez = rg.uniform(-0.01, 0.06, NE)
    esz = rg.uniform(0.002, 0.005, NE)
    heat_e = rg.uniform(0.0, 0.7, NE)
    N = NR + NE
    ax = P["axis"]

    def state(t):
        R = _ring_radius(P, t)
        # ring sparks: the drawing head sweeps 0 -> 360 deg over the first 2.5 f; a spark shows once swept
        sweep = 2 * np.pi * X._sstep(w0, w0 + 2.6, t) * 1.05
        ang = th0 - om * (t - w0)
        vis_r = ((th0 % (2 * np.pi)) <= sweep).astype(float)
        rr = R * (1 + rj)
        cx = rr * np.cos(ang)
        cy = rr * np.sin(ang)
        czz = zj + 0.004
        dx, dy = np.sin(ang), -np.cos(ang)  # clockwise tangent
        Lr = sz * (2.5 + 6.0 * om) * vis_r
        Wr = sz * 0.35 * vis_r
        # embers
        age = t - eb
        alive = ((age >= 0) & (age <= el)).astype(float)
        a_ = np.clip(age, 0, None)
        Rb = np.array([_ring_radius(P, float(x)) for x in eb])
        ba = eth - np.radians(24.0) * (eb - w0)
        tx, ty = np.sin(ba), -np.cos(ba)
        ox, oy = np.cos(ba), np.sin(ba)
        vx = ev * (tx + eo * ox)
        vy = ev * (ty + eo * oy)
        ex = Rb * ox + vx * a_
        ey = Rb * oy + vy * a_ - 0.0015 * a_ ** 2
        ezz = 0.004 + ez * a_
        sp = np.sqrt(vx ** 2 + (vy - 0.003 * a_) ** 2) + 1e-6
        edx, edy = vx / sp, (vy - 0.003 * a_) / sp
        life = np.clip(1 - a_ / el, 0, 1) * alive
        Le = esz * (2.0 + 40 * ev) * life
        We = esz * 0.4 * life
        C = np.concatenate([np.stack([cx, cy, czz], 1), np.stack([ex, ey, ezz], 1)])
        D = np.concatenate([np.stack([dx, dy], 1), np.stack([edx, edy], 1)])
        L = np.concatenate([Lr, Le])
        Wd = np.concatenate([Wr, We])
        return C, D, L, Wd

    def verts(t):
        C, D, L, Wd = state(t)
        nx, ny = -D[:, 1], D[:, 0]
        v = np.zeros((N, 4, 3), np.float32)
        v[:, 0, 0] = C[:, 0] + D[:, 0] * L
        v[:, 0, 1] = C[:, 1] + D[:, 1] * L
        v[:, 1, 0] = C[:, 0] + nx * Wd
        v[:, 1, 1] = C[:, 1] + ny * Wd
        v[:, 2, 0] = C[:, 0] - D[:, 0] * L * 0.35
        v[:, 2, 1] = C[:, 1] - D[:, 1] * L * 0.35
        v[:, 3, 0] = C[:, 0] - nx * Wd
        v[:, 3, 1] = C[:, 1] - ny * Wd
        v[:, :, 2] = C[:, 2:3]
        v[:, :, 0] += ax.x
        v[:, :, 1] += ax.y
        return v.reshape(-1, 3)

    v0 = verts(float(w0))
    faces = [(4 * i, 4 * i + 1, 4 * i + 2, 4 * i + 3) for i in range(N)]
    ob = X.mesh_obj("XA_sling_sparks", [tuple(x) for x in v0], faces, coll)
    ob.matrix_world = P["MA"]
    heat = np.repeat(np.concatenate([heat_r, heat_e]), 4).astype(np.float32)
    at = ob.data.attributes.new("heat", "FLOAT", "POINT")
    at.data.foreach_set("value", heat)
    ob.shape_key_add(name="Basis", from_mix=False)
    ts = [w0 - 1 + 0.5 * i for i in range(int((w1 + 1 - (w0 - 1)) * 2) + 1)]
    for t in ts:
        kb = ob.shape_key_add(name=f"t{t:.1f}", from_mix=False)
        kb.data.foreach_set("co", verts(t).ravel())
        for tt, v in ((t - 0.5, 0.0), (t, 1.0), (t + 0.5, 0.0)):
            kb.value = v
            kb.keyframe_insert("value", frame=tt)
        kb.value = 0.0
    X.set_linear(ob.data.shape_keys)
    ob.cycles.motion_steps = 2 if hasattr(ob, "cycles") else 1
    m, nt, out = X._nodes("XA_sling_spark_m")
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "heat"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*ORANGE, 1)
    ramp.color_ramp.elements[1].color = (1.0, 0.92, 0.7, 1)
    nt.links.new(attr.outputs["Fac"], ramp.inputs[0])
    em = X.node(nt, "ShaderNodeEmission", Strength=22.0)
    nt.links.new(ramp.outputs[0], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    ob.data.materials.append(m)
    return ob


def _sigil_mat(name, seed, strength, col):
    """Rune circle: rings of glyph-like marks from a cellular pattern along the annulus, two border lines."""
    m, nt, out = X._nodes(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    u, v = sep.outputs[0], sep.outputs[1]
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(X.math_node(nt, "MULTIPLY", u, 64.0), comb.inputs[0])
    nt.links.new(X.math_node(nt, "MULTIPLY", v, 3.0), comb.inputs[1])
    comb.inputs[2].default_value = seed
    vo = X.node(nt, "ShaderNodeTexVoronoi", Scale=1.0)
    vo.feature = "DISTANCE_TO_EDGE"
    nt.links.new(comb.outputs[0], vo.inputs["Vector"])
    glyph = X.math_node(nt, "LESS_THAN", vo.outputs["Distance"], 0.06)
    band = X.math_node(nt, "MULTIPLY", X.math_node(nt, "GREATER_THAN", v, 0.18),
                       X.math_node(nt, "LESS_THAN", v, 0.82))
    glyph = X.math_node(nt, "MULTIPLY", glyph, band)
    edge = X.math_node(nt, "ADD", X.math_node(nt, "LESS_THAN", v, 0.07), X.math_node(nt, "GREATER_THAN", v, 0.93))
    mask = X.math_node(nt, "MINIMUM", X.math_node(nt, "ADD", glyph, edge), 1.0)
    fade = X.key_value(nt, "fade", [], 1.0)
    em = X.node(nt, "ShaderNodeEmission", Color=(*col, 1))
    nt.links.new(X.math_node(nt, "MULTIPLY", X.math_node(nt, "MULTIPLY", mask, fade), strength), em.inputs["Strength"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(em.outputs[0], add.inputs[0])
    nt.links.new(tr.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return m


# ------------------------------------------------------------------------------------------------- build
def build(T, ctx):
    P = _plan(T, ctx)
    w0, w1, cut, O = P["w0"], P["w1"], P["cut"], P["O"]
    a, b = P["a"], P["b"]
    ax = P["axis"]
    plate_c, light_c = ctx.coll("plate"), ctx.coll("light")
    R0 = P["R0"]
    hole_keys = [(f, 1000.0 * _ring_radius(P, f) * 0.94) for f in [w0 + 0.5 * i for i in range(2 * (w1 - w0) + 1)]]
    X.copy_card(ctx, a, "XA_sling_S24", P["MA"], frames=(w0 - 1, cut + 2),
                hole=dict(center=list(P["ring_px"]), radius=hole_keys, feather=6.0))
    X.copy_card(ctx, b, "XA_sling_S25", P["MB"], frames=(w0 - 1, w1 + 1))
    _sparks(P, ctx, light_c)
    # sigil circles and the glow, scaled with the ring
    parts = []
    for i, (r0, r1, spin, st, seed) in enumerate([(0.80, 0.93, 4.5, 7.0, 3.0), (1.07, 1.22, -3.0, 5.0, 11.0)]):
        an = X.annulus_obj(f"XA_sling_sigil{i}", r0, r1, light_c, n=192, nr=1)
        an.data.materials.append(_sigil_mat(f"XA_sling_sigil{i}_m", seed, st, ORANGE))
        parts.append((an, spin))
    glow = X.annulus_obj("XA_sling_glow", 0.95, 1.06, light_c, n=160, nr=2)
    glow.data.materials.append(_glow_mat())
    parts.append((glow, 0.0))
    for ob, spin in parts:
        ob.rotation_mode = "XYZ"
        for i in range(2 * (w1 - w0 + 2) + 1):
            t = w0 - 1 + 0.5 * i
            R = _ring_radius(P, t)
            op = X._sstep(w0 + 0.8, w0 + 3.5, t) if ob is not glow else X._sstep(w0, w0 + 2.5, t)
            sc = max(R * (0.6 + 0.4 * op), 1e-4)
            ob.location = O + Vector((ax.x, ax.y, 0.003 + 0.001 * parts.index((ob, spin))))
            ob.scale = (sc, sc, sc)
            ob.rotation_euler = (0, 0, -math.radians(spin * (t - w0)))
            ob.keyframe_insert("location", frame=t)
            ob.keyframe_insert("scale", frame=t)
            ob.keyframe_insert("rotation_euler", frame=t)
        X.set_linear(ob)
    ctx.env(O, ctx.act_at(cut))

    homeA = ctx.card(a).matrix_world.copy()
    homeB = ctx.card(b).matrix_world.copy()
    t_in, t_out = w0 + 0.5, P["handoff"]
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
        d = P["z"](t) - P["zB"]
        if t > t_out:
            d /= P["kB"]
        u = X._sstep(cut + 0.5, cut + 6.0, t)
        k = X._sstep(cut - 0.5, cut + 0.5, t)
        return d * X.lerp(0.4, 1.0, u), X.lerp(64.0, X.lerp(1.4, 64.0, u), k)

    X.key_path(ctx, w0, w1, fn, teleports=(t_in, t_out), dof_fn=dof)
    _wash(P, light_c)
    ctx.log(f"sling_ring: ring at {P['ring_px']} r{R0:.0f}px, through the ring plane at f{_cross(P):.1f}, "
            f"S25 copy {-P['zB']:.1f} m deep x{P['kB']}")


def _cross(P):
    t = P["w0"]
    while P["z"](t) > 0 and t < P["w1"]:
        t += 0.05
    return t


def _norm(m):
    loc, rot, _ = m.decompose()
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()


def _wash(P, coll):
    """REFS a07: the whole frame floods orange for ~4 f as the ring passes the lens. A veil riding 6 cm in front of the
    camera (private set only), hot at the edges, opacity peaking as the camera crosses the ring plane."""
    cut = P["cut"]
    ve = X.plane_obj("XA_sling_wash", 0.16, 0.09, coll)
    m, nt, out = X._nodes("XA_sling_wash_m")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    gr = nt.nodes.new("ShaderNodeTexGradient")
    gr.gradient_type = "SPHERICAL"
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Location"].default_value = (0.5, 0.5, 0)
    mp.inputs["Scale"].default_value = (1.4, 2.4, 1)
    nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
    mp2 = nt.nodes.new("ShaderNodeMapping")
    mp2.inputs["Location"].default_value = (-0.5, -0.5, 0)
    nt.links.new(mp.outputs[0], mp2.inputs["Vector"])
    nt.links.new(mp2.outputs[0], gr.inputs["Vector"])
    edge = X.math_node(nt, "SUBTRACT", 1.0, X.math_node(nt, "POWER", gr.outputs["Fac"], 0.6))
    op = X.key_value(nt, "opacity", [(cut - 3.0, 0.0), (cut - 1.5, 0.2), (cut - 0.3, 0.36), (cut + 0.7, 0.26),
                                     (cut + 1.7, 0.1), (cut + 2.5, 0.0)])
    a = X.math_node(nt, "MINIMUM", X.math_node(nt, "MULTIPLY", op, X.math_node(nt, "ADD", 0.45, edge)), 1.0)
    em = X.node(nt, "ShaderNodeEmission", Color=(1.0, 0.34, 0.04, 1), Strength=1.3)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(a, mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    ve.data.materials.append(m)
    ve.rotation_mode = "QUATERNION"
    for i in range(int(2 * (P["handoff"] - P["w0"])) + 1):
        t = P["w0"] + 0.5 + 0.5 * i
        ve.matrix_world = P["m_set"](t) @ Matrix.Translation(Vector((0, 0, -0.06)))
        ve.keyframe_insert("location", frame=t)
        ve.keyframe_insert("rotation_quaternion", frame=t)
    X.set_linear(ve)
    X.key_hide(ve, [(cut - 3, int(P["handoff"]))])


def _glow_mat():
    m, nt, out = X._nodes("XA_sling_glow_m")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    v = sep.outputs[1]
    prof = X.math_node(nt, "POWER", X.math_node(nt, "SINE", X.math_node(nt, "MULTIPLY", v, math.pi)), 3.0)
    no = X.node(nt, "ShaderNodeTexNoise", Scale=14.0, Detail=5.0)
    nt.links.new(tc.outputs["Object"], no.inputs["Vector"])
    st = X.math_node(nt, "MULTIPLY", X.math_node(nt, "MULTIPLY", prof, X.math_node(nt, "ADD", no.outputs["Fac"], 0.2)), 2.0)
    em = X.node(nt, "ShaderNodeEmission", Color=(*ORANGE, 1))
    nt.links.new(st, em.inputs["Strength"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(em.outputs[0], add.inputs[0])
    nt.links.new(tr.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return m
