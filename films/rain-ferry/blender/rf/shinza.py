"""Shinza, the young ronin of The Rain Ferry (STORY.md), as a realistic figure in the film's ink-anime look: a
MakeHuman body (blender/lib/human.py) dressed from its own fitted shells (garments.py), his hair cut from its scalp
(hair.py), posed in a low guard with his katana forward and down. Only his design lives here: his build and face, his
colours, his costume, his stance and his sword.

Built in the film's convention: a root empty at the origin facing +x at identity, feet on z 0 (the shot places and
turns the root). His own frame (the rig's) faces -y with his left at +x, as MakeHuman's does; the stance and the props
are written in it.
"""
from __future__ import annotations

import math

import numpy as np

from lib import anime, animeface, animehair, garments, hair, human, props, shapes, toon

# toon colours, linear RGB: (lit, shade)
COLORS = {
    "skin": ((0.42, 0.28, 0.19), (0.17, 0.1, 0.07)),
    "lips": ((0.34, 0.19, 0.14), (0.14, 0.07, 0.05)),
    "nails": ((0.5, 0.36, 0.28), (0.2, 0.13, 0.1)),
    "kimono": ((0.085, 0.09, 0.105), (0.018, 0.019, 0.025)),
    "hakama": ((0.05, 0.052, 0.062), (0.012, 0.012, 0.016)),
    "under": ((0.4, 0.41, 0.42), (0.14, 0.145, 0.16)),
    "obi": ((0.2, 0.19, 0.17), (0.05, 0.048, 0.045)),
    "cord": ((0.25, 0.22, 0.18), (0.06, 0.05, 0.04)),
    "hair": ((0.05, 0.05, 0.062), (0.009, 0.009, 0.012)),
    "tasuki": ((0.55, 0.5, 0.4), (0.2, 0.18, 0.14)),
    "band": ((0.66, 0.05, 0.03), (0.25, 0.018, 0.012)),
    "steel": ((0.85, 0.88, 0.92), (0.3, 0.32, 0.36)),
    "lacquer": ((0.04, 0.04, 0.045), (0.008, 0.008, 0.01)),
    "wrap": ((0.11, 0.1, 0.09), (0.025, 0.022, 0.02)),
    "brass": ((0.42, 0.32, 0.15), (0.12, 0.09, 0.04)),
    "straw": ((0.3, 0.235, 0.125), (0.06, 0.045, 0.025)),
    "ink": ((0.012, 0.012, 0.016), (0.012, 0.012, 0.016)),
}
# his face, drawn (lib/animeface.py, eye units round the eyes' midpoint): narrow, hard eyes the upper lid cuts into,
# dark-brown irises, brows driven down to the nose, a set mouth
DRAWING = animeface.Face(
    eye=animeface.Eye(width=0.74, height=0.245, tilt=7.0, peak=0.55, round=0.5, lower=0.42, slant=0.68,
                      iris=(0.17, 0.215), iris_at=(0.02, 0.05), iris_top=(0.02, 0.012, 0.008), iris_bottom=(0.27, 0.13, 0.05),
                      rim=(0.008, 0.006, 0.004), pupil=0.42, highlights=((-0.35, 0.38, 0.27), (0.42, -0.45, 0.12)),
                      white=(0.9, 0.9, 0.92), lash=0.095, lash_inner=0.4, flick=(0.1, -6.0, 0.9),
                      lower_lash=(0.3, 0.98, 0.022), crease=0.5, crease_width=0.011),
    strokes=[
        animeface.Stroke(((0.08, 0.2), (0.38, 0.31), (0.7, 0.39), (0.92, 0.37)), width=(0.09, 0.095, 0.075, 0.035),
                         taper=(0.75, 0.15), mirror=True, far=0.8),                                            # the brows
        animeface.Stroke(((0.07, -0.47), (0.1, -0.66), (0.02, -0.73)), width=0.022, taper=(0.25, 0.45), far=0.8),  # the nose
        animeface.Stroke(((-0.28, -1.27), (-0.1, -1.25), (0.1, -1.25), (0.28, -1.28)), width=0.03, taper=(0.35, 0.35)),  # mouth
        animeface.Stroke(((-0.07, -1.4), (0.07, -1.4)), width=0.014, color=(0.14, 0.08, 0.06), taper=(0.2, 0.2), far=0.0),  # lip
    ])
