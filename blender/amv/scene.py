"""The AMV main comp as one editable Blender scene: an orthographic camera on a stack of image-sequence planes.

This rebuilds After Effects' MAIN comp (handover build.jsx 29-151) from the plan (docs/PIPELINE-AMV.md "scene"):

- World units: 1 unit = 100 screen px at 1920x1080; screen px (x, y), y down from the top-left, is world
  (x/100 - 9.6, 5.4 - y/100). The camera is orthographic on z, `ortho_scale` 19.2 = the screen's width.
- A shot is a plane the size of its baked canvas (`Shot.canvas`), its origin at the AE anchor (layer px 960,540 =
  canvas px (960 + ox, 540 + oy)), so the plan's px, py, s, rz are the plane's location, scale / 100 and -rz about z.
  One LINEAR key per frame of `Shot.frames()` plus the frame before and after (motion blur reads them).
- The picture is the layer frames `layers/<shot>/<f:04d>.png` as an image sequence whose frame N is comp frame N (the
  image user's start / offset do it), emission 1 x opacity, alpha through a Mix Shader with a Transparent BSDF: an
  unlit "over", so Cycles' transparent bounces stack the planes exactly as AE's layers do. Stacking = `Plan.stack()`
  order as increasing z.
- Visibility is the keyed alpha (0 outside [a, end)). `hide_for_frame` additionally parks the planes that cannot show on
  the frame about to render (`--render` calls it): Cycles crashed when `hide_render` was keyed under motion blur
  (blender/lib/export.py _film_off), and a plane parked for the whole render is consistent across the blur samples.
- Motion blur: Cycles, shutter 301/360, position Center. The per-frame keys are straight between frames, so the three
  time points Cycles takes per object (frame -+ 0.42, frame) lie on straight pieces; `motion_steps` 3 gives 7 anyway.
- The drop portal (`plan.raw['portals']`): `A_in`, a second plane on shot A's layer frames with its own per-frame
  transform and opacity, placed directly above shot B. In ITS SHADER: a rounded-rect alpha mask (a packed image, layer
  space, 140 px feather), CC Radial Fast Blur as 16 taps along the zoom (amount [[f0,60],[f0+2,25],[f0+4,0]] % of the
  distance to the layer centre), and the alpha matte = the per-frame screen-space ellipse (mx, my, mrx, mry, mrot,
  mfe) from Window coordinates (a linear ramp mfe px wide centred on the ellipse edge).
- The glint: two 4-point stars as a mesh object whose material writes an AOV `glint` (white x opacity) and nothing
  into the combined pass; the compositor adds it with its glow and bloom (compositor.py).

Also bpy-free here (so pytest can run them): the mapping and key functions at the top.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import bpy
except ImportError:  # the pure geometry below is tested without Blender
    bpy = None

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

from filmtools.amv import plan as amv_plan  # noqa: E402

UNIT = 100.0                      # screen px per world unit
W, H = amv_plan.W, amv_plan.H
Z_STEP = 0.1                      # between stacked planes
Z_CAMERA = 20.0
SHUTTER = amv_plan.SHUTTER_ANGLE / 360.0
RADIAL_TAPS = 16
CUBIC_FROM_SCALE = 150.0          # shots that zoom beyond this % sample the layer with Cubic, not Linear


# ---------------------------------------------------------------- geometry (bpy-free)

def screen_to_world(x: float, y: float) -> tuple[float, float]:
    """Screen px (from the top-left, y down) -> world x, y."""
    return x / UNIT - W / 2 / UNIT, H / 2 / UNIT - y / UNIT


def world_to_screen(x: float, y: float) -> tuple[float, float]:
    return (x + W / 2 / UNIT) * UNIT, (H / 2 / UNIT - y) * UNIT


def plane_pose(px: float, py: float, s: float, rz: float) -> tuple[tuple[float, float, float], float, float]:
    """The plane's (location x, y, z=0), rotation about z in radians (counter-clockwise, so -rz) and scale for the
    plan's per-frame (px, py, s %, rz deg): the anchor lands on screen (px, py)."""
    x, y = screen_to_world(px, py)
    return (x, y, 0.0), -math.radians(rz), s / 100.0


