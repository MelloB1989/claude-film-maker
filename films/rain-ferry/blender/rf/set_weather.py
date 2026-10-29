"""The Rain Ferry's weather, as the sets wear it: the sky, the fog, the key light and the palette of each state, and
how much the rain dimples the water, how wet the planks shine and how thick the mist lies.

- "rain": most of the film. Almost monochrome: cold slate, grey and ink, the hut's lantern the one warm light; the
  river and the puddles dimpled with rings, everything wet.
- "thinning": 24 board, the rain giving out (the shot keys RAIN down to nothing with `key_rain`): the same cold
  palette, the sky a little paler, the mist thinner.
- "after": 25 light, 26 cross, 27 title. The clouds open: a warm gold key low over the far end of the valley, colour
  back in the grass and the pines, the water calm and shining, the puddles still as mirrors, the mist lifting.

A state is a name above, a Weather, or the film's look schedule at an instant (data/look.json through
lib/look_schedule.py: `ctx.look_at(f)`): `weather()` turns the schedule's warmth, light, rain and mist into a Weather
(its warmth blends the palette and the water from "rain" to "after"; its sky, fog, key, ambient, rain density and
mist come from the schedule as they are), so a set lit from the schedule grades with every other shot.

`stage(scene, state)` lights a scene for a state (the world's ambient, the key sun, EEVEE's ray tracing for the
reflections) and returns its toon.Look; the set builders (rf/set_world.py) take the state's colours from `palette`.
`key(world, ctx)` keys what moves over a shot (the rain on the water, the sheen, the key light) from the schedule,
frame by frame. Pure data and Python but for `stage`, `key` and `key_rain`.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from . import sets


@dataclass
class Weather:
    name: str
    sky: tuple                      # the sky at the horizon (linear)
    zenith: tuple                   # the sky overhead
    fog: tuple | None = None        # the fog (None: the sky's colour)
    warm: float = 0.0               # 0 the cold palette of the rain .. 1 the warm one after it (`palette`)
    fog_near: float = 18.0
    fog_far: float = 480.0
    fog_max: float = 0.9
    fog_power: float = 0.65
    key: tuple = (0.55, 0.45, -0.7)    # the key sun's direction of travel (world)
    key_color: tuple = (1.0, 1.0, 1.0)
    key_gain: float = 1.0           # the key's strength, times a new sun's (as the standoff lights its set)
    key_angle: float = 3.0          # degrees: the sun's size (soft shadows under cloud)
    ambient: tuple = (0.03, 0.032, 0.038)
    rain: float = 1.0               # rings on the water and the puddles (water.RAIN)
    wet: float = 0.22               # the sheen on planks, posts and mud (water.WET)
    mirror: float = 0.3             # how much the river reflects
    puddle_mirror: float = 0.55
    shine: float = 0.0              # glints on the river's swell
    shine_color: tuple = (1.0, 0.78, 0.45)
    mist: float = 1.0               # the mist's density, times the set's own
    lantern: float = 3.0            # the hut lantern's glow
    river: tuple = sets.RIVER       # (the water, the light of its streaks and rings)


# the warm world after the rain (`palette` at warm 1): colour comes back into the living things, the wood warms, the far ridges go
# golden grey in the light through the mist
AFTER_GRADE = {
    "plank": ((0.16, 0.12, 0.085), (0.035, 0.03, 0.03)),
    "post": ((0.11, 0.08, 0.06), (0.025, 0.022, 0.022)),
    "rope": ((0.45, 0.33, 0.18), (0.1, 0.075, 0.05)),
    "mud": ((0.16, 0.12, 0.08), (0.04, 0.032, 0.028)),
    "grass": ((0.2, 0.22, 0.09), (0.045, 0.05, 0.03)),
    "wall": ((0.12, 0.085, 0.06), (0.028, 0.022, 0.02)),
    "thatch": ((0.38, 0.27, 0.13), (0.08, 0.06, 0.04)),
    "hull": ((0.13, 0.095, 0.07), (0.03, 0.025, 0.022)),
    "wood": ((0.2, 0.15, 0.1), (0.045, 0.036, 0.03)),
    "needles": ((0.06, 0.085, 0.055), (0.018, 0.024, 0.02)),
    "slope": ((0.09, 0.09, 0.065), (0.03, 0.03, 0.026)),
    "ridge": ((0.16, 0.13, 0.1), (0.16, 0.13, 0.1)),
}

STATES = {
    "rain": Weather("rain", sky=sets.SKY, zenith=sets.ZENITH),
    "thinning": Weather("thinning", sky=(0.58, 0.6, 0.64), zenith=(0.36, 0.38, 0.42), rain=0.35, mist=0.8, wet=0.25,
                        mirror=0.38, puddle_mirror=0.65, key_gain=1.1),
    "after": Weather("after", sky=(1.0, 0.78, 0.48), zenith=(0.55, 0.5, 0.45), fog_near=22.0, fog_far=650.0, fog_max=0.82,
                     key=(-0.25, -0.9, -0.35), key_color=(1.0, 0.82, 0.58), key_gain=1.25, key_angle=1.5,
                     ambient=(0.06, 0.05, 0.04), rain=0.0, wet=0.32, mirror=0.55, puddle_mirror=0.85, shine=1.0,
                     mist=0.55, lantern=1.6, warm=1.0,
                     river=((0.11, 0.085, 0.065), (0.32, 0.25, 0.16))),
}


MIST = 0.6     # the schedule's cold mist density: the sets' own mist at 1


def _lerp(a, b, k: float):
    if isinstance(a, tuple):
        return tuple(_lerp(x, y, k) for x, y in zip(a, b))
    return a + (b - a) * k


def blend(warm: float) -> Weather:
    """The weather `warm` of the way from "rain" (0) to "after" (1): every number and colour between them."""
    a, b = STATES["rain"], STATES["after"]
    k = min(max(float(warm), 0.0), 1.0)
    out = {f: _lerp(getattr(a, f), getattr(b, f), k) for f in Weather.__dataclass_fields__ if f not in ("name", "fog")}
    return Weather(name=f"warm{k:.2f}", **{f: v for f, v in out.items() if f != "name"})


def weather(state) -> Weather:
    """A state by name, a Weather as it is, or a look schedule State (`ctx.look_at(f)`) as a Weather: the blend at
    its warmth, with the schedule's sky, fog, key, ambient, rain density and mist."""
    if isinstance(state, Weather):
        return state
    if hasattr(state, "light") and hasattr(state, "warm"):
        w, li = blend(state.warm), state.light
        return replace(w, name=f"look{state.warm:.2f}", sky=tuple(li.sky), zenith=tuple(c * 0.62 for c in li.sky),
                       fog=tuple(li.fog), key_color=tuple(li.key), key_gain=li.key_strength, ambient=tuple(li.ambient),
                       rain=state.rain.density, mist=state.mist.density / MIST)
    if state not in STATES:
        raise ValueError(f"set_weather: no state {state!r} ({', '.join(STATES)})")
    return STATES[state]


