"""The Rain Ferry's valley seen from high on its slope: the film's establishing view, which opens it in the rain
(shots/open.py), lights up gold when the rain stops (shots/light.py) and carries the title (shots/title.py). Ridge after
ridge of pine-fringed mountains closing in on a winding river far below, mist pooled in the valley between them, the
ferrywoman's hut with its red lantern and the jetty small on the near bank, a sky of cloud that can open on the sun.

An ink-wash distance is ink that pales into the mist: every surface here is painted (emission) in one of two inks, its
shade and its lit side (a sun's light cut into a soft band), brushed with a little texture, then faded toward the fog
by its distance and, low in the valley, by height (the mist lying in it). Its colours are not fixed: every material
reads them from the scene's properties (`PROPS`), which `key(scene, frame, state)` keys from the look schedule's state
(lib/look_schedule.py: the light's sky, fog, key, accent and warm gold; the rain and the mist), so the same world turns
from the cold rain to gold light frame by frame as the schedule says, and `sun` opens the clouds.

World axes: z up, metres; the river runs from near the camera (y small) away up the valley toward +y; the camera stands
on the left (west) slope looking up the valley. `height(x, y)` is the land (numpy, tested without Blender); `build`
needs Blender.
"""
from __future__ import annotations

import math

import numpy as np

from . import sets

WATER_Z = sets.WATER_Z
EXTENT = (-3200.0, 3200.0, -900.0, 7000.0)     # the land's x and y range (m)
GRID = (230, 250)                               # its vertices across and along
# the valley's camera: where it stands (x, y, height over the land), what it looks at
CAMERA = (-75.0, -390.0, 45.0)        # (x, y, metres over the land), up the near slope behind the crossing
AIM = (60.0, 1900.0, -110.0)
SUN = (0.42, 1.0, 0.19)          # toward the sun (behind the valley's right side, low): the gold light's direction
SKY_FAR = 9000.0                  # the sky dome's radius
# the scene properties the materials read (linear colours, or 0..1)
PROPS = ("rf_zenith", "rf_horizon", "rf_fog", "rf_lit", "rf_shade", "rf_accent", "rf_gold", "rf_sun", "rf_rain",
         "rf_mist", "rf_flash")
INK = (0.010, 0.011, 0.014)      # the darkest ink, the shade of the near slopes
TREE_INK = (0.006, 0.007, 0.009)


# ---------------------------------------------------------------------------------------------------- the land

def _hash(ix, iy, seed):
    h = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h ^ (h >> 16)) / 0xFFFFFFFF


def noise(x, y, seed: int = 0) -> np.ndarray:
    """Smooth value noise in 0..1 at points (x, y) (any shape, units of one cell)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ix, iy = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = x - ix, y - iy
    ux, uy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _hash(ix, iy, seed), _hash(ix + 1, iy, seed)
    c, d = _hash(ix, iy + 1, seed), _hash(ix + 1, iy + 1, seed)
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy


def ridged(x, y, octaves: int = 5, seed: int = 0) -> np.ndarray:
    """Ridged fractal noise in about 0..1: sharp crests and soft valleys, as mountains are."""
    out, amp, f, total = 0.0, 1.0, 1.0, 0.0
    for o in range(octaves):
        n = 1.0 - np.abs(2.0 * noise(x * f, y * f, seed + o) - 1.0) ** 1.6     # crests rounded a little, not glass
        out = out + amp * n * n
        total += amp
        amp *= 0.5
        f *= 2.03
    return out / total


def _away(y) -> np.ndarray:
    """0 by the crossing, rising to 1 well up the valley: where the vista's own river and mountains take over from
    the film's set (rf/set_valley.py)."""
    return np.clip((np.asarray(y, float) - 350.0) / 700.0, 0.0, 1.0) ** 2


def banks(y) -> tuple[np.ndarray, np.ndarray]:
    """The river's near (west) and far (east) waterlines at y: the set's by the crossing (set_valley.near_edge and
    far_edge: the jetty's bank, the far bank about 75 m off), then winding away and widening up the valley."""
    from . import set_valley

    y = np.asarray(y, float)
    k = _away(y)
    wind = 150.0 * k * np.sin((y - 350.0) / 950.0) + 90.0 * k * np.sin((y - 350.0) / 380.0 + 0.4)
    widen = 0.025 * np.maximum(y - 350.0, 0.0)
    return set_valley.near_edge(y) - wind - widen * 0.4, set_valley.far_edge(y) - wind + widen * 0.6


def river_x(y) -> np.ndarray:
    """The river's middle across x at y."""
    a, b = banks(y)
    return (a + b) / 2


def river_half(y) -> np.ndarray:
    """The river's half width at y (m)."""
    a, b = banks(y)
    return (b - a) / 2