HAIR =((0.03, 0.032, 0.045), (0.006, 0.006, 0.009))   # black, lit and in shade, a little blue as anime draws it
HAIR_SHINE = (0.17, 0.19, 0.27)    # the cool band of light round it

# lean, tall, early twenties; brows down, eyes narrowed, the mouth set
BUILD = dict(sex=1.0, age=23.0, muscle=0.66, weight=0.4, height=0.62, proportions=0.8, ancestry=(0.9, 0.05, 0.05))
FACE = {"eyebrows-left-down": 0.5, "eyebrows-right-down": 0.5}   # the brow ridge low (the eyes and the mouth are drawn)

# the guard, in his own frame (front -y, left +x): hips dropped, right foot forward, the left back and turned out
DROP = 0.15
FEET = {"R": ((-0.13, -0.36, 0.075), (-0.3, -1.2, 0.55), 0.0), "L": ((0.17, 0.36, 0.075), (0.6, -0.6, 0.55), 38.0)}
# the sword: its pommel by his navel, the hilt and the blade forward and down toward her knees
POMMEL = np.array((0.012, -0.27, 0.925))
HILT_DIR = np.array((0.0, -0.91, -0.41))
HILT, BLADE, SORI = 0.27, 0.72, 0.017
ELBOWS = {"L": (0.5, 0.1, 0.55), "R": (-0.5, -0.1, 0.55)}


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def shinza(coll, look, name: str = "shinza") -> dict:
    before = set(coll.all_objects)
    m = anime.palette(COLORS, look, prefix=name, cuts={"steel": 0.55, "hair": 0.22, "tasuki": 0.3})
    p = human.make(name, face=FACE, targets=animeface.head(), coll=coll, **BUILD)
    root = anime.empty(name, coll)
    p.rig.parent = root
    p.rig.rotation_euler = (0.0, 0.0, math.pi / 2)

    # ---- the face: smoothed, shaded from a proxy and drawn (its eyeballs kept, hidden, as landmarks) ----
    p.paint(m["skin"], {"fingernails": m["nails"], "toenails": m["nails"]})
    animeface.apply(p, DRAWING, look=look, bias=0.45)   # lit, the shadow a small one beside the nose, not a strip down the face

    # ---- the costume, in the rest pose ----
    waist, neck, chest = p.rest("spine04").z, p.rest("neck01").z, p.rest("spine01").z
    cross = chest - 0.03
    vneck = garments.v_neck(cross, neck + 0.01, half_width=0.068, cross_x=-0.012)

    def top_keep(co, w):
        if co[2] < waist - 0.07:
            return False
        if sum(x for k, x in w.items() if k.startswith(("lowerarm", "wrist", "finger", "metacarpal"))) > 0.35:
            return False     # the sleeves tied back above the elbow: bare forearms
        return vneck(co, w)
    top_keep.edge = vneck.edge

    def sleeves(co, w):
        # bunched where the cord holds the sleeves back
        k = sum(x for k_, x in w.items() if k_.startswith("upperarm"))
        return 0.03 * k + 0.008 * k * math.sin(co[2] * 90.0)

    kimono = garments.cut(p, f"{name}-kimono", "tights", keep=top_keep, push=0.012, swell=sleeves, material=m["kimono"])
    garments.lapels(p, f"{name}-collar", kimono, neck_z=neck + 0.01, cross_z=cross, waist_z=waist - 0.02, half_width=0.068,
                    cross_x=-0.012, width=0.04, push=0.012, material=m["under"])
    hakama = garments.legs(p, f"{name}-hakama", waist_z=waist + 0.03, hem_z=0.1, waist=(0.105, 0.115), hips=(0.15, 0.16),
                           knee=(0.17, 0.19), hem=(0.21, 0.23), pleats=5, depth=0.02, ragged=(0.04, 7), material=m["hakama"], seed=3)
    garments.belt(p, f"{name}-obi", kimono, waist + 0.055, 0.05, push=0.004, thickness=0.006, material=m["obi"],
                  bone="spine04", smooth=True, subsurf=0)
    for k, dz in enumerate((0.012, -0.012)):
        garments.belt(p, f"{name}-himo{k}", hakama, waist + 0.02 + dz, 0.011, push=0.003, thickness=0.004, material=m["cord"],
                      bone="spine05", smooth=True, subsurf=0)
    _tasuki(p, f"{name}-tasuki", kimono, m["tasuki"])
    _sleeve_ties(p, f"{name}-ties", kimono, m["tasuki"])

    # ---- hair (animehair): big clean locks from a whorl at the back of his crown, a full top, short parted bangs over the
    # band clear of his brows, spiky locks to the jaw and a ragged back flaring at the nape, over a cap; placed from his
    # eyes ----
    eye_z = float(np.mean([np.mean([v.co.z for v in e.data.vertices]) for e in p.parts["eyes"]]))
    hm = animehair.material(f"{name}-hair", *HAIR, look=look, highlight=HAIR_SHINE, cut=0.3, flash=0.2)  # stays black in a flash
    cap = animehair.cap(p, f"{name}-haircap", hem=hair.hem_profile(eye_z + 0.09, eye_z - 0.01, eye_z - 0.11), push=0.012,
                        material=hm)
    locks, bangs = _hair_style()
    whorl = animehair.direction(180, 62)
    hair_ob = animehair.grow(p, f"{name}-hair", locks, whorl=whorl, material=hm)
    animehair.grow(p, f"{name}-bangs", bangs, whorl=whorl, material=hm, seed=11)
    # the band: a crisp cloth band tied tight round the head (over the cap, under the locks that fall over it) across the
    # middle of his forehead, clear above the brows, knotted at the back with two tails falling and streaming back
    band, tails = garments.belt(p, f"{name}-band", [p.body, cap], eye_z + 0.056, 0.026, push=0.003, thickness=0.0022,
                                tilt=math.radians(-3), material=m["band"], bone="head", smooth=True, subsurf=0,
                                knot=(math.pi, 0.016), tails=[(0.3, 0.032, 0.62), (0.26, 0.03, 0.85)], curl=0.9)

    p.discard("hair", "tights", "skirt")

    # ---- the guard ----
    p.lower(DROP, dy=0.02)
    for side, (at, pole, yaw) in FEET.items():
        p.reach(f"foot.{side}", at, pole=pole)
        p.hold(f"foot.{side}", (0.0, 0.0, yaw))
    pommel, hilt = POMMEL, HILT_DIR / np.linalg.norm(HILT_DIR)
    guard = pommel + hilt * HILT
    grips = {"L": pommel + hilt * 0.05, "R": guard - hilt * 0.06}
    for side, g in grips.items():
        p.reach(f"hand.{side}", tuple(g + np.array((0.0, 0.035, 0.045))), pole=ELBOWS[side])
        p.grip(side, 1.0)
    for bone, x in (("spine03", 10.0), ("spine02", 7.0), ("neck02", -9.0), ("head", -8.0)):
        p.turn(bone, x=x)

    # ---- the sword, the scabbard, the sandals: rigid, built round the pose ----
    gear = _katana(p, name, pommel, hilt, guard, m) + _scabbard(p, name, m) + _sandals(p, name, m)
    for ob in gear:
        ob.parent = p.rig

    import bpy
    bpy.context.view_layer.update()
    head = (p.point("head") + p.point("head", tail=True)) / 2

    def breathe(frames, fps):
        p.breathe(frames, fps, rate=0.42, depth=1.8, lean=lambda t: 1.6 * ease((t - 2.2) / 1.2))

    parts = [ob for ob in coll.all_objects if ob.type == "MESH" and ob not in before]
    return {"root": root, "rig": p.rig, "person": p, "head": tuple(head), "tails": tails, "parts": parts, "breathe": breathe}


