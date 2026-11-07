"""The explainer set's plan: marks, props, lights and cameras as numbers, with no engine in it, so set.py builds it on a
box and `python3 setplan.py --check` proves the framing offline (the mic never over the mouth, the eyes in the upper
third, the sign in the MCU's background).

The frame is the karma studio's (unreal/studio.py): back wall x = -260, the camera side +X, screen-left +Y, up +Z, cm.
The presenter sits on the chair mark facing +X; agent-01's seated anim keeps the actor root on the mark (no root motion)
and puts the hips over it at seat top + ~9 cm, forearms on the desk.

    her left = +Y   the mic's side (the boom comes from the desk's +Y edge, low, to the side of the mouth)
    her right = -Y  the cameras' side (a slight 3/4 on her right cheek); the key from her left (+Y, the window side),
                    so the camera sees the broad side in soft fill and the far side keyed: short lighting
    behind her      the slat panel with the karma sign lowered into the MCU's background, the warm shelves (-Y)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

WALL = -260.0
MARK = (20.0, -20.0, 0.0)  # the chair mark = the presenter actor's root (agent-01's contract)
YAW = -90.0                # the presenter actor yaw: a MetaHuman BP faces +Y at yaw 0 (box B eye bones), so -90 faces +X

# the seated presenter, estimated until measured on the box (set.py measure → --face): eyes above the floor, and how
# far forward of the mark the eyes sit when leaning to the desk
SEAT_TOP = 45.0
FACE = {  # who: (eyes forward of the mark, eyes to +Y of the mark, eye height, mouth below the eyes)
    "her": (10.55, 1.24, 120.43, 6.8),  # measured on box B, 17:00 IST: agent-01's fe5ab6c0 seat, f60
    "him": (11.0, 0.0, 127.0, 9.0),     # estimate until measured on box A
}
FACE_ESTIMATED = {"him"}  # framing rules that hinge on the exact eye height (the sign's corner) wait for a measurement

# the props (agent-05; s3 …/props/explainer/). Origins: chair and desk on the floor at their centre, the mic boom at its
# desk clamp on the desk top (props/mic_boom.py's convention). Yaw in degrees about +Z.
DESK_TOP = 71.0  # r6 (agent-01, the shoulder): 3 cm lower (and 6 cm in) puts her upper arms ~35° instead of 45°
DESK_TOP_MESH = 74.0  # the desk meshes are built to 74: scaled in Z to DESK_TOP until agent-05's waterfall desk
SIDE_WALL = -330.0     # the room's -Y wall (room_shell: side walls at y = ±330)
DESK_C = (59.5, -20.0)  # r3: 12.5 cm in; r6: 6 cm more (near edge x 32) for elbows by her sides
PROPS = {  # label: (FBX stem, loc, yaw, scale)
    "ExpChair": ("SM_PodcastChair", (MARK[0], MARK[1], 0.0), 0.0, None),  # seat top 45, front edge +24.5, faces +X
    "ExpDesk": ("SM_WalnutDesk", (DESK_C[0], DESK_C[1], 0.0), 0.0, [1.0, 1.0, DESK_TOP / DESK_TOP_MESH]),  # 55 x 110: x 32..87
    # agent-05 posed the boom for a clamp on the desk's +Y edge (70,32.6,74) → capsule (44,-6,99). The cameras moved to
    # the +Y side (r3: no window behind her), so the boom is MIRRORED about the desk's centre line y = -20: local X
    # scale -1 at yaw -90 mirrors world Y → clamp (70,-72.6,74), capsule (44,-34,99), still aimed at the mouth
    # r6: the clamp 3 cm back (x 67) so the capsule follows her head (3 cm further back in agent-01's a22617ca pose)
    # r6b (the orchestrator, with agent-05's waterfall desk, whose end panel sits under the -Y edge): the clamp moves to
    # the desk's FAR (+X) edge and the boom turns about it by MIC_ROT, so the capsule stays exactly where it was
    "ExpMic": ("SM_MicBoom", None, None, [-1.0, 1.0, 1.0]),  # loc and yaw filled in below (MIC_CLAMP, -90 + MIC_ROT)
    "ExpPlant": ("SM_DeskPlant", (80.0, -66.0, DESK_TOP), 25.0, None),  # 13 x 44 cm: the far -Y corner, behind the boom
    # r5: the WIDE's right side (the -Y wall) — agent-05's floor lamp (a real practical) and a snake plant
    "ExpLamp": ("SM_FloorLamp", (-110.0, SIDE_WALL + 30.0, 0.0), 0.0, None),
    "ExpSnake": ("SM_FloorSnakePlant", (-215.0, SIDE_WALL + 32.0, 0.0), 30.0, None),
}
DESK_PANEL = "SM_WalnutDesk_Panel"  # agent-05's desk with the modesty panel; set.py uses it when it is on the box
# r6b: agent-05's waterfall desk (task 8c95, approved by the orchestrator): built at the final height (top 71, under
# the top 67.8), same frame as the panel desk, one slot dressed with the studio's walnut; preferred when on the box
DESK_WATERFALL = "SM_WalnutDesk_Waterfall"
DESK_WATERFALL_SLOTS = {"M_WalnutFine": "/Game/Studio/Materials/MI_K_Walnut"}

# the boom as agent-05 posed it (props/mic_boom.py), clamp first, on the +Y edge of a 74 cm desk
BOOM_POSE = {"clamp": (70.0, 32.6, 74.0), "elbow": (63.8, 22.9, 119.3), "tip": (49.5, 0.4, 103.4),
             "capsule": (44.0, -6.0, 99.0)}
_R6_CLAMP = (67.0, 2 * DESK_C[1] - 32.6)  # where the r6 clamp sat (the -Y edge): the capsule it gave is kept


def _mirrored(k: str) -> tuple:
    """A boom point from its clamp, mirrored to the -Y side (local X scale -1 at yaw -90)."""
    (cx, cy, cz), (x, y, z) = BOOM_POSE["clamp"], BOOM_POSE[k]
    return (x - cx, -(y - cy), z - cz)


_cap = _mirrored("capsule")
_CAPSULE_XY = (_R6_CLAMP[0] + _cap[0], _R6_CLAMP[1] + _cap[1])
_reach = math.hypot(_cap[0], _cap[1])
_cx = DESK_C[0] + 27.5 - 2.4  # the clamp's jaw 2.4 cm inside the far edge, as agent-05 posed it on the +Y edge
MIC_CLAMP = (_cx, _CAPSULE_XY[1] - math.sqrt(_reach ** 2 - (_cx - _CAPSULE_XY[0]) ** 2), DESK_TOP)
MIC_ROT = math.degrees(math.atan2(_CAPSULE_XY[1] - MIC_CLAMP[1], _CAPSULE_XY[0] - MIC_CLAMP[0])
                       - math.atan2(_cap[1], _cap[0]))
PROPS["ExpMic"] = ("SM_MicBoom", (round(MIC_CLAMP[0], 2), round(MIC_CLAMP[1], 2), DESK_TOP), round(-90.0 + MIC_ROT, 2),
                   [-1.0, 1.0, 1.0])


def boom_points() -> dict:
    """The boom's clamp, elbow, arm tip and capsule in the studio, as placed (mirrored, turned by MIC_ROT)."""
    r = math.radians(MIC_ROT)
    out = {}
    for k in BOOM_POSE:
        x, y, z = _mirrored(k)
        out[k] = (MIC_CLAMP[0] + x * math.cos(r) - y * math.sin(r), MIC_CLAMP[1] + x * math.sin(r) + y * math.cos(r),
                  MIC_CLAMP[2] + z)
    return out
