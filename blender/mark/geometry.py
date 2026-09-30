"""The GitLoom mark as seven parametric ribbons, traced from web/public/mark.png.

The mark is a woven hash: two verticals and two horizontals in a plain weave, the bone G wrapped round its top left
and a moss loop hanging off its bottom right. Every strand that passes under another changes there, hidden, as a diff
does: the G's bar goes under the stem and comes out moss, the blood vertical goes under the moss bar and comes out
moss, the blood crossbar goes under the moss vertical and comes out moss. Modelled as the seven ribbons you see:

  piece      colour  path (mark px: x right, y down, mark.png's 256 px frame)
  g          bone    top terminal (leaf) -> top bar left -> the semicircle -> bottom bar right -> under the stem
  stem       bone    top (left corner round) -> down -> bottom (left corner round): over H1, under H2
  vert       blood   top (round cap) -> down -> under the moss bar
  cross      blood   left terminal (leaf) -> right, over the stem -> under the moss vertical
  bar        moss    from under the stem -> right, over the blood vertical -> right terminal (leaf)
  loop       moss    from under the moss bar -> down, over the crossbar -> round the bottom left -> bottom bar -> under
                     the loop's right side
  hook       moss    from under the moss vertical -> right -> round the top right -> down the right side -> square end

A piece is a centreline (lines and circular arcs) swept by a flat band: half-width `hw(s)` either side, and at each
end a corner radius per side (0 sharp, the band's width a leaf, half of it a round cap). Side A is the centreline's
left in the picture's own axes (the normal (-ty, tx), y down), side B the other.

The 2D outline of each piece and their union's raster (4x4 supersampled) give the silhouette; `iou` compares it with
the reference, mark.png's alpha thresholded at 0.5 and kept to the mark's own connected region (its scattered specks
of dust go). Everything here is numpy only: it runs in Blender and under the tools project.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PARAMS = HERE / "params.json"
REFERENCE = Path.home() / "Developer" / "code" / "gitloom" / "web" / "public" / "mark.png"
SIZE = 256  # the reference's frame, in mark px

# The weave: (over, under..., at) per crossing; `at` names the point by the pieces' own coordinates.
CROSSINGS = {
    "A": {"over": "stem", "under": ("g", "bar")},  # the stem over the G's bar / the moss bar
    "B": {"over": "cross", "under": ("stem",)},  # the blood crossbar over the stem
    "C": {"over": "bar", "under": ("vert", "loop")},  # the moss bar over the blood vertical / the loop
    "D": {"over": "loop", "under": ("cross", "hook")},  # the moss vertical over the crossbar / the hook
    "E": {"over": "hook", "under": ("loop",)},  # the hook's right side over the loop's bottom bar
}

COLOURS = {"g": "bone", "stem": "bone", "vert": "blood", "cross": "blood", "bar": "moss", "loop": "moss", "hook": "moss"}

# Traced from mark.png (see fit.py, which refines these and writes params.json).
DEFAULTS = {
    # the G: centreline semicircle (centre, radius) and the top terminal's x (the bar ends under the stem's centre);
    # the outer and the inner edge's offsets (it is a calligraphic stroke, heavier at the upper left) at: the
    # terminal, the top of the arc, 45 deg on, the left, 135 deg on, the bottom, the bar's end
    "g_cx": 79.5, "g_cy": 79.19, "g_r": 58.31, "g_x_top": 142.5,
    "g_ho": [12.12, 12.12, 13.7, 14.0, 9.3, 11.0, 11.0],
    "g_hi": [12.12, 12.12, 13.7, 14.0, 9.3, 11.0, 11.0],
    # the stem: centre x, half-width, top and bottom y, the left corners' radii
    "stem_x": 125.4, "stem_hw": 11.4, "stem_y0": 62.75, "stem_y1": 232.0, "stem_r0": 16.0, "stem_r1": 16.0,
    # the blood vertical: centre x, half-width, top y, its cap's corner radii (left, right)
    "vert_x": 159.0, "vert_hw": 13.2, "vert_y0": 42.8, "vert_rl": 12.0, "vert_rr": 14.0,
    # the blood crossbar: centre y, half-width, left end x (its sharp top corner)
    "cross_y": 173.96, "cross_hw": 11.23, "cross_x0": 15.6,
    # the moss bar: centre y, half-width, right end x (its sharp top corner)
    "bar_y": 136.6, "bar_hw": 9.8, "bar_x1": 248.3,
    # the loop: the moss vertical's centre x and half-width, the bottom-left turn's centreline radius, the bottom
    # bar's centre y and half-width
    "loop_x": 159.0, "loop_hw": 11.3, "loop_r": 28.5, "loop_y": 238.5, "loop_hw2": 9.6,
    # the hook: the top bar's centre y and half-width, the top-right turn's radius, the right side's centre x and
    # half-width, its square bottom end
    "hook_y": 172.6, "hook_hw": 9.72, "hook_r": 26.3, "hook_x": 230.4, "hook_hw2": 10.7, "hook_y1": 248.2,
}


def load_params(path: Path = PARAMS) -> dict:
    """The fitted parameters (params.json), else the traced defaults."""
    p = dict(DEFAULTS)
    if path.exists():
        p.update(json.loads(path.read_text()))
    return p


def save_params(p: dict, path: Path = PARAMS) -> None:
    """Write the parameters, to a ten-thousandth of a mark px."""
    def r(v):
        return [round(float(x), 4) for x in v] if isinstance(v, list) else round(float(v), 4)

    path.write_text(json.dumps({k: r(v) for k, v in p.items()}, indent=1) + "\n")


# ------------------------------------------------------------------------------------------------ centrelines

def _line(a, b, step):
    a, b = np.asarray(a, float), np.asarray(b, float)
    n = max(1, math.ceil(np.linalg.norm(b - a) / step))
    return a + (b - a) * np.linspace(0, 1, n + 1)[:, None]


def _arc(c, r, a0, a1, step):
    """Points on the circle (c, r) from angle a0 to a1 (radians, image axes: (cos a, sin a), y down)."""
    n = max(2, math.ceil(abs(a1 - a0) * r / step))
    a = np.linspace(a0, a1, n + 1)
    return np.column_stack([c[0] + r * np.cos(a), c[1] + r * np.sin(a)])


def _chain(*parts):
    out = [parts[0]]
    for p in parts[1:]:
        out.append(p[1:] if np.allclose(p[0], out[-1][-1], atol=1e-6) else p)
    return np.vstack(out)


@dataclass
class Piece:
    name: str
    colour: str
    path: np.ndarray  # (n, 2) centreline, mark px
    hw_knots: list  # [(s fraction 0..1, half-width)], interpolated linearly in s: side A's offset
    cap0: tuple  # (radius side A, radius side B) at the start
    cap1: tuple  # likewise at the end
    hwb_knots: list | None = None  # side B's, when it differs from side A's
    s: np.ndarray = field(init=False)  # arc length at each path point

    def __post_init__(self):
        self.s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(self.path, axis=0), axis=1))])

    @property
    def length(self) -> float:
        return float(self.s[-1])

    def hw(self, s, side: str = "a") -> np.ndarray:
        """The band's offset on side A (or B) before the end corners."""
        f, v = zip(*(self.hwb_knots if side == "b" and self.hwb_knots else self.hw_knots))
        return np.interp(np.asarray(s, float) / self.length, f, v)

    def at(self, s) -> tuple[np.ndarray, np.ndarray]:
        """Centre points and unit tangents at arc lengths s (clamped to the piece)."""
        s = np.clip(np.asarray(s, float), 0, self.length)
        p = np.column_stack([np.interp(s, self.s, self.path[:, k]) for k in range(2)])
        i = np.clip(np.searchsorted(self.s, s, side="right") - 1, 0, len(self.path) - 2)
        t = self.path[i + 1] - self.path[i]
        return p, t / np.linalg.norm(t, axis=1, keepdims=True)

    def sides(self, s) -> tuple[np.ndarray, np.ndarray]:
        """Side A's and side B's offsets from the centre at arc lengths s: the half-width, less the end corners."""
        s = np.asarray(s, float)
        offa, offb = self.hw(s, "a"), self.hw(s, "b")
        L = self.length
        for (ra, rb), u in ((self.cap0, s), (self.cap1, L - s)):
            for off, r in ((offa, ra), (offb, rb)):
                if r > 0:
                    k = u < r
                    off[k] -= r - np.sqrt(np.maximum(r * r - (r - u[k]) ** 2, 0.0))
        return offa, offb

    def samples(self, step: float = 0.5, corner: int = 24) -> np.ndarray:
        """Arc lengths to sample: every `step`, and densely through each end's corners (where the edge turns
        fastest; the ends are straight runs). Even spacing elsewhere keeps the tangents smooth round the turns: a
        ring's offset edge on the inside of a turn must never step back past its neighbour's."""
        L = self.length
        s = [np.linspace(0, L, max(2, math.ceil(L / step)) + 1)]
        for r in (*self.cap0, *self.cap1):
            if r > 0:
                ph = np.linspace(0, math.pi / 2, corner + 1)
                u = r - r * np.cos(ph)  # the corner's arc, evenly in angle
                s += [u, L - u]
        s = np.unique(np.clip(np.concatenate(s), 0, L))
        return s

    def outline(self, step: float = 0.5) -> np.ndarray:
        """The band's 2D outline (closed polygon): side A forward, side B back."""
        s = self.samples(step)
        p, t = self.at(s)
        n = np.column_stack([-t[:, 1], t[:, 0]])
        offa, offb = self.sides(s)
        a = p + n * offa[:, None]
        b = p - n * offb[:, None]
        return np.vstack([a, b[::-1]])


