"""The standoff, made in Blender, cut as anime covers a face-off: the wide two-shot of Shinza and Tsuru ten paces
apart on the jetty in the downpour (the river, its ridges of mountains fading into the mist, the hut's red lantern
swinging at the left, the covered boat at the right, the camera easing in), then Shinza's medium close-up, lightning
forking down in the space he glares into and whitening him, his eyes narrowing, then Tsuru's, calm, until her eyes
open.

The set is 3D (films/rain-ferry/blender/rf/sets.py, in the toon look of blender/lib/toon.py); the cast is drawn, as a
TV anime draws its characters over its backgrounds: 2D cels (blender/lib/cels.py) from rf/shinza_cels.py,
rf/shinza_full.py and rf/tsuru_cels.py, standing in the set as Grease Pencil cards turned to the camera. Full figures
in metres stand on the deck in the wide; busts in head units hang where the heads are in the close-ups. They are drawn
on twos, on ones through the lightning and through Tsuru's look. The rain falls in 3D; the drops between the lens and a
card are drawn again on the card (a rain layer clipped to its drawing), since Grease Pencil goes over blended surfaces.

One plate, three setups: the camera, its lens and focus, which cards show and the near set's line art are keyed frame
by frame (held, so each cut lands on its frame).

The cast can be 3D instead: RF_CAST=vroid (or shots/standoff_vroid.py, whose plates are its own) builds Shinza and Tsuru
from their VRoid Studio models (rf/vroid_cast.py, blender/lib/vrm.py), standing where the cels stand, through the same
compositing; the close-ups are framed on their measured heads (MCU3D), they are painted as the cels are (TONES3D,
blender/lib/toon3d.py), each lit by a key of their own from the side they face (KEY3D), their outlines keyed to a
width on screen (OUTLINE), and a copy of the rain falls in the cast's layer, so the drops in front of a face stay in
front of it.
"""
from __future__ import annotations

import math

SHOT = {"scene": "standoff"}

CAM_FROM, CAM_TO = (0.25, -6.85, 1.05), (0.1, -6.1, 1.02)
AIM_FROM, AIM_TO = (0.05, 0.0, 1.02), (0.02, 0.0, 1.0)
LENS = 30.0
WIDE_PUSH = 0.45  # how far along CAM_FROM -> CAM_TO the wide gets before the cut
CUTS = (1.5, 3.0)  # s: the wide, then his close-up (the lightning falls in it), then hers
# the cast on the deck: where each stands (x, y), metres per head unit in their close-ups, the point of the bust
# drawing between the eyes and how high it hangs (m)
STAND = {"shinza": (-2.3, 0.0), "tsuru": (2.35, 0.05)}
HEAD = {"shinza": 0.235, "tsuru": 0.21}
FACE = {"shinza": ((0.07, 0.5), 1.55), "tsuru": ((-0.07, 0.5), 1.31)}
# the close-ups, framed from the drawings: lens (mm), f-stop, the head (chin at 0 to `crown`, head units) as a share of
# the letterboxed band (start, end: a slow creep in), the highest point that must stay in the band (`top`: the crown,
# her bun and pin), the camera's bearing from the face (degrees from -y toward +x: both stay on the camera's side of
# the line between them) and height off the eyes (m), which third the face sits in (-1 left, +1 right: room on the
# side they look to)
MCU = {
    "shinza": dict(lens=85.0, fstop=4.0, ratio=(0.58, 0.60), crown=1.165, top=1.165, bearing=28.0, dz=-0.04, third=-1),
    "tsuru": dict(lens=85.0, fstop=4.0, ratio=(0.58, 0.60), crown=1.114, top=1.16, bearing=-55.0, dz=-0.22, third=1),
}
# the 3D cast's close-ups: the camera's bearing from the face (a model turns its face; a card always faces the lens).
# His looks out over the river behind him as the cel's does, the hut's dark edge at the left with its lit door a thin
# warm strip at the frame's edge (further round, its lantern sits by his head)
MCU3D = {"shinza": dict(bearing=30.0), "tsuru": dict(bearing=-50.0)}
TSURU_TURN = 0.3      # rad: the 3D Tsuru turned this far from Shinza toward the camera
OUTLINE = 0.0018      # the 3D cast's outline, in frame heights
# the 3D cast painted as the cels are (blender/lib/toon3d.py). Each has a key of its own from the side they face
# (where it comes from, world: x toward Tsuru, y away from the wide's camera), per setup: in the wide a little from
# the camera's side, so they read lit with their backs in shade (his back to the lantern's rim); in a close-up a little
# from beyond them, so the cheek nearer the lens falls into the 1st shade
KEY3D = {"wide": {"shinza": (1.0, -0.3, 0.8), "tsuru": (-1.0, -0.3, 0.8)},
         "shinza": {"shinza": (1.0, 0.95, 0.6), "tsuru": (-1.0, -0.3, 0.8)},
         "tsuru": {"shinza": (1.0, -0.3, 0.8), "tsuru": (-1.0, 0.35, 0.75)}}
KEY3D_ANGLE = 5.0     # degrees: an overcast key's soft-edged shadows
# how each part is painted (toon3d.Tone's fields): rain-cooled shades (skin to a mauve, cloth and hair to a slate
# blue), a deep 2nd shade in their cores and creases, the face kept a little more lit, wet cloth and hair sheened, the
# lines a dark brown round skin and a dark blue round everything else; eyes and the drawn face unshaded
SKIN3D = dict(shade=(0.6, 0.47, 0.6), deep=(0.38, 0.28, 0.43), lit=(0.84, 0.79, 0.8), crease=0.35, flash=0.6, sink=0.35,
              line_mul=0.12, line_add=(0.022, 0.009, 0.009))
