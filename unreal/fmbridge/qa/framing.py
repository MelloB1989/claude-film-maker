"""Framing without looking: a pinhole model of an Unreal camera projects world points (bones, bounds corners) into
the frame, and the checks read the composition from where they land: is the subject in frame, how big (shot size),
headroom, a crop at a joint (knees, ankles, wrists, elbows), feet just cut off, look room, eyes on the upper third.

Unreal space: cm, X forward, Y right, Z up; a rotator is {"pitch", "yaw", "roll"} degrees. Frame space: (u, v) with
u right and v down, 0..1 across the image; depth is cm along the view axis (<= 0 is behind the camera).

The horizontal field of view is what Unreal keeps when the output aspect differs from the camera's (the default
"maintain X FOV"); a cine camera's FOV is 2*atan(sensor_width / (2 * focal_length)). Lens distortion and the
cine camera's crop settings are not modelled."""
from __future__ import annotations

import math

from .issues import issue

# a body, top to bottom: landmark -> the bones (UE5 mannequin / MetaHuman body skeleton) that locate it. The first
# found wins; "head_top" and "eyes" are derived from "head" when the caller does not give them.
LANDMARKS = {
    "head_top": ["head_top"], "eyes": ["eyes", "FACIAL_L_Eye", "FACIAL_R_Eye"], "chin": ["chin", "neck_02", "neck_01"],
    "neck": ["neck_01"], "chest": ["spine_05", "spine_04", "spine_03"], "waist": ["spine_01", "pelvis"],
    "hips": ["pelvis"], "knees": ["calf_l", "calf_r"], "ankles": ["foot_l", "foot_r"], "toes": ["ball_l", "ball_r"],
}
# joints where a frame edge should not cut (cinematography's "don't cut at a joint"), with the bones per side
JOINTS = {"knee": ["calf_l", "calf_r"], "ankle": ["foot_l", "foot_r"], "wrist": ["hand_l", "hand_r"],
          "elbow": ["lowerarm_l", "lowerarm_r"], "waist": ["pelvis"], "neck": ["neck_01"]}
# limbs as bone chains: a chain leaving the frame mid-joint is a cut limb
LIMBS = {"left arm": ["upperarm_l", "lowerarm_l", "hand_l"], "right arm": ["upperarm_r", "lowerarm_r", "hand_r"],
         "left leg": ["thigh_l", "calf_l", "foot_l"], "right leg": ["thigh_r", "calf_r", "foot_r"]}

# shot sizes by the lowest body landmark inside the frame (with the head in)
SHOT_SIZES = [  # (name, abbreviation, lowest landmark visible)
    ("extreme close-up", "ECU", None), ("close-up", "CU", "chin"), ("medium close-up", "MCU", "chest"),
    ("medium shot", "MS", "waist"), ("medium long shot", "MLS", "knees"), ("long shot", "LS", "toes"),
]
# headroom (frame top to head top, fraction of frame height) that reads right per shot size
HEADROOM = {"ECU": (-1.0, 0.0), "CU": (-0.06, 0.08), "MCU": (0.02, 0.12), "MS": (0.03, 0.15), "MLS": (0.04, 0.18),
            "LS": (0.04, 0.30), "ELS": (0.0, 1.0)}
HEAD_TOP_CM = 18.0   # head bone (skull base, MetaHuman) to the crown, along the head's up
EYES_CM = (9.0, 9.0)  # head bone to the eye line: (forward, up)
JOINT_EDGE = 0.03    # an edge within 3% of the frame of a joint is a crop at that joint


def _rad(d: float) -> float:
    return math.radians(float(d))


