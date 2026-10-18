"""eye_tunnel (C09, Tobey -> Andrew, window 236-264, cut 252): through Tobey's iris into the multiverse tunnel.

The camera is already pushing into Tobey's left iris (S08). The iris opens as a hole in the card with a burning gold rim,
the iris texture stretching back into a funnel; the camera flies through it into a tunnel whose walls are floating cards
playing moving frames from all three eras, wrapped in web strands, light rings and dust, spiralling (roll accumulates),
the light shifting from Tobey gold to Andrew cyan as it passes the cut. Andrew's lens (S09) waits at the end of the tunnel
behind a last cyan ring; the camera decelerates onto it and hands over to S09's pull-out.

One private set, one continuous camera path z(t) along the tunnel axis (a monotone-cubic speed profile, so the camera
never stops and never jerks). Teleports: home S08 -> private set at w0 + 0.5 (identical copy of the card, invisible),
private set -> home S09 at HANDOFF (the S09 copy fills the frame, invisible).
"""
import math
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.append(_here)
import bpy  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402

import _xfxa as X  # noqa: E402
import camlib  # noqa: E402

FILL = X.FILL
ERAS = {
    "tobey": ["S01", "S02", "S03", "S04", "S06", "S07"],
    "andrew": ["S10", "S11", "S12", "S13", "S14", "S15", "S16"],
    "tom": ["S18", "S19", "S21", "S23", "S25", "S27", "S28", "S30"],
}
_PLAN = {}


