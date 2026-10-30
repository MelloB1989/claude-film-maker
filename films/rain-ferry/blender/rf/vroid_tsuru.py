"""Tsuru from her VRoid Studio model (films/rain-ferry/assets/vroid/tsuru.vrm), as STORY.md has her: an old woman,
small and wiry, very still; aged where VRoid paints young (blender/lib/vrm_skin.py: her face's lines, folds and spots,
a soft grey hairline, grey brows, heavy lids), her hair white and gathered in a low bun held with a plain wooden pin
(VRoid's ponytail hidden), a faded indigo kimono, the sneakers VRoid gave her swapped for dark tabi and straw sandals,
and what VRoid does not make (blender/lib/props.py): her straw rain cape (mino), her long thin kiseru and her bamboo
ferry pole, wrapped with worn cord near the top, which hides a thin straight blade.

    tsuru(coll, look, pipe=None, pole="hand", seated=False, wet=1.0)

  pipe    "hand" (in her left hand, the bowl forward), "mouth" (its mouthpiece at her lips, her left hand on the stem)
          or None
  pole    "hand" (upright in her right hand: the standoff), "shoulder" (on her right shoulder, held in front of it),
          "boat" (not with her: laid on the ground at her right, carried by her root alone, for a shot to put in its
          boat) or "drawn" (parted at the cord: the handle and its blade in her right hand, the blade forward and low,
          the shaft upright in her left; with "drawn" the pipe goes)
  seated  sitting on something knee high (a post, a boat's edge: 0.42 m under her), her feet on the ground in front
  wet     1 soaked (the standoff) to 0 dry (after the rain)

Returns rf/vroid_cast.py's dict and "parts": {"pole" (the pole, or its shaft), "handle" (its handle, with the blade:
empty unless it can part), "blade", "pipe", "bun", "mino", "sandals"}, each a list of objects whose first is the one to
move. What carries what is rf/vroid_common.py's: the pole (or the handle, with the blade) by rightHand, the shaft drawn
by leftHand, the pipe by leftHand, the bun and pin by head, the mino by upperChest; the pole laid down ("boat") by her
root. The pole always parts at the cord: move parts["handle"][0] off it to draw the blade."""
from __future__ import annotations

import math

import numpy as np

from lib import anime, props, vrm, vrm_rig, vrm_skin as skin

from .vroid_common import HEIGHT, SOLE, colors, move, plant, posed, sandals, soak, to_frame, vrm_file

MM = 1e-3

# ---- Tsuru standing still: small and perfectly upright, the back straight, the head level and the chin a little down,
# the shoulders square; the pole upright in her right hand before her right shoulder, the left arm hanging (lib/vrm.py's
# turns). Her age is in her walk (vrm_anim's "old" gait), not her stance
TS_HIPS = (0.0, 0.0, -0.01)
TS_POSE = {"spine": (1.0, 0.0, 0.0), "chest": (1.0, 0.0, 0.0), "upperChest": (0.0, 0.0, 0.0),
           "neck": (2.0, 0.0, 0.0), "head": (5.0, 0.0, 2.0),
           "leftShoulder": (0.0, 3.0, 0.0), "rightShoulder": (0.0, -3.0, 0.0), **vrm.hand_pose("left")}
LEFT_HAND = ((0.19, -0.03, 0.68), (0.5, 0.6, 0.9))   # where the hanging left hand's wrist is, and its elbow's pole
# her knuckles forward round the upright pole, the palm in and back (square in, the pole reads beside her fist)
POLE_PALM = (0.55, 0.85, 0.0)
POLE_R, HANDLE_R = 0.022, 0.016      # the pole's radius (props.ferry_pole), its corded handle's, for her fingers
# seated, a hand resting on her thigh: the palm down on it, the fingers forward and over its front (vrm.hold's turn)
LAP_TURN = {"left": (0.0, 20.0, 90.0), "right": (0.0, -20.0, -90.0)}
ELBOWS = {"left": 25.0, "right": 70.0}   # how far each elbow starts folded for its IK (vrm.reach): the right well in
FEET = {"left": ((0.09, 0.03), (0.1, -1.0, 0.45), (0.0, 0.0, 8.0)),
        "right": ((-0.09, -0.01), (-0.1, -1.0, 0.45), (0.0, 0.0, -8.0))}
