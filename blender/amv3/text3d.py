"""Timeless v3: 3D hero titles inside the stage (text3d).

`build(E, ctx)` adds every `style == "text3d"` title of edl.json TITLES as chunky extruded, bevelled letters (the user's
Novax look in 3D: white-to-hue gradient face with grunge, glossy coloured metal sides, a light sweep, settling to a
glowing outline), lit by their own light-linked lights, in perspective in the shot's home set.

Placement: a word is laid out in its shot's card frame (card-local x right, y up, +z toward the camera). `behind=True`
words live BEHIND the card plane (z < 0) and the shot's matte card (z = 0) holds them out, so the subject stays in
front for any camera move; a letter that flies forward through the card plane (fly-through exits) is in front of the
subject without any trick. Screen placement is given in pixels at the title's hero frame (STYLE below): the word is put
on the hero camera's ray through that pixel, `depth` metres behind the card plane, scaled to `width_px` on screen.

Teleports: when the camera jumps to another set inside a title's range (zt / text_fly cuts), the title continues as a
copy in the new set with the same camera-space pose at the jump (M_B = Cam_B @ Cam_A^-1 @ M_A), so the words keep
moving with the camera through the cut and then live in the new set (parallax with the new shot).

Passes: letters are in ctx.coll("text") (a sub-collection per title, which is also the lights' light-linking receiver
set); an emission-only twin of every letter (sweep + outline + pops) is in ctx.coll("light") for the glow pass.
Runs after the camera is keyed (stage core: text3d is built last), reads it with ctx.cam_matrix(f).
"""
import math
import os
import random
import subprocess

import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector

LENS_MM, SENSOR_MM, W_PX, H_PX = 35.0, 36.0, 1920, 1080
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
FONT_DIRS = [os.path.join(REPO, "films/timeless/fonts"), os.path.expanduser("~/.local/share/fonts"),
             "/usr/share/fonts", "/usr/local/share/fonts"]
FONTS = {  # key -> (file names to look for, fc-match pattern)
    "barlow": (["BarlowCondensed-BlackItalic.ttf"], "Barlow Condensed:style=Black Italic"),
    "anton": (["Anton-Regular.ttf"], "Anton"),
    "bebas": (["BebasNeue-Regular.ttf"], "Bebas Neue"),
    "rocks": (["chinese rocks rg.otf", "ChineseRocks.otf"], "Chinese Rocks"),
    "spiderman": (["Spider-Man.otf.ttf", "Spider-Man.otf"], "Spider\\-Man"),
    "exo": (["Exo2-BlackItalic.ttf"], "Exo 2:style=Black Italic"),
}

# Novax palettes in 3D. top/hue: face gradient (top -> bottom); edge: bevel metal; side: extrusion metal;
# glow: outline/pop emission; core: inside of chunks.
PAL = {
    "cyan_white": dict(top="#A8EAFF", hue="#0058DA", edge="#A8F2FF", side="#04234F", glow="#2FC8FF", core="#9FEFFF"),
    # REFS: eitaX SPIDER-MAN = red face, gold/cream bevelled extrusion (~15-20 % of cap height)
    "red_gold": dict(top="#FF4636", hue="#9E000C", edge="#FFE2A0", side="#C88A2E", glow="#FF3A1C", core="#FFD27A"),
    "crimson_white": dict(top="#FFFFFF", hue="#E8143E", edge="#FF6A86", side="#5E0016", glow="#FF1F4C", core="#FFC2CF"),
    "chrome": dict(top="#F4F7FF", hue="#9FB4D8", edge="#FFFFFF", side="#20283A", glow="#BFD4FF", core="#FFFFFF"),
}

# Per-title look and placement. center/width_px: screen pixels at `hero` (the frame the word is fully readable);
# depth: metres behind the card plane (behind=True); yaw/pitch/roll: degrees, the word's turn in its card frame
# (+yaw = right end recedes, +pitch = top recedes); ext/bev: extrusion half-depth and bevel in em.
STYLE = {
    "AMAZING": dict(font="barlow", center=(930, 330), width_px=1500, hero=328, depth=0.42, yaw=-16, pitch=10,
                    roll=-4, ext=0.13, bev=0.03, shear=0.0, track=0.04, hold=(321, 330)),
    # S25 is an extreme close-up: the subject matte covers ~the whole frame, so "behind" would hide the word. It sits
    # in front of the face (lower third, clear of the eye), behind the card plane only for parallax.
    "SPIDER-MAN": dict(behind=False, font="anton", center=(1000, 742), width_px=1540, hero=645, depth=0.30, yaw=14,
                       pitch=-8, roll=3, ext=0.12, bev=0.032, shear=0.18, track=0.03, hold=(632, 648)),
    "BRAND NEW DAY": dict(font="anton", center=(960, 250), width_px=1560, hero=758, depth=0.36, yaw=-12, pitch=12,
                          roll=-2, ext=0.12, bev=0.028, shear=0.18, track=0.05, shots=["S31", "S32"],
                          per_shot=dict(S31=dict(hero=755, center=(960, 250)), S32=dict(hero=772, center=(960, 290))),
                          sub=dict(font="barlow", dy_em=-0.95, scale=0.26, at=768),
                          hold=(768, 777), beats=[750.0, 751.0, 752.0, 753.0, 754.0, 755.5, 756.8, 758.0, 761.0, 763.0, 764.4]),
    "TIMELESS": dict(font="anton", center=(960, 548), width_px=1500, hero=806, depth=0.0, yaw=0, pitch=0, roll=0,
                     ext=0.11, bev=0.02, shear=0.0, track=0.06, chrome=True),
}
GAMMA = 2.2


# --------------------------------------------------------------------------------------------------------------------
# small helpers
def hexlin(h):
    h = h.lstrip("#")
    return tuple((int(h[i:i + 2], 16) / 255.0) ** GAMMA for i in (0, 2, 4))


def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def ease_out_expo(u):
    u = clamp01(u)
    return 1.0 if u >= 1 else 1.0 - 2.0 ** (-10.0 * u)


def ease_in_cubic(u):
    u = clamp01(u)
    return u * u * u


def ease_out_back(u, k=1.9):
    u = clamp01(u) - 1.0
    return 1.0 + (k + 1.0) * u ** 3 + k * u ** 2


def hermite(p0, v0, p1, v1, u, T):
    """cubic Hermite on [0, 1] with end velocities given per frame over a span of T frames"""
    u2, u3 = u * u, u * u * u
    return (p0 * (2 * u3 - 3 * u2 + 1) + v0 * T * (u3 - 2 * u2 + u) + p1 * (-2 * u3 + 3 * u2) + v1 * T * (u3 - u2))


def frange(a, b, step):
    n = int(round((b - a) / step))
    return [a + i * step for i in range(n + 1)]


def find_font(key):
    files, pattern = FONTS[key]
    for d in FONT_DIRS:
        for f in files:
            p = os.path.join(d, f)
            if os.path.exists(p):
                return p
    try:
        p = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True, timeout=10).stdout
        if p and os.path.exists(p):
            return p
    except Exception:
        pass
    raise FileNotFoundError(f"font {key} ({files}) not found")


