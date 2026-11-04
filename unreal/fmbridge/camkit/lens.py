"""Filmbacks, lenses, fields of view, depth of field, and where a world point lands in the frame.

The presets are the engine's own (Engine/Config/BaseEngine.ini [/Script/CinematicCamera.CineCameraSettings],
lines 3609-3639 in 5.8.4): a camera made here with filmback "16:9 Digital Film" is the editor's default cine camera.
A cine camera constrains its aspect ratio to the filmback's (CineCameraComponent.cpp:45, :536), so the picture is
the sensor: the horizontal field of view comes from the sensor width and the focal length (:286-301), the vertical
from the sensor height. Projection here follows the engine's view: depth along the camera's X, right along Y, up
along Z.

A camera is a plain dict: {"loc": [x, y, z], "rot": {"pitch", "yaw", "roll"}, "focal": mm, "filmback": [w, h] mm
(or a preset name), "aperture": f-stop, "focus": cm}. Frame coordinates are fractions of the picture: u 0 (left)..1
(right), v 0 (top)..1 (bottom); a point outside the frame has u or v outside [0, 1].
"""
from __future__ import annotations

import math

from . import geo

# name: (sensor width, sensor height) in mm, as BaseEngine.ini lists them
FILMBACKS = {
    "16:9 Film": (24.00, 13.5),
    "16:9 Digital Film": (23.76, 13.365),
    "16:9 DSLR": (36.0, 20.25),
    "Super 8mm": (5.79, 4.01),
    "Super 16mm": (12.52, 7.58),
    "Super 35mm": (24.89, 18.66),
    "35mm Academy": (21.946, 16.002),
    "35mm Full Aperture": (24.892, 18.9121),
    "35mm VistaVision": (37.719, 25.146),
    "IMAX 70mm": (70.41, 56.63),
    "APS-C (Canon)": (22.2, 14.8),
    "Full Frame DSLR": (36.0, 24.0),
    "Micro Four Thirds": (17.3, 13.0),
}
DEFAULT_FILMBACK = "16:9 Digital Film"

# name: (min focal, max focal, min f-stop, max f-stop, diaphragm blades)
LENSES = {
    "12mm Prime f/2.8": (12, 12, 2.8, 22, 7),
    "30mm Prime f/1.4": (30, 30, 1.4, 22, 7),
    "50mm Prime f/1.8": (50, 50, 1.8, 22, 7),
    "85mm Prime f/1.8": (85, 85, 1.8, 22, 7),
    "105mm Prime f/2": (105, 105, 2.0, 22, 7),
    "200mm Prime f/2": (200, 200, 2.0, 22, 7),
    "24-70mm Zoom f/2.8": (24, 70, 2.8, 22, 7),
    "70-200mm Zoom f/2.8": (70, 200, 2.8, 22, 7),
    "Universal Zoom": (4, 1000, 1.2, 22, 7),
}
DEFAULT_LENS = "Universal Zoom"  # the engine's default: any focal 4-1000 mm, f/1.2-22

# a cinematographer's prime set: the solver snaps to these when asked (`snap_focal`)
PRIMES = (14, 18, 21, 25, 27, 32, 35, 40, 50, 65, 75, 85, 100, 135, 150, 200)


def filmback(fb) -> tuple:
    """(width, height) mm from a preset name or a [w, h] pair; unknown names raise with the list."""
    if fb is None:
        fb = DEFAULT_FILMBACK
    if isinstance(fb, str):
        key = _match(fb, FILMBACKS)
        return FILMBACKS[key]
    w, h = float(fb[0]), float(fb[1])
    if w <= 0 or h <= 0:
        raise ValueError(f"filmback {fb}: width and height must be > 0 mm")
    return (w, h)


def filmback_name(fb) -> str:
    """The preset a [w, h] pair matches, or "custom"."""
    w, h = filmback(fb)
    for k, (pw, ph) in FILMBACKS.items():
        if abs(pw - w) < 1e-3 and abs(ph - h) < 1e-3:
            return k
    return "custom"


def lens(name: str) -> tuple:
    return LENSES[_match(name, LENSES)]


def _match(name: str, table: dict) -> str:
    if name in table:
        return name
    low = {k.lower().replace(" ", ""): k for k in table}
    k = low.get(name.lower().replace(" ", ""))
    if k:
        return k
    near = [k for k in table if name.lower() in k.lower()]
    if len(near) == 1:
        return near[0]
    raise ValueError(f"no preset {name!r}; one of: {', '.join(table)}")


def hfov(focal: float, fb=None) -> float:
    """Horizontal field of view in degrees (GetHorizontalFieldOfView with no crop, squeeze 1, no overscan)."""
    w, _ = filmback(fb)
    return math.degrees(2.0 * math.atan(w / (2.0 * focal)))


def vfov(focal: float, fb=None) -> float:
    _, h = filmback(fb)
    return math.degrees(2.0 * math.atan(h / (2.0 * focal)))


