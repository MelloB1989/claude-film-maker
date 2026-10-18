"""eye_tunnel (C08, Tobey -> Andrew, window 236-264, cut 252): a nested null-camera eye zoom (EDIT.md v3.1).

Both clips stay STILL in 3D; only the camera rig moves. Andrew's lens (a copy of the S09 card) sits physically behind
Tobey's left eye (a copy of the S08 card), sized so that, seen from the camera, it shows small inside the eye opening
and fills the frame as the camera passes the eye. Inside the exact eye opening (regions/S08/eye/ masks when present, an
almond ellipse around the iris track until then, feathered 3-12 screen px) Tobey's opacity drops to 0 over ~7 f from
~241, so B is already playing inside the eye. The camera dollies along the eye axis with an eased speed: fast on
Tobey's face, easing into the eye, so Tobey's eye opening blows up past the frame while Andrew's lens only grows
gently. It crosses Tobey's plane on the cut and lands on S09's hold framing. Depth of field stays focused on S09, so
Tobey's face goes out of focus as the camera nears it (refs c 164-179, a 56-71).

Rig (ctx.key_rig): dolly (the speed profile along the axis, keyed every half frame through the core's path) -> orbit
(small eased pan/tilt keys) -> roll (one eased drift) as sparse explicit Bezier keys on RIG_ORBIT / RIG_ROLL, offset
from each other and from the dolly so the motion overlaps and never stops (both sides keyed at the teleports).

The geometry follows from the motion: the B zoom rate rho(t) = speed / distance-to-B is keyed; its integral up to the
crossing fixes S09's depth behind the eye (D), the framing at the crossing (s_cross) fixes S09's card scale, and the
integral after the crossing gives S09's landing framing.
Teleports: home S08 -> private set at w0 + 0.5 (identical copy, the eye still opaque), private set -> home S09 at
t_cross + 2.5 (the S09 copy fills the frame, identical to the home card).
"""
import bisect
import json
import math
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.append(_here)
from mathutils import Euler, Matrix, Quaternion, Vector  # noqa: E402

import _xfxa as X  # noqa: E402
import camlib  # noqa: E402,F401  (keeps the core camera lib loaded first)

FILL = X.FILL
# S08 left eye opening (between the lids) relative to the iris track, plate px: centre offset, semi-axes, tilt (deg,
# + = clockwise on screen). Measured on f244; the stand-in until regions/S08/eye/ lands.
EYE = dict(off=(12.0, 2.0), axes=(66.0, 25.0), tilt=3.0)
_PLAN = {}


