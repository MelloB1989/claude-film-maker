"""Camera moves as keyframes: a start camera, a list of moves, a frame range, and out come baked keys (location,
rotation, focal length, focus distance) every `step` frames, eased and continuous, ready for Sequencer.

A move is a dict {"move": kind, "frames": n | "from"/"to", "ease": ..., kind's own args}; moves run one after
another, each starting where the last one left the camera. Kinds:

    hold                                  stay put
    dolly       distance (cm, + forward)  move along the lens axis (level: the horizontal part, unless `free`)
    push_in     distance | fraction (of the distance to `aim`, default 0.25)       a dolly toward the subject
    pull_out    distance | fraction                                               a dolly away
    truck       distance (cm, + right)    move sideways
    pedestal    distance (cm, + up)       move straight up or down
    crane       rise (cm), reach (cm, + forward), swing (deg)  a jib: up/down, in/out and around its base
    orbit       degrees (+ counter-clockwise seen from above), radius (keep)       around `aim` (an arc when partial)
    arc         same as orbit
    pan         degrees (+ right)         turn on the spot
    tilt        degrees (+ up)
    roll        degrees                   (a dutch that moves)
    zoom        focal (mm at the end)     change the focal length
    dolly_zoom  focal (mm at the end)     the vertigo: dolly so the subject at `aim` keeps its size while the lens
                                          changes
    whip        degrees (+ right)         a whip pan: a fast pan with a hard ease, for a cut hidden in the blur
    rack        to (cm or a point)        pull focus to a new distance or point

With `aim` (a point) the camera keeps the aim point where it sat in the frame at the start of that move (a tracked
dolly, a crane that holds its subject); without it the rotation stays as it was (or turns, for pan/tilt/roll/whip).
`focus_on` (a point) bakes the focus distance to it on every key (a follow-focus).

Handheld noise (`noise`) is layered over the whole: smooth deterministic wobble in the camera's own axes,
{"preset": "subtle" | "handheld" | "documentary" | "breathing", "seed": int, "scale": 1.0} or explicit
{"pos": cm, "rot": deg, "hz": Hz}.
"""
from __future__ import annotations

import math

from . import geo, lens

EASES = ("linear", "in", "out", "in_out", "sine", "expo", "smooth")


def ease(t: float, kind: str = "in_out") -> float:
    """Easing 0..1 -> 0..1: linear, in (cubic), out, in_out (cubic), sine, smooth (smootherstep), expo (a whip)."""
    t = min(1.0, max(0.0, float(t)))
    k = (kind or "linear").lower().replace("-", "_").replace("ease_", "")
    if k == "linear":
        return t
    if k == "in":
        return t * t * t
    if k == "out":
        return 1.0 - (1.0 - t) ** 3
    if k in ("in_out", "inout", "both"):
        return 4 * t * t * t if t < 0.5 else 1.0 - (-2 * t + 2) ** 3 / 2
    if k == "sine":
        return -(math.cos(math.pi * t) - 1) / 2
    if k == "smooth":
        return t * t * t * (t * (t * 6 - 15) + 10)
    if k == "expo":
        if t in (0.0, 1.0):
            return t
        return 2 ** (20 * t - 10) / 2 if t < 0.5 else (2 - 2 ** (-20 * t + 10)) / 2
    raise ValueError(f"ease {kind!r}: one of {', '.join(EASES)}")


NOISE = {  # position amplitude cm, rotation amplitude deg, base frequency Hz
    "subtle": {"pos": 0.25, "rot": 0.15, "hz": 0.5},
    "handheld": {"pos": 0.7, "rot": 0.45, "hz": 0.9},
    "documentary": {"pos": 1.4, "rot": 0.9, "hz": 1.4},
    "breathing": {"pos": 0.4, "rot": 0.1, "hz": 0.22},
    "shake": {"pos": 2.5, "rot": 1.6, "hz": 3.0},
}


def _rng(seed: int):
    """A tiny deterministic generator (an LCG): the same seed gives the same wobble in any Python."""
    state = [(int(seed) * 2654435761 + 1013904223) & 0xFFFFFFFF]

    def nxt() -> float:
        state[0] = (1664525 * state[0] + 1013904223) & 0xFFFFFFFF
        return state[0] / 4294967296.0
    return nxt


