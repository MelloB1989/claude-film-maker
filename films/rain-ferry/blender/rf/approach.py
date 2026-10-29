"""Shinza's approach to the crossing, shared by shots 3 to 5 (step, walk, eyes): the mountain path he walks down out
of the mist, his walk, his kasa and the nodachi on his back, the puddle he steps in and the way the three shots paint
and light him.

World axes (the path's own place, not the crossing's): the path runs along y, the ground's top at z 0; he walks down
it toward -y, toward a camera at -y looking up it into the mist. The path's centre line is x = 0; pines stand along
both sides, ridges fade into the mist behind.

Stand-ins, each replaced when its owner's API is merged (the shots go through the functions here, so only this file
changes):
- `path_set(look)`: the path, its puddles, pines, mist and sky (the sets agent's path, rf/set_path.py, when there).
- `walker(coll, look)`: Shinza for the walk, his guard undone, a kasa on and the nodachi on his back (the cast
  agent's variant, rf/vroid_shinza.shinza(kasa="on"), when there).
- `Gait` / `key_walk`: a heavy walk, its feet planted by IK on footfalls laid down the path (no foot slides on the
  ground), the hips falling and rising between them, the trunk and arms swinging against the legs (the anim agent's
  walk generator, lib/vrm_anim.py, when there).
- `splash`, `ripples`, `drips`: the water a footfall throws up and the rings it leaves (the cinema agent's fx).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# ---- the path: a muddy track down a wooded slope, flat across its middle, banks rising either side
PATH_HALF = 1.1           # half the trodden track's width (m)
BANK = (2.6, 0.9)         # the banks: how far out they rise (m), how high
PATH_Y = (-14.0, 70.0)    # how far the ground runs along y
# the path's colours (linear lit, shade), cold and wet
COLORS = {
    "mud": ((0.055, 0.052, 0.05), (0.016, 0.016, 0.019)),
    "bank": ((0.06, 0.066, 0.058), (0.016, 0.018, 0.019)),
    "grass": ((0.075, 0.088, 0.072), (0.02, 0.024, 0.024)),
    "rock": ((0.07, 0.072, 0.075), (0.017, 0.018, 0.021)),
    "trunk": ((0.035, 0.033, 0.033), (0.009, 0.009, 0.011)),
    "needles": ((0.04, 0.05, 0.048), (0.012, 0.015, 0.016)),
    "ridge": ((0.035, 0.04, 0.048), (0.035, 0.04, 0.048)),
}
SKY = (0.42, 0.45, 0.5)       # the fog at the horizon (linear): colder and darker than the crossing's open sky
ZENITH = (0.26, 0.28, 0.32)
PUDDLE = ((0.012, 0.014, 0.018), (0.2, 0.215, 0.24))   # (water, the light of its rings)
# puddles on the track: (x, y, radius x, radius y, seed); the first is the one he steps in
PUDDLES = [(-0.12, 0.0, 0.42, 0.3, 1), (0.35, 3.2, 0.5, 0.28, 2), (-0.3, 6.8, 0.6, 0.32, 3), (0.2, 10.5, 0.45, 0.25, 4),
           (-0.15, 15.0, 0.7, 0.35, 5), (0.4, 21.0, 0.55, 0.3, 6), (-0.4, -2.6, 0.5, 0.3, 7)]
# pines: (x, y, height); near ones frame the path, far ones go grey in the mist
PINES = [(-3.4, 4.0, 13.0), (3.9, 7.5, 15.0), (-4.6, 13.0, 16.0), (4.4, 17.0, 14.0), (-3.6, 22.0, 15.0),
         (5.4, 26.0, 17.0), (-5.8, 30.0, 16.0), (3.6, 36.0, 15.0), (-4.2, 42.0, 18.0), (6.5, 48.0, 16.0),
         (-7.5, 55.0, 17.0), (2.8, 60.0, 15.0), (-6.0, 1.0, 14.0), (6.8, 1.5, 16.0), (-8.5, 18.0, 18.0),
         (8.5, 33.0, 18.0)]
ROCKS = [(-1.8, 1.2, 0.45), (1.7, 4.6, 0.38), (-2.0, 9.5, 0.55), (1.9, 12.4, 0.4), (-1.6, -1.5, 0.35),
         (2.2, -0.6, 0.5)]
RIDGES = [(110, 30, 1.4), (190, 60, 0.0), (300, 95, 0.0)]          # (distance, height, tree fringe)
MIST = [(14, 3.2, 40), (28, 5.0, 70), (48, 8.0, 110), (80, 16, 220)]   # (distance, height, width): mist down the path


def _bank_z(x: float, y: float) -> float:
    """The ground's height at (x, y): flat across the track, rising over the banks, rolling a little."""
    out = max(0.0, abs(x) - PATH_HALF) / BANK[0]
    rise = BANK[1] * (1 - math.cos(math.pi * min(out, 1.0))) / 2 + 0.35 * max(0.0, out - 1.0)
    return rise * (1 + 0.25 * math.sin(y * 0.45 + x)) - 0.025 * math.sin(x * 3.1) * math.sin(y * 2.3)


