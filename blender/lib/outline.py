"""Anime outlines for Blender shots: the clean, even line round a character that toon shading alone never draws, and
smooth shading under it, so a character reads as drawn rather than as a low-poly model.

- `hull(ob, px, ...)`: an inverted hull. A linked copy of the object (the same mesh, skinning and modifiers, so it
  follows the armature, the breath and the wind) pushed out along its normals by a width that stays `px` pixels on
  screen at any distance from the active camera (Geometry Nodes), drawn in ink on its back faces only, so only a rim
  shows round the silhouette, smooth however coarse the mesh. Its `outline` vertex group, where it has one, thins it
  (fingertips, a lock's tip). Kept out of the Line Art and the shadows.
- `apply(collection, px, ...)`: hulls on the meshes of a collection worth one; `skip(ob)` leaves some out, and so does
  a custom property `outline` set False on an object (eyes, brows, fine straw).
- `ink_tone(color)`: an outline's colour from a surface's: a deep dark of the same hue, near black for dark things, so
  the line round a red headband reads dark red-brown and round skin a warm brown.
- `pixel_scale(lens_mm, sensor_mm, res_px)`: metres on screen per pixel per metre from the camera.
- `taper(ob, factors)`: the `outline` vertex group from the bones' groups (the fingers, the toes thinner).
- `smooth_normals(ob, iterations)`: custom normals blurred across the surface after its skinning, so toon bands follow
  the broad form rather than every facet and fold of the mesh.

`ink_tone` and `pixel_scale` are pure Python and tested without Blender.
"""
from __future__ import annotations

import colorsys

RGB = tuple[float, float, float]

GROUP = "outline-hull"       # the Geometry Nodes group pushing a hull out
SMOOTH = "outline-smooth"    # the Geometry Nodes group blurring normals


def pixel_scale(lens_mm: float, sensor_mm: float = 36.0, res_px: int = 1920) -> float:
    """Metres on screen per pixel, per metre of distance from a camera of `lens_mm` on a `sensor_mm` wide gate
    rendering `res_px` across: width (m) = px * pixel_scale * distance."""
    return sensor_mm / (lens_mm * res_px)


def ink_tone(color: RGB, *, value: float = 0.012, saturation: float = 1.25) -> RGB:
    """An outline colour for a surface of `color` (linear RGB): the same hue at `value` (linear: 0.012 shows as about
    11% grey), more saturated, so it reads as that colour's ink; greys and dark colours come out a near-neutral
    black."""
    h, s, v = colorsys.rgb_to_hsv(*[max(0.0, c) for c in color])
    s = min(1.0, s * saturation) if v > 0.08 else s * 0.5
    return colorsys.hsv_to_rgb(h, s, min(v, value))


