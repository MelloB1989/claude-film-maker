"""drone — a generic ultralight foldable camera quadcopter (mini class), arms unfolded, resting on its feet
as if just put down. No logos, names or text anywhere.

Body ~14.5 (X, nose to tail, gimbal included) x 9 x 6 cm; motor centres on a ~25 cm diagonal; two-blade
~15 cm props with twist and an airfoil, parked clear of each other; 3-axis gimbal camera at the nose (+X).
Modelled in cm, nose toward +X. Origin: bottom centre of the footprint (props included).

    blender -b --factory-startup -P films/host-studio/props/drone.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _drone_kit as K  # noqa: E402

# ---------------------------------------------------------------- layout (cm)
XT, XN = -7.0, 6.2              # tail and nose tips of the shell
CAP_T, CAP_N = -5.6, 4.9        # where the rounded end caps start
W_ = K.pchip([(-7, 3.1), (-5, 3.45), (-2, 3.7), (2, 3.75), (4, 3.6), (4.9, 3.42), (6.2, 3.3)])
ZT_ = K.pchip([(-7, 5.0), (-5.5, 5.55), (-3, 5.9), (0, 6.0), (3, 5.95), (4.9, 5.75), (6.2, 5.6)])
ZB_ = K.pchip([(-7, 1.7), (-5.5, 1.15), (2.2, 1.1), (3.6, 2.0), (4.4, 3.0), (4.9, 3.45), (6.2, 3.45)])
ZM_FRAC = 0.47                  # height of the top/bottom shell parting line
NT, NB = 2.7, 3.6               # superellipse exponents of the upper and lower shell
GD, GW = 0.045, 0.085           # panel-line depth and half width
RING_GROOVES = [(-6.3, False), (-1.8, True), (4.75, False)]    # (x, upper shell only): tail cap, battery, nose
SIDE_GROOVE = (-6.3, 4.75)

FRONT, REAR = (6.8, 10.6), (-7.2, 10.2)          # motor centres (x, |y|): diagonal ~25 cm
POD_TOP = {1: 5.62, -1: 4.65}                     # motor seat height, front / rear
BELL_H = 1.08
# parked props: blade direction (deg from +X) and spin (+1 = CCW seen from above), keyed (front/rear, side)
PROPS = {(1, 1): (60, 1), (1, -1): (-75, -1), (-1, 1): (120, -1), (-1, -1): (-110, 1)}

CHORD = K.pchip([(0.6, 0.8), (1.3, 1.3), (2.6, 1.8), (4.3, 1.62), (6.0, 1.2), (7.0, 0.9)])
THICK = K.pchip([(0.6, 0.2), (1.5, 0.12), (3.5, 0.075), (7.5, 0.06)])
PROP_R = 7.5


# ---------------------------------------------------------------- body shell
def section(x):
    """(half width, parting-line z, half height above, half height below) with the end caps applied."""
    w, zt, zb = W_(x), ZT_(x), ZB_(x)
    zm = zb + (zt - zb) * ZM_FRAC
    f = 1.0
    if x < CAP_T:
        u = min(1.0, (CAP_T - x) / (CAP_T - XT))
        f = (1 - u ** 2.3) ** (1 / 2.3)
    elif x > CAP_N:
        u = min(1.0, (x - CAP_N) / (XN - CAP_N))
        f = (1 - u ** 2.6) ** (1 / 2.6)
    return w * f, zm, (zt - zm) * f, (zm - zb) * f


def sec_point(x, t, sec):
    w, zm, ht, hb = sec
    c, s = math.cos(t), math.sin(t)
    n, h = (NT, ht) if s >= 0 else (NB, hb)
    return Vector((x, w * K.spow(c, 2 / n), zm + h * K.spow(s, 2 / n)))


def stations():
    xs = [CAP_T + (CAP_N - CAP_T) * k / 64 for k in range(65)]
    for k in range(1, 14):
        u = math.sin(k / 14 * math.pi / 2)
        xs.append(CAP_T - u * (CAP_T - XT))
        xs.append(CAP_N + u * (XN - CAP_N))
    gx = [xg + d for xg, _ in RING_GROOVES for d in (-GW, -0.04, 0.0, 0.04, GW)]
    xs = [x for x in xs if all(abs(x - g) > 0.03 for g in gx)] + gx
    return sorted(xs)


def columns():
    n = 64
    _w, _zm, ht, hb = section(0.0)
    ins = []
    for d in (-GW, -0.04, 0.0, 0.04, GW):
        if d == 0:
            t = 0.0
        elif d > 0:
            t = math.asin(min(1.0, (d / ht) ** (NT / 2)))
        else:
            t = -math.asin(min(1.0, (-d / hb) ** (NB / 2)))
        ins += [t % (2 * math.pi), (math.pi - t) % (2 * math.pi)]
    dt = 2 * math.pi / n
    base = [dt * k for k in range(n)]

    def dist(a, b):
        e = abs(a - b) % (2 * math.pi)
        return min(e, 2 * math.pi - e)
    keep = [t for t in base if all(dist(t, s) > 0.35 * dt for s in ins)]
    return sorted(set(keep + ins))


def groove_depth(p, x, sec):
    w, zm, _ht, _hb = sec

    def prof(dist):
        return GD * math.cos(math.pi * dist / (2 * GW)) ** 2 if dist < GW else 0.0
    d = 0.0
    for xg, top in RING_GROOVES:
        if top and p.z < zm - 0.06:
            continue
        d = max(d, prof(abs(x - xg)))
    if SIDE_GROOVE[0] - 1e-6 <= x <= SIDE_GROOVE[1] + 1e-6 and abs(p.y) > 0.8 * w:
        d = max(d, prof(abs(p.z - zm)))
    return d


def body_bmesh():
    xs, ts = stations(), columns()
    rings, depth = [], []
    for x in xs:
        sec = section(x)
        ring = [sec_point(x, t, sec) for t in ts]
        rings.append(ring)
        depth += [groove_depth(p, x, sec) for p in ring]
    bm = bmesh.new()
    vr = K.add_grid(bm, rings, Vector((XT, 0, section(XT)[1])), Vector((XN, 0, section(XN)[1])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    flat = [v for ring in vr for v in ring]
    nrm = [v.normal.copy() for v in flat]
    for v, n, d in zip(flat, nrm, depth):
        if d > 0:
            v.co -= n * d
    bm.normal_update()
    return bm


# ---------------------------------------------------------------- part builders
def rrect(w, h, r, segs=3):
    return S.rounded_rect(w, h, min(r, w / 2 - 1e-4, h / 2 - 1e-4), segs)


def ellipse(a, b, n=2.4, segs=16):
    return [(a * K.spow(math.cos(2 * math.pi * k / segs), 2 / n),
             b * K.spow(math.sin(2 * math.pi * k / segs), 2 / n)) for k in range(segs)]


def screw_head(bm, p, n, scale=1.0, slot=0):
    prof = [(0, 0.03), (0.055, 0.03), (0.07, 0.058), (0.14, 0.052), (0.165, 0.03), (0.165, -0.08), (0, -0.08)]
    prof = [(r * scale, z * scale) for r, z in prof]
    K.add_lathe(bm, prof, K.frame(p, n), segs=12, slot=slot)


def socket(bm_dark, bm_lens, p, n, r=0.7, up=(0, 0, 1)):
    """A dark sensor bezel set into the shell with a glossy black window."""
    m = K.frame(p, n, up)
    s = r / 0.7
    bez = K.fillet([(0, -0.45), (0.7, -0.45), (0.7, 0.04), (0.64, 0.09), (0.52, 0.085), (0.48, 0.03), (0, 0.03)],
                   [0, 0, 0.03, 0.03, 0.02, 0.02, 0], steps=2)
    K.add_lathe(bm_dark, [(a * s, b * s) for a, b in bez], m, segs=24)
    glass = K.fillet([(0, 0.125), (0.3, 0.112), (0.47, 0.07), (0.49, 0.03), (0.49, -0.05), (0, -0.05)],
                     [0, 0, 0.03, 0.01, 0, 0], steps=2)
    K.add_lathe(bm_lens, [(a * s, b * s) for a, b in glass], m, segs=24)


def add_blade(bm, hub, phi, spin, zc):
    R = Vector((math.cos(phi), math.sin(phi), 0.0))
    Z = Vector((0, 0, 1))
    T = Z.cross(R) * spin
    N, NA = 26, 8
    xcs = [0.5 * (1 - math.cos(math.pi * k / NA)) for k in range(NA + 1)]
    pts = [(xc, 1) for xc in reversed(xcs)] + [(xc, -1) for xc in xcs[1:]]
    cm_, pm_ = 0.04, 0.4
    rings = []
    rs = [0.6 + (PROP_R - 0.08 - 0.6) * math.sin(k / N * math.pi / 2) for k in range(N + 1)]
    for r in rs:
        c = CHORD(r)
        if r > 6.5:
            c *= math.sqrt(max(0.0, 1 - ((r - 6.5) / 1.0) ** 2))
        c = max(c, 0.12)
        beta = min(math.radians(20 + 4 * K.smoothstep(0.8, 1.6, r)), math.atan(7.6 / (2 * math.pi * r)))
        tr = THICK(r)
        cd = T * math.cos(beta) + Z * math.sin(beta)
        nd = Z * math.cos(beta) - T * math.sin(beta)
        sweep = -0.45 * max(0.0, (r - 2.0) / 5.5) ** 2
        base = Vector(hub) + R * r + T * sweep + Z * zc
        ring = []
        for xc, sg in pts:
            yt = 5 * tr * (0.2969 * math.sqrt(xc) - 0.126 * xc - 0.3516 * xc ** 2 + 0.2843 * xc ** 3
                           - 0.1036 * xc ** 4) * c + 0.008 * xc
            if xc < pm_:
                yc = cm_ / pm_ ** 2 * (2 * pm_ * xc - xc * xc)
            else:
                yc = cm_ / (1 - pm_) ** 2 * ((1 - 2 * pm_) + 2 * pm_ * xc - xc * xc)
            ring.append(tuple(base + cd * ((0.35 - xc) * c) + nd * (yc * c + sg * yt)))
        rings.append(ring)
    last = rings[-1]
    tip = sum((Vector(p) for p in last), Vector()) / len(last) + R * 0.08
    K.add_grid(bm, rings, "ngon", tip)


# ---------------------------------------------------------------- build
def build():
    M = K.materials()
    parts = []

    # ---- shell with side vents cut in (recess walls in M_DroneDark)
    bm = body_bmesh()
    body_bvh = BVHTree.FromBMesh(bm)
    cut = bmesh.new()
    vents = []
    for s in (1, -1):
        loc, nrm = K.hit(body_bvh, (0.9, s * 12, 2.45), (0, -s, 0))
        K.add_prism(cut, rrect(3.0, 0.85, 0.3, 4), loc - nrm * 0.2, loc + nrm * 2.0, up=(1, 0, 0), slot=1)
        vents.append((loc, nrm))
    body = K.mk("body", bm, [M["body"], M["dark"]], bevel=0.03, segs=2, angle=55, cut=cut)
    parts.append(body)

    dark = bmesh.new()       # lathes and small parts in M_DroneDark, no bevel needed
    darkb = bmesh.new()      # boxy dark parts, bevelled
    lens = bmesh.new()
    motor_bits = bmesh.new()  # screws (metal)

    for loc, nrm in vents:
        m = K.frame(loc, nrm)
        for yy in (-0.24, 0.0, 0.24):
            K.add_box(darkb, (-1.35, yy - 0.045, -0.24), (1.35, yy + 0.045, -0.05), m)

    # ---- hinge housings, arms, pods, legs
    shell = bmesh.new()      # extra M_DroneBody parts (housings, arms, pods, legs)
    for s in (1, -1):
        K.add_lathe(shell, K.fillet([(0, 4.3), (0.8, 4.3), (0.8, 5.62), (0, 5.62)], 0.22, 4),
                    Matrix.Translation((3.9, s * 3.35, 0)), segs=28)
        K.add_lathe(dark, K.fillet([(0, 5.5), (0.42, 5.5), (0.42, 5.66), (0, 5.675)], [0, 0, 0.04, 0], 2),
                    Matrix.Translation((3.9, s * 3.35, 0)), segs=24)
        K.add_lathe(shell, K.fillet([(0, 1.75), (0.7, 1.75), (0.7, 3.05), (0, 3.05)], 0.2, 4),
                    Matrix.Translation((-4.4, s * 3.2, 0)), segs=24)

        fpath = S.catmull_rom([(3.9, s * 3.35, 4.95), (4.7, s * 6.0, 5.05), (5.8, s * 8.6, 5.05),
                               (FRONT[0], s * FRONT[1], 4.9)], 10)
        K.add_tube(shell, fpath, lambda u: rrect(0.92 - 0.14 * u, 1.35 - 0.35 * u, 0.32, 3))
        rpath = S.catmull_rom([(-4.4, s * 3.2, 2.5), (-5.6, s * 6.0, 2.9), (-6.6, s * 8.6, 3.45),
                               (REAR[0], s * REAR[1], 3.7)], 10)
        K.add_tube(shell, rpath, lambda u: rrect(0.75 - 0.15 * u, 1.25 - 0.3 * u, 0.26, 3))

        for fr, (mx, my) in ((1, FRONT), (-1, REAR)):
            top = POD_TOP[fr]
            bot = 4.25 if fr == 1 else 3.4
            K.add_lathe(shell, K.fillet([(0, bot), (0.78, bot), (1.06, bot + 0.38), (1.08, top), (0, top)],
                                        [0, 0.2, 0.15, 0.12, 0], 3),
                        Matrix.Translation((mx, s * my, 0)), segs=30)
            lx, ly = mx + 0.15 * fr, s * (my + 0.35)
            leg = S.catmull_rom([(mx, s * my, bot + 0.2), (mx + 0.07 * fr, s * (my + 0.15), bot * 0.5),
                                 (lx, ly, 0.3)], 8)
            wa, wb = (1.3, 0.8) if fr == 1 else (1.1, 0.7)
            ta, tb = (0.56, 0.4) if fr == 1 else (0.5, 0.36)
            K.add_tube(shell, leg, lambda u, wa=wa, wb=wb, ta=ta, tb=tb:
                       ellipse((wa + (wb - wa) * u) / 2, (ta + (tb - ta) * u) / 2), hint=(1, 0, 0))
            K.add_lathe(dark, K.fillet([(0, 0), (0.3, 0), (0.4, 0.08), (0.42, 0.34), (0.3, 0.44), (0, 0.46)],
                                       [0, 0.05, 0.05, 0.08, 0.05, 0], 3),
                        Matrix.Translation((lx, ly, 0)), segs=20)

    # ---- front LEDs on the front pods (forward-outward)
    led = bmesh.new()
    for s in (1, -1):
        d = Vector((1.0, s * 0.6, 0)).normalized()
        c = Vector((FRONT[0], s * FRONT[1], 4.5))
        K.add_prism(led, rrect(0.3, 0.62, 0.13, 3), c + d * 0.8, c + d * 1.115, up=(0, 0, 1))

    # ---- motors (bell with cooling windows, lined dark) and props
    motors, props = [], bmesh.new()
    for (fr, s), (phi, spin) in PROPS.items():
        mx, my = FRONT if fr == 1 else REAR
        c = Vector((mx, s * my, POD_TOP[fr]))
        mb = bmesh.new()
        prof = K.fillet([(0, 0), (0.86, 0), (0.86, 0.1), (0.95, 0.15), (0.95, 0.8), (0.88, 1.0), (0.45, BELL_H),
                         (0, BELL_H + 0.01)], [0, 0, 0.02, 0.03, 0.08, 0.08, 0.05, 0], 3)
        K.add_lathe(mb, prof, Matrix.Translation(c), segs=36)
        mc = bmesh.new()
        for k in range(6):
            a = math.radians(30 + 60 * k + phi)
            K.add_box(mc, (0.8, -0.17, 0.42), (1.2, 0.17, 0.74),
                      Matrix.Translation(c) @ Matrix.Rotation(a, 4, "Z"), slot=1)
        motors.append(K.mk(f"motor_{fr}_{s}", mb, [M["motor"], M["dark"]], bevel=0.015, segs=2, angle=55,
                           cut=mc))
        hz = c.z + BELL_H - 0.02
        K.add_lathe(props, K.fillet([(0, 0), (0.8, 0), (1.02, 0.07), (1.06, 0.2), (0.98, 0.34), (0.62, 0.42),
                                     (0, 0.44)], [0, 0.04, 0.05, 0.06, 0.08, 0.1, 0], 3),
                    Matrix.Translation((c.x, c.y, hz)), segs=36)
        ph = math.radians(phi)
        for side in (1, -1):
            add_blade(props, (c.x, c.y, 0.0), ph + (0 if side == 1 else math.pi), spin, hz + 0.24)
            R = Vector((math.cos(ph), math.sin(ph), 0)) * side
            screw_head(motor_bits, Vector((c.x, c.y, hz + 0.43)) + R * 0.5, (0, 0, 1))

    # ---- gimbal: yaw (under the chin) -> roll (behind the camera) -> bracket -> pitch (left side) -> camera
    gim = bmesh.new()
    gimb = bmesh.new()
    K.add_lathe(gim, K.fillet([(0, 2.85), (0.6, 2.85), (0.65, 2.95), (0.65, 3.75), (0, 3.75)], [0, 0.05, 0.05, 0, 0]),
                Matrix.Translation((4.75, 0, 0)), segs=32)
    K.add_lathe(gim, K.fillet([(0, 0), (0.55, 0), (0.6, 0.08), (0.6, 0.62), (0.55, 0.7), (0, 0.7)],
                              [0, 0.04, 0.04, 0.04, 0.04, 0]),
                Matrix.Translation((4.3, 0, 2.4)) @ Matrix.Rotation(math.radians(90), 4, "Y"), segs=32)
    K.add_box(gimb, (4.98, -1.78, 1.95), (5.16, 0.2, 2.85))
    K.add_box(gimb, (4.98, -1.78, 1.95), (6.6, -1.58, 2.85))
    K.add_lathe(gim, K.fillet([(0, 0), (0.5, 0), (0.55, 0.06), (0.55, 0.4), (0.5, 0.44), (0, 0.44)],
                              [0, 0.03, 0.03, 0.03, 0.03, 0]),
                Matrix.Translation((6.15, -1.64, 2.4)) @ Matrix.Rotation(math.radians(-90), 4, "X"), segs=28)
    cam_body = bmesh.new()
    K.add_box(cam_body, (5.3, -1.2, 1.45), (7.02, 1.2, 3.3))
    lens_m = Matrix.Translation((6.95, 0, 2.4)) @ Matrix.Rotation(math.radians(90), 4, "Y")
    K.add_lathe(gim, K.fillet([(0, -0.1), (0.78, -0.1), (0.8, 0.2), (0.74, 0.3), (0.62, 0.3), (0.58, 0.24),
                               (0.5, 0.22), (0, 0.22)], [0, 0, 0.05, 0.03, 0.02, 0.02, 0, 0], 3), lens_m, segs=40)
    K.add_lathe(lens, K.fillet([(0, 0.34), (0.25, 0.325), (0.45, 0.275), (0.53, 0.21), (0.53, 0.15), (0, 0.15)],
                               [0, 0, 0.02, 0.02, 0, 0], 2), lens_m, segs=40)

    # ---- sensors (front pair, rear pair, downward pair), battery latches, screws: placed on the shell
    for s in (1, -1):
        socket(dark, lens, *K.hit(body_bvh, (15, s * 2.05, 5.05), (-1, 0, 0)))
        socket(dark, lens, *K.hit(body_bvh, (-15, s * 1.9, 4.55), (1, 0, 0)), r=0.55)
        socket(dark, lens, *K.hit(body_bvh, (0.9, s * 1.25, -5), (0, 0, 1)), r=0.5, up=(1, 0, 0))
        loc, nrm = K.hit(body_bvh, (-5.0, s * 12, 4.15), (0, -s, 0))
        m = K.frame(loc, nrm)
        K.add_prism(darkb, rrect(0.95, 0.5, 0.2, 3), m @ Vector((0, 0, -0.3)), m @ Vector((0, 0, 0.05)),
                    up=m.col[0].xyz)
        for k in (-0.25, 0.0, 0.25):
            K.add_box(darkb, (k - 0.04, -0.17, 0.0), (k + 0.04, 0.17, 0.085), m)
        for x in (2.2, -4.8):
            screw_head(motor_bits, *K.hit(body_bvh, (x, s * 2.6, -5), (0, 0, 1)))
    socket(dark, lens, *K.hit(body_bvh, (-1.2, 0, -5), (0, 0, 1)), r=0.32, up=(1, 0, 0))

    parts.append(K.mk("shell_parts", shell, M["body"]))
    arms_bvh = K.bvh_of([parts[-1]])
    for s in (1, -1):
        for p in ((5.3, s * 7.4), (-6.0, s * 7.2)):
            screw_head(motor_bits, *K.hit(arms_bvh, (p[0], p[1], -5), (0, 0, 1)))

    parts += motors
    parts.append(K.mk("dark_parts", dark, M["dark"]))
    parts.append(K.mk("dark_boxes", darkb, M["dark"], bevel=0.02, segs=2, angle=40))
    parts.append(K.mk("lens", lens, M["lens"]))
    parts.append(K.mk("leds", led, M["led"], bevel=0.03, segs=2, angle=40))
    parts.append(K.mk("screws", motor_bits, M["motor"]))
    parts.append(K.mk("gimbal", gim, M["gimbal"]))
    parts.append(K.mk("gimbal_plates", gimb, M["gimbal"], bevel=0.06, segs=3, angle=40))
    parts.append(K.mk("camera", cam_body, M["gimbal"], bevel=0.3, segs=4, angle=40))
    prop_ob = K.mk("props", props, M["prop"])
    parts.append(prop_ob)

    clearance(prop_ob, [p for p in parts if p is not prop_ob])
    return parts


def clearance(prop_ob, others):
    """Print how close the parked blades come to everything else (cm), ignoring the hubs' own motors."""
    tree = K.bvh_of(others)
    worst = 1e9
    for v in prop_ob.data.vertices:
        r = min(math.hypot(v.co.x - mx, v.co.y - s * my) for mx, my in (FRONT, REAR) for s in (1, -1))
        if r < 1.3:
            continue
        _loc, _n, _i, dist = tree.find_nearest(v.co)
        if dist is not None:
            worst = min(worst, dist)
    print(f"drone: closest blade-to-other-part distance {worst:.2f} cm")


