"""Subjects, shot sizes and the framing solver.

A subject is what the solver frames: {"name", "points": {landmark: [x, y, z]}, "facing": [x, y, 0]} with the
landmarks below in world cm. `subject_from_bones` builds one from a skeleton's bone positions (UE5 mannequin and
MetaHuman names), `subject_from_bounds` from an actor's bounding box with standard human proportions, and any
object (a prop, a car) can be framed from its bounds with `subject_from_box`.

A shot size says where the frame's top and bottom edges fall on the body: each size has a top anchor and a bottom
anchor, a landmark (or a point between two) and the frame height (v, 0 top .. 1 bottom) it lands on. The bottom
edges are put between joints, never on one (a frame cut at the knee, the waist or the neck reads as an amputation).

The solver (`solve`) places a camera around a pivot (the subject's eyes) at an angle (front, 3/4, profile...) on a
side (the subject's left or right), at a height (eye level, high, low, overhead, a fixed height), with a fixed focal
length (distance solved) or a fixed distance (focal length solved), so that the anchors land where the size wants
them and the subject sits where the composition wants it (centre, thirds with lead room). It solves the three
unknowns (distance or focal, pan, tilt) by Newton's method on the real projection, so a dutch angle, a high angle
and a group of subjects are framed as exactly as a frontal single.
"""
from __future__ import annotations

import math

from . import geo, lens

LANDMARKS = ("head_top", "eyes", "nose", "mouth", "chin", "neck", "shoulders", "chest", "waist", "hips", "knees",
             "ankles", "feet")

# fractions of standing height above the soles: an 8-heads figure (crown 1, chin 7/8, nipples 6/8, navel 5/8,
# crotch 4/8, knees ~2/8), eyes about halfway down the head
PROPORTIONS = {"head_top": 1.0, "eyes": 0.935, "nose": 0.91, "mouth": 0.893, "chin": 0.87, "neck": 0.845,
               "shoulders": 0.815, "chest": 0.72, "waist": 0.62, "hips": 0.53, "knees": 0.285, "ankles": 0.04,
               "feet": 0.0}

# skeleton bones per landmark, first found wins (UE5 mannequin and MetaHuman body; MetaHuman face for the eyes)
BONES = {
    "eye_l": ("FACIAL_L_Eye", "FACIAL_L_EyeParallel", "eye_l", "LeftEye"),
    "eye_r": ("FACIAL_R_Eye", "FACIAL_R_EyeParallel", "eye_r", "RightEye"),
    "head": ("head", "Head"),
    "neck": ("neck_02", "neck_01", "neck", "Neck"),
    "clavicle_l": ("clavicle_l", "LeftShoulder"),
    "clavicle_r": ("clavicle_r", "RightShoulder"),
    "upperarm_l": ("upperarm_l", "LeftArm"),
    "upperarm_r": ("upperarm_r", "RightArm"),
    "chest": ("spine_04", "spine_05", "spine_03", "Spine2", "chest"),
    "waist": ("spine_01", "Spine", "spine"),
    "hips": ("pelvis", "Hips", "hips"),
    "knee_l": ("calf_l", "LeftLeg"),
    "knee_r": ("calf_r", "RightLeg"),
    "ankle_l": ("foot_l", "LeftFoot"),
    "ankle_r": ("foot_r", "RightFoot"),
    "ball_l": ("ball_l", "LeftToeBase"),
    "ball_r": ("ball_r", "RightToeBase"),
}
CROWN_ABOVE_EYES = 11.5  # cm from the eye line to the top of an adult head (hair adds; pass top_z when it is big)
ALL_BONES = tuple(dict.fromkeys(b for names in BONES.values() for b in names))

