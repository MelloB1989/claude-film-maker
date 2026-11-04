"""Camera grammar checks from geometry alone (no pixels): what a script supervisor and a focus puller look at.

The split with QA (WP10): per-frame subject framing (headroom, cut-offs at joints, feet and limbs, shot size, look
room, eye line) is fmbridge.qa.framing's; here are the checks of a camera's optics and of the cut between cameras:

- `frame`: focus (the subject's eyes inside the depth of field), safe areas (the face inside action safe), an
  accidental dutch, another subject standing in front.
- `cut`: the 180-degree line between two subjects, the 30-degree rule and the size step (a jump cut).

Issues have QA's shape: {"code", "severity": "fail" | "warn" | "info", "message", "fix", "camera", "subject",
"value", "expected"}. `fail` is a broken shot (a crossed line, an unsharp face), `warn` a choice to confirm.
"""
from __future__ import annotations

from . import framing, geo, lens

ACTION_SAFE = 0.93  # fraction of the frame, centred
TITLE_SAFE = 0.90


def issue(code: str, severity: str, message: str, fix: str = "", camera: str = "", subject: str = "", value=None,
          expected=None, frame: int | None = None) -> dict:
    return {"code": code, "severity": severity, "message": message, "fix": fix, "frame": frame, "camera": camera,
            "subject": subject, "value": value, "expected": expected}


def frame(cam: dict, subjects, others=None, camera: str = "", at: int | None = None) -> list:
    """Optics checks of one camera on its subjects (the first is the one in focus); `others` should not block."""
    subs = subjects if isinstance(subjects, (list, tuple)) else [subjects]
    out = []
    for k, s in enumerate(subs):
        n = s["name"]
        eye = lens.project(cam, s["points"]["eyes"])
        if eye["depth"] <= 0 or not eye["visible"]:
            continue  # out of frame: QA's out_of_frame says so
        m = (1 - ACTION_SAFE) / 2
        if not (m <= eye["u"] <= 1 - m and m <= eye["v"] <= 1 - m):
            out.append(issue("cam.safe_area", "warn", f"{n}'s eyes are outside action safe ({ACTION_SAFE:.0%}) at "
                             f"u={eye['u']:.2f} v={eye['v']:.2f}", "pan or tilt the face inward", camera, n,
                             [round(eye["u"], 3), round(eye["v"], 3)], [m, 1 - m], at))
        if cam.get("focus") and cam.get("aperture"):
            d = lens.dof(cam["focal"], cam["aperture"], cam["focus"], cam.get("filmback"))
            depth = eye["depth"]
            sharp = d["near"] <= depth and (d["far"] is None or depth <= d["far"])
            if not sharp:
                far = "inf" if d["far"] is None else f"{d['far']:.0f}"
                out.append(issue("cam.focus", "fail" if k == 0 else "info",
                                 f"{n}'s eyes at {depth:.0f} cm are outside the sharp zone {d['near']:.0f}-{far} cm "
                                 f"(focus {cam['focus']:.0f} cm, f/{cam['aperture']:g})",
                                 "camera.focus on the subject's eyes, or stop down (camera.lens aperture=...)",
                                 camera, n, round(depth, 1), [round(d["near"], 1), d["far"] and round(d["far"], 1)], at))
    roll = abs(geo.wrap180(cam["rot"].get("roll", 0.0)))
    if 0.3 < roll < 4.0:
        out.append(issue("cam.horizon", "warn", f"roll {roll:.1f} deg: a dutch this small reads as a mistake",
                         "roll 0, or 5+ deg for a deliberate dutch", camera, "", round(roll, 2), 0.0, at))
    for o in others or []:
        for s in subs:
            if o is not s and _blocks(cam, o, s):
                out.append(issue("cam.occlusion", "warn", f"{o['name']} stands between the camera and {s['name']}'s face",
                                 "move the camera around (angle) or raise it", camera, s["name"], o["name"], None, at))
    return out


def _blocks(cam: dict, blocker: dict, s: dict, radius: float = 22.0) -> bool:
    """Whether `blocker`'s body (a vertical capsule from feet to head top, `radius` cm) crosses the line from the
    lens to `s`'s eyes."""
    a, b = geo.v(cam["loc"]), geo.v(s["points"]["eyes"])
    feet, top = geo.v(blocker["points"]["feet"]), geo.v(blocker["points"]["head_top"])
    for i in range(1, 60):
        p = geo.lerp(a, b, i / 60.0)
        if feet[2] <= p[2] <= top[2] and ((p[0] - feet[0]) ** 2 + (p[1] - feet[1]) ** 2) ** 0.5 < radius:
            return True
    return False


def side_of_line(cam_loc, a, b) -> float:
    """Which side of the line a -> b (seen from above) a camera stands: + one side, - the other, 0 on it."""
    a, b, c = geo.v(a), geo.v(b), geo.v(cam_loc)
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def cut(cam_a: dict, cam_b: dict, subjects, size_a: str | None = None, size_b: str | None = None,
        names=("A", "B"), at: int | None = None) -> list:
    """Check a cut from camera A to camera B on one scene: the 180-degree line (between the first two subjects), and
    on the first subject the 30-degree rule with the size step. `size_*` are the intended sizes (else classified)."""
    subs = subjects if isinstance(subjects, (list, tuple)) else [subjects]
    out = []
    label = f"{names[0]} -> {names[1]}"
    if len(subs) >= 2:
        a, b = subs[0]["points"]["eyes"], subs[1]["points"]["eyes"]
        sa, sb = side_of_line(cam_a["loc"], a, b), side_of_line(cam_b["loc"], a, b)
        if sa * sb < 0:
            out.append(issue("shot.line_180", "fail", f"the cut {label} crosses the line between {subs[0]['name']} and "
                             f"{subs[1]['name']}: their screen directions flip",
                             "keep both cameras on one side (camera.coverage side=...), or cut through a neutral "
                             "shot on the line", label, subs[0]["name"], None, None, at))
    s = subs[0]
    e = geo.v(s["points"]["eyes"])
    ang = geo.angle_between(geo.sub(geo.v(cam_a["loc"]), e), geo.sub(geo.v(cam_b["loc"]), e))
    ka = framing.size_key(size_a) if size_a else framing.classify(cam_a, s)["size"]
    kb = framing.size_key(size_b) if size_b else framing.classify(cam_b, s)["size"]
    step = abs(framing.ORDER.index(ka) - framing.ORDER.index(kb)) if ka and kb else 0
    if ang < 30.0 and step < 2:
        out.append(issue("shot.rule_30", "warn", f"a jump cut on {s['name']} ({label}): {ang:.0f} deg apart, {ka} -> {kb}",
                         "move the camera 30+ deg around the subject or change the size by two steps (MS -> CU)",
                         label, s["name"], round(ang, 1), 30.0, at))
    return out


def worst(issues: list) -> str:
    sev = {i["severity"] for i in issues}
    return "fail" if "fail" in sev else "warn" if "warn" in sev else "pass"


def summary(issues: list) -> str:
    """One line per warn/fail: what Claude reads first."""
    return "\n".join(f"{i['severity'].upper()} {i['code']}: {i['message']}" for i in issues
                     if i["severity"] != "info") or "all checks pass"
