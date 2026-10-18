"""Timeless v3 stage gate: the smoothness contract (EDIT.md "motion rules") measured on the keyed camera.

From the stage's camera dump (per frame: CAM matrix + lens, every visible card's matrix) it measures the screen-space
motion of the picture between consecutive frames at 9 points (centre, 4 corners, 4 edge midpoints at 40 % of the frame):
for each point, the card point under it at frame f is re-projected at f+1. A least-squares fit of the 9 displacements
gives T (translation px/f), zoom (scale rate per frame, d ln s) and roll (deg/f). Teleport steps are skipped.

Checks (frames 0-818):
  stall      every point moves < 0.5 px/f (a dead frame)
  step       speed (max point displacement) changes by more than x1.35 frame to frame outside the windows' intended
             accelerations (both speeds above 2 px/f; below that an absolute change > 1.5 px/f is the limit)
  flip       the motion direction reverses across a window edge (w0, w1) by more than 2 px/f each side
  reversal   a hold shorter than 16 f where the zoom, pan or roll reverses with real magnitude on both sides AND the
             picture slows below 1.5 px/f while it turns round (a visible stop/bounce)
  nocard     no card under the frame outside the windows (inside 3D windows the void is intentional)

  python blender/amv3/gate.py out/stage/<name>/camdump.json [--csv gate.csv] [--strict]
"""
import csv
import json
import math
import sys

HERE_W, HERE_H = 1920, 1080
LENS0, SENSOR = 35.0, 36.0
END = 819


def _mat_vec(M, v):
    return [M[i][0] * v[0] + M[i][1] * v[1] + M[i][2] * v[2] + M[i][3] for i in range(3)]


def _mat_dir(M, v):
    return [M[i][0] * v[0] + M[i][1] * v[1] + M[i][2] * v[2] for i in range(3)]


def _inv_rigid(M):
    """Inverse of a camera matrix (rotation + translation, no scale)."""
    R = [[M[j][i] for j in range(3)] for i in range(3)]
    t = [M[0][3], M[1][3], M[2][3]]
    ti = [-(R[i][0] * t[0] + R[i][1] * t[1] + R[i][2] * t[2]) for i in range(3)]
    return [R[0] + [ti[0]], R[1] + [ti[1]], R[2] + [ti[2]], [0, 0, 0, 1]]


def screen_points(w=HERE_W, h=HERE_H):
    cx, cy = w / 2, h / 2
    dx, dy = 0.4 * w, 0.4 * h
    ex, ey = 0.15 * w, 0.15 * h
    return [(cx, cy), (cx - dx, cy - dy), (cx + dx, cy - dy), (cx + dx, cy + dy), (cx - dx, cy + dy),
            (cx - dx, cy), (cx + dx, cy), (cx, cy - dy), (cx, cy + dy),
            (cx - ex, cy - ey), (cx + ex, cy - ey), (cx + ex, cy + ey), (cx - ex, cy + ey)]


def ray(fr, u, v):
    lens = fr.get("lens") or LENS0
    sx, sy = SENSOR, SENSOR * HERE_H / HERE_W
    d = [(u / HERE_W - 0.5) * sx / lens, (0.5 - v / HERE_H) * sy / lens, -1.0]
    C = fr["cam"]
    return [C[0][3], C[1][3], C[2][3]], _mat_dir(C, d)


def project(fr, p):
    Ci = _inv_rigid(fr["cam"])
    x, y, z = _mat_vec(Ci, p)
    if z >= -1e-6:
        return None
    lens = fr.get("lens") or LENS0
    sx, sy = SENSOR, SENSOR * HERE_H / HERE_W
    return ((x / -z * lens / sx + 0.5) * HERE_W, (0.5 - y / -z * lens / sy) * HERE_H)


def hit(fr, u, v):
    """Nearest card under screen pixel (u, v) -> (card name, card-local point) or None."""
    o, d = ray(fr, u, v)
    best = None
    for c in fr["cards"]:
        Mi = c["Mi"]
        lo = _mat_vec(Mi, o)
        ld = _mat_dir(Mi, d)
        if abs(ld[2]) < 1e-9:
            continue
        t = -lo[2] / ld[2]
        if t <= 0:
            continue
        x, y = lo[0] + t * ld[0], lo[1] + t * ld[1]
        if abs(x) <= 0.96 and abs(y) <= 0.54 and (best is None or t < best[0]):
            best = (t, c["name"], (x, y, 0.0))
    return None if best is None else best[1:]