LAMP_BULB = dict(kind="point", z=138.5, intensity=6.0, temperature=2700, radius=320)  # candela, channel 0
PLANT_TOP = DESK_TOP + 44.0
UV_METRES = False  # agent-05: tile_m is baked into UV0 (1 UV = tile_m metres), so Tiling 1
MIC_FROM_MOUTH = (11.5, -15.3, -14.6)  # the capsule's centre from the mouth: forward, to -Y (away from the cameras), down
MIC_LEN = 19.0                       # the capsule body's length (props/mic_boom.py)

# the set dressing that moves in this level only: the karma sign comes down into the seated MCU's background
SIGN_DROP = -30.0  # r3: out of the close frames; wholly in the WIDE beside her head (searched with the window out)  # cm on Z for Sign, SignHalo and Halo0..8 (studio: the sign's centre at z ~228)
SIGN = (WALL + 4.0, 25.0, 228.0 + SIGN_DROP)

# the studio's standing-host rig and reel cameras: not this set's (deleted in the explainer level only)
# r5 (the orchestrator): the WIDE's right half was the bare -Y side wall (y -330, x -240..0) → dressed with copies of
# the studio's own dressed actors (their materials come along), plus a warm grazing light on the new slats (channel 0)
DRESSING = {  # new label: (studio actor to copy, loc, yaw)
    "ExpSlats": ("SlatPanel", (-150.0, SIDE_WALL, 0.0), 90.0),
    "ExpOlive": ("OliveTree", (-25.0, SIDE_WALL + 55.0, 0.0), 160.0),
}
SIDE_GRAZER = dict(kind="rect", loc=(-150.0, SIDE_WALL + 30.0, 265.0), look_at=(-150.0, SIDE_WALL, 90.0),
                   intensity=1.6, temperature=2700, width=150.0, height=4.0, barn_angle=60)
