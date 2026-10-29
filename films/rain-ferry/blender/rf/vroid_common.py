"""What the Rain Ferry's VRoid cast (rf/vroid_shinza.py, rf/vroid_tsuru.py) shares: where the VRMs live, the
characters' heights, the props' toon colours (wet or dry), how soaked they are, their straw sandals and the planting of
feet.

Animating them (blender/lib/vrm.py's poses, keyed on top of a builder's): the builder leaves the character posed and
its props carried, each by one bone, so a pose keyed later moves them:
  - a prop in a hand (a sword, a pipe, a pole) is carried by that hand's bone (rightHand, leftHand);
  - what is worn (a kasa on the head, a headband) by head; what is slung or hangs on the back (a sheathed sword, a
    kasa on its cord, the mino) by upperChest; an obi by spine; sandals by their foot (leftFoot, rightFoot);
  - a prop that is let go (half a broken blade, a pole laid in a boat) by the character's root alone: a shot moves it
    (or parents it elsewhere) itself.
A builder's hands and feet are held by IK (vrm.reach, vrm.hold, vrm.grasp): the handles are empties under the
armature, `ch.handles["rightHand-target"]` (the wrist), `["rightHand-pole"]` (where the elbow points),
`["rightHand-hold"]` (the hand's turn), the same for leftHand, leftFoot and rightFoot; key the handles to move a held
hand or a planted foot, or `vrm_rig.release(ch)` to drop them and key every bone by vrm.pose alone (the limbs then
stay where the IK had them until a pose turns them).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from lib import shapes, vrm

VROID = Path(__file__).resolve().parents[2] / "assets" / "vroid"
STANDIN = "base_masc"
HEIGHT = {"shinza": 1.76, "tsuru": 1.48}
# how far cloth whitens in a lightning flash (toon.cel's flash): the props of cloth as the painted clothes do
# (shots/standoff.py TONES3D's cloth), a dark kimono staying dark in the strike as the cels draw it
CLOTH_FLASH = 0.03
# the props' toon colours, linear (lit, shade), soaked by the rain (`dry` lifts them)
COLORS = {
    "steel": ((0.85, 0.88, 0.92), (0.3, 0.32, 0.36)),
    "lacquer": ((0.04, 0.04, 0.045), (0.008, 0.008, 0.01)),
    "wrap": ((0.11, 0.1, 0.09), (0.025, 0.022, 0.02)),
    "brass": ((0.42, 0.32, 0.15), (0.12, 0.09, 0.04)),
    "obi": ((0.12, 0.115, 0.105), (0.03, 0.029, 0.027)),
    "band": ((0.42, 0.035, 0.022), (0.16, 0.012, 0.008)),      # red, darkened by the rain
    "bamboo": ((0.42, 0.36, 0.2), (0.14, 0.11, 0.065)),
    "cord": ((0.2, 0.13, 0.08), (0.06, 0.04, 0.025)),
    "straw": ((0.26, 0.205, 0.11), (0.05, 0.04, 0.022)),
    "straw_tip": ((0.4, 0.33, 0.19), (0.1, 0.075, 0.045)),
    "straw_dark": ((0.18, 0.14, 0.075), (0.04, 0.03, 0.018)),
    "rope": ((0.16, 0.12, 0.07), (0.04, 0.03, 0.018)),
    "stem": ((0.07, 0.045, 0.03), (0.018, 0.012, 0.008)),        # a kiseru's dark lacquered bamboo
    "wood": ((0.3, 0.22, 0.13), (0.08, 0.055, 0.032)),           # a hairpin's plain wood
}
# how much lighter each of those is dry (cloth, straw and wood drink the rain; steel, lacquer and brass do not)
DRY = {"band": 1.7, "bamboo": 1.25, "cord": 1.45, "straw": 1.55, "straw_tip": 1.35, "straw_dark": 1.6, "rope": 1.5,
       "obi": 1.35, "wrap": 1.3, "wood": 1.35}
# the characters soaked (vrm.wet's gains at wet=1, eased to none at wet=0)
SOAK = dict(saturation=0.75, sheen=(0.16, 0.18, 0.22))
SOLE = 0.016                  # a straw sandal's thickness


def vrm_file(name: str) -> Path:
    path = VROID / f"{name}.vrm"
    if not path.exists():
        print(f"vroid_common: no {path.name} yet; {STANDIN}.vrm stands in for {name}")
        path = VROID / f"{STANDIN}.vrm"
    return path


def colors(wet: float = 1.0, extra: dict | None = None) -> dict:
    """The props' colours (and `extra`, a character's own), `wet` from 1 (soaked, as COLORS has them) to 0 (dry)."""
    out = {}
    for k, (lit, shade) in {**COLORS, **(extra or {})}.items():
        g = 1.0 + (DRY.get(k, 1.0) - 1.0) * (1.0 - wet)
        out[k] = (tuple(min(1.0, c * g) for c in lit), tuple(min(1.0, c * g) for c in shade))
    return out


def eased(gain, wet: float):
    """A gain (one, or per channel) eased from none (wet=0) to itself (wet=1)."""
    g = np.asarray(gain, float)
    out = 1.0 + (g - 1.0) * wet
    return tuple(out) if out.ndim else float(out)


def soak(ch, wet: float, *, cloth=(0.62, 0.66, 0.74), hair=(0.6, 0.64, 0.72), skin=(0.9, 0.92, 0.97)) -> None:
    """The character `wet` (1 soaked: vrm.wet with these gains; 0 dry, left as it is)."""
    if wet <= 0.0:
        return
    vrm.wet(ch, cloth=eased(cloth, wet), hair=eased(hair, wet), skin=eased(skin, wet),
            saturation=eased(SOAK["saturation"], wet), sheen=tuple(np.asarray(SOAK["sheen"]) * wet))


def plant(ch, feet: dict) -> None:
    for side, (at, pole, turn) in feet.items():
        vrm.reach(ch, f"{side}Foot", at, pole=pole)
        vrm.hold(ch, f"{side}Foot", turn)


def sandals(ch, m: dict, coll, name: str, *, size: float = 1.0, ties: bool = False) -> list:
    """Straw sandals under each posed foot (on the ground, along the foot), `size` times a small foot's: a straw sole
    and its thong from between the first toes over the forefoot to either side (zori); with `ties` (waraji) a cord
    from the sole's sides up round the ankle. Each carried by its foot. Returns them."""
    obs = []
    s = ch.scale * size
    for side in ("left", "right"):
        a = np.array(ch.point(f"{side}Foot"))
        t = np.array(ch.point(f"{side}Toes"))
        f = t - a
        f[2] = 0.0
        f /= np.linalg.norm(f)
        inward = np.cross((0.0, 0.0, 1.0), f) * (-1.0 if side == "left" else 1.0)   # toward the other foot
        heel, toe = a - f * 0.052 * s, a + f * 0.155 * s
        heel[2] = toe[2] = SOLE / 2
        along = lambda k, across=0.0, up=0.0: heel + (toe - heel) * k + inward * across * s + np.array([0, 0, up])  # noqa: E731
        path = [along(k) for k in (0.0, 0.05, 0.3, 0.6, 0.85, 0.97, 1.0)]
        half = np.array([0.018, 0.028, 0.031, 0.036, 0.034, 0.026, 0.012]) * s
        obs.append(shapes.loft(f"{name}-zori-{side}", path, half, SOLE / 2, material=m["straw"], coll=coll, n=12,
                               power=3.0, subsurf=0, up=(0.0, 0.0, 1.0)))
        # the thong: from the post between the big toe and the next, up over the forefoot, down to the sole's edges
        post = along(0.83, 0.012, SOLE / 2)
        for k, sgn in enumerate((1.0, -1.0)):
            path = [post, along(0.74, 0.012 + sgn * 0.012, SOLE / 2 + 0.03 * s),
                    along(0.62, sgn * 0.026, SOLE / 2 + 0.03 * s), along(0.55, sgn * 0.034, SOLE / 2)]
            obs.append(shapes.loft(f"{name}-hanao-{side}{k}", path, 0.004 * s, material=m["cord"], coll=coll, n=6,
                                   subsurf=0))
        if ties:
            # waraji: a cord from each side of the heel up and round behind the ankle, crossing in front
            ankle = a + np.array([0.0, 0.0, 0.01])
            for k, sgn in enumerate((1.0, -1.0)):
                path = [along(0.18, sgn * 0.03, SOLE / 2), ankle + inward * sgn * 0.035 * s - f * 0.01,
                        ankle - f * 0.05 * s, ankle - inward * sgn * 0.035 * s + f * 0.01 + np.array([0, 0, 0.012]),
                        ankle + f * 0.04 * s + np.array([0, 0, 0.004])]
                obs.append(shapes.loft(f"{name}-himo-{side}{k}", path, 0.0035 * s, material=m["cord"], coll=coll, n=6,
                                       subsurf=0))
    for ob in obs:
        vrm.attach(ob, ch, ("left" if "-left" in ob.name else "right") + "Foot")
        ob["outline"] = False
    return obs


