"""Neon outline: a white-hot glass tube along the letter outlines with a coloured halo, flickering on.

AE spec (T_neon): Anton (Bebas fallback) italic, no fill, 7 px white stroke, tracking 40, two glows (tight white
thr 20 / r 12 / 1.4, wide palette colour thr 10 / r 45 / 1.8), turbulent-displace jitter (6 px, size 40), opacity flicker
0, 100, 25, 100, 55, 100 over f0-5 (and a dip at dur-5), scale 92 -> 100 (f5) -> 108, sub line (T_subline, f5) below.

Here: the outline is a real round tube (emissive white core, a thin tinted glass shell is implied by the bloom) so the
strokes have the swollen ends and depth of real neon; the halo is two Bloom glares in the palette colours; the jitter is a
per-frame noise displacement of the tube.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from . import common as C
from .common import Glow, Mat, TitleOpts, TitleScene, Word, lin, lin_keys


def render(spec: dict, out_dir: Path, opts: TitleOpts) -> None:
    pal = C.TPAL[spec.get("palette") or "red"]
    S = float(spec.get("size") or 300)
    P = tuple(spec.get("pos") or (C.W / 2, C.H / 2))
    dur = int(spec["dur"])
    text = spec["text"]
    TR = 40

    sc = TitleScene(opts)
    sc.set_environment(color="#000000")
    layer = sc.empty("layer")
    m = Mat("tube")
    m.nt.nodes.remove(m.bsdf)
    a = m.value("alpha", 1.0)
    e = m.value("e", 6.0)
    m.emission_only(m.mix(lin("#FFFFFF"), lin(pal["glow"]), 0.12), e, alpha=a)
    word = Word(sc, text, "anton", S, TR, name="neon", outline_px=7.0, material=m.mat)
    word.attach(layer)
    sub = C.SubLine(sc, spec["sub"], layer, (0, S * 0.58), 5, dur) if spec.get("sub") else None

    comp = sc.build_compositor(glows=[Glow(0.5, 0.18, 1.2, "#FFFFFF"), Glow(0.15, 0.7, 2.4, pal["glow"]),
                                      Glow(0.15, 0.9, 1.4, pal["mid"])])

    def pose(k):
        s = lin_keys([[0, 92], [5, 100], [dur - 1, 108]], k) / 100.0
        flick = lin_keys([[0, 0], [1, 1], [2, .25], [3, 1], [4, .55], [5, 1], [dur - 6, 1], [dur - 5, .3], [dur - 4, 1],
                          [dur - 1, 0]], k)
        C.set_layer(layer, P, s)
        word.pose((C.W / 2, C.H / 2), shear=0.2)
        # AE turbulent displace (6 px, size 40, evolving): a per-letter wobble re-seeded every frame
        rng = random.Random(opts.seed * 1000 + k)
        for ob in word.letters:
            if ob is not None:
                ob.delta_location = (rng.uniform(-3, 3) / C.PX, rng.uniform(-3, 3) / C.PX, 0.0)
                ob.delta_rotation_euler[2] = math.radians(rng.uniform(-0.6, 0.6))
        m.set("alpha", min(1.0, flick * 1.0))
        m.set("e", 6.0 * flick)
        comp.set_glow(0, strength=1.2 * flick)
        comp.set_glow(1, strength=2.4 * flick)
        comp.set_glow(2, strength=1.4 * flick)
        if sub:
            sub.update(k, flick if k > dur - 5 else 1.0)

    C.render_sequence(sc, spec, out_dir, opts, pose)