def noise_fn(spec, fps: float):
    """t (frames) -> ((dx, dy, dz) cm in the camera's axes, (dpitch, dyaw, droll) deg). Each channel is three
    sines at incommensurate frequencies with seeded phases (1/f amplitudes): smooth, never repeating in a shot."""
    if not spec:
        return None
    spec = {"preset": spec} if isinstance(spec, str) else dict(spec)
    base = dict(NOISE[spec.get("preset", "handheld")]) if spec.get("preset", "handheld") in NOISE else None
    if base is None:
        raise ValueError(f"noise preset {spec.get('preset')!r}: one of {', '.join(NOISE)}")
    base.update({k: float(spec[k]) for k in ("pos", "rot", "hz") if k in spec})
    sc = float(spec.get("scale", 1.0))
    rnd = _rng(spec.get("seed", 7))
    chans = []
    for c in range(6):
        amp = (base["pos"] if c < 3 else base["rot"]) * sc
        if c == 5:
            amp *= 0.4  # roll wobbles least
        parts = [(amp / (1.0 + k) / 1.6, base["hz"] * m * (0.8 + 0.4 * rnd()), 2 * math.pi * rnd())
                 for k, m in enumerate((1.0, 2.13, 4.37))]
        chans.append(parts)

    def at(frame: float):
        t = frame / fps
        vals = [sum(a * math.sin(2 * math.pi * hz * t + ph) for a, hz, ph in parts) for parts in chans]
        return tuple(vals[:3]), tuple(vals[3:])
    return at


def _offset_in_frame(cam: dict, aim) -> tuple:
    """The aim point's angular offset from the lens axis: (pitch, yaw) to add to a look-at."""
    la = geo.look_at(cam["loc"], aim)
    return cam["rot"]["pitch"] - la["pitch"], geo.wrap180(cam["rot"]["yaw"] - la["yaw"])


def _aimed(loc, aim, off, roll) -> dict:
    la = geo.look_at(loc, aim)
    return geo.rot(la["pitch"] + off[0], la["yaw"] + off[1], roll)


def _seg_frames(m: dict, cursor: int) -> tuple:
    if "from" in m or "to" in m:
        a = int(m.get("from", cursor))
        b = int(m["to"])
    else:
        a, b = cursor, cursor + int(m.get("frames", 48))
    if b <= a:
        raise ValueError(f"move {m.get('move')!r}: frames {a}..{b} must run forward")
    return a, b


def plan(start: dict, moves: list, first: int = 0, last: int | None = None, fps: float = 24.0, step: int = 2,
         aim=None, focus_on=None, noise=None) -> dict:
    """Bake moves from `start` (a camera dict, see lens.camera) into keys.

    Returns {"keys": [{"frame", "loc", "rot", "focal", "focus"}], "segments": [[kind, from, to]], "end": camera}.
    `aim` and `focus_on` apply to every move that does not name its own; `last` holds the final pose to that frame.
    """
    cam = {**start, "loc": list(geo.v(start["loc"])), "rot": geo.as_rot(start["rot"])}
    cam.setdefault("focal", 35.0)
    states = []  # (frame, cam) samples
    segs = []
    cursor = int(first)
    states.append((cursor, _copy(cam)))
    for m in moves or []:
        m = dict(m)
        kind = str(m.get("move", "hold")).lower().replace("-", "_").replace(" ", "_")
        a, b = _seg_frames(m, cursor)
        if a > cursor:  # a gap: hold
            states.append((a, _copy(cam)))
        tgt = m.get("aim", aim)
        fn = _segment(kind, cam, m, tgt)
        e = m.get("ease", "expo" if kind == "whip" else "in_out")
        frames = list(range(a, b, max(1, int(step)))) + [b]
        for fr in frames[1:]:
            states.append((fr, fn(ease((fr - a) / (b - a), e))))
        cam = states[-1][1]
        segs.append([kind, a, b])
        cursor = b
    if last is not None and last > cursor:
        states.append((int(last), _copy(cam)))
    nfn = noise_fn(noise, fps)
    keys = []
    prev_yaw = None
    fo = focus_on
    for fr, c in _dense(states, step, nfn is not None):
        loc, r = list(c["loc"]), dict(c["rot"])
        if nfn:
            dp, dr = nfn(fr)
            fwd, right, up = geo.axes(r)
            loc = list(geo.add(loc, geo.add(geo.mul(fwd, dp[0]), geo.add(geo.mul(right, dp[1]), geo.mul(up, dp[2])))))
            r = geo.rot(r["pitch"] + dr[0], r["yaw"] + dr[1], r["roll"] + dr[2])
        if prev_yaw is not None:
            r["yaw"] = geo.unwrap(prev_yaw, r["yaw"])
        prev_yaw = r["yaw"]
        key = {"frame": int(fr), "loc": geo.rounded(loc, 3), "rot": geo.rounded_rot(r, 4), "focal": round(c["focal"], 4),
               "focus": None}
        if fo is not None and not c.get("racked"):
            key["focus"] = round(max(1.0, lens.view({"loc": loc, "rot": r}, fo)[0]), 2)
        elif c.get("focus") is not None:
            key["focus"] = round(float(c["focus"]), 2)
        keys.append(key)
    return {"keys": keys, "segments": segs, "end": _copy(cam), "frames": [int(first), keys[-1]["frame"]]}