# shot sizes: (top anchor, v), (bottom anchor, v); an anchor is a landmark or (landmark, landmark, t) between them
SIZES = {
    "EWS": {"top": ("head_top", 0.40), "bottom": ("feet", 0.62), "name": "extreme wide shot",
            "desc": "the figure small in its world (about a fifth of the frame height)"},
    "WS": {"top": ("head_top", 0.10), "bottom": ("feet", 0.92), "name": "wide shot (full shot)",
           "desc": "head to feet with a little floor"},
    "MWS": {"top": ("head_top", 0.08), "bottom": (("knees", "ankles", 0.3), 1.0), "name": "medium wide shot",
            "desc": "knees up, cut below the knee"},
    "COWBOY": {"top": ("head_top", 0.08), "bottom": (("hips", "knees", 0.45), 1.0), "name": "cowboy shot",
               "desc": "mid-thigh up"},
    "MS": {"top": ("head_top", 0.08), "bottom": (("waist", "hips", 0.6), 1.0), "name": "medium shot",
           "desc": "waist up, cut below the belt"},
    "MCU": {"top": ("head_top", 0.07), "bottom": (("chest", "waist", 0.3), 1.0), "name": "medium close-up",
            "desc": "chest up, cut mid-chest"},
    "CU": {"top": ("head_top", 0.05), "bottom": (("chin", "chest", 0.55), 1.0), "name": "close-up",
           "desc": "the head and the top of the shoulders"},
    "ECU": {"top": (("eyes", "head_top", 0.4), 0.0), "bottom": (("chin", "neck", 0.2), 1.0),
            "name": "extreme close-up", "desc": "forehead to chin, the top of the head cropped"},
}
ALIASES = {"FS": "WS", "LS": "WS", "FULL": "WS", "WIDE": "WS", "LONG": "WS", "ELS": "EWS", "XWS": "EWS",
           "MLS": "MWS", "MEDIUMWIDE": "MWS", "MEDIUM": "MS", "MCS": "MCU", "CLOSE": "CU", "CLOSEUP": "CU",
           "XCU": "ECU", "BCU": "ECU", "CHOKER": "ECU", "AMERICAN": "COWBOY", "MFS": "MWS"}
ORDER = ("ECU", "CU", "MCU", "MS", "COWBOY", "MWS", "WS", "EWS")  # tight to wide

ANGLES = {"front": 0.0, "frontal": 0.0, "quarter": 22.5, "1/4": 22.5, "3/4": 45.0, "three-quarter": 45.0,
          "threequarter": 45.0, "profile": 90.0, "side": 90.0, "3/4 back": 135.0, "back3/4": 135.0,
          "three-quarter back": 135.0, "back": 180.0, "rear": 180.0}

# camera height: an elevation in degrees seen from the pivot (eyes), or a landmark the lens sits at
HEIGHTS = {"eye": 0.0, "eye level": 0.0, "level": 0.0, "high": 20.0, "low": -20.0, "overhead": 75.0,
           "bird": 75.0, "birds eye": 75.0, "top": 89.0, "worm": -45.0, "worms eye": -45.0, "slight high": 10.0,
           "slight low": -10.0}
HEIGHT_AT = {"shoulder": "shoulders", "chest": "chest", "hip": "hips", "waist": "waist", "knee": "knees",
             "ground": "feet"}


def size_key(size: str) -> str:
    k = str(size).upper().replace(" ", "").replace("-", "").replace("_", "")
    k = ALIASES.get(k, k)
    if k not in SIZES:
        raise ValueError(f"unknown shot size {size!r}; one of {', '.join(ORDER)} (aliases: "
                         f"{', '.join(sorted(ALIASES))})")
    return k


def angle_deg(angle) -> float:
    if isinstance(angle, (int, float)):
        return float(angle)
    k = str(angle).lower().strip().replace("_", " ")
    if k in ANGLES:
        return ANGLES[k]
    k2 = k.replace(" ", "")
    for name, a in ANGLES.items():
        if name.replace(" ", "") == k2:
            return a
    raise ValueError(f"unknown angle {angle!r}; degrees or one of {', '.join(sorted(set(ANGLES)))}")


# --- subjects ---------------------------------------------------------------------------------------------------

def _first(bones: dict, key: str):
    for n in BONES[key]:
        if n in bones and bones[n] is not None:
            return geo.v(bones[n])
    return None


