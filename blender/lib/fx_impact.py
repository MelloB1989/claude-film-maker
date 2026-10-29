"""Impact effects for a duel's fastest frames, drawn the way an anime's key animators and compositors draw them.

- **Speed lines**: `focus_lines` (manga focus lines: wedges from beyond the frame's edge converging on what matters,
  stopping short of it) and `streaks` (parallel lines along a rush, the subject's space left clear).
- **The impact frame**: a flash of white, then the clash as a stark ink panel, black on paper, flipped to its negative
  and back a few frames each. `beats` lays such a pattern out frame by frame; `ink_panel` turns the render into the
  panel in the compositor (the picture's light thresholded to ink and paper, its edges drawn, negative or not, or
  white), keyed per frame.
- **Shards** (`shards`): splinters and water bursting out from a blow, flying and turning, frame by frame.
- **The glint** (`glint`): the one fine line of light a cut leaves across the frame, tapering to nothing at both ends,
  drawn across over a few frames; `star` is the spark at its head.
- **The jolt** (`jolt`, `shake`): the camera's shake, a decaying jolt on an impact on top of a run's steady rumble.

Everything drawn is screen space: points in frame heights from the frame's centre (x right, y up; a 16:9 frame spans
x +-0.889, y +-0.5), as triangles (n, 3, 2). `overlay` hangs them in front of a camera, a flat unlit card at a depth
of its own (it follows the lens, so it covers the same part of the frame whatever the focal length), and
`alternate` shows one of several drawings of it at a time (redrawn on twos, as speed lines are). `shake_camera`
puts a shake on a camera as lens shift (the picture moves, its perspective does not).

The pure halves (every function of numpy alone) are tested without Blender in blender/tests/test_fx_impact.py.
"""
from __future__ import annotations

import math

import numpy as np

ASPECT = 16 / 9
PAPER = (0.93, 0.91, 0.86)     # the ink panel's paper and its ink (linear)
INK = (0.012, 0.012, 0.016)
BEATS = ("color", "white", "pos", "neg", "black")


def _rng(seed):
    return np.random.default_rng(seed)


def _corner(aspect: float) -> float:
    """The distance from the frame's centre to its corner (frame heights)."""
    return math.hypot(aspect / 2, 0.5)


# ---------------------------------------------------------------------------------------------------- speed lines

def focus_lines(count: int = 90, *, center=(0.0, 0.0), inner: float = 0.3, ellipse=(1.4, 1.0), jitter: float = 0.45,
                width=(0.006, 0.022), aspect: float = ASPECT, seed: int = 1) -> np.ndarray:
    """Manga focus lines: `count` thin wedges, each from beyond the frame's edge toward `center`, its tip stopping at
    an ellipse round it (`inner` frame heights, stretched by `ellipse`) pushed out by up to `jitter` of that. Their
    angles are spread evenly with a random wobble, their bases `width` wide. Returns triangles (count, 3, 2)."""
    rng = _rng(seed)
    c = np.asarray(center, float)
    outer = _corner(aspect) + float(np.hypot(*c)) + 0.1
    a = (np.arange(count) + rng.uniform(-0.45, 0.45, count)) * (2 * math.pi / count)
    u = np.c_[np.cos(a), np.sin(a)]
    r_tip = inner * (1.0 + jitter * rng.uniform(0.0, 1.0, count) ** 1.5)
    tip = c + u * np.c_[ellipse[0] * r_tip, ellipse[1] * r_tip]
    base = c + u * outer
    w = rng.uniform(*width, count)[:, None] / 2
    side = np.c_[-u[:, 1], u[:, 0]]
    return np.stack([base - side * w, base + side * w, tip], axis=1)


