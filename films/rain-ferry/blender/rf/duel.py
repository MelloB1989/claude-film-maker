"""What the duel's last four shots share (shots/charge.py, flash.py, after.py, fall.py): the crossing in the rain, the
3D VRoid cast painted as the standoff paints it (shots/standoff.py's tones and keys), what the clash does to their
props, their keyed poses, the light and the compositing, all read from the film's look schedule (ctx.look_at).

The blocking (rf/sets.py's axes: the jetty along x, the deck's top at z 0, the river behind at +y, the camera's side
-y). In the standoff Shinza stands at x -2.3 facing +x and Tsuru at x +2.35 facing -x. He charges along the jetty;
they meet at CLASH, pass through each other and stand back to back (END): him further out toward the jetty's end
facing +x, her nearer the bank facing -x.

The props the clash changes:
- his katana breaks BREAK of the way along the blade: `broken_sword` swaps its blade for the stub (in his hand) and
  the half blade, a prop of its own that the shots fly.
- his headband is cut: `loose_headband` lets it go from his head (the band, its knot and tails as one object) for a
  shot to slide off.
- Tsuru's ferry pole hides a straight blade (a shikomizue): `shikomizue` splits it into the sheath (the pole below
  SPLIT) and the hilt above it with the blade under it, drawn (`draw`, metres out of the sheath) or sheathed.

The poses are keyed whole (`Pose`, `apply`, `key`): where the character stands and turns, the hips, the bones' turns,
the hands (on a hilt, through `sword_hands`, or reaching) and the feet, and the face. Generic keyed posing belongs to
the core's character animation (blender/lib/vrm_anim.py) when it lands; this is the duel's own until then.
"""
from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

STANDOFF = {"shinza": (-2.3, 0.0), "tsuru": (2.35, 0.05)}
CLASH = 0.7                       # x where the blades meet
END = {"shinza": (1.95, 0.08), "tsuru": (-0.3, -0.06)}
BREAK = 0.4                       # where along his blade (from the guard) it breaks
SPLIT = 1.5                       # where Tsuru's pole parts, hilt above, sheath below (m up the pole)
TS_BLADE = 0.62                   # her blade's length under the hilt
OUTLINE = 0.0018                  # the 3D cast's outline, in frame heights (as the standoff's)


