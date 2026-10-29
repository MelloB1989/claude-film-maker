"""Smoke from a pipe: the thin wisp off a kiseru's bowl, or a breath of it let out, drawn as a soft ribbon that curls up
and away and that the rain beats down.

A wisp is a chain of puffs. One leaves its source (the bowl, the mouth) `rate` times a second and goes on its own: it
rises slowly straight up at first (the laminar thread just above the bowl), then sways wider and wider as it ages (the
curl, which differs smoothly from puff to puff, so the chain bends as one ribbon), drifts with the wind and fades out
over its `life`. `rain` (0..1) beats it down: it climbs less, sags where drops hit it, frays and tears in places and
dies sooner. A breath (`Wisp.push`: a velocity it leaves with, slowed by the air's drag; `emit`: when it is let out)
starts wider and moves out before it rises.

The pure half (`Wisp.points`, `ribbon_verts`) is numpy: where every puff of a chain is at a time, given where the source
was at the times they left it. `ribbon()` makes the Blender object, a strip of quads turned to face the camera, its
material a pale emission fading along the ribbon, soft at its edges and broken by drifting noise (whitening with
toon.FLASH); `Ribbon.bake()` samples the source and the camera over the shot (frame_set: call it last, once
everything is keyed) and works out every frame's strip, set on each frame by a frame_change_pre handler (render.py
guards it). The ribbon can be linked into more collections (`also`): a copy in a shot's cast layer (lib/satsuei.py) so
the smoke in front of a face stays in front of it, as rain does.

    from lib import smoke
    wisp = smoke.Wisp(rain=0.6, wind=(0.05, 0.0, 0.0))
    rb = smoke.ribbon("pipe-smoke", wisp, source=bowl, coll=world, also=(cast,))
    ...                                          # the camera, the cast, everything keyed
    rb.bake(scene, ctx.f0, ctx.f1, ctx.fps)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

UP = np.array((0.0, 0.0, 1.0))


def smoothstep(e0: float, e1: float, x):
    u = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def wave(x, seed: int, octaves: int = 3):
    """A smooth, repeatable noise of x in about [-1, 1]: a few sines of seeded frequencies and phases."""
    rng = np.random.default_rng(seed)
    x = np.asarray(x, float)
    out = np.zeros_like(x)
    total = 0.0
    for k in range(octaves):
        f = rng.uniform(0.8, 1.25) * 1.9 ** k
        a = 0.55 ** k
        out = out + a * np.sin(f * x + rng.uniform(0.0, 2.0 * math.pi))
        total += a
    return out / total


@dataclass(frozen=True)
class Wisp:
    """How a wisp moves (metres, seconds). `emit`: the windows (s, the film's time) when the source lets smoke out
    (None: always); outside them its puffs are clear, so the ribbon breaks off and fades."""
    rate: float = 36.0            # puffs a second: the ribbon's resolution in time
    life: float = 2.6             # s a puff lives before it is gone
    rise: float = 0.17            # m/s it climbs once its heat takes it
    lift: float = 0.5             # s it takes to come up to that speed
    wind: tuple = (0.04, 0.02, 0.0)   # m/s it drifts with the air
    curl: float = 0.05            # m: how far it sways at 1 s old (growing with age)
    curl_rate: float = 1.4        # rad/s of age: how fast it turns as it rises
    calm: float = 0.25            # s of the laminar thread over the bowl before it starts to curl
    width: tuple = (0.002, 0.035)  # m: at the source, at the end of its life
    push: tuple = (0.0, 0.0, 0.0)  # m/s it leaves the source with (a breath let out)
    drag: float = 0.35            # s: how soon the air slows that push
    opacity: float = 0.4          # the wisp's alpha at its densest: smoke is thin, the world shows through
    rain: float = 0.0             # 0..1: the rain beating it down
    emit: tuple | None = None     # ((start, end), ...) s
    seed: int = 1

    @property
    def lifetime(self) -> float:
        """How long a puff lives in this rain: drops knock it out sooner."""
        return self.life * (1.0 - 0.45 * self.rain)

    def count(self) -> int:
        """How many points a chain holds: its newest (at the source, age 0) and one per puff still alive."""
        return int(math.ceil(self.lifetime * self.rate)) + 2

    def ages(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        """(emission times, ages) of the chain at time t, newest first: the head at the source now, then the puffs
        left on the grid of 1/rate (fixed in the film's time, so a puff keeps its own curl from frame to frame)."""
        n = self.count()
        last = math.floor(t * self.rate) / self.rate
        te = np.concatenate([[t], last - np.arange(n - 1) / self.rate])
        if te[1] >= t:            # t on the grid: the head is that puff
            te[1:] -= 1.0 / self.rate
        return te, t - te

    def emitting(self, te) -> np.ndarray:
        """1 where a puff left inside an emit window, fading over a few puffs at either end, else 0."""
        te = np.asarray(te, float)
        if self.emit is None:
            return np.ones_like(te)
        ramp = 4.0 / self.rate
        out = np.zeros_like(te)
        for a, b in self.emit:
            out = np.maximum(out, smoothstep(a - ramp, a + ramp, te) * (1.0 - smoothstep(b - ramp, b + ramp, te)))
        return out

    def offsets(self, te, age) -> np.ndarray:
        """(n, 3): how far each puff has gone from where it left the source."""
        te, a = np.asarray(te, float), np.maximum(np.asarray(age, float), 0.0)
        s, r = self.seed, self.rain
        # the push of a breath, slowed by the air
        out = np.outer(self.drag * (1.0 - np.exp(-a / self.drag)), self.push)
        # the climb: slow off the bowl, up to speed over `lift`; the rain holds it down
        rise = self.rise * (1.0 - 0.6 * r) * (a - self.lift * (1.0 - np.exp(-a / self.lift)))
        out[:, 2] += rise
        out += np.outer(a, self.wind)
        # the curl: a sway growing with age past the calm thread, turning as it rises, its phase drifting smoothly
        # from puff to puff (so the chain bends as one ribbon); the rain shakes it wider
        amp = self.curl * (1.0 + 0.8 * r) * a ** 1.3 * smoothstep(0.4 * self.calm, self.calm * 1.6, a)
        ph = self.curl_rate * a + 2.2 * wave(te * 0.9, s) + 0.7 * wave(te * 2.3 + a * 0.4, s + 1)
        out[:, 0] += amp * np.sin(ph)
        out[:, 1] += amp * 0.7 * np.cos(ph * 0.83 + 1.1 * wave(te * 0.6, s + 2))
        out[:, 2] += amp * 0.25 * np.sin(ph * 1.7 + 0.5)
        if r > 0:
            # drops hitting it: it sags where they strike (in patches along the chain), more the older it is, and
            # kinks sideways in short jerks
            hit = np.clip(0.4 + wave(te * 2.7 + a * 0.3, s + 3), 0.0, None)
            out[:, 2] -= r * 0.07 * hit * a ** 1.5
            jerk = r * 0.012 * smoothstep(0.1, 0.5, a)
            out[:, 0] += jerk * wave(te * 9.0 + a * 5.0, s + 4)
            out[:, 1] += jerk * wave(te * 8.0 - a * 4.0, s + 5)
        return out

    def points(self, t: float, source) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """The chain at time t: (positions (n, 3), ages (n,), alpha (n,), width (n,)), newest first. `source(times)`
        gives where the source was at those times ((m, 3))."""
        te, a = self.ages(t)
        P = np.asarray(source(te), float).reshape(-1, 3) + self.offsets(te, a)
        L = self.lifetime
        u = np.clip(a / L, 0.0, 1.0)
        # in from clear just off the source, out to nothing over its life; a breath dense at first
        alpha = self.opacity * smoothstep(0.0, 0.06, a) * (1.0 - u) ** 1.6 * self.emitting(te)
        if self.rain > 0:
            # torn: gaps where the drops cut through it, more of them as it ages
            tear = np.clip(wave(te * 4.1 + a * 1.3, self.seed + 6) + 0.2, 0.0, 1.0) * smoothstep(0.15, 0.6, a)
            alpha = alpha * (1.0 - 0.85 * self.rain * tear)
        alpha = np.where(a > L, 0.0, alpha)
        w0, w1 = self.width
        width = (w0 + (w1 - w0) * u ** 0.8) * (1.0 + 0.6 * self.rain * u)
        if any(self.push):
            width = width * (1.0 + 1.5 * smoothstep(0.0, 0.4, a) * (1.0 - u))   # a breath billows
        return P, a, alpha, width


def ribbon_verts(P, width, cam) -> np.ndarray:
    """(2n, 3): a strip along the points P (n, 3), each pair across it `width` wide at right angles to both the chain
    and the line to the camera at `cam` (so it faces the lens), as [left0, right0, left1, right1, ...]."""
    P = np.asarray(P, float)
    T = np.gradient(P, axis=0) if len(P) > 1 else np.array([[0.0, 0.0, 1.0]])
    V = np.asarray(cam, float) - P
    S = np.cross(T, V)
    n = np.linalg.norm(S, axis=1, keepdims=True)
    # where the chain runs straight at the lens, any side across it will do
    S = np.where(n > 1e-9, S / np.maximum(n, 1e-9), np.array([1.0, 0.0, 0.0]))
    half = (np.asarray(width, float) / 2.0)[:, None] * S
    out = np.empty((2 * len(P), 3))
    out[0::2], out[1::2] = P - half, P + half
    return out


def strip_faces(n: int) -> list[tuple[int, int, int, int]]:
    """The quads of a strip of n pairs."""
    return [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(n - 1)]


# ---------------------------------------------------------------------------------------------------- Blender

class Ribbon:
    """A wisp drawn as a ribbon in Blender (`ribbon()` makes it; `bake()` sets every frame)."""

    def __init__(self, ob, wisp: Wisp, source, offset):
        self.ob, self.wisp, self.source, self.offset = ob, wisp, source, np.asarray(offset, float)
        self.frames: dict[int, tuple] = {}

    def bake(self, scene, f0: int, f1: int, fps: float) -> None:
        """Sample where the source (and the camera) is on every frame from a puff's life before f0 to f1, work out
        the ribbon on every frame of [f0, f1) and set it on each by a frame_change_pre handler."""
        import bpy
        from mathutils import Vector

        back = int(math.ceil(self.wisp.lifetime * fps)) + 1
        frames = range(f0 - back, f1 + 1)
        at, cams = {}, {}
        for f in frames:
            scene.frame_set(f)
            if callable(self.source):
                at[f] = np.asarray(self.source(f), float)
            else:
                m = self.source.matrix_world
                at[f] = np.array(m @ Vector(self.offset))
            cams[f] = np.array(scene.camera.matrix_world.translation)
        fs = np.array(list(frames), float)
        xyz = np.array([at[f] for f in frames])

        def source(times):
            fr = np.clip(np.asarray(times, float) * fps, fs[0], fs[-1])
            return np.stack([np.interp(fr, fs, xyz[:, k]) for k in range(3)], axis=1)

        me = self.ob.data
        for f in range(f0, f1):
            P, _, alpha, width = self.wisp.points(f / fps, source)
            self.frames[f] = (ribbon_verts(P, width, cams[f]).ravel(), np.repeat(alpha, 2))
        self._set(me, f0)
        name = self.ob.name

        def pose_smoke(scn, *_):
            ob = bpy.data.objects.get(name)
            if ob is None:
                return
            self._set(ob.data, scn.frame_current)

        pose_smoke.__name__ = f"smoke_{name}".replace("-", "_")
        bpy.app.handlers.frame_change_pre.append(pose_smoke)
        scene.frame_set(f0)

    def _set(self, me, f: int) -> None:
        if not self.frames:
            return
        f = min(max(f, min(self.frames)), max(self.frames))
        co, alpha = self.frames[f]
        me.vertices.foreach_set("co", co)
        me.attributes["smoke_alpha"].data.foreach_set("value", alpha)
        me.update()


def ribbon(name: str, wisp: Wisp, *, source, coll, offset=(0.0, 0.0, 0.0), color=(0.62, 0.65, 0.7),
           also=(), breakup: float = 0.75, scene=None) -> Ribbon:
    """A wisp as a ribbon in `coll` (and linked into the collections `also`). `source` is an object (its world
    location, plus `offset` in its own axes: the bowl on a pipe) or a function of the film frame giving a point.
    `color` linear; `breakup` (0..1): how much drifting noise thins it into strands."""
    import bpy

    from . import toon

    scene = scene or bpy.context.scene
    n = wisp.count()
    me = bpy.data.meshes.new(name)
    me.from_pydata([(0.0, 0.0, 0.01 * i) for i in range(2 * n)], [], strip_faces(n))
    uv = me.uv_layers.new(name="UVMap")
    co = []
    for i in range(n):
        for side in (0.0, 1.0):
            co.append((i / max(1, n - 1), side))
    for poly in me.polygons:
        for li in poly.loop_indices:
            uv.data[li].uv = co[me.loops[li].vertex_index]
    me.attributes.new("smoke_alpha", "FLOAT", "POINT")
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    for c in also:
        c.objects.link(ob)
    ob.visible_shadow = False
    ob.lineart.usage = "EXCLUDE"        # a wisp has no ink line round it (toon.ink's Line Art leaves it out)

    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    N, L = nt.nodes, nt.links
    tc = N.new("ShaderNodeUVMap")
    tc.uv_map = "UVMap"
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["UV"], sep.inputs[0])

    def math_(op, a, b=None, clamp=False):
        m = N.new("ShaderNodeMath")
        m.operation, m.use_clamp = op, clamp
        for i, x in enumerate((a, b)):
            if x is None:
                continue
            if isinstance(x, (int, float)):
                m.inputs[i].default_value = float(x)
            else:
                L.new(x, m.inputs[i])
        return m.outputs[0]

    # soft across: dense along the middle, fading to nothing well before the edges (no hard side to the strip)
    across = math_("SUBTRACT", 1.0, math_("ABSOLUTE", math_("SUBTRACT", math_("MULTIPLY", sep.outputs["Y"], 2.0), 1.0)))
    soft = math_("POWER", math_("MULTIPLY", across, across), 1.3)
    # broken into strands by noise drifting up the ribbon: long along it (u), fine across it (v), so it reads as
    # threads of smoke rather than bands
    t = toon.frame_value(nt, scene, 0.35)
    vec = N.new("ShaderNodeCombineXYZ")
    L.new(math_("SUBTRACT", math_("MULTIPLY", sep.outputs["X"], 1.8), t), vec.inputs["X"])
    L.new(math_("MULTIPLY", sep.outputs["Y"], 7.0), vec.inputs["Y"])
    vec.inputs["Z"].default_value = float(wisp.seed)
    noise = N.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.2
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.6
    L.new(vec.outputs[0], noise.inputs["Vector"])
    rng = N.new("ShaderNodeMapRange")
    rng.inputs["From Min"].default_value = 0.35
    rng.inputs["From Max"].default_value = 0.7
    L.new(noise.outputs["Fac"], rng.inputs["Value"])
    strands = math_("ADD", math_("MULTIPLY", rng.outputs["Result"], breakup), 1.0 - breakup)
    attr = N.new("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = "smoke_alpha"
    alpha = math_("MULTIPLY", math_("MULTIPLY", soft, strands), attr.outputs["Fac"], clamp=True)
    em = N.new("ShaderNodeEmission")
    L.new(toon.flashed(nt, tuple(color), (0.9, 0.93, 1.0), 0.6), em.inputs["Color"])
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    L.new(alpha, mx.inputs["Fac"])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(em.outputs[0], mx.inputs[2])
    out = N.new("ShaderNodeOutputMaterial")
    L.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    me.materials.append(mat)
    return Ribbon(ob, wisp, source, offset)
