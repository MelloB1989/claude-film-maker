"""Optical-flow frame interpolation on the CPU: the open-source stand-in for Twixtor Pro.

Two dense flows between the neighbours (OpenCV DIS by default, Farneback as an alternative), img0 -> img1 (F01) and
img1 -> img0 (F10), computed once per pair at a working resolution (<= `work_width`) and reused for every timestep.
To synthesise time t:

1. Forward-splat each flow to time t (a pixel of img0 lands at x + t F01(x); of img1 at x + (1-t) F10(x)). When
   several pixels land on one spot the faster one wins (foreground moves more than background), so the front object
   covers what it passes over. Small cracks (zoom, rounding) are filled from their neighbours.
2. The flow t -> 0 is -t F01 at the splatted position, t -> 1 is -(1-t) F10. Warp both frames with it.
3. Occlusion handling: a pixel nobody splatted to is a disocclusion, seen by the other frame only; where both warps
   exist but disagree (the flows are inconsistent, i.e. an occlusion or a flow failure) the frame nearer in time wins
   and the far one is faded out, which degrades to a plain cross-fade at worst rather than to ghosted warps.

Pure numpy + cv2, no GPU.
"""
from __future__ import annotations

import cv2
import numpy as np

from . import Interpolator

# photometric disagreement (mean abs difference of the two warps, 0..1 values) at which the far frame is faded to 1/e
DISAGREE = 0.07


def _gray(img):
    return cv2.cvtColor(np.clip(img * 255.0 + 0.5, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)


def dense_flow(g0, g1, method="dis"):
    """Flow g0 -> g1 (float32 HxWx2, px) between two uint8 gray images."""
    if method == "farneback":
        return cv2.calcOpticalFlowFarneback(g0, g1, None, 0.5, 4, 21, 5, 7, 1.5, 0)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    return dis.calc(g0, g1, None)


def splat(flow, t, fill_min=6):
    """Forward-splat `flow` (HxWx2) to time t: (flow t -> source = -t * splatted flow, valid mask)."""
    h, w = flow.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    tx = np.rint(xs + t * flow[..., 0]).astype(np.int64)
    ty = np.rint(ys + t * flow[..., 1]).astype(np.int64)
    ok = (tx >= 0) & (tx < w) & (ty >= 0) & (ty < h)
    mag = (flow ** 2).sum(-1)
    order = np.argsort(mag[ok], kind="stable")          # slow first, so the fast (front) pixels overwrite last
    idx = (ty * w + tx)[ok][order]
    out = np.zeros((h * w, 2), np.float32)
    hit = np.zeros(h * w, np.float32)
    out[idx] = flow[ok][order]
    hit[idx] = 1.0
    out = out.reshape(h, w, 2)
    hit = hit.reshape(h, w)
    # fill cracks from the valid neighbours
    cnt = cv2.boxFilter(hit, -1, (5, 5), normalize=False)
    num = cv2.boxFilter(out * hit[..., None], -1, (5, 5), normalize=False)
    crack = (hit == 0) & (cnt >= fill_min)
    out[crack] = num[crack] / cnt[crack][:, None]
    hit[crack] = 1.0
    return -t * out, hit


class FlowInterpolator(Interpolator):
    name = "flow"

    def __init__(self, method="dis", work_width=960):
        self.method = method
        self.work_width = work_width
        self._pair = None            # (img0, img1, F01, F10) for the last pair

    def _flows(self, img0, img1):
        if self._pair is not None and self._pair[0] is img0 and self._pair[1] is img1:
            return self._pair[2], self._pair[3]
        h, w = img0.shape[:2]
        k = min(1.0, self.work_width / w)
        g0, g1 = _gray(img0), _gray(img1)
        if k < 1.0:
            size = (int(round(w * k)), int(round(h * k)))
            g0, g1 = cv2.resize(g0, size, interpolation=cv2.INTER_AREA), cv2.resize(g1, size, interpolation=cv2.INTER_AREA)
        f01, f10 = dense_flow(g0, g1, self.method), dense_flow(g1, g0, self.method)
        self._pair = (img0, img1, f01, f10)
        return f01, f10

    def between(self, img0, img1, ts):
        f01, f10 = self._flows(img0, img1)
        h, w = img0.shape[:2]
        fh, fw = f01.shape[:2]
        up = w / fw
        gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))

        def warp(img, flow, valid):
            if (fh, fw) != (h, w):
                flow = cv2.resize(flow, (w, h), interpolation=cv2.INTER_LINEAR) * up
                valid = cv2.resize(valid, (w, h), interpolation=cv2.INTER_LINEAR)
            mx, my = gx + flow[..., 0], gy + flow[..., 1]
            return cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE), valid

        out = []
        for t in ts:
            t = float(t)
            fa, va = splat(f01, t)
            fb, vb = splat(f10, 1.0 - t)
            wa, va = warp(img0, fa, va)
            wb, vb = warp(img1, fb, vb)
            err = np.abs(wa - wb).mean(-1)
            far = np.exp(-(err / DISAGREE) ** 2)
            # the far-in-time frame fades where the warps disagree; nearer one keeps its weight
            ka = (1.0 - t) * va * (1.0 if t <= 0.5 else far)
            kb = t * vb * (1.0 if t >= 0.5 else far)
            tot = ka + kb
            fallback = tot < 1e-4                        # nobody covers it: plain cross-fade of the unwarped pair
            ka = np.where(fallback, 1.0 - t, ka)
            kb = np.where(fallback, t, kb)
            wa = np.where(fallback[..., None], img0, wa)
            wb = np.where(fallback[..., None], img1, wb)
            tot = ka + kb
            out.append(((wa * ka[..., None] + wb * kb[..., None]) / tot[..., None]).astype(np.float32))
        return out