def pieces(p: dict | None = None, step: float = 0.25) -> dict[str, Piece]:
    """The seven ribbons for parameters `p` (default: params.json)."""
    p = load_params() if p is None else p
    out = {}

    # the G: terminal -> left along the top bar -> the semicircle (top, left, bottom) -> right along the bottom bar
    cx, cy, r = p["g_cx"], p["g_cy"], p["g_r"]
    top, bot = cy - r, cy + r
    path = _chain(_line((p["g_x_top"], top), (cx, top), step),
                  _arc((cx, cy), r, -math.pi / 2, -3 * math.pi / 2, step),
                  _line((cx, bot), (p["stem_x"], bot), step))
    g = Piece("g", "bone", path, [], (0.0, 0.0), (0.0, 0.0))
    lt, la = p["g_x_top"] - cx, math.pi * r  # the top bar's length, the arc's
    knots = [0.0, lt, lt + la * 0.25, lt + la * 0.5, lt + la * 0.75, lt + la, g.length]
    g.hw_knots = [(k / g.length, h) for k, h in zip(knots, p["g_ho"])]  # side A: the outside of the G
    g.hwb_knots = [(k / g.length, h) for k, h in zip(knots, p["g_hi"])]  # side B: its inside
    g.cap0 = (0.0, p["g_ho"][0] + p["g_hi"][0])  # the leaf: sharp at the top (side A), round across the whole band
    out["g"] = g

    # the stem: down (side A is the left: the round corners)
    hw = p["stem_hw"]
    out["stem"] = Piece("stem", "bone", _line((p["stem_x"], p["stem_y0"]), (p["stem_x"], p["stem_y1"]), step),
                        [(0, hw), (1, hw)], (p["stem_r0"], 0.0), (p["stem_r1"], 0.0))

    # the blood vertical: down from its round cap to the moss bar's centre line (hidden under it)
    hw = p["vert_hw"]
    out["vert"] = Piece("vert", "blood", _line((p["vert_x"], p["vert_y0"]), (p["vert_x"], p["bar_y"]), step),
                        [(0, hw), (1, hw)], (p["vert_rl"], p["vert_rr"]), (0.0, 0.0))

    # the blood crossbar: right from its leaf (sharp at the top: going right, side A is down) to under the loop
    hw = p["cross_hw"]
    out["cross"] = Piece("cross", "blood", _line((p["cross_x0"], p["cross_y"]), (p["loop_x"], p["cross_y"]), step),
                         [(0, hw), (1, hw)], (2 * hw, 0.0), (0.0, 0.0))

    # the moss bar: from under the stem, right to its leaf (sharp at the top)
    hw = p["bar_hw"]
    out["bar"] = Piece("bar", "moss", _line((p["stem_x"], p["bar_y"]), (p["bar_x1"], p["bar_y"]), step),
                       [(0, hw), (1, hw)], (0.0, 0.0), (2 * hw, 0.0))

    # the loop: from under the moss bar, down, round the bottom left, right along the bottom to under the hook
    x, y, rr = p["loop_x"], p["loop_y"], p["loop_r"]
    path = _chain(_line((x, p["bar_y"]), (x, y - rr), step),
                  _arc((x + rr, y - rr), rr, math.pi, math.pi / 2, step),
                  _line((x + rr, y), (p["hook_x"], y), step))
    lp = Piece("loop", "moss", path, [], (0.0, 0.0), (0.0, 0.0))
    l1 = (y - rr) - p["bar_y"]
    lp.hw_knots = [(0, p["loop_hw"]), (l1 / lp.length, p["loop_hw"]),
                   ((l1 + math.pi / 2 * rr) / lp.length, p["loop_hw2"]), (1, p["loop_hw2"])]
    out["loop"] = lp

    # the hook: from under the moss vertical, right, round the top right, down the right side to its square end
    x, y, rr = p["hook_x"], p["hook_y"], p["hook_r"]
    path = _chain(_line((p["loop_x"], y), (x - rr, y), step),
                  _arc((x - rr, y + rr), rr, -math.pi / 2, 0.0, step),
                  _line((x, y + rr), (x, p["hook_y1"]), step))
    hk = Piece("hook", "moss", path, [], (0.0, 0.0), (0.0, 0.0))
    l1 = (x - rr) - p["loop_x"]
    hk.hw_knots = [(0, p["hook_hw"]), (l1 / hk.length, p["hook_hw"]),
                   ((l1 + math.pi / 2 * rr) / hk.length, p["hook_hw2"]), (1, p["hook_hw2"])]
    out["hook"] = hk
    return out


