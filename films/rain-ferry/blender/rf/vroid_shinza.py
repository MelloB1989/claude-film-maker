"""Shinza from his VRoid Studio model (films/rain-ferry/assets/vroid/shinza.vrm), dressed as STORY.md has him, with
what VRoid does not make (blender/lib/props.py): his nodachi in its plain black scabbard slung across his back (hilt
over his right shoulder, its cord across his chest), his straw kasa (worn low, or hanging on his back by its cord), his
faded vermilion headband knotted at the back with its two tails, the cord tying back his sleeves (a tasuki crossed on
his back), his obi and straw sandals. VRoid dresses him in a shirt and a long pleated skirt; the core's
blender/lib/vrm_rig.py makes them a patched charcoal kimono (one colour, the shirt's collar cut away for a kimono's V
and its collar laid crossing the chest) and a tattered dark hakama let down to his ankles; a thin pale scar runs
through his left eyebrow, his hair is cut short and ragged, his bangs parted off his eyes, his face a closed-mouthed
glare.

    shinza(coll, look, kasa="back", sword="hand", headband=True, wet=1.0, pose=None)

  kasa      "on" (on his head, its brim low over his eyes), "back" (hanging between his shoulders by its cord) or None
  sword     "back" (sheathed on his back), "hand" (drawn: in his hands, the empty scabbard still on his back) or
            "broken" (half the blade in his hands, the other half a separate prop, `parts["half"]`)
  headband  False: none (after it is cut off; `parts["headband"]` is then empty)
  wet       1 soaked (the standoff) to 0 dry (after the rain): cloth and hair darker, cooler and sheened, the bangs
            hanging heavy, the props' straw, cord and cloth darker
  pose      "guard" (the standoff's low guard, both hands on the hilt) or "stand" (standing easy, arms down); by
            default "guard" with a sword in hand, "stand" with it on his back

Returns rf/vroid_cast.py's dict, and "parts": {"kasa", "sheath", "sword", "half", "headband", "obi", "tasuki",
"sandals"}, each a list of objects (a list's first is the one to move: the rest of a prop is carried by it or by the
same bone). What carries what is rf/vroid_common.py's: the sword in hand by rightHand (in the guard the left hand holds
it by IK: ch.handles["leftHand-target"]), sheathed by upperChest with the scabbard; the kasa on his head by head, on his
back by upperChest; the headband by head; `half` by his root alone (stuck point-down in the planks in front of him).
"""
from __future__ import annotations

import math

import numpy as np

from lib import anime, props, vrm, vrm_rig, vrm_skin as skin

from .vroid_common import CLOTH_FLASH, HEIGHT, colors, plant, sandals, soak, vrm_file

MM = 1e-3

# ---- Shinza's low guard (his frame: front -y, left +x; metres as he stands): the hips dropped and forward, right foot
# ahead, the left back on its ball and turned out, the trunk leaning in, the head up to her; the hilt a fist in front
# of his navel, forward and down, the blade on toward her shins. VRoid's arms are short (0.47 m shoulder to wrist): the
# hands are where they reach with the elbows still bent (the left fist on the pommel, the right a fist and a half up the
# hilt)
SH_HIPS = (0.0, -0.04, -0.15)
SH_POSE = {"hips": (0.0, 0.0, 10.0), "spine": (9.0, 0.0, -5.0), "chest": (6.0, 0.0, -3.0), "upperChest": (2.0, 0.0, 0.0),
           "neck": (-7.0, 0.0, -2.0), "head": (-9.0, 0.0, 0.0),
           "leftShoulder": (0.0, 8.0, -6.0), "rightShoulder": (0.0, -8.0, 6.0),
           "leftFoot": (0.0, 0.0, 0.0), "leftToes": (-30.0, 0.0, 0.0)}
SH_FEET = {"right": ((-0.12, -0.36, 0.095), (-0.15, -1.2, 0.5), (0.0, 0.0, -8.0)),
           "left": ((0.15, 0.4, 0.16), (0.35, -0.8, 0.5), (32.0, 0.0, 30.0))}