def height(x, y) -> np.ndarray:
    """The land's height (m) at (x, y): the river's bed, banks rising steeply into mountains whose spurs reach in from
    each side in turn up the valley (so the river weaves between them), taller the further up it; by the crossing,
    the set's own ground (set_valley.ground) along the banks, so the jetty, the hut and the path stand where every
    other shot has them."""
    from . import set_valley

    x, y = np.asarray(x, float), np.asarray(y, float)
    yy = np.maximum(y, 0.0)
    mid, half = river_x(y), river_half(y)
    side = np.sign(x - mid)
    k = _away(y)
    # spurs: each side's ridges reach in toward the river up the valley, the two sides out of step
    spur = 0.5 + 0.5 * np.sin(yy / (380.0 + 0.12 * yy) + side * 1.9 + 0.8)
    inland = np.abs(x - mid) - half
    d = inland - 30.0 * (1 - spur) * k
    reach = 90.0 + 0.09 * yy
    rise = 1.0 - np.exp(-1.4 * np.clip(d / reach, 0.0, None))     # steep at the bank, levelling to the crests
    tall = 170.0 + 0.2 * yy                                         # the mountains' height grows up the valley
    s = 1.0 / (260.0 + 0.06 * yy)
    m = 0.55 + 0.75 * ridged(x * s, y * s, seed=3) * (0.6 + 0.6 * spur)
    h = tall * rise * m
    # rock and gullies on the slopes
    h = h + 22.0 * rise * (noise(x / 60.0, y / 60.0, 11) - 0.5) + 8.0 * (noise(x / 17.0, y / 17.0, 12) - 0.5) * rise
    mine = np.where(d < 0, WATER_Z - 3.0 + d * 0.02, h + WATER_Z - 1.5)
    # by the crossing: the set's ground (sunk a little under its fine ground round the ferry, as the set sinks its own)
    w = np.clip((140.0 - inland) / 70.0, 0.0, 1.0) * np.clip((430.0 - np.abs(y)) / 130.0, 0.0, 1.0)
    theirs = set_valley.ground(x, y) - 1.2 * set_valley.fine_mask(x, y)
    return w * theirs + (1 - w) * mine


def grid(extent=EXTENT, size=GRID):
    """The land's sample points: x evenly across, y bunched near the camera (where it sees detail) and opening out
    up the valley. Returns (xs, ys)."""
    x0, x1, y0, y1 = extent
    nx, ny = size
    u = np.linspace(0.0, 1.0, nx)
    xs = x0 + (x1 - x0) * (0.5 + 0.5 * np.sign(u - 0.5) * np.abs(2 * u - 1) ** 1.6)   # denser in the middle
    v = np.linspace(0.0, 1.0, ny)
    ys = y0 + (y1 - y0) * v ** 1.9
    return xs, ys


def tree_density(x, y, z, slope, cam=CAMERA) -> np.ndarray:
    """Where pines grow and how thickly (trees per m² before their size): on the slopes above the water, thinning on
    cliffs, kept to about the same count on screen by thinning with the distance from the camera (the far ones are
    drawn bigger)."""
    dist = np.hypot(x - cam[0], y - cam[1])
    above = np.clip((z - 4.0) / 10.0, 0.0, 1.0)
    steep = np.clip(1.4 - slope, 0.0, 1.0)
    return above * steep * (0.4 / tree_size(dist) ** 2) * (dist < 5500.0)


def tree_size(dist) -> np.ndarray:
    """A pine's height (m) at `dist` from the camera: real near it, drawn larger far off so the ridges' fringes read."""
    return 7.0 + 0.012 * np.asarray(dist, float)


# ---------------------------------------------------------------------------------------------------- materials

def _key_props(scene, frame, values: dict) -> None:
    for k, v in values.items():
        scene[k] = v
        if frame is not None:
            scene.keyframe_insert(f'["{k}"]', frame=frame)


def palette(state, *, sun: float | None = None, flash: float = 0.0) -> dict:
    """The scene's properties from a look schedule state: the sky's zenith and horizon, the fog, the lit side's
    colour (the key, brighter and gold as it warms), the shade, the accent, the gold, the clouds' opening (`sun`;
    default: as warm as the state is), the rain, the mist, and a lightning flash."""
    L = state.light
    w = state.warm
    sun = w if sun is None else sun
    k = L.key_strength
    lit = tuple(min(4.0, c * k * (0.035 + 0.3 * w)) for c in L.key)
    zen = tuple(c * (0.62 + 0.1 * w) for c in L.sky)
    shade = tuple(i * (1 - w) + c * w for i, c in zip(INK, (0.03, 0.022, 0.016)))
    return {"rf_zenith": zen, "rf_horizon": tuple(L.sky), "rf_fog": tuple(L.fog), "rf_lit": lit, "rf_shade": shade,
            "rf_accent": tuple(L.accent), "rf_gold": tuple(L.warm), "rf_sun": float(sun),
            "rf_rain": float(min(1.0, state.rain.density)), "rf_mist": float(state.mist.density), "rf_flash": float(flash)}


def key(scene, frame, state, **kw) -> dict:
    """Key the world's colours at `frame` (None: set them) from a look schedule state (`palette`'s keywords pass on).
    Returns the palette."""
    p = palette(state, **kw)
    _key_props(scene, frame, p)
    return p


