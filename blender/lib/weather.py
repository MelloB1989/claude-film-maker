"""Weather: the air a shot is filmed through, one way for the whole film. Rain in near, mid and far layers round each of
the shot's camera setups, its density, speed and wind keyed over the shot (a downpour thinning to nothing, or slowing to
a stop and hanging in the air); splashes and rings on the water that thin with it; banks of mist in depth in front of the
lens and a volumetric haze; drips off an eave or a hat's brim; sun beams through the mist; and the lightning.

    from lib import cinema, weather
    rig = cinema.film(ctx, [...])                         # the shot's camera (lib/cinema.py)
    sky = weather.storm(ctx, rig)                         # the look schedule's rain and mist (data/look.json), keyed
    sky = weather.storm(ctx, rig, rain=[(0, 1.0), (2.5, 0.3), (4.4, 0.0)], mist=0.8,
                        splashes=[((-6.5, -0.95, 0.004), (7.6, 0.95, 0.004))], waters=world["waters"])
    weather.drips("eave", weather.edge((-7.6, 2.4, 2.1), (-5.8, 2.4, 2.1), 9), fall=2.2)
    weather.sun_beams("beams", (60, 140, 60), (-0.3, -0.85, -0.45), spread=(30, 14), count=7)
    weather.lightning(ctx, [2.1], bolt=((40, 45, 30), (46, 52, -1)), lights=[world["key"]])

A value over the shot is a number, or keys [(s into the shot, value), ...] eased in-out-sine between keys and held
outside them (the look schedule's keys: lib/look_schedule.py). The rain is a pure function of keyed numbers (how far it
has fallen and drifted, its density, its streaks' length and tilt), never of the clock: speed keyed to 0 stops it where
it is (17 freeze) and keyed back up lets it fall on from there.

Each layer of rain is a box in the world round what one setup sees between two distances from its lens (`frustum_box`),
shown only while that setup is cut in: the drops stay put in the world as the camera moves (they parallax), and every
setup has its rain whatever way it faces. Near drops are long, wider streaks (a drop close to the lens smears across the
shutter); far ones fine and faint, many; a drop is a spindle, so from above, looking down the fall, it reads as a short
dot. Everything here whitens with a lightning flash (toon.FLASH). The keys and boxes are numpy only (tests:
blender/tests/test_weather.py); the builders need Blender.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .look_schedule import is_keys, keys_at
from .rig import SENSOR_H_MM

FULL_SPEED = 9.5    # m/s: the film's rain at full fall; a streak is its full length at this speed and over
BEAD = 0.12         # a still drop's length, as a share of its streak's: a bead hanging in the air
G = 9.81


# ---------------------------------------------------------------------------------------------------- values

def value_at(spec, t: float) -> float:
    """A value over the shot (a number, or keys [(s, v), ...]) at t seconds into it."""
    if isinstance(spec, (list, tuple)) and spec and isinstance(spec[0], (list, tuple)):
        return float(keys_at([tuple(k) for k in spec], t))
    return float(spec)


def travel(speeds, dt: float) -> np.ndarray:
    """How far something moving at `speeds` (one per frame, m/s) has gone by each frame (m, 0 at the first), the
    trapezoid's sum: rain keyed to slow down falls less each frame and stops where it is, never jumps."""
    v = np.asarray(speeds, float)
    if len(v) == 0:
        return v
    return np.concatenate([[0.0], np.cumsum((v[1:] + v[:-1]) * 0.5 * dt)])


def stretch(speed: float, full: float = FULL_SPEED) -> float:
    """A streak's length at `speed` as a share of its full length: a drop falling at full speed is a full streak, a
    still one a bead (BEAD), in between in proportion."""
    return BEAD + (1.0 - BEAD) * min(1.0, max(0.0, abs(speed) / max(full, 1e-9)))


def drip(s: float, period: float, hang: float, height: float) -> tuple[float, float]:
    """A drip `s` seconds into its `period`: (how far below the edge it is (m, + down), its size 0..1). It swells on
    the edge for `hang` seconds (0.4 to full), then lets go and falls (free fall) until it has dropped `height` metres,
    then is gone (size 0) until the next."""
    s = s % period
    if s < hang:
        return 0.0, 0.4 + 0.6 * s / max(hang, 1e-9)
    t = s - hang
    dz = 0.5 * G * t * t
    return (dz, 1.0) if dz < height else (height, 0.0)


# ---------------------------------------------------------------------------------------------------- layers

@dataclass(frozen=True)
class Layer:
    """One depth of rain round a setup: drops `near`..`far` metres from the lens, `count` of them at full density,
    streaks `length` long and `width` wide at full speed, `alpha` opaque. `shrink`: drops nearer the lens than this
    shrink with their distance (a fine streak, not a bar across a face); `clear`: none at all within this of it."""
    near: float
    far: float
    count: int
    length: float
    width: float
    alpha: float
    shrink: float = 0.0
    clear: float = 0.0


