"""VRM characters (VRoid Studio's exports, or any .vrm) in Blender shots, through the VRM add-on ("VRM format" by
saturday06, a Blender extension: bl_ext.user_default.vrm). A --factory-startup session has it off; `load` turns it
on (`ensure_addon`).

`load(path, coll, name=...)` imports a .vrm into a collection of its own and returns a `Character`: a root empty at its
feet, turned so the character faces +x like every character in a shot (blender/lib/anime.py), the armature under it,
its meshes, its expressions and its MToon materials. Everything after goes by the VRM humanoid's bone names (hips,
spine, chest, neck, head, leftUpperArm, rightHand, leftIndexProximal, ...: HUMANOID), never the file's own, so a pose
or an expression written for one VRM fits any other.

Posing. A pose is {humanoid bone: (x, y, z) degrees}: each bone turned from its rest about the character's own axes,
x toward its left, y toward its back, z up (the VRM's own frame as it stands in the file: facing -y with its left at +x,
as MakeHuman's people stand in blender/lib/human.py), x first, then y, then z. A turn is relative to the bone's parent,
so a child's adds to its parent's. For any VRM, from its T-pose (arms out along x, palms down):
    x  + bends forward: a head nods, a spine leans in; a thigh or a hanging arm swings back; a knee or a finger
       pointing down curls back
    y  + tips toward its own left: a head or a spine leans left; the left arm comes down, the right arm goes up
    z  + turns toward its own left: a head or the hips look left; the left arm swings back, the right arm forward
This is VRM 1.0's normalized pose (what .vrma animations are written in), so it does not depend on how a file rolled
its bones. `mirror(pose)` swaps left and right; `blend(a, b, k)` goes between two poses. `pose(ch, rotations,
hips=(x, y, z))` sets one (every humanoid bone it does not name back at rest) and moves the hips, in metres along the
same axes ((0, -0.05, -0.15) drops them 15 cm and brings them 5 cm forward). Eyes are bones too (leftEye, rightEye:
x + looks down, z + looks to its left).

For props: `reach(ch, "leftHand", at, pole=...)` (IK: a hand or a foot to a point, the elbow or knee toward the
pole, starting folded its own way, `fold`, so a limb straight in its T-pose still bends), `hold(ch, bone, rotation)` (a
bone kept at an orientation in the character's frame, whatever its parents do: a foot flat on the deck), `grasp(ch,
"right", point, along, palm)` (a fist closed round a hilt or a pole running along `along` through `point`, the palm
facing `palm`). Points and directions are in the character's frame, metres as it
stands (after `scale_to`); `Character.world(p)` puts one in the world, `Character.point(bone)` reads a posed bone's.

Expressions are the VRM's own: the presets (happy, angry, sad, relaxed, surprised, aa, ih, ou, ee, oh, blink,
blinkLeft, blinkRight, ...) and the file's custom ones. `express(ch, {"angry": 0.6, "blink": 0.3}, frame=f)` sets (and
keys) the morph targets they bind, every other expression at 0; weights add up per shape key, clamped to 1.

Materials are the add-on's MToon. VRoid names each by what it is (..._SKIN, _CLOTH, _HAIR, _FACE, _EYE): `kind(name)`
reads it and `Character.materials(kind)` lists them. `tint` multiplies the lit and shade colours (linear),
`desaturate` grades their textures toward grey, `gloss` sets MToon's parametric rim (a fresnel sheen: wet cloth and
hair), `outline` the MToon outline (metres in the world; `outline_width(frac, distance, lens)` turns a width in frame
heights into metres at a distance) and `key_outline` keys its width per frame (a wide and a close-up want different
widths), `flash` lets them whiten with the scene's lightning (toon.FLASH: MToon ignores a light's strength, so the
key light's flare alone leaves it as it was). `anime(ch, tones, key)` paints them instead as an anime colour designer
would (blender/lib/toon3d.py: a base, a soft 1st shade and a deep 2nd shade from a key of the character's own, with
its cast shadows; lines coloured from their surface, round the hair too), by each material's `part` (`kind`, the
face's skin told from the body's); `smooth` subdivides the meshes as they render, so a sleeve's silhouette is no
polygon chain. `scale_to(ch, height)` scales the character to a standing height.

The add-on's import sets the scene's view transform to Standard; `load` puts it back. The numpy halves (the names, a
pose's maths, a hand's turn, the colour grade, sizes) are tested without Blender in blender/tests/test_vrm.py.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

ADDON = "bl_ext.user_default.vrm"

_FINGERS = (("Thumb", ("Metacarpal", "Proximal", "Distal")), ("Index", ("Proximal", "Intermediate", "Distal")),
            ("Middle", ("Proximal", "Intermediate", "Distal")), ("Ring", ("Proximal", "Intermediate", "Distal")),
            ("Little", ("Proximal", "Intermediate", "Distal")))
# VRM 1.0's humanoid bones
HUMANOID = ("hips", "spine", "chest", "upperChest", "neck", "head", "leftEye", "rightEye", "jaw",
            "leftUpperLeg", "leftLowerLeg", "leftFoot", "leftToes", "rightUpperLeg", "rightLowerLeg", "rightFoot",
            "rightToes", "leftShoulder", "leftUpperArm", "leftLowerArm", "leftHand", "rightShoulder", "rightUpperArm",
            "rightLowerArm", "rightHand") + tuple(f"{side}{finger}{joint}" for side in ("left", "right")
                                                 for finger, joints in _FINGERS for joint in joints)
_BY_KEY = {re.sub(r"[^a-z]", "", h.lower()): h for h in HUMANOID}
# VRM 0.x named the thumb's joints one along: its proximal is 1.0's metacarpal
VRM0_THUMB = {"ThumbProximal": "ThumbMetacarpal", "ThumbIntermediate": "ThumbProximal"}
KINDS = ("skin", "cloth", "hair", "face", "eye")
# a hand's shapes, the left's (the right's mirrored: `hand_pose`), {finger joint: (x, y, z) degrees} from the T-pose's
# flat hand (palm down, fingers along +x): y + curls a finger toward the palm, z + fans it back (toward the little
# finger's side), x + drops the thumb toward the palm. Every finger its own: a cascade, index least, little most
_CURL = ("Proximal", "Intermediate", "Distal")


def _shape(curls: dict, fan: dict, thumb) -> dict:
    out = {}
    for f, cs in curls.items():
        for j, c in zip(_CURL, cs):
            out[f"{f}{j}"] = (0.0, float(c), float(fan.get(f, 0.0)) if j == "Proximal" else 0.0)
    for j, t in zip(("Metacarpal", "Proximal", "Distal"), thumb):
        out[f"Thumb{j}"] = tuple(float(v) for v in t)
    return out


_FAN = {"Index": -3.0, "Middle": -0.5, "Ring": 2.0, "Little": 5.0}
HAND_SHAPES = {
    # at rest: a soft cascade, the thumb lying against the index's side, its tip by the index's middle joint
    "relaxed": _shape({"Index": (10, 16, 10), "Middle": (16, 24, 14), "Ring": (22, 30, 16), "Little": (28, 36, 18)},
                      _FAN, ((18, 6, 16), (0, 10, 8), (0, 14, 0))),
    # loose: half closed, an idle or tired hand
    "loose": _shape({"Index": (28, 38, 22), "Middle": (34, 46, 26), "Ring": (40, 52, 30), "Little": (46, 58, 32)},
                    _FAN, ((26, 10, 22), (0, 18, 12), (0, 20, 0))),
    # open: fingers out and fanned, a little curl left in them (an open hand never goes dead flat)
    "open": _shape({"Index": (2, 4, 2), "Middle": (3, 5, 3), "Ring": (5, 7, 4), "Little": (7, 9, 5)},
                   {"Index": -8.0, "Middle": -2.0, "Ring": 4.0, "Little": 11.0}, ((6, -4, -6), (0, 2, -4), (0, 4, 0))),
    # a fist: knuckles in, the thumb folded across the index's and middle's middle joints
    "fist": _shape({"Index": (82, 96, 62), "Middle": (86, 98, 64), "Ring": (88, 100, 64), "Little": (90, 100, 62)},
                   {"Index": -1.0, "Middle": 0.0, "Ring": 1.0, "Little": 3.0}, ((42, 14, 30), (0, 30, 20), (0, 40, 0))),
    # point: the index out (a touch of curl), the rest closed, the thumb on the middle finger
    "point": _shape({"Index": (2, 6, 4), "Middle": (78, 92, 58), "Ring": (84, 96, 60), "Little": (88, 98, 60)},
                    {"Index": -2.0, "Middle": 0.0, "Ring": 1.0, "Little": 3.0}, ((36, 10, 26), (0, 26, 16), (0, 30, 0))),
    # beckon: the fingers curled in (a beckoning hand goes between "open" and this: Performance.gesture)
    "beckon": _shape({"Index": (52, 70, 40), "Middle": (56, 74, 42), "Ring": (58, 74, 42), "Little": (60, 74, 40)},
                     _FAN, ((20, 6, 18), (0, 12, 10), (0, 16, 0))),
    # press: flat and together, pressed to something (a palm on the deck, on a chest), the fingertips a little back
    "press": _shape({"Index": (-6, 2, 4), "Middle": (-6, 2, 4), "Ring": (-5, 3, 4), "Little": (-4, 4, 4)},
                    {"Index": -1.0, "Middle": 0.0, "Ring": 1.0, "Little": 2.0}, ((4, 0, 12), (0, 2, 4), (0, 6, 0))),
    # tremble: a strained half-open hand (Performance.gesture shakes it)
    "tremble": _shape({"Index": (14, 22, 14), "Middle": (20, 30, 18), "Ring": (26, 36, 20), "Little": (32, 42, 22)},
                      {"Index": -6.0, "Middle": -1.0, "Ring": 3.0, "Little": 8.0}, ((14, 0, 6), (0, 10, 4), (0, 18, 0))),
}
FINGERS = tuple(f"{f}{j}" for f, joints in _FINGERS for j in joints)


def hand_pose(side: str, shape: str = "relaxed", amount: float = 1.0) -> dict:
    """The fingers of one hand ("left" or "right") in a shape (HAND_SHAPES), `amount` of the way from the flat T-pose
    hand (1 the shape; between, the shape eased in). {humanoid bone: (x, y, z)}: merge it into any pose."""
    if shape not in HAND_SHAPES:
        raise KeyError(f"no hand shape {shape!r} (one of {', '.join(HAND_SHAPES)})")
    s = 1.0 if side == "left" else -1.0
    a = float(amount)
    return {f"{side}{k}": (x * a, s * y * a, s * z * a) for k, (x, y, z) in HAND_SHAPES[shape].items()}


def hand_blend(side: str, a: str, b: str, k: float) -> dict:
    """A hand between two shapes (HAND_SHAPES), `k` of the way from `a` to `b`."""
    pa, pb = hand_pose(side, a), hand_pose(side, b)
    return {n: tuple(x + (y - x) * k for x, y in zip(pa[n], pb[n])) for n in pa}


# standing easy: the arms hanging close by the sides from the T-pose, the elbows softly bent, the palms toward the
# thighs (a little back), the wrists a touch flexed, the hands relaxed (a sheet's pose)
RELAXED = {"leftUpperArm": (0.0, 76.0, 5.0), "rightUpperArm": (0.0, -76.0, -5.0),
           "leftLowerArm": (12.0, 0.0, -16.0), "rightLowerArm": (12.0, 0.0, 16.0),
           "leftHand": (0.0, 10.0, -4.0), "rightHand": (0.0, -10.0, 4.0),
           **hand_pose("left"), **hand_pose("right")}
# a hanging hand's turn (vrm.hold's, the character's frame from the T-pose): fingers down, the palm toward the thigh and
# a little back, the wrist a touch flexed; for an IK hand left to hang (vrm.reach)
HANG_TURN = {"left": (12.0, 88.0, 0.0), "right": (12.0, -88.0, 0.0)}
LUMA = (0.2126, 0.7152, 0.0722)
GATE_H = 20.25   # the engine's gate (mm), fit vertically (lib/rig.py)
FOLD = 20.0      # degrees an elbow or knee starts folded when an IK reaches through it (`fold`)


# ---------------------------------------------------------------------------------------------------- names

def canonical(name: str) -> str:
    """A humanoid bone's VRM 1.0 name from any spelling of it: "leftUpperArm", "left_upper_arm", "LeftUpperArm"."""
    key = re.sub(r"[^a-z]", "", name.lower())
    if key not in _BY_KEY:
        near = [h for h in HUMANOID if key[:6] and key[:6] in h.lower()]
        raise KeyError(f"{name!r} is not a VRM humanoid bone" + (f" (did you mean {', '.join(near[:4])}?)" if near else ""))
    return _BY_KEY[key]


