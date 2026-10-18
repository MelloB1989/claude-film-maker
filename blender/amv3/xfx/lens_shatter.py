"""lens_shatter (C17, the DROP, 469-494, cut 480), v3.1 nested lens zoom (EDIT.md "v3.1: nested null-camera zooms").

The camera flies INTO Andrew's lens; the clips stay still in 3D. One private set: A (S17, A09) is a static card whose
lens opening (the region mask $AMV3_DATA/regions/S17/lens/ when it exists, else a tracked lens-shaped stand-in: a tapered
superellipse fitted to the A09 lens) turns transparent with a feathered edge from ~8 f before the cut, so Tom's M01 is
already playing inside the lens, framed small; B is a static card far behind it, placed and scaled so its lens framing
fills the opening from the camera at the reveal and the camera's straight path down the lens axis ends exactly on
Tom's lens hold framing. Depth of field sits on B, so Andrew's mask defocuses as the camera nears it. Over the opening is
the lens GLASS (bevelled shards cut from the lens shape, carrying a faint trace of the hex lens); cracks race across it
from 477 and on 480, as the camera passes through the plane, it shatters: the shards stay almost still in the world,
part around the camera's path and tumble while the camera flies past them, with a refractive shock ring, a flash,
glints and lingering flakes between the planes. The camera decelerates (k 0.83) onto Tom's lens, rolling clockwise.
Invisible teleports at w0+0.5 (home A -> the set, same view) and w1-0.5 (the set -> home B, same view).
"""
import json
import math
import os
import random
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fx3d as fx  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from camlib import State, FILL_DIST  # noqa: E402

# the A09 lens stand-in in plate pixels relative to the lens track: semi axes, rotation, offset, exponent, taper
LENS = dict(a=470.0, b=250.0, th=-17.0, ox=-5.0, oy=75.0, e=0.75, taper=0.28)


def _track(ctx, sid, f, default):
    if hasattr(ctx, "track"):
        t = ctx.track(sid, f)
        if t:
            return list(t)
        return list(default)
    p = os.path.join(ctx.data, "tracks", "%s.json" % sid)
    if not os.path.exists(p):
        return list(default)
    fr = json.load(open(p)).get("frames", {})
    if not fr:
        return list(default)
    k = min(fr, key=lambda x: abs(float(x) - f))
    return list(fr[k])


def _region(ctx, sid, kind="lens"):
    p = os.path.join(ctx.data, "regions", sid, kind, "region.json")
    if not os.path.exists(p):
        return None
    try:
        fr = json.load(open(p)).get("frames", {})
        return {int(k): v for k, v in fr.items() if v and v.get("area", 0) > 0}
    except Exception:  # noqa: BLE001
        return None


def _region_at(reg, f):
    k = min(reg, key=lambda x: abs(x - f))
    return reg[k]


def region_poly(r, n=64, shrink=0.94):
    """The region's fitted ellipse (cx, cy, w, h, angle deg, plate px), slightly inside the edge."""
    a, b, th = 0.5 * r["w"] * shrink, 0.5 * r["h"] * shrink, math.radians(r["angle"])
    return [(r["cx"] + a * math.cos(t) * math.cos(th) - b * math.sin(t) * math.sin(th),
             r["cy"] + a * math.cos(t) * math.sin(th) + b * math.sin(t) * math.cos(th))
            for t in (2 * math.pi * k / n for k in range(n))]


def lens_poly(c, n=96, grow=1.0):
    """The stand-in lens outline (plate px) around track point c."""
    L = LENS
    r = math.radians(L["th"])
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n
        cc, ss = math.cos(t), math.sin(t)
        x = L["a"] * grow * math.copysign(abs(cc) ** L["e"], cc)
        y = L["b"] * grow * math.copysign(abs(ss) ** L["e"], ss) * (1 + L["taper"] * x / (L["a"] * grow))
        pts.append((c[0] + L["ox"] + x * math.cos(r) - y * math.sin(r), c[1] + L["oy"] + x * math.sin(r) + y * math.cos(r)))
    return pts


def _hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


