"""read3d: TRANSCRIPTION. Macro on one real handwritten page (assets/sheets/hires_38189_p02.jpg, a linear-algebra answer)
lying on a dark desk. A thin scan beam (accent emission) sweeps down the page; as it passes each handwritten line a
crisp typeset version of it (Inter, fg, a faint accent glow on its edges) lifts out of the paper and floats about 3 cm
above its source line. The camera starts low and close on the handwriting, then rises and pulls back to reveal the
layer of clean text hovering over the page.

Everything is deterministic (no random calls). The geometry helpers are numpy only; build() needs Blender.
"""
from __future__ import annotations

import math

import numpy as np

SHOT = {"frames": [1050, 1260], "look": [1050, 1085, 1120, 1160, 1200, 1259]}

PAGE_W = 0.210  # A4 sheet (m); height follows the scan's aspect
IMG_PX = (2392, 3517)
PAGE_H = PAGE_W * IMG_PX[1] / IMG_PX[0]
DISP = (1360.0, 2000.0)  # the coordinates the line table below was measured in (the scan shown at 1360 x 2000)
FONT = "/usr/share/fonts/opentype/inter/Inter-Regular.otf"

HOVER = 0.026  # how far above the paper the typeset layer floats (m)
UNDER = -0.003  # where a line waits: under the paper
BEAM_FRAMES = (1056, 1250)  # the beam enters above the page and leaves below it
BEAM_Y = (20.0, 2080.0)  # in display px
LIFT_FRAMES = 26
SHIFT = HOVER / math.tan(math.radians(58.0))  # the layer slides toward the camera as it rises, so from the closing
TOWARD = (0.087, -0.996)  # high view each line sits right over its source (in the page's frame)
EM_MAX, EM_MIN = 0.0078, 0.0042  # the typeset size range (m)

# --- the transcription: (text, x0, x1, y) for a line, ("row", [cells], [x centres], y) for a matrix row, in display px
LINES = [
    ("this is in the form of AX = B", 240, 835, 165),
    ("the Augmented matrix AB is", 275, 920, 222),
    ("AB =", 282, 375, 325),
    ("By using Elementary row operations we need", 250, 1185, 465),
    ("to reduce the matrix into Echelon form.", 240, 1050, 525),
    ("R1 ↔ R3", 465, 650, 580),
    ("=", 340, 360, 690),
    ("R2 → R2 − 2R1", 440, 655, 885),
    ("R3 → R3 − 3R1", 440, 670, 945),
    ("=", 335, 355, 1050),
]
MATRICES = [  # (rows, x centres of the four columns, y of each row, x of the brackets)
    ([["3", "1", "−1", "3"], ["2", "−8", "1", "−5"], ["1", "−2", "9", "8"]],
     [470, 535, 590, 655], [285, 340, 405], (400, 695)),
    ([["1", "−2", "9", "8"], ["2", "−8", "1", "−5"], ["3", "1", "−1", "3"]],
     [455, 520, 598, 665], [685, 745, 805], (380, 700)),
    ([["1", "−2", "9", "8"], ["0", "−4", "−17", "−21"], ["0", "7", "−28", "−21"]],
     [455, 525, 595, 665], [1045, 1105, 1170], (385, 715)),
    ([["1", "−2", "9", "8"], ["0", "−4", "−17", "−21"], ["0", "1", "−4", "−3"]],
     [450, 525, 600, 665], [1335, 1395, 1465], (385, 710)),
]


# ------------------------------------------------------------------------------------------------- pure helpers

def to_page(xd: float, yd: float) -> tuple[float, float]:
    """Display px (from the scan's top-left) to the page's own metres (centre origin, +y up the page)."""
    return (xd / DISP[0] - 0.5) * PAGE_W, (0.5 - yd / DISP[1]) * PAGE_H


def curl(x, y):
    """The page's lift (m): a gentle bow along its width, the top corners and the far edge a touch raised."""
    u, v = np.asarray(x) / (PAGE_W / 2), np.asarray(y) / (PAGE_H / 2)
    return 0.0004 + 0.0028 * u ** 2 * (0.5 + 0.5 * v) + 0.0016 * np.clip(v, 0, 1) ** 3 * u + 0.0012 * np.clip(-v, 0, 1) ** 2


