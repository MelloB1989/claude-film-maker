"""A hero motif: an engraved glass bead, mirroring the engine's (app/src/engine/bead.ts): a glass sphere with a bore and
chamfered lips, a short text (a code, a version, a hash) etched round its face, frosted. It threads onto lib/thread.py's
threads (its bore along the thread) or stands alone as a product-style jewel.

The bead's own frame is the engine's: the bore runs along x (the thread passes through it), the engraving faces +z and
its letters stand up along +y. The geometry is bead.ts's lathe profile (`bead_profile`: the sphere from lip to lip, a
45 degree chamfer in to the bore at each end, and the bore's wall) turned round x. The engraving is laid on the great
circle through the bore and the face, as bead.ts lays it: a letter point at arc x along that circle and arc y off it
goes to the sphere at angle x / r round it and y / r up (`wrap_to_sphere`), so the letters keep their proportions on the
face and foreshorten as the surface turns away. It lies a hair proud of the glass's surface (a frosted etch is the
surface itself): under even a thin skin of glass Cycles could light it only through refraction, a caustic it barely
samples, and the letters render black.

Materials: clear satin glass (IOR 1.5, roughness 0.15, a light clear coat, as bead.ts), tinted a breath toward the
theme's fg, and the frosted etch (rough, opaque, in the theme's fg; it never glows). Colours are palette roles of the
theme in use (lib/theme.py).

The profile, the lathe and the wrap are numpy only (tested without Blender); the rest imports bpy.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np


def bead_profile(r: float, bore: float, chamfer: float, arc: int = 72) -> np.ndarray:
    """bead.ts beadProfile: (radius from the bore's axis, height along it), bottom lip to bottom lip, counter-clockwise:
    the sphere's arc between the lips, then the chamfers and the bore's wall."""
    lip = min(bore + chamfer, 0.9 * r)
    h_lip = math.sqrt(r * r - lip * lip)
    h_bore = h_lip - (lip - bore)
    phi = math.atan2(h_lip, lip)
    a = np.linspace(-phi, phi, arc + 1)
    pts = [(r * math.cos(x), r * math.sin(x)) for x in a]
    pts += [(bore, h_bore), (bore, -h_bore), (lip, -h_lip)]
    return np.array(pts, float)


def lathe(profile: np.ndarray, segments: int = 96) -> tuple[np.ndarray, list]:
    """The profile (radius, height) turned round the x axis (height along x): vertices (n, 3) and quad faces. The
    profile is closed (its last point joins its first) and so is the turn, so the mesh is watertight."""
    P = np.asarray(profile, float)
    m = len(P)
    a = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    verts = np.zeros((segments * m, 3))
    for i in range(segments):
        # the profile's radius goes round in (y, z); its height runs along x
        verts[i * m:(i + 1) * m] = np.column_stack([P[:, 1], P[:, 0] * np.sin(a[i]), P[:, 0] * np.cos(a[i])])
    faces = []
    for i in range(segments):
        i1 = (i + 1) % segments
        for j in range(m):
            j1 = (j + 1) % m
            faces.append((i * m + j, i * m + j1, i1 * m + j1, i1 * m + j))
    return verts, faces


def wrap_to_sphere(xy: np.ndarray, r: float) -> np.ndarray:
    """Points (n, 2) of a flat engraving, x along the great circle through the bore (+x) and the face (+z) and y up off
    it, both as arc lengths on a sphere of radius r, laid on that sphere: (n, 3) in the bead's frame."""
    xy = np.asarray(xy, float)
    al, be = xy[:, 0] / r, xy[:, 1] / r
    return np.column_stack([r * np.sin(al) * np.cos(be), r * np.sin(be), r * np.cos(al) * np.cos(be)])


def bead_basis(bore, face) -> np.ndarray:
    """The rotation (columns: the bead's x, y, z in the world) that puts its bore along `bore` and its engraving's face
    toward `face` (made square to the bore), its letters upright."""
    x = np.asarray(bore, float)
    x = x / np.linalg.norm(x)
    z = np.asarray(face, float) - x * (np.asarray(face, float) @ x)
    z /= np.linalg.norm(z)
    y = np.cross(z, x)
    return np.column_stack([x, y, z])


def glass_tint(color: str = "fg", amount: float = 0.1) -> tuple[float, float, float]:
    """The glass's colour (linear): white, `amount` of the way toward `color` (a palette role or '#rrggbb'), so clear
    glass picks up a breath of the film's own light."""
    from . import materials

    return tuple(1.0 + (c - 1.0) * amount for c in materials.linear(color))  # type: ignore[return-value]


# ---------------------------------------------------------------------------------------------------- Blender side

def glass_material(name: str = "bead_glass", *, tint: str = "fg"):
    """The bead's glass: clear satin (roughness 0.15), IOR 1.5, a light clear coat, tinted a breath toward `tint`."""
    import bpy

    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    b = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*glass_tint(tint), 1.0)
    b.inputs["Roughness"].default_value = 0.15
    b.inputs["IOR"].default_value = 1.5
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["Coat Weight"].default_value = 0.6
    b.inputs["Coat Roughness"].default_value = 0.06
    return mat


def etch_material(name: str = "bead_etch", *, color: str = "fg"):
    """The frosted etch: rough, opaque, in `color` (the theme's fg by default; it never glows)."""
    from . import materials

    mat, b = materials._principled(name)
    b.inputs["Base Color"].default_value = (*[0.9 * c for c in materials.linear(color)], 1.0)
    b.inputs["Roughness"].default_value = 0.85
    b.inputs["Specular IOR Level"].default_value = 0.3
    return mat


def bead_mesh(name: str, r: float, bore: float, chamfer: float, material, segments: int = 96):
    """The bead's glass as a smooth-shaded mesh in its own frame."""
    import bpy

    verts, faces = lathe(bead_profile(r, bore, chamfer), segments)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], faces)
    me.shade_smooth()
    me.materials.append(material)
    me.validate()
    return me


def etch_mesh(name: str, text: str, r: float, material, *, font: str | Path | None = None, em: float | None = None,
              lift: float = 0.004):
    """`text` as a flat mesh wrapped onto the bead (radius r) a hair proud of its surface (lift x r: clear of the
    faceted glass, whose faces lie inside the true sphere), centred on the face, at `em` (default bead.ts's: the band's
    length at 64%, in mono cells of 0.6 em). `font` is a font file (a film's, say films/<id>/fonts/...); None uses
    Blender's built-in font."""
    import bpy

    em = em if em is not None else 0.64 * 2 * 0.95 * r / (0.6 * max(1, len(text)))
    cu = bpy.data.curves.new(f"{name}.text", "FONT")
    cu.body = text
    if font is not None:
        font = Path(font)
        cu.font = bpy.data.fonts.get(font.name) or bpy.data.fonts.load(str(font))
    cu.size = em
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.resolution_u = 4
    ob = bpy.data.objects.new(f"{name}.text", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(cu)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    me.vertices.foreach_set("co", wrap_to_sphere(co[:, :2], r * (1 + lift)).ravel())
    me.name = name
    me.materials.append(material)
    me.update()
    return me