def _plan(T, ctx):
    key = (T["id"], T["w0"], T["w1"], T["f"])
    if key in _PLAN:
        return _PLAN[key]
    w0, w1, cut = T["w0"], T["w1"], T["f"]
    a, b = T["a"]["id"], T["b"]["id"]
    p = T.get("p", {})
    P = dict(w0=w0, w1=w1, cut=cut, a=a, b=b)
    s0, ds0 = float(p.get("s0", 1.15)), float(p.get("ds0", 0.035))  # matches C08's zt push landing on the eye
    z0 = FILL / s0
    t_c = float(p.get("t_cross", cut - 0.2))  # the camera passes Tobey's plane just before the cut frame
    s_cross = float(p.get("s_cross", 1.05))  # S09's framing as the camera passes the eye
    r_e = X.exit_rate(ctx, T, 0.022)
    eye_off = p.get("eye_off", EYE["off"])

    reg = _region_json(ctx, a, "eye")

    def eye(t):
        """Centre of the eye opening (plate px): the region masks' centroid when they exist, else iris track + offset."""
        if reg:
            return _interp_frames(reg, t)
        ix, iy = X.track(ctx, a, t, (901, 390))
        return ix + eye_off[0], iy + eye_off[1]

    P["eye"] = eye

    # B zoom rate rho = speed / distance to B: a gentle push on Andrew's lens, peaking ~0.12 / f while Tobey's face
    # grows past the frame, easing to ~0.045 / f as the camera passes the eye, then into S09's hold drift
    def rho_keys(D):
        r0 = z0 * ds0 / (z0 + D)
        return [(w0, r0), (w0 + 3, 0.055), (w0 + 6, 0.10), (w0 + 10, 0.12), (w0 + 13, 0.085), (t_c, 0.045),
                (t_c + 2.0, max(r_e, 0.032)), (w1, r_e)], r0

    D = 0.6
    for _ in range(8):  # D <-> the start rate (it depends on D): converges in a few rounds
        ks, r0 = rho_keys(D)
        rho = X.Speed(ks, m0=r0 * 0.15)
        D = z0 / (math.exp(rho.x(t_c)) - 1.0)
    P["rho"], P["D"] = rho, D
    kB = s_cross * D / FILL
    s_end = s_cross * math.exp(rho.x(w1) - rho.x(t_c))
    P["kB"], P["s_end"], P["t_c"] = kB, s_end, t_c
    dB = lambda t: D * math.exp(rho.x(t_c) - rho.x(t))  # noqa: E731  camera distance to the S09 plane
    z = lambda t: dB(t) - D  # noqa: E731  camera distance in front of the S08 plane (< 0 past it)
    P["dB"], P["z"] = dB, z
    # roll: one eased clockwise drift, keyed later than the dolly (overlap); S09 is turned so it lands near level
    P["roll"] = lambda t: 7.0 * X._sstep(w0 + 3, t_c + 3, t)  # noqa: E731
    r_end = 0.4
    theta = P["roll"](w1) - r_end
    # orbit: small eased pan/tilt keys (deg) between the dolly keys, back to 0 before the eye so the axis stays true
    yaw_k = [(w0, 0.0), (w0 + 5, 0.45), (w0 + 10, -0.25), (t_c - 1.5, 0.0)]
    pit_k = [(w0, 0.0), (w0 + 3, -0.25), (w0 + 8, 0.35), (t_c - 2.5, 0.0)]
    P["yaw"] = lambda t: _eased(yaw_k, t)  # noqa: E731
    P["pitch"] = lambda t: _eased(pit_k, t)  # noqa: E731
    P["orbit_t"] = sorted({k[0] for k in yaw_k + pit_k})
    P["roll_t"] = [w0 + 3, t_c + 3]
    O = ctx.new_set("eye_tunnel")
    P["O"] = O
    P["MA"] = Matrix.Translation(O)
    ax = X.px2local(*eye(t_c))  # the eye axis: where the camera passes Tobey's plane
    MB_local = (Matrix.Translation(Vector((ax.x, ax.y, -D)))
                @ Quaternion((0, 0, 1), math.radians(theta)).to_matrix().to_4x4() @ Matrix.Scale(kB, 4))
    P["MB"] = Matrix.Translation(O) @ MB_local
    P["theta"] = theta
    P["t_in"], P["t_out"] = w0 + 0.5, t_c + 2.5
    PB = tuple(p.get("exit_lens", (1036.0, 546.0)))

    def softclamp(x, L):
        return 0.0 if L <= 1e-6 else L * math.tanh(x / L)

    def lateral(t):
        """Camera position across the axis (A-local metres): on the eye centre up to the crossing, then drifting to
        S09's lens framing (soft-clamped so the frame never leaves the S09 card); continuous at the crossing."""
        if t <= t_c:
            e = X.px2local(*eye(t))
            return Vector((e.x, e.y))
        sB = FILL * kB / dB(t)
        lens = X.track(ctx, b, t, PB)
        wgt = X._sstep(t_c, w1 + 1.0, t)
        Lx = max(0.0, 960 - 960 / sB - 12)
        Ly = max(0.0, 540 - 540 / sB - 6)
        q = MB_local @ X.px2local(960 + softclamp((lens[0] - 960) * wgt, Lx), 540 + softclamp((lens[1] - 540) * wgt, Ly))
        return Vector((q.x, q.y))

    def m_set(t):
        """World camera matrix in the private set: dolly -> orbit -> roll."""
        lat = lateral(t)
        loc = O + Vector((lat.x, lat.y, z(t)))
        orbit = Euler((math.radians(P["pitch"](t)), math.radians(P["yaw"](t)), 0.0), "XYZ").to_quaternion()
        q = orbit @ Quaternion((0, 0, 1), math.radians(P["roll"](t)))
        return Matrix.Translation(loc) @ q.to_matrix().to_4x4()

    P["m_set"] = m_set

    def a_state(t):
        s, cx, cy, r, _ = X.state_from_cam(P["MA"], m_set(t), r_hint=P["roll"](t))
        return (s, cx, cy, r)

    def b_state(t):
        s, cx, cy, r, _ = X.state_from_cam(P["MB"], m_set(t), r_hint=P["roll"](t) - theta)
        return (s, cx, cy, r)

    P["a_state"], P["b_state"] = a_state, b_state
    _PLAN[key] = P
    return P


