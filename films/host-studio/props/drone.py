"""drone — a premium foldable mini camera quadcopter (current 249 g class), arms unfolded, resting on its feet as
if just put down, props parked. No logos, names or text anywhere.

Modelled in cm, nose toward +X, then scaled to metres with the origin at the bottom centre of the footprint.

    fuselage   two shells with a real parting line: a faceted top shell (crown, shoulder, chamfer, side wall,
               small radii on every feature line) over a tucked lower shell; the battery is a separate pack
               sliding in at the rear under the top shell, with a ribbed grip and latch buttons
    sensors    forward stereo pair on the nose, rear pair under the top shell's tail, downward pair and a ToF
               window underneath; side intakes with louvres, a bottom grille, a USB-C port and card slot
    arms       front arms hinge out sideways from the upper body, rear arms from the lower body on a raked
               axis; hinge barrels with knuckles and pins; aerofoil arm sections; landing legs with pads
    motors     outrunner bells with spoked tops and side slots, wound stator visible inside, screw-on hubs
    props      two-blade folding props, ~15 cm, cambered aerofoil with twist and a swept tip, blade pivots
               with screws, parked a little out of line as they come to rest
    gimbal     yaw motor on a damped plate under the chin, roll motor behind the camera, pitch motor on its
               side; square camera head with a multi-element lens (rings, coated glass, iris blades)

    blender -b --factory-startup -P films/host-studio/props/drone.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _drone_kit as K  # noqa: E402

# ---------------------------------------------------------------- layout (cm)
XT, XN = -3.1, 6.35             # rear face and nose tip of the shells (the battery pack fills the rear)
LT, LN = 1.4, 1.9               # length of the top shell's raked tail and of the nose rounding
PT, PN = (2.0, 1.6), (3.4, 2.1)  # superellipse exponents in plan (y) and elevation (z)
XL0, LL = XT, 0.12              # rear face of the lower shell and its edge rounding
XB0, XB1 = -7.15, -1.9          # battery pack: rear face, front end (hidden in the body)
LB = 0.8                        # battery's rear rounding

W_ = K.pchip([(-7.15, 2.72), (-6.0, 2.92), (-4.0, 3.1), (-1.0, 3.3), (2.0, 3.36), (3.8, 3.18), (5.0, 2.8),
              (6.35, 2.45)])                                    # half width at the parting line
ZT_ = K.pchip([(-7.15, 6.2), (-5.5, 6.85), (-3.0, 7.25), (0.0, 7.45), (2.5, 7.45), (4.4, 7.22), (6.35, 6.7)])
ZP_ = K.pchip([(-7.15, 4.55), (0.0, 4.65), (4.0, 4.72), (6.35, 4.72)])     # parting line
ZB_ = K.pchip([(-4.4, 2.55), (-2.0, 2.42), (1.6, 2.42), (3.0, 2.62), (4.2, 3.3), (5.2, 3.78), (6.35, 4.0)])
ZBB_ = K.pchip([(-7.15, 2.95), (-5.6, 2.62), (-3.1, 2.56), (-1.9, 2.56)])              # battery underside
ZTB_ = K.pchip([(-7.15, 5.6), (-5.5, 6.18), (-3.1, 6.45), (-1.9, 6.5)])               # battery top (a step below the shell)

FRONT, REAR = (7.2, 10.1), (-7.6, 9.7)          # motor centres (x, |y|); diagonal ~24.6 cm
SEAT = {1: 6.95, -1: 4.1}                        # motor seat height, front / rear
HINGE_F = (2.7, 3.55)                            # front hinge axis (x, |y|), vertical
HINGE_R = (-2.35, 3.12, 3.4)                     # rear hinge centre (x, |y|, z), raked axis
BELL_H = 1.08
PROP_R = 7.5
# parked props, keyed (front/rear, side): the two blade directions (deg from +X) and spin (+1 = CCW from above)
PROPS = {(1, 1): ((97, -80), 1), (1, -1): ((-104, 77), -1),
         (-1, 1): ((152, -31), -1), (-1, -1): ((-149, 26), 1)}

CHORD = K.pchip([(0.75, 0.55), (1.3, 1.02), (2.2, 1.34), (3.1, 1.4), (4.5, 1.24), (5.8, 0.98), (6.8, 0.74),
                 (7.4, 0.5)])
THICK = K.pchip([(0.75, 0.2), (1.4, 0.16), (3.0, 0.1), (7.5, 0.07)])   # t/c
GIM = Vector((6.1, 0.0, 2.5))                  # camera head centre


# ---------------------------------------------------------------- fuselage sections
def nose_tail(x):
    """Scale factors (plan, elevation) of the end roundings at station x."""
    if x > XN - LN:
        u = (x - (XN - LN)) / LN
        return K.end_curve(u, PN[0]), K.end_curve(u, PN[1])
    if x < XT + LT:                              # tail: rakes down onto the battery, square in plan
        u = ((XT + LT) - x) / LT
        return K.end_curve((XT + 0.15 - x) / 0.15, PT[0]), K.end_curve(u, PT[1])
    return 1.0, 1.0


def scaled(pts, f, zc):
    fy, fz = f if isinstance(f, tuple) else (f, f)
    return [(y * fy, zc + (z - zc) * fz) for y, z in pts]


def top_half(x):
    w, zt, zp = W_(x), ZT_(x), ZP_(x)
    h = zt - zp
    ch = min(0.78, 0.3 * h)                      # chamfer height (45 deg)
    zc = zt - 0.16                               # shoulder (chamfer / crown)
    zb = zc - ch                                 # crease (side wall / chamfer)
    wb = w - 0.16
    wc = wb - ch
    crown = [(wc * (1 - k / 5), zt - (zt - zc) * (1 - k / 5) ** 2) for k in range(1, 5)]
    pts = [(0.0, zp), (w, zp), (wb, zb), (wc, zc)] + crown + [(0.0, zt)]
    rad = [0, 0.035, 0.07, 0.2] + [0] * 4 + [0]
    return K.fillet(pts, rad, steps=3)


def top_section(x):
    return scaled(K.mirror_half(top_half(x)), nose_tail(x), ZP_(x))


def lower_half(x, zb, inset, ztop):
    w, zp = W_(x), ZP_(x)
    pts = [(0.0, zb), (w - 0.8, zb), (w - inset, zp - 0.45), (w - inset, ztop), (0.0, ztop)]
    return K.fillet(pts, [0, 0.38, 0.16, 0.025, 0], steps=3)


def lower_section(x):
    f = nose_tail(x) if x > 0 else (1.0, 1.0)
    if x < XL0 + LL:
        e = K.end_curve((XL0 + LL - x) / LL, 2.0)
        f = (e, e)
    zp = ZP_(x)
    return scaled(K.mirror_half(lower_half(x, ZB_(x), 0.085, zp + 0.15)), f, zp if x > 0 else zp - 1.0)


def battery_half(x):
    """The pack: same language as the body (tucked underside, side wall, crease, 45 deg chamfer, crown)."""
    w, zb, zt, zm = W_(x) - 0.15, ZBB_(x), ZTB_(x), ZP_(x)
    ch = min(0.6, 0.3 * (zt - zm))
    zs = zt - 0.14
    zc = zs - ch
    wc = w - 0.16 - ch
    crown = [(wc * (1 - k / 5), zt - (zt - zs) * (1 - k / 5) ** 2) for k in range(1, 5)]
    pts = [(0.0, zb), (w - 0.75, zb), (w, zm - 0.4), (w, zm), (w - 0.16, zc), (wc, zs)] + crown + [(0.0, zt)]
    return K.fillet(pts, [0, 0.38, 0.16, 0.12, 0.07, 0.2] + [0] * 5, steps=3)


def battery_mid(x):
    return (ZBB_(x) + ZTB_(x)) / 2


def battery_section(x):
    f = (1.0, 1.0)
    if x < XB0 + LB:
        u = (XB0 + LB - x) / LB
        f = (K.end_curve(u, 3.6), K.end_curve(u, 2.6))
    elif x > XB1 - 0.3:
        e = K.end_curve((x - (XB1 - 0.3)) / 0.3, 2.0)
        f = (e, e)
    return scaled(K.mirror_half(battery_half(x)), f, battery_mid(x))


def fuselage_stations(x0, x1, dx=0.12):
    n = max(2, int((x1 - x0) / dx))
    return [x0 + (x1 - x0) * k / n for k in range(n + 1)]


def top_shell_bm():
    xs = (sorted(set(K.end_stations(XT + LT, XT, 22, 1.6) + K.end_stations(XT + 0.15, XT, 5, 2.0)))
          + fuselage_stations(XT + LT, XN - LN)[1:]
          + K.end_stations(XN - LN, XN, 22, 2.4))
    bm = bmesh.new()
    K.loft(bm, xs, top_section, Vector((XT, 0, ZP_(XT))), Vector((XN, 0, ZP_(XN))))
    return bm


def lower_shell_bm():
    xs = (list(reversed(K.end_stations(XL0 + LL, XL0, 6, 2.0))) + fuselage_stations(XL0 + LL, XN - LN)
          + K.end_stations(XN - LN, XN, 22, 2.4))
    bm = bmesh.new()
    zl = ZP_(XL0) - 1.0
    K.loft(bm, xs, lower_section, Vector((XL0, 0, zl)), Vector((XN, 0, ZP_(XN))))
    return bm


def battery_bm():
    xs = (list(reversed(K.end_stations(XB0 + LB, XB0, 16, 2.6))) + fuselage_stations(XB0 + LB, XB1 - 0.3)
          + K.end_stations(XB1 - 0.3, XB1, 6, 2.0))
    bm = bmesh.new()
    K.loft(bm, xs, battery_section, Vector((XB0, 0, battery_mid(XB0))), Vector((XB1, 0, battery_mid(XB1))))
    return bm


# ---------------------------------------------------------------- small parts
def rrect(w, h, r, segs=3):
    return S.rounded_rect(w, h, min(r, w / 2 - 1e-4, h / 2 - 1e-4), segs)


def screw_head(bm, p, n, scale=1.0, slot=0):
    """Pan head with a socket dimple."""
    prof = [(0, 0.012), (0.045, 0.012), (0.065, 0.045), (0.13, 0.05), (0.16, 0.03), (0.165, -0.1), (0, -0.1)]
    prof = [(r * scale, z * scale) for r, z in prof]
    K.add_lathe(bm, K.fillet(prof, [0, 0, 0.01, 0.03, 0.02, 0, 0], 2), K.frame(p, n), segs=14, slot=slot)


def socket(bm_dark, bm_lens, p, n, r=0.6, up=(0, 0, 1), proud=0.06):
    """A dark bezel set into the shell carrying a domed glossy sensor window."""
    m = K.frame(p, n, up)
    bez = K.fillet([(0, -0.5), (r + 0.16, -0.5), (r + 0.16, proud - 0.03), (r + 0.11, proud), (r + 0.02, proud),
                    (r - 0.02, proud - 0.05), (0, proud - 0.05)], [0, 0, 0.03, 0.02, 0.015, 0.01, 0], steps=2)
    K.add_lathe(bm_dark, bez, m, segs=28)
    glass = K.fillet([(0, proud + 0.07), (r * 0.6, proud + 0.05), (r - 0.01, proud - 0.01), (r - 0.01, proud - 0.1),
                      (0, proud - 0.1)], [0, 0, 0.04, 0, 0], steps=2)
    K.add_lathe(bm_lens, glass, m, segs=28)
    # the sensor's own small lens inside, seen through the window
    K.add_lathe(bm_dark, K.fillet([(0, proud - 0.06), (r * 0.42, proud - 0.06), (r * 0.42, proud - 0.12),
                                   (0, proud - 0.12)], 0.02, 2), m, segs=20)


def pad(bm, centre, a, b, h, slot=0):
    """Rubber foot: rounded oval pad, bottom at centre.z."""
    prof = K.fillet([(0, 0), (0.85, 0), (1.0, 0.25), (0.9, 1.0), (0, 1.0)], [0, 0.12, 0.2, 0.25, 0], 3)
    sc = Matrix.Diagonal((a, b, h, 1.0))
    K.add_lathe(bm, [(r, z) for r, z in prof], Matrix.Translation(centre) @ sc, segs=24, slot=slot)


def add_blade(bm, hub, phi, spin, zc):
    """One folding blade along direction phi from the hub centre: root lug, cambered aerofoil, twist, swept tip."""
    R = Vector((math.cos(phi), math.sin(phi), 0.0))
    Z = Vector((0, 0, 1))
    T = Z.cross(R) * spin                      # direction of travel (leading edge side)
    N, NA = 30, 9
    xcs = [0.5 * (1 - math.cos(math.pi * k / NA)) for k in range(NA + 1)]
    pts = [(xc, 1) for xc in reversed(xcs)] + [(xc, -1) for xc in xcs[1:]]
    cm_, pm_ = 0.045, 0.38
    r0 = 0.75
    rs = [r0 + (PROP_R - 0.05 - r0) * (1 - math.cos(k / N * math.pi / 2)) ** 0.85 for k in range(N + 1)]
    rings = []
    for r in rs:
        c = CHORD(r)
        tip = K.smoothstep(6.3, PROP_R, r)
        if r > 6.6:
            c *= math.sqrt(max(0.0, 1 - ((r - 6.6) / (PROP_R - 6.6 + 0.02)) ** 2.2))
        c = max(c, 0.1)
        root = 1 - K.smoothstep(0.75, 1.5, r)
        beta = min(math.radians(30), math.atan(7.4 / (2 * math.pi * r))) * (1 - 0.6 * root)
        tr = THICK(r)
        cd = T * math.cos(beta) + Z * math.sin(beta)
        nd = Z * math.cos(beta) - T * math.sin(beta)
        sweep = -0.6 * max(0.0, (r - 3.5) / 4.0) ** 2 - 0.25 * tip     # leading edge sweeps back to the tip
        base = Vector(hub) + R * r + T * sweep + Z * zc
        lead = 0.32 + 0.1 * tip                                       # chord fraction ahead of the blade axis
        ring = []
        for xc, sg in pts:
            yt = naca_t(xc, tr) * c + 0.006 * xc
            if xc < pm_:
                yc = cm_ / pm_ ** 2 * (2 * pm_ * xc - xc * xc)
            else:
                yc = cm_ / (1 - pm_) ** 2 * ((1 - 2 * pm_) + 2 * pm_ * xc - xc * xc)
            yc *= (1 - root)
            ring.append(tuple(base + cd * ((lead - xc) * c) + nd * (yc * c + sg * yt)))
        rings.append(ring)
    last = rings[-1]
    tip = sum((Vector(p) for p in last), Vector()) / len(last) + R * 0.05
    K.add_grid(bm, rings, "ngon", tip)


def naca_t(x, t):
    return K.naca(x, t)


def lug(bm, centre, phi, zc, h=0.13):
    """The blade's flat root lug around its pivot, between the hub plates."""
    out = [(math.cos(a) * 0.3, math.sin(a) * 0.3) for a in
           [math.pi / 2 + math.pi * k / 10 for k in range(11)]] + [(0.75, -0.24), (0.75, 0.24)]
    m = Matrix.Translation((centre[0], centre[1], zc)) @ Matrix.Rotation(phi, 4, "Z")
    rings = [[tuple(m @ Vector((a, b, z))) for a, b in out] for z in (-h / 2, h / 2)]
    K.add_grid(bm, rings, "ngon", "ngon")


