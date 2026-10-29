"""Shinza's approach to the crossing, shared by shots 3 to 5 (step, walk, eyes): his walk up the path along the near
bank out of the mist, the puddle he steps in, and the way the three shots paint and light him.

The world is the sets' (rf/set_world.py, in rf/sets.py's axes): the path comes up the river along the near bank from
down the valley's other way (-y) to the jetty's foot, over the valley's ground (not level: `ground`), its line
rf/set_approach.path_xy(). Shinza is the cast's (`walker`: rf/vroid_cast.py with the kasa on, the sword on his back).

He walks by lib/vrm_anim.py (`walk_through`: a walk laid so a given foot lands on a given spot at a given time, over
the set's ground); `Gait` is the line along the path and where a steady walk puts him on it (pure). The shots are
filmed with lib/cinema.py and rained on by lib/weather.py (`storm`, `brim_drips`); what a footfall does to the water
is here (`splash`, `ripples`, `drips` off a lifted sole).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# ---- Shinza for the walk

def walker(coll, look, name: str = "shinza") -> dict:
    """Shinza for the walk: rf/vroid_cast.py's, the kasa on his head, the nodachi on his back, standing; his limbs
    let go of their IK (key_walk plants the feet again). Returns its dict with "stand" (the standing pose,
    vrm_rig.release's: a base to key on top of) and "kasa" (its objects, the hat first)."""
    from lib import vrm_rig
    from rf import vroid_cast

    built = vroid_cast.shinza(coll, look, name=name, kasa="on", sword="back")
    built["stand"] = vrm_rig.release(built["vrm"])
    built["kasa"] = built["parts"]["kasa"]
    return built


def brim(hat) -> list:
    """The kasa's brim edge: its vertices farthest out from its axis (the hat's own frame)."""
    r = [math.hypot(v.co.x, v.co.y) for v in hat.data.vertices]
    top = max(r)
    return [v.co.copy() for v, d in zip(hat.data.vertices, r) if d > top - 1e-4]


# ---- the walk

def arc(line) -> np.ndarray:
    """The arc length at each point of a polyline (n, 2)."""
    P = np.asarray(line, float)
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])