def anchor_in_canvas(canvas) -> tuple[float, float]:
    """The AE anchor (layer px 960, 540) in canvas px, canvas = (w, h, ox, oy)."""
    return amv_plan.ANCHOR[0] + canvas[2], amv_plan.ANCHOR[1] + canvas[3]


def canvas_corners(canvas) -> list[tuple[float, float]]:
    """The plane's corners (top-left, bottom-left, bottom-right, top-right) as local x, y in world units, relative to
    the anchor."""
    w, h = canvas[0], canvas[1]
    ax, ay = anchor_in_canvas(canvas)
    return [((cx - ax) / UNIT, -(cy - ay) / UNIT) for cx, cy in ((0, 0), (0, h), (w, h), (w, 0))]


def layer_point_to_screen(pose, canvas, lx: float, ly: float) -> tuple[float, float]:
    """Where a layer pixel (lx, ly) lands on screen when the plane is at `pose` = plane_pose(...): the plane's local
    point, scaled, rotated about z, moved, then world -> screen. What the camera sees, without Blender."""
    (x, y, _), rot, k = pose
    ax, ay = anchor_in_canvas(canvas)
    u, v = (lx + canvas[2] - ax) / UNIT, -(ly + canvas[3] - ay) / UNIT
    c, s = math.cos(rot), math.sin(rot)
    return world_to_screen(x + k * (c * u - s * v), y + k * (s * u + c * v))


def key_frames(shot) -> list[int]:
    """The frames a shot's plane is keyed on: every frame of the shot and one before and after."""
    return list(range(shot.a - 1, shot.end + 1))


def visible_range(shot) -> tuple[int, int]:
    """The comp frames a shot's plane may need to be un-parked on (the frame before and after, for motion blur)."""
    return shot.a - 1, shot.end


def opacity_keys(shot) -> list[tuple[int, float]]:
    """(frame, alpha 0..1) for the plane's alpha: Shot.opacity inside [a, end), 0 outside, one value per frame."""
    return [(f, (shot.opacity(f) / 100.0) if shot.a <= f < shot.end else 0.0) for f in key_frames(shot)]


def star_polygon(outer: float, inner: float, rot_deg: float, points: int = 4) -> list[tuple[float, float]]:
    """An AE star (type star) around the origin: `points` tips at `outer`, valleys at `inner`, one tip up, then
    rotated clockwise by `rot_deg`; y down, as AE draws."""
    out = []
    for i in range(points * 2):
        r = outer if i % 2 == 0 else inner
        a = math.radians(rot_deg) + math.pi * i / points - math.pi / 2
        out.append((r * math.cos(a), r * math.sin(a)))
    return out


def wm_keys(plan) -> list[tuple[float, float]]:
    """Watermark opacity keys (build.jsx 220-225): 62 %, faded to 0 over the `wm_hide` windows."""
    wk = [(0, 62.0)]
    for a, b in plan.raw.get("wm_hide") or []:
        wk += [(a - 3, 62.0), (a, 0.0), (b, 0.0), (b + 3, 62.0)]
    wk.sort(key=lambda k: k[0])
    out = []
    for k in wk:
        if not out or out[-1][0] != k[0]:
            out.append(k)
    return out


def parse_frames(spec: str) -> list[int]:
    out = set()
    for part in spec.split(","):
        a, _, b = part.strip().partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return sorted(out)


def read_canvas(folder: Path, shot) -> tuple[int, int, int, int]:
    """The shot's canvas (w, h, ox, oy): `canvas.json` of its layer folder (the bake writes it), else Shot.canvas."""
    f = Path(folder) / "canvas.json"
    if f.exists():
        d = json.loads(f.read_text())
        return int(d["w"]), int(d["h"]), int(d["ox"]), int(d["oy"])
    return shot.canvas


# ---------------------------------------------------------------- animation helpers (bpy)