def _tasuki(p, name, kimono, material, *, radius: float = 0.0072):
    """The cord that ties his sleeves back: a loop round each shoulder, crossing in an X between his shoulder blades,
    lying on the kimono."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    bvh = BVHTree.FromObject(kimono, bpy.context.evaluated_depsgraph_get(), deform=False)
    specs = []
    for side in ("L", "R"):
        sgn = 1 if side == "L" else -1
        sh = np.array(p.rest(f"upperarm01.{side}"))
        cl = np.array(p.rest(f"clavicle.{side}"))
        back = np.array((0.0, 0.0, 0.0))
        pts = [
            (-sgn * 0.08, 0.16, sh[2] - 0.2),             # from low on the far side of the back
            (0.0, 0.17, sh[2] - 0.1),                     # across the middle of the back
            (sgn * 0.09, 0.15, sh[2] + 0.0),              # up to the shoulder blade
            (sh[0] - sgn * 0.02, 0.06, sh[2] + 0.06),     # over the top of the shoulder
            (sh[0] + sgn * 0.01, -0.07, sh[2] + 0.0),     # down its front
            (sh[0] + sgn * 0.02, -0.02, sh[2] - 0.12),    # under the arm
            (sh[0] - sgn * 0.01, 0.1, sh[2] - 0.08),      # back round to the shoulder blade
        ]
        path = []
        for x, y, z in pts:
            h = bvh.find_nearest(Vector((x, y, z)))
            if h[0] is not None:
                path.append(np.array(h[0][:]) + np.array(h[1][:]) * (radius + 0.004))
        if len(path) >= 4:
            specs.append((np.array(path), radius, radius))
    ob = shapes.lofts(name, specs, material=material, coll=p.coll, n=6, subsurf=1)
    human.skin_like(ob, kimono, p.rig)
    p.parts[name] = ob
    return ob


def _sleeve_ties(p, name, kimono, material, *, at: float = 0.4, radius: float = 0.0068, n: int = 28):
    """Where the cord binds each tied-back sleeve: a loop round the upper arm, lying on the sleeve (the light stripe
    that reads at a distance)."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    bvh = BVHTree.FromObject(kimono, bpy.context.evaluated_depsgraph_get(), deform=False)
    specs = []
    for side in ("L", "R"):
        a = np.array(p.rest(f"upperarm01.{side}"))
        b = np.array(p.rest(f"lowerarm01.{side}"))
        c = a + (b - a) * at
        axis = (b - a) / np.linalg.norm(b - a)
        u = np.cross(axis, (0.0, 1.0, 0.0))
        u /= np.linalg.norm(u)
        v = np.cross(axis, u)
        ring = []
        for k in range(n + 1):
            th = 2 * math.pi * k / n
            d = u * math.cos(th) + v * math.sin(th)
            h = bvh.ray_cast(Vector(c), Vector(d), 0.3)
            if h[0] is None:
                continue
            ring.append(np.array(h[0][:]) + d * (radius + 0.003))
        if len(ring) > n // 2:
            specs.append((np.array(ring), radius, radius))
    ob = shapes.lofts(name, specs, material=material, coll=p.coll, n=6, subsurf=1)
    human.skin_like(ob, kimono, p.rig)
    p.parts[name] = ob
    return ob