class Path:
    """The camera in the set (A card at the origin, normal +Z): xy glides onto the lens axis, z flies through the A
    plane on the cut frame, then decelerates; B's placement follows from the framings at the reveal and at the exit."""

    def __init__(self, T, ctx, P, A):
        self.T, self.P, self.A = T, P, A
        w0, w1, f = T["w0"], T["w1"], T["f"]
        self.fc = f - 0.5                                   # the camera crosses the glass at the half frame before the cut
        self.z0 = FILL_DIST / A.s
        self.v0 = A.ds * self.z0
        TA = self.fc - w0
        self.vp = max(2.0 * self.z0 / TA - self.v0, 1.4 * self.z0 / TA)   # speed through the glass
        self.lam = -math.log(P["decay"])
        TB = w1 - self.fc
        self.v_end = P["ds_out"] * 1.0                       # placeholder, solved below via the exit distance
        # lens axis: the lens centre at the crossing (A card metres)
        reg = _region(ctx, T["a"]["id"])
        if reg:
            r = _region_at(reg, self.fc - 0.5)
            cl = (r["cx"], r["cy"])
        else:
            lc = _track(ctx, T["a"]["id"], self.fc - 0.5, P["lens_a"])
            cl = (lc[0] + LENS["ox"], lc[1] + LENS["oy"])
        self.axis = fx.px2local(*cl)
        self.x0 = fx.px2local(A.cx, A.cy)
        # after the crossing: z(u) = -(v_end u + (vp - v_end)(1 - q^u)/lam); exit distance to B = k FILL / s_out and
        # B's zoom rate at the exit = v(TB) / dist = ds_out -> solve v_end by fixed point
        dist = 1.4
        for _ in range(30):
            self.v_end = P["ds_out"] * dist * 0.98
            z_end = self._zB(TB)
            t_r = P["t_reveal"]
            z_r = self._zA(t_r - w0)
            sv, so = P["s_vis"], P["s_out"]
            D = (sv * z_r - so * z_end) / (so - sv)
            k = so * (z_end + D) / FILL_DIST
            dist = z_end + D
        self.D, self.k, self.z_end = D, k, z_end
        lb = _track(ctx, T["b"]["id"], w1, P["lens_b"])
        self.lb = fx.safe_center(lb[0], lb[1], P["s_out"], P["r_out"])
        xl = fx.px2local(*self.lb)
        self.B_origin = Vector((self.axis.x - k * xl.x, self.axis.y - k * xl.y, -D))
        self.rA = fx.attack(A.r, A.dr, P["dr_cross"], TA, 0.0, 1.35, P["decay"])
        self.rB = fx.landing(P["r_out"], P["dr_cross"], P["dr_out"], TB, P["decay"])

    def _zA(self, u):
        TA = self.fc - self.T["w0"]
        x = u / TA
        h00, h10, h01, h11 = 2 * x ** 3 - 3 * x ** 2 + 1, x ** 3 - 2 * x ** 2 + x, -2 * x ** 3 + 3 * x ** 2, x ** 3 - x ** 2
        return h00 * self.z0 + h10 * (-self.v0) * TA + h01 * 0.0 + h11 * (-self.vp) * TA

    def _zB(self, u):
        return -(self.v_end * u + (self.vp - self.v_end) * (1 - math.exp(-self.lam * u)) / self.lam)

    def _vB(self, u):
        return self.v_end + (self.vp - self.v_end) * math.exp(-self.lam * u)

    def z(self, t):
        return self._zA(t - self.T["w0"]) if t <= self.fc else self._zB(t - self.fc)

    def xy(self, t):
        k = fx.smooth((t - self.T["w0"]) / 7.0)
        return self.x0.lerp(self.axis, k)

    def r(self, t):
        return self.rA[0](t - self.T["w0"]) if t <= self.fc else self.rB[0](t - self.fc)

    def dr(self, t):
        return self.rA[1](t - self.T["w0"]) if t <= self.fc else self.rB[1](t - self.fc)

    def matrix(self, t, MO):
        p = self.xy(t)
        return MO @ Matrix.LocRotScale(Vector((p.x, p.y, self.z(t))), Quaternion((0, 0, 1), math.radians(self.r(t))),
                                       None)

    def stateB(self, t):
        """The camera seen from B's (k-scaled) copy, as a state on B's unscaled home card."""
        u = t - self.fc
        d = self._zB(u) + self.D
        p = self.xy(t)
        x, y = (p.x - self.B_origin.x) / self.k, (p.y - self.B_origin.y) / self.k
        cx, cy = x / fx.PX + 960.0, -y / fx.PX + 540.0
        return State(self.k * FILL_DIST / d, cx, cy, self.r(t), self._vB(u) / d, 0.0, 0.0, self.dr(t))


def _params(T, ctx):
    p = T["p"]
    f = T["f"]
    return dict(s_vis=p.get("s_vis", 0.85), s_out=p.get("s_out", 1.50), ds_out=p.get("ds_out", 0.022),
                r_out=p.get("r_out", 7.0), dr_cross=p.get("dr_cross", 1.6), dr_out=0.12, decay=p.get("decay", 0.83),
                t_reveal=f - 7.0, reveal=(f - 9.0, f - 3.0), crack0=f - 3.5,
                lens_a=p.get("lens_a", T["a"]["focus"] or [960, 540]), lens_b=p.get("lens_b", T["b"]["focus"] or [960, 540]))


def bounds(T, ctx):
    P = _params(T, ctx)
    A = ctx.entry_state(T) if hasattr(ctx, "entry_state") else State(1.12, 1060, 484, 0.0)
    A = A.with_(ds=max(A.ds, 0.04)) if hasattr(A, "with_") else A
    pa = Path(T, ctx, P, A)
    return {"A": A, "B": pa.stateB(T["w1"])}