def _dense(states, step, noisy):
    """The samples, deduplicated by frame (a later state wins), and densified to every `step` frames across holds
    when noise needs keys there."""
    by = {}
    for fr, c in states:
        by[fr] = c
    frames = sorted(by)
    if not noisy:
        return [(f, by[f]) for f in frames]
    out = []
    for i, f in enumerate(frames):
        out.append((f, by[f]))
        if i + 1 < len(frames):
            for g in range(f + step, frames[i + 1], step):
                out.append((g, _lerp_cam(by[f], by[frames[i + 1]], (g - f) / (frames[i + 1] - f))))
    return out


def _lerp_cam(a, b, t):
    c = _copy(a)
    c["loc"] = list(geo.lerp(a["loc"], b["loc"], t))
    c["rot"] = geo.rot(*(a["rot"][k] + geo.wrap180(b["rot"][k] - a["rot"][k]) * t for k in ("pitch", "yaw", "roll")))
    c["focal"] = a["focal"] + (b["focal"] - a["focal"]) * t
    return c


def _copy(c: dict) -> dict:
    return {**c, "loc": list(c["loc"]), "rot": dict(c["rot"])}


def _num(m: dict, *names, default=None):
    for n in names:
        if n in m and m[n] is not None:
            return float(m[n])
    if default is None:
        raise ValueError(f"move {m.get('move')!r} needs {' or '.join(names)}")
    return float(default)


