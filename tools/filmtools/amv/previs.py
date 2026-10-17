"""AMV previs: the whole edit from its plan, in minutes on a CPU, so it can be watched before anything is rendered.

The final picture comes out of Blender (Cycles motion blur, the fitted grade, 3D titles and outro: docs/PIPELINE-AMV.md);
that costs GPU hours. The previs answers "is this the edit?" first: every shot's real footage at its planned time, the
camera's per-frame moves with a few-sample motion blur, the eye-dive hole, the drop portal and its glint, zoom/whip
blurs and the lens bulge on the cuts, flashes and strobes, a stand-in for the Premium Glow grade, letterbox, accents,
every title in its planned style, place and timing (2D stand-ins), the watermark, a 2D stand-in for the 3D outro, and
the final mix. Effects are cheap approximations of the After Effects ones; the geometry and timing are exact (plan.py).

    python -m filmtools.amv.previs --film films/timeless --out out/timeless/amv/previs.mp4 [--scale 0.5] [--mb 3]
           [--frames a-b] [--grade none|glow] [--side-by-side ref.mp4]

`--side-by-side` puts the plan's previs next to another render of the same edit (e.g. the After Effects reference) for
the frames that render covers.
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import plan as P

if os.environ.get("OMP_NUM_THREADS"):
    cv2.setNumThreads(int(os.environ["OMP_NUM_THREADS"]))

FFMPEG = "ffmpeg"


# ---------------------------------------------------------------- colour helpers

def to_lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def to_srgb(x):
    x = np.clip(x, 0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def hexc(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def luma(x):
    return x[..., 0] * 0.2126 + x[..., 1] * 0.7152 + x[..., 2] * 0.0722


# ---------------------------------------------------------------- footage

class Clips:
    """Decoded clips at the previs size, a few kept at a time (shots are mostly sequential)."""

    def __init__(self, plan, size, keep=6):
        self.plan, self.size, self.keep, self.cache = plan, size, keep, {}

    def frames(self, shot):
        key = shot.src
        if key not in self.cache:
            if len(self.cache) >= self.keep:
                self.cache.pop(next(iter(self.cache)))
            w, h = self.size
            cmd = [FFMPEG, "-v", "error", "-i", str(self.plan.clip(shot)), "-vf", f"scale={w}:{h}:flags=area",
                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
            raw = subprocess.run(cmd, capture_output=True, check=True).stdout
            self.cache[key] = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)
        return self.cache[key]

    def at(self, shot, f):
        fr = self.frames(shot)
        i = int(math.floor(shot.remap(f) * 60.0 + 1e-6))
        return fr[min(max(i, 0), len(fr) - 1)]


# ---------------------------------------------------------------- layer effects (cheap stand-ins for AE's)

def exposure(img, ev):
    return img if abs(ev) < 1e-4 else to_srgb(to_lin(img) * (2.0 ** ev))


def saturate(img, amt):
    """amt: AE Hue/Sat master saturation (-100..100)."""
    if abs(amt) < 1e-4:
        return img
    y = luma(img)[..., None]
    return np.clip(y + (img - y) * (1 + amt / 100.0), 0, 1)


def scale_about(img, k, c, border=cv2.BORDER_REFLECT):
    M = np.float32([[k, 0, c[0] * (1 - k)], [0, k, c[1] * (1 - k)]])
    return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR, borderMode=border)


def radial_blur(img, amount, c, brightest=True, n=12):
    """CC Radial Fast Blur stand-in: copies scaled towards the centre; Brightest keeps the max (glowing streaks)."""
    reach = min(0.6, amount / 100.0 * 0.55)
    acc = img.copy()
    mean = img.copy()
    for i in range(1, n):
        s = scale_about(img, 1.0 - reach * i / (n - 1), c)
        mean += s
        if brightest:
            acc = np.maximum(acc, s * (1.0 - 0.35 * i / n) + img * (0.35 * i / n))
    mean /= n
    return 0.5 * acc + 0.5 * mean if brightest else mean


def directional_blur(img, direction, length):
    L = int(max(1, round(length)))
    if L < 2:
        return img
    k = np.zeros((L | 1, L | 1), np.float32)
    k[(L | 1) // 2, :] = 1.0
    R = cv2.getRotationMatrix2D(((L | 1) / 2 - 0.5, (L | 1) / 2 - 0.5), 90 - direction, 1.0)
    k = cv2.warpAffine(k, R, k.shape[::-1])
    k /= max(k.sum(), 1e-6)
    return cv2.filter2D(img, -1, k, borderType=cv2.BORDER_REFLECT)


def bulge(img, fov, c):
    """Optics Compensation (reverse) stand-in: magnify the middle, fov 0..45 -> strength."""
    h, w = img.shape[:2]
    k = min(0.45, fov / 100.0)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xx - c[0], yy - c[1]
    R = math.hypot(w, h) / 2
    r = np.sqrt(dx * dx + dy * dy) / R
    f = 1.0 - k * (1.0 - np.clip(r, 0, 1) ** 2)
    return cv2.remap(img, c[0] + dx * f, c[1] + dy * f, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def ellipse_mask(shape, cx, cy, rx, ry, rot_deg, feather):
    """1 inside a feathered ellipse (feather px, centred on the edge), 0 outside."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = math.radians(rot_deg)
    dx, dy = xx - cx, yy - cy
    u = dx * math.cos(r) + dy * math.sin(r)
    v = -dx * math.sin(r) + dy * math.cos(r)
    rx, ry = max(rx, 1e-3), max(ry, 1e-3)
    d = (np.sqrt((u / rx) ** 2 + (v / ry) ** 2) - 1.0) * min(rx, ry)  # ~signed px distance
    fe = max(feather, 0.5)
    return np.clip(0.5 - d / fe, 0, 1)


