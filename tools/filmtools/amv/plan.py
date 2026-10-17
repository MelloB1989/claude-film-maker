"""An AMV plan: every per-frame value of a phonk/AMV edit, and the After Effects semantics they were written in.

The plan is `films/<id>/amv/plan.json` (film.json `amv.plan`). It was first written for an After Effects build
(`build.jsx`), so its numbers follow AE's conventions, and every renderer (the layer bake, the Blender scene, the
EffectCraft export) reads them through this module so they agree to the pixel:

- The comp is `W` x `H` (1920x1080) at `fps` (30); frames are comp frames, `0 .. dur-1`.
- A shot's layer is its clip at 1920x1080 with the anchor at the layer centre (960, 540). `px, py` is where the anchor
  lands on screen (px from the top-left, y down), `s` the uniform scale in %, `rz` the rotation in degrees, clockwise
  on screen. Screen point = P + R(rz) . (s/100) . (layer point - anchor), with R the usual matrix in y-down
  coordinates (so a positive angle turns clockwise).
- Per-frame arrays (`remap, px, py, s, rz`) start at the shot's `a` (index j = comp frame a + j) and hold their end
  values outside; between frames (motion-blur sub-samples) they are linear, as AE's per-frame linear keys are.
- `[[frame, value], ...]` key lists (`rfb, dblur, bulge, opacity, expo_keys, flash_ev, ...`) are AE linear keys:
  linear between keys, held before the first and after the last. Frames are comp frames.
- `remap[j]` is the clip time in seconds the layer shows at comp frame a + j. Clips are 60 fps, frame 0 at t = 0.

bpy-free and numpy-free: Blender's Python and the bake tools both import it.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

W, H = 1920, 1080
RFB_LEN = 0.07   # CC Radial Fast Blur: ray length as a fraction of the distance to the centre per amount/100 (global default)
RFB_BETA = 12.0  # 'Brightest' softness: weight exp(beta * luma) per ray sample (larger = nearer the hard brightest pixel)
RFB_MIX = 1.0    # 'Brightest': share of the per-channel max in the result, the rest the plain ray average (global default)
ANCHOR = (960.0, 540.0)
SHUTTER_ANGLE = 301.0
SHUTTER_PHASE = -150.0


def keys_lin(keys, f, default=0.0):
    """AE linear keys `[[frame, value], ...]` at frame `f` (may be fractional): held outside, linear inside.
    Values may be numbers or equal-length lists."""
    if not keys:
        return default
    ks = sorted(keys, key=lambda k: k[0])
    if f <= ks[0][0]:
        return ks[0][1]
    if f >= ks[-1][0]:
        return ks[-1][1]
    for (f0, v0), (f1, v1) in zip(ks, ks[1:]):
        if f0 <= f <= f1:
            u = 0.0 if f1 == f0 else (f - f0) / (f1 - f0)
            return _lerp(v0, v1, u)
    return ks[-1][1]


def keys_multi(keys, f):
    """Keys whose rows carry several values, `[[frame, v1, v2, ...], ...]` (e.g. rfb = [f, amount, cx, cy]):
    the values at `f` as a list, each linear between keys and held outside."""
    if not keys:
        return None
    ks = sorted(keys, key=lambda k: k[0])
    return [keys_lin([[k[0], k[i]] for k in ks], f) for i in range(1, len(ks[0]))]


def per_frame(arr, j):
    """A per-frame array at (fractional) index `j`: linear between entries, held outside."""
    if not arr:
        return None
    if j <= 0:
        return arr[0]
    n = len(arr) - 1
    if j >= n:
        return arr[n]
    i = int(math.floor(j))
    return _lerp(arr[i], arr[i + 1], j - i)


def _lerp(a, b, u):
    if isinstance(a, (list, tuple)):
        return [x + (y - x) * u for x, y in zip(a, b)]
    return a + (b - a) * u


def shutter_times(f, samples):
    """The `samples` sub-frame times of comp frame `f` under the plan's shutter (301 deg, phase -150 deg):
    evenly spread over [f + phase/360, f + (phase + angle)/360], centres of equal slices."""
    t0 = f + SHUTTER_PHASE / 360.0
    span = SHUTTER_ANGLE / 360.0
    return [t0 + span * (i + 0.5) / samples for i in range(samples)]


@dataclass
class Shot:
    index: int
    raw: dict

    @property
    def name(self):
        return self.raw["name"]

    @property
    def a(self):
        """First comp frame the layer shows."""
        return self.raw["a"]

    @property
    def b(self):
        """The cut: the next shot takes over here (the layer may run on to `end` under or over it)."""
        return self.raw["b"]

    @property
    def end(self):
        """One past the last comp frame the layer shows."""
        return self.raw["end"]

    @property
    def src(self):
        return self.raw["src"]

    def frames(self):
        return range(self.a, self.end)

    def remap(self, f):
        """Clip seconds shown at comp frame `f` (fractional `f` is linear between frames)."""
        return per_frame(self.raw["remap"], f - self.a)

    def transform(self, f):
        """(px, py, scale %, rz deg) at comp frame `f`."""
        j = f - self.a
        return (per_frame(self.raw["px"], j), per_frame(self.raw["py"], j),
                per_frame(self.raw["s"], j), per_frame(self.raw["rz"], j))

    def matrix(self, f):
        """2x3 affine, layer px -> screen px, at comp frame `f` (rows of [a, b, c] with x' = a x + b y + c)."""
        return affine(*self.transform(f))

    @property
    def tile(self):
        """Motion Tile output size in % (width, height) of the 1920x1080 layer: edge fill around the plate."""
        t = self.raw.get("tile") or [100, 100]
        return (float(t[0]), float(t[1]))

    @property
    def canvas(self):
        """The baked layer's canvas: (w, h, ox, oy), even sizes, layer pixel (x, y) at canvas (x + ox, y + oy)."""
        tw, th = self.tile
        w = int(round(W * tw / 100.0 / 2.0)) * 2
        h = int(round(H * th / 100.0 / 2.0)) * 2
        return (w, h, (w - W) // 2, (h - H) // 2)

    def ev(self, f):
        """Exposure trim in stops at `f` (`expo_keys` override the constant `ev`)."""
        if self.raw.get("expo_keys"):
            return keys_lin(self.raw["expo_keys"], f)
        return float(self.raw.get("ev") or 0.0)

    @property
    def sat(self):
        """Hue/Saturation master saturation trim (-100..100, 0 = none)."""
        return float(self.raw.get("sat") or 0.0)

    def rfb(self, f):
        """CC Radial Fast Blur (Zoom: Brightest) at `f`: (amount, cx, cy) in layer px, or None when off."""
        v = keys_multi(self.raw.get("rfb"), f)
        return None if v is None or v[0] <= 1e-6 else tuple(v)

    @property
    def rfb_len(self):
        """Radial blur ray length (fraction of the distance to the centre per amount/100): the shot's `rfb_len` or `RFB_LEN`."""
        return float(self.raw.get("rfb_len", RFB_LEN))

    @property
    def rfb_beta(self):
        """Softmax sharpness of the shot's Brightest radial blur: the shot's `rfb_beta` or `RFB_BETA`."""
        return float(self.raw.get("rfb_beta", RFB_BETA))

    @property
    def rfb_mix(self):
        """Share of the max (vs the average) along the ray in the shot's Brightest radial blur: `rfb_mix` or `RFB_MIX`."""
        return float(self.raw.get("rfb_mix", RFB_MIX))

    def dblur(self, f):
        """Directional Blur at `f`: (direction deg, length px) or None. Direction defaults to 90 (AE: horizontal)."""
        if not self.raw.get("dblur"):
            return None
        L = keys_lin(self.raw["dblur"], f)
        return None if L <= 1e-6 else (float(self.raw.get("dblur_dir", 90)), L)

    def bulge(self, f):
        """Optics Compensation field of view (reverse lens distortion on, FOV orientation 2, centre 960,540) at `f`."""
        if not self.raw.get("bulge"):
            return None
        v = keys_lin(self.raw["bulge"], f)
        return None if v <= 1e-6 else v

    def opacity(self, f):
        """Layer opacity 0..100 at `f`."""
        return keys_lin(self.raw.get("opacity"), f, 100.0)

    def hole(self, f):
        """Eye-dive hole at `f`, or None: (cx, cy, rx, ry, feather, expansion) in layer px. A Subtract ellipse mask
        (with a full-frame Add mask under it), feather = 0.45 rx, expansion keyed [[hole_f0, 0], [b-3, 4], [b-1, 40]].
        Before hole_f0 - 1 the hole is not keyed (AE holds the first key: radius ~0.7 px, invisible)."""
        if not self.raw.get("hole"):
            return None
        j = f - self.a
        h = per_frame(self.raw["hole"], j)
        f0 = self.raw["hole_f0"]
        if f < f0 - 1:
            h = self.raw["hole"][max(0, f0 - 1 - self.a)]
        exp = keys_lin([[f0, 0], [self.b - 3, 4], [self.b - 1, 40]], f)
        return (h[0], h[1], h[2], h[3], h[2] * 0.45, exp)

    @property
    def titles(self):
        """Titles inside the shot (layer space, ride the shot's camera): [{style, f_in, spec}] (f_in in comp frames)."""
        return self.raw.get("titles") or []

    @property
    def matte(self):
        """First frame of the shot's matte sequence (luma PNGs, frame i = comp frame a + matte_f0 + i), or None."""
        return self.raw.get("matte")

    @property
    def under(self):
        """Stacked below the previous shot (seen through its hole) instead of above it."""
        return bool(self.raw.get("under"))

    @property
    def slow(self):
        return bool(self.raw.get("slow"))

    @property
    def rim(self):
        return bool(self.raw.get("rim"))


def affine(px, py, s, rz):
    k = s / 100.0
    r = math.radians(rz)
    c, sn = math.cos(r) * k, math.sin(r) * k
    ax, ay = ANCHOR
    return [[c, -sn, px - (c * ax - sn * ay)],
            [sn, c, py - (sn * ax + c * ay)]]


@dataclass
class Plan:
    raw: dict
    root: Path
    shots: list = field(default_factory=list)

    @property
    def dur(self):
        return self.raw["dur"]

    @property
    def fps(self):
        return self.raw["fps"]

    def path(self, rel):
        """A path in the plan (relative to the film folder) made absolute."""
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    def clip(self, shot):
        return self.path(self.raw["footage"][shot.src])

    def shot(self, name):
        return next(s for s in self.shots if s.name == name)

    def visible(self, f):
        """Shots whose layer covers comp frame `f`, bottom to top in stacking order."""
        return [s for s in self.stack() if s.a <= f < s.end]

    def stack(self):
        """All shots bottom to top: later shots above earlier ones, an `under` shot directly below its predecessor
        (build.jsx: moveAfter / moveBefore)."""
        order = []
        for s in self.shots:
            if s.under and order:
                order.insert(order.index(self.shots[s.index - 1]), s)
            else:
                order.append(s)
        return order

    def flash_ev(self, f):
        return keys_lin(self.raw.get("flash_ev"), f)

    def bars(self, f):
        """Letterbox bar height in px at (integer) frame `f`."""
        b = self.raw.get("bars") or []
        return b[f] if 0 <= f < len(b) else 0.0


def load(film_dir, plan_rel=None):
    """The plan of the film in `film_dir` (film.json `amv.plan`, default `amv/plan.json`)."""
    film_dir = Path(film_dir)
    if plan_rel is None:
        cfg = json.loads((film_dir / "film.json").read_text())
        plan_rel = (cfg.get("amv") or {}).get("plan", "amv/plan.json")
    raw = json.loads((film_dir / plan_rel).read_text())
    plan = Plan(raw=raw, root=film_dir)
    plan.shots = [Shot(i, s) for i, s in enumerate(raw["shots"])]
    return plan
