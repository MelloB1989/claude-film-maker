"""Tsuru, the ferrywoman (STORY.md): about seventy-two, small, lean and wiry, once the swordswoman the river valley
called the River Demon. A realistic body (blender/lib/human.py) dressed and posed for the standoff in the film's toon
look: an indigo work kimono with narrow sleeves to the ankles under a shaggy straw rain cape open at the front, white hair combed
back tight into a low bun with a wooden pin, her tall bamboo pole upright in her right hand, straw sandals; a calm,
half-lidded face.

Built facing +x with her feet at the origin (the film's convention, rf/cast.py): a root empty, her rig turned under it.
"""
from __future__ import annotations

import math

import numpy as np

from lib import animeface, animehair, garments, hair, human, props, shapes, toon

# toon colours, linear RGB: (lit, shade)
COLORS = {
    "skin": ((0.55, 0.4, 0.3), (0.25, 0.165, 0.125)),
    "lips": ((0.45, 0.29, 0.23), (0.2, 0.12, 0.1)),
    "nails": ((0.62, 0.5, 0.42), (0.3, 0.22, 0.18)),
    "kimono": ((0.05, 0.065, 0.12), (0.012, 0.016, 0.034)),
    "collar": ((0.3, 0.31, 0.33), (0.1, 0.105, 0.12)),
    "obi": ((0.2, 0.19, 0.17), (0.05, 0.048, 0.045)),
    "straw": ((0.3, 0.235, 0.125), (0.06, 0.045, 0.025)),
    "straw_tip": ((0.46, 0.38, 0.22), (0.11, 0.085, 0.05)),
    "straw_dark": ((0.21, 0.16, 0.085), (0.045, 0.034, 0.02)),
    "rope": ((0.16, 0.12, 0.07), (0.04, 0.03, 0.018)),
    "hair": ((0.86, 0.86, 0.88), (0.38, 0.39, 0.44)),
    "hair_line": ((0.52, 0.52, 0.56), (0.24, 0.24, 0.28)),
    "brow": ((0.6, 0.59, 0.6), (0.3, 0.29, 0.31)),
    "lines": ((0.2, 0.12, 0.09), (0.12, 0.07, 0.05)),
    "lash": ((0.03, 0.025, 0.025), (0.015, 0.012, 0.012)),
    "bamboo": ((0.48, 0.4, 0.22), (0.16, 0.12, 0.07)),
    "wood": ((0.28, 0.18, 0.1), (0.08, 0.05, 0.03)),
}
HAIR_SHINE = (1.0, 1.0, 1.0)    # the band of light round her white hair
POLE = (-0.215, -0.15)      # the pole's foot, in her own frame (her right, a little ahead), and its height
POLE_TOP = 2.1
# her face, drawn (lib/animeface.py, eye units round the eyes' midpoint, x toward her left): calm, half-lidded eyes
# with grey-brown irises, soft white brows, a faint smile, and her age in a few clean lines
LINE = (0.16, 0.09, 0.06)
DRAWING = animeface.Face(
    eye=animeface.Eye(width=0.64, height=0.165, tilt=-3.0, peak=0.42, round=0.9, lower=0.6, droop=0.5,
                      iris=(0.15, 0.19), iris_at=(0.0, -0.02), iris_top=(0.035, 0.03, 0.025), iris_bottom=(0.25, 0.19, 0.14),
                      rim=(0.02, 0.016, 0.013), pupil=0.4, highlights=((-0.3, 0.25, 0.23), (0.4, -0.45, 0.1)),
                      white=(0.87, 0.86, 0.84), lash=0.06, lash_inner=0.45, flick=(0.05, -10.0, 0.6),
                      lower_lash=(0.4, 0.95, 0.014), crease=0.7, crease_width=0.01, lash_color=(0.05, 0.035, 0.03)),
    strokes=[
        # the brows: soft white, edged in grey so they show against her skin
        animeface.Stroke(((0.15, 0.4), (0.45, 0.49), (0.75, 0.45), (0.9, 0.37)), width=(0.055, 0.065, 0.058, 0.04),
                         color=(0.3, 0.29, 0.3), taper=(0.6, 0.35), mirror=True),
        animeface.Stroke(((0.15, 0.4), (0.45, 0.49), (0.75, 0.45), (0.9, 0.37)), width=(0.035, 0.045, 0.04, 0.022),
                         color=(0.82, 0.82, 0.84), taper=(0.55, 0.25), mirror=True),
        animeface.Stroke(((0.87, 0.04), (0.99, 0.09)), width=0.012, color=LINE, mirror=True, far=0.0),       # crow's feet
        animeface.Stroke(((0.87, -0.07), (0.98, -0.13)), width=0.012, color=LINE, mirror=True, far=0.0),
        animeface.Stroke(((0.32, -0.29), (0.5, -0.34), (0.7, -0.29)), width=0.011, color=LINE, mirror=True, far=0.0),  # bags
        animeface.Stroke(((0.21, -0.7), (0.3, -0.93), (0.35, -1.18)), width=0.016, color=LINE, mirror=True, far=1.3),  # smile lines
        animeface.Stroke(((-0.4, 0.88), (0.0, 0.93), (0.4, 0.88)), width=0.011, color=LINE, far=0.0),            # the forehead
        animeface.Stroke(((0.06, -0.5), (0.09, -0.67), (0.02, -0.72)), width=0.02, color=LINE, taper=(0.25, 0.45),
                         far=0.8),                                                                         # the nose
        animeface.Stroke(((-0.26, -1.21), (-0.1, -1.255), (0.1, -1.255), (0.26, -1.21)), width=0.025,
                         color=(0.1, 0.05, 0.04), taper=(0.35, 0.35)),                                     # a faint smile
    ])