def streaks(count: int = 60, *, direction=(1.0, 0.0), length=(0.25, 0.9), width=(0.002, 0.009), clear=None,
            aspect: float = ASPECT, seed: int = 1) -> np.ndarray:
    """Parallel speed lines along `direction` (on screen) scattered over the frame: each a thin lens `length` long and
    `width` wide at its middle. `clear` ((x, y), (rx, ry)): an ellipse left empty for the subject (a line crossing it
    is cut back to its far side or dropped). Returns triangles (count * 2, 3, 2), fewer when lines are dropped."""
    rng = _rng(seed)
    d = np.asarray(direction, float)
    d = d / np.linalg.norm(d)
    n = np.array([-d[1], d[0]])
    tris = []
    for _ in range(count):
        mid = np.array([rng.uniform(-aspect / 2 - 0.1, aspect / 2 + 0.1), rng.uniform(-0.55, 0.55)])
        half = rng.uniform(*length) / 2
        w = rng.uniform(*width) / 2
        a, b = mid - d * half, mid + d * half
        if clear is not None:
            (cx, cy), (rx, ry) = clear
            # in the ellipse's own units, where it is the unit circle
            def inside(p):
                return ((p[0] - cx) / rx) ** 2 + ((p[1] - cy) / ry) ** 2 < 1.0
            if inside(mid):
                continue
            # cut the line back to the part on mid's side of the ellipse
            ts = np.linspace(0.0, 1.0, 17)
            pts = [mid + (a - mid) * t for t in ts]
            hit = next((i for i, p in enumerate(pts) if inside(p)), None)
            if hit is not None:
                a = pts[max(0, hit - 1)]
            pts = [mid + (b - mid) * t for t in ts]
            hit = next((i for i, p in enumerate(pts) if inside(p)), None)
            if hit is not None:
                b = pts[max(0, hit - 1)]
            if np.linalg.norm(b - a) < 0.02:
                continue
        m = (a + b) / 2
        tris.append([a, m + n * w, m - n * w])
        tris.append([b, m - n * w, m + n * w])
    return np.asarray(tris, float).reshape(-1, 3, 2)


# ---------------------------------------------------------------------------------------------------- the glint

def glint(p0, p1, width: float, *, draw: float = 1.0, n: int = 24) -> np.ndarray:
    """The glint a cut leaves: a fine line of light from `p0` toward `p1` (frame heights), `width` at its widest,
    tapering to points at both ends, drawn `draw` (0..1) of the way across (its head running ahead). Returns
    triangles (2 * (n - 1), 3, 2); none when nothing is drawn."""
    if draw <= 0:
        return np.zeros((0, 3, 2))
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    end = p0 + (p1 - p0) * min(1.0, draw)
    d = end - p0
    length = float(np.linalg.norm(d))
    if length < 1e-9:
        return np.zeros((0, 3, 2))
    d = d / length
    nrm = np.array([-d[1], d[0]])
    t = np.linspace(0.0, 1.0, n)
    # widest a little behind the head: the light gathers where the blade has just been
    half = width / 2 * np.sin(np.pi * t) ** 0.6 * (0.55 + 0.45 * t)
    c = p0 + np.outer(t * length, d)
    left, right = c + np.outer(half, nrm), c - np.outer(half, nrm)
    tris = []
    for i in range(n - 1):
        tris.append([left[i], right[i], right[i + 1]])
        tris.append([left[i], right[i + 1], left[i + 1]])
    return np.asarray(tris)


def star(center, size: float, *, rays: int = 4, thin: float = 0.06, turn: float = 0.0) -> np.ndarray:
    """A spark: `rays` thin points of light round `center`, `size` long, `thin` of that wide at the root, turned by
    `turn` radians. Returns triangles (2 * rays, 3, 2)."""
    c = np.asarray(center, float)
    tris = []
    for k in range(rays):
        a = turn + 2 * math.pi * k / rays
        u = np.array([math.cos(a), math.sin(a)])
        v = np.array([-u[1], u[0]]) * size * thin
        tip = c + u * size
        tris.append([c + v, c - v, tip])
        tris.append([c - v * 0.2, c + v * 0.2, c - u * size * 0.15])
    return np.asarray(tris)


