"""Coverage: the set of shots an editor needs to cut a scene, all on one side of the line.

For one subject: a wide, a medium, a medium close-up and a close-up from a 3/4 angle, and a profile. For two or more
(a conversation): the line runs between the first two subjects' eyes; every camera stands on one side of it (`side`
"left" or "right" of the line seen from the first subject toward the second, as from above), so cutting between any
two keeps screen direction: a master two-shot square to the line, each subject's clean single (MCU and CU) from
just off the other's eyeline, and an over-the-shoulder each (from behind the other's shoulder, the lens solved for
the size at that distance). Every shot is a `framing.solve` result with its name and a recipe that re-creates it.
"""
from __future__ import annotations

import math

from . import checks, framing, geo, lens

SINGLE = ("WS", "MS", "MCU", "CU")


def _line_side(side: str) -> float:
    s = str(side).lower()
    if s in ("left", "l", "+"):
        return 1.0
    if s in ("right", "r", "-"):
        return -1.0
    raise ValueError(f"side {side!r}: 'left' or 'right' of the line from the first subject to the second")


def _subject_side_for(subject: dict, angle: float, want: float, a, b, **kw) -> str:
    """Which of the subject's own sides ("left"/"right") puts a camera at `angle` on the wanted side of the line."""
    for s in ("left", "right"):
        d = framing.camera_direction(subject["facing"], angle, s)
        p = geo.add(geo.v(subject["points"]["eyes"]), geo.mul(d, 200.0))
        if checks.side_of_line(p, a, b) * want > 0:
            return s
    return "left"


def _facing_toward(s: dict, other: dict) -> dict:
    """The subject turned to face the other (a conversation's eyeline), unless it already roughly does."""
    to = geo.sub(geo.v(other["points"]["eyes"]), geo.v(s["points"]["eyes"]))
    to = (to[0], to[1], 0.0)
    if geo.length(to) < 1e-3:
        return s
    if geo.angle_between(to, s["facing"]) < 60:
        return s
    return {**s, "facing": list(geo.norm(to))}


def plan(subjects, side: str = "left", focal: float = 50.0, wide_focal: float = 28.0, filmback=None,
         sizes=SINGLE, overs: bool = True, single_angle: float = 30.0, height="eye", aperture: float = 2.8) -> dict:
    """The coverage of a scene: {"line": [a, b] | None, "side", "shots": [{"name", "kind", "subjects", "size",
    "recipe", "solve"}], "issues": [cut checks between every pair that would break a rule]}."""
    subs = subjects if isinstance(subjects, (list, tuple)) else [subjects]
    if not subs:
        raise ValueError("coverage needs at least one subject")
    shots = []

    def add(name, kind, who, size, recipe):
        r = framing.solve([s for s in subs if s["name"] in who] if len(who) > 1 else
                          [next(s for s in subs if s["name"] == who[0])], size, filmback=filmback, aperture=aperture,
                          **recipe)
        shots.append({"name": name, "kind": kind, "subjects": list(who), "size": framing.size_key(size),
                      "recipe": {"subjects": list(who), "size": framing.size_key(size), **recipe}, "solve": r})

    if len(subs) == 1:
        s = subs[0]
        n = s["name"]
        sd = "left" if _line_side(side) > 0 else "right"
        for k in sizes:
            add(f"{n}_{k}", "single", [n], k, {"angle": 35.0, "side": sd, "focal": wide_focal if k in ("WS", "EWS")
                                                else focal, "height": height})
        add(f"{n}_MS_profile", "profile", [n], "MS", {"angle": 90.0, "side": sd, "focal": focal, "height": height})
        return {"line": None, "side": side, "shots": shots, "issues": []}

    want = _line_side(side)
    a, b = subs[0], subs[1]
    pa, pb = geo.v(a["points"]["eyes"]), geo.v(b["points"]["eyes"])
    ab = geo.sub(pb, pa)
    # the master: square to the line on the wanted side, aimed at the middle of the group
    perp = geo.norm((-ab[1], ab[0], 0.0))
    if checks.side_of_line(geo.add(pa, perp), pa, pb) * want < 0:
        perp = geo.mul(perp, -1.0)
    names = [s["name"] for s in subs]
    add("master", "master", names, "WS", {"angle": 0.0, "look": list(perp), "focal": wide_focal, "height": height})
    add("two_shot", "two", names[:2], "MS", {"angle": 0.0, "look": list(perp), "focal": focal * 0.7,
                                             "height": height})
    for me, other in ((a, b), (b, a)):
        faced = _facing_toward(me, other)
        n = me["name"]
        sd = _subject_side_for(faced, single_angle, want, pa, pb)
        for k in [k for k in sizes if k in ("MCU", "CU", "MS")]:
            r = framing.solve(faced, k, angle=single_angle, side=sd, focal=focal, filmback=filmback,
                              aperture=aperture, height=height)
            shots.append({"name": f"{n}_{k}", "kind": "single", "subjects": [n], "size": k,
                          "recipe": {"subjects": [n], "size": k, "angle": single_angle, "side": sd, "focal": focal,
                                     "height": height, "look": faced["facing"]}, "solve": r})
        if overs:
            shots.append(_over(faced, other, want, pa, pb, filmback, aperture))
    for s in subs[2:]:
        faced = _facing_toward(s, a)
        sd = _subject_side_for(faced, single_angle, want, pa, pb)
        r = framing.solve(faced, "MCU", angle=single_angle, side=sd, focal=focal, filmback=filmback, aperture=aperture)
        shots.append({"name": f"{s['name']}_MCU", "kind": "single", "subjects": [s["name"]], "size": "MCU",
                      "recipe": {"subjects": [s["name"]], "size": "MCU", "angle": single_angle, "side": sd,
                                 "focal": focal, "look": faced["facing"]}, "solve": r})
    issues = []
    for i, x in enumerate(shots):
        for y in shots[i + 1:]:
            for it in checks.cut(x["solve"]["camera"], y["solve"]["camera"], subs, names=(x["name"], y["name"])):
                if it["code"] == "line_180":
                    issues.append(it)
    return {"line": [list(pa), list(pb)], "side": side, "shots": shots, "issues": issues}