def axes(rot: dict) -> tuple:
    """Forward, right and up unit vectors of an Unreal rotator (FRotationMatrix's X, Y, Z axes)."""
    p, y, r = _rad(rot.get("pitch", 0)), _rad(rot.get("yaw", 0)), _rad(rot.get("roll", 0))
    sp, cp, sy, cy, sr, cr = math.sin(p), math.cos(p), math.sin(y), math.cos(y), math.sin(r), math.cos(r)
    fwd = (cp * cy, cp * sy, sp)
    right = (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp)
    up = (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
    return fwd, right, up


def look_at(src, dst) -> dict:
    """The rotator that points from src to dst (no roll)."""
    d = [b - a for a, b in zip(src, dst)]
    return {"pitch": math.degrees(math.atan2(d[2], math.hypot(d[0], d[1]))), "yaw": math.degrees(math.atan2(d[1], d[0])),
            "roll": 0.0}


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


class Camera:
    """A camera as framing sees it: location, rotation, horizontal FOV, output aspect (width / height)."""

    def __init__(self, loc, rot: dict, fov: float = 0.0, aspect: float = 16 / 9, focal: float = 0.0,
                 sensor_width: float = 0.0, name: str = ""):
        if not fov:
            if not (focal and sensor_width):
                raise ValueError("a camera needs fov (degrees, horizontal) or focal and sensor_width (mm)")
            fov = math.degrees(2 * math.atan(sensor_width / (2 * focal)))
        self.loc, self.rot, self.fov, self.aspect, self.name = [float(v) for v in loc], dict(rot), float(fov), float(aspect), name
        self.fwd, self.right, self.up = axes(self.rot)
        self.tx = math.tan(math.radians(self.fov) / 2)
        self.ty = self.tx / self.aspect

    @classmethod
    def from_dict(cls, d: dict) -> "Camera":
        """From what the qa ops report: {"loc", "rot", "fov" | "focal"+"sensor_width", "aspect", "name"}."""
        return cls(d["loc"], d.get("rot") or look_at(d["loc"], d["look_at"]), d.get("fov", 0.0), d.get("aspect", 16 / 9),
                   d.get("focal", 0.0), d.get("sensor_width", 0.0), d.get("name", ""))

    def to_dict(self) -> dict:
        return {"name": self.name, "loc": self.loc, "rot": self.rot, "fov": round(self.fov, 4), "aspect": self.aspect}

    def project(self, p) -> tuple:
        """World point -> (u, v, depth). u, v are only meaningful when depth > 0."""
        d = (p[0] - self.loc[0], p[1] - self.loc[1], p[2] - self.loc[2])
        x, y, z = _dot(d, self.fwd), _dot(d, self.right), _dot(d, self.up)
        if x <= 1e-6:
            return float("nan"), float("nan"), x
        return 0.5 + y / (x * 2 * self.tx), 0.5 - z / (x * 2 * self.ty), x

    def ray(self, u: float, v: float) -> tuple:
        """The world direction through frame point (u, v) (unit length)."""
        y = (u - 0.5) * 2 * self.tx
        z = (0.5 - v) * 2 * self.ty
        d = [self.fwd[k] + y * self.right[k] + z * self.up[k] for k in range(3)]
        n = math.sqrt(_dot(d, d))
        return tuple(c / n for c in d)

    def distance_for_height(self, height_cm: float, fill: float = 0.8) -> float:
        """How far away to stand for a subject `height_cm` tall to fill `fill` of the frame height."""
        return height_cm / (fill * 2 * self.ty)


def inside(u: float, v: float, depth: float, margin: float = 0.0) -> bool:
    return depth > 0 and -margin <= u <= 1 + margin and -margin <= v <= 1 + margin


def screen_box(cam: Camera, points) -> dict:
    """The frame-space box of world points (bounds corners, bones): {"box" clipped to the frame, "raw" unclipped,
    "in_frame" fraction of points inside, "behind" count, "area" fraction of the frame covered}."""
    pr = [cam.project(p) for p in points]
    front = [(u, v) for u, v, d in pr if d > 0]
    behind = len(pr) - len(front)
    if not front:
        return {"box": None, "raw": None, "in_frame": 0.0, "behind": behind, "area": 0.0}
    us, vs = [u for u, _ in front], [v for _, v in front]
    raw = [min(us), min(vs), max(us), max(vs)]
    box = [max(0.0, raw[0]), max(0.0, raw[1]), min(1.0, raw[2]), min(1.0, raw[3])]
    vis = sum(1 for u, v in front if 0 <= u <= 1 and 0 <= v <= 1)
    area = max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])
    return {"box": [round(x, 4) for x in box], "raw": [round(x, 4) for x in raw], "in_frame": round(vis / len(pr), 3),
            "behind": behind, "area": round(area, 4)}