# ---------------------------------------------------------------------------------------------------- shards

def shards(count: int, t: float, *, center=(0.0, 0.0), speed=(0.5, 1.6), size=(0.008, 0.04), spread=(0.0, 2 * math.pi),
           drag: float = 2.5, gravity: float = 0.35, elongate=(1.5, 4.0), seed: int = 1) -> np.ndarray:
    """`count` splinters bursting from `center` `t` seconds after the blow (frame heights): each flies out on its own
    heading within `spread` (radians, from, to) at `speed` (frame heights a second), slowed by `drag` and falling by
    `gravity`, a sliver `size` long stretched `elongate` times along its flight, turning as it goes. Returns
    triangles (count * 2, 3, 2); none before the blow."""
    if t < 0:
        return np.zeros((0, 3, 2))
    rng = _rng(seed)
    a = rng.uniform(*spread, count)
    v = rng.uniform(*speed, count)
    s = rng.uniform(*size, count)
    stretch = rng.uniform(*elongate, count)
    spin = rng.uniform(-14.0, 14.0, count)
    turn0 = rng.uniform(0, 2 * math.pi, count)
    # distance along the heading with drag: v (1 - e^(-drag t)) / drag
    k = (1 - math.exp(-drag * t)) / drag if drag > 0 else t
    pos = np.asarray(center, float) + np.c_[np.cos(a), np.sin(a)] * (v * k)[:, None]
    pos[:, 1] -= 0.5 * gravity * t * t
    tris = []
    for i in range(count):
        ang = turn0[i] + spin[i] * t
        u = np.array([math.cos(ang), math.sin(ang)])
        w = np.array([-u[1], u[0]])
        L, W = s[i] * stretch[i] / 2, s[i] / 2
        p = pos[i]
        # a sliver: four points, a kite with one long end
        q = [p + u * L, p + w * W, p - u * L * 0.5, p - w * W * 0.6]
        tris.append([q[0], q[1], q[2]])
        tris.append([q[0], q[2], q[3]])
    return np.asarray(tris)


# ---------------------------------------------------------------------------------------------------- the beats

def beats(pattern, frames: int | None = None) -> list[str]:
    """An impact frame's beats laid out frame by frame: `pattern` is [(beat, frames)], each beat one of BEATS
    ("color": the picture as it is; "white": a white-out; "pos": the ink panel, ink on paper; "neg": its negative;
    "black": ink alone). A pattern shorter than `frames` holds its last beat; a longer one is an error."""
    out = []
    for beat, n in pattern:
        if beat not in BEATS:
            raise ValueError(f"fx_impact: unknown beat {beat!r} (one of {', '.join(BEATS)})")
        if n < 0:
            raise ValueError(f"fx_impact: beat {beat!r} lasts {n} frames")
        out += [beat] * int(n)
    if frames is not None:
        if len(out) > frames:
            raise ValueError(f"fx_impact: the pattern runs {len(out)} frames, longer than the {frames} it has")
        out += [out[-1] if out else "color"] * (frames - len(out))
    return out


def beat_values(beat: str) -> dict:
    """The ink panel's inputs for a beat: `amount` (0 the picture, 1 the panel), `invert` (the negative), `white`."""
    if beat not in BEATS:
        raise ValueError(f"fx_impact: unknown beat {beat!r}")
    return {"amount": 0.0 if beat in ("color", "white") else 1.0, "invert": 1.0 if beat == "neg" else 0.0,
            "white": 1.0 if beat == "white" else 0.0, "black": 1.0 if beat == "black" else 0.0}


# ---------------------------------------------------------------------------------------------------- the shake

