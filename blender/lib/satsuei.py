"""Compositing (撮影, satsuei): the anime photography stage, where the drawn cast is lit by the world it is laid over.

A cel drawn flat and pasted over a lit background reads as a sticker. An anime's compositors fix that after the
drawing: they grade the cast to the scene's light (a storm is cold and dim), lay a gradient over it (the "para": the
side away from the light and the bottom of the frame fall off), run a rim of light along the silhouette on the side a
light is on, let the blurred background bleed a little over its edges (light wrap), and put the air between the lens
and it (haze). `setup(scene, cast)` does this in Blender's compositor: the cast collection renders on a view layer of
its own ("cast"), the rest of the scene on the first ("world"); the cast is hidden wherever the world's depth is
nearer than its own (Grease Pencil writes the depth pass), then graded, lit and laid back over the world.

What it does to the cast at a frame is a `Look` (`Rim`s, the grade, the para, the wrap, a lightning flash's cold rim
all round), keyed per frame with `Comp.key(frame, look)` and held (`Comp.hold()`: every key constant, a cut is a cut).
`values(look, res)` is the pure half: the node inputs a look sets, in pixels at the render size `res`.

Widths are in frame heights (a look renders the same at any size). Colours are linear. Directions are on screen, x
right and y up; para points are frame fractions from the bottom left.

A scene that never calls `setup` is untouched: no compositing (lib/setup.py turns it off), one view layer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

RIMS = 3          # rim lights a look can have at once
WORLD, CAST = "world", "cast"   # the view layers


@dataclass(frozen=True)
class Rim:
    """A rim of light along the cast's silhouette on the side the light is on."""
    toward: tuple = (0.0, 1.0)       # where the light is, on screen (x right, y up; any length)
    color: tuple = (1.0, 1.0, 1.0)   # linear
    strength: float = 0.0
    width: float = 0.004             # how far in from the silhouette it reaches, in frame heights
    soft: float = 0.5                # its blur, over its width


@dataclass(frozen=True)
class Look:
    """What the compositor does to the cast at a frame. The default changes nothing."""
    gain: tuple = (1.0, 1.0, 1.0)        # multiplied in (linear): the light's level and colour on the cast
    saturation: float = 1.0
    haze: tuple = (0.5, 0.5, 0.5)        # the air's colour (linear) ...
    haze_amount: float = 0.0             # ... and how much of it lies between the lens and the cast, 0..1
    para: tuple = (0.45, 0.47, 0.6)      # the colour multiplied over the side away from the light ...
    para_amount: float = 0.0             # ... at its full strength, 0..1
    para_from: tuple = (0.5, 1.0)        # the frame point the para starts at (nothing) ...
    para_to: tuple = (0.5, 0.0)          # ... and the one it is full at (frame fractions from the bottom left)
    rims: tuple = ()                     # up to RIMS Rim lights
    wrap: float = 0.0                    # how much of the blurred world bleeds over the cast's edges ...
    wrap_width: float = 0.02             # ... and how far in, in frame heights (small figures want little)
    flash: float = 0.0                   # a lightning flash's cold rim all round, 0..1
    flash_color: tuple = (0.85, 0.9, 1.0)


def _unit(v) -> tuple[float, float]:
    x, y = float(v[0]), float(v[1])
    n = math.hypot(x, y)
    if n < 1e-12:
        raise ValueError(f"a direction needs a length, got {v!r}")
    return x / n, y / n


def shift(toward, width: float, res) -> tuple[float, float]:
    """The translation (px) that brings each pixel the silhouette `width` (frame heights) toward the light: where
    the cast is, but is not once shifted so, is its rim on that side."""
    ux, uy = _unit(toward)
    d = width * res[1]
    return -ux * d, -uy * d