def bounds_corners(origin, extent) -> list:
    """The 8 corners of an axis-aligned box (Unreal's get_actor_bounds: origin and half-size)."""
    return [[origin[0] + sx * extent[0], origin[1] + sy * extent[1], origin[2] + sz * extent[2]]
            for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]


def derive_landmarks(bones: dict, head_up=None, head_fwd=None) -> dict:
    """Body landmarks from bone positions: head_top and eyes from the head bone when not measured (the head's up
    and forward default to world up and the direction the body faces), every other landmark the mean of its bones."""
    out = {}
    for name, keys in LANDMARKS.items():
        found = [bones[k] for k in keys if k in bones]
        if found:
            out[name] = [sum(p[i] for p in found) / len(found) for i in range(3)]
    if "head" in bones:
        h = bones["head"]
        up = head_up or (0.0, 0.0, 1.0)
        fwd = head_fwd or _facing(bones) or (1.0, 0.0, 0.0)
        out.setdefault("head_top", [h[i] + HEAD_TOP_CM * up[i] for i in range(3)])
        out.setdefault("eyes", [h[i] + EYES_CM[0] * fwd[i] + EYES_CM[1] * up[i] for i in range(3)])
    return out


def _facing(bones: dict):
    """The horizontal direction a body faces, from its shoulders (or thighs): right-to-left crossed with up."""
    for l_, r_ in (("upperarm_l", "upperarm_r"), ("clavicle_l", "clavicle_r"), ("thigh_l", "thigh_r")):
        if l_ in bones and r_ in bones:
            lx, ly = bones[l_][0] - bones[r_][0], bones[l_][1] - bones[r_][1]
            n = math.hypot(lx, ly)
            if n > 1e-6:
                # Unreal is left-handed with Y right: a body facing +X has its left side at -Y, so facing = (-ly, lx)
                return (-ly / n, lx / n, 0.0)
    return None


def shot_size(cam: Camera, marks: dict) -> dict:
    """The shot size from which body landmarks are in frame (the head must be in, or it is an ECU or the subject is
    out of frame), and the subject's height in the frame."""
    seen = {k: inside(*cam.project(p)) for k, p in marks.items()}
    proj = {k: cam.project(p) for k, p in marks.items()}
    head_in = seen.get("eyes") or seen.get("head_top") or seen.get("chin")
    if not head_in:
        anything = any(seen.values())
        return {"size": "OUT" if not anything else "BODY", "name": "subject's head out of frame" if anything
                else "subject out of frame", "visible": [k for k, s in seen.items() if s]}
    size = ("ECU", "extreme close-up")
    for name, ab, lowest in SHOT_SIZES[1:]:
        if lowest in marks and seen.get(lowest):
            size = (ab, name)
    vs = [proj[k][1] for k in marks if proj[k][2] > 0]
    tall = (max(vs) - min(vs)) if vs else 0.0
    if size[0] == "LS" and tall < 0.33:
        size = ("ELS", "extreme long shot")
    return {"size": size[0], "name": size[1], "subject_height": round(tall, 3), "visible": [k for k, s in seen.items() if s]}