def _eased(keys, t):
    """AE 'easy ease' through [(t, v), ...]: smoothstep between neighbouring keys, held outside."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            return X.lerp(v0, v1, X._sstep(t0, t1, t))
    return keys[-1][1]


def bounds(T, ctx):
    P = _plan(T, ctx)
    return {"A": X.mix_state(P["a_state"], P["w0"]), "B": X.mix_state_back(P["b_state"], P["w1"])}


# ------------------------------------------------------------------------------------------------- build
def build(T, ctx):
    P = _plan(T, ctx)
    w0, w1, t_c = P["w0"], P["w1"], P["t_c"]
    a, b = P["a"], P["b"]
    z, dB, kB = P["z"], P["dB"], P["kB"]

    # Tobey (A): a still copy of the home card, transparent inside the eye opening once the reveal starts
    cardA = X.copy_card(ctx, a, "XA_eye_S08", P["MA"], frames=(w0, int(math.ceil(t_c)) + 1))
    ts = [w0 - 1 + 0.5 * i for i in range(2 * (w1 - w0 + 2) + 1)]
    reveal = [(t, X._sstep(w0 + 4.5, w0 + 11.0, t)) for t in ts]  # B inside the eye from ~241-242
    feather = []
    for t in ts:  # 3 .. 12 screen px, growing with the opening's size on screen, in card px
        sA = FILL / max(z(t), 1e-3)
        feather.append((t, max(0.25, X.lerp(3.0, 12.0, X._sstep(1.5, 12.0, sA)) / sA)))
    centre = [(t, P["eye"](t)) for t in ts]
    mask = _region_seq(ctx, a, "eye")
    _eye_region(cardA, centre, reveal, feather, mask)
    # Andrew (B): a still copy of S09 behind the eye, already playing
    X.copy_card(ctx, b, "XA_eye_S09", P["MB"], frames=(w0, w1 + 1))

    # --- camera: home S08 -> private set (t_in) -> home S09 (t_out)
    homeA = ctx.card(a).matrix_world.copy()
    homeB = ctx.card(b).matrix_world.copy()
    t_in, t_out = P["t_in"], P["t_out"]
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
        """Focus on S09 the whole way (Tobey defocuses as the camera nears him); the aperture opens as the eye
        reveals and closes again as S09 settles."""
        d = dB(t) if t <= t_out else dB(t) / kB
        n = X.lerp(64.0, float(T.get("p", {}).get("fstop", 2.8)), X._sstep(w0 + 3.0, w0 + 9.0, t))
        return d, X.lerp(n, 64.0, X._sstep(t_c + 1.0, w1, t))

    X.key_path(ctx, w0, w1, fn, teleports=(t_in, t_out), dof_fn=dof)
    n_rig = _key_rig(ctx, P, fn, (t_in, t_out))
    ctx.log("eye_tunnel nested zoom (f: A %/f | B %/f, sB): " + "  ".join(
        f"{f}: {100 * _rate(z, f) if z(f) > 0.01 else float('nan'):.0f}|{100 * _rate(dB, f):.1f},{FILL * kB / dB(f):.2f}"
        for f in range(w0, w1 + 1)))
    ctx.log(f"eye_tunnel: S09 {P['D']:.2f} m behind the eye at k {kB:.3f}, crossing f{t_c:.1f} at sB "
            f"{FILL * kB / P['D']:.2f}, lands sB {P['s_end']:.2f}, region {'masks' if mask else 'ellipse stand-in'}, "
            f"rig keys {n_rig or 'none (no ctx.key_rig: composed path)'}")


def _decompose(rot, prev=None):
    """World rotation -> (RIG_ORBIT swing, RIG_ROLL angle deg), rot = swing @ Rz(angle): the core's split."""
    q = rot.normalized()
    ang = 2.0 * math.atan2(q.z, q.w) if math.hypot(q.w, q.z) > 1e-9 else 0.0
    if prev is not None:
        ang += 2 * math.pi * round((math.radians(prev) - ang) / (2 * math.pi))
    return (q @ Quaternion((0, 0, 1), ang).inverted()).normalized(), math.degrees(ang)