# the desk's modesty panel until agent-05's SM_WalnutDesk_Panel lands: a 2 cm walnut slab inside the +X (camera) edge,
# from 8 cm up to the apron, so her feet and lower legs are never seen
MODESTY = {"loc": (DESK_C[0] + 25.5, DESK_C[1], 8.0 + (63.4 - 8.0) / 2), "size": (2.0, 98.0, 63.4 - 8.0)}
SUN_LUX = 0.0  # r5: the floor sun patches; her rig gives ~20 lux at her face, any real sun clips (the window is out of frame)

# seated garment cuts (body.hide_under on copies, this level's instance only): (component, under garment, reach cm),
# applied in order from the original meshes. Her r3 shoulder: the Top through the Overshirt seam.
GARMENT_HIDES = {
    # r6b (V2, no overshirt; agent-02): the seated waist (Trousers>Top 12 % in the WIDE) and her side (Body>Top 1.3 %,
    # the same spot in every frame, so the garment and not a gesture) need 6 cm instead of 4
    "her": [("Top", "Overshirt", 6.0), ("Trousers", "Top", 6.0), ("Body", "Top", 6.0)],
    "him": [],
}
GARMENT_SRC = {"her": {"Overshirt": "/Game/Host/Presenter_Overshirt/SKM_Presenter_Overshirt_RW",  # r6: agent-02's
                       # reweight (the MetaHuman helper/corrective joints carried 60% of the shoulder cap: it ballooned)
                       "Top": "/Game/Host/Presenter_Outfit/SKM_Presenter_Top",
                       "Trousers": "/Game/Host/Presenter_Outfit/SKM_Presenter_Trousers",
                       "Body": "/Game/Host/Unpacked/Presenter/Body/SKM_Presenter_F_BodyMesh"}, "him": {}}

# r6b (the orchestrator rejected RW: skin holes at both shoulders, a shredded collar): her overshirt is a choice made by
# eye from stills. set.py reads $EXPL_OVERSHIRT: "orig" (the round-4 weights), "rw" (agent-02's
# reweight), "none" (no overshirt: her top alone, so the Top is not cut under it; the DEFAULT since the V2 pick), "rw2" (arms-only reweight)
OVERSHIRT = {"orig": "/Game/Host/Presenter_Overshirt/SKM_Presenter_Overshirt",
             "rw": "/Game/Host/Presenter_Overshirt/SKM_Presenter_Overshirt_RW", "none": None,
             # agent-02's narrower reweight (df8947b2): only the upper-arm/forearm helpers (the cap balloon); the
             # clavicle/spine helpers that hold the collar on the body stay
             "rw2": "/Game/Host/Presenter_Overshirt/SKM_Presenter_Overshirt_RW2"}


def overshirt_variant() -> str:
    v = os.environ.get("EXPL_OVERSHIRT", "none")  # r6b: the orchestrator picked V2 (no overshirt) by eye
    if v not in OVERSHIRT:
        raise SystemExit(f"EXPL_OVERSHIRT={v!r}: one of {sorted(OVERSHIRT)}")
    return v


STUDIO_HOST_LIGHTS = ["Key", "Fill", "HairLight", "RimWarm", "RimWindow", "EyeLight"]
STUDIO_CAMS = ["KarmaHost", "KarmaWide", "KarmaVertical", "KarmaShelf", "KarmaCredenza", "KarmaSign"]

