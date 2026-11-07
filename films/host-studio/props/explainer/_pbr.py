"""_pbr — tileable 2K PBR texture sets drawn in numpy, their preview materials, world-scale UVs, UCX collision and
the FBX/texture delivery for the explainer props (chair, desk, broadcast mic on a boom, headphones, desk plant).

Every texture tiles seamlessly: noise is white noise filtered in the frequency domain, which is periodic by
construction, and every pattern has a whole number of periods across the tile.

Per material M_<X>: T_<X>_BC.png (sRGB base colour), T_<X>_N.png (normal, DirectX / Unreal: green down),
T_<X>_ORM.png (linear: R ambient occlusion, G roughness, B metallic). TILE_M[X] is the world size of one tile:
UV0 is laid out so 1 UV unit = that many metres (tiled, islands may overlap 0..1). UV1 is a packed, non-overlapping
0..1 layout for lightmaps.

Units: 1 Blender unit = 1 m; FBX written in cm (FBX_SCALE_UNITS). Unreal maps Blender (x, y, z) to (x, -y, z).
"""
import json
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

N = 2048

# material -> world size of one texture tile (m)
TILE_M = {
    "ChairFabric": 0.08, "BrushedAlu": 0.25, "PowderBlack": 0.12, "Rubber": 0.06, "Grille": 0.025,
    "Walnut": 0.60, "Leather": 0.06, "PlasticBlack": 0.08, "Steel": 0.06, "Ceramic": 0.20, "Soil": 0.10,
    "Leaf": 0.12, "Brass": 0.25, "ShadeLinen": 0.10, "LampBulb": 0.05,
}


# --------------------------------------------------------------------------- periodic noise

def _freqs(n):
    f = np.fft.fftfreq(n)
    return np.meshgrid(f, f, indexing="xy")     # fx varies along columns (u), fy along rows (v)


def noise(n, period_px, seed, aniso=1.0, angle=0.0):
    """Zero-mean unit-std periodic noise with features ~period_px; aniso > 1 stretches features along u."""
    rng = np.random.default_rng(seed)
    fx, fy = _freqs(n)
    c, s = math.cos(angle), math.sin(angle)
    ru, rv = c * fx + s * fy, -s * fx + c * fy
    sig = 1.0 / max(period_px, 1e-3)
    filt = np.exp(-0.5 * (((ru * aniso) / sig) ** 2 + (rv / sig) ** 2))
    w = rng.standard_normal((n, n))
    out = np.real(np.fft.ifft2(np.fft.fft2(w) * filt))
    out -= out.mean()
    return out / (out.std() + 1e-12)


def fbm(n, period_px, seed, octaves=4, gain=0.5, aniso=1.0):
    out = np.zeros((n, n))
    amp, p = 1.0, period_px
    for i in range(octaves):
        out += amp * noise(n, p, seed + 17 * i, aniso=aniso)
        amp *= gain
        p *= 0.5
    return out / out.std()


def blur(a, px):
    fx, fy = _freqs(a.shape[0])
    sig = 1.0 / max(px, 1e-3)
    return np.real(np.fft.ifft2(np.fft.fft2(a) * np.exp(-0.5 * ((fx / sig) ** 2 + (fy / sig) ** 2))))


def coords(n):
    u = (np.arange(n) + 0.5) / n
    return np.meshgrid(u, u, indexing="xy")      # u along columns, v along rows (row 0 = v 0 = image bottom)


def normal_from_height(h, strength):
    """Height in tile-relative units -> OpenGL tangent-space normal (x, y, z) arrays."""
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * strength
    nz = np.ones_like(h)
    ln = np.sqrt(dx * dx + dy * dy + 1.0)
    return -dx / ln, -dy / ln, nz / ln


def cavity_ao(h, px, k):
    return np.clip(1.0 - k * np.clip(blur(h, px) - h, 0, None), 0.0, 1.0)