def path_set(look, *, seed: int = 3) -> dict:
    """The path (rf/set_path.py's when there): returns {"near": the collection drawn in line art, "far": the
    distance, "puddles": [puddle objects], "materials": {...}}."""
    try:
        from rf import set_path  # the sets agent's
        return set_path.path(look, seed=seed)
    except ImportError:
        pass
    from lib import landscape, shapes, toon

    near = toon.collection("set-near")
    far = toon.collection("set-far")
    m = {k: toon.cel(f"path-{k}", lit, shade, look=look, cut=0.38, flash=0.0 if k in ("ridge", "needles") else None)
         for k, (lit, shade) in COLORS.items()}

    # the ground: one sheet across the track and up both banks
    xs = np.concatenate([np.linspace(-14, -PATH_HALF, 22), np.linspace(-PATH_HALF, PATH_HALF, 12)[1:-1],
                         np.linspace(PATH_HALF, 14, 22)])
    ys = np.linspace(*PATH_Y, 90)
    verts = [(x, y, _bank_z(x, y)) for y in ys for x in xs]
    n = len(xs)
    faces = [(j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i) for j in range(len(ys) - 1)
             for i in range(n - 1)]
    ground = shapes.mesh_object("path-ground", verts, faces, m["mud"], near, smooth=True)
    ground.data.materials.append(m["bank"])
    for poly in ground.data.polygons:
        poly.material_index = int(abs(poly.center.x) > PATH_HALF + 0.3)
    # grass along the track's edges, rocks on its banks
    rng = np.random.default_rng(seed)
    roots, tips, widths = [], [], []
    for _ in range(900):
        y = rng.uniform(-8, 40)
        side = rng.choice((-1.0, 1.0))
        x = side * (PATH_HALF + abs(rng.normal(0.25, 0.6)))
        r0 = np.array([x, y, _bank_z(x, y) - 0.02])
        roots.append(r0)
        tips.append(r0 + np.array([rng.normal(0, 0.08), rng.normal(0, 0.08), rng.uniform(0.18, 0.5)]))
        widths.append(rng.uniform(0.012, 0.03))
    shapes.spikes("path-grass", roots, tips, widths, material=m["grass"], coll=near, sides=3)
    for k, (x, y, r) in enumerate(ROCKS):
        shapes.ellipsoid(f"path-rock{k}", (x, y, _bank_z(x, y) + r * 0.2), (r * 1.3, r, r * 0.6), material=m["rock"],
                         coll=near, n=12, squash=lambda v, s=k: v * (1 + 0.18 * np.sin(v[:, :1] * 9 + s)))
    puddles = [puddle(f"puddle{k}", (x, y), (rx, ry), look, coll=near, seed=s)
               for k, (x, y, rx, ry, s) in enumerate(PUDDLES)]
    for k, (x, y, h) in enumerate(PINES):
        landscape.pine(f"pine{k}", (x, y, _bank_z(x, y)), h, trunk=m["trunk"], needles=m["needles"],
                       coll=near if y < 20 else far, seed=seed + k)
    for k, (d, h, trees) in enumerate(RIDGES):
        landscape.ridge(f"ridge{k}", m["ridge"], far, d, h, seed=seed * 10 + k, trees=trees, base_z=-2)
    landscape.mist_layers(far, SKY, MIST, base_z=0.0, density=0.8)
    landscape.sky("sky", far, horizon=SKY, zenith=ZENITH, distance=600.0)
    return {"near": near, "far": far, "puddles": puddles, "materials": m}


