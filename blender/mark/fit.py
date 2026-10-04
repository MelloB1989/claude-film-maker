"""Fit the mark's parameters to mark.png and write blender/mark/params.json.

  uv run --project tools python blender/mark/fit.py [--rounds 3]

Starts from params.json (or the traced defaults) and maximises the soft IoU of the model's coverage (5x5 supersampled)
against the reference's own alpha inside the mark's region, with Powell's method, a few rounds; prints the binary IoU
(coverage > 0.5 against alpha > 0.5, the acceptance measure) before and after. The ribbons stay what they are: the
same pieces, paths and terminals, only their numbers move.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mark import geometry as G  # noqa: E402
from mark.png import read_png  # noqa: E402


def flat(p: dict) -> tuple[list[str], np.ndarray]:
    keys, vals = [], []
    for k in sorted(p):
        v = p[k]
        if isinstance(v, list):
            for i, x in enumerate(v):
                keys.append(f"{k}[{i}]")
                vals.append(x)
        else:
            keys.append(k)
            vals.append(v)
    return keys, np.array(vals, float)


def unflat(keys: list[str], x: np.ndarray, like: dict) -> dict:
    p = {k: (list(v) if isinstance(v, list) else v) for k, v in like.items()}
    for k, v in zip(keys, x):
        if k.endswith("]"):
            name, i = k[:-1].split("[")
            p[name][int(i)] = float(v)
        else:
            p[k] = float(v)
    return p


def main(argv=None):
    from scipy.optimize import minimize

    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--ss", type=int, default=5)
    a = ap.parse_args(argv)

    alpha = read_png(G.REFERENCE)[..., 3] / 255.0
    region = G.reference()
    grown = region.copy()  # the region and its anti-aliased rim
    grown[1:] |= region[:-1]
    grown[:-1] |= region[1:]
    grown[:, 1:] |= region[:, :-1]
    grown[:, :-1] |= region[:, 1:]
    soft = np.where(grown, alpha, 0.0)

    p0 = G.load_params()
    keys, x0 = flat(p0)

    def loss(x):
        try:
            c = G.silhouette(unflat(keys, x, p0), ss=a.ss)
        except (ValueError, FloatingPointError, ZeroDivisionError):
            return 1.0
        return 1.0 - np.minimum(c, soft).sum() / np.maximum(c, soft).sum()

    print(f"start: IoU {G.iou(G.silhouette(p0), region):.4f}, soft {1 - loss(x0):.4f}")
    x = x0
    for r in range(a.rounds):
        t = time.time()
        res = minimize(loss, x, method="Powell", options={"xtol": 1e-3, "ftol": 1e-7, "maxfev": 6000})
        x = res.x
        p = unflat(keys, x, p0)
        print(f"round {r + 1}: IoU {G.iou(G.silhouette(p), region):.4f}, soft {1 - res.fun:.4f} "
              f"({res.nfev} evaluations, {time.time() - t:.0f}s)")
    p = unflat(keys, x, p0)
    G.save_params(p)
    for k, v0, v1 in zip(keys, x0, x):
        if abs(v1 - v0) > 0.3:
            print(f"  {k}: {v0:.2f} -> {v1:.2f}")
    print(f"wrote {G.PARAMS}: IoU {G.iou(G.silhouette(p), region):.4f}")


if __name__ == "__main__":
    main()