def _plan(T, ctx):
    key = (T["id"], T["w0"], T["w1"], T["f"])
    if key in _PLAN:
        return _PLAN[key]
    w0, w1, cut = T["w0"], T["w1"], T["f"]
    a, b = T["a"]["id"], T["b"]["id"]
    p = T.get("p", {})
    P = dict(w0=w0, w1=w1, cut=cut, a=a, b=b)
    # iris: static hole centre (contract), from the track around the moment the hole opens
    iris = X.track(ctx, a, w0 + 6, tuple(p.get("iris", (901, 390))))
    P["iris"] = iris
    s0, ds0 = float(p.get("s0", 1.15)), float(p.get("ds0", 0.035))  # matches C08's zt push landing on the iris
    z0 = FILL / s0
    P["z0"] = z0
    # handoff and exit framing on S09 (B)
    kB = 1.0  # the S09 copy floats at the tunnel end as a framed picture, small until the last frames
    s_end, ds_end = 1.15, -0.018  # REFS: holds never drift under ~1 %/f
    v_end = -(FILL * kB / s_end) * (-ds_end) * 1.0  # moving away from the card = pulling out
    u = lambda t: t - w0  # noqa: E731
    # dive through the iris (expo attack), a readable cruise through the multiverse, a 2-frame whoosh on the cut (REFS:
    # smear 1-3 f), then Andrew's lens: B lands at the cut speed and decays ~0.8 / f into S09's pull-out
    spd = X.Speed([
        (w0, z0 * ds0), (w0 + 4, 0.13), (w0 + 7, 0.32), (w0 + 8.5, 0.50), (w0 + 10.5, 0.36), (cut - 2.5, 0.34),
        (cut - 1, 0.62), (cut, 0.85), (cut + 1, 0.72), (cut + 2.5, 0.40), (cut + 4, 0.20), (cut + 5.5, 0.07),
        (cut + 7, 0.0), (w1, v_end)], m0=z0 * ds0 * 0.16)
    P["spd"] = spd
    z = lambda t: z0 - spd.x(t)  # noqa: E731  camera distance in front of the S08 copy along the axis
    P["z"] = z
    zB = z(w1) - FILL * kB / s_end
    P["zB"], P["kB"] = zB, kB
    # roll: one clockwise spiral, rate a smooth bell peaking at the cut
    rs = X.Speed([(w0, 0.0), (w0 + 4, 1.0), (w0 + 7, 2.6), (w0 + 9, 4.5), (w0 + 11, 2.8), (cut - 2, 3.2),
                  (cut - 0.5, 12.0), (cut + 0.5, 15.0), (cut + 2, 8.0), (cut + 4, 3.0), (cut + 7, 0.8), (w1, 0.12)],
                 m0=0.0)
    P["roll"] = lambda t: rs.x(t)  # noqa: E731
    r_end = 0.6
    theta = P["roll"](w1) - r_end
    P["theta"] = theta
    PB = (1036.0, 546.0) if not p.get("exit_lens") else tuple(p["exit_lens"])
    P["PB"] = PB
    O = ctx.new_set("eye_tunnel")
    P["O"] = O
    ax = X.px2local(*iris)
    P["axis"] = ax
    # S09 copy: lens point PB on the axis at depth zB, rotated theta about the axis, scaled kB
    lb = X.px2local(*PB)
    MB_local = (Matrix.Translation(Vector((ax.x, ax.y, zB))) @ Quaternion((0, 0, 1), math.radians(theta)).to_matrix().to_4x4()
                @ Matrix.Scale(kB, 4) @ Matrix.Translation(-lb))
    P["MA"] = Matrix.Translation(O)
    P["MB"] = Matrix.Translation(O) @ MB_local
    P["handoff"] = cut + 6.5
    P["lat0"] = cut + 2.0  # lateral re-centre on the moving lens starts here

    def wob(t):
        amp = 0.16 * X.bump(t, w0 + 9.5, cut + 1.5)
        ph = 0.45 * (t - w0) + 0.8
        return Vector((amp * math.cos(ph), amp * math.sin(ph), 0.0))

    def softclamp(x, L):
        return 0.0 if L <= 1e-6 else L * math.tanh(x / L)

    def b_state(t):
        """Camera as a State on the S09 copy (valid for t >= lat0)."""
        sB = FILL * kB / (z(t) - zB)
        lens = X.track(ctx, b, t, PB)
        Lx = max(0.0, 960 - 960 / sB - 12)
        Ly = max(0.0, 540 - 540 / sB - 6)
        tx, ty = 960 + softclamp(lens[0] - 960, Lx), 540 + softclamp(lens[1] - 540, Ly)
        wgt = X._sstep(P["lat0"], w1 + 1.0, t)
        return (sB, PB[0] + (tx - PB[0]) * wgt, PB[1] + (ty - PB[1]) * wgt, P["roll"](t) - theta)

    P["b_state"] = b_state

    def a_center(t):
        zt = z(t)
        if zt <= 0.05:
            return iris
        sA = FILL / zt
        Lx = max(0.0, 960 - 960 / sA - 12)
        Ly = max(0.0, 540 - 540 / sA - 6)
        return (960 + softclamp(iris[0] - 960, Lx), 540 + softclamp(iris[1] - 540, Ly))

    P["a_center"] = a_center

    def m_set(t):
        """World camera matrix in the private set."""
        if t >= P["lat0"]:
            sB, cx, cy, r = b_state(t)
            return X.cam_world(P["MB"], camlib.State(sB, cx, cy, r))
        o = wob(t)
        ca = a_center(t)
        o = o + Vector(((ca[0] - iris[0]) / 1000.0, (iris[1] - ca[1]) / 1000.0, 0.0))
        h = 0.05
        dw = (wob(t + h) - wob(t - h)) / (2 * h)  # look-ahead tilt follows the corkscrew, not the re-centring
        fwd = Vector((0.35 * dw.x, 0.35 * dw.y, (z(t + h) - z(t - h)) / (2 * h)))
        if fwd.length < 1e-6:
            fwd = Vector((0, 0, -1))
        q = Vector((0, 0, -1)).rotation_difference(fwd.normalized()) @ Quaternion((0, 0, 1), math.radians(P["roll"](t)))
        loc = O + Vector((ax.x + o.x, ax.y + o.y, z(t)))
        return Matrix.Translation(loc) @ q.to_matrix().to_4x4()

    P["m_set"] = m_set
    P["a_state"] = lambda t: (FILL / z(t), *a_center(t), P["roll"](t))  # noqa: E731
    _PLAN[key] = P
    return P


def bounds(T, ctx):
    P = _plan(T, ctx)
    A = X.mix_state(P["a_state"], P["w0"])
    sB, cx, cy, r = P["b_state"](P["w1"])
    Bst = X.mix_state_back(P["b_state"], P["w1"])
    return {"A": A, "B": Bst}