def mirror_name(name: str) -> str:
    """leftX <-> rightX; a bone on the middle stays."""
    h = canonical(name)
    if h.startswith("left"):
        return "right" + h[4:]
    if h.startswith("right"):
        return "left" + h[5:]
    return h


def kind(material_name: str) -> str | None:
    """What a VRoid material is, from its name ("N00_007_02_Tops_01_CLOTH (Instance).001" -> "cloth"): one of KINDS,
    or None for a name that does not say."""
    stem = re.sub(r"(\s*\(Instance\))?(\.\d+)?$", "", material_name)
    found = re.findall(r"(?:^|_)(SKIN|CLOTH|HAIR|FACE|EYE)(?=_|$)", stem, flags=re.IGNORECASE)
    return found[-1].lower() if found else None


def part(material_name: str) -> str | None:
    """`kind`, with the face's skin told from the body's ("N00_000_00_Face_00_SKIN" -> "face_skin"): what `anime`
    paints a material by."""
    k = kind(material_name)
    if k == "skin" and re.search(r"(?:^|_)Face_\d+_SKIN", material_name, flags=re.IGNORECASE):
        return "face_skin"
    return k


# ---------------------------------------------------------------------------------------------------- poses

def euler(rotation) -> np.ndarray:
    """The rotation (degrees about x, then y, then z, all fixed axes) as a 3x3 matrix."""
    x, y, z = (math.radians(float(a)) for a in rotation)
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rz @ ry @ rx


def body_frame(left_hip, right_hip) -> np.ndarray:
    """The character's frame in its armature's space, as columns (its left, its back, up), from where its hips' leg
    joints are at rest: up is the armature's z (a VRM is always imported z up), its left level from the right hip to
    the left."""
    left = np.subtract(left_hip, right_hip).astype(float)
    left[2] = 0.0
    n = np.linalg.norm(left)
    if n < 1e-9:
        raise ValueError("the hips' joints are on top of each other: no left to the character")
    left /= n
    up = np.array([0.0, 0.0, 1.0])
    return np.column_stack([left, np.cross(up, left), up])


