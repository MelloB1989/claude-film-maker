"""eye_tunnel (C09, Tobey -> Andrew, window 236-264, cut 252): through Tobey's iris into the multiverse tunnel.

The camera is already pushing into Tobey's left iris (S08). The iris opens as a hole in the card with a burning gold rim,
the iris texture stretching back into a funnel; the camera flies through it into a tunnel whose walls are shingled
with cards playing moving frames from all three eras (faces of Tobey / Andrew / Tom passing close to the lens), web
helices and energy streams spiralling with the roll, spiral passes of light running over the cards, soft energy bands
on the walls, the light shifting from Tobey gold to Andrew cyan as it passes the cut. Andrew's lens (S09) waits at the
end of the tunnel as a soft round opening (no frame) that grows over the whole picture before the handoff; the camera
decelerates onto it and hands over to S09.

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
    # S09 lands still pushing in at its hold drift (the zoom sign carries into the hold and the next push zt; the
    # plate itself pulls out of the lens, which is what reads)
    s_end, ds_end = 1.15, X.exit_rate(ctx, T, 0.028)
    v_end = (FILL * kB / s_end) * ds_end
    u = lambda t: t - w0  # noqa: E731
    # dive through the iris (expo attack), a readable cruise through the multiverse, a 2-frame whoosh on the cut (REFS:
    # smear 1-3 f), then Andrew's lens: B lands at the cut speed and decays ~0.8 / f into S09's pull-out
    spd = X.Speed([
        (w0, z0 * ds0), (w0 + 4, 0.13), (w0 + 7, 0.32), (w0 + 8.5, 0.50), (w0 + 10.5, 0.36), (cut - 2.5, 0.34),
        (cut - 1, 0.62), (cut, 0.85), (cut + 1, 0.72), (cut + 2.5, 0.40), (cut + 4, 0.20), (cut + 5.5, 0.10),
        (cut + 7.5, 0.065), (w1, v_end)], m0=z0 * ds0 * 0.16)
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
        if zt <= 0.05 or p.get("tiled", True):  # home cards and copies are mirror-tiled: no need to keep off the edges
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
    cardA = X.copy_card(ctx, a, "XA_eye_S08", P["MA"], frames=(w0, cut + 1),
                        hole=dict(center=list(P["iris"]), radius=r_keys, feather=3.0))
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

    # --- the tunnel: a cylinder whose walls are shingled with moving cards, flaring like a bell at Andrew's end (so
    # the walls leave the frame before the handoff)
    z_end_tun = zB + 1.2

    def radius_at(zz):
        u = (0.0 - zz) / (0.0 - zB)
        return 0.95 + 0.55 * X._sstep(0.0, 0.25, u) + 1.1 * X._sstep(0.78, 1.0, u)

    seq = []
    for era in ("tobey", "andrew", "tom"):
        seq += [(era, s) for s in ERAS[era] if os.path.isdir(X.plate_dir(ctx, s))]
    look = dict(O=O, ax=ax, gold=_sat(gold, 1.3), cyan=_sat(cyan, 1.3), fog_a=pal_a["fog"], fog_b=pal_b["fog"],
                z_cut=z_cut, w0=w0, w1=w1)
    mats = {}

    def wall_mat(sid, shift):
        mk = (sid, shift)
        if mk not in mats:
            mats[mk] = _wall_card_mat(ctx, sid, look, f"XA_eye_wall_{sid}_{shift}", shift=shift)
        return mats[mk]

    # wall cards: rows of cards around the wall, staggered, each tilted a little toward the camera like scales, the
    # picture's top edge pointing into the distance on the lower half and toward the camera on the upper half (so
    # both read upright on screen); sizes grow in the bell
    ncard, zz, row = 0, -0.32, 0
    while zz > z_end_tun:
        uu = (0.0 - zz) / (0.0 - zB)
        rad = radius_at(zz) + 0.03
        scl = 0.27 * (1.0 + 0.7 * X._sstep(0.72, 1.0, uu))
        cw = camlib.CARD_W * scl
        n = max(9, int(2 * math.pi * rad / (cw * 1.1)))
        a0 = R.uniform(0, 2 * math.pi) + (math.pi / n if row % 2 else 0.0)
        em = era_mix(zz)
        for ci in range(n):
            ang = a0 + 2 * math.pi * ci / n + R.uniform(-0.04, 0.04)
            era_pick = "tobey" if R.random() > em else R.choice(["andrew", "tom"])
            pool = [s for s in seq if s[0] == era_pick] or seq
            _era, sid = R.choice(pool)
            k = scl * R.uniform(0.92, 1.06)
            c = X.plane_obj(f"XA_eye_wall_{row}_{ci}", camlib.CARD_W * k, camlib.CARD_H * k, plate_c)
            pos = Vector((ax.x + rad * math.cos(ang), ax.y + rad * math.sin(ang), zz + R.uniform(-0.03, 0.03)))
            inward = Vector((-math.cos(ang), -math.sin(ang), 0.0))
            tilt = math.radians(R.uniform(12, 24))
            nrm = (inward * math.cos(tilt) + Vector((0, 0, 1)) * math.sin(tilt)).normalized()
            zdir = Vector((0, 0, 1 if math.sin(ang) > 0 else -1))
            up = (zdir - nrm * zdir.dot(nrm)).normalized()
            q = Quaternion(nrm, math.radians(R.uniform(-4, 4))) @ _quat_with_up(nrm, up)
            c.matrix_world = Matrix.Translation(O + pos) @ q.to_matrix().to_4x4()
            c.data.materials.append(wall_mat(sid, R.choice((0, 9, 17))))
            ncard += 1
        zz -= camlib.CARD_H * scl * 1.12
        row += 1
    # faces passing close (Tobey -> Andrew -> Tom): bigger cards near the camera path, nearly facing the lens and
    # upright, readable for ~3-5 f as the camera cruises at them (1.5 m ahead of the camera at t_pass)
    heroes = [("S03", 245.6), ("S06", 246.5), ("S02", 247.4), ("S16", 248.3), ("S10", 249.2), ("S26", 250.1),
              ("S25", 251.0)]
    heroes = [(s, t + (w0 - 236)) for s, t in heroes if os.path.isdir(X.plate_dir(ctx, s))]
    for hi, (sid, tp) in enumerate(heroes):
        ang = 0.7 + 2.45 * hi
        rad = 0.84
        k = 0.5
        c = X.plane_obj(f"XA_eye_face_{sid}", camlib.CARD_W * k, camlib.CARD_H * k, plate_c)
        pos = Vector((ax.x + rad * math.cos(ang), ax.y + rad * math.sin(ang), z(tp) - 1.5))
        inward = Vector((-math.cos(ang), -math.sin(ang), 0.0))
        nrm = (Vector((0, 0, 1)) * math.cos(math.radians(22)) + inward * math.sin(math.radians(22))).normalized()
        upw = Vector((0, 1, 0))
        up = (upw - nrm * upw.dot(nrm)).normalized()
        c.matrix_world = Matrix.Translation(O + pos) @ _quat_with_up(nrm, up).to_matrix().to_4x4()
        mv = X.plate_moving_frames(ctx, sid)
        f_face = mv[len(mv) // 2]
        c.data.materials.append(_wall_card_mat(ctx, sid, look, f"XA_eye_face_{sid}_m", hero=True,
                                               f_at=f_face, frame0=int(round(tp - 2))))
        X.key_hide(c, [(w0, cut + 3)])
    # soft energy bands on the wall (no hard rings): short glowing sleeves with a gaussian falloff across, broken into
    # two slow-spinning lobes, gold -> cyan with depth
    zb, bi = -1.1, 0
    while zb > z_end_tun + 0.4:
        em = era_mix(zb)
        rb = radius_at(zb) - 0.06
        band = X.tube_obj(f"XA_eye_band_{bi}", lambda q, a, rb=rb: (rb * math.cos(a), rb * math.sin(a)),
                          [0.22 - 0.44 * i / 6 for i in range(7)], light_c, n=96)
        band.location = O + Vector((ax.x, ax.y, zb))
        band.data.materials.append(_band_mat(f"XA_eye_band_m{bi}", _sat(X.lerp3(gold, cyan, em), 1.4),
                                             X.lerp(2.6, 3.4, em)))
        band.rotation_mode = "XYZ"
        spin = math.radians(R.uniform(5.0, 11.0))
        a0 = R.uniform(0, 2 * math.pi)
        for f in (w0 - 2, w1 + 2):
            band.rotation_euler = (0.0, 0.0, a0 + spin * (f - w0))
            band.keyframe_insert("rotation_euler", frame=f)
        X.set_linear(band)
        zb -= 1.35 + 0.15 * bi
        bi += 1
    # web: helices along the wall turning the same way as the camera roll, web rings joining them; energy streams:
    # thicker helices nearer the axis carrying travelling pulses of act light
    nh = 10
    twist = -0.5  # rad / m, sign of the camera roll as the camera dives (-z)
    web_m = X.mat_emit_fog("XA_eye_web_m", (0.85, 0.92, 1.0), 1.8, (0.02, 0.03, 0.05), k=4.0, near=0.5)
    for h in range(nh):
        pts = []
        for i in range(64):
            zz = -0.3 + (z_end_tun + 0.3) * i / 63
            ang = 2 * math.pi * h / nh + zz * twist
            rad = radius_at(zz) - 0.12 + 0.05 * math.sin(i * 1.7 + h)
            pts.append(Vector((ax.x + rad * math.cos(ang), ax.y + rad * math.sin(ang), zz)))
        cv = X.curve_obj(f"XA_eye_web_{h}", [p + O for p in pts], light_c, bevel=0.0016, res=4)
        cv.data.materials.append(web_m)
    zw, wi = -0.8, 0
    while zw > z_end_tun:
        pts = []
        for h in range(nh):
            ang = 2 * math.pi * h / nh + zw * twist
            rad = radius_at(zw) - 0.12
            pts.append(Vector((ax.x + rad * math.cos(ang), ax.y + rad * math.sin(ang), zw)) + O)
        pts.append(pts[0])
        cv = X.curve_obj(f"XA_eye_webring_{wi}", pts, light_c, bevel=0.0013, res=1)
        cv.data.splines[0].order_u = 2
        cv.data.materials.append(web_m)
        zw -= 0.9
        wi += 1
    stream_m = _stream_mat("XA_eye_stream_m", look)
    for h in range(4):
        pts = []
        for i in range(96):
            zz = -0.2 + (z_end_tun + 0.2) * i / 95
            ang = 2 * math.pi * h / 4 + 0.4 + zz * twist * 1.6
            rad = radius_at(zz) * 0.8
            pts.append(Vector((ax.x + rad * math.cos(ang), ax.y + rad * math.sin(ang), zz)) + O)
        cv = X.curve_obj(f"XA_eye_stream_{h}", pts, light_c, bevel=0.006, res=4)
        cv.data.materials.append(stream_m)
    # dust / sparkles (one mesh of tiny octahedra), coloured by depth
    _dust("XA_eye_dust", O, ax, 0.0, z_end_tun, radius_at, R, light_c, gold, cyan, era_mix)
    # nebula tube behind the cards so the gaps are never black
    neb = X.tube_obj("XA_eye_nebula", lambda zz, ang: (3.4 * math.cos(ang), 3.4 * math.sin(ang)),
                     [0.4 - (0.4 - (zB - 2.0)) * i / 30 for i in range(31)], plate_c, n=48)
    neb.location = O + Vector((ax.x, ax.y, 0.0))
    neb.data.materials.append(_nebula_mat("XA_eye_neb_m", gold, cyan, pal_a["fog"], pal_b["fog"]))
    cap = X.annulus_obj("XA_eye_nebula_cap", 0.0, 3.5, plate_c, n=48, nr=4)  # closes the tunnel behind the S09 copy
    cap.location = O + Vector((ax.x, ax.y, zB - 2.0))
    cap.data.materials.append(neb.data.materials[0])
    # Andrew's lens at the end of the tunnel (comp time, already moving): an opening, not a picture. The S09 copy is
    # mirror-tiled like its home card and only a soft round aperture around the lens is opaque; the aperture grows so
    # it covers the whole frame (feather included) a frame before the handoff, so the exit is seamless.
    cardB = X.copy_card(ctx, b, "XA_eye_S09", P["MB"], frames=(w0, w1 + 1), tile=3)
    ap_keys, fe_keys, rmax = [], [], 0.0
    for i in range(2 * (w1 + 1 - w0) + 1):
        t = w0 + 0.5 * i
        sB, cx, cy, _r = P["b_state"](t)
        off = math.hypot(cx - P["PB"][0], cy - P["PB"][1])
        cover = (1101.0 / sB + off) * 1.04
        q = X._sstep(cut - 1.0, cut + 5.0, t)
        rin = max(470.0, q * cover)
        rmax = max(rmax, rin)
        fe = 300.0 + 0.2 * rmax
        ap_keys.append((t, rmax))
        fe_keys.append((t, fe * (1.0 - X._sstep(cut + 4.0, cut + 5.5, t))))  # hard-full by the handoff
    _aperture(cardB, P["PB"], ap_keys, fe_keys)
    glow = X.annulus_obj("XA_eye_S09_glow", 0.55, 1.6, light_c, n=128, nr=6)
    glow.matrix_world = P["MB"] @ Matrix.Translation(Vector((*X.px2local(*P["PB"]).xy, 0.006)))
    glow.data.materials.append(_glow_mat("XA_eye_S09_glow_m", _sat(cyan, 1.3),
                                         [(t, 0.1 * (1.0 - X._sstep(cut - 1.0, cut + 2.5, t))) for t, _ in ap_keys]))
    for (t, rin), (_t, fe) in zip(ap_keys, fe_keys):
        sc = (rin + 0.6 * max(fe, 300.0)) / 1000.0
        glow.scale = (sc, sc, 1.0)
        glow.keyframe_insert("scale", frame=t)
    X.set_linear(glow)
    X.key_hide(glow, [(w0, cut + 4)])
    ctx.log(f"eye_tunnel: {ncard} wall cards, {len(heroes)} face cards, {bi} energy bands, S09 aperture "
            f"{ap_keys[0][1]:.0f} -> {ap_keys[-1][1]:.0f} px")
    # no act void inside: the tunnel is closed (nebula tube + cap); the void's haze and strands would sit in the tunnel
    for ob in (rim, funnel):
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
    ctx.log(f"eye_tunnel: tunnel {-zB:.1f} m, roll {P['roll'](w1):.0f} deg, "
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


def _mix_rgb(nt, fac, a, b, blend="MIX"):
    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    mx.blend_type = blend
    for i, v in ((0, fac), (6, a), (7, b)):
        if isinstance(v, (int, float)):
            mx.inputs[i].default_value = v
        elif isinstance(v, tuple):
            mx.inputs[i].default_value = (*v[:3], 1)
        else:
            nt.links.new(v, mx.inputs[i])
    return mx.outputs[2]


def _vec(nt, op, a, b):
    n = nt.nodes.new("ShaderNodeVectorMath")
    n.operation = op
    for i, v in enumerate((a, b)):
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = (v, v, v)
        elif isinstance(v, (tuple, Vector)):
            n.inputs[i].default_value = tuple(v)
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def _maprange(nt, val, a, b, smooth=True):
    n = nt.nodes.new("ShaderNodeMapRange")
    if smooth:
        n.interpolation_type = "SMOOTHSTEP"
    for name, v in (("Value", val), ("From Min", a), ("From Max", b)):
        if isinstance(v, (int, float)):
            n.inputs[name].default_value = v
        else:
            nt.links.new(v, n.inputs[name])
    return n.outputs["Result"]


def _tunnel_coords(nt, look):
    """(lx, ly, lz, era 0..1, time) sockets: shading point relative to the tunnel axis (lz = depth along the tunnel,
    0 at the S08 copy, negative inward), gold -> cyan era by depth, and the scene frame."""
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    c0 = look["O"] + Vector((look["ax"].x, look["ax"].y, 0.0))
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(_vec(nt, "SUBTRACT", geo.outputs["Position"], c0), sep.inputs[0])
    lz = sep.outputs[2]
    em = _maprange(nt, X.math_node(nt, "MULTIPLY", lz, -1.0), -(look["z_cut"] + 0.5), -(look["z_cut"] - 3.0))
    t = X.key_value(nt, "t", [(look["w0"] - 3, look["w0"] - 3.0), (look["w1"] + 3, look["w1"] + 3.0)])
    X.set_linear(nt)
    return sep.outputs[0], sep.outputs[1], lz, em, t


def _wave(nt, phase, power):
    """(0.5 + 0.5 sin(2 pi phase)) ** power: a sharp travelling pulse."""
    s = X.math_node(nt, "SINE", X.math_node(nt, "MULTIPLY", phase, 2 * math.pi))
    return X.math_node(nt, "POWER", X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", s, 0.5), 0.5), power)


def _fog_keep(nt, k, near):
    cd = nt.nodes.new("ShaderNodeCameraData")
    d = X.math_node(nt, "MAXIMUM", X.math_node(nt, "SUBTRACT", cd.outputs["View Distance"], near), 0.0)
    return X.math_node(nt, "EXPONENT", X.math_node(nt, "DIVIDE", d, -k))


def _wall_card_mat(ctx, sid, look, name, shift=0, hero=False, f_at=None, frame0=None):
    """A tunnel card: the shot's moving frames (looped over its non-held frames), lightly tinted gold -> cyan by depth,
    with a feathered edge (no frame), spiral streams of act light passing over it, fading into the act fog with
    distance. hero: a face card passing close to the lens (barely tinted, starts on image f_at at frame0)."""
    m, nt, out = X._nodes(name)
    mv = X.plate_moving_frames(ctx, sid)
    lo, hi = mv[0], mv[-1] + 1
    if hero:
        img = X.plate_node(nt, ctx, sid, f_at=f_at, frame0=frame0, loop=(lo, hi))
    else:
        img = X.plate_node(nt, ctx, sid, f_at=lo + shift % max(1, hi - lo), frame0=look["w0"], loop=(lo, hi))
    lx, ly, lz, em, t = _tunnel_coords(nt, look)
    tint = _mix_rgb(nt, em, look["gold"], look["cyan"])
    fogc = _mix_rgb(nt, em, look["fog_a"], look["fog_b"])
    pic = _mix_rgb(nt, 0.1 if hero else 0.4, img.outputs["Color"], tint, "MULTIPLY")
    # light passing over the walls: two spiral arms travelling down the tunnel + a broad band coming at the camera
    ang = X.math_node(nt, "DIVIDE", X.math_node(nt, "ARCTAN2", ly, lx), math.pi)  # -1..1, x2 arms
    arm = _wave(nt, X.math_node(nt, "SUBTRACT", X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", lz, 0.55), ang),
                                X.math_node(nt, "MULTIPLY", t, 0.2)), 14.0)
    band = _wave(nt, X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", lz, 0.3), X.math_node(nt, "MULTIPLY", t, 0.11)),
                 6.0)
    light = X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", arm, 2.2), X.math_node(nt, "MULTIPLY", band, 0.6))
    if hero:
        light = X.math_node(nt, "MULTIPLY", light, 0.35)
    # feathered edge + a faint glow just inside it
    uv = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(nt.nodes.new("ShaderNodeTexCoord").outputs["UV"], uv.inputs[0])
    du = X.math_node(nt, "MINIMUM", uv.outputs[0], X.math_node(nt, "SUBTRACT", 1.0, uv.outputs[0]))
    dv = X.math_node(nt, "MINIMUM", uv.outputs[1], X.math_node(nt, "SUBTRACT", 1.0, uv.outputs[1]))
    e = X.math_node(nt, "MINIMUM", X.math_node(nt, "MULTIPLY", du, 1.78), dv)
    alpha = _maprange(nt, e, 0.0, 0.05 if hero else 0.03)
    eglow = X.math_node(nt, "MULTIPLY", X.math_node(nt, "SUBTRACT", 1.0, _maprange(nt, e, 0.0, 0.08)),
                        0.0 if hero else 0.25)
    col = _vec(nt, "MULTIPLY", pic, X.math_node(nt, "ADD", 1.0, X.math_node(nt, "MULTIPLY", light, 0.6)))
    col = _vec(nt, "ADD", col, _vec(nt, "MULTIPLY", tint, X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", light, 0.45),
                                                                      eglow)))
    keep = _fog_keep(nt, 12.0 if hero else 9.0, 1.5)
    col = _mix_rgb(nt, keep, fogc, col)
    emn = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, emn.inputs["Color"])
    emn.inputs["Strength"].default_value = 1.35 if hero else 1.15
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(alpha, mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(emn.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


def _additive(nt, out, col, strength):
    emn = nt.nodes.new("ShaderNodeEmission")
    if isinstance(col, tuple):
        emn.inputs["Color"].default_value = (*col[:3], 1)
    else:
        nt.links.new(col, emn.inputs["Color"])
    nt.links.new(strength, emn.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(emn.outputs[0], add.inputs[0])
    nt.links.new(nt.nodes.new("ShaderNodeBsdfTransparent").outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])


def _gauss(nt, x, mu, sig):
    d = X.math_node(nt, "DIVIDE", X.math_node(nt, "SUBTRACT", x, mu), sig)
    return X.math_node(nt, "EXPONENT", X.math_node(nt, "MULTIPLY", X.math_node(nt, "MULTIPLY", d, d), -1.0))


def _band_mat(name, col, strength):
    """Soft energy band on the tunnel wall (tube UV: u around, v across): gaussian falloff across the band, two
    broad lobes around it, a noisy breakup, fading into the fog; additive."""
    m, nt, out = X._nodes(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    across = _gauss(nt, sep.outputs[1], 0.5, 0.2)
    lob = X.math_node(nt, "POWER", X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", X.math_node(
        nt, "COSINE", X.math_node(nt, "MULTIPLY", sep.outputs[0], 4 * math.pi)), 0.5), 0.5), 2.0)
    lob = X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", lob, 0.8), 0.2)
    no = X.node(nt, "ShaderNodeTexNoise", Scale=6.0, Detail=4.0, Roughness=0.6)
    nt.links.new(tc.outputs["Object"], no.inputs["Vector"])
    brk = X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", no.outputs["Fac"], 1.2), 0.1)
    k = X.math_node(nt, "MULTIPLY", X.math_node(nt, "MULTIPLY", across, lob), brk)
    k = X.math_node(nt, "MULTIPLY", X.math_node(nt, "MULTIPLY", k, _fog_keep(nt, 5.0, 1.0)), strength)
    _additive(nt, out, col, k)
    return m


def _stream_mat(name, look):
    """Energy stream along a helix: pulses of act light travelling toward the camera, gold -> cyan by depth."""
    m, nt, out = X._nodes(name)
    lx, ly, lz, em, t = _tunnel_coords(nt, look)
    tint = _mix_rgb(nt, em, look["gold"], look["cyan"])
    pulse = _wave(nt, X.math_node(nt, "SUBTRACT", X.math_node(nt, "MULTIPLY", lz, 0.9), X.math_node(nt, "MULTIPLY", t, 0.3)),
                  10.0)
    k = X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", pulse, 9.0), 0.5)
    _additive(nt, out, tint, X.math_node(nt, "MULTIPLY", k, _fog_keep(nt, 5.0, 0.8)))
    return m


def _glow_mat(name, col, strength_keys):
    """Soft halo around the S09 aperture (annulus UV v radial, 0.55 .. 1.6 x the aperture edge)."""
    m, nt, out = X._nodes(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    prof = _gauss(nt, sep.outputs[1], 0.35, 0.32)
    no = X.node(nt, "ShaderNodeTexNoise", Scale=3.0, Detail=3.0, Roughness=0.5)
    nt.links.new(tc.outputs["Object"], no.inputs["Vector"])
    k = X.math_node(nt, "MULTIPLY", prof, X.math_node(nt, "ADD", no.outputs["Fac"], 0.3))
    st = X.key_value(nt, "glow", strength_keys)
    X.set_linear(nt)
    _additive(nt, out, col, X.math_node(nt, "MULTIPLY", k, st))
    return m


def _aperture(ob, center, r_keys, fe_keys):
    """Make a card an opening: opaque inside a soft disc around `center` (card px), radius and feather keyed (px)."""
    mat = ob.data.materials[0].copy()  # make_card shares materials between cards of a shot
    mat.name = "m_" + ob.name + "_aperture"
    ob.data.materials[0] = mat
    nt = mat.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output)
    sh = out.inputs["Surface"].links[0].from_socket
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(nt.nodes.new("ShaderNodeTexCoord").outputs["UV"], sep.inputs[0])
    px = X.math_node(nt, "SUBTRACT", X.math_node(nt, "MULTIPLY", sep.outputs[0], 1920.0), float(center[0]))
    py = X.math_node(nt, "SUBTRACT", X.math_node(nt, "MULTIPLY", X.math_node(nt, "SUBTRACT", 1.0, sep.outputs[1]),
                                                 1080.0), float(center[1]))
    cmb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(px, cmb.inputs[0])
    nt.links.new(py, cmb.inputs[1])
    ln = nt.nodes.new("ShaderNodeVectorMath")
    ln.operation = "LENGTH"
    nt.links.new(cmb.outputs[0], ln.inputs[0])
    r = X.key_value(nt, "ApR", r_keys)
    fe = X.key_value(nt, "ApFE", [(f, max(1.0, v)) for f, v in fe_keys])
    X.set_linear(nt)
    k = X.math_node(nt, "SUBTRACT", 1.0, _maprange(nt, ln.outputs["Value"], r, X.math_node(nt, "ADD", r, fe)))
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(k, mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(sh, mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def _nebula_mat(name, c0, c1, f0, f1):
    """Behind the cards: dark act fog with coloured filaments drifting along the tunnel (gold -> cyan with depth)."""
    m, nt, out = X._nodes(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.0, 0.35)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    no = X.node(nt, "ShaderNodeTexNoise", Scale=0.6, Detail=3.0, Roughness=0.5)
    nt.links.new(mp.outputs[0], no.inputs["Vector"])
    # sparse soft clouds of act light over a near-black void (the cards and arcs carry the picture)
    fil = X.math_node(nt, "POWER", X.math_node(nt, "DIVIDE", X.math_node(
        nt, "MAXIMUM", X.math_node(nt, "SUBTRACT", no.outputs["Fac"], 0.56), 0.0), 0.2), 2.0)
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
    nt.links.new(X.math_node(nt, "MULTIPLY", fil, 0.35), e1.inputs["Strength"])
    e2 = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(fog.outputs[2], e2.inputs["Color"])
    e2.inputs["Strength"].default_value = 0.2
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(e1.outputs[0], add.inputs[0])
    nt.links.new(e2.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return m