POMMEL = np.array((0.01, -0.16, 0.96))
HILT_DIR = np.array((0.0, -0.91, -0.45))
GRIPS = {"left": 0.045, "right": 0.16}      # each hand's hole along the hilt from the pommel (m)
TSUKA = 0.013                               # the hilt's half thickness (props.katana's wrap), for the fingers
SH_ELBOWS = {"left": (0.55, 0.15, 0.6), "right": (-0.55, -0.05, 0.6)}
# ---- standing easy: the arms down (vrm.RELAXED), the weight a little on the left leg, the head up
STAND_POSE = {**vrm.RELAXED, "hips": (0.0, 0.0, 4.0), "spine": (2.0, 2.0, -2.0), "neck": (-3.0, 0.0, 0.0),
              "head": (-3.0, -2.0, -3.0), "leftUpperLeg": (0.0, 2.0, 0.0), "rightUpperLeg": (-4.0, -3.0, 0.0),
              "rightLowerLeg": (6.0, 0.0, 0.0)}
# ---- his nodachi: longer than a katana in hilt and blade, a shallow curve; its scabbard a little longer than the blade
NODACHI = dict(hilt=0.33, blade=0.9, sori=0.014)
BROKEN = 0.48          # where it snaps (of the blade from the guard)
SAYA = 0.93
# slung across his back (his frame, at rest): the scabbard's mouth behind his right shoulder blade, its end behind his
# left hip, `BACK_OFF` off his back (over the kimono and the tasuki; the kasa hangs over it)
SAYA_MOUTH = (-0.13, 1.43)      # (x, z)
SAYA_END = (0.2, 0.69)
BACK_OFF = 0.03
# the scabbard's cord: tied to it below the mouth, over his right shoulder and across his chest to his left side,
# round under his left arm to its end (points on his front, the collar laid on him)
SAGEO = [(-0.12, 0.06, 1.47), (-0.12, -0.04, 1.45), (-0.09, -0.11, 1.36), (-0.02, -0.135, 1.22),
         (0.07, -0.13, 1.09), (0.14, -0.08, 0.98), (0.17, 0.02, 0.94), (0.15, 0.1, 0.9)]
# the tasuki: a cord from the front of each shoulder over it, crossing on his back to under the other arm and round to
# the front of it again (his right shoulder's; the left mirrored)
TASUKI = [(-0.11, -0.08, 1.41), (-0.12, 0.0, 1.46), (-0.08, 0.1, 1.38), (0.0, 0.12, 1.27), (0.09, 0.11, 1.17),
          (0.15, 0.05, 1.14), (0.16, -0.04, 1.17)]
# ---- the kasa: wide, shallow; on his head its brim tipped down in front (worn low, over the eyes), resting a little
# into his hair; on his back hung between the shoulders, its brim against his back, on a cord round his throat
KASA = dict(radius=0.31, height=0.115)
KASA_ON = dict(tip=11.0, sink=0.025)     # degrees forward, metres down into the hair
KASA_BACK = (0.0, 1.17, 9.0)             # its middle's (x, z) and its top tipped in onto him (degrees)
# ---- the scar: a thin pale line through his left eyebrow, slanting a little from above the brow down onto the lid's
# fold (points: x out from the brow's middle along it, z up from the brow; metres on the face's front view)
SCAR = [(-1.5 * MM, 11 * MM), (0.0, 3 * MM), (1.2 * MM, -5 * MM), (2.0 * MM, -10 * MM)]
SCAR_COLOR = (0.98, 0.86, 0.8)
# ---- his face, of the VRoid face's parts (vrm_rig.compose): VRoid's angry preset bares the teeth in a grin, so the
# glare is the angry brows (down and drawn in) and eyes (the lids flattened) over a set, closed mouth turned down; his
# eyes narrow further (`face(eyes)`) toward NARROWED, the lids coming down
GLARE = {"Fcl_BRW_Angry": 1.0, "Fcl_EYE_Angry": 0.8, "Fcl_MTH_Sorrow": 0.5}
NARROW = {"Fcl_EYE_Angry": 0.2, "Fcl_EYE_Close": 0.25}
NARROWED = 0.75
# ---- his bangs parted off his eyes and brows: the front strands (VRoid's chains 06..09, which hang across his face)
# swept to their own sides (degrees) and a little down, heavy with the rain, framing his face; the middle one (05), a
# wide clump over his brows, thinned (width, length) and tipped forward off them: a wet lock under the headband
BANGS = ("J_Sec_Hair1_06", "J_Sec_Hair1_07", "J_Sec_Hair1_08", "J_Sec_Hair1_09")
PART = (100.0, 0.2)
MIDDLE = ("J_Sec_Hair1_05", (0.0, -1.0, 0.4), 25.0, (0.35, 0.75))
# his hair cut short and ragged: every strand below the ears (the back and sides) shortened and thinned at its root,
# each a little differently, so its ends fall unevenly (a strand's root height (m) under which it is cut; length range)
TRIM = (1.6, (0.55, 0.8), 0.85)
# ---- his clothes (heights at rest, metres as he stands). The kimono and hakama one colour each (linear lit, shade),
# their prints gone and their folds kept (vrm_rig.recolor): a faded charcoal kimono, the hakama darker
KIMONO = ((0.055, 0.056, 0.064), (0.018, 0.019, 0.026))
HAKAMA = ((0.04, 0.042, 0.05), (0.014, 0.015, 0.021))
CLOTH_INK = (0.006, 0.006, 0.009)      # their outlines
# patches sewn on (a box in his frame: centre (x, y, z), half sizes; the faces in it painted `PATCH` times the cloth's
# own): the kimono's left shoulder blade and right forearm, the hakama's left knee
PATCHES = [("Tops", (0.09, 0.12, 1.3), (0.06, 0.06, 0.05), 1.55), ("Tops", (-0.33, 0.0, 1.07), (0.05, 0.08, 0.04), 1.4),
           ("Bottoms", (0.1, -0.12, 0.55), (0.06, 0.06, 0.06), 1.5)]