def build(T, ctx):
    fx.set_linear_keys()
    P = _params(T, ctx)
    A = bounds(T, ctx)["A"]
    pa = Path(T, ctx, P, A)
    f, w0, w1 = T["f"], T["w0"], T["w1"]
    fc = pa.fc
    sa, sb = T["a"]["id"], T["b"]["id"]
    cardA, cardB = ctx.card(sa), ctx.card(sb)
    O = ctx.new_set("lens_%s" % T["id"])
    MO = Matrix.Translation(O)
    rng = random.Random(4800 + f)
    light, plate = ctx.coll("light"), ctx.coll("plate")
    palA, palB = ctx.palette(fx.act_id(ctx, f - 1)), ctx.palette(fx.act_id(ctx, f))
    tp0, tp1 = w0 + 0.5, w1 - 0.5

    # ---- camera: home A -> (tp0) the set -> (tp1) home B, the same views on both sides of each jump
    def fn(t):
        if t < tp0:
            return ctx.pose(cardA, A.at(t - w0))
        if t > tp1:
            return ctx.pose(cardB, pa.stateB(t))
        loc, rot, _ = pa.matrix(t, MO).decompose()
        return loc, rot
    ctx.teleport(tp0)
    ctx.teleport(tp1)
    ctx.key_path(fn, w0, w1, 0.25)
    # DOF on B through the approach (A's mask defocuses as the camera nears it), racking to B's hold
    fx.dof(ctx, w0 + 1.0, pa.z(w0 + 1) + pa.D, 128.0)
    for t, fs in ((f - 8.0, 9.0), (f - 5.0, 3.2), (f - 2.0, 2.2), (fc, 2.0), (f + 3.0, 3.5), (f + 6.0, 9.0),
                  (f + 9.0, 40.0), (w1 - 1.0, 128.0)):
        fx.dof(ctx, t, pa.z(t) + pa.D, fs)

    # ---- the static cards: A with the feathered lens opening, B far behind it
    a_card = _lens_card(ctx, sa, MO, P, w0, w1)
    MB = MO @ Matrix.Translation(pa.B_origin) @ Matrix.Scale(pa.k, 4)
    try:
        ctx.make_card(sb, "ls_B_" + sb, matrix=MB, frames=(w0, w1 + 1), tile=3)
    except TypeError:
        ctx.make_card(sb, "ls_B_" + sb, matrix=MB)

    # ---- the lens glass over the opening: Voronoi shards of the lens shape at the cut
    reg = _region(ctx, sa)
    if reg:
        hull_px = _hull([(round(x, 2), round(y, 2)) for x, y in region_poly(_region_at(reg, fc - 0.5), 64, 1.0)])
    else:
        lc = _track(ctx, sa, fc - 0.5, P["lens_a"])
        hull_px = _hull([(round(x, 2), round(y, 2)) for x, y in lens_poly(lc, 64, 1.04)])
    hull = [((x - 960) * fx.PX, -(y - 540) * fx.PX) for x, y in hull_px]
    imp = pa.axis
    R = max(math.hypot(x - imp.x, y - imp.y) for x, y in hull)
    seeds = fx.impact_seeds(rng, (imp.x, imp.y), 0.012, R * 1.05, rings=6, sectors=12, jitter=0.6, swirl=0.33)
    cells = fx.voronoi(seeds, hull)
    face = fx.lens_glass_mat(fx.plate_mat(ctx, sa), "ls_face", pic=0.10)
    rim = fx.glass_mat("ls_rim", tint=(0.9, 0.97, 1.0), emit=palA["key"], emit_strength=0.6, rough=0.01, ior=1.5)
    M_glass = MO @ Matrix.Translation((0, 0, 0.004))
    shards = fx.build_shards(cells, M_glass, 0.003, [face, rim], plate, "ls_shard", rng, uv_fn=fx.local2uv,
                             bevel_w=0.0008)
    me_i, c_i = fx.shard_mesh("ls_glass_intact", hull, 0.003, fx.local2uv)  # one seamless slab until the break
    me_i.materials.append(face)
    me_i.materials.append(rim)
    glass_i = bpy.data.objects.new("ls_glass_intact", me_i)
    glass_i.matrix_world = M_glass @ Matrix.Translation(c_i)
    fx.link(glass_i, plate)
    fx.key_visible(glass_i, w0 - 0.5, fc - 1.0)
    edge_mat = fx.emission_mat("ls_edge", _mix(palA["key"], (1, 1, 1), 0.4), 2.0)
    prev = {}
    for sh in shards:
        c = (MO.inverted() @ sh.rest).translation
        off = Vector((c.x - imp.x, c.y - imp.y, 0.0))
        rn = min(off.length / R, 1.0)
        out = off.normalized() if off.length > 1e-6 else Vector((1, 0, 0))
        spin = sh.spin * (4 + 10 * (1 - rn)) * (1 if sh.jit.x > 0 else -1)
        q0 = sh.rest.to_quaternion()
        for t in fx.frames_half(w0, w1):
            u = max(0.0, t - (fc - 0.6) - 0.3 * rn)           # the break runs outward from the centre
            # parting round the camera's path (the centre opens first), then an almost-still drift and tumble
            part = out * (0.022 * (1 - rn) + 0.004) * (1 - math.exp(-1.2 * u))
            drift = out * 0.0025 * u + Vector((0, 0, 0.0035 * sh.jit.z * u)) + Vector((0, -0.0006 * u * u, 0))
            M = MO @ Matrix.LocRotScale(Vector((c.x, c.y, 0.004)) + part + drift,
                                        Quaternion(sh.axis, math.radians(spin * u * u / (u + 2.0))) @ q0, None)
            fx.key_matrix(sh.ob, t, M, prev)
        fx.key_visible(sh.ob, fc - 1.0, tp1)
        if sh.size > 0.03 and rng.random() < 0.5:
            eo = _edge_outline(sh, edge_mat, light)
            if eo:
                fx.key_visible(eo, fc - 1.0, tp1)
    for t, gw in ((w0, 0.2), (f - 3, 0.4), (fc - 0.5, 1.0), (fc, 0.8), (f + 2, 0.5), (f + 6, 0.2)):
        fx.key_glass_glow(rim, t, gw)
    for t, gw in ((fc - 1.0, 0.0), (fc, 1.5), (f + 3, 0.6), (f + 8, 0.2)):
        fx.key_glow(edge_mat, t, gw)

    # ---- cracks racing across the glass before the camera reaches it
    crack_mat = fx.crack_material("ls_crack", _mix(palA["key"], (1, 1, 1), 0.5), imp)
    splines = []
    for (p, q) in fx.cell_edges(cells):
        a, b = Vector((p[0], p[1], 0.0058)), Vector((q[0], q[1], 0.0058))
        mid, e = (a + b) / 2 - imp, b - a
        radial = mid.length < 1e-6 or abs(e.normalized().dot(mid.normalized())) > 0.55
        if not radial and rng.random() < 0.6:
            continue
        pts = fx.bolt_path(rng, a, b, 3, 0.07, normal=Vector((0, 0, 1)), zjag=0.0)
        splines.append([(v, 1.0) for v in pts])
    cr = fx.poly_curve("ls_cracks", splines, 0.00045, crack_mat)
    cr.matrix_world = MO
    fx.link(cr, light)
    fx.key_visible(cr, P["crack0"], fc + 0.5)
    for t, rr, g in ((P["crack0"], 0.0, 0.0), (f - 3, 0.06, 3.0), (f - 2, 0.35, 3.0), (f - 1.5, 0.6, 2.2),
                     (fc - 0.5, 1.3, 1.2), (fc + 0.5, 1.6, 0.3)):
        fx.key_crack(crack_mat, t, rr * R, g)

    # ---- the hit: shock ring in the glass plane, flash between the planes, sparks and chips, lingering flakes
    K = MO @ Matrix.Translation((imp.x, imp.y, 0.004))
    impK = Vector((0, 0, 0))
    fh = fc - 0.5
    _shockwave(K, impK, 0.08, fh, f, palA, palB, light, plate, rng)
    _flash(K, impK, pa.D * 0.5, fh, f, palB, light, 0.35)
    _chips(K, impK, 0.08, fh, f, palA, palB, light, plate, rng, face)
    _debris(K, pa.D, fh, f, w1, palA, plate, rng, face)
    cam_fn = lambda t: pa.matrix(t, MO)  # noqa: E731
    # glints only once the glass is broken (a flat intact slab mirrors an area light as a hard square)
    fx.camera_light("ls_keyB", cam_fn, fc - 1.0, tp1, Vector((-0.45, 0.35, 0.25)), palB["key"], 25.0, 0.4)
    fx.camera_light("ls_rimB", cam_fn, fc - 1.0, tp1, Vector((0.5, -0.3, 0.2)), palA["key"], 20.0, 0.35)
    ctx.log("lens_shatter v3.1: %d shards, R %.3f m, z0 %.3f v0 %.3f vp %.3f m/f, D %.3f k %.3f, z_end %.3f, "
            "B at reveal s %.2f, at cross s %.2f" % (len(shards), R, pa.z0, pa.v0, pa.vp, pa.D, pa.k, pa.z_end,
                                                    pa.k * FILL_DIST / (pa.z(P["t_reveal"]) + pa.D),
                                                    pa.k * FILL_DIST / pa.D))