def axis(p_from, p_to) -> tuple[tuple, tuple]:
    """(origin, axis) of the para: dot(uv - origin, axis) runs 0 at `p_from` to 1 at `p_to` (uv in frame fractions)."""
    dx, dy = float(p_to[0]) - float(p_from[0]), float(p_to[1]) - float(p_from[1])
    n2 = dx * dx + dy * dy
    if n2 < 1e-12:
        raise ValueError(f"the para needs two different points, got {p_from!r} and {p_to!r}")
    return (float(p_from[0]), float(p_from[1]), 0.0), (dx / n2, dy / n2, 0.0)


def _rgba(c) -> tuple:
    return (float(c[0]), float(c[1]), float(c[2]), 1.0)


def values(look: Look, res) -> dict:
    """The compositor inputs `look` sets at the render size `res` (w, h): {(node name, input index): value}."""
    if len(look.rims) > RIMS:
        raise ValueError(f"a look has at most {RIMS} rims, got {len(look.rims)}")
    rims = list(look.rims) + [Rim()] * (RIMS - len(look.rims))
    origin, ax = axis(look.para_from, look.para_to)
    v = {
        ("sat", 2): float(look.saturation),
        ("gain", 7): _rgba(look.gain),
        ("haze_color", 7): _rgba(look.haze),
        ("haze", 0): min(max(float(look.haze_amount), 0.0), 1.0),
        ("para_origin", 1): origin,
        ("para_axis", 1): ax,
        ("para_amount", 1): min(max(float(look.para_amount), 0.0), 1.0),
        ("para", 7): _rgba(look.para),
        ("wrap", 0): max(float(look.wrap), 0.0),
        ("wrap_world", 1): (max(look.wrap_width * res[1], 1.0),) * 2,
        ("wrap_alpha", 1): (max(look.wrap_width * res[1], 1.0),) * 2,
        ("flash", 0): max(float(look.flash), 0.0),
        ("flash_color", 7): _rgba(look.flash_color),
    }
    for i, r in enumerate(rims):
        x, y = shift(r.toward, r.width, res)
        s = max(r.width * r.soft * res[1], 0.0)
        v[(f"rim{i}_shift", 1)] = x
        v[(f"rim{i}_shift", 2)] = y
        v[(f"rim{i}_blur", 1)] = (s, s)
        v[(f"rim{i}_color", 7)] = _rgba(r.color)
        v[(f"rim{i}", 0)] = max(float(r.strength), 0.0) if r.width > 0 else 0.0
    return v


# ---------------------------------------------------------------------------------------------------- Blender