FILMBACK = [36.0, 20.25]  # full frame 16:9, every camera
# exposure, locked: manual, NOT physical-camera (so f/2 and f/2.8 cameras cut with no brightness jump). Bias is a
# compensation (higher = brighter). Box B 17:20 IST: -0.7 put her face at 164/255 with the studio's rig; one stop
# lower with her rig one stop up (LIGHT_GAIN 2) keeps the face and takes the bright window down a stop
EXPOSURE_BIAS = -0.4
LIGHT_GAIN = 2.8          # her rig (channel 1 only) x this; the set's own light (channel 0) is untouched


def face(who: str) -> dict:
    fwd, dy, eye_z, mouth_dz = FACE[who]
    eyes = (MARK[0] + fwd, MARK[1] + dy, eye_z)
    mouth = (eyes[0] + 1.9, eyes[1], eye_z - mouth_dz)
    return {"eyes": eyes, "mouth": mouth, "chin": (mouth[0], mouth[1], mouth[2] - 6.0)}


def mic(who: str) -> dict:
    """The capsule's centre, where it points (the mouth) and the boom's yaw from its clamp."""
    m = face(who)["mouth"]
    cap = tuple(a + b for a, b in zip(m, MIC_FROM_MOUTH))
    clamp = PROPS["ExpMic"][1]
    yaw = math.degrees(math.atan2(cap[1] - clamp[1], cap[0] - clamp[0]))
    d = [m[i] - cap[i] for i in range(3)]
    n = math.sqrt(sum(x * x for x in d))
    back = tuple(cap[i] - d[i] / n * MIC_LEN / 2 for i in range(3))   # the capsule's tail
    front = tuple(cap[i] + d[i] / n * MIC_LEN / 2 for i in range(3))  # its grille, nearest the mouth
    reach = math.hypot(cap[0] - clamp[0], cap[1] - clamp[1])
    return {"capsule": cap, "front": front, "back": back, "clamp": clamp, "yaw": yaw, "reach_cm": reach,
            "rise_cm": cap[2] - clamp[2]}


def _orbit(target, az_deg, el_deg, dist):
    a, e = math.radians(az_deg), math.radians(el_deg)
    return [round(target[0] + dist * math.cos(e) * math.cos(a), 2), round(target[1] + dist * math.cos(e) * math.sin(a), 2),
            round(target[2] + dist * math.sin(e), 2)]


def _aim_right(cam: dict, du: float) -> dict:
    """The same camera turned so its subject moves du of the frame width to screen-left (du > 0): the look point
    shifts to screen-right by du x the frame's width at the look distance."""
    c, a = cam["loc"], cam["look_at"]
    dist = math.dist(c, a)
    r = _right([a[i] - c[i] for i in range(3)])
    s = du * cam["filmback"][0] / cam["focal"] * dist
    return cam | {"look_at": [round(a[i] + r[i] * s, 2) for i in range(3)]}


def cameras(who: str) -> dict:
    """Each camera: loc, look_at, focal, aperture, filmback, focus bone. Azimuth from the presenter's facing (+X),
    positive = studio +Y (her right). r3 (the orchestrator): the cameras on the +Y side so every presenter background is
    the warm shelves wall, never the window (y 130..280 on the back wall); the sign stays out of the close frames. Eye level: the lens at her eye height, aimed a little below the eyes so they sit in the
    upper third. CAM_MCU_L is CAM_MCU turned so she sits on the left third, for agent-11's PANEL shots (a graphic panel
    over x 1010-1860 of 1920)."""
    eyes = face(who)["eyes"]
    plan = {  # az, el, distance from the look point, focal, f-stop, look point
        "CAM_MCU": (26.0, 2.5, 175.0, 60.0, 2.0, (eyes[0], eyes[1], eyes[2] - 7.0)),
        "CAM_CU": (17.0, 2.0, 128.0, 85.0, 2.0, (eyes[0], eyes[1], eyes[2] - 4.0)),
        # r6 (the operator: the desk front looked weird): higher and tighter, the desk top's front edge in the lower
        # third, the set behind her; within 1° of CAM_MCU_L (her look to the lens across the 43.3 s cut)
        # within 4° of CAM_MCU_L (her look to the lens across the 43.3 s cut) and the window just out of frame
        # r6b (the orchestrator: the 14° high angle read as a security camera): back near her eye level, the lens at
        # ~125 cm with a slight tilt down (el 5.5° at 280 cm), same azimuth and look point, the desk front still in the
        # lower third and the set behind
        "CAM_WIDE": (22.0, 5.5, 280.0, 35.0, 2.8, (eyes[0] + 8.0, eyes[1] - 16.0, eyes[2] - 22.0)),
    }
    out = {}
    for name, (az, el, dist, focal, stop, look) in plan.items():
        out[name] = {"loc": _orbit(look, az, el, dist), "look_at": [round(v, 2) for v in look], "focal": focal,
                     "aperture": stop, "filmback": FILMBACK,
                     # focus tracks her camera-side eye (her right, +Y): the CU's depth of field is ±1.2 cm at f/2
                     "focus": "FACIAL_R_Eye"}
    out["CAM_MCU_L"] = _aim_right(out["CAM_MCU"], 0.26)
    return out


