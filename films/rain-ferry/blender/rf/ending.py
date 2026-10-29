"""The Rain Ferry's ending, shots 22 to 26 (lesson, kneel, board, cross): the jetty after the duel, the rain stopping,
the crossing. What those shots share lives here; each shot is its own file under shots/.

The world is rf/set_world.py's, its weather and light the film's look schedule's (data/look.json, `ctx.look_at(f)`,
keyed on the set by rf/set_weather.py). The grade is the engine's, over the plate: nothing here bakes one in.

- The stage after the duel (`SHINZA_AT` ...): where Shinza went down on his knees, where the cut headband lies,
  Tsuru's way to the boat.
- Pure helpers for the cast's stand-in animation: `step(s, ...)` (where a walking foot is), `kneel_legs(...)` (where
  the knee and hips come for a kneel), `mouth(t, lines)` (a line's mouth flaps), `ease`, `smooth`, `keys_at`,
  `path_at`, `drift` (a held camera's breathing).
- In Blender: `stage(ctx)` builds the world, inks it and lets the rain fall in it at the schedule's density (thinned,
  not faded: fewer drops; the splashes with it); `cast(st, {name: variant})` builds the 3D cast (rf/vroid_cast.py)
  painted as the standoff paints them; `kneel`, `hands_rest`, `hold_blade` and `walk` pose and animate them;
  `headband` is the cut band (on the deck, or afloat); `camera(...)` keys a camera frame by frame and `finish(...)`
  composites the cast over the world (lib/satsuei.py) from the schedule's looks, a shot's rims on top.

Until the core's animation (blender/lib/vrm_anim.py) and camera kit (blender/lib/cinema.py) land, the stand-ins here
do their work: a procedural walk, a kneel by IK, a camera keyed frame by frame, the rain thinned by a mask on its drops.

World axes are rf/sets.py's: the jetty along x (the bank at -x), its deck's top at z 0, the river toward +y.
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------------------------------------------- the stage

# Where things are after the duel (world metres, rf/sets.py's axes; until S6's fall publishes its end marks, these are
# the defaults). The duel is near the jetty's end; Shinza's charge carried him past her toward the end: he went down on
# his knees there, facing on along it (radians from +x toward +y), half his blade standing in the planks ahead of him
# where it fell (rf/vroid_shinza.py's), the cut headband on the deck by his knee. Tsuru, back to back with him on the
# land side, walks away from him along the boat's side to the ferry's stern (rf/set_jetty.py). Looking back along
# the jetty from its end (every camera of 22-24), he is on the left, she on the right, the hut's lantern beyond.
SHINZA_AT = (5.9, -0.5)
SHINZA_FACING = math.radians(4.0)
HEADBAND_AT = (6.3, -0.08, 35.0)                  # (x, y, turn (deg)): where the cut band lies on the deck
TSURU_WALK = [(4.6, 0.5), (3.9, 0.66), (3.05, 0.82)]   # her way to the boat (x, y)


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


def step(s: float, stride: float, stance: float = 0.62, phase: float = 0.0) -> tuple[float, float]:
    """A walking foot when the body has come `s` metres: (how far ahead of the body it is, m; how high it is lifted,
    0..1). Each foot lands 2 x `stride` on from where it last did, so the body comes `stride` a step; it is planted for
    `stance` of each cycle (an old woman keeps both feet down a long while), swung forward the rest. `phase` (0..1 of a
    cycle) is the foot's place in it: one foot 0, the other 0.5."""
    cycle = 2.0 * stride
    p = (s / cycle + phase) % 1.0
    reach = stance * cycle / 2.0            # how far ahead it lands (and behind it lifts off)
    if p < stance:
        return reach - (p / stance) * 2.0 * reach, 0.0
    u = (p - stance) / (1.0 - stance)
    return -reach + 2.0 * reach * ease(u), math.sin(math.pi * u)


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