def standoff():
    """shots/standoff.py, for its painting of the 3D cast (TONES3D, TONES3D_OF, KEY3D_ANGLE, LOOKS...)."""
    path = Path(__file__).resolve().parents[1] / "shots" / "standoff.py"
    spec = importlib.util.spec_from_file_location("shots.standoff", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def lerp(a, b, k):
    return tuple(float(x) + (float(y) - float(x)) * k for x, y in zip(a, b))


def keys_at(keys, t: float, interp=ease):
    """A value from [(t, value)] keys at time t: eased between keys, held outside them. Values are numbers or
    tuples."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            k = interp((t - t0) / max(1e-9, t1 - t0))
            if isinstance(v0, (int, float)):
                return v0 + (v1 - v0) * k
            return lerp(v0, v1, k)
    return keys[-1][1]


# ---------------------------------------------------------------------------------------------------- the world

def world(ctx, *, rain_box=((-8.0, -6.0, -0.6), (8.0, 10.0, 5.5)), clear: float = 1.0, near: float = 3.5,
          splashes: bool = True, motion_blur: float = 0.0, look_far: float = 480.0) -> dict:
    """The crossing in the shot's rain and light (ctx.look_at(ctx.f0)): the scene set up as the standoff's, the set,
    the near set's ink, the world's key, the rain (if it falls) and its splashes. `motion_blur`: a shutter (0 off).
    Returns {look, crossing, ink, key, sun, rain, splashes, state}."""
    import bpy
    from mathutils import Vector

    from lib import toon
    from rf import sets

    scene = ctx.scene
    s = ctx.look_at(ctx.f0)
    scene.render.use_motion_blur = motion_blur > 0
    if motion_blur > 0:
        scene.render.motion_blur_shutter = motion_blur
    scene.eevee.use_shadows = True
    scene.eevee.use_raytracing = True
    scene.view_settings.view_transform = "Standard"
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (*s.light.ambient, 1)

    look = toon.Look(fog=s.light.fog, fog_near=18.0, fog_far=look_far, fog_max=0.9, fog_power=0.65)
    crossing = sets.crossing(look)
    ink = toon.ink("ink-near", crossing["near"], radius=0.0042, crease=150)

    sun = bpy.data.lights.new("key", "SUN")
    sun.angle = math.radians(3)
    sun.color = s.light.key
    sun.energy = 4.2 * s.light.key_strength
    key = bpy.data.objects.new("key", sun)
    scene.collection.objects.link(key)
    key.rotation_euler = Vector((0.55, 0.45, -0.7)).to_track_quat("-Z", "Y").to_euler()

    r = s.rain
    rain = None
    drops = r.drops or 5200      # a shot whose rain starts stopped still has its drops, hanging
    if r.alpha > 0:
        rain = toon.rain("rain", rain_box[0], rain_box[1], count=drops, speed=r.speed or 9.5, wind=r.wind,
                         length=r.length, width=r.width, color=r.color, alpha=r.alpha, seed=4, near=near, clear=clear)
    spl = []
    if splashes:
        spl.append(toon.splashes("splash-deck", (sets.SPAN[0], -sets.HALF + 0.05, 0.004),
                                 (sets.SPAN[1], sets.HALF - 0.05, 0.004), count=240, size=0.08, seed=5))
        spl.append(toon.splashes("splash-river", (-7.5, -3.6, sets.WATER_Z + 0.002), (7.5, -1.15, sets.WATER_Z + 0.002),
                                 count=340, size=0.11, alpha=0.45, seed=9))
    return {"look": look, "crossing": crossing, "ink": ink, "key": key, "sun": sun, "rain": rain, "splashes": spl,
            "state": s}


def rain_clock(ctx, obs, speed_at) -> None:
    """Run the rain (and its splashes) on a clock of its own: `speed_at(t)` (0..1 of its speed, t seconds into the
    shot) integrated frame by frame, so the drops slow to a stop or start falling again where they hang (keying the
    rain's speed itself would jump them)."""
    from lib import fx_impact

    clock, t = {}, 0.0
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        clock[f] = (ctx.f0 - 1) / ctx.fps + t
        t += speed_at((f - ctx.f0) / ctx.fps) / ctx.fps
    for ob in obs:
        if ob is not None:
            fx_impact.clock(ob, clock)


# ---------------------------------------------------------------------------------------------------- the cast

def cast(ctx, w: dict, names=("shinza", "tsuru")) -> dict:
    """The 3D cast in the shot, painted as the standoff paints them: each built (rf/vroid_cast.py), lit by a key of
    its own, toned, smoothed. Returns {name: {built..., "key": light}} and "coll" (the cast's collection) and
    "rain" (a copy of the rain in the cast's layer, so the drops in front of a face stay in front of it)."""
    from lib import toon, toon3d, vrm
    from rf import vroid_cast

    so = standoff()
    coll = toon.collection("cast")
    look = w["look"]
    cast_look = toon.Look(fog=look.fog, fog_near=look.fog_near, fog_far=look.fog_far, fog_max=look.fog_max,
                          fog_power=look.fog_power)
    toon.move_to(w["key"], toon.collection("world-light"))
    out = {"coll": coll}
    for name in names:
        built = getattr(vroid_cast, name)(coll, cast_look)
        k = toon3d.key(f"{name}-key", [built["root"], *built["root"].children_recursive], so.KEY3D["wide"][name],
                       coll=coll, angle=so.KEY3D_ANGLE)
        tones = {p: toon3d.Tone(**{**kw, **so.TONES3D_OF.get(name, {}).get(p, {})}) for p, kw in so.TONES3D.items()}
        vrm.anime(built["vrm"], tones, k)
        vrm.smooth(built["vrm"])
        built["key"] = k
        out[name] = built
    if w.get("rain") is not None:
        rc = w["rain"].copy()
        rc.name = "rain-cast"
        coll.objects.link(rc)
        out["rain"] = rc
    return out


def outlines(ctx, actors: dict, cam_at, lens_at) -> None:
    """Key each character's outline to OUTLINE of the frame's height on every frame (cam_at(f), lens_at(f))."""
    from lib import vrm

    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        for name in ("shinza", "tsuru"):
            if name in actors:
                ch = actors[name]["vrm"]
                d = (np.asarray(cam_at(f)) - np.asarray(ch.face())).dot(np.asarray(cam_at(f)) - np.asarray(ch.face()))
                vrm.key_outline(ch, vrm.outline_width(OUTLINE, math.sqrt(d), lens_at(f)), f)


# ---------------------------------------------------------------------------------------------------- the props

def _sword_parts(actor):
    """His katana's objects by part (blade, habaki, tsuba, tsuka, kashira)."""
    return {ob.name.rsplit("-", 1)[-1]: ob for ob in actor["props"]}


def broken_sword(actor, m=None) -> dict:
    """His blade broken BREAK of the way from the guard: the whole blade hidden, the stub in its place (carried by
    his hand) and the half blade a free prop at the break, as it is in the current pose. Returns {"stub", "half",
    "whole", "tip" (the half's far end, world), "break" (world)}."""
    import bpy

    from lib import shapes

    parts = _sword_parts(actor)
    whole = parts["blade"]
    bpy.context.view_layer.update()
    me = whole.data
    co = np.array([whole.matrix_world @ v.co for v in me.vertices])
    # the blade's centre line from the loft's rings (n=4 a ring, 16 rings from the guard)
    rings = co.reshape(16, -1, 3).mean(axis=1)
    mat = whole.data.materials[0]
    seg = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(rings, axis=0), axis=1))]
    cut = BREAK * seg[-1]
    at = np.array([np.interp(cut, seg, rings[:, i]) for i in range(3)])
    j = int(np.searchsorted(seg, cut))
    side = co.reshape(16, -1, 3)[0][0] - rings[0]
    side = side / np.linalg.norm(side)
    up = tuple(np.cross(rings[1] - rings[0], side))
    fs = np.linspace(0, 1, 16)
    width = np.where(fs < 0.97, 0.016 - 0.004 * fs, 0.002)
    thick = np.where(fs < 0.97, 0.0036 - 0.0012 * fs, 0.0008)
    w_at = float(np.interp(cut, seg, width))
    t_at = float(np.interp(cut, seg, thick))
    # a jagged break: the stub's end and the half's start cut on a slant
    lean = (rings[-1] - rings[0]) / seg[-1] * 0.012
    stub_path = [*rings[:j], at + lean]
    stub = shapes.loft(f"{whole.name}-stub", stub_path, [*width[:j], w_at], [*thick[:j], t_at], material=mat,
                       coll=whole.users_collection[0], n=4, power=1.0, subsurf=0, up=up)
    half_path = [at - lean, *rings[j:]]
    half = shapes.loft(f"{whole.name}-half", half_path, [w_at, *width[j:]], [t_at, *thick[j:]], material=mat,
                       coll=whole.users_collection[0], n=4, power=1.0, subsurf=0, up=up)
    stub.parent, stub.parent_type, stub.parent_bone = whole.parent, whole.parent_type, whole.parent_bone
    stub.matrix_parent_inverse = whole.matrix_parent_inverse.copy()
    stub.matrix_world = whole.matrix_world.copy()
    # the half pivots on its own middle, for a shot to fly it
    mid = (at + rings[-1]) / 2
    _origin_to(half, mid)
    return {"stub": stub, "half": half, "whole": whole, "tip": rings[-1], "break": at}