# --------------------------------------------------------------------------------------------------------------------
# shader node helpers (a tiny expression builder)
class N:
    nt = None

    def __init__(self, sock):
        self.s = sock

    @staticmethod
    def wrap(x):
        if isinstance(x, N):
            return x.s
        v = N.nt.nodes.new("ShaderNodeValue")
        v.outputs[0].default_value = float(x)
        return v.outputs[0]

    def _op(self, op, other=None, rev=False):
        m = N.nt.nodes.new("ShaderNodeMath")
        m.operation = op
        a, b = (other, self) if rev else (self, other)
        N.nt.links.new(N.wrap(a), m.inputs[0])
        if other is not None:
            N.nt.links.new(N.wrap(b), m.inputs[1])
        return N(m.outputs[0])

    def __add__(self, o): return self._op("ADD", o)
    def __radd__(self, o): return self._op("ADD", o, True)
    def __sub__(self, o): return self._op("SUBTRACT", o)
    def __rsub__(self, o): return self._op("SUBTRACT", o, True)
    def __mul__(self, o): return self._op("MULTIPLY", o)
    def __rmul__(self, o): return self._op("MULTIPLY", o, True)
    def __truediv__(self, o): return self._op("DIVIDE", o)
    def __pow__(self, o): return self._op("POWER", o)


def nfn(op, a, b=None):
    m = N.nt.nodes.new("ShaderNodeMath")
    m.operation = op
    N.nt.links.new(N.wrap(a), m.inputs[0])
    if b is not None:
        N.nt.links.new(N.wrap(b), m.inputs[1])
    return N(m.outputs[0])


def nclamp(a):
    m = N.nt.nodes.new("ShaderNodeMath")
    m.operation = "ADD"
    m.use_clamp = True
    N.nt.links.new(N.wrap(a), m.inputs[0])
    m.inputs[1].default_value = 0.0
    return N(m.outputs[0])


def nsstep(x, e0, e1):
    """smoothstep from e0 to e1 (e0 > e1 allowed: falling)"""
    t = nclamp((x - e0) * (1.0 / (e1 - e0)))
    return t * t * (3.0 - t * 2.0)


def nmix(a, b, t):
    return a + (b - a) * t


def nsep(vec_sock):
    s = N.nt.nodes.new("ShaderNodeSeparateXYZ")
    N.nt.links.new(vec_sock, s.inputs[0])
    return N(s.outputs[0]), N(s.outputs[1]), N(s.outputs[2])


def nrgb(r, g, b):
    c = N.nt.nodes.new("ShaderNodeCombineColor")
    for i, x in enumerate((r, g, b)):
        N.nt.links.new(N.wrap(x), c.inputs[i])
    return c.outputs[0]


def ncol(rgb, k):
    """colour constant * scalar expression -> colour socket"""
    return nrgb(k * rgb[0], k * rgb[1], k * rgb[2])


def nattr(name, kind="GEOMETRY"):
    a = N.nt.nodes.new("ShaderNodeAttribute")
    a.attribute_type = kind
    a.attribute_name = name
    return N(a.outputs["Fac"])


def nvalue(name, v):
    n = N.nt.nodes.new("ShaderNodeValue")
    n.name = n.label = name
    n.outputs[0].default_value = v
    return N(n.outputs[0]), n


def caddc(a, b, op="ADD"):
    """colour (vector) add / multiply"""
    m = N.nt.nodes.new("ShaderNodeVectorMath")
    m.operation = op
    N.nt.links.new(a, m.inputs[0])
    N.nt.links.new(b, m.inputs[1])
    return m.outputs[0]


def principled(base_sock_or_rgb, metallic, rough, coat=0.0):
    p = N.nt.nodes.new("ShaderNodeBsdfPrincipled")
    if isinstance(base_sock_or_rgb, tuple):
        p.inputs["Base Color"].default_value = (*base_sock_or_rgb, 1)
    else:
        N.nt.links.new(base_sock_or_rgb, p.inputs["Base Color"])
    p.inputs["Metallic"].default_value = metallic
    N.nt.links.new(N.wrap(rough), p.inputs["Roughness"])
    p.inputs["Coat Weight"].default_value = coat
    return p.outputs[0]


def mixsh(a, b, fac):
    m = N.nt.nodes.new("ShaderNodeMixShader")
    N.nt.links.new(N.wrap(fac), m.inputs[0])
    N.nt.links.new(a, m.inputs[1])
    N.nt.links.new(b, m.inputs[2])
    return m.outputs[0]


def addsh(a, b):
    m = N.nt.nodes.new("ShaderNodeAddShader")
    N.nt.links.new(a, m.inputs[0])
    N.nt.links.new(b, m.inputs[1])
    return m.outputs[0]


def emission(col_sock, strength=1.0):
    e = N.nt.nodes.new("ShaderNodeEmission")
    N.nt.links.new(col_sock, e.inputs["Color"])
    e.inputs["Strength"].default_value = strength
    return e.outputs[0]


def matcap(nt_normal_sock):
    """view-space reflection -> a studio horizon (bright band, cool sky, dark floor): glossy metal that does not need
    a world to reflect (the stage's void is near black). Returns the intensity (scalar N, ~0..3)."""
    geo = N.nt.nodes.new("ShaderNodeNewGeometry")
    refl = N.nt.nodes.new("ShaderNodeVectorMath")
    refl.operation = "REFLECT"
    inv = N.nt.nodes.new("ShaderNodeVectorMath")
    inv.operation = "SCALE"
    N.nt.links.new(geo.outputs["Incoming"], inv.inputs[0])
    inv.inputs["Scale"].default_value = -1.0
    N.nt.links.new(inv.outputs[0], refl.inputs[0])
    N.nt.links.new(nt_normal_sock or geo.outputs["Normal"], refl.inputs[1])
    vt = N.nt.nodes.new("ShaderNodeVectorTransform")
    vt.vector_type = "VECTOR"
    vt.convert_from = "WORLD"
    vt.convert_to = "CAMERA"
    N.nt.links.new(refl.outputs[0], vt.inputs[0])
    rx, ry, _ = nsep(vt.outputs[0])
    band = nfn("EXPONENT", (ry - 0.08) * (ry - 0.08) * -90.0)            # hot horizon line
    sky = nsstep(ry, 0.0, 0.6) * 0.55 + 0.25
    floor = nsstep(ry, 0.05, -0.15)
    side = nfn("EXPONENT", (rx - 0.55) * (rx - 0.55) * -14.0) * 0.8       # a vertical softbox on the right
    return sky + (0.03 - sky) * floor + band * 2.4 + side