def lights(who: str) -> dict:
    """The presenter's rig (lighting channel 1 only, as the studio's host rig): a large soft key at ~45° on the side AWAY from the cameras (-Y; short lighting),
    a gentle fill from the camera side, a warm rim on the shadow side, a hair light, a small eye light by the lens.
    Intensities (candela, look.light) are the studio's host rig's at its distances (Key 9 cd at 190 cm under the
    same locked exposure), scaled by the square of the new distance."""
    e = face(who)["eyes"]
    f = (e[0], e[1], e[2] - 5.0)

    def cd(ref_cd, ref_d, d):
        return round(LIGHT_GAIN * ref_cd * (d / ref_d) ** 2, 3)

    return {
        "ExpKey": dict(kind="rect", loc=_orbit(f, -45.0, 28.0, 175.0), look_at=f, intensity=cd(9.0, 190.0, 175.0),
                       temperature=5200, width=160, height=120, barn_angle=75),
        "ExpFill": dict(kind="rect", loc=_orbit(f, 55.0, 8.0, 230.0), look_at=f, intensity=cd(3.4, 221.0, 230.0),
                        temperature=5000, width=180, height=180, specular=0.25),
        "ExpRim": dict(kind="rect", loc=_orbit(f, 145.0, 18.0, 150.0), look_at=(f[0], f[1], f[2] - 6.0),
                       intensity=cd(3.0, 181.0, 150.0), temperature=3100, width=25, height=120, barn_angle=50),
        "ExpHair": dict(kind="rect", loc=_orbit(f, -175.0, 52.0, 140.0), look_at=(e[0] - 4.0, e[1], e[2] + 12.0),
                        intensity=cd(5.0, 133.0, 140.0), temperature=3600, width=60, height=30, barn_angle=55),
        "ExpEye": dict(kind="rect", loc=_orbit(f, 19.0, 9.0, 150.0), look_at=f, intensity=0.35 * LIGHT_GAIN, temperature=5600,
                       width=22, height=22, shadows=False),
    }


# ----------------------------------------------------------------------------------------------------- camera drift

def drift(cam: dict, start: int, end: int, seed: int = 0, step: int = 6) -> list:
    """A very subtle hand-held breathing on a locked-off camera: the lens moves ≤0.4 cm and the aim point ≤0.3 cm at
    the subject (≈0.1°), as a sum of slow sines (periods 3.7-9.1 s, phase by seed), keyed every `step` frames with
    smooth interpolation. Keys are seq.key_transform's [frame, loc, look_at]."""
    rnd = [((seed * 7919 + k * 104729) % 1000) / 1000.0 * 2 * math.pi for k in range(6)]
    out = []
    for fr in list(range(start, end, step)) + [end]:
        t = fr / 24.0
        dl = [0.30 * math.sin(2 * math.pi * t / 4.3 + rnd[0]) + 0.10 * math.sin(2 * math.pi * t / 9.1 + rnd[1]),
              0.22 * math.sin(2 * math.pi * t / 6.1 + rnd[2]),
              0.25 * math.sin(2 * math.pi * t / 3.7 + rnd[3])]  # the breath: mostly up/down
        da = [0.0, 0.22 * math.sin(2 * math.pi * t / 5.3 + rnd[4]), 0.18 * math.sin(2 * math.pi * t / 7.7 + rnd[5])]
        out.append([fr, [round(cam["loc"][i] + dl[i], 3) for i in range(3)],
                    [round(cam["look_at"][i] + da[i], 3) for i in range(3)]])
    return out


# ---------------------------------------------------------------------------------------------- offline projection

def _right(f) -> list:
    """Screen-right for a camera looking along f: looking down -X, +Y is screen-left (the studio's frame)."""
    n = math.hypot(f[0], f[1])
    return [-f[1] / n, f[0] / n, 0.0]


