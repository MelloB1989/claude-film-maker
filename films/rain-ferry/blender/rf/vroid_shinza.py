"""Shinza from his VRoid Studio model (films/rain-ferry/assets/vroid/shinza.vrm) for the standoff: his low guard,
soaked, with what VRoid does not make (blender/lib/props.py): his katana, his obi and his headband knotted at the back.
VRoid dresses him in a shirt and a long pleated skirt; the core's blender/lib/vrm_rig.py makes them a kimono (one dark
colour, the shirt's collar cut away for a kimono's V and its collar laid crossing the chest) and hakama (dark slate,
let down to his ankles), bares his feet, parts his bangs off his eyes and gives him a closed-mouthed glare.
rf/vroid_cast.py describes what the builder returns."""
from __future__ import annotations

import numpy as np

from lib import anime, props, vrm, vrm_rig

from .vroid_common import CLOTH_FLASH, COLORS, HEIGHT, plant, vrm_file

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
HILT, BLADE = 0.27, 0.72
GRIPS = {"left": 0.045, "right": 0.16}      # each hand's hole along the hilt from the pommel (m)
TSUKA = 0.013                               # the hilt's half thickness (props.katana's wrap), for the fingers
SH_ELBOWS = {"left": (0.55, 0.15, 0.6), "right": (-0.55, -0.05, 0.6)}
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
# ---- his clothes (heights at rest, metres as he stands). The kimono and hakama one colour each (linear lit, shade),
# their prints gone and their folds kept (vrm_rig.recolor)
KIMONO = ((0.04, 0.043, 0.056), (0.014, 0.015, 0.024))
HAKAMA = ((0.05, 0.053, 0.062), (0.018, 0.019, 0.027))
CLOTH_INK = (0.006, 0.006, 0.009)      # their outlines
# the hakama let down from just under the knee to the ankles, flaring
HEM = (0.55, 0.075, 0.3)
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


def shinza(coll, look, name: str = "shinza") -> dict:
    # his collars, obi and hilt wrap whiten in the strike as his kimono does
    m = anime.palette({**COLORS, **SH_COLORS}, look, prefix=name, cuts={"steel": 0.55},
                      flashes={k: CLOTH_FLASH for k in ("eri", "juban", "obi", "wrap")})
    ch = vrm.load(vrm_file(name), coll, name=name)
    vrm.scale_to(ch, HEIGHT["shinza"])
    vrm.wet(ch)
    vrm.flash(ch)
    dress(ch, m, name)
    # what VRoid does not make, tied on at rest: the obi over the top's waist, the headband over his hair across the
    # forehead, knotted at the back with its two tails
    eye = ch.rest("leftEye")[2] - ch.rest("head")[2]
    vrm.band(ch, f"{name}-obi", "spine", 0.0, 0.075, material=m["obi"], push=0.006, thickness=0.006, limit=0.24)
    vrm.band(ch, f"{name}-band", "head", eye + 0.045, 0.028, material=m["band"], push=0.002, thickness=0.003,
             tilt=-6.0, limit=0.16, knot=0.018, tails=[(0.3, 0.03, 18.0), (0.24, 0.028, -14.0)])

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

    p0 = ch.world(POMMEL)
    sword = props.katana(f"{name}-katana", m, tuple(p0), tuple(ch.world(POMMEL + hilt) - p0), hilt=HILT, blade=BLADE,
                         coll=coll)
    for ob in sword:
        vrm.attach(ob, ch, "rightHand")

    vrm_rig.compose(ch, "glare", GLARE)
    vrm_rig.compose(ch, "narrow", NARROW)
    bangs = [c for c in vrm_rig.chains(ch) if c[0] in BANGS]
    vrm_rig.part(ch, bangs, PART[0], down=PART[1])
    for chain in vrm_rig.chains(ch):
        if chain[0] == MIDDLE[0]:
            vrm_rig.sweep(ch, chain, MIDDLE[1], MIDDLE[2])
            vrm_rig.thin(ch, chain, *MIDDLE[3])

    def face(eyes: float = 1.0) -> dict:
        """A hard glare, the mouth shut; narrowing as `eyes` falls from 1 to NARROWED."""
        return {"glare": 1.0, "narrow": min(1.0, max(0.0, (1.0 - eyes) / (1.0 - NARROWED)))}

    vrm.express(ch, face())
    return {"root": ch.root, "vrm": ch, "head": tuple(ch.face()), "face": face, "props": sword}


def dress(ch, m, name: str) -> None:
    """VRoid's shirt and skirt as a kimono and hakama, his feet bare (at rest, before posing)."""
    body = next((ob for ob in ch.meshes if vrm_rig.faces_of(ob, "Bottoms").size), None)
    if body is None:
        print(f"vroid_shinza: {name} has no Bottoms to dress; left as VRoid made him")
        return
    for which, (lit, shade) in (("Tops", KIMONO), ("Bottoms", HAKAMA)):
        # the shirt's cuffs and the skirt's waistband cut in a zigzag (feathers in a close-up) made whole: a kimono's
        # sleeves and a hakama's waist end clean
        for mat in ch.materials("cloth"):
            if which in mat.name:
                vrm_rig.recolor(mat, lit, shade, opaque=True, outline=CLOTH_INK)
    bottoms, tops = vrm_rig.faces_of(body, "Bottoms"), vrm_rig.faces_of(body, "Tops")
    skin, shoes = vrm_rig.faces_of(body, "Body_00_SKIN"), vrm_rig.faces_of(body, "Shoes")
    vrm_rig.lengthen(ch, body, bottoms, HEM[0], HEM[1], flare=HEM[2])

    c = vrm_rig.face_centers(ch, body)

    def in_v(p):
        half = V_HALF * np.clip((p[:, 2] - CROSS) / (NECK - CROSS), 0, None)
        return (p[:, 1] < 0.02) & (p[:, 2] > CROSS) & (np.abs(p[:, 0]) < half)

    sc = c[skin]
    # the skin in the V, round the neck and below the old hem (VRoid's white socks) his own, from his throat
    tone = vrm_rig.sample(body, skin[(sc[:, 2] > NECK + 0.02) & (sc[:, 2] < NECK + 0.07) & (sc[:, 1] < 0.0)])
    bare = skin[in_v(sc) | ((sc[:, 2] > NECK - 0.03) & (sc[:, 2] < NECK + 0.1)) | (sc[:, 2] < HEM[0] - 0.1)]
    vrm_rig.paint(body, bare, tone)
    under = skin[(sc[:, 2] > UNDER[0]) & (sc[:, 2] < UNDER[1]) & (np.abs(sc[:, 0]) < UNDER[2]) & ~in_v(sc)]
    vrm_rig.cut(body, np.concatenate([tops[((c[tops, 2] > NECK) & (c[tops, 1] < NAPE)) | in_v(c[tops])], shoes, under]))
    # laid on what is left of the shirt (bridging the gap between its cut edge and his neck, so its inside stays hidden)
    on = [(body, vrm_rig.faces_of(body, "Tops"))]
    for i, path in enumerate((ERI, ERI_UNDER)):
        lift = 0.002 * (i == 0)      # the left side's over the right's
        vrm_rig.collar(ch, f"{name}-eri{i}", path, ERI_WIDTH[:len(path)], on=on, material=m["eri"], push=0.007 + lift)
        # under its collar, thinner: the two never cross in depth
        vrm_rig.collar(ch, f"{name}-juban{i}", path[:7], JUBAN[0], on=on, material=m["juban"], push=0.0045 + lift,
                       thickness=0.002, shift=JUBAN[1][i] * np.array(ERI_WIDTH[:7]) / 2)
