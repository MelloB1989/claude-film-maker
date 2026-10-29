"""The end of the jetty, where Tsuru sits smoking and Shinza comes to her: the staging the shots there share (ferry,
ask, refuse; demand, tap, look and draw may import it), so each puts the two of them, her seat and the rain in the
same places, and builds the world, the 3D cast, the camera and the compositing the same way as shots/standoff.py.

World axes are rf/sets.py's: the jetty along x (the bank at -x, its end at +x), its deck's top at z 0, the river and the
moored boat behind it toward +y. Tsuru sits on a low crate near the jetty's end, turned to the river with the boat
across the water before her and the post at x 5 by her left hand (where she taps her pipe out); Shinza stops at his
mark a couple of paces behind her left shoulder, on the jetty's middle.
"""
from __future__ import annotations

import math

import numpy as np

# Tsuru on her crate: where (x, y) and which way she faces (degrees from +x toward +y)
SEAT = dict(at=(5.55, 0.42), heading=72.0)
CRATE = (0.46, 0.36, 0.42)            # the crate she sits on (x, y, height): rf/vroid_tsuru.py SEAT high
# Shinza's mark behind her, and which way he faces when he stops there (toward her)
MARK = dict(at=(4.0, -0.22), heading=23.0)
# the 3D cast's outline in frame heights, their keys' softness (shots/standoff.py's)
OUTLINE = 0.0018
KEY_ANGLE = 5.0
SMOKE = (0.6, 0.63, 0.68)             # the pipe's smoke, linear: a pale cool grey in the rain light
# her pole laid along the moored boat's floor: its foot (x, y, z) and which way it lies (degrees from +x toward +y)
POLE_LAID = dict(foot=(4.1, 2.05, -0.12), heading=2.0)


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def lerp(a, b, k):
    return tuple(x + (y - x) * k for x, y in zip(a, b))


def heading_vec(deg: float) -> np.ndarray:
    a = math.radians(deg)
    return np.array((math.cos(a), math.sin(a), 0.0))


def walk_path(t: float, start, stop, t0: float, t1: float, settle: float = 0.25) -> tuple[np.ndarray, float]:
    """Where a walker is at t going from `start` to `stop` (x, y) between t0 and t1 (s), and how far through his
    stride cycle he is: at an even pace with an ease in over his first step and a settle into the stop (`settle`: the
    share of the walk spent slowing). Pure."""
    start, stop = np.asarray(start, float), np.asarray(stop, float)
    u = min(1.0, max(0.0, (t - t0) / max(t1 - t0, 1e-6)))
    # even speed, eased at both ends: a smoothed ramp whose ends take `settle` of the time each
    s = settle

    def ramp(x):
        if x < s:
            return x * x / (2 * s)
        if x > 1 - s:
            return 1 - (1 - x) ** 2 / (2 * s)
        return x - s / 2

    k = ramp(u) / ramp(1.0)
    return start + (stop - start) * k, k


# ---------------------------------------------------------------------------------------------------- Blender

