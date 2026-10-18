"""Per-frame motion / blur / colour metrics for a reference edit (REFS.md study).

Usage: python ref_metrics.py <frames_dir with f_NNNN.jpg> <out.csv> [--workers 4]

For every frame f (pair f-1 -> f) it writes:
  sim_*   global similarity transform that maps frame f-1 onto frame f (ORB + RANSAC on 1/4-res frames, refined with
          ECC): s = scale ratio, rot = degrees (+ = picture turns clockwise on screen), tx/ty = px at full res,
          inl = inlier ratio (low = cut, smear or subject-dominated motion), ecc = ECC correlation after alignment
  hist    HSV histogram correlation f-1 vs f (low = cut)
  sharp   Laplacian variance at 1/2 res (sharpness; smeared frames drop by 5-50x)
  rad     share of gradient energy that is tangential (radial blur kills radial gradients -> rad > 0.5)
  aniso   structure tensor anisotropy 0..1 (directional blur -> high) and ang = its blur direction in degrees
  ca_px   R vs B channel misregistration at the frame edge (px, full res): radial (scale) part + lateral part
  luma, r, g, b, clip = mean levels and fraction of near-white pixels (flashes / leaks)
"""
import csv
import glob
import math
import os
import sys
from multiprocessing import Pool

import cv2
import numpy as np

ORB = None


def load(path, scale):
    im = cv2.imread(path, cv2.IMREAD_COLOR)
    if scale != 1:
        im = cv2.resize(im, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return im


def similarity(g0, g1):
    """Similarity mapping g0 -> g1 about the frame centre. Returns s, rot_deg, tx, ty (in g pixels), inlier ratio."""
    global ORB
    if ORB is None:
        ORB = cv2.ORB_create(1500, fastThreshold=7)
    k0, d0 = ORB.detectAndCompute(g0, None)
    k1, d1 = ORB.detectAndCompute(g1, None)
    M, inl = None, 0.0
    if d0 is not None and d1 is not None and len(k0) > 12 and len(k1) > 12:
        m = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d0, d1)
        if len(m) >= 12:
            p0 = np.float32([k0[x.queryIdx].pt for x in m])
            p1 = np.float32([k1[x.trainIdx].pt for x in m])
            M, mask = cv2.estimateAffinePartial2D(p0, p1, method=cv2.RANSAC, ransacReprojThreshold=2.0,
                                                  maxIters=4000, confidence=0.995)
            if M is not None:
                inl = float(mask.sum()) / len(m)
    W = np.eye(2, 3, dtype=np.float32) if M is None else M.astype(np.float32)
    ecc = float("nan")
    try:
        ecc, W2 = cv2.findTransformECC(g1.astype(np.float32), g0.astype(np.float32), _inv(W), cv2.MOTION_AFFINE,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5), None, 3)
        W = _inv(W2)
    except cv2.error:
        pass
    h, w = g0.shape
    a, b = W[0, 0], W[1, 0]
    s = math.hypot(a, b)
    rot = math.degrees(math.atan2(b, a))  # image y down: + = clockwise on screen
    c = np.array([w / 2, h / 2])
    cc = W[:, :2] @ c + W[:, 2]
    return s, rot, cc[0] - c[0], cc[1] - c[1], inl, ecc


def _inv(W):
    return cv2.invertAffineTransform(W.astype(np.float32)).astype(np.float32)


def blur_stats(g):
    g = g.astype(np.float32)
    sharp = float(cv2.Laplacian(g, cv2.CV_32F).var())
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    h, w = g.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rx, ry = xx - w / 2, yy - h / 2
    rn = np.sqrt(rx * rx + ry * ry) + 1e-3
    rx, ry = rx / rn, ry / rn
    ring = rn > 0.15 * min(h, w)
    gr = (gx * rx + gy * ry)[ring]
    gt = (-gx * ry + gy * rx)[ring]
    er, et = float((gr ** 2).sum()), float((gt ** 2).sum())
    rad = et / (er + et + 1e-6)
    jxx, jyy, jxy = float((gx * gx).sum()), float((gy * gy).sum()), float((gx * gy).sum())
    lam = math.sqrt((jxx - jyy) ** 2 + 4 * jxy * jxy)
    aniso = lam / (jxx + jyy + 1e-6)
    # dominant gradient orientation; blur runs perpendicular to it
    ang = (math.degrees(0.5 * math.atan2(2 * jxy, jxx - jyy)) + 90) % 180
    return sharp, rad, aniso, ang