def _over(me: dict, other: dict, want: float, pa, pb, filmback, aperture, size: str = "MCU", back: float = 70.0,
          out: float = 22.0) -> dict:
    """An over-the-shoulder on `me`: the lens behind `other`'s shoulder on the wanted side of the line, a little
    above its eyes, the focal length solved so `me` is a `size` at that distance."""
    e_me, e_ot = geo.v(me["points"]["eyes"]), geo.v(other["points"]["eyes"])
    away = geo.norm((e_ot[0] - e_me[0], e_ot[1] - e_me[1], 0.0))
    lateral = (-away[1], away[0], 0.0)
    if checks.side_of_line(geo.add(e_ot, lateral), pa, pb) * want < 0:
        lateral = geo.mul(lateral, -1.0)
    sh = geo.v(other["points"]["shoulders"])
    lens_at = geo.add(geo.add((sh[0], sh[1], e_ot[2] + 6.0), geo.mul(away, back)), geo.mul(lateral, out))
    rel = geo.sub(lens_at, e_me)
    dist = math.hypot(rel[0], rel[1])
    # the angle of that point around `me`, from its facing, and on which of its sides
    yaw_cam, yaw_face = geo.yaw_of(rel), geo.yaw_of(me["facing"])
    delta = geo.wrap180(yaw_face - yaw_cam)  # + = toward me's left
    sd = "left" if delta >= 0 else "right"
    kw = dict(angle=abs(delta), side=sd, distance=dist, focal=None, height={"z": lens_at[2]}, filmback=filmback,
              aperture=aperture)
    r = framing.solve(me, size, **kw)
    # the foreground shoulder fills one side of the frame: the face goes on the other third
    fg = lens.project(r["camera"], sh)["u"]
    place = 2.0 / 3.0 if fg < 0.5 else 1.0 / 3.0
    r = framing.solve(me, size, place=place, **kw)
    n = me["name"]
    return {"name": f"{n}_OTS", "kind": "over", "subjects": [n], "size": size, "foreground": other["name"],
            "recipe": {"subjects": [n], "size": size, "angle": round(abs(delta), 3), "side": sd, "distance": dist,
                       "focal": None, "height": {"z": lens_at[2]}, "place": place, "look": me["facing"]},
            "solve": r}


def describe(plan_: dict) -> list:
    """One row per shot: what Claude reads to pick shots."""
    out = []
    for s in plan_["shots"]:
        r = s["solve"]
        out.append({"name": s["name"], "kind": s["kind"], "size": s["size"], "focal": round(r["focal"], 1),
                    "distance": round(r["distance"]), "loc": geo.rounded(r["camera"]["loc"], 1),
                    "rot": geo.rounded_rot(r["camera"]["rot"], 2), "warnings": r["warnings"]})
    return out


def hfov_of(shot: dict) -> float:
    return lens.hfov(shot["solve"]["camera"]["focal"], shot["solve"]["camera"]["filmback"])