def check(cam: Camera, subject: str, bones: dict | None = None, bounds=None, facing=None, frame=None,
          expect: dict | None = None) -> dict:
    """Frame one subject. `bones` {bone name: [x, y, z]} (a character), or `bounds` (origin, extent) for anything
    else. `facing` [x, y, z] the way the subject looks (defaults from the shoulders). `expect` states intent:
    {"size": "MCU"} (or a list), {"headroom": [lo, hi]}, {"side": "left"|"right"|"center"}, {"in_frame": 1.0}.

    Returns {"subject", "size", "box", "headroom", "eyes_v", "look_room", "issues"}."""
    expect = expect or {}
    issues = []
    out = {"subject": subject, "camera": cam.name}
    where = {"subject": subject, "camera": cam.name or None, "frame": frame}
    pts = list((bones or {}).values())
    if bounds is not None:
        pts += bounds_corners(*bounds)
    if not pts:
        raise ValueError(f"framing {subject}: give bones or bounds")
    sb = screen_box(cam, pts)
    out["box"], out["in_frame"] = sb["box"], sb["in_frame"]
    if sb["box"] is None or sb["in_frame"] == 0 and _off(sb["raw"]):
        issues.append(issue("framing.out_of_frame", "fail", f"{subject} is not in {cam.name or 'the'} frame"
                            + (" (behind the camera)" if sb["behind"] == len(pts) else ""),
                            "aim the camera at it (level.move look_at=... or seq.key_transform)", **where))
        out["issues"] = issues
        return out
    if not bones:
        need = expect.get("in_frame", 1.0)
        if sb["in_frame"] < need:
            sides = _cut_sides(sb["raw"])
            issues.append(issue("framing.cut", "warn", f"{subject} is cut by the frame's {', '.join(sides)} edge "
                                f"({100 * sb['in_frame']:.0f}% of its bounds inside)", "widen (shorter focal length), "
                                "step back, or reframe", box=sb["box"], value=sb["in_frame"], **where))
        out["issues"] = issues
        return out
    marks = derive_landmarks(bones, head_fwd=facing)
    ss = shot_size(cam, marks)
    out["size"] = ss
    if ss["size"] in ("OUT", "BODY"):
        issues.append(issue("framing.head_out", "fail", f"{subject}'s head is out of frame ({ss['name']})",
                            "tilt up or reframe", box=sb["box"], **where))
        out["issues"] = issues
        return out
    want = expect.get("size")
    if want:
        wants = [want] if isinstance(want, str) else list(want)
        if ss["size"] not in wants:
            issues.append(issue("framing.size", "warn", f"{subject} is framed as a {ss['name']} ({ss['size']}), "
                                f"expected {'/'.join(wants)}", _size_fix(ss["size"], wants[0]),
                                value=ss["size"], expected=wants, **where))
    # headroom: frame top to the crown
    if "head_top" in marks:
        u, v, _ = cam.project(marks["head_top"])
        head = round(v, 4)
        out["headroom"] = head
        lo, hi = expect.get("headroom", HEADROOM.get(ss["size"], (0.0, 0.2)))
        if head < lo:
            issues.append(issue("framing.headroom_low", "warn" if head > -0.08 else "fail",
                                f"{subject}'s head is cut: crown at {100 * head:.0f}% of frame height (want {100 * lo:.0f}.."
                                f"{100 * hi:.0f}% for a {ss['size']})", "tilt up / raise the camera, or go tighter "
                                "on purpose (a choker CU)", box=[max(0, u - 0.08), 0, min(1, u + 0.08), 0.06],
                                value=head, expected=[lo, hi], **where))
        elif head > hi:
            issues.append(issue("framing.headroom_high", "warn", f"too much headroom over {subject}: crown "
                                f"{100 * head:.0f}% down (want {100 * lo:.0f}..{100 * hi:.0f}% for a {ss['size']})",
                                "tilt down or lower the camera so the eyes sit near the upper third",
                                box=[0, 0, 1, max(0.02, head)], value=head, expected=[lo, hi], **where))
    if "eyes" in marks:
        u, v, d = cam.project(marks["eyes"])
        if d > 0:
            out["eyes"] = [round(u, 4), round(v, 4)]
            if ss["size"] in ("CU", "MCU", "MS") and not (0.2 <= v <= 0.45):
                issues.append(issue("framing.eyeline", "info", f"{subject}'s eyes sit {100 * v:.0f}% down the frame; "
                                    "the upper third (~33%) reads best for a " + ss["size"],
                                    "tilt so the eyes land near the upper third line", value=round(v, 3),
                                    expected=[0.2, 0.45], **where))
    # joints on the frame edge
    for joint, names in JOINTS.items():
        for b in names:
            if b not in bones:
                continue
            u, v, d = cam.project(bones[b])
            if d <= 0:
                continue
            for edge, dist in (("bottom", abs(1 - v)), ("top", abs(v)), ("left", abs(u)), ("right", abs(1 - u))):
                along = u if edge in ("bottom", "top") else v
                if dist < JOINT_EDGE and -0.02 <= along <= 1.02:
                    if joint == "waist" and ss["size"] == "MS":
                        continue  # a medium shot is framed at the waist on purpose: cut a bit lower (hips) is fine
                    if joint == "neck":
                        continue
                    issues.append(issue("framing.joint_cut", "warn", f"the {edge} edge cuts {subject} at the {joint} "
                                        f"({b}, {100 * dist:.1f}% from the edge)", "reframe to cut between joints "
                                        "(mid-thigh, mid-shin, mid-forearm), not at one",
                                        box=_edge_box(edge, u, v), value=round(dist, 4), **where))
                    break
    # feet just cut off: everything down to the shins in, the feet out
    if all(k in marks for k in ("knees", "ankles")):
        kn, an = cam.project(marks["knees"]), cam.project(marks["ankles"])
        toes = cam.project(marks.get("toes", marks["ankles"]))
        if inside(*kn) and an[2] > 0 and (an[1] > 1.0 or toes[1] > 1.0) and an[1] < 1.12:
            issues.append(issue("framing.feet_cut", "warn", f"{subject}'s feet are just cut off by the bottom edge "
                                f"(ankles at {100 * an[1]:.0f}% of the frame height)", "widen or tilt down to include "
                                "the feet with a little floor, or go tighter (cut mid-thigh)",
                                box=[max(0, an[0] - 0.12), 0.9, min(1, an[0] + 0.12), 1.0], value=round(an[1], 3), **where))
    # limbs leaving the frame partway along (arm or leg cut across a segment near its joint is already reported)
    for limb, chain in LIMBS.items():
        ins = [inside(*cam.project(bones[b])) for b in chain if b in bones]
        if len(ins) == len(chain) and ins[0] and not ins[-1] and ss["size"] in ("MS", "MLS", "LS", "ELS"):
            if not ("leg" in limb and ss["size"] in ("MS",)):
                issues.append(issue("framing.limb_cut", "info", f"{subject}'s {limb} leaves the frame "
                                    f"({chain[-1]} outside)", "fine if intended; otherwise widen or reframe",
                                    subject_part=limb, **where))
    # side placement and look room
    eyes = out.get("eyes")
    fwd = facing or _facing(bones)
    if eyes and fwd:
        su = _screen_dir(cam, marks.get("eyes"), fwd)
        out["looks"] = "right" if su > 0.15 else "left" if su < -0.15 else "camera"
        if out["looks"] != "camera":
            room = (1 - eyes[0]) if out["looks"] == "right" else eyes[0]
            out["look_room"] = round(room, 3)
            if room < 0.4 and ss["size"] in ("CU", "MCU", "MS", "MLS"):
                issues.append(issue("framing.look_room", "warn", f"{subject} looks {out['looks']} with only "
                                    f"{100 * room:.0f}% of the frame in front of them", "move them to the opposite "
                                    "third so they look into the space (pan or truck the camera)",
                                    value=room, expected=[0.5, 0.75], **where))
    side = expect.get("side")
    if side and eyes:
        cu = eyes[0]
        got = "left" if cu < 0.42 else "right" if cu > 0.58 else "center"
        if got != side:
            issues.append(issue("framing.side", "warn", f"{subject} is frame {got} (u {cu:.2f}), expected {side}",
                                "pan or truck the camera", value=cu, expected=side, **where))
    out["issues"] = issues
    return out