def palette(state, colors: dict) -> dict:
    """`colors` (part -> (lit, shade)) as `state` paints them: toward AFTER_GRADE's by its warmth."""
    k = weather(state).warm
    out = {}
    for part in {*colors, *AFTER_GRADE}:
        cold = colors.get(part, AFTER_GRADE.get(part))
        warm = AFTER_GRADE.get(part, cold)
        out[part] = tuple(_lerp(c, w, k) for c, w in zip(cold, warm))
    return out


def look(state):
    """The toon.Look of a state: its fog."""
    from lib import toon

    w = weather(state)
    return toon.Look(fog=w.fog or w.sky, fog_near=w.fog_near, fog_far=w.fog_far, fog_max=w.fog_max, fog_power=w.fog_power)


def stage(scene, state):
    """Light `scene` for `state`: the world's dim ambient, a key sun (returned, in a collection of its own,
    "world-light", which the satsuei compositor leaves out of the cast's layer), EEVEE's shadows and ray tracing (the
    water's and the wet planks' reflections). Returns (look, key)."""
    import math

    import bpy
    from mathutils import Vector

    from lib import toon

    w = weather(state)
    scene.eevee.use_shadows = True
    scene.eevee.use_raytracing = True
    scene.view_settings.view_transform = "Standard"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("world")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (*w.ambient, 1)
    sun = bpy.data.lights.new("key", "SUN")
    sun.angle = math.radians(w.key_angle)
    sun.color = w.key_color
    sun.energy *= w.key_gain
    key = bpy.data.objects.new("key", sun)
    toon.collection("world-light").objects.link(key)
    key.rotation_euler = Vector(w.key).to_track_quat("-Z", "Y").to_euler()
    return look(w), key


def key_rain(world: dict, frames_values) -> None:
    """Key how hard it rains on the set's water (the river's and the puddles' rings) to [(frame, 0..1), ...]: the rain
    thinning to nothing (24 board), or easing back."""
    from lib import water

    for mat in world["waters"]:
        water.key(mat, water.RAIN, frames_values)


def key(world: dict, ctx, frames=None) -> None:
    """Key the set's weather over a shot from the look schedule, on every frame of `frames` (default the shot's,
    one either side): the rain on the water (RAIN), the planks' sheen, the river's mirror and shine, the key light's
    colour and strength and the ambient, as the schedule moves them (24 board: the rain thinning; 25 light: the sun
    coming). The palette stays as built (the engine's grade carries the rest of the warmth)."""
    from lib import water

    frames = frames if frames is not None else range(ctx.f0 - 1, ctx.f1 + 1)
    key_light, bg = world["key"], world["scene"].world.node_tree.nodes.get("Background")
    base = world["key_base"]
    for f in frames:
        w = weather(ctx.look_at(f))
        for mat in world["waters"]:
            water.key(mat, water.RAIN, [(f, w.rain)])
        water.key(world["river_material"], water.MIRROR, [(f, w.mirror)])
        water.key(world["river_material"], water.SHINE, [(f, w.shine)])
        for mat in world["wet"]:
            water.key(mat, water.WET, [(f, w.wet)])
        key_light.data.color = w.key_color
        key_light.data.energy = base * w.key_gain
        key_light.data.keyframe_insert("color", frame=f)
        key_light.data.keyframe_insert("energy", frame=f)
        bg.inputs[0].default_value = (*w.ambient, 1)
        bg.inputs[0].keyframe_insert("default_value", frame=f)