# ---------------------------------------------------------------- titles (2D stand-ins in the planned style)

FONTS = {"novax": "chinese rocks rg.otf", "spring": "chinese rocks rg.otf", "chrome": "Exo2-BlackItalic.ttf",
         "neon": "Anton-Regular.ttf", "gold": "BarlowCondensed-BlackItalic.ttf", "extended": "Exo2-BlackItalic.ttf",
         "tag": "Montserrat-Light.ttf", "sub": "Orbitron-Bold.ttf", "mono": "Orbitron-Bold.ttf",
         "light": "Montserrat-Light.ttf", "outro": "Spider-Man.otf.ttf"}
TPAL = {"chrome": ("#F4F4F2", "#D3CDC0", "#7E848D", "#2A2E35", "#FFFFFF"),
        "gold": ("#FCF8EA", "#EDC466", "#B4782F", "#8E561D", "#FFC86A"),
        "ice": ("#F1F6F8", "#AAD1ED", "#335E86", "#152C47", "#7FC8FF"),
        "red": ("#FFF0EC", "#E8323C", "#7A0E12", "#3A0507", "#FF2A3A"),
        "white_chrome": ("#FFFFFF", "#CEDDEB", "#98B8D9", "#525C66", "#DBF2FF")}


class Titles:
    def __init__(self, fonts_dir, sc):
        self.fonts_dir, self.sc = Path(fonts_dir), sc

    @lru_cache(maxsize=64)
    def font(self, key, px):
        return ImageFont.truetype(str(self.fonts_dir / FONTS[key]), max(6, int(px)))

    def mask(self, text, key, size, tracking=0, italic=0.0, hscale=1.0, vscale=1.0):
        """Text coverage (float32 0..1), tracked in 1/1000 em like AE; returns (mask, anchor x, anchor y = baseline centre)."""
        f = self.font(key, size * self.sc)
        adv = [f.getlength(ch) + tracking / 1000.0 * size * self.sc for ch in text]
        tw = int(sum(adv) + size * self.sc) + 8
        asc, desc = f.getmetrics()
        th = asc + desc + 8
        im = Image.new("L", (tw, th), 0)
        d = ImageDraw.Draw(im)
        x = 4.0
        for ch, a in zip(text, adv):
            d.text((x, 4), ch, font=f, fill=255)
            x += a
        m = np.asarray(im, np.float32) / 255.0
        bb = np.argwhere(m > 0.02)
        if not len(bb):
            return m, tw / 2, th / 2
        y0, x0 = bb.min(0)
        y1, x1 = bb.max(0)
        m = m[y0:y1 + 1, x0:x1 + 1]
        if italic or hscale != 1 or vscale != 1:
            h, w = m.shape
            sh = math.tan(math.radians(italic))
            M = np.float32([[hscale, sh * vscale, 0 if sh <= 0 else 0], [0, vscale, 0]])
            M[0, 2] = 0
            ow = int(w * hscale + abs(sh) * h * vscale) + 2
            oh = int(h * vscale) + 2
            # shear about the baseline: the top moves right
            M[0, 1] = -sh * vscale
            M[0, 2] = abs(sh) * h * vscale
            m = cv2.warpAffine(m, M, (ow, oh))
        return m, m.shape[1] / 2, m.shape[0] / 2

    def place(self, canvas_shape, m, cx, cy, scale=1.0, sx=None, sy=None):
        """Coverage `m` centred at (cx, cy) on a canvas, scaled about its centre."""
        h, w = canvas_shape
        sx = scale if sx is None else sx
        sy = scale if sy is None else sy
        M = np.float32([[sx, 0, cx - sx * m.shape[1] / 2], [0, sy, cy - sy * m.shape[0] / 2]])
        return cv2.warpAffine(m, M, (w, h))

    def grad(self, cov, cy, half, pal):
        """Vertical top -> mid -> bot ramp over the text's height, as RGB."""
        h, w = cov.shape
        t = np.clip((np.arange(h, dtype=np.float32) - (cy - half)) / max(2 * half, 1), 0, 1)[:, None, None]
        top, mid, bot = (hexc(c) for c in pal[:3])
        rgb = np.where(t < 0.5, top + (mid - top) * (t / 0.5), mid + (bot - mid) * ((t - 0.5) / 0.5))
        return np.broadcast_to(rgb, (h, w, 3)).astype(np.float32)

    def frame(self, style, spec, k, shape):
        """RGBA (premultiplied, float32) of a title at local frame k, on a canvas of `shape` (h, w) at the previs scale."""
        sc = self.sc
        h, w = shape
        out = np.zeros((h, w, 4), np.float32)
        dur = spec.get("dur", 30)
        if k < 0 or k >= dur:
            return out
        S = spec.get("size", 200)
        px, py = [v * sc for v in spec.get("pos", [960, 540])]
        pal = TPAL.get(spec.get("palette") or {"chrome": "chrome", "gold": "gold", "extended": "ice"}.get(style, "red"),
                       TPAL["red"])

        def over(rgb, a):
            a = np.clip(a, 0, 1)[..., None]
            out[..., :3] = rgb * a + out[..., :3] * (1 - a)
            out[..., 3:] = a + out[..., 3:] * (1 - a)

        def add(rgb, a):
            out[..., :3] += rgb * np.clip(a, 0, None)[..., None]
            out[..., 3:] = np.clip(out[..., 3:] + np.clip(a, 0, 1)[..., None] * 0.5, 0, 1)

        def glow(cov, col, sigma, gain):
            g = cv2.GaussianBlur(cov, (0, 0), max(0.5, sigma * sc))
            add(np.broadcast_to(hexc(col), (h, w, 3)), g * gain)

        def fade(keys):
            return P.keys_lin(keys, k) / 100.0

        def sweep(cov, f0, f1, cy, half):
            if f0 <= k <= f1:
                x = (px - 700 * sc) + (1400 * sc) * (k - f0) / max(f1 - f0, 1)
                xx = np.arange(w, dtype=np.float32)[None, :]
                yy = np.arange(h, dtype=np.float32)[:, None]
                band = np.clip(1 - np.abs((xx - x) + (yy - cy) * 0.35) / (60 * sc), 0, 1)
                add(np.ones((h, w, 3), np.float32), cov * band * 1.2)
                glow(cov * band, "#FFFFFF", 30, 1.5)

        if style == "sub":
            yellow = spec.get("variant") == "yellow"
            S = 50 if yellow else 46
            words = spec["words"]
            full = " ".join(wd for _, wd in words)
            m, _, _ = self.mask(full, "sub", S, tracking=160 if yellow else 120, italic=12)
            cov = self.place(shape, m, 960 * sc, H_ * (0.83 if yellow else 0.86) * sc)
            # reveal word by word in place: cut the line at the end of the last spoken word
            shown = [wd for f0, wd in words if k >= f0]
            if not shown:
                return out
            part = " ".join(shown)
            mp, _, _ = self.mask(part, "sub", S, tracking=160 if yellow else 120, italic=12)
            x0 = int(960 * sc - m.shape[1] / 2 + mp.shape[1] + 2)
            cov[:, max(0, x0):] = 0
            a = fade([[dur - 4, 100], [dur - 1, 0]])
            col = hexc("#FBEA39") if yellow else hexc("#FFFFFF")
            sh = cv2.GaussianBlur(np.roll(cov, (int(2 * sc), int(2 * sc)), (0, 1)), (0, 0), 3 * sc)
            over(np.zeros((h, w, 3), np.float32), sh * 0.8 * a)
            if yellow:
                glow(cov, "#FF9A1A", 8, 0.9 * a)
            over(np.broadcast_to(col, (h, w, 3)), cov * a)
            return out

        if style == "novax":
            pal = TPAL[spec.get("palette", "white_chrome")]
            m, _, _ = self.mask(spec["text"], "novax", S, tracking=40 + 160 * (1 - min(1, k / 8)) ** 3, italic=12, vscale=0.84)
            s = P.keys_lin([[0, 104], [dur - 6, 96], [dur - 1, 112]], k) / 100
            cov = self.place(shape, m, px, py, s)
            half = m.shape[0] * s / 2
            a = fade([[dur - 5, 100], [dur - 1, 0]])
            fill = max(0.0, 0.52 * (1 - k / 22.0)) + 0.15
            glow(cov, pal[4], 26, 0.7 * a)
            over(self.grad(cov, py, half, pal), cov * fill * a * 1.6)
            edge = np.clip(cov - cv2.erode(cov, np.ones((3, 3), np.uint8), iterations=max(1, int(4 * sc))), 0, 1)
            over(np.broadcast_to(hexc(pal[1]), (h, w, 3)), edge * a)
            sweep(cov, 0, 19, py, half)
            if spec.get("tag"):
                tm, _, _ = self.mask(spec["tag"], "light", S * 0.16, tracking=600)
                ty = py + half + 28 * sc
                bar = np.zeros((h, w), np.float32)
                bw, bh = tm.shape[1] / 2 + 30 * sc, tm.shape[0] / 2 + 10 * sc
                cv2.rectangle(bar, (int(px - bw), int(ty - bh)), (int(px + bw), int(ty + bh)), 1.0, -1)
                bar *= (np.random.default_rng(3).random((h, w)) > 0.12)
                over(np.zeros((h, w, 3), np.float32), cv2.GaussianBlur(bar, (0, 0), 1.2) * 0.85 * a)
                over(np.ones((h, w, 3), np.float32), self.place(shape, tm, px, ty) * a * min(1, k / 6))
            return out

        if style in ("chrome", "gold"):
            key = "chrome" if style == "chrome" else "gold"
            m, _, _ = self.mask(spec["text"], key, S, tracking=20 if style == "chrome" else 30)
            if style == "chrome":
                s = P.keys_lin([[0, 235], [1, 170], [2, 132], [3, 112], [4, 104], [5, 100], [dur - 1, 92]], k) / 100
                a = fade([[0, 0], [1, 100]])
                y, sy = py, s
                ext_n, ext_d = 6, (1.6, 2.2)
                sw = (2, 16)
            else:
                s = P.keys_lin([[0, 100], [dur - 1, 104]], k) / 100
                e = 1 - (1 - min(1, k / 8)) ** 3
                y = py + 160 * sc * (1 - e)
                sy = s * P.keys_lin([[0, 40], [8, 100]], k) / 100
                a = fade([[0, 0], [3, 100], [dur - 5, 100], [dur - 1, 0]])
                ext_n, ext_d = 9, (1.2, 1.8)
                sw = (3, 20)
            for i in range(ext_n, 0, -1):
                ce = self.place(shape, m, px + i * ext_d[0] * sc * s, y + i * ext_d[1] * sc * s, s, sy=sy)
                over(np.broadcast_to(hexc(pal[3]), (h, w, 3)), ce * a)
            cov = self.place(shape, m, px, y, s, sy=sy)
            half = m.shape[0] * sy / 2
            if style == "chrome" and spec.get("echo"):
                ec = self.place(shape, m, px, y + S * 0.78 * sc, s, sy=sy)
                edge = np.clip(ec - cv2.erode(ec, np.ones((3, 3), np.uint8), iterations=max(1, int(3 * sc))), 0, 1)
                over(np.broadcast_to(hexc(pal[0]), (h, w, 3)), edge * spec["echo"] / 100.0 * a)
            if style == "gold":
                refl = self.place(shape, m[::-1], px, y + m.shape[0] * sy * 1.02, s, sy=sy)
                yy = np.arange(h, dtype=np.float32)[:, None]
                fadeR = np.clip(1 - (yy - (y + half)) / (m.shape[0] * sy * 0.8), 0, 1)
                over(self.grad(refl, y + half * 3, half, pal), refl * fadeR * 0.35 * a)
            glow(cov, pal[4], 30, 0.6 * a)
            over(self.grad(cov, y, half, pal), cov * a)
            sweep(cov, sw[0], sw[1], y, half)
            if style == "chrome" and k >= dur - 4:
                out[..., :3] *= 2 ** P.keys_lin([[dur - 4, 0], [dur - 1, 1.5]], k)
            if spec.get("sub"):
                sm, _, _ = self.mask(spec["sub"], "light", S * 0.2, tracking=500)
                over(np.ones((h, w, 3), np.float32), self.place(shape, sm, px, y + half + 40 * sc) * a * min(1, k / 8))
            return out

        if style == "neon":
            m, _, _ = self.mask(spec["text"], "neon", S, tracking=40, italic=10)
            s = P.keys_lin([[0, 92], [5, 100], [dur - 1, 108]], k) / 100
            a = fade([[0, 0], [1, 100], [2, 25], [3, 100], [4, 55], [5, 100], [dur - 6, 100], [dur - 5, 30],
                      [dur - 4, 100], [dur - 1, 0]])
            cov = self.place(shape, m, px, py, s)
            edge = np.clip(cov - cv2.erode(cov, np.ones((3, 3), np.uint8), iterations=max(1, int(7 * sc))), 0, 1)
            glow(edge, pal[4], 45, 1.8 * a)
            glow(edge, "#FFFFFF", 12, 1.0 * a)
            over(np.broadcast_to(hexc(pal[1]), (h, w, 3)), cov * 0.55 * a)
            over(np.ones((h, w, 3), np.float32), edge * a)
            if spec.get("sub"):
                sm, _, _ = self.mask(spec["sub"], "light", S * 0.16, tracking=600)
                over(np.ones((h, w, 3), np.float32), self.place(shape, sm, px, py + m.shape[0] * s * 0.62) * a)
            return out

        if style == "spring":
            m, _, _ = self.mask(spec["text"], "spring", S, tracking=25, italic=12)
            t = k / 30.0
            s = (1 + 0.35 * math.exp(-6 * t) * math.cos(14 * t)) * P.keys_lin([[0, 100], [dur - 1, 107]], k) / 100
            if k < 2:
                s *= 0.4 + 0.3 * k
            a = fade([[0, 0], [1, 100], [dur - 4, 100], [dur - 1, 0]])
            over(np.broadcast_to(hexc("#570E0E"), (h, w, 3)), self.place(shape, m, px + 10 * sc, py + 12 * sc, s) * a)
            cov = self.place(shape, m, px, py, s)
            half = m.shape[0] * s / 2
            glow(cov, pal[4], 18, 0.9 * a)
            over(self.grad(cov, py, half, pal), cov * a)
            if spec.get("sub"):
                sm, _, _ = self.mask(spec["sub"], "mono", S * 0.13, tracking=500, italic=10)
                over(np.ones((h, w, 3), np.float32), self.place(shape, sm, px, py + half + 34 * sc) * a * min(1, k / 6))
            return out

        if style == "extended":
            m, _, _ = self.mask(spec["text"], "extended", S, tracking=30, hscale=1.25)
            e = 1 - (1 - min(1, k / 6)) ** 4
            x = px + (-520 * sc) * (1 - e) + 40 * sc * max(0, k - 6) / max(dur - 7, 1)
            a = fade([[0, 0], [2, 100], [dur - 4, 100], [dur - 1, 0]])
            cov = self.place(shape, m, x, py)
            if k < 6:
                cov = directional_blur(cov, 90, P.keys_lin([[0, 120], [3, 50], [6, 0]], k) * sc)
            half = m.shape[0] / 2
            ring = np.zeros((h, w), np.float32)
            rr = int(P.keys_lin([[0, 60], [10, 100], [dur - 1, 110]], k) / 100 * 330 * sc)
            cv2.circle(ring, (int(px), int(py)), rr, 1.0, max(1, int(3 * sc)))
            glow(ring, pal[4], 10, 0.9 * a * 0.45)
            glow(cov, pal[4], 25, 0.8 * a)
            over(self.grad(cov, py, half, pal), cov * a)
            for sx in (-1, 1):  # brackets
                b = np.zeros((h, w), np.float32)
                bx = int(px + sx * (m.shape[1] / 2 + 50 * sc))
                cv2.line(b, (bx, int(py - half - 20 * sc)), (bx, int(py + half + 20 * sc)), 1.0, max(1, int(4 * sc)))
                over(np.ones((h, w, 3), np.float32), b * a * 0.9)
            if spec.get("sub"):
                sm, _, _ = self.mask(spec["sub"], "light", S * 0.33, tracking=600)
                over(np.ones((h, w, 3), np.float32), self.place(shape, sm, px, py + S * 0.62 * sc) * fade([[5, 0], [8, 100], [dur - 4, 100], [dur - 1, 0]]))
            return out

        if style == "tag":
            tr = P.keys_lin([[0, 1150], [7, 0], [dur - 1, 60]], k)
            m, _, _ = self.mask(spec["text"], "tag", S, tracking=350 + tr * 0.3)
            a = fade([[0, 0], [3, 100], [dur - 4, 100], [dur - 1, 0]])
            bar = np.zeros((h, w), np.float32)
            bw = int(min(1, k / 5) * (m.shape[1] / 2 + 40 * sc))
            cv2.rectangle(bar, (int(px - bw), int(py - m.shape[0] * 0.9)), (int(px + bw), int(py + m.shape[0] * 0.9)), 1.0, -1)
            over(np.zeros((h, w, 3), np.float32), cv2.GaussianBlur(bar, (0, 0), 2) * 0.8 * a)
            over(np.ones((h, w, 3), np.float32), self.place(shape, m, px, py) * a)
            if spec.get("sub"):
                sm, _, _ = self.mask(spec["sub"], "mono", S * 0.45, tracking=400, italic=10)
                over(np.ones((h, w, 3), np.float32), self.place(shape, sm, px, py - S * 1.15 * sc) * fade([[4, 0], [8, 100], [dur - 4, 100], [dur - 1, 0]]))
            return out
        return out