class _Nodes:
    """A small helper for building node trees."""

    def __init__(self, nt):
        self.nt, self.N, self.L = nt, nt.nodes, nt.links

    def new(self, kind, **inputs):
        n = self.N.new(kind)
        for k, v in inputs.items():
            self.set(n.inputs[k], v)
        return n

    def set(self, sock, v):
        if isinstance(v, (int, float, tuple)):
            sock.default_value = v if not isinstance(v, tuple) else (v + (1.0,) if len(sock.default_value) == 4 and len(v) == 3 else v)
        else:
            self.L.new(v, sock)

    def prop(self, name, color=False):
        a = self.N.new("ShaderNodeAttribute")
        a.attribute_type = "VIEW_LAYER"
        a.attribute_name = name
        return a.outputs["Color" if color else "Fac"]

    def math(self, op, a, b=0.0, c=None, clamp=False):
        n = self.N.new("ShaderNodeMath")
        n.operation, n.use_clamp = op, clamp
        self.set(n.inputs[0], a)
        self.set(n.inputs[1], b)
        if c is not None:
            self.set(n.inputs[2], c)
        return n.outputs[0]

    def mix(self, fac, a, b, blend="MIX"):
        n = self.N.new("ShaderNodeMix")
        n.data_type, n.blend_type = "RGBA", blend
        self.set(n.inputs["Factor"], fac)
        self.set(n.inputs["A"], a)
        self.set(n.inputs["B"], b)
        return n.outputs["Result"]

    def vmath(self, op, a, b=None, scale=None):
        n = self.N.new("ShaderNodeVectorMath")
        n.operation = op
        self.set(n.inputs[0], a)
        if b is not None:
            self.set(n.inputs[1], b)
        if scale is not None:
            self.set(n.inputs["Scale"], scale)
        return n.outputs["Value" if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else "Vector"]

    def ramp(self, value, lo, hi, smooth=True, to=(0.0, 1.0)):
        n = self.N.new("ShaderNodeMapRange")
        if smooth:
            n.interpolation_type = "SMOOTHSTEP"
        n.inputs["From Min"].default_value = lo
        n.inputs["From Max"].default_value = hi
        n.inputs["To Min"].default_value = to[0]
        n.inputs["To Max"].default_value = to[1]
        self.set(n.inputs["Value"], value)
        return n.outputs["Result"]

    def noise(self, vector, scale, detail=3.0, rough=0.55):
        n = self.new("ShaderNodeTexNoise", Scale=scale, Detail=detail, Roughness=rough)
        self.set(n.inputs["Vector"], vector)
        return n.outputs["Fac"]

    def clock(self, scene, scale=1.0):
        v = self.N.new("ShaderNodeValue")
        fc = v.outputs[0].driver_add("default_value")
        fc.driver.type = "SCRIPTED"
        fps = scene.render.fps / scene.render.fps_base
        fc.driver.expression = f"frame / {fps:.6f} * {scale:.6f}"
        return v.outputs[0]

    def out(self, surface):
        o = self.N.new("ShaderNodeOutputMaterial")
        self.L.new(surface, o.inputs["Surface"])


def _material(name):
    import bpy

    from lib import toon

    mat = bpy.data.materials.new(name)
    return mat, _Nodes(toon.nodes(mat))


def fogged(n: _Nodes, col, *, cam, haze: float = 1.0, mist: float = 0.75, mist_low: float = 40.0, scene=None):
    """`col` faded toward the fog: by its distance from the camera (an ink-wash distance pales but never vanishes)
    and, low in the valley, by the mist lying there (drifting, thicker as `rf_mist` is, times `mist`)."""
    geo = n.N.new("ShaderNodeNewGeometry")
    dist = n.vmath("DISTANCE", geo.outputs["Position"], tuple(cam))
    # dark ink near, paling with the distance's square-ish (an ink painting's near ridge is black, its far one a breath)
    reach = n.math("POWER", n.math("DIVIDE", dist, 4300.0), 1.7)
    fd = n.math("MULTIPLY", n.math("SUBTRACT", 1.0, n.math("EXPONENT", n.math("MULTIPLY", reach, -1.0))), 0.95 * haze)
    sep = n.new("ShaderNodeSeparateXYZ")
    n.set(sep.inputs[0], geo.outputs["Position"])
    # the mist: densest at the water, gone by `mist_low` m up (higher far up the valley), torn by drifting noise
    lift = n.math("MULTIPLY_ADD", sep.outputs["Y"], 0.025, mist_low)
    low = n.math("SUBTRACT", 1.0, n.math("DIVIDE", sep.outputs["Z"], lift), clamp=True)
    t = n.clock(scene, 4.0) if scene is not None else 0.0
    drift = n.new("ShaderNodeCombineXYZ")
    n.set(drift.inputs["X"], n.math("ADD", n.math("MULTIPLY", sep.outputs["X"], 1.0), t))
    n.set(drift.inputs["Y"], n.math("MULTIPLY", sep.outputs["Y"], 0.4))
    n.set(drift.inputs["Z"], n.math("MULTIPLY", sep.outputs["Z"], 3.0))
    torn = n.ramp(n.noise(drift.outputs[0], 0.004, 4.0, 0.6), 0.35, 0.7)
    fm = n.math("MULTIPLY", n.math("MULTIPLY", n.math("POWER", low, 1.6), n.math("MULTIPLY_ADD", torn, 0.7, 0.3)),
                n.math("MULTIPLY", n.prop("rf_mist"), mist), clamp=True)
    fm = n.math("MULTIPLY", fm, n.ramp(dist, 350.0, 1400.0))      # the mist lies off in the valley, not on our slope
    f = n.math("MAXIMUM", fd, fm, clamp=True)
    return n.mix(f, col, n.prop("rf_fog", True))


