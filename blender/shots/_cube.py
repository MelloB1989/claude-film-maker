"""Test shot for plates and tracks (Review Focus 4). Film frames 40-59.

A satin bone cube in the ink studio, spinning a degree a frame while the camera trucks right, pans and pushes in, so
its top-right corner crosses the frame at about 10 px a frame at 1080p: showing the wrong plate frame, or the track a
frame off, misses by far more than the 2 px allowed. An empty `corner` rides that corner (parented to the spinning
cube) and is tracked. The film frame number is burned into the render at the lower left (a text object riding the
camera), so a still shows which plate frame it got. Below the cube run a bone thread and a glowing blood strand: a
smoke test of thread.ply_thread and materials.fiber.

  Blender -b -P blender/render.py -- --shot _cube --mode look --res 1920x1080
  (app) bun scripts/render.ts stills --module _platetest --t 1.4333333333333333,1.9
"""
SHOT = {"scene": "_cube", "frames": [40, 60], "track": ["corner"]}

FONT = "app/public/fonts/JetBrainsMono-700.ttf"


def build(ctx):
    import math

    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector

    from lib import export, lights, materials, thread, timing

    scene = ctx.scene
    coll = scene.collection

    # the cube: 1 m, sharp, spinning 1 degree a frame from 25 degrees
    h = 0.5
    verts = [(x, y, z) for x in (-h, h) for y in (-h, h) for z in (-h, h)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me = bpy.data.meshes.new("cube")
    me.from_pydata(verts, [], faces)
    me.materials.append(materials.satin("bone"))
    cube = bpy.data.objects.new("cube", me)
    coll.objects.link(cube)
    for f in (ctx.f0, ctx.f1 - 1):
        cube.rotation_euler = (0.0, 0.0, math.radians(25 + (f - ctx.f0)))
        cube.keyframe_insert("rotation_euler", frame=f)
    _linear_keys(cube)

    # the camera trucks right 0.9 m, pans 3 degrees and pushes in 0.6 m over the shot (no constraint: keyed outright)
    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    cam.data.lens = 50
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.sensor_width = 36
    coll.objects.link(cam)
    scene.camera = cam
    for f, x, y, look_x in ((ctx.f0, -0.45, -7.0, 0.35), (ctx.f1 - 1, 0.45, -6.4, -0.02)):
        cam.location = (x, y, 2.1)
        cam.rotation_euler = (Vector((look_x, 0.0, -0.25)) - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    _linear_keys(cam)

    # the empty on the corner that is top-right in the middle of the shot
    scene.frame_set((ctx.f0 + ctx.f1) // 2)
    dg = bpy.context.evaluated_depsgraph_get()
    cam_ev = cam.evaluated_get(dg)
    mw = cube.evaluated_get(dg).matrix_world

    def score(v):
        co = world_to_camera_view(scene, cam_ev, mw @ Vector(v))
        return co.x + co.y

    corner = bpy.data.objects.new("corner", None)
    corner.empty_display_size = 0.1
    corner.parent = cube
    corner.location = max(verts, key=score)
    coll.objects.link(corner)

    lights.studio()

    # threads below the cube
    thread.ply_thread([(-1.9, -0.5, -0.62), (-0.6, -0.95, -0.7), (0.7, -0.8, -0.6), (1.9, -0.35, -0.5)], 0.035,
                      material=materials.fiber("bone", sheen=0.6), name="bone_thread")
    thread.ply_thread([(-1.9, -0.3, -0.8), (-0.5, -0.7, -0.78), (0.8, -0.55, -0.72), (1.9, -0.1, -0.66)], 0.016,
                      plies=2, fuzz=False, material=materials.fiber("blood", sheen=0.4, emissive=2.5),
                      name="blood_strand")

    # the film frame number, burned in at the lower left: 1 m in front of the camera, 100 px in from the corner
    fcu = bpy.data.curves.new("burn", "FONT")
    fcu.font = bpy.data.fonts.load(str(export.REPO / FONT))
    px = 36 / 50 / 1920  # m per px at 1 m in front of the camera (36 mm sensor, 50 mm lens)
    fcu.size = 80 * px
    fcu.body = str(ctx.f0)
    burn = bpy.data.objects.new("burn", fcu)
    burn.data.materials.append(materials.emission("bone", 1.0))
    burn.parent = cam
    burn.location = (-960 * px + 100 * px, -540 * px + 100 * px, -1.0)
    for k in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
        setattr(burn, k, False)
    coll.objects.link(burn)

    def burn_frame(sc, *_):
        # the frame's own number on every motion-blur step of it (a step can sit a quarter frame either side)
        c = bpy.data.curves.get("burn")
        if c is not None:
            c.body = str(timing.js_round(sc.frame_current + sc.frame_subframe))

    bpy.app.handlers.frame_change_pre.append(burn_frame)


def _linear_keys(ob):
    """Linear interpolation on every key of the object's action (Blender 5 keeps F-curves in slots and layers)."""
    act = ob.animation_data.action
    curves = []
    if hasattr(act, "layers") and act.layers:
        for layer in act.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves.extend(bag.fcurves)
    elif hasattr(act, "fcurves"):
        curves.extend(act.fcurves)
    for fc in curves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