def motion(fa, fb):
    """Screen motion from frame fa to fb -> dict(T=(tx, ty), zoom, roll_deg, speed, cspeed, n) or None (no card)."""
    cards_b = {c["name"]: c for c in fb["cards"]}
    pts, disp = [], []
    for (u, v) in screen_points():
        h = hit(fa, u, v)
        if h is None or h[0] not in cards_b:
            continue
        pw = _mat_vec(cards_b[h[0]]["M"], h[1])
        q = project(fb, pw)
        if q is None:
            continue
        pts.append((u - HERE_W / 2, v - HERE_H / 2))
        disp.append((q[0] - u, q[1] - v))
    if len(pts) < 3:
        return None
    # fit d = T + a p + b perp(p), perp(p) = (-py, px) (screen y down: + b = clockwise on screen)
    n = len(pts)
    S = [[0.0] * 4 for _ in range(4)]
    rhs = [0.0] * 4
    for (px, py), (dx, dy) in zip(pts, disp):
        for row, val in (([1, 0, px, -py], dx), ([0, 1, py, px], dy)):
            for i in range(4):
                rhs[i] += row[i] * val
                for j in range(4):
                    S[i][j] += row[i] * row[j]
    sol = _solve(S, rhs)
    if sol is None:
        return None
    tx, ty, a, b = sol
    sp = [math.hypot(dx, dy) for dx, dy in disp]
    return dict(T=(tx, ty), zoom=math.log(max(1e-6, 1 + a)), roll=math.degrees(b), speed=max(sp), mean=sum(sp) / n,
                cspeed=sp[0] if pts[0] == (0.0, 0.0) else float("nan"), n=n)


