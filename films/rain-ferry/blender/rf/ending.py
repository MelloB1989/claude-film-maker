"""The Rain Ferry's ending, shots 22 to 26 (lesson, kneel, board, cross): the jetty after the duel, the rain stopping,
the crossing. What those shots share lives here; each shot is its own file under shots/.

The world is rf/set_world.py's, its weather and light the film's look schedule's (data/look.json, `ctx.look_at(f)`,
keyed on the set by rf/set_weather.py). The grade is the engine's, over the plate: nothing here bakes one in.

- The stage after the duel (`SHINZA_AT` ...): where Shinza went down on his knees and where the cut headband lies
  (rf/clash.py's END and FALL), Tsuru's way to the boat.
- Pure helpers: `kneel_legs(...)` (where the knee and hips come for a kneel), `mouth(t, lines)` (a line's mouth
  flaps), `ease`, `smooth`, `keys_at`, `path_at`.
- In Blender: `stage(ctx)` builds the world and inks it; `weather(ctx, st, rig)` lets the schedule's rain fall round
  the shot's camera (lib/weather.py), in the cast's layer too; `cast(st, {name: variant})` builds the 3D cast
  (rf/vroid_cast.py) painted as the standoff paints them; `fallen` gives Shinza's pose as shot 21 leaves him and
  `stick_half` his blade's half where shot 20 stuck it; `kneel` and `hands_rest` kneel him anywhere (in the boat);
  `headband` is the cut band (on the deck, or afloat); `finish(...)` composites the cast over the world
  (lib/satsuei.py) from the schedule's looks, a shot's rims on top, the cast's outlines a width on screen.

The cameras are lib/cinema.py's, the walking and lip-sync lib/vrm_anim.py's.

World axes are rf/sets.py's: the jetty along x (the bank at -x), its deck's top at z 0, the river toward +y.
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------------------------------------------- the stage

# Where things are after the duel (world metres, rf/sets.py's axes; rf/clash.py's END and FALL). The duel is near the
# jetty's end; Shinza's charge carried him through her toward the end: he went down on his knees there, facing on
# along it (radians from +x toward +y), half his blade standing in the planks behind him where it fell, the cut
# headband on the deck by his knee. Tsuru, back to back with him on the land side, walks away from him along the
# boat's side to the ferry's stern (rf/set_jetty.py). Looking back along
# the jetty from its end (every camera of 22-24), he is on the left, she on the right, the hut's lantern beyond.
SHINZA_AT = (7.2, 0.08)                            # rf/clash.py FALL["kneel"]
SHINZA_FACING = 0.0
TSURU_WALK = [(4.4, -0.06), (3.9, 0.45), (3.3, 0.8)]   # her way from her END mark (rf/clash.py) to the ferry's stern (x, y)


def smooth(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


def ease(u: float) -> float:
    """In and out, gentler at its ends than `smooth` (in-out sine)."""
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def lerp(a, b, k: float) -> tuple:
    return tuple(x + (y - x) * k for x, y in zip(a, b))


def keys_at(keys, t: float):
    """A value through keys [(t, value), ...] (a number or a tuple), eased in-out between neighbours, held beyond the
    ends."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, a), (t1, b) in zip(keys, keys[1:]):
        if t <= t1:
            k = ease((t - t0) / (t1 - t0)) if t1 > t0 else 1.0
            return a + (b - a) * k if isinstance(a, (int, float)) else lerp(a, b, k)
    return keys[-1][1]


def kneel_legs(shin: float, thigh: float, ankle_z: float, knee_z: float, hip_z: float) -> tuple[float, float]:
    """A kneel sitting back on the heels: the shin from the ankle (at `ankle_z`) forward and down to the knee on the
    floor (`knee_z`), the thigh from the knee back up to the hip joint (`hip_z`). Returns (how far the knee is ahead
    of the ankle, how far the hip joint is), metres."""
    dz = knee_z - ankle_z
    knee = math.sqrt(max(shin * shin - dz * dz, 0.0))
    dz2 = hip_z - knee_z
    return knee, knee - math.sqrt(max(thigh * thigh - dz2 * dz2, 0.0))