# --------------------------------------------------------------------------------------------------------------------
# materials
def title_material(name, pal, chrome=False):
    """returns (material, {param: Value node}) — params keyed per frame: face (face emission), rim (outline glow),
    sweep (sweep amplitude), pos (sweep position along the word, 0..1 = left..right). Per-object "t3d_pop" (custom
    prop) adds a glow pop on that letter."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    N.nt = nt
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    _, _, nz = nsep(tc.outputs["Normal"])                    # object space: +z = the face
    face = nsstep(nz, 0.90, 0.985)
    rim = nsstep(nz, 0.10, 0.40) * (1.0 - face)
    side = nclamp(1.0 - face - rim)
    wx, wy = nattr("wx"), nattr("wy")
    pop = nattr("t3d_pop", "OBJECT")
    P = {}
    face_e, P["face"] = nvalue("face", 1.0)
    rim_e, P["rim"] = nvalue("rim", 0.0)
    sweep_a, P["sweep"] = nvalue("sweep", 0.0)
    sweep_p, P["pos"] = nvalue("pos", -1.0)

    top, hue, edge, sidec, glow = (hexlin(pal[k]) for k in ("top", "hue", "edge", "side", "glow"))
    # face: white -> hue gradient, grunge
    grad = nsstep(wy, 0.10, 0.92) ** 0.8
    nz_tex = nt.nodes.new("ShaderNodeTexNoise")
    nz_tex.inputs["Scale"].default_value = 9.0
    nz_tex.inputs["Detail"].default_value = 8.0
    nz_tex.inputs["Roughness"].default_value = 0.65
    cvec = nrgb(wx * 6.0, wy * 1.6, 0.0)
    nt.links.new(cvec, nz_tex.inputs["Vector"])
    grunge = nsstep(N(nz_tex.outputs["Fac"]), 0.52, 0.70)
    scr = nt.nodes.new("ShaderNodeTexVoronoi")
    scr.feature = "DISTANCE_TO_EDGE"
    scr.inputs["Scale"].default_value = 22.0
    nt.links.new(nrgb(wx * 7.0, wy * 2.2, 0.0), scr.inputs["Vector"])
    cracks = nsstep(N(scr.outputs["Distance"]), 0.035, 0.0)
    dirt = nclamp(grunge * 0.6 + cracks * 0.7)
    shade = 1.0 - dirt * 0.7
    fr = (hue[0] + (top[0] - hue[0]) * grad) * shade
    fg = (hue[1] + (top[1] - hue[1]) * grad) * shade
    fb = (hue[2] + (top[2] - hue[2]) * grad) * shade
    face_col = nrgb(fr, fg, fb)
    mc = matcap(None)
    if chrome:
        # mirror chrome face (matcap), dark gunmetal sides, red/blue Spider-Verse rim like v2
        face_bsdf = principled((0.92, 0.94, 1.0), 1.0, 0.04)
        side_bsdf = principled((0.03, 0.035, 0.05), 0.6, 0.3)
        rim_bsdf = principled((1.0, 1.0, 1.0), 1.0, 0.08)
        lr = nsstep(wx, 0.2, 0.8)
        crim = nrgb(nmix(1.0, 0.10, lr), nmix(0.08, 0.32, lr), nmix(0.16, 1.0, lr))   # red left .. blue right
        face_emit = ncol((0.92, 0.95, 1.0), mc * face * face_e * (1.0 - dirt * 0.3) * 0.6)
        side_emit = ncol((0.35, 0.40, 0.55), mc * side * 0.35)
        rim_mul = nmix(1.0, mc, 0.6) * rim * rim_e
        rim_emit = caddc(ncol((1, 1, 1), mc * rim * 0.8), caddc(crim, nrgb(rim_mul, rim_mul, rim_mul), "MULTIPLY"))
    else:
        face_bsdf = principled(face_col, 0.0, nclamp(dirt * 0.4 + 0.22), coat=0.6)
        side_bsdf = principled(sidec, 0.85, 0.22)
        rim_bsdf = principled(edge, 1.0, 0.12)
        face_emit = caddc(nrgb(fr * face * face_e, fg * face * face_e, fb * face * face_e), ncol(edge, mc * face * 0.10))
        side_emit = ncol(tuple(min(1.0, c * 2.5 + 0.02) for c in sidec), mc * side * 0.6 + side * 0.04)
        rim_emit = caddc(ncol(glow, rim * rim_e), ncol(edge, mc * rim * 0.9))
    # light sweep: a slanted band travelling left -> right
    u = wx + wy * 0.32 - sweep_p
    band = nfn("EXPONENT", u * u * -420.0) + nfn("EXPONENT", u * u * -30.0) * 0.25
    sweep = band * sweep_a * (face + rim * 0.7 + side * 0.25)
    sweep_emit = ncol((1.0, 0.98, 0.94), sweep)
    pop_emit = ncol(glow, pop * (rim * 3.0 + face * 0.8 + side * 0.4))
    bsdf = mixsh(mixsh(side_bsdf, rim_bsdf, rim), face_bsdf, face)
    em = caddc(caddc(caddc(face_emit, side_emit), rim_emit), caddc(sweep_emit, pop_emit))
    nt.links.new(addsh(bsdf, emission(em)), out.inputs["Surface"])

    # light-pass twin: only the bright parts (sweep, outline glow, pops), black elsewhere
    ml = bpy.data.materials.new(name + "_light")
    ml.use_nodes = True
    N.nt = ml.node_tree
    N.nt.nodes.clear()
    out2 = N.nt.nodes.new("ShaderNodeOutputMaterial")
    tc2 = N.nt.nodes.new("ShaderNodeTexCoord")
    _, _, nz2 = nsep(tc2.outputs["Normal"])
    face2 = nsstep(nz2, 0.90, 0.985)
    rim2 = nsstep(nz2, 0.10, 0.40) * (1.0 - face2)
    wx2, wy2 = nattr("wx"), nattr("wy")
    pop2 = nattr("t3d_pop", "OBJECT")
    LP = {}
    rim_e2, LP["rim"] = nvalue("rim", 0.0)
    sweep_a2, LP["sweep"] = nvalue("sweep", 0.0)
    sweep_p2, LP["pos"] = nvalue("pos", -1.0)
    u2 = wx2 + wy2 * 0.32 - sweep_p2
    band2 = nfn("EXPONENT", u2 * u2 * -420.0) + nfn("EXPONENT", u2 * u2 * -30.0) * 0.25
    g = caddc(ncol((1.0, 0.98, 0.94), band2 * sweep_a2 * (face2 + rim2 * 0.7)),
              ncol(glow, rim2 * rim_e2 * 0.7 + pop2 * (rim2 * 3.0 + face2 * 0.8)))
    N.nt.links.new(emission(g), out2.inputs["Surface"])

    # core: the inside of chunks (hot palette glow)
    mcore = bpy.data.materials.new(name + "_core")
    mcore.use_nodes = True
    N.nt = mcore.node_tree
    bs = N.nt.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*hexlin(pal["side"]), 1)
    bs.inputs["Emission Color"].default_value = (*hexlin(pal["core"]), 1)
    bs.inputs["Emission Strength"].default_value = 2.5
    return m, ml, mcore, P, LP


# --------------------------------------------------------------------------------------------------------------------
# geometry
def _curve(body, font, ext, bev, shear, name):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = font
    cu.size = 1.0
    cu.align_x = "LEFT"
    cu.align_y = "BOTTOM_BASELINE"
    cu.extrude = ext
    cu.bevel_depth = bev
    cu.bevel_resolution = 3
    cu.resolution_u = 10
    cu.shear = shear
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _to_bmesh(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bm = bmesh.new()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    return bm


def word_glyphs(text, font_key, ext, bev, shear, track):
    """-> list of (char, bmesh in em units, x offset of the glyph's own origin) for the non-space chars. Positions come
    from the right edge of each prefix, so the font's kerning/advances are kept."""
    font = bpy.data.fonts.load(find_font(font_key), check_existing=True)
    out = []
    for i, ch in enumerate(text):
        if ch == " ":
            continue
        pre = _curve(text[:i + 1], font, ext, bev, shear, "t3d_probe")
        one = _curve(ch, font, ext, bev, shear, "t3d_glyph")
        bpy.context.view_layer.update()
        bp, bo = _to_bmesh(pre), _to_bmesh(one)
        right_pre = max(v.co.x for v in bp.verts)
        right_one = max(v.co.x for v in bo.verts)
        bp.free()
        for o in (pre, one):
            bpy.data.objects.remove(o)
        bmesh.ops.translate(bo, verts=bo.verts, vec=(right_pre - right_one + track * i, 0, 0))
        out.append((ch, bo))
    return out


def fracture(bm, n, rnd, cut_mat=1):
    """split a closed bmesh into ~n chunks by random planes; cut faces get material index cut_mat."""
    pieces = [bm]
    guard = 0
    while len(pieces) < n and guard < n * 4:
        guard += 1
        pieces.sort(key=lambda b: _bbox_vol(b))
        big = pieces.pop()
        lo, hi = _bbox(big)
        c = (lo + hi) * 0.5
        co = c + Vector(((rnd.random() - 0.5) * (hi.x - lo.x) * 0.5, (rnd.random() - 0.5) * (hi.y - lo.y) * 0.5, 0))
        no = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.35, 0.35))).normalized()
        halves = []
        for keep_outer in (True, False):
            b = big.copy()
            res = bmesh.ops.bisect_plane(b, geom=b.verts[:] + b.edges[:] + b.faces[:], dist=1e-6, plane_co=co,
                                         plane_no=no, clear_inner=keep_outer, clear_outer=not keep_outer)
            cut_edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
            if cut_edges:
                try:
                    tf = bmesh.ops.triangle_fill(b, use_beauty=True, use_dissolve=False, edges=cut_edges, normal=no)
                    for f in tf["geom"]:
                        if isinstance(f, bmesh.types.BMFace):
                            f.material_index = cut_mat
                except Exception:
                    pass
            if len(b.verts) >= 4:
                halves.append(b)
            else:
                b.free()
        if len(halves) == 2:
            big.free()
            pieces.extend(halves)
        else:
            for b in halves:
                b.free()
            pieces.append(big)
    return pieces