def _lens_card(ctx, sid, MO, P, w0, w1):
    """A's static card with the lens opening: alpha = 1 - reveal * feathered lens mask (region mask when present, else
    the tracked stand-in shape). Emission of the plate, Transparent where open."""
    src = fx.plate_mat(ctx, sid)
    img_node = next(n for n in src.node_tree.nodes if n.type == "TEX_IMAGE")
    m = bpy.data.materials.new("ls_lenscard")
    nt = fx._nt(m)
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputMaterial")
    tc = N("ShaderNodeTexCoord")
    tex = N("ShaderNodeTexImage")
    tex.image = img_node.image
    tex.extension = "EXTEND"
    for k in ("frame_start", "frame_duration", "frame_offset", "use_cyclic", "use_auto_refresh"):
        setattr(tex.image_user, k, getattr(img_node.image_user, k))
    L(tc.outputs["UV"], tex.inputs["Vector"])
    em = N("ShaderNodeEmission")
    L(tex.outputs["Color"], em.inputs["Color"])
    tr = N("ShaderNodeBsdfTransparent")
    mix = N("ShaderNodeMixShader")
    L(em.outputs[0], mix.inputs[1])
    L(tr.outputs[0], mix.inputs[2])
    L(mix.outputs[0], out.inputs["Surface"])

    def mnode(op, a, b=None):
        n = N("ShaderNodeMath")
        n.operation = op
        for k, x in enumerate((a, b)):
            if x is None:
                continue
            if isinstance(x, (int, float)):
                n.inputs[k].default_value = x
            else:
                L(x, n.inputs[k])
        return n.outputs[0]
    sep = N("ShaderNodeSeparateXYZ")
    L(tc.outputs["UV"], sep.inputs[0])
    px = mnode("MULTIPLY", sep.outputs[0], 1920.0)
    py = mnode("MULTIPLY", mnode("SUBTRACT", 1.0, sep.outputs[1]), 1080.0)
    cxn, cyn, rev = N("ShaderNodeValue"), N("ShaderNodeValue"), N("ShaderNodeValue")
    Ls = LENS
    r = math.radians(Ls["th"])
    dx = mnode("SUBTRACT", px, cxn.outputs[0])
    dy = mnode("SUBTRACT", py, cyn.outputs[0])
    x = mnode("ADD", mnode("MULTIPLY", dx, math.cos(r)), mnode("MULTIPLY", dy, math.sin(r)))
    y = mnode("SUBTRACT", mnode("MULTIPLY", dy, math.cos(r)), mnode("MULTIPLY", dx, math.sin(r)))
    y = mnode("DIVIDE", y, mnode("ADD", 1.0, mnode("MULTIPLY", x, Ls["taper"] / Ls["a"])))
    ex = 2.0 / Ls["e"]
    d = mnode("ADD", mnode("POWER", mnode("ABSOLUTE", mnode("DIVIDE", x, Ls["a"])), ex),
              mnode("POWER", mnode("ABSOLUTE", mnode("DIVIDE", y, Ls["b"])), ex))
    fr = N("ShaderNodeMapRange")
    fr.interpolation_type = "SMOOTHSTEP"
    L(d, fr.inputs["Value"])
    fr.inputs["From Min"].default_value = 0.80
    fr.inputs["From Max"].default_value = 1.05
    fr.inputs["To Min"].default_value = 1.0
    fr.inputs["To Max"].default_value = 0.0
    mask = fr.outputs["Result"]
    region = os.path.join(ctx.data, "regions", sid, "lens")
    if os.path.isdir(region) and hasattr(ctx, "_sequence"):
        try:
            seq = ctx._sequence("regions", "%s/lens" % sid, "png")
            if seq is not None:
                rt = N("ShaderNodeTexImage")
                rt.image = seq
                for k in ("frame_start", "frame_duration", "frame_offset", "use_cyclic", "use_auto_refresh"):
                    setattr(rt.image_user, k, getattr(img_node.image_user, k))
                # feather the hard mask: a 3x3 box of taps FEATHER px apart, then a smoothstep
                fe = P.get("feather", 6.0)
                acc = None
                for dx_ in (-fe, 0.0, fe):
                    for dy_ in (-fe, 0.0, fe):
                        tap = N("ShaderNodeTexImage")
                        tap.image = seq
                        tap.interpolation = "Linear"
                        tap.extension = "EXTEND"
                        for k in ("frame_start", "frame_duration", "frame_offset", "use_cyclic", "use_auto_refresh"):
                            setattr(tap.image_user, k, getattr(img_node.image_user, k))
                        vm = N("ShaderNodeVectorMath")
                        vm.operation = "ADD"
                        vm.inputs[1].default_value = (dx_ / 1920.0, dy_ / 1080.0, 0.0)
                        L(tc.outputs["UV"], vm.inputs[0])
                        L(vm.outputs[0], tap.inputs["Vector"])
                        c = mnode("MULTIPLY", tap.outputs["Color"], 1.0 / 9.0)
                        acc = c if acc is None else mnode("ADD", acc, c)
                sm = N("ShaderNodeMapRange")
                sm.interpolation_type = "SMOOTHSTEP"
                L(acc, sm.inputs["Value"])
                sm.inputs["From Min"].default_value = 0.15
                sm.inputs["From Max"].default_value = 0.85
                mask = sm.outputs["Result"]
                rt.image = None
                ctx.log("lens_shatter: lens region masks from %s" % region)
        except Exception as e:  # noqa: BLE001
            ctx.log("lens_shatter: region masks failed (%s), stand-in shape" % e)
    L(mnode("MULTIPLY", mask, rev.outputs[0]), mix.inputs[0])
    for t in fx.frames_half(w0, w1):
        c = _track(ctx, sid, t, P["lens_a"])
        cxn.outputs[0].default_value = c[0] + Ls["ox"]
        cyn.outputs[0].default_value = c[1] + Ls["oy"]
        cxn.outputs[0].keyframe_insert("default_value", frame=t)
        cyn.outputs[0].keyframe_insert("default_value", frame=t)
    r0, r1 = P["reveal"]
    for t, v in ((w0, 0.0), (r0, 0.0), (0.5 * (r0 + r1), 0.55), (r1, 1.0)):
        rev.outputs[0].default_value = v
        rev.outputs[0].keyframe_insert("default_value", frame=t)
    me = fx.quad_mesh("ls_A", 1.92, 1.08)
    me.materials.append(m)
    ob = bpy.data.objects.new("ls_A", me)
    ob.matrix_world = MO
    ctx.coll("plate").objects.link(ob)
    fx.key_visible(ob, w0, w1)
    ob["amv3_shot"], ob["amv3_card"], ob["amv3_tile"] = sid, True, 1
    if hasattr(ctx, "all_cards"):
        ctx.all_cards.append(ob)   # so the gate measures A's picture as the camera flies into it
    return ob


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _edge_outline(sh, mat, coll):
    me = sh.ob.data
    zs = max(v.co.z for v in me.vertices)
    top = [v.co.copy() for v in me.vertices if abs(v.co.z - zs) < 1e-6]
    if len(top) < 3:
        return
    ang = sorted(top, key=lambda v: math.atan2(v.y, v.x))
    pts = [(Vector((v.x, v.y, v.z + 0.0002)), 1.0) for v in ang] + [(Vector((ang[0].x, ang[0].y, ang[0].z + 0.0002)), 1.0)]
    ob = fx.poly_curve(sh.ob.name + "_edge", [pts], 0.00035, mat, caps=False)
    ob.parent = sh.ob
    fx.link(ob, coll)
    return ob