def wash(name: str, *, cam, ink=INK, lit_k: float = 1.0, texture: float = 0.5, scene=None, haze: float = 1.0):
    """The land's ink: the shade (`rf_shade`, or `ink` darker) and the lit side (`rf_lit`) by the sun's light cut
    into a soft band, rim-lit gold toward the sun as it opens (`rf_sun`), brushed with texture (`texture` 0..1),
    then `fogged`."""
    mat, n = _material(name)
    diff = n.new("ShaderNodeBsdfDiffuse")
    s2r = n.new("ShaderNodeShaderToRGB")
    n.L.new(diff.outputs[0], s2r.inputs[0])
    lum = n.new("ShaderNodeRGBToBW")
    n.L.new(s2r.outputs["Color"], lum.inputs[0])
    band = n.ramp(lum.outputs[0], 0.18, 0.5)
    geo = n.N.new("ShaderNodeNewGeometry")
    tc = n.N.new("ShaderNodeTexCoord")
    # brushwork: long strokes across the slope and a dry-brush grain
    stroke = n.new("ShaderNodeMapping")
    stroke.inputs["Scale"].default_value = (1.0, 1.0, 6.0)
    n.L.new(tc.outputs["Object"], stroke.inputs["Vector"])
    # the strokes: rock and gully run down the slope (cun, the texture strokes of a mountain), a finer grain over them
    brush = n.math("MULTIPLY_ADD", n.noise(stroke.outputs[0], 0.02, 6.0, 0.7), 2.0 * texture, 1.0 - texture)
    shade = n.mix(1.0, n.prop("rf_shade", True), (ink[0] / INK[0], ink[1] / INK[1], ink[2] / INK[2]), "MULTIPLY")
    lit = n.mix(1.0, n.prop("rf_lit", True), (lit_k, lit_k, lit_k), "MULTIPLY")
    col = n.mix(n.math("MULTIPLY", band, brush, clamp=True), shade, n.mix(0.5, shade, lit, "ADD"))
    col = n.mix(1.0, col, n.math("MULTIPLY_ADD", brush, 1.1, 0.35), "MULTIPLY")
    # a rim of gold on the slopes facing the sun as the clouds open
    facing = n.math("MAXIMUM", n.vmath("DOT_PRODUCT", geo.outputs["Normal"], _unit(SUN)), 0.0)
    rim = n.math("MULTIPLY", n.ramp(facing, 0.45, 0.85), n.prop("rf_sun"))
    col = n.mix(n.math("MULTIPLY", rim, 0.55), col, n.mix(1.0, n.prop("rf_gold", True), (0.5, 0.5, 0.5), "MULTIPLY"))
    col = fogged(n, col, cam=cam, haze=haze, scene=scene)
    em = n.new("ShaderNodeEmission")
    n.set(em.inputs["Color"], col)
    n.out(em.outputs[0])
    return mat


def _unit(v):
    a = np.asarray(v, float)
    return tuple(float(c) for c in a / np.linalg.norm(a))


def sky_material(name: str, *, scene, sun=SUN):
    """The sky inside a dome round the camera: the horizon's colour rising to the zenith's, a low ceiling of rain
    cloud (dark ink washes drifting slowly) that opens round the sun as `rf_sun` rises, its torn edges lit gold
    there, the sun's glow behind them; a lightning flash (`rf_flash`) lights the cloud from within."""
    mat, n = _material(name)
    tc = n.N.new("ShaderNodeTexCoord")
    d = n.vmath("NORMALIZE", tc.outputs["Object"])
    sep = n.new("ShaderNodeSeparateXYZ")
    n.set(sep.inputs[0], d)
    up = n.math("MAXIMUM", sep.outputs["Z"], 0.0)
    grad = n.ramp(up, 0.0, 0.45, to=(0.0, 1.0))
    col = n.mix(grad, n.prop("rf_horizon", True), n.prop("rf_zenith", True))
    # the cloud deck: noise over the direction, flattened toward the horizon (clouds bank up low), drifting
    uv = n.new("ShaderNodeCombineXYZ")
    t = n.clock(scene, 0.006)
    n.set(uv.inputs["X"], n.math("ADD", sep.outputs["X"], t))
    n.set(uv.inputs["Y"], sep.outputs["Y"])
    n.set(uv.inputs["Z"], n.math("MULTIPLY", sep.outputs["Z"], 3.2))
    big = n.noise(uv.outputs[0], 1.6, 5.0, 0.66)
    fine = n.noise(uv.outputs[0], 6.0, 5.0, 0.62)
    cloud = n.math("MULTIPLY_ADD", fine, 0.35, n.math("MULTIPLY", big, 0.8))
    # the opening: round the sun, wider as rf_sun rises
    toward = n.math("MAXIMUM", n.vmath("DOT_PRODUCT", d, _unit(sun)), 0.0)
    opening = n.math("MULTIPLY", n.ramp(toward, 0.82, 0.997), n.prop("rf_sun"))
    cover = n.math("SUBTRACT", n.math("MULTIPLY_ADD", cloud, 1.0, 0.12),
                   n.math("ADD", n.math("MULTIPLY", opening, 0.55), n.math("MULTIPLY", n.prop("rf_sun"), 0.06)))
    thick = n.ramp(cover, 0.38, 0.62)
    dark = n.mix(0.55, n.prop("rf_horizon", True), (0.02, 0.022, 0.028))
    shaded = n.mix(n.ramp(fine, 0.3, 0.75), dark, n.mix(0.5, n.prop("rf_horizon", True), n.prop("rf_zenith", True)))
    # the clouds' edges near the sun lit gold, and lightning inside them
    edge = n.math("MULTIPLY", n.math("MULTIPLY", n.ramp(cover, 0.3, 0.48), n.math("SUBTRACT", 1.0, n.ramp(cover, 0.5, 0.66))),
                  n.math("MULTIPLY", n.ramp(toward, 0.5, 0.95), n.prop("rf_sun")))
    shaded = n.mix(n.math("MULTIPLY", edge, 1.6, clamp=True), shaded, n.mix(1.0, n.prop("rf_gold", True), (2.2, 2.0, 1.8), "MULTIPLY"))
    shaded = n.mix(n.math("MULTIPLY", n.prop("rf_flash"), n.ramp(big, 0.35, 0.7)), shaded, (0.75, 0.8, 0.95))
    sky = n.mix(n.math("MULTIPLY", thick, n.ramp(up, -0.02, 0.06)), col, shaded)
    # the sun: a glow behind it all, its disc hidden while the cloud covers it
    glow = n.math("MULTIPLY", n.math("POWER", toward, 24.0), n.prop("rf_sun"))
    disc = n.math("MULTIPLY", n.ramp(toward, 0.9985, 0.9993), n.math("SUBTRACT", 1.0, thick))
    sun_col = n.mix(1.0, n.prop("rf_gold", True), (3.0, 2.7, 2.3), "MULTIPLY")
    sky = n.mix(n.math("MULTIPLY", glow, 0.85, clamp=True), sky, sun_col, "ADD")
    sky = n.mix(n.math("MULTIPLY", disc, n.prop("rf_sun")), sky, (6.0, 5.4, 4.2))
    em = n.new("ShaderNodeEmission")
    n.set(em.inputs["Color"], sky)
    n.out(em.outputs[0])
    return mat