def main():
    args = S.parse_args(__file__)
    S.reset_scene()
    parts = build()
    ob, origin = K.assemble("drone", parts, sharp_angle=40)
    lo, hi = S.bbox(ob)
    print(f"drone: footprint {100 * (hi.x - lo.x):.1f} (X, depth) x {100 * (hi.y - lo.y):.1f} (Y) cm; "
          f"origin offset from body centre {100 * origin.x:.2f}, {100 * origin.y:.2f} cm")
    K.export(ob, args)
    if args.no_render:
        return
    S.render_preview(ob, os.path.join(args.out, "drone.png"), (1.0, -0.75, 0.7), args.samples, lens=60)
    K.shoot(ob, os.path.join(args.out, "drone_front.png"), view_dir=(1.0, 0.0, 0.1), lens=60)
    target = Vector((6.0, -0.5, 3.4)) * K.CM - origin
    K.shoot(ob, os.path.join(args.out, "drone_close.png"), lens=55,
            loc=target + Vector((0.75, -0.5, 0.42)).normalized() * 0.30, target=target)
    if os.environ.get("DBG"):
        for tag, v in (("rear", (-1.0, 0.6, 0.6)), ("top", (0.05, 0.0, 1.0)), ("under", (0.3, -0.4, -0.5)),
                       ("side", (0.0, -1.0, 0.15))):
            K.shoot(ob, os.path.join(args.out, f"dbg_{tag}.png"), view_dir=v, lens=60)


if __name__ == "__main__":
    main()