def fcurve(idb, path: str, index: int = 0):
    ad = idb.animation_data or idb.animation_data_create()
    if ad.action is None:
        ad.action = bpy.data.actions.new(f"{idb.name}Action")
    return ad.action.fcurve_ensure_for_datablock(idb, path, index=index)


def key(idb, path: str, index: int, pts, interp: str = "LINEAR") -> None:
    """Keys (frame, value) on `path[index]` of `idb`, all with one interpolation. Held outside the range."""
    pts = sorted(pts, key=lambda p: p[0])
    fc = fcurve(idb, path, index)
    kp = fc.keyframe_points
    kp.add(len(pts))
    kp.foreach_set("co", [float(v) for p in pts for v in (p[0], p[1])])
    for p in kp:
        p.interpolation = interp
    fc.update()


def key_socket(node, socket, pts, interp="LINEAR", index=None, tree=None) -> None:
    """Keys on an input socket's default_value (a Value, or one channel of a vector / colour)."""
    tree = tree or node.id_data
    i = list(node.inputs).index(socket) if not isinstance(socket, int) else socket
    path = f'nodes["{node.name}"].inputs[{i}].default_value'
    if index is None:
        key(tree, path, 0, pts, interp)
    else:
        key(tree, path, index, pts, interp)


# ---------------------------------------------------------------- scene settings

def configure(scene, res_scale: float, plan, samples: int, engine: str = "cycles", allow_cpu: bool = True) -> str:
    """Resolution, colour management, motion blur and the engine for the AMV scene. Returns the device used."""
    from lib import cli, setup
    r = scene.render
    r.resolution_x, r.resolution_y = max(2, round(W * res_scale)), max(2, round(H * res_scale))
    r.resolution_percentage = 100
    r.pixel_aspect_x = r.pixel_aspect_y = 1.0
    r.fps = plan.fps
    r.fps_base = 1.0
    scene.frame_start, scene.frame_end = 0, plan.dur - 1
    r.film_transparent = False
    r.use_motion_blur = True
    r.motion_blur_shutter = SHUTTER
    r.motion_blur_position = "CENTER"
    r.use_compositing = True
    r.use_sequencer = False
    r.compositor_device = "CPU"      # no GPU context in a headless pod shell; the node tree is light
    r.dither_intensity = 0.0
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    r.image_settings.color_depth = "8"
    r.image_settings.compression = 15

    scene.display_settings.display_device = "sRGB"
    vs = scene.view_settings
    vs.view_transform = "Standard"
    vs.look = "None"
    vs.exposure = 0.0
    vs.gamma = 1.0
    vs.use_curve_mapping = False
    scene.sequencer_colorspace_settings.name = "sRGB"

    device = "CPU"
    if engine == "cycles":
        r.engine = "CYCLES"
        c = scene.cycles
        import os
        tried = cli.gpu_backends(os.environ.get(cli.GPU_ENV))
        backend, gpus = setup.use_gpu(tried)
        c.device = cli.cycles_device(gpus, require_gpu=not allow_cpu, tried=tried)
        device = f"{backend} {', '.join(gpus)}" if gpus else "CPU"
        c.samples = samples
        c.use_adaptive_sampling = False
        c.use_denoising = False
        c.pixel_filter_type = "BLACKMAN_HARRIS"
        c.filter_width = 1.0
        c.max_bounces = 0
        for name in ("diffuse_bounces", "glossy_bounces", "transmission_bounces", "volume_bounces"):
            setattr(c, name, 0)
        c.transparent_max_bounces = 64   # the planes at one pixel: a handful, +A_in; never the limit
        c.sample_clamp_direct = c.sample_clamp_indirect = 0.0
        c.seed = 0
        c.use_animated_seed = True
        c.film_exposure = 1.0
    else:
        try:
            r.engine = "BLENDER_EEVEE"
        except TypeError:
            r.engine = "BLENDER_EEVEE_NEXT"
        scene.eevee.taa_render_samples = samples
    w = bpy.data.worlds.new("AMV black") if not scene.world else scene.world
    scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (0, 0, 0, 1)
        bg.inputs[1].default_value = 0.0
    return device