def _light(M, p_local, color, watts, name, f_on, f_off, size=0.3, target=None):
    ld = bpy.data.lights.new(name, "AREA")
    ld.color = color[:3]
    ld.energy = watts
    ld.size = size
    ob = bpy.data.objects.new(name, ld)
    ob.visible_camera = False
    tgt = target if target is not None else Vector()
    d = (tgt - p_local)
    rot = d.to_track_quat("-Z", "Y")
    ob.matrix_world = M @ Matrix.LocRotScale(p_local, rot, None)
    bpy.context.scene.collection.objects.link(ob)
    fx.key_visible(ob, f_on, f_off)
    return ob


def _shockwave(K, impK, depth0, fh, f, palA, palB, light, plate, rng):
    """A refractive shock ring (a flattened glass torus that bends B behind it, falling off inward) with a thin bright
    leading edge split cyan-outside / warm-inside (a chromatic fringe), expanding fast and tilted so it sweeps by."""
    tq = Quaternion(Vector((1.0, 0.35, 0.0)).normalized(), math.radians(22.0))
    speed = 0.085

    def place(ob, scale_r, dz, zsq, prev):
        for t in fx.frames_half(fh, f + 6):
            u = max(0.0, t - fh)
            rad = 0.004 + speed * u * (1.0 - 0.05 * u)
            z = impK.z + depth0 * 0.22 * u + dz
            M = K @ Matrix.LocRotScale(Vector((impK.x, impK.y, z)), tq, Vector((rad * scale_r, rad * scale_r,
                                                                                  rad * zsq)))
            fx.key_matrix(ob, t, M, prev)
        fx.key_visible(ob, fh, f + 5)

    me = fx.torus_mesh("ls_ring_glass", 1.0, 0.11, 192, 16)
    me.materials.append(fx.glass_mat("ls_ring_glass", tint=(1, 1, 1), emit=(1, 1, 1), rough=0.0, ior=1.22))
    ob = bpy.data.objects.new("ls_ring_glass", me)
    fx.link(ob, plate)
    place(ob, 0.9, -0.004, 0.22, {})
    for name, col, sr, g0 in (("ls_edge_cyan", _mix(palA["key"], (1, 1, 1), 0.3), 1.012, 9.0),
                              ("ls_edge_warm", _mix(palB["key"], (1, 0.8, 0.3), 0.3), 0.992, 6.0)):
        me = fx.torus_mesh(name, 1.0, 0.0022, 192, 6)
        mat = fx.emission_mat(name, col, g0, additive=True)
        me.materials.append(mat)
        o = bpy.data.objects.new(name, me)
        fx.link(o, light)
        place(o, sr, 0.0, 1.0, {})
        for t, g in ((fh, 0.0), (f, g0), (f + 1.5, g0 * 0.5), (f + 3, g0 * 0.15), (f + 4.5, 0.0)):
            fx.key_glow(mat, t, g)