# the hakama let down from just under the knee to the ankles, flaring; its hem torn (faces below `TATTER` cut away in
# a ragged line: how high a tear may run, metres)
HEM = (0.55, 0.075, 0.3)
TATTER = 0.07
# the kimono's V: the shirt's collar cut away above NECK in front of NAPE (behind it, it stands under the kimono's
# collar) and the shirt in front down to CROSS, V_HALF either side at NECK; the skin under it painted (VRoid paints the
# body under clothes white)
NECK, NAPE, CROSS, V_HALF = 1.45, 0.02, 1.27, 0.075
# the body hidden under the kimono (above the hips, below the neck, the arms to short of the wrists) cut away: where his
# elbows fold to the hilt it pokes through the sleeves
UNDER = (0.95, NECK - 0.03, 0.55)
# its collar, a dark band laid along these points (his frame, near the surface), left side over right: from the back of
# the neck round its left side and down across the chest to the obi at his right; the right side's to the crossing
ERI = [(0.0, 0.08, 1.455), (0.045, 0.06, 1.455), (0.075, 0.02, 1.45), (0.083, -0.05, 1.43), (0.066, -0.11, 1.38),
       (0.033, -0.135, 1.31), (0.0, -0.14, 1.26), (-0.045, -0.14, 1.2), (-0.07, -0.135, 1.14)]
ERI_UNDER = [(-x, y, z) for x, y, z in ERI[:7]]
ERI_WIDTH = [0.06, 0.055, 0.045] + [0.042] * 6        # standing taller at the nape
# the under-kimono's collar, a pale line along each collar's inner edge down to the crossing (width; each side's way
# inward across its band)
JUBAN = (0.012, {0: -1.0, 1: 1.0})
SH_COLORS = {"eri": ((0.028, 0.03, 0.04), (0.01, 0.011, 0.017)), "juban": ((0.42, 0.44, 0.47), (0.16, 0.17, 0.2))}