# the standoff's rain (5200 drops, 0.34 x 0.0055 m, alpha 0.3, in a box 1 to 16 m out) split by depth: a few long,
# heavier streaks close to the lens, the body of it in the middle, and a fine far curtain that greys the distance
LAYERS = {
    "near": Layer(0.6, 3.5, 420, 0.5, 0.008, 0.34, shrink=2.5, clear=0.7),
    "mid": Layer(3.5, 16.0, 4200, 0.34, 0.0055, 0.3),
    "far": Layer(16.0, 70.0, 7000, 0.9, 0.022, 0.12),
}


def frustum_box(poses, near: float, far: float, *, aspect: float = 16 / 9, margin: float = 0.1, floor=None,
                ceiling=None) -> tuple[np.ndarray, np.ndarray]:
    """The world box (lo, hi) round what the cameras `poses` (cinema.Pose) see from `near` to `far` metres in front of
    them: every corner of each view's slab, `margin` of the box's size to spare (a shake, a drop's length), its bottom
    no lower than `floor` and its top no higher than `ceiling` (z) when given."""
    pts = []
    for p in poses:
        r, u, f = p.rotation[:, 0], p.rotation[:, 1], -p.rotation[:, 2]
        for d in (near, far):
            hh = d * SENSOR_H_MM / p.lens / 2
            for sx in (-1, 1):
                for sy in (-1, 1):
                    pts.append(p.position + f * d + r * sx * hh * aspect + u * sy * hh)
    P = np.array(pts)
    lo, hi = P.min(axis=0), P.max(axis=0)
    pad = (hi - lo) * margin
    lo, hi = lo - pad, hi + pad
    if floor is not None:
        lo[2] = max(lo[2], floor)
    if ceiling is not None:
        hi[2] = min(hi[2], ceiling)
    hi[2] = max(hi[2], lo[2] + 0.5)
    return lo, hi


def edge(a, b, n: int) -> np.ndarray:
    """`n` points evenly along an edge from a to b (an eave, a rail): where drips hang."""
    return np.linspace(np.asarray(a, float), np.asarray(b, float), max(n, 1))


def ring(center, radius: float, n: int, *, z: float = 0.0) -> np.ndarray:
    """`n` points round a circle (a hat's brim) of `radius` about `center` at height z over it."""
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    c = np.asarray(center, float)
    return np.column_stack([c[0] + radius * np.cos(a), c[1] + radius * np.sin(a), np.full(n, c[2] + z)])


# ---------------------------------------------------------------------------------------------------- Blender helpers

def _tree(name: str):
    import bpy

    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    return ng


class _Nodes:
    """A small builder over a node tree: math by name, numbers and sockets alike as inputs."""

    def __init__(self, nt):
        self.nt, self.N, self.L = nt, nt.nodes, nt.links

    def put(self, sock, v):
        if isinstance(v, (int, float)):
            sock.default_value = v
        elif isinstance(v, tuple):
            sock.default_value = v
        else:
            self.L.new(v, sock)

    def math(self, op: str, a, b=None, c=None):
        m = self.N.new("ShaderNodeMath")
        m.operation = op
        for sock, v in zip(m.inputs, (a, b, c)):
            if v is not None:
                self.put(sock, v)
        return m.outputs[0]

    def value(self, v: float, name: str):
        n = self.N.new("ShaderNodeValue")
        n.name = n.label = name
        n.outputs[0].default_value = v
        return n

    def random(self, lo: float, hi: float, seed: int, ident=None):
        from .toon import _socket

        r = self.N.new("FunctionNodeRandomValue")
        r.data_type = "FLOAT"
        _socket(r.inputs, "Min", "VALUE").default_value = lo
        _socket(r.inputs, "Max", "VALUE").default_value = hi
        _socket(r.inputs, "Seed").default_value = seed
        if ident is not None:
            self.L.new(ident, _socket(r.inputs, "ID"))
        return _socket(r.outputs, "Value", "VALUE")