def _hair_style(seed: int = 7) -> tuple[list, list]:
    """His hair as anime locks (lib/animehair.py), combed from a whorl at the back of the crown: a wild top standing off
    the skull (none from its front, which would fall over his face), locks swept back from the temples, spiky locks to
    the jaw by the ears, a ragged back whose points kick out at the nape; and, apart (the band goes over the rest but
    under them), short bangs parted a little right of centre and swept out toward the temples, ending on the band so his
    brows and eyes stay clear, and a lock either side hanging before the ears. Returns (locks, bangs)."""
    rng = np.random.default_rng(seed)
    L = animehair.Lock
    locks = []
    # the top: round the whorl to the sides and back, standing well off the skull, flaring out into points (none from
    # the front of the top: combed away from the whorl they would fall over his face)
    locks += animehair.fan(np.arange(103, 260, 38), 70, rng=rng, jitter=0.2, length=0.21, width=0.062, hug=0.48, lift=0.034,
                           fall=0.6, flare=0.7, curl=18, twist=14)
    # over the whorl itself: short locks lying on the crown round it, so the cap never shows there and the top is full
    locks += animehair.fan([110, 145, 180, 215, 250], [76, 80, 82, 80, 76], rng=rng, jitter=0.15, length=0.14, width=0.07, hug=0.85,
                           lift=0.03, fall=0.55, flare=0.6, curl=14, twist=10)
    # the temples: locks swept back from his face (heading round toward the whorl), wild over the ears
    locks += [L(az=s * 62, el=64, length=0.17, width=0.055, hug=0.62, lift=0.026, fall=0.8, flare=0.6, curl=16, twist=s * 12,
                heading=s * 150) for s in (-1, 1)]
    # the upper ring, back from the temples (the front left to the bangs, the temples to the locks before the ears)
    locks += animehair.fan([a for a in np.arange(0, 360, 30) + 15 if 85 < a < 275], 45, rng=rng, jitter=0.22, length=0.2,
                           width=0.056, hug=0.42, lift=0.02, fall=0.95, flare=0.55, curl=16, twist=-16)
    # the lower sides and back: shorter, spiky, kicking out at the nape
    locks += animehair.fan(np.linspace(75, 285, 11), [24, 20, 16, 12, 10, 8, 10, 12, 16, 20, 24], rng=rng, jitter=0.25,
                           length=0.165, width=0.048, hug=0.32, lift=0.013, fall=1.05, flare=0.65, curl=24, twist=18)
    # by the ears, down to the jaw, their points in a little
    locks += [L(az=a, el=27, length=0.17, width=0.043, hug=0.38, lift=0.011, fall=1.25, flare=0.14, curl=-6) for a in (-80, 80)]
    # the bangs: parted a little right of centre, each side swept out toward its temple (heading: + toward his left) over
    # the band, so his brows and eyes stay clear; over their roots the front of the top combed forward; and two longer
    # locks framing his face by the temples, down to the cheekbones
    bangs = [L(az=a + rng.uniform(-3, 3), el=72, length=0.07 * rng.uniform(0.92, 1.08), width=0.058, depth=0.3, hug=1.0, lift=0.03,
               heading=h, peak=0.3, point=0.85, root=0.75) for a, h in ((-34, -20), (-12, -16), (10, 16), (32, 20))]
    for a, length, width, heading in ((-30, 0.046, 0.044, -30), (-16, 0.05, 0.042, -24), (-3, 0.046, 0.036, -18), (10, 0.048, 0.038, 22),
                                      (24, 0.05, 0.042, 28), (36, 0.044, 0.04, 32)):
        bangs.append(L(az=a + rng.uniform(-2, 2), el=50, length=length * rng.uniform(0.96, 1.04), width=width, depth=0.3, hug=1.0,
                       lift=0.016, heading=heading, peak=0.28, point=0.8, root=0.7))
    for a, heading in ((-72, -6), (72, 6)):
        bangs.append(L(az=a, el=40, length=0.12, width=0.04, depth=0.3, hug=0.45, lift=0.012, fall=1.4, flare=0.18, heading=heading,
                       curl=-6, peak=0.28, point=0.9, root=0.7))
    return locks, bangs