def shinza(coll, look, name: str = "shinza", *, kasa: str | None = "back", sword: str = "hand", headband: bool = True,
           wet: float = 1.0, pose: str | None = None) -> dict:
    if kasa not in ("on", "back", None) or sword not in ("back", "hand", "broken"):
        raise ValueError(f"shinza: kasa={kasa!r} (on, back, None), sword={sword!r} (back, hand, broken)")
    pose = pose or ("guard" if sword in ("hand", "broken") else "stand")
    # his collars, obi, hilt wrap and cords whiten in the strike as his kimono does
    m = anime.palette(colors(wet, SH_COLORS), look, prefix=name, cuts={"steel": 0.55},
                      flashes={k: CLOTH_FLASH for k in ("eri", "juban", "obi", "wrap", "cord")})
    ch = vrm.load(vrm_file(name), coll, name=name)
    vrm.scale_to(ch, HEIGHT["shinza"])
    soak(ch, wet)
    vrm.flash(ch)
    is_shinza = vrm_file(name).stem == name     # the stand-in keeps its face and hair
    body = dress(ch, m, name)
    if is_shinza:
        scar(ch)
    parts = {k: [] for k in ("kasa", "sheath", "sword", "half", "headband", "obi", "tasuki", "sandals")}
    # what VRoid does not make, tied on at rest: the obi over the top's waist, the headband over his hair across the
    # forehead, knotted at the back with its two tails, the cords on his kimono
    eye = ch.rest("leftEye")[2] - ch.rest("head")[2]
    parts["obi"] = vrm.band(ch, f"{name}-obi", "spine", 0.0, 0.075, material=m["obi"], push=0.006, thickness=0.006,
                            limit=0.24)
    if headband:
        parts["headband"] = vrm.band(ch, f"{name}-band", "head", eye + 0.045, 0.028, material=m["band"], push=0.002,
                                     thickness=0.003, tilt=-6.0, limit=0.16, knot=0.018,
                                     tails=[(0.3, 0.03, 18.0), (0.24, 0.028, -14.0)])
    if body is not None:
        on = [(body, vrm_rig.faces_of(body, "Tops"))]
        for k, path in enumerate((TASUKI, [(-x, y, z) for x, y, z in TASUKI])):
            parts["tasuki"].append(vrm_rig.collar(ch, f"{name}-tasuki{k}", path, 0.011, on=on, material=m["cord"],
                                                  push=0.006 + 0.002 * k, thickness=0.006))
        parts["sheath"].append(vrm_rig.collar(ch, f"{name}-sageo", SAGEO, 0.014, on=on, material=m["cord"], push=0.01,
                                              thickness=0.004))
    # slung on his back at rest, carried by his upper chest: the scabbard (and in it the sword), the kasa on its cord
    carrier = "upperChest" if ch.has("upperChest") else "chest"
    mouth, d, flat = _slung(ch, body)
    sheath = props.saya(f"{name}-saya", m, coll, tuple(ch.world(mouth)), _w(ch, d), SAYA, sori=NODACHI["sori"],
                        edge=_w(ch, -flat))
    for ob in sheath[:1]:
        vrm.attach(ob, ch, carrier)
    parts["sheath"] = sheath + parts["sheath"]
    if sword == "back":
        # sheathed: the guard just above the mouth, the hilt up over his right shoulder; carried by the scabbard
        pommel = mouth - d * (NODACHI["hilt"] + 0.004)
        parts["sword"] = _nodachi(ch, m, coll, name, pommel, d, flat)
        anime.attach(parts["sword"][:1], sheath[0])
        anime.attach(parts["sword"][1:], parts["sword"][0])
    if kasa == "back":
        parts["kasa"] = _kasa_back(ch, m, coll, name, body)
        vrm.attach(parts["kasa"][0], ch, carrier)
    elif kasa == "on":
        parts["kasa"] = _kasa_on(ch, m, coll, name)
        vrm.attach(parts["kasa"][0], ch, "head")

    if pose == "guard":
        hilt = HILT_DIR / np.linalg.norm(HILT_DIR)
        fingers = {}
        for side, along in GRIPS.items():
            # the knuckles along the hilt (index toward the blade), the palm down onto it and in from his side; each
            # finger wrapped round it (vrm_rig.wrap), not every hand curled alike
            palm = np.array((1.0 if side == "right" else -1.0, 0.0, -0.6))
            vrm.grasp(ch, side, POMMEL + hilt * along, hilt, palm, pole=SH_ELBOWS[side])
            fingers.update(vrm_rig.wrap(ch, side, TSUKA))
        vrm.pose(ch, {**SH_POSE, **fingers}, hips=SH_HIPS)
        plant(ch, SH_FEET)
    else:
        vrm.pose(ch, STAND_POSE)
        plant(ch, {"left": ((0.1, 0.0, ch.rest("leftFoot")[2]), (0.1, -1.0, 0.45), (0.0, 0.0, 10.0)),
                   "right": ((-0.11, -0.04, ch.rest("rightFoot")[2]), (-0.1, -1.0, 0.45), (0.0, 0.0, -12.0))})
    if is_shinza:
        parts["sandals"] = sandals(ch, m, coll, name, size=1.12, ties=True)

    if sword in ("hand", "broken"):
        # in his hands: in the guard where the fists close; standing, hanging from his right hand, point down
        if pose == "guard":
            p0, hd = ch.world(POMMEL), _w(ch, HILT_DIR)
        else:
            wrist = np.array(ch.point("rightHand"))
            p0 = ch.point("rightHand") + ch.root.matrix_world.to_3x3() @ _v((0.0, -0.02, -0.06))
            hd = np.array(ch.point("rightMiddleProximal")) - wrist
            hd = _unit(hd + np.array((0.0, 0.0, -0.4)))
        blade = props.katana(f"{name}-nodachi", m, tuple(p0), tuple(hd), side=_side(ch), coll=coll,
                             broken=BROKEN if sword == "broken" else None, **NODACHI)
        for ob in blade:
            vrm.attach(ob, ch, "rightHand")
        if sword == "broken":
            *blade, half = blade
            parts["half"] = [_stuck(ch, half)]
        parts["sword"] = blade

    if is_shinza:
        vrm_rig.compose(ch, "glare", GLARE)
        vrm_rig.compose(ch, "narrow", NARROW)
        hair(ch, wet)

    def face(eyes: float = 1.0) -> dict:
        """A hard glare, the mouth shut; narrowing as `eyes` falls from 1 to NARROWED."""
        if not is_shinza:
            return {"angry": 0.6 + 0.4 * min(1.0, max(0.0, (1.0 - eyes) / (1.0 - NARROWED)))}
        return {"glare": 1.0, "narrow": min(1.0, max(0.0, (1.0 - eyes) / (1.0 - NARROWED)))}

    vrm.express(ch, face())
    flat_props = [ob for k in parts for ob in parts[k]]
    return {"root": ch.root, "vrm": ch, "head": tuple(ch.face()), "face": face, "props": flat_props, "parts": parts}