H_ = P.H


# ---------------------------------------------------------------- the frame

class Previs:
    def __init__(self, plan, sc, mb, grade, fonts):
        self.plan, self.sc, self.mb, self.grade = plan, sc, mb, grade
        self.w, self.h = int(P.W * sc) // 2 * 2, int(P.H * sc) // 2 * 2
        self.clips = Clips(plan, (self.w, self.h))
        self.titles = Titles(fonts, sc)
        self.matte_cache = {}

    def to_screen(self, M, shot):
        """3x3 affine from the previs-scale canvas of `shot` to previs-scale screen px."""
        _, _, ox, oy = shot.canvas
        sc = self.sc
        A = np.array([[M[0][0], M[0][1], M[0][2]], [M[1][0], M[1][1], M[1][2]], [0, 0, 1]], np.float64)
        Cin = np.array([[1 / sc, 0, -ox], [0, 1 / sc, -oy], [0, 0, 1]])
        Cout = np.diag([sc, sc, 1.0])
        return (Cout @ A @ Cin)[:2]

    def layer(self, shot, f, hole=True):
        """The shot's layer at frame f: premultiplied RGBA on its canvas (previs scale)."""
        sc = self.sc
        img = self.clips.at(shot, f).astype(np.float32) / 255.0
        img = saturate(exposure(img, shot.ev(f)), shot.sat)
        for i, t in enumerate(shot.titles):
            k = f - t["f_in"]
            if 0 <= k < t["spec"].get("dur", 30):
                tt = self.titles.frame(t["style"], t["spec"], k, img.shape[:2])
                img = tt[..., :3] + img * (1 - tt[..., 3:])
                if shot.matte:
                    m = self.matte(shot, f)
                    if m is not None:
                        cut = saturate(exposure(self.clips.at(shot, f).astype(np.float32) / 255.0, shot.ev(f)), shot.sat)
                        img = cut * m[..., None] + img * (1 - m[..., None])
        alpha = np.ones(img.shape[:2], np.float32)
        hh = shot.hole(f) if hole else None
        if hh is not None:
            cx, cy, rx, ry, fe, ex = hh
            alpha *= 1 - ellipse_mask(alpha.shape, cx * sc, cy * sc, (rx + ex) * sc, (ry + ex) * sc, 0, fe * sc)
        w, h, ox, oy = shot.canvas
        pw, ph = int(round(w * sc)), int(round(h * sc))
        l, t = int(round(ox * sc)), int(round(oy * sc))
        img = cv2.copyMakeBorder(img, t, ph - img.shape[0] - t, l, pw - img.shape[1] - l, cv2.BORDER_REFLECT)
        alpha = cv2.copyMakeBorder(alpha, t, ph - alpha.shape[0] - t, l, pw - alpha.shape[1] - l, cv2.BORDER_REFLECT)
        rf = shot.rfb(f)
        if rf:
            img = radial_blur(img, rf[0], ((rf[1] + ox) * sc, (rf[2] + oy) * sc))
        db = shot.dblur(f)
        if db:
            img = directional_blur(img, db[0], db[1] * sc)
        bg = shot.bulge(f)
        if bg:
            img = bulge(img, bg, ((960 + ox) * sc, (540 + oy) * sc))
        return np.dstack([img * alpha[..., None], alpha])

    def matte(self, shot, f):
        i = f - shot.a + int(shot.raw.get("matte_f0") or 0)
        p = self.plan.path(shot.matte).parent / f"{i:05d}.png"
        if not p.exists():
            return None
        m = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        return cv2.resize(m, (self.w, self.h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

    def warp_mb(self, rgba, mats):
        acc = np.zeros((self.h, self.w, 4), np.float32)
        for M in mats:
            acc += cv2.warpAffine(rgba, M, (self.w, self.h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        return acc / len(mats)

    def render(self, f):
        plan, sc = self.plan, self.sc
        out = np.zeros((self.h, self.w, 3), np.float32)
        times = P.shutter_times(f, self.mb) if self.mb > 1 else [f]
        portals = plan.raw.get("portals") or []
        for shot in plan.visible(f):
            rgba = self.layer(shot, f)
            op = shot.opacity(f) / 100.0
            if op <= 0:
                continue
            mats = [self.to_screen(shot.matrix(t), shot) for t in times]
            lay = self.warp_mb(rgba, mats) * op
            out = lay[..., :3] + out * (1 - lay[..., 3:])
            for pt in portals:
                if plan.shots[pt["B"]] is shot and pt["f0"] <= f < pt["f1"]:
                    out = self.portal(pt, f, out, times)
        out = self.glints(f, out)
        # flash (linear light), strobes
        ev = plan.flash_ev(f)
        if abs(ev) > 1e-4:
            out = to_srgb(to_lin(out) * 2 ** ev)
        if f in (plan.raw.get("black") or []):
            out[:] = 0
        if f in (plan.raw.get("invert") or []):
            y = 1 - luma(out)[..., None]
            out = hexc("#010105") + (hexc("#C7DAE8") - hexc("#010105")) * y
        for hf in plan.raw.get("halftone") or []:
            if hf <= f < hf + 2:
                out = self.halftone(out)
        if f < plan.raw["outro"]["f"]:
            if self.grade == "glow":
                out = premium_glow(out, sc)
            out = self.bars_accents(f, out)
            for t in plan.raw.get("titles") or []:
                k = f - t["f_in"]
                if 0 <= k < t["spec"].get("dur", 30):
                    tt = self.titles.frame(t["style"], t["spec"], k, (self.h, self.w))
                    out = tt[..., :3] + out * (1 - np.clip(tt[..., 3:], 0, 1))
            out = self.watermark(f, out)
        else:
            out = self.outro(f)
        return np.clip(out, 0, 1)

    def portal(self, pt, f, out, times):
        sc = self.sc
        A = self.plan.shots[pt["A"]]
        j = f - pt["f0"]
        rgba = self.layer(A, f, hole=False)
        _, _, ox, oy = A.canvas
        # rounded-rect mask on A_in's layer (140 px feather)
        hh, ww = rgba.shape[:2]
        m = np.zeros((hh, ww), np.float32)
        cv2.rectangle(m, (int((ox + 70) * sc), int((oy + 70) * sc)), (int((ox + 1850) * sc), int((oy + 1010) * sc)), 1.0, -1)
        m = cv2.GaussianBlur(m, (0, 0), 50 * sc)
        rgba = rgba * m[..., None]
        rb = P.keys_lin([[pt["f0"], 60], [pt["f0"] + 2, 25], [pt["f0"] + 4, 0]], f)
        if rb > 0.5:
            rgba = radial_blur(rgba, rb, ((960 + ox) * sc, (540 + oy) * sc), brightest=False)
        mats = []
        for t in times:
            jj = t - pt["f0"]
            M = P.affine(P.per_frame(pt["px"], jj), P.per_frame(pt["py"], jj), P.per_frame(pt["s"], jj), P.per_frame(pt["rz"], jj))
            mats.append(self.to_screen(M, A))
        lay = self.warp_mb(rgba, mats) * (P.per_frame(pt["op"], j) / 100.0)
        mt = ellipse_mask((self.h, self.w), pt["mx"][j] * sc, pt["my"][j] * sc, pt["mrx"][j] * sc, pt["mry"][j] * sc,
                          pt["mrot"][j], pt["mfe"][j] * sc)
        lay = lay * mt[..., None]
        return lay[..., :3] + out * (1 - lay[..., 3:])

    def glints(self, f, out):
        sc = self.sc
        for pt in self.plan.raw.get("portals") or []:
            G = pt.get("glint")
            if not G or not (G["f0"] <= f < G["f0"] + len(G["x"])):
                continue
            j = f - G["f0"]
            op = P.keys_lin([[G["f0"], 0], [G["f0"] + 1, 100], [G["f0"] + 4, 100], [G["f0"] + 9, 0]], f) / 100
            s = P.keys_lin([[G["f0"], 60], [G["f0"] + 2, 100], [G["f0"] + 5, 85], [G["f0"] + 11, 40]], f) / 100
            rot = f / 30.0 * 120
            star = np.zeros((self.h, self.w), np.float32)
            for outer, inner, r0 in ((G["r"], G["r"] * 0.10, 0), (G["r"] * 0.5, G["r"] * 0.08, 45)):
                pts = []
                for i in range(8):
                    rr = (outer if i % 2 == 0 else inner) * s * sc
                    a = math.radians(rot + r0 + i * 45 - 90)
                    pts.append([G["x"][j] * sc + rr * math.cos(a), G["y"][j] * sc + rr * math.sin(a)])
                cv2.fillPoly(star, [np.int32(pts)], 1.0, lineType=cv2.LINE_AA)
            glow = cv2.GaussianBlur(star, (0, 0), 20 * sc) * 1.2 + cv2.GaussianBlur(star, (0, 0), 60 * sc) * 0.5
            out = out + (star[..., None] + glow[..., None] * hexc("#9FD8FF")) * op
        return out

    def halftone(self, img, grid=13):
        g = max(3, int(grid * self.sc))
        small = cv2.resize(img, (self.w // g, self.h // g), interpolation=cv2.INTER_AREA)
        out = np.zeros_like(img)
        for yy in range(small.shape[0]):
            for xx in range(small.shape[1]):
                c = small[yy, xx]
                r = int(g * 0.5 * math.sqrt(max(0.0, float(luma(c[None, None])[0, 0])))) + 1
                cv2.circle(out, (xx * g + g // 2, yy * g + g // 2), r, tuple(float(v) for v in c), -1, lineType=cv2.LINE_AA)
        return out

    def bars_accents(self, f, out):
        b = int(round(self.plan.bars(f) * self.sc))
        if b > 0:
            out[:b] = 0
            out[-b:] = 0
        for A in self.plan.raw.get("accents") or []:
            if A["f"] <= f < A["f"] + A["n"]:
                wid = P.keys_lin([[A["f"], 96], [A["f"] + 8, 1250], [A["f"] + A["n"], 1700]], f) * self.sc
                op = P.keys_lin([[A["f"], 100], [A["f"] + A["n"] - 4, 90], [A["f"] + A["n"], 0]], f) / 100
                tint = (f - A["f"]) / A["n"]
                col = np.ones(3, np.float32) * (1 - tint) + hexc("#EEB6BF") * tint
                y = int(A["y"] * self.sc)
                x0, x1 = int(self.w / 2 - wid / 2), int(self.w / 2 + wid / 2)
                hh = max(1, int(9 * self.sc / 2))
                out[max(0, y - hh):y + hh, max(0, x0):x1] = out[max(0, y - hh):y + hh, max(0, x0):x1] * (1 - op) + col * op
        return out

    @lru_cache(maxsize=1)
    def wm_cov(self):
        m, _, _ = self.titles.mask(self.plan.raw.get("watermark", "SAU_EDITZ"), "mono", 30, tracking=250)
        return self.titles.place((self.h, self.w), m, 960 * self.sc, 1050 * self.sc)

    def watermark(self, f, out):
        keys = [[0, 62]]
        for a, b in self.plan.raw.get("wm_hide") or []:
            keys += [[a - 3, 62], [a, 0], [b, 0], [b + 3, 62]]
        op = P.keys_lin(sorted(keys), f) / 100
        cov = self.wm_cov()
        sh = cv2.GaussianBlur(np.roll(cov, (2, 2), (0, 1)), (0, 0), 2)
        out = out * (1 - sh[..., None] * 0.7 * op)
        return out * (1 - cov[..., None] * op) + cov[..., None] * op

    def outro(self, f):
        """2D stand-in for the 3D SAU_EDITZ outro: letters fly in one by one, rings, sweep, pixel dissolve."""
        sc, w, h = self.sc, self.w, self.h
        o = self.plan.raw["outro"]
        k = f - o["f"]
        n = o["n"]
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        r = np.sqrt((xx - w / 2) ** 2 + (yy - h / 2) ** 2) / (h / 2)
        out = (np.clip(1 - r * 0.8, 0, 1) ** 2)[..., None] * hexc("#2A0608") * 1.2
        rings = np.zeros((h, w), np.float32)
        for i, rr in enumerate((0.55, 0.78, 1.02)):
            rad = int(h / 2 * rr * (0.9 + 0.1 * math.sin(k / 9 + i)))
            cv2.circle(rings, (w // 2, h // 2), rad, 1.0, max(1, int(3 * sc)))
        ring_on = min(1, max(0, (k - 6) / 10))
        out += (cv2.GaussianBlur(rings, (0, 0), 6 * sc) * 1.5 + rings)[..., None] * hexc("#FF3040") * 0.5 * ring_on
        text = "SAU_EDITZ"
        order = "EAT_ISDZU"
        font = self.titles.font("outro", 230 * sc)
        adv = [font.getlength(c) * 1.08 if c != "_" else 110 * sc for c in text]
        x = w / 2 - sum(adv) / 2
        used = set()
        for ci, c in enumerate(text):
            oi = next(i for i, ch in enumerate(order) if ch == c and i not in used)
            used.add(oi)
            start = 2 + oi * 3.5
            u = min(1.0, max(0.0, (k - start) / 34.0))
            e = 1 - 2 ** (-10 * u) if u < 1 else 1.0
            rng = np.random.default_rng(ci + 7)
            ang = rng.uniform(0, 2 * math.pi)
            dist = (1 - e) * w * 0.9
            cx = x + adv[ci] / 2 + math.cos(ang) * dist
            cy = h / 2 + math.sin(ang) * dist * 0.6
            scl = 1 + (1 - e) * rng.uniform(1.5, 3.5)
            rot = (1 - e) * rng.uniform(-200, 200)
            x += adv[ci]
            if u <= 0:
                continue
            im = Image.new("L", (int(330 * sc), int(380 * sc)), 0)
            d = ImageDraw.Draw(im)
            if c == "_":
                d.rectangle([110 * sc, 250 * sc, 220 * sc, 280 * sc], fill=255)
            else:
                d.text((165 * sc, 190 * sc), c, font=font, fill=255, anchor="mm")
            m = np.asarray(im, np.float32) / 255.0
            M = cv2.getRotationMatrix2D((m.shape[1] / 2, m.shape[0] / 2), rot, scl)
            M[0, 2] += cx - m.shape[1] / 2
            M[1, 2] += cy - m.shape[0] / 2
            cov = cv2.warpAffine(m, M, (w, h))
            for dd in range(8, 0, -1):  # extruded navy sides
                side = np.roll(cov, (int(dd * 1.2 * sc), int(dd * 0.8 * sc)), (0, 1))
                out = out * (1 - side[..., None]) + hexc("#16203C") * side[..., None]
            face = hexc("#FF2633") * (0.75 + 0.25 * (1 - yy / h))[..., None]
            out = out * (1 - cov[..., None]) + face * cov[..., None]
        sweep_x = (k - 40) / 25.0 * w
        band = np.clip(1 - np.abs(xx - sweep_x + (yy - h / 2) * 0.4) / (90 * sc), 0, 1)
        out += band[..., None] * 0.35 * (luma(out)[..., None] > 0.15)
        bloom = cv2.GaussianBlur(np.clip(out - 0.55, 0, None), (0, 0), 25 * sc)
        out = out + bloom * 1.2
        if k > n - 14:  # pixel dissolve to black
            u = (k - (n - 14)) / 13.0
            g = max(2, int(16 * sc))
            noise = cv2.resize(np.random.default_rng(1).random((h // g + 1, w // g + 1)).astype(np.float32), (w, h),
                               interpolation=cv2.INTER_NEAREST)
            out = out * (noise > u)[..., None]
        return np.clip(out, 0, 1)


def premium_glow(img, sc):
    """A stand-in for the Premium Glow grade (contrast, lifted shadows, crushed blacks, sat 150, teal/orange, bloom)."""
    x = np.clip(img, 0, 1)
    x = x + 0.45 * 0.18 * x * (1 - x) ** 2 * 4                 # shadows +45
    x = np.clip((x - 0.5) * 1.25 + 0.5, 0, 1)                   # contrast 25
    x = np.clip((x - 0.035) / (1 - 0.035), 0, 1)                # blacks -12
    x = np.clip(x * 1.06 + 0.03, 0, 1)                          # brightness 15 / whites 20
    y = luma(x)[..., None]
    x = np.clip(y + (x - y) * 1.5, 0, 1)                        # saturation 150
    sh = np.clip(1 - y * 2.2, 0, 1)
    hi = np.clip(y * 2 - 1, 0, 1)
    x = np.clip(x + sh * np.array([-0.035, 0.02, 0.04], np.float32) + hi * np.array([0.04, 0.012, -0.04], np.float32), 0, 1)
    bright = np.clip(luma(x) - 0.72, 0, None)[..., None] * x
    x = x + cv2.GaussianBlur(bright, (0, 0), 30 * sc) * 0.9
    blur = cv2.GaussianBlur(x, (0, 0), 1.2 * sc + 0.3)
    x = x + (x - blur) * 0.5                                     # sharpen
    h, w = x.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    v = 1 - 0.28 * np.clip(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2 - 0.35, 0, 1)
    return np.clip(x * v[..., None], 0, 1)


def parse_frames(s, dur):
    if not s:
        return list(range(dur))
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [f for f in out if 0 <= f < dur]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--film", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--mb", type=int, default=3, help="motion-blur sub-samples per frame (1 = off)")
    ap.add_argument("--frames", default="")
    ap.add_argument("--grade", default="glow", choices=["glow", "none"])
    ap.add_argument("--fonts", default=None)
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--side-by-side", default=None, help="another render of the edit to show on the right")
    ap.add_argument("--stills", default=None, help="also write these frames as JPGs into --stills-dir")
    ap.add_argument("--stills-dir", default=None)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--workers", type=int, default=1, help="render contiguous ranges in parallel processes, then join")
    a = ap.parse_args(argv)
    if a.workers > 1:
        return parallel(a, argv if argv is not None else sys.argv[1:])

    film = Path(a.film)
    plan = P.load(film)
    pv = Previs(plan, a.scale, a.mb, a.grade, a.fonts or film / "fonts")
    frames = parse_frames(a.frames, plan.dur)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    W2 = pv.w * (2 if a.side_by_side else 1)
    audio = [] if a.no_audio or a.frames else ["-i", str(plan.path(plan.raw["audio"]))]
    cmd = [FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W2}x{pv.h}", "-r", str(plan.fps),
           "-i", "-", *audio, "-map", "0:v", *(["-map", "1:a", "-c:a", "aac", "-b:a", "256k"] if audio else []),
           "-c:v", "libx264", "-preset", "medium", "-crf", str(a.crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart",
           "-shortest" if audio else "-y", str(out)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    ref = None
    if a.side_by_side:
        ref = subprocess.Popen([FFMPEG, "-v", "error", "-i", a.side_by_side, "-vf", f"scale={pv.w}:{pv.h}", "-f", "rawvideo",
                                "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    still_set = set(parse_frames(a.stills, plan.dur)) if a.stills else set()
    t0 = time.time()
    ref_i = 0
    for n, f in enumerate(frames):
        img = (pv.render(f) * 255 + 0.5).astype(np.uint8)
        if ref is not None:
            while ref_i <= f:
                buf = ref.stdout.read(pv.w * pv.h * 3)
                ref_i += 1
            right = np.frombuffer(buf, np.uint8).reshape(pv.h, pv.w, 3) if len(buf) == pv.w * pv.h * 3 \
                else np.zeros((pv.h, pv.w, 3), np.uint8)
            img = np.hstack([img, right])
        enc.stdin.write(img.tobytes())
        if f in still_set and a.stills_dir:
            Path(a.stills_dir).mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(Path(a.stills_dir) / f"{f:04d}.jpg"), img[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 90])
        if n % 60 == 0:
            el = time.time() - t0
            print(f"frame {f} ({n + 1}/{len(frames)}) {el / (n + 1):.2f} s/f", file=sys.stderr, flush=True)
    enc.stdin.close()
    enc.wait()
    if ref is not None:
        ref.kill()
    print(f"wrote {out} ({len(frames)} frames, {time.time() - t0:.0f} s)")


def parallel(a, argv):
    """Split the frames into `workers` contiguous ranges, render each as a silent segment, join, mux the mix."""
    plan = P.load(Path(a.film))
    frames = parse_frames(a.frames, plan.dur)
    n = a.workers
    out = Path(a.out)
    seg_dir = out.parent / (out.stem + "_segs")
    seg_dir.mkdir(parents=True, exist_ok=True)
    base = []
    skip = False
    for x in argv:  # drop the options the segments set themselves
        if skip:
            skip = False
            continue
        if x in ("--workers", "--out", "--frames"):
            skip = True
            continue
        if x.startswith(("--workers=", "--out=", "--frames=")):
            continue
        base.append(x)
    chunks = [frames[i * len(frames) // n:(i + 1) * len(frames) // n] for i in range(n)]
    procs, segs = [], []
    th = str(max(1, (os.cpu_count() or n) // n))   # one worker per core group: numpy/cv2 threads would oversubscribe
    env = {**os.environ, "OMP_NUM_THREADS": th, "OPENBLAS_NUM_THREADS": th, "OPENCV_FOR_THREADS_NUM": th}
    for i, ch in enumerate(c for c in chunks if c):
        seg = seg_dir / f"seg{i:02d}.mp4"
        segs.append(seg)
        procs.append(subprocess.Popen([sys.executable, "-m", "filmtools.amv.previs", *base, "--no-audio",
                                       "--frames", f"{ch[0]}-{ch[-1]}", "--out", str(seg)], env=env))
    if any(p.wait() for p in procs):
        raise SystemExit("a segment failed")
    lst = seg_dir / "list.txt"
    lst.write_text("".join(f"file '{s.resolve()}'\n" for s in segs))
    audio = [] if a.no_audio else ["-i", str(plan.path(plan.raw["audio"]))]
    start = frames[0] / plan.fps
    cmd = [FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst)]
    if audio:
        cmd += ["-ss", f"{start:.4f}", *audio, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "256k", "-shortest"]
    cmd += ["-c:v", "copy", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    print(f"wrote {out} ({len(frames)} frames, {len(segs)} segments)")


if __name__ == "__main__":
    main()