def _screen_dir(cam: Camera, at, fwd) -> float:
    """Which way a world direction points on screen at a world point: + right, - left (the u change over 30 cm)."""
    a = cam.project(at)
    b = cam.project([at[i] + 30 * fwd[i] for i in range(3)])
    if a[2] <= 0 or b[2] <= 0:
        return 0.0
    return (b[0] - a[0]) / max(1e-6, abs(b[0] - a[0]) + abs(b[1] - a[1]) + 1e-3) * min(1.0, abs(b[0] - a[0]) * 20)


def _edge_box(edge: str, u: float, v: float) -> list:
    if edge == "bottom":
        return [max(0, u - 0.08), 0.94, min(1, u + 0.08), 1.0]
    if edge == "top":
        return [max(0, u - 0.08), 0.0, min(1, u + 0.08), 0.06]
    if edge == "left":
        return [0.0, max(0, v - 0.08), 0.06, min(1, v + 0.08)]
    return [0.94, max(0, v - 0.08), 1.0, min(1, v + 0.08)]


def _off(raw) -> bool:
    return raw is None or raw[2] < 0 or raw[0] > 1 or raw[3] < 0 or raw[1] > 1


def _cut_sides(raw) -> list:
    out = []
    if raw[0] < 0:
        out.append("left")
    if raw[2] > 1:
        out.append("right")
    if raw[1] < 0:
        out.append("top")
    if raw[3] > 1:
        out.append("bottom")
    return out or ["?"]