def mouth(t: float, lines, rate: float = 7.0, seed: int = 3) -> float:
    """How open a speaking mouth is at time t (s) for lines [(start, end), ...]: syllables at about `rate` a second,
    each opening by its own amount, shut between the lines and easing in and out of each."""
    for a, b in lines:
        if a <= t <= b:
            u = (t - a) * rate
            n = int(u)
            r = math.sin(n * 12.9898 + seed * 78.233) * 43758.5453
            size = 0.45 + 0.55 * (r - math.floor(r))
            env = min(1.0, (t - a) / 0.08, (b - t) / 0.12)
            return size * math.sin(math.pi * (u - n)) ** 2 * env
    return 0.0


def path_at(points, s: float) -> tuple[tuple, float]:
    """The point `s` metres along a polyline [(x, y)], and its heading there (radians from +x)."""
    import numpy as np

    P = np.asarray(points, float)
    for i in range(len(P) - 1):
        d = P[i + 1] - P[i]
        L = float(np.linalg.norm(d))
        if s <= L or i == len(P) - 2:
            return tuple(P[i] + d * min(max(s / L, 0.0), 1.0)), math.atan2(d[1], d[0])
        s -= L


def path_length(points) -> float:
    import numpy as np

    return float(np.linalg.norm(np.diff(np.asarray(points, float), axis=0), axis=1).sum())


# ---------------------------------------------------------------------------------------------------- the world

INK = 0.0042        # the near set's line art radius (m), as the standoff's wide


class Stage:
    """What `stage` built: scene, world (rf/set_world.py's), look (toon.Look), cast (the cast's collection), ink,
    sky (lib/weather.py's, once `weather` has made it), held (what is keyed and must cut, not tween)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def stage(ctx, *, ink: float | None = None) -> Stage:
    """The world (rf/set_world.py) for the shot, its weather keyed from the look schedule (rf/set_weather.py: the
    rain on the water, the sheen, the key), inked; the cast's collection ready."""
    from lib import toon
    from rf import set_weather, set_world

    scene = ctx.scene
    scene.render.use_motion_blur = False   # drawn animation has no shutter
    world = set_world.build(ctx)
    set_weather.key(world, ctx)
    lines = toon.ink("ink-near", world["near"], radius=ink, crease=150) if ink else None
    return Stage(scene=scene, world=world, look=world["look"], cast=toon.collection("cast"), ink=lines, sky=None,
                 held=[])


def weather(ctx, st: Stage, rig, *, deck=True, river=True, **kw):
    """The schedule's rain and mist round the shot's camera (lib/weather.py's storm: thinning with its density,
    splashing on the deck and the river, ringing the waters), its drops falling in the cast's layer too, so those
    in front of a face stay in front of it (lib/satsuei.py)."""
    from lib import weather as wx
    from rf import sets

    areas = []
    if deck:
        areas.append(((sets.SPAN[0], -sets.HALF + 0.05, 0.004), (sets.SPAN[1], sets.HALF - 0.05, 0.004)))
    if river:
        areas.append(((-8.0, -8.0, sets.WATER_Z + 0.002), (14.0, 10.0, sets.WATER_Z + 0.002)))
    st.sky = wx.storm(ctx, rig, splashes=areas, waters=st.world["waters"], floor=sets.WATER_Z, ground=sets.WATER_Z,
                      strikes=[], **kw)
    if st.sky.rain is not None:
        for d in st.sky.rain.drops.values():
            if d.ob.name not in st.cast.objects:
                st.cast.objects.link(d.ob)
    return st.sky


def head_of(built):
    """A focus on a character's head (lib/cinema.py's (Character, bone))."""
    return (built["vrm"], "head")


def point_focus(name: str, at):
    """An empty at a world point, to focus on."""
    import bpy

    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.location = at
    return e


# ---------------------------------------------------------------------------------------------------- the cast

_SHOTS: dict = {}


