"""The freeze: the instant before the cut, when time stops. The duel's painted frame is rebuilt as cards in depth (the
plate far behind, Shinza and Tsuru each on a card of their own at the jetty's distance), rain hangs frozen in the air
between them and the lens, and the camera glides in through the drops toward the gap between the two fighters, its
focus on them, the nearest drops gone to soft discs of light.

Each card is a full-frame picture placed so that from the camera's first position it covers the frame exactly: the
first frame is the keyframe's own composition, and the move opens up the depth (the near drops sweep past fastest, the
plate barely moves). The cards are emission-only (the painting is its own light), the drops a pale light of their own,
and the world black behind the plate.

Layers from tools/ film-anime-cutout --parts (assets/layers/standoff2/): part1.png (Shinza), part2.png (Tsuru), and
plate-clean.png, the keyframe with both of them painted out (an inpainting of their grown matte).
(Tsuru). The drops' layout and the camera's path are numpy only; build() needs Blender.
"""
from __future__ import annotations

import math

import numpy as np

SHOT = {"scene": "freeze"}

LENS_MM = 35.0
GATE_MM = 20.25                       # the engine's gate height: the vertical fov means the same in both renderers
DEPTH = {"plate": 46.0, "shinza": 15.0, "tsuru": 17.0}
MOVE = {"forward": 4.6, "side": 0.15, "rise": -0.12, "yaw_deg": -1.0, "roll_deg": -2.0}
FSTOP = 1.6
DROPS = 3600
SEED = 11


def half_height(d: float) -> float:
    """Half the frame's height at distance d from the camera."""
    return d * (GATE_MM / 2) / LENS_MM