def river_material(name: str, *, cam, scene, sun=SUN):
    """The river from high above: the sky's light on it (lighter far off, as water at a low angle is), long slow
    streaks of current, the rain's pocking while it rains (`rf_rain`), the mountains' reflections (ray traced), and
    when the sun comes a path of glitter on it toward the sun."""
    mat, n = _material(name)
    geo = n.N.new("ShaderNodeNewGeometry")
    sep = n.new("ShaderNodeSeparateXYZ")
    n.set(sep.inputs[0], geo.outputs["Position"])
    dist = n.vmath("DISTANCE", geo.outputs["Position"], tuple(cam))
    far = n.ramp(dist, 150.0, 3000.0)
    base = n.mix(far, n.mix(1.0, n.prop("rf_fog", True), (0.12, 0.125, 0.14), "MULTIPLY"),
                 n.mix(1.0, n.prop("rf_horizon", True), (0.45, 0.46, 0.49), "MULTIPLY"))
    t = n.clock(scene, 1.0)
    cur = n.new("ShaderNodeCombineXYZ")
    n.set(cur.inputs["X"], n.math("MULTIPLY", sep.outputs["X"], 0.25))
    n.set(cur.inputs["Y"], n.math("MULTIPLY_ADD", t, 0.6, n.math("MULTIPLY", sep.outputs["Y"], 0.012)))
    streak = n.ramp(n.noise(cur.outputs[0], 0.35, 4.0, 0.6), 0.55, 0.72)
    col = n.mix(n.math("MULTIPLY", streak, 0.35), base, n.prop("rf_horizon", True))
    # the rain pocking it: a fine flicker of rings, near only
    pock = n.new("ShaderNodeTexVoronoi")
    pock.inputs["Scale"].default_value = 0.6
    pv = n.new("ShaderNodeCombineXYZ")
    n.set(pv.inputs["X"], sep.outputs["X"])
    n.set(pv.inputs["Y"], sep.outputs["Y"])
    n.set(pv.inputs["Z"], n.math("MULTIPLY", t, 3.0))
    n.L.new(pv.outputs[0], pock.inputs["Vector"])
    rings = n.math("MULTIPLY", n.ramp(pock.outputs["Distance"], 0.12, 0.02), n.math("MULTIPLY", n.prop("rf_rain"),
                                                                                       n.math("SUBTRACT", 1.0, far)))
    col = n.mix(n.math("MULTIPLY", rings, 0.5), col, n.mix(1.0, n.prop("rf_horizon", True), (1.3, 1.3, 1.3), "MULTIPLY"))
    # the glitter: toward the sun's bearing from the camera, sparkling
    rel = n.vmath("SUBTRACT", geo.outputs["Position"], tuple(cam))
    rsep = n.new("ShaderNodeSeparateXYZ")
    n.set(rsep.inputs[0], rel)
    flat = n.new("ShaderNodeCombineXYZ")
    n.set(flat.inputs["X"], rsep.outputs["X"])
    n.set(flat.inputs["Y"], rsep.outputs["Y"])
    sx, sy = _unit((sun[0], sun[1], 0.0))[:2]
    along = n.vmath("DOT_PRODUCT", n.vmath("NORMALIZE", flat.outputs[0]), (sx, sy, 0.0))
    path = n.ramp(along, 0.965, 0.9995)
    sparkle = n.new("ShaderNodeTexVoronoi")
    sparkle.inputs["Scale"].default_value = 0.35
    sv = n.new("ShaderNodeCombineXYZ")
    n.set(sv.inputs["X"], n.math("MULTIPLY", sep.outputs["X"], 1.0))
    n.set(sv.inputs["Y"], n.math("MULTIPLY", sep.outputs["Y"], 0.25))
    n.set(sv.inputs["Z"], n.math("MULTIPLY", t, 1.6))
    n.L.new(sv.outputs[0], sparkle.inputs["Vector"])
    glint = n.math("ADD", n.ramp(sparkle.outputs["Distance"], 0.16, 0.03), n.math("MULTIPLY", path, 0.45))
    glint = n.math("MULTIPLY", n.math("MULTIPLY", glint, path), n.prop("rf_sun"))
    col = n.mix(1.0, col, n.mix(n.math("MULTIPLY", glint, 1.0), (0.0, 0.0, 0.0), n.mix(1.0, n.prop("rf_gold", True),
                                                                                       (3.2, 2.8, 2.2), "MULTIPLY")), "ADD")
    col = fogged(n, col, cam=cam, haze=0.85, mist=0.3, scene=scene)
    em = n.new("ShaderNodeEmission")
    n.set(em.inputs["Color"], col)
    gl = n.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = 0.08
    gl.inputs["Color"].default_value = (0.32, 0.33, 0.35, 1.0)
    add = n.new("ShaderNodeAddShader")
    n.L.new(em.outputs[0], add.inputs[0])
    n.L.new(gl.outputs[0], add.inputs[1])
    n.out(add.outputs[0])
    return mat


def near_ink(name: str):
    """The nearest things' ink: almost black, a breath of the air's colour in it (it warms with the light)."""
    mat, n = _material(name)
    em = n.new("ShaderNodeEmission")
    n.set(em.inputs["Color"], n.mix(1.0, n.prop("rf_fog", True), (0.035, 0.036, 0.04), "MULTIPLY"))
    n.out(em.outputs[0])
    return mat