def local_rotation(rest, frame, rotation) -> np.ndarray:
    """The rotation (3x3, in the bone's own space) to give a pose bone whose rest orientation in armature space is
    `rest` (3x3, the bone's axes as columns) for a turn `rotation` (degrees, x/y/z about the character's axes;
    `frame` from body_frame). The bone's parent's turn carries over, so this holds anywhere down a chain."""
    rest, frame = np.asarray(rest, float), np.asarray(frame, float)
    r = frame @ euler(rotation) @ frame.T if not _is_matrix(rotation) else frame @ np.asarray(rotation, float) @ frame.T
    return rest.T @ r @ rest


def _is_matrix(v) -> bool:
    return np.shape(v) == (3, 3)


def facing_turn(frame) -> float:
    """The turn about z (radians) that brings a character with axes `frame` (body_frame) to face +x."""
    front = -np.asarray(frame, float)[:, 1]
    return -math.atan2(front[1], front[0])


def offset_local(rest, frame, offset) -> np.ndarray:
    """The pose location to give a bone at rest orientation `rest` (an unposed parent: the hips) to move it by
    `offset` (metres along the character's axes)."""
    return np.asarray(rest, float).T @ (np.asarray(frame, float) @ np.asarray(offset, float))


def mirror(pose: dict) -> dict:
    """A pose with left and right swapped (as seen in a mirror: the turns' y and z change sign)."""
    return {mirror_name(k): (float(v[0]), -float(v[1]), -float(v[2])) for k, v in pose.items()}


def blend(a: dict, b: dict, k: float) -> dict:
    """Between two poses: each bone's turn from a to b by k (a bone in one only turns from or to rest)."""
    out = {}
    for name in {canonical(n) for n in (*a, *b)}:
        va = next((v for n, v in a.items() if canonical(n) == name), (0.0, 0.0, 0.0))
        vb = next((v for n, v in b.items() if canonical(n) == name), (0.0, 0.0, 0.0))
        out[name] = tuple(float(x) + (float(y) - float(x)) * k for x, y in zip(va, vb))
    return out


def align(k0, p0, k1, p1) -> np.ndarray:
    """The rotation (3x3) taking a hand whose knuckles run along k0 (index to little) with its palm facing p0 to
    knuckles along k1, palm facing p1. Each pair is made square (p by k) first."""
    def frame(k, p):
        k = np.asarray(k, float) / np.linalg.norm(k)
        p = np.asarray(p, float) - k * np.dot(p, k)
        n = np.linalg.norm(p)
        if n < 1e-9:
            raise ValueError("a palm cannot face along its knuckles")
        p /= n
        return np.column_stack([k, p, np.cross(k, p)])
    return frame(k1, p1) @ frame(k0, p0).T


RELAX_HANDS = True     # a pose that names none of a hand's fingers rests them relaxed (HAND_SHAPES), not flat


def relaxed_fingers(turns) -> dict:
    """The relaxed fingers (hand_pose) of each hand none of whose fingers `turns` names (with RELAX_HANDS)."""
    if not RELAX_HANDS:
        return {}
    out = {}
    for side in ("left", "right"):
        if not any(f"{side}{f}" in turns for f in FINGERS):
            out.update(hand_pose(side))
    return out


def grip_pose(side: str, amount: float = 1.0, thumb: float = 0.6) -> dict:
    """The fingers of one hand ("left" or "right") curled into a fist by `amount` (1: closed round a hilt) and the
    thumb across them by `thumb`, from a T-pose's flat hand (palm down)."""
    s = 1.0 if side == "left" else -1.0
    out = {}
    for finger in ("Index", "Middle", "Ring", "Little"):
        for joint, deg in (("Proximal", 65.0), ("Intermediate", 80.0), ("Distal", 55.0)):
            out[f"{side}{finger}{joint}"] = (0.0, s * deg * amount, 0.0)
    out[f"{side}ThumbMetacarpal"] = (0.0, s * 10.0 * thumb, s * 25.0 * thumb)
    out[f"{side}ThumbProximal"] = (0.0, s * 25.0 * thumb, s * 15.0 * thumb)
    out[f"{side}ThumbDistal"] = (0.0, s * 35.0 * thumb, 0.0)
    return out


def fold(bone: str, degrees: float = FOLD) -> tuple:
    """The way an elbow or a knee folds, as a turn of its lower bone (leftLowerArm, rightLowerLeg, ...) by `degrees`
    from the T-pose: a forearm swings forward, a shin curls back. An IK chain that starts dead straight cannot tell
    which way to fold, so `reach` starts it so."""
    h = canonical(bone)
    if h.endswith("LowerArm"):
        return (0.0, 0.0, -degrees if h.startswith("left") else degrees)
    if h.endswith("LowerLeg"):
        return (degrees, 0.0, 0.0)
    raise ValueError(f"{h} is not an elbow's or a knee's lower bone")


# ---------------------------------------------------------------------------------------------------- colours, sizes

def tinted(color, gain) -> tuple:
    """`color` (RGB or RGBA, linear) times `gain` (RGB); alpha kept."""
    c = tuple(float(v) for v in color)
    rgb = tuple(a * float(g) for a, g in zip(c[:3], gain))
    return rgb + c[3:]


def grade(pixels, saturation: float = 1.0) -> np.ndarray:
    """Texture pixels ((..., 4) RGBA, 0..1) with their colour moved toward its own grey by `saturation` (1 as they
    are, 0 grey; the luma kept, the alpha untouched)."""
    px = np.array(pixels, dtype=np.float32, copy=True)
    luma = px[..., :3] @ np.asarray(LUMA, np.float32)
    px[..., :3] = np.clip(luma[..., None] + (px[..., :3] - luma[..., None]) * float(saturation), 0.0, 1.0)
    return px


def outline_width(frac: float, distance: float, lens: float, gate: float = GATE_H) -> float:
    """Metres that make `frac` of the frame's height at `distance` metres from a lens of `lens` mm on a gate `gate` mm
    tall: an outline of so many frame heights, whatever the shot."""
    if distance <= 0 or lens <= 0:
        raise ValueError("an outline's width needs a distance and a lens")
    return float(frac) * distance * gate / lens


def height_scale(height: float, target: float) -> float:
    """The scale that makes a character `height` tall stand `target` tall."""
    if height <= 0 or target <= 0:
        raise ValueError(f"heights must be positive, got {height} and {target}")
    return target / height


# ---------------------------------------------------------------------------------------------------- Blender

def ensure_addon() -> None:
    """The VRM add-on on (a --factory-startup session starts with it off), or RuntimeError saying how to install it."""
    import bpy

    if ADDON not in bpy.context.preferences.addons:
        try:
            bpy.ops.preferences.addon_enable(module=ADDON)
        except Exception as e:  # noqa: BLE001 - say what to do, not just that it failed
            raise RuntimeError(f"the VRM add-on ({ADDON}) is not installed: get 'VRM format' from "
                               f"extensions.blender.org into the user_default repository ({e})") from e
    if not hasattr(bpy.ops.import_scene, "vrm"):
        raise RuntimeError(f"the VRM add-on ({ADDON}) is on but has no importer")