class Comp:
    """The compositor graph `setup` built: `key(frame, look)` keys a look at a frame (frames in increasing order; an
    input is keyed only where it changes), `hold()` makes every key constant."""

    def __init__(self, scene, tree, res):
        self.scene, self.tree, self.res = scene, tree, res
        self._last: dict = {}

    def set(self, look: Look) -> None:
        """`look` everywhere, unkeyed (a still, or a shot that never changes it)."""
        for (name, i), val in values(look, self.res).items():
            self._socket(name, i, val)

    def key(self, frame: int, look: Look) -> None:
        for (name, i), val in values(look, self.res).items():
            if self._last.get((name, i)) == val:
                continue
            self._socket(name, i, val).keyframe_insert("default_value", frame=int(frame))
            self._last[(name, i)] = val

    def _socket(self, name: str, i: int, val):
        sock = self.tree.nodes[name].inputs[i]
        sock.default_value = val if not isinstance(val, tuple) else val[:len(sock.default_value)]
        return sock

    def hold(self) -> None:
        from . import toon

        ad = self.tree.animation_data
        if ad is None or ad.action is None:
            return
        for fc in toon._fcurves(ad.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


def _gather(scene, keep) -> None:
    """Objects linked straight to the scene's collection (rain, line art, ...) moved into a collection of their own,
    so a view layer can leave them out; cameras, lights and empties stay."""
    import bpy

    loose = [ob for ob in scene.collection.objects if ob.type not in ("CAMERA", "LIGHT", "EMPTY")]
    if not loose:
        return
    coll = bpy.data.collections.new("satsuei-loose")
    scene.collection.children.link(coll)
    for ob in loose:
        if ob.name in keep.all_objects:
            continue
        scene.collection.objects.unlink(ob)
        coll.objects.link(ob)


def setup(scene, cast, *, flash_width: float = 0.006, backdrop=None) -> Comp:
    """Composite the collection `cast` (a child of the scene's collection) over the rest of `scene` through a
    `Look`: two view layers (WORLD, CAST), the compositor on, its graph built. `flash_width` (frame heights): the
    width of a lightning flash's rim. `backdrop` (linear): what shows where
    nothing was rendered (default: the world's colour), so the plate stays opaque. Call it once the scene is built
    (it moves loose objects into a collection: `_gather`). Returns the Comp to key looks on."""
    import bpy

    if cast.name not in scene.collection.children:
        raise ValueError(f"satsuei: the cast collection {cast.name!r} must be a child of the scene's collection")
    _gather(scene, cast)
    res = (scene.render.resolution_x, scene.render.resolution_y)
    if backdrop is None:
        bg = scene.world.node_tree.nodes.get("Background") if scene.world and scene.world.node_tree else None
        backdrop = tuple(bg.inputs[0].default_value[:3]) if bg is not None else (0.0, 0.0, 0.0)

    # EEVEE (5.2) leaves a view layer's depth pass all zeros on a frame where it has Grease Pencil objects but every
    # one is hidden (a shot's line art, a bolt keyed off): the cast would read as behind everything. An empty one that
    # is never hidden keeps the depth pass written.
    guard = bpy.data.objects.new("satsuei-depth", bpy.data.grease_pencils.new("satsuei-depth"))
    guard.data.layers.new("empty").frames.new(scene.frame_start)
    keep = bpy.data.collections.new("satsuei-world")
    scene.collection.children.link(keep)
    keep.objects.link(guard)

    world = scene.view_layers[0]
    world.name = WORLD
    layer = scene.view_layers.get(CAST) or scene.view_layers.new(CAST)
    for vl, cast_only in ((world, False), (layer, True)):
        vl.use_pass_z = True
        for lc in vl.layer_collection.children:
            lc.exclude = (lc.collection != cast) if cast_only else (lc.collection == cast)
    r = scene.render
    r.film_transparent = True
    r.use_compositing = True
    r.compositor_device = "GPU"

    nt = bpy.data.node_groups.new("satsuei", "CompositorNodeTree")
    scene.compositing_node_group = nt
    nt.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    N, L = nt.nodes, nt.links

    def node(kind, name=None, **inputs):
        n = N.new(kind)
        if name:
            n.name = n.label = name
        for k, v in inputs.items():
            n.inputs[k].default_value = v
        return n

    def math_(op, a, b, name=None, clamp=False):
        n = node("ShaderNodeMath", name)
        n.operation, n.use_clamp = op, clamp
        for i, x in enumerate((a, b)):
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = float(x)
            else:
                L.new(x, n.inputs[i])
        return n.outputs[0]

    def mix(kind, a, b, name=None, fac=1.0):
        n = node("ShaderNodeMix", name)
        n.data_type, n.blend_type, n.clamp_factor = "RGBA", kind, False
        for i, x in ((0, fac), (6, a), (7, b)):
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = float(x)
            elif isinstance(x, tuple):
                n.inputs[i].default_value = x
            else:
                L.new(x, n.inputs[i])
        return n.outputs[2]   # the RGBA result

    def blur(x, px, name=None):
        n = node("CompositorNodeBlur", name)
        n.inputs["Type"].default_value = "Gaussian"
        n.inputs["Size"].default_value = (px, px)
        L.new(x, n.inputs["Image"])
        return n.outputs[0]

    rw = node("CompositorNodeRLayers")
    rw.layer = WORLD
    rc = node("CompositorNodeRLayers")
    rc.layer = CAST

    # the cast where nothing of the world is nearer
    seen = math_("GREATER_THAN", rw.outputs["Depth"], rc.outputs["Depth"])
    A = math_("MULTIPLY", rc.outputs["Alpha"], seen, "alpha")
    C = mix("MULTIPLY", rc.outputs["Image"], seen)

    # the grade: saturation, the light's level and colour, the air in front
    sat = node("CompositorNodeHueSat", "sat")
    L.new(C, sat.inputs["Image"])
    C = mix("MULTIPLY", sat.outputs[0], (1.0, 1.0, 1.0, 1.0), "gain")
    air = mix("MULTIPLY", A, (0.5, 0.5, 0.5, 1.0), "haze_color")          # premultiplied: the air's colour times alpha
    C = mix("MIX", C, air, "haze", fac=0.0)

    # the para: a gradient across the frame, multiplied in
    uv = node("CompositorNodeImageCoordinates")
    L.new(rc.outputs["Image"], uv.inputs["Image"])
    d = node("ShaderNodeVectorMath", "para_origin")
    d.operation = "SUBTRACT"
    L.new(uv.outputs["Normalized"], d.inputs[0])
    t = node("ShaderNodeVectorMath", "para_axis")
    t.operation = "DOT_PRODUCT"
    L.new(d.outputs[0], t.inputs[0])
    tt = math_("MULTIPLY", t.outputs["Value"], 1.0, clamp=True)
    k = math_("MULTIPLY", tt, 0.0, "para_amount")
    C = mix("MULTIPLY", C, (0.45, 0.47, 0.6, 1.0), "para", fac=k)

    # the rims: the cast less itself shifted toward the light (blurred, so the light fades in from the silhouette
    # rather than stopping at a line)
    for i in range(RIMS):
        sh = node("CompositorNodeTranslate", f"rim{i}_shift")
        sh.inputs["Interpolation"].default_value = "Bilinear"
        sh.inputs["Extension X"].default_value = sh.inputs["Extension Y"].default_value = "Extend"
        L.new(A, sh.inputs["Image"])
        rim = math_("MULTIPLY", A, math_("SUBTRACT", 1.0, blur(sh.outputs[0], 1.0, f"rim{i}_blur")), clamp=True)
        C = mix("ADD", C, mix("MULTIPLY", rim, (1.0, 1.0, 1.0, 1.0), f"rim{i}_color"), f"rim{i}", fac=0.0)

    # the flash: a cold rim all round
    fpx = max(1, round(flash_width * res[1]))
    er = node("CompositorNodeDilateErode", Size=-fpx)
    er.inputs["Type"].default_value = "Distance"
    L.new(A, er.inputs["Mask"])
    ring = math_("MULTIPLY", blur(math_("SUBTRACT", A, er.outputs[0], clamp=True), fpx * 0.6), A)
    C = mix("ADD", C, mix("MULTIPLY", ring, (0.85, 0.9, 1.0, 1.0), "flash_color"), "flash", fac=0.0)

    # the light wrap: the blurred world over the cast's edges
    inner = math_("MULTIPLY", math_("MULTIPLY", A, math_("SUBTRACT", 1.0, blur(A, 1.0, "wrap_alpha"))), 2.0, clamp=True)
    C = mix("ADD", C, mix("MULTIPLY", blur(rw.outputs["Image"], 1.0, "wrap_world"), inner), "wrap", fac=0.0)

    # back over the world, over the backdrop
    cut = node("CompositorNodeSetAlpha")
    cut.inputs["Type"].default_value = "Replace Alpha"
    L.new(C, cut.inputs["Image"])
    L.new(A, cut.inputs["Alpha"])
    over = node("CompositorNodeAlphaOver")
    L.new(rw.outputs["Image"], over.inputs["Background"])
    L.new(cut.outputs[0], over.inputs["Foreground"])
    under = node("CompositorNodeAlphaOver")
    under.inputs["Background"].default_value = _rgba(backdrop)
    L.new(over.outputs[0], under.inputs["Foreground"])
    out = N.new("NodeGroupOutput")
    L.new(under.outputs[0], out.inputs[0])

    comp = Comp(scene, nt, res)
    comp.set(Look())
    return comp