# ---------------------------------------------------------------- build
def build():
    M = K.materials()
    parts = []
    dark = bmesh.new()       # lathes and small parts in M_DroneDark
    darkb = bmesh.new()      # boxy dark parts, bevelled
    lens = bmesh.new()
    metal = bmesh.new()      # screws, pins (M_Motor)
    shell = bmesh.new()      # extra M_DroneBody parts (hinge knuckles, arms, pods, legs)
    shellb = bmesh.new()     # boxy body-coloured parts, bevelled
    led = bmesh.new()

    # ---- top shell, with sockets cut for the front and rear sensor pairs (lined dark)
    top = top_shell_bm()
    top_bvh = K.bvh_bm(top)
    tcut = bmesh.new()
    sensors = []
    for s in (1, -1):
        for org, d, r in (((20, s * 1.38, 5.72), (-1, 0, 0), 0.43), ((-20, s * 1.25, 6.85), (1, 0, 0), 0.3)):
            p, n = K.hit(top_bvh, org, d)
            K.add_lathe(tcut, [(0, -0.5), (r + 0.17, -0.5), (r + 0.17, 2.0), (0, 2.0)], K.frame(p, n), segs=32, slot=1)
            sensors.append((p, n, r))

    # ---- lower shell with side intakes, bottom grille, USB-C port and card slot cut in (lined dark)
    low = lower_shell_bm()
    low_bvh = K.bvh_bm(low)
    cut = bmesh.new()
    intakes = []
    for s in (1, -1):
        loc, nrm = K.hit(low_bvh, (-0.1, s * 12, 3.6), (0, -s, 0))
        K.add_prism(cut, rrect(2.7, 0.78, 0.3, 4), loc - nrm * 0.25, loc + nrm * 1.5, up=(1, 0, 0), slot=1)
        intakes.append((loc, nrm))
    for k in range(7):
        x = -2.55 + 0.36 * k
        loc, nrm = K.hit(low_bvh, (x, 0, -5), (0, 0, 1))
        K.add_prism(cut, rrect(0.17, 2.6, 0.08, 3), loc - nrm * 0.18, loc + nrm * 1.0, up=(1, 0, 0), slot=1)
    loc, nrm = K.hit(low_bvh, (1.95, -12, 3.72), (0, 1, 0))
    K.add_prism(cut, rrect(0.92, 0.32, 0.15, 4), loc - nrm * 0.3, loc + nrm * 1.0, up=(1, 0, 0), slot=1)
    usb = (loc, nrm)
    loc, nrm = K.hit(low_bvh, (1.95, -12, 3.25), (0, 1, 0))
    K.add_prism(cut, rrect(1.1, 0.12, 0.05, 2), loc - nrm * 0.2, loc + nrm * 1.0, up=(1, 0, 0), slot=1)
    parts.append(K.mk("lower_shell", low, [M["body"], M["dark"]], cut=cut))
    parts.append(K.mk("top_shell", top, [M["body"], M["dark"]], cut=tcut))
    battery = battery_bm()
    batt_bvh = K.bvh_bm(battery)
    parts.append(K.mk("battery", battery, M["body"]))

    # louvres in the side intakes, tongue in the USB-C port
    for loc, nrm in intakes:
        m = K.frame(loc, nrm, (0, 0, 1))
        for k in range(-2, 3):
            yy = 0.135 * k
            fr = m @ Matrix.Translation((0, yy, -0.12)) @ Matrix.Rotation(math.radians(-35), 4, "X")
            K.add_box(shellb, (-1.25, -0.03, -0.11), (1.25, 0.03, 0.11), fr)
    m = K.frame(usb[0], usb[1], (0, 0, 1))
    K.add_box(darkb, (-0.3, -0.04, -0.28), (0.3, 0.04, -0.12), m)

    # ---- battery: ribbed grip across the top of its rear face, latch buttons on its chamfers near the front,
    #      power button and four level LEDs low on the rear face
    for k in range(7):
        z = ZTB_(XB0) - 0.42 - 0.17 * k
        K.conform_strip(batt_bvh, [(XB0, -1.3 + 2.6 * j / 12, z) for j in range(13)], (1, 0, 0),
                        [(0.035 * math.cos(a), 0.05 * math.sin(a)) for a in
                         [2 * math.pi * i / 8 for i in range(8)]], dark, lift=0.0)
    for s in (1, -1):
        loc, nrm = K.hit(batt_bvh, (-3.95, s * 14.2, 17.9), Vector((0, -s, -1)).normalized())
        m = K.frame(loc, nrm, (1, 0, 0))
        K.add_prism(darkb, rrect(0.5, 1.05, 0.22, 4), m @ Vector((0, 0, -0.25)), m @ Vector((0, 0, 0.06)),
                    up=m.col[0].xyz)
        for k in (-0.3, -0.1, 0.1, 0.3):
            K.add_box(darkb, (-0.17, k - 0.03, 0.03), (0.17, k + 0.03, 0.095), m)
    zl = battery_mid(XB0) - 0.75
    loc, nrm = K.hit(batt_bvh, (-20, 1.35, zl), (1, 0, 0))
    K.add_lathe(darkb, K.fillet([(0, 0.07), (0.2, 0.07), (0.24, 0.0), (0.24, -0.2), (0, -0.2)],
                                [0, 0.03, 0.02, 0, 0], 2), K.frame(loc, nrm), segs=20)
    for j in range(4):
        loc, nrm = K.hit(batt_bvh, (-20, -0.3 + 0.2 * j, zl), (1, 0, 0))
        K.add_lathe(darkb, [(0, 0.03), (0.04, 0.03), (0.05, 0.0), (0.05, -0.2), (0, -0.2)],
                    K.frame(loc, nrm), segs=10)

    # ---- sensors: forward stereo pair, rear pair, downward pair + ToF
    for p, n, r in sensors:
        socket(dark, lens, p - n * 0.12, n, r=r, proud=0.0)
    for s in (1, -1):
        p, n = K.hit(low_bvh, (2.0, s * 1.2, -5), (0, 0, 1))
        socket(dark, lens, p, n, r=0.38, up=(1, 0, 0), proud=0.04)
    p, n = K.hit(low_bvh, (1.0, 0, -5), (0, 0, 1))
    m = K.frame(p, n, (1, 0, 0))
    K.add_prism(darkb, rrect(0.95, 0.55, 0.2, 4), m @ Vector((0, 0, -0.3)), m @ Vector((0, 0, 0.04)),
                up=m.col[0].xyz)
    K.add_prism(lens, rrect(0.75, 0.38, 0.14, 4), m @ Vector((0, 0, -0.1)), m @ Vector((0, 0, 0.075)),
                up=m.col[0].xyz)

    # bottom screws
    for x, y in ((-0.4, 2.0), (3.1, 1.5), (-2.75, 1.95)):
        for s in (1, -1):
            screw_head(metal, *K.hit(low_bvh, (x, s * y, -5), (0, 0, 1)), scale=0.95)

    # ---- front arms: vertical hinge barrel (body knuckles top/bottom, arm knuckle between, pin), aerofoil arm,
    #      motor pod, landing leg with pad, LED on the leg's leading edge
    for s in (1, -1):
        hx, hy = HINGE_F[0], s * HINGE_F[1]
        knuckle = lambda z0, z1, r=0.5: K.fillet([(0, z0), (r, z0), (r, z1), (0, z1)], [0, 0.07, 0.07, 0], 3)
        mH = Matrix.Translation((hx, hy, 0))
        for z0, z1 in ((5.22, 5.55), (6.56, 6.9)):          # body knuckles: lugs growing out of the shell
            ear = [(a, b - s * 0.5) for a, b in rrect(1.0, 2.0, 0.5, 6)]
            K.add_prism(shellb, ear, (hx, hy, z0), (hx, hy, z1), up=(1, 0, 0))
        K.add_lathe(shell, knuckle(5.6, 6.51, 0.52), mH, segs=28)
        K.add_lathe(metal, K.fillet([(0, 5.15), (0.2, 5.15), (0.2, 6.9), (0.3, 6.9), (0.3, 6.95), (0.2, 6.99),
                                     (0.07, 6.99), (0.05, 6.94), (0, 6.94)], [0, 0, 0, 0.02, 0.03, 0.02, 0, 0, 0],
                                    2), mH, segs=20)
        path = S.catmull_rom([(hx, hy, 6.05), (hx + 0.9, s * 5.4, 6.12), (5.4, s * 8.1, 6.22),
                              (FRONT[0], s * FRONT[1], 6.28)], 12)
        K.add_tube(shell, path, lambda u: K.foil(0.86 - 0.22 * u, 0.6 - 0.18 * u, n=9, blunt=0.05), hint=(0, 0, 1))
        mx, my = FRONT[0], s * FRONT[1]
        z0 = SEAT[1] - 0.95
        K.add_lathe(shell, K.fillet([(0, z0), (0.55, z0), (0.98, z0 + 0.4), (1.0, SEAT[1] - 0.05),
                                     (0.96, SEAT[1]), (0, SEAT[1])], [0, 0.3, 0.25, 0.04, 0, 0], 4),
                    Matrix.Translation((mx, my, 0)), segs=40)
        leg = S.catmull_rom([(mx - 0.05, my, z0 + 0.6), (mx + 0.06, my + s * 0.1, 3.4),
                             (mx + 0.22, my + s * 0.28, 0.42)], 12)
        K.add_tube(shell, leg, lambda u: [(b, a) for a, b in K.foil(1.75 - 0.85 * u ** 0.7, 0.86 - 0.42 * u ** 0.7,
                                                                     n=9, blunt=0.06)], hint=(0, 1, 0))
        pad(dark, (mx + 0.22, my + s * 0.28, 0.0), 0.55, 0.32, 0.5)
        # LED window on the leg's leading edge, facing forward
        p, n = K.hit(K.bvh_bm(shell), (mx + 5, my, 4.85), (-1, 0, 0))
        m = K.frame(p, n, (0, 0, 1))
        K.add_prism(led, rrect(0.2, 0.62, 0.09, 3), m @ Vector((0, 0, -0.15)), m @ Vector((0, 0, 0.035)),
                    up=m.col[0].xyz)

    # ---- rear arms: raked hinge in the lower body, arm out and back to a low pod with a short foot
    for s in (1, -1):
        hx, hy, hz = HINGE_R[0], s * HINGE_R[1], HINGE_R[2]
        ax = Vector((-0.3, s * 0.32, 1.0)).normalized()
        mH = K.frame((hx, hy, hz), ax, (1, 0, 0))
        knuckle = lambda z0, z1, r=0.46: K.fillet([(0, z0), (r, z0), (r, z1), (0, z1)], [0, 0.07, 0.07, 0], 3)
        for z0, z1 in ((-0.8, -0.5), (0.5, 0.8)):
            ear = [(a + s * 0.5, b) for a, b in rrect(1.92, 0.92, 0.46, 6)]
            K.add_prism(shellb, ear, mH @ Vector((0, 0, z0)), mH @ Vector((0, 0, z1)), up=mH.col[0].xyz)
        K.add_lathe(shell, knuckle(-0.45, 0.45, 0.48), mH, segs=26)
        K.add_lathe(metal, K.fillet([(0, -0.88), (0.18, -0.88), (0.18, 0.8), (0.27, 0.8), (0.27, 0.85),
                                     (0.18, 0.89), (0.06, 0.89), (0.04, 0.84), (0, 0.84)],
                                    [0, 0, 0, 0.02, 0.03, 0.02, 0, 0, 0], 2), mH, segs=18)
        path = S.catmull_rom([(hx, hy, hz), (hx - 1.1, s * 5.3, hz + 0.02), (-6.2, s * 8.0, 3.42),
                              (REAR[0], s * REAR[1], 3.45)], 12)
        K.add_tube(shell, path, lambda u: K.foil(0.8 - 0.18 * u, 0.56 - 0.16 * u, n=9, blunt=0.05), hint=(0, 0, 1))
        mx, my = REAR[0], s * REAR[1]
        z0 = SEAT[-1] - 0.95
        K.add_lathe(shell, K.fillet([(0, z0), (0.55, z0), (0.96, z0 + 0.4), (0.98, SEAT[-1] - 0.05),
                                     (0.94, SEAT[-1]), (0, SEAT[-1])], [0, 0.3, 0.25, 0.04, 0, 0], 4),
                    Matrix.Translation((mx, my, 0)), segs=40)
        foot = S.catmull_rom([(mx, my, z0 + 0.5), (mx - 0.12, my + s * 0.12, 1.7), (mx - 0.3, my + s * 0.25, 0.4)], 10)
        K.add_tube(shell, foot, lambda u: [(b, a) for a, b in K.foil(1.5 - 0.6 * u ** 0.7, 0.76 - 0.34 * u ** 0.7,
                                                                      n=9, blunt=0.06)], hint=(0, 1, 0))
        pad(dark, (mx - 0.3, my + s * 0.25, 0.0), 0.5, 0.32, 0.5)

    shell_ob = K.mk("shell_parts", shell, M["body"])
    parts.append(shell_ob)
    parts.append(K.mk("shell_boxes", shellb, M["body"], bevel=0.035, segs=2, angle=40))

    # ---- motors and props
    motors, props, hubs, hubsb = [], bmesh.new(), bmesh.new(), bmesh.new()
    for (fr, s), (angles, spin) in PROPS.items():
        mx, my = FRONT if fr == 1 else REAR
        c = Vector((mx, s * my, SEAT[fr]))
        motors += motor(M, c, math.radians(angles[0]), f"motor_{fr}_{s}", metal, dark)
        hz = c.z + BELL_H + 0.06
        # screw-on hub: dog-bone plates above and below the blade lugs carrying the two pivots, a waist and
        # a domed centre; each blade swings on its own pivot, so the pair rests a little out of line
        ph0 = math.radians(angles[0])
        R0 = Vector((math.cos(ph0), math.sin(ph0), 0))
        bone = rrect(2.04, 0.84, 0.42, 6)
        for z0, z1 in ((0.0, 0.1), (0.27, 0.37)):
            K.add_prism(hubsb, bone, (c.x, c.y, hz + z0), (c.x, c.y, hz + z1), up=tuple(R0))
        K.add_lathe(hubs, K.fillet([(0, 0.05), (0.44, 0.05), (0.44, 0.33), (0.4, 0.37), (0.36, 0.45), (0.2, 0.5),
                                    (0, 0.51)], [0, 0, 0, 0.02, 0.03, 0.04, 0], 2),
                    Matrix.Translation((c.x, c.y, hz)), segs=32)
        K.add_lathe(metal, K.fillet([(0, 0.0), (0.38, 0.0), (0.38, -0.06), (0, -0.06)], [0, 0, 0, 0], 1),
                    Matrix.Translation((c.x, c.y, hz)), segs=28)                    # threaded collar
        for k, a in enumerate(angles):
            ph = math.radians(a)
            Rb = Vector((math.cos(ph), math.sin(ph), 0))
            piv = Vector((c.x, c.y, 0)) + R0 * (0.6 if k == 0 else -0.6)
            lug(props, piv, ph, hz + 0.185)
            add_blade(props, tuple(piv - Rb * 0.6), ph, spin, hz + 0.185)
            screw_head(metal, Vector((piv.x, piv.y, hz + 0.37)), (0, 0, 1), scale=0.9)

    # ---- gimbal: damped mount plate under the chin, yaw motor, yaw arm down to the roll motor behind the
    #      camera, roll bracket round the -Y side to the pitch motor, camera head with the lens
    gim, gimb = bmesh.new(), bmesh.new()
    gx, gz = GIM.x, GIM.z
    yx = 4.7                                                                    # yaw axis
    for x in (3.95, 5.35):
        for y in (-0.95, 0.95):
            p, n = K.hit(low_bvh, (x, y, -5), (0, 0, 1))
            K.add_lathe(gim, K.fillet([(0, -0.22), (0.16, -0.2), (0.22, 0.0), (0.16, 0.2), (0, 0.22)],
                                      [0, 0.05, 0.08, 0.05, 0], 3),
                        Matrix.Translation(p + Vector((0, 0, -0.08))), segs=16)     # damper balls
    K.add_lathe(gim, K.fillet([(0, 3.1), (0.6, 3.1), (0.66, 3.17), (0.66, 3.55), (0.5, 3.95), (0, 3.95)],
                              [0, 0.04, 0.04, 0.08, 0, 0], 3), Matrix.Translation((yx, 0, 0)), segs=40)
    for k in range(20):                                                         # yaw motor cooling ribs
        m = Matrix.Translation((yx, 0, 0)) @ Matrix.Rotation(2 * math.pi * k / 20, 4, "Z")
        K.add_box(gimb, (0.62, -0.025, 3.22), (0.7, 0.025, 3.48), m)
    K.add_prism(gimb, rrect(0.95, 1.4, 0.22, 3), (4.06, 0, gz + 0.12), (4.32, 0, gz + 0.12), up=(0, 1, 0))  # yaw arm
    roll_m = Matrix.Translation((4.3, 0, gz)) @ Matrix.Rotation(math.radians(90), 4, "Y")
    K.add_lathe(gim, K.fillet([(0, 0), (0.58, 0), (0.62, 0.06), (0.62, 0.6), (0.56, 0.68), (0, 0.68)],
                              [0, 0.04, 0.04, 0.04, 0.04, 0], 3), roll_m, segs=36)
    K.add_lathe(metal, [(0, 0.67), (0.24, 0.67), (0.24, 0.73), (0, 0.73)], roll_m, segs=20)
    K.add_prism(gimb, rrect(2.1, 0.96, 0.2, 3), (4.98, -0.72, gz), (5.13, -0.72, gz), up=(0, 1, 0))  # roll bracket
    arc = [(gx - 4.98 + 0.62 * math.cos(a), -0.62 * math.sin(a)) for a in
           [math.radians(-90 + 180 * k / 12) for k in range(13)]]
    side = K.ccw(arc + [(0.15, -0.48), (0.0, -0.33), (0.0, 0.33), (0.15, 0.48)])
    K.add_prism(gimb, side, (4.98, -1.79, gz), (4.98, -1.62, gz), up=(1, 0, 0))        # ... along the -Y side
    pitch_m = Matrix.Translation((gx, -1.14, gz)) @ Matrix.Rotation(math.radians(90), 4, "X")
    K.add_lathe(gim, K.fillet([(0, 0), (0.56, 0), (0.6, 0.05), (0.6, 0.42), (0.54, 0.48), (0, 0.48)],
                              [0, 0.03, 0.03, 0.04, 0.03, 0], 3), pitch_m, segs=36)
    K.add_lathe(gim, K.fillet([(0, 0), (0.4, 0), (0.44, 0.04), (0.44, 0.18), (0.38, 0.22), (0, 0.22)],
                              [0, 0.02, 0.02, 0.03, 0.02, 0], 2),
                Matrix.Translation((gx, 1.12, gz)) @ Matrix.Rotation(math.radians(-90), 4, "X"), segs=28)
    cam_body = bmesh.new()
    K.add_box(cam_body, (5.15, -1.15, gz - 1.0), (6.8, 1.15, gz + 1.0))             # body
    K.add_box(cam_body, (6.83, -1.13, gz - 0.98), (7.05, 1.13, gz + 0.98))          # front cover (seam between)
    K.add_lathe(metal, [(0.3, 0.46), (0.42, 0.46), (0.42, 0.5), (0.3, 0.5), (0.3, 0.46)],
                Matrix.Translation((gx, -1.14, gz)) @ Matrix.Rotation(math.radians(90), 4, "X"), segs=32)
    lens_assembly(gim, lens, metal, Matrix.Translation((7.05, 0, gz)) @ Matrix.Rotation(math.radians(90), 4, "Y"))

    parts += motors
    parts.append(K.mk("dark_parts", dark, M["dark"]))
    parts.append(K.mk("dark_boxes", darkb, M["dark"], bevel=0.02, segs=2, angle=40))
    parts.append(K.mk("lens", lens, M["lens"]))
    parts.append(K.mk("leds", led, M["led"], bevel=0.025, segs=2, angle=40))
    parts.append(K.mk("metal", metal, M["motor"]))
    parts.append(K.mk("hubs", hubs, M["dark"]))
    parts.append(K.mk("hub_plates", hubsb, M["dark"], bevel=0.03, segs=2, angle=40))
    parts.append(K.mk("gimbal", gim, M["gimbal"]))
    parts.append(K.mk("gimbal_plates", gimb, M["gimbal"], bevel=0.04, segs=2, angle=40))
    parts.append(K.mk("camera", cam_body, M["gimbal"], bevel=0.24, segs=4, angle=40))
    prop_ob = K.mk("props", props, M["prop"])
    parts.append(prop_ob)

    clearance(prop_ob, [p for p in parts if p is not prop_ob])
    return parts