@dataclass
class Character:
    """A VRM in the scene (`load`). Its frame: origin at the feet, its own axes (x its left, y its back, z up), metres
    as it stands."""
    name: str
    root: object                     # the empty at its feet: place and turn the character by it
    armature: object
    meshes: list
    coll: object
    frame: np.ndarray                # the character's axes in armature space (body_frame)
    bones: dict                      # humanoid name -> the armature's bone
    expressions: dict                # expression -> [(mesh object, shape key, weight)]
    binary: set = field(default_factory=set)   # expressions that are on or off
    handles: dict = field(default_factory=dict)
    bends: dict = field(default_factory=dict)  # humanoid bone -> the turn it starts from when not posed (`reach`)

    @property
    def scale(self) -> float:
        return float(self.root.scale[0])

    def has(self, bone: str) -> bool:
        return canonical(bone) in self.bones

    def bone(self, bone: str):
        """The pose bone a humanoid bone is."""
        h = canonical(bone)
        if h not in self.bones:
            raise KeyError(f"{self.name}: no {h} in this VRM (it maps {', '.join(sorted(self.bones))})")
        return self.armature.pose.bones[self.bones[h]]

    def to_armature(self, p):
        """A point of the character's frame in armature space."""
        from mathutils import Vector

        return Vector(self.frame @ (np.asarray(p, float) / self.scale))

    def world(self, p):
        """A point of the character's frame in the world."""
        import bpy

        bpy.context.view_layer.update()
        return self.armature.matrix_world @ self.to_armature(p)

    def rest(self, bone: str, *, tail: bool = False) -> np.ndarray:
        """A humanoid bone's head (or tail) at rest, in the character's frame."""
        b = self.armature.data.bones[self.bones[canonical(bone)]]
        return self.frame.T @ np.array(b.tail_local if tail else b.head_local) * self.scale

    def point(self, bone: str, *, tail: bool = False):
        """A humanoid bone's head (or tail) in the world, as posed."""
        import bpy

        bpy.context.view_layer.update()
        pb = self.bone(bone)
        return self.armature.matrix_world @ (pb.tail if tail else pb.head)

    def materials(self, which: str | None = None) -> list:
        """Its materials (each once), or those of one kind (KINDS)."""
        out = []
        for ob in self.meshes:
            for slot in ob.material_slots:
                m = slot.material
                if m is not None and m not in out and (which is None or kind(m.name) == which):
                    out.append(m)
        return out

    def face(self):
        """The point between its eyes in the world, as posed (the eyes' pivots; the head's if it has no eye bones)."""
        if self.has("leftEye") and self.has("rightEye"):
            return (self.point("leftEye") + self.point("rightEye")) / 2
        return self.point("head", tail=True)

    def head_span(self) -> tuple[float, float]:
        """(chin, crown) heights in the world, as posed: the lowest point of the face (the mesh its expressions move)
        and the highest of everything over the neck within a head's reach of it (the hair's top)."""
        import bpy

        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        neck = self.point("head")
        reach = 0.22 * self.scale
        faces = {ob for binds in self.expressions.values() for ob, _, _ in binds}
        chin, crown = None, neck.z
        for ob in self.meshes:
            ev = ob.evaluated_get(dg)
            me = ev.to_mesh()
            co = np.empty(len(me.vertices) * 3, np.float32)
            me.vertices.foreach_get("co", co)
            ev.to_mesh_clear()
            m = np.array(ob.matrix_world)
            w = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
            near = np.hypot(w[:, 0] - neck.x, w[:, 1] - neck.y) < reach
            up = w[near & (w[:, 2] > neck.z)]
            if len(up):
                crown = max(crown, float(up[:, 2].max()))
            if ob in faces and len(w):
                low = float(w[:, 2].min())
                chin = low if chin is None else min(chin, low)
        return (chin if chin is not None else neck.z), crown


def load(path, coll, name: str | None = None) -> Character:
    """Import the .vrm at `path` into `coll` (every object it makes; the add-on's own collections go), named after
    `name` (default the file's stem), and return its Character: the armature under a root empty at the feet that
    turns it to face +x."""
    import bpy
    from pathlib import Path

    ensure_addon()
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no VRM at {path}")
    name = name or path.stem
    scene = bpy.context.scene
    view = scene.view_settings
    keep = (view.view_transform, view.look, view.exposure, view.gamma)
    obs0, colls0 = set(bpy.data.objects), set(bpy.data.collections)
    result = bpy.ops.import_scene.vrm(filepath=str(path))
    if "FINISHED" not in result:
        raise RuntimeError(f"the VRM add-on could not import {path}: {result}")
    view.view_transform, view.look, view.exposure, view.gamma = keep

    new = [ob for ob in bpy.data.objects if ob not in obs0]
    arm = next((ob for ob in new if ob.type == "ARMATURE"), None)
    if arm is None:
        raise RuntimeError(f"{path} made no armature")
    for ob in new:
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        coll.objects.link(ob)
    for c in set(bpy.data.collections) - colls0:
        if not c.objects and not c.children:
            bpy.data.collections.remove(c)
    bones = _humanoid(arm)
    for k in ("hips", "leftUpperLeg", "rightUpperLeg", "head"):
        if k not in bones:
            raise RuntimeError(f"{path}: its humanoid has no {k}")
    ext = arm.data.vrm_addon_extension
    exprs, binary = {}, set()
    if ext.spec_version != "0.0":
        for ex_name, ex in ext.vrm1.expressions.all_name_to_expression_dict().items():
            binds = []
            for b in ex.morph_target_binds:
                ob = bpy.data.objects.get(b.node.mesh_object_name)
                key = _shape_key(ob, b.index)
                if key is not None:
                    binds.append((ob, key, float(b.weight)))
            exprs[ex_name] = binds
            if ex.is_binary:
                binary.add(ex_name)
    else:
        for group in ext.vrm0.blend_shape_master.blend_shape_groups:
            binds = []
            for b in group.binds:
                ob = bpy.data.objects.get(b.mesh.mesh_object_name)
                key = _shape_key(ob, b.index)
                if key is not None:
                    binds.append((ob, key, float(b.weight)))
            exprs[_vrm0_expression(group.preset_name, group.name)] = binds
            if group.is_binary:
                binary.add(_vrm0_expression(group.preset_name, group.name))

    root = bpy.data.objects.new(name, None)
    root.empty_display_size = 0.3
    coll.objects.link(root)
    arm.parent = root
    arm.name = f"{name}-rig"
    left = arm.data.bones[bones["leftUpperLeg"]].head_local
    right = arm.data.bones[bones["rightUpperLeg"]].head_local
    frame = body_frame(left, right)
    # its front (-its back) turned to +x
    arm.rotation_mode = "XYZ"
    arm.rotation_euler = (0.0, 0.0, facing_turn(frame))
    meshes = [ob for ob in new if ob.type == "MESH"]
    for ob in meshes:
        ob.name = f"{name}-{ob.name}"
    for ob in new:
        if ob.type == "EMPTY":
            ob.hide_render = True
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return Character(name, root, arm, meshes, coll, frame, bones, exprs, binary)


def _shape_key(ob, index) -> str | None:
    """The name of the shape key a bind names (the add-on keeps its name; a file's index, as a number, works too)."""
    keys = ob.data.shape_keys if ob is not None and ob.type == "MESH" else None
    if keys is None:
        return None
    if isinstance(index, str):
        return index if index in keys.key_blocks else None
    return keys.key_blocks[index].name if 0 <= index < len(keys.key_blocks) else None


def _humanoid(arm) -> dict:
    """{humanoid name: bone name} from the add-on's humanoid mapping (VRM 1.0 or 0.x)."""
    ext = arm.data.vrm_addon_extension
    out = {}
    if ext.spec_version != "0.0":
        for h, hb in ext.vrm1.humanoid.human_bones.human_bone_name_to_human_bone().items():
            if hb.node.bone_name and hb.node.bone_name in arm.data.bones:
                out[str(getattr(h, "value", h))] = hb.node.bone_name
    else:
        for hb in ext.vrm0.humanoid.human_bones:
            if hb.node.bone_name and hb.node.bone_name in arm.data.bones:
                b = hb.bone
                for old, new in VRM0_THUMB.items():
                    if b.endswith(old):
                        b = b[: -len(old)] + new
                out[b] = hb.node.bone_name
    return {canonical(k): v for k, v in out.items() if re.sub(r"[^a-z]", "", k.lower()) in _BY_KEY}