def make_camera(scene):
    cam = bpy.data.cameras.new("AMV camera")
    cam.type = "ORTHO"
    cam.ortho_scale = W / UNIT
    cam.sensor_fit = "HORIZONTAL"
    cam.clip_start, cam.clip_end = 0.1, 100.0
    ob = bpy.data.objects.new("AMV camera", cam)
    ob.location = (0.0, 0.0, Z_CAMERA)
    scene.collection.objects.link(ob)
    scene.camera = ob
    return ob


# ---------------------------------------------------------------- planes and materials

def load_sequence(folder: Path, first: int, count: int):
    """The image datablock of `folder/<first:04d>.png ...` as a sequence (straight alpha, sRGB)."""
    img = bpy.data.images.load(str(Path(folder) / f"{first:04d}.png"), check_existing=True)
    img.source = "SEQUENCE"
    img.alpha_mode = "STRAIGHT"
    img.colorspace_settings.name = "sRGB"
    return img


def set_sequence_user(user, first: int, count: int) -> None:
    """Texture frame N = comp frame N for the files first .. first+count-1: the user's frame 1 is scene frame `first`
    and its file number is frame + offset."""
    user.frame_start = first
    user.frame_duration = count
    user.frame_offset = first - 1
    user.use_cyclic = False
    user.use_auto_refresh = True


def new_plane(name: str, canvas, z: float):
    """A canvas-sized quad, UV-mapped to the whole image, its origin at the AE anchor."""
    w, h = canvas[0], canvas[1]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(x, y, 0.0) for x, y in canvas_corners(canvas)], [], [(0, 1, 2, 3)])
    uv = mesh.uv_layers.new(name="UV")
    for loop, (u, v) in zip(mesh.loops, ((0, 1), (0, 0), (1, 0), (1, 1))):
        uv.data[loop.index].uv = (u, v)
    ob = bpy.data.objects.new(name, mesh)
    ob.location = (0.0, 0.0, z)
    ob.cycles.motion_steps = 3
    return ob


def _tex(nodes, image, first, count, interp, x, y, name="layer"):
    t = nodes.new("ShaderNodeTexImage")
    t.name = t.label = name
    t.image = image
    t.interpolation = interp
    t.extension = "EXTEND"
    set_sequence_user(t.image_user, first, count)
    t.location = (x, y)
    return t