def _key_rig(ctx, P, fn, teleports, h=0.05, eps=0.02):
    """Orbit and roll as explicit eased keys: at their own key times (slope 0 there), at the other channel's keys, on
    both sides of each teleport and before w1. Values and slopes come from the composed camera fn (one-sided at a
    teleport), so the Bezier reproduces the eased curves. -> number of keys (0 without ctx.key_rig)."""
    if not hasattr(ctx, "key_rig"):
        return 0
    w0, w1 = P["w0"], P["w1"]
    sides = [th + d for th in teleports for d in (-eps, eps)]
    base = [w0] + sides + [w1 - 0.5]

    def split(t, prev):
        return _decompose(_norm(fn(t)).to_quaternion(), prev)

    def slope_h(t):
        lo = max([w0] + [th for th in teleports if th <= t])
        hi = min([w1] + [th for th in teleports if th > t])
        return h if t + h < hi else -h if t - h >= lo else None

    n, prev, qprev = 0, 0.0, None
    times = sorted({round(t, 4) for t in base + P["orbit_t"] + P["roll_t"] if w0 <= t < w1})
    for t in times:
        q, r = split(t, prev)
        if qprev is not None and qprev.dot(q) < 0:
            q = -q
        dt = slope_h(t)
        if dt is None:
            dq, dr = (0.0,) * 4, 0.0
        else:
            q2, r2 = split(t + dt, r)
            if q2.dot(q) < 0:
                q2 = -q2
            dq, dr = tuple((q2[i] - q[i]) / dt for i in range(4)), (r2 - r) / dt
        ctx.key_rig(t, "orbit", q, dq)
        ctx.key_rig(t, "roll", r, dr)
        prev, qprev = r, q
        n += 2
    return n


def _rate(fz, f, h=0.25):
    """Zoom rate d ln s / f of a distance function (s ~ 1 / distance)."""
    return (math.log(fz(f - h)) - math.log(fz(f + h))) / (2 * h)


def _norm(m):
    loc, rot, _ = m.decompose()
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()


def _region_json(ctx, sid, kind):
    """{frame: (cx, cy)} from regions/<shot>/<kind>/region.json, or None."""
    pj = os.path.join(ctx.data, "regions", sid, kind, "region.json")
    if not os.path.exists(pj):
        return None
    fr = json.load(open(pj)).get("frames", {})
    out = {int(k): (float(v["cx"]), float(v["cy"])) for k, v in fr.items() if v and v.get("area", 1) > 0}
    return out or None


def _interp_frames(tab, t):
    ks = sorted(tab)
    if t <= ks[0]:
        return tab[ks[0]]
    if t >= ks[-1]:
        return tab[ks[-1]]
    i = bisect.bisect_right(ks, t) - 1
    k0, k1 = ks[i], ks[i + 1]
    u = (t - k0) / (k1 - k0)
    (x0, y0), (x1, y1) = tab[k0], tab[k1]
    return x0 + (x1 - x0) * u, y0 + (y1 - y0) * u


def _region_seq(ctx, sid, kind):
    """The region masks regions/<shot>/<kind>/f_NNNNN.png as a held comp-time sequence (None when not there yet)."""
    if not os.path.isdir(os.path.join(ctx.data, "regions", sid, kind)):
        return None
    try:
        return ctx._sequence(os.path.join("regions", sid), kind, "png")
    except Exception:  # noqa: BLE001 - harness / older ctx
        return None