TONES3D = {
    "skin": SKIN3D,
    "face_skin": {**SKIN3D, "bias": 0.1, "cast": -0.2, "form": 0.6},
    # (its flash is rf/vroid_common.py's CLOTH_FLASH: the props of cloth whiten alike)
    "cloth": dict(shade=(0.55, 0.58, 0.76), deep=(0.3, 0.32, 0.5), crease=0.45, sheen=((0.05, 0.06, 0.08), 0.22, 1.0),
                  flash=0.03, sink=0.35, line_mul=0.22, line_add=(0.004, 0.006, 0.015)),
    "hair": dict(shade=(0.55, 0.6, 0.8), deep=(0.3, 0.34, 0.55), bias=-0.08, crease=0.35,
                 spec=((0.09, 0.11, 0.15), 0.25, 0.55, 1.0), sheen=((0.06, 0.07, 0.1), 0.2, 1.0), flash=0.03, sink=0.35,
                 line_mul=0.25, line_add=(0.004, 0.006, 0.018)),
    "face": dict(shaded=False, lit=(0.9, 0.9, 0.92), flash=0.3),
    "eye": dict(shaded=False, lit=(0.78, 0.8, 0.86), flash=0.4),
}
# ... and what is a character's own: his black hair lifted to the cels' dark slate blue, so its shades and lines show
TONES3D_OF = {"shinza": {"hair": dict(lit=(1.9, 2.0, 2.5))}}
GATE_H = 20.25    # the engine's gate (mm), fit vertically (rig.engine_camera)
BAND = (0.128, 0.872)   # the 2.39 letterbox's visible band, in frame heights from the bottom
TOP_V = 0.86      # the highest a close-up's `top` reaches on screen
# the compositing (blender/lib/satsuei.py): the storm's light on the drawn cast, per setup. Colours linear; a rim is
# (where its light is on screen, x right and y up; its colour; strength; width in frame heights; softness), and the
# para darkens from its first point to its second (frame fractions from the bottom left). The sky is cold, from above
# and from the open river; the hut's lantern hangs behind Shinza (screen left) and warms his back edge, the ferry's
# behind Tsuru (screen left) warms hers a little; the rain's air lies between the lens and them
SKY_RIM, LANTERN_RIM, BOAT_RIM = (0.6, 0.68, 0.85), (1.0, 0.5, 0.18), (0.95, 0.58, 0.26)
LOOKS = {
    "wide": dict(gain=(0.86, 0.87, 0.91), saturation=0.9, haze_amount=0.015, para_amount=0.3, para=(0.55, 0.58, 0.7),
                 para_from=(0.5, 0.62), para_to=(0.5, 0.25), rims=[((0.2, 1.0), SKY_RIM, 0.2, 0.002, 0.8)], wrap=0.1,
                 wrap_width=0.004),
    "shinza": dict(gain=(0.9, 0.9, 0.95), saturation=0.92, haze_amount=0.02, para_amount=0.5, para=(0.5, 0.53, 0.7),
                   para_from=(0.7, 0.85), para_to=(0.2, 0.12),
                   rims=[((-1.0, 0.3), LANTERN_RIM, 0.45, 0.0035, 0.9), ((0.4, 1.0), SKY_RIM, 0.25, 0.003, 0.9)],
                   wrap=0.3, wrap_width=0.02),
    "tsuru": dict(gain=(0.9, 0.9, 0.95), saturation=0.92, haze_amount=0.02, para_amount=0.45, para=(0.5, 0.53, 0.7),
                  para_from=(0.3, 0.85), para_to=(0.8, 0.12),
                  rims=[((1.0, 0.4), SKY_RIM, 0.35, 0.0035, 0.9), ((-1.0, 0.2), BOAT_RIM, 0.2, 0.003, 0.9)],
                  wrap=0.3, wrap_width=0.02),
}
# ... and what the 3D cast wants on top (it is darker than the cels and solid to its edges): more of the rain's air
# between the lens and them in the wide
LOOKS3D = {"wide": dict(haze_amount=0.05, wrap=0.15)}
# the lightning at the strike's peak: a cold rim from the bolt's side (it forks down at the right of his close-up)
# and a fainter one all round
FLASH = dict(toward=(0.8, 0.6), color=(0.85, 0.9, 1.0), strength=1.3, width=0.007, soft=1.0, round=0.35)
LIGHTNING = 2.1   # s into the shot: 0.6 s into Shinza's close-up
NARROW = (0.75, 2, 6)       # his eyes after the strike: to 0.75, from 2 frames after it, over 6
OPEN = (0.55, 1.0, 4.0, 3)  # hers: calm, then wide, at 4.0 s, over 3 frames
BOLT = (45.0, 6.5, 26.0, -1.2)  # the drawn fork behind him: metres out, degrees right of his camera's axis, top, foot z
RAIN = dict(box_min=(-6.5, -3.6, -0.6), box_max=(6.5, 12.0, 5.5), count=5200, speed=9.5, wind=1.8, length=0.34,
            width=0.0055, color=(0.78, 0.81, 0.86), alpha=0.3, seed=4, near=3.5)
CLEAR = {"wide": 1.2, "mcu": 1.5}   # no drops nearer the lens than this (m): room in front of a face
HALO = (3.0, 0.22)                  # a drop drawn on a card: a soft halo this many times its width, this opaque
NEAR = {"wide": 3.5, "mcu": 6.0}    # drops nearer than this shrink with their distance: fine streaks, not smears
INK = {"wide": 0.0042}              # the near set's Line Art radius (m); off in the close-ups, whose set is out of focus


