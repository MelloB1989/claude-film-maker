"""room_shell — the closed room the studio sits in: walls, floor, ceiling and an oak baseboard.

Interior (studio cm): back wall x = -260, front wall x = +420, side walls y = +-330, floor 0, ceiling 300.
Walls, floor and ceiling are 15 cm thick, all outside the interior, so the only way in for light is
the window opening in the back wall (studio y = +130..+280, z = 0..285; Blender y = -1.30..-2.80,
since the FBX import mirrors Y). Origin: the world origin (the floor under the presenter).

Slots: M_Wall, M_Ceiling, M_Floor (planks run along X: U = x, 1 UV = 1 m), M_Baseboard (9 cm tall,
1.5 cm proud; none across the window, none behind the slat panel at studio y = -60..+110).

    blender -b --factory-startup -P room_shell.py -- --out out            # the shell and its previews
    blender -b --factory-startup -P room_shell.py -- --out out --combo    # room_combo.png from the four FBX
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import _studio as S  # noqa: E402
import _room_common as R  # noqa: E402

NAME = "room_shell"
combo = "--combo" in sys.argv
if combo:
    sys.argv.remove("--combo")
args = S.parse_args(__file__)
S.reset_scene()

T = R.WALL


# ------------------------------------------------------------------ shell: outer solid minus the interior and the window

def shell():
    WALLM = R.slot("M_Wall")
    outer = S.box("shell", (R.X_BACK - T, -R.Y_SIDE - T, -T), (R.X_FRONT + T, R.Y_SIDE + T, R.Z_CEIL + T), WALLM)
    for m in ("M_Ceiling", "M_Floor"):
        outer.data.materials.append(R.slot(m))
    inner = S.box("_cut_room", (R.X_BACK, -R.Y_SIDE, 0.0), (R.X_FRONT, R.Y_SIDE, R.Z_CEIL), WALLM)
    # the window cutter reaches 5 cm into the room so it shares no face with the back wall
    win = S.box("_cut_win", (R.X_BACK - T - 0.05, R.WIN_Y0, 0.0), (R.X_BACK + 0.05, R.WIN_Y1, R.WIN_Z1), WALLM)
    for cutter in (inner, win):
        mod = outer.modifiers.new(cutter.name, "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cutter
        cutter.hide_render = True
        cutter.display_type = "WIRE"
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(outer.evaluated_get(dg))
    for cutter in (inner, win):
        bpy.data.objects.remove(cutter, do_unlink=True)
    bpy.data.objects.remove(outer, do_unlink=True)
    ob = bpy.data.objects.new("shell", me)
    bpy.context.scene.collection.objects.link(ob)
    R.ensure_uv(ob)

    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.5), verts=bm.verts, edges=bm.edges)
    # concave n-gons (the back wall around the opening) are triangulated here, not by the importer
    big = [f for f in bm.faces if len(f.verts) > 4]
    bmesh.ops.triangulate(bm, faces=big, quad_method="BEAUTY", ngon_method="BEAUTY")
    names = [m.name for m in me.materials]
    i_wall, i_ceil, i_floor = names.index("M_Wall"), names.index("M_Ceiling"), names.index("M_Floor")
    for f in bm.faces:
        c = f.calc_center_median()
        n = f.normal
        inside = R.X_BACK - 1e-4 <= c.x <= R.X_FRONT + 1e-4 and abs(c.y) <= R.Y_SIDE + 1e-4
        if n.z > 0.9 and abs(c.z) < 1e-4:
            f.material_index = i_floor          # the room's floor (and the opening's bottom, under the sill)
        elif n.z < -0.9 and abs(c.z - R.Z_CEIL) < 1e-4 and inside:
            f.material_index = i_ceil
        else:
            f.material_index = i_wall
    bm.to_mesh(me)
    bm.free()
    return ob


# ------------------------------------------------------------------ baseboard

# (d into the room, z): square back, a soft 4 mm round on the top front edge, a 1 mm chamfer at the floor.
# The back and the bottom sit 0.5 mm inside the wall and floor, so there is no hairline and no coplanar face.
BB_H, BB_D = 0.090, 0.015
_r = 0.004
BB_PROFILE = ([(-0.0005, -0.0005), (BB_D - 0.001, -0.0005), (BB_D, 0.0005)]
              + [(BB_D - _r + _r * math.cos(a), BB_H - _r + _r * math.sin(a))
                 for a in (math.radians(t) for t in (0, 22.5, 45, 67.5, 90))]
              + [(-0.0005, BB_H)])


def baseboard_run(name, pts, mat):
    """Sweep BB_PROFILE along a wall path given counter-clockwise (the room on the left), mitred at corners."""
    pts = [Vector((x, y)) for x, y in pts]
    n = len(pts)
    segs = [(pts[i + 1] - pts[i]).normalized() for i in range(n - 1)]
    normals = [Vector((-d.y, d.x)) for d in segs]
    miters = []
    for i in range(n):
        if i == 0:
            miters.append(normals[0])
        elif i == n - 1:
            miters.append(normals[-1])
        else:
            a, b = normals[i - 1], normals[i]
            miters.append((a + b) / (1.0 + a.dot(b)))
    # path length at each point (for U), profile length at each profile point (for V)
    s = [0.0]
    for i in range(n - 1):
        s.append(s[-1] + (pts[i + 1] - pts[i]).length)
    arc = [0.0]
    for k in range(len(BB_PROFILE) - 1):
        arc.append(arc[-1] + (Vector(BB_PROFILE[k + 1]) - Vector(BB_PROFILE[k])).length)

    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    rings = []
    for i in range(n):
        rings.append([bm.verts.new((pts[i].x + miters[i].x * d, pts[i].y + miters[i].y * d, z))
                      for d, z in BB_PROFILE])
    m = len(BB_PROFILE)
    for i in range(n - 1):
        for k in range(m - 1):
            f = bm.faces.new((rings[i][k], rings[i + 1][k], rings[i + 1][k + 1], rings[i][k + 1]))
            uvs = ((s[i], arc[k]), (s[i + 1], arc[k]), (s[i + 1], arc[k + 1]), (s[i], arc[k + 1]))
            for lp, uv in zip(f.loops, uvs):
                lp[uvl].uv = uv
        # the back face (against the wall, hidden) closes the solid
        f = bm.faces.new((rings[i][m - 1], rings[i + 1][m - 1], rings[i + 1][0], rings[i][0]))
        for lp in f.loops:
            lp[uvl].uv = (s[i], 0.0)
    for i, sign in ((0, -1), (n - 1, 1)):
        f = bm.faces.new(rings[i] if sign < 0 else list(reversed(rings[i])))
        for lp in f.loops:
            d = (Vector(lp.vert.co.xy) - pts[i]).dot(miters[i])
            lp[uvl].uv = (s[i] + sign * d, lp.vert.co.z)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return S.obj_from_bm(bm, name, mat)


def baseboards():
    mat = R.slot("M_Baseboard")
    xb, xf, ys = R.X_BACK, R.X_FRONT, R.Y_SIDE
    # counter-clockwise seen from above: along the back wall that is towards -Y
    run_a = [(xb, R.WIN_Y0), (xb, -ys), (xf, -ys), (xf, ys), (xb, ys), (xb, R.PANEL_Y1)]
    run_b = [(xb, R.PANEL_Y0), (xb, R.WIN_Y1)]   # the short piece between the slat panel and the window
    return [baseboard_run("bb_a", run_a, mat), baseboard_run("bb_b", run_b, mat)]


# ------------------------------------------------------------------ build / export / previews

def build():
    parts = [shell()] + baseboards()
    ob = S.join(NAME, parts)
    S.set_origin(ob, (0, 0, 0))
    S.tidy(ob, sharp_angle=30)
    R.box_uv(ob, only_mats={"M_Wall", "M_Ceiling", "M_Floor"})
    return ob


def stats(ob, fbx):
    lo, hi = S.bbox(ob)
    print("=" * 60)
    print(f"{ob.name}: exported {fbx}")
    print(f"{ob.name}: materials {[m.name for m in ob.data.materials]}")
    print(f"{ob.name}: triangles {S.tri_count(ob)}")
    print(f"{ob.name}: bbox cm  X {lo.x*100:.1f}..{hi.x*100:.1f}  Y {lo.y*100:.1f}..{hi.y*100:.1f}"
          f"  Z {lo.z*100:.1f}..{hi.z*100:.1f}")
    print("=" * 60)


def dress_all():
    for m in bpy.data.materials:
        R.dress(m.name, m)


def interior(path, loc, look, lens, samples, exposure=0.0):
    R.camera(loc, look, lens)
    R.render(path, exposure=exposure)
    for o in list(bpy.data.objects):
        if o.name == "_cam":
            bpy.data.objects.remove(o, do_unlink=True)


def import_fbx(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        if o.type == "MESH":
            return o
    raise RuntimeError(f"nothing imported from {path}")


if combo:
    obs = {}
    for nm in ("room_shell", "window", "curtains", "rug"):
        obs[nm] = import_fbx(os.path.join(args.out, nm + ".fbx"))
        lo, hi = S.bbox(obs[nm])
        print(f"imported {nm}: bbox cm X {lo.x*100:.1f}..{hi.x*100:.1f} Y {lo.y*100:.1f}..{hi.y*100:.1f}"
              f" Z {lo.z*100:.1f}..{hi.z*100:.1f}")
    dress_all()
    R.use_cycles(args.samples)
    R.sun_and_sky()
    # the studio camera's place: studio (x = +230, y = 0, z = 165), looking at the back wall
    interior(os.path.join(args.out, "room_combo.png"), (2.30, 0.0, 1.65), (R.X_BACK, -0.55, 1.30), 20.0,
             args.samples, exposure=1.6)
    # and a closer look at the window wall: the sheer's folds against the light
    interior(os.path.join(args.out, "room_combo_window.png"), (0.6, 0.4, 1.35), (R.X_BACK, -2.05, 1.25), 28.0,
             args.samples, exposure=1.6)
else:
    ob = build()
    os.makedirs(args.out, exist_ok=True)
    fbx = os.path.join(args.out, NAME + ".fbx")
    S.export_fbx(ob, fbx)
    stats(ob, fbx)
    if not args.no_render:
        dress_all()
        R.use_cycles(args.samples)
        R.sun_and_sky()
        interior(os.path.join(args.out, NAME + ".png"), (3.95, 3.05, 2.55), (R.X_BACK, -1.6, 0.7), 16.0,
                 args.samples, exposure=1.6)
        interior(os.path.join(args.out, NAME + "_front.png"), (4.05, 0.0, 1.45), (R.X_BACK, -0.3, 1.40), 18.0,
                 args.samples, exposure=1.6)