def motor(M, c, phi, name, metal, dark):
    """Outrunner on its seat at c: base ring, slotted bell wall, spoked top, wound stator inside."""
    mb = bmesh.new()
    base = Matrix.Translation(c)
    K.add_lathe(mb, K.fillet([(0, 0.0), (0.9, 0.0), (0.92, 0.1), (0, 0.1)], [0, 0.02, 0, 0], 2), base, segs=40)
    # bell wall: a hollow cup without a top (lathe of the wall's cross-section)
    wall = K.fillet([(0.86, 0.16), (0.96, 0.16), (0.98, 0.22), (0.98, BELL_H - 0.12), (0.93, BELL_H - 0.04),
                     (0.86, BELL_H - 0.04)], [0, 0.02, 0.02, 0.06, 0.02, 0], 2)
    K.add_lathe(mb, wall + [wall[0]], base, segs=48)
    # spoked top: rim, hub, six swept spokes
    top = BELL_H - 0.14
    K.add_lathe(mb, [(0.0, top), (0.9, top), (0.9, BELL_H - 0.04), (0.0, BELL_H - 0.04)], base, segs=48)
    cut = bmesh.new()
    for k in range(6):
        a = phi + math.pi / 6 + k * math.pi / 3
        out = [(0.44 * math.cos(a + d), 0.44 * math.sin(a + d)) for d in (-0.2, 0.0, 0.2)] + \
              [(0.74 * math.cos(a + d), 0.74 * math.sin(a + d)) for d in (0.34, 0.17, 0.0, -0.17, -0.34)]
        out = K.ccw(out)
        K.add_prism(cut, out, c + Vector((0, 0, top - 0.1)), c + Vector((0, 0, BELL_H + 0.1)), up=(1, 0, 0), slot=1)
    for k in range(10):                                                     # side slots low on the bell
        a = phi + 2 * math.pi * k / 10
        m = base @ Matrix.Rotation(a, 4, "Z")
        K.add_box(cut, (0.75, -0.11, 0.3), (1.1, 0.11, 0.5), m, slot=1)
    K.add_lathe(mb, K.fillet([(0, BELL_H - 0.04), (0.36, BELL_H - 0.04), (0.36, BELL_H + 0.06), (0, BELL_H + 0.06)],
                             [0, 0, 0.02, 0], 2), base, segs=28)
    ob = K.mk(name, mb, [M["motor"], M["dark"]], cut=cut)
    # stator: twelve teeth with windings, a dark core
    st = bmesh.new()
    K.add_lathe(st, [(0, 0.12), (0.45, 0.12), (0.45, BELL_H - 0.2), (0, BELL_H - 0.2)], base, segs=24)
    for k in range(12):
        a = phi + 2 * math.pi * k / 12
        m = base @ Matrix.Rotation(a, 4, "Z")
        K.add_box(st, (0.4, -0.12, 0.17), (0.8, 0.12, BELL_H - 0.24), m)
        K.add_box(st, (0.48, -0.17, 0.22), (0.72, 0.17, BELL_H - 0.29), m, slot=1)
    stator = K.mk(name + "_stator", st, [M["motor"], M["dark"]])
    return [ob, stator]