def mcu_camera(name: str, k: float, at=None):
    """(camera, aim) of `name`'s close-up `k` (0..1) through its creep in, from the head's share of the band: the
    frame's height at the card follows from it, the lens's distance from that, and the aim puts `top` at TOP_V and the
    face in its third. `at` frames a 3D head instead of the card: ((x, y, z) between the eyes, chin to crown and eyes to
    top in metres, the bearing)."""
    p = MCU[name]
    if at is None:
        H = HEAD[name]
        (_, fy), z = FACE[name]
        x0, y0 = STAND[name]
        head, above, bearing = p["crown"] * H, (p["top"] - fy) * H, p["bearing"]
    else:
        (x0, y0, z), head, above, bearing = at
    r = p["ratio"][0] + (p["ratio"][1] - p["ratio"][0]) * k
    h = head / (r * (BAND[1] - BAND[0]))                  # the frame's height at the card (m)
    d = h * p["lens"] / GATE_H
    b = math.radians(bearing)
    ux, uy = math.sin(b), -math.cos(b)                    # from the face toward the camera
    rx, ry = -uy, ux                                       # the camera's right
    cam = (x0 + ux * d, y0 + uy * d, z + p["dz"])
    side = p["third"] * (h * 16 / 9) / 6                   # the face's place right of the frame's middle (m)
    lift = (TOP_V - 0.5) * h - above                        # ... and over it
    aim = (x0 - rx * side, y0 - ry * side, z - lift)
    return cam, aim


def track_basis(cam, aim):
    """The camera's right, up and forward when TRACK_TO turns its -Z to `aim` with Y up."""
    import numpy as np

    f = np.subtract(aim, cam).astype(float)
    f /= np.linalg.norm(f)
    r = np.cross(f, (0.0, 0.0, 1.0))
    r /= np.linalg.norm(r)
    return r, np.cross(r, f), f


def card_screen(name: str, cam, aim, points):
    """Where points of `name`'s bust (head units) land in the frame, as (u, v) in frame widths and heights from the
    bottom left: the card hangs square to the lens with its face point on the face."""
    import numpy as np

    lens = MCU[name]["lens"]
    H = HEAD[name]
    (fx, fy), z = FACE[name]
    e = np.array([*STAND[name], z])
    r, up, f = track_basis(cam, aim)
    P = np.asarray(points, float)
    world = e + np.outer(P[:, 0] - fx, r) * H + np.outer(P[:, 1] - fy, up) * H
    rel = world - np.asarray(cam, float)
    depth = rel @ f
    h = depth * GATE_H / lens
    return np.c_[0.5 + (rel @ r) / (h * 16 / 9), 0.5 + (rel @ up) / h]


CROWN_LAYERS = {"shinza": ("hair",), "tsuru": ("hair",)}            # what the crown is the top of, in the drawings
TOP_LAYERS = {"shinza": ("hair",), "tsuru": ("hair", "bun", "pin")}   # ... and what must stay in the band


def windows(fps: float, n_frames: int) -> dict:
    """Each setup's plate frames, [first, last]."""
    c1, c2 = round(CUTS[0] * fps), round(CUTS[1] * fps)
    return {"wide": (0, c1 - 1), "shinza": (c1, c2 - 1), "tsuru": (c2, n_frames - 1)}


def creep(name: str, f_rel: int, fps: float, n_frames: int) -> float:
    """How far through its creep in a close-up is at plate frame f_rel (0..1, eased)."""
    a, b = windows(fps, n_frames)[name]
    return ease((f_rel - a) / max(1, b - a))


def framing(name: str, draw, fps: float, n_frames: int) -> list[dict]:
    """Every frame of a close-up measured against the letterbox: the head's share of the band (chin to crown), where
    the top of the crown (or bun) and the bottom of the bust land (v, frame heights from the bottom; the band is
    BAND), from the drawing as drawn on that frame (`draw(t)`: its breath and the push in included)."""
    import numpy as np

    a, b = windows(fps, n_frames)[name]
    out = []
    for k in range(a, b + 1):
        d = draw(k / fps)
        cam, aim = mcu_camera(name, creep(name, k, fps, n_frames))

        def top_of(layers):
            pts = [p.points for n in layers if n in d.layers for p in d.layers[n].pieces if len(p.points)]
            return float(np.vstack(pts)[:, 1].max())

        skin = np.vstack([p.points for p in d.layers["skin"].pieces])
        chin, crown, top = float(skin[:, 1].min()), top_of(CROWN_LAYERS[name]), top_of(TOP_LAYERS[name])
        bottom = d.bounds()[1]
        (fx, fy), _ = FACE[name]
        uv = card_screen(name, cam, aim, [(fx, chin), (fx, crown), (fx, top), (fx, bottom), (fx, fy)])
        out.append(dict(frame=k, ratio=(uv[1, 1] - uv[0, 1]) / (BAND[1] - BAND[0]), top=uv[2, 1], bottom=uv[3, 1],
                        face=(uv[4, 0], uv[4, 1])))
    return out


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def lerp(a, b, k):
    return tuple(x + (y - x) * k for x, y in zip(a, b))


# ---------------------------------------------------------------------------------------------------- the drawings

def _drawing(module: str, func: str):
    """A drawing function from rf/<module>.py, or None while it is not there (or not working) yet."""
    import importlib

    try:
        fn = getattr(importlib.import_module(f"rf.{module}"), func, None)
        if fn is not None:
            fn(0.0)   # one drawing made, so one that fails when called is caught here too
        return fn
    except Exception as e:  # noqa: BLE001 - a drawing still being written must not stop the shot
        print(f"standoff: rf.{module}.{func} unavailable ({e!r}); drawing a stand-in")
        return None


