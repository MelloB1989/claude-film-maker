"""smartwatch — a modern smartwatch on an olive/sage woven sport loop, closed round a 15 cm wrist.

Case: 41 x 35 x 10.7 mm rounded square (41 mm along the band), satin champagne-gold aluminium
(M_WatchCase), curved sides, a domed black-glass front (M_WatchGlass) over the display face
(M_Label_WatchFace, UV 0..1 over the visible screen) and an opaque black border under the glass and
the domed sensor back (M_WatchBlack). A knurled digital crown and a pill side button on the +Y side
(towards the hand), two speaker slots on the -Y side.

Band: a woven sport loop (M_WatchBand), 20 mm wide, 2.6 mm thick, from lug to lug round the wrist;
its tail comes back through a keeper on the +X side and lies over the band, ending in a pull tab.
The weave is left for a normal map: the band's UVs run U along the band, V across it, 1 UV unit = 1 m.

Axes: origin at the centre of the wrist loop; the wrist (forearm) runs along +Y (+Y = towards the
hand); the screen faces +Z. 12 o'clock is -X, so seen from the front (+X, above) the face is upright:
on the label, U runs to +Y (screen-right) and V to -X (up the face).
Inner loop: ~54 x 42 mm (X x Z), ~15 cm round.

    blender -b --factory-startup -P films/host-studio/props/smartwatch.py -- --out films/host-studio/props/out
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
import _accessories as A  # noqa: E402

MM = A.MM
args = A.parse_args(__file__)
S.reset_scene()

# --------------------------------------------------------------------------- materials
CASE = S.material("M_WatchCase", (0.74, 0.63, 0.48), 0.30, metallic=1.0)
SM.roughness_noise(CASE, 0.26, 0.36, scale=3000.0)
GLASS = SM.glassy(S.material("M_WatchGlass", (0.02, 0.02, 0.022), 0.02, specular=0.5), roughness=0.02, ior=1.76)
BLACK = S.material("M_WatchBlack", (0.010, 0.010, 0.011), 0.12, specular=0.5)
FACE = SM.label_material("M_Label_WatchFace")
BAND = S.material("M_WatchBand", (0.105, 0.125, 0.068), 0.92)


def weave_preview(m):
    """Preview only: a basket-weave bump and two-tone threads on the band's metre UVs."""
    nt = m.node_tree
    b = SM.principled(m)
    SM.set_input(b, ["Sheen Weight", "Sheen"], 0.3)
    SM.set_input(b, "Sheen Roughness", 0.5)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    pitch = 0.00055

    def sine(axis):
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = 2 * math.pi / pitch
        nt.links.new(sep.outputs[axis], mul.inputs[0])
        sn = nt.nodes.new("ShaderNodeMath")
        sn.operation = "SINE"
        nt.links.new(mul.outputs[0], sn.inputs[0])
        return sn
    su, sv = sine("X"), sine("Y")
    prod = nt.nodes.new("ShaderNodeMath")
    prod.operation = "MULTIPLY"
    nt.links.new(su.outputs[0], prod.inputs[0])
    nt.links.new(sv.outputs[0], prod.inputs[1])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.0002
    nt.links.new(prod.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (900.0, 6000.0, 1.0)     # streaky along the threads
    nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.40, (0.068, 0.082, 0.040, 1)
    els[1].position, els[1].color = 0.62, (0.165, 0.190, 0.110, 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])


weave_preview(BAND)

# --------------------------------------------------------------------------- dimensions (mm)
CL, CW = 41.0, 35.0           # case: along the band (X) x across (Y)
CR = 9.5                      # plan corner radius
CSEG = 10                     # segments per plan corner
ZB = 22.2                     # case back plane (the sensor dome below it touches the wrist at 20.9)
WRIST_A, WRIST_B = 27.0, 21.0  # inner loop half-extents (X, Z)
BAND_W, BAND_T = 20.0, 2.6
BAND_Z = ZB + 4.25            # the band's centreline where it leaves the case ends
HAND = +1                     # crown side: +Y


def ring_pts(inset, z):
    return [Vector((a, b, z)) for a, b in A.rrect(CL - 2 * inset, CW - 2 * inset, CR - inset, CSEG)]