# ---------------------------------------------------------------------------------------------------- where things go

def _v(p):
    from mathutils import Vector

    return Vector(tuple(float(c) for c in p))


def _unit(v) -> np.ndarray:
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def _w(ch, d) -> tuple:
    """A direction of his frame in the world."""
    return tuple(np.array(ch.world(np.asarray(d, float))) - np.array(ch.world((0.0, 0.0, 0.0))))


def _side(ch) -> tuple:
    """A held blade's flat faces his left and right (the world's way of his +x)."""
    return _w(ch, (1.0, 0.0, 0.0))


def back_y(ch, body, x: float, z: float, *, reach: float = 0.035) -> float:
    """How far behind his middle his back (or what he wears there) is at (x, z), his frame at rest."""
    pts = np.concatenate([vrm_rig._to_frame(ch, ob)[0] for ob in ch.meshes])
    near = pts[(np.abs(pts[:, 0] - x) < reach) & (np.abs(pts[:, 2] - z) < reach) & (pts[:, 1] > 0.0)]
    return float(near[:, 1].max()) if len(near) else 0.12


def _slung(ch, body) -> tuple:
    """(mouth, its way down, the blade's flat) of the scabbard slung across his back, his frame at rest."""
    (mx, mz), (ex, ez) = SAYA_MOUTH, SAYA_END
    mouth = np.array((mx, back_y(ch, body, mx, mz) + BACK_OFF, mz))
    end = np.array((ex, back_y(ch, body, ex, ez) + BACK_OFF, ez))
    d = _unit(end - mouth)
    return mouth, d, np.array((0.0, 1.0, 0.0))     # its flat against his back


def _nodachi(ch, m, coll, name, pommel, d, flat) -> list:
    """The nodachi along `d` from `pommel` (his frame at rest), its flat facing `flat`, sheathed."""
    return props.katana(f"{name}-nodachi", m, tuple(ch.world(pommel)), _w(ch, d), side=_w(ch, flat), coll=coll,
                        **NODACHI)