def _close_shards(K, impK, depth0, fh, f, palA, plate, rng):
    """A few big clear glass shards that tumble right past the lens (481-484): they refract and reflect B, bevel glints."""
    mat = fx.glass_mat("ls_big", tint=(0.96, 0.99, 1.0), emit=palA["key"], emit_strength=0.15, rough=0.0, ior=1.5)
    prev = {}
    for i in range(6):
        n = rng.choice((4, 5, 6))
        L = rng.uniform(0.025, 0.05)
        poly = [(L * math.cos(2 * math.pi * k / n + rng.uniform(-0.3, 0.3)) * rng.uniform(0.5, 1.4),
                 L * math.sin(2 * math.pi * k / n + rng.uniform(-0.3, 0.3)) * rng.uniform(0.5, 1.4)) for k in range(n)]
        hull = sorted(poly, key=lambda q: math.atan2(q[1], q[0]))
        me, _ = fx.shard_mesh("ls_big_%d" % i, hull, 0.003, None)
        me.materials.append(mat)
        me.materials.append(mat)
        ob = bpy.data.objects.new(me.name, me)
        fx.bevel(ob, 0.0009)
        fx.link(ob, plate)
        a = 2 * math.pi * (i + rng.uniform(-0.3, 0.3)) / 6
        start = Vector((math.cos(a) * 0.012, math.sin(a) * 0.008, impK.z * 0.55))
        end = Vector((math.cos(a) * 0.09, math.sin(a) * 0.06, -0.02))
        ax = fx.rand_axis(rng)
        t0 = f + 0.5 + 0.4 * i / 6
        for t in fx.frames_half(fh, f + 6):
            u = fx.clamp01((t - t0) / 3.0)
            pos = start.lerp(end, u ** 1.6)
            q = Quaternion(ax, math.radians(rng.uniform(55, 80) * 0 + 70 * u)) @ Quaternion((1, 0, 0), math.radians(25))
            fx.key_matrix(ob, t, K @ Matrix.LocRotScale(pos, q, None), prev)
        fx.key_visible(ob, round(t0 * 2) / 2, f + 4.5)


