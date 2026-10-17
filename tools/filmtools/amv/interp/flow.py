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


class Splatter:
    """Forward-splats one flow field (HxWx2) to any time t. The slow-to-fast pixel order is the same for every t, so
    it is sorted once per flow and reused."""

    def __init__(self, flow, fill_min=6):
        h, w = flow.shape[:2]
        self.h, self.w, self.fill_min = h, w, fill_min
        order = np.argsort((flow ** 2).sum(-1).ravel(), kind="stable")    # slow first: fast (front) pixels land last
        ys, xs = np.divmod(order, w)
        self.x0, self.y0 = xs.astype(np.float32), ys.astype(np.float32)
        self.vec = flow.reshape(-1, 2)[order]

    def at(self, t):
        """(flow t -> source = -t * splatted flow, valid mask) at time t."""
        h, w = self.h, self.w
        tx = np.rint(self.x0 + t * self.vec[:, 0]).astype(np.int32)
        ty = np.rint(self.y0 + t * self.vec[:, 1]).astype(np.int32)
        ok = (tx >= 0) & (tx < w) & (ty >= 0) & (ty < h)
        slot = np.full(h * w, -1, np.int32)                                # scatter the sorted index once, then gather
        slot[(ty * w + tx)[ok]] = np.nonzero(ok)[0].astype(np.int32)
        hit = (slot >= 0).astype(np.float32)
        out = np.where(hit[:, None] > 0, self.vec[np.maximum(slot, 0)], 0.0).astype(np.float32)
        out = out.reshape(h, w, 2)
        hit = hit.reshape(h, w)
        cnt = cv2.boxFilter(hit, -1, (5, 5), normalize=False)               # fill cracks from valid neighbours
        num = cv2.boxFilter(out * hit[..., None], -1, (5, 5), normalize=False)
        crack = (hit == 0) & (cnt >= self.fill_min)
        out[crack] = num[crack] / cnt[crack][:, None]
        hit[crack] = 1.0
        return -t * out, hit


class FlowInterpolator(Interpolator):
    name = "flow"

    def __init__(self, method="dis", work_width=640):
        self.method = method
        self.work_width = work_width
        self._pair = None            # (img0, img1, splatter 0->1, splatter 1->0) for the last pair

    def _flows(self, img0, img1):
        if self._pair is not None and self._pair[0] is img0 and self._pair[1] is img1:
            return self._pair[2], self._pair[3], self._pair[4]
        h, w = img0.shape[:2]
        k = min(1.0, self.work_width / w)
        g0, g1 = _gray(img0), _gray(img1)
        if k < 1.0:
            size = (int(round(w * k)), int(round(h * k)))
            g0, g1 = cv2.resize(g0, size, interpolation=cv2.INTER_AREA), cv2.resize(g1, size, interpolation=cv2.INTER_AREA)
        f01, f10 = dense_flow(g0, g1, self.method), dense_flow(g1, g0, self.method)
        self._pair = (img0, img1, Splatter(f01), Splatter(f10), f01.shape)
        return self._pair[2], self._pair[3], f01.shape

    def between(self, img0, img1, ts):
        sa, sb, (fh, fw, _) = self._flows(img0, img1)
        h, w = img0.shape[:2]
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
            fa, va = sa.at(t)
            fb, vb = sb.at(1.0 - t)
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