_ORDER = ["ECU", "CU", "MCU", "MS", "MLS", "LS", "ELS"]


def _size_fix(got: str, want: str) -> str:
    if got in _ORDER and want in _ORDER:
        if _ORDER.index(got) < _ORDER.index(want):
            return "widen: a shorter focal length or move the camera back"
        return "tighten: a longer focal length or move the camera in"
    return "reframe"


def suggest(cam: Camera, bones: dict, size: str = "MS", facing=None) -> dict:
    """Where to put the camera (same direction and lens) for a shot size: the distance along the view axis that
    frames the subject from the crown to the size's lowest landmark with the size's headroom, and the aim point.
    Returns {"loc", "look_at", "distance"} to feed look.camera / level.move."""
    marks = derive_landmarks(bones, head_fwd=facing)
    lowest = {s[1]: s[2] for s in SHOT_SIZES}.get(size, "waist") or "eyes"
    if "head_top" not in marks or lowest not in marks:
        raise ValueError(f"suggest {size}: need the head and {lowest} landmarks (bones {sorted(bones)[:8]}...)")
    lo, hi = HEADROOM.get(size, (0.05, 0.15))
    room = (lo + hi) / 2
    top, bottom = marks["head_top"][2], marks[lowest][2]
    span = (top - bottom) / max(0.05, 1 - room - 0.08)  # the landmark sits 8% above the bottom edge (a cut between joints)
    dist = span / (2 * cam.ty)
    centre_z = top + room * span - span / 2
    mid = [(marks["head_top"][0] + marks[lowest][0]) / 2, (marks["head_top"][1] + marks[lowest][1]) / 2, centre_z]
    loc = [mid[i] - cam.fwd[i] * dist for i in range(3)]
    return {"loc": [round(x, 2) for x in loc], "look_at": [round(x, 2) for x in mid], "distance": round(dist, 2)}