def _mirrored(fn):
    """A bust drawing turned to face the other way (a stand-in for a close-up not drawn yet)."""
    def draw(t, flash=0.0, eyes=1.0):
        d = fn(t, flash=flash, eyes=eyes)
        for L in d.layers.values():
            for p in L.pieces:
                p.points = p.points * [-1.0, 1.0]
        return d
    return draw


def _figure(height: float, facing: int, body: str, head: str = "#d9b9a6"):
    """A plain standing figure `height` tall facing +x (`facing` 1) or -x (-1): a stand-in for a full drawing."""
    import numpy as np

    from lib import cels

    def draw(t, flash=0.0):
        h, s = height, facing
        d = cels.Drawing()
        outline = np.array([(-0.24, 0.0), (0.26, 0.0), (0.2, 0.46 * h), (0.24, 0.8 * h), (0.12, 0.84 * h), (-0.1, 0.84 * h),
                            (-0.22, 0.8 * h), (-0.2, 0.46 * h)]) * [s, 1]
        d.add("body", cels.Fill(outline, body), cels.Line(outline, 0.012, cels.INK, closed=True))
        face = cels.ellipse((0.03 * s, 0.92 * h), 0.085, 0.11)
        d.add("head", cels.Fill(face, head), cels.Line(face, 0.01, cels.INK, closed=True))
        return d
    return draw


def _keys(ob, frames_on, f_lo: int, f_hi: int) -> None:
    """Show `ob` only on frames_on (a [first, last] film frame window), keyed from f_lo to f_hi, held."""
    a, b = frames_on
    for f in sorted({f_lo, a - 1, a, b, b + 1, f_hi}):
        if f < f_lo or f > f_hi:
            continue
        hide = not (a <= f <= b)
        ob.hide_render = ob.hide_viewport = hide
        ob.keyframe_insert("hide_render", frame=f)
        ob.keyframe_insert("hide_viewport", frame=f)


def _srgb(c) -> tuple:
    """A linear colour as sRGB (cels takes sRGB)."""
    return tuple(1.055 * max(v, 0.0) ** (1 / 2.4) - 0.055 if v > 0.0031308 else 12.92 * v for v in c)


class Drops:
    """toon.rain's drops, replayed in numpy: where each is at a time, so the ones between the lens and a card can be
    drawn again on it (Grease Pencil goes over blended surfaces, which the rain is)."""

    def __init__(self, box_min, box_max, count, seed, speed, wind, length, width, near, **_):
        import numpy as np

        self.lo, self.hi = np.asarray(box_min, float), np.asarray(box_max, float)
        self.pts = np.random.default_rng(seed).uniform(self.lo, self.hi, size=(count, 3))
        self.size = np.random.default_rng(seed + 101).uniform(0.65, 1.3, count)   # the GN's random scale, near enough
        tilt = math.atan2(wind, speed)
        self.half = np.array([math.sin(tilt) * length / 2, 0.0, math.cos(tilt) * length / 2])
        self.speed, self.wind, self.width, self.near = speed, wind, width, near

    def at(self, seconds: float):
        import numpy as np

        P = self.pts.copy()
        span = self.hi - self.lo
        for i, rate in ((0, self.wind), (2, -self.speed)):
            v = (P[:, i] - self.lo[i] + rate * seconds) / span[i]
            P[:, i] = self.lo[i] + (v - np.floor(v)) * span[i]
        return P

    def front(self, seconds, cam, origin, ax, ay, clear, near, bounds):
        """The drops between `cam` and the plane through `origin` spanned by ax, ay, projected onto it: [(u0, v0, u1,
        v1, width)] in the plane's metres, those over `bounds` (u0, v0, u1, v1)."""
        import numpy as np

        cam, origin, ax, ay = (np.asarray(v, float) for v in (cam, origin, ax, ay))
        n = np.cross(ax, ay)
        n /= np.linalg.norm(n)
        dc = float(np.dot(cam - origin, n))
        if dc < 0:
            n, dc = -n, -dc
        P = self.at(seconds)
        dist = np.linalg.norm(P - cam, axis=1)
        k = np.clip(dist / near, 0.0, 1.0) * (dist > clear) * self.size
        e0, e1 = P - k[:, None] * self.half, P + k[:, None] * self.half
        d0, d1 = (e0 - origin) @ n, (e1 - origin) @ n
        ok = (k > 0) & (d0 > 0) & (d0 < dc) & (d1 > 0) & (d1 < dc)
        if not ok.any():
            return []
        e0, e1, d0, d1, k = e0[ok], e1[ok], d0[ok], d1[ok], k[ok]
        r0, r1 = dc / (dc - d0), dc / (dc - d1)
        q0 = cam + (e0 - cam) * r0[:, None] - origin
        q1 = cam + (e1 - cam) * r1[:, None] - origin
        u0, v0, u1, v1 = q0 @ ax, q0 @ ay, q1 @ ax, q1 @ ay
        over = ~((np.maximum(u0, u1) < bounds[0]) | (np.minimum(u0, u1) > bounds[2]) |
                 (np.maximum(v0, v1) < bounds[1]) | (np.minimum(v0, v1) > bounds[3]))
        w = self.width * k * (r0 + r1) / 2
        return [tuple(float(x) for x in row) for row in np.c_[u0, v0, u1, v1, w][over]]


# ---------------------------------------------------------------------------------------------------- the shot

