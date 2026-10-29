"""What the duel's last four shots share (shots/charge.py, flash.py, after.py, fall.py): the crossing in the rain, the
3D VRoid cast painted as S5's duel paints it (rf/duel.py's tones), what the clash does to their
props, their keyed poses, the light and the compositing, all read from the film's look schedule (ctx.look_at).

The blocking (rf/sets.py's axes: the jetty along x out from the bank at -x, the deck's top at z 0, the cameras on
the -y side). In the standoff Shinza stands at STANDOFF facing +x (screen left) and Tsuru facing -x (screen right). He charges along the jetty;
they meet at CLASH, pass through each other and stand back to back (END): him further out toward the jetty's end
facing +x, her nearer the bank facing -x.

The props the clash changes are the cast's variants (rf/vroid_cast.py): his sword "broken" (the half blade a prop of
its own, parts["half"]), Tsuru's pole "drawn" or whole; `loose_headband` lets his cut headband go from his head.

The poses are keyed whole (`Pose`, `apply`, `key`): where the character stands and turns, the hips, the bones' turns,
the hands (on a hilt, through `sword_hands`, or reaching) and the feet, and the face. Generic keyed posing belongs to
the core's character animation (blender/lib/vrm_anim.py) when it lands; this is the duel's own until then.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# the duel's marks: S5's (rf/duel.py MARKS: him toward the bank facing +x, her near the jetty's end facing -x)
STANDOFF = {"shinza": (2.2, 0.0), "tsuru": (6.7, 0.05)}
CLASH = 6.1                       # x where the blades meet: he has run the gap, she has not left her mark
# where the duel leaves them (the lesson starts here): passed through each other, back to back, ((x, y), facing)
END = {"shinza": ((7.2, 0.08), 0.0), "tsuru": ((5.0, -0.06), math.pi)}
# the fall's marks: where he kneels (facing +x), where the half blade sticks in the planks (its point), where his
# headband lies
FALL = {"kneel": (7.2, 0.08), "half": (6.03, -0.55), "headband": (7.42, -0.2)}
KEYS = {"shinza": (1.0, -0.3, 0.8), "tsuru": (-1.0, -0.3, 0.8)}   # each one's key, from the side they face (world)
OUTLINE = 0.0018                  # the 3D cast's outline, in frame heights (as the standoff's)


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

def world(ctx) -> dict:
    """The crossing as every shot has it (rf/set_world.py: lit for the look schedule's weather at the shot's start),
    its near set inked. Returns set_world's dict with "ink" and "state" (the schedule at the first frame)."""
    from lib import toon
    from rf import set_world

    w = set_world.build(ctx)
    w["ink"] = toon.ink("ink-near", w["near"], radius=0.0042, crease=150)
    w["state"] = ctx.look_at(ctx.f0)
    return w


def weather(ctx, rig, w: dict, actors: dict | None = None, **kw):
    """The shot's rain, splashes, rings and mist (lib/weather.py storm, round `rig`'s setups; the look schedule's
    unless `kw` says otherwise), the drops also linked into the cast's layer (`actors["coll"]`) so those in front of
    a face stay in front of it. Returns the Sky."""
    import bpy

    from lib import weather as wx
    from rf import sets

    deck = ((-6.5, -sets.HALF + 0.05, 0.004), (7.6, sets.HALF - 0.05, 0.004))
    river = ((-2.0, -9.0, sets.WATER_Z + 0.002), (14.0, -1.15, sets.WATER_Z + 0.002))
    kw.setdefault("splashes", [deck, river])
    kw.setdefault("strikes", [])
    sky = wx.storm(ctx, rig, waters=w["waters"], floor=sets.WATER_Z, ground=sets.WATER_Z, **kw)
    coll = bpy.data.collections.get("rain")
    if actors is not None and sky.rain is not None and coll is not None:
        for ob in coll.all_objects:
            if ob.name not in actors["coll"].objects:
                actors["coll"].objects.link(ob)
    return sky