# ---- seated on something SEAT high: the hips down onto it, the thighs forward and level, the shins down to her feet
# on the ground a little in front, upright as she stands
SEAT = 0.42
# seated, the skirt taken in round each leg from hip to ankle, and the cloth between her knees round the line between
# them (radius, keep, ease: vrm_rig.cinch), so it lies on her lap and falls past her shins as heavy cloth, no bell
LAP = {"leg": (0.1, 0.2, 0.3)}
SEATED_HANDS = -0.24          # how much lower her held pipe is (m)
SEATED_POSE = {"spine": (1.0, 0.0, 0.0), "chest": (1.0, 0.0, 0.0), "upperChest": (0.0, 0.0, 0.0),
               "neck": (2.0, 0.0, 0.0), "head": (5.0, 0.0, 2.0),
               "leftUpperLeg": (-84.0, 0.0, -5.0), "rightUpperLeg": (-84.0, 0.0, 5.0),
               "leftLowerLeg": (82.0, 0.0, 0.0), "rightLowerLeg": (82.0, 0.0, 0.0),
               "leftShoulder": (0.0, 3.0, 0.0), "rightShoulder": (0.0, -3.0, 0.0)}
SEATED_FEET = {"left": ((0.11, -0.4), (0.15, -1.5, 0.6), (0.0, 0.0, 10.0)),
               "right": ((-0.11, -0.38), (-0.15, -1.5, 0.6), (0.0, 0.0, -10.0))}
# ---- her pole: its foot before her right shoulder (her frame), its top; where her right hand holds it upright
# (standing, seated); it parts at SPLIT, the cord wound from there up GRIP long, its blade BLADE long inside the shaft
POLE = (-0.24, -0.2)
POLE_TOP = 2.1
GRIP_Z = {False: 0.98, True: 0.66}
SPLIT, CORD, BLADE = 1.66, 0.2, 0.62
# on her shoulder: resting on the top of her right shoulder (a point over it, her frame at rest), the long end back
# and up over it, the top (its way) forward and down to her right hand `hand` ahead of the shoulder, at her chest
SHOULDER = dict(over=(-0.13, 0.02, 0.06), way=(0.0, -0.8, -0.6), behind=1.3, hand=0.38)
# laid down at her right (the foot behind her)
LAID = dict(foot=(-0.35, 0.85, 0.024), way=(0.0, -1.0, 0.0))
# drawn: her right hand on the handle (its wrist; the blade from the fist forward and down: its way), the shaft upright
# in her left hand, held low at her side
DRAWN = dict(grip=(-0.17, -0.3, 0.95), way=(0.15, -0.88, -0.45), shaft=(0.24, -0.08, 0.72))
# ---- her kiseru: in her left hand before her at the waist, the bowl forward and a little out; in her mouth, from the
# left corner of her lips forward, down and out, her hand low on its stem and her elbow out at her side (her face
# clear of her forearm)
KISERU = 0.3
PIPE_HAND = dict(hole=(0.13, -0.24, 0.86), way=(-0.15, -0.95, 0.15))
PIPE_MOUTH = dict(way=(0.45, -0.65, -0.62), hold=0.22, elbow=(0.5, 0.0, 0.85))
# ---- her hair: white, the ponytail's strands (VRoid's chains behind her head, rooted below its crown) hidden, the
# rest gathered into a low bun at the back of her head (its middle off the head bone: behind, up; its half sizes),
# a wooden pin through it, aslant
HAIR_WHITE = ((0.78, 0.78, 0.8), (0.42, 0.44, 0.5))
BUN = dict(at=(0.0, 0.085, 0.035), radii=(0.05, 0.036, 0.04), pin=(0.16, 0.0035, 24.0))
# ---- her robe recoloured a faded indigo (linear lit, shade)
INDIGO = ((0.055, 0.075, 0.15), (0.018, 0.026, 0.06))
# its wide sleeves taken in (tied back for work: vrm_rig.cinch) to SLEEVE metres round her arms, keeping `keep` of
# the rest, so a hand raised to her face never buries it
SLEEVE = (0.045, 0.1)
TS_COLORS = {"hair": HAIR_WHITE}

# ---- her face. The marks are drawn on a front view of it (lib/vrm_skin.py: projected along +y onto the face's skin),
# placed from its landmarks, in metres; colours as the texture holds them (sRGB)
LINE = (0.5, 0.33, 0.27)      # a line's colour, multiplied into the skin
SHADE = (0.7, 0.55, 0.52)     # a fold's or a hollow's shadow
SPOT = (0.66, 0.48, 0.36)     # an age spot
# a few age spots (x, z: metres on the face's front view, + her left) and their sizes
SPOTS = [((0.074, 1.362), 3.2), ((0.058, 1.303), 2.2), ((-0.034, 1.392), 2.6), ((-0.066, 1.296), 3.0),
         ((0.069, 1.27), 2.0), ((-0.081, 1.346), 2.4), ((0.012, 1.398), 1.6)]
