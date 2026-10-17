"""Blender side of the basic title styles: a `basic.Frame` -> an RGBA PNG (straight alpha, 1920x1080).

Everything is emission (no lights): 1 Blender unit = 100 px, an orthographic camera looking down -Z frames the screen
exactly (docs/PIPELINE-AMV.md). Text is one Blender text object per glyph (laid out by `basic`), bars/brackets are
n-gon meshes. Each `basic.Group` (a layer with its own drop shadow / glow / smear in AE) is its own view layer, and the
compositor does the 2D effects per group (blur-based shadow and bloom halos, directional smear, the slash cut) and
stacks the groups with Alpha Over. CPU Cycles, a few samples are enough for flat emission.

`render_frames` is the one entry the style modules call. Run inside Blender (`blender -b --factory-startup -P ...`).
"""
from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import bpy

from . import basic
from .basic import GlyphEl, PolyEl, Ramp, Solid, W, H

PX = 0.01          # Blender units per px


def wx(x):
    return x * PX - W * PX / 2


def wy(y):
    return H * PX / 2 - y * PX


def lin3(rgb):
    return tuple(basic.srgb_to_linear(c) for c in rgb)


# ---------------------------------------------------------------------------------------------------------------------
# scene


def setup_scene(scale=1.0, samples=16):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.cycles.filter_width = 1.0
    sc.cycles.max_bounces = 0
    sc.render.film_transparent = True
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.resolution_percentage = int(round(scale * 100))
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.display_settings.display_device = "sRGB"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.image_settings.color_depth = "8"
    sc.render.image_settings.compression = 15
    try:
        sc.render.compositor_device = "CPU"
    except Exception:
        pass
    cam = bpy.data.cameras.new("cam")
    cam.type = "ORTHO"
    cam.ortho_scale = W * PX
    cam.clip_start, cam.clip_end = 0.1, 100.0
    co = bpy.data.objects.new("cam", cam)
    co.location = (0, 0, 10)
    sc.collection.objects.link(co)
    sc.camera = co
    sc.view_layers[0].use = False     # only the per-group view layers render
    return sc


_fonts = {}


def blender_font(name):
    if name not in _fonts:
        _fonts[name] = bpy.data.fonts.load(str(basic.font_path(name)))
    return _fonts[name]


_em = {}


def em_factor(name):
    """Blender's text `size` is not the em: it scales each font by a factor of its own (Orbitron 0.797, Montserrat 0.772
    ...). Measured from the advance of "HH" vs "H" (the metrics are ours, from the file), so size / factor = AE's px em."""
    if name not in _em:
        w = []
        for body in ("H", "HH"):
            cu = bpy.data.curves.new("cal", "FONT")
            cu.body, cu.font, cu.size = body, blender_font(name), 1.0
            ob = bpy.data.objects.new("cal", cu)
            bpy.context.scene.collection.objects.link(ob)
            bpy.context.view_layer.update()
            w.append(ob.dimensions.x)
            bpy.data.objects.remove(ob)
            bpy.data.curves.remove(cu)
        _em[name] = (w[1] - w[0]) / basic.metrics(name).advance("H")
    return _em[name]


# ---------------------------------------------------------------------------------------------------------------------
# materials