def glow_material(name: str, prop: str, strength: float = 3.0):
    """A flat glow in a scene colour (the lantern's vermilion: `rf_accent`)."""
    mat, n = _material(name)
    em = n.new("ShaderNodeEmission", Strength=strength)
    n.set(em.inputs["Color"], n.prop(prop, True))
    n.out(em.outputs[0])
    return mat


def mist_material(name: str, *, scene, density: float = 0.6, drift: float = 6.0, seed: float = 0.0, size=(1.0, 1.0)):
    """A bank of mist on a card (as toon.mist_card) in the scene's fog colour, as dense as `rf_mist` says."""
    mat, n = _material(name)
    tc = n.N.new("ShaderNodeTexCoord")
    sep = n.new("ShaderNodeSeparateXYZ")
    n.set(sep.inputs[0], tc.outputs["Generated"])
    t = n.clock(scene, drift / max(size[0], 1.0))
    v = n.new("ShaderNodeCombineXYZ")
    n.set(v.inputs["X"], n.math("MULTIPLY", n.math("ADD", sep.outputs["X"], t), size[0] / max(size[1], 1.0) * 0.6))
    n.set(v.inputs["Y"], sep.outputs["Y"])
    v.inputs["Z"].default_value = seed
    nz = n.ramp(n.noise(v.outputs[0], 3.0, 5.0, 0.6), 0.36, 0.72)
    prof = n.math("MULTIPLY", n.ramp(sep.outputs["Y"], 0.0, 0.35), n.ramp(sep.outputs["Y"], 1.0, 0.45))
    prof = n.math("MULTIPLY", prof, n.math("MULTIPLY", n.ramp(sep.outputs["X"], 0.0, 0.3), n.ramp(sep.outputs["X"], 1.0, 0.7)))
    a = n.math("MULTIPLY", n.math("MULTIPLY", nz, prof), n.math("MULTIPLY", n.prop("rf_mist"), density), clamp=True)
    em = n.new("ShaderNodeEmission")
    n.set(em.inputs["Color"], n.mix(n.math("MULTIPLY", n.prop("rf_sun"), 0.25), n.prop("rf_fog", True),
                                    n.prop("rf_gold", True)))
    tr = n.new("ShaderNodeBsdfTransparent")
    mx = n.new("ShaderNodeMixShader")
    n.set(mx.inputs["Fac"], a)
    n.L.new(tr.outputs[0], mx.inputs[1])
    n.L.new(em.outputs[0], mx.inputs[2])
    n.out(mx.outputs[0])
    mat.surface_render_method = "BLENDED"
    return mat


# ---------------------------------------------------------------------------------------------------- Blender

def card(name: str, coll, location, size, material, *, rotation=(0.0, 0.0, 0.0)):
    """A flat card `size` (x, y) in its own x-y plane at `location`, turned by `rotation` (made from data: an
    operator re-evaluates the whole scene, seconds a call in a big one)."""
    import bpy

    me = bpy.data.meshes.new(name)
    me.from_pydata([(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)], [], [(0, 1, 2, 3)])
    me.uv_layers.new(name="UVMap")
    me.materials.append(material)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.location, ob.rotation_euler, ob.scale = location, rotation, (size[0], size[1], 1.0)
    ob.visible_shadow = False
    return ob


def _pine_mesh(name: str):
    """One pine as a silhouette for instancing: a thin trunk under four drooping tiers, 1 m tall."""
    import bpy

    verts, faces = [], []
    tiers = [(0.18, 0.5, 0.32), (0.38, 0.4, 0.27), (0.58, 0.3, 0.22), (0.78, 0.2, 0.22)]
    n = 7
    for z0, r, h in tiers:
        base = len(verts)
        for j in range(n):
            a = 2 * math.pi * j / n
            rr = r * (0.75 + 0.25 * ((j * 37) % 5) / 4)
            verts.append((rr * math.cos(a), rr * math.sin(a), z0 - 0.04))
        verts.append((0.0, 0.0, z0 + h))
        for j in range(n):
            faces.append((base + j, base + (j + 1) % n, base + n))
        faces.append(tuple(base + j for j in range(n - 1, -1, -1)))
    base = len(verts)
    verts += [(-0.025, 0, 0), (0.025, 0, 0), (0.02, 0, 0.4), (-0.02, 0, 0.4)]
    faces.append((base, base + 1, base + 2, base + 3))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    return ob