def crossing_points(p: dict | None = None) -> dict[str, tuple[float, float]]:
    """Where the weave's five crossings are (mark px)."""
    p = load_params() if p is None else p
    return {"A": (p["stem_x"], p["bar_y"]), "B": (p["stem_x"], p["cross_y"]), "C": (p["loop_x"], p["bar_y"]),
            "D": (p["loop_x"], p["cross_y"]), "E": (p["hook_x"], p["loop_y"])}


# ------------------------------------------------------------------------------------------------ rasters

def fill(poly: np.ndarray, size: int = SIZE, ss: int = 4) -> np.ndarray:
    """Nonzero fill of a closed polygon (mark px) on a size x size frame, ss x ss samples a pixel: (size*ss)^2 bool."""
    n = size * ss
    x0, y0 = poly[:, 0] * ss, poly[:, 1] * ss
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    up = y1 > y0
    lo, hi = np.where(up, y0, y1), np.where(up, y1, y0)
    # sample rows sit at r + 0.5; an edge covers the rows whose centre is in [lo, hi)
    r0 = np.clip(np.ceil(lo - 0.5), 0, n).astype(int)
    r1 = np.clip(np.ceil(hi - 0.5), 0, n).astype(int)
    cnt = r1 - r0
    keep = cnt > 0
    if not keep.any():
        return np.zeros((n, n), bool)
    e = np.repeat(np.nonzero(keep)[0], cnt[keep])
    rows = np.concatenate([np.arange(a, b) for a, b in zip(r0[keep], r1[keep])])
    yc = rows + 0.5
    x = x0[e] + (yc - y0[e]) * (x1[e] - x0[e]) / (y1[e] - y0[e])
    col = np.clip(np.ceil(x - 0.5), 0, n).astype(int)  # the first sample column right of the crossing
    w = np.where(up[e], 1, -1)
    acc = np.zeros((n, n + 1), np.int32)
    np.add.at(acc, (rows, col), w)
    return np.cumsum(acc, axis=1)[:, :n] != 0