# ------------------------------------------------------------------------------------------------- build
def build(T, ctx):
    P = _plan(T, ctx)
    w0, w1, cut, O = P["w0"], P["w1"], P["cut"], P["O"]
    a, b = P["a"], P["b"]
    z, zB = P["z"], P["zB"]
    pal_a, pal_b = ctx.palette(ctx.act_at(cut - 1)), ctx.palette(ctx.act_at(cut))
    gold, cyan = pal_a["key"], pal_b["key"]
    plate_c, light_c = ctx.coll("plate"), ctx.coll("light")
    R = X.rng(9252)
    ax = P["axis"]
    z_cut = z(cut)

    def era_mix(zz):
        """0 = Tobey gold ... 1 = Andrew cyan, by depth (the camera passes the middle on the cut)."""
        return X._sstep(z_cut + 0.5, z_cut - 3.0, zz)

    # --- A copy with the iris hole (comp time, same plate as the home card)
    # hole radius from the camera path: its on-screen size grows ~x1.86 per frame from 4 % of the frame half-diagonal
    # to over-full in ~6 f (REFS: the hole grows to fill in 6 f); never shrinks on the card
    r_keys, rp = [], 0.0
    for i in range(2 * (cut + 1 - w0) + 1):
        t = w0 + 0.5 * i
        frac = 0.04 * math.exp(0.62 * (t - (w0 + 3.5))) * X._sstep(w0, w0 + 2.5, t)
        zt = z(t)
        r = frac * 1101.0 * zt / FILL if zt > 0.04 else 4000.0
        rp = max(rp, r)
        r_keys.append((t, rp))
    cardA = ctx.make_card(a, "XA_eye_S08", matrix=P["MA"], hole=dict(center=list(P["iris"]), radius=r_keys, feather=3.0))
    # hole rim (burning gold) and the iris funnel, both scaled with the hole radius
    rim = X.annulus_obj("XA_eye_rim", 0.97, 1.09, light_c, n=160, nr=2)
    rim.location = O + Vector((ax.x, ax.y, 0.002))
    rim.data.materials.append(_rim_mat("XA_eye_rim_m", gold, cyan))
    fun_zs = [-0.02 * (1.25 ** k) for k in range(14)]
    funnel = X.tube_obj("XA_eye_funnel", lambda zz, ang: ((1.0 - zz * 0.9) * math.cos(ang),
                                                         (1.0 - zz * 0.9) * math.sin(ang)), [0.0] + fun_zs, plate_c, n=128)
    funnel.location = O + Vector((ax.x, ax.y, 0.0))
    funnel.data.materials.append(_funnel_mat(ctx, a, P["iris"], r_keys, gold))
    for ob in (rim, funnel):
        for f, rpx in r_keys:
            sc = max(rpx, 0.001) / 1000.0
            ob.scale = (sc, sc, 1.0 if ob is rim else max(0.15, min(1.0, rpx / 300.0)))
            ob.keyframe_insert("scale", frame=f)
        X.set_linear(ob)

    # --- the tunnel
    z_end_tun = zB + 1.2
    rings = []
    zz = -0.9
    k = 0
    while zz > z_end_tun:
        rings.append(zz)
        k += 1
        zz -= 0.95 + 0.1 * k
    nring = len(rings)

    def radius_at(zz):
        u = (0.0 - zz) / (0.0 - zB)
        return 0.95 + 0.55 * X._sstep(0.0, 0.25, u) + 1.1 * X._sstep(0.78, 1.0, u)

    # floating cards: moving frames from all three eras
    seq = []
    for era in ("tobey", "andrew", "tom"):
        seq += [(era, s) for s in ERAS[era] if os.path.isdir(X.plate_dir(ctx, s))]
    mats = {}
    for ri, zr in enumerate(rings):
        n = 7 if ri < nring - 2 else 9
        rad = radius_at(zr)
        a0 = R.uniform(0, 2 * math.pi)
        for ci in range(n):
            ang = a0 + 2 * math.pi * ci / n + R.uniform(-0.12, 0.12)
            em = era_mix(zr)
            pool = [s for s in seq if s[0] == ("tobey" if R.random() > em else R.choice(["andrew", "tom"]))] or seq
            era, sid = R.choice(pool)
            scl = R.uniform(0.33, 0.42) * (1.0 + 0.5 * X._sstep(0.7, 1.0, (0 - zr) / (0 - zB)))
            c = X.plane_obj(f"XA_eye_card_{ri}_{ci}", camlib.CARD_W * scl, camlib.CARD_H * scl, plate_c)
            rr = rad + R.uniform(-0.05, 0.15)
            pos = Vector((ax.x + rr * math.cos(ang), ax.y + rr * math.sin(ang), zr + R.uniform(-0.3, 0.3)))
            inward = Vector((-math.cos(ang), -math.sin(ang), 0.0))
            tilt = math.radians(R.uniform(38, 58))
            nrm = (inward * math.cos(tilt) + Vector((0, 0, 1)) * math.sin(tilt)).normalized()
            up = Vector((math.cos(ang), math.sin(ang), 0.0)).cross(nrm).normalized()  # picture up along the wall
            q = _quat_with_up(nrm, up)
            c.matrix_world = Matrix.Translation(O + pos) @ q.to_matrix().to_4x4()
            mk = (sid, round(em, 1))
            if mk not in mats:
                mats[mk] = _tunnel_card_mat(ctx, sid, X.lerp3(gold, cyan, em), w0, R.randint(0, 40), len(mats),
                                            fog=X.lerp3(pal_a["fog"], pal_b["fog"], em))
            c.data.materials.append(mats[mk])
    # swirl arcs (REFS a 110-124, c 436-444): partial glowing arcs at several radii between the card rings, each
    # spinning at its own rate, gold -> cyan with depth; a last full cyan ring frames Andrew's lens
    zs_arc = [zr - 0.45 for zr in rings] + [rings[0] + 0.5]
    for ri, zl in enumerate(zs_arc):
        em = era_mix(zl)
        col = _sat(X.lerp3(gold, cyan, em), 1.5)
        fogc = X.lerp3(pal_a["fog"], pal_b["fog"], em)
        for j in range(3):
            rad = radius_at(zl) * R.uniform(0.55, 0.95)
            span = math.radians(R.uniform(110, 250))
            npt = 24
            pts = [Vector((rad * math.cos(span * i / (npt - 1)), rad * math.sin(span * i / (npt - 1)), 0.0))
                   for i in range(npt)]
            arc = X.curve_obj(f"XA_eye_arc_{ri}_{j}", pts, light_c, bevel=R.uniform(0.005, 0.011), res=4,
                              taper=[(0.0, 0.05), (0.25, 1.0), (0.75, 1.0), (1.0, 0.05)])
            arc.location = O + Vector((ax.x, ax.y, zl + R.uniform(-0.25, 0.25)))
            arc.data.materials.append(X.mat_emit_fog(f"XA_eye_arc_m{ri}_{j}", col, R.uniform(9.0, 16.0), fogc,
                                                     k=6.0, near=1.0))
            arc.rotation_mode = "XYZ"
            spin = math.radians(R.uniform(6.0, 16.0)) * R.choice([-1, 1, 1])
            a0 = R.uniform(0, 2 * math.pi)
            for f in (w0 - 2, w1 + 2):
                arc.rotation_euler = (R.uniform(-0.06, 0.06) * 0, 0.0, a0 + spin * (f - w0))
                arc.keyframe_insert("rotation_euler", frame=f)
            X.set_linear(arc)
    lr = X.curve_obj("XA_eye_lring_end", [Vector((1.45 * math.cos(t), 1.45 * math.sin(t), 0.0))
                                          for t in [2 * math.pi * i / 32 for i in range(32)]],
                     light_c, bevel=0.006, res=6, closed=True)
    lr.location = O + Vector((ax.x, ax.y, zB + 0.8))
    lr.data.materials.append(X.mat_emit_fog("XA_eye_lring_end_m", _sat(cyan), 10.0, pal_b["fog"], k=6.0, near=1.0))
    # web strands: helices along the wall + polygonal web rings joining them
    nh = 6
    web_m = X.mat_emit_fog("XA_eye_web_m", (0.85, 0.92, 1.0), 1.6, (0.02, 0.03, 0.05), k=4.0, near=0.5)
    for h in range(nh):
        pts = []
        for i in range(48):
            zz = -0.3 + (z_end_tun + 0.3) * i / 47
            ang = 2 * math.pi * h / nh + zz * 0.55
            rad = radius_at(zz) - 0.2 + 0.06 * math.sin(i * 1.7 + h)
            pts.append(Vector((ax.x + rad * math.cos(ang), ax.y + rad * math.sin(ang), zz)))
        cv = X.curve_obj(f"XA_eye_web_{h}", [p + O for p in pts], light_c, bevel=0.0018, res=4)
        cv.data.materials.append(web_m)
    for wi, zr in enumerate(rings[1::2]):
        zw = zr - 0.2
        pts = []
        for h in range(nh):
            ang = 2 * math.pi * h / nh + zw * 0.55
            rad = radius_at(zw) - 0.2
            pts.append(Vector((ax.x + rad * math.cos(ang), ax.y + rad * math.sin(ang), zw)) + O)
        pts.append(pts[0])
        cv = X.curve_obj(f"XA_eye_webring_{wi}", pts, light_c, bevel=0.0015, res=1)
        cv.data.splines[0].order_u = 2
        cv.data.materials.append(web_m)
    # dust / sparkles (one mesh of tiny octahedra), coloured by depth
    _dust(f"XA_eye_dust", O, ax, 0.0, z_end_tun, radius_at, R, light_c, gold, cyan, era_mix)
    # nebula tube behind the cards so the void is never black
    neb = X.tube_obj("XA_eye_nebula", lambda zz, ang: (3.4 * math.cos(ang), 3.4 * math.sin(ang)),
                     [0.4 - (0.4 - (zB - 2.0)) * i / 30 for i in range(31)], plate_c, n=48)
    neb.location = O + Vector((ax.x, ax.y, 0.0))
    neb.data.materials.append(_nebula_mat("XA_eye_neb_m", gold, cyan, pal_a["fog"], pal_b["fog"]))
    cap = X.annulus_obj("XA_eye_nebula_cap", 0.0, 3.5, plate_c, n=48, nr=4)  # closes the tunnel behind the S09 copy
    cap.location = O + Vector((ax.x, ax.y, zB - 2.0))
    cap.data.materials.append(neb.data.materials[0])
    # Andrew's lens at the end of the tunnel (comp time, already moving), with a thin cyan frame
    cardB = ctx.make_card(b, "XA_eye_S09", matrix=P["MB"])
    frame = _frame_obj("XA_eye_S09_frame", light_c)
    frame.matrix_world = P["MB"] @ Matrix.Translation(Vector((0, 0, 0.004)))
    frame.data.materials.append(X.mat_emit("XA_eye_frame_m", cyan, 3.0))
    ctx.env(O, ctx.act_at(cut))
    for ob in (cardA, rim, funnel):
        X.key_hide(ob, [(w0, cut + 1)])

    # --- camera: home S08 -> private set (w0 + 0.5) -> home S09 (handoff)
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
        """Rack defocus on Andrew's arrival (REFS): focus pulled short of the S09 card, racking onto it by cut + 9."""
        if t > t_out:
            d = (P["z"](t) - zB) / P["kB"]
        else:
            d = max(0.05, P["z"](t) - zB)
        u = X._sstep(cut + 1, cut + 9, t)
        k = X.bump(t, cut - 2, cut + 3) if t < cut else 1.0
        rel = X.lerp(0.25, 1.0, u)
        fstop = X.lerp(1.1, 64.0, max(u, 1 - k)) if t >= cut - 2 else 64.0
        return d * rel, fstop

    X.key_path(ctx, w0, w1, fn, teleports=(t_in, t_out), dof_fn=dof)
    ctx.log("eye_tunnel rates (f: zoom %/f on S08 | on S09, roll deg/f): " + "  ".join(
        f"{f}: {100 * P['spd'].vel(f) / z(f) if z(f) > 0.15 else float('nan'):.1f}|"
        f"{100 * P['spd'].vel(f) / (z(f) - zB):.1f},{P['roll'](f + 0.5) - P['roll'](f - 0.5):.1f}" for f in range(w0, w1 + 1)))
    ctx.log(f"eye_tunnel: tunnel {-zB:.1f} m, {nring} card rings, roll {P['roll'](w1):.0f} deg, "
            f"v peak {P['spd'].vel(cut):.2f} m/f, through the card at f{_cross(P):.1f}")