def box_uv_bm(bm, slots=None):
    """Box projection in metres (bmesh in mm) on the faces whose slot is in `slots` (all if None)."""
    uvl = bm.loops.layers.uv.get("UVMap")
    for f in bm.faces:
        if slots is not None and f.material_index not in slots:
            continue
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        ua, va = [i for i in range(3) if i != ax]
        for loop in f.loops:
            loop[uvl].uv = (loop.vert.co[ua] * MM, loop.vert.co[va] * MM)


# --------------------------------------------------------------------------- case
# (inset from the 41 x 35 outline, z above the case back), from the back's inner edge round the
# curved side, over the lip that holds the glass, down to the black border under the glass.
CASE_PROFILE = [
    (4.0, 0.0), (2.4, 0.0), (1.55, 0.18), (0.88, 0.62), (0.40, 1.32), (0.11, 2.28), (0.0, 3.25),
    (0.0, 5.25), (0.10, 6.20), (0.32, 7.02), (0.64, 7.62), (0.98, 8.00), (1.20, 8.17), (1.34, 8.20),
    (1.42, 8.12), (1.50, 7.92), (1.60, 7.70),
]
SCREEN_INSET = 3.75           # visible display: 33.5 x 27.5 mm, corner radius 5.75
Z_FACE = 7.70                 # display plane (0.35 mm under the glass)

bm, uvl = A.new_bm()
rings = [[bm.verts.new(p) for p in ring_pts(i, ZB + z)] for i, z in CASE_PROFILE]
n = len(rings[0])
for a, b in zip(rings, rings[1:]):
    for k in range(n):
        k2 = (k + 1) % n
        bm.faces.new((a[k], a[k2], b[k2], b[k]))
bm.faces.new(list(reversed(rings[0])))                      # the back, inside the sensor ring
scr = [bm.verts.new(p) for p in ring_pts(SCREEN_INSET, ZB + Z_FACE)]
for k in range(n):
    k2 = (k + 1) % n
    f = bm.faces.new((rings[-1][k], rings[-1][k2], scr[k2], scr[k]))
    f.material_index = 1                                    # black border under the glass
disp = bm.faces.new(scr)
disp.material_index = 2
bm.normal_update()
box_uv_bm(bm, slots={0, 1})
sx0, sx1 = -(CL / 2 - SCREEN_INSET), CL / 2 - SCREEN_INSET
sy0, sy1 = -(CW / 2 - SCREEN_INSET), CW / 2 - SCREEN_INSET
for loop in disp.loops:
    co = loop.vert.co
    loop[uvl].uv = ((co.y - sy0) / (sy1 - sy0), (sx1 - co.x) / (sx1 - sx0))   # U -> +Y, V -> -X
FACE_SIZE = (sx1 - sx0, sy1 - sy0)
case = A.to_obj(bm, "case", [CASE, BLACK, FACE])