def _eye_region(ob, centre, reveal, feather, mask=None):
    """Make the card transparent inside the eye opening: alpha *= 1 - region * reveal(t). region = the plate-frame mask
    softened by a 9-tap disc of the feather radius, or the almond ellipse around the tracked centre feathered inward
    by `feather` card px."""
    mat = ob.data.materials[0].copy()  # make_card shares materials between cards of a shot
    mat.name = "m_" + ob.name + "_eye"
    ob.data.materials[0] = mat
    nt = mat.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output)
    sh = out.inputs["Surface"].links[0].from_socket
    uv = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(nt.nodes.new("ShaderNodeTexCoord").outputs["UV"], uv.inputs[0])
    fe = X.key_value(nt, "EyeFE", feather)
    rv = X.key_value(nt, "EyeReveal", reveal)
    if mask is not None:
        import cards
        acc = None
        taps = [(0.0, 0.0)] + [(math.cos(2 * math.pi * i / 8), math.sin(2 * math.pi * i / 8)) for i in range(8)]
        for dx, dy in taps:
            cmb = nt.nodes.new("ShaderNodeCombineXYZ")
            nt.links.new(X.math_node(nt, "ADD", uv.outputs[0], X.math_node(nt, "MULTIPLY", fe, dx / 1920.0)), cmb.inputs[0])
            nt.links.new(X.math_node(nt, "ADD", uv.outputs[1], X.math_node(nt, "MULTIPLY", fe, dy / 1080.0)), cmb.inputs[1])
            tx = nt.nodes.new("ShaderNodeTexImage")
            tx.image = mask
            tx.extension = "EXTEND"
            tx.interpolation = "Linear"
            cards.setup_user(tx.image_user)
            nt.links.new(cmb.outputs[0], tx.inputs["Vector"])
            acc = tx.outputs["Color"] if acc is None else X.math_node(nt, "ADD", acc, tx.outputs["Color"])
        region = X.math_node(nt, "MULTIPLY", acc, 1.0 / len(taps))
    else:
        cx = X.key_value(nt, "EyeCX", [(t, c[0]) for t, c in centre])
        cy = X.key_value(nt, "EyeCY", [(t, c[1]) for t, c in centre])
        px = X.math_node(nt, "SUBTRACT", X.math_node(nt, "MULTIPLY", uv.outputs[0], 1920.0), cx)
        py = X.math_node(nt, "SUBTRACT", X.math_node(nt, "MULTIPLY", X.math_node(nt, "SUBTRACT", 1.0, uv.outputs[1]),
                                                     1080.0), cy)
        c, s = math.cos(math.radians(EYE["tilt"])), math.sin(math.radians(EYE["tilt"]))
        ex = X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", px, c), X.math_node(nt, "MULTIPLY", py, s))
        ey = X.math_node(nt, "SUBTRACT", X.math_node(nt, "MULTIPLY", py, c), X.math_node(nt, "MULTIPLY", px, s))
        A, B = EYE["axes"]
        # almond: the upper lid (ey < 0, px y down) arches a little higher than the lower one
        top = X.math_node(nt, "LESS_THAN", ey, 0.0)
        bsemi = X.math_node(nt, "ADD", B * 0.92, X.math_node(nt, "MULTIPLY", top, B * 0.16))
        nx = X.math_node(nt, "DIVIDE", ex, A)
        ny = X.math_node(nt, "DIVIDE", ey, bsemi)
        r = X.math_node(nt, "SQRT", X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", nx, nx),
                                                X.math_node(nt, "MULTIPLY", ny, ny)))
        # distance inside the edge ~ (1 - r) * minor semi-axis (px); region = smoothstep over the feather
        din = X.math_node(nt, "MULTIPLY", X.math_node(nt, "SUBTRACT", 1.0, r), B)
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.interpolation_type = "SMOOTHSTEP"
        nt.links.new(din, mr.inputs["Value"])
        mr.inputs["From Min"].default_value = 0.0
        nt.links.new(fe, mr.inputs["From Max"])
        region = mr.outputs["Result"]
    X.set_linear(nt)
    keep = X.math_node(nt, "SUBTRACT", 1.0, X.math_node(nt, "MULTIPLY", region, rv), clamp=True)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(keep, mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(sh, mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return mat