def _flash(K, impK, camB0, fh, f, pal, light, gain=1.0):
    import bmesh
    me = bpy.data.meshes.new("ls_flash")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    mat = fx.emission_mat("ls_flash", _mix(pal["key"], (1, 1, 1), 0.75), 0.0, additive=True)
    me.materials.append(mat)
    ob = bpy.data.objects.new("ls_flash", me)
    p = Vector((impK.x, impK.y, impK.z - 0.6 * (camB0 - (-impK.z))))
    ob.matrix_world = K @ Matrix.LocRotScale(p, Quaternion(), Vector((0.018, 0.018, 0.018)))
    fx.link(ob, light)
    for t, g in ((fh, 0.0), (f, 30.0 * gain), (f + 1, 9.0 * gain)):
        fx.key_glow(mat, t, g)
    fx.key_visible(ob, fh, f + 1.5)
    ld = bpy.data.lights.new("ls_flash_pt", "POINT")
    ld.color = _mix(pal["key"], (1, 1, 1), 0.6)
    ld.shadow_soft_size = 0.02
    lo = bpy.data.objects.new("ls_flash_pt", ld)
    lo.visible_camera = False
    lo.matrix_world = K @ Matrix.Translation(p)
    bpy.context.scene.collection.objects.link(lo)
    for t, e in ((fh, 0.0), (f, 60.0 * gain), (f + 1, 20.0 * gain), (f + 2, 5.0 * gain), (f + 4, 0.0)):
        ld.energy = e
        ld.keyframe_insert("energy", frame=t)