def make_material(fill, opacity, lit):
    """Emission of `fill` (Solid or vertical Ramp in screen px) at `opacity`; `lit` shades bevels by their normal."""
    m = bpy.data.materials.new("m")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    col = None
    if isinstance(fill, Ramp):
        pos = nt.nodes.new("ShaderNodeNewGeometry")
        mr = nt.nodes.new("ShaderNodeMapRange")
        sepy = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(pos.outputs["Position"], sepy.inputs[0])
        mr.inputs["From Min"].default_value = wy(fill.y0)
        mr.inputs["From Max"].default_value = wy(fill.y1)
        mr.inputs["To Min"].default_value = 0.0
        mr.inputs["To Max"].default_value = 1.0
        nt.links.new(sepy.outputs["Y"], mr.inputs["Value"])
        cr = nt.nodes.new("ShaderNodeValToRGB")
        el = cr.color_ramp.elements
        stops = fill.stops
        el[0].position, el[0].color = stops[0][0], (*lin3(stops[0][1]), 1)
        el[1].position, el[1].color = stops[-1][0], (*lin3(stops[-1][1]), 1)
        for t, c in stops[1:-1]:
            e = el.new(t)
            e.color = (*lin3(c), 1)
        nt.links.new(mr.outputs["Result"], cr.inputs["Fac"])
        col = cr.outputs["Color"]
    else:
        em.inputs["Color"].default_value = (*lin3(fill.rgb), 1)
    if lit:
        # light from the upper left on the bevel normals: flat faces (normal +Z) keep their exact colour
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        dot = nt.nodes.new("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        dot.inputs[1].default_value = (-0.55, 0.65, 0.0)
        k = nt.nodes.new("ShaderNodeMath")
        k.operation = "MULTIPLY_ADD"
        k.inputs[1].default_value = 0.75
        k.inputs[2].default_value = 1.0
        nt.links.new(geo.outputs["Normal"], dot.inputs[0])
        nt.links.new(dot.outputs["Value"], k.inputs[0])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        if col is not None:
            nt.links.new(col, mix.inputs["A"])
        else:
            mix.inputs["A"].default_value = (*lin3(fill.rgb), 1)
        nt.links.new(k.outputs["Value"], mix.inputs["B"])
        col = mix.outputs["Result"]
    if col is not None:
        nt.links.new(col, em.inputs["Color"])
    if opacity >= 0.999:
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    else:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mx = nt.nodes.new("ShaderNodeMixShader")
        mx.inputs["Fac"].default_value = max(0.0, min(1.0, 1.0 - opacity))
        nt.links.new(em.outputs["Emission"], mx.inputs[1])
        nt.links.new(tr.outputs["BSDF"], mx.inputs[2])
        nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])
    return m


# ---------------------------------------------------------------------------------------------------------------------
# geometry


def add_glyph(coll, e: GlyphEl, mat, z):
    cu = bpy.data.curves.new("g", "FONT")
    cu.body = e.ch
    cu.font = blender_font(e.font)
    cu.size = e.size * PX / em_factor(e.font)
    cu.align_x = "LEFT"
    cu.align_y = "BOTTOM_BASELINE"
    cu.shear = e.shear
    cu.resolution_u = 6
    if e.stroke_only:
        cu.fill_mode = "NONE"
        cu.bevel_depth = e.stroke[1] * PX / 2 if e.stroke else PX
        cu.bevel_resolution = 1
    else:
        cu.extrude = e.depth * PX / 2
        cu.bevel_depth = e.bevel * PX
        cu.bevel_resolution = 2
    ob = bpy.data.objects.new("g", cu)
    ob.data.materials.append(mat)
    place(ob, e, z)
    coll.objects.link(ob)
    return ob


def place(ob, e, z):
    """Position of the glyph origin: pivot + R(rot) S (origin - pivot) + (dx, dy); y down on screen, rot clockwise."""
    ox, oy = e.x - e.px, e.y - e.py
    ox, oy = ox * e.sx, oy * e.sy
    a = math.radians(e.rot)
    c, s = math.cos(a), math.sin(a)
    rx, ry = ox * c - oy * s, ox * s + oy * c       # y-down screen: positive angle = clockwise
    x, y = e.px + rx + e.dx, e.py + ry + e.dy
    ob.location = (wx(x), wy(y), z)
    ob.rotation_euler = (0, 0, -a)
    ob.scale = (e.sx, e.sy, 1.0)


def add_poly(coll, e: PolyEl, mat, z):
    me = bpy.data.meshes.new("p")
    vs = [(wx(x), wy(y), 0.0) for x, y in e.pts]
    me.from_pydata(vs, [], [tuple(range(len(vs)))])
    me.update()
    ob = bpy.data.objects.new("p", me)
    ob.data.materials.append(mat)
    ob.location = (0, 0, z)
    coll.objects.link(ob)
    return ob


# ---------------------------------------------------------------------------------------------------------------------
# frame build + compositor