def project(cam: dict, p) -> tuple:
    """(u, v, depth): u, v 0..1 from the top left, a pinhole with the camera's focal and filmback."""
    c, a = cam["loc"], cam["look_at"]
    f = [a[i] - c[i] for i in range(3)]
    n = math.sqrt(sum(x * x for x in f))
    f = [x / n for x in f]
    r = _right(f)
    up = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
    if up[2] < 0:
        up = [-x for x in up]
    d = [p[i] - c[i] for i in range(3)]
    z = sum(d[i] * f[i] for i in range(3))
    x = sum(d[i] * r[i] for i in range(3))
    y = sum(d[i] * up[i] for i in range(3))
    w, h = cam["filmback"]
    return (0.5 + x / z * cam["focal"] / w, 0.5 - y / z * cam["focal"] / h, z)


def check(who: str) -> list:
    """The framing rules, offline: [(rule, ok, detail)]."""
    fc, mc, cams = face(who), mic(who), cameras(who)
    rows = []
    for name, cam in cams.items():
        eu, ev, ez = project(cam, fc["eyes"])
        mu, mv, _ = project(cam, fc["mouth"])
        # the mic's capsule as a segment; how near it comes to the mouth on screen, in frame heights
        pts = [project(cam, mc["back"]), project(cam, mc["capsule"]), project(cam, mc["front"])]
        near = min(math.hypot((pu - mu) * 16 / 9, pv - mv) for pu, pv, _ in pts)
        # the mouth's own size on screen (~5 cm wide) to scale the margin
        mouth_h = 5.0 / ez * cam["focal"] / cam["filmback"][1]
        u_lo, u_hi = (0.2, 0.42) if name.endswith("_L") else (0.2, 0.8)
        rows.append((f"{name} eyes upper third", 0.22 <= ev <= 0.42 and u_lo <= eu <= u_hi, f"u {eu:.3f} v {ev:.3f}"))
        if name.endswith("_L"):  # everything of hers (and the mic) left of the panel at x 1010/1920
            xs = [project(cam, q)[0] for q in (fc["eyes"], fc["mouth"], mc["back"], mc["front"],
                                                (fc["eyes"][0], fc["eyes"][1] - 22.0, fc["eyes"][2] - 30.0))]
            rows.append((f"{name} her and the mic left of the panel (u < 0.51)", max(xs) < 0.51,
                         f"max u {max(xs):.3f}"))
        rows.append((f"{name} mic clear of the mouth", near > 2.0 * mouth_h,
                     f"nearest {near:.3f} frame-h vs mouth {mouth_h:.3f}; capsule below the mouth: "
                     f"{all(pv > mv for _, pv, _ in pts)}"))
        rows.append((f"{name} mic below the mouth", all(pv > mv for _, pv, _ in pts),
                     ", ".join(f"v {pv:.3f}" for _, pv, _ in pts) + f" (mouth v {mv:.3f})"))
        # r3: no window in any presenter frame (its opening on the back wall, y 130..280, z 0..285)
        wp = [project(cam, (WALL + 2, y, z)) for y in (130, 170, 205, 240, 280) for z in (10, 80, 150, 220, 285)]
        inside = [p for p in wp if -0.01 <= p[0] <= 1.01 and -0.01 <= p[1] <= 1.01]
        rows.append((f"{name} no window in frame", not inside, f"{len(inside)} window points in frame"))
        # the sign: clear of her head, wholly in or wholly out (never cut by the head or the frame edge)
        sp = [project(cam, (SIGN[0], SIGN[1] + dy, SIGN[2] + dz)) for dy in (-60, 0, 60) for dz in (-18, 18)]
        n_in = sum(0 <= p[0] <= 1 and 0 <= p[1] <= 1 for p in sp)
        head = min(abs(p[0] - eu) for p in sp)
        rows.append((f"{name} sign wholly in (clear of the head) or wholly out", n_in == 0 or (n_in == len(sp)
                     and head > 0.12), f"{n_in}/{len(sp)} sign points in frame, nearest to the eyes {head:.2f}"))
        if name == "CAM_WIDE":  # r6: the desk front small in frame (its top's camera-side edge in the lower third)
            dv = [project(cam, (DESK_C[0] + 27.5, y, DESK_TOP))[1] for y in (DESK_C[1] - 55, DESK_C[1], DESK_C[1] + 55)]
            rows.append(("CAM_WIDE desk front in the lower third", min(dv) >= 0.67, f"v {[round(v, 3) for v in dv]}"))
    for name, cam in cams.items():  # the desk plant stays off her face and mouth
        x, y, _ = PROPS["ExpPlant"][1]
        mu, mv, _ = project(cam, fc["mouth"])
        pts = [project(cam, (x + dx, y + dy, PLANT_TOP)) for dx in (-8, 8) for dy in (-8, 8)]
        clear = all(pv > mv + 0.05 or abs(pu - mu) > 0.15 for pu, pv, _ in pts)
        rows.append((f"{name} desk plant off the mouth", clear,
                     "top corners " + ", ".join(f"({pu:.2f},{pv:.2f})" for pu, pv, _ in pts) + f" mouth ({mu:.2f},{mv:.2f})"))
    bp = boom_points()
    for name, cam in cams.items():  # r6b: the boom's arm (elbow, tip) stays off her face on screen
        eu, ev, _ = project(cam, fc["eyes"])
        cu, cv, _ = project(cam, fc["chin"])
        on_face = []
        for k in ("elbow", "tip"):
            for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                a, b = bp[k], bp["tip" if k == "elbow" else "capsule"]
                q = tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
                pu, pv, _ = project(cam, q)
                if abs(pu - eu) < 0.07 and ev - 0.08 < pv < cv + 0.02:
                    on_face.append((k, t, round(pu, 3), round(pv, 3)))
        rows.append((f"{name} boom arm off her face", not on_face, f"{on_face[:3]}" if on_face else
                     f"elbow {tuple(round(v, 3) for v in project(cam, bp['elbow'])[:2])} eyes ({eu:.3f},{ev:.3f})"))
    rows.append(("mic boom reach (prop: ~45 cm, +35 cm)", 30.0 <= mc["reach_cm"] <= 60.0,
                 f"reach {mc['reach_cm']:.1f} cm, rise {mc['rise_cm']:.1f} cm, yaw {mc['yaw']:.1f}°"))
    return rows