def _cross(P):
    t = P["w0"]
    while P["z"](t) > 0 and t < P["w1"]:
        t += 0.05
    return t


def _norm(m):
    loc, rot, _ = m.decompose()
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()


def _sat(c, k=1.35):
    """More saturated version of an RGB colour (keeps the max channel)."""
    mx = max(c)
    return tuple(max(0.0, mx - (mx - x) * k) for x in c)


def _quat_with_up(nrm, up):
    zc = nrm.normalized()
    xc = up.cross(zc).normalized()
    yc = zc.cross(xc)
    return Matrix((xc, yc, zc)).transposed().to_quaternion()


def _frame_obj(name, coll, w=1.92, h=1.08, t=0.012):
    vs = [(-w / 2 - t, -h / 2 - t, 0), (w / 2 + t, -h / 2 - t, 0), (w / 2 + t, h / 2 + t, 0), (-w / 2 - t, h / 2 + t, 0),
          (-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)]
    fs = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return X.mesh_obj(name, vs, fs, coll)


def _dust(name, O, ax, z_from, z_to, radius_at, R, coll, c0, c1, era_mix, n=520):
    vs, fs, cols = [], [], []
    for i in range(n):
        zz = R.uniform(z_to, z_from)
        ang = R.uniform(0, 2 * math.pi)
        rad = radius_at(zz) * R.uniform(0.35, 0.95)
        c = Vector((ax.x + rad * math.cos(ang), ax.y + rad * math.sin(ang), zz))
        s = R.uniform(0.002, 0.006)
        b = len(vs)
        vs += [c + Vector(d) * s for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]
        fs += [(b + 0, b + 2, b + 4), (b + 2, b + 1, b + 4), (b + 1, b + 3, b + 4), (b + 3, b + 0, b + 4),
               (b + 2, b + 0, b + 5), (b + 1, b + 2, b + 5), (b + 3, b + 1, b + 5), (b + 0, b + 3, b + 5)]
        cols += [era_mix(zz)] * 6
    ob = X.mesh_obj(name, [O + v for v in vs], fs, coll)
    at = ob.data.attributes.new("era", "FLOAT", "POINT")
    at.data.foreach_set("value", cols)
    m, nt, out = X._nodes(name + "_m")
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "era"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (*c0, 1)
    mix.inputs[7].default_value = (*c1, 1)
    nt.links.new(attr.outputs["Fac"], mix.inputs[0])
    em = X.node(nt, "ShaderNodeEmission", Strength=3.0)
    nt.links.new(mix.outputs[2], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    ob.data.materials.append(m)
    return ob


# ------------------------------------------------------------------------------------------------- materials
def _rim_mat(name, gold, cyan):
    m, nt, out = X._nodes(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    # radial profile: hot core at the inner edge, soft outward falloff
    v = sep.outputs[1]
    prof = X.math_node(nt, "POWER", X.math_node(nt, "SUBTRACT", 1.0, v), 2.2)
    no = X.node(nt, "ShaderNodeTexNoise", Scale=9.0, Detail=6.0, Roughness=0.65)
    nt.links.new(tc.outputs["Object"], no.inputs["Vector"])
    fl = X.math_node(nt, "MULTIPLY", X.math_node(nt, "ADD", no.outputs["Fac"], 0.15), 1.6)
    stren = X.math_node(nt, "MULTIPLY", X.math_node(nt, "MULTIPLY", prof, fl), 4.5)
    col = nt.nodes.new("ShaderNodeMix")
    col.data_type = "RGBA"
    col.inputs[6].default_value = (1.0, 0.78, 0.38, 1)
    col.inputs[7].default_value = (gold[0], gold[1] * 0.6, gold[2] * 0.3, 1)
    nt.links.new(v, col.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col.outputs[2], em.inputs["Color"])
    nt.links.new(stren, em.inputs["Strength"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(em.outputs[0], add.inputs[0])
    nt.links.new(tr.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return m


def _funnel_mat(ctx, sid, iris, r_keys, gold):
    """The iris stretched into the tunnel: each wall point samples the plate just outside the hole edge at its angle,
    twisting with depth, darkening into gold light further in."""
    m, nt, out = X._nodes("XA_eye_funnel_m")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    u, v = sep.outputs[0], sep.outputs[1]
    ang = X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", u, 2 * math.pi), X.math_node(nt, "MULTIPLY", v, 1.4))
    rad = X.key_value(nt, "hole_radius", r_keys)
    rr = X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", rad, 1.04), 3.0)
    px = X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", X.math_node(nt, "COSINE", ang), rr), float(iris[0]))
    py = X.math_node(nt, "SUBTRACT", float(iris[1]), X.math_node(nt, "MULTIPLY", X.math_node(nt, "SINE", ang), rr))
    uu = X.math_node(nt, "DIVIDE", px, 1920.0)
    vv = X.math_node(nt, "SUBTRACT", 1.0, X.math_node(nt, "DIVIDE", py, 1080.0))
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(uu, comb.inputs[0])
    nt.links.new(vv, comb.inputs[1])
    img = X.plate_node(nt, ctx, sid)
    nt.links.new(comb.outputs[0], img.inputs["Vector"])
    fade = X.math_node(nt, "POWER", X.math_node(nt, "SUBTRACT", 1.0, v, clamp=True), 1.6)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(X.math_node(nt, "SUBTRACT", 1.0, fade), mix.inputs[0])
    nt.links.new(img.outputs["Color"], mix.inputs[6])
    mix.inputs[7].default_value = (*[c * 0.6 for c in gold], 1)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(mix.outputs[2], em.inputs["Color"])
    nt.links.new(X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", fade, 1.3), 0.25), em.inputs["Strength"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def _tunnel_card_mat(ctx, sid, tint, w0, shift, idx, fog=(0.02, 0.03, 0.05)):
    """A decor card: the shot's moving frames (looped over its non-held frames), tinted, with a glowing edge."""
    m, nt, out = X._nodes(f"XA_eye_tcard_{sid}_{idx}")
    mv = X.plate_moving_frames(ctx, sid)
    lo, hi = mv[0], mv[-1] + 1
    img = X.plate_node(nt, ctx, sid, f_at=lo + shift % max(1, hi - lo), frame0=w0, loop=(lo, hi))
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    du = X.math_node(nt, "MINIMUM", sep.outputs[0], X.math_node(nt, "SUBTRACT", 1.0, sep.outputs[0]))
    dv = X.math_node(nt, "MINIMUM", sep.outputs[1], X.math_node(nt, "SUBTRACT", 1.0, sep.outputs[1]))
    edge = X.math_node(nt, "MINIMUM", X.math_node(nt, "MULTIPLY", du, 1.78), dv)
    border = X.math_node(nt, "LESS_THAN", edge, 0.018)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 0.35
    nt.links.new(img.outputs["Color"], mix.inputs[6])
    mix.inputs[7].default_value = (*tint, 1)
    mix2 = nt.nodes.new("ShaderNodeMix")
    mix2.data_type = "RGBA"
    nt.links.new(border, mix2.inputs[0])
    nt.links.new(mix.outputs[2], mix2.inputs[6])
    mix2.inputs[7].default_value = (*tint, 1)
    col, keep = X.depth_fog(nt, mix2.outputs[2], fog, k=5.0, near=1.0)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    nt.links.new(X.math_node(nt, "ADD", 1.1, X.math_node(nt, "MULTIPLY", X.math_node(nt, "MULTIPLY", border, keep), 4.0)),
                 em.inputs["Strength"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def _nebula_mat(name, c0, c1, f0, f1):
    """Behind the cards: dark act fog with coloured filaments drifting along the tunnel (gold -> cyan with depth)."""
    m, nt, out = X._nodes(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.0, 0.35)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    no = X.node(nt, "ShaderNodeTexNoise", Scale=1.6, Detail=10.0, Roughness=0.62, Distortion=1.4)
    nt.links.new(mp.outputs[0], no.inputs["Vector"])
    fil = X.math_node(nt, "POWER", X.math_node(nt, "SUBTRACT", 1.0, X.math_node(
        nt, "ABSOLUTE", X.math_node(nt, "SUBTRACT", X.math_node(nt, "MULTIPLY", no.outputs["Fac"], 2.0), 1.0))), 16.0)
    col = nt.nodes.new("ShaderNodeMix")
    col.data_type = "RGBA"
    nt.links.new(sep.outputs[1], col.inputs[0])
    col.inputs[6].default_value = (*c0, 1)
    col.inputs[7].default_value = (*c1, 1)
    fog = nt.nodes.new("ShaderNodeMix")
    fog.data_type = "RGBA"
    nt.links.new(sep.outputs[1], fog.inputs[0])
    fog.inputs[6].default_value = (*f0, 1)
    fog.inputs[7].default_value = (*f1, 1)
    e1 = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col.outputs[2], e1.inputs["Color"])
    nt.links.new(X.math_node(nt, "MULTIPLY", fil, 0.55), e1.inputs["Strength"])
    e2 = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(fog.outputs[2], e2.inputs["Color"])
    e2.inputs["Strength"].default_value = 0.45
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(e1.outputs[0], add.inputs[0])
    nt.links.new(e2.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return m
