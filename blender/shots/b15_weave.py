"""B15 `weave`: the film's threads converge out of the dark and weave the GitLoom mark (spec §4 15, Plan 2 Task 12).

The woven mark is blender/mark (traced from web/public/mark.png: front silhouette IoU 0.98 against it, validate.py).
Four threads lay its hash in the weave's order: bone, moss, blood and moss arrive from the dark in long arcs, flatten
into satin ribbons as they run into the mark, pass over and under each other, and change colour only under a
crossing (the diff happens inside the weave). The hook's thread lands last: the blood crossbar over the stem to its
leaf, on the scene's first downbeat after the cut (its own first one is the cut), in a 0.5x speed ramp
(mark/choreo.py); the weave cinches and the ribbons' edges flare. Then a slow push-in, a light sweep across the satin
(a strip only reflections see, aimed through the mirror so its sheen runs over the faces and along the rounded edges)
and the mark's slight turn settling square to the camera by the last downbeat, on the left third so the engine can
set the type beside it (app/src/scenes/weave.ts). The light is plain white: lit bone keeps bone's hue.

  /Applications/Blender.app/Contents/MacOS/Blender -b -P blender/render.py -- --shot b15_weave --mode look
  (preview: --mode preview; stills at 1080p: --mode look --res 1920x1080 --frames ...)

Tracks: the mark's bounding corners and centre (mark_tl, mark_tr, mark_bl, mark_br, mark_c) and the crossbar's leaf
(lock), for the engine's type and accents.
"""
from lib import timing as _timing

from mark import choreo as _choreo

_T = _choreo.times(_timing.film())
# look frames: mid-weave on "GitLoom.", the lock + 0.3 s, the final frame (the end - 0.5 s)
LOOK = [round(_T.l30 * 30), _T.lock_frame + 9, _T.f1 - 15]
SHOT = {
    "scene": "weave",
    "frames": "scene",
    "track": ["mark_tl", "mark_tr", "mark_bl", "mark_br", "mark_c", "lock"],
    "look": ",".join(str(f) for f in LOOK),
}

LENS = 85.0
SENSOR = 36.0
SWEEP_DIST = 0.55  # m from the mark to the sweep strip
# (name, kind, position m, aimed at, size m (disk) / (x, y) (rectangle) / soft radius (spot), watts). All plain white:
# lit bone keeps bone's own hue (the plate measures (0.80, 0.75, 0.77) where lit, blood and moss at their palette
# values: blender/mark/measure.py).
LIGHTS = [
    ("key", "AREA", (-0.36, -0.5, 0.42), (0.02, 0.0, 0.0), 0.32, 6.4),
    ("top", "AREA", (0.05, 0.1, 0.55), (0.0, 0.0, 0.0), (0.9, 0.07), 9.0),
    ("fill", "AREA", (1.0, -1.3, -0.4), (0.0, 0.0, 0.0), 1.4, 1.6),
    ("rim", "SPOT", (1.1, 0.9, 0.35), (0.0, 0.0, 0.0), 0.03, 50.0),
]
# a soft card that only reflections see, placed by the mirror so the satin's sheen falls on the mark's upper left
# and fades across it (the card's own gradient)
SHEEN = {"size": (0.34, 0.26), "on": (-0.05, 0.05), "dist": 0.95, "level": 2.4}