def _forest(name: str, land, pine, coll, *, seed: int = 2):
    """Pines scattered over `land` by its "trees" attribute (per m²), each as tall as its "tree_size" (Geometry
    Nodes: distributed once, instanced)."""
    import bpy

    from lib import toon

    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gin, gout = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    dens = N.new("GeometryNodeInputNamedAttribute")
    dens.data_type = "FLOAT"
    dens.inputs["Name"].default_value = "trees"
    size = N.new("GeometryNodeInputNamedAttribute")
    size.data_type = "FLOAT"
    size.inputs["Name"].default_value = "tree_size"
    dist = N.new("GeometryNodeDistributePointsOnFaces")
    dist.distribute_method = "RANDOM"
    L.new(gin.outputs[0], dist.inputs["Mesh"])   # the land's attributes carry over onto the points
    dist.inputs["Density"].default_value = 1.0
    L.new(dens.outputs["Attribute"], dist.inputs["Density Factor"] if "Density Factor" in dist.inputs else dist.inputs["Density"])
    dist.inputs["Seed"].default_value = seed
    info = N.new("GeometryNodeObjectInfo")
    info.inputs["Object"].default_value = pine
    rnd = N.new("FunctionNodeRandomValue")
    rnd.data_type = "FLOAT"
    toon._socket(rnd.inputs, "Min", "VALUE").default_value = 0.6
    toon._socket(rnd.inputs, "Max", "VALUE").default_value = 1.35
    rot = N.new("FunctionNodeRandomValue")
    rot.data_type = "FLOAT_VECTOR"
    toon._socket(rot.inputs, "Min", "VECTOR").default_value = (-0.08, -0.08, 0.0)
    toon._socket(rot.inputs, "Max", "VECTOR").default_value = (0.08, 0.08, 6.28)
    inst = N.new("GeometryNodeInstanceOnPoints")
    L.new(dist.outputs["Points"], inst.inputs["Points"])
    L.new(info.outputs["Geometry"], inst.inputs["Instance"])
    sc = N.new("ShaderNodeMath")
    sc.operation = "MULTIPLY"
    L.new(size.outputs["Attribute"], sc.inputs[0])
    L.new(next(o for o in rnd.outputs if o.type == "VALUE" and o.enabled), sc.inputs[1])
    # taller than wide: the scale is a vector (1, 1, 1) * size, stretched up
    comb = N.new("ShaderNodeCombineXYZ")
    sw = N.new("ShaderNodeMath")
    sw.operation = "MULTIPLY"
    sw.inputs[1].default_value = 0.55
    L.new(sc.outputs[0], sw.inputs[0])
    L.new(sw.outputs[0], comb.inputs["X"])
    L.new(sw.outputs[0], comb.inputs["Y"])
    L.new(sc.outputs[0], comb.inputs["Z"])
    L.new(comb.outputs[0], inst.inputs["Scale"])
    L.new(next(o for o in rot.outputs if o.type == "VECTOR" and o.enabled), inst.inputs["Rotation"])
    join = N.new("GeometryNodeJoinGeometry")
    L.new(inst.outputs["Instances"], join.inputs[0])
    L.new(gin.outputs[0], join.inputs[0])
    L.new(join.outputs[0], gout.inputs[0])
    mod = land.modifiers.new(name, "NODES")
    mod.node_group = ng
    return mod


def build(ctx, *, cam=None, aim=None, weather=None, coll=None, foreground: bool = True, seed: int = 5) -> dict:
    """The valley for a shot (`ctx`, render.py's): the film's world by the crossing (rf/set_world.py, lit for
    `weather`: its jetty, hut and lantern, moored ferry, path and signpost, the ground they stand on), and round it
    the vista's own land with its forests, the river, the mist banks, the sky dome round `cam` (its location; default
    CAMERA), and (with `foreground`) old pines overhanging the lower left of the view toward `aim`. The vista's
    colours are the scene's properties (`key` them). Returns its pieces, and the set's world as "world"."""
    import bpy

    from lib import shapes, toon

    from . import set_world

    scene = ctx.scene
    world = set_world.build(ctx, weather=weather)
    # the set's distance gives way to the vista's: its coarse ground, river, ridges, forests, mist and sky card
    v = world["valley"]
    hide = [v["valley_ground"], v["river"], v["sky"], *v["mist"]]
    hide += [ob for ob in world["far"].all_objects if ob.name.startswith(("ridge", "valley-forest", "river-mist",
                                                                           "slope-mist"))]
    for ob in hide:
        ob.hide_render = ob.hide_viewport = True
    coll = coll or toon.collection("valley")
    cam = tuple(cam) if cam is not None else camera_location()
    # the land
    xs, ys = grid()
    X, Y = np.meshgrid(xs, ys)
    Z = height(X, Y)
    nx, ny = len(xs), len(ys)
    verts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(ny - 1) for i in range(nx - 1)]
    land = shapes.mesh_object("land", verts, faces, None, coll, smooth=True)
    gy, gx = np.gradient(Z, ys, xs)
    slope = np.hypot(gx, gy)
    dist = np.hypot(X - cam[0], Y - cam[1])
    dens = tree_density(X, Y, Z, slope, cam=cam)
    me = land.data
    for aname, vals in (("trees", dens), ("tree_size", tree_size(dist))):
        a = me.attributes.new(aname, "FLOAT", "POINT")
        a.data.foreach_set("value", vals.ravel().astype(np.float32))
    m = {"land": wash("valley-land", cam=cam, scene=scene, texture=0.55),
         "trees": wash("valley-trees", cam=cam, scene=scene, ink=TREE_INK, lit_k=0.6, texture=0.25),
         "river": river_material("valley-river", cam=cam, scene=scene),
         "sky": sky_material("valley-sky", scene=scene),
         "near": near_ink("valley-near")}
    me.materials.append(m["land"])
    pine = _pine_mesh("valley-pine")
    coll.objects.link(pine)
    pine.data.materials.append(m["trees"])
    pine.hide_render = pine.hide_viewport = True
    _forest("valley-forest", land, pine, coll, seed=seed)
    # the river: a plane under the land
    river = card("river", coll, (0.0, (EXTENT[2] + EXTENT[3]) / 2, WATER_Z), (EXTENT[1] - EXTENT[0], EXTENT[3] - EXTENT[2]),
                 m["river"])
    # the sky: a dome round the camera
    sky = shapes.ellipsoid("sky", (0.0, 0.0, 0.0), (SKY_FAR,) * 3, material=m["sky"], coll=coll, n=48)
    sky.location = cam            # its object coordinates are the view's directions
    sky.visible_shadow = False
    # mist banks across the valley at distances up it, low over the water
    mists = []
    for k, (y, h, w) in enumerate([(560, 50, 1100), (760, 80, 1500), (900, 110, 2200), (1500, 170, 3200), (2400, 260, 4800),
                                   (3600, 380, 6400)]):
        mists.append(card(f"mist{k}", coll, (float(river_x(y)) + 40.0, y, WATER_Z + h * 0.32), (w, h),
                          mist_material(f"valley-mist{k}", scene=scene, density=0.75, drift=4.0 + 2.5 * k, seed=k * 2.7,
                                        size=(w, h)), rotation=(math.pi / 2, 0, 0)))
    # the land's lit side is lit by the set's key (set_weather.stage)
    out = {"coll": coll, "land": land, "river": river, "sky": sky, "mists": mists, "materials": m, "world": world,
           "lantern": world["lantern"]}
    if foreground:
        out["foreground"] = _foreground(coll, m, cam, aim or AIM, seed=seed)
    return out