def _group(name: str = GROUP, px: float = 2.5, scale: float | None = None):
    """The node group pushing a set of hulls out: offset = normal * px * scale * distance to the active camera *
    weight. One group per set of hulls, its width in two Value nodes ("pixels", "scale": set_width changes them)."""
    import bpy

    ng = bpy.data.node_groups.get(name)
    if ng is not None:
        return ng
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gin, gout = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    vals = {}
    for key, v in (("pixels", px), ("scale", scale if scale is not None else pixel_scale(30.0))):
        n = N.new("ShaderNodeValue")
        n.name = n.label = key
        n.outputs[0].default_value = float(v)
        vals[key] = n.outputs[0]
    me = N.new("GeometryNodeSelfObject")
    me_info = N.new("GeometryNodeObjectInfo")
    me_info.transform_space = "ORIGINAL"
    L.new(me.outputs[0], me_info.inputs["Object"])
    cam = N.new("GeometryNodeInputActiveCamera")
    cam_info = N.new("GeometryNodeObjectInfo")
    cam_info.transform_space = "ORIGINAL"
    L.new(cam.outputs[0], cam_info.inputs["Object"])
    pos = N.new("GeometryNodeInputPosition")
    world = N.new("FunctionNodeTransformPoint")
    L.new(pos.outputs[0], world.inputs["Vector"])
    L.new(me_info.outputs["Transform"], world.inputs["Transform"])
    dist = N.new("ShaderNodeVectorMath")
    dist.operation = "DISTANCE"
    L.new(world.outputs[0], dist.inputs[0])
    L.new(cam_info.outputs["Location"], dist.inputs[1])

    def math(op, a, b):
        m = N.new("ShaderNodeMath")
        m.operation = op
        for sock, x in ((m.inputs[0], a), (m.inputs[1], b)):
            if isinstance(x, (int, float)):
                sock.default_value = x
            else:
                L.new(x, sock)
        return m.outputs[0]

    # the weight: the "outline" group where the mesh has one, else 1
    attr = N.new("GeometryNodeInputNamedAttribute")
    attr.data_type = "FLOAT"
    attr.inputs["Name"].default_value = "outline"
    has = attr.outputs["Exists"]
    weight = math("ADD", math("MULTIPLY", attr.outputs["Attribute"], has), math("SUBTRACT", 1.0, has))
    width = math("MULTIPLY", math("MULTIPLY", vals["pixels"], vals["scale"]), dist.outputs["Value"])
    width = math("MULTIPLY", width, weight)
    nrm = N.new("GeometryNodeInputNormal")
    off = N.new("ShaderNodeVectorMath")
    off.operation = "SCALE"
    L.new(nrm.outputs["Normal"], off.inputs[0])
    L.new(width, off.inputs["Scale"])
    setp = N.new("GeometryNodeSetPosition")
    L.new(gin.outputs["Geometry"], setp.inputs["Geometry"])
    L.new(off.outputs[0], setp.inputs["Offset"])
    L.new(setp.outputs["Geometry"], gout.inputs["Geometry"])
    return ng