def _noise(n: int, freq: float, fps: float, seed: int) -> np.ndarray:
    """Smooth noise in -1..1 over n frames, about `freq` wobbles a second (a few sines of random phase)."""
    rng = _rng(seed)
    t = np.arange(n) / fps
    out = np.zeros(n)
    for k, w in enumerate((1.0, 0.53, 0.29)):
        f = freq * (1.0 + 0.6 * k) * rng.uniform(0.85, 1.15)
        out += w * np.sin(2 * math.pi * f * t + rng.uniform(0, 2 * math.pi))
    return out / 1.82


def jolt(n: int, at: float, amplitude: float, *, decay: float = 7.0, fps: float = 24.0) -> np.ndarray:
    """An impact's envelope over n frames: nothing before frame `at`, `amplitude` on it, dying away at `decay` a
    second."""
    t = (np.arange(n) - at) / fps
    return np.where(t >= 0, amplitude * np.exp(-decay * np.clip(t, 0, None)), 0.0)


def shake(envelope, *, freq: float = 9.0, roll: float = 0.0, fps: float = 24.0, seed: int = 1) -> np.ndarray:
    """A camera shake following `envelope` (frame heights, one value a frame: a run's steady rumble plus `jolt`s):
    (n, 3) offsets x, y (frame heights) and a roll (radians, `roll` of the envelope)."""
    env = np.asarray(envelope, float)
    n = len(env)
    x = _noise(n, freq, fps, seed) * env
    y = _noise(n, freq * 1.1, fps, seed + 1) * env
    r = _noise(n, freq * 0.7, fps, seed + 2) * env * roll
    return np.c_[x, y, r]


# ---------------------------------------------------------------------------------------------------- in Blender

def _mesh(name: str, tris):
    import bpy

    t = np.asarray(tris, float).reshape(-1, 3, 2)
    verts = [(float(x), float(y), 0.0) for x, y in t.reshape(-1, 2)]
    faces = [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(len(t))]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def unlit(name: str, color, *, alpha: float = 1.0, strength: float = 1.0):
    """A flat unlit colour (linear), `alpha` opaque, drawn over what is behind it: the material of what is drawn."""
    import bpy

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.name = "Emission"
    em.inputs["Color"].default_value = (*color, 1.0)
    em.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    mx.name = "Alpha"
    mx.inputs["Fac"].default_value = alpha
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    return mat


def overlay(name: str, cam, tris, material, *, depth: float = 0.5, coll=None):
    """Screen-space triangles hung in front of `cam` at `depth` metres (its custom property "depth", which can be
    keyed), scaled so a frame height there is one unit whatever the lens: drawn over what is beyond that depth.
    Casts no shadow. Returns the object."""
    import bpy

    ob = bpy.data.objects.new(name, _mesh(name, tris))
    (coll or bpy.context.scene.collection).objects.link(ob)
    ob.data.materials.append(material)
    ob.parent = cam
    ob["depth"] = float(depth)
    ob.visible_shadow = False
    for prop, idx, expr in (("location", 2, "-depth"),
                            ("scale", 0, "depth * sensor / lens"), ("scale", 1, "depth * sensor / lens")):
        fc = ob.driver_add(prop, idx)
        drv = fc.driver
        drv.type = "SCRIPTED"
        v = drv.variables.new()
        v.name = "depth"
        v.targets[0].id = ob
        v.targets[0].data_path = '["depth"]'
        if "lens" in expr:
            for var, path in (("sensor", "sensor_height"), ("lens", "lens")):
                v = drv.variables.new()
                v.name = var
                v.targets[0].id_type = "CAMERA"
                v.targets[0].id = cam.data
                v.targets[0].data_path = path
        drv.expression = expr
    return ob


def show(ob, frames, f_lo: int, f_hi: int) -> None:
    """Show `ob` on the film frames in `frames` alone, keyed (held) from f_lo to f_hi."""
    on = set(frames)
    last = None
    for f in range(f_lo, f_hi + 1):
        hide = f not in on
        if hide != last:
            ob.hide_render = ob.hide_viewport = hide
            ob.keyframe_insert("hide_render", frame=f)
            ob.keyframe_insert("hide_viewport", frame=f)
            last = hide
    _constant(ob)