def to_frame(ch, p) -> np.ndarray:
    """A point in the world in the character's frame (Character.world undone)."""
    import bpy

    bpy.context.view_layer.update()
    arm = ch.armature.matrix_world.inverted() @ _vec(p)
    return ch.frame.T @ np.array(arm) * ch.scale


def posed(ch, bone: str, p) -> np.ndarray:
    """Where a point of the character's frame at rest (on its face, its shoulder) has gone as posed, carried by a
    humanoid bone: in the character's frame."""
    import bpy

    bpy.context.view_layer.update()
    pb = ch.bone(bone)
    arm = pb.matrix @ pb.bone.matrix_local.inverted() @ ch.to_armature(p)
    return ch.frame.T @ np.array(arm) * ch.scale


def move(ob, a0, d0, a1, d1) -> None:
    """Move `ob` (world) so its point `a0` goes to `a1` and its direction `d0` turns to `d1` (the shortest turn): a
    pole's section lifted from where it was built into a hand."""
    from mathutils import Matrix

    d0, d1 = _vec(d0).normalized(), _vec(d1).normalized()
    turn = d0.rotation_difference(d1).to_matrix().to_4x4()
    ob.matrix_world = Matrix.Translation(_vec(a1)) @ turn @ Matrix.Translation(-_vec(a0)) @ ob.matrix_world


def _vec(p):
    from mathutils import Vector

    return Vector(tuple(float(c) for c in p))
