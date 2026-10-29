"""The duel's stage, shared by its shots (shots/rise.py, standoff_vroid.py, eye_s.py, eye_t.py, freeze.py): the
crossing in the downpour (rf/sets.py), the 3D cast at their marks on the jetty (rf/vroid_cast.py) painted as anime
(blender/lib/toon3d.py) with a key of their own each, the rain falling in front of them, and the compositing that lays
them over the world (blender/lib/satsuei.py). A shot builds the stage, then keys its camera, its cast's acting and its
light frame by frame with the helpers here; the motion itself is rf/duel_motion.py's (pure, tested).

The world as rf/sets.py lays it out: the jetty along x (the bank and the hut at -x, its end and the moored boat at +x),
its deck's top at z 0, the river behind it toward +y. Shinza stands at the hut's end facing +x, Tsuru at the boat's end
facing him (turned a little toward the -y side, where the cameras mostly are).

Acting. `vrm.pose` sets a whole pose; a shot here keys turns on top of what the cast's builder posed (`Body`: the
pose as built, each frame's turns added about the character's axes, the IK handles' moves keyed with it), so the
builders' hands on the hilt and the pole and feet on the deck stay as they made them while the body breathes, sways
and moves. The wind in hair and hanging cloth turns VRoid's secondary chains (J_Sec_*) the same way.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import duel_motion as dm

MARKS = {"shinza": (-2.3, 0.0), "tsuru": (2.35, 0.05)}
TURNS = {"shinza": 0.0, "tsuru": math.pi + 0.3}    # Tsuru turned 0.3 rad from him toward the -y side
OUTLINE = 0.0018      # the cast's outline, in frame heights
KEY_ANGLE = 5.0       # degrees: an overcast key's soft-edged shadows
# how each part is painted (toon3d.Tone's fields), as the standoff's cels are: rain-cooled shades (skin to a mauve,
# cloth and hair to a slate blue), a deep 2nd shade in the creases, the face kept a little more lit, wet cloth and
# hair sheened, the lines a dark brown round skin and a dark blue round everything else; eyes and the drawn face flat
SKIN = dict(shade=(0.6, 0.47, 0.6), deep=(0.38, 0.28, 0.43), lit=(0.84, 0.79, 0.8), crease=0.35, flash=0.6, sink=0.35,
            line_mul=0.12, line_add=(0.022, 0.009, 0.009))
TONES = {
    "skin": SKIN,
    "face_skin": {**SKIN, "bias": 0.1, "cast": -0.2, "form": 0.6},
    "cloth": dict(shade=(0.55, 0.58, 0.76), deep=(0.3, 0.32, 0.5), crease=0.45, sheen=((0.05, 0.06, 0.08), 0.22, 1.0),
                  flash=0.03, sink=0.35, line_mul=0.22, line_add=(0.004, 0.006, 0.015)),
    "hair": dict(shade=(0.55, 0.6, 0.8), deep=(0.3, 0.34, 0.55), bias=-0.08, crease=0.35,
                 spec=((0.09, 0.11, 0.15), 0.25, 0.55, 1.0), sheen=((0.06, 0.07, 0.1), 0.2, 1.0), flash=0.03, sink=0.35,
                 line_mul=0.25, line_add=(0.004, 0.006, 0.018)),
    "face": dict(shaded=False, lit=(0.9, 0.9, 0.92), flash=0.3),
    "eye": dict(shaded=False, lit=(0.78, 0.8, 0.86), flash=0.4),
}
# ... and what is a character's own: his black hair lifted to a dark slate blue, so its shades and lines show
TONES_OF = {"shinza": {"hair": dict(lit=(1.9, 2.0, 2.5))}}
# the rain: a box of streaks over the jetty and the water in front of it (rf/sets.py's world), and the splashes
RAIN = dict(box_min=(-6.5, -3.6, -0.6), box_max=(6.5, 12.0, 5.5), count=5200, speed=9.5, wind=1.8, length=0.34,
            width=0.0055, color=(0.78, 0.81, 0.86), alpha=0.3, seed=4, near=3.5)
# the compositing's lights (linear): the cold sky, the hut's lantern (behind Shinza), the boat's (behind Tsuru)
SKY_RIM, LANTERN_RIM, BOAT_RIM = (0.6, 0.68, 0.85), (1.0, 0.5, 0.18), (0.95, 0.58, 0.26)
FLASH_COLOR = (0.85, 0.9, 1.0)
# VRoid's secondary chains the wind moves: the hair, and whatever cloth hangs on bones (a skirt's, a sleeve's)
HAIR, CLOTH = "J_Sec_Hair*", "J_Sec_*Skirt*"


@dataclass
class Stage:
    ctx: object
    scene: object
    crossing: dict
    look: object                     # the toon.Look the set and the cast fade to the fog with
    cast: object                     # the cast's collection (the compositor's own layer)
    actors: dict                     # name -> what the builder returned (rf/vroid_cast.py)
    keys: dict                       # name -> the character's own key light
    sun: object                      # the world's key
    rain: object | None = None
    rain_cast: object | None = None
    ink: object | None = None
    flash: dict = field(default_factory=dict)   # film frame -> the lightning's flash, 0..1
    bodies: dict = field(default_factory=dict)  # name -> Body

    def ch(self, name: str):
        return self.actors[name]["vrm"]


def stage(ctx, *, who=("shinza", "tsuru"), rain: dict | None = None, frozen: bool = False, ink: float | None = 0.0042,
          lightning=None, splashes: bool = True, sun_energy: float = 4.2) -> Stage:
    """The crossing with `who` at their marks, painted, under the rain (`rain`: RAIN's fields overridden; `frozen`:
    the drops hang where they are), the near set inked (`ink`: Line Art radius, m; None for none), lightning striking
    at `lightning` (s into the shot; default the look schedule's). The rain, the world's light and the keys' colour are
the look schedule's (data/look.json, ctx.look_at) at the shot's first frame. The camera, the acting and the
compositing are the shot's."""
    import bpy
    from mathutils import Vector

    from lib import toon, toon3d, vrm

    from . import sets, vroid_cast

    scene = ctx.scene
    sched = ctx.look_at(ctx.f0)
    light = sched.light
    if lightning is None:
        lightning = ctx.look.lightning
    scene.render.use_motion_blur = False   # drawn animation has no shutter (and the rain's drops wrap)
    scene.eevee.use_shadows = True
    scene.eevee.use_raytracing = True
    scene.view_settings.view_transform = "Standard"
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (*light.ambient, 1)   # a dim ambient: the cel bands come from the keys

    look = toon.Look(fog=sets.SKY, fog_near=18.0, fog_far=480.0, fog_max=0.9, fog_power=0.65)
    crossing = sets.crossing(look)
    ink_ob = toon.ink("ink-near", crossing["near"], radius=ink, crease=150) if ink else None

    # the world's key: overcast light from the upper left, behind the wide's shoulder
    sun = bpy.data.lights.new("key", "SUN")
    sun.angle = math.radians(3)
    sun.energy = sun_energy * light.key_strength
    sun.color = light.key
    key = bpy.data.objects.new("key", sun)
    scene.collection.objects.link(key)
    key.rotation_euler = Vector((0.55, 0.45, -0.7)).to_track_quat("-Z", "Y").to_euler()

    sr = sched.rain
    r = {**RAIN, **dict(count=sr.drops, speed=sr.speed, wind=sr.wind, length=sr.length, width=sr.width,
                        color=sr.color, alpha=sr.alpha), **(rain or {})}
    rain_ob = toon.rain("rain", r["box_min"], r["box_max"], count=r["count"], speed=r["speed"], wind=r["wind"],
                        length=r["length"], width=r["width"], color=r["color"], alpha=r["alpha"], seed=r["seed"],
                        near=r["near"], clear=r.get("clear", 1.2), frozen=frozen)

    cast = toon.collection("cast")
    cast_look = toon.Look(fog=look.fog, fog_near=look.fog_near, fog_far=look.fog_far, fog_max=look.fog_max,
                          fog_power=look.fog_power)
    toon.move_to(key, toon.collection("world-light"))   # the sun lights the set alone; each of the cast has a key
    actors, keys = {}, {}
    for name in who:
        actors[name] = built = getattr(vroid_cast, name)(cast, cast_look)
        built["root"].location = (*MARKS[name], 0.0)
        built["root"].rotation_euler = (0.0, 0.0, TURNS[name])
        bpy.context.view_layer.update()
        keys[name] = toon3d.key(f"{name}-key", [built["root"], *built["root"].children_recursive],
                                (1.0, -0.3, 0.8) if name == "shinza" else (-1.0, -0.3, 0.8), coll=cast,
                                angle=KEY_ANGLE, color=light.key,
                                energy=toon3d.ENERGY * light.key_strength)
        tones = {p: toon3d.Tone(**{**kw, **TONES_OF.get(name, {}).get(p, {})}) for p, kw in TONES.items()}
        vrm.anime(built["vrm"], tones, keys[name])
        vrm.smooth(built["vrm"])
    # the drops in front of them: the rain again in the cast's layer (only those over a figure pass the depth test)
    rain_cast = None
    if actors:
        rain_cast = rain_ob.copy()
        rain_cast.name = "rain-cast"
        cast.objects.link(rain_cast)
    if splashes and not frozen:
        toon.splashes("splash-deck", (sets.SPAN[0], -sets.HALF + 0.05, 0.004), (sets.SPAN[1], sets.HALF - 0.05, 0.004),
                      count=240, size=0.08, seed=5)
        toon.splashes("splash-river", (-7.5, -3.6, sets.WATER_Z + 0.002), (7.5, -1.15, sets.WATER_Z + 0.002),
                      count=340, size=0.11, alpha=0.45, seed=9)
    frames = range(ctx.f0 - 1, ctx.f1 + 1)
    flash = (toon.lightning(scene, list(lightning), frames, ctx.fps, ctx.f0) if lightning
             else {f: 0.0 for f in frames})
    st = Stage(ctx, scene, crossing, look, cast, actors, keys, sun, rain_ob, rain_cast, ink_ob, flash)
    for name in actors:
        st.bodies[name] = Body(st.ch(name))
    return st


def rain_input(rain_ob, which: str):
    """A socket of toon.rain's node group to key: "clear" (no drops nearer the lens than this, m) or "near" (drops
    nearer than this shrink with their distance)."""
    nodes = rain_ob.modifiers[0].node_group.nodes
    if which == "clear":
        return next(n.inputs[1] for n in nodes if n.bl_idname == "ShaderNodeMath" and n.operation == "GREATER_THAN")
    return next(n.inputs["From Max"] for n in nodes if n.bl_idname == "ShaderNodeMapRange")


# ---------------------------------------------------------------------------------------------------- the camera

def camera(ctx, *, lens: float = 35.0, fstop: float = 4.0, clip_start: float = 0.01):
    """The shot's camera on the engine's gate, aimed (TRACK_TO) at an empty its focus follows: (camera, aim)."""
    import bpy

    from lib import rig

    cam = rig.engine_camera("camera", fstop=fstop, size=ctx.size)
    cam.data.lens = lens
    cam.data.clip_start = clip_start
    cam.data.clip_end = 3000.0
    ctx.scene.camera = cam
    aim = bpy.data.objects.new("aim", None)
    ctx.scene.collection.objects.link(aim)
    c = cam.constraints.new("TRACK_TO")
    c.target = aim
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    cam.data.dof.focus_object = aim
    return cam, aim


def key_camera(cam, aim, f: int, at, to, *, lens: float | None = None, fstop: float | None = None,
               focus: float | None = None) -> None:
    """Key the camera at film frame f: where it is, what it looks at (its focus there, unless `focus` gives a
    distance), its lens (mm) and f-stop."""
    cam.location = tuple(at)
    aim.location = tuple(to)
    cam.keyframe_insert("location", frame=f)
    aim.keyframe_insert("location", frame=f)
    if lens is not None:
        cam.data.lens = lens
        cam.data.keyframe_insert("lens", frame=f)
    if fstop is not None:
        cam.data.dof.aperture_fstop = fstop
        cam.data.dof.keyframe_insert("aperture_fstop", frame=f)
    if focus is not None:
        cam.data.dof.focus_object = None
        cam.data.dof.focus_distance = focus
        cam.data.dof.keyframe_insert("focus_distance", frame=f)


def shake(t: float, amount: float, seed: int = 3) -> np.ndarray:
    """A hand-held camera's drift at time t (m, x y z), `amount` its size: slow incommensurate wanders."""
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 2 * math.pi, (3, 2))
    return amount * np.array([0.6 * math.sin(2 * math.pi * 0.37 * t + ph[i, 0]) + 0.4 * math.sin(2 * math.pi * 1.13 * t + ph[i, 1])
                              for i in range(3)])