# speaker slots on the -Y side: cut 0.8 mm deep, the cut faces take the cutter's black
for i, xc in enumerate((-4.2, 4.2)):
    bm, uvl = A.new_bm()
    prof = A.rrect(7.0, 1.15, 0.574, 6)
    lo_r = [bm.verts.new((xc + a, -CW / 2 + 0.8, ZB + 4.25 + b)) for a, b in prof]
    hi_r = [bm.verts.new((xc + a, -CW / 2 - 1.5, ZB + 4.25 + b)) for a, b in prof]
    for k in range(len(prof)):
        k2 = (k + 1) % len(prof)
        bm.faces.new((lo_r[k], lo_r[k2], hi_r[k2], hi_r[k]))
    bm.faces.new(list(reversed(lo_r)))
    bm.faces.new(hi_r)
    bm.normal_update()
    box_uv_bm(bm)
    cutter = A.to_obj(bm, f"_slot{i}", [BLACK])
    mod = case.modifiers.new(f"slot{i}", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    try:
        mod.material_mode = "TRANSFER"
    except Exception:
        pass
    cutter.hide_render = cutter.hide_viewport = True
case = SM.bake(case)
for nm in ("_slot0", "_slot1"):
    bpy.data.objects.remove(bpy.data.objects[nm], do_unlink=True)

# --------------------------------------------------------------------------- glass
GLASS_PROFILE = [(1.50, 8.05), (1.52, 8.33), (1.68, 8.74), (2.08, 9.08), (2.75, 9.30), (3.55, 9.39), (4.6, 9.40)]
bm, uvl = A.new_bm()
rings = [[bm.verts.new(p) for p in ring_pts(i, ZB + z)] for i, z in GLASS_PROFILE]
for a, b in zip(rings, rings[1:]):
    for k in range(n):
        k2 = (k + 1) % n
        bm.faces.new((a[k], a[k2], b[k2], b[k]))
bm.faces.new(list(reversed(rings[0])))
bm.faces.new(rings[-1])
bm.normal_update()
box_uv_bm(bm)
glass = A.to_obj(bm, "glass", [GLASS])

# --------------------------------------------------------------------------- sensor dome (back)
DOME = [(0.0, -1.30), (2.5, -1.29), (5.0, -1.25), (7.2, -1.17), (7.35, -1.12), (7.5, -1.165),
        (9.2, -1.04), (10.6, -0.86), (11.45, -0.64), (11.85, -0.40), (12.0, -0.14), (12.0, 0.4), (0.0, 0.4)]
bm, uvl = A.new_bm()
SEGS_D = 64
rings = []
for r, z in DOME:
    if r < 1e-9:
        rings.append([bm.verts.new((0, 0, ZB + z))])
    else:
        rings.append([bm.verts.new((r * math.cos(A.TAU * k / SEGS_D), r * math.sin(A.TAU * k / SEGS_D), ZB + z))
                      for k in range(SEGS_D)])
for a, b in zip(rings, rings[1:]):
    for k in range(SEGS_D):
        k2 = (k + 1) % SEGS_D
        if len(a) == 1:
            bm.faces.new((a[0], b[k2], b[k]))
        elif len(b) == 1:
            bm.faces.new((a[k], a[k2], b[0]))
        else:
            bm.faces.new((a[k], a[k2], b[k2], b[k]))
bm.normal_update()
box_uv_bm(bm)
dome = A.to_obj(bm, "dome", [BLACK])


# --------------------------------------------------------------------------- crown and button
def lathe_y(name, prof, mat, centre, segs, knurl=None):
    """Revolve [(r, y)] about an axis along +Y through `centre` (x, z); knurl(i) -> ridge depth."""
    bm, uvl = A.new_bm()
    rings = []
    for i, (r, y) in enumerate(prof):
        if r < 1e-9:
            rings.append([bm.verts.new((centre[0], y, centre[1]))])
            continue
        d = knurl(i) if knurl else 0.0
        ring = []
        for k in range(segs):
            t = A.TAU * k / segs
            rr = r - d * (0.5 - 0.5 * math.cos(t * segs / 4))
            ring.append(bm.verts.new((centre[0] + rr * math.cos(t), y, centre[1] + rr * math.sin(t))))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for k in range(segs):
            k2 = (k + 1) % segs
            if len(a) == 1:
                bm.faces.new((a[0], b[k], b[k2]))
            elif len(b) == 1:
                bm.faces.new((a[k2], a[k], b[0]))
            else:
                bm.faces.new((a[k2], a[k], b[k], b[k2]))
    bm.normal_update()
    box_uv_bm(bm)
    return A.to_obj(bm, name, [mat])


CROWN_X, CROWN_Z = -6.2, ZB + 4.6
y0 = CW / 2
crown_prof = [(0.0, y0 - 1.5), (2.2, y0 - 1.5), (2.2, y0 + 0.55), (2.45, y0 + 0.62), (2.95, y0 + 0.72),
              (3.12, y0 + 0.88), (3.15, y0 + 1.05), (3.15, y0 + 2.70), (3.12, y0 + 2.88), (2.98, y0 + 3.02),
              (2.70, y0 + 3.10), (2.10, y0 + 3.14), (0.0, y0 + 3.16)]
KNURLED = {6, 7}
crown = lathe_y("crown", crown_prof, CASE, (CROWN_X, CROWN_Z), 120,
                knurl=lambda i: 0.14 if i in KNURLED else 0.0)

BTN_X, BTN_Z = 6.0, ZB + 4.25
bm, uvl = A.new_bm()
btn_rings = []
for inset, dy in ((0.0, -1.2), (0.0, 0.42), (0.05, 0.56), (0.17, 0.64), (0.35, 0.67)):
    btn_rings.append([bm.verts.new((BTN_X + a, y0 + dy, BTN_Z + b))
                      for a, b in A.rrect(11.0 - 2 * inset, 2.8 - 2 * inset, 1.4 - inset, 6)])
for a, b in zip(btn_rings, btn_rings[1:]):
    m_ = len(a)
    for k in range(m_):
        k2 = (k + 1) % m_
        bm.faces.new((a[k], a[k2], b[k2], b[k]))
bm.faces.new(btn_rings[0])
bm.faces.new(list(reversed(btn_rings[-1])))
bm.normal_update()
box_uv_bm(bm)
button = A.to_obj(bm, "button", [CASE])

# --------------------------------------------------------------------------- band path
ELL_A, ELL_B = WRIST_A + BAND_T / 2, WRIST_B + BAND_T / 2 + 0.5     # band centreline round the wrist
EXIT_X = CL / 2 + 1.0                                               # where the band leaves the lug connector
BEND_R = 4.0


def band_centreline():
    """Lug to lug: the convex hull of the wrist ellipse and the band's bend out of each case end,
    i.e. the band pulled snug round the wrist."""
    cloud = [(ELL_A * math.cos(t), ELL_B * math.sin(t)) for t in (A.TAU * k / 1440 for k in range(1440))]
    for sgn in (-1, 1):
        for k in range(31):
            al = math.radians(90 * k / 30)
            cloud.append((sgn * (EXIT_X + BEND_R * math.sin(al)), BAND_Z - BEND_R * (1 - math.cos(al))))
    pts = sorted(set(cloud))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]      # counter-clockwise in (x, z)
    # walk from the left exit, down, round the bottom, up to the right exit
    i0 = hull.index((-EXIT_X, BAND_Z))
    walk = hull[i0:] + hull[:i0]
    i1 = walk.index((EXIT_X, BAND_Z))
    chain = [(-EXIT_X + 6.0, BAND_Z)] + walk[:i1 + 1] + [(EXIT_X - 6.0, BAND_Z)]
    pts = A.resample([Vector((x, 0.0, z)) for x, z in chain], 0.9)
    for _ in range(6):                  # soften the hull's joins a little (ends fixed)
        pts = [pts[0]] + [(pts[i - 1] + 2 * pts[i] + pts[i + 1]) / 4 for i in range(1, len(pts) - 1)] + [pts[-1]]
    return pts