# how far each colour whitens in a lightning flash where it should not take the look's full amount: the straw keeps
# its texture instead of going to a white robe
FLASH = {"straw": 0.35, "straw_tip": 0.35, "straw_dark": 0.35}


def materials(look, name: str) -> dict:
    return {k: toon.cel(f"{name}-{k}", lit, shade, look=look, flash=FLASH.get(k)) for k, (lit, shade) in COLORS.items()}


def _hold_round(person, side: str, pole_xy, wrist_xy):
    """Turn a hand so its fist closes round an upright pole: the hand pointing from the wrist to the pole, level, its
    knuckles in a vertical line (index on top). In the person's frame."""
    from mathutils import Matrix, Vector

    rest = person.rig.data.bones[f"wrist.{side}"].matrix_local.to_3x3()
    knuckles = person.rest(f"finger5-1.{side}") - person.rest(f"finger2-1.{side}")
    local = rest.transposed() @ knuckles
    axis = 0 if abs(local.x) > abs(local.z) else 2
    sign = 1.0 if (local.x if axis == 0 else local.z) > 0 else -1.0
    y = Vector((pole_xy[0] - wrist_xy[0], pole_xy[1] - wrist_xy[1], 0.0)).normalized()
    k = Vector((0.0, 0.0, -1.0)) * sign
    if axis == 0:
        x, z = k, k.cross(y)
    else:
        z = k
        x = y.cross(z)
    target = Matrix((x, y, z)).transposed()
    turn = (target @ rest.inverted()).to_euler("XYZ")
    person.hold(f"wrist.{side}", tuple(math.degrees(a) for a in turn))


def _close_on(person, side: str, pole_xy, rounds: int = 3):
    """Slide the hand's IK target until the hole of the closed fist (between the knuckles and the curled finger ends)
    is on the pole's axis, so the fingers wrap it instead of stopping short. In the person's frame."""
    import bpy
    from mathutils import Vector

    target = person.handles[f"hand.{side}-target"]
    inv = person.rig.matrix_world.inverted()
    for _ in range(rounds):
        bpy.context.view_layer.update()
        pts = [inv @ person.point(f"finger{f}-{j}.{side}") for f in range(2, 6) for j in (1, 3)]
        hole = sum(pts, Vector((0.0, 0.0, 0.0))) / len(pts)
        target.location += Vector((pole_xy[0] - hole.x, pole_xy[1] - hole.y, 0.0))