FOREGROUND = [(-0.6, 270.0, 210.0, 1, 75.0), (-0.47, 330.0, 150.0, 3, 55.0)]


def ink_pine(name: str, base, height: float, material, coll, *, seed: int = 1, lean=(0.0, 0.0, 0.0),
             reach: float = 1.0) -> list:
    """A pine as an ink painter draws one near: a trunk leaning and kinking as it climbs, a few long branches reaching
    out level, and on each a flat pad of needles, its edge serrated (spikes fanned out round a flattened core), the
    top pad crowning it. `lean` (a direction) tips it. Returns its objects."""
    from lib import shapes

    rng = np.random.default_rng(seed)
    b = np.asarray(base, float)
    ln = np.asarray(lean, float)
    pts = [b - np.array([0, 0, 2.0])]
    for i in range(1, 7):
        u = i / 6
        kink = np.array([rng.normal(0, 0.06), rng.normal(0, 0.06), 0.0]) * height
        pts.append(b + np.array([0, 0, height * u]) + ln * height * u * u + kink * u)
    trunk = shapes.loft(f"{name}-trunk", np.array(pts), np.linspace(0.022, 0.006, 7) * height, material=material,
                        coll=coll, n=8, subsurf=1)
    obs = [trunk]
    roots, tips, widths = [], [], []
    pads = []
    for j in range(rng.integers(5, 8)):
        u = 0.42 + 0.5 * j / 6 + rng.uniform(-0.03, 0.03)
        at = pts[0] + (np.array(pts[-1]) - pts[0]) * u
        ang = rng.uniform(0, 2 * math.pi)
        far = height * (0.32 - 0.22 * u) * rng.uniform(0.8, 1.3) * reach
        tip = at + np.array([math.cos(ang) * far, math.sin(ang) * far, far * rng.uniform(-0.05, 0.15)])
        sag = (at + tip) / 2 + np.array([0.0, 0.0, -0.06 * far + rng.uniform(-0.02, 0.04) * far])
        obs.append(shapes.loft(f"{name}-branch{j}", np.array([at, sag, tip]), [0.0045 * height, 0.0025 * height, 0.001 * height],
                               material=material, coll=coll, n=6, subsurf=1))
        pads.append((tip, height * (0.17 - 0.08 * u) * rng.uniform(0.8, 1.25)))
    pads.append((np.array(pts[-1]) + np.array([0, 0, height * 0.02]), height * 0.11))
    for k, (c, r) in enumerate(pads):
        # a pad is a few overlapping tufts, each a low core bristling with needles that droop at its rim
        for q in range(3):
            cq = c + np.array([rng.normal(0, 0.35), rng.normal(0, 0.3), rng.normal(0, 0.06)]) * r
            rq = r * rng.uniform(0.5, 0.75)
            obs.append(shapes.ellipsoid(f"{name}-pad{k}{q}", tuple(cq), (rq * 0.7, rq * 0.6, rq * 0.22), material=material,
                                        coll=coll, n=10))
            for _ in range(70):
                a = rng.uniform(0, 2 * math.pi)
                root = cq + np.array([math.cos(a) * rq * 0.45, math.sin(a) * rq * 0.38, rng.uniform(-0.04, 0.1) * rq])
                rr = rq * rng.uniform(0.75, 1.1)
                tip = cq + np.array([math.cos(a) * rr, math.sin(a) * rr * 0.85, rng.uniform(-0.45, 0.05) * rq])
                roots.append(root)
                tips.append(tip)
                widths.append(rq * 0.07)
    obs.append(shapes.spikes(f"{name}-needles", roots, tips, widths, material=material, coll=coll, sides=3))
    for ob in obs:
        ob.visible_shadow = False
    return obs


def _foreground(coll, m, cam, aim, *, seed: int = 5) -> list:
    """The near layer: a dark rock ledge falling away below the lens at the lower left, pines standing on it whose
    crowns reach up into the frame's corner (`FOREGROUND`: (bearing left of the view as a share of the half-width,
    metres out, height, seed))."""
    c = np.asarray(cam, float)
    f = np.asarray(aim, float) - c
    f[2] = 0.0
    f /= np.linalg.norm(f)
    r = np.array([f[1], -f[0], 0.0])
    obs = []
    rng = np.random.default_rng(seed)
    for k, (side, d, h, sd, below) in enumerate(FOREGROUND):
        base = c + f * d + r * side * d - np.array([0.0, 0.0, below + rng.uniform(-3, 3)])
        obs += ink_pine(f"near-pine{k}", tuple(base), h, m["near"], coll, seed=seed + sd, lean=(r * 0.42 - f * 0.05),
                        reach=1.6)
    return obs


def camera_location(cam=CAMERA) -> tuple:
    """CAMERA's (x, y, height over the land) as a point in the world."""
    x, y, over = cam
    return (x, y, float(height(x, y)) + over)