def _bbox(b):
    xs = [v.co.x for v in b.verts]
    ys = [v.co.y for v in b.verts]
    zs = [v.co.z for v in b.verts]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


def _bbox_vol(b):
    if not b.verts:
        return 0.0
    lo, hi = _bbox(b)
    d = hi - lo
    return d.x * d.y


def finish_mesh(bm, name, k, origin_em, word_lo, word_hi):
    """bmesh in em (word space) -> mesh in metres centred on its own bbox centre; wx/wy word attributes."""
    lo, hi = _bbox(bm)
    c = (lo + hi) * 0.5
    span = word_hi - word_lo
    wxs, wys = [], []
    for v in bm.verts:
        wxs.append((v.co.x - word_lo.x) / max(span.x, 1e-6))
        wys.append((v.co.y - word_lo.y) / max(span.y, 1e-6))
    for v in bm.verts:
        v.co = (v.co - c) * k
    bm.normal_update()
    flat = lambda f: abs(f.normal.z) > 0.995 or f.material_index != 0   # front/back caps and chunk cuts stay flat
    for f in bm.faces:
        f.smooth = not flat(f)
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) == 2:
            e.smooth = (flat(lf[0]) == flat(lf[1])) and lf[0].normal.angle(lf[1].normal, 0.0) < math.radians(38)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    for nm, vals in (("wx", wxs), ("wy", wys)):
        a = me.attributes.new(nm, "FLOAT", "POINT")
        a.data.foreach_set("value", vals)
    return me, (c - origin_em) * k


def glow_collection(ctx):
    """T3D_glow under the light collection, excluded from every view layer except the light pass (the plate pass also
    renders the light collection, where the letters' glow twins must not appear)."""
    c = bpy.data.collections.get("T3D_glow")
    if c is not None:
        return c
    c = bpy.data.collections.new("T3D_glow")
    ctx.coll("light").children.link(c)
    layers = getattr(ctx, "layers", None) or {vl.name: vl for vl in bpy.context.scene.view_layers}
    for name, vl in layers.items():
        if name == "light":
            continue
        lc = _find_lc(vl.layer_collection, c.name)
        if lc is not None:
            lc.exclude = True
    return c


def _find_lc(lc, name):
    if lc.collection.name == name:
        return lc
    for ch in lc.children:
        r = _find_lc(ch, name)
        if r is not None:
            return r
    return None


