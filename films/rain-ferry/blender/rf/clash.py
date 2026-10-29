"""What the duel's last four shots share (shots/charge.py, flash.py, after.py, fall.py): the crossing in the rain, the
3D VRoid cast painted as the standoff paints it (shots/standoff.py's tones and keys), what the clash does to their
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

import importlib.util
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# the duel's marks, on the outer half of the jetty near its end (rf/set_jetty.py: the end posts at x 7.42), her back
# to the open river, him 4.5 m from her toward the bank. S5's rf/duel.py publishes the standoff's marks; these follow
# them until it is merged
STANDOFF = {"shinza": (1.6, 0.0), "tsuru": (6.1, 0.05)}
CLASH = 5.55                      # x where the blades meet: he has run the gap, she has not moved from her mark
END = {"shinza": (7.0, 0.08), "tsuru": (5.2, -0.06)}   # passed through each other: back to back
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
          splashes: bool = True, motion_blur: float = 0.0) -> dict:
    """The crossing in the shot's rain and light: the sets agent's world (rf/set_world.py, its weather from the look
    schedule at the shot's start), the near set's ink, the rain (if it falls: ctx.look_at(ctx.f0).rain) and its
    splashes. `motion_blur`: a shutter (0 off). Returns set_world's dict with "ink", "rain", "splashes", "state"."""
    from lib import toon
    from rf import set_world, sets

    scene = ctx.scene
    s = ctx.look_at(ctx.f0)
    scene.render.use_motion_blur = motion_blur > 0
    if motion_blur > 0:
        scene.render.motion_blur_shutter = motion_blur
    w = set_world.build(ctx)
    w["ink"] = toon.ink("ink-near", w["near"], radius=0.0042, crease=150)
    r = s.rain
    rain = None
    drops = r.drops or 5200      # a shot whose rain starts stopped still has its drops, hanging
    if r.alpha > 0 and r.density > 0:
        rain = toon.rain("rain", rain_box[0], rain_box[1], count=drops, speed=r.speed or 9.5, wind=r.wind,
                         length=r.length, width=r.width, color=r.color, alpha=r.alpha, seed=4, near=near, clear=clear)
    spl = []
    if splashes and rain is not None:
        spl.append(toon.splashes("splash-deck", (-6.5, -sets.HALF + 0.05, 0.004), (7.6, sets.HALF - 0.05, 0.004),
                                 count=240, size=0.08, seed=5))
        spl.append(toon.splashes("splash-river", (-7.5, -3.6, sets.WATER_Z + 0.002), (7.5, -1.15, sets.WATER_Z + 0.002),
                                 count=340, size=0.11, alpha=0.45, seed=9))
    w.update(rain=rain, splashes=spl, state=s)
    return w


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

def cast(ctx, w: dict, variants: dict) -> dict:
    """The 3D cast in the shot, painted as the standoff paints them: each built (rf/vroid_cast.py, with its variant's
    arguments: {"shinza": {"sword": "broken"}, ...}), lit by a key of
    its own, toned, smoothed. Returns {name: {built..., "key": light}} and "coll" (the cast's collection) and
    "rain" (a copy of the rain in the cast's layer, so the drops in front of a face stay in front of it)."""
    from lib import toon, toon3d, vrm
    from rf import vroid_cast

    so = standoff()
    coll = toon.collection("cast")
    look = w["look"]
    cast_look = toon.Look(fog=look.fog, fog_near=look.fog_near, fog_far=look.fog_far, fog_max=look.fog_max,
                          fog_power=look.fog_power)
    out = {"coll": coll}
    for name, kw in variants.items():
        built = getattr(vroid_cast, name)(coll, cast_look, **kw)
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


def camera(ctx, name: str = "camera", *, fstop: float = 2.8):
    """The shot's camera on the engine's gate, tracking an aim empty (its focus): (camera, aim)."""
    import bpy

    from lib import rig

    cam = rig.engine_camera(name, fstop=fstop, size=ctx.size)
    cam.data.clip_end = 3000.0
    ctx.scene.camera = cam
    aim = bpy.data.objects.new(f"{name}-aim", None)
    ctx.scene.collection.objects.link(aim)
    c = cam.constraints.new("TRACK_TO")
    c.target = aim
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    return cam, aim


def focus(ctx, cam, name: str = "focus"):
    """An empty the camera focuses on (key its location)."""
    import bpy

    e = bpy.data.objects.new(name, None)
    ctx.scene.collection.objects.link(e)
    cam.data.dof.focus_object = e
    return e