# her expressions, composed from VRoid's per-part shape keys and her own (hood: the upper lids heavy, more at their
# outer corners; brow-low: the brows down and flat; press: the lips pressed thin; sneer: one corner drawn up): calm
# and half-lidded with the faint smile, and the glare, narrowed under low brows, the mouth a tight thin line
FACES = {
    "tsuru-calm": {"tsuru-hood": 0.5, "tsuru-brow-low": 0.6, "Fcl_EYE_Close": 0.0, "Fcl_BRW_Angry": 0.1,
                   "Fcl_MTH_Close": 1.0, "tsuru-press": 0.3, "Fcl_MTH_Fun": 0.2},
    "tsuru-glare": {"tsuru-hood": 0.45, "Fcl_EYE_Angry": 0.5, "tsuru-brow-low": 1.0, "Fcl_BRW_Angry": 0.3,
                    "Fcl_MTH_Close": 1.0, "tsuru-press": 1.0, "tsuru-sneer": 0.8},
}


def _at(x: float, z: float) -> tuple:
    """A point on the face's front view (the projection ignores its depth)."""
    return (x, -0.2, z)


def wrinkles(lm: dict) -> list:
    """Her face's lines, folds, hollows and spots (vrm_skin.Mark), from its landmarks (vrm_skin.landmarks)."""
    marks = []
    line = dict(color=LINE, blend="multiply")
    brow_top = max(lm[s]["brow_inner"][2] for s in ("left", "right")) + 0.012
    for side, s in (("left", 1.0), ("right", -1.0)):
        e = lm[side]
        o, i, t, b, m = e["outer"], e["inner"], e["top"][2], e["bottom"][2], e["middle"]
        # crow's feet: fanned out from past the outer corner, fine and fading
        for ang, length in ((30.0, 10.0), (8.0, 13.0), (-14.0, 12.0), (-36.0, 9.0)):
            a = math.radians(ang)
            x0, z0 = o[0] + s * 3.5 * MM, o[2] + 0.5 * MM
            dx, dz = s * math.cos(a) * length * MM, math.sin(a) * length * MM
            marks.append(skin.Mark([_at(x0, z0), _at(x0 + dx * 0.5, z0 + dz * 0.5 - 0.6 * MM), _at(x0 + dx, z0 + dz)],
                                   0.9 * MM, strength=0.4, taper=(0.8, 0.1), **line))
        # the bags under the eyes: a crescent and a fainter one below it, a cool shadow over them
        marks.append(skin.Mark([_at(i[0] + s * 3 * MM, b - 2.5 * MM), _at(m[0], b - 6 * MM),
                                _at(o[0] - s * 2 * MM, b - 4.5 * MM), _at(o[0] + s * 2 * MM, b - 2 * MM)],
                               1.0 * MM, strength=0.4, taper=(0.15, 0.3), **line))
        marks.append(skin.Mark([_at(i[0] + s * 1 * MM, b - 5 * MM), _at(m[0] - s * 2 * MM, b - 11 * MM),
                                _at(o[0] + s * 1 * MM, b - 12 * MM)], 0.9 * MM, strength=0.22, taper=(0.2, 0.2), **line))
        marks.append(skin.Mark([_at(i[0] + s * 4 * MM, b - 3 * MM), _at(m[0], b - 4.5 * MM),
                                _at(o[0] - s * 3 * MM, b - 3.5 * MM)], 5.5 * MM, color=(0.66, 0.52, 0.55),
                               strength=0.16, soft=1.0, taper=(0.5, 0.5)))
        # the fold of the heavy upper lid, sagging over the outer corner
        marks.append(skin.Mark([_at(i[0] + s * 2 * MM, t + 3 * MM), _at(m[0], t + 4.5 * MM),
                                _at(o[0] - s * 2 * MM, t + 2 * MM), _at(o[0] + s * 3.5 * MM, o[2] - 1.5 * MM)],
                               1.0 * MM, strength=0.42, taper=(0.2, 0.4), **line))
        # the folds from the nose's wings past the mouth's corners, their shadow on the mouth's side
        mc = lm["mouth_left" if s > 0 else "mouth_right"]
        nz = lm["nose"][2]
        fold = [_at(s * 17 * MM, nz - 1 * MM), _at(s * 22 * MM, nz - 9 * MM), _at(mc[0] + s * 6 * MM, mc[2] - 1 * MM),
                _at(mc[0] + s * 6.5 * MM, mc[2] - 5 * MM)]
        marks.append(skin.Mark(fold, 1.3 * MM, strength=0.42, taper=(0.12, 0.2), **line))
        marks.append(skin.Mark([(p[0] - s * 2.5 * MM, p[1], p[2]) for p in fold], 5 * MM, color=SHADE, strength=0.12,
                               soft=1.0, taper=(0.3, 0.3)))
        # the lines down from the mouth's corners toward the jaw
        marks.append(skin.Mark([_at(mc[0] + s * 1.5 * MM, mc[2] - 3 * MM), _at(mc[0] + s * 2.5 * MM, mc[2] - 8 * MM),
                                _at(mc[0] + s * 3 * MM, mc[2] - 14 * MM)], 0.9 * MM, strength=0.24, taper=(0.3, 0.1),
                               **line))
        # the frown's two short lines between the brows
        bi = e["brow_inner"]
        marks.append(skin.Mark([_at(s * 4 * MM, bi[2] - 3 * MM), _at(s * 4.5 * MM, bi[2] + 3 * MM),
                                _at(s * 4 * MM, bi[2] + 9 * MM)], 0.9 * MM, strength=0.36, taper=(0.2, 0.4), **line))
        # the cheeks fallen in under the cheekbones
        marks.append(skin.Mark([_at(s * 0.058, 1.304), _at(s * 0.055, 1.287), _at(s * 0.048, 1.27)], 18 * MM,
                               color=SHADE, strength=0.1, soft=1.0, taper=(0.5, 0.5)))
    # the forehead's lines, wavering across it above the brows
    for k, (dz, span) in enumerate(((0.0, 27.0), (6.0, 31.0), (12.0, 25.0))):
        z = brow_top + dz * MM
        wob = (0.0, 0.9, -0.5, 0.8, 0.0) if k % 2 == 0 else (0.0, -0.6, 0.7, -0.4, 0.0)
        xs = np.linspace(-span, span, 5) * MM
        marks.append(skin.Mark([_at(x, z + w * MM) for x, w in zip(xs, wob)], 0.8 * MM, strength=0.3, taper=(0.1, 0.1),
                               **line))
    # the crease under the lower lip
    mz = lm["mouth"][2]
    marks.append(skin.Mark([_at(-8 * MM, mz - 9 * MM), _at(0.0, mz - 10.5 * MM), _at(8 * MM, mz - 9 * MM)], 1.0 * MM,
                           strength=0.25, taper=(0.2, 0.2), **line))
    for (x, z), size in SPOTS:
        marks.append(skin.Mark([_at(x, z)], size * MM, color=SPOT, strength=0.3, soft=0.6))
    return marks