# --------------------------------------------------------------------------------------------------------------------
# the title
class Title:
    def __init__(self, T, E, ctx):
        self.T, self.E, self.ctx = T, E, ctx
        self.id = T["id"]
        self.st = dict(STYLE.get(self.id, STYLE["AMAZING"]))
        self.pal = PAL[T.get("palette", "cyan_white")]
        self.f0, self.f1 = float(T["f"]), float(T["f1"])
        self.rnd = random.Random(sum(map(ord, self.id)))
        self.exit = None
        if T.get("exit"):
            kind, at = T["exit"].split("@")
            self.exit = (kind, float(at))
        self.behind = bool(self.st.get("behind", T.get("behind")))
        self.shots = self.st.get("shots") or ([T["shot"]] if T.get("shot") else [])
        self.hero = float(self.st.get("hero", self.f0 + 10))

    # ---------------------------------------------------------------------------- camera
    def cam(self, f):
        if hasattr(self.ctx, "cam_matrix"):
            return self.ctx.cam_matrix(f)
        return bpy.context.scene.camera.matrix_world.copy()

    def lens(self, f):
        if hasattr(self.ctx, "cam_lens"):
            return self.ctx.cam_lens(f)
        return LENS_MM

    def teleports(self):
        tps = list(getattr(self.ctx, "teleports", []) or [])
        a, b = self.f0 - 1.0, self.end_frame() + 1.0
        return [t for t in tps if a < t < b]

    def end_frame(self):
        if self.exit and self.exit[0] == "shatter":
            return self.exit[1] + 9.0
        return self.f1

    # ---------------------------------------------------------------------------- placement
    def word_frame(self, width_em, height_em, shot=None, hero=None, center=None):
        """-> (world matrix of the word centre, metres per em). x = reading direction, y = up, +z toward camera."""
        st = self.st
        shot = shot or (self.shots[0] if self.shots else None)
        hero = self.hero if hero is None else hero
        anchor = bpy.data.objects.get("TRIPTYCH_TITLE") if self.id == "TIMELESS" else None
        if anchor is not None:
            Mw = anchor.matrix_world.normalized()
            width_m = float(anchor.get("width", 1.5))
            self.ctx.log(f"text3d {self.id}: on TRIPTYCH_TITLE, {width_m:.2f} m")
            return Mw, width_m / width_em
        C = self.cam(hero)
        lens = self.lens(hero)
        px, py = center or st["center"]
        d_cam = Vector(((px - W_PX / 2) / W_PX * SENSOR_MM / lens, (H_PX / 2 - py) / W_PX * SENSOR_MM / lens, -1.0))
        o = C.translation
        ray = (C.to_3x3() @ d_cam)
        if shot:
            card = self.ctx.card(shot)
            Mc = card.matrix_world.normalized()
            nrm = (Mc.to_3x3() @ Vector((0, 0, 1))).normalized()
            p_plane = Mc.translation - nrm * st["depth"]
            t = (p_plane - o).dot(nrm) / ray.dot(nrm)
            centre = o + ray * t
            base = Mc.to_3x3().to_4x4()
        else:
            dist = 1.6
            centre = o + ray.normalized() * dist
            t = dist / ray.length
            base = C.to_3x3().to_4x4()
        dist_axis = t  # ray has unit z in camera space, so t = depth along the view axis
        width_m = st["width_px"] / W_PX * SENSOR_MM / lens * dist_axis
        rot = (Matrix.Rotation(math.radians(st.get("roll", 0)), 4, "Z") @
               Matrix.Rotation(math.radians(st.get("yaw", 0)), 4, "Y") @      # +yaw: +x goes to -z (recedes)
               Matrix.Rotation(math.radians(-st.get("pitch", 0)), 4, "X"))    # +pitch: top recedes
        M = Matrix.Translation(centre) @ base @ rot
        return M, width_m / width_em

    # ---------------------------------------------------------------------------- build
    def build(self):
        ctx, st = self.ctx, self.st
        text = self.T["text"]
        glyphs = word_glyphs(text, st["font"], st["ext"], st["bev"], st["shear"], st.get("track", 0.0))
        lo = Vector((1e9, 1e9, 1e9))
        hi = -lo
        for _, b in glyphs:
            l, h = _bbox(b)
            lo = Vector(map(min, lo, l))
            hi = Vector(map(max, hi, h))
        origin_em = (lo + hi) * 0.5
        self.Mw, k = self.word_frame(hi.x - lo.x, hi.y - lo.y)
        self.k, self.width_m, self.height_m = k, (hi.x - lo.x) * k, (hi.y - lo.y) * k
        # per_shot: the word lives in each shot's own set (placed at that shot's hero frame) and switches at the cut
        self.shot_frames = None
        if st.get("per_shot"):
            self.shot_frames = []
            for sid in self.shots:
                ps = st["per_shot"][sid]
                M_i, k_i = self.word_frame(hi.x - lo.x, hi.y - lo.y, shot=sid, hero=ps["hero"], center=ps["center"])
                self.shot_frames.append((sid, M_i @ Matrix.Scale(k_i / k, 4)))
            self.Mw = self.shot_frames[0][1]
        ctx.log(f"text3d {self.id}: {len(glyphs)} glyphs, word {self.width_m:.2f} x {self.height_m:.2f} m")

        self.coll = bpy.data.collections.new(f"T3D_{self.id}")
        ctx.coll("text").children.link(self.coll)
        self.glow_coll = glow_collection(ctx)
        self.mat, self.mat_l, self.mat_core, self.P, self.LP = title_material(f"t3d_{self.id}", self.pal,
                                                                              chrome=bool(st.get("chrome")))
        self.letters = []
        n_ch = len(glyphs)
        for i, (ch, bm) in enumerate(glyphs):
            chunks = None
            if self.exit and self.exit[0] == "shatter":
                chunks = fracture(bm.copy(), 9, self.rnd)
            me, c = finish_mesh(bm, f"t3d_{self.id}_{i}_{ch}", k, origin_em, lo, hi)
            bm.free()
            L = dict(ch=ch, i=i, mesh=me, rest=c, order=i, n=n_ch, rnd=random.Random(self.rnd.random()))
            if chunks:
                L["chunks"] = []
                for j, cb in enumerate(chunks):
                    cme, cc = finish_mesh(cb, f"t3d_{self.id}_{i}_c{j}", k, origin_em, lo, hi)
                    cb.free()
                    L["chunks"].append(dict(mesh=cme, rest=cc, rnd=random.Random(self.rnd.random())))
            self.letters.append(L)
        if st.get("sub") and self.T.get("sub"):
            self.build_sub(origin_em, lo, hi)
        for me in self.meshes():
            me.materials.append(self.mat)
            me.materials.append(self.mat_core)
        self.lights()
        self.animate()
        self.key_hold_focus()
        if self.behind:
            for sid in self.shots:
                ctx.matte_card(sid)
        ctx.log(f"text3d {self.id}: done, {len(self.coll.all_objects)} objects")

    def meshes(self):
        for L in self.letters:
            yield L["mesh"]
            for c in L.get("chunks", []):
                yield c["mesh"]

    def build_sub(self, origin_em, lo, hi):
        sub = self.st["sub"]
        gl = word_glyphs(self.T["sub"], sub["font"], 0.08, 0.012, 0.0, 0.12)
        slo = Vector((1e9, 1e9, 1e9))
        shi = -slo
        for _, b in gl:
            l, h = _bbox(b)
            slo, shi = Vector(map(min, slo, l)), Vector(map(max, shi, h))
        bm = bmesh.new()
        for _, b in gl:
            me = bpy.data.meshes.new("tmp")
            b.to_mesh(me)
            bm.from_mesh(me)
            bpy.data.meshes.remove(me)
            b.free()
        # scale the sub line to sub.scale of the main word's height, put it under the word, right-aligned-ish
        s = sub["scale"] * (hi.y - lo.y) / (shi.y - slo.y)
        sc = (slo + shi) * 0.5
        for v in bm.verts:
            v.co = (v.co - sc) * s
        y = (lo.y - origin_em.y) + sub["dy_em"] * 0.18 - (shi.y - slo.y) * s * 0.5
        bmesh.ops.translate(bm, verts=bm.verts, vec=(origin_em.x + (hi.x - lo.x) * 0.18, origin_em.y + y, 0))
        me, c = finish_mesh(bm, f"t3d_{self.id}_sub", self.k, origin_em, lo, hi)
        bm.free()
        self.letters.append(dict(ch="SUB", i=len(self.letters), mesh=me, rest=c, order=len(self.letters),
                                 n=len(self.letters) + 1, rnd=random.Random(5), sub=True))

    # ---------------------------------------------------------------------------- lights
    def lights(self):
        W = self.width_m
        act = self.act_palette()
        key = act.get("key", (1.0, 0.95, 0.9))
        specs = [  # name, word-space position (in word widths), colour, power W per (m of word width)^2, size
            ("key", (-0.55, 0.65, 1.1), tuple(0.6 + 0.4 * c for c in key), 90.0, 0.8),
            ("rim", (0.75, 0.45, -0.55), hexlin(self.pal["glow"]), 260.0, 0.6),
            ("under", (0.1, -0.8, 0.45), hexlin(self.pal["hue"]), 90.0, 0.9),
        ]
        if self.st.get("chrome"):
            specs[1] = ("rim", (-0.9, 0.3, -0.5), (1.0, 0.1, 0.18), 300.0, 0.6)
            specs.append(("rim2", (0.9, -0.2, -0.5), (0.1, 0.3, 1.0), 300.0, 0.6))
        self.light_obs = []
        for name, p, col, pw, size in specs:
            ld = bpy.data.lights.new(f"t3d_{self.id}_{name}", "AREA")
            ld.color = col
            ld.energy = pw * W * W
            ld.size = size * W
            lo = bpy.data.objects.new(ld.name, ld)
            self.coll.objects.link(lo)
            pos_w = Vector(p) * W
            lo.matrix_world = self.Mw @ Matrix.Translation(pos_w) @ \
                (-pos_w).to_track_quat("-Z", "Y").to_matrix().to_4x4()
            lo.light_linking.receiver_collection = self.coll
            lo["t3d_rest"] = [list(r) for r in lo.matrix_world]
            self.light_obs.append(lo)

    def act_palette(self):
        try:
            sh = self.ctx.shot(self.shots[0]) if self.shots else None
            act = self.ctx.act_at(sh["a"] if sh else self.f0)
            aid = act["id"] if isinstance(act, dict) else act
            return self.ctx.palette(aid) or {}
        except Exception:
            return {}

    # ---------------------------------------------------------------------------- animation
    def frames(self):
        a = math.floor(self.f0) - 6.0      # entrances may start up to ~5 f before f0; keys before them are hidden
        b = math.ceil(self.end_frame()) + 1.0
        return frange(a, b, 0.5)

    def segments(self):
        """-> [(t_start, t_end, X, Mw)]: the word's world frame is X @ Mw on [t_start, t_end)."""
        segs = []
        if self.shot_frames:
            t_prev = -1e9
            for j, (sid, M_i) in enumerate(self.shot_frames):
                t_end = 1e9
                if j + 1 < len(self.shot_frames):
                    nxt = self.shot_frames[j + 1][0]
                    c = next((c for c in self.E["cuts"] if c.get("a") == sid and c.get("b") == nxt), None)
                    t_end = (c["f"] - 0.5) if c else float(self.ctx.shot(nxt)["a"]) - 0.5
                segs.append((t_prev, t_end, Matrix.Identity(4), M_i))
                t_prev = t_end
            return segs
        X = Matrix.Identity(4)
        t_prev = -1e9
        for th in self.teleports():
            segs.append((t_prev, th, X.copy(), self.Mw))
            eps = getattr(self.ctx, "EPS", 0.02)   # the core keys a teleport at th -/+ EPS
            Xa = self.cam(th - eps)
            Xb = self.cam(th + eps)
            X = Xb @ Xa.inverted() @ X
            t_prev = th
        segs.append((t_prev, 1e9, X, self.Mw))
        return segs

    def seg_at(self, f):
        for ta, tb, X, M in self.segs:
            if ta <= f < tb:
                return X, M
        return self.segs[-1][2], self.segs[-1][3]

    def animate(self):
        self.segs = segs = self.segments()
        frames = self.frames()
        targets = []
        for L in self.letters:
            targets.append((L, None))
            for c in L.get("chunks", []):
                targets.append((L, c))
        for si, (ta, tb, Xs, Mseg) in enumerate(segs):
            fr = [f for f in frames if ta - 0.5 <= f <= tb + 0.5]
            if not fr:
                continue
            for L, c in targets:
                me = (c or L)["mesh"]
                ob = bpy.data.objects.new(f"{me.name}.s{si}", me)
                self.coll.objects.link(ob)
                tw = bpy.data.objects.new(f"{me.name}.s{si}.glow", me)
                self.glow_coll.objects.link(tw)
                tw.material_slots[0].link = "OBJECT"
                tw.material_slots[0].material = self.mat_l
                tw.material_slots[1].link = "OBJECT"
                tw.material_slots[1].material = self.mat_l
                for o in (ob, tw):
                    o.rotation_mode = "QUATERNION"
                    o["t3d_pop"] = 0.0
                    o.visible_shadow = False
                for f in fr:
                    M, vis, pop = self.pose(L, c, f)
                    vis = vis and ta <= f < tb
                    Mw = Xs @ Mseg @ M
                    loc, rot, sca = Mw.decompose()
                    for o in (ob, tw):
                        o.location, o.rotation_quaternion, o.scale = loc, rot, sca
                        o["t3d_pop"] = pop
                        o.keyframe_insert("location", frame=f)
                        o.keyframe_insert("rotation_quaternion", frame=f)
                        o.keyframe_insert("scale", frame=f)
                        o.keyframe_insert('["t3d_pop"]', frame=f)
                        o.hide_render = not vis
                        o.keyframe_insert("hide_render", frame=f)
            if si > 0:
                for lo in self.light_obs:
                    cp = lo.copy()
                    cp.data = lo.data
                    self.coll.objects.link(cp)
                    cp.matrix_world = Xs @ Mseg @ self.Mw.inverted() @ lo.matrix_world
        self.key_material()

    # ---- the plate defocuses slightly while the title holds (REFS: rack focus to the text)
    def key_hold_focus(self, blur_px=5.0, ramp=3):
        span = self.st.get("hold")
        cam = bpy.context.scene.camera
        if not span or cam is None or not self.shots:
            return
        busy = [(w0, w1) for w0, w1, _ in (getattr(self.ctx, "windows", []) or [])]
        f_mm = LENS_MM
        a, b = span
        sid = self.shots[0]
        if self.shot_frames:
            for (ta, tb, _, _), (sd, _) in zip(self.segs, self.shot_frames):
                if ta <= a < tb:
                    sid = sd
        card = self.ctx.card(sid)
        nrm = (card.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
        keyed = []
        for f in range(int(a), int(b) + 1):
            if any(w0 - 1 <= f < w1 + 1 for w0, w1 in busy):
                continue
            C = self.cam(f)
            fwd = (C.to_3x3() @ Vector((0, 0, -1))).normalized()
            dc = (card.matrix_world.translation - C.translation).dot(nrm) / fwd.dot(nrm)
            Xs, Ms = self.seg_at(f)
            dt = ((Xs @ Ms).translation - C.translation).dot(fwd)
            if dc <= 0 or dt <= f_mm / 1000.0:
                continue
            u = min(1.0, (f - a + 1) / float(ramp), (b - f + 1) / float(ramp))
            c_mm = max(0.05, blur_px * u) * SENSOR_MM / W_PX
            N = (f_mm ** 2) * abs(dc - dt) * 1000.0 / (c_mm * dc * 1000.0 * (dt * 1000.0 - f_mm))
            N = min(max(N, 1.2), 128.0)
            cam.data.dof.focus_distance = dt
            cam.data.dof.aperture_fstop = N
            cam.data.keyframe_insert("dof.focus_distance", frame=f)
            cam.data.keyframe_insert("dof.aperture_fstop", frame=f)
            keyed.append(f)
        if keyed:
            cam.data.dof.aperture_fstop = 128.0
            for f in (keyed[0] - 1, keyed[-1] + 1):
                if not any(w0 <= f < w1 for w0, w1 in busy):
                    cam.data.keyframe_insert("dof.aperture_fstop", frame=f)
            self.ctx.log(f"text3d {self.id}: plate defocus {blur_px:.0f} px while holding {keyed[0]}-{keyed[-1]}")

    # ---- material timeline: face emission, outline glow, sweep
    def key_material(self):
        st = self.st
        anim = self.T.get("anim", "assemble")
        f0 = self.f0
        if anim == "assemble":
            t_sweep, t_settle = 317.0, 324.0
        elif anim == "fly_in":
            t_sweep, t_settle = 638.0, 644.0
        elif anim == "slam_letters":
            t_sweep, t_settle = 766.0, 771.0
        else:
            t_sweep, t_settle = 806.0, 810.0
        frames = self.frames()
        for f in frames:
            u_sw = (f - t_sweep) / 9.0
            pos = -0.3 + 1.7 * ease_out_expo(u_sw * 0.9) if f >= t_sweep else -0.6
            amp = (math.sin(math.pi * clamp01(u_sw)) ** 0.7) * 5.0 if 0 <= u_sw <= 1 else 0.0
            face = 0.45 - 0.25 * ease_out_expo((f - t_settle) / 8.0) if f >= t_settle else 0.45
            if st.get("chrome"):
                face = 1.0
            rim = 0.8 + 4.0 * ease_out_expo((f - t_settle) / 8.0) if f >= t_settle else 0.8
            if self.exit and f >= self.exit[1] - 3:
                rim += 2.0 * clamp01((f - (self.exit[1] - 3)) / 3)
            vals = dict(face=face, rim=rim, sweep=amp, pos=pos)
            for k, node in self.P.items():
                node.outputs[0].default_value = vals[k]
                node.outputs[0].keyframe_insert("default_value", frame=f)
            for k, node in self.LP.items():
                node.outputs[0].default_value = vals[k]
                node.outputs[0].keyframe_insert("default_value", frame=f)

    # ---- per-letter pose in word space: -> (Matrix, visible, pop)
    def base_pose(self, L, f):
        anim = self.T.get("anim", "assemble")
        if L.get("sub"):
            M, vis, pop = self.anim_sub(L, f)
        elif anim == "assemble":
            M, vis, pop = self.anim_assemble(L, f)
        elif anim == "fly_in":
            M, vis, pop = self.anim_fly_in(L, f)
        elif anim == "slam_letters":
            M, vis, pop = self.anim_slam_letters(L, f)
        else:
            M, vis, pop = self.anim_slam(L, f)
        return M @ self.idle(L, f), vis, pop

    def pose(self, L, chunk, f):
        M, vis, pop = self.base_pose(L, f)
        if self.exit:
            kind, fe = self.exit
            if kind == "fly_through":
                M, vis2, pop2 = self.exit_fly_through(L, f, M)
                vis = vis and vis2
                pop = max(pop, pop2)
            elif kind == "shatter":
                if chunk is None:
                    vis = vis and f < fe + 0.5
                    pop = max(pop, 1.5 * clamp01((f - (fe - 1.5)) / 1.5))
                else:
                    M, vis, pop = self.exit_shatter(L, chunk, f, M)
        elif chunk is not None:
            vis = False
        if not vis:
            return M, False, pop
        return M, vis and f <= self.end_frame(), pop

    def W(self):
        return self.width_m

    def cam_dist(self):
        """distance from the word plane to the hero camera (m)"""
        C = self.cam(self.hero)
        return (C.translation - self.Mw.translation).length

    def idle(self, L, f):
        r = L["rnd"]
        ph = r.random() * 6.28
        a = 0.004 * self.W()
        return Matrix.Translation((0, a * math.sin(f * 0.21 + ph), a * 0.6 * math.sin(f * 0.17 + ph * 1.3))) @ \
            Matrix.Rotation(math.radians(0.8 * math.sin(f * 0.13 + ph)), 4, "Y")

    def anim_assemble(self, L, f):
        Wm = self.W()
        r = random.Random(L["i"] * 31 + 7)
        order = [3, 1, 5, 0, 6, 2, 4]
        o = order[L["i"] % len(order)] if L["n"] == 7 else L["i"]
        ts = self.f0 + o * 1.4
        dur = 10.0
        u = (f - ts) / dur
        side = 1.0 if L["rest"].x >= 0 else -1.0
        d0 = Vector((side * r.uniform(0.5, 1.1) * Wm, r.uniform(0.25, 0.7) * Wm, -r.uniform(1.4, 2.6) * Wm))
        e = ease_out_expo(u)
        pos = L["rest"] + d0 * (1.0 - e)
        ax = Vector((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-0.4, 0.4))).normalized()
        ang = math.radians(r.uniform(140, 260)) * (1.0 - ease_out_back(u, 1.4))
        M = Matrix.Translation(pos) @ Quaternion(ax, ang).to_matrix().to_4x4()
        pop = 1.6 * math.exp(-max(0.0, f - (ts + dur * 0.55)) / 2.5) if f >= ts + dur * 0.4 else 0.0
        return M, f >= ts, pop

    def anim_fly_in(self, L, f):
        Wm = self.W()
        D = self.cam_dist()
        r = random.Random(L["i"] * 17 + 3)
        n = L["n"]
        o = abs(L["i"] - (n - 1) / 2.0)          # centre letters first, outer ones follow
        ts = self.f0 + o * 0.9
        dur = 7.5
        u = (f - ts) / dur
        side = 1.0 if L["rest"].x >= 0 else -1.0
        d0 = Vector((side * r.uniform(0.25, 0.6) * Wm + L["rest"].x * 0.8, r.uniform(-0.25, 0.25) * Wm,
                     D * r.uniform(0.82, 0.92)))
        e = ease_out_expo(u)
        pos = L["rest"] + d0 * (1.0 - e)
        ax = Vector((r.uniform(-0.4, 0.4), 1.0, r.uniform(-0.3, 0.3))).normalized()
        ang = math.radians(r.choice([-1, 1]) * r.uniform(90, 160)) * (1.0 - ease_out_back(u, 1.2))
        M = Matrix.Translation(pos) @ Quaternion(ax, ang).to_matrix().to_4x4()
        pop = 1.4 * math.exp(-max(0.0, f - (ts + dur * 0.6)) / 3.0) if f >= ts + dur * 0.45 else 0.0
        return M, f >= ts, pop

    def anim_slam_letters(self, L, f):
        Wm = self.W()
        D = self.cam_dist()
        beats = self.st.get("beats") or [self.f0 + 2 + 1.5 * i for i in range(L["n"])]
        tb = beats[min(L["i"], len(beats) - 1)]
        r = random.Random(L["i"] * 13 + 1)
        lead = 4.0
        u = (f - (tb - lead)) / lead
        if f < tb:
            e = ease_in_cubic(u)
            z = D * 0.78 * (1.0 - e)
            ang = math.radians(r.uniform(-28, 28)) * (1.0 - e)
            s = 1.0
        else:
            k = f - tb
            z = -0.06 * Wm * math.exp(-k / 2.2) * math.cos(k * 1.1)
            ang = 0.0
            s = 1.0 + 0.10 * math.exp(-k / 1.6) * math.cos(k * 1.3)
        pos = L["rest"] + Vector((L["rest"].x * 0.35 * clamp01(z / max(D, 1e-6)), 0, z))
        M = Matrix.Translation(pos) @ Matrix.Rotation(ang, 4, "Z") @ Matrix.Scale(s, 4)
        pop = 2.2 * math.exp(-(f - tb) / 2.5) if f >= tb else 0.0
        return M, f >= tb - lead, pop

    def anim_sub(self, L, f):
        at = float(self.st["sub"]["at"])
        u = (f - at) / 6.0
        e = ease_out_expo(u)
        M = Matrix.Translation(L["rest"] + Vector((-(1 - e) * 0.4 * self.W(), 0, 0))) @ \
            Matrix.Diagonal((max(e, 1e-3), 1.0, 1.0, 1.0))
        pop = 1.2 * math.exp(-max(0.0, f - at - 2) / 3.0) if f >= at else 0.0
        return M, f >= at, pop

    def anim_slam(self, L, f):
        """TIMELESS: the whole word slams in from behind the camera on f0, letters 0.4 f apart, a settle bounce."""
        D = max(self.cam_dist(), 1.0)
        n = L["n"]
        tb = self.f0 + (abs(L["i"] - (n - 1) / 2.0)) * 0.3
        lead = 2.5
        r = random.Random(L["i"] * 7 + 11)
        if f < tb:
            e = ease_in_cubic((f - (tb - lead)) / lead)
            z = D * 0.95 * (1.0 - e)
            ang = math.radians(r.uniform(-35, 35)) * (1.0 - e)
            s = 1.0
        else:
            k = f - tb
            z = -0.05 * self.W() * math.exp(-k / 2.0) * math.cos(k * 1.2)
            ang = 0.0
            s = 1.0 + 0.08 * math.exp(-k / 1.5) * math.cos(k * 1.4)
        pos = L["rest"] + Vector((L["rest"].x * 0.6 * clamp01(z / D), 0, z))
        M = Matrix.Translation(pos) @ Matrix.Rotation(ang, 4, "Z") @ Matrix.Scale(s, 4)
        pop = 2.5 * math.exp(-(f - tb) / 2.5) if f >= tb else 0.0
        return M, f >= tb - lead, pop

    # ---- exits
    def fly_cut(self):
        fe = self.exit[1]
        for c in self.E.get("cuts", []):
            if c["f"] == fe:
                return c
        return dict(f=fe, w0=fe - 8, w1=fe + 6)

    def exit_fly_through(self, L, f, M):
        """letters launch staggered from their place and rush at the camera, passing around the lens just before the
        cut (one very close), tumbling. Paths are world-space Hermites to points beside the camera, then straight on."""
        cut = self.fly_cut()
        fe = float(cut["f"])
        w0 = float(cut["w0"])
        n = L["n"]
        i = L["i"]
        near = (n - 1) // 2
        r = random.Random(i * 29 + 5)
        # launch order: outer letters first, the near (centre) letter last
        # the near letter covers the lens at the cut; its two neighbours pass just after it (in B's set, through the
        # teleport copy), the rest before it, outer letters first
        late = [near + 1] if n >= 5 and near + 1 < n else []
        early = sorted([j for j in range(n) if j != near and j not in late], key=lambda j: -abs(j - near))
        if i == near:
            t_pass = fe - 0.7
        elif i in late:
            t_pass = fe + 0.6
        else:
            t_pass = fe - 1.3 - (len(early) - 1 - early.index(i)) * 0.5
        t_l = max(w0 + 0.5, t_pass - 5.5)
        if f < t_l:
            return M, True, 0.0
        if not hasattr(self, "_inv_mw"):
            self._inv_mw = self.Mw.inverted()
        M_l = self.base_pose(L, t_l)[0]
        P0 = (self.Mw @ M_l).translation
        tc = min(t_pass, fe - 0.55)
        C = self.cam(tc)
        cpos = C.translation
        if t_pass > tc:  # after the teleport: extrapolate the A-side camera (the copy maps it into B's set)
            cpos = cpos + (cpos - self.cam(tc - 0.5).translation) * ((t_pass - tc) / 0.5)
        cx = C.to_3x3() @ Vector((1, 0, 0))
        cy = C.to_3x3() @ Vector((0, 1, 0))
        fwd = C.to_3x3() @ Vector((0, 0, -1))
        rel = P0 - cpos
        d2 = Vector((rel.dot(cx), rel.dot(cy)))
        if d2.length < 1e-4:
            d2 = Vector((1, 0))
        d2.normalize()
        if i == near:
            radius = 0.045
        elif i in late:
            radius = 0.16
        else:
            radius = r.uniform(0.16, 0.5) * self.W() * 0.6
        Pp = cpos + cx * (d2.x * radius) + cy * (d2.y * radius) + fwd * 0.02
        T = t_pass - t_l
        v_avg = (Pp - P0) / T
        v_end = v_avg * 2.6
        if f <= t_pass:
            u = (f - t_l) / T
            P = hermite(P0, Vector((0, 0, 0)), Pp, v_end, u, T)
        else:
            P = Pp + v_end * (f - t_pass)
        ax = Vector((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-1, 1))).normalized()
        spin = math.radians(r.uniform(2.5, 5.0)) * (f - t_l) ** 2
        Pw = self._inv_mw @ P
        R = M_l.to_3x3().to_4x4()
        Mn = Matrix.Translation(Pw) @ Quaternion(ax, spin).to_matrix().to_4x4() @ R
        pop = 1.5 * clamp01((f - t_l) / 3.0)
        return Mn, f < t_pass + (1.0 if i in late else 3.0), pop

    def exit_shatter(self, L, c, f, M):
        fe = self.exit[1]
        th = fe + 0.5
        if f < th:
            return M, False, 0.0
        burst = bpy.data.objects.get("TRIPTYCH_BURST")
        Minv = self.Mw.inverted()
        if burst is not None:
            o = Minv @ burst.matrix_world.translation
            tow = (Minv.to_3x3() @ (burst.matrix_world.to_3x3() @ Vector((0, 0, 1)))).normalized()
        else:
            o = Vector((0, 0, -0.45))
            tow = Vector((0, 0, 1))
        r = c["rnd"]
        Mth = self.base_pose(L, th)[0] @ Matrix.Translation(c["rest"] - L["rest"])
        p0 = Mth.translation
        radial = p0 - o
        radial -= tow * radial.dot(tow)
        dist = radial.length
        rd = radial.normalized() if dist > 1e-6 else Vector((1, 0, 0))
        v = rd * (r.uniform(0.10, 0.18) * max(dist, 0.3)) + tow * r.uniform(0.12, 0.25)
        k = f - th
        acc = sum(1.25 ** min(j, 3) for j in range(int(k))) + (k - int(k)) * 1.25 ** min(int(k), 3)
        pos = p0 + v * acc
        ax = Vector((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-1, 1))).normalized()
        ang = math.radians(r.uniform(15, 40)) * k
        Mc = Matrix.Translation(pos) @ Quaternion(ax, ang).to_matrix().to_4x4() @ Mth.to_3x3().to_4x4()
        return Mc, k < 9.0, 1.0 * math.exp(-k / 2.0)


def build(E, ctx):
    pref = bpy.context.preferences.edit
    old = pref.keyframe_new_interpolation_type
    pref.keyframe_new_interpolation_type = "LINEAR"
    made = []
    # --only runs (module tests): build just the titles that overlap a built window; T3D_ONLY=AMAZING,... forces a list
    want = os.environ.get("T3D_ONLY")
    want = set(want.split(",")) if want else None
    wins = list(getattr(ctx, "windows", []) or [])
    only = getattr(getattr(ctx, "args", None), "only", None)
    try:
        for T in E.get("titles", []):
            if T.get("style") != "text3d":
                continue
            if want is not None and T["id"] not in want:
                continue
            if want is None and only and not any(w0 - 30 <= T["f1"] and T["f"] <= w1 + 30 for w0, w1, _ in wins):
                ctx.log(f"text3d {T['id']}: outside the --only windows, skipped")
                continue
            t = Title(T, E, ctx)
            t.build()
            made.append(t)
    finally:
        pref.keyframe_new_interpolation_type = old
    return made