def build(ctx, cast_kind: str | None = None):
    """The shot, its cast drawn (cast_kind "cels", the default) or 3D ("vroid"; $RF_CAST when not given)."""
    import os
    import sys
    from pathlib import Path

    import bpy
    import numpy as np
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cels, rig, satsuei, toon, vrm
    from rf import sets

    scene = ctx.scene
    scene.render.use_motion_blur = False  # drawn animation has no shutter (and the rain's drops wrap)
    scene.eevee.use_shadows = True
    scene.eevee.use_raytracing = True
    scene.view_settings.view_transform = "Standard"
    world = scene.world
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.03, 0.032, 0.038, 1)  # a dim ambient: the cel bands come from the key

    look = toon.Look(fog=sets.SKY, fog_near=18.0, fog_far=480.0, fog_max=0.9, fog_power=0.65)
    crossing = sets.crossing(look)
    ink_near = toon.ink("ink-near", crossing["near"], radius=INK["wide"], crease=150)

    # the key: overcast light from the upper left, behind the camera's shoulder
    sun = bpy.data.lights.new("key", "SUN")
    sun.angle = math.radians(3)
    key = bpy.data.objects.new("key", sun)
    scene.collection.objects.link(key)
    key.rotation_euler = Vector((0.55, 0.45, -0.7)).to_track_quat("-Z", "Y").to_euler()

    # rain in front of the camera, out past the jetty; near a close-up's camera the drops thin to fine streaks, and
    # none fall within CLEAR of the lens
    rain = toon.rain("rain", RAIN["box_min"], RAIN["box_max"], count=RAIN["count"], speed=RAIN["speed"],
                     wind=RAIN["wind"], length=RAIN["length"], width=RAIN["width"], color=RAIN["color"],
                     alpha=RAIN["alpha"], seed=RAIN["seed"], near=RAIN["near"], clear=CLEAR["wide"])
    clear_in = next(n.inputs[1] for n in rain.modifiers[0].node_group.nodes
                    if n.bl_idname == "ShaderNodeMath" and n.operation == "GREATER_THAN")
    near_in = next(n.inputs["From Max"] for n in rain.modifiers[0].node_group.nodes if n.bl_idname == "ShaderNodeMapRange")
    drops = Drops(**RAIN)
    cast_kind = cast_kind or os.environ.get("RF_CAST", "cels")
    if cast_kind not in ("cels", "vroid"):
        raise ValueError(f"standoff: RF_CAST={cast_kind!r} (cels or vroid)")
    cast = toon.collection("cast")
    actors, at3d = {}, {}
    if cast_kind == "vroid":
        # the 3D cast where the cels stand, facing each other (Tsuru turned a little to the camera), their heads
        # measured for the close-ups
        from rf import vroid_cast

        cast_look = toon.Look(fog=look.fog, fog_near=look.fog_near, fog_far=look.fog_far, fog_max=look.fog_max,
                              fog_power=look.fog_power)
        for name, turn in (("shinza", 0.0), ("tsuru", math.pi + TSURU_TURN)):
            actors[name] = built = getattr(vroid_cast, name)(cast, cast_look)
            built["root"].location = (*STAND[name], 0.0)
            built["root"].rotation_euler = (0.0, 0.0, turn)
            bpy.context.view_layer.update()
            ch = built["vrm"]
            face = ch.face()
            chin, crown = ch.head_span()
            at3d[name] = ((face.x, face.y, face.z), crown - chin, crown - face.z, MCU3D[name]["bearing"])
            print(f"standoff: 3D {name}: eyes at {tuple(round(v, 3) for v in face)}, head {crown - chin:.3f} m")
        # painted as the cels are: each lit by a key of its own (aimed per setup below); the shot's sun lights the set
        # alone (a collection of its own, which the compositor leaves out of the cast's layer)
        from lib import toon3d

        toon.move_to(key, toon.collection("world-light"))
        keys3d = {}
        for name, built in actors.items():
            keys3d[name] = toon3d.key(f"{name}-key", [built["root"], *built["root"].children_recursive],
                                      KEY3D["wide"][name], coll=cast, angle=KEY3D_ANGLE)
            tones = {p: toon3d.Tone(**{**kw, **TONES3D_OF.get(name, {}).get(p, {})}) for p, kw in TONES3D.items()}
            vrm.anime(built["vrm"], tones, keys3d[name])
            vrm.smooth(built["vrm"])
        # the drops in front of them: the rain again in the cast's layer (the same drops: only those over a figure
        # pass the compositor's depth test)
        rain_cast = rain.copy()
        rain_cast.name = "rain-cast"
        cast.objects.link(rain_cast)
    # drops landing on the deck and on the water in front of it
    toon.splashes("splash-deck", (sets.SPAN[0], -sets.HALF + 0.05, 0.004), (sets.SPAN[1], sets.HALF - 0.05, 0.004),
                  count=240, size=0.08, seed=5)
    toon.splashes("splash-river", (-7.5, -3.6, sets.WATER_Z + 0.002), (7.5, -1.15, sets.WATER_Z + 0.002), count=340,
                  size=0.11, alpha=0.45, seed=9)

    # ---- the setups ----
    def face_at(name: str) -> Vector:
        x, y = STAND[name]
        return Vector((x, y, FACE[name][1]))

    def mcu(name: str, k: float):
        c_, a_ = mcu_camera(name, k, at3d.get(name))
        return Vector(c_), Vector(a_)

    f_cut1 = round(CUTS[0] * ctx.fps)
    f_cut2 = round(CUTS[1] * ctx.fps)
    n_frames = ctx.f1 - ctx.f0

    def setup(f_rel: int):
        """(name, camera, aim, lens, f-stop) for a frame of the plate (0 its first)."""
        if f_rel < f_cut1:
            k = ease(max(0, f_rel) / max(1, f_cut1 - 1)) * WIDE_PUSH
            return "wide", lerp(CAM_FROM, CAM_TO, k), lerp(AIM_FROM, AIM_TO, k), LENS, 5.6
        name = "shinza" if f_rel < f_cut2 else "tsuru"
        c, a = mcu(name, creep(name, f_rel, ctx.fps, n_frames))
        return name, tuple(c), tuple(a), MCU[name]["lens"], MCU[name]["fstop"]

    def basis(cam_at, aim_at):
        """The camera's right and up (as TRACK_TO, -Z at the aim and Y up, turns it)."""
        fwd = (Vector(aim_at) - Vector(cam_at)).normalized()
        right = fwd.cross(Vector((0.0, 0.0, 1.0))).normalized()
        return right, right.cross(fwd)

    cam = rig.engine_camera("camera", fstop=5.6, size=ctx.size)
    cam.data.lens = LENS
    cam.data.clip_end = 3000.0
    scene.camera = cam
    target = bpy.data.objects.new("aim", None)
    scene.collection.objects.link(target)
    c = cam.constraints.new("TRACK_TO")
    c.target = target
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    cam.data.dof.focus_object = target

    lantern = crossing["lantern"]
    lantern_base = lantern.location.copy()
    # one strike of lightning: every material of the set whitens with it (toon.FLASH) and the key flares
    flash = toon.lightning(scene, [LIGHTNING], range(ctx.f0 - 1, ctx.f1 + 1), ctx.fps, ctx.f0)
    held = []   # what is keyed per setup and must hold, not tween, across a cut
    shots = {}
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        name, cam_at, aim_at, lens, fstop = setup(f - ctx.f0)
        shots[f] = (name, cam_at, aim_at)
        cam.location = cam_at
        target.location = aim_at
        cam.data.lens = lens
        cam.data.dof.aperture_fstop = fstop
        cam.keyframe_insert("location", frame=f)
        target.keyframe_insert("location", frame=f)
        cam.data.keyframe_insert("lens", frame=f)
        cam.data.dof.keyframe_insert("aperture_fstop", frame=f)
        # the set's ink in the wide; behind a close-up the set is out of focus, drawn lines over it would not be
        ink_near.hide_render = ink_near.hide_viewport = name != "wide"
        ink_near.keyframe_insert("hide_render", frame=f)
        ink_near.keyframe_insert("hide_viewport", frame=f)
        clear_in.default_value = CLEAR["wide" if name == "wide" else "mcu"]
        clear_in.keyframe_insert("default_value", frame=f)
        near_in.default_value = NEAR["wide" if name == "wide" else "mcu"]
        near_in.keyframe_insert("default_value", frame=f)
        # the lantern swings in the wind
        lantern.rotation_euler = (math.radians(4) * math.sin(2 * math.pi * 0.6 * t),
                                  math.radians(2) * math.sin(2 * math.pi * 0.45 * t + 1), 0)
        lantern.keyframe_insert("rotation_euler", frame=f)
        sun.energy = 4.2 + 8.0 * flash[f]
        sun.keyframe_insert("energy", frame=f)
        # behind his close-up the hut's doorway and lantern stay small warm accents, not a bright block by his head
        for k_, base, near in (("door", 0.45, 0.12), ("lantern", 3.0, 1.3)):
            em = crossing["materials"][k_].node_tree.nodes["Emission"].inputs["Strength"]
            em.default_value = near if name == "shinza" else base
            em.keyframe_insert("default_value", frame=f)
    lantern.location = lantern_base
    held += [cam, target, cam.data, rain.modifiers[0].node_group]
    held += [crossing["materials"][k_].node_tree for k_ in ("door", "lantern")]

    # ---- the cast ----
    def plate(k: int) -> int:
        return ctx.f0 + k

    wins = windows(ctx.fps, n_frames)
    strike_k = next(k for k in range(n_frames) if flash[plate(k)] >= 0.99)

    def sh_eyes(k: int) -> float:
        return 1.0 + (NARROW[0] - 1.0) * ease((k - strike_k - NARROW[1]) / NARROW[2])

    open_k = round(OPEN[2] * ctx.fps)

    def ts_eyes(k: int) -> float:
        u = (k - open_k + 1) / OPEN[3]
        return OPEN[0] + (OPEN[1] - OPEN[0]) * (1 - (1 - min(1.0, max(0.0, u))) ** 2)

    def pool(name: str, x: float, y: float, window) -> None:
        """A soft dark pool on the deck where a figure stands, shown on `window` (film frames): the cast renders on a
        layer of its own, so casts no shadow on the deck."""
        shadow = bpy.data.meshes.new(f"{name}-pool")
        ring = [(0.0, 0.0, 0.0)] + [(0.55 * math.cos(2 * math.pi * i / 32), 0.22 * math.sin(2 * math.pi * i / 32), 0.0)
                                    for i in range(32)]
        shadow.from_pydata(ring, [], [(0, i, i % 32 + 1) for i in range(1, 33)])
        pool = bpy.data.objects.new(f"{name}-pool", shadow)
        crossing["near"].objects.link(pool)   # the deck's, not the cast's: the compositor lays the cast over it
        pool.location = (x, y, 0.006)
        mat = bpy.data.materials.new(f"{name}-pool")
        nt = toon.nodes(mat)
        tc = nt.nodes.new("ShaderNodeTexCoord")
        grad = nt.nodes.new("ShaderNodeTexGradient")
        grad.gradient_type = "SPHERICAL"
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1 / 0.55, 1 / 0.22, 1.0)
        nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
        nt.links.new(mp.outputs[0], grad.inputs["Vector"])
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (0.004, 0.004, 0.006, 1)
        amt = nt.nodes.new("ShaderNodeMath")
        amt.operation = "MULTIPLY"
        amt.inputs[1].default_value = 0.6
        nt.links.new(grad.outputs["Fac"], amt.inputs[0])
        mx = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(amt.outputs[0], mx.inputs["Fac"])
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(em.outputs[0], mx.inputs[2])
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(mx.outputs[0], out.inputs["Surface"])
        mat.surface_render_method = "BLENDED"
        shadow.materials.append(mat)
        pool.visible_shadow = False
        _keys(pool, window, ctx.f0 - 1, ctx.f1)

    rain_lin = np.array(RAIN["color"])

    def look_of(f: int):
        """The compositing look at film frame f: its setup's, lifted by the lightning (the flash's own whitening is
        the drawings'): the grade let go, the para gone, a cold rim all round."""
        p = dict(LOOKS[shots[f][0]], **(LOOKS3D.get(shots[f][0], {}) if cast_kind == "vroid" else {}))
        fl = flash[f]
        p["rims"] = tuple(satsuei.Rim(*r) for r in p["rims"])
        p["gain"] = tuple(g + (1 - g) * fl for g in p["gain"])
        p["para_amount"] *= 1 - fl
        if fl > 0:
            p["rims"] += (satsuei.Rim(FLASH["toward"], FLASH["color"], FLASH["strength"] * fl, FLASH["width"],
                                      FLASH["soft"]),)
        return satsuei.Look(**p, haze=tuple(sets.SKY), flash=FLASH["round"] * fl, flash_color=FLASH["color"])

    if cast_kind == "vroid":
        # the 3D cast: their faces keyed by the cels' eyes (his narrowing after the strike, hers opening), their
        # outlines a width on screen whatever the setup, a pool under each in the wide
        sh_face, ts_face = actors["shinza"]["face"], actors["tsuru"]["face"]
        for f in range(ctx.f0 - 1, ctx.f1 + 1):
            k = f - ctx.f0
            setup_name, cam_at = shots[f][0], Vector(shots[f][1])
            vrm.express(actors["shinza"]["vrm"], sh_face(sh_eyes(k) if setup_name != "wide" else 1.0), frame=f)
            vrm.express(actors["tsuru"]["vrm"], ts_face(ts_eyes(k) if setup_name == "tsuru" else OPEN[0]), frame=f)
            lens = LENS if setup_name == "wide" else MCU[setup_name]["lens"]
            for name, built in actors.items():
                d = (cam_at - built["vrm"].face()).length
                vrm.key_outline(built["vrm"], vrm.outline_width(OUTLINE, d, lens), f)
                toon3d.aim(keys3d[name], KEY3D[setup_name][name], frame=f)
        for name, built in actors.items():
            held += [ob.data.shape_keys for ob in built["vrm"].meshes if ob.data.shape_keys is not None]
            pool(name, *STAND[name], (plate(wins["wide"][0]), plate(wins["wide"][1])))
    else:
        sh_close = _drawing("shinza_cels", "closeup")
        ts_close = _drawing("tsuru_cels", "closeup") or _mirrored(sh_close)
        sh_full = _drawing("shinza_full", "full") or _figure(1.75, 1, "#3c4150")
        ts_full = _drawing("tsuru_cels", "full") or _figure(1.42, -1, "#8a7346", head="#d4b8a8")
        # every close-up frame measured against the letterbox: no bust's bottom may show above it, no crown leave it
        for name, fn in (("shinza", sh_close), ("tsuru", ts_close)):
            m = framing(name, fn, ctx.fps, n_frames)
            ratio = [x["ratio"] for x in m]
            low = max(x["bottom"] for x in m)
            high = max(x["top"] for x in m)
            print(f"standoff: {name}'s close-up: head {min(ratio):.1%}-{max(ratio):.1%} of the band; top at {high:.3f}, "
                  f"bust bottom at {low:.3f} (band {BAND[0]}-{BAND[1]})")
            if low > BAND[0] - 0.01 or high > BAND[1]:
                raise ValueError(f"standoff: {name}'s close-up leaves the letterbox's band (top {high:.3f}, bottom {low:.3f})")

        def mcu_frames(name: str, extra) -> list[int]:
            a, b = wins[name]
            return sorted(k for k in set(cels.twos(a, b + 1)) | set(extra) if a <= k <= b)

        def rain_layer(card, cam_of, plane_of, bounds, window):
            """The drops between the lens and `card` drawn again on it, every frame of `window` (plate frames),
            clipped to the card's drawing. `plane_of(f)` -> (origin, ax, ay, local offset) of the card's plane."""
            names = [L.name for L in card.data.layers]
            frames = {}
            a, b = window
            for k in range(a, b + 1):
                f = plate(k)
                origin, ax, ay, off = plane_of(f)
                fl = flash[f]
                # the compositor grades the card, these drops with it: they are drawn brighter by its gain, so they come
                # out the rain's own colour
                col = _srgb((rain_lin + (1 - rain_lin) * fl) / np.array(look_of(f).gain))
                alpha = RAIN["alpha"] * (1 + fl)
                pieces = []
                for u0, v0, u1, v1, w in drops.front(f / ctx.fps, cam_of(f), origin, ax, ay,
                                                     CLEAR["wide" if a == 0 else "mcu"], NEAR["wide" if a == 0 else "mcu"],
                                                     bounds):
                    seg = np.array([[u0 + off[0], v0 + off[1]], [u1 + off[0], v1 + off[1]]])
                    # out of focus this near the lens: a soft halo round a fine core
                    pieces.append(cels.Line(seg, w * HALO[0], col, None, False, min(1.0, alpha) * HALO[1]))
                    pieces.append(cels.Line(seg, w, col, None, False, min(1.0, alpha)))
                frames[f] = pieces
            cels.add_layer(card, "rain", frames, mask=tuple(names))

        def bounds_of(drawings, scale, off=(0.0, 0.0)):
            bs = np.array([d.bounds() for d in drawings])
            return (bs[:, 0].min() * scale - off[0], bs[:, 1].min() * scale - off[1],
                    bs[:, 2].max() * scale - off[0], bs[:, 3].max() * scale - off[1])

        # the wide: full figures standing on the deck, turned to the camera (the air between them and the lens is the
        # compositor's haze)
        for name, fn in (("shinza", sh_full), ("tsuru", ts_full)):
            a, b = wins["wide"]
            ks = cels.twos(a, b + 1)
            ds = {plate(k): fn(k / ctx.fps, flash=flash[plate(k)]) for k in ks}
            card = cels.build(f"cel-{name}-wide", ds, collection=cast, scale=1.0)
            anchor = bpy.data.objects.new(f"{name}-wide", None)
            cast.objects.link(anchor)
            x, y = STAND[name]
            anchor.location = (x, y, 0.0)
            card.parent = anchor
            yaws = {}
            for f in range(ctx.f0 - 1, ctx.f1 + 1):
                cx, cy, _ = shots[f][1]
                yaws[f] = math.atan2(cx - x, -(cy - y))
                anchor.rotation_euler = (0.0, 0.0, yaws[f])
                anchor.keyframe_insert("rotation_euler", frame=f)
            held.append(anchor)
            _keys(card, (plate(a), plate(b)), ctx.f0 - 1, ctx.f1)

            def plane_wide(f, x=x, y=y, yaws=yaws):
                yw = yaws[f]
                return (np.array([x, y, 0.0]), np.array([math.cos(yw), math.sin(yw), 0.0]), np.array([0.0, 0.0, 1.0]),
                        (0.0, 0.0))

            rain_layer(card, lambda f: np.array(shots[f][1]), plane_wide, bounds_of(ds.values(), 1.0), wins["wide"])
            # a soft dark pool where they stand: drawn figures cast no shadow of their own
            pool(name, x, y, (plate(a), plate(b)))

        # the close-ups: busts hanging where the heads are, square to the lens
        for name, fn, extra, eyes in (
                ("shinza", sh_close, range(strike_k - 1, strike_k + 13), sh_eyes),
                ("tsuru", ts_close, range(open_k - 1, open_k + OPEN[3] + 1), ts_eyes)):
            a, b = wins[name]
            ds = {plate(k): fn(k / ctx.fps, flash=flash[plate(k)], eyes=eyes(k)) for k in mcu_frames(name, extra)}
            H = HEAD[name]
            (fx, fy), _ = FACE[name]
            card = cels.build(f"cel-{name}-mcu", ds, collection=cast, scale=H)
            anchor = bpy.data.objects.new(f"{name}-mcu", None)
            cast.objects.link(anchor)
            anchor.location = face_at(name)
            cr = anchor.constraints.new("COPY_ROTATION")
            cr.target = cam
            card.parent = anchor
            card.rotation_euler = (-math.pi / 2, 0.0, 0.0)     # its drawing's up to the camera's up, its face to the lens
            card.location = (-fx * H, -fy * H, 0.0)              # the point between the eyes on the anchor
            _keys(card, (plate(a), plate(b)), ctx.f0 - 1, ctx.f1)

            def plane_mcu(f, e=Vector(face_at(name)), H=H, fx=fx, fy=fy):
                right, up = basis(shots[f][1], shots[f][2])
                return np.array(e), np.array(right), np.array(up), (fx * H, fy * H)

            rain_layer(card, lambda f: np.array(shots[f][1]), plane_mcu, bounds_of(ds.values(), H, (fx * H, fy * H)),
                       wins[name])

    # the fork of lightning in his close-up: drawn, crisp, far out in the space he glares into, on the strike's
    # brightest frames
    c0, a0 = mcu("shinza", 0.5)
    fwd = Vector(a0) - Vector(c0)
    fwd.z = 0.0
    fwd.normalize()
    r = math.radians(BOLT[1])
    ray = Vector((fwd.x * math.cos(r) + fwd.y * math.sin(r), -fwd.x * math.sin(r) + fwd.y * math.cos(r), 0.0))
    foot = Vector(c0) + ray * BOLT[0]
    a, b = wins["shinza"]
    fork = cels.bolt((0.0, BOLT[2]), (1.6, BOLT[3]), width=0.075, glow=6.0, branches=3, seed=11)
    blank = cels.Drawing()
    bolt = cels.build("bolt", {plate(k): (fork if flash[plate(k)] > 0.45 else blank) for k in range(a, b + 1)},
                      collection=crossing["far"])
    bolt.location = (foot.x, foot.y, 0.0)
    bolt.rotation_euler = (0.0, 0.0, math.atan2(c0.x - foot.x, -(c0.y - foot.y)))
    _keys(bolt, (plate(a), plate(b)), ctx.f0 - 1, ctx.f1)

    # hold every per-setup key to its frame: a cut is a cut, never a frame tweened between two setups
    for owner in held:
        ad = getattr(owner, "animation_data", None)
        if ad is None or ad.action is None:
            continue
        for fc in toon._fcurves(ad.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"

    # the compositing: the cast on a view layer of its own, lit by the storm (LOOKS) frame by frame and laid back over
    # the world
    comp = satsuei.setup(scene, cast)
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        comp.key(f, look_of(f))
    comp.hold()