def _segment(kind: str, cam: dict, m: dict, aim):
    """t (eased 0..1) -> camera for one move from `cam`."""
    c0 = _copy(cam)
    loc0 = geo.v(c0["loc"])
    r0 = c0["rot"]
    fwd, right, up = geo.axes(r0)
    off = _offset_in_frame(c0, aim) if aim is not None else None
    roll = r0["roll"]

    def place(loc, t, rot=None):
        c = _copy(c0)
        c["loc"] = list(loc)
        if rot is not None:
            c["rot"] = rot
        elif aim is not None:
            c["rot"] = _aimed(loc, aim, off, roll)
        return c

    if kind == "hold":
        return lambda t: _copy(c0)
    if kind in ("dolly", "push_in", "pull_out"):
        level = not m.get("free", False)
        axis = geo.norm((fwd[0], fwd[1], 0.0)) if level and abs(fwd[2]) < 0.999 else fwd
        if kind == "dolly":
            dist = _num(m, "distance", "cm")
        else:
            if "distance" in m:
                dist = abs(float(m["distance"]))
            else:
                if aim is None:
                    raise ValueError(f"{kind} needs distance (cm) or an aim point for a fraction of the way")
                dist = geo.dist(loc0, aim) * _num(m, "fraction", default=0.25)
            dist = dist if kind == "push_in" else -dist
            if aim is not None:  # push toward the subject, not along a lens that may be panned off it
                axis = geo.norm(geo.sub(aim, loc0))
                if level:
                    axis = geo.norm((axis[0], axis[1], 0.0))
        return lambda t: place(geo.add(loc0, geo.mul(axis, dist * t)), t)
    if kind == "truck":
        dist = _num(m, "distance", "cm")
        axis = geo.norm((right[0], right[1], 0.0)) if not m.get("free") else right
        return lambda t: place(geo.add(loc0, geo.mul(axis, dist * t)), t)
    if kind in ("pedestal", "boom_up", "boom_down"):
        dist = _num(m, "distance", "cm", "rise")
        if kind == "boom_down":
            dist = -abs(dist)
        return lambda t: place(geo.add(loc0, (0.0, 0.0, dist * t)), t)
    if kind in ("crane", "jib", "boom"):
        rise, reach, swing = _num(m, "rise", default=0), _num(m, "reach", default=0), _num(m, "swing", default=0)
        # the jib's base: `arm` cm behind the camera along its level heading
        arm = _num(m, "arm", default=300)
        h = geo.norm((fwd[0], fwd[1], 0.0))
        base = geo.sub(loc0, geo.mul(h, arm))

        def crane(t):
            yaw = geo.yaw_of(h) + swing * t
            hh = geo.from_yaw(yaw)
            loc = geo.add(base, geo.add(geo.mul(hh, arm + reach * t), (0.0, 0.0, rise * t)))
            if aim is None:
                return place(loc, t, geo.rot(r0["pitch"], r0["yaw"] + swing * t, roll))
            return place(loc, t)
        return crane
    if kind in ("orbit", "arc"):
        if aim is None:
            raise ValueError(f"{kind} needs an aim point to go around")
        deg = _num(m, "degrees", "angle")
        rel = geo.sub(loc0, aim)
        r_h = math.hypot(rel[0], rel[1])
        radius = _num(m, "radius", default=r_h)
        rise = _num(m, "rise", default=0)
        yaw0 = math.degrees(math.atan2(rel[1], rel[0]))

        def orbit(t):
            # + degrees is counter-clockwise seen from above; in Unreal's left-handed frame that is -yaw
            yaw = yaw0 - deg * t
            rr = r_h + (radius - r_h) * t
            loc = (aim[0] + rr * math.cos(math.radians(yaw)), aim[1] + rr * math.sin(math.radians(yaw)),
                   aim[2] + rel[2] + rise * t)
            return place(loc, t)
        return orbit
    if kind in ("pan", "tilt", "roll", "whip"):
        deg = _num(m, "degrees", "angle")
        k = {"pan": "yaw", "whip": "yaw", "tilt": "pitch", "roll": "roll"}[kind]
        return lambda t: place(loc0, t, {**r0, k: r0[k] + deg * t})
    if kind == "zoom":
        f1 = _num(m, "focal", "to")
        f0 = c0["focal"]

        def zoom(t):
            c = _copy(c0)
            c["focal"] = f0 * (f1 / f0) ** t  # zooms read evenly in log focal
            return c
        return zoom
    if kind in ("dolly_zoom", "vertigo", "zolly"):
        if aim is None:
            raise ValueError("dolly_zoom needs the aim point whose size it keeps")
        f1 = _num(m, "focal", "to")
        f0 = c0["focal"]
        d0 = lens.view(c0, aim)[0]
        axis = geo.norm(geo.sub(aim, loc0))

        def vertigo(t):
            f = f0 * (f1 / f0) ** t
            d = d0 * f / f0  # the subject's size ~ f / d: hold it
            c = place(geo.sub(aim, geo.mul(axis, d)), t)
            c["focal"] = f
            return c
        return vertigo
    if kind == "rack":
        to = m.get("to_point", m.get("to"))
        f0 = c0.get("focus")
        if to is None:
            raise ValueError("rack needs to (cm) or to_point ([x, y, z])")

        def rack(t):
            c = _copy(c0)
            target = lens.view(c0, to)[0] if isinstance(to, (list, tuple)) else float(to)
            start = f0 if f0 is not None else target
            c["focus"] = start + (target - start) * t
            c["racked"] = True  # from here on the focus is what the rack left, not the follow-focus
            return c
        return rack
    raise ValueError(f"unknown move {kind!r}; one of hold dolly push_in pull_out truck pedestal crane orbit arc pan "
                     "tilt roll zoom dolly_zoom whip rack")


def sequencer_keys(keys: list) -> dict:
    """Keys in the shapes the Sequencer ops take: transform [[frame, [x, y, z], {pitch, yaw, roll}]], and float
    tracks [[frame, value]] for the focal length and focus distance (only when they change or are set)."""
    xf = [[k["frame"], k["loc"], k["rot"]] for k in keys]
    focal = [[k["frame"], k["focal"]] for k in keys]
    if len({k[1] for k in focal}) == 1:
        focal = focal[:1]
    focus = [[k["frame"], k["focus"]] for k in keys if k.get("focus") is not None]
    if focus and len({k[1] for k in focus}) == 1:
        focus = focus[:1]
    return {"transform": xf, "focal": focal, "focus": focus}