RAIN_BOX = ((-7.0, -6.0, -0.6), (9.0, 10.0, 5.5))
INK = 0.0042        # the near set's line art radius (m), as the standoff's wide


class Stage:
    """What `stage` built: scene, world (rf/set_world.py's), look (toon.Look), rain (or None), rain_cast, cast (the
    cast's collection), splashes, ink, held (what is keyed and must cut, not tween)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def thin(ob, seed: int = 0):
    """A mask over a Geometry Nodes drop field (toon.rain, toon.splashes): only a share of its points kept, the
    returned input's value (key it 0..1), each point at a fixed random rank so the drops thin, not jump."""
    from lib import toon

    ng = ob.modifiers[0].node_group
    gin = next(n for n in ng.nodes if n.bl_idname == "NodeGroupInput")
    link = next(lk for lk in ng.links if lk.from_node == gin)
    to = link.to_socket
    ng.links.remove(link)
    rnd = ng.nodes.new("FunctionNodeRandomValue")
    rnd.data_type = "FLOAT"
    rnd.inputs["Seed"].default_value = 77 + seed
    keep = ng.nodes.new("ShaderNodeValue")
    keep.name = keep.label = "keep"
    gt = ng.nodes.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    ng.links.new(toon._socket(rnd.outputs, "Value", "VALUE"), gt.inputs[0])
    ng.links.new(keep.outputs[0], gt.inputs[1])
    dele = ng.nodes.new("GeometryNodeDeleteGeometry")
    dele.domain = "POINT"
    ng.links.new(gin.outputs[0], dele.inputs["Geometry"])
    ng.links.new(gt.outputs[0], dele.inputs["Selection"])
    ng.links.new(dele.outputs[0], to)
    return keep.outputs[0]


def stage(ctx, *, rain_box=RAIN_BOX, clear: float = 1.2, near: float = 3.5, splash_deck=True, splash_river=True,
          ink: float | None = INK) -> Stage:
    """The world (rf/set_world.py) for the shot, its weather keyed from the look schedule (rf/set_weather.py: the
    rain on the water, the sheen, the key), inked, and the rain falling in it at the schedule's density: thinned, not
    faded (fewer drops), the splashes on the deck and the river with it, its fall slowing as the schedule says."""
    from lib import toon
    from rf import set_weather, set_world, sets

    scene = ctx.scene
    scene.render.use_motion_blur = False   # drawn animation has no shutter (and the rain's drops wrap)
    world = set_world.build(ctx)
    set_weather.key(world, ctx)
    lines = toon.ink("ink-near", world["near"], radius=ink, crease=150) if ink else None

    r0 = ctx.look_at(ctx.f0).rain
    rain = rain_cast = None
    splashes = []
    if any(ctx.look_at(f).rain.drops for f in range(ctx.f0, ctx.f1)):
        rain = toon.rain("rain", rain_box[0], rain_box[1], count=r0.count, speed=r0.speed, wind=r0.wind,
                         length=r0.length, width=r0.width, color=r0.color, alpha=r0.alpha, seed=4, near=near,
                         clear=clear)
        if splash_deck:
            splashes.append(toon.splashes("splash-deck", (sets.SPAN[0], -sets.HALF + 0.05, 0.004),
                                          (sets.SPAN[1], sets.HALF - 0.05, 0.004), count=240, size=0.08, seed=5))
        if splash_river:
            splashes.append(toon.splashes("splash-river", (-7.5, -6.0, sets.WATER_Z + 0.002),
                                          (9.5, 8.0, sets.WATER_Z + 0.002), count=520, size=0.11, alpha=0.45, seed=9))
    cast = toon.collection("cast")
    if rain is not None:
        rain_cast = rain.copy()       # the drops in front of the cast, in the cast's layer (lib/satsuei.py)
        rain_cast.name = "rain-cast"
        cast.objects.link(rain_cast)
    st = Stage(scene=scene, world=world, look=world["look"], rain=rain, rain_cast=rain_cast, cast=cast,
               splashes=splashes, ink=lines, held=[])
    _rain(ctx, st)
    return st