def _origin_to(ob, point) -> None:
    """Move an object's origin to a world point, its mesh staying where it is."""
    from mathutils import Matrix, Vector

    p = ob.matrix_world.inverted() @ Vector(point)
    ob.data.transform(Matrix.Translation(-p))
    ob.matrix_world = ob.matrix_world @ Matrix.Translation(p)


def loose_headband(actor):
    """His headband (band, knot and tails) as one object let go of his head, where it is in the current pose, its
    origin at the band's centre: a shot slides it off. Returns the object."""
    import bpy

    ch = actor["vrm"]
    parts = [ob for ob in ch.coll.objects if ob.name.startswith(f"{ch.name}-band")]
    if not parts:
        raise RuntimeError(f"duel: {ch.name} has no headband")
    bpy.context.view_layer.update()
    for ob in parts:
        world = ob.matrix_world.copy()
        ob.parent = None
        ob.matrix_world = world
    with bpy.context.temp_override(selected_editable_objects=parts, active_object=parts[0]):
        bpy.ops.object.join()
    band = parts[0]
    bpy.context.view_layer.update()
    co = np.array([band.matrix_world @ v.co for v in band.data.vertices])
    _origin_to(band, co.mean(axis=0))
    band.name = f"{ch.name}-band-loose"
    return band