def smooth(a: float, b: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def beam_y(frame: float) -> float:
    a, b = BEAM_FRAMES
    return BEAM_Y[0] + (BEAM_Y[1] - BEAM_Y[0]) * (frame - a) / (b - a)


def frame_for_y(yd: float) -> float:
    a, b = BEAM_FRAMES
    return a + (yd - BEAM_Y[0]) / (BEAM_Y[1] - BEAM_Y[0]) * (b - a)


def page_grid(nx: int = 70, ny: int = 100):
    """Vertices, faces, uvs of the curled page: a grid in the page's metres. The uvs inset the scan's grey borders."""
    xs, ys = np.linspace(-PAGE_W / 2, PAGE_W / 2, nx), np.linspace(PAGE_H / 2, -PAGE_H / 2, ny)
    X, Y = np.meshgrid(xs, ys)
    Z = curl(X, Y)
    verts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    ins = 0.012
    U, V = np.meshgrid(np.linspace(ins, 1 - ins, nx), np.linspace(1 - ins, ins, ny))
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(ny - 1)
             for i in range(nx - 1)]
    return verts, faces, np.column_stack([U.ravel(), V.ravel()])


# ------------------------------------------------------------------------------------------------- the shot

def build(ctx):
    import bpy
    from mathutils import Vector

    from lib import lights, materials, rig

    scene, coll = ctx.scene, ctx.scene.collection
    F0, F1 = ctx.f0 - 1, ctx.f1
    cy = scene.cycles
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 4, 2, 2
    cy.transmission_bounces, cy.transparent_max_bounces, cy.volume_bounces = 0, 4, 0
    cy.caustics_reflective = cy.caustics_refractive = False
    cy.sample_clamp_indirect = 6.0
    lin = materials.linear

    def link(ob, parent=None):
        coll.objects.link(ob)
        if parent is not None:
            ob.parent = parent
        return ob

    # the page rig: the whole sheet turns a few degrees on the desk, so nothing is square to the frame
    root = link(bpy.data.objects.new("page_root", None))
    root.rotation_euler = (0, 0, math.radians(-7.0))
    root.location = (0.0, 0.0, 0.0)

    # --- the paper: a curled slab, the real scan as its colour, warmed to the film's paper white
    verts, faces, uvs = page_grid()
    me = bpy.data.meshes.new("paper")
    me.from_pydata(verts.tolist(), [], faces)
    uvl = me.uv_layers.new(name="uv")
    for poly in me.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = uvs[me.loops[li].vertex_index]
    me.shade_smooth()
    mat = bpy.data.materials.new("paper")
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    img = bpy.data.images.load(str(ctx.film.path("assets/sheets/hires_38189_p02.jpg")))
    img.colorspace_settings.name = "sRGB"
    tex = N("ShaderNodeTexImage")
    tex.image, tex.interpolation, tex.extension = img, "Cubic", "EXTEND"
    warm = N("ShaderNodeMix")
    warm.data_type, warm.blend_type = "RGBA", "MULTIPLY"
    warm.inputs["Factor"].default_value = 1.0
    warm.inputs["B"].default_value = (*[c * 0.3 for c in lin("fg")], 1.0)
    L(tex.outputs["Color"], warm.inputs["A"])
    bs = N("ShaderNodeBsdfPrincipled")
    L(warm.outputs["Result"], bs.inputs["Base Color"])
    bs.inputs["Roughness"].default_value = 0.78
    bs.inputs["Sheen Weight"].default_value = 0.25
    bs.inputs["Sheen Roughness"].default_value = 0.5
    bs.inputs["Subsurface Weight"].default_value = 0.0
    out = N("ShaderNodeOutputMaterial")
    L(bs.outputs["BSDF"], out.inputs["Surface"])
    me.materials.append(mat)
    paper = link(bpy.data.objects.new("paper", me), root)
    sol = paper.modifiers.new("slab", "SOLIDIFY")
    sol.thickness, sol.offset = 0.00032, -1.0

    # --- the desk: a dark, finely uneven satin, wide enough that its edge is never seen
    dme = bpy.data.meshes.new("desk")
    s = 8.0
    dme.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    dm = bpy.data.materials.new("desk")
    dn = dm.node_tree
    dn.nodes.clear()
    DN, DL = dn.nodes.new, dn.links.new
    dbs = DN("ShaderNodeBsdfPrincipled")
    dbs.inputs["Base Color"].default_value = (*[c * 0.9 for c in lin("surface")], 1.0)
    dbs.inputs["Coat Weight"].default_value = 0.35
    dbs.inputs["Coat Roughness"].default_value = 0.25
    dnoise = DN("ShaderNodeTexNoise")
    dnoise.inputs["Scale"].default_value, dnoise.inputs["Detail"].default_value = 140.0, 2.0
    dramp = DN("ShaderNodeMapRange")
    dramp.inputs["To Min"].default_value, dramp.inputs["To Max"].default_value = 0.32, 0.62
    DL(dnoise.outputs["Fac"], dramp.inputs["Value"])
    DL(dramp.outputs["Result"], dbs.inputs["Roughness"])
    dout = DN("ShaderNodeOutputMaterial")
    DL(dbs.outputs["BSDF"], dout.inputs["Surface"])
    dme.materials.append(dm)
    desk = link(bpy.data.objects.new("desk", dme))
    desk.location.z = -0.0001

    # --- the typeset layer: one material, fg on its faces, a faint accent glow on its side walls (facing sideways)
    tm = bpy.data.materials.new("typeset")
    tn = tm.node_tree
    tn.nodes.clear()
    TN, TL = tn.nodes.new, tn.links.new
    tb = TN("ShaderNodeBsdfPrincipled")
    tb.inputs["Base Color"].default_value = (*lin("fg"), 1.0)
    tb.inputs["Roughness"].default_value = 0.3
    tb.inputs["Coat Weight"].default_value = 0.5
    geo = TN("ShaderNodeNewGeometry")
    dot = TN("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    dot.inputs[1].default_value = (0.0, 0.0, 1.0)
    TL(geo.outputs["Normal"], dot.inputs[0])
    ab = TN("ShaderNodeMath")
    ab.operation = "ABSOLUTE"
    TL(dot.outputs["Value"], ab.inputs[0])
    inv = TN("ShaderNodeMath")
    inv.operation, inv.use_clamp = "SUBTRACT", True
    inv.inputs[0].default_value = 1.0
    TL(ab.outputs["Value"], inv.inputs[1])
    sq = TN("ShaderNodeMath")
    sq.operation = "POWER"
    sq.inputs[1].default_value = 3.0
    TL(inv.outputs["Value"], sq.inputs[0])
    tb.inputs["Emission Color"].default_value = (*lin("accent"), 1.0)
    mulg = TN("ShaderNodeMath")
    mulg.operation = "MULTIPLY"
    mulg.inputs[1].default_value = 7.0
    TL(sq.outputs["Value"], mulg.inputs[0])
    TL(mulg.outputs["Value"], tb.inputs["Emission Strength"])
    tout = TN("ShaderNodeOutputMaterial")
    TL(tb.outputs["BSDF"], tout.inputs["Surface"])

    font = bpy.data.fonts.load(FONT)
    bpy.context.view_layer.update()

    def start_frame(yd: float) -> int:
        return int(round(frame_for_y(yd))) - 2

    def keyed_lift(ob, yd, delay=0):
        """Wait under the page, then rise to HOVER once the beam has passed the line."""
        f = start_frame(yd) + delay
        x0, y0 = ob.location.x, ob.location.y
        for fr, z, sc in ((F0, UNDER, 0.9), (f, UNDER, 0.9), (f + LIFT_FRAMES, HOVER, 1.0), (F1, HOVER + 0.002, 1.0)):
            k = (z - UNDER) / (HOVER - UNDER)
            ob.location = (x0 + TOWARD[0] * SHIFT * k, y0 + TOWARD[1] * SHIFT * k, z)
            ob.scale = (sc, sc, 1.0)
            ob.keyframe_insert("location", frame=fr)
            ob.keyframe_insert("scale", frame=fr)

    def text(body, x, y, size, align="LEFT"):
        cu = bpy.data.curves.new("t", "FONT")
        cu.body, cu.font, cu.size = body, font, size
        cu.align_x, cu.align_y = align, "CENTER"
        cu.extrude, cu.bevel_depth, cu.bevel_resolution, cu.resolution_u = 0.00055, 0.00003, 1, 4
        cu.materials.append(tm)
        ob = link(bpy.data.objects.new("t", cu), root)
        ob.location = (x, y, UNDER)
        return ob

    for body, x0, x1, yd in LINES:
        ax, ay = to_page(x0, yd)
        width = (x1 - x0) / DISP[0] * PAGE_W
        probe = text(body, ax, ay, 0.006)
        bpy.context.view_layer.update()
        fit = 0.006 * width / max(probe.dimensions.x, 1e-6)
        size = min(EM_MAX, max(EM_MIN, fit))
        probe.data.size = size
        keyed_lift(probe, yd)

    for rows, cols, ys, (bx0, bx1) in MATRICES:
        for r, yd in zip(rows, ys):
            for c, xd in zip(r, cols):
                ax, ay = to_page(xd, yd)
                ob = text(c, ax, ay, 0.0058, "CENTER")
                keyed_lift(ob, yd, delay=int(cols.index(xd)))
        # the brackets: thin extruded strokes, one mesh per matrix
        top, bot = to_page(0, ys[0] - 36)[1], to_page(0, ys[-1] + 36)[1]
        t, k, w = 0.00035, 0.0042, 0.0007
        quads = []
        for sgn, bxd in ((1, bx0), (-1, bx1)):
            bx = to_page(bxd, 0)[0]
            for (xa, ya, xb, yb) in ((bx, bot, bx + sgn * w, top), (bx, top, bx + sgn * k, top - w),
                                     (bx, bot + w, bx + sgn * k, bot)):
                quads.append((min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)))
        bv, bf = [], []
        for (xa, ya, xb, yb) in quads:
            i = len(bv)
            for z in (-t, t):
                bv += [(xa, ya, z), (xb, ya, z), (xb, yb, z), (xa, yb, z)]
            bf += [(i, i + 1, i + 2, i + 3), (i + 4, i + 7, i + 6, i + 5), (i, i + 4, i + 5, i + 1),
                   (i + 1, i + 5, i + 6, i + 2), (i + 2, i + 6, i + 7, i + 3), (i + 3, i + 7, i + 4, i)]
        bme = bpy.data.meshes.new("bracket")
        bme.from_pydata(bv, [], bf)
        bme.materials.append(tm)
        bob = link(bpy.data.objects.new("bracket", bme), root)
        keyed_lift(bob, ys[0] - 40)

    # --- the scan beam: a hot thin bar (accentBright) with a soft accent trail behind it and a light that washes the page
    beam = link(bpy.data.objects.new("beam", None), root)
    bz = 0.0032
    bw = PAGE_W * 1.03
    bar = bpy.data.meshes.new("bar")
    bar.from_pydata([(-bw / 2, -0.00035, 0), (bw / 2, -0.00035, 0), (bw / 2, 0.00035, 0), (-bw / 2, 0.00035, 0)], [],
                    [(0, 1, 2, 3)])
    bar.materials.append(materials.emission("accentBright", 9.0, name="beam_core"))
    link(bpy.data.objects.new("bar", bar), beam).location.z = bz
    tl = 0.034  # the trail's length behind the bar (toward the top of the page)
    tr = bpy.data.meshes.new("trail")
    tr.from_pydata([(-bw / 2, 0, 0), (bw / 2, 0, 0), (bw / 2, tl, 0), (-bw / 2, tl, 0)], [], [(0, 1, 2, 3)])
    uvt = tr.uv_layers.new(name="uv")
    for poly in tr.polygons:
        for li in poly.loop_indices:
            uvt.data[li].uv = [(0, 0), (1, 0), (1, 1), (0, 1)][list(poly.vertices).index(tr.loops[li].vertex_index)]
    trm = bpy.data.materials.new("beam_trail")
    rn = trm.node_tree
    rn.nodes.clear()
    RN, RL = rn.nodes.new, rn.links.new
    uvn = RN("ShaderNodeTexCoord")
    sep = RN("ShaderNodeSeparateXYZ")
    RL(uvn.outputs["UV"], sep.inputs["Vector"])
    fall = RN("ShaderNodeMath")
    fall.operation = "POWER"
    fall.inputs[1].default_value = 2.2
    inv2 = RN("ShaderNodeMath")
    inv2.operation = "SUBTRACT"
    inv2.inputs[0].default_value = 1.0
    RL(sep.outputs["Y"], inv2.inputs[1])
    RL(inv2.outputs["Value"], fall.inputs[0])
    em = RN("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*lin("accent"), 1.0)
    em.inputs["Strength"].default_value = 0.8
    tp = RN("ShaderNodeBsdfTransparent")
    mix = RN("ShaderNodeMixShader")
    RL(fall.outputs["Value"], mix.inputs["Fac"])
    RL(tp.outputs["BSDF"], mix.inputs[1])
    RL(em.outputs["Emission"], mix.inputs[2])
    mo = RN("ShaderNodeOutputMaterial")
    RL(mix.outputs["Shader"], mo.inputs["Surface"])
    tr.materials.append(trm)
    link(bpy.data.objects.new("trail", tr), beam).location.z = bz - 0.0003
    ld = bpy.data.lights.new("beam_light", "AREA")
    ld.shape, ld.size, ld.size_y, ld.energy = "RECTANGLE", PAGE_W * 1.0, 0.006, 0.05
    ld.color = lin("accent")
    bl = link(bpy.data.objects.new("beam_light", ld), beam)
    bl.location.z = bz + 0.002
    bl.rotation_euler = (0, 0, 0)  # area lights face -Z: straight down at the paper
    for fr in (F0, BEAM_FRAMES[0], BEAM_FRAMES[1], F1):
        yd = beam_y(min(max(fr, BEAM_FRAMES[0]), BEAM_FRAMES[1]))
        beam.location = (0.0, to_page(0, yd)[1], 0.0)
        beam.keyframe_insert("location", frame=fr)
    for fc in _fcurves(beam):
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"

    # --- the camera: low and close on the handwriting, then up and back to see the floating layer
    tgt = link(bpy.data.objects.new("focus", None))
    cam = rig.engine_camera("camera", fstop=2.0, size=ctx.size)
    cam.data.clip_start = 0.002
    con = cam.constraints.new("TRACK_TO")
    con.target, con.track_axis, con.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    cam.data.dof.focus_object = tgt
    rot = math.radians(-7.0)

    def world_of(px, py, pz):
        c, s_ = math.cos(rot), math.sin(rot)
        return (px * c - py * s_, px * s_ + py * c, pz)

    def orbit(tp, elev, dist, az):
        a, e = math.radians(az), math.radians(elev)
        return (tp[0] + dist * math.sin(a) * math.cos(e), tp[1] - dist * math.cos(a) * math.cos(e), tp[2] + dist * math.sin(e))

    # (frame, target in page metres (x, yd, z), elevation, distance, azimuth, fov, fstop)
    ks = [
        (F0, (560, 215, 0.0), 22.0, 0.150, -9.0, 22.0, 2.0),
        (1100, (570, 420, 0.006), 36.0, 0.24, -6.0, 24.0, 2.8),
        (1140, (590, 650, 0.010), 52.0, 0.40, -4.0, 23.0, 3.2),
        (1190, (640, 830, 0.013), 56.0, 0.66, -2.0, 21.0, 4.0),
        (F1, (650, 840, 0.013), 58.0, 0.70, -1.0, 21.0, 4.5),
    ]
    for fr, (tx, tyd, tz), elev, dist, az, fov, fs in ks:
        px, py = to_page(tx, tyd)
        tp = world_of(px, py, tz)
        tgt.location = tp
        tgt.keyframe_insert("location", frame=fr)
        cam.location = Vector(orbit(tp, elev, dist, az))
        cam.keyframe_insert("location", frame=fr)
        cam.data.lens = rig.lens_mm(fov)
        cam.data.keyframe_insert("lens", frame=fr)
        cam.data.dof.aperture_fstop = fs
        cam.data.dof.keyframe_insert("aperture_fstop", frame=fr)
    scene.camera = cam
    cy.denoising_prefilter = "FAST"
    cy.denoising_input_passes = "RGB_ALBEDO"

    # --- light: a soft warm key from the upper left, a magenta-indigo kicker from low right behind, a dim cool fill
    lights.world_color("bg", 0.25)
    centre = Vector(world_of(0.0, 0.0, 0.0))
    key = lights._light("key", "SPOT", 55.0, centre + Vector((-0.30, -0.34, 0.52)), centre + Vector((0.02, 0.05, 0)),
                        spot_size=0.95, soft=0.12, temperature=4700)
    key.data.spot_blend = 1.0
    lights._light("kick", "SPOT", 1.2, centre + Vector((0.45, 0.42, 0.10)), centre + Vector((0, 0.05, 0.03)),
                  spot_size=0.5, soft=0.02, temperature=7500)
    lights._light("fill", "AREA", 1.5, centre + Vector((0.5, -0.5, 0.2)), centre, size=0.8, temperature=7000)


def _fcurves(ob):
    act = ob.animation_data.action
    out = []
    if getattr(act, "layers", None):
        for layer in act.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    out.extend(bag.fcurves)
    elif hasattr(act, "fcurves"):
        out.extend(act.fcurves)
    return out