def _face_mesh(ch):
    """The mesh her expressions move (VRoid's Face)."""
    return next(ob for binds in ch.expressions.values() for ob, _, _ in binds)


def _material(ch, part: str):
    return next(m for m in ch.materials() if part in m.name)


def age(ch) -> dict:
    """Her face and hair made old: the marks painted into her face's texture (its lips thinned to a pale line, its
    colour a little sallow), the hood shape key, grey brows, dimmer catchlights and a soft grey hairline. Returns the
    face's landmarks."""
    face = _face_mesh(ch)
    lm = skin.face_landmarks(face)
    face_skin = next(m for m in ch.materials("skin") if face.material_slots.find(m.name) >= 0)
    surf = skin.surface(face, face_skin)
    marks = wrinkles(lm)

    def paint_face(px):
        lips = (px[..., 0] - px[..., 1]) > 0.25
        skin.lighten(px, (0.95, 0.9, 0.9), saturation=0.3, lift=0.35, where=lips)
        skin.lighten(px, saturation=0.86)
        return skin.paint(px, surf, marks, along=(0.0, 1.0, 0.0))

    skin.retexture(face_skin, paint_face, scale=2, tag="aged")
    # the body's skin (her hands, her neck) as sallow as her face
    for m in ch.materials("skin"):
        if m is not face_skin:
            skin.retexture(m, lambda px: skin.lighten(px, saturation=0.86), tag="aged")

    # heavy upper lids: VRoid's closing eyes' offsets on the upper lids only, more toward the outer corners
    def hood(co):
        w = np.zeros(len(co))
        for side, s in (("left", 1.0), ("right", -1.0)):
            e = lm[side]
            ax, ox = abs(e["inner"][0]), abs(e["outer"][0])
            on = (co[:, 0] * s > 0) & (np.abs(co[:, 0]) < ox + 0.015) & (np.abs(co[:, 2] - e["middle"][2]) < 0.02)
            u = np.clip((np.abs(co[:, 0]) - ax) / (ox - ax), 0.0, 1.0)
            w = np.where(on, (0.3 + 0.7 * skin.smoothstep(0.0, 1.0, u))
                         * skin.smoothstep(e["middle"][2] - 0.002, e["middle"][2] + 0.002, co[:, 2]), w)
        return w

    skin.derive(face, "tsuru-hood", "Fcl_EYE_Close", hood)
    # brows lowered and flattened (VRoid's angry brows only knit them), their outer ends sagging; one corner of the
    # mouth drawn back and up a little (contempt); both driven by her expressions
    brow = [(e["brow_inner"] + e["brow_outer"]) / 2 for e in (lm["left"], lm["right"])]
    skin.sculpt(face, "tsuru-brow-low", [(c, (0.0, 0.0, -2.5 * MM), 0.04) for c in brow]
                + [(lm[sd]["brow_outer"], (0.0, 0.0, -1.5 * MM), 0.015) for sd in ("left", "right")],
                value=0.0, only=_material(ch, "FaceBrow"))
    skin.sculpt(face, "tsuru-sneer", [(lm["mouth_left"], (1.0 * MM, 1.0 * MM, 1.2 * MM), 0.012)], value=0.0)
    # the lips pressed thin: both corners drawn back and out
    skin.sculpt(face, "tsuru-press", [(lm["mouth_left"], (1.5 * MM, 1.5 * MM, 0.0), 0.012),
                                      (lm["mouth_right"], (-1.5 * MM, 1.5 * MM, 0.0), 0.012)], value=0.0)

    # grey brows, a little heavier
    def brows(px):
        skin.soften(px, radius=3, feather=0.25, level=0.3, bleed=6)
        return skin.lighten(px, (1.0, 1.0, 1.02), saturation=0.08, lift=0.5)

    skin.retexture(_material(ch, "FaceBrow"), brows, tag="grey")
    # the catchlights dimmed: old eyes, and hard ones
    hl = _material(ch, "EyeHighlight").vrm_addon_extension.mtoon1.pbr_metallic_roughness
    hl.base_color_factor = (*tuple(hl.base_color_factor)[:3], 0.35)

    # the hairline: VRoid's zigzag smoothed back a little and softened, fine hairs across it, combed back
    rng = np.random.default_rng(7)

    def hairline(px):
        h, w = px.shape[:2]
        skin.soften(px, radius=max(4, w // 90), feather=0.3, level=0.62, bleed=w // 40)
        front = np.zeros((h, w), bool)
        front[int(h * 0.42):] = True
        skin.strands(px, 520, w / 70, w / 640, rng=rng, where=front, color=(0.62, 0.62, 0.63), strength=0.9)
        # combed: long fine streaks from the hairline back toward the nape
        ys, xs = np.nonzero((px[..., 3] > 0.9) & front)
        for k in rng.choice(len(xs), size=min(160, len(xs)), replace=False):
            p0 = np.array([xs[k], ys[k]], float)
            p1 = p0 + (np.array([w * 0.5, h * 0.2]) - p0) * rng.uniform(0.25, 0.45)
            mid = (p0 + p1) / 2 + rng.normal(0, w * 0.01, 2)
            tone = (0.78, 0.78, 0.8) if rng.uniform() < 0.5 else (0.36, 0.36, 0.38)
            skin.stroke(px, [p0, mid, p1], w / 500, tone, 0.22, blend="mix")
        return px

    back = _material(ch, "HairBack")
    skin.retexture(back, hairline, scale=2, tag="hairline")
    skin.blend_alpha(back)
    return lm


def robe(ch) -> None:
    """The robe's white collar, cuffs and lining gone: everything light in its texture made the robe's own dark."""
    for m in ch.materials("cloth"):
        if "Tops" not in m.name:
            continue

        def dark(px):
            y = skin.luma(px)
            body = (y < 0.3) & (px[..., 3] > 0.5)
            return skin.replace(px, y > 0.32, np.median(px[body][:, :3], axis=0), grow=3)

        skin.retexture(m, dark, tag="plain")


def tabi(ch) -> float:
    """VRoid's sneakers off, her feet in dark tabi (painted into the body's skin, up under the robe's hem). Returns how
    high her bare soles are off the ground as she stands (the sneakers' soles were under them)."""
    body = next(ob for ob in ch.meshes if any(s.material and "Shoes" in s.material.name for s in ob.material_slots))
    skin.drop_faces(body, "Shoes")
    body_skin = next(mt for mt in ch.materials("skin") if body.material_slots.find(mt.name) >= 0)
    surf = skin.surface(body, body_skin)
    low = surf.tris[:, :, 2].max(axis=1) < 0.24 / ch.scale
    skin.retexture(body_skin, lambda px: skin.fill(px, surf.uvs[low], (0.13, 0.135, 0.16)), tag="tabi")
    return float(surf.tris[:, :, 2].min()) * ch.scale




def indigo(ch) -> None:
    """Her robe (VRoid's top and bottoms) one faded indigo, its folds kept, its sleeves taken in."""
    for mat in ch.materials("cloth"):
        if "Tops" in mat.name or "Bottoms" in mat.name:
            vrm_rig.recolor(mat, *INDIGO, opaque=True)
    for ob in ch.meshes:
        tops = vrm_rig.faces_of(ob, "Tops")
        if tops.size and ob.data.shape_keys is None:
            for side in ("left", "right"):
                vrm_rig.cinch(ch, ob, tops, side, SLEEVE[0], keep=SLEEVE[1], ease=0.15)


def drape_skirt(ch) -> None:
    """Seated: the robe's skirt laid over her thighs and down past her knees: VRoid hangs it from bones of its own
    (J_Sec_*_CoatSkirt*), which stay where a standing skirt hangs, so it is handed to her legs (vrm_rig.shift_weights),
    her thighs above the knee and her shins below (taken in round them), the cloth between her knees spanning them."""
    knee = ch.rest("leftLowerLeg")[2]
    skirt = {}
    for chain in vrm_rig.chains(ch, "J_Sec_*_CoatSkirt*"):
        for bone in chain:
            skirt[bone] = "leftUpperLeg" if "_L_" in bone else "rightUpperLeg"
    for ob in ch.meshes:
        tops = vrm_rig.faces_of(ob, "Tops")
        if tops.size:
            vrm_rig.shift_weights(ch, ob, tops, 10.0, 0.01, skirt)
            vrm_rig.shift_weights(ch, ob, tops, knee - 0.02, 0.08,
                                  {"leftUpperLeg": "leftLowerLeg", "rightUpperLeg": "rightLowerLeg"})
            for limb, (radius, keep, ease) in LAP.items():
                for side in ("left", "right", "both"):
                    vrm_rig.cinch(ch, ob, tops, side, radius, keep=keep, ease=ease,
                                  limb=limb)


def hair(ch, m: dict, coll, name: str) -> list:
    """Her hair white, VRoid's ponytail hidden (its strands shrunk into their roots at the back of her head) and a low
    bun there with a wooden pin through it. At rest; returns [bun, pin], carried by her head."""
    from lib import shapes

    for mat in ch.materials("hair"):
        vrm_rig.recolor(mat, *HAIR_WHITE, keep=0.45)
    head = ch.rest("head")
    for chain in vrm_rig.chains(ch):
        root, tip = vrm_rig.rest_point(ch, chain[0]), vrm_rig.rest_point(ch, chain[-1], tail=True)
        if root[1] > head[1] + 0.02 and tip[2] < head[2] + 0.02:
            vrm_rig.thin(ch, chain, 0.05, 0.05)
    at = head + np.asarray(BUN["at"])
    bun = shapes.ellipsoid(f"{name}-bun", tuple(ch.world(at)), BUN["radii"], material=m["hair"], coll=coll, n=16,
                           rot=_rot(ch))
    length, r, tilt = BUN["pin"]
    a = math.radians(tilt)
    d = np.array((math.cos(a), 0.0, math.sin(a)))
    pin = shapes.cylinder(f"{name}-pin", tuple(ch.world(at - d * length / 2 + (0, 0.02, 0))),
                          tuple(ch.world(at + d * length / 2 + (0, 0.02, 0))), r, material=m["wood"], coll=coll, n=8)
    for ob in (bun, pin):
        vrm.attach(ob, ch, "head")
    return [bun, pin]


def _rot(ch) -> np.ndarray:
    """Her frame's axes in the world (columns)."""
    o = np.array(ch.world((0.0, 0.0, 0.0)))
    return np.column_stack([np.array(ch.world(e)) - o for e in np.eye(3)])


def _w(ch, d) -> tuple:
    """A direction of her frame in the world."""
    return tuple(_rot(ch) @ np.asarray(d, float))


def _mouth(ch, lm) -> np.ndarray:
    """The left corner of her lips as posed, in her frame (lm: the face's landmarks, mesh space)."""
    face = _face_mesh(ch)
    mm = np.array(ch.armature.matrix_world.inverted() @ face.matrix_world)
    arm = mm[:3, :3] @ np.asarray(lm["mouth_left"], float) + mm[:3, 3]
    return posed(ch, "head", ch.frame.T @ arm * ch.scale)


def tsuru(coll, look, name: str = "tsuru", *, pipe: str | None = None, pole: str = "hand", seated: bool = False,
          wet: float = 1.0) -> dict:
    if pipe not in ("hand", "mouth", None) or pole not in ("hand", "boat", "shoulder", "drawn"):
        raise ValueError(f"tsuru: pipe={pipe!r} (hand, mouth, None), pole={pole!r} (hand, boat, shoulder, drawn)")
    if pole == "drawn":
        pipe = None
    m = anime.palette(colors(wet, TS_COLORS), look, prefix=name)
    ch = vrm.load(vrm_file(name), coll, name=name)
    vrm.scale_to(ch, HEIGHT["tsuru"])
    is_tsuru = vrm_file(name).stem == name     # the stand-in is not aged
    parts = {k: [] for k in ("pole", "handle", "blade", "pipe", "bun", "mino", "sandals")}
    sole, lm = 0.0, None
    if is_tsuru:
        robe(ch)
        indigo(ch)
        parts["bun"] = hair(ch, m, coll, name)
        lm = age(ch)
        sole = tabi(ch)
    soak(ch, wet, cloth=(0.66, 0.7, 0.78), hair=(0.8, 0.82, 0.88))   # white hair stays light when wet

    # her body, then her hands on what they hold (a pipe at her lips needs her head where the pose puts it)
    base = SEATED_POSE if seated else TS_POSE
    hips = (0.0, 0.0, SEAT + 0.07 - ch.rest("leftUpperLeg")[2]) if seated else TS_HIPS
    vrm.pose(ch, base, hips=hips)
    fingers = {}
    px, py = POLE
    up = np.array((0.0, 0.0, 1.0))
    if pole == "hand":
        fingers.update(vrm.grasp(ch, "right", (px, py, GRIP_Z[seated]), up, POLE_PALM, pole=(-0.5, 0.4, 0.6),
                                 bend=ELBOWS["right"], radius=POLE_R))
    elif pole == "shoulder":
        over = posed(ch, "rightShoulder", ch.rest("rightUpperArm") + np.asarray(SHOULDER["over"]))
        way = np.asarray(SHOULDER["way"]) / np.linalg.norm(SHOULDER["way"])
        fingers.update(vrm.grasp(ch, "right", over + way * SHOULDER["hand"], way, (0.3, 0.0, -1.0),
                                 pole=(-0.45, -0.1, 0.75), bend=ELBOWS["right"], radius=POLE_R))
    elif pole == "drawn":
        fingers.update(vrm.grasp(ch, "right", DRAWN["grip"], DRAWN["way"], (1.0, 0.0, 0.2), pole=(-0.5, 0.2, 0.7),
                                 bend=ELBOWS["right"], radius=HANDLE_R))
        fingers.update(vrm.grasp(ch, "left", DRAWN["shaft"], up, (-1.0, 0.0, 0.0), pole=(0.5, 0.4, 0.7),
                                 bend=ELBOWS["left"], radius=POLE_R))
    else:
        vrm.reach(ch, "rightHand", (-LEFT_HAND[0][0], *LEFT_HAND[0][1:]) if not seated else (-0.13, -0.24, SEAT + 0.14),
                  pole=(-0.5, 0.6, 0.9), bend=ELBOWS["left"])
        vrm.hold(ch, "rightHand", vrm.HANG_TURN["right"] if not seated else LAP_TURN["right"])
    mouth = None
    # seated, her hands in her lap come down with her hips
    pipe_hole = np.asarray(PIPE_HAND["hole"]) + np.array((0.0, -0.08, SEATED_HANDS)) * float(seated)
    if pipe == "hand":
        fingers.update(vrm.grasp(ch, "left", pipe_hole, PIPE_HAND["way"], (-0.5, 0.0, 0.8),
                                 pole=(0.5, 0.4, 0.7), bend=ELBOWS["left"], kind="pinch"))
    elif pipe == "mouth":
        mouth = _mouth(ch, lm) if lm is not None else np.array((0.02, -0.12, 1.28))
        pway = np.asarray(PIPE_MOUTH["way"]) / np.linalg.norm(PIPE_MOUTH["way"])
        fingers.update(vrm.grasp(ch, "left", mouth + pway * PIPE_MOUTH["hold"], pway, (-0.6, 0.0, 0.6),
                                 pole=PIPE_MOUTH["elbow"], bend=60.0, kind="pinch"))
    elif pole != "drawn":
        vrm.reach(ch, "leftHand", LEFT_HAND[0] if not seated else (0.13, -0.24, SEAT + 0.14), pole=LEFT_HAND[1],
                  bend=ELBOWS["left"])
        vrm.hold(ch, "leftHand", vrm.HANG_TURN["left"] if not seated else LAP_TURN["left"])
    vrm.pose(ch, {**base, **fingers}, hips=hips)
    if seated:
        drape_skirt(ch)
    lift = SOLE - sole if is_tsuru else 0.0      # bare soles down onto the sandals
    feet = SEATED_FEET if seated else FEET
    plant(ch, {side: ((x, y, ch.rest(f"{side}Foot")[2] + lift), pl, turn) for side, ((x, y), pl, turn) in feet.items()})
    if is_tsuru:
        parts["sandals"] = sandals(ch, m, coll, name)

    # the straw cape (props.straw_cape: built facing +x), heavy and soaked: a collar and three tiers of straw in wet
    # clumps tied on round the base of her neck, lying on her shoulders and falling straight from the round of her
    # back (the drape of her posed body, her forearms and hands left out), open in front, longer behind; carried by her
    # upper chest
    nk = ch.point("neck")
    top = nk.z - 0.01
    hem = ch.point("leftLowerLeg").z + 0.03 if not seated else SEAT + 0.02
    zs = np.linspace(hem, top, 48)
    drape = skin.Drape(zs, skin.girth(ch, (nk.x, nk.y), zs, n=72, limit=0.32, slab=0.008,
                                      skip=("leftLowerArm", "rightLowerArm", "leftHand", "rightHand",
                                            "leftUpperLeg", "rightUpperLeg") if seated else
                                      ("leftLowerArm", "rightLowerArm")))
    cape = props.straw_cape(f"{name}-mino", m["straw"], coll, center=(nk.x, nk.y), radii=(0.05, 0.06), top_z=top,
                            hem_z=hem, front_gap=36.0, flare=0.05, droop=0.02, segs=8, taper=0.7, front_hem=0.3,
                            clump=3 if wet > 0.5 else 1, shag=0.008 + 0.006 * (1.0 - wet), ragged=(0.72, 1.15),
                            hug=drape, gap=0.01, layer=0.006,
                            tiers=[(-0.02, 0.26, 230, (0.008, 0.016), 0.2), (0.1, 0.36, 280, (0.009, 0.018), 0.1),
                                   (0.32, 0.4, 320, (0.009, 0.018), 0.06), (0.56, 0.5, 360, (0.009, 0.018), 0.04)],
                            tip_material=m["straw_tip"], alt_material=m["straw_dark"], ink=False)
    vrm.attach(cape, ch, "upperChest" if ch.has("upperChest") else "chest")
    parts["mino"] = [cape]

    # the pole, built upright at the origin and parted at the cord, then each part put where she has it
    built = props.ferry_pole(f"{name}-pole", {"bamboo": m["bamboo"], "cord": m["cord"], "steel": m["steel"]}, coll,
                             (0.0, 0.0, 0.0), POLE_TOP, grip=(SPLIT, SPLIT + CORD), turns=8, split=SPLIT, blade=BLADE)
    shaft, handle = built[:2]
    parts["pole"] = [shaft] + [ob for ob in built[2:] if ob.parent is shaft]
    parts["handle"] = [handle] + [ob for ob in built[2:] if ob.parent is handle and not ob.name.endswith("-blade")]
    parts["blade"] = [ob for ob in built if ob.name.endswith("-blade")]
    o, z = (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)
    if pole == "drawn":
        way = np.asarray(DRAWN["way"]) / np.linalg.norm(DRAWN["way"])
        move(handle, (0.0, 0.0, SPLIT + 0.06), z, ch.world(DRAWN["grip"]), _w(ch, -way))
        move(shaft, (0.0, 0.0, SPLIT - 0.12), z, ch.world(DRAWN["shaft"]), _w(ch, z))
        vrm.attach(handle, ch, "rightHand")
        vrm.attach(shaft, ch, "leftHand")
    else:
        if pole == "hand":
            at, d = (px, py, 0.0), z
        elif pole == "shoulder":
            at, d = over - way * SHOULDER["behind"], way
        else:
            at, d = LAID["foot"], LAID["way"]
        for ob in (shaft, handle):
            move(ob, o, z, ch.world(at), _w(ch, d))
        anime.attach([handle], shaft)
        if pole == "boat":
            anime.attach([shaft], ch.root)
        else:
            vrm.attach(shaft, ch, "rightHand")
    if pipe is not None:
        if pipe == "hand":
            pway = np.asarray(PIPE_HAND["way"]) / np.linalg.norm(PIPE_HAND["way"])
            start = pipe_hole - pway * 0.09
        else:
            start = mouth + pway * 0.004
        parts["pipe"] = props.kiseru(f"{name}-kiseru", {"brass": m["brass"], "stem": m["stem"]}, coll,
                                     tuple(ch.world(start)), _w(ch, pway), length=KISERU, up=_w(ch, z))
        vrm.attach(parts["pipe"][0], ch, "leftHand")

    # her own expressions (FACES: lib/vrm_rig.py composes them of the face's shape keys); the stand-in keeps the presets
    composed = is_tsuru
    if composed:
        for ex, keys in FACES.items():
            vrm_rig.compose(ch, ex, keys)

    def face(eyes: float = 0.55) -> dict:
        """Calm and half-lidded at the cels' 0.55; the glare as `eyes` opens to 1."""
        k = min(1.0, max(0.0, (eyes - 0.55) / 0.45))
        if composed:
            return {"tsuru-calm": 1.0 - k, "tsuru-glare": k}
        return {"angry": 0.2 + 0.5 * k, "blink": 0.45 * (1.0 - k)}

    vrm.express(ch, face())
    flat_props = [ob for k in parts for ob in parts[k]]
    return {"root": ch.root, "vrm": ch, "head": tuple(ch.face()), "face": face, "props": flat_props, "parts": parts}