def _mid(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return geo.lerp(a, b, 0.5)


def subject_from_bones(name: str, bones: dict, ground_z: float | None = None, top_z: float | None = None,
                       facing=None) -> dict:
    """A subject from world bone positions {bone: [x, y, z]} (any of BONES' names). `ground_z` is the floor under
    the feet (else the lowest foot bone less 8 cm), `top_z` the crown (else estimated from the eyes and the head).
    `facing` [x, y, z] overrides the facing worked out from the eyes or the shoulders."""
    g = {k: _first(bones, k) for k in BONES}
    eyes = _mid(g["eye_l"], g["eye_r"])
    head, neck = g["head"], g["neck"]
    hips = g["hips"]
    if head is None or hips is None:
        raise ValueError(f"{name}: no head/pelvis bones among {sorted(bones)[:12]}...; frame it from its bounds "
                         "(camera.landmarks with mode='bounds')")
    if eyes is None:  # no face rig: the eyes sit ~9 cm above the head joint (UE5 mannequin)
        eyes = geo.add(head, (0.0, 0.0, 9.0))
    ankles = _mid(g["ankle_l"], g["ankle_r"])
    balls = _mid(g["ball_l"], g["ball_r"])
    if ground_z is None:
        lows = [p[2] for p in (ankles, balls) if p is not None]
        if lows:
            ground_z = min(lows) - 8.0
        else:  # the pelvis at 0.53 and the eyes at 0.935 of standing height
            tall = (eyes[2] - hips[2]) / (PROPORTIONS["eyes"] - PROPORTIONS["hips"])
            ground_z = hips[2] - PROPORTIONS["hips"] * tall
    feet = (hips[0], hips[1], ground_z) if ankles is None else (ankles[0], ankles[1], ground_z)
    if top_z is None:
        top_z = eyes[2] + CROWN_ABOVE_EYES
    head_top = (eyes[0], eyes[1], top_z)
    shoulders = _mid(_mid(g["clavicle_l"], g["clavicle_r"]), _mid(g["upperarm_l"], g["upperarm_r"])) \
        or (neck if neck is not None else geo.lerp(head, hips, 0.25))
    chin = (eyes[0], eyes[1], eyes[2] - 12.0) if neck is None else geo.lerp(eyes, neck, 0.7)
    chest = g["chest"] or geo.lerp(shoulders, hips, 0.35)
    waist = g["waist"] or geo.lerp(chest, hips, 0.55)
    knees = _mid(g["knee_l"], g["knee_r"]) or geo.lerp(hips, feet, 0.5)
    if ankles is None:
        ankles = geo.lerp(knees, feet, 0.85)
    pts = {"head_top": head_top, "eyes": eyes, "nose": geo.lerp(eyes, chin, 0.45), "mouth": geo.lerp(eyes, chin, 0.7),
           "chin": chin, "neck": neck or geo.lerp(chin, shoulders, 0.5), "shoulders": shoulders, "chest": chest,
           "waist": waist, "hips": hips, "knees": knees, "ankles": ankles, "feet": feet}
    if facing is None:
        facing = facing_from(g["eye_l"], g["eye_r"]) or facing_from(g["clavicle_l"], g["clavicle_r"]) or \
            facing_from(g["upperarm_l"], g["upperarm_r"])
    if facing is None:
        raise ValueError(f"{name}: cannot tell which way it faces (no eye or shoulder bones); pass facing")
    return make_subject(name, pts, facing)


def facing_from(left, right):
    """The horizontal direction a figure faces from its left and right (eyes, shoulders): Unreal is left-handed with
    Y right of X, so the figure's right side lies at yaw(facing) + 90."""
    if left is None or right is None:
        return None
    r = geo.sub(right, left)
    r = (r[0], r[1], 0.0)
    if geo.length(r) < 1e-3:
        return None
    return geo.from_yaw(geo.yaw_of(r) - 90.0)


def subject_from_bounds(name: str, origin, extent, facing, scale: float = 1.0) -> dict:
    """A standing figure from its bounding box (origin, half-extent), with standard proportions."""
    o, e = geo.v(origin), geo.v(extent)
    bottom, top = o[2] - e[2], o[2] + e[2]
    h = (top - bottom) * scale
    pts = {k: (o[0], o[1], bottom + f * h) for k, f in PROPORTIONS.items()}
    return make_subject(name, pts, facing)


def subject_from_box(name: str, origin, extent, facing=(1.0, 0.0, 0.0)) -> dict:
    """Any object from its bounds: the top and bottom faces stand for head_top and feet, the middle for the eyes
    (a prop, a car, a building). Shot sizes that cut the body (MCU, CU) then cut the box proportionally."""
    return subject_from_bounds(name, origin, extent, facing)


def make_subject(name: str, points: dict, facing) -> dict:
    f = geo.v(facing)
    f = geo.norm((f[0], f[1], 0.0))
    missing = [k for k in LANDMARKS if k not in points]
    if missing:
        raise ValueError(f"{name}: landmarks missing {missing}")
    return {"name": name, "points": {k: list(geo.v(p)) for k, p in points.items()}, "facing": list(f),
            "height": points["head_top"][2] - points["feet"][2]}


def anchor_point(subject: dict, anchor) -> tuple:
    """A shot size's anchor on a subject: a landmark name, or (a, b, t) between two."""
    pts = subject["points"]
    if isinstance(anchor, str):
        if anchor not in pts:
            raise ValueError(f"no landmark {anchor!r} on {subject['name']}; one of {sorted(pts)}")
        return geo.v(pts[anchor])
    a, b, t = anchor
    return geo.lerp(geo.v(pts[a]), geo.v(pts[b]), float(t))


# --- the solver -------------------------------------------------------------------------------------------------

def _lin(J, r):
    """x with J x = r by Gaussian elimination with partial pivoting; None when singular."""
    n = len(r)
    m = [list(J[i]) + [r[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda i: abs(m[i][c]))
        if abs(m[p][c]) < 1e-12:
            return None
        m[c], m[p] = m[p], m[c]
        for i in range(c + 1, n):
            k = m[i][c] / m[c][c]
            for j in range(c, n + 1):
                m[i][j] -= k * m[c][j]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


def _newton(fn, x, iters: int = 80, tol: float = 1e-7):
    """Damped Newton on fn(x) -> residuals (None = invalid: the subject went behind the lens) with a numeric
    Jacobian; x[0] is a log (distance or focal), the last two are angles."""
    x = list(x)
    for _ in range(iters):
        r = fn(x)
        if r is None:
            x[0] += 0.3  # behind the lens: back off (a longer distance or a longer lens)
            continue
        if max(abs(e) for e in r) < tol:
            break
        J = [[0.0] * len(x) for _ in r]
        for j in range(len(x)):
            xs = list(x)
            xs[j] += 1e-5
            r2 = fn(xs)
            if r2 is None:
                return x
            for i in range(len(r)):
                J[i][j] = (r2[i] - r[i]) / 1e-5
        step = _lin(J, r)
        if step is None:
            break
        n = len(x)
        # damp: at most 0.5 in log units and 15 degrees in angle per step
        s = min([1.0] + [(0.5 if j < n - 2 else 15.0) / abs(step[j]) for j in range(n) if step[j]])
        x = [x[j] - step[j] * s for j in range(n)]
    return x


def _side_sign(side: str) -> float:
    s = str(side or "left").lower()
    if s in ("left", "l", "subject-left", "subject_left"):
        return 1.0
    if s in ("right", "r", "subject-right", "subject_right"):
        return -1.0
    raise ValueError(f"side {side!r}: 'left' or 'right' (the subject's own left or right)")


def camera_direction(facing, angle, side: str = "left", elevation: float = 0.0) -> tuple:
    """The unit direction from a subject to the camera: `angle` degrees around from its front (0 front, 45 3/4, 90
    profile, 180 behind) toward the subject's own `side`, raised `elevation` degrees."""
    a = angle_deg(angle) * _side_sign(side)
    # the subject's left is at yaw(facing) - 90 (Y is right of X): positive angles turn toward it
    return geo.from_yaw(geo.yaw_of(facing) - a, elevation)


def group_facing(subs: list, side: str = "left") -> tuple:
    """Which way a group "faces" for framing: square to the line through the first two subjects' eyes, on the side
    their facings lean to (people side by side facing the room); when they face each other (a conversation) the
    facings cancel and `side` picks: "left" of the line from the first to the second, seen from above."""
    a, b = geo.v(subs[0]["points"]["eyes"]), geo.v(subs[1]["points"]["eyes"])
    ab = geo.sub(b, a)
    if math.hypot(ab[0], ab[1]) < 1e-3:
        return geo.v(subs[0]["facing"])
    perp = geo.norm((-ab[1], ab[0], 0.0))  # +90 deg yaw from a->b: the line's right seen from above (Y right of X)
    mean = [sum(geo.v(s["facing"])[k] for s in subs) / len(subs) for k in range(3)]
    lean = geo.dot(mean, perp)
    if abs(lean) > 0.3:
        return perp if lean > 0 else geo.mul(perp, -1.0)
    # left of the line a->b (seen from above, X up, Y right) is -perp
    return geo.mul(perp, -1.0) if _side_sign(side) > 0 else perp


def solve(subjects, size: str = "MCU", angle=0.0, side: str = "left", height="eye", focal: float | None = 50.0,
          distance: float | None = None, place="auto", headroom: float | None = None, dutch: float = 0.0,
          filmback=None, aperture: float = 2.8, lead: float = 1.0 / 3.0, margin: float = 0.06,
          snap_focal: bool = False, pivot=None, look=None, ground_clearance: float = 10.0) -> dict:
    """Frame one or more subjects. Returns {"camera": camera dict, "distance", "focal", "warnings", "predicted",
    ...}.

    - `size`: ECU CU MCU MS COWBOY MWS WS EWS (or an alias); for a group, the frame spans the highest top anchor and
      the lowest bottom anchor, and widens until every subject fits between the side margins.
    - `angle` (degrees or "front", "3/4", "profile", "3/4 back", "back") toward the subject's own `side` (left or
      right), measured from the first subject's facing; for a group from the group's facing (`group_facing`:
      square to the line between the first two, toward where they face, or on `side` of it when they face each
      other).
    - `height`: "eye" (level), "high", "low", "slight high", "overhead", "worm" (elevations seen from the eyes), a
      number of degrees, a landmark the lens sits at ("shoulder", "chest", "hip", "knee", "ground"), or
      {"z": cm} for an absolute height.
    - `focal` mm with `distance` None: the distance is solved. `distance` cm (horizontal, eyes to lens) with
      `focal` None: the focal length is solved (`snap_focal` rounds it to a standard prime and re-solves the
      distance). Both: the camera is placed and aimed, and the size is whatever results.
    - `place`: where the subject's eyes sit across the frame: "auto" (centre when frontal, else on the third that
      leaves lead room in front of the face), "center", "left third", "right third", or a u (0..1). `lead` is the
      third's position (1/3).
    - `headroom`: overrides the size's v of its top anchor (0.05..0.15 typical).
    - `dutch`: roll in degrees. `pivot` (a world point) and `look` (a facing) override the first subject's.
    """
    subs = subjects if isinstance(subjects, (list, tuple)) else [subjects]
    if not subs:
        raise ValueError("solve needs at least one subject")
    key = size_key(size)
    spec = SIZES[key]
    fb = lens.filmback(filmback)
    warnings: list = []
    first = subs[0]
    facing = geo.v(look) if look is not None else (group_facing(subs, side) if len(subs) > 1 else
                                                     geo.v(first["facing"]))
    eyes = [geo.v(s["points"]["eyes"]) for s in subs]
    piv = geo.v(pivot) if pivot is not None else geo.mul(
        (sum(p[0] for p in eyes), sum(p[1] for p in eyes), sum(p[2] for p in eyes)), 1.0 / len(eyes))
    tops = [anchor_point(s, spec["top"][0]) for s in subs]
    bottoms = [anchor_point(s, spec["bottom"][0]) for s in subs]
    vt = float(headroom) if headroom is not None else spec["top"][1]
    vb = spec["bottom"][1]
    if not vt < vb:
        raise ValueError(f"headroom {vt} must be above the bottom anchor's {vb}")

    # the camera position as a function of its distance d (horizontal, from the pivot)
    fixed_z = None
    elev = 0.0
    if isinstance(height, dict):
        fixed_z = float(height["z"])
    elif isinstance(height, (int, float)):
        elev = float(height)
    else:
        hk = str(height).lower().strip()
        if hk in HEIGHTS:
            elev = HEIGHTS[hk]
        elif hk in HEIGHT_AT or hk.rstrip("s") in HEIGHT_AT:
            lm = HEIGHT_AT.get(hk) or HEIGHT_AT[hk.rstrip("s")]
            fixed_z = first["points"][lm][2] + (ground_clearance if lm == "feet" else 0.0)
        else:
            raise ValueError(f"height {height!r}: a number of degrees, {{'z': cm}}, or one of "
                             f"{', '.join(list(HEIGHTS) + list(HEIGHT_AT))}")
    hdir = camera_direction(facing, angle, side, 0.0)
    ground = min(s["points"]["feet"][2] for s in subs)

    def cam_loc(d: float) -> tuple:
        if fixed_z is not None:
            return (piv[0] + hdir[0] * d, piv[1] + hdir[1] * d, fixed_z)
        return (piv[0] + hdir[0] * d, piv[1] + hdir[1] * d, piv[2] + d * math.tan(math.radians(elev)))

    # where the eyes go across the frame
    fixed_u = None
    pk = place if not isinstance(place, str) else place.lower().replace("_", " ").replace("-", " ").strip()
    if isinstance(pk, (int, float)):
        fixed_u = float(pk)
    elif pk in ("center", "centre", "middle"):
        fixed_u = 0.5
    elif pk in ("left third", "left"):
        fixed_u = lead
    elif pk in ("right third", "right"):
        fixed_u = 1.0 - lead
    elif pk not in ("auto", "thirds", "third"):
        raise ValueError(f"place {place!r}: auto, center, left third, right third, or a number 0..1")
    a_abs = abs(angle_deg(angle))

    def u_target(cam) -> float:
        if fixed_u is not None:
            return fixed_u
        if len(subs) > 1 or (a_abs < 20.0 and pk == "auto") or a_abs > 160.0:
            return 0.5
        # lead room: the face looks toward one side of the frame; put it on the other third
        p0 = lens.project(cam, piv)
        p1 = lens.project(cam, geo.add(piv, geo.mul(facing, 30.0)))
        if p0["depth"] <= 0 or p1["depth"] <= 0 or abs(p1["u"] - p0["u"]) < 1e-4:
            return 0.5
        return lead if p1["u"] > p0["u"] else 1.0 - lead

    solve_focal = distance is not None and focal is None
    both_fixed = distance is not None and focal is not None
    f = float(focal) if focal is not None else 35.0
    d = float(distance) if distance is not None else None
    if d is None:  # first guess: the span over the frame's share of it
        span = max(abs(t[2] - b[2]) for t, b in zip(tops, bottoms)) or 50.0
        d = span / (vb - vt) * f / fb[1]
    tilt0 = geo.look_at(cam_loc(d), piv)["pitch"]

    def build(x) -> dict:
        # x: [log distance | log focal (absent when both are fixed), pan offset, tilt]
        pan, tilt = x[-2], x[-1]
        dd = math.exp(x[0]) if not (solve_focal or both_fixed) else d
        ff = math.exp(x[0]) if solve_focal else f
        loc = cam_loc(dd)
        return lens.camera(loc, geo.rot(tilt, geo.yaw_of(geo.sub(piv, loc)) + pan, dutch), ff, fb, aperture)

    def measure(cam):
        pt = [lens.project(cam, p) for p in tops]
        pb = [lens.project(cam, p) for p in bottoms]
        pe = lens.project(cam, piv)
        if any(p["depth"] <= 0 for p in pt + pb + [pe]):
            return None
        return min(p["v"] for p in pt), max(p["v"] for p in pb), pe["u"]

    def residual(x, ut):
        cam = build(x)
        m = measure(cam)
        if m is None:
            return None
        if both_fixed:
            return [m[0] - vt, m[2] - ut]
        return [m[0] - vt, m[1] - vb, m[2] - ut]

    x = ([] if both_fixed else [math.log(f if solve_focal else d)]) + [0.0, tilt0]
    for outer in range(8):  # widen for groups until everyone fits across
        for _ in range(3):  # which third leaves lead room depends on the frame: solve, re-read, re-solve
            ut = u_target(build(x))
            x = _newton(lambda xx: residual(xx, ut), x)
            if abs(u_target(build(x)) - ut) < 1e-9:
                break
        if len(subs) == 1 or both_fixed:
            break
        cam = build(x)
        us = [lens.project(cam, s["points"][k])["u"] for s in subs for k in ("eyes", "shoulders", "hips", "head_top")]
        over, room = max(us) - min(us), 1.0 - 2 * margin
        if over <= room * 1.0001:
            break
        # too wide for the frame: shrink the vertical span the anchors take, around their middle
        mid = (vt + vb) / 2.0
        vt, vb = mid - (mid - vt) * room / over, mid + (vb - mid) * room / over
        if outer == 0:
            warnings.append(f"widened so all {len(subs)} subjects fit across the frame")
    state = x
    final_ut = u_target(build(x))

    cam = build(state)
    if snap_focal and solve_focal:
        snapped = lens.snap(cam["focal"])
        return solve(subs, key, angle, side, height, snapped, None, place, headroom, dutch, fb, aperture, lead,
                     margin, False, pivot, look, ground_clearance)
    dd = geo.dist((cam["loc"][0], cam["loc"][1], 0), (piv[0], piv[1], 0))
    if cam["loc"][2] < ground + ground_clearance:
        warnings.append(f"the lens is {ground - cam['loc'][2] + ground_clearance:.0f} cm below the floor clearance "
                        f"(z {cam['loc'][2]:.0f}, floor {ground:.0f}): raise the height or use a wider size")
    if cam["focal"] < 12 or cam["focal"] > 300:
        warnings.append(f"focal {cam['focal']:.0f} mm is extreme; fix the focal length and let the distance solve")
    near = min(lens.view(cam, p)[0] for s in subs for p in s["points"].values())
    if near < 30:
        warnings.append(f"the lens is {near:.0f} cm from the subject: inside its body or too close to focus")
    focus = lens.view(cam, eyes[0])[0]
    cam["focus"] = focus
    pred = {s["name"]: {k: _uv(lens.project(cam, p)) for k, p in s["points"].items()} for s in subs}
    res = residual(state, final_ut)
    return {"camera": cam, "size": key, "distance": round(dd, 2), "focal": round(cam["focal"], 3),
            "focus": round(focus, 2), "hfov": round(lens.hfov(cam["focal"], fb), 3), "pivot": list(piv),
            "angle": angle_deg(angle), "side": side, "height": height, "dutch": dutch,
            "error": None if res is None else round(max(abs(e) for e in res), 6),
            "dof": {k: (None if v is None else round(v, 1)) for k, v in
                    lens.dof(cam["focal"], aperture, focus, fb).items()},
            "predicted": pred, "warnings": warnings}


def _uv(p: dict) -> list:
    if not p["depth"] > 0:
        return [None, None]
    return [round(p["u"], 4), round(p["v"], 4)]


def classify(cam: dict, subject: dict) -> dict:
    """What size a camera's frame is on a subject: where the frame's bottom edge cuts the body, named as the nearest
    shot size, and the headroom (v of the head's top; negative = the head is cropped)."""
    pts = subject["points"]
    top = lens.project(cam, pts["head_top"])
    best, err = None, 9.0
    for k in ORDER:
        b = lens.project(cam, anchor_point(subject, SIZES[k]["bottom"][0]))
        t = lens.project(cam, anchor_point(subject, SIZES[k]["top"][0]))
        if b["depth"] <= 0:
            continue
        e = abs(b["v"] - SIZES[k]["bottom"][1]) + abs(t["v"] - SIZES[k]["top"][1])
        if e < err:
            best, err = k, e
    return {"size": best, "fit_error": round(err, 3), "headroom": round(top["v"], 4) if top["depth"] > 0 else None}