def _katana(p, name, pommel, hilt, guard, m) -> list:
    """The katana in his hands (blender/lib/props.py katana): its flat to his sides, the guard at `guard`."""
    return props.katana(name, m, pommel, hilt, hilt=float(np.linalg.norm(np.asarray(guard) - pommel)), blade=BLADE,
                        sori=SORI)


def _scabbard(p, name, m) -> list:
    """The empty scabbard thrust through his obi at the left hip, its end back and down."""
    import bpy

    bpy.context.view_layer.update()
    hips = np.array(p.rig.pose.bones["spine05"].head)
    mouth = hips + np.array((0.13, -0.11, 0.04))
    d = np.array((0.1, 1.0, -0.4))
    d /= np.linalg.norm(d)
    path = [mouth + d * f * 0.78 for f in (0.0, 0.5, 1.0)]
    saya = shapes.loft(f"{name}-saya", path, [0.019, 0.018, 0.016], [0.013, 0.0125, 0.0115], material=m["lacquer"], n=12,
                       subsurf=0)
    return [saya]


def _sandals(p, name, m) -> list:
    """Straw sandals under his planted feet: a sole and the cords over the instep."""
    import bpy

    bpy.context.view_layer.update()
    out = []
    for side in ("L", "R"):
        pb = p.rig.pose.bones[f"foot.{side}"]
        ankle = np.array(pb.head)
        toes = np.array(pb.tail)
        fwd = toes - ankle
        fwd[2] = 0.0
        fwd /= np.linalg.norm(fwd)
        across = np.array((-fwd[1], fwd[0], 0.0))
        heel = np.array((ankle[0], ankle[1], 0.0)) - fwd * 0.065
        tip = heel + fwd * 0.27
        sole = shapes.loft(f"{name}-waraji.{side}", [heel + (0, 0, 0.006), (heel + tip) / 2 + np.array((0, 0, 0.006)),
                                                    tip + (0, 0, 0.006)],
                           [0.042, 0.05, 0.04], 0.0065, material=m["straw"], n=12, power=3.0, subsurf=0, up=(0, 0, 1))
        out.append(sole)
        for s in (-1, 1):
            a = heel + fwd * 0.17 + across * s * 0.045 + np.array((0, 0, 0.012))
            b = ankle + across * s * 0.02 + np.array((0, 0, 0.0))
            out.append(shapes.cylinder(f"{name}-cord.{side}{s}", tuple(a), tuple(b), 0.0035, material=m["straw"], n=6))
    return out