def shikomizue(actor, m) -> dict:
    """Her pole parted at SPLIT: the builder's pole hidden, the sheath (below) standing where it stood, the hilt (above,
    with the cord wound round it) and the straight blade under it as one object whose origin is the parting, so
    lifting it `d` metres up the pole draws that much of the blade. Returns {"sheath", "hilt", "axis" (unit, up the
    pole), "foot", "top"}."""
    import bpy
    from mathutils import Vector

    from lib import shapes

    poles = [ob for ob in actor["props"] if "-pole" in ob.name]
    pole = next(ob for ob in poles if ob.name.endswith("-pole"))
    bpy.context.view_layer.update()
    co = np.array([pole.matrix_world @ v.co for v in pole.data.vertices])
    axis = np.array([0.0, 0.0, 1.0])
    foot = co[co[:, 2].argmin()].copy()
    foot[:2] = co[:, :2].mean(axis=0)
    top = co[:, 2].max()
    coll = pole.users_collection[0]
    name = actor["vrm"].name
    sheath = [ob for ob in poles if (ob.matrix_world.translation.z if ob is not pole else 0) < SPLIT]
    hilt_parts = [ob for ob in poles if ob is not pole and ob not in sheath]
    pole.hide_render = pole.hide_viewport = True
    r = 0.022
    base = foot + axis * (SPLIT - foot[2])
    low = shapes.cylinder(f"{name}-sheath", tuple(foot), tuple(base - axis * 0.002), r, material=pole.data.materials[0],
                          coll=coll, n=12)
    hi = shapes.cylinder(f"{name}-hilt", tuple(base + axis * 0.002), (foot[0], foot[1], top), r,
                         material=pole.data.materials[0], coll=coll, n=12)
    steel = m["steel"]
    fs = np.linspace(0, 1, 8)
    path = [base - axis * TS_BLADE * f for f in fs]
    blade = shapes.loft(f"{name}-blade", path, np.where(fs < 0.9, 0.011, 0.002), np.where(fs < 0.9, 0.0025, 0.0006),
                        material=steel, coll=coll, n=4, power=1.0, subsurf=0, up=(1.0, 0.0, 0.0))
    for ob in (hi, blade, *hilt_parts):
        w = ob.matrix_world.copy()
        ob.parent = None
        ob.matrix_world = w
    with bpy.context.temp_override(selected_editable_objects=[hi, blade, *hilt_parts], active_object=hi):
        bpy.ops.object.join()
    _origin_to(hi, base)
    for ob in (low, *sheath):
        if ob is pole:
            continue
        if ob is not low:
            continue
    # the sheath's nodes stay as the builder made them (carried by her root); the new sheath and hilt follow it too
    root = actor["root"]
    for ob in (low, hi):
        w = ob.matrix_world.copy()
        ob.parent = root
        ob.matrix_world = w
    hi["rest"] = tuple(hi.location)
    return {"sheath": low, "hilt": hi, "axis": axis, "foot": foot, "top": top, "base": Vector(base)}


# ---------------------------------------------------------------------------------------------------- poses

@dataclass
class Pose:
    """A whole pose: where the character stands (x, y on the deck, `lift` up off it) facing `yaw` (radians, 0 is +x),
    the hips' offset and the bones' turns (lib/vrm.py's frame), the hands ({side: ("grasp", point, along, palm, pole)
    or ("reach", wrist, pole) with an optional hand turn (degrees) as a fourth}), the feet ({side: (ankle, knee's
    pole, turn)}) and the face ({expression: weight})."""
    at: tuple = (0.0, 0.0)
    yaw: float = 0.0
    lift: float = 0.0
    hips: tuple = (0.0, 0.0, 0.0)
    turns: dict = field(default_factory=dict)
    hands: dict = field(default_factory=dict)
    feet: dict = field(default_factory=dict)
    face: dict | None = None