def _stuck(ch, half):
    """The snapped-off half where it falls: stuck point-down in the planks a pace in front of him, leaning, carried by
    his root (a shot moves it)."""
    import bpy
    from mathutils import Matrix

    bpy.context.view_layer.update()
    mw = half.matrix_world.copy()
    co = np.array([mw @ v.co for v in half.data.vertices])
    rings = co.reshape(-1, 4, 3)       # props.katana's blade: four points a ring
    root_c, tip_c = rings[0].mean(0), rings[-1].mean(0)
    # turn it point down, leaning 20 degrees toward him, its point 4 cm into the deck at (0.05, -0.75) in his frame
    goal = np.array(ch.world((0.05, -0.75, -0.04)))
    lean = _unit(np.array(_w(ch, (0.0, 0.35, 0.0))) + np.array((0.0, 0.0, -1.0)))
    have = _unit(tip_c - root_c)
    axis = np.cross(have, lean)
    ang = math.atan2(np.linalg.norm(axis), float(np.dot(have, lean)))
    rot = Matrix.Rotation(ang, 4, _v(axis if np.linalg.norm(axis) > 1e-9 else (1.0, 0.0, 0.0)))
    half.parent = None
    half.matrix_world = Matrix.Translation(_v(goal)) @ rot @ Matrix.Translation(_v(-tip_c)) @ mw
    anime.attach([half], ch.root)
    return half


def _place(ob, ch, at, x, z) -> None:
    """Put `ob` (built at the world's origin, its axes the world's) at `at` with its x and z along `x` and `z` (his
    frame)."""
    from mathutils import Matrix

    z = _unit(z)
    x = _unit(np.asarray(x, float) - z * np.dot(x, z))
    y = np.cross(z, x)
    w = np.column_stack([_w(ch, x), _w(ch, y), _w(ch, z)])
    mat = Matrix.Identity(4)
    for i in range(3):
        for j in range(3):
            mat[i][j] = float(w[i, j])
    mat.translation = ch.world(at)
    ob.matrix_world = mat


def head_fit(ch) -> tuple:
    """(the top of his head (x, y, z), how wide it is across 6 cm under that), his frame at rest: where a hat sits."""
    pts = np.concatenate([vrm_rig._to_frame(ch, ob)[0] for ob in ch.meshes])
    head = ch.rest("head")
    near = pts[(np.hypot(pts[:, 0] - head[0], pts[:, 1] - head[1]) < 0.16) & (pts[:, 2] > head[2])]
    crown = near[np.argmax(near[:, 2])]
    ring = near[np.abs(near[:, 2] - (crown[2] - 0.06)) < 0.01]
    r = float(np.median(np.hypot(ring[:, 0] - crown[0], ring[:, 1] - crown[1]))) if len(ring) else 0.09
    return crown, r


def _kasa_on(ch, m, coll, name) -> list:
    """The kasa on his head, its brim tipped down in front, worn low; its cords down past his cheeks to under his
    chin. Built at rest; the caller carries it by his head."""
    from lib import shapes

    hat = props.kasa(f"{name}-kasa", m, coll, **KASA)
    crown, r = head_fit(ch)
    seat = props.kasa_seat(KASA["radius"], KASA["height"], r + 0.01) + 0.06
    a = math.radians(KASA_ON["tip"])
    up = np.array((0.0, math.sin(a), math.cos(a)))          # its apex leaning back: the brim down in front
    at = crown - up * (seat + KASA_ON["sink"])
    _place(hat[0], ch, at, (1.0, 0.0, 0.0), up)
    # the cords: from inside the brim at each side down past the cheeks, tied under the chin
    chin = np.array((0.0, ch.rest("head")[1] - 0.06, ch.rest("head")[2] - 0.035))
    for k, s in enumerate((1.0, -1.0)):
        top = at + np.array((s * 0.085, 0.01, 0.025))
        path = [ch.world(p) for p in (top, top + np.array((s * 0.01, -0.03, -0.07)),
                                      chin + np.array((s * 0.045, 0.0, 0.0)), chin)]
        cord = shapes.loft(f"{name}-kasa-cord{k}", [tuple(p) for p in path], 0.0022, material=m["cord"], coll=coll, n=6,
                           subsurf=0)
        cord["outline"] = False
        hat.append(cord)
    anime.attach(hat[2:], hat[0])
    return hat