def lens_assembly(gim, lens, metal, m):
    """Lens on the camera face (local +Z out of the face): stepped barrel rings, iris, two glass elements."""
    K.add_lathe(gim, K.fillet([(0, -0.05), (0.98, -0.05), (0.98, 0.12), (0.93, 0.2), (0.86, 0.2), (0.84, 0.16),
                               (0.78, 0.16), (0.74, 0.1), (0.66, 0.1), (0.6, 0.02), (0, 0.02)],
                              [0, 0, 0.03, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0, 0], 2), m, segs=56)
    ring = [(0.7, 0.15), (0.83, 0.15), (0.83, 0.172), (0.7, 0.172)]
    K.add_lathe(metal, ring + [ring[0]], m, segs=56)
    # iris: seven blades leaving a heptagonal opening, set back inside the barrel
    for k in range(7):
        a = 2 * math.pi * k / 7
        rot = m @ Matrix.Rotation(a, 4, "Z")
        out = [(0.22, -0.02), (0.6, -0.36), (0.62, 0.14), (0.26, 0.2)]
        rings = [[tuple(rot @ Vector((u, v, z + 0.012 * k))) for u, v in out] for z in (0.03, 0.045)]
        K.add_grid(gim, rings, "ngon", "ngon")
    # rear element (small, deep) and the domed front element
    K.add_lathe(lens, K.fillet([(0, 0.13), (0.3, 0.12), (0.4, 0.09), (0.4, 0.07), (0, 0.07)], [0, 0, 0.02, 0, 0], 2),
                m, segs=40)
    K.add_lathe(lens, K.fillet([(0, 0.31), (0.35, 0.29), (0.6, 0.22), (0.66, 0.17), (0.66, 0.14), (0, 0.14)],
                               [0, 0, 0.03, 0.02, 0, 0], 2), m, segs=56)


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