def layer_material(name: str, image, shot, interp: str):
    """emission(texture) over transparent, mixed by texture alpha x the keyed `opacity` input."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    n = nt.nodes
    tex = _tex(n, image, shot.a, shot.end - shot.a, interp, -700, 0)
    mul = n.new("ShaderNodeMath")
    mul.name = "opacity"
    mul.operation = "MULTIPLY"
    mul.location = (-400, -200)
    emi = n.new("ShaderNodeEmission")
    emi.location = (-400, 100)
    tr = n.new("ShaderNodeBsdfTransparent")
    tr.location = (-400, -50)
    mix = n.new("ShaderNodeMixShader")
    mix.location = (-150, 0)
    out = n.new("ShaderNodeOutputMaterial")
    out.location = (100, 0)
    nt.links.new(tex.outputs["Color"], emi.inputs["Color"])
    nt.links.new(tex.outputs["Alpha"], mul.inputs[0])
    nt.links.new(mul.outputs[0], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(emi.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    key_socket(mul, 1, opacity_keys(shot), "CONSTANT", tree=nt)
    return mat


def key_pose(ob, shot_frames, pose_at) -> None:
    """Per-frame LINEAR location / rotation z / scale keys: `pose_at(f)` -> plane_pose(...)."""
    rows = [(f, *pose_at(f)) for f in shot_frames]    # (f, (x, y, z), rot, scale)
    key(ob, "location", 0, [(r[0], r[1][0]) for r in rows])
    key(ob, "location", 1, [(r[0], r[1][1]) for r in rows])
    key(ob, "rotation_euler", 2, [(r[0], r[2]) for r in rows])
    for i in range(3):
        key(ob, "scale", i, [(r[0], r[3]) for r in rows] if i < 2 else [(r[0], 1.0) for r in rows])


def rounded_rect_mask(canvas, name: str, radius: float = 140.0, feather: float = 140.0, down: int = 4):
    """A packed grey image over the canvas: 1 inside the layer's rounded rectangle (0,0,1920,1080; AE's roundRect
    with its `radius`), a linear ramp `feather` px wide centred on its edge (AE mask feather), 0 outside."""
    import numpy as np
    w, h, ox, oy = canvas
    mw, mh = max(2, w // down), max(2, h // down)
    u = (np.arange(mw) + 0.5) / mw
    v = (np.arange(mh) + 0.5) / mh
    lx = (u * w - ox)[None, :]
    ly = ((1.0 - v) * h - oy)[:, None]
    qx = np.abs(lx - W / 2) - (W / 2 - radius)
    qy = np.abs(ly - H / 2) - (H / 2 - radius)
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - radius
    a = np.clip(0.5 - d / feather, 0.0, 1.0).astype(np.float32)
    rgba = np.repeat(a[..., None], 4, axis=2)
    rgba[..., 3] = 1.0
    img = bpy.data.images.new(name, mw, mh, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(rgba.ravel())
    img.pack()
    return img


def portal_material(name: str, image, shot, canvas, P, interp: str):
    """The `A_in` shader: layer frames x rounded-rect mask, radial blur by taps, x screen-space ellipse matte."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    n, L = nt.nodes, nt.links
    f0, f1 = P["f0"], P["f1"]
    cw, ch = canvas[0], canvas[1]
    ax, ay = anchor_in_canvas(canvas)
    centre = (ax / cw, 1.0 - ay / ch)

    uvn = n.new("ShaderNodeTexCoord")
    uvn.location = (-1800, 0)
    # d = centre - uv, the direction each tap walks along
    d = n.new("ShaderNodeVectorMath")
    d.operation = "SUBTRACT"
    d.inputs[0].default_value = (centre[0], centre[1], 0.0)
    L.new(uvn.outputs["UV"], d.inputs[1])
    amount = n.new("ShaderNodeValue")
    amount.name = "radial amount"
    amount.location = (-1800, -300)
    key(nt, f'nodes["{amount.name}"].outputs[0].default_value', 0,
        [(f0, 0.60), (f0 + 2, 0.25), (f0 + 4, 0.0)])
    sum_c = sum_a = None
    for k in range(RADIAL_TAPS):
        t = k / (RADIAL_TAPS - 1)
        step = n.new("ShaderNodeMath")
        step.operation = "MULTIPLY"
        step.inputs[1].default_value = t
        L.new(amount.outputs[0], step.inputs[0])
        off = n.new("ShaderNodeVectorMath")
        off.operation = "SCALE"
        L.new(d.outputs[0], off.inputs[0])
        L.new(step.outputs[0], off.inputs["Scale"])
        pos = n.new("ShaderNodeVectorMath")
        pos.operation = "ADD"
        L.new(uvn.outputs["UV"], pos.inputs[0])
        L.new(off.outputs[0], pos.inputs[1])
        tex = _tex(n, image, shot.a, shot.end - shot.a, interp, -1400, 600 - k * 260, f"tap{k}")
        tex.extension = "CLIP"
        L.new(pos.outputs[0], tex.inputs["Vector"])
        pm = n.new("ShaderNodeVectorMath")          # premultiplied colour
        pm.operation = "SCALE"
        L.new(tex.outputs["Color"], pm.inputs[0])
        L.new(tex.outputs["Alpha"], pm.inputs["Scale"])
        if sum_c is None:
            sum_c, sum_a = pm.outputs[0], tex.outputs["Alpha"]
        else:
            ac = n.new("ShaderNodeVectorMath")
            ac.operation = "ADD"
            L.new(sum_c, ac.inputs[0])
            L.new(pm.outputs[0], ac.inputs[1])
            aa = n.new("ShaderNodeMath")
            aa.operation = "ADD"
            L.new(sum_a, aa.inputs[0])
            L.new(tex.outputs["Alpha"], aa.inputs[1])
            sum_c, sum_a = ac.outputs[0], aa.outputs[0]
    # straight colour = sum(c a) / sum(a); mean alpha = sum(a) / taps
    den = n.new("ShaderNodeMath")
    den.operation = "MAXIMUM"
    den.inputs[1].default_value = 1e-6
    L.new(sum_a, den.inputs[0])
    col = n.new("ShaderNodeVectorMath")
    col.operation = "DIVIDE"
    L.new(sum_c, col.inputs[0])
    L.new(den.outputs[0], col.inputs[1])
    mean_a = n.new("ShaderNodeMath")
    mean_a.operation = "DIVIDE"
    mean_a.inputs[1].default_value = float(RADIAL_TAPS)
    L.new(sum_a, mean_a.inputs[0])

    # rounded-rect layer mask
    mimg = rounded_rect_mask(canvas, f"{name} mask")
    mt = n.new("ShaderNodeTexImage")
    mt.name = "layer mask"
    mt.image = mimg
    mt.interpolation = "Linear"
    mt.extension = "EXTEND"
    L.new(uvn.outputs["UV"], mt.inputs["Vector"])

    # screen-space ellipse: Window -> screen px (y down) -> inverse (centre, rotation, radii) -> |q|
    win = n.new("ShaderNodeTexCoord")
    scr = n.new("ShaderNodeMapping")
    scr.vector_type = "POINT"
    scr.inputs["Scale"].default_value = (W, -H, 1.0)
    scr.inputs["Location"].default_value = (0.0, H, 0.0)
    L.new(win.outputs["Window"], scr.inputs["Vector"])
    ell = n.new("ShaderNodeMapping")
    ell.name = "ellipse"
    ell.vector_type = "TEXTURE"
    L.new(scr.outputs[0], ell.inputs["Vector"])
    fr = range(f0, f1)
    j = lambda f: f - f0
    key(nt, 'nodes["ellipse"].inputs[1].default_value', 0, [(f, P["mx"][j(f)]) for f in fr])
    key(nt, 'nodes["ellipse"].inputs[1].default_value', 1, [(f, P["my"][j(f)]) for f in fr])
    key(nt, 'nodes["ellipse"].inputs[2].default_value', 2, [(f, math.radians(P["mrot"][j(f)])) for f in fr])
    key(nt, 'nodes["ellipse"].inputs[3].default_value', 0, [(f, P["mrx"][j(f)]) for f in fr])
    key(nt, 'nodes["ellipse"].inputs[3].default_value', 1, [(f, P["mry"][j(f)]) for f in fr])
    ln = n.new("ShaderNodeVectorMath")
    ln.operation = "LENGTH"
    L.new(ell.outputs[0], ln.inputs[0])
    m1 = n.new("ShaderNodeMath")
    m1.operation = "SUBTRACT"
    m1.inputs[1].default_value = 1.0
    L.new(ln.outputs["Value"], m1.inputs[0])
    kn = n.new("ShaderNodeMath")
    kn.name = "ramp"
    kn.operation = "MULTIPLY"
    L.new(m1.outputs[0], kn.inputs[0])
    # edge ramp: px distance = (r - 1) * sqrt(rx ry); alpha = 0.5 - distance / mfe
    key(nt, 'nodes["ramp"].inputs[1].default_value', 0,
        [(f, math.sqrt(P["mrx"][j(f)] * P["mry"][j(f)]) / max(P["mfe"][j(f)], 1e-3)) for f in fr])
    ea = n.new("ShaderNodeMath")
    ea.operation = "SUBTRACT"
    ea.use_clamp = True
    ea.inputs[0].default_value = 0.5
    L.new(kn.outputs[0], ea.inputs[1])

    # alpha = taps alpha x layer mask x ellipse x keyed opacity
    a1 = n.new("ShaderNodeMath")
    a1.operation = "MULTIPLY"
    L.new(mean_a.outputs[0], a1.inputs[0])
    L.new(mt.outputs["Color"], a1.inputs[1])
    a2 = n.new("ShaderNodeMath")
    a2.operation = "MULTIPLY"
    L.new(a1.outputs[0], a2.inputs[0])
    L.new(ea.outputs[0], a2.inputs[1])
    op = n.new("ShaderNodeMath")
    op.name = "opacity"
    op.operation = "MULTIPLY"
    L.new(a2.outputs[0], op.inputs[0])
    pts = [(f, P["op"][j(f)] / 100.0 if f0 <= f < f1 else 0.0) for f in range(f0 - 1, f1 + 1)]
    key_socket(op, 1, pts, "CONSTANT", tree=nt)

    emi = n.new("ShaderNodeEmission")
    L.new(col.outputs[0], emi.inputs["Color"])
    tr = n.new("ShaderNodeBsdfTransparent")
    mix = n.new("ShaderNodeMixShader")
    L.new(op.outputs[0], mix.inputs[0])
    L.new(tr.outputs[0], mix.inputs[1])
    L.new(emi.outputs[0], mix.inputs[2])
    out = n.new("ShaderNodeOutputMaterial")
    L.new(mix.outputs[0], out.inputs[0])
    return mat


