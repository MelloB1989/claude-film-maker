"""Tsuru from her VRoid Studio model (films/rain-ferry/assets/vroid/tsuru.vrm) for the standoff: an old woman stooped
and very still, soaked, aged where VRoid paints young (blender/lib/vrm_skin.py: her face's lines, folds and spots, a
soft grey hairline, grey brows, heavy lids), the sneakers VRoid gave her swapped for dark tabi and straw sandals, and
what VRoid does not make (blender/lib/props.py): her ferry pole and her straw rain cape. rf/vroid_cast.py describes
what the builder returns."""
from __future__ import annotations

import math

import numpy as np

from lib import anime, props, shapes, vrm, vrm_rig, vrm_skin as skin

from .vroid_common import COLORS, HEIGHT, plant, vrm_file

MM = 1e-3

# ---- Tsuru, stooped: the upper back rounded over (the chest and upper chest bent on), the head pushed forward on the
# neck and lifted to look ahead, the shoulders rolled in, the hips back and down on soft knees; the pole upright in
# her right hand before her right shoulder, the left arm hanging (lib/vrm.py's turns)
TS_HIPS = (0.0, 0.05, -0.045)
TS_POSE = {"spine": (6.0, 0.0, 0.0), "chest": (13.0, 0.0, 0.0), "upperChest": (15.0, 0.0, 0.0),
           "neck": (12.0, 0.0, 0.0), "head": (-54.0, 0.0, 4.0),
           "leftShoulder": (0.0, 6.0, -10.0), "rightShoulder": (0.0, -6.0, 10.0),
           **{f"left{f}{j}": (0.0, 28.0, 0.0) for f in ("Index", "Middle", "Ring", "Little") for j in ("Proximal", "Intermediate")}}
LEFT_HAND = ((0.2, -0.1, 0.66), (0.5, 0.6, 0.9))   # where the hanging left hand's wrist is, and its elbow's pole
ELBOWS = {"left": 25.0, "right": 70.0}   # how far each elbow starts folded for its IK (vrm.reach): the right well in
POLE = (-0.24, -0.2)          # its foot, in her frame
POLE_TOP = 2.1
GRIP_Z = 0.98                 # where her right hand holds it
SOLE = 0.016                  # the sandals' thickness

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
# and half-lidded, and the glare, narrowed under low brows, the mouth a tight thin line
FACES = {
    "tsuru-calm": {"tsuru-hood": 0.75, "tsuru-brow-low": 0.6, "Fcl_EYE_Close": 0.05, "Fcl_BRW_Angry": 0.1,
                   "Fcl_MTH_Close": 1.0, "tsuru-press": 0.5},
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


def sandals(ch, m: dict, coll, name: str) -> list:
    """A zori under each posed foot (on the deck, along the foot): a straw sole and its dark thong from between the
    first toes over the forefoot to either side; carried by the foot."""
    obs = []
    s = ch.scale
    for side in ("left", "right"):
        a = np.array(ch.point(f"{side}Foot"))
        t = np.array(ch.point(f"{side}Toes"))
        f = t - a
        f[2] = 0.0
        f /= np.linalg.norm(f)
        inward = np.cross((0.0, 0.0, 1.0), f) * (-1.0 if side == "left" else 1.0)   # toward her other foot
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
            path = [post, along(0.74, 0.012 + sgn * 0.012, SOLE / 2 + 0.03 * s), along(0.62, sgn * 0.026, SOLE / 2 + 0.03 * s),
                    along(0.55, sgn * 0.034, SOLE / 2)]
            obs.append(shapes.loft(f"{name}-hanao-{side}{k}", path, 0.004 * s, material=m["cord"], coll=coll, n=6,
                                   subsurf=0))
    for ob in obs:
        vrm.attach(ob, ch, ("left" if "-left" in ob.name else "right") + "Foot")
        ob["outline"] = False
    return obs


def tsuru(coll, look, name: str = "tsuru") -> dict:
    m = anime.palette(COLORS, look, prefix=name)
    ch = vrm.load(vrm_file(name), coll, name=name)
    vrm.scale_to(ch, HEIGHT["tsuru"])
    is_tsuru = vrm_file(name).stem == name     # the stand-in is not aged
    sole = 0.0
    if is_tsuru:
        age(ch)
        robe(ch)
        sole = tabi(ch)
    vrm.wet(ch, cloth=(0.66, 0.7, 0.78), hair=(0.8, 0.82, 0.88))   # grey hair stays light when wet

    px, py = POLE
    fingers = vrm.grasp(ch, "right", (px, py, GRIP_Z), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), pole=(-0.5, 0.4, 0.6),
                        amount=0.95, bend=ELBOWS["right"])
    vrm.pose(ch, {**TS_POSE, **fingers}, hips=TS_HIPS)
    vrm.reach(ch, "leftHand", LEFT_HAND[0], pole=LEFT_HAND[1], bend=ELBOWS["left"])
    lift = SOLE - sole if is_tsuru else 0.0      # bare soles down onto the sandals
    plant(ch, {"left": ((0.09, 0.03, ch.rest("leftFoot")[2] + lift), (0.1, -1.0, 0.45), (0.0, 0.0, 8.0)),
               "right": ((-0.09, -0.01, ch.rest("rightFoot")[2] + lift), (-0.1, -1.0, 0.45), (0.0, 0.0, -8.0))})
    extra = sandals(ch, m, coll, name) if is_tsuru else []

    # the straw cape (props.straw_cape: built facing +x), heavy and soaked: a collar and three tiers of straw in wet
    # clumps tied on round the base of her neck, lying on her shoulders and falling straight from the round of her back (the drape
    # of her posed body, her forearms and hands left out), open in front, longer behind; carried by her upper chest
    nk = ch.point("neck")
    top = nk.z - 0.01
    hem = ch.point("leftLowerLeg").z + 0.03
    zs = np.linspace(hem, top, 48)
    drape = skin.Drape(zs, skin.girth(ch, (nk.x, nk.y), zs, n=72, limit=0.32, slab=0.008,
                                      skip=("leftLowerArm", "rightLowerArm")))
    cape = props.straw_cape(f"{name}-mino", m["straw"], coll, center=(nk.x, nk.y), radii=(0.05, 0.06), top_z=top,
                            hem_z=hem, front_gap=36.0, flare=0.05, droop=0.02, segs=8, taper=0.7, front_hem=0.3,
                            clump=3, shag=0.008, ragged=(0.72, 1.15), hug=drape, gap=0.01, layer=0.006,
                            tiers=[(-0.02, 0.26, 230, (0.008, 0.016), 0.2), (0.1, 0.36, 280, (0.009, 0.018), 0.1),
                                   (0.32, 0.4, 320, (0.009, 0.018), 0.06), (0.56, 0.5, 360, (0.009, 0.018), 0.04)],
                            tip_material=m["straw_tip"], alt_material=m["straw_dark"], ink=False)
    vrm.attach(cape, ch, "upperChest" if ch.has("upperChest") else "chest")
    foot = ch.world((px, py, 0.0))
    pole = props.ferry_pole(f"{name}-pole", {"bamboo": m["bamboo"], "cord": m["cord"]}, coll, (foot.x, foot.y, 0.0),
                            POLE_TOP)
    for ob in pole:
        anime.attach([ob], ch.root)

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
    return {"root": ch.root, "vrm": ch, "head": tuple(ch.face()), "face": face, "props": [cape, *pole, *extra]}