path = band_centreline()
Yv = Vector((0, 1, 0))
frames = []      # the path runs counter-clockwise in (x, z), so Y x tangent points away from the wrist
for i, p in enumerate(path):
    t = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
    frames.append((t, Yv.cross(t).normalized(), Yv))
assert frames[len(frames) // 2][1].z < 0

S_PATH = A.arc_len(path)
# the wrist the loop closes round snugly (band on its sides and underside, the sensor on top)
_h = ((WRIST_A - WRIST_B) / (WRIST_A + WRIST_B)) ** 2
print(f"smartwatch: wrist oval {2 * WRIST_A:.0f} x {2 * WRIST_B:.0f} mm, circumference "
      f"{math.pi * (WRIST_A + WRIST_B) * (1 + 3 * _h / (10 + math.sqrt(4 - 3 * _h))):.1f} mm")


def band_profile(w, t, crown=0.18, r=1.05, segs=4):
    """Cross-section [(radial, across)]: a rounded rectangle with a slightly crowned outer face."""
    pts = A.rrect(t, w, r, segs)          # first axis radial (thickness), second across (width)
    return [(a + (crown * (1 - (b / (w / 2)) ** 2) if a > 0 else 0.0), b) for a, b in pts]


PROF = band_profile(BAND_W, BAND_T)
band = A.tube("band", path, frames, lambda i: PROF, [BAND], caps=True)

# --------------------------------------------------------------------------- lug connectors
lugs = []
for sgn in (-1, 1):
    bm, uvl = A.new_bm()
    rr = []
    for dx, inset in ((-2.5, 0.0), (0.55, 0.0), (0.85, 0.12), (1.0, 0.35)):
        x = sgn * (CL / 2 + dx)
        rr.append([bm.verts.new((x, a, BAND_Z + b)) for a, b in A.rrect(BAND_W + 1.4 - 2 * inset, BAND_T + 0.8 - 2 * inset, 1.3 - inset, 4)])
    for a, b in zip(rr, rr[1:]):
        for k in range(len(a)):
            k2 = (k + 1) % len(a)
            bm.faces.new((a[k], a[k2], b[k2], b[k]))
    bm.faces.new(list(reversed(rr[0])))
    bm.faces.new(rr[-1])
    bm.normal_update()
    box_uv_bm(bm)
    lugs.append(A.to_obj(bm, f"lug{sgn}", [CASE]))

# --------------------------------------------------------------------------- keeper and tail (+X side)
def at_s(s):
    """Path point and frame at arc length s."""
    j = max(0, min(len(S_PATH) - 2, next(i for i in range(len(S_PATH) - 1) if S_PATH[i + 1] >= s)))
    f = (s - S_PATH[j]) / max(S_PATH[j + 1] - S_PATH[j], 1e-9)
    p = path[j].lerp(path[j + 1], f)
    t, nn, bb = frames[j]
    return p, t, nn


# keeper: where the band passes z = -3 on the +X side
s_keep = next(S_PATH[i] for i in range(len(path) // 2, len(path)) if path[i].x > 0 and path[i].z > -3.0)
KEEP_L = 4.2
TAIL_T = 2.0
TAIL_OFF = BAND_T / 2 + 0.25 + TAIL_T / 2          # tail centre, outward of the band's centreline
kp, kt, kn = at_s(s_keep)
inner_h = BAND_T + 0.25 + TAIL_T + 0.5            # opening, radially
inner_w = BAND_W + 0.6
k_mid = -BAND_T / 2 - 0.25 + inner_h / 2          # opening centre, radially from the centreline
WALL = 0.9
loop2d = A.rrect(inner_h + WALL, inner_w + WALL, 1.1 + WALL / 2, 5)   # wall centreline of the keeper
loop3d = [kp + (k_mid + a) * kn + b * Yv for a, b in loop2d]
kframes = []
m_ = len(loop3d)
for k in range(m_):
    t = (loop3d[(k + 1) % m_] - loop3d[k - 1]).normalized()
    kframes.append((t, kt, t.cross(kt)))
kprof = [(a, b) for a, b in A.rrect(KEEP_L, WALL, 0.42, 3)]
keeper = A.tube("keeper", loop3d, kframes, lambda i: kprof, [BAND], closed_path=True, caps=False)

# tail: from just below the keeper (the fold round the keeper's bar) up over the band, 26 mm long,
# the last 9 mm tapering into a rounded pull tab
S0 = s_keep - KEEP_L / 2 - 1.2
L_TAIL = 26.0
tail_pts, tail_frames, tail_s = [], [], []
N_T = 70
for i in range(N_T + 1):
    s = S0 + L_TAIL * i / N_T                    # the path runs from the -X lug to the +X lug: up the +X side
    p, t, nn = at_s(s)
    tail_pts.append(p + TAIL_OFF * nn)
    tail_frames.append((t, nn, Yv))
    tail_s.append(L_TAIL * i / N_T)


def tail_profile(i):
    s = tail_s[i]
    w, th = BAND_W - 0.4, TAIL_T
    if s < 1.2:                                  # the fold: a rounded nose
        q = math.sqrt(max(0.0, 1 - ((1.2 - s) / 1.25) ** 2))
        th = max(0.25, TAIL_T * q)
    tip = L_TAIL - s
    if tip < 9.0:                                # pull tab: narrows and rounds off
        q = tip / 9.0
        w = w * (0.62 + 0.38 * q ** 0.5)
        if tip < 3.0:
            w *= math.sqrt(max(0.0, 1 - ((3.0 - tip) / 3.05) ** 2)) * 0.9 + 0.1
        th = TAIL_T * (0.82 + 0.18 * q)
    return band_profile(w, th, crown=0.12, r=min(0.9, th / 2 - 0.05), segs=4)


print(f"smartwatch: keeper at s {s_keep:.1f} of {S_PATH[-1]:.1f} mm; tail ends at s {S0 + L_TAIL:.1f}")
tail = A.tube("tail", tail_pts, tail_frames, tail_profile, [BAND], caps=True)

# --------------------------------------------------------------------------- finish
ob = A.finish("smartwatch", [case, glass, dome, crown, button, band, lugs[0], lugs[1], keeper, tail],
              args, origin=(0, 0, 0), sharp_angle=45)
print(f"smartwatch: label M_Label_WatchFace {FACE_SIZE[1] / 10:.2f} cm wide (Y) x {FACE_SIZE[0] / 10:.2f} cm tall (X)")


# --------------------------------------------------------------------------- previews
def forearm():
    """A forearm stand-in along Y (preview only): the wrist's oval under the watch, wider and rounder
    toward the elbow, flattening into the back of the hand."""
    skin = A.skin_material()
    bm = bmesh.new()
    SEG = 64
    stations = [(-150, 31.5, 26.0, 2.2), (-90, 30.0, 24.0, 2.2), (-40, 28.0, 22.0, 2.1), (-12, 26.8, 20.8, 2.0),
                (12, 26.8, 20.8, 2.0), (32, 28.5, 18.5, 2.6), (55, 33.0, 14.5, 3.2), (78, 35.0, 12.5, 3.4),
                (88, 31.0, 10.0, 3.4), (94, 20.0, 6.0, 3.0), (96.5, 4.0, 2.0, 2.5)]
    rings = []
    for y, a, b, nexp in stations:
        rings.append([bm.verts.new(Vector(((a * math.copysign(abs(math.cos(t)) ** (2 / nexp), math.cos(t))),
                                            y, b * math.copysign(abs(math.sin(t)) ** (2 / nexp), math.sin(t)))))
                      for t in (A.TAU * k / SEG for k in range(SEG))])
    for a, b in zip(rings, rings[1:]):
        for k in range(SEG):
            k2 = (k + 1) % SEG
            bm.faces.new((a[k], a[k2], b[k2], b[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    for f in bm.faces:
        f.smooth = True
    arm = A.to_obj(bm, "_forearm", [skin])
    sub = arm.modifiers.new("sub", "SUBSURF")
    sub.levels = sub.render_levels = 1
    A.hide_stage()


lo, hi = S.bbox(ob)
V34 = (1.0, 0.8, 0.7)
if not args.no_render:
    A.render_views(ob, args.out, args.samples, [
        ("smartwatch.png", V34, 70, 1.12, None, None),
        ("smartwatch_front.png", (1.0, 0.0, 0.08), 70, 1.12, None, None),
        ("smartwatch_top.png", (0.18, 0.0, 1.0), 70, 1.05,
         (Vector((-0.024, -0.021, 0.02)), Vector((0.024, 0.021, 0.032))), None),
        ("smartwatch_close.png", (0.9, 1.0, 0.75), 60, 1.0,
         (Vector((-0.022, 0.005, 0.022)), Vector((0.0, 0.021, 0.032))), None),
    ] + ([  # review only (ACC_CHECK=1): the speaker side and the sensor back
        ("smartwatch_check_side.png", (-0.5, -1.0, 0.35), 70, 1.1, None, None),
        ("smartwatch_check_back.png", (0.3, -0.4, -1.0), 70, 1.1, None, A.hide_stage),
    ] if os.environ.get("ACC_CHECK") else []) + [
        ("smartwatch_wrist.png", (1.0, 0.55, 0.85), 60, 1.05,
         (Vector((-0.04, -0.07, -0.03)), Vector((0.04, 0.07, 0.04))), forearm),
    ])