# ---------------------------------------------------------------------------------------------------- the cast

def cast(ctx, w: dict, variants: dict) -> dict:
    """The 3D cast in the shot, painted as rf/duel.py paints them: each built (rf/vroid_cast.py, with its variant's
    arguments: {"shinza": {"sword": "broken"}, ...}), lit by a key of
    its own, toned, smoothed. Returns {name: {built..., "key": light}} and "coll" (the cast's collection)."""
    from lib import toon, toon3d, vrm
    from rf import duel, vroid_cast

    coll = toon.collection("cast")
    look = w["look"]
    cast_look = toon.Look(fog=look.fog, fog_near=look.fog_near, fog_far=look.fog_far, fog_max=look.fog_max,
                          fog_power=look.fog_power)
    out = {"coll": coll}
    for name, kw in variants.items():
        built = getattr(vroid_cast, name)(coll, cast_look, **kw)
        k = toon3d.key(f"{name}-key", [built["root"], *built["root"].children_recursive], KEYS[name], coll=coll,
                       angle=duel.KEY_ANGLE)
        tones = {p: toon3d.Tone(**{**t, **duel.TONES_OF.get(name, {}).get(p, {})}) for p, t in duel.TONES.items()}
        vrm.anime(built["vrm"], tones, k)
        vrm.smooth(built["vrm"])
        built["key"] = k
        out[name] = built
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

def loose_headband(actor):
    """His headband (band, knot and tails: parts["headband"]) as one object let go of his head where it is in the
    current pose, its origin at its centre: a shot slides it off. Returns the object."""
    import bpy

    parts = list(actor["parts"]["headband"])
    if not parts:
        raise RuntimeError("clash: no headband to cut")
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
    band.name = f"{actor['vrm'].name}-band-loose"
    return band


def _origin_to(ob, point) -> None:
    """Move an object's origin to a world point, its mesh staying where it is."""
    from mathutils import Matrix, Vector

    p = ob.matrix_world.inverted() @ Vector(point)
    ob.data.transform(Matrix.Translation(-p))
    ob.matrix_world = ob.matrix_world @ Matrix.Translation(p)


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


def shinza_sword(ch, pommel, hilt_dir, *, flat=(1.0, 0.0, 0.0), poles=None) -> tuple[dict, dict]:
    """Shinza's two hands on his hilt from `pommel` along `hilt_dir` (his frame), as rf/vroid_shinza.py grips it in
    the guard, turned with it: (Pose.hands, the fingers' pose)."""
    from lib import vrm_rig
    from rf import vroid_shinza as vs

    hilt = vs.HILT_DIR / np.linalg.norm(vs.HILT_DIR)
    palms = {side: np.array((1.0 if side == "right" else -1.0, 0.0, -0.6)) for side in vs.GRIPS}
    hands = sword_hands(pommel, hilt_dir, flat, vs.GRIPS, poles or vs.SH_ELBOWS, hilt, (1.0, 0.0, 0.0), palms)
    fingers = {}
    for side in vs.GRIPS:
        fingers.update(vrm_rig.wrap(ch, side, vs.TSUKA))
    return hands, fingers


# ---------------------------------------------------------------------------------------------------- compositing

def composite(ctx, actors: dict, setup_of) -> object:
    """The cast laid over the world through satsuei (lib/satsuei.py), its look the schedule's (ctx.look_at(f).look)
    with each frame's setup on top (`setup_of(f)` -> rims, para_from, para_to, flash ...), keyed and held. Returns
    the Comp."""
    from lib import satsuei

    comp = satsuei.setup(ctx.scene, actors["coll"])
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        own = dict(setup_of(f))
        if "rims" in own:
            own["rims"] = tuple(r if isinstance(r, satsuei.Rim) else satsuei.Rim(*r) for r in own["rims"])
        comp.key(f, ctx.look_at(f).look(**own))
    comp.hold()
    return comp