def _glass(name: str, color, alpha: float, *, flash_alpha: float = 2.0):
    """An unlit see-through material for drops and spray: `color` at `alpha`, whitening and thickening with a flash."""
    import bpy

    from . import toon

    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(toon.flashed(nt, tuple(color), (1.0, 1.0, 1.0), 1.0), em.inputs["Color"])
    fa = nt.nodes.new("ShaderNodeMapRange")
    fa.inputs["To Min"].default_value = alpha
    fa.inputs["To Max"].default_value = min(1.0, alpha * flash_alpha)
    nt.links.new(toon.scene_value(nt), fa.inputs["Value"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fa.outputs["Result"], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    return mat


def _spindle(name: str, length: float, width: float, material, coll):
    """A raindrop: a thin four-sided spindle `length` along z and `width` across, its fattest a third of the way up
    (a streak's head): a streak from the side, a dot from above. Hidden: rain instances it."""
    import bpy

    w, h = width / 2, length
    verts = [(0, 0, h * 0.66), (w, 0, 0), (0, w, 0), (-w, 0, 0), (0, -w, 0), (0, 0, -h * 0.34)]
    faces = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1), (5, 2, 1), (5, 3, 2), (5, 4, 3), (5, 1, 4)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.materials.append(material)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.hide_render = ob.hide_viewport = True
    return ob


def _key(sock_owner, frame: int, value: float) -> None:
    sock_owner.default_value = value
    sock_owner.keyframe_insert("default_value", frame=frame)


def _linear(ng) -> None:
    """A node tree's keys straight between frames (the rain's travel is already eased frame by frame)."""
    from .toon import _fcurves

    ad = ng.animation_data
    if ad is None or ad.action is None:
        return
    for fc in _fcurves(ad.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


# ---------------------------------------------------------------------------------------------------- rain

class Drops:
    """One layer of rain in a box: its object and the numbers a shot keys on it (`key`)."""

    def __init__(self, name: str, lo, hi, layer: Layer, *, color, seed: int, coll):
        import bpy

        self.name, self.layer = name, layer
        self.lo, self.hi = np.asarray(lo, float), np.asarray(hi, float)
        rng = np.random.default_rng(seed)
        pts = rng.uniform(self.lo, self.hi, size=(layer.count, 3))
        me = bpy.data.meshes.new(name)
        me.from_pydata(pts.tolist(), [], [])
        self.ob = bpy.data.objects.new(name, me)
        coll.objects.link(self.ob)
        self.ob.visible_shadow = False
        drop = _spindle(f"{name}-drop", layer.length, layer.width, _glass(f"{name}-drop", color, layer.alpha), coll)

        ng = _tree(name)
        b = _Nodes(ng)
        N, L = ng.nodes, ng.links
        gin, gout = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
        self.fall = b.value(0.0, "fall")          # metres fallen since the shot began
        self.drift = b.value(0.0, "drift")        # metres blown along +x
        self.density = b.value(1.0, "density")    # the share of the drops falling
        self.stretch = b.value(1.0, "stretch")    # the streaks' length (1 full, BEAD a bead)
        self.tilt = b.value(0.0, "tilt")          # radians the streaks lean downwind
        pos = N.new("GeometryNodeInputPosition")
        sep = N.new("ShaderNodeSeparateXYZ")
        L.new(pos.outputs[0], sep.inputs[0])

        def wrap(coord, lo_v: float, size: float, by, sign: float):
            """The offset that moves `coord` on by `by` (times sign) through the box, wrapping round it."""
            moved = b.math("MULTIPLY_ADD", by, sign, coord)
            u = b.math("FRACT", b.math("DIVIDE", b.math("SUBTRACT", moved, lo_v), size))
            return b.math("SUBTRACT", b.math("MULTIPLY_ADD", u, size, lo_v), coord)

        size = self.hi - self.lo
        comb = N.new("ShaderNodeCombineXYZ")
        L.new(wrap(sep.outputs["X"], float(self.lo[0]), float(size[0]), self.drift.outputs[0], 1.0), comb.inputs["X"])
        L.new(wrap(sep.outputs["Z"], float(self.lo[2]), float(size[2]), self.fall.outputs[0], -1.0), comb.inputs["Z"])
        setp = N.new("GeometryNodeSetPosition")
        L.new(gin.outputs[0], setp.inputs["Geometry"])
        L.new(comb.outputs[0], setp.inputs["Offset"])

        idx = N.new("GeometryNodeInputIndex")
        # which drops fall at this density (each its own threshold), and each a little bigger or smaller
        on = b.math("LESS_THAN", b.random(0.0, 1.0, seed + 7, idx.outputs[0]), self.density.outputs[0])
        k = b.math("MULTIPLY", on, b.random(0.65, 1.3, seed, idx.outputs[0]))
        if layer.shrink or layer.clear:
            cam = N.new("GeometryNodeInputActiveCamera")
            ci = N.new("GeometryNodeObjectInfo")
            ci.transform_space = "ORIGINAL"
            L.new(cam.outputs[0], ci.inputs["Object"])
            p2 = N.new("GeometryNodeInputPosition")
            dist = N.new("ShaderNodeVectorMath")
            dist.operation = "DISTANCE"
            L.new(p2.outputs[0], dist.inputs[0])
            L.new(ci.outputs["Location"], dist.inputs[1])
            d = dist.outputs["Value"]
            if layer.shrink:
                k = b.math("MULTIPLY", k, b.math("MINIMUM", b.math("DIVIDE", d, layer.shrink), 1.0))
            if layer.clear:
                k = b.math("MULTIPLY", k, b.math("GREATER_THAN", d, layer.clear))
        sc = N.new("ShaderNodeCombineXYZ")
        L.new(k, sc.inputs["X"])
        L.new(k, sc.inputs["Y"])
        L.new(b.math("MULTIPLY", k, self.stretch.outputs[0]), sc.inputs["Z"])
        rot = N.new("ShaderNodeCombineXYZ")
        L.new(self.tilt.outputs[0], rot.inputs["Y"])
        info = N.new("GeometryNodeObjectInfo")
        info.inputs["Object"].default_value = drop
        inst = N.new("GeometryNodeInstanceOnPoints")
        L.new(setp.outputs["Geometry"], inst.inputs["Points"])
        L.new(info.outputs["Geometry"], inst.inputs["Instance"])
        L.new(rot.outputs[0], inst.inputs["Rotation"])
        L.new(sc.outputs[0], inst.inputs["Scale"])
        L.new(inst.outputs["Instances"], gout.inputs[0])
        mod = self.ob.modifiers.new(name, "NODES")
        mod.node_group = ng
        self.tree = ng

    def key(self, frame: int, *, fall: float, drift: float, density: float, speed: float, wind: float) -> None:
        _key(self.fall.outputs[0], frame, fall)
        _key(self.drift.outputs[0], frame, drift)
        _key(self.density.outputs[0], frame, density)
        _key(self.stretch.outputs[0], frame, stretch(speed))
        _key(self.tilt.outputs[0], frame, math.atan2(wind, speed) if speed > 0.3 else 0.0)


def _visible(ob, frames, on) -> None:
    """Key `ob` shown on the frames where on(f), hidden elsewhere, held."""
    from .toon import _fcurves

    prev = None
    for f in frames:
        hide = not on(f)
        if hide != prev:
            ob.hide_render = ob.hide_viewport = hide
            ob.keyframe_insert("hide_render", frame=f)
            ob.keyframe_insert("hide_viewport", frame=f)
            prev = hide
    for fc in _fcurves(ob.animation_data.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"


def _setup_poses(rig, i: int, step: int = 4) -> list:
    """Poses of rig's setup i over its window, every `step` frames and its last."""
    a, b = rig.shot.window(i)
    n = max(1, int((b - a) * rig.ctx.fps))
    ts = [a + min(k, n - 1) / rig.ctx.fps for k in list(range(0, n, step)) + [n - 1]]
    return [rig.shot.pose(t) for t in ts]


def _schedule(ctx, field: str):
    """The look schedule's rain `field` over the shot, as a function of film frame (None when the shot has none)."""
    if getattr(ctx, "look", None) is None:
        return None
    return lambda f: getattr(ctx.look_at(f).rain, field)


class Rain:
    """The shot's rain: `drops` {(setup, layer): Drops}, `frames`, and per frame its density, speed and wind (what
    splashes and ripples follow)."""

    def __init__(self, drops, frames, density, speed, wind):
        self.drops, self.frames = drops, frames
        self.density, self.speed, self.wind = density, speed, wind

    def hitting(self, f: int) -> float:
        """How hard it lands at frame f: its density, less as it slows (still rain makes no splashes)."""
        return self.density[f] * min(1.0, self.speed[f] / FULL_SPEED)


def rain(ctx, rig, *, density=None, speed=None, wind=None, layers=None, color=None, floor=None, ceiling=None,
         seed: int = 4, coll=None) -> Rain:
    """Rain round every setup of `rig` (cinema.Rig) over ctx's frames, in `layers` (LAYERS: names to use, or
    {name: Layer}), its `density` (0..1), `speed` (m/s) and `wind` (m/s along +x) values over the shot (a number or
    keys; None: the look schedule's, else full rain). `floor`/`ceiling`: no drops below/above these heights (the water,
    a roof over a doorway's camera). Each setup's layers show only while it is cut in."""
    import bpy

    from . import toon

    coll = coll or toon.collection("rain")
    if layers is None:
        layers = LAYERS
    elif not isinstance(layers, dict):
        layers = {n: LAYERS[n] for n in layers}
    sched = {k: _schedule(ctx, k) for k in ("density", "speed", "wind", "color")}
    if color is None:
        color = sched["color"](ctx.f0) if sched["color"] else (0.78, 0.81, 0.86)

    def over(spec, field, default):
        if spec is not None:
            return lambda f: value_at(spec, (f - ctx.f0) / ctx.fps)
        return sched[field] or (lambda f: default)

    frames = list(rig.frames)
    dens, spd, wnd = over(density, "density", 1.0), over(speed, "speed", FULL_SPEED), over(wind, "wind", 1.8)
    D = {f: max(0.0, min(1.0, float(dens(f)))) for f in frames}
    S = {f: max(0.0, float(spd(f))) for f in frames}
    W = {f: float(wnd(f)) for f in frames}
    dt = 1.0 / ctx.fps
    fall = dict(zip(frames, travel([S[f] for f in frames], dt)))
    # the wind blows the drops along only while they fall (a frozen drop hangs where it is)
    drift = dict(zip(frames, travel([W[f] * min(1.0, S[f] / FULL_SPEED) for f in frames], dt)))

    drops = {}
    for i, s in enumerate(rig.shot.setups):
        poses = _setup_poses(rig, i)
        for j, (ln, layer) in enumerate(layers.items()):
            lo, hi = frustum_box(poses, layer.near, layer.far, aspect=ctx.size[0] / ctx.size[1], floor=floor,
                                 ceiling=ceiling)
            d = Drops(f"rain-{s.name}-{ln}", lo, hi, layer, color=color, seed=seed + 13 * i + j, coll=coll)
            for f in frames:
                d.key(f, fall=fall[f], drift=drift[f], density=D[f], speed=S[f], wind=W[f])
            _linear(d.tree)
            if len(rig.shot.setups) > 1:
                _visible(d.ob, frames, lambda f, n=s.name: rig.setup_at(f) == n)
            drops[(s.name, ln)] = d
    print(f"weather: rain {len(drops)} layer(s) over {len(rig.shot.setups)} setup(s); density "
          f"{D[frames[0]]:.2f}->{D[frames[-1]]:.2f}, speed {S[frames[0]]:.1f}->{S[frames[-1]]:.1f} m/s")
    bpy.context.view_layer.update()
    return Rain(drops, frames, D, S, W)


# ---------------------------------------------------------------------------------------------------- what the rain hits

def thin(ob, frames_values, *, seed: int = 9):
    """Key how much of a scattering object's instances show (toon.splashes, toon.rain: anything whose Geometry Nodes
    put out instances) to [(frame, 0..1), ...]: a modifier after its own drops all but that share. Returns its value."""
    import bpy

    ng = _tree(f"{ob.name}-thin")
    b = _Nodes(ng)
    N, L = ng.nodes, ng.links
    gin, gout = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    amount = b.value(1.0, "amount")
    idx = N.new("GeometryNodeInputIndex")
    gone = b.math("GREATER_THAN", b.random(0.0, 1.0, seed, idx.outputs[0]), amount.outputs[0])
    dg = N.new("GeometryNodeDeleteGeometry")
    dg.domain = "INSTANCE"
    L.new(gin.outputs[0], dg.inputs["Geometry"])
    L.new(gone, dg.inputs["Selection"])
    L.new(dg.outputs[0], gout.inputs[0])
    mod = ob.modifiers.new("thin", "NODES")
    mod.node_group = ng
    for f, v in frames_values:
        _key(amount.outputs[0], f, float(v))
    _linear(ng)
    return amount


def splashes(rain_: Rain, areas, *, count: int = 260, seed: int = 21, coll=None, **kw) -> list:
    """Crowns of spray where the rain lands on `areas` [(lo, hi), ...] (a deck, the river: lo's z is the surface),
    thinning and stopping as the rain does (toon.splashes, `thin`). Returns the objects."""
    from . import toon

    out = []
    for k, (lo, hi) in enumerate(areas):
        ob = toon.splashes(f"splash{k}", lo, hi, count=count, seed=seed + k, coll=coll, **kw)
        thin(ob, [(f, rain_.hitting(f)) for f in rain_.frames], seed=seed + 50 + k)
        out.append(ob)
    return out


def ripples(rain_: Rain, materials) -> None:
    """Key the rings the rain opens on water and puddles (lib/water.py surfaces) to how hard it lands."""
    from . import water

    for mat in materials:
        water.key(mat, water.RAIN, [(f, rain_.hitting(f)) for f in rain_.frames])


# ---------------------------------------------------------------------------------------------------- mist and haze

# banks of mist in front of each setup's lens: (metres out, height of the band's middle over `ground`, its height,
# opacity): a thin veil close, thicker ones further out, each drifting at its own pace
BANKS = ((6.0, 0.4, 2.2, 0.18), (14.0, 0.8, 4.5, 0.32), (30.0, 1.5, 9.0, 0.45), (60.0, 3.0, 16.0, 0.55))


def mist(ctx, rig, *, density=None, color=None, banks=BANKS, ground: float = 0.0, coll=None, seed: int = 3) -> list:
    """Banks of drifting mist (toon.mist_card) across each setup's view at `banks`' distances, facing its lens, as wide
    as it sees there, their opacity times `density` over the shot (a value; None: the look schedule's, relative to its
    cold 0.6). Each setup's banks show only while it is cut in. Returns [(object, its density socket)]."""
    from . import toon

    coll = coll or toon.collection("mist")
    frames = list(rig.frames)
    if density is not None:
        dens = lambda f: value_at(density, (f - ctx.f0) / ctx.fps)  # noqa: E731
    elif getattr(ctx, "look", None) is not None:
        dens = lambda f: ctx.look_at(f).mist.density / 0.6  # noqa: E731
    else:
        dens = lambda f: 1.0  # noqa: E731
    if color is None:
        color = ctx.look_at(ctx.f0).mist_color() if getattr(ctx, "look", None) is not None else (0.5, 0.53, 0.58)
    aspect = ctx.size[0] / ctx.size[1]
    out = []
    for i, s in enumerate(rig.shot.setups):
        poses = _setup_poses(rig, i)
        p0 = poses[len(poses) // 2]
        f = -p0.rotation[:, 2]
        flat = np.array([f[0], f[1], 0.0])
        flat /= max(np.linalg.norm(flat), 1e-9)
        yaw = math.atan2(flat[0], -flat[1])          # a card faces -y; turned to face back along the view
        for k, (d, z, h, a) in enumerate(banks):
            c = np.mean([p.position for p in poses], axis=0) + flat * d
            hw = d * SENSOR_H_MM / min(p.lens for p in poses) / 2 * aspect
            spread = max(np.linalg.norm(p.position - poses[0].position) for p in poses)
            card = toon.mist_card(f"mist-{s.name}-{k}", (c[0], c[1], ground + z), (2.6 * hw + 2 * spread + 4.0, h),
                                  tuple(color), density=a, drift=0.25 + 0.12 * k, seed=seed + k * 2.3,
                                  rotation=(math.pi / 2, 0.0, yaw))
            toon.move_to(card, coll)
            sock = next(n for n in card.active_material.node_tree.nodes
                        if n.bl_idname == "ShaderNodeMath" and n.operation == "MULTIPLY"
                        and abs(n.inputs[1].default_value - a) < 1e-6).inputs[1]
            for fr in frames:
                _key(sock, fr, a * max(0.0, dens(fr)))
            if len(rig.shot.setups) > 1:
                _visible(card, frames, lambda fr, n=s.name: rig.setup_at(fr) == n)
            out.append((card, sock))
    return out


def haze(ctx, rig, *, density=0.02, color=(0.6, 0.63, 0.68), anisotropy: float = 0.3, reach: float = 80.0, coll=None):
    """A volumetric haze filling everything each setup sees out to `reach` metres (a box of Principled Volume): light
    scatters in it, so a lantern or a sun beam glows through it and the distance pales with real depth. `density` is a
    value over the shot. Slow on a software renderer: for the finals and the shots that need it."""
    import bpy

    from . import shapes, toon

    coll = coll or toon.collection("haze")
    poses = [p for i in range(len(rig.shot.setups)) for p in _setup_poses(rig, i)]
    lo, hi = frustum_box(poses, 0.05, reach, aspect=ctx.size[0] / ctx.size[1], margin=0.05)
    c, s = (lo + hi) / 2, (hi - lo) / 2
    verts = [tuple(c + s * np.array(v)) for v in
             ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mat = bpy.data.materials.new("haze")
    nt = toon.nodes(mat)
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (*color, 1)
    vol.inputs["Anisotropy"].default_value = anisotropy
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(vol.outputs[0], out.inputs["Volume"])
    ob = shapes.mesh_object("haze", verts, faces, mat, coll, smooth=False)
    ob.visible_shadow = False
    for f in rig.frames:
        vol.inputs["Density"].default_value = value_at(density, (f - ctx.f0) / ctx.fps)
        vol.inputs["Density"].keyframe_insert("default_value", frame=f)
    ctx.scene.eevee.volumetric_end = reach
    return ob


# ---------------------------------------------------------------------------------------------------- drips

def drips(name: str, points, *, period: float = 1.1, hang: float = 0.7, fall: float = 1.5, size: float = 0.012,
          color=(0.8, 0.84, 0.9), alpha: float = 0.6, parent=None, seed: int = 5, coll=None):
    """Water dripping off an edge: at each of `points` (an eave's `edge`, a brim's `ring`; in `parent`'s space when
    given: an object, or (armature, bone) for a hat on a head) a drop swells for about `hang` s, lets go and falls
    `fall` metres, again every `period` s or so (each its own phase and pace: `drip`). A pure function of the scene's
    time. Returns the object."""
    import bpy

    from . import toon

    coll = coll or toon.collection("drips")
    P = np.asarray(points, float)
    me = bpy.data.meshes.new(name)
    me.from_pydata(P.tolist(), [], [])
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.visible_shadow = False
    if parent is not None:
        if isinstance(parent, (tuple, list)):
            ob.parent, ob.parent_type, ob.parent_bone = parent[0], "BONE", parent[1]
            # bone parenting places the child at the bone's tail: the points are given from its head
            ob.location = (0.0, -parent[0].data.bones[parent[1]].length, 0.0)
        else:
            ob.parent = parent
    drop = _spindle(f"{name}-drop", size * 2.2, size, _glass(f"{name}-drop", color, alpha), coll)

    ng = _tree(name)
    b = _Nodes(ng)
    N, L = ng.nodes, ng.links
    gin, gout = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    idx = N.new("GeometryNodeInputIndex")
    tnode = N.new("GeometryNodeInputSceneTime")
    per = b.math("MULTIPLY", b.random(0.75, 1.3, seed, idx.outputs[0]), period)       # each its own pace
    phase = b.math("MULTIPLY", b.random(0.0, 1.0, seed + 1, idx.outputs[0]), per)
    s = b.math("FLOORED_MODULO", b.math("ADD", tnode.outputs["Seconds"], phase), per)  # seconds into this drip
    hold = b.math("MULTIPLY", per, hang / period)
    t = b.math("MAXIMUM", b.math("SUBTRACT", s, hold), 0.0)                             # seconds falling
    dz = b.math("MULTIPLY", b.math("MULTIPLY", t, t), 0.5 * G)
    alive = b.math("LESS_THAN", dz, fall)
    swell = b.math("MINIMUM", b.math("MULTIPLY_ADD", b.math("DIVIDE", s, hold), 0.6, 0.4), 1.0)
    k = b.math("MULTIPLY", alive, swell)
    off = N.new("ShaderNodeCombineXYZ")
    L.new(b.math("MULTIPLY", dz, -1.0), off.inputs["Z"])
    setp = N.new("GeometryNodeSetPosition")
    L.new(gin.outputs[0], setp.inputs["Geometry"])
    L.new(off.outputs[0], setp.inputs["Offset"])
    sc = N.new("ShaderNodeCombineXYZ")
    L.new(k, sc.inputs["X"])
    L.new(k, sc.inputs["Y"])
    L.new(b.math("MULTIPLY", k, b.math("MULTIPLY_ADD", t, 6.0, 1.0)), sc.inputs["Z"])   # it stretches as it falls
    info = N.new("GeometryNodeObjectInfo")
    info.inputs["Object"].default_value = drop
    inst = N.new("GeometryNodeInstanceOnPoints")
    L.new(setp.outputs["Geometry"], inst.inputs["Points"])
    L.new(info.outputs["Geometry"], inst.inputs["Instance"])
    L.new(sc.outputs[0], inst.inputs["Scale"])
    L.new(inst.outputs["Instances"], gout.inputs[0])
    mod = ob.modifiers.new(name, "NODES")
    mod.node_group = ng
    return ob


# ---------------------------------------------------------------------------------------------------- light

def sun_beams(name: str, origin, direction, *, spread=(24.0, 10.0), length: float = 120.0, count: int = 7,
              width=(2.0, 9.0), color=(1.0, 0.82, 0.55), strength: float = 0.35, seed: int = 2, camera=None,
              coll=None, scene=None) -> list:
    """Shafts of sunlight through the mist (25 light): `count` long cards from about `origin` (where the light breaks
    through, metres) along `direction` (the sun's travel), fanned over `spread` (m across, m up) at the source,
    widening from width[0] to width[1] along their `length`, each fading in from its source and out at its end, soft at
    its edges and slowly breathing (the mist moving through it). Each turns about its own length to face `camera`
    (default the scene's). `strength` is a scene property "beams" times this, so a shot can key them in as the cloud
    opens (scene["beams"]: 0 none, 1 full; set to 1). Returns the cards."""
    import bpy

    from . import shapes, toon

    scene = scene or bpy.context.scene
    coll = coll or toon.collection("beams")
    camera = camera or scene.camera
    if "beams" not in scene:
        scene["beams"] = 1.0
    rng = np.random.default_rng(seed)
    o, d = np.asarray(origin, float), np.asarray(direction, float)
    d /= np.linalg.norm(d)
    side = np.cross(d, (0.0, 0.0, 1.0))
    side /= max(np.linalg.norm(side), 1e-9)
    up = np.cross(side, d)
    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    b = _Nodes(nt)
    uv = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs[0])
    u, v = sep.outputs["X"], sep.outputs["Y"]      # u across the shaft (0..1), v along it from the source
    across = b.math("SUBTRACT", 1.0, b.math("POWER", b.math("ABSOLUTE", b.math("MULTIPLY_ADD", u, 2.0, -1.0)), 1.6))
    along = b.math("MULTIPLY", b.math("MINIMUM", b.math("DIVIDE", v, 0.15), 1.0),
                   b.math("POWER", b.math("SUBTRACT", 1.0, v), 1.4))
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.5
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(u, comb.inputs["X"])
    nt.links.new(b.math("ADD", b.math("MULTIPLY", v, 0.4), toon.frame_value(nt, scene, 0.05)), comb.inputs["Y"])
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    nt.links.new(oi.outputs["Random"], comb.inputs["Z"])
    nt.links.new(comb.outputs[0], noise.inputs["Vector"])
    breath = b.math("MULTIPLY_ADD", noise.outputs["Fac"], 1.2, -0.1)
    lvl = toon.scene_value(nt, "beams")
    a = b.math("MULTIPLY", b.math("MULTIPLY", b.math("MULTIPLY", across, along), breath),
               b.math("MULTIPLY", lvl, strength))
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    add = nt.nodes.new("ShaderNodeAddShader")       # light added over what is behind: a beam never darkens
    nt.links.new(tr.outputs[0], add.inputs[0])
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(b.math("MINIMUM", b.math("MAXIMUM", a, 0.0), 1.0), mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], add.inputs[1])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"

    cards = []
    for k in range(count):
        s0 = o + side * rng.uniform(-0.5, 0.5) * spread[0] + up * rng.uniform(-0.5, 0.5) * spread[1]
        dk = d + side * rng.uniform(-0.06, 0.06) + up * rng.uniform(-0.04, 0.04)
        dk /= np.linalg.norm(dk)
        ln = length * rng.uniform(0.7, 1.1)
        w0, w1 = (w * rng.uniform(0.6, 1.4) for w in width)
        # a card in its own space: x across, y along the shaft; placed at its source, its y turned onto dk
        verts = [(-w0 / 2, 0, 0), (w0 / 2, 0, 0), (w1 / 2, ln, 0), (-w1 / 2, ln, 0)]
        ob = shapes.mesh_object(f"{name}{k}", verts, [(0, 1, 2, 3)], mat, coll, smooth=False)
        ob.data.uv_layers.new(name="UVMap")
        for loop, (uu, vv) in zip(ob.data.uv_layers[0].data, ((0, 0), (1, 0), (1, 1), (0, 1))):
            loop.uv = (uu, vv)
        ob.location = tuple(s0)
        ob.visible_shadow = False
        if camera is not None:
            c = ob.constraints.new("LOCKED_TRACK")
            c.target = camera
            c.lock_axis = "LOCK_Y"
            c.track_axis = "TRACK_Z"
        from mathutils import Vector
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = Vector(tuple(dk)).to_track_quat("Y", "Z")
        cards.append(ob)
    return cards


def lightning(ctx, strikes, *, bolt=None, lights=(), flare: float = 4.0, width: float = 2.5, seed: int = 11) -> dict:
    """Strikes of lightning `strikes` seconds into the shot: the scene's FLASH keyed (every toon material, the rain,
    the spray and the drips whiten with it), the `lights` flared to `flare` times their energy at its height, and the
    fork itself (`bolt`: (sky point, ground point), world metres; toon.bolt, seen only while it flashes). Returns
    frame -> flash (0..1) for whatever else the shot flashes, and pair it with a cinema.Shake hit on the same times."""
    from . import toon

    frames = range(ctx.f0 - 1, ctx.f1 + 1)
    vals = toon.lightning(ctx.scene, list(strikes), frames, ctx.fps, ctx.f0)
    for li in lights:
        base = li.data.energy
        for f in frames:
            li.data.energy = base * (1.0 + (flare - 1.0) * vals[f])
            li.data.keyframe_insert("energy", frame=f)
        for fc in toon._fcurves(li.data.animation_data.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
    if bolt is not None:
        toon.bolt("bolt", bolt[0], bolt[1], width=width, seed=seed)
    return vals


# ---------------------------------------------------------------------------------------------------- one call

@dataclass
class Sky:
    """What `storm` built: the rain, its splashes, the mist's banks, the haze (or None), the flash per frame."""
    rain: Rain | None
    splashes: list
    mist: list
    haze: object = None
    flash: dict | None = None


def storm(ctx, rig, *, rain=None, speed=None, wind=None, layers=None, mist=None, splashes=(), waters=(),
          haze=None, strikes=None, bolt=None, lights=(), floor=None, ground: float = 0.0, seed: int = 4) -> Sky:
    """A shot's weather in one call, round `rig`'s setups (cinema.Rig): its rain (`rain`: the density over the shot,
    `speed`, `wind`; None: the look schedule's) in `layers` near, mid and far, splashing on `splashes` areas
    [(lo, hi), ...] and ringing the `waters` (lib/water.py materials), all thinning with it; banks of `mist` (its
    density times the banks' own; None the schedule's, 0 none) standing on `ground`; a volumetric `haze` (a density,
    None none); and lightning at `strikes` (None: the schedule's) with its `bolt` and flaring `lights`. No rain at all
    when its density stays 0 over the shot."""
    sched = getattr(ctx, "look", None) is not None
    frames = list(rig.frames)
    if rain is None and sched:
        wet = max(ctx.look_at(f).rain.density for f in frames) > 0.001
    else:
        wet = rain is None or max(value_at(rain, (f - ctx.f0) / ctx.fps) for f in frames) > 0.001
    r = globals()["rain"](ctx, rig, density=rain, speed=speed, wind=wind, layers=layers, floor=floor,
                          seed=seed) if wet else None
    sp = splashes and r and globals()["splashes"](r, splashes) or []
    if r and waters:
        ripples(r, waters)
    banks = [] if mist == 0 else globals()["mist"](ctx, rig, density=mist, ground=ground)
    hz = None if haze is None else globals()["haze"](ctx, rig, density=haze)
    if strikes is None and sched:
        strikes = list(getattr(ctx.look, "lightning", None) or [])
    flash = lightning(ctx, strikes, bolt=bolt, lights=lights) if strikes else None
    return Sky(r, sp, banks, hz, flash)