def focal_for_hfov(deg: float, fb=None) -> float:
    w, _ = filmback(fb)
    return (w / 2.0) / math.tan(math.radians(deg) / 2.0)


def focal_for_vfov(deg: float, fb=None) -> float:
    _, h = filmback(fb)
    return (h / 2.0) / math.tan(math.radians(deg) / 2.0)


def aspect(fb=None) -> float:
    w, h = filmback(fb)
    return w / h


def equivalent_focal(focal: float, fb_from, fb_to) -> float:
    """The focal length on `fb_to` with the same horizontal field of view as `focal` on `fb_from`."""
    return focal * filmback(fb_to)[0] / filmback(fb_from)[0]


def coc_mm(fb=None) -> float:
    """Circle of confusion (mm): the sensor diagonal / 1500 (the Zeiss rule)."""
    w, h = filmback(fb)
    return math.hypot(w, h) / 1500.0


def dof(focal: float, aperture: float, focus_cm: float, fb=None) -> dict:
    """Depth of field: {"near", "far", "hyperfocal"} in cm (far None = to infinity)."""
    f, n, s = float(focal), float(aperture), float(focus_cm) * 10.0
    c = coc_mm(fb)
    hyper = f * f / (n * c) + f
    near = s * (hyper - f) / (hyper + s - 2 * f)
    far = s * (hyper - f) / (hyper - s) if s < hyper else None
    return {"near": near / 10.0, "far": None if far is None else far / 10.0, "hyperfocal": hyper / 10.0,
            "depth": None if far is None else (far - near) / 10.0}


def in_focus(focal: float, aperture: float, focus_cm: float, distance_cm: float, fb=None) -> bool:
    d = dof(focal, aperture, focus_cm, fb)
    return d["near"] <= distance_cm and (d["far"] is None or distance_cm <= d["far"])


def aperture_for_depth(focal: float, focus_cm: float, near_cm: float, far_cm: float, fb=None,
                       stops=(1.2, 1.4, 2.0, 2.8, 4.0, 5.6, 8.0, 11.0, 16.0, 22.0)) -> float:
    """The widest standard f-stop that holds [near_cm, far_cm] in focus at `focus_cm` (22 if none does)."""
    for n in stops:
        d = dof(focal, n, focus_cm, fb)
        if d["near"] <= near_cm and (d["far"] is None or far_cm <= d["far"]):
            return n
    return stops[-1]


def snap(focal: float, primes=PRIMES) -> float:
    return float(min(primes, key=lambda p: abs(math.log(p / focal))))


def camera(loc, rot, focal: float = 35.0, filmback_=None, aperture: float = 2.8, focus: float | None = None) -> dict:
    """A camera dict (see the module docstring)."""
    return {"loc": list(geo.v(loc)), "rot": geo.as_rot(rot), "focal": float(focal),
            "filmback": list(filmback(filmback_)), "aperture": float(aperture), "focus": focus}


def view(cam: dict, p) -> tuple:
    """A world point in camera space: (depth along the lens axis, right, up) in cm."""
    fwd, right, up = geo.axes(cam["rot"])
    d = geo.sub(geo.v(p), geo.v(cam["loc"]))
    return geo.dot(d, fwd), geo.dot(d, right), geo.dot(d, up)


def project(cam: dict, p) -> dict:
    """Where a world point lands in the frame: {"u", "v", "depth", "visible"}; u, v are fractions of the picture
    (0, 0 top left), beyond [0, 1] when outside it; a point behind the lens has depth <= 0 and visible False."""
    depth, right, up = view(cam, p)
    w, h = filmback(cam.get("filmback"))
    f = float(cam["focal"])
    if depth <= 1e-6:
        return {"u": float("nan"), "v": float("nan"), "depth": depth, "visible": False}
    # on the sensor: x = f * right / depth (mm), over the half-width
    u = 0.5 + (f * right / depth) / w
    vv = 0.5 - (f * up / depth) / h
    return {"u": u, "v": vv, "depth": depth, "visible": 0.0 <= u <= 1.0 and 0.0 <= vv <= 1.0}


def unproject(cam: dict, u: float, v: float, depth: float) -> tuple:
    """The world point at frame position (u, v) and `depth` cm along the lens axis."""
    w, h = filmback(cam.get("filmback"))
    f = float(cam["focal"])
    right = (u - 0.5) * w * depth / f
    up = (0.5 - v) * h * depth / f
    fwd, r, uu = geo.axes(cam["rot"])
    return geo.add(geo.v(cam["loc"]), geo.add(geo.mul(fwd, depth), geo.add(geo.mul(r, right), geo.mul(uu, up))))


def frame_height_at(cam: dict, depth: float) -> float:
    """The height (cm) the frame covers at `depth` cm."""
    _, h = filmback(cam.get("filmback"))
    return h * depth / float(cam["focal"])