# ---------------------------------------------------------------------------------------------------- per frame

def key_lines(st: Stage, f: int, cam_at, lens: float, frac: float = OUTLINE) -> None:
    """Every cast member's outline keyed to `frac` of the frame's height from the camera at `cam_at` with `lens`."""
    from mathutils import Vector

    from lib import vrm

    for built in st.actors.values():
        d = (Vector(cam_at) - built["vrm"].face()).length
        vrm.key_outline(built["vrm"], vrm.outline_width(frac, d, lens), f)


def key_light(st: Stage, f: int, toward: dict) -> None:
    """Each character's key from `toward` ({name: world direction}) at film frame f; the world's sun flares with the
    lightning."""
    from lib import toon3d

    for name, d in toward.items():
        toon3d.aim(st.keys[name], d, frame=f)
    st.sun.energy = (4.2 + 8.0 * st.flash.get(f, 0.0)) * st.ctx.look_at(f).light.key_strength
    st.sun.keyframe_insert("energy", frame=f)


def swing_lantern(st: Stage, f: int, t: float, gust: float = 0.0) -> None:
    """The hut's lantern swinging on its cord in the wind (harder in a gust)."""
    lantern = st.crossing["lantern"]
    a = 1.0 + 1.5 * gust
    lantern.rotation_euler = (math.radians(4 * a) * math.sin(2 * math.pi * 0.6 * t),
                              math.radians(2 * a) * math.sin(2 * math.pi * 0.45 * t + 1), 0)
    lantern.keyframe_insert("rotation_euler", frame=f)


