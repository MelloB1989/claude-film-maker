"""The studio: a soft key from the upper left, a hard rim from behind on the right, a low fill, and a dark world.

The rig is placed around `target` for a camera looking down +Y (Blender's front view: the camera on -Y), with
distances in units of `scale`; powers are the watts at scale 1 and grow with scale squared, so the light reaching the
subject stays the same. Keep the key near neutral: a key warmer than about 4000 K tints bone past the engine's bloom
gate (only blood and moss may glow). Each light takes a power, or None to leave it out.
"""
from __future__ import annotations

import bpy
from mathutils import Vector

from . import materials


def _aim(ob, target: Vector) -> None:
    ob.rotation_euler = (target - ob.location).to_track_quat("-Z", "Y").to_euler()


def _light(name, kind, power, pos, target, *, size=None, temperature=None, spot_size=None, soft=None, coll=None):
    data = bpy.data.lights.new(name, kind)
    data.energy = power
    if temperature:
        data.use_temperature = True
        data.temperature = temperature
    if size is not None:
        data.shape = "DISK"
        data.size = size
    if spot_size is not None:
        data.spot_size = spot_size
        data.spot_blend = 0.25
    if soft is not None:
        data.shadow_soft_size = soft
    ob = bpy.data.objects.new(name, data)
    ob.location = pos
    _aim(ob, target)
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


def world_color(color: str | None, strength: float = 1.0):
    """The world as a flat colour (a palette name or hex; None for black) at `strength`."""
    scene = bpy.context.scene
    w = scene.world or bpy.data.worlds.new("world")
    scene.world = w
    if w.node_tree is None:  # Blender < 5 made node trees on request
        w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (*(materials.linear(color) if color else (0.0, 0.0, 0.0)), 1.0)
    bg.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return w


def studio(key: float | None = 200.0, rim: float | None = 600.0, fill: float | None = 40.0, world: str | None = "ink",
           *, target=(0.0, 0.0, 0.0), scale: float = 1.0, key_temperature: float = 6000.0, world_strength: float = 1.0,
           collection=None) -> dict:
    """Light the subject at `target`. Returns {'key', 'rim', 'fill', 'world'} (the lights left out are absent).

    The defaults expose for the engine's look: a bone surface facing the key comes out near bone's own albedo (about
    0.85 linear), the fill side about a stop under it, and the rim a bright edge."""
    t = Vector(target)
    s2 = scale * scale
    out = {}
    if key is not None:  # soft, from the upper left and in front
        out["key"] = _light("key", "AREA", key * s2, t + Vector((-2.2, -2.6, 2.4)) * scale, t, size=1.4 * scale,
                            temperature=key_temperature, coll=collection)
    if rim is not None:  # hard, from behind on the right: sculpts the silhouette
        out["rim"] = _light("rim", "SPOT", rim * s2, t + Vector((2.6, 3.4, 1.3)) * scale, t, spot_size=0.6,
                            soft=0.02 * scale, temperature=6500, coll=collection)
    if fill is not None:  # broad and low from the right, just lifting the shadows
        out["fill"] = _light("fill", "AREA", fill * s2, t + Vector((3.0, -2.8, -0.3)) * scale, t, size=3.0 * scale,
                             temperature=6500, coll=collection)
    out["world"] = world_color(world, world_strength)
    return out