def coverage(polys, size: int = SIZE, ss: int = 4) -> np.ndarray:
    """The union of polygons as per-pixel coverage 0..1 (size x size)."""
    m = np.zeros((size * ss, size * ss), bool)
    for poly in polys:
        m |= fill(poly, size, ss)
    return m.reshape(size, ss, size, ss).mean(axis=(1, 3))


def silhouette(p: dict | None = None, size: int = SIZE, ss: int = 5) -> np.ndarray:
    """The mark's front silhouette as coverage (size x size, the reference's frame scaled to `size`). An odd `ss`
    keeps a pixel's coverage off 0.5 exactly, so the 0.5 threshold never ties on an edge through sample centres."""
    k = size / SIZE
    return coverage([pc.outline() * k for pc in pieces(p).values()], size, ss)


def largest_region(mask: np.ndarray, seed: tuple[int, int] | None = None) -> np.ndarray:
    """The 4-connected region of `mask` holding `seed` (row, col), else its largest (flood fill, numpy only)."""
    if seed is None:
        # the region with the most pixels: flood from each unvisited pixel until the mask is used up
        left, best = mask.copy(), np.zeros_like(mask)
        while left.any():
            r = _flood(left, tuple(np.argwhere(left)[0]))
            if r.sum() > best.sum():
                best = r
            left &= ~r
            if best.sum() > left.sum():
                break
        return best
    return _flood(mask, seed)


def _flood(mask: np.ndarray, seed) -> np.ndarray:
    reg = np.zeros_like(mask)
    reg[seed] = True
    while True:
        g = reg.copy()
        g[1:] |= reg[:-1]
        g[:-1] |= reg[1:]
        g[:, 1:] |= reg[:, :-1]
        g[:, :-1] |= reg[:, 1:]
        g &= mask
        if (g == reg).all():
            return reg
        reg = g


def reference(path: Path = REFERENCE, threshold: float = 0.5) -> np.ndarray:
    """mark.png's silhouette: alpha > threshold, the mark's own connected region (the dust specks go)."""
    from .png import read_png

    a = read_png(path)[..., 3] / 255.0
    return largest_region(a > threshold)


def iou(a: np.ndarray, b: np.ndarray) -> float:
    """Intersection over union of two masks (or coverages, thresholded at 0.5)."""
    a = a > 0.5 if a.dtype != bool else a
    b = b > 0.5 if b.dtype != bool else b
    return float((a & b).sum() / max(1, (a | b).sum()))