def _kasa_back(ch, m, coll, name, body) -> list:
    """The kasa hung on his back by its cord, its brim against him over the scabbard, the cord over his shoulders and
    round his throat. Built at rest; the caller carries it by his upper chest."""
    from lib import shapes

    hat = props.kasa(f"{name}-kasa", m, coll, **KASA)
    x, z, tip = KASA_BACK
    y = max(back_y(ch, body, x, z), back_y(ch, body, x, z + 0.15)) + BACK_OFF + 0.03
    a = math.radians(tip)
    out = np.array((0.0, math.cos(a), -math.sin(a)))       # its apex out from his back, its top tipped in
    at = np.array((x, y, z))
    _place(hat[0], ch, at, (1.0, 0.0, 0.0), out)
    if body is not None:
        # the cord: from the brim's top over each shoulder by the neck to the throat, knotted there
        brim = at + np.array((0.0, 0.0, KASA["radius"] * 0.95))
        path = [(0.07, 0.07, 1.47), (0.075, -0.02, 1.455), (0.0, -0.075, 1.415), (-0.075, -0.02, 1.455),
                (-0.07, 0.07, 1.47)]
        hat.append(vrm_rig.collar(ch, f"{name}-kasa-tie", path, 0.006, on=[(body, vrm_rig.faces_of(body, "Tops")),
                                                                          (body, vrm_rig.faces_of(body, "SKIN"))],
                                  material=m["cord"], push=0.004, thickness=0.004))
        for k, s in enumerate((1.0, -1.0)):
            ends = [brim + np.array((s * 0.12, -0.01, -0.03)), np.array((s * 0.08, brim[1] - 0.06, 1.48)),
                    np.array((s * 0.07, 0.07, 1.47))]
            cord = shapes.loft(f"{name}-kasa-cord{k}", [tuple(ch.world(p)) for p in ends], 0.0025, material=m["cord"],
                               coll=coll, n=6, subsurf=0)
            cord["outline"] = False
            hat.append(cord)
        anime.attach([ob for ob in hat[2:] if ob.parent is None], hat[0])
    return hat


# ---------------------------------------------------------------------------------------------------- his face, hair

def scar(ch) -> None:
    """A thin pale scar through his left eyebrow: painted into the face's skin and cut through the brow."""
    face = next(ob for binds in ch.expressions.values() for ob, _, _ in binds)
    lm = skin.face_landmarks(face)
    e = lm["left"]
    mid = (e["brow_inner"] + e["brow_outer"]) / 2
    path = [(mid[0] + dx, -0.2, mid[2] + dz) for dx, dz in SCAR]
    face_skin = next(mt for mt in ch.materials("skin") if face.material_slots.find(mt.name) >= 0)
    surf = skin.surface(face, face_skin)
    mark = skin.Mark(path, 1.1 * MM, color=SCAR_COLOR, strength=0.85, taper=(0.3, 0.4), blend="mix")
    skin.retexture(face_skin, lambda px: skin.paint(px, surf, [mark], along=(0.0, 1.0, 0.0)), scale=2, tag="scar")
    # the brow parted where the scar crosses it: its alpha cleared under a slightly wider stroke
    brow = next(mt for mt in ch.materials() if "FaceBrow" in mt.name)
    bsurf = skin.surface(face, brow)

    def part_brow(px):
        mask = np.zeros_like(px)
        skin.paint(mask, bsurf, [skin.Mark(path, 1.8 * MM, color=(1.0, 1.0, 1.0), strength=1.0, taper=(1.0, 1.0),
                                           blend="mix")], along=(0.0, 1.0, 0.0))
        px[..., 3] *= 1.0 - mask[..., 0]
        return px

    skin.retexture(brow, part_brow, tag="scar")


def hair(ch, wet: float) -> None:
    """His bangs parted off his eyes (hanging heavier the wetter), the middle lock thinned and tipped forward, the
    longer strands cut short and ragged."""
    bangs = [c for c in vrm_rig.chains(ch) if c[0] in BANGS]
    vrm_rig.part(ch, bangs, PART[0], down=PART[1] * wet)
    rng = np.random.default_rng(11)
    for chain in vrm_rig.chains(ch):
        if chain[0] == MIDDLE[0]:
            vrm_rig.sweep(ch, chain, MIDDLE[1], MIDDLE[2])
            vrm_rig.thin(ch, chain, *MIDDLE[3])
        elif chain[0] not in BANGS and vrm_rig.rest_point(ch, chain[0])[2] < TRIM[0]:
            vrm_rig.thin(ch, chain, TRIM[2], rng.uniform(*TRIM[1]))


# ---------------------------------------------------------------------------------------------------- his clothes