def srgb_to_lin(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def mix(a, b, t):
    """Mix two sRGB colours (as linear) by t (array) -> linear (n, n, 3)."""
    a, b = srgb_to_lin(a), srgb_to_lin(b)
    return a[None, None, :] * (1 - t[..., None]) + b[None, None, :] * t[..., None]


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# --------------------------------------------------------------------------- the materials

def tex_fabric(n, seed=1, a=(0.30, 0.30, 0.31), b=(0.20, 0.205, 0.215)):
    """Plain-woven heathered upholstery: ~1 mm yarns (100 per tile), each yarn its own tone, fibre fuzz."""
    u, v = coords(n)
    P = 100                                              # yarns per tile each way
    rng = np.random.default_rng(seed)
    iu, iv = np.floor(u * P).astype(int), np.floor(v * P).astype(int)
    fu, fv = u * P - iu, v * P - iv
    bump_u = np.sin(np.pi * fu) ** 0.6                   # weft yarn cross-section (yarn runs along v)
    bump_v = np.sin(np.pi * fv) ** 0.6                   # warp yarn cross-section (yarn runs along u)
    over = (iu + iv) % 2                                  # plain weave
    warp = bump_v * (0.55 + 0.45 * np.where(over == 0, np.sin(np.pi * fu), 1 - np.sin(np.pi * fu) * 0.6))
    weft = bump_u * (0.55 + 0.45 * np.where(over == 1, np.sin(np.pi * fv), 1 - np.sin(np.pi * fv) * 0.6))
    top_is_warp = warp >= weft
    fib_u = noise(n, 1.2, seed + 1, aniso=6.0)             # fibres along the yarn
    fib_v = noise(n, 1.2, seed + 2, aniso=6.0, angle=math.pi / 2)
    h = np.maximum(warp, weft) + 0.08 * np.where(top_is_warp, fib_u, fib_v)
    h += 0.05 * noise(n, 2.0, seed + 3)
    tone_warp = rng.random(P)[iv]
    tone_weft = rng.random(P)[iu]
    tone = np.where(top_is_warp, tone_warp, tone_weft)
    t = np.clip(0.5 * tone + 0.2 * noise(n, 40, seed + 4) * 0.5 + 0.25 + 0.08 * np.where(top_is_warp, fib_u, fib_v), 0, 1)
    col = mix(a, b, t)
    ao = cavity_ao(h, 6, 1.4) * (0.75 + 0.25 * np.clip(np.maximum(warp, weft), 0, 1))
    col *= (0.85 + 0.15 * ao)[..., None]
    rough = 0.88 + 0.06 * noise(n, 3, seed + 5) * 0.5
    return col, normal_from_height(h, 0.35 * n / P / 6), ao, np.clip(rough, 0, 1), np.zeros((n, n))


def tex_brushed(n, seed=2, base=(0.86, 0.865, 0.87)):
    """Brushed aluminium: long fine streaks along u, a few deeper scratches."""
    s = noise(n, 0.9, seed, aniso=60) * 0.7 + noise(n, 3, seed + 1, aniso=40) * 0.3
    scratches = np.clip(noise(n, 0.7, seed + 2, aniso=200) - 2.2, 0, None)
    h = 0.6 * s - 1.5 * scratches
    t = np.clip(0.5 + 0.12 * s + 0.03 * noise(n, 900, seed + 3, aniso=8), 0, 1)
    col = mix(base, (0.70, 0.705, 0.71), t * 0.6)
    rough = np.clip(0.32 + 0.025 * s + 0.06 * scratches, 0.25, 0.45)
    return col, normal_from_height(h, 0.02), np.ones((n, n)), rough, np.ones((n, n))


def tex_powder(n, seed=3, base=(0.045, 0.045, 0.048), rough0=0.48):
    """Powder-coated / satin painted metal: soft orange peel, faint speckle."""
    peel = noise(n, 14, seed) * 0.7 + noise(n, 5, seed + 1) * 0.3
    speck = noise(n, 1.0, seed + 2)
    col = mix(base, (0.06, 0.06, 0.064), np.clip(0.5 + 0.25 * speck, 0, 1))
    rough = np.clip(rough0 + 0.05 * peel + 0.04 * speck, 0, 1)
    return col, normal_from_height(peel, 0.3), np.ones((n, n)), rough, np.zeros((n, n))


def tex_rubber(n, seed=4, base=(0.048, 0.048, 0.05)):
    g = noise(n, 1.5, seed) * 0.6 + noise(n, 8, seed + 1) * 0.4
    col = mix(base, (0.07, 0.07, 0.072), np.clip(0.5 + 0.2 * g, 0, 1))
    rough = np.clip(0.82 + 0.05 * g, 0, 1)
    return col, normal_from_height(g, 0.08), cavity_ao(g, 4, 0.05), rough, np.zeros((n, n))


def tex_grille(n, seed=5):
    """Woven wire mesh: 40 openings per tile (~0.6 mm pitch), dark gunmetal wire, black holes."""
    u, v = coords(n)
    P = 40
    iu, iv = np.floor(u * P).astype(int), np.floor(v * P).astype(int)
    fu, fv = u * P - iu, v * P - iv
    wr = 0.22                                             # wire half-width as a fraction of the pitch
    du, dv = np.minimum(fu, 1 - fu), np.minimum(fv, 1 - fv)
    wire_v = np.clip(1 - (dv / wr) ** 2, 0, None) ** 0.5   # wire along u, centred on the cell edge
    wire_u = np.clip(1 - (du / wr) ** 2, 0, None) ** 0.5
    over = (iu + iv) % 2
    hv = wire_v * (0.6 + 0.4 * np.where(over == 0, np.cos(np.pi * (fu - 0.5)), -np.cos(np.pi * (fu - 0.5))))
    hu = wire_u * (0.6 + 0.4 * np.where(over == 1, np.cos(np.pi * (fv - 0.5)), -np.cos(np.pi * (fv - 0.5))))
    wire = np.maximum(wire_u, wire_v) > 0
    h = np.maximum(hv, hu)
    col = np.where(wire[..., None], mix((0.20, 0.205, 0.21), (0.14, 0.14, 0.15),
                                        np.clip(0.5 + 0.3 * noise(n, 3, seed), 0, 1)), srgb_to_lin((0.01, 0.01, 0.01)))
    ao = np.where(wire, 0.6 + 0.4 * np.clip(h, 0, 1), 0.05)
    rough = np.where(wire, 0.38, 0.9)
    metal = np.where(wire, 1.0, 0.0)
    return col, normal_from_height(h, 0.6 * n / P / 8), ao, rough, metal


def tex_walnut(n, seed=6):
    """Flat-sawn American walnut, oiled satin: cathedral/stripe figure along u, pores, colour drift."""
    u, v = coords(n)
    warp = 0.016 * noise(n, 420, seed, aniso=6) + 0.0025 * noise(n, 90, seed + 1, aniso=12)
    # 30 growth rings across the tile, nearly straight along u, gently drifting (flat-sawn stripe figure)
    ring_pos = 30 * (v + warp + 0.004 * np.sin(2 * np.pi * (u + 0.15 * noise(n, 500, seed + 2, aniso=4))))
    fr = ring_pos - np.floor(ring_pos)
    late = smooth(0.55, 0.85, fr) * (1 - smooth(0.92, 1.0, fr))    # darker latewood band
    streak = noise(n, 2.5, seed + 3, aniso=25)                     # fibre streaks along u
    pores = np.clip(noise(n, 0.9, seed + 4, aniso=14) - 1.6, 0, None)
    drift = noise(n, 500, seed + 5, aniso=2)
    t = np.clip(0.30 + 0.45 * late + 0.10 * streak + 0.12 * drift, 0, 1)
    col = mix((0.47, 0.31, 0.20), (0.20, 0.115, 0.07), t)
    col *= (1 - 0.55 * np.clip(pores, 0, 1))[..., None]
    h = -0.4 * pores - 0.05 * late + 0.03 * streak
    rough = np.clip(0.40 + 0.08 * late + 0.25 * np.clip(pores, 0, 1) + 0.03 * streak, 0, 1)
    ao = 1 - 0.4 * np.clip(pores, 0, 1)
    return col, normal_from_height(h, 0.8), ao, rough, np.zeros((n, n))


def tex_leather(n, seed=7, base=(0.038, 0.036, 0.036)):
    """Protein leather: fine pebble grain (ridged noise), soft sheen."""
    g = 1 - np.abs(noise(n, 9, seed))
    g = g * 0.7 + 0.3 * (1 - np.abs(noise(n, 4, seed + 1)))
    col = mix(base, (0.065, 0.062, 0.06), np.clip(g - 0.3, 0, 1))
    rough = np.clip(0.52 - 0.12 * g + 0.04 * noise(n, 80, seed + 2), 0, 1)
    return col, normal_from_height(g, 0.4), cavity_ao(g, 5, 0.25), rough, np.zeros((n, n))


def tex_plastic(n, seed=8, base=(0.035, 0.035, 0.037)):
    """Matte-textured ABS (fine mould texture)."""
    g = noise(n, 2.2, seed) * 0.7 + noise(n, 10, seed + 1) * 0.3
    col = mix(base, (0.05, 0.05, 0.052), np.clip(0.5 + 0.2 * g, 0, 1))
    rough = np.clip(0.42 + 0.05 * g, 0, 1)
    return col, normal_from_height(g, 0.08), np.ones((n, n)), rough, np.zeros((n, n))


def tex_steel(n, seed=9):
    s = noise(n, 1.0, seed, aniso=30)
    col = mix((0.80, 0.80, 0.81), (0.70, 0.70, 0.71), np.clip(0.5 + 0.2 * s, 0, 1))
    rough = np.clip(0.18 + 0.04 * s, 0, 1)
    return col, normal_from_height(s, 0.02), np.ones((n, n)), rough, np.ones((n, n))


def tex_ceramic(n, seed=10):
    """Satin glazed stoneware, warm off-white with iron speckle."""
    sp = np.clip(noise(n, 1.4, seed) - 2.6, 0, None)
    wav = noise(n, 60, seed + 1) * 0.6 + noise(n, 12, seed + 2) * 0.4
    col = mix((0.86, 0.84, 0.80), (0.78, 0.75, 0.70), np.clip(0.4 + 0.2 * wav, 0, 1))
    col = col * (1 - 0.7 * np.clip(sp, 0, 1))[..., None] + srgb_to_lin((0.25, 0.17, 0.10))[None, None] * 0.7 * np.clip(sp, 0, 1)[..., None]
    rough = np.clip(0.34 + 0.05 * wav, 0, 1)
    return col, normal_from_height(0.4 * wav, 0.25), np.ones((n, n)), rough, np.zeros((n, n))


def tex_soil(n, seed=11):
    g = fbm(n, 30, seed, octaves=5)
    grains = np.clip(noise(n, 2.0, seed + 1) - 1.0, 0, None)
    col = mix((0.13, 0.09, 0.06), (0.05, 0.035, 0.025), np.clip(0.5 - 0.25 * g, 0, 1))
    col += srgb_to_lin((0.45, 0.42, 0.38))[None, None] * (0.15 * np.clip(grains, 0, 1))[..., None]
    h = g + 1.5 * grains
    return col, normal_from_height(h, 2.0), cavity_ao(h, 8, 0.25), np.full((n, n), 0.93), np.zeros((n, n))


def tex_leaf(n, seed=12):
    """Sansevieria (snake plant) blade: deep green with pale zig-zag cross bands along v (the blade's length)."""
    u, v = coords(n)
    zig = 0.010 * np.abs(((u * 6) % 1.0) - 0.5) + 0.003 * noise(n, 60, seed, aniso=3)
    bands = 0.5 + 0.5 * np.sin(2 * np.pi * (v * 22 + zig * 22 + 0.10 * noise(n, 300, seed + 1, aniso=4)))
    b = smooth(0.55, 0.9, bands)
    fine = noise(n, 6, seed + 2, aniso=3) * 0.5
    col = mix((0.10, 0.19, 0.10), (0.36, 0.45, 0.30), np.clip(0.75 * b + 0.08 * fine, 0, 1))
    col = col * (0.9 + 0.1 * np.clip(0.5 + 0.3 * noise(n, 300, seed + 3), 0, 1))[..., None]
    h = 0.15 * fine + 0.05 * b
    rough = np.clip(0.42 + 0.06 * fine, 0, 1)
    return col, normal_from_height(h, 0.6), np.ones((n, n)), rough, np.zeros((n, n))


def tex_brass(n, seed=13):
    """Satin brushed brass (warm, streaks along u)."""
    col, nrm, ao, rough, metal = tex_brushed(n, seed, base=(0.86, 0.70, 0.45))
    return col, nrm, ao, np.clip(rough + 0.03, 0, 1), metal


def tex_linen(n, seed=14):
    """Lamp-shade linen: an open, slubby plain weave in warm off-white (light shows through it in Unreal)."""
    col, nrm, ao, rough, metal = tex_fabric(n, seed, a=(0.86, 0.82, 0.74), b=(0.78, 0.73, 0.64))
    slub = np.clip(noise(n, 3, seed + 9, aniso=25), 0, None) * 0.08
    return np.clip(col * (1 + slub)[..., None], 0, 1), nrm, ao, rough, metal


TEXTURES = {
    "ChairFabric": tex_fabric, "BrushedAlu": tex_brushed, "PowderBlack": tex_powder, "Rubber": tex_rubber,
    "Grille": tex_grille, "Walnut": tex_walnut, "Leather": tex_leather, "PlasticBlack": tex_plastic,
    "Steel": tex_steel, "Ceramic": tex_ceramic, "Soil": tex_soil, "Leaf": tex_leaf,
    "Brass": tex_brass, "ShadeLinen": tex_linen,
}


def _save(path, rgb, colorspace):
    """rgb (n, n, 3) in 0..1, row 0 = bottom, saved as 8-bit PNG through Blender."""
    n = rgb.shape[0]
    name = os.path.basename(path)
    img = bpy.data.images.get(name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, n, n, alpha=False, float_buffer=False)
    img.colorspace_settings.name = colorspace
    px = np.ones((n, n, 4), np.float32)
    px[..., :3] = np.clip(rgb, 0, 1)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return img


def write_textures(out_dir, names=None, n=N):
    """Draw and save every texture set (or `names`); returns {name: {BC, N, ORM, N_GL}} paths."""
    os.makedirs(out_dir, exist_ok=True)
    gl_dir = os.path.join(out_dir, "_blender")
    os.makedirs(gl_dir, exist_ok=True)
    paths = {}
    for name in names or TEXTURES:
        col, (nx, ny, nz), ao, rough, metal = TEXTURES[name](n)
        p = {k: os.path.join(out_dir, f"T_{name}_{k}.png") for k in ("BC", "N", "ORM")}
        p["N_GL"] = os.path.join(gl_dir, f"T_{name}_N_GL.png")
        _save(p["BC"], lin_to_srgb(col), "sRGB")
        _save(p["N"], np.stack([nx * 0.5 + 0.5, -ny * 0.5 + 0.5, nz * 0.5 + 0.5], -1), "Non-Color")   # DirectX
        _save(p["N_GL"], np.stack([nx * 0.5 + 0.5, ny * 0.5 + 0.5, nz * 0.5 + 0.5], -1), "Non-Color")
        _save(p["ORM"], np.stack([ao, rough, metal], -1), "Non-Color")
        paths[name] = p
        print(f"texture {name}: done", flush=True)
    return paths


# --------------------------------------------------------------------------- preview materials

def pbr_material(name, paths):
    """M_<name> sampling the drawn textures by UV0 (the OpenGL normal for Blender's previews)."""
    mname = "M_" + name
    m = bpy.data.materials.get(mname) or bpy.data.materials.new(mname)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"

    def img(path, cs):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(path, check_existing=True)
        t.image.colorspace_settings.name = cs
        t.interpolation = "Cubic"
        nt.links.new(uv.outputs[0], t.inputs[0])
        return t

    bc, orm, nrm = img(paths["BC"], "sRGB"), img(paths["ORM"], "Non-Color"), img(paths["N_GL"], "Non-Color")
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(orm.outputs[0], sep.inputs[0])
    ao_mul = nt.nodes.new("ShaderNodeMix")
    ao_mul.data_type = "RGBA"
    ao_mul.blend_type = "MULTIPLY"
    ao_mul.inputs[0].default_value = 1.0
    nt.links.new(bc.outputs[0], ao_mul.inputs[6])
    nt.links.new(sep.outputs[0], ao_mul.inputs[7])
    nt.links.new(ao_mul.outputs[2], bsdf.inputs["Base Color"])
    nt.links.new(sep.outputs[1], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs[2], bsdf.inputs["Metallic"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nrm.outputs[0], nm.inputs["Color"])
    nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    if name == "ChairFabric":                                       # a little fuzz for the previews
        bsdf.inputs["Sheen Weight"].default_value = 0.35
        bsdf.inputs["Sheen Roughness"].default_value = 0.4
    return m


# --------------------------------------------------------------------------- UVs

def _face_area_uv(bm, uvl, faces):
    a3 = sum(f.calc_area() for f in faces)
    a2 = 0.0
    for f in faces:
        pts = [l[uvl].uv for l in f.loops]
        s = 0.0
        for i in range(len(pts)):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % len(pts)]
            s += x0 * y1 - x1 * y0
        a2 += abs(s) / 2
    return a3, a2


def uv_grain_box(ob, grain_axis, tile):
    """Box projection on an object (before join) with U along `grain_axis` (0/1/2) where the face allows:
    1 UV unit = `tile` m. End-grain faces get the other two axes."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    mw = ob.matrix_world
    for f in bm.faces:
        nrm = (mw.to_3x3() @ f.normal)
        dom = max(range(3), key=lambda i: abs(nrm[i]))
        plane = [i for i in range(3) if i != dom]
        if grain_axis in plane:
            ua, va = grain_axis, [i for i in plane if i != grain_axis][0]
        else:
            ua, va = plane
        for l in f.loops:
            co = mw @ l.vert.co
            l[uvl].uv = (co[ua] / tile, co[va] / tile)
    bm.to_mesh(me)
    bm.free()


def _select_only(ob):
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob


def _edit_select(ob, pred):
    """Enter edit mode with exactly the faces for which pred(face) is true selected."""
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(ob.data)
    for v in bm.verts:
        v.select = False
    for e in bm.edges:
        e.select = False
    for f in bm.faces:
        f.select = False
    for f in bm.faces:
        if pred(f):
            f.select_set(True)
    bmesh.update_edit_mesh(ob.data)


def uv_finish(ob, tiles_by_slot, skip_slots=()):
    """UV0 'UVMap': smart-project every face of each slot not in skip_slots (whose UVs are already set), scaled
    so 1 UV unit = that slot's tile. UV1 'Lightmap': a packed 0..1 layout of the whole mesh."""
    _select_only(ob)
    me = ob.data
    if "UVMap" not in me.uv_layers:
        me.uv_layers.new(name="UVMap")
    if "Lightmap" not in me.uv_layers:
        me.uv_layers.new(name="Lightmap")
    for slot, mat in enumerate(me.materials):
        if mat is None or slot in skip_slots or not any(p.material_index == slot for p in me.polygons):
            continue
        me.uv_layers.active = me.uv_layers["UVMap"]
        _edit_select(ob, lambda f, s=slot: f.material_index == s)
        bpy.ops.uv.smart_project(angle_limit=math.radians(55), island_margin=0.002, area_weight=0.0,
                                 correct_aspect=True, scale_to_bounds=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        bm = bmesh.new()
        bm.from_mesh(me)
        uvl = bm.loops.layers.uv["UVMap"]
        faces = [f for f in bm.faces if f.material_index == slot]
        a3, a2 = _face_area_uv(bm, uvl, faces)
        k = math.sqrt(a3 / max(a2, 1e-12)) / tiles_by_slot[mat.name[2:]]
        for f in faces:
            for l in f.loops:
                l[uvl].uv = l[uvl].uv * k
        bm.to_mesh(me)
        bm.free()
    me.uv_layers.active = me.uv_layers["Lightmap"]
    _edit_select(ob, lambda f: True)
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.01, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=True)
    bpy.ops.uv.pack_islands(margin=0.01)
    bpy.ops.object.mode_set(mode="OBJECT")
    me.uv_layers.active = me.uv_layers["UVMap"]
    me.uv_layers["UVMap"].active_render = True


# --------------------------------------------------------------------------- collision, sockets, export

def ucx(asset, hulls):
    """UCX_<asset>_NN convex hulls (each a list of world points), parented to nothing, identity transforms."""
    obs = []
    for i, pts in enumerate(hulls):
        bm = bmesh.new()
        for p in pts:
            bm.verts.new(p)
        bmesh.ops.convex_hull(bm, input=list(bm.verts))
        for v in [v for v in bm.verts if not v.link_faces]:
            bm.verts.remove(v)
        name = f"UCX_{asset}_{i:02d}"
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        ob.display_type = "WIRE"
        bpy.context.scene.collection.objects.link(ob)
        obs.append(ob)
    return obs


def box_pts(lo, hi):
    return [Vector((x, y, z)) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]


def cyl_pts(c, r, z0, z1, n=12):
    return [Vector((c[0] + r * math.cos(2 * math.pi * k / n), c[1] + r * math.sin(2 * math.pi * k / n), z))
            for k in range(n) for z in (z0, z1)]


def socket(name, loc, direction=None):
    """SOCKET_<name> empty (Unreal makes it a static-mesh socket); its +X points along `direction`."""
    e = bpy.data.objects.new("SOCKET_" + name, None)
    e.empty_display_size = 0.03
    rot = Matrix.Identity(4)
    if direction is not None:
        rot = Vector(direction).to_track_quat("X", "Z").to_matrix().to_4x4()
    e.matrix_world = Matrix.Translation(loc) @ rot
    bpy.context.scene.collection.objects.link(e)
    return e


def export_fbx(path, objects):
    for o in bpy.context.scene.objects:
        o.select_set(o in objects)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"MESH", "EMPTY"},
        apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
        axis_forward="-Y", axis_up="Z", mesh_smooth_type="FACE", use_tspace=True,
        use_mesh_modifiers=True, add_leaf_bones=False, bake_space_transform=False, path_mode="STRIP")