# ---------------------------------------------------------------- previews
def shelf_shot(ob, path, args):
    """The drone on a light-oak shelf 26 cm deep against a wall, from the studio shelf camera's angle."""
    sc = bpy.context.scene
    for o in list(sc.objects):
        if o.name.startswith("_") and o.type != "CAMERA":
            bpy.data.objects.remove(o, do_unlink=True)
    lo, hi = S.bbox(ob)
    depth, length, thick = 0.26, 1.2, 0.035
    xf = hi.x + 0.012
    bm = bmesh.new()
    K.add_box(bm, (xf - depth, -length / 2, -thick), (xf, length / 2, 0))
    shelf = K.mk("_shelf", bm, K.oak(), bevel=0.002, segs=3, angle=40)
    bm = bmesh.new()
    K.add_box(bm, (xf - depth - 0.02, -3, -1.5), (xf - depth, 3, 1.5))
    K.mk("_wall", bm, S.material("_Wall", (0.62, 0.55, 0.47), 0.9))
    bm = bmesh.new()
    K.add_box(bm, (xf - depth, -length / 2, 0.40), (xf, length / 2, 0.435))
    K.mk("_shelf_up", bm, shelf.data.materials[0])
    world = sc.world
    bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is not None:
        bg.inputs["Color"].default_value = (0.36, 0.30, 0.24, 1)
        bg.inputs["Strength"].default_value = 0.35
    K.area_light("_key", (0.9, -0.5, 0.75), (0, 0, 0.03), 26, 0.8)
    K.area_light("_fill", (1.0, 0.8, 0.25), (0, 0, 0.03), 8, 1.2, color=(0.95, 0.9, 0.85))
    K.area_light("_strip", (xf - 0.03, 0, 0.395), (xf - 0.03, 0, 0), 14, 1.1, size_y=0.02, color=(1.0, 0.8, 0.55))
    cam = sc.camera
    cam.data.lens = 105
    cam.data.clip_start = 0.02
    target = Vector((0.0, 0.0, 0.045))
    cam.location = Vector((1.25, 0.40, 0.15))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


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
    only = os.environ.get("ONLY", "")
    out = lambda n: os.path.join(args.out, n)
    S.render_preview(ob, out("drone.png"), (1.0, -0.75, 0.7), args.samples, lens=60)

    def cm(p):
        return Vector(p) * K.CM - origin
    shots = {
        "front": dict(view_dir=(1.0, 0.0, 0.08), lens=60),
        "top": dict(view_dir=(0.001, 0.0, 1.0), lens=60),
        "close": dict(loc=cm((6.0, -0.3, 2.9)) + Vector((0.8, -0.55, 0.25)).normalized() * 0.2,
                      target=cm((6.0, -0.3, 2.9)), lens=60),
        "hinge": dict(loc=cm((5.0, -6.9, 6.4)) + Vector((0.35, -0.8, 0.5)).normalized() * 0.22,
                      target=cm((5.0, -6.9, 6.4)), lens=60),
    }
    if os.environ.get("DBG"):
        shots.update({"dbg_rear": dict(view_dir=(-1.0, 0.6, 0.45), lens=60),
                      "dbg_under": dict(view_dir=(0.3, -0.4, -0.6), lens=60),
                      "dbg_side": dict(view_dir=(0.0, -1.0, 0.1), lens=60)})
    for tag, kw in shots.items():
        if only and tag not in only.split(","):
            continue
        floor = bpy.data.objects.get("_floor")
        if floor is not None:
            floor.hide_render = tag == "dbg_under"
        K.shoot(ob, out(f"drone_{tag}.png"), **kw)
    if not only or "shelf" in only:
        shelf_shot(ob, out("drone_shelf.png"), args)


if __name__ == "__main__":
    main()