def _vrm0_expression(preset: str, name: str) -> str:
    """A VRM 0.x blend shape group as a VRM 1.0 expression name."""
    renames = {"joy": "happy", "sorrow": "sad", "fun": "relaxed", "a": "aa", "i": "ih", "u": "ou", "e": "ee",
               "o": "oh", "blink_l": "blinkLeft", "blink_r": "blinkRight", "lookup": "lookUp", "lookdown": "lookDown",
               "lookleft": "lookLeft", "lookright": "lookRight"}
    if preset and preset != "unknown":
        return renames.get(preset, preset)
    return name


# ---- posing

def pose(ch: Character, rotations: dict, *, hips=None, frame: int | None = None, reset: bool = True) -> None:
    """Turn humanoid bones from rest ({bone: (x, y, z) degrees}, see the module's doc) and move the hips by `hips`
    (metres along the character's axes); every other humanoid bone back at rest (an elbow or knee an IK reaches
    through at its `fold`) unless `reset` is False. Keyed at `frame` when given."""
    from mathutils import Matrix, Quaternion, Vector

    turns = {canonical(k): v for k, v in rotations.items()}
    if reset:
        turns = {**{k: v for k, v in relaxed_fingers(turns).items() if k in ch.bones}, **turns}
    missing = sorted(set(turns) - set(ch.bones))
    if missing:
        print(f"vrm: {ch.name} has no {', '.join(missing)}; left out of the pose")
    for h, bone_name in ch.bones.items():
        if h not in turns and not reset:
            continue
        pb = ch.armature.pose.bones[bone_name]
        rest = np.array(ch.armature.data.bones[bone_name].matrix_local.to_3x3())
        pb.rotation_mode = "QUATERNION"
        turn = turns.get(h, ch.bends.get(h))
        pb.rotation_quaternion = (Matrix(local_rotation(rest, ch.frame, turn).tolist()).to_quaternion()
                                  if turn is not None else Quaternion())
        if frame is not None:
            pb.keyframe_insert("rotation_quaternion", frame=frame)
    if hips is not None or reset:
        pb = ch.bone("hips")
        rest = np.array(ch.armature.data.bones[pb.name].matrix_local.to_3x3())
        pb.location = Vector(offset_local(rest, ch.frame, np.asarray(hips if hips is not None else (0, 0, 0)) / ch.scale))
        if frame is not None:
            pb.keyframe_insert("location", frame=frame)


def _handle(ch: Character, key: str, at):
    import bpy

    e = ch.handles.get(key)
    if e is None:
        e = bpy.data.objects.new(f"{ch.name}-{key}", None)
        ch.coll.objects.link(e)
        e.parent = ch.armature
        e.empty_display_size = 0.04
        ch.handles[key] = e
    e.location = ch.to_armature(at)
    return e


def _chain(ch: Character, end: str) -> tuple[object, object, int]:
    """(upper bone, lower bone, chain length) of the limb `end` ends: leftHand -> leftUpperArm..leftLowerArm."""
    h = canonical(end)
    side = "left" if h.startswith("left") else "right"
    upper, lower = ((f"{side}UpperArm", f"{side}LowerArm") if h.endswith("Hand") else (f"{side}UpperLeg", f"{side}LowerLeg"))
    lo, up = ch.bone(lower), ch.bone(upper)
    n, b = 1, lo
    while b is not None and b != up:
        b, n = b.parent, n + 1
    if b is None:
        raise RuntimeError(f"{ch.name}: {upper} is not above {lower}")
    return up, lo, n


def reach(ch: Character, end: str, at, *, pole, bend: float = FOLD) -> object:
    """IK: the hand or foot `end` (leftHand, rightHand, leftFoot, rightFoot) reaches `at` (its wrist or ankle) with
    its elbow or knee toward `pole`, both in the character's frame. The elbow or knee starts folded its own way by
    `bend` degrees (`fold`; kept by `pose` while no pose turns it), so a limb straight in the T-pose still folds."""
    from mathutils import Matrix

    up, lo, n = _chain(ch, end)
    lower = next(h for h, b in ch.bones.items() if b == lo.name)
    if bend:
        ch.bends[lower] = fold(lower, bend)
        if lo.rotation_mode == "QUATERNION" and lo.rotation_quaternion.angle < 1e-6:     # at rest: no pose turned it
            rest = np.array(ch.armature.data.bones[lo.name].matrix_local.to_3x3())
            lo.rotation_quaternion = Matrix(local_rotation(rest, ch.frame, ch.bends[lower]).tolist()).to_quaternion()
    c = next((c for c in lo.constraints if c.type == "IK"), None) or lo.constraints.new("IK")
    c.target = _handle(ch, f"{canonical(end)}-target", at)
    c.pole_target = _handle(ch, f"{canonical(end)}-pole", pole)
    c.chain_count = n
    c.use_stretch = False
    c.pole_angle = _pole_angle(ch.armature.data.bones[up.name], ch.armature.data.bones[lo.name], ch.to_armature(pole))
    return c


def _pole_angle(base, tip, pole) -> float:
    """The IK pole angle that bends the chain base..tip (rest bones) in the plane toward `pole` (armature space)."""
    axis = base.tail_local - base.head_local
    normal = (tip.tail_local - base.head_local).cross(pole - base.head_local)
    toward = normal.cross(axis)
    x = base.matrix_local.to_3x3().col[0]
    a = x.angle(toward)
    return -a if x.cross(toward).angle(axis) < 1 else a


def hold(ch: Character, bone: str, rotation=(0.0, 0.0, 0.0)) -> object:
    """Keep a humanoid bone at its rest orientation turned by `rotation` (degrees about the character's axes, or a 3x3
    matrix), in the character's frame, whatever its parents do."""
    from mathutils import Matrix

    pb = ch.bone(bone)
    rest = np.array(ch.armature.data.bones[pb.name].matrix_local.to_3x3())
    turn = np.asarray(rotation, float) if _is_matrix(rotation) else euler(rotation)
    e = _handle(ch, f"{canonical(bone)}-hold", ch.rest(bone))
    e.rotation_mode = "QUATERNION"
    e.rotation_quaternion = Matrix((ch.frame @ turn @ ch.frame.T @ rest).tolist()).to_quaternion()
    c = next((c for c in pb.constraints if c.type == "COPY_ROTATION"), None) or pb.constraints.new("COPY_ROTATION")
    c.target = e
    c.target_space = c.owner_space = "WORLD"
    return c


