"""Geometry of the SAU_EDITZ outro: extruded bevelled glyph meshes in Blender, laid out like outro.jsx's `_layout`.

Each letter is its own mesh object whose origin sits at the glyph's centre, so it spins about its own middle. Faces are
sorted into three material slots from their normals (front / bevel / side), because a text curve has a single slot:
red face, light bevel, navy sides (handover ref 06 §3). The font has no `_` glyph, so the underscore is a bevelled bar.
Faces look at the camera at -Y, text up is +Z; 1 BU = 100 AE px (`outro_schedule.PX`).
"""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix

from . import outro_schedule as sch

FRONT, BEVEL, SIDE = 0, 1, 2
CAP = 3.79                    # BU: the AE word is 379 px high at size 470
EXTRUDE = 0.60                # BU half depth of the extrusion (AE: 70 px deep; a little more reads better)
BEVEL_DEPTH = 0.10
GAP = 0.13                    # of the font size, outro.jsx `gap = size * 0.13`
WORD_W = 14.21                # BU: the AE word is 1421 px wide
BAR_W = 0.42                  # underscore width in cap heights (outro.jsx clamps it to 0.42 x size)


def _glyph_mesh(ch, font, size, extrude, bevel):
    """Mesh of one character as a text curve: in the XY plane, extruded along Z (not yet standing up)."""
    cu = bpy.data.curves.new(f"g_{ch}", "FONT")
    cu.body = ch
    cu.font = font
    cu.size = size
    cu.extrude = extrude
    cu.bevel_depth = bevel
    cu.bevel_resolution = 4
    cu.resolution_u = 12
    cu.align_x = "LEFT"
    cu.align_y = "BOTTOM_BASELINE"
    ob = bpy.data.objects.new(f"g_{ch}", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return me


def _stand_up(me):
    """Text plane XY -> XZ (up = +Z), extrusion +Z -> -Y so the front looks at the camera."""
    me.transform(Matrix.Rotation(math.pi / 2, 4, "X"))


def _bounds(me):
    xs = [v.co.x for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    return min(xs), max(xs), min(zs), max(zs)


def assign_materials(me, mats):
    """Front / bevel / side by polygon normal (front looks at -Y); smooth shading across bevel rings only."""
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
    for p in me.polygons:
        ny = -p.normal.y
        p.material_index = FRONT if ny > 0.93 else (SIDE if abs(p.normal.y) < 0.2 else BEVEL)
        p.use_smooth = p.material_index == BEVEL
    me.update()


def _bar_mesh(w, h, depth, bevel):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= w
        v.co.y *= depth * 2
        v.co.z *= h
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=4, profile=0.6, affect="EDGES")
    me = bpy.data.meshes.new("g__")
    bm.to_mesh(me)
    bm.free()
    return me


def build_letters(font_path, mats, collection):
    """Create the 9 letter objects. Returns (objects, layout) where layout has each slot's rest position (BU) and the
    word's size; objects are named `L<slot> <ch>` and sit at their rest positions (the animation offsets from there).
    The word is sized to the AE layout: 14.21 BU wide (1421 px), at most CAP high."""
    font = bpy.data.fonts.load(str(font_path))
    # the cap box and every glyph's width at size 1; everything is linear in the font size
    trial = _glyph_mesh("SAUEDITZ", font, 1.0, 0.0, 0.0)
    _stand_up(trial)
    _, _, z0, z1 = _bounds(trial)
    bpy.data.meshes.remove(trial)
    unit = {}
    for ch in sch.WORD:
        if ch != "_" and ch not in unit:
            m = _glyph_mesh(ch, font, 1.0, 0.0, 0.0)
            _stand_up(m)
            a, b, _, _ = _bounds(m)
            unit[ch] = b - a
            bpy.data.meshes.remove(m)
    cap1 = z1 - z0
    w1 = [unit[ch] if ch != "_" else BAR_W * cap1 for ch in sch.WORD]
    total1 = sum(w1) + GAP * (len(w1) - 1)
    size = min(CAP / cap1, WORD_W / total1)
    k = size * cap1 / CAP                       # how much smaller than the AE cap height the word came out
    extrude, bevel = EXTRUDE * k, BEVEL_DEPTH * k
    parts = []
    gap = size * GAP
    for ch in sch.WORD:
        if ch == "_":
            me = _bar_mesh(BAR_W * cap1 * size, 0.12 * cap1 * size, extrude, bevel)
            cx, cz = 0.0, -cap1 * size * 0.54    # just under the baseline
            w = BAR_W * cap1 * size
        else:
            me = _glyph_mesh(ch, font, size, extrude, bevel)
            _stand_up(me)
            a, b, c, d = _bounds(me)
            cx, cz = (a + b) / 2, (c + d) / 2
            w = b - a
            me.transform(Matrix.Translation((-cx, 0, -cz)))
        parts.append([ch, me, w, cz])
    total = sum(p[2] for p in parts) + gap * (len(parts) - 1)
    cap_c = (z0 + z1) / 2 * size                # centre of the cap box: the word is centred on z = 0
    objs, layout, x = [], [], -total / 2
    for slot, (ch, me, w, cz) in enumerate(parts):
        assign_materials(me, mats)
        ob = bpy.data.objects.new(f"L{slot} {ch}", me)
        collection.objects.link(ob)
        px = x + w / 2
        pz = (cz - cap_c) if ch != "_" else cz
        ob.location = (px, 0.0, pz)
        ob["rest"] = (px, 0.0, pz)
        objs.append(ob)
        layout.append({"ch": ch, "x": px, "z": pz, "w": w})
        x += w + gap
    return objs, {"slots": layout, "width": total, "height": cap1 * size, "size": size}