def glint_object(P, z: float):
    """The portal's glint (build.jsx 123-144): the two stars as a mesh at the pupil; its material writes AOV 'glint'."""
    G = P["glint"]
    n_f = len(G["x"])
    f0 = G["f0"]
    r = G["r"]
    verts, faces = [], []
    for outer, inner, rot in ((r, r * 0.10, 0.0), (r * 0.5, r * 0.08, 45.0)):
        poly = star_polygon(outer, inner, rot)
        c = len(verts)
        verts.append((0.0, 0.0, 0.0))
        verts += [(x / UNIT, -y / UNIT, 0.0) for x, y in poly]      # AE y is down
        faces += [(c, c + 1 + i, c + 1 + (i + 1) % len(poly)) for i in range(len(poly))]
    mesh = bpy.data.meshes.new("glint")
    mesh.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new("glint", mesh)
    ob.location = (0, 0, z)
    ob.cycles.motion_steps = 3
    fr = list(range(f0, f0 + n_f))
    key(ob, "location", 0, [(f, screen_to_world(G["x"][f - f0], G["y"][f - f0])[0]) for f in fr])
    key(ob, "location", 1, [(f, screen_to_world(G["x"][f - f0], G["y"][f - f0])[1]) for f in fr])
    # rotation = time * 120 deg/s clockwise (AE expression), scale keys in %
    rot_frames = range(f0 - 1, f0 + n_f + 1)
    key(ob, "rotation_euler", 2, [(f, -math.radians(120.0 * f / 30.0)) for f in rot_frames])
    sk = [(f0, 0.60), (f0 + 2, 1.00), (f0 + 5, 0.85), (f0 + 11, 0.40)]
    for i in range(2):
        key(ob, "scale", i, sk)
    mat = bpy.data.materials.new("glint")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    aov = nt.nodes.new("ShaderNodeOutputAOV")
    aov.aov_name = "glint"
    aov.name = "glint aov"
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tr.outputs[0], out.inputs[0])
    ok = [(f0, 0.0), (f0 + 1, 1.0), (f0 + 4, 1.0), (f0 + 9, 0.0)]
    for i in range(3):
        key_socket(aov, 0, ok, "LINEAR", index=i, tree=nt)
    mesh.materials.append(mat)
    ob["amv_range"] = (f0 - 1, f0 + 12)
    return ob