def hand_rest(ch: Character, side: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A hand at rest in the character's frame: (knuckle line from index to little, the way the palm faces, the
    wrist to the middle knuckle)."""
    wrist = ch.rest(f"{side}Hand")
    k = ch.rest(f"{side}LittleProximal") - ch.rest(f"{side}IndexProximal")
    reach_ = ch.rest(f"{side}MiddleProximal") - wrist
    palm = np.cross(k, reach_) * (1.0 if side == "left" else -1.0)
    return k / np.linalg.norm(k), palm / np.linalg.norm(palm), reach_


def grasp(ch: Character, side: str, point, along, palm, *, pole, amount: float = 1.0, thumb: float = 0.6,
          depth: float = 0.028, bend: float = FOLD, radius: float | None = None, kind: str = "wrap") -> dict:
    """Close the `side` hand ("left" or "right") round a hilt or a pole running along `along` through `point`: its
    knuckles along `along` (index first), its palm facing `palm`, the fist's hole on the point; the elbow toward
    `pole`, starting folded by `bend` (`reach`). All in the character's frame. Returns the fingers' pose (pass it to
    `pose` with the rest of the body, or pose with reset=False after). With `radius` (the grip's, metres) each finger
    closes round it (vrm_rig.wrap: no gap, none through it), `amount` under 1 easing it toward relaxed. `kind`
    "pinch": something thin (a pipe's stem) held between the thumb and the index and middle fingers at `point`."""
    k0, p0, r0 = hand_rest(ch, side)
    turn = align(k0, p0, -np.asarray(along, float), palm)
    # the fist's hole: most of the way to the knuckles, out from the palm
    hole = r0 * 1.22 + p0 * 0.012 if kind == "pinch" else r0 * 0.85 + p0 * depth
    wrist = np.asarray(point, float) - turn @ hole
    hold(ch, f"{side}Hand", turn)
    reach(ch, f"{side}Hand", wrist, pole=pole, bend=bend)
    if kind == "pinch":
        from . import vrm_rig
        return vrm_rig.pinch(side, amount)
    if radius is not None:
        from . import vrm_rig
        return vrm_rig.grip(ch, side, radius, amount=amount, depth=depth, thumb=thumb)
    return grip_pose(side, amount, thumb)


def attach(ob, ch: Character, bone: str):
    """Carry `ob` with a humanoid bone from now on, keeping where it is in the current pose (a sword built in the
    posed hands, a cape round the posed shoulders)."""
    import bpy

    bpy.context.view_layer.update()
    world = ob.matrix_world.copy()
    ob.parent = ch.armature
    ob.parent_type = "BONE"
    ob.parent_bone = ch.bones[canonical(bone)]
    bpy.context.view_layer.update()
    ob.matrix_world = world
    return ob


def outline_ring(points, center, axis, u, *, n: int = 48, limit: float | None = None, smooth: int = 2) -> np.ndarray:
    """How far a body reaches from `center` in each of `n` directions round `axis` (from `u`, a direction square to
    it), from `points` near the plane there: each direction's furthest point (within `limit` of the axis), gaps
    filled from their neighbours, eased over `smooth` neighbours either side. Returns n radii."""
    p = np.asarray(points, float) - np.asarray(center, float)
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    u = np.asarray(u, float) - a * np.dot(u, a)
    u /= np.linalg.norm(u)
    w = np.cross(a, u)
    x, y = p @ u, p @ w
    r = np.hypot(x, y)
    keep = r < limit if limit is not None else np.ones(len(r), bool)
    k = (np.floor((np.arctan2(y, x) % (2 * math.pi)) / (2 * math.pi) * n).astype(int) % n)[keep]
    radii = np.full(n, np.nan)
    for i, rr in zip(k, r[keep]):
        if not rr <= radii[i]:
            radii[i] = rr
    if np.isnan(radii).all():
        raise ValueError("no points round the axis there")
    ok = ~np.isnan(radii)
    idx = np.arange(n)
    radii = np.interp(idx, np.concatenate([idx[ok] - n, idx[ok], idx[ok] + n]), np.tile(radii[ok], 3))
    if smooth > 0:
        radii = np.mean([np.roll(radii, s) for s in range(-smooth, smooth + 1)], axis=0)
    return radii


def wrap(radii, *, smooth: int = 2) -> np.ndarray:
    """A band pulled tight round a cross-section given as `radii` in n directions evenly round (outline_ring's): the
    radii of their convex hull read back in the same directions (a band bridges the dips between folds, never follows
    them in), eased over `smooth` neighbours either side and never inside the section."""
    r = np.asarray(radii, float)
    n = len(r)
    th = 2 * math.pi * np.arange(n) / n
    d = np.c_[np.cos(th), np.sin(th)]
    pts = d * r[:, None]
    # the hull (monotone chain), counter-clockwise
    order = sorted(range(n), key=lambda i: (pts[i, 0], pts[i, 1]))

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def half(idx):
        h = []
        for i in idx:
            while len(h) >= 2 and turn(pts[h[-2]], pts[h[-1]], pts[i]) <= 0:
                h.pop()
            h.append(i)
        return h

    lo, hi = half(order), half(order[::-1])
    hull = pts[lo[:-1] + hi[:-1]]
    out = r.copy()
    a, e = hull, np.roll(hull, -1, axis=0) - hull
    for i in range(n):
        den = d[i, 0] * e[:, 1] - d[i, 1] * e[:, 0]
        ok = np.abs(den) > 1e-12
        t = np.where(ok, (a[:, 0] * e[:, 1] - a[:, 1] * e[:, 0]) / np.where(ok, den, 1.0), -1.0)
        s_ = np.where(ok, (a[:, 0] * d[i, 1] - a[:, 1] * d[i, 0]) / np.where(ok, den, 1.0), -1.0)
        hit = t[ok & (s_ >= -1e-9) & (s_ <= 1 + 1e-9) & (t > 0)]
        if len(hit):
            out[i] = max(r[i], float(hit.max()))
    if smooth > 0:
        eased = np.mean([np.roll(out, k) for k in range(-smooth, smooth + 1)], axis=0)
        out = np.maximum(eased, r)
    return out


def band(ch: Character, name: str, bone: str, height: float, width: float, *, material=None, coll=None,
         push: float = 0.004, thickness: float = 0.004, tilt: float = 0.0, limit: float | None = None, n: int = 48,
         knot: float | None = None, tails=()) -> list:
    """A band tied round the character (an obi, a sash, a headband), `height` metres up `bone` from its head (as it
    stands at rest), its plane tipped forward by `tilt` degrees (+ the front lower): pulled tight round the meshes'
    cross-section there (outline_ring, nothing further than `limit` from the bone; `wrap`), at its top edge round what
    is under its upper half and at its bottom edge round what is under its lower half (over a flaring hakama it
    flares), `push` out from them, `width` across and `thickness` thick, flat-faced with square edges. `knot` (a size,
    metres) ties it at the back; `tails` [(length, width, spread degrees)] hang from the knot, falling and blown a
    little apart. Build it at rest, before posing: it is carried by `bone`. Returns its objects (the band first)."""
    import bpy

    from . import shapes

    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for ob in ch.meshes:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        m = np.array(ob.matrix_world)
        pts.append(co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3])
    pts = np.concatenate(pts)
    rot = np.array(ch.armature.matrix_world.to_3x3().normalized())
    up = rot @ (ch.frame @ (euler((tilt, 0, 0)) @ np.array([0.0, 0.0, 1.0])))
    back = rot @ ch.frame[:, 1]
    head = np.array(ch.point(bone))
    center = head + up * height
    u = back - up * np.dot(back, up)
    u /= np.linalg.norm(u)
    w = np.cross(up, u)
    # what each half of it goes round: the cross-sections at heights through it, the furthest in each direction
    h = (pts - center) @ up
    slab = max(width * 0.15, 0.005)
    halves = {}
    for edge, levels in (("top", np.linspace(0.0, width / 2, 3)), ("bottom", np.linspace(-width / 2, 0.0, 3))):
        rings = []
        for z in levels:
            near = np.abs(h - z) < slab
            if near.sum() >= 8:
                rings.append(outline_ring(pts[near], center + up * z, up, back, n=n, limit=limit))
        if not rings:
            near = np.abs(h) < max(width * 0.6, 0.01)
            rings = [outline_ring(pts[near], center, up, back, n=n, limit=limit)]
        halves[edge] = wrap(np.max(rings, axis=0))
    th = 2 * math.pi * np.arange(n) / n
    dirs = np.outer(np.cos(th), u) + np.outer(np.sin(th), w)

    def ring(edge, out):
        return center + up * (width / 2 if edge == "top" else -width / 2) + dirs * (halves[edge] + push + out)[:, None]

    it, ot, ob_, ib = ring("top", 0.0), ring("top", thickness), ring("bottom", thickness), ring("bottom", 0.0)
    verts, faces = [], []
    # four strips round it (outer, top, bottom, inner), each with its own vertices: square edges, smooth along it
    for a, b in ((ot, ob_), (it, ot), (ob_, ib), (ib, it)):
        base = len(verts)
        verts.extend(a)
        verts.extend(b)
        for i in range(n):
            j = (i + 1) % n
            faces.append((base + i, base + n + i, base + n + j, base + j))
    obs = [shapes.mesh_object(name, verts, faces, material, coll or ch.coll, smooth=True)]
    if knot:
        at = (ot[0] + ob_[0]) / 2 + u * knot * 0.6
        obs.append(shapes.ellipsoid(f"{name}-knot", tuple(at), (knot * 0.7, knot, knot * 0.8), material=material,
                                    coll=coll or ch.coll, n=10))
        for i, (length, tw, spread) in enumerate(tails):
            side = w * math.sin(math.radians(spread))
            path = [at + u * 0.01, at + u * (0.03 + length * 0.15) + side * length * 0.3 - up * length * 0.45,
                    at + u * (0.05 + length * 0.2) + side * length * 0.5 - up * length]
            obs.append(shapes.loft(f"{name}-tail{i}", path, [thickness / 2] * 3, [tw / 2, tw / 2, tw * 0.35],
                                   material=material, coll=coll or ch.coll, n=4, power=1.0, subsurf=0, up=tuple(w)))
    for ob in obs:
        attach(ob, ch, bone)
    return obs


# ---- the face

def express(ch: Character, weights: dict, frame: int | None = None) -> None:
    """Set the character's expressions ({name: weight}; every other at 0), keyed at `frame` when given."""
    unknown = sorted(set(weights) - set(ch.expressions))
    if unknown:
        raise KeyError(f"{ch.name}: no expression {', '.join(unknown)} (it has {', '.join(sorted(ch.expressions))})")
    total: dict = {}
    for binds in ch.expressions.values():
        for ob, key, _ in binds:
            total.setdefault((ob, key), 0.0)
    for name_, w in weights.items():
        w = float(round(w)) if name_ in ch.binary else float(w)
        for ob, key, bw in ch.expressions[name_]:
            total[(ob, key)] += w * bw
    for (ob, key), v in total.items():
        kb = ob.data.shape_keys.key_blocks[key]
        kb.value = min(1.0, max(0.0, v))
        if frame is not None:
            kb.keyframe_insert("value", frame=frame)


# ---- size

def standing_height(ch: Character) -> float:
    """How tall it stands at rest (feet to the top of its hair), metres as it stands now."""
    top = 0.0
    for ob in ch.meshes:
        top = max(top, max((ob.matrix_local @ _v(c)).z for c in ob.bound_box))
    return top * ch.scale


def _v(c):
    from mathutils import Vector

    return Vector(c)


def scale_to(ch: Character, height: float) -> float:
    """Scale the character (at its root) to stand `height` metres tall, measured at rest; returns the scale. Scale
    before posing: poses, reaches and holds are in metres as it stands."""
    s = height_scale(standing_height(ch) / ch.scale, height)
    ch.root.scale = (s, s, s)
    return s


# ---- materials

def _mtoon(mat):
    return mat.vrm_addon_extension.mtoon1


def tint(mat, lit=(1.0, 1.0, 1.0), shade=None) -> None:
    """Multiply a material's MToon lit colour by `lit` and its shade colour by `shade` (default `lit`), linear."""
    mt = _mtoon(mat)
    pbr, m = mt.pbr_metallic_roughness, mt.extensions.vrmc_materials_mtoon
    pbr.base_color_factor = tinted(pbr.base_color_factor, lit)
    m.shade_color_factor = tinted(m.shade_color_factor, lit if shade is None else shade)


_GRADED: dict = {}


def desaturate(mat, saturation: float) -> None:
    """Grade a material's lit and shade textures toward grey (`saturation` 1 leaves them, 0 greys them). A texture
    shared by several materials is graded once per saturation."""
    mt = _mtoon(mat)
    for info in (mt.pbr_metallic_roughness.base_color_texture, mt.extensions.vrmc_materials_mtoon.shade_multiply_texture):
        src = info.index.source
        if src is None or src.size[0] * src.size[1] <= 64:
            continue   # none, or the add-on's 8x8 stand-in
        key = (src.name, round(float(saturation), 4))
        img = _GRADED.get(key)
        if img is None or img.name not in _images():
            img = src.copy()
            img.name = f"{src.name}-sat{saturation:g}"
            px = np.empty(len(src.pixels), np.float32)
            src.pixels.foreach_get(px)
            img.pixels.foreach_set(grade(px.reshape(-1, 4), saturation).ravel())
            img.pack()
            _GRADED[key] = img
        info.index.source = img


def _images():
    import bpy

    return bpy.data.images


def gloss(mat, color=(0.25, 0.27, 0.3), *, power: float = 4.0, lift: float = 0.0, mix: float = 0.5) -> None:
    """MToon's parametric rim on a material: a fresnel sheen of `color` (linear) at grazing angles, `power` the
    sharper the narrower, lifted by `lift`, `mix` of it following the light (0: always there)."""
    m = _mtoon(mat).extensions.vrmc_materials_mtoon
    m.parametric_rim_color_factor = tuple(float(c) for c in color)
    m.parametric_rim_fresnel_power_factor = float(power)
    m.parametric_rim_lift_factor = float(lift)
    m.rim_lighting_mix_factor = float(mix)


def outline(mat, width: float, color=None, *, lighting: float | None = None, force: bool = False) -> None:
    """A material's MToon outline: `width` metres (world), `color` (linear), `lighting` how much the light colours it.
    A material drawn without one (eyes, brows, the mouth) is left without, unless `force`."""
    m = _mtoon(mat).extensions.vrmc_materials_mtoon
    if m.outline_width_mode == "none" and not force:
        return
    m.outline_width_mode = "worldCoordinates"
    m.outline_width_factor = float(width)
    if color is not None:
        m.outline_color_factor = tuple(float(c) for c in color)
    if lighting is not None:
        m.outline_lighting_mix_factor = float(lighting)


def outline_modifiers(ch: Character) -> list:
    """The add-on's outline modifiers on the character's meshes, as (modifier, its width input)."""
    out = []
    for ob in ch.meshes:
        for md in ob.modifiers:
            if md.type != "NODES" or md.node_group is None or "Outline" not in md.node_group.name:
                continue
            keys = [it.identifier for it in md.node_group.interface.items_tree
                    if it.item_type == "SOCKET" and it.in_out == "INPUT"]
            inputs = getattr(getattr(md, "properties", None), "inputs", None)
            sock = getattr(inputs, keys[4], None) if inputs is not None and len(keys) > 4 else None
            if sock is not None:
                out.append((md, sock))
    return out


def key_outline(ch: Character, width: float, frame: int) -> None:
    """Every outline of the character at `width` metres from `frame` on (keyed, held: a cut changes it at once)."""
    for md, sock in outline_modifiers(ch):
        sock.value = float(width)
        sock.keyframe_insert("value", frame=frame)
        ad = md.id_data.animation_data
        if ad is not None and ad.action is not None:
            from . import toon

            for fc in toon._fcurves(ad.action):
                if fc.data_path.endswith(".value") and md.name in fc.data_path:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "CONSTANT"


def flash(ch: Character, color=(0.85, 0.9, 1.0), amount: float = 0.35, prop: str | None = None) -> None:
    """Let every MToon material of the character whiten with the scene's lightning (toon.FLASH, or `prop`): an
    emission of `color` times the flash times `amount`, over the lit and the shaded side alike."""
    from . import toon

    prop = prop or toon.FLASH
    for mat in ch.materials():
        nt = mat.node_tree
        out = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeGroup" and n.node_tree is not None
                    and "MToon 1.0 Output" in n.node_tree.name), None)
        if out is None or out.inputs["Emissive Factor"].is_linked:
            continue
        mul = nt.nodes.new("ShaderNodeMix")
        mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        k = nt.nodes.new("ShaderNodeMath")
        k.operation = "MULTIPLY"
        k.inputs[1].default_value = float(amount)
        nt.links.new(toon.scene_value(nt, prop), k.inputs[0])
        cc = nt.nodes.new("ShaderNodeCombineColor")
        for i in range(3):
            nt.links.new(k.outputs[0], cc.inputs[i])
        nt.links.new(cc.outputs[0], mul.inputs["A"])
        mul.inputs["B"].default_value = (*color, 1.0)
        nt.links.new(mul.outputs["Result"], out.inputs["Emissive Factor"])
        # the emissive texture multiplies the factor: a white one where the file has none
        tex = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeTexImage" and n.name.startswith("Mtoon1EmissiveTexture")), None)
        if tex is not None and tex.image is not None and tex.image.size[0] * tex.image.size[1] <= 64:
            for link in list(nt.links):
                if link.to_node == out and link.to_socket.name == "Emissive Texture":
                    nt.links.remove(link)
            out.inputs["Emissive Texture"].default_value = (1.0, 1.0, 1.0, 1.0)