def sword_hands(pommel, hilt_dir, flat, grips: dict, poles: dict, rest_hilt, rest_flat, rest_palms: dict) -> dict:
    """Both hands on a hilt from `pommel` along `hilt_dir` (character's frame), its flat facing `flat`: each hand
    `grips[side]` up the hilt, its palm turned with the hilt from how it held it at rest (rest_hilt, rest_flat,
    rest_palms), so a sword built in the hand at rest stays in it. Pose.hands entries."""
    from lib import vrm

    R = vrm.align(rest_hilt, rest_flat, hilt_dir, flat)
    d = np.asarray(hilt_dir, float) / np.linalg.norm(hilt_dir)
    return {side: ("grasp", np.asarray(pommel, float) + d * along, d, R @ np.asarray(rest_palms[side], float),
                   poles[side]) for side, along in grips.items()}


def apply(actor, p: Pose, *, fingers: dict | None = None) -> None:
    """Set a pose (not keyed)."""
    from lib import vrm

    ch = actor["vrm"]
    root = actor["root"]
    root.location = (p.at[0], p.at[1], p.lift)
    root.rotation_euler = (0.0, 0.0, p.yaw)
    fing = dict(fingers or {})
    for side, h in p.hands.items():
        if h[0] == "grasp":
            _, point, along, palm, pole = h[:5]
            f = vrm.grasp(ch, side, point, along, palm, pole=pole)
            if not fingers:
                fing.update(f)
        else:
            _, wrist, pole = h[:3]
            vrm.reach(ch, f"{side}Hand", wrist, pole=pole)
            if len(h) > 3:
                vrm.hold(ch, f"{side}Hand", h[3])
    vrm.pose(ch, {**p.turns, **fing}, hips=p.hips)
    for side, (at, pole, turn) in p.feet.items():
        vrm.reach(ch, f"{side}Foot", at, pole=pole)
        vrm.hold(ch, f"{side}Foot", turn)
    if p.face is not None:
        vrm.express(ch, p.face)


def key(actor, frame: int, *, face: dict | None = None) -> None:
    """Key everything a pose sets at `frame`: the root, every humanoid bone's turn, the hips' place, every IK and hold
    handle, and the face (when given)."""
    from lib import vrm

    ch = actor["vrm"]
    actor["root"].keyframe_insert("location", frame=frame)
    actor["root"].keyframe_insert("rotation_euler", frame=frame)
    for bone_name in ch.bones.values():
        pb = ch.armature.pose.bones[bone_name]
        pb.keyframe_insert("rotation_quaternion", frame=frame)
    ch.bone("hips").keyframe_insert("location", frame=frame)
    for e in ch.handles.values():
        e.keyframe_insert("location", frame=frame)
        if e.rotation_mode == "QUATERNION":
            e.keyframe_insert("rotation_quaternion", frame=frame)
    if face is not None:
        vrm.express(ch, face, frame=frame)


def blend(a: Pose, b: Pose, k: float) -> Pose:
    """Between two poses (hands and feet of the same kinds in both): every place, turn and point by k."""
    from lib import vrm

    def mix(x, y):
        if isinstance(x, (int, float)):
            return x + (y - x) * k
        if isinstance(x, str):
            return x
        if isinstance(x, dict):
            return {kk: mix(x[kk], y[kk]) for kk in x}
        if isinstance(x, (tuple, list, np.ndarray)) and len(x) and isinstance(x[0], str):
            return tuple(mix(u, v) for u, v in zip(x, y))
        arr = np.asarray(x, float) + (np.asarray(y, float) - np.asarray(x, float)) * k
        return tuple(arr) if arr.ndim == 1 else arr
    face = None
    if a.face is not None or b.face is not None:
        fa, fb = a.face or {}, b.face or {}
        face = {n: fa.get(n, 0.0) + (fb.get(n, 0.0) - fa.get(n, 0.0)) * k for n in {*fa, *fb}}
    return Pose(at=mix(a.at, b.at), yaw=mix(a.yaw, b.yaw), lift=mix(a.lift, b.lift), hips=mix(a.hips, b.hips),
                turns=vrm.blend(a.turns, b.turns, k),
                hands={s: mix(a.hands[s], b.hands[s]) for s in a.hands},
                feet={s: mix(a.feet[s], b.feet[s]) for s in a.feet}, face=face)


def hold_constant(*owners) -> None:
    from lib import toon

    for owner in owners:
        ad = getattr(owner, "animation_data", None)
        if ad is None or ad.action is None:
            continue
        for fc in toon._fcurves(ad.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