def build(ctx):
    import math

    import bpy
    import numpy as np
    from mathutils import Euler, Vector

    from lib import lights
    from mark import build as B, choreo as C, geometry as G, strands as S

    scene = ctx.scene
    coll = scene.collection
    T = C.times(ctx.timing)
    frames = np.arange(ctx.f0, ctx.f1 + 1, 0.5)  # half-frame keys: the motion-blur steps see the eased curves
    taus = [C.tau(T, f) for f in frames]

    # the mark: MU (mark px) scaled to metres, turned and breathing as a whole
    root = bpy.data.objects.new("mark", None)
    coll.objects.link(root)
    rx, rz, sc = [], [], []
    for ta in taus:
        pose = C.mark_pose(T, ta)
        rx.append(math.radians(pose["pitch"]))
        rz.append(math.radians(pose["yaw"]))
        sc.append(B.MU * pose["scale"])
    root.rotation_mode = "XYZ"
    root.rotation_euler = (rx[0], 0.0, rz[0])
    root.scale = (sc[0],) * 3
    _series(root, "rotation_euler", 0, frames, rx)
    _series(root, "rotation_euler", 2, frames, rz)
    for i in range(3):
        _series(root, "scale", i, frames, sc)

    # the threads, their windows keyed through the shot
    strands = S.all_strands()
    for name, st in strands.items():
        ob = B.thread_object(st, parent=root, coll=coll)
        ws = [C.window(T, name, st, ta) for ta in taus]
        for k in B.INPUTS[:7]:
            B.key_series(ob, B.input_path(ob, k), frames, [w[k] for w in ws])
        B.key_series(ob, B.input_path(ob, "glow"), frames, [C.ribbon_glow(T, ta) for ta in taus])

    # anchors for the engine: the mark's bounding corners and centre, and the crossbar's leaf
    p = G.load_params()
    x0, x1 = p["cross_x0"], p["bar_x1"]
    y0, y1 = p["g_cy"] - p["g_r"] - p["g_ho"][1], p["hook_y1"]
    for name, (x, y) in {"mark_tl": (x0, y0), "mark_tr": (x1, y0), "mark_bl": (x0, y1), "mark_br": (x1, y1),
                         "mark_c": ((x0 + x1) / 2, (y0 + y1) / 2), "lock": (x0, p["cross_y"])}.items():
        e = bpy.data.objects.new(name, None)
        e.parent = root
        e.location = (x - G.SIZE / 2, 0.0, G.SIZE / 2 - y)
        coll.objects.link(e)

    # the camera: 85 mm, looking down +Y at the mark, trucking and pushing in; focus on the mark's plane
    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    cam.data.lens = LENS
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.sensor_width = SENSOR
    cam.data.clip_start = 0.05
    cam.data.clip_end = 60.0
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_blades = 7
    cam.data.dof.aperture_rotation = math.radians(10)
    coll.objects.link(cam)
    scene.camera = cam
    cam.rotation_euler = Euler((math.pi / 2, 0.0, 0.0))
    cx, cy, fd, fs = [], [], [], []
    for ta in taus:
        c = C.camera(T, ta)
        cx.append(c["x"])
        cy.append(-c["d"])
        fd.append(c["d"])
        fs.append(c["fstop"])
    cam.location = (cx[0], cy[0], 0.0)
    _series(cam, "location", 0, frames, cx)
    _series(cam, "location", 1, frames, cy)
    cam.data.dof.focus_distance = fd[0]
    cam.data.dof.aperture_fstop = fs[0]
    _series(cam.data, "dof.focus_distance", -1, frames, fd)
    _series(cam.data, "dof.aperture_fstop", -1, frames, fs)

    # the light: a close softbox key from the upper left (its falloff grades the satin across the mark), a long thin
    # strip above and a little behind that grazes the top faces and rounded edges, a low broad fill from the right,
    # and a kicker from behind on the right; the world is ink
    lights.world_color("ink")
    rig = {}
    for name, kind, pos, aim, size, energy in LIGHTS:
        data = bpy.data.lights.new(name, kind)
        data.energy = energy
        data.color = (1.0, 1.0, 1.0)
        if kind == "AREA":
            if isinstance(size, tuple):
                data.shape, data.size, data.size_y = "RECTANGLE", size[0], size[1]
            else:
                data.shape, data.size = "DISK", size
        else:
            data.spot_size, data.spot_blend, data.shadow_soft_size = math.radians(40), 0.4, size
        ob = bpy.data.objects.new(name, data)
        ob.location = pos
        ob.rotation_euler = (Vector(aim) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
        coll.objects.link(ob)
        rig[name] = ob
    rim = rig["rim"]
    rim_w = rim.data.energy
    _series(rim.data, "energy", -1, frames, [rim_w * C.light(T, ta)["rim"] for ta in taus])

    # the sheen card: static, seen only in the coat and specular reflections, aimed through the mark's final pose
    cm = bpy.data.meshes.new("sheen")
    cw, chh = SHEEN["size"][0] / 2, SHEEN["size"][1] / 2
    cm.from_pydata([(-cw, 0, -chh), (cw, 0, -chh), (cw, 0, chh), (-cw, 0, chh)], [], [(0, 1, 2, 3)])
    uv = cm.uv_layers.new(name="uv")
    for li, co in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[li].uv = co
    card = bpy.data.objects.new("sheen", cm)
    end = C.camera(T, taus[-1])
    on = Vector((SHEEN["on"][0], 0.0, SHEEN["on"][1]))
    dvec = (on - Vector((end["x"], -end["d"], 0.0))).normalized()
    rvec = dvec - 2 * dvec.dot(Vector((0.0, -1.0, 0.0))) * Vector((0.0, -1.0, 0.0))
    card.location = on + rvec * SHEEN["dist"]
    card.rotation_euler = (-rvec).to_track_quat("-Y", "Z").to_euler()
    coll.objects.link(card)
    cmat = bpy.data.materials.new("sheen")
    if cmat.node_tree is None:
        cmat.use_nodes = True
    cnt = cmat.node_tree
    cnt.nodes.clear()
    tc = cnt.nodes.new("ShaderNodeTexCoord")
    grad = cnt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "QUADRATIC_SPHERE"
    mp = cnt.nodes.new("ShaderNodeMapping")
    mp.inputs["Location"].default_value = (-0.35, -0.65, 0.0)
    mp.inputs["Scale"].default_value = (1.3, 1.3, 1.0)
    cnt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
    cnt.links.new(mp.outputs["Vector"], grad.inputs["Vector"])
    cem = cnt.nodes.new("ShaderNodeEmission")
    cem.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    mul = cnt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = SHEEN["level"]
    cnt.links.new(grad.outputs["Fac"], mul.inputs[0])
    cnt.links.new(mul.outputs[0], cem.inputs["Strength"])
    cout = cnt.nodes.new("ShaderNodeOutputMaterial")
    cnt.links.new(cem.outputs["Emission"], cout.inputs["Surface"])
    cm.materials.append(cmat)
    for k in ("visible_camera", "visible_diffuse", "visible_shadow", "visible_transmission", "visible_volume_scatter"):
        setattr(card, k, False)

    # the sweep: a tall thin emissive strip in front of the mark that only reflections see (no light on anything,
    # no shadow), sliding across so its reflection runs over the satin faces and along the rounded edges
    sm = bpy.data.meshes.new("sweep")
    hw, hh = 0.014, 0.75
    sm.from_pydata([(-hw, 0, -hh), (hw, 0, -hh), (hw, 0, hh), (-hw, 0, hh)], [], [(0, 1, 2, 3)])
    sob = bpy.data.objects.new("sweep", sm)
    coll.objects.link(sob)
    emit = bpy.data.materials.new("sweep")
    if emit.node_tree is None:
        emit.use_nodes = True
    nt = emit.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 0.985, 0.965, 1.0)
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], outn.inputs["Surface"])
    sm.materials.append(emit)
    for k in ("visible_camera", "visible_diffuse", "visible_shadow", "visible_transmission", "visible_volume_scatter"):
        setattr(sob, k, False)
    # aim it: the point the sheen is on sweeps across the mark (mark px -150 .. 150 about its centre), and the strip
    # sits SWEEP_DIST along the camera's ray to that point mirrored in the mark's (turned) face
    sx, sy, sz, st_ = [], [], [], []
    for ta in taus:
        sp = C.light(T, ta)["sweep"]
        u = 0.0 if sp is None else sp
        pose, cam_ = C.mark_pose(T, ta), C.camera(T, ta)
        rot = Euler((math.radians(pose["pitch"]), 0.0, math.radians(pose["yaw"])), "XYZ").to_matrix()
        target = rot @ Vector(((-170 + 340 * u) * B.MU, 0.0, 30 * B.MU))
        normal = rot @ Vector((0.0, -1.0, 0.0))
        d = (target - Vector((cam_["x"], -cam_["d"], 0.0))).normalized()
        r = d - 2 * d.dot(normal) * normal
        pos = target + r * SWEEP_DIST
        sx.append(pos.x)
        sy.append(pos.y)
        sz.append(pos.z)
        st_.append(0.0 if sp is None else C.SWEEP_LEVEL * math.sin(math.pi * u) ** 1.2)
    sob.location = (sx[0], sy[0], sz[0])
    for i, v in enumerate((sx, sy, sz)):
        _series(sob, "location", i, frames, v)
    _series(em.inputs["Strength"], "default_value", -1, frames, st_)

    scene.frame_set(ctx.f0)


def _series(owner, path: str, index: int, frames, values):
    """Key owner.path[index] (index -1: a scalar) at every frame in one bulk write, linear between them."""
    import bpy
    import numpy as np

    if index >= 0:
        owner.keyframe_insert(path, index=index, frame=float(frames[0]))
    else:
        owner.keyframe_insert(path, frame=float(frames[0]))
    idb = owner.id_data  # the ID that holds the animation (a node socket's is its node tree)
    full = path if owner == idb else owner.path_from_id(path)
    act = idb.animation_data.action
    bags = [b for layer in getattr(act, "layers", []) for strip in layer.strips for b in strip.channelbags]
    curves = [f for b in bags for f in b.fcurves] if bags else list(getattr(act, "fcurves", []))
    fc = next(f for f in curves if f.data_path == full and (index < 0 or f.array_index == index))
    fc.keyframe_points.clear()
    fc.keyframe_points.add(len(frames))
    fc.keyframe_points.foreach_set("co", np.column_stack([np.asarray(frames, float), np.asarray(values, float)])
                                   .ravel().astype(np.float32))
    lin = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value
    fc.keyframe_points.foreach_set("interpolation", [lin] * len(frames))
    fc.update()