def standoff():
    """shots/standoff.py as a module: the cast's paint (TONES3D) is the film's, kept in one place."""
    import importlib.util
    from pathlib import Path

    p = Path(__file__).resolve().parents[1] / "shots" / "standoff.py"
    spec = importlib.util.spec_from_file_location("shots.standoff", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def world(ctx, *, rain_box, clear: float = 1.2, near: float = 3.5, deck_splashes=None, river_splashes=None) -> dict:
    """The crossing in the rain: the set (rf/sets.py), the world's dim ambient and the sun on the set, Tsuru's crate,
    the rain (as dense as the look schedule has it at the shot's start) in `rain_box`, splashes on the deck and the
    river. Returns {crossing, look, sun, rain, cast (the cast's collection), state}."""
    import bpy

    from lib import toon

    from . import sets

    scene = ctx.scene
    scene.render.use_motion_blur = False
    scene.eevee.use_shadows = True
    scene.eevee.use_raytracing = True
    scene.view_settings.view_transform = "Standard"
    state = ctx.look_at(ctx.f0)
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (*state.light.ambient, 1)

    look = toon.Look(fog=sets.SKY, fog_near=18.0, fog_far=480.0, fog_max=0.9, fog_power=0.65)
    crossing = sets.crossing(look)
    sun = bpy.data.lights.new("key", "SUN")
    sun.angle = math.radians(3)
    sun.energy = 4.2 * state.light.key_strength
    key = bpy.data.objects.new("key", sun)
    toon.collection("world-light").objects.link(key)
    from mathutils import Vector

    key.rotation_euler = Vector((0.55, 0.45, -0.7)).to_track_quat("-Z", "Y").to_euler()

    # her crate: a few planks nailed into a box, dark with the rain
    from lib import shapes

    cx, cy = SEAT["at"]
    hdg = math.radians(SEAT["heading"])
    cw, cd, ch = CRATE
    m = crossing["materials"]
    for k, (dz, h) in enumerate(((0.0, 0.13), (0.14, 0.13), (0.28, 0.12))):
        shapes.box(f"crate-slat{k}", (cx, cy, dz + h / 2), (cw, cd, h - 0.01), material=m["plank"],
                   coll=crossing["near"], rot_z=hdg + 0.06)
    shapes.box("crate-lid", (cx, cy, ch - 0.012), (cw + 0.02, cd + 0.02, 0.024), material=m["post"],
               coll=crossing["near"], rot_z=hdg + 0.06)

    r = state.rain
    rain = toon.rain("rain", rain_box[0], rain_box[1], count=max(1, r.drops), speed=r.speed, wind=r.wind,
                     length=r.length, width=r.width, color=r.color, alpha=r.alpha, seed=4, near=near, clear=clear)
    if deck_splashes is not None:
        toon.splashes("splash-deck", *deck_splashes, count=round(240 * r.density), size=0.08, seed=5)
    if river_splashes is not None:
        toon.splashes("splash-river", *river_splashes, count=round(380 * r.density), size=0.11, alpha=0.45, seed=9)
    cast = toon.collection("cast")
    return {"crossing": crossing, "look": look, "sun": sun, "key": key, "rain": rain, "cast": cast, "state": state}


def cast_member(w: dict, name: str, *, at, heading: float, key_from, **variant) -> dict:
    """One of the 3D cast (rf/vroid_cast.py with `variant`) at `at` facing `heading` degrees, painted as the film's
    cast is (shots/standoff.py TONES3D) and lit by a key of its own from `key_from` (world)."""
    import bpy

    from lib import toon, toon3d, vrm

    from . import vroid_cast

    st = standoff()
    cast_look = toon.Look(fog=w["look"].fog, fog_near=w["look"].fog_near, fog_far=w["look"].fog_far,
                          fog_max=w["look"].fog_max, fog_power=w["look"].fog_power)
    built = getattr(vroid_cast, name)(w["cast"], cast_look, **variant)
    built["root"].location = (*at, 0.0)
    built["root"].rotation_euler = (0.0, 0.0, math.radians(heading))
    bpy.context.view_layer.update()
    key = toon3d.key(f"{name}-key", [built["root"], *built["root"].children_recursive], key_from, coll=w["cast"],
                     angle=KEY_ANGLE)
    tones = {p: toon3d.Tone(**{**kw, **st.TONES3D_OF.get(name, {}).get(p, {})}) for p, kw in st.TONES3D.items()}
    vrm.anime(built["vrm"], tones, key)
    vrm.smooth(built["vrm"])
    built["key"] = key
    return built


def pole_in_boat(tsuru) -> None:
    """Her pole (left lying at her right by the builder, carried by her root) laid along the moored boat, where she
    lifts it from when she rises."""
    import bpy
    from mathutils import Matrix, Vector

    bpy.context.view_layer.update()
    pole = tsuru["parts"]["pole"][0]
    pole.parent = None
    pole.matrix_world = (Matrix.Translation(Vector(POLE_LAID["foot"]))
                         @ Matrix.Rotation(math.radians(POLE_LAID["heading"]), 4, "Z")
                         @ Matrix.Rotation(math.radians(90.0), 4, "Y"))


def rain_in_cast(w: dict):
    """The rain again in the cast's layer (the same drops: only those over a figure pass the compositor's depth
    test), so drops in front of a face stay in front of it."""
    r = w["rain"].copy()
    r.name = "rain-cast"
    w["cast"].objects.link(r)
    return r


def camera(ctx, lens: float = 35.0, fstop: float = 4.0):
    """The engine's camera aimed at an empty by TRACK_TO, its focus on that empty. Returns (camera, aim)."""
    import bpy

    from lib import rig

    cam = rig.engine_camera("camera", fstop=fstop, size=ctx.size)
    cam.data.lens = lens
    cam.data.clip_end = 3000.0
    ctx.scene.camera = cam
    target = bpy.data.objects.new("aim", None)
    ctx.scene.collection.objects.link(target)
    c = cam.constraints.new("TRACK_TO")
    c.target = target
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    cam.data.dof.use_dof = True
    return cam, target


def key_camera(ctx, cam, target, at, *, focus=None) -> dict:
    """Key the camera on every frame of the shot from `at(t)` (s into the shot) -> (location, aim, lens, f-stop);
    `focus(t)` a point to focus on (default the aim). Returns {frame: (location, lens)} (the outlines are keyed from
    it)."""
    import bpy
    from mathutils import Vector

    focus_ob = bpy.data.objects.new("focus", None)
    ctx.scene.collection.objects.link(focus_ob)
    cam.data.dof.focus_object = focus_ob
    where = {}
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        loc, aim, lens, fstop = at(t)
        cam.location = loc
        target.location = aim
        focus_ob.location = focus(t) if focus is not None else aim
        cam.data.lens = lens
        cam.data.dof.aperture_fstop = fstop
        cam.keyframe_insert("location", frame=f)
        target.keyframe_insert("location", frame=f)
        focus_ob.keyframe_insert("location", frame=f)
        cam.data.keyframe_insert("lens", frame=f)
        cam.data.dof.keyframe_insert("aperture_fstop", frame=f)
        where[f] = (Vector(loc), lens)
    return where


def outlines(ctx, actors: dict, where: dict) -> None:
    """Every frame, each character's outline a width on screen (OUTLINE) from the camera's distance and lens."""
    from lib import vrm

    for f, (loc, lens) in where.items():
        for built in actors.values():
            d = (loc - built["vrm"].face()).length
            vrm.key_outline(built["vrm"], vrm.outline_width(OUTLINE, d, lens), f)


def nudge(ch, turns: dict, frame: int) -> None:
    """Turn bones on from where their pose has them ({bone: (x, y, z) degrees about the character's axes}), keyed at
    `frame`: a head lifted, a breath in the chest, on top of a builder's pose."""
    from mathutils import Matrix

    from lib import vrm

    for bone, turn in turns.items():
        pb = ch.bone(bone)
        base = pb.get("_base")
        if base is None:
            pb.rotation_mode = "QUATERNION"
            pb["_base"] = base = list(pb.rotation_quaternion)
        rest = np.array(ch.armature.data.bones[pb.name].matrix_local.to_3x3())
        from mathutils import Quaternion

        q = Matrix(vrm.local_rotation(rest, ch.frame, turn).tolist()).to_quaternion() @ Quaternion(list(base))
        pb.rotation_quaternion = q
        pb.keyframe_insert("rotation_quaternion", frame=frame)


def breathe(ctx, ch, *, rate: float = 0.22, depth: float = 1.4, phase: float = 0.0, extra=None) -> None:
    """A slow breath in the chest and a little in the neck, every other frame over the shot, plus `extra(t)` ->
    {bone: turn} (a look, a nod) added on top."""
    for f in range(ctx.f0 - 1, ctx.f1 + 2, 2):
        t = (f - ctx.f0) / ctx.fps
        b = math.sin(2 * math.pi * rate * t + phase)
        turns = {"upperChest": (-depth * b, 0.0, 0.0), "neck": (0.4 * depth * b, 0.0, 0.0)}
        for bone, (x, y, z) in (extra(t) if extra else {}).items():
            bx, by, bz = turns.get(bone, (0.0, 0.0, 0.0))
            turns[bone] = (bx + x, by + y, bz + z)
        nudge(ch, turns, f)


def bowl(built):
    """(the pipe's bowl, the top of its mouth in the bowl's own axes): where the smoke leaves."""
    from mathutils import Vector

    ob = built["parts"]["pipe"][-1]
    corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    top = sum(corners, Vector()) / 8
    top.z = max(c.z for c in corners)
    return ob, tuple(ob.matrix_world.inverted() @ top)


def mouth(built, forward: float = 0.07, down: float = 0.062):
    """A function of the film frame giving where the character's lips are (the head's bone carries a point found at
    the posed face: below the eyes, out in front)."""
    from mathutils import Vector

    ch = built["vrm"]
    pb = ch.bone("head")
    m0 = ch.armature.matrix_world @ pb.matrix
    face = ch.face()
    look = Vector(ch.world((0.0, -1.0, 0.0))) - Vector(ch.world((0.0, 0.0, 0.0)))
    look.z = 0.0
    look.normalize()
    p = face + look * forward - Vector((0.0, 0.0, down))
    local = m0.inverted() @ p

    def at(_frame):
        return np.array(ch.armature.matrix_world @ ch.bone("head").matrix @ local)
    return at


def hold_constant(*owners) -> None:
    from lib import toon

    for owner in owners:
        ad = getattr(owner, "animation_data", None)
        if ad is None or ad.action is None:
            continue
        for fc in toon._fcurves(ad.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


def composite(ctx, w: dict, setup) -> None:
    """The cast laid over the world through the satsuei stage (lib/satsuei.py), its base from the look schedule on
    every frame and `setup(t)` -> the shot's own Look fields (rims, para) on top."""
    from lib import satsuei

    comp = satsuei.setup(ctx.scene, w["cast"])
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        comp.key(f, ctx.look_at(f).look(**setup(t)))
    comp.hold()


# ---------------------------------------------------------------------------------------------------- acting

def footfalls(distance: float, stride: float, width: float) -> dict:
    """Where each foot lands along a straight walk `distance` long, as (along, across) pairs: the right foot leads
    from feet together, each step `stride` long (shortened so the last lands even), the left foot `width` to the left
    and the right to the right, and both together at the end. Pure."""
    n = max(1, round(distance / stride))
    step = distance / n
    out = {"left": [(0.0, width)], "right": [(0.0, -width)]}
    for i in range(1, n + 1):
        out["right" if i % 2 else "left"].append((min(distance, i * step), width if i % 2 == 0 else -width))
    last = "right" if n % 2 == 0 else "left"     # the foot that did not take the last step comes alongside
    if out[last][-1][0] < distance:
        out[last].append((distance, out[last][-1][1]))
    return out


def foot_at(prints: list, d: float, stride: float, lift: float = 0.09, swing: float = 0.8) -> tuple[float, float, float]:
    """A foot's (along, across, height) when the body has come `d` along its walk: planted on a footfall until the
    body is past it, swinging to its next over `swing` strides of the body's travel centred between the two. Pure."""
    for (a0, c0), (a1, c1) in zip(prints, prints[1:]):
        mid = (a0 + a1) / 2
        span = min(swing * stride, a1 - a0)
        lo, hi = mid - span / 2, mid + span / 2
        if d < lo:
            return a0, c0, 0.0
        if d <= hi:
            u = (d - lo) / max(hi - lo, 1e-6)
            k = ease(u)
            return a0 + (a1 - a0) * k, c0 + (c1 - c0) * k, lift * math.sin(math.pi * u)
    a, c = prints[-1]
    return a, c, 0.0


def syllables(t: float, start: float, end: float, rate: float = 6.0) -> float:
    """How open a speaking mouth is at t (0..1) through a line from `start` to `end` (s): a beat of opening and
    closing `rate` times a second, its height varying from syllable to syllable, closed before and after. Pure."""
    if t <= start or t >= end:
        return 0.0
    u = (t - start) * rate
    beat = max(0.0, math.sin(math.pi * (u % 1.0)))
    height = 0.55 + 0.45 * abs(math.sin(1.7 * math.floor(u) + 0.4))
    edge = min(1.0, (t - start) / 0.06, (end - t) / 0.1)
    return beat * height * edge


def talk(ch, face: dict, t: float, lines, frame: int, amount: float = 0.7) -> None:
    """Key the face (the builder's `face` weights) with the mouth moving through any of `lines` [(start, end) s] at
    t: VRM's vowels (aa, oh, ih), where the model has them."""
    from lib import vrm

    w = dict(face)
    o = max((syllables(t, a, b) for a, b in lines), default=0.0) * amount
    if o > 0:
        vowels = [v for v in ("aa", "oh", "ih") if v in ch.expressions]
        if vowels:
            v = vowels[int(t * 6.0) % len(vowels)]
            w[v] = w.get(v, 0.0) + o
    vrm.express(ch, w, frame=frame)


def walk(ctx, built, start, stop, t0: float, t1: float, *, stride: float = 0.72, lift: float = 0.09,
         bob: float = 0.025, lean: float = 4.0) -> None:
    """Key a character's walk from `start` to `stop` (x, y, world, on the deck) between t0 and t1 (s into the shot;
    t0 may be before it: he is already walking when it opens): the root along the line (facing along it), each foot
    planted on its footfalls and swinging between them (its IK target keyed), the body bobbing down onto each step
    and leaning into the walk, settling upright at the stop. A blocking walk until the anim module's cycles land."""
    from mathutils import Vector

    ch = built["vrm"]
    root = built["root"]
    start, stop = np.asarray(start, float), np.asarray(stop, float)
    way = stop - start
    dist = float(np.linalg.norm(way))
    hdg = math.atan2(way[1], way[0])
    fwd = np.array((math.cos(hdg), math.sin(hdg), 0.0))
    left = np.array((-fwd[1], fwd[0], 0.0))
    # each foot's planted target in the character's frame (x its left, y its back, z up) as the builder left it
    rest = {}
    for side in ("left", "right"):
        e = ch.handles[f"{side}Foot-target"]
        rest[side] = ch.frame.T @ np.array(e.location) * ch.scale
    width = abs(rest["left"][0] - rest["right"][0]) / 2
    prints = footfalls(dist, stride, width)
    root.rotation_euler = (0.0, 0.0, hdg)
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        p, k = walk_path(t, start, stop, t0, t1)
        d = k * dist
        moving = 0.0 < k < 1.0
        # down onto each footfall: twice a stride cycle
        phase = d / (dist / max(1, round(dist / stride)))
        dz = -bob * (0.5 - 0.5 * math.cos(2 * math.pi * phase)) if moving else 0.0
        root.location = Vector((p[0], p[1], dz))
        root.keyframe_insert("location", frame=f)
        root.keyframe_insert("rotation_euler", frame=f)
        for side in ("left", "right"):
            a, c, h = foot_at(prints[side], d, stride, lift)
            world = start + fwd * a + left * c
            rel = world - np.array((p[0], p[1], 0.0))
            # world to the character's frame: its front (-y) is the root's +x, its left (+x) the root's +y
            along, across = float(rel @ fwd), float(rel @ left)
            q = np.array((across, -along, rest[side][2] + h - dz))
            e = ch.handles[f"{side}Foot-target"]
            e.location = ch.to_armature(q)
            e.keyframe_insert("location", frame=f)
        go = math.sin(math.pi * min(1.0, max(0.0, k * 1.0))) if moving else 0.0
        nudge(ch, {"spine": (lean * go, 0.0, 0.0)}, f)