def puddle_outline(radii, seed: int, n: int = 40) -> np.ndarray:
    """A puddle's wandering edge: n points round an ellipse of `radii`, pushed in and out (unit-free)."""
    rng = np.random.default_rng(seed)
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    wob = 1 + 0.16 * np.sin(2 * a + rng.uniform(0, 6)) + 0.09 * np.sin(5 * a + rng.uniform(0, 6))
    return np.c_[np.cos(a) * radii[0] * wob, np.sin(a) * radii[1] * wob]


def puddle(name: str, at, radii, look, *, coll, seed: int = 1, z: float = 0.004):
    """A puddle lying on the track at `at` (x, y): dark water with rain rings, the sky and whatever stands over it
    reflected (toon.water)."""
    from lib import shapes, toon

    ring = puddle_outline(radii, seed)
    x, y = at
    verts = [(x, y, z)] + [(x + px, y + py, z) for px, py in ring]
    faces = [(0, i, i % len(ring) + 1) for i in range(1, len(ring) + 1)]
    mat = toon.water(f"{name}-water", PUDDLE[0], PUDDLE[1], look=look, rings=1.0, reflect=0.55, scale=0.25)
    ob = shapes.mesh_object(name, verts, faces, mat, coll, smooth=False)
    ob.visible_shadow = False
    return ob


# ---- Shinza for the walk

KASA = dict(radius=0.29, height=0.15, drop=0.115, tilt=9.0)   # the hat: its brim's radius, its cone's height, how far
# below the crown its brim's front comes (low over the eyes) and how far it tips forward (degrees)
NODACHI = dict(hilt=0.3, saya=1.02, across=(0.55, 0.0, -1.0))   # his sword on his back: hilt over the right shoulder,
# the scabbard running down across his back toward the left hip
STRAW = {"straw": ((0.26, 0.205, 0.11), (0.05, 0.04, 0.022)), "straw_dark": ((0.15, 0.115, 0.06), (0.035, 0.026, 0.016)),
         "cord": ((0.2, 0.13, 0.08), (0.06, 0.04, 0.025))}


def walker(coll, look, name: str = "shinza") -> dict:
    """Shinza for the walk (rf/vroid_shinza.py's variant with kasa="on" when there): his low guard undone, the
    katana gone from his hands, his arms hanging, a kasa on his head and the nodachi across his back. Returns the
    builder's dict (rf/vroid_cast.py) with "kasa" (its objects; "brim": the brim's front edge points, his frame) added."""
    import inspect

    from rf import vroid_shinza

    if "kasa" in inspect.signature(vroid_shinza.shinza).parameters:
        return vroid_shinza.shinza(coll, look, name=name, kasa="on")
    built = vroid_shinza.shinza(coll, look, name=name)
    ch = built["vrm"]
    unpose(ch, built.pop("props", []))
    from lib import vrm

    vrm.pose(ch, vrm.RELAXED)
    built["kasa"] = kasa(ch, coll, look, name)
    built["props"] = nodachi(ch, coll, look, name)
    return built


def unpose(ch, props) -> None:
    """A built pose undone: every IK and held bone let go, its handles gone, the props in its hands removed."""
    import bpy

    for pb in ch.armature.pose.bones:
        for c in list(pb.constraints):
            pb.constraints.remove(c)
    for e in ch.handles.values():
        bpy.data.objects.remove(e, do_unlink=True)
    ch.handles.clear()
    ch.bends.clear()
    for ob in props:
        bpy.data.objects.remove(ob, do_unlink=True)


def kasa_profile(radius: float, height: float, n: int = 12) -> list:
    """The kasa's cone as (r, z) from its brim to its point, its slope easing a little near the top, a lip at the
    brim's edge (z up from the brim)."""
    out = [(radius, -0.008), (radius * 0.985, 0.0)]
    for k in range(1, n):
        u = k / n
        out.append((radius * (1 - u), height * (u ** 0.85)))
    out.append((0.0, height))
    return out