def ca_stats(im, full_w):
    """R vs B misregistration. ECC affine of B onto R at 1/2 res; report edge px at full res."""
    b = im[:, :, 0].astype(np.float32)
    r = im[:, :, 2].astype(np.float32)
    h, w = r.shape
    if r.std() < 4:
        return 0.0, 0.0
    W = np.eye(2, 3, dtype=np.float32)
    try:
        _, W = cv2.findTransformECC(r, b, W, cv2.MOTION_AFFINE,
                                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-5), None, 3)
    except cv2.error:
        return float("nan"), float("nan")
    k = full_w / w
    s = math.hypot(W[0, 0], W[1, 0])
    radial = abs(s - 1) * (w / 2) * k
    c = np.array([w / 2, h / 2])
    cc = W[:, :2] @ c + W[:, 2] - c
    lateral = float(math.hypot(*cc)) * k
    return radial, lateral


def frame_row(args):
    i, paths, full_w = args
    im = load(paths[i], 0.5)
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    sharp, rad, aniso, ang = blur_stats(g)
    ca_r, ca_l = ca_stats(im, full_w)
    lum = g.astype(np.float32)
    row = dict(f=i, sharp=sharp, rad=rad, aniso=aniso, ang=ang, ca_rad=ca_r, ca_lat=ca_l, luma=float(lum.mean()),
               b=float(im[:, :, 0].mean()), g=float(im[:, :, 1].mean()), r=float(im[:, :, 2].mean()),
               clip=float((lum > 235).mean()))
    if i > 0:
        p = load(paths[i - 1], 0.25)
        q = load(paths[i], 0.25)
        gp, gq = cv2.cvtColor(p, cv2.COLOR_BGR2GRAY), cv2.cvtColor(q, cv2.COLOR_BGR2GRAY)
        s, rot, tx, ty, inl, ecc = similarity(gp, gq)
        k = full_w / gp.shape[1]
        hp = cv2.calcHist([cv2.cvtColor(p, cv2.COLOR_BGR2HSV)], [0, 1], None, [30, 16], [0, 180, 0, 256])
        hq = cv2.calcHist([cv2.cvtColor(q, cv2.COLOR_BGR2HSV)], [0, 1], None, [30, 16], [0, 180, 0, 256])
        hist = cv2.compareHist(cv2.normalize(hp, None), cv2.normalize(hq, None), cv2.HISTCMP_CORREL)
        row.update(sim_s=s, sim_rot=rot, sim_tx=tx * k, sim_ty=ty * k, sim_inl=inl, sim_ecc=ecc, hist=hist)
    return row


def main():
    src, out = sys.argv[1], sys.argv[2]
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4
    paths = sorted(glob.glob(os.path.join(src, "f_*.jpg")))
    full_w = cv2.imread(paths[0]).shape[1]
    with Pool(workers) as pool:
        rows = pool.map(frame_row, [(i, paths, full_w) for i in range(len(paths))], chunksize=8)
    keys = ["f", "sim_s", "sim_rot", "sim_tx", "sim_ty", "sim_inl", "sim_ecc", "hist", "sharp", "rad", "aniso", "ang",
            "ca_rad", "ca_lat", "luma", "r", "g", "b", "clip"]
    with open(out, "w", newline="") as fh:
        wr = csv.DictWriter(fh, keys, extrasaction="ignore")
        wr.writeheader()
        for r in rows:
            wr.writerow({k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()})


if __name__ == "__main__":
    main()