def _chips(K, impK, depth0, fh, f, palA, palB, light, plate, rng, face):
    """Glass chips (glints when they turn to the lights) and a few sparks of varied size, life and heat."""
    glass = fx.glass_mat("ls_chip", tint=(0.95, 0.98, 1.0), emit=palA["key"], emit_strength=0.4, rough=0.02)
    sparks = []
    for k in range(4):
        m = fx.emission_mat("ls_spark_%d" % k, _mix(palA["key"] if k % 2 else palB["key"], (1, 1, 1), 0.35 + 0.1 * k),
                            0.0, additive=True)
        g0 = (16.0, 9.0, 5.0, 2.5)[k]
        life = (2.5, 3.5, 4.5, 5.5)[k]
        for t, g in ((fh, g0), (f + life * 0.5, g0 * 0.6), (f + life, 0.0)):
            fx.key_glow(m, t, g)
        sparks.append(m)
    prev = {}
    for i in range(70):
        is_spark = i % 3 == 0
        sz = rng.uniform(0.0006, 0.0035) if not is_spark else rng.uniform(0.0002, 0.0007)
        n = rng.choice((3, 4, 5))
        poly = [(sz * math.cos(2 * math.pi * k / n + rng.uniform(-0.4, 0.4)) * rng.uniform(0.6, 1.3),
                 sz * math.sin(2 * math.pi * k / n + rng.uniform(-0.4, 0.4)) * rng.uniform(0.6, 1.3)) for k in range(n)]
        me, _ = fx.shard_mesh("ls_chip_%03d" % i, poly, sz * 0.4 if not is_spark else sz, None)
        m = sparks[rng.randrange(4)] if is_spark else glass
        me.materials.append(m)
        me.materials.append(m)
        ob = bpy.data.objects.new(me.name, me)
        fx.link(ob, light if is_spark else plate)
        a = rng.uniform(0, 2 * math.pi)
        el = rng.uniform(0.15, 1.0)
        v = Vector((math.cos(a) * el, math.sin(a) * el, rng.uniform(0.4, 1.4))) * rng.uniform(0.008, 0.05)
        ax = fx.rand_axis(rng)
        spin = rng.uniform(20, 70)
        t0 = fh + rng.uniform(0.0, 1.5)
        for t in fx.frames_half(fh, f + 7):
            u = max(0.0, t - t0)
            pos = Vector((impK.x, impK.y, impK.z - 0.01)) + v * u * (1.0 + 0.15 * u)
            M = K @ Matrix.LocRotScale(pos, Quaternion(ax, math.radians(spin * u)), None)
            fx.key_matrix(ob, t, M, prev)
        fx.key_visible(ob, round(t0 * 2) / 2, f + 6.5)


def _debris(K, camB0, fh, f, w1, palA, plate, rng, face):
    """After the burst a few glass flakes keep drifting and tumbling in front of Tom's lens to the end of the window
    (the reference's debris lingers for 6-10 f), twinkling as they turn through the lights."""
    mat = fx.glass_mat("ls_flake", tint=(0.96, 0.98, 1.0), emit=palA["key"], emit_strength=0.25, rough=0.01, ior=1.5)
    prev = {}
    for i in range(110):
        sz = rng.uniform(0.0015, 0.0075) * (1.0 if i % 4 else 1.6)
        n = rng.choice((3, 4, 5))
        poly = sorted([(sz * math.cos(2 * math.pi * k / n + rng.uniform(-0.4, 0.4)) * rng.uniform(0.5, 1.4),
                        sz * math.sin(2 * math.pi * k / n + rng.uniform(-0.4, 0.4)) * rng.uniform(0.5, 1.2))
                       for k in range(n)], key=lambda q: math.atan2(q[1], q[0]))
        me, _ = fx.shard_mesh("ls_flake_%02d" % i, poly, sz * 0.25, None)
        m0 = face if i % 5 < 2 else mat   # 40 % still carry Andrew's picture (blue lens, red mask) like the ref's debris
        me.materials.append(m0)
        me.materials.append(mat)
        if m0 is face:
            u0, v0 = rng.uniform(0.3, 0.7), rng.uniform(0.3, 0.7)
            uvl = me.uv_layers[0]
            for lp in me.loops:
                co = me.vertices[lp.vertex_index].co
                uvl.data[lp.index].uv = (u0 + co.x * 2.0, v0 + co.y * 2.0)
        ob = bpy.data.objects.new(me.name, me)
        fx.link(ob, plate)
        z = -camB0 * rng.uniform(0.25, 0.9)
        half = abs(z) * 0.55
        p0 = Vector((rng.uniform(-1.6, 1.6) * half, rng.uniform(-0.9, 0.9) * half, z))
        v0 = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.uniform(0.5, 2.0))) * 0.006 * abs(z)
        ax = fx.rand_axis(rng)
        spin = rng.uniform(8, 25)
        t0 = f + rng.uniform(0.0, 2.0)
        for t in fx.frames_half(round(t0 * 2) / 2, w1):
            u = t - t0
            pos = p0 + v0 * (u * 4.0 / (u + 4.0)) * 3.0   # thrown out, slowing (drag)
            M = K @ Matrix.LocRotScale(pos, Quaternion(ax, math.radians(spin * u)), None)
            fx.key_matrix(ob, t, M, prev)
        fx.key_visible(ob, round(t0 * 2) / 2, w1)