def kasa(ch, coll, look, name: str) -> list:
    """A woven straw kasa on his head, its brim low over his eyes, tipped forward; carried by his head."""
    from mathutils import Vector

    from lib import anime, shapes, vrm

    m = anime.palette(STRAW, look, prefix=f"{name}-kasa")
    chin, crown = ch.head_span()
    face = ch.face()
    head = ch.point("head")
    centre = Vector((head.x, head.y, crown - KASA["drop"] + 0.02))
    prof = kasa_profile(KASA["radius"], KASA["height"])
    hat = shapes.lathe(f"{name}-kasa", prof, material=m["straw"], coll=coll, n=48, center=tuple(centre))
    # the weave's rings: darker bands round the cone
    rings = []
    for k, u in enumerate((0.22, 0.45, 0.68)):
        r = KASA["radius"] * (1 - u)
        z = KASA["height"] * u ** 0.85
        rings.append(shapes.lathe(f"{name}-kasa-ring{k}", [(r + 0.004, z - 0.006), (r + 0.004, z + 0.006)],
                                  material=m["straw_dark"], coll=coll, n=48, center=tuple(centre)))
    obs = [hat, *rings]
    # tipped forward over his face (toward where he looks), pivoting at the crown
    front = Vector(face) - Vector((head.x, head.y, face.z))
    front.z = 0.0
    front = front.normalized() if front.length > 1e-6 else Vector((1.0, 0.0, 0.0))
    axis = front.cross(Vector((0.0, 0.0, 1.0)))
    tip = math.radians(KASA["tilt"])
    for ob in obs:
        ob.rotation_mode = "AXIS_ANGLE"
        ob.rotation_axis_angle = (-tip, *axis)
        vrm.attach(ob, ch, "head")
    return obs


def nodachi(ch, coll, look, name: str) -> list:
    """His long sword sheathed across his back: the hilt up over his right shoulder, the black scabbard down to his
    left hip; carried by his chest."""
    from lib import anime, props, shapes, vrm

    from .vroid_common import COLORS

    m = anime.palette(COLORS, look, prefix=f"{name}-nodachi")
    neck = np.asarray(ch.rest("neck"))
    d = np.asarray(NODACHI["across"], float)
    d /= np.linalg.norm(d)
    # his frame: x his left, y his back. The hilt's guard sits behind his right shoulder blade
    guard = neck + np.array([-0.1, 0.13, -0.08])
    pommel = guard - d * NODACHI["hilt"]
    pw, gw = ch.world(pommel), ch.world(guard)
    sword = props.katana(f"{name}-nodachi", m, tuple(pw), tuple(gw - pw), hilt=NODACHI["hilt"], blade=0.04, coll=coll)
    end = ch.world(guard + d * NODACHI["saya"])
    saya = shapes.loft(f"{name}-saya", [tuple(gw), tuple(end)], [0.02, 0.016], [0.013, 0.011], material=m["lacquer"],
                       coll=coll, n=10, subsurf=0)
    obs = [*sword, saya]
    for ob in obs:
        vrm.attach(ob, ch, "upperChest" if ch.has("upperChest") else "chest")
    return obs


# ---- the walk

@dataclass
class Gait:
    """A walk laid down as footfalls. Foot k (0, 1, 2, ...; even ones the right) lands at time t0 + k * step on the
    point origin + dir * k * stride (+ either side by `width`), flat after `heel` of its cycle, its heel rising from
    `rise` and its toes leaving the ground at `stance` (of the two-step cycle); then it swings, `lift` high, to its
    next footfall. Times in seconds, lengths in metres. Pure: positions of feet and hips at any time."""
    origin: tuple = (0.0, 0.0)
    dir: tuple = (0.0, -1.0)
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
    first: str = "right"          # which foot is foot 0

    def _d(self):
        d = np.asarray(self.dir, float)
        return d / np.linalg.norm(d)

    def left_axis(self) -> np.ndarray:
        d = self._d()
        return np.array([-d[1], d[0]])

    def footfall(self, k: int) -> tuple[str, float, np.ndarray]:
        """(side, time, ground point (x, y)) of foot k."""
        side = self.first if k % 2 == 0 else ("left" if self.first == "right" else "right")
        s = 1.0 if side == "left" else -1.0
        p = np.asarray(self.origin, float) + self._d() * k * self.stride + self.left_axis() * s * self.width
        return side, self.t0 + k * self.step, p

    def foot(self, side: str, t: float, ankle: float, ball: float) -> tuple[np.ndarray, float]:
        """Where the `side` foot's ankle is at time t ((x, y, z), its ankle `ankle` over the ground when flat and the
        ball of its foot `ball` ahead of the ankle) and its pitch (degrees, + toes down)."""
        k0 = 0 if side == self.first else 1
        n = math.floor((t - self.t0 - k0 * self.step) / (2 * self.step))
        k = k0 + 2 * n
        _, tk, p = self.footfall(k)
        _, _, q = self.footfall(k + 2)
        u = (t - tk) / (2 * self.step)
        d = self._d()

        def on_toe(base, pitch):
            # the foot turned about the ball of the foot by `pitch`: the ankle rises and comes forward over it
            a = math.radians(pitch)
            f = -ball * math.cos(a) + ankle * math.sin(a)
            z = ball * math.sin(a) + ankle * math.cos(a)
            return np.array([*(base + d * (ball + f)), z])

        if u < self.heel:
            pitch = self.strike * (1 - smooth(u / self.heel))
            return np.array([*p, ankle]), pitch
        if u < self.rise:
            return np.array([*p, ankle]), 0.0
        if u < self.stance:
            pitch = self.push * smooth((u - self.rise) / (self.stance - self.rise))
            return on_toe(p, pitch), pitch
        s = (u - self.stance) / (1 - self.stance)
        a0 = on_toe(p, self.push)
        a1 = np.array([*q, ankle])
        e = smooth(s)
        at = a0 + (a1 - a0) * e
        at[2] += self.lift * math.sin(math.pi * s) ** 0.8
        pitch = self.push + (self.strike - self.push) * smooth(min(1.0, s * 1.4))
        return at, pitch

    def root(self, t: float) -> np.ndarray:
        """The body's point on the ground (x, y) at time t: midway between the feet at each strike, on at an even
        pace."""
        u = (t - self.t0) / self.step
        return np.asarray(self.origin, float) + self._d() * self.stride * (u - 0.5)

    def phase(self, t: float) -> float:
        """Where in the two-step cycle the walk is (0 at the first foot's strike, 0.5 at the other's)."""
        return ((t - self.t0) / (2 * self.step)) % 1.0