def drop_field(n: int = DROPS, seed: int = SEED, aspect: float = 16 / 9) -> np.ndarray:
    """(n, 4): x, y (depth), z and a size factor for each drop, filling the camera's view from 2.6 to 34 units deep
    (with margin for the move), denser in the middle distance where the fighters stand."""
    rng = np.random.default_rng(seed)
    # depth: a mix of uniform and a bump around the fighters
    d = np.concatenate([rng.uniform(2.6, 34.0, n * 2 // 3), rng.normal(13.0, 4.0, n - n * 2 // 3)])
    d = np.clip(d, 2.6, 34.0)
    hh = half_height(d) * 1.25
    hw = hh * aspect
    x = rng.uniform(-1, 1, n) * hw + MOVE["side"] * 0.5
    z = rng.uniform(-1, 1, n) * hh
    s = rng.uniform(0.6, 1.4, n)
    return np.column_stack([x, d, z, s])


def ease(t: np.ndarray | float) -> np.ndarray | float:
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(t, 0, 1))


def camera_at(u: float) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """The camera's position and rotation (radians, XYZ euler) at progress u through the shot."""
    k = float(ease(u))
    pos = (MOVE["side"] * k, MOVE["forward"] * k, MOVE["rise"] * k)
    rot = (math.pi / 2, math.radians(MOVE["roll_deg"]) * k, math.radians(MOVE["yaw_deg"]) * k)
    return pos, rot


def build(ctx):
    import bpy

    scene = ctx.scene
    scene.world.color = (0, 0, 0)
    if scene.world.use_nodes:
        bg = scene.world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs[0].default_value = (0, 0, 0, 1)

    def image_card(name: str, rel: str, depth: float, alpha: bool):
        img = bpy.data.images.load(str(ctx.film.path(rel)), check_existing=True)
        img.colorspace_settings.name = "sRGB"
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.interpolation = "Cubic"
        emit = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(tex.outputs["Color"], emit.inputs["Color"])
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        if alpha:
            mix = nt.nodes.new("ShaderNodeMixShader")
            clear = nt.nodes.new("ShaderNodeBsdfTransparent")
            nt.links.new(tex.outputs["Alpha"], mix.inputs["Fac"])
            nt.links.new(clear.outputs[0], mix.inputs[1])
            nt.links.new(emit.outputs[0], mix.inputs[2])
            nt.links.new(mix.outputs[0], out.inputs["Surface"])
            if hasattr(mat, "surface_render_method"):
                mat.surface_render_method = "DITHERED"  # writes depth: the depth of field blurs it
        else:
            nt.links.new(emit.outputs[0], out.inputs["Surface"])
        h = 2 * half_height(depth)
        w = h * img.size[0] / img.size[1]
        bpy.ops.mesh.primitive_plane_add(size=1, location=(0, depth, 0), rotation=(math.pi / 2, 0, 0))
        ob = bpy.context.active_object
        ob.name = name
        ob.scale = (w, h, 1)
        ob.data.materials.append(mat)
        return ob

    image_card("plate", "assets/layers/standoff2/plate-clean.png", DEPTH["plate"], alpha=False)
    image_card("shinza", "assets/layers/standoff2/part1.png", DEPTH["shinza"], alpha=True)
    image_card("tsuru", "assets/layers/standoff2/part2.png", DEPTH["tsuru"], alpha=True)

    # the frozen drops: one mesh, each drop a small elongated diamond (a bead stretched by its fall)
    field = drop_field(aspect=ctx.size[0] / ctx.size[1])
    verts, faces = [], []
    for x, y, z, s in field:
        r, L = 0.004 * s * (1 + y * 0.02), 0.055 * s * (1 + y * 0.02)
        base = len(verts)
        verts += [(x, y, z + L), (x - r, y, z), (x, y - r, z), (x + r, y, z), (x, y + r, z), (x, y, z - L * 0.6)]
        faces += [(base, base + 1, base + 2), (base, base + 2, base + 3), (base, base + 3, base + 4), (base, base + 4, base + 1),
                  (base + 5, base + 2, base + 1), (base + 5, base + 3, base + 2), (base + 5, base + 4, base + 3), (base + 5, base + 1, base + 4)]
    me = bpy.data.meshes.new("drops")
    me.from_pydata(verts, [], faces)
    me.update()
    drops = bpy.data.objects.new("drops", me)
    scene.collection.objects.link(drops)
    dm = bpy.data.materials.new("drop")
    dm.use_nodes = True
    nt = dm.node_tree
    nt.nodes.clear()
    # a bead of water: clear in the middle, a bright rim where it turns away from the lens
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.8, 0.86, 0.94, 1)
    em.inputs["Strength"].default_value = 1.1
    rim = nt.nodes.new("ShaderNodeLayerWeight")
    rim.inputs["Blend"].default_value = 0.35
    ramp = nt.nodes.new("ShaderNodeMapRange")
    ramp.inputs["To Min"].default_value = 0.18
    ramp.inputs["To Max"].default_value = 0.85
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(rim.outputs["Facing"], ramp.inputs["Value"])
    nt.links.new(ramp.outputs["Result"], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    if hasattr(dm, "surface_render_method"):
        dm.surface_render_method = "DITHERED"
    me.materials.append(dm)

    # physically sampled depth of field (the camera jittered over the aperture across the samples) where EEVEE has it
    if hasattr(scene.eevee, "use_dof_jitter"):
        scene.eevee.use_dof_jitter = True
    # the camera: the engine's gate, a glide in toward the gap between them, the focus pulled onto them
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = LENS_MM
    cam_data.sensor_fit = "VERTICAL"
    cam_data.sensor_height = GATE_MM
    cam_data.clip_start = 0.05
    cam_data.clip_end = 200
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = FSTOP
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        u = (f - ctx.f0) / max(1, ctx.f1 - 1 - ctx.f0)
        pos, rot = camera_at(u)
        cam.location = pos
        cam.rotation_euler = rot
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
        cam_data.dof.focus_distance = (DEPTH["shinza"] + DEPTH["tsuru"]) / 2 - pos[1]
        cam_data.dof.keyframe_insert("focus_distance", frame=f)
