"""iot_tray — the maker tray: a walnut display tray holding a single-board computer, a microcontroller
board and a half-size breadboard with three LEDs, all leaning back ~20 degrees against the tray's back.

Generic look-alikes only: no logos, brand names or printed text anywhere.
Tray 42 cm (Y) x 13 cm (X), front toward +X. Origin: bottom centre of the tray.

    blender -b --factory-startup -P films/host-studio/props/iot_tray.py -- --out films/host-studio/props/out
"""
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402

args = S.parse_args(__file__)
S.reset_scene()
rng = random.Random(13)


# ---------------------------------------------------------------- mesh helpers (this prop only)

def add_box(bm, lo, hi, m=None):
    lo, hi = Vector(lo), Vector(hi)
    mat = Matrix.Translation((lo + hi) / 2) @ Matrix.Diagonal((*(hi - lo), 1.0))
    bmesh.ops.create_cube(bm, size=1.0, matrix=(m @ mat) if m else mat)


def add_cyl(bm, p0, p1, r, segs=16, r2=None, m=None):
    f, length = S.frame_to(p0, p1)
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r,
                          radius2=r if r2 is None else r2, depth=length, matrix=(m @ f) if m else f)


def add_poly(bm, outline, z0, z1, m=None):
    """Extrude a simple 2D outline (convex or not) along local Z."""
    m = m or Matrix()
    a = [bm.verts.new(m @ Vector((x, y, z0))) for x, y in outline]
    b = [bm.verts.new(m @ Vector((x, y, z1))) for x, y in outline]
    n = len(outline)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(list(reversed(a)))
    bm.faces.new(b)


def add_lathe(bm, prof, m=None, segs=24, closed=False, slots=None):
    """Revolve (r, z) points around local Z (r == 0 is a pole); `slots(i)` = material of band i."""
    m = m or Matrix()
    rings = []
    for r, z in prof:
        if r <= 1e-9:
            rings.append([bm.verts.new(m @ Vector((0, 0, z)))])
        else:
            rings.append([bm.verts.new(m @ Vector((r * math.cos(2 * math.pi * k / segs),
                                                   r * math.sin(2 * math.pi * k / segs), z)))
                          for k in range(segs)])
    n = len(rings)
    for i in range(n if closed else n - 1):
        a, b = rings[i], rings[(i + 1) % n]
        for k in range(segs):
            k2 = (k + 1) % segs
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                vs = (a[0], b[k2], b[k])
            elif len(b) == 1:
                vs = (a[k], a[k2], b[0])
            else:
                vs = (a[k], a[k2], b[k2], b[k])
            f = bm.faces.new(vs)
            if slots:
                f.material_index = slots(i)