def set_for_perf(who: str) -> dict:
    """agent-01's perform.py set file (set_<who>.json), in the actor frame (studio - MARK): the desk and the boom as
    the solve checks hands, elbows and knees against them. The boom polyline is agent-05's posed clamp → elbow →
    arm tip → capsule, mirrored to -Y, turned by MIC_ROT about its clamp on the far edge (boom_points)."""
    pts = boom_points()
    a = lambda p: [round(p[0] - MARK[0], 2), round(p[1] - MARK[1], 2), round(p[2] - MARK[2], 2)]
    return {"desk_top": DESK_TOP, "desk_near": round(DESK_C[0] - 27.5 - MARK[0], 2),
            "desk_far": round(DESK_C[0] + 27.5 - MARK[0], 2), "desk_y": [round(DESK_C[1] - 55 - MARK[1], 2),
            round(DESK_C[1] + 55 - MARK[1], 2)], "desk_under": round(63.4 - (DESK_TOP_MESH - DESK_TOP), 2),
            "mic": a(pts["capsule"]), "boom": [a(pts[k]) for k in ("clamp", "elbow", "tip", "capsule")],
            "frame": "actor (studio minus the chair mark (20,-20,0)), cm; written by setplan.set_for_perf"}


def spec(who: str) -> dict:
    """Everything set.py builds, as one JSON-able dict (the hand-off to box A)."""
    return {"who": who, "mark": MARK, "yaw": YAW, "face": face(who), "mic": mic(who), "props": PROPS,
            "sign_drop": SIGN_DROP, "cameras": cameras(who), "lights": lights(who), "exposure_bias": EXPOSURE_BIAS}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", default="her", choices=sorted(FACE))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--perf-set", action="store_true", help="write set_<who>.json for agent-01's perform.py")
    a = ap.parse_args()
    if a.perf_set:
        out = Path(__file__).resolve().parent / f"set_{a.who}.json"
        out.write_text(json.dumps(set_for_perf(a.who), indent=1) + "\n")
        print(out.read_text())
        return 0
    if a.json:
        print(json.dumps(spec(a.who), indent=1))
        return 0
    bad = 0
    for rule, ok, detail in check(a.who):
        print(f"{'ok ' if ok else 'BAD'} {rule}: {detail}")
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