class Stage:
    """A scene with one collection + view layer per group name; objects are rebuilt every frame."""

    def __init__(self, scale=1.0, samples=16):
        self.sc = setup_scene(scale, samples)
        self.layers = {}
        self.temp_objs = []

    def layer(self, name):
        if name not in self.layers:
            coll = bpy.data.collections.new(name)
            self.sc.collection.children.link(coll)
            vl = self.sc.view_layers.new(name)
            self.layers[name] = (coll, vl)
            # in every view layer only its own collection is enabled
            for n, (c, v) in self.layers.items():
                for lc in v.layer_collection.children:
                    lc.exclude = lc.name != n
        return self.layers[name]

    def clear(self):
        for ob in self.temp_objs:
            data = ob.data
            bpy.data.objects.remove(ob)
            if data and data.users == 0:
                (bpy.data.curves if isinstance(data, bpy.types.TextCurve) else bpy.data.meshes).remove(data)
        self.temp_objs = []
        for m in [m for m in bpy.data.materials if m.users == 0]:
            bpy.data.materials.remove(m)

    def build(self, frame: basic.Frame):
        self.clear()
        used = {}
        for g in frame.groups:
            coll, vl = self.layer(g.name)
            matcache = {}

            def mat_for(fill, op, lit):
                key = (fill, round(op, 3), lit)
                if key not in matcache:
                    matcache[key] = make_material(fill, op, lit)
                return matcache[key]

            for i, e in enumerate(sorted(g.elems, key=lambda e: e.z)):
                z = 0.02 * e.z + 0.0001 * (i % 50)
                if isinstance(e, GlyphEl):
                    if e.opacity <= 0.002:
                        continue
                    lit = e.bevel > 0
                    if e.stroke and not e.stroke_only:
                        st = replace(e, stroke_only=True, depth=0.0, bevel=0.0, fill=Solid(e.stroke[0]))
                        self.temp_objs.append(add_glyph(coll, st, mat_for(Solid(e.stroke[0]), e.opacity, False),
                                                        z - 0.005))
                    self.temp_objs.append(add_glyph(coll, e, mat_for(e.fill if not e.stroke_only else Solid(e.stroke[0]),
                                                                     e.opacity, lit and not e.stroke_only), z))
                else:
                    if e.opacity <= 0.002:
                        continue
                    self.temp_objs.append(add_poly(coll, e, mat_for(e.fill, e.opacity, False), z))
            if g.cut:
                coll2, _ = self.layer(g.name + ".cut")
                self.temp_objs.append(add_poly(coll2, PolyEl(g.cut, Solid((1, 1, 1))),
                                               mat_for(Solid((1, 1, 1)), 1.0, False), 0))
                used[g.name + ".cut"] = True
            used[g.name] = bool(coll.objects)
        for n, (c, vl) in self.layers.items():
            vl.use = used.get(n, False)
        self.compose(frame)

    # -- compositor --------------------------------------------------------------------------------------------------
    def compose(self, frame):
        sc = self.sc
        ng = bpy.data.node_groups.get("amv_titles")
        if ng:
            bpy.data.node_groups.remove(ng)
        ng = bpy.data.node_groups.new("amv_titles", "CompositorNodeTree")
        sc.compositing_node_group = ng
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        N = ng.nodes
        L = ng.links
        scale = sc.render.resolution_percentage / 100.0

        def blur(socket, r, ry=None, kind="Gaussian"):
            n = N.new("CompositorNodeBlur")
            n.inputs["Type"].default_value = kind
            n.inputs["Size"].default_value = (r * scale, (r if ry is None else ry) * scale)
            L.new(socket, n.inputs["Image"])
            return n.outputs["Image"]

        def math_(op, a, b=None, clamp=False):
            n = N.new("ShaderNodeMath")
            n.operation = op
            n.use_clamp = clamp
            for i, v in enumerate((a, b)):
                if v is None:
                    continue
                if isinstance(v, (int, float)):
                    n.inputs[i].default_value = v
                else:
                    L.new(v, n.inputs[i])
            return n.outputs["Value"]

        def halo(alpha_socket, rgb, gain, dx=0.0, dy=0.0):
            c = N.new("CompositorNodeRGB")
            c.outputs[0].default_value = (*lin3(rgb), 1)
            sa = N.new("CompositorNodeSetAlpha")
            sa.inputs["Type"].default_value = "Replace Alpha"
            L.new(c.outputs[0], sa.inputs["Image"])
            L.new(math_("MULTIPLY", alpha_socket, gain, clamp=True), sa.inputs["Alpha"])
            pm = N.new("CompositorNodePremulKey")
            pm.inputs["Type"].default_value = "To Premultiplied"
            L.new(sa.outputs["Image"], pm.inputs["Image"])
            out = pm.outputs["Image"]
            if dx or dy:
                tr = N.new("CompositorNodeTranslate")
                tr.inputs["X"].default_value = dx * scale
                tr.inputs["Y"].default_value = -dy * scale
                L.new(out, tr.inputs["Image"])
                out = tr.outputs["Image"]
            return out

        def over(bg, fg):
            if bg is None:
                return fg
            n = N.new("CompositorNodeAlphaOver")
            L.new(bg, n.inputs["Background"])
            L.new(fg, n.inputs["Foreground"])
            return n.outputs["Image"]

        acc = None
        for g in frame.groups:
            coll, vl = self.layers[g.name]
            if not vl.use:
                continue
            rl = N.new("CompositorNodeRLayers")
            rl.scene = sc
            rl.layer = g.name
            img, alpha = rl.outputs["Image"], rl.outputs["Alpha"]
            if g.cut:
                rc = N.new("CompositorNodeRLayers")
                rc.scene = sc
                rc.layer = g.name + ".cut"
                keep = math_("SUBTRACT", 1.0, rc.outputs["Alpha"], clamp=True)
                sa = N.new("CompositorNodeSetAlpha")
                sa.inputs["Type"].default_value = "Apply Mask"
                L.new(img, sa.inputs["Image"])
                L.new(keep, sa.inputs["Alpha"])
                img = sa.outputs["Image"]
                alpha = math_("MULTIPLY", alpha, keep)
            if g.smear:
                db = N.new("CompositorNodeBlur")
                db.inputs["Type"].default_value = "Gaussian"
                lx, ly = g.smear
                db.inputs["Size"].default_value = (lx * scale * 0.5, ly * scale * 0.5)
                L.new(img, db.inputs["Image"])
                img = db.outputs["Image"]
                alpha = blur(alpha, lx * 0.5, ly * 0.5)
            layer = img
            for gl in g.glows:
                # a bloom: two scales of the silhouette tinted by the glow colour, under the layer
                for r, w in ((gl.radius * 0.35, 0.55), (gl.radius, 0.45)):
                    h = halo(blur(alpha, r), gl.rgb, gl.intensity * w * 3.0)
                    layer = over(h, layer)
            if g.shadow:
                sh = halo(blur(alpha, g.shadow.soft), (0, 0, 0), g.shadow.opacity, g.shadow.dx, g.shadow.dy)
                layer = over(sh, layer)
            acc = over(acc, layer)
        if acc is None:
            rl = N.new("CompositorNodeRGB")
            rl.outputs[0].default_value = (0, 0, 0, 0)
            acc = rl.outputs[0]
        go = N.new("NodeGroupOutput")
        L.new(acc, go.inputs[0])


def render_frames(frame_fn, spec, ks, out_dir, scale=1.0, samples=16, log=print):
    """Render `frame_fn(spec, k)` for k in `ks` to out_dir/<k:04d>.png."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    st = Stage(scale, samples)
    # lay the view layers out in the order the groups first appear (so Alpha Over stacks bottom to top)
    for k in ks:
        fr = frame_fn(spec, k)
        st.build(fr)
        st.sc.render.filepath = str(out_dir / f"{k:04d}.png")
        bpy.ops.render.render(write_still=True)
        log(f"  frame {k}: {st.sc.render.filepath}")
    return st


def run_params(opts):
    """scale / samples from the dispatcher's options (`TitleOpts`), with defaults for a full-res CPU render."""
    return dict(scale=float(getattr(opts, "scale", 1.0) or 1.0), samples=int(getattr(opts, "samples", 24) or 24))