def _rain(ctx, st: Stage) -> None:
    """Key the rain's density (its drops thinned) and its fall's speed from the schedule, every frame."""
    if st.rain is None:
        return
    keeps = [thin(ob, k) for k, ob in enumerate([st.rain] + st.splashes)]
    ng = st.rain.modifiers[0].node_group
    # the fall's rate: toon.rain's wrap of z multiplies the scene's seconds by -speed
    speed = next((n.inputs[1] for n in ng.nodes if n.bl_idname == "ShaderNodeMath" and n.operation == "MULTIPLY"
                  and n.inputs[0].links and n.inputs[0].links[0].from_node.bl_idname == "GeometryNodeInputSceneTime"
                  and n.inputs[1].default_value < 0), None)
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        r = ctx.look_at(f).rain
        for sock in keeps:
            sock.default_value = max(0.0, min(1.0, r.density))
            sock.keyframe_insert("default_value", frame=f)
        if speed is not None:
            speed.default_value = -r.speed
            speed.keyframe_insert("default_value", frame=f)


# ---------------------------------------------------------------------------------------------------- the cast

def _standoff():
    """shots/standoff.py, for the 3D cast's paint (TONES3D, TONES3D_OF, OUTLINE): one look for the cast in every
    shot."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("shots.standoff", Path(__file__).resolve().parents[1] / "shots" /
                                                  "standoff.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def hide(obs) -> None:
    for ob in obs:
        ob.hide_render = ob.hide_viewport = True


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


def hold_blade(built, *, at=(-0.1, -0.36, 0.5), d=(1.0, 0.0, 0.06), cradle=0.3, up=(0.0, 0.25, 1.0)) -> None:
    """His broken sword (rf/vroid_shinza.py's sword="broken", carried by his right hand) held across his lap: the
    right fist round the hilt at `at` (char frame), the blade on toward his left along `d`, his left hand open under
    it `cradle` metres on, both palms up `up`."""
    import numpy as np

    from lib import vrm

    ch = built["vrm"]
    d = np.asarray(d, float) / np.linalg.norm(d)
    at = np.asarray(at, float)
    fr = vrm.grasp(ch, "right", at, d, up, pole=(-0.55, 0.2, 0.55), amount=0.95)
    fl = vrm.grasp(ch, "left", at + d * cradle, d, up, pole=(0.55, 0.2, 0.55), amount=0.3, thumb=0.2)
    built["fingers"] = {**fr, **fl}
    vrm.pose(ch, {**SAG, **built["fingers"]}, reset=False)


# Tsuru's walk: short steps, both feet down a long while, the hips bobbing a little; her left arm swinging a little
# from where it hangs
WALK = dict(stride=0.34, stance=0.64, lift=0.065, bob=0.012, sway=2.5, swing=0.07)


def walk(ctx, built, path, distance, *, pose: dict, hips, frames=None, head=None) -> None:
    """Key Tsuru walking along `path` [(x, y)] on the deck: `distance(t)` (metres along it at t seconds into the
    shot) moves her root, her feet step under her (IK on the planted handles), her hips bob and her left hand swings
    opposite her left foot. `pose` and `hips` are her standing pose; `head(t)` an extra turn of the head (x, y, z)."""
    import numpy as np

    from lib import vrm

    ch = built["vrm"]
    w = WALK
    targets = {side: ch.handles[f"{side}Foot-target"] for side in ("left", "right")}
    base = {side: ch.frame.T @ np.array(h.location) * ch.scale for side, h in targets.items()}
    hand = ch.handles.get("leftHand-target")
    hand0 = ch.frame.T @ np.array(hand.location) * ch.scale if hand else None
    for f in frames or range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        s = distance(t)
        (x, y), heading = path_at(path, s)
        place(built, (x, y), heading, frame=f)
        lifts = {}
        for side, phase in (("left", 0.0), ("right", 0.5)):
            ahead, up = step(s, w["stride"], w["stance"], phase)
            b = base[side]
            lifts[side] = ahead
            targets[side].location = ch.to_armature((b[0], b[1] - ahead, b[2] + up * w["lift"]))
            targets[side].keyframe_insert("location", frame=f)
        cyc = 2 * math.pi * s / (2 * w["stride"])
        bob = w["bob"] * math.cos(2 * cyc)
        turns = dict(pose)
        hx, hy, hz = turns.get("hips", (0.0, 0.0, 0.0))
        turns["hips"] = (hx, hy, hz + w["sway"] * math.sin(cyc))
        if head is not None:
            ax, ay, az = turns.get("head", (0.0, 0.0, 0.0))
            dx, dy, dz = head(t)
            turns["head"] = (ax + dx, ay + dy, az + dz)
        vrm.pose(ch, turns, hips=(hips[0], hips[1], hips[2] + bob), frame=f)
        if hand is not None:
            hand.location = ch.to_armature((hand0[0], hand0[1] - w["swing"] * math.sin(cyc + math.pi) * 0.5, hand0[2]))
            hand.keyframe_insert("location", frame=f)


# ---------------------------------------------------------------------------------------------------- the leavings

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


# ---------------------------------------------------------------------------------------------------- the camera

def drift(t: float, amount: float, seed: int = 1) -> tuple:
    """A held camera's breathing: a slow wander of about `amount` metres, (x, y, z)."""
    out = []
    for k in range(3):
        a = 0.0
        for j, (f, w) in enumerate(((0.13, 1.0), (0.31, 0.5), (0.71, 0.22))):
            a += w * math.sin(2 * math.pi * f * t + seed * 1.7 + k * 2.3 + j * 0.9)
        out.append(amount * a / 1.72)
    return tuple(out)


def camera(ctx, setup, *, name: str = "camera"):
    """A camera keyed every frame from `setup(t)` (t: seconds into the shot) -> (location, aim, lens mm, f-stop,
    focus point): its focus distance along its view to the focus point."""
    import bpy
    from mathutils import Vector

    from lib import rig

    cam = rig.engine_camera(name, size=ctx.size)
    cam.data.clip_end = 3000.0
    ctx.scene.camera = cam
    target = bpy.data.objects.new(f"{name}-aim", None)
    ctx.scene.collection.objects.link(target)
    c = cam.constraints.new("TRACK_TO")
    c.target = target
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        at, aim, lens, fstop, focus = setup(t)
        cam.location, target.location = at, aim
        cam.data.lens = lens
        cam.data.dof.aperture_fstop = fstop
        fwd = (Vector(aim) - Vector(at)).normalized()
        cam.data.dof.focus_distance = max(0.05, (Vector(focus) - Vector(at)).dot(fwd))
        cam.keyframe_insert("location", frame=f)
        target.keyframe_insert("location", frame=f)
        cam.data.keyframe_insert("lens", frame=f)
        cam.data.dof.keyframe_insert("aperture_fstop", frame=f)
        cam.data.dof.keyframe_insert("focus_distance", frame=f)
    return cam


# ---------------------------------------------------------------------------------------------------- compositing

def finish(ctx, st: Stage, setup=None, actors=None, lens_of=None):
    """Composite the cast over the world (lib/satsuei.py) with the schedule's look every frame, a setup's own on top
    (`setup(f, state)` -> satsuei.Look fields: rims, para_from, para_to, ...); the cast's outlines a width on screen
    (`lens_of(f)`: the lens at frame f)."""
    from mathutils import Vector

    from lib import satsuei, toon, vrm

    if actors and lens_of:
        for f in range(ctx.f0 - 1, ctx.f1 + 1):
            ctx.scene.frame_set(f)
            cam_at = Vector(ctx.scene.camera.matrix_world.translation)
            for built in actors.values():
                d = (cam_at - built["vrm"].face()).length
                vrm.key_outline(built["vrm"], vrm.outline_width(st.outline, d, lens_of(f)), f)
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