def look(st: Stage, f: int, setup: dict, flash_toward=(0.8, 0.6)):
    """The compositing look (satsuei.Look) for film frame f: the look schedule's base for the shot with the setup's
    own on top (`setup`: rims as tuples, para_from, para_to, ...), lifted by the lightning: the grade let go, the
    para gone, a cold rim from the bolt's side and a fainter one all round."""
    from dataclasses import replace

    from lib import satsuei

    p = dict(setup)
    p["rims"] = tuple(satsuei.Rim(*r) if not isinstance(r, satsuei.Rim) else r for r in p.get("rims", ()))
    lk = st.ctx.look_at(f).look(**p)
    fl = st.flash.get(f, 0.0)
    if fl <= 0:
        return lk
    rims = lk.rims + ((satsuei.Rim(flash_toward, FLASH_COLOR, 1.3 * fl, 0.007, 1.0),)
                      if len(lk.rims) < satsuei.RIMS else ())
    return replace(lk, rims=rims, gain=tuple(g + (1 - g) * fl for g in lk.gain), para_amount=lk.para_amount * (1 - fl),
                   flash=0.35 * fl, flash_color=FLASH_COLOR)


def hold(*owners) -> None:
    """Make every key of these owners constant: a cut is a cut, never tweened (and a per-frame key never eased)."""
    from lib import toon

    for owner in owners:
        ad = getattr(owner, "animation_data", None)
        if ad is None or ad.action is None:
            continue
        for fc in toon._fcurves(ad.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


# ---------------------------------------------------------------------------------------------------- acting

class Body:
    """A character's pose as its builder left it, to key turns on top of frame by frame (`key`): every bone's
    rotation (the humanoid's and the secondary chains'), the hips' place and the IK handles'."""

    def __init__(self, ch):
        self.ch = ch
        pb = ch.armature.pose.bones
        for b in pb:
            b.rotation_mode = "QUATERNION"
        self.rot = {b.name: b.rotation_quaternion.copy() for b in pb}
        self.loc = {b.name: b.location.copy() for b in pb}
        self.handles = {k: (e.location.copy(), e.rotation_quaternion.copy() if e.rotation_mode == "QUATERNION"
                            else e.rotation_euler.to_quaternion()) for k, e in ch.handles.items()}
        self.rest = {b.name: np.array(ch.armature.data.bones[b.name].matrix_local.to_3x3()) for b in pb}
        from lib import vrm_rig

        self.hair = vrm_rig.chains(ch, HAIR)
        self.cloth = vrm_rig.chains(ch, CLOTH)

    def bone_name(self, bone: str) -> str:
        """The armature's name of a humanoid bone (or an armature bone's own name)."""
        from lib import vrm

        h = vrm.canonical(bone)
        return self.ch.bones.get(h, bone)

    def turn(self, name: str, rotation):
        """The quaternion of bone `name` (the armature's) at its built pose turned by `rotation` ((x, y, z) degrees
        about the character's axes, or a 3x3) after it."""
        from mathutils import Matrix

        from lib import vrm

        d = vrm.local_rotation(self.rest[name], self.ch.frame, rotation)
        return Matrix(d.tolist()).to_quaternion() @ self.rot[name]

    def key(self, f: int, turns: dict | None = None, *, hips=(0.0, 0.0, 0.0), moves: dict | None = None,
            chains: dict | None = None, keep=()) -> None:
        """Key the whole body at film frame f: `turns` ({humanoid or armature bone: (x, y, z) degrees}) on top of
        the built pose (every other bone back at it), the hips moved by `hips` (m, character's axes) from where they
        were built, the IK handles in `moves` ({handle key: (x, y, z) m in the character's frame, added}) and the
        rest where they were (but those in `keep`, keyed as they stand: a hand a shot moved itself with vrm.grasp), and
        `chains` ({armature bone: turn}) for hair and cloth."""
        from mathutils import Vector

        from lib import vrm

        turns = {self.bone_name(k): v for k, v in (turns or {}).items()}
        turns.update(chains or {})
        pbs = self.ch.armature.pose.bones
        for name, q in self.rot.items():
            pb = pbs[name]
            pb.rotation_quaternion = self.turn(name, turns[name]) if name in turns else q
            pb.keyframe_insert("rotation_quaternion", frame=f)
        hp = pbs[self.ch.bones["hips"]]
        hp.location = self.loc[hp.name] + Vector(vrm.offset_local(self.rest[hp.name], self.ch.frame,
                                                                  np.asarray(hips, float) / self.ch.scale))
        hp.keyframe_insert("location", frame=f)
        for k, e in self.ch.handles.items():
            loc0, q0 = self.handles.get(k, (e.location.copy(), None))
            if k in keep:
                pass
            elif moves and k in moves:
                e.location = loc0 + Vector(self.ch.frame @ (np.asarray(moves[k], float) / self.ch.scale))
            elif k in self.handles:
                e.location = loc0
                if q0 is not None and e.rotation_mode == "QUATERNION":
                    e.rotation_quaternion = q0
            e.keyframe_insert("location", frame=f)
            if e.rotation_mode == "QUATERNION":
                e.keyframe_insert("rotation_quaternion", frame=f)

    def sway(self, t: float, *, amount: float = 6.0, cloth: float = 3.0, toward=(0.0, 1.0, 0.0), seed: int = 0,
             at=()) -> dict:
        """The wind through the hair and the hanging cloth at time t: each chain swung about the axis square to the
        wind (`toward`, the character's frame) and up, by up to `amount` degrees (`cloth` for cloth), most at its
        tip, each strand out of step with the next. Returns the chains' turns, for `key`."""
        w = np.asarray(toward, float)
        axis = np.cross((0.0, 0.0, 1.0), w)
        axis = axis / (np.linalg.norm(axis) or 1.0)
        out = {}
        for group, size in ((self.hair, amount), (self.cloth, cloth)):
            for i, chain in enumerate(group):
                n = len(chain)
                for j, bone in enumerate(chain):
                    k = (j + 1) / n
                    deg = size * dm.sway(t, k, seed=seed + 31 * i, at=at) / n
                    lean = 0.35 * size * dm.wind(t, seed + 31 * i, at=at) / n    # the wind's steady push
                    out[bone] = _axis_turn(axis, deg + lean)
        return out


def _axis_turn(axis, degrees: float) -> np.ndarray:
    """The rotation (3x3) by `degrees` about `axis`."""
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    t = math.radians(degrees)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K


def to_frame(ch, w) -> np.ndarray:
    """A world point in a character's frame (vrm.Character.world's inverse)."""
    m = np.array(ch.armature.matrix_world.inverted())
    a = m[:3, :3] @ np.asarray(w, float) + m[:3, 3]
    return ch.scale * (ch.frame.T @ a)


def dir_to_frame(ch, d) -> np.ndarray:
    """A world direction in a character's frame."""
    v = to_frame(ch, np.asarray(d, float)) - to_frame(ch, np.zeros(3))
    return v / np.linalg.norm(v)


def breathing(t: float, rate: float, depth: float = 1.0, phase: float = 0.0) -> dict:
    """A breath's turns at time t (rate breaths a second, `depth` 1 for a calm one): the chest lifting and opening,
    the shoulders rising with it, the head settling against it."""
    b = dm.breath(t, rate, phase) * depth
    return {"spine": (-0.8 * b, 0.0, 0.0), "chest": (-1.2 * b, 0.0, 0.0), "upperChest": (-1.5 * b, 0.0, 0.0),
            "leftShoulder": (0.0, -2.0 * b, 0.0), "rightShoulder": (0.0, 2.0 * b, 0.0), "neck": (1.2 * b, 0.0, 0.0),
            "head": (1.0 * b, 0.0, 0.0)}


def add(*poses) -> dict:
    """Turns summed bone by bone (small turns add near enough as Euler angles)."""
    out: dict = {}
    for p in poses:
        for k, v in p.items():
            out[k] = tuple(a + b for a, b in zip(out.get(k, (0.0, 0.0, 0.0)), v))
    return out