def _texture(nt, name: str):
    """A texture node of the add-on's graph with a real image (not its 8x8 stand-in), or None."""
    n = nt.nodes.get(name)
    if n is None or n.image is None or n.image.size[0] * n.image.size[1] <= 64:
        return None
    return n


def anime(ch: Character, tones: dict, key, *, lines=("hair",), line_width: float = 0.001) -> list:
    """Paint the character as anime (blender/lib/toon3d.py) instead of MToon's one even band: each material by the
    toon3d.Tone of its `part` in `tones` ("face_skin", "skin", "cloth", "hair", "face", "eye"; "face_skin" falls back
    to "skin"; a part not given stays MToon), from its own lit and shade textures, normal map and alpha, shaded from
    `key` (toon3d.key: the character's own sun). Each outline's colour is drawn from the surface it goes round
    (toon3d.ink), and the parts in `lines` get an outline where the file has none (VRoid draws none round hair),
    `line_width` metres until `key_outline` keys it. Call it after `wet`, `tint` and `desaturate` (it reads their
    colours; textures they grade stay live) and before `key_outline`. Returns the materials painted."""
    from . import toon3d

    def tone_of(mat):
        p = part(mat.name)
        return tones.get(p) if p != "face_skin" else tones.get(p, tones.get("skin"))

    for mat in ch.materials():
        if part(mat.name) in lines and tone_of(mat) is not None:
            outline(mat, line_width, force=True)
    for ob in ch.meshes:
        if any(s.material is not None and getattr(tone_of(s.material), "form", 0) > 0 for s in ob.material_slots):
            toon3d.form(ob)
    done = []
    for mat in ch.materials():
        tone = tone_of(mat)
        if tone is None or mat.node_tree is None:
            continue
        mt = _mtoon(mat)
        nt = mat.node_tree
        base = _texture(nt, "Mtoon1BaseColorTexture.Image")
        shade = _texture(nt, "Mtoon1ShadeMultiplyTexture.Image")
        out = nt.nodes.get("Mtoon1Material.Mtoon1Output")
        normal = out.inputs["Normal"].links[0].from_socket if out is not None and out.inputs["Normal"].is_linked else None
        factor = tuple(mt.pbr_metallic_roughness.base_color_factor)
        lit = base.outputs["Color"] if base is not None else (1.0, 1.0, 1.0)
        alpha, cutoff = _alpha(mat, base)
        toon3d.paint(mat, lit=lit, factor=factor[:3], shade=shade.outputs["Color"] if shade is not None else None,
                     normal=normal, alpha=alpha, cutoff=cutoff, tone=tone, key=key)
        _unhook(mat)
        ol = mt.outline_material
        if ol is not None and ol.node_tree is not None:
            ob = _texture(ol.node_tree, "Mtoon1BaseColorTexture.Image")
            oa, oc = _alpha(ol, ob)
            toon3d.ink(ol, surface=ob.outputs["Color"] if ob is not None else (1.0, 1.0, 1.0), factor=factor[:3],
                       alpha=oa, cutoff=oc, tone=tone)
            _unhook(ol)
        done.append(mat)
    return done