def tsuru(coll, look, name: str = "tsuru") -> dict:
    """Tsuru standing very still in her straw cape, the bamboo pole planted in her right hand (built facing +x)."""
    import bpy
    from mathutils import Vector

    m = materials(look, name)
    root = bpy.data.objects.new(name, None)
    coll.objects.link(root)
    p = human.make(name, sex=0.0, age=72, muscle=0.45, weight=0.32, height=0.42, proportions=0.55, ancestry=(0.92, 0.04, 0.04),
                   targets=animeface.head(), coll=coll)
    p.rig.parent = root
    p.rig.rotation_euler = (0.0, 0.0, math.pi / 2)    # MakeHuman faces -y; the film's cast faces +x

    # ---- the face ----
    # (the scalp under her hair white, so no gap in it shows skin)
    p.paint(m["skin"], {"fingernails": m["nails"], "toenails": m["nails"], "scalp": m["hair"]})
    # smoothed (her age's folds eased: the drawing draws them, and deep ones let the outline hull peek through),
    # shaded from a proxy, drawn; the eyeballs kept as landmarks
    eyes = animeface.apply(p, DRAWING, look=look, smooth_args={"rest": 0.85})

    # ---- landmarks, at rest in her own frame (facing -y, left +x) ----
    waist = p.rest("spine04").z
    chest = p.rest("spine01").z
    neck = p.rest("neck01").z
    eye_c = np.mean([np.mean([v.co[:] for v in e.data.vertices], axis=0) for e in eyes], axis=0)
    ez = float(eye_c[2])

    # ---- the indigo kimono: a top with narrow sleeves to the wrists, a skirt to mid-shin, the obi, the collar ----
    def top_keep(co, w):
        if co[2] < waist - 0.07:
            return False
        if sum(v for k, v in w.items() if k.startswith(("wrist", "finger", "metacarpal"))) > 0.3:
            return False
        return garments.v_neck(chest - 0.035, neck + 0.02, half_width=0.06)(co, w)

    def sleeves(co, w):
        return 0.012 * sum(v for k, v in w.items() if k.startswith(("upperarm", "lowerarm")))

    top = garments.cut(p, f"{name}-kimono", "tights", keep=top_keep, push=0.01, swell=sleeves, material=m["kimono"])
    skirt = garments.cut(p, f"{name}-kimono-skirt", "skirt", keep=garments.above(0.1), push=0.013,
                         swell=garments.flare(waist, 0.1, amount=0.035), material=m["kimono"])
    # the obi round the skirt's top (a slice of the top would catch the arms, hanging by the waist at rest)
    sk_top = max(v.co.z for v in skirt.data.vertices)
    garments.belt(p, f"{name}-obi", skirt, sk_top - 0.03, 0.08, push=0.003, thickness=0.004, material=m["obi"], bone="spine04",
                  knot=(math.pi, 0.035))
    garments.lapels(p, f"{name}-collar", top, neck_z=neck, cross_z=chest - 0.035, waist_z=waist - 0.04, half_width=0.06,
                    material=m["collar"])

    # ---- white hair combed back in clean sections into a low bun with a wooden pin (animehair), two loose wisps ----
    # an underlayer cut from the scalp shell (no lines of its own) so nothing shows between the sections
    # grey partings drawn along each section's edges, as white hair is inked
    hm = animehair.material(f"{name}-hairtoon", *COLORS["hair"], look=look, highlight=HAIR_SHINE, ring=(0.5, 0.66), teeth=9,
                            lines=(COLORS["hair_line"][0], 0.16))
    hem = hair.hem_profile(ez + 0.05, ez + 0.018, ez - 0.062)
    mass = animehair.cap(p, f"{name}-hair", hem=hem, push=0.002, material=hm)
    mass.lineart.usage = "OCCLUSION_ONLY"
    mco = np.array([v.co[:] for v in mass.data.vertices])
    back_y = float(mco[:, 1].max())
    bun_at = (0.0, back_y + 0.006, ez - 0.045)
    animehair.grow(p, f"{name}-sections", _hair_style(p, hem, bun_at), whorl=animehair.direction(180, 30), material=hm)
    hair.coil(p, f"{name}-bun", bun_at, axis=(0.0, 1.0, -0.25), radius=0.036, thick=0.0135, turns=2.5, material=hm,
              pin=(0.16, 0.0038, 18.0), pin_material=m["wood"])

    # the shells the clothes and hair were cut from
    for k in ("hair", "tights", "skirt"):
        bpy.data.objects.remove(p.parts.pop(k), do_unlink=True)

    # ---- the pose: upright and very still, a little stooped; the pole in her right hand, the left arm loose ----
    p.turn("spine03", x=5)
    p.turn("spine02", x=4)
    p.turn("neck02", x=-4)
    p.turn("head", x=-4)
    ank_l, ank_r = p.rest("foot.L"), p.rest("foot.R")
    p.reach("foot.L", (0.085, ank_l.y, ank_l.z), pole=(0.1, -1.0, 0.45), level=True)
    p.reach("foot.R", (-0.085, ank_r.y, ank_r.z), pole=(-0.1, -1.0, 0.45), level=True)
    px, py = POLE
    p.reach("hand.R", (px + 0.04, py + 0.075, waist + 0.22), pole=(-0.22, 0.35, waist - 0.45))
    p.reach("hand.L", (0.175, -0.1, waist - 0.07), pole=(0.3, 0.6, waist + 0.15))
    _hold_round(p, "R", (px, py), (px + 0.04, py + 0.075))
    p.grip("R", 0.82, thumb=0.7)     # a fist just open enough for the pole
    _close_on(p, "R", (px, py))
    p.grip("L", 0.3, thumb=0.3)
    bpy.context.view_layer.update()

    # ---- built round the posed body (world: she faces +x): the straw cape, the pole, the sandals ----
    sh_l, sh_r = p.point("shoulder01.L"), p.point("shoulder01.R")
    nk = p.point("neck01")
    mid = (sh_l + sh_r) / 2
    half = (sh_l - sh_r).length / 2
    knee = p.point("lowerleg01.L").z
    # three tiers of fine straw like thatch, bleached at the ends, tied at the neck; the fibres draw no lines of their own
    cape = props.straw_cape(f"{name}-mino", m["straw"], coll, center=(mid.x - 0.025, mid.y), radii=(0.12, half + 0.05),
                            top_z=max(mid.z, nk.z - 0.04) + 0.01, hem_z=knee - 0.02, front_gap=30.0, flare=0.14, droop=0.1,
                            tiers=[(-0.12, 0.34, 90, (0.01, 0.014), 0.75, 0.55), (0.0, 0.42, 130, (0.01, 0.015)),
                                   (0.3, 0.45, 160, (0.01, 0.015)), (0.58, 0.45, 190, (0.01, 0.015))],
                            tip_material=m["straw_tip"], alt_material=m["straw_dark"], rope_material=m["rope"], ink=False)
    human.attach(cape, p, "spine01")

    wp = root.matrix_world @ (p.rig.matrix_basis @ Vector((px, py, 0.0)))
    parts = [cape]
    parts += props.ferry_pole(name, {"bamboo": m["bamboo"], "cord": m["wood"]}, coll, (wp.x, wp.y, 0.0), POLE_TOP)
    for side in ("L", "R"):
        a, t = p.point(f"foot.{side}"), p.point(f"foot.{side}", tail=True)
        d = Vector((t.x - a.x, t.y - a.y, 0.0))
        d.normalize()
        c = Vector((a.x, a.y, 0.0)) + d * 0.06
        sole = shapes.box(f"{name}-sandal.{side}", (c.x, c.y, 0.008), (0.22, 0.082, 0.016), material=m["straw"], coll=coll,
                          rot_z=math.atan2(d.y, d.x))
        parts.append(sole)
    for ob in parts[1:]:
        ob.parent = root

    head_c = p.point("head") + Vector((0.02, 0.0, 0.085))
    return {
        "root": root,
        "rig": p.rig,
        "person": p,
        "head": tuple(head_c),
        "cape": cape,
        "parts": [o for o in coll.all_objects],
        "breathe": lambda frames, fps: p.breathe(frames, fps, rate=0.2, depth=0.6, phase=0.5),
    }