def shot_module(name: str):
    """shots/<name>.py as a module (another shot's constants: the standoff's paint, the fall's last pose), loaded once."""
    if name in _SHOTS:
        return _SHOTS[name]
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(f"shots.{name}", Path(__file__).resolve().parents[1] / "shots" /
                                                  f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _SHOTS[name] = mod
    return mod


def _standoff():
    """shots/standoff.py, for the 3D cast's paint (TONES3D, TONES3D_OF, OUTLINE): one look for the cast in every
    shot."""
    return shot_module("standoff")


KEY_ANGLE = 5.0   # degrees: an overcast key's soft-edged shadows


def cast(st: Stage, variants: dict) -> dict:
    """The 3D cast (rf/vroid_cast.py), {name: the builder's variant arguments}, in the stage's cast collection, each
    painted as the standoff paints them (toon3d, a key of their own: aim it with `toon3d.aim(built["key"], toward,
    frame=f)`)."""
    from lib import toon, toon3d, vrm
    from rf import vroid_cast

    so = _standoff()
    look = toon.Look(fog=st.look.fog, fog_near=st.look.fog_near, fog_far=st.look.fog_far, fog_max=st.look.fog_max,
                     fog_power=st.look.fog_power)
    out = {}
    for name, kw in variants.items():
        built = getattr(vroid_cast, name)(st.cast, look, **kw)
        built["key"] = toon3d.key(f"{name}-key", [built["root"], *built["root"].children_recursive], (1.0, -0.3, 0.8),
                                  coll=st.cast, angle=KEY_ANGLE)
        tones = {p: toon3d.Tone(**{**kw, **so.TONES3D_OF.get(name, {}).get(p, {})}) for p, kw in so.TONES3D.items()}
        vrm.anime(built["vrm"], tones, built["key"])
        vrm.smooth(built["vrm"])
        out[name] = built
    st.outline = so.OUTLINE
    return out


def place(built, at, facing: float, z: float = 0.0, frame: int | None = None) -> None:
    root = built["root"]
    root.location = (at[0], at[1], z)
    root.rotation_euler = (0.0, 0.0, facing)
    if frame is not None:
        root.keyframe_insert("location", frame=frame)
        root.keyframe_insert("rotation_euler", frame=frame)


def _foot_turn(ch, side: str, toward) -> tuple:
    """The turn about the character's x (degrees) that points a foot (ankle to toes) along `toward` (y, z in its
    frame)."""
    import numpy as np

    t0 = ch.rest(f"{side}Toes") - ch.rest(f"{side}Foot")
    a0 = math.atan2(t0[2], t0[1])
    a1 = math.atan2(toward[1], toward[0])
    return (math.degrees(a1 - a0), 0.0, 0.0) if np.isfinite(a0) else (0.0, 0.0, 0.0)


# Shinza on his knees, sitting back on his heels: the knees apart, the insteps flat on the deck; the hips' height and
# where the knees come from his legs' lengths (kneel_legs). His trunk sags forward over his lap and his head hangs.
KNEEL = dict(ankle_z=0.075, knee_z=0.065, hip_z=0.3, ankle_y=0.16, width=0.14)
SAG = {"hips": (-6.0, 0.0, 0.0), "spine": (14.0, 0.0, 0.0), "chest": (10.0, 0.0, 0.0), "upperChest": (6.0, 0.0, 0.0),
       "neck": (14.0, 0.0, 0.0), "head": (20.0, 0.0, 0.0),
       "leftShoulder": (0.0, 10.0, -4.0), "rightShoulder": (0.0, -10.0, 4.0)}


def kneel(built, *, sag=SAG, hips_dz: float = 0.0, frame: int | None = None, legs: bool = True) -> dict:
    """Shinza's legs folded under him (IK: his feet behind him, insteps down, knees forward on the deck) and his trunk
    posed `sag`; keyed at `frame` when given. Returns where the legs went (char frame): knee and hip joint."""
    import numpy as np

    from lib import vrm

    ch = built["vrm"]
    p = KNEEL
    thigh = float(np.linalg.norm(ch.rest("leftLowerLeg") - ch.rest("leftUpperLeg")))
    shin = float(np.linalg.norm(ch.rest("leftFoot") - ch.rest("leftLowerLeg")))
    knee_y, hip_y = kneel_legs(shin, thigh, p["ankle_z"], p["knee_z"], p["hip_z"])
    hip0 = (ch.rest("leftUpperLeg") + ch.rest("rightUpperLeg")) / 2
    hips = (0.0, p["ankle_y"] - hip_y - hip0[1], p["hip_z"] + hips_dz - hip0[2])
    vrm.pose(ch, {**sag, **built.get("fingers", {})}, hips=hips, frame=frame, reset=True)
    if legs:
        for side, s in (("left", 1.0), ("right", -1.0)):
            x = s * p["width"]
            vrm.reach(ch, f"{side}Foot", (x * 0.8, p["ankle_y"], p["ankle_z"]), pole=(x * 1.4, -1.5, p["knee_z"]))
            vrm.hold(ch, f"{side}Foot", _foot_turn(ch, side, (1.0, -0.12)))
    return {"knee": (0.0, p["ankle_y"] - knee_y, p["knee_z"]), "hip": (0.0, p["ankle_y"] - hip_y, p["hip_z"])}


def fallen(built, *, turns: dict | None = None, stub=None):
    """Shinza as shot 21 (shots/fall.py) leaves him, at rf/clash.py's FALL: on both knees, slumped, the stub of his
    sword in his right hand, its broken end on the planks, his left hand loose on his thigh. `turns` on top of the
    fall's kneel (a breath, the head sinking); `stub` (pommel, hilt direction) moves the sword in both hands instead.
    Returns (rf/clash.py's Pose, the fingers): `clash.apply` it, `clash.key` it."""
    from rf import clash

    fall = shot_module("fall")
    ch = built["vrm"]
    if stub is None:
        hands, fingers = clash.arms(ch, fall.KNEEL_STUB, fall.KNEEL_LEFT)
    else:
        hands, fingers = clash.arms(ch, {"pommel": stub[0], "hilt": stub[1]})
    (x, y), yaw = clash.FALL["kneel"], clash.END["shinza"][1]
    return clash.Pose(at=(x, y), yaw=yaw, hips=fall.KNEEL_HIPS, turns={**fall.KNEEL, **(turns or {})}, hands=hands,
                      feet=fall.KNEEL_FEET), fingers


HALF_LEAN = 18.0    # degrees the stuck half leans from upright toward +x (shots/after.py's LEAN)


def stick_half(built) -> None:
    """His blade's broken half where shot 20 (shots/after.py) stuck it: point 4 cm into the planks at rf/clash.py's
    FALL["half"], leaning HALF_LEAN toward +x (and a little toward -y). Left there, out of his hands."""
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    from rf import clash

    half = built["parts"]["half"][0]
    bpy.context.view_layer.update()
    co = np.array([half.matrix_world @ v.co for v in half.data.vertices])
    rings = co.reshape(-1, 4, 3).mean(axis=1)
    tip, root_ = rings[np.argmin(rings[:, 2])], rings[np.argmax(rings[:, 2])]
    half.parent = None
    lean = math.radians(HALF_LEAN)
    up = Vector((math.sin(lean), -0.25 * math.sin(lean), math.cos(lean))).normalized()
    rot = Vector(root_ - tip).normalized().rotation_difference(up).to_matrix().to_4x4()
    goal = Vector((*clash.FALL["half"], -0.04))
    half.matrix_world = Matrix.Translation(goal) @ rot @ Matrix.Translation(-Vector(tip)) @ half.matrix_world


def key_handles(built, frame: int, keys=None) -> None:
    """Key the IK and hold handles (all, or those named) where they are now."""
    for k, h in built["vrm"].handles.items():
        if keys is None or k in keys:
            h.keyframe_insert("location", frame=frame)
            h.keyframe_insert("rotation_quaternion", frame=frame)


def hands_rest(built, legs: dict, frame: int | None = None) -> None:
    """His hands on his thighs, palms down, fingers loose."""
    from lib import vrm

    ch = built["vrm"]
    kn, hp = legs["knee"], legs["hip"]
    for side, s in (("left", 1.0), ("right", -1.0)):
        at = (s * 0.13, hp[1] + (kn[1] - hp[1]) * 0.62 - 0.03, 0.3)
        vrm.reach(ch, f"{side}Hand", at, pole=(s * 0.6, 0.5, 0.6))
        vrm.hold(ch, f"{side}Hand", (0.0, s * -12.0, -s * 80.0))
    built["fingers"] = {**vrm.grip_pose("left", 0.3, 0.3), **vrm.grip_pose("right", 0.3, 0.3)}


# ---------------------------------------------------------------------------------------------------- the leavings

BAND_LANDED = (1.45, -1.45, 1.1)    # shots/fall.py: the turn its headband has taken by the time it lies on the planks


def cut_headband(built, *, afloat: bool = False):
    """His own headband (rf/vroid_shinza.py's, built with headband=True) cut loose as shot 21 (shots/fall.py) leaves
    it: off his head (rf/clash.py's loose_headband, before he is posed), lying flat on the planks at FALL["headband"],
    turned as it landed. `afloat`: leave it free for a shot to float it (the cross). Returns the band."""
    from mathutils import Euler

    from rf import clash

    band = clash.loose_headband(built)
    r0 = band.matrix_world.to_euler()
    band.rotation_euler = Euler((r0.x + BAND_LANDED[0], r0.y + BAND_LANDED[1], r0.z + BAND_LANDED[2]))
    if not afloat:
        band.location = (*clash.FALL["headband"], 0.012)
    return band


def band_material(look, wet: float = 1.0, name: str = "ending-band"):
    """The headband's cloth (rf/vroid_common.py's band red, as wet as `wet`)."""
    from lib import toon
    from rf.vroid_common import colors

    lit, shade = colors(wet)["band"]
    return toon.cel(name, lit, shade, look=look)


def headband(name: str, material, coll, at, turn: float, *, z: float = 0.004, length: float = 1.05, width: float = 0.03,
             curl: float = 0.16, seed: int = 2):
    """The cut headband lying loose: a strip of cloth `width` wide and `length` long, flat on z, wandering in loose
    curves (a knot near one end, where it was tied), turned `turn` degrees about z at (x, y). Returns the strip."""
    import numpy as np

    from lib import shapes

    rng = np.random.default_rng(seed)
    n = 28
    u = np.linspace(0.0, 1.0, n)
    ph = rng.uniform(0, 6.28, 3)
    xs = (u - 0.5) * length * 0.8
    ys = curl * (np.sin(u * 5.0 + ph[0]) * 0.6 + np.sin(u * 11.0 + ph[1]) * 0.25)
    zs = z + 0.006 * np.abs(np.sin(u * 17.0 + ph[2]))           # creases lifting off the deck
    c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
    pts = [(at[0] + x * c - y * s, at[1] + x * s + y * c, zz) for x, y, zz in zip(xs, ys, zs)]
    w = width / 2 * (0.9 + 0.1 * np.sin(u * 23.0))
    w[-1] = w[-1] * 0.6
    band = shapes.loft(name, pts, w, 0.0016, material=material, coll=coll, n=4, power=6.0, subsurf=0, up=(0, 0, 1))
    kx, ky, kz = pts[4]
    knot = shapes.ellipsoid(f"{name}-knot", (kx, ky, kz + 0.008), (0.028, 0.02, 0.014), material=material, coll=coll,
                            n=10)
    return [band, knot]


# ---------------------------------------------------------------------------------------------------- compositing

INK_REACH = 30.0    # m: set pieces farther than this from the camera all shot are left uninked (their lines sub-pixel)


def trim(ctx, st: Stage) -> int:
    """The render's cost cut without touching the look: the line art skips the set pieces the camera never comes
    within INK_REACH of and the faces turned away from it; EEVEE traces its rays and shadows at half resolution (the
    reflections are soft on rain-struck water anyway). Returns how many pieces it left uninked."""
    import bpy
    from mathutils import Vector

    ev = ctx.scene.eevee
    for attr, value in (("ray_tracing_method", "SCREEN"), ("shadow_resolution_scale", 0.5), ("shadow_ray_count", 1),
                        ("shadow_step_count", 4)):
        if hasattr(ev, attr):
            setattr(ev, attr, value)
    ev.use_raytracing = False   # PROBE
    rt = getattr(ev, "ray_tracing_options", None)
    if rt is not None:
        rt.resolution_scale = "2"
    if st.ink is not None:
        for md in st.ink.modifiers:
            if md.type == "LINEART" and hasattr(md, "use_back_face_culling"):
                md.use_back_face_culling = True
    eyes = []
    for f in range(ctx.f0, ctx.f1 + 1, 12):
        ctx.scene.frame_set(f)
        eyes.append(Vector(ctx.scene.camera.matrix_world.translation))
    cut = 0
    for ob in st.world["near"].all_objects:
        if ob.type != "MESH" or ob.lineart.usage == "EXCLUDE":
            continue
        corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        lo = Vector([min(c[i] for c in corners) for i in range(3)])
        hi = Vector([max(c[i] for c in corners) for i in range(3)])
        near = min((Vector([min(max(e[i], lo[i]), hi[i]) for i in range(3)]) - e).length for e in eyes)
        if near > INK_REACH:
            ob.lineart.usage = "EXCLUDE"
            cut += 1
    bpy.context.view_layer.update()
    print(f"trim: {cut} far set pieces uninked")
    return cut


OUTLINE_STEP = 8    # frames between the outline widths' keys (each key evaluates the scene: the build's cost)


def finish(ctx, st: Stage, setup=None, actors=None, lens_of=None):
    """Composite the cast over the world (lib/satsuei.py) with the schedule's look every frame, a setup's own on top
    (`setup(f, state)` -> satsuei.Look fields: rims, para_from, para_to, ...); the cast's outlines a width on screen
    (`lens_of(f)`: the lens at frame f), keyed every OUTLINE_STEP frames and eased between."""
    from mathutils import Vector

    from lib import satsuei, toon, vrm

    trim(ctx, st)
    if actors and lens_of:
        frames = list(range(ctx.f0 - 1, ctx.f1 + 1, OUTLINE_STEP))
        if frames[-1] != ctx.f1:
            frames.append(ctx.f1)
        for f in frames:
            ctx.scene.frame_set(f)
            cam_at = Vector(ctx.scene.camera.matrix_world.translation)
            for built in actors.values():
                d = (cam_at - built["vrm"].face()).length
                vrm.key_outline(built["vrm"], vrm.outline_width(st.outline, d, lens_of(f)), f)
        # one setup, no cuts: the widths eased between their sparse keys, not held
        for built in actors.values():
            for md, _ in vrm.outline_modifiers(built["vrm"]):
                ad = md.id_data.animation_data
                for fc in (toon._fcurves(ad.action) if ad is not None and ad.action is not None else []):
                    if md.name in fc.data_path:
                        for kp in fc.keyframe_points:
                            kp.interpolation = "LINEAR"
    for owner in st.held:
        ad = getattr(owner, "animation_data", None)
        if ad is not None and ad.action is not None:
            for fc in toon._fcurves(ad.action):
                for kp in fc.keyframe_points:
                    kp.interpolation = "CONSTANT"
    if actors is None:
        return None
    comp = satsuei.setup(ctx.scene, st.cast)
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        s = ctx.look_at(f)
        own = dict(setup(f, s)) if setup else {}
        if "rims" in own:
            own["rims"] = tuple(r if isinstance(r, satsuei.Rim) else satsuei.Rim(*r) for r in own["rims"])
        comp.key(f, s.look(**own))
    comp.hold()
    return comp