@dataclass
class Gait:
    """A walk laid down as footfalls along `line` ((n, 2) points on the ground, in the order walked; or a straight
    line from `origin` along `dir`). Foot k (0, 1, 2, ...; foot 0 is `first`) lands at time t0 + k * step, `s0 + k *
    stride` metres along the line (either side of it by `width`), flat after `heel` of its cycle, its heel rising from
    `rise` and its toes leaving the ground at `stance` (of the two-step cycle); then it swings, `lift` high, to its
    next footfall. `ground(x, y)` is the ground's height (default 0). Times in seconds, lengths in metres. Pure:
    where the feet and the body are at any time."""
    line: object = None
    origin: tuple = (0.0, 0.0)
    dir: tuple = (0.0, -1.0)
    s0: float = 0.0
    t0: float = 0.0
    step: float = 0.62            # seconds a step
    stride: float = 0.7           # metres a step
    width: float = 0.1            # each foot's line out from the middle
    lift: float = 0.09            # the swinging ankle's highest over its path (heavy: low)
    heel: float = 0.06
    rise: float = 0.4
    stance: float = 0.6
    strike: float = -14.0         # the foot's pitch at heel strike (degrees, + toes down)
    push: float = 38.0            # ... and at toe off
    first: str = "right"
    ground: object = None
    _s: object = field(default=None, repr=False)

    def __post_init__(self):
        if self.line is not None:
            self.line = np.asarray(self.line, float)
            self._s = arc(self.line)

    def at(self, s: float) -> tuple[np.ndarray, np.ndarray]:
        """(point (x, y), unit way forward) `s` metres along the line (straight on past its ends)."""
        if self.line is None:
            d = np.asarray(self.dir, float)
            d = d / np.linalg.norm(d)
            return np.asarray(self.origin, float) + d * s, d
        P, S = self.line, self._s
        i = int(np.clip(np.searchsorted(S, s) - 1, 0, len(P) - 2))
        d = P[i + 1] - P[i]
        n = np.linalg.norm(d)
        d = d / n
        # the way forward eased between segments, so the body turns smoothly at the line's corners
        u = (s - S[i]) / n
        if 0 < i and u < 0.5:
            p = P[i] - P[i - 1]
            d = d + (p / np.linalg.norm(p) - d) * (0.5 - u)
        elif i < len(P) - 2 and u > 0.5:
            q = P[i + 2] - P[i + 1]
            d = d + (q / np.linalg.norm(q) - d) * (u - 0.5)
        return P[i] + (P[i + 1] - P[i]) * (s - S[i]) / n, d / np.linalg.norm(d)

    def nearest(self, p) -> float:
        """The arc length of the line's point nearest `p` (x, y)."""
        if self.line is None:
            d = np.asarray(self.dir, float)
            return float((np.asarray(p, float) - self.origin) @ (d / np.linalg.norm(d)))
        ss = np.linspace(self._s[0], self._s[-1], int(self._s[-1] / 0.02) + 2)
        pts = np.array([self.at(s)[0] for s in ss])
        return float(ss[np.argmin(np.linalg.norm(pts - np.asarray(p, float)[:2], axis=1))])

    def z(self, p) -> float:
        return float(self.ground(p[0], p[1])) if self.ground is not None else 0.0

    @staticmethod
    def left_of(d) -> np.ndarray:
        return np.array([-d[1], d[0]])

    def footfall(self, k: int) -> tuple[str, float, np.ndarray, np.ndarray]:
        """(side, time, ground point (x, y), way forward) of foot k."""
        side = self.first if k % 2 == 0 else ("left" if self.first == "right" else "right")
        s = 1.0 if side == "left" else -1.0
        p, d = self.at(self.s0 + k * self.stride)
        return side, self.t0 + k * self.step, p + self.left_of(d) * s * self.width, d

    def foot(self, side: str, t: float, ankle: float, ball: float) -> tuple[np.ndarray, float]:
        """Where the `side` foot's ankle is at time t ((x, y, z), its ankle `ankle` over the ground when flat and the
        ball of its foot `ball` ahead of the ankle) and its pitch (degrees, + toes down)."""
        k0 = 0 if side == self.first else 1
        n = math.floor((t - self.t0 - k0 * self.step) / (2 * self.step))
        k = k0 + 2 * n
        _, tk, p, d = self.footfall(k)
        _, _, q, _ = self.footfall(k + 2)
        u = (t - tk) / (2 * self.step)

        def on_toe(base, pitch):
            # the foot turned about the ball of the foot by `pitch`: the ankle rises and comes forward over it
            a = math.radians(pitch)
            f = -ball * math.cos(a) + ankle * math.sin(a)
            z = ball * math.sin(a) + ankle * math.cos(a)
            return np.array([*(base + d * (ball + f)), z + self.z(base)])

        if u < self.heel:
            return np.array([*p, ankle + self.z(p)]), self.strike * (1 - smooth(u / self.heel))
        if u < self.rise:
            return np.array([*p, ankle + self.z(p)]), 0.0
        if u < self.stance:
            pitch = self.push * smooth((u - self.rise) / (self.stance - self.rise))
            return on_toe(p, pitch), pitch
        s = (u - self.stance) / (1 - self.stance)
        a0 = on_toe(p, self.push)
        a1 = np.array([*q, ankle + self.z(q)])
        at = a0 + (a1 - a0) * smooth(s)
        at[2] += self.lift * math.sin(math.pi * s) ** 0.8
        return at, self.push + (self.strike - self.push) * smooth(min(1.0, s * 1.4))

    def root(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        """The body's point on the ground (x, y) and the way it faces at time t: midway between the feet at each
        strike, on at an even pace."""
        u = (t - self.t0) / self.step
        return self.at(self.s0 + self.stride * (u - 0.5))

    def phase(self, t: float) -> float:
        """Where in the two-step cycle the walk is (0 at the right foot's strike, 0.5 at the left's)."""
        ph = ((t - self.t0) / (2 * self.step)) % 1.0
        return ph if self.first == "right" else (ph + 0.5) % 1.0


def smooth(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


# the walk's carriage (degrees, lib/vrm.py's convention): a heavy, purposeful walk, the trunk leaning into it, the head
# down under the kasa
LEAN = {"spine": (7.0, 0.0, 0.0), "chest": (3.0, 0.0, 0.0), "neck": (4.0, 0.0, 0.0), "head": (6.0, 0.0, 0.0)}


def puddle_on(world: dict, line, s: float, *, within: float = 0.7, reach: float = 6.0):
    """The set's puddle on the path nearest `s` metres along `line` (its middle within `within` of the line, and
    within `reach` of s): (its middle (x, y, water z), how far along the line it lies), or None."""
    from mathutils import Vector

    probe = Gait(line=line)
    best = None
    for ob in world["approach"]["puddles"]:
        c = sum((ob.matrix_world @ Vector(v) for v in ob.bound_box), Vector()) / 8
        sc = probe.nearest((c.x, c.y))
        if np.linalg.norm(probe.at(sc)[0] - (c.x, c.y)) > within or abs(sc - s) > reach:
            continue
        if best is None or abs(sc - s) < abs(best[1] - s):
            best = (np.array([c.x, c.y, ob.matrix_world.translation.z + max(v[2] for v in ob.bound_box)]), sc)
    return best


def walk_through(p, line, *, side: str, at, t: float, gait="heavy", ground=None, before: float = 3.0,
                 after: float = 3.0, pose=None, speed=None) -> dict:
    """Key Performance `p` (lib/vrm_anim.py) walking along `line` ((n, 2) points, in the order walked) so that its
    `side` foot lands on `at` (x, y) at film time `t`: the walk set off `before` seconds of walking earlier and going on
    `after` seconds past it (a shot cut into the middle of a walk), each footfall on `ground` (a height, or (x, y) -> z).
    Returns {"start", "stop" (film frames), "path" (the walked points), "plan" (vrm_anim.plan_steps'), "index" (the
    footfall on `at`, in the plan)}."""
    from lib import vrm_anim as va

    g = va.gait_of(gait).scaled(p.height)
    if speed is not None:
        g = g.but(speed=float(speed))
    probe = Gait(line=line)
    s_at = probe.nearest(at)
    length = (before + after) * g.speed
    steps, _, _ = va.plan_steps(length, g)
    # the footfall of `side` nearest `before` seconds in, laid on `at`: the walk starts that far back along the line
    cands = [(i, st) for i, st in enumerate(steps) if st.side == side]
    i, st = min(cands, key=lambda c: abs(c[1].b - before * g.speed))
    s0 = s_at - st.b
    _, fwd = probe.at(s_at)
    # the line moved over so that foot (half the gait's width to its side) comes down on the point itself
    shift = np.asarray(at, float) - probe.at(s_at)[0] + Gait.left_of(fwd) * (g.width / 2) * (1.0 if side == "right" else -1.0)
    ss = np.linspace(s0, s0 + length, int(length / 0.25) + 2)
    path = np.array([probe.at(x)[0] + shift for x in ss])
    start = t * p.fps - st.t1 * p.fps
    z0 = ground(*path[0]) if callable(ground) else (ground or 0.0)
    d0 = path[1] - path[0]
    p.root(start, (*path[0], z0), yaw=math.degrees(math.atan2(d0[1], d0[0])))
    stop = p.walk(path, start, gait=g, ground=ground, pose=pose)
    return {"start": start, "stop": stop, "path": path, "plan": steps, "index": i}


# ---- water thrown up and rings left

def _water_bead(name: str, color, alpha: float):
    """Water in the air: its colour, `alpha` opaque, blended (catching no shadow)."""
    import bpy

    from lib import toon

    mat = bpy.data.materials.new(name)
    nt = toon.nodes(mat)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(toon.flashed(nt, color, (1.0, 1.0, 1.0), 1.0), em.inputs["Color"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    mx.inputs["Fac"].default_value = alpha
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    return mat


def splash(name: str, at, t: float, fps: float, *, coll, count: int = 70, speed=(0.6, 1.7), spread: float = 0.17,
           size: float = 0.007, color=(0.62, 0.66, 0.72), alpha: float = 0.7, seed: int = 1, frames=None) -> list:
    """A foot coming down in water at `at` (x, y, z: the water's surface) at time t (s): `count` drops thrown up
    and out from a ring `spread` round it at `speed` (m/s), each a bead stretched along its flight, falling back
    under gravity and gone where it meets the water. Keyed over `frames` (film frames). Returns the drops."""
    import bpy
    from mathutils import Vector

    from lib import shapes

    rng = np.random.default_rng(seed)
    mat = _water_bead(f"{name}-water", color, alpha)
    drops = []
    x0, y0, z0 = at
    for i in range(count):
        a = rng.uniform(0, 2 * math.pi)
        r0 = spread * rng.uniform(0.5, 0.9)
        p0 = np.array([x0 + math.cos(a) * r0, y0 + math.sin(a) * r0 * 0.8, z0 + 0.01])
        up = rng.uniform(*speed)
        out_v = up * rng.uniform(0.15, 0.45)       # thrown up more than out: a crown, not a fan
        v0 = np.array([math.cos(a) * out_v, math.sin(a) * out_v * 0.8, up])
        delay = rng.uniform(0.0, 0.05)
        s = size * rng.uniform(0.5, 1.4)
        ob = shapes.ellipsoid(f"{name}-{i}", (0, 0, 0), (s, s, s), material=mat, coll=coll, n=6)
        ob.visible_shadow = False
        for f in frames:
            dt = f / fps - t - delay
            z = p0[2] + v0[2] * dt - 4.9 * dt * dt if dt > 0 else -1.0
            live = dt > 0 and z > z0
            ob.hide_render = ob.hide_viewport = not live
            ob.keyframe_insert("hide_render", frame=f)
            ob.keyframe_insert("hide_viewport", frame=f)
            if live:
                v = v0 + np.array([0, 0, -9.8 * dt])
                ob.location = tuple(p0 + v0 * dt + np.array([0, 0, -4.9 * dt * dt]))
                # stretched along its flight by how far it goes in half a frame's shutter
                stretch = 1 + np.linalg.norm(v) * 0.5 / fps / s
                ob.rotation_mode = "QUATERNION"
                ob.rotation_quaternion = Vector(tuple(v)).to_track_quat("Z", "Y")
                ob.scale = (1.0, 1.0, min(stretch, 6.0))
                for path in ("location", "rotation_quaternion", "scale"):
                    ob.keyframe_insert(path, frame=f)
        drops.append(ob)
    return drops


def ripples(name: str, at, t: float, fps: float, *, coll, frames, rings: int = 4, speed: float = 0.32,
            gap: float = 0.11, life: float = 1.6, width: float = 0.006, color=(0.55, 0.59, 0.65), alpha: float = 0.6,
            squash: float = 1.0) -> list:
    """Rings running out over the water from `at` (x, y, z) from time t: `rings` of them, each `gap` seconds after
    the one before, at `speed` m/s, thinning and fading over `life` seconds. Returns their objects."""
    import bpy

    from lib import toon

    obs = []
    for k in range(rings):
        n = 64
        a = np.linspace(0, 2 * math.pi, n, endpoint=False)
        verts = [(math.cos(v) * (1 - width), math.sin(v) * (1 - width) * squash, 0.0) for v in a]
        verts += [(math.cos(v) * (1 + width), math.sin(v) * (1 + width) * squash, 0.0) for v in a]
        faces = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        me = bpy.data.meshes.new(f"{name}-{k}")
        me.from_pydata(verts, [], faces)
        ob = bpy.data.objects.new(f"{name}-{k}", me)
        coll.objects.link(ob)
        ob.location = (at[0], at[1], at[2] + 0.002)
        ob.visible_shadow = False
        mat = bpy.data.materials.new(f"{name}-{k}")
        nt = toon.nodes(mat)
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*color, 1)
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mx = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(em.outputs[0], mx.inputs[2])
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(mx.outputs[0], out.inputs["Surface"])
        mat.surface_render_method = "BLENDED"
        me.materials.append(mat)
        fac = mx.inputs["Fac"]
        for f in frames:
            dt = f / fps - t - k * gap
            u = dt / life
            r = max(0.002, 0.03 + speed * max(dt, 0.0) * (1 - 0.35 * min(max(u, 0.0), 1.0)))
            ob.scale = (r, r, 1.0)
            ob.keyframe_insert("scale", frame=f)
            fac.default_value = alpha * (1 - u) ** 1.5 * min(1.0, dt * 12) if 0 < u < 1 else 0.0
            fac.keyframe_insert("default_value", frame=f)
        obs.append(ob)
    return obs


def drips(name: str, points, t0: float, t1: float, fps: float, *, coll, frames, every=(0.35, 0.8), fall: float = 1.6,
          size: float = 0.0045, color=(0.7, 0.74, 0.8), alpha: float = 0.75, seed: int = 2, carry=None) -> list:
    """Water dripping from edges (a kasa's brim, a sandal lifted out of a puddle): at each of `points` ((x, y, z),
    or a function of time giving them) a drop swells and falls every `every` seconds (from, to: each its own) between
    t0 and t1, falling `fall` metres and gone. `carry(t)` -> a point list for drops that move with what they hang from
    (only while they hang). Returns the drops' objects."""
    from lib import shapes

    rng = np.random.default_rng(seed)
    mat = _water_bead(f"{name}-water", color, alpha)
    where = carry or (lambda t: points)
    obs = []
    n_pts = len(where(t0))
    for i in range(n_pts):
        times, tt = [], t0 + rng.uniform(0, every[1])
        while tt < t1:
            times.append(tt)
            tt += rng.uniform(*every)
        for j, tf in enumerate(times):
            ob = shapes.ellipsoid(f"{name}-{i}-{j}", (0, 0, 0), (size, size, size * 1.3), material=mat, coll=coll, n=8)
            ob.visible_shadow = False
            swell = 0.3
            for f in frames:
                t = f / fps
                dt = t - tf
                live = -swell < dt and dt < math.sqrt(2 * fall / 9.8)
                ob.hide_render = ob.hide_viewport = not live
                ob.keyframe_insert("hide_render", frame=f)
                ob.keyframe_insert("hide_viewport", frame=f)
                if not live:
                    continue
                p = np.asarray(where(min(t, tf))[i], float)
                if dt < 0:      # swelling where it hangs
                    k = 0.3 + 0.7 * (1 + dt / swell)
                    ob.location = tuple(p - np.array([0, 0, size * k]))
                    ob.scale = (k, k, k * 1.2)
                else:
                    v = 9.8 * dt
                    ob.location = tuple(p - np.array([0, 0, size + 4.9 * dt * dt]))
                    ob.scale = (0.85, 0.85, min(1.0 + v * 0.5 / fps / size, 8.0))
                ob.keyframe_insert("location", frame=f)
                ob.keyframe_insert("scale", frame=f)
            obs.append(ob)
    return obs


# ---- painting and lighting him

def paint(actors: dict, toward: dict, *, coll, tones: dict | None = None, tones_of: dict | None = None,
          angle: float = 5.0) -> dict:
    """The 3D cast painted as the standoff paints it (shots/standoff.py's TONES3D: blender/lib/toon3d.py), each lit by
    a key of their own from `toward[name]` (world). Returns {name: key light}."""
    import importlib.util
    from pathlib import Path

    from lib import toon3d, vrm

    if tones is None or tones_of is None:
        spec = importlib.util.spec_from_file_location("shots.standoff",
                                                      Path(__file__).resolve().parents[1] / "shots" / "standoff.py")
        standoff = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(standoff)
        tones = standoff.TONES3D if tones is None else tones
        tones_of = standoff.TONES3D_OF if tones_of is None else tones_of
    keys = {}
    for name, built in actors.items():
        keys[name] = toon3d.key(f"{name}-key", [built["root"], *built["root"].children_recursive], toward[name],
                                coll=coll, angle=angle)
        t = {p: toon3d.Tone(**{**kw, **tones_of.get(name, {}).get(p, {})}) for p, kw in tones.items()}
        vrm.anime(built["vrm"], t, keys[name])
        vrm.smooth(built["vrm"])
    return keys


# ---- the stage the three shots share

@dataclass
class Stage:
    """What `stage` built: the world and Shinza in it, painted and lit, ready for a shot's camera and weather."""
    world: dict           # rf/set_world.build's
    cast: object          # the cast's collection (satsuei)
    shinza: dict
    key: object           # his own key light (toon3d)

    @property
    def look(self):
        return self.world["look"]


def stage(ctx, *, key_toward, ink: float | None = None) -> Stage:
    """The world (rf/set_world.py, its weather from the look schedule) with Shinza in it, painted with his own key
    from `key_toward` (world); the near set inked `ink` metres (None: none, a close shot's set is out of focus)."""
    from lib import toon
    from rf import set_world

    scene = ctx.scene
    scene.view_settings.view_transform = "Standard"
    world = set_world.build(ctx)
    if ink:
        toon.ink("ink-near", world["near"], radius=ink, crease=150)
    cast = toon.collection("cast")
    look = world["look"]
    shinza = walker(cast, toon.Look(fog=look.fog, fog_near=look.fog_near, fog_far=look.fog_far, fog_max=look.fog_max,
                                    fog_power=look.fog_power))
    keys = paint({"shinza": shinza}, {"shinza": key_toward}, coll=cast)
    return Stage(world, cast, shinza, keys["shinza"])


def storm(ctx, rig, st: Stage, *, splashes=(), floor=None, ground: float = 0.0, layers=None, in_cast=("near", "mid")):
    """The shot's weather (lib/weather.py storm: the look schedule's rain and mist round the rig's setups in `layers`,
    splashing on `splashes`, ringing the set's waters) with the rain's `in_cast` layers falling again in the cast's
    layer too, so the drops between the lens and him stay in front of him once the compositor lays him over the
    world."""
    from lib import weather

    sky = weather.storm(ctx, rig, splashes=list(splashes), waters=st.world["waters"], floor=floor, ground=ground,
                        layers=layers)
    if sky.rain is not None:
        for (_, ln), d in sky.rain.drops.items():
            if ln in in_cast:
                twin = d.ob.copy()
                twin.name = f"{d.ob.name}-cast"
                st.cast.objects.link(twin)
    return sky


def brim_drips(name: str, hat, *, front=None, n: int = 12, **kw):
    """Water dripping off the kasa's brim (lib/weather.py drips, carried by the hat): `n` points round it, or the `n`
    nearest `front` (a world point: the lens) when given."""
    import bpy

    from lib import weather

    lip = brim(hat)
    if front is not None:
        bpy.context.view_layer.update()
        mw = hat.matrix_world
        lip = sorted(lip, key=lambda v: ((mw @ v) - front).length)[:n * 3]
        lip = sorted(lip, key=lambda v: math.atan2(v.y, v.x))
    step = max(1, len(lip) // n)
    pts = [tuple(v) for v in lip[::step][:n]]
    return weather.drips(name, pts, parent=hat, **kw)