def add_tube(bm, pts, r, sides=10):
    """Round tube along a polyline (rotation-minimising frames), capped."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tans = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
    nrm = tans[0].orthogonal().normalized()
    rings = []
    for i in range(n):
        t = tans[i]
        nrm = (nrm - nrm.dot(t) * t).normalized()
        b = t.cross(nrm)
        rings.append([bm.verts.new(pts[i] + r * (math.cos(2 * math.pi * k / sides) * nrm
                                                 + math.sin(2 * math.pi * k / sides) * b))
                      for k in range(sides)])
    for i in range(n - 1):
        a, c = rings[i], rings[i + 1]
        for k in range(sides):
            k2 = (k + 1) % sides
            bm.faces.new((a[k], a[k2], c[k2], c[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def mk(name, bm, mats, bevel=None, segs=2, angle=35, cut=None, weight=False):
    """Object from a bmesh, with an optional boolean cut and bevel, modifiers applied (local space)."""
    if not isinstance(mats, (list, tuple)):
        mats = [mats]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for mt in mats:
        me.materials.append(mt)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    cutter = None
    if cut is not None:
        bmesh.ops.recalc_face_normals(cut, faces=cut.faces)
        cme = bpy.data.meshes.new(name + "_cut")
        cut.to_mesh(cme)
        cut.free()
        cme.materials.append(mats[0])      # cut faces take the part's own material, no empty slot
        cutter = bpy.data.objects.new(name + "_cut", cme)
        bpy.context.scene.collection.objects.link(cutter)
        cutter.hide_render = True
        mod = ob.modifiers.new("cut", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.use_self = True            # cutters may overlap each other
        mod.use_hole_tolerant = True
        mod.object = cutter
    if bevel:
        mod = ob.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = segs
        if weight:
            mod.limit_method = "WEIGHT"
        else:
            mod.limit_method = "ANGLE"
            mod.angle_limit = math.radians(angle)
    if ob.modifiers:
        dg = bpy.context.evaluated_depsgraph_get()
        new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        ob.modifiers.clear()
        old = ob.data
        ob.data = new
        bpy.data.meshes.remove(old)
        new.name = name
    if cutter is not None:
        cme = cutter.data
        bpy.data.objects.remove(cutter, do_unlink=True)
        bpy.data.meshes.remove(cme)
    return ob


def place(objs, m):
    for o in objs:
        o.matrix_world = m @ o.matrix_world


def box_uv(bm, grain=None):
    """World-scale box projection, 1 UV unit = 1 m; U runs along `grain` (0/1/2 = X/Y/Z) where it can."""
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        n = f.normal
        k = max(range(3), key=lambda i: abs(n[i]))
        a, b = [i for i in range(3) if i != k]
        if grain is not None and grain == b:
            a, b = b, a
        for loop in f.loops:
            co = loop.vert.co
            loop[uv].uv = (co[a], co[b])


def finalize(ob, grain=None):
    """Bake the object transform into the mesh, triangulate n-gons, add UVs."""
    me = ob.data
    me.transform(ob.matrix_world)
    ob.matrix_world = Matrix.Identity(4)
    bm = bmesh.new()
    bm.from_mesh(me)
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    if ngons:
        bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    box_uv(bm, grain)
    bm.to_mesh(me)
    bm.free()
    return ob


def wood(name, dark, light, rough, period=0.0035):
    """Walnut for the preview: grain bands run along U, so the preview shows the UV direction."""
    m = S.material(name, light, rough)
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.06, 1.0, 1.0)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Y"
    wave.inputs["Scale"].default_value = 0.314 / period
    wave.inputs["Distortion"].default_value = 9.0
    wave.inputs["Detail"].default_value = 3.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].color = (*light, 1)
    ramp.color_ramp.elements[0].position = 0.1
    ramp.color_ramp.elements[1].position = 0.9
    nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def led_mat(name, color):
    m = S.material(name, color, 0.25)
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    for key in ("Emission Color", "Emission"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = (*color, 1)
            break
    bsdf.inputs["Emission Strength"].default_value = 1.2
    return m


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- materials
WALNUT = wood("M_Walnut", (0.11, 0.052, 0.024), (0.19, 0.097, 0.048), 0.48, period=0.0022)
PCB_G = S.material("M_PcbGreen", (0.025, 0.14, 0.055), 0.32)
PCB_B = S.material("M_PcbBlue", (0.008, 0.06, 0.26), 0.32)
GOLD = S.material("M_Gold", (1.0, 0.74, 0.36), 0.22, metallic=1.0)
CHIP = S.material("M_ChipBlack", (0.018, 0.018, 0.02), 0.5)
LID = S.material("M_ChipLid", (0.62, 0.62, 0.64), 0.32, metallic=1.0)
PORT = S.material("M_PortMetal", (0.78, 0.78, 0.79), 0.26, metallic=1.0)
BREAD = S.material("M_Breadboard", (0.80, 0.80, 0.77), 0.5)
PRINT_R = S.material("M_PrintRed", (0.55, 0.03, 0.03), 0.6)
PRINT_B = S.material("M_PrintBlue", (0.02, 0.07, 0.45), 0.6)
CERAMIC = S.material("M_Ceramic", (0.42, 0.30, 0.17), 0.45)
RES = S.material("M_ResistorBody", (0.62, 0.50, 0.32), 0.45)
WIRES = {
    "red": S.material("M_WireRed", (0.55, 0.025, 0.02), 0.38),
    "black": S.material("M_WireBlack", (0.02, 0.02, 0.022), 0.38),
    "yellow": S.material("M_WireYellow", (0.78, 0.52, 0.02), 0.38),
    "blue": S.material("M_WireBlue", (0.02, 0.12, 0.58), 0.38),
}
LEDS = [led_mat("M_LedRed", (1.0, 0.04, 0.02)),
        led_mat("M_LedYellow", (1.0, 0.55, 0.02)),
        led_mat("M_LedGreen", (0.08, 1.0, 0.06))]

cm, mm = 0.01, 0.001


def scatter_smd(bms, rect, n, occupied, tall=0.0):
    """Tiny SMD resistors/capacitors in a rect (u0, v0, u1, v1), avoiding occupied footprints."""
    sizes = [(1.0, 0.5, 0.35), (1.6, 0.8, 0.45), (2.0, 1.25, 0.6)]
    placed = 0
    tries = 0
    while placed < n and tries < n * 60:
        tries += 1
        sx, sy, sz = rng.choice(sizes)
        if rng.random() < 0.5:
            sx, sy = sy, sx
        x = rng.uniform(rect[0] + sx, rect[2] - sx)
        y = rng.uniform(rect[1] + sy, rect[3] - sy)
        fp = (x - sx / 2, y - sy / 2, x + sx / 2, y + sy / 2)
        if any(fp[0] < o[2] + 0.35 and fp[2] > o[0] - 0.35 and fp[1] < o[3] + 0.35 and fp[3] > o[1] - 0.35
               for o in occupied):
            continue
        occupied.append(fp)
        which = "cap" if rng.random() < 0.62 else "res"
        add_box(bms[which], (fp[0], fp[1], tall - 0.05), (fp[2], fp[3], tall + sz))
        placed += 1


# ---------------------------------------------------------------- single-board computer (mm, flat)
def build_sbc():
    W, H, TH = 85.0, 56.0, 1.4
    out, occ = [], []

    def foot(u0, v0, u1, v1):
        occ.append((u0, v0, u1, v1))

    holes = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]
    bm = bmesh.new()
    add_poly(bm, [(x + W / 2, y + H / 2) for x, y in S.rounded_rect(W, H, 3.0, 5)], 0, TH)
    cut = bmesh.new()
    for x, y in holes:
        add_cyl(cut, (x, y, -1), (x, y, TH + 1), 1.375, 20)
        foot(x - 3.1, y - 3.1, x + 3.1, y + 3.1)
    out.append(mk("sbc_pcb", bm, PCB_G, bevel=0.25, segs=2, cut=cut))

    pads = bmesh.new()
    for x, y in holes:
        add_lathe(pads, [(1.45, TH - 0.1), (3.0, TH - 0.1), (3.0, TH + 0.3), (1.45, TH + 0.3)],
                  Matrix.Translation((x, y, 0)), segs=24, closed=True)
    out.append(mk("sbc_pads", pads, GOLD))

    # 2x20 pin header along the top edge
    hx, hy = 32.5, 52.5
    bm = bmesh.new()
    add_box(bm, (hx - 25.4, hy - 2.54, TH - 0.05), (hx + 25.4, hy + 2.54, TH + 2.5))
    out.append(mk("sbc_hdr", bm, CHIP, bevel=0.2))
    foot(hx - 25.4, hy - 2.54, hx + 25.4, hy + 2.54)
    pins = bmesh.new()
    for i in range(20):
        for j in (-1, 1):
            x, y = hx + (i - 9.5) * 2.54, hy + j * 1.27
            add_box(pins, (x - 0.32, y - 0.32, TH + 2.0), (x + 0.32, y + 0.32, TH + 8.5))
    # 2x2 power header
    for x, y in ((62.2, 45.0), (64.74, 45.0), (62.2, 47.54), (64.74, 47.54)):
        add_box(pins, (x - 0.32, y - 0.32, TH + 2.0), (x + 0.32, y + 0.32, TH + 8.5))
    out.append(mk("sbc_pins", pins, GOLD, bevel=0.1, segs=1))
    bm = bmesh.new()
    add_box(bm, (60.93, 43.73, TH - 0.05), (66.01, 48.81, TH + 2.5))
    out.append(mk("sbc_poe", bm, CHIP, bevel=0.2))
    foot(60.93, 43.73, 66.01, 48.81)

    # SoC with a silver lid, RAM, controller, PMIC, inductors
    bm = bmesh.new()
    add_box(bm, (21.5, 24.5, TH - 0.05), (36.5, 39.5, TH + 0.9))
    add_box(bm, (40.0, 28.25, TH - 0.05), (52.0, 37.75, TH + 1.1))
    add_box(bm, (56.5, 21.5, TH - 0.05), (63.5, 28.5, TH + 0.9))
    add_box(bm, (9.5, 19.5, TH - 0.05), (14.5, 24.5, TH + 0.9))
    out.append(mk("sbc_ics", bm, CHIP, bevel=0.15, segs=1))
    for r in ((21.5, 24.5, 36.5, 39.5), (40.0, 28.25, 52.0, 37.75), (56.5, 21.5, 63.5, 28.5),
              (9.5, 19.5, 14.5, 24.5)):
        foot(*r)
    bm = bmesh.new()
    add_poly(bm, [(x + 29.0, y + 32.0) for x, y in S.rounded_rect(12.4, 12.4, 1.2, 3)], TH + 0.85, TH + 1.75)
    out.append(mk("sbc_lid", bm, LID, bevel=0.25, segs=2))
    bm = bmesh.new()
    for x in (9.0, 14.0, 19.0):
        add_box(bm, (x - 2.0, 11.0, TH - 0.05), (x + 2.0, 15.0, TH + 2.0))
        foot(x - 2.0, 11.0, x + 2.0, 15.0)
    out.append(mk("sbc_ind", bm, CHIP, bevel=0.35, segs=2))

    # shielded radio module
    bm = bmesh.new()
    add_box(bm, (7.0, 36.0, TH - 0.05), (19.0, 47.0, TH + 1.6))
    out.append(mk("sbc_can", bm, PORT, bevel=0.3, segs=2))
    foot(7.0, 36.0, 19.0, 47.0)

    # flat-cable connectors (display along the left edge, camera near the bottom)
    bm = bmesh.new()
    add_box(bm, (1.6, 15.0, TH - 0.05), (5.0, 37.0, TH + 2.4))
    add_box(bm, (43.6, 3.0, TH - 0.05), (47.0, 25.0, TH + 2.4))
    out.append(mk("sbc_fpc", bm, CHIP, bevel=0.2))
    bm = bmesh.new()
    add_box(bm, (1.2, 15.3, TH + 2.35), (5.4, 36.7, TH + 2.9))
    add_box(bm, (43.2, 3.3, TH + 2.35), (47.4, 24.7, TH + 2.9))
    out.append(mk("sbc_fpc_latch", bm, CERAMIC, bevel=0.15))
    foot(1.2, 15.0, 5.4, 37.0)
    foot(43.2, 3.0, 47.4, 25.0)

    # two stacked USB-A blocks and an Ethernet jack on the right edge
    for vc in (29.0, 47.0):
        bm = bmesh.new()
        add_box(bm, (70.5, vc - 6.6, TH - 0.05), (87.5, vc + 6.6, TH + 16.0))
        cut = bmesh.new()
        for wc in (TH + 4.1, TH + 11.9):
            add_box(cut, (78.0, vc - 6.05, wc - 2.6), (89.0, vc + 6.05, wc + 2.6))
        out.append(mk("sbc_usb", bm, PORT, bevel=0.3, segs=2, cut=cut))
        bm = bmesh.new()
        for wc in (TH + 4.1, TH + 11.9):
            add_box(bm, (77.5, vc - 5.6, wc + 0.35), (86.8, vc + 5.6, wc + 2.15))
            add_box(bm, (77.5, vc - 6.1, wc - 2.65), (78.3, vc + 6.1, wc + 2.65))
        out.append(mk("sbc_usb_tongue", bm, CHIP, bevel=0.15))
        foot(70.5, vc - 6.6, 87.5, vc + 6.6)
    bm = bmesh.new()
    add_box(bm, (66.0, 2.25, TH - 0.05), (87.5, 18.25, TH + 13.5))
    cut = bmesh.new()
    add_box(cut, (75.0, 4.4, TH + 2.6), (88.5, 16.1, TH + 10.6))
    add_box(cut, (75.0, 7.6, TH + 1.2), (88.5, 12.9, TH + 3.0))      # latch slot
    out.append(mk("sbc_eth", bm, PORT, bevel=0.3, segs=2, cut=cut))
    bm = bmesh.new()
    add_box(bm, (74.5, 4.3, TH + 1.1), (75.6, 16.2, TH + 10.7))       # dark housing at the back
    out.append(mk("sbc_eth_in", bm, CHIP))
    bm = bmesh.new()
    for k in range(8):
        y = 10.25 + (k - 3.5) * 1.02
        add_box(bm, (75.5, y - 0.2, TH + 9.9), (84.0, y + 0.2, TH + 10.15))
    out.append(mk("sbc_eth_pins", bm, GOLD))
    foot(66.0, 2.25, 87.5, 18.25)

    # bottom edge: power (USB-C), two micro-HDMI, audio jack
    rot = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # local (x, y, z) -> (u, w, v)
    bm = bmesh.new()
    add_poly(bm, S.rounded_rect(9.0, 3.2, 1.5, 4), 0.25, 7.5, m=Matrix.Translation((11.2, 0, TH + 1.6)) @ rot)
    for uc in (26.0, 39.5):
        add_poly(bm, S.rounded_rect(6.5, 3.0, 0.6, 2), 0.25, 7.7, m=Matrix.Translation((uc, 0, TH + 1.5)) @ rot)
    out.append(mk("sbc_ports_b", bm, PORT, bevel=0.15))
    for r in ((6.7, 0.2, 15.7, 7.5), (22.75, 0.2, 29.25, 7.7), (36.25, 0.2, 42.75, 7.7)):
        foot(*r)
    bm = bmesh.new()
    add_box(bm, (50.5, 3.0, TH - 0.05), (56.5, 15.5, TH + 6.0))
    add_cyl(bm, (53.5, 0.3, TH + 3.0), (53.5, 3.2, TH + 3.0), 3.0, 24)
    cut = bmesh.new()
    add_cyl(cut, (53.5, -1.0, TH + 3.0), (53.5, 6.0, TH + 3.0), 1.75, 20)
    out.append(mk("sbc_audio", bm, CHIP, bevel=0.3, cut=cut))
    foot(50.3, 0.2, 56.7, 15.5)

    bms = {"cap": bmesh.new(), "res": bmesh.new()}
    scatter_smd(bms, (6.0, 6.0, 69.0, 49.0), 95, occ, tall=TH)
    out.append(mk("sbc_smd_c", bms["cap"], CERAMIC))
    out.append(mk("sbc_smd_r", bms["res"], CHIP))
    return out


# ---------------------------------------------------------------- microcontroller board (mm, flat)
def female_header(n, u0, vc, TH, name):
    bm = bmesh.new()
    add_box(bm, (u0, vc - 1.27, TH - 0.05), (u0 + n * 2.54, vc + 1.27, TH + 8.5))
    cut = bmesh.new()
    for i in range(n):
        uc = u0 + (i + 0.5) * 2.54
        add_box(cut, (uc - 0.5, vc - 0.5, TH + 4.0), (uc + 0.5, vc + 0.5, TH + 9.5))
    return mk(name, bm, CHIP, bevel=0.18, segs=2, cut=cut)


def build_mcu():
    W, H, TH = 68.6, 53.3, 1.6
    out, occ = [], []

    def foot(u0, v0, u1, v1):
        occ.append((u0, v0, u1, v1))

    outline = [(0.0, 0.0), (66.0, 0.0), (68.6, 2.6), (68.6, 37.9), (66.0, 40.5), (66.0, 51.8),
               (64.5, 53.3), (0.0, 53.3)]
    holes = [(14.0, 2.5), (15.3, 50.7), (66.1 - 1.2, 7.6), (66.1 - 1.2, 35.5)]
    bm = bmesh.new()
    add_poly(bm, outline, 0, TH)
    cut = bmesh.new()
    for x, y in holes:
        add_cyl(cut, (x, y, -1), (x, y, TH + 1), 1.6, 20)
        foot(x - 2.8, y - 2.8, x + 2.8, y + 2.8)
    out.append(mk("mcu_pcb", bm, PCB_B, bevel=0.3, segs=2, cut=cut))
    pads = bmesh.new()
    for x, y in holes:
        add_lathe(pads, [(1.7, TH - 0.1), (2.7, TH - 0.1), (2.7, TH + 0.3), (1.7, TH + 0.3)],
                  Matrix.Translation((x, y, 0)), segs=24, closed=True)
    out.append(mk("mcu_pads", pads, PORT))

    # female headers along both long edges
    for n, u0, vc in ((10, 18.0, 51.4), (8, 45.0, 51.4), (8, 26.6, 2.0), (6, 48.6, 2.0)):
        out.append(female_header(n, u0, vc, TH, "mcu_fhdr"))
        foot(u0, vc - 1.27, u0 + n * 2.54, vc + 1.27)

    # USB-B socket on the left edge
    bm = bmesh.new()
    add_box(bm, (-6.3, 32.1, TH - 0.05), (10.0, 44.1, TH + 10.9))
    rot = Matrix(((0, 0, 1, 0), (1, 0, 0, 38.1), (0, 1, 0, TH + 5.45), (0, 0, 0, 1)))  # (x,y,z)->(v,w,u)
    cut = bmesh.new()
    add_poly(cut, [(-4.2, -3.9), (4.2, -3.9), (4.2, 2.7), (3.0, 3.9), (-3.0, 3.9), (-4.2, 2.7)],
             -7.5, 1.8, m=rot)
    out.append(mk("mcu_usb", bm, PORT, bevel=0.35, segs=2, cut=cut))
    bm = bmesh.new()
    add_box(bm, (-5.2, 35.35, TH + 4.0), (2.0, 40.85, TH + 6.9))
    add_box(bm, (1.6, 33.6, TH + 1.3), (2.2, 42.6, TH + 9.6))
    out.append(mk("mcu_usb_in", bm, CHIP, bevel=0.15))
    foot(-6.3, 32.1, 10.0, 44.1)

    # barrel jack
    bm = bmesh.new()
    add_box(bm, (-1.8, 3.1, TH - 0.05), (12.4, 12.1, TH + 11.0))
    add_cyl(bm, (-2.6, 7.6, TH + 6.5), (0.0, 7.6, TH + 6.5), 4.3, 28)
    cut = bmesh.new()
    add_cyl(cut, (-4.0, 7.6, TH + 6.5), (9.0, 7.6, TH + 6.5), 3.15, 24)
    out.append(mk("mcu_jack", bm, CHIP, bevel=0.45, segs=2, cut=cut))
    bm = bmesh.new()
    add_cyl(bm, (0.2, 7.6, TH + 6.5), (9.2, 7.6, TH + 6.5), 1.0, 12)
    out.append(mk("mcu_jack_pin", bm, PORT))
    foot(-2.6, 3.1, 12.4, 12.1)

    # 28-pin DIP chip in a socket
    sc_u, sc_v = 46.5, 12.5
    bm = bmesh.new()
    add_box(bm, (sc_u - 18.0, sc_v - 5.0, TH - 0.05), (sc_u + 18.0, sc_v + 5.0, TH + 3.2))
    cut = bmesh.new()
    add_box(cut, (sc_u - 16.0, sc_v - 1.6, TH + 1.4), (sc_u + 16.0, sc_v + 1.6, TH + 4.0))
    for i in range(14):
        uc = sc_u + (i - 6.5) * 2.54
        for vv in (sc_v - 3.81, sc_v + 3.81):
            add_box(cut, (uc - 0.45, vv - 0.45, TH + 1.6), (uc + 0.45, vv + 0.45, TH + 4.0))
    out.append(mk("mcu_socket", bm, CHIP, bevel=0.25, segs=2, cut=cut))
    foot(sc_u - 18.0, sc_v - 5.0, sc_u + 18.0, sc_v + 5.0)
    w0, w1 = TH + 4.0, TH + 7.3
    bm = bmesh.new()
    add_box(bm, (sc_u - 17.8, sc_v - 3.25, w0), (sc_u + 17.8, sc_v + 3.25, w1))
    cut = bmesh.new()
    add_cyl(cut, (sc_u - 17.8, sc_v, w1 - 0.9), (sc_u - 17.8, sc_v, w1 + 1.0), 1.1, 20)
    add_cyl(cut, (sc_u - 14.8, sc_v - 1.6, w1 - 0.2), (sc_u - 14.8, sc_v - 1.6, w1 + 1.0), 0.65, 16)
    out.append(mk("mcu_dip", bm, CHIP, bevel=0.3, segs=2, cut=cut))
    legs = bmesh.new()
    for i in range(14):
        uc = sc_u + (i - 6.5) * 2.54
        for s in (-1, 1):
            vin, vout = sc_v + s * 3.2, sc_v + s * 3.95
            lo_v, hi_v = min(vin, vout), max(vin, vout)
            add_box(legs, (uc - 0.75, lo_v, w0 + 1.2), (uc + 0.75, hi_v, w0 + 1.45))
            vv = sc_v + s * 3.81
            add_box(legs, (uc - 0.75, vv - 0.14, w0 - 0.9), (uc + 0.75, vv + 0.14, w0 + 1.45))
            add_box(legs, (uc - 0.25, vv - 0.14, TH + 2.4), (uc + 0.25, vv + 0.14, w0 - 0.85))
    out.append(mk("mcu_dip_legs", legs, PORT))

    # crystal can
    bm = bmesh.new()
    add_poly(bm, [(x + 24.0, y + 21.0) for x, y in S.rounded_rect(4.65, 11.0, 2.3, 6)], TH + 0.4, TH + 3.9)
    out.append(mk("mcu_xtal", bm, PORT, bevel=0.4, segs=3))
    bm = bmesh.new()
    add_poly(bm, [(x + 24.0, y + 21.0) for x, y in S.rounded_rect(5.0, 11.4, 2.5, 6)], TH - 0.05, TH + 0.45)
    out.append(mk("mcu_xtal_base", bm, CHIP, bevel=0.15))
    foot(21.5, 15.3, 26.5, 26.7)

    # reset button
    bm = bmesh.new()
    add_box(bm, (5.0, 45.0, TH - 0.05), (11.0, 51.0, TH + 2.0))
    out.append(mk("mcu_btn_base", bm, CHIP, bevel=0.25))
    bm = bmesh.new()
    add_box(bm, (5.0, 45.0, TH + 1.95), (11.0, 51.0, TH + 2.3))
    out.append(mk("mcu_btn_plate", bm, PORT, bevel=0.1, segs=1))
    bm = bmesh.new()
    add_lathe(bm, [(0, TH + 2.25), (1.75, TH + 2.25), (1.75, TH + 3.3), (1.55, TH + 3.6), (0, TH + 3.62)],
              Matrix.Translation((8.0, 48.0, 0)), segs=24)
    out.append(mk("mcu_btn", bm, CHIP))
    foot(5.0, 45.0, 11.0, 51.0)

    # 2x3 programming headers (male)
    pins = bmesh.new()
    bm = bmesh.new()
    for cu, cv in ((63.0, 27.0), (14.5, 39.0)):
        add_box(bm, (cu - 2.54, cv - 3.81, TH - 0.05), (cu + 2.54, cv + 3.81, TH + 2.5))
        foot(cu - 2.54, cv - 3.81, cu + 2.54, cv + 3.81)
        for i in (-0.5, 0.5):
            for j in (-1, 0, 1):
                x, y = cu + i * 2.54, cv + j * 2.54
                add_box(pins, (x - 0.32, y - 0.32, TH + 2.0), (x + 0.32, y + 0.32, TH + 8.5))
    out.append(mk("mcu_icsp", bm, CHIP, bevel=0.2))
    out.append(mk("mcu_icsp_pins", pins, PORT, bevel=0.1, segs=1))

    # USB interface chip, regulator, electrolytic caps
    bm = bmesh.new()
    add_box(bm, (20.0, 35.5, TH - 0.05), (25.0, 40.5, TH + 0.9))
    add_box(bm, (15.5, 9.0, TH - 0.05), (22.0, 12.5, TH + 1.6))
    out.append(mk("mcu_ics", bm, CHIP, bevel=0.15, segs=1))
    foot(20.0, 35.5, 25.0, 40.5)
    foot(15.5, 7.0, 22.0, 14.0)
    bm = bmesh.new()
    add_box(bm, (17.0, 12.4, TH - 0.05), (20.5, 13.9, TH + 0.25))
    for x in (16.5, 18.75, 21.0):
        add_box(bm, (x - 0.35, 7.4, TH - 0.05), (x + 0.35, 9.1, TH + 0.25))
    out.append(mk("mcu_reg_tab", bm, PORT))
    bm = bmesh.new()
    can = bmesh.new()
    for cu, cv in ((14.5, 19.5), (14.5, 27.0)):
        add_poly(bm, [(cu + x, cv + y) for x, y in
                      [(-3.3, -3.3), (2.3, -3.3), (3.3, -2.3), (3.3, 2.3), (2.3, 3.3), (-3.3, 3.3)]],
                 TH - 0.05, TH + 1.0)
        add_lathe(can, [(0, TH + 0.95), (3.0, TH + 0.95), (3.1, TH + 1.5), (3.1, TH + 6.0),
                        (2.95, TH + 6.25), (0, TH + 6.3)], Matrix.Translation((cu, cv, 0)), segs=32)
        foot(cu - 3.3, cv - 3.3, cu + 3.3, cv + 3.3)
    out.append(mk("mcu_cap_base", bm, CHIP, bevel=0.2))
    out.append(mk("mcu_cap_can", can, PORT))

    bms = {"cap": bmesh.new(), "res": bmesh.new()}
    scatter_smd(bms, (3.0, 4.0, 66.0, 49.0), 55, occ, tall=TH)
    out.append(mk("mcu_smd_c", bms["cap"], CERAMIC))
    out.append(mk("mcu_smd_r", bms["res"], CHIP))
    return out


# ---------------------------------------------------------------- half-size breadboard (mm, flat)
BB_W, BB_H, BB_T = 82.0, 55.0, 8.5
P = 2.54
VC = BB_H / 2
COLS = {c: VC + s * (5.5 - i) * P for i, c in enumerate("abcde") for s in (-1,)}
COLS.update({c: VC + (1.5 + i) * P for i, c in enumerate("fghij")})
COLS.update({"T-": VC + 8 * P, "T+": VC + 9 * P, "B-": VC - 8 * P, "B+": VC - 9 * P})
STRIPES = [(VC + 6.75 * P, 2), (BB_H - 2.0, 1), (VC - 6.75 * P, 2), (2.0, 1)]   # (v, slot): blue inner, red outer
HOLE = 0.55


def row_u(r):
    return BB_W / 2 + (r - 14.5) * P


def rail_row(r):
    return r % 6 != 5


def hole(r, c):
    return Vector((row_u(r), COLS[c], BB_T))


def build_breadboard():
    out = []
    holes = [(row_u(r), v) for r in range(30) for c, v in COLS.items() if len(c) == 1]
    holes += [(row_u(r), COLS[c]) for r in range(30) if rail_row(r) for c in ("T-", "T+", "B-", "B+")]
    hole_set = set((round(u, 3), round(v, 3)) for u, v in holes)
    us = {0.0, BB_W, 1.6, BB_W - 1.6, 3.0, BB_W - 3.0}
    for r in range(30):
        us.update((row_u(r) - HOLE, row_u(r) + HOLE))
    vs = {0.0, BB_H, VC - 1.4, VC + 1.4}
    for v in COLS.values():
        vs.update((v - HOLE, v + HOLE))
    for v, _ in STRIPES:
        vs.update((v - 0.35, v + 0.35))
    us, vs = sorted(us), sorted(vs)

    bm = bmesh.new()
    grid = [[bm.verts.new((u, v, BB_T)) for v in vs] for u in us]
    hole_faces, chan_faces = [], []
    for i in range(len(us) - 1):
        for j in range(len(vs) - 1):
            f = bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
            uc, vc = (us[i] + us[i + 1]) / 2, (vs[j] + vs[j + 1]) / 2
            is_hole = any(abs(uc - hu) < HOLE and abs(vc - hv) < HOLE
                          for hu, hv in ((row_u(min(29, max(0, round((uc - BB_W / 2) / P + 14.5)))), v)
                                         for v in COLS.values())
                          if (round(hu, 3), round(hv, 3)) in hole_set)
            if is_hole:
                hole_faces.append(f)
            elif abs(vc - VC) < 1.4 and 1.6 < uc < BB_W - 1.6:
                chan_faces.append(f)
            else:
                for sv, slot in STRIPES:
                    if abs(vc - sv) < 0.35 and 3.0 < uc < BB_W - 3.0:
                        f.material_index = slot
    res = bmesh.ops.extrude_discrete_faces(bm, faces=hole_faces)
    for f in res["faces"]:
        c = f.calc_center_median()
        for v in f.verts:
            co = c + (v.co - c) * 0.7
            v.co = (co.x, co.y, BB_T - 2.6)
        f.material_index = 3
    res = bmesh.ops.extrude_face_region(bm, geom=chan_faces)
    for v in [e for e in res["geom"] if isinstance(e, bmesh.types.BMVert)]:
        v.co.z = BB_T - 3.2
    # walls and bottom
    top_border = [e for e in bm.edges if e.is_boundary]
    res = bmesh.ops.extrude_edge_only(bm, edges=top_border)
    new_verts = [e for e in res["geom"] if isinstance(e, bmesh.types.BMVert)]
    for v in new_verts:
        v.co.z = 0.0
    bottom_edges = [e for e in bm.edges if e.is_boundary]
    bmesh.ops.holes_fill(bm, edges=bottom_edges, sides=0)
    bw = bm.edges.layers.float.get("bevel_weight_edge") or bm.edges.layers.float.new("bevel_weight_edge")
    for e in bm.edges:
        a, b = e.verts
        on_rim = all(abs(v.co.z - BB_T) < 1e-6 or abs(v.co.z) < 1e-6 for v in (a, b))
        border = all(v.co.x < 1e-6 or v.co.x > BB_W - 1e-6 or v.co.y < 1e-6 or v.co.y > BB_H - 1e-6
                     for v in (a, b))
        same_z = abs(a.co.z - b.co.z) < 1e-6
        corner = all((v.co.x < 1e-6 or v.co.x > BB_W - 1e-6) and (v.co.y < 1e-6 or v.co.y > BB_H - 1e-6)
                     for v in (a, b))
        if (border and same_z and on_rim) or corner:
            e[bw] = 1.0
    out.append(mk("bb_body", bm, [BREAD, PRINT_R, PRINT_B, PORT], bevel=0.6, segs=3, weight=True))

    # ---- LEDs (anode row r, cathode row r + 1, column i), resistors to the top ground rail
    n = Vector((0, 0, 1))
    legs = bmesh.new()
    for k, r in enumerate((18, 22, 26)):
        a, c = hole(r, "i"), hole(r + 1, "i")
        base = (a + c) / 2 + n * 4.0
        for p in (a, c):
            add_cyl(legs, p - n * 2.0, Vector((p.x, p.y, base.z + 0.4)), 0.23, 6)
        bm = bmesh.new()
        add_lathe(bm, [(0, 0), (2.9, 0), (2.9, 1.0), (2.5, 1.05), (2.5, 5.9), (2.42, 6.6), (2.15, 7.35),
                       (1.65, 7.95), (0.9, 8.4), (0, 8.6)], Matrix.Translation(base), segs=28)
        out.append(mk(f"led_{k}", bm, LEDS[k]))
        # resistor: row r + 1 column j -> ground rail one row along
        p0, p1 = hole(r + 1, "j"), hole(r + 2, "T-")
        out += resistor(p0, p1, legs)
    out.append(mk("bb_legs", legs, PORT))

    # ---- jumper wires
    wires = {k: bmesh.new() for k in WIRES}
    tips = bmesh.new()
    for colour, a, b, h in (("red", (0, "B+"), (0, "T+"), 13.0),
                            ("black", (1, "B-"), (1, "T-"), 11.0),
                            ("yellow", (18, "f"), (8, "c"), 7.5),
                            ("blue", (22, "f"), (11, "c"), 8.0),
                            ("red", (26, "f"), (14, "c"), 8.5),
                            ("black", (2, "a"), (2, "B-"), 4.0)):
        A, B = hole(*a), hole(*b)
        d = B - A
        pts = [A + n * 0.6, A + n * 1.8 + d * 0.01, A + n * (h * 0.8) + d * 0.12, (A + B) / 2 + n * h,
               B + n * (h * 0.8) - d * 0.12, B + n * 1.8 - d * 0.01, B + n * 0.6]
        add_tube(wires[colour], S.catmull_rom(pts, 8), 0.65, sides=10)
        for p in (A, B):
            add_cyl(tips, p - n * 2.2, p + n * 1.0, 0.3, 8)
    for k, bmw in wires.items():
        if bmw.verts:
            out.append(mk(f"wire_{k}", bmw, WIRES[k]))
        else:
            bmw.free()
    out.append(mk("wire_tips", tips, PORT))
    return out


def resistor(p0, p1, legs):
    """Axial resistor with bent legs between two holes; colour bands as material bands."""
    n = Vector((0, 0, 1))
    L, hz = 3.6, 2.1
    d = Vector((p1.x - p0.x, p1.y - p0.y, 0))
    span = d.length
    d.normalize()
    mid = (p0 + p1) / 2 + n * hz
    e0, e1 = mid - d * (L / 2 - 0.05), mid + d * (L / 2 - 0.05)
    for p, e, s in ((p0, e0, 1), (p1, e1, -1)):
        pts = [p - n * 2.0, p + n * (hz - 0.7), p + n * hz + d * s * 0.55, e]
        add_tube(legs, S.catmull_rom(pts, 5), 0.24, sides=6)
    bands = [(0.42, 0.68, 1), (0.95, 1.2, 1), (1.45, 1.7, 2), (2.85, 3.1, 3)]   # red red black gold
    zs = sorted({0.0, 0.03, 0.09, 0.18, 0.3, L - 0.3, L - 0.18, L - 0.09, L - 0.03, L,
                 0.75, 1.05, L - 0.75, L - 1.05, L / 2} | {z for b in bands for z in b[:2]})

    def rad(z):
        t = min(z, L - z)
        r = 0.68 + 0.12 * (1 - smoothstep(0.7, 1.05, t))
        if t < 0.3:
            r *= math.sqrt(max(0.0, 1 - ((0.3 - t) / 0.3) ** 2))
        return r

    prof = [(rad(z), z) for z in zs]

    def slot(i):
        zm = (zs[i] + zs[i + 1]) / 2
        return next((b[2] for b in bands if b[0] <= zm <= b[1]), 0)

    bm = bmesh.new()
    frame, _ = S.frame_to(mid - d * L / 2, mid + d * L / 2)
    add_lathe(bm, prof, frame @ Matrix.Translation((0, 0, -L / 2)), segs=16, slots=slot)
    return [mk("resistor", bm, [RES, WIRES["red"], CHIP, GOLD])]


# ---------------------------------------------------------------- the walnut tray (cm)
T, L, D = 1.2, 42.0, 13.0
Y_IN = L / 2 - T - 0.01
A = math.radians(20.0)
sA, cA = math.sin(A), math.cos(A)
XI = -2.9           # foot of the back board's front face
LW = 7.0            # back board length up the slope
XZ = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # outline (x, z), extrude along y

tray = []
bm = bmesh.new()
add_box(bm, (-D / 2, -Y_IN, 0), (D / 2 - T - 0.01, Y_IN, T))
tray.append(mk("tray_base", bm, WALNUT, bevel=0.15, segs=3))
bm = bmesh.new()
add_box(bm, (D / 2 - T, -Y_IN, 0), (D / 2, Y_IN, 2.5))
tray.append(mk("tray_front", bm, WALNUT, bevel=0.15, segs=3))

d_up, n_out = Vector((-sA, cA)), Vector((-cA, -sA))
p1 = Vector((XI, T + 0.005))
p2 = p1 + d_up * LW
p3 = p2 + n_out * T
p4 = p3 - d_up * ((p3.y - p1.y) / cA)
bm = bmesh.new()
add_poly(bm, [tuple(p1), tuple(p2), tuple(p3), tuple(p4)], -Y_IN, Y_IN, m=XZ)
tray.append(mk("tray_back", bm, WALNUT, bevel=0.15, segs=3))


def cheek_outline():
    pts = [(D / 2, 0.0), (D / 2, 2.7)]
    xt, zt, r = -5.0, 8.8, 1.5
    n = 20
    for i in range(1, n + 1):
        t = i / n
        pts.append((D / 2 + (xt - D / 2) * t, 2.7 + (zt - 2.7) * t * t * (3 - 2 * t)))
    for i in range(1, 8):
        a = math.pi / 2 + (math.pi / 2) * i / 7
        pts.append((xt + r * math.cos(a), zt - r + r * math.sin(a)))
    pts.append((-D / 2, 0.0))
    return pts


cheeks = []
for s in (-1, 1):
    bm = bmesh.new()
    y0, y1 = sorted((s * (L / 2 - T), s * L / 2))
    add_poly(bm, cheek_outline(), y0, y1, m=XZ)
    cheeks.append(mk("tray_cheek", bm, WALNUT, bevel=0.15, segs=3))
for o in tray + cheeks:
    o.matrix_world = Matrix.Scale(cm, 4)

# ---------------------------------------------------------------- boards, leaning on the back board
O = Vector((XI, 0, T)) + 0.03 * Vector((cA, 0, sA))


def board_matrix(y0):
    return Matrix(((0, -sA, cA, O.x * cm), (1, 0, 0, y0 * cm), (0, cA, sA, O.z * cm + 0.0001),
                   (0, 0, 0, 1))) @ Matrix.Scale(mm, 4)


sbc = build_sbc()
place(sbc, board_matrix(-16.01))
mcu = build_mcu()
place(mcu, board_matrix(-2.87))
bb = build_breadboard()
place(bb, board_matrix(7.82))

parts = []
for o in tray:
    parts.append(finalize(o, grain=1))
for o in cheeks:
    parts.append(finalize(o, grain=0))
for o in sbc + mcu + bb:
    parts.append(finalize(o))

ob = S.finish("iot_tray", parts, origin=(0, 0, 0), view_dir=(1.0, -0.75, 0.6), args=args,
              sharp_angle=40, lens=60)


# ---------------------------------------------------------------- extra previews
def shoot(path, view_dir=None, lens=60, margin=1.08, loc=None, target=None):
    sc = bpy.context.scene
    cam = sc.camera
    cam.data.lens = lens
    if loc is not None:
        cam.location = Vector(loc)
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    else:
        v = Vector(view_dir).normalized()
        lo, hi = S.bbox(ob)
        centre = (lo + hi) / 2
        cam.rotation_euler = (-v).to_track_quat("-Z", "Y").to_euler()
        corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        dg = bpy.context.evaluated_depsgraph_get()
        co, _ = cam.camera_fit_coords(dg, [c for p in corners for c in p])
        cam.location = centre + (Vector(co) - centre) * margin
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


if not args.no_render:
    shoot(os.path.join(args.out, "iot_tray_front.png"), view_dir=(1.0, 0.0, 0.12), lens=60)
    target = Vector((0.0, 0.03, 0.04))
    shoot(os.path.join(args.out, "iot_tray_close.png"), lens=55,
          loc=target + Vector((1.0, -0.22, 0.42)).normalized() * 0.5, target=target)
    if os.environ.get("DBG"):
        for tag, y0, w, h in (("sbc", -16.01, 85, 56), ("mcu", -2.87, 68.6, 53.3), ("bb", 7.82, 82, 55)):
            c = board_matrix(y0) @ Vector((w / 2, h / 2, 5))
            for k, dv in enumerate(((1.0, -0.5, 0.5), (1.0, 0.6, 0.25))):
                shoot(os.path.join(args.out, f"dbg_{tag}{k}.png"), lens=50,
                      loc=c + Vector(dv).normalized() * 0.16, target=c)