def ink_material(name: str, color: RGB, *, look=None):
    """An outline's material: `color` (faded to the look's fog like any toon colour) on back faces only; front faces
    are see-through, so a pushed-out copy shows only as a rim round the original's silhouette."""
    import bpy

    from . import toon

    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    rgb = nt.nodes.new("ShaderNodeRGB")
    rgb.outputs[0].default_value = (*color, 1.0)
    col = toon._fog_mix(nt, rgb.outputs[0], look) if look is not None else rgb.outputs[0]
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(geo.outputs["Backfacing"], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "DITHERED"
    mat.use_backface_culling = False
    mat.use_backface_culling_shadow = True
    return mat


def _tone_of(mat, default: RGB) -> RGB:
    lit = mat.get("toon_lit") if mat is not None else None
    return ink_tone(tuple(lit)) if lit else default


def hull(ob, px: float = 2.5, *, scale: float | None = None, color: RGB | None = None, look=None, coll=None,
         keep_smoothing: bool = False, group: str = GROUP):
    """An inverted-hull outline round `ob`, `px` pixels wide on screen (at the render's width for `scale`, metres per
    pixel per metre: pixel_scale; default a 30 mm lens on 36 mm at 1920 across). Its colour is `color`, else each
    material's ink tone. Hulls sharing a `group` share one width (the first one's; set_width changes it). Returns the
    hull object (a linked copy with its own modifier and materials)."""
    import bpy

    h = ob.copy()                       # shares the mesh: the same skinning, groups and edits
    h.name = f"{ob.name}-outline"
    for c in (coll,) if coll is not None else ob.users_collection:
        c.objects.link(h)
    for m in list(h.modifiers):
        if m.type == "NODES" and m.node_group is not None and m.node_group.name.startswith(SMOOTH) and not keep_smoothing:
            h.modifiers.remove(m)       # shading normals mean nothing to an outline
    mod = h.modifiers.new("outline", "NODES")
    mod.node_group = _group(group, px, scale)
    dark = (0.012, 0.011, 0.014)
    slots = h.material_slots
    if len(slots) == 0:
        h.data.materials.append(None)
    for slot in h.material_slots:
        tone = color or _tone_of(slot.material, dark)
        slot.link = "OBJECT"
        key = "%.3f-%.3f-%.3f" % tone
        slot.material = ink_material(f"outline-{key}", tone, look=look)
    h.visible_shadow = False
    h.lineart.usage = "EXCLUDE"
    h["outline"] = False
    h["outline_of"] = ob.name
    return h


def set_width(px: float | None = None, scale: float | None = None, group: str = GROUP):
    """Change a set of hulls' on-screen width or pixel scale (a close-up after a wide shot, a different lens)."""
    import bpy

    ng = bpy.data.node_groups.get(group)
    if ng is None:
        return
    if px is not None:
        ng.nodes["pixels"].outputs[0].default_value = float(px)
    if scale is not None:
        ng.nodes["scale"].outputs[0].default_value = float(scale)


def wants_hull(ob, *, min_size: float = 0.03, decal: float = 0.003) -> bool:
    """Whether a mesh is worth an outline: not marked `outline` False or `decal` (a drawing laid over a face), not kept
    out of the ink by its builder (Line Art
    usage occlusion-only or excluded: fine straw, a filler under hair), at least `min_size` across (not an eyeball),
    and not a decal lying on a surface (thinner than `decal` and under 0.25 m: a brow, an age line)."""
    if ob.type != "MESH" or ob.get("outline", True) is False or ob.get("decal") or ob.hide_render:
        return False
    if ob.lineart.usage in ("OCCLUSION_ONLY", "EXCLUDE"):
        return False
    d = sorted(ob.dimensions)
    if d[2] < min_size:
        return False
    return not (d[0] < decal and d[2] < 0.25)


def apply(collection, px: float = 2.5, *, scale: float | None = None, skip=None, min_size: float = 0.03, look=None,
          group: str = GROUP) -> list:
    """Hulls on every mesh in `collection` (and its children) that `wants_hull` and not `skip(ob)`, all sharing one
    width (`group`). Returns the hulls."""
    out = []
    for ob in list(collection.all_objects):
        if not wants_hull(ob, min_size=min_size):
            continue
        if skip is not None and skip(ob):
            continue
        out.append(hull(ob, px, scale=scale, look=look, group=group))
    return out


def taper(ob, factors: dict) -> None:
    """The `outline` vertex group on a skinned mesh from its bones' groups: each vertex's weight is 1 (or its weight in
    an `outline-scale` group where the mesh has one: a builder thinning the line somewhere, animeface round a drawn
    nose) less, for every bone group whose name starts with a key of `factors`, its weight there times (1 - factor):
    {"finger": 0.35} makes the line round the fingers about a third as wide."""
    g = ob.vertex_groups.get("outline") or ob.vertex_groups.new(name="outline")
    names = {vg.index: vg.name for vg in ob.vertex_groups}
    scale = ob.vertex_groups.get("outline-scale")
    for v in ob.data.vertices:
        w = 1.0
        if scale is not None:
            w = next((e.weight for e in v.groups if e.group == scale.index), 1.0)
        for e in v.groups:
            n = names.get(e.group, "")
            for prefix, f in factors.items():
                if n.startswith(prefix):
                    w -= e.weight * (1.0 - f)
        g.add([v.index], max(0.05, min(1.0, w)), "REPLACE")


def smooth_normals(ob, iterations: int = 6) -> None:
    """Custom normals blurred `iterations` times across the surface, after everything else the object does (its
    skinning, its subdivision): toon bands then follow the broad form, not the facets and small folds of the mesh."""
    import bpy

    name = f"{SMOOTH}-{iterations}"
    ng = bpy.data.node_groups.get(name)
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
        ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        N, L = ng.nodes, ng.links
        gin, gout = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
        nrm = N.new("GeometryNodeInputNormal")
        blur = N.new("GeometryNodeBlurAttribute")
        blur.data_type = "FLOAT_VECTOR"
        blur.inputs["Iterations"].default_value = iterations
        L.new(nrm.outputs["Normal"], blur.inputs["Value"])
        unit = N.new("ShaderNodeVectorMath")
        unit.operation = "NORMALIZE"
        L.new(blur.outputs["Value"], unit.inputs[0])
        setn = N.new("GeometryNodeSetMeshNormal")
        setn.mode = "FREE"
        setn.domain = "POINT"
        L.new(gin.outputs["Geometry"], setn.inputs["Mesh"])
        L.new(unit.outputs[0], setn.inputs["Custom Normal"])
        L.new(setn.outputs["Mesh"], gout.inputs["Geometry"])
    mod = ob.modifiers.new("smooth shading", "NODES")
    mod.node_group = ng