def smooth(ch: Character, levels: int = 1, *, skip=("face",)) -> list:
    """Subdivide the character's meshes as they render (Catmull-Clark after the skinning, before the outlines): a
    VRoid body's few hundred faces round a sleeve show as a polygon chain on its silhouette and in its shadows. Meshes
    holding a material of a part in `skip` are left (the face: subdividing pulls in its drawn eyelids and brows).
    Returns the meshes subdivided."""
    out = []
    for ob in ch.meshes:
        if any(s.material is not None and part(s.material.name) in skip for s in ob.material_slots):
            continue
        if any(m.type == "SUBSURF" for m in ob.modifiers):
            continue
        sub = ob.modifiers.new("smooth", "SUBSURF")
        sub.levels = sub.render_levels = int(levels)
        sub.boundary_smooth = "PRESERVE_CORNERS"
        sub.use_limit_surface = False
        after = max((i for i, m in enumerate(ob.modifiers) if m.type == "ARMATURE"), default=-1)
        ob.modifiers.move(len(ob.modifiers) - 1, after + 1)
        out.append(ob)
    return out


def _unhook(mat) -> None:
    """Mute the add-on's MToon output group in a material: it holds a material output of its own, which EEVEE renders
    over the material's active one."""
    out = mat.node_tree.nodes.get("Mtoon1Material.Mtoon1Output")
    if out is not None:
        out.mute = True


def _alpha(mat, base):
    """(alpha socket or None, cutoff or None) of an MToon material: its base texture's alpha, cut for a mask."""
    mt = _mtoon(mat)
    if mt.alpha_mode == "OPAQUE" or base is None:
        return None, None
    return base.outputs["Alpha"], (float(mt.alpha_cutoff) if mt.alpha_mode == "MASK" else None)


def wet(ch: Character, *, cloth=(0.62, 0.66, 0.74), hair=(0.6, 0.64, 0.72), skin=(0.9, 0.92, 0.97),
        saturation: float = 0.75, sheen=(0.16, 0.18, 0.22), sheen_power: float = 3.5) -> None:
    """Soaked in the rain: cloth and hair darker and cooler (`cloth`, `hair`: linear gains), their textures toward
    grey (`saturation`) and a cold fresnel sheen on them (`sheen`, `sheen_power`); the skin a little cooler (`skin`)."""
    for which, gain in (("cloth", cloth), ("hair", hair), ("skin", skin)):
        for mat in ch.materials(which):
            tint(mat, gain)
            if which != "skin":
                desaturate(mat, saturation)
                gloss(mat, sheen, power=sheen_power, lift=0.0, mix=0.4)