# ---------------------------------------------------------------- the build

@dataclass
class Built:
    scene: object
    plan: object
    device: str
    planes: dict = field(default_factory=dict)      # shot name -> object
    portals: dict = field(default_factory=dict)     # portal name -> object
    glints: dict = field(default_factory=dict)
    skipped: list = field(default_factory=list)


def build_scene(film_dir, layers_dir, *, res_scale: float = 1.0, samples: int = 64, engine: str = "cycles",
                allow_cpu: bool = True, log=print) -> Built:
    """Reset the current scene and build the AMV main comp (planes, camera, settings). The compositor is added by
    compositor.build (build.py does both). A shot whose layer frames are missing is skipped with a warning."""
    from lib import setup
    film_dir, layers_dir = Path(film_dir), Path(layers_dir)
    plan = amv_plan.load(film_dir)
    scene = bpy.context.scene
    setup.clear_scene()
    for coll in (bpy.data.images, bpy.data.worlds):
        for b in list(coll):
            if b.users == 0:
                coll.remove(b)
    device = configure(scene, res_scale, plan, samples, engine, allow_cpu)
    make_camera(scene)
    built = Built(scene, plan, device)
    col = bpy.data.collections.new("AMV planes")
    scene.collection.children.link(col)

    stack = plan.stack()
    zs = {s.name: Z_STEP * (i + 1) for i, s in enumerate(stack)}
    for shot in stack:
        folder = layers_dir / shot.name
        if not (folder / f"{shot.a:04d}.png").exists():
            log(f"WARNING: no layer frames for {shot.name} ({folder}): its plane is skipped")
            built.skipped.append(shot.name)
            continue
        canvas = read_canvas(folder, shot)
        interp = "Cubic" if max(shot.raw["s"]) > CUBIC_FROM_SCALE else "Linear"
        img = load_sequence(folder, shot.a, shot.end - shot.a)
        ob = new_plane(shot.name, canvas, zs[shot.name])
        ob.data.materials.append(layer_material(shot.name, img, shot, interp))
        key_pose(ob, key_frames(shot), lambda f, s=shot: plane_pose(*s.transform(f)))
        ob["amv_range"] = visible_range(shot)
        col.objects.link(ob)
        built.planes[shot.name] = ob

    for P in plan.raw.get("portals") or []:
        A, B = plan.shots[P["A"]], plan.shots[P["B"]]
        if A.name in built.skipped or B.name in built.skipped:
            log(f"WARNING: portal {P['name']}: shot {A.name} or {B.name} has no layer frames, portal skipped")
            continue
        folder = layers_dir / A.name
        canvas = read_canvas(folder, A)
        interp = "Cubic" if max(P["s"]) > CUBIC_FROM_SCALE else "Linear"
        img = load_sequence(folder, A.a, A.end - A.a)
        ob = new_plane(f"A_in {P['name']}", canvas, zs[B.name] + Z_STEP / 2)
        ob.data.materials.append(portal_material(f"A_in {P['name']}", img, A, canvas, P, interp))
        frames = range(P["f0"] - 1, P["f1"] + 1)

        def pose(f, P=P):
            j = min(max(f - P["f0"], 0), len(P["px"]) - 1)
            return plane_pose(P["px"][j], P["py"][j], P["s"][j], P["rz"][j])
        key_pose(ob, frames, pose)
        ob["amv_range"] = (P["f0"] - 1, P["f1"])
        col.objects.link(ob)
        built.portals[P["name"]] = ob
        if P.get("glint"):
            g = glint_object(P, 5.0)
            col.objects.link(g)
            built.glints[P["name"]] = g
            vl = scene.view_layers[0]
            if "glint" not in [a.name for a in vl.aovs]:
                aov = vl.aovs.add()
                aov.name, aov.type = "glint", "COLOR"
    log(f"scene: {len(built.planes)} planes, {len(built.portals)} portal(s), device {device}, "
        f"{scene.render.resolution_x}x{scene.render.resolution_y}")
    return built


def hide_for_frame(built: Built, f: int) -> int:
    """Park (hide_render) every plane that cannot show on comp frame `f` (outside its keyed range plus the motion-blur
    frame either side); un-park the rest. Static for the whole render of the frame. Returns the number shown."""
    shown = 0
    for ob in list(built.planes.values()) + list(built.portals.values()) + list(built.glints.values()):
        lo, hi = ob["amv_range"]
        hide = not (lo <= f <= hi)
        ob.hide_render = hide
        shown += not hide
    return shown