def smooth(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def hips_drop(hips: np.ndarray, ankles: list, leg: float) -> float:
    """How far the hips must come down (m, >= 0) for legs `leg` long (hip joint to ankle) to reach every ankle from
    hip joints at `hips` (one (x, y, z) per ankle)."""
    need = 0.0
    for h, a in zip(hips, ankles):
        d = np.asarray(h, float) - np.asarray(a, float)
        flat = math.hypot(d[0], d[1])
        z = math.sqrt(max(leg * leg - flat * flat, 0.0))
        need = max(need, d[2] - z)
    return need


# the walk's upper body (degrees, the module's doc in lib/vrm.py): a heavy, purposeful walk, the trunk leaning into it,
# the head down under the kasa, the arms swinging a little against the legs, the shoulders working
LEAN = {"spine": (7.0, 0.0, 0.0), "chest": (3.0, 0.0, 0.0), "neck": (4.0, 0.0, 0.0), "head": (6.0, 0.0, 0.0)}
SWING = dict(arm=14.0, elbow=(14.0, 8.0), pelvis=6.0, chest=7.0, sway=0.025, sink=0.03, roll=3.0)


def upper_body(phase: float, *, lean: dict = LEAN, swing: dict = SWING) -> dict:
    """The upper body's pose at a phase of the walk (0: the right foot strikes): the pelvis turned with the leading
    leg, the chest against it, the arms swinging opposite the legs (the right back while the right leg leads)."""
    from lib import vrm

    c = math.cos(2 * math.pi * phase)
    s2 = math.sin(4 * math.pi * phase)
    out = {k: tuple(v) for k, v in lean.items()}
    out["hips"] = (0.0, swing["roll"] * math.sin(2 * math.pi * phase), swing["pelvis"] * c)
    sp = out.get("spine", (0.0, 0.0, 0.0))
    out["spine"] = (sp[0], -0.5 * swing["roll"] * math.sin(2 * math.pi * phase), -0.5 * swing["pelvis"] * c)
    ch = out.get("chest", (0.0, 0.0, 0.0))
    out["chest"] = (ch[0] + 1.0 * s2, 0.0, -swing["chest"] * c)
    for side, sign in (("right", 1.0), ("left", -1.0)):
        down = vrm.RELAXED[f"{side}UpperArm"]
        sw = sign * swing["arm"] * c                       # + back
        out[f"{side}UpperArm"] = vrm.euler((sw + 4.0, 0.0, 0.0)) @ vrm.euler(down)
        bend = swing["elbow"][0] + swing["elbow"][1] * max(0.0, -sign * c)   # bent more as it swings forward
        out[f"{side}LowerArm"] = (0.0, 0.0, bend if side == "right" else -bend)
        for f in ("Index", "Middle", "Ring", "Little"):
            for j, deg in (("Proximal", 35.0), ("Intermediate", 45.0), ("Distal", 25.0)):
                out[f"{side}{f}{j}"] = (0.0, (deg if side == "left" else -deg), 0.0)
    return out


def key_walk(ch, gait: Gait, frames, fps: float, *, lean: dict = LEAN, swing: dict = SWING, extra=None) -> dict:
    """Key the character walking `gait` over film `frames` (film frame f is time f / fps): its root carried down the
    path facing the way it goes, its feet on their footfalls by IK (no slide), its hips down as far as the legs need
    and swaying over the foot it stands on, its upper body swinging (`upper_body`). `extra(t)` -> {bone: turn} adds
    to the pose (a head turned, a hand raised). Returns {frame: (root (x, y), phase)}."""
    import bpy

    from lib import vrm

    yaw = math.atan2(gait._d()[1], gait._d()[0])
    root = ch.root
    root.rotation_euler = (0.0, 0.0, yaw)
    ankle = float(ch.rest("rightFoot")[2])
    ball = abs(float((ch.rest("rightToes") - ch.rest("rightFoot"))[1])) if ch.has("rightToes") else 0.12
    hip_l, hip_r = ch.rest("leftUpperLeg"), ch.rest("rightUpperLeg")
    leg = 0.985 * (np.linalg.norm(hip_l - ch.rest("leftLowerLeg")) + np.linalg.norm(ch.rest("leftLowerLeg") - ch.rest("leftFoot")))
    left = gait.left_axis()
    fwd = gait._d()

    def to_char(w, r):
        """A world point as the character's frame (x its left, y its back) with its root at r (x, y)."""
        v = np.asarray(w, float) - np.array([*r, 0.0])
        return np.array([v[:2] @ left, -(v[:2] @ fwd), v[2]])

    out = {}
    # the IK set up once (at the first frame's places), then its handles keyed frame by frame
    t = frames[0] / fps
    r = gait.root(t)
    for side in ("left", "right"):
        a, _ = gait.foot(side, t, ankle, ball)
        vrm.reach(ch, f"{side}Foot", to_char(a, r), pole=to_char(a + np.array([*fwd * 0.8, 0.5]), r))
        vrm.hold(ch, f"{side}Foot", (0.0, 0.0, 0.0))
    for f in frames:
        t = f / fps
        r = gait.root(t)
        ph = gait.phase(t)
        if gait.first == "left":
            ph = (ph + 0.5) % 1.0
        root.location = (r[0], r[1], 0.0)
        root.keyframe_insert("location", frame=f)
        ankles, pitches = {}, {}
        for side in ("left", "right"):
            ankles[side], pitches[side] = gait.foot(side, t, ankle, ball)
        sway = -swing["sway"] * math.sin(2 * math.pi * ph)
        hips_xy = np.array([sway, 0.0])
        joints = [np.array([*(r + left * (hip_l[0] + sway)), hip_l[2]]), np.array([*(r + left * (hip_r[0] + sway)), hip_r[2]])]
        drop = hips_drop(np.array(joints), [ankles["left"], ankles["right"]], leg) + swing["sink"]
        pose = upper_body(ph, lean=lean, swing=swing)
        for side in ("left", "right"):
            pose[f"{side}Toes"] = (-max(0.0, pitches[side]) * 0.9, 0.0, 0.0)
        if extra is not None:
            pose.update(extra(t))
        vrm.pose(ch, pose, hips=(hips_xy[0], 0.0, -drop), frame=f)
        for side in ("left", "right"):
            a = ankles[side]
            tgt = ch.handles[f"{side}Foot-target"]
            tgt.location = ch.to_armature(to_char(a, r))
            tgt.keyframe_insert("location", frame=f)
            pole = ch.handles[f"{side}Foot-pole"]
            pole.location = ch.to_armature(to_char(a + np.array([*fwd * 0.8, 0.5]), r))
            pole.keyframe_insert("location", frame=f)
            hold = ch.handles[f"{side}Foot-hold"]
            vrm.hold(ch, f"{side}Foot", (pitches[side], 0.0, 0.0))
            hold.keyframe_insert("rotation_quaternion", frame=f)
        out[f] = (tuple(r), ph)
    bpy.context.view_layer.update()
    return out


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
        r0 = spread * rng.uniform(0.6, 1.1)
        p0 = np.array([x0 + math.cos(a) * r0, y0 + math.sin(a) * r0 * 0.8, z0 + 0.01])
        up = rng.uniform(*speed)
        out_v = up * rng.uniform(0.35, 0.9)
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