def dress(ch, m, name: str):
    """VRoid's shirt and skirt as a patched kimono and a tattered hakama, his feet bare (at rest, before posing).
    Returns the body mesh (the one wearing them), or None for a model with none."""
    body = next((ob for ob in ch.meshes if vrm_rig.faces_of(ob, "Bottoms").size), None)
    if body is None:
        print(f"vroid_shinza: {name} has no Bottoms to dress; left as VRoid made him")
        return None
    for which, (lit, shade) in (("Tops", KIMONO), ("Bottoms", HAKAMA)):
        # the shirt's cuffs and the skirt's waistband cut in a zigzag (feathers in a close-up) made whole: a kimono's
        # sleeves and a hakama's waist end clean
        for mat in ch.materials("cloth"):
            if which in mat.name:
                vrm_rig.recolor(mat, lit, shade, opaque=True, outline=CLOTH_INK)
    bottoms, tops = vrm_rig.faces_of(body, "Bottoms"), vrm_rig.faces_of(body, "Tops")
    skin_f, shoes = vrm_rig.faces_of(body, "Body_00_SKIN"), vrm_rig.faces_of(body, "Shoes")
    vrm_rig.lengthen(ch, body, bottoms, HEM[0], HEM[1], flare=HEM[2])

    c = vrm_rig.face_centers(ch, body)
    # patches: the cloth under a few boxes a lighter, faded grey
    for which, at, half, gain in PATCHES:
        fs = vrm_rig.faces_of(body, which)
        inside = fs[np.all(np.abs(c[fs] - np.asarray(at)) < np.asarray(half), axis=1)]
        if inside.size:
            tone = vrm_rig.sample(body, inside)
            vrm_rig.paint(body, inside, tuple(min(1.0, v * gain) for v in tone), grow=1)

    def in_v(p):
        half = V_HALF * np.clip((p[:, 2] - CROSS) / (NECK - CROSS), 0, None)
        return (p[:, 1] < 0.02) & (p[:, 2] > CROSS) & (np.abs(p[:, 0]) < half)

    sc = c[skin_f]
    # the skin in the V, round the neck and below the old hem (VRoid's white socks) his own, from his throat
    tone = vrm_rig.sample(body, skin_f[(sc[:, 2] > NECK + 0.02) & (sc[:, 2] < NECK + 0.07) & (sc[:, 1] < 0.0)])
    bare = skin_f[in_v(sc) | ((sc[:, 2] > NECK - 0.03) & (sc[:, 2] < NECK + 0.1)) | (sc[:, 2] < HEM[0] - 0.1)]
    vrm_rig.paint(body, bare, tone)
    under = skin_f[(sc[:, 2] > UNDER[0]) & (sc[:, 2] < UNDER[1]) & (np.abs(sc[:, 0]) < UNDER[2]) & ~in_v(sc)]
    # the hakama's hem torn: its lowest faces cut away along a ragged line round it
    cb = vrm_rig.face_centers(ch, body)[bottoms]
    hem_z = cb[:, 2].min()
    ang = np.arctan2(cb[:, 1], cb[:, 0])
    rag = TATTER * (0.5 + 0.5 * np.sin(ang * 7.0 + 1.3)) * (0.5 + 0.5 * np.sin(ang * 3.0 + 0.4)) ** 2
    torn = bottoms[cb[:, 2] < hem_z + rag]
    vrm_rig.cut(body, np.concatenate([tops[((c[tops, 2] > NECK) & (c[tops, 1] < NAPE)) | in_v(c[tops])], shoes, under,
                                      torn]))
    # laid on what is left of the shirt (bridging the gap between its cut edge and his neck, so its inside stays hidden)
    on = [(body, vrm_rig.faces_of(body, "Tops"))]
    for i, path in enumerate((ERI, ERI_UNDER)):
        lift = 0.002 * (i == 0)      # the left side's over the right's
        vrm_rig.collar(ch, f"{name}-eri{i}", path, ERI_WIDTH[:len(path)], on=on, material=m["eri"], push=0.007 + lift)
        # under its collar, thinner: the two never cross in depth
        vrm_rig.collar(ch, f"{name}-juban{i}", path[:7], JUBAN[0], on=on, material=m["juban"], push=0.0045 + lift,
                       thickness=0.002, shift=JUBAN[1][i] * np.array(ERI_WIDTH[:7]) / 2)
    return body
