"""A face performance as a picture, for looking at without the editor: stacked strips of the head (yaw, pitch, roll
in degrees), the eyes (left eye's yaw and pitch in the head), the blinks, the upper face (brows, cheeks) and the
mouth, on one time axis, with the gaze shifts and stressed words marked. Drawn with camkit.png (pure Python).

    img = plot.performance(curves, marks={"shifts": [1.0, 2.4], "emphasis": [1.2]})
    png.write("/tmp/perf.png", img)

What to look for: head lines that ease and overshoot a little (not straight ramps), small wobble in holds (not flat),
blinks irregularly spaced with some right after a gaze shift, brows moving on the stressed words, the two sides of
the face not identical.
"""
from __future__ import annotations

try:
    from ..camkit import png
except ImportError:  # perfkit loaded on its own (the client puts unreal/fmbridge on sys.path)
    from camkit import png
from . import curves as C
from . import eyes as E
from .rig import PREFIX, HeadSigns

BG, GRID, AXIS, TEXT = (18, 18, 22), (40, 40, 48), (90, 90, 100), (210, 210, 220)
COLORS = [(240, 120, 90), (110, 200, 120), (100, 160, 250), (230, 200, 90), (200, 120, 230), (90, 210, 220)]


def _strips(curves: dict, signs: HeadSigns) -> list:
    """[(title, unit, [(label, (times, values))])] for whatever the curves hold."""
    out = []
    head = [(n[4:].lower(), curves[n]) for n in ("HeadYaw", "HeadPitch", "HeadRoll") if n in curves]
    if head:
        out.append(("HEAD", "DEG", [(k, (t, [signs.__dict__[k] * x for x in v])) for k, (t, v) in head]))
    if any("eyeLook" in n for n in curves):
        a = E.angles_from_rig(curves, signs)
        if a["times"]:
            out.append(("EYE L IN HEAD", "DEG", [("yaw", (a["times"], [y for y, _ in a["L"]])),
                                                  ("pitch", (a["times"], [p for _, p in a["L"]]))]))
    bl = [(s, curves[PREFIX + "eyeBlink" + s]) for s in ("L", "R") if PREFIX + "eyeBlink" + s in curves]
    if bl:
        out.append(("BLINK", "0-1", [(f"blink {s.lower()}", c) for s, c in bl]))
    upper = [n for n in ("browRaiseInL", "browRaiseInR", "browDownL", "eyeCheekRaiseL", "eyeCheekRaiseR", "eyeSquintInnerL")
             if PREFIX + n in curves]
    if upper:
        out.append(("UPPER FACE", "0-1", [(n, curves[PREFIX + n]) for n in upper[:6]]))
    mouth = [n for n in ("jawOpen", "mouthCornerPullL", "mouthCornerPullR", "mouthCornerDepressL", "mouthLipsPressL")
             if PREFIX + n in curves]
    if mouth:
        out.append(("MOUTH", "0-1", [(n, curves[PREFIX + n]) for n in mouth[:5]]))
    return out


def performance(curves: dict, t0: float | None = None, t1: float | None = None, marks: dict | None = None,
                width: int = 1200, strip_h: int = 120, signs: HeadSigns | None = None, title: str = "") -> png.Image:
    """The curves as stacked strips (see the module docstring). `marks`: {"shifts": [t], "emphasis": [t], "blinks":
    [t]} drawn as vertical ticks (gaze shifts blue, emphasis yellow)."""
    signs = signs or HeadSigns()
    strips = _strips(curves, signs)
    allt = [t for _, (ts, _) in curves.items() for t in ts[:1] + ts[-1:]] or [0.0, 1.0]
    t0 = min(allt) if t0 is None else t0
    t1 = max(allt) if t1 is None else t1
    if t1 <= t0:
        t1 = t0 + 1.0
    left, top, gap = 130, 26 if title else 8, 10
    h = top + max(1, len(strips)) * (strip_h + gap) + 24
    img = png.Image(width, h, BG)
    if title:
        img.text(8, 6, title.upper()[:120], TEXT, scale=2)
    W = width - left - 10

    def X(t):
        return left + int((t - t0) / (t1 - t0) * W)
    marks = marks or {}
    for k, (si, (name, unit, series)) in enumerate([(i, s) for i, s in enumerate(strips)]):
        y0 = top + k * (strip_h + gap)
        y1 = y0 + strip_h
        img.rect(left, y0, left + W, y1, GRID)
        img.text(6, y0 + 4, name, TEXT)
        img.text(6, y0 + 16, unit, AXIS)
        vals = [v for _, (_, vs) in series for v in vs] or [0.0, 1.0]
        lo, hi = min(vals), max(vals)
        if unit == "0-1":
            lo, hi = 0.0, max(1.0, hi)
        if hi - lo < 1.0:
            mid = (hi + lo) / 2
            lo, hi = mid - 0.5, mid + 0.5
        pad = (hi - lo) * 0.08
        lo, hi = lo - pad, hi + pad

        def Y(v):
            return y1 - int((v - lo) / (hi - lo) * strip_h)
        if lo < 0 < hi:
            img.line(left, Y(0.0), left + W, Y(0.0), AXIS, dash=4)
        img.text(left - 44, y0 + 2, f"{hi:.0f}" if abs(hi) >= 10 else f"{hi:.1f}", AXIS)
        img.text(left - 44, y1 - 10, f"{lo:.0f}" if abs(lo) >= 10 else f"{lo:.1f}", AXIS)
        for kind, col in (("shifts", (100, 160, 250)), ("emphasis", (230, 200, 90))):
            for t in marks.get(kind, []):
                if t0 <= t <= t1:
                    img.line(X(t), y0, X(t), y1, col, alpha=0.35)
        for j, (label, (ts, vs)) in enumerate(series):
            col = COLORS[j % len(COLORS)]
            grid = C.grid(t0, t1, W / (t1 - t0))
            pv = None
            for t in grid:
                v = C.at(ts, vs, t)
                p = (X(t), max(y0, min(y1, Y(v))))
                if pv is not None:
                    img.line(pv[0], pv[1], p[0], p[1], col)
                pv = p
            img.text(left + 6 + 110 * j, y0 + 4, label.upper()[:16], col)
    yb = top + len(strips) * (strip_h + gap)
    step = 1.0 if t1 - t0 <= 20 else 5.0
    t = (int(t0 / step) + 1) * step if t0 % step else t0
    while t <= t1:
        img.line(X(t), yb - gap, X(t), yb - gap + 4, AXIS)
        img.text(X(t) - 6, yb, f"{t:.0f}S", AXIS)
        t += step
    return img