def _hair_style(p, hem, bun_at, seed: int = 5) -> list:
    """Her hair as anime locks (lib/animehair.py): wide flat sections from her hairline (`hem`) combed tight over the
    skull into the bun at `bun_at`, a second layer over the crown, and two fine wisps escaped by her temples."""
    rng = np.random.default_rng(seed)
    head = animehair.Head(p)
    c, r = head.center, head.radius
    b = np.asarray(bun_at, float) - c
    b /= np.linalg.norm(b)
    # a few wide sections (too many and they melt into one smooth helmet), standing a little off the head so each reads
    angles = [math.radians(a) for a in (-156, -120, -86, -56, -28, 0, 28, 56, 86, 120, 156)]
    locks = []
    for root in hair.hairline(p, hem, angles, center=c):
        d = np.asarray(root, float) - c
        d /= np.linalg.norm(d)
        arc = animehair.arc(d, b, r)
        if arc < 0.03:
            continue
        az, el = math.degrees(math.atan2(d[0], -d[1])), math.degrees(math.asin(d[2]))
        locks.append(animehair.Lock(az=az, el=el, length=arc * 0.92, width=0.072 * rng.uniform(0.94, 1.06), depth=0.24, hug=1.0,
                                    lift=0.006, toward=tuple(bun_at), kind="lens", peak=0.4, point=1.3, root=0.85))
    # over the crown, a second layer of the same, from just behind the hairline
    for az in (-34, 0, 34):
        d = animehair.direction(az, 52)
        arc = animehair.arc(d, b, r)
        locks.append(animehair.Lock(az=az + rng.uniform(-4, 4), el=52, length=arc * 0.9, width=0.072, depth=0.24, hug=1.0, lift=0.01,
                                    toward=tuple(bun_at), kind="lens", peak=0.45, point=1.3, root=0.85))
    # two fine wisps loose by her temples, hanging close along her cheeks (looser, they stuck out sideways)
    for az, sw in ((-74, -0.1), (74, 0.1)):
        locks.append(animehair.Lock(az=az, el=24, length=0.075, width=0.011, depth=0.5, hug=0.6, lift=0.003, fall=1.6, flare=0.0,
                                    swoop=sw, curl=8, twist=20, kind="lens", peak=0.2, point=0.9, root=0.8))
    return locks