def alternate(obs, frames, *, every: int = 2) -> dict:
    """Show one of `obs` at a time over `frames` (film frames, in order), the next every `every` frames (speed lines
    redrawn on twos), each hidden everywhere else. Returns frame -> the object shown."""
    frames = list(frames)
    shown = {f: obs[(i // every) % len(obs)] for i, f in enumerate(frames)}
    lo, hi = min(frames) - 1, max(frames) + 1
    for ob in obs:
        show(ob, [f for f in frames if shown[f] is ob], lo, hi)
    return shown


def _constant(owner) -> None:
    from . import toon

    ad = getattr(owner, "animation_data", None)
    if ad is None or ad.action is None:
        return
    for fc in toon._fcurves(ad.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"


def shake_camera(cam, offsets, f0: int, *, aspect: float = ASPECT) -> None:
    """Key a shake (`shake`'s (n, 3), from film frame f0) on `cam` as lens shift added to its own (the roll is left
    to a camera that is not tracked)."""
    base_x, base_y = cam.data.shift_x, cam.data.shift_y
    # shift is in units of the frame's longer side (its width)
    for i, (dx, dy, _) in enumerate(np.asarray(offsets, float)):
        cam.data.shift_x = base_x + dx / aspect
        cam.data.shift_y = base_y + dy / aspect
        cam.data.keyframe_insert("shift_x", frame=f0 + i)
        cam.data.keyframe_insert("shift_y", frame=f0 + i)
    cam.data.shift_x, cam.data.shift_y = base_x, base_y


class InkPanel:
    """The compositor's ink panel (`ink_panel`): `key(frame, beat)` keys a beat at a frame (held to the next)."""

    def __init__(self, tree):
        self.tree = tree

    def key(self, frame: int, beat: str) -> None:
        for name, val in beat_values(beat).items():
            sock = self.tree.nodes[f"ink_{name}"].outputs[0]
            sock.default_value = val
            sock.keyframe_insert("default_value", frame=int(frame))
        _constant(self.tree)


def ink_panel(scene, *, threshold: float = 0.3, soft: float = 0.03, edges: float = 1.0, paper=PAPER, ink=INK) -> InkPanel:
    """Turn the render into a stark ink panel in the compositor: its light thresholded at `threshold` (linear, `soft`
    either side) into paper and ink, its edges (`edges`, 0..1: a Sobel of the light) inked over, and, per frame
    (`InkPanel.key`), the picture itself, the panel, its negative, all ink or a white-out. Takes over what the
    compositor outputs (a graph already there, satsuei's, feeds it), so call it after the rest. Returns the
    InkPanel."""
    import bpy

    r = scene.render
    r.use_compositing = True
    nt = scene.compositing_node_group
    if nt is None:
        nt = bpy.data.node_groups.new("ink", "CompositorNodeTree")
        nt.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        scene.compositing_node_group = nt
        rl = nt.nodes.new("CompositorNodeRLayers")
        src = rl.outputs["Image"]
        out = nt.nodes.new("NodeGroupOutput")
    else:
        out = next(n for n in nt.nodes if n.bl_idname == "NodeGroupOutput")
        src = out.inputs[0].links[0].from_socket
    N, L = nt.nodes, nt.links

    def value(name, v):
        n = N.new("ShaderNodeValue")
        n.name = n.label = name
        n.outputs[0].default_value = v
        return n.outputs[0]

    def math_(op, a, b, clamp=False):
        n = N.new("ShaderNodeMath")
        n.operation, n.use_clamp = op, clamp
        for i, x in enumerate((a, b)):
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = float(x)
            else:
                L.new(x, n.inputs[i])
        return n.outputs[0]

    def mix(a, b, fac):
        n = N.new("ShaderNodeMix")
        n.data_type, n.blend_type, n.clamp_factor = "RGBA", "MIX", True
        for i, x in ((0, fac), (6, a), (7, b)):
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = float(x)
            elif isinstance(x, tuple):
                n.inputs[i].default_value = x
            else:
                L.new(x, n.inputs[i])
        return n.outputs[2]

    amount, invert, white, black = (value(f"ink_{k}", 0.0) for k in ("amount", "invert", "white", "black"))
    # the light: luminance of the picture
    sep = N.new("ShaderNodeSeparateColor")
    L.new(src, sep.inputs[0])
    lum = math_("ADD", math_("ADD", math_("MULTIPLY", sep.outputs[0], 0.2126), math_("MULTIPLY", sep.outputs[1], 0.7152)),
                math_("MULTIPLY", sep.outputs[2], 0.0722))
    ramp = N.new("ShaderNodeMapRange")
    ramp.interpolation_type = "SMOOTHSTEP"
    ramp.clamp = True
    ramp.inputs["From Min"].default_value = threshold - soft
    ramp.inputs["From Max"].default_value = threshold + soft
    L.new(lum, ramp.inputs["Value"])
    v = ramp.outputs["Result"]
    if edges > 0:
        # the edges of the light, inked: a Sobel of the picture, hard-cut
        fl = N.new("CompositorNodeFilter")
        fl.inputs["Type"].default_value = "Sobel"
        L.new(src, fl.inputs["Image"])
        fsep = N.new("ShaderNodeSeparateColor")
        L.new(fl.outputs[0], fsep.inputs[0])
        e = math_("MULTIPLY", math_("GREATER_THAN", fsep.outputs[1], threshold * 0.9), edges)
        v = math_("MULTIPLY", v, math_("SUBTRACT", 1.0, e), clamp=True)
    # the negative, then all ink
    v = math_("ADD", math_("MULTIPLY", v, math_("SUBTRACT", 1.0, math_("MULTIPLY", invert, 2.0))), invert)
    v = math_("MULTIPLY", v, math_("SUBTRACT", 1.0, black), clamp=True)
    panel = mix(tuple((*ink, 1.0)), tuple((*paper, 1.0)), v)
    pic = mix(src, panel, amount)
    pic = mix(pic, (1.0, 1.0, 1.0, 1.0), white)
    L.new(pic, out.inputs[0])
    return InkPanel(nt)


def clock(ob, seconds: dict, *, fps: float = 24.0) -> None:
    """Run a Geometry Nodes object that moves with the scene's time (toon.rain, toon.splashes) on a clock of its own:
    its Scene Time replaced by a value keyed on every film frame of `seconds` (frame -> seconds, linear between), so
    the time can slow, stop and start again (rain hanging in the air at an impact, falling again after). Objects that
    share the node group (a copy of the rain) share the clock."""
    for mod in ob.modifiers:
        ng = getattr(mod, "node_group", None)
        if mod.type != "NODES" or ng is None or ng.get("fx_clock"):
            continue
        times = [n for n in ng.nodes if n.bl_idname == "GeometryNodeInputSceneTime"]
        if not times:
            continue
        v = ng.nodes.new("ShaderNodeValue")
        v.name = v.label = "fx_clock"
        fr = ng.nodes.new("ShaderNodeMath")
        fr.operation = "MULTIPLY"
        fr.inputs[1].default_value = fps
        ng.links.new(v.outputs[0], fr.inputs[0])
        for t in times:
            for link in list(t.outputs["Seconds"].links):
                ng.links.new(v.outputs[0], link.to_socket)
            for link in list(t.outputs["Frame"].links):
                ng.links.new(fr.outputs[0], link.to_socket)
        sock = v.outputs[0]
        for f, s in sorted(seconds.items()):
            sock.default_value = float(s)
            sock.keyframe_insert("default_value", frame=int(f))
        from . import toon

        for fc in toon._fcurves(ng.animation_data.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
        ng["fx_clock"] = True