def check_fbx(path, expect_cm):
    """Re-import the FBX into an empty scene and compare the main mesh's size (cm) with `expect_cm`."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    mesh = [o for o in new if o.type == "MESH" and not o.name.startswith("UCX_")]
    dims = None
    if mesh:
        ob = mesh[0]
        vs = [ob.matrix_world @ v.co for v in ob.data.vertices]
        dims = [round((max(v[i] for v in vs) - min(v[i] for v in vs)) * 100, 1) for i in range(3)]
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    ok = dims is not None and all(abs(a - b) < 0.2 for a, b in zip(dims, expect_cm))
    return ok, dims


def manifest_entry(ob, fbx, extra=None):
    vs = [ob.matrix_world @ v.co for v in ob.data.vertices]
    lo = [min(v[i] for v in vs) * 100 for i in range(3)]
    hi = [max(v[i] for v in vs) * 100 for i in range(3)]
    d = {
        "fbx": os.path.basename(fbx),
        "bbox_cm_blender": [[round(x, 1) for x in lo], [round(x, 1) for x in hi]],
        "size_cm": [round(h - l, 1) for l, h in zip(lo, hi)],
        "triangles": sum(len(p.vertices) - 2 for p in ob.data.polygons),
        "material_slots": [m.name for m in ob.data.materials],
    }
    d.update(extra or {})
    return d


def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