def _solve(A, b):
    n = len(b)
    M = [A[i][:] + [b[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            return None
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                k = M[r][c] / M[c][c]
                for j in range(c, n + 1):
                    M[r][j] -= k * M[c][j]
    return [M[i][n] / M[i][i] for i in range(n)]


def analyse(dump, out_csv=None, only=False):
    frames = dump["frames"]
    tele = dump.get("teleports", [])
    wins = dump.get("windows", [])
    holds = dump.get("holds", {})
    rows = []
    for fa, fb in zip(frames, frames[1:]):
        f = fa["f"]
        jump = any(f < t < fb["f"] for t in tele)
        m = None if jump else motion(fa, fb)
        win = next((w for w in wins if w["w0"] <= f < w["w1"]), None)
        rows.append(dict(f=f, teleport=jump, m=m, win=win["id"] if win else "", wtype=win["type"] if win else "",
                         shutter=fa.get("shutter")))
    fails = []

    def fail(kind, f, msg):
        fails.append(dict(kind=kind, f=f, msg=msg))

    covered = set()
    for w in wins:
        covered |= set(range(w["w0"], w["w1"]))
    prev = None
    for r in rows:
        f, m = r["f"], r["m"]
        if r["teleport"]:
            prev = None
            continue
        if f >= END:
            break
        if m is None:
            if f < END and f not in covered:  # inside 3D windows the void around a card is intentional
                fail("nocard", f, "no card under the frame (void / black)")
            prev = None
            continue
        if m["speed"] < 0.5:
            fail("stall", f, f"max point speed {m['speed']:.2f} px/f")
        if prev is not None:
            a, b = prev["speed"], m["speed"]
            in_win = r["win"] != "" and any(w["w0"] <= f - 1 and f < w["w1"] for w in wins)
            if not in_win:
                if a > 2 and b > 2:
                    ratio = max(a, b) / min(a, b)
                    if ratio > 1.35:
                        fail("step", f, f"speed {a:.1f} -> {b:.1f} px/f (x{ratio:.2f})")
                elif abs(a - b) > 1.5:
                    fail("step", f, f"speed {a:.1f} -> {b:.1f} px/f")
        prev = m
    # direction across window edges
    byf = {r["f"]: r for r in rows}
    for w in wins:
        for e in (w["w0"], w["w1"]):
            r0, r1 = byf.get(e - 1), byf.get(e)
            if not r0 or not r1 or not r0["m"] or not r1["m"] or r0["teleport"] or r1["teleport"]:
                continue
            m0, m1 = r0["m"], r1["m"]
            for name, k, thr in (("zoom", "zoom", 2.0 / 1100), ("roll", "roll", 2.0 / 1100 * 57.3)):
                if m0[k] * m1[k] < 0 and abs(m0[k]) > thr and abs(m1[k]) > thr:
                    fail("flip", e, f"{w['id']} edge {e}: {name} {m0[k]:+.4f} -> {m1[k]:+.4f}")
            t0, t1 = m0["T"], m1["T"]
            if math.hypot(*t0) > 2 and math.hypot(*t1) > 2 and t0[0] * t1[0] + t0[1] * t1[1] < 0:
                fail("flip", e, f"{w['id']} edge {e}: pan ({t0[0]:+.1f},{t0[1]:+.1f}) -> ({t1[0]:+.1f},{t1[1]:+.1f})")
    # reversals in short holds
    for sid, (h0, h1) in holds.items():
        if h1 - h0 >= 16:
            continue
        ms = [byf[f]["m"] for f in range(h0, h1) if f in byf and byf[f]["m"] and not byf[f]["teleport"]]
        if len(ms) < 2:
            continue
        slow = min(m["speed"] for m in ms)
        if slow >= 1.5:
            continue  # a component turns round but the picture never slows to a stop: reads as one flowing move
        for name, get, thr in (("zoom", lambda m: m["zoom"], 2.0 / 1100), ("pan x", lambda m: m["T"][0], 2.0),
                               ("pan y", lambda m: m["T"][1], 2.0), ("roll", lambda m: m["roll"], 0.1)):
            v = [get(m) for m in ms]
            if max(v) > thr and min(v) < -thr:
                fail("reversal", h0, f"hold {sid} [{h0},{h1}) {h1 - h0} f: {name} {min(v):+.4f}..{max(v):+.4f}")
    if out_csv:
        with open(out_csv, "w", newline="") as fh:
            wr = csv.writer(fh)
            wr.writerow(["f", "window", "type", "teleport", "speed_max", "speed_mean", "centre", "tx", "ty", "zoom", "roll",
                         "shutter"])
            for r in rows:
                m = r["m"]
                if m:
                    wr.writerow([r["f"], r["win"], r["wtype"], int(r["teleport"]), f"{m['speed']:.2f}", f"{m['mean']:.2f}",
                                 f"{m['cspeed']:.2f}", f"{m['T'][0]:.2f}", f"{m['T'][1]:.2f}", f"{m['zoom']:.5f}",
                                 f"{m['roll']:.3f}", f"{r['shutter']:.3f}" if r["shutter"] is not None else ""])
                else:
                    wr.writerow([r["f"], r["win"], r["wtype"], int(r["teleport"])] + [""] * 7 +
                                [f"{r['shutter']:.3f}" if r["shutter"] is not None else ""])
    return dict(rows=rows, fails=fails)


def print_report(res):
    rows = res["rows"]
    print("[gate]    f  window type          speed  centre      tx      ty     zoom    roll  shutter")
    for r in rows:
        m = r["m"]
        if r["teleport"]:
            print(f"[gate] {r['f']:4d}  {r['win']:<6} {r['wtype']:<12} -- teleport --")
        elif m:
            print(f"[gate] {r['f']:4d}  {r['win']:<6} {r['wtype']:<12} {m['speed']:6.1f} {m['cspeed']:7.1f} {m['T'][0]:7.1f} "
                  f"{m['T'][1]:7.1f} {m['zoom']:+.4f} {m['roll']:+7.2f}  {r['shutter'] or 0:.2f}")
        else:
            print(f"[gate] {r['f']:4d}  {r['win']:<6} {r['wtype']:<12} -- no card --")
    kinds = {}
    for x in res["fails"]:
        kinds[x["kind"]] = kinds.get(x["kind"], 0) + 1
        print(f"[gate] FAIL {x['kind']:<8} f{x['f']}: {x['msg']}")
    print(f"[gate] {'PASS' if not res['fails'] else 'FAIL'}: {len(res['fails'])} issue(s) {kinds}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    with open(a.dump) as fh:
        d = json.load(fh)
    res = analyse(d, a.csv)
    print_report(res)
    sys.exit(3 if a.strict and res["fails"] else 0)
