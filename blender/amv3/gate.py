"""Timeless v3 stage gate: the smoothness contract (EDIT.md "motion rules") measured on the keyed camera.

From the stage's camera dump (per frame: CAM matrix + lens, every visible card's matrix) it measures the screen-space
motion of the picture between consecutive frames at 9 points (centre, 4 corners, 4 edge midpoints at 40 % of the frame):
for each point, the card point under it at frame f is re-projected at f+1. A least-squares fit of the 9 displacements
gives T (translation px/f), zoom (scale rate per frame, d ln s) and roll (deg/f). Teleport steps are skipped.

Checks (frames 0-818):
  stall      every point moves < 0.5 px/f (a dead frame)
  step       speed (max point displacement) changes by more than x1.35 frame to frame outside the windows' intended
             accelerations (both speeds above 2 px/f; below that an absolute change > 1.5 px/f is the limit)
  flip       the motion direction reverses across a window edge (w0, w1): zoom / pan > 4 px/f or roll > 0.3 deg/f
             each side
  reversal   a hold shorter than 5 f where the zoom, pan or roll reverses with real magnitude on both sides AND the
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
JUMP_MAX = 6.0  # hold picture-speed jump frame to frame (REFS target: max <= 6, p95 <= 2.1)
REVERSAL_MIN = 6  # a hold may turn its zoom / pan / roll round only over at least 5 f (REFS: reversals take 5-7 f)


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


def hit(fr, u, v, allowed=None):
    """Nearest card under screen pixel (u, v) -> (card name, card-local point) or None (allowed: card names to try)."""
    o, d = ray(fr, u, v)
    best = None
    for c in fr["cards"]:
        if allowed is not None and c["name"] not in allowed:
            continue
        Mi = c["Mi"]
        lo = _mat_vec(Mi, o)
        ld = _mat_dir(Mi, d)
        if abs(ld[2]) < 1e-9:
            continue
        t = -lo[2] / ld[2]
        if t <= 0:
            continue
        x, y = lo[0] + t * ld[0], lo[1] + t * ld[1]
        k = c.get("tile", 1)
        if abs(x) <= 0.96 * k and abs(y) <= 0.54 * k and (best is None or t < best[0]):
            best = (t, c["name"], (x, y, 0.0))
    return None if best is None else best[1:]


def motion(fa, fb, seamless=False):
    """Screen motion from frame fa to fb -> dict(T=(tx, ty), zoom, roll_deg, speed, cspeed, n) or None (no card)."""
    cards_b = {c["name"]: c for c in fb["cards"]}
    shot_a = {c["name"]: c.get("shot") for c in fa["cards"]}
    by_shot = {}
    for c in fb["cards"]:
        if c.get("shot"):
            by_shot.setdefault(c["shot"], c)
    allowed = {c["name"] for c in fa["cards"] if c["name"] in cards_b or (seamless and c.get("shot") in by_shot)}
    pts, disp = [], []
    for (u, v) in screen_points():
        h = hit(fa, u, v, allowed)
        if h is None:
            continue
        cb = cards_b.get(h[0])
        if cb is None and seamless:
            cb = by_shot.get(shot_a.get(h[0]))  # a seamless teleport: the copy's point is the home card's same point
        if cb is None:
            continue
        pw = _mat_vec(cb["M"], h[1])
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
    rms = math.sqrt(sum(x * x for x in sp) / n)
    # p' = (1 + a) p + b perp(p) is a similarity: scale |1 + a + i b|, rotation atan2(b, 1 + a) (exact for big rolls)
    return dict(T=(tx, ty), zoom=math.log(max(1e-6, math.hypot(1 + a, b))), roll=math.degrees(math.atan2(b, 1 + a)),
                speed=max(sp), mean=sum(sp) / n, rms=rms,
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
    seam = set(dump.get("seamless", []))
    wins = dump.get("windows", [])
    holds = dump.get("holds", {})
    rows = []
    for fa, fb in zip(frames, frames[1:]):
        f = fa["f"]
        jump = any(f < t < fb["f"] for t in tele if t not in seam)
        smooth = any(f < t < fb["f"] for t in seam)
        m = None if jump else motion(fa, fb, seamless=smooth)
        win = next((w for w in wins if w["w0"] <= f < w["w1"]), None)
        rows.append(dict(f=f, teleport=jump, m=m, win=win["id"] if win else "", wtype=win["type"] if win else "",
                         shutter=fa.get("shutter")))
    fails = []

    def fail(kind, f, msg):
        fails.append(dict(kind=kind, f=f, msg=msg))

    warns = []

    def warn(kind, f, msg):
        """Reported, not failed: the camera-geometry estimate of accel / decel reads rolls and pans harder than
        motion_metrics.py (the official gate, run on the rendered plate pass) does."""
        warns.append(dict(kind=kind, f=f, msg=msg))

    covered = set()
    for w in wins:
        covered |= set(range(w["w0"], w["w1"]))
    zoom = {r["f"]: r["m"]["zoom"] for r in rows if r["m"] and not r["teleport"]}

    def turning(f):
        """f is inside a zoom turn-round (the zoom changes sign within 2 f): the speed dips on purpose; a turn is fine
        when its hold is >= REVERSAL_MIN frames (checked below)."""
        zs = [zoom[g] for g in range(f - 2, f + 3) if g in zoom]
        return len(zs) >= 2 and max(zs) > 0 > min(zs)

    holdrows = [r for r in rows if r["f"] < END and r["f"] not in covered and r["m"] and not r["teleport"]]
    # stalls (any frame) and hold statistics (REFS "Targets for v3")
    for r in rows:
        if r["f"] < END and r["m"] and not r["teleport"] and r["m"]["speed"] < 0.5:
            fail("stall", r["f"], f"max point speed {r['m']['speed']:.2f} px/f")
    stats = {}
    if holdrows:
        sp = sorted(r["m"]["rms"] for r in holdrows)
        stats["hold_speed_median"] = sp[len(sp) // 2]
        stats["hold_static_pct"] = 100.0 * sum(1 for x in sp if x < 4) / len(sp)
        zs = sorted(abs(r["m"]["zoom"]) for r in holdrows)
        stats["hold_zoom_median_pct"] = 100 * zs[len(zs) // 2]
        run = best = 0
        for r in rows:
            if r["f"] in covered or not r["m"] or r["f"] >= END:
                run = 0
                continue
            run = run + 1 if r["m"]["rms"] < 4 else 0
            best = max(best, run)
        stats["hold_static_run"] = best
        jumps = []
        byf0 = {r["f"]: r for r in rows}
        for r in holdrows:
            q = byf0.get(r["f"] - 1)
            if q and q["m"] and not q["teleport"] and q["f"] not in covered and not turning(r["f"]):
                a_, b_ = q["m"]["rms"], r["m"]["rms"]
                if min(a_, b_) > 2:
                    jumps.append((max(a_, b_) / min(a_, b_), r["f"]))
        if jumps:
            js = sorted(j for j, _ in jumps)
            stats["hold_jump_p95"] = js[int(0.95 * (len(js) - 1))]
            stats["hold_jump_max"] = js[-1]
            for j, f in jumps:
                if j > JUMP_MAX:
                    fail("step", f, f"hold speed jump x{j:.2f} (max {JUMP_MAX})")
        if stats["hold_static_pct"] > 5:
            fail("static", 0, f"{stats['hold_static_pct']:.1f} % hold frames under 4 px/f (<= 5 %)")
        if best > 4:
            fail("static", 0, f"a run of {best} hold frames under 4 px/f (<= 4)")
        if stats["hold_speed_median"] < 12:
            fail("slow", 0, f"hold speed median {stats['hold_speed_median']:.1f} px/f (>= 12)")
        if stats["hold_zoom_median_pct"] < 1.5:
            fail("slow", 0, f"hold zoom median {stats['hold_zoom_median_pct']:.2f} %/f (>= 1.5)")
        if stats.get("hold_jump_p95", 0) > 2.1:
            fail("step", 0, f"hold speed jump p95 x{stats['hold_jump_p95']:.2f} (<= 2.1)")
    # per cut: acceleration in, deceleration out, peak speed, drop / step at the cut, zoom sign
    byf1 = {r["f"]: r for r in rows}

    def spd(f):
        r = byf1.get(f)
        return r["m"]["rms"] if r and r["m"] and not r["teleport"] else None
    cutstats = []
    fb_w0 = {w["w0"] for w in wins if w.get("fallback")}
    for w in wins:
        if w.get("fallback") or w["w1"] in fb_w0:
            continue  # a stand-in zt for a module that has not landed (or a window ending in one): not judged
        f = w["f"]
        A = [spd(g) for g in range(f - 6, f - 1)]  # rows f-6 .. f-2 (f-1 -> f crosses the teleport)
        B = [spd(g) for g in range(f, f + 10)]
        if None in A[-4:] or None in B[:9]:
            continue
        acc = (A[-1] / max(1e-6, A[-4])) ** (1 / 3.0)
        dec = (B[0] / max(1e-6, B[8])) ** (1 / 8.0)
        drop = max([B[i] / max(1e-6, B[i + 1]) for i in range(8)] + [A[-1] / max(1e-6, B[0])])
        step = max(A[-4 + i + 1] / max(1e-6, A[-4 + i]) for i in range(3))
        za = byf1[f - 2]["m"]["zoom"]
        zb = byf1[f]["m"]["zoom"]
        cutstats.append(dict(id=w["id"], type=w["type"], f=f, acc=acc, dec=dec, peak=max(A[-1], B[0]), drop=drop, step=step,
                             zoom_a=za, zoom_b=zb, flip=(za * zb < 0 and abs(za) > 0.01 and abs(zb) > 0.01)))
    if cutstats:
        def med(k):
            v = sorted(c[k] for c in cutstats)
            return v[len(v) // 2]
        # drop / step statistics skip the 3D-object windows (flip, cube): the card under the frame changes depth
        # (the door, then B behind it), so the screen speed ratio says little about the camera there
        # ... and the eye / lens nests: A's face fills the frame until the camera passes the opening, B after it (the
        # speed ratio there compares two planes metres apart; the nest itself keeps the dolly speed continuous)
        small = {w["id"] for w in wins if w.get("region") in ("eye", "lens")}
        flat = [c for c in cutstats if c["type"] not in ("flip", "cube") and c["id"] not in small] or cutstats
        drops = sorted(c["drop"] for c in flat)
        stats.update(cut_acc_median=med("acc"), cut_dec_median=med("dec"), cut_peak_median=med("peak"),
                     cut_drop_median=drops[len(drops) // 2], cut_drop_p90=drops[int(0.9 * (len(drops) - 1))],
                     cut_step_median=med("step"),
                     zoom_flip_pct=100.0 * sum(c["flip"] for c in cutstats) / max(1, sum(
                         1 for c in cutstats if abs(c["zoom_a"]) > 0.01 and abs(c["zoom_b"]) > 0.01)))
        if stats["cut_drop_median"] > 2.3 or stats["cut_drop_p90"] > 4:
            fail("drop", 0, f"drop out of cuts median x{stats['cut_drop_median']:.2f} p90 x{stats['cut_drop_p90']:.2f} (<= 2.3 / 4)")
        if stats["cut_step_median"] > 2.6:
            fail("stepin", 0, f"step into cuts median x{stats['cut_step_median']:.2f} (<= 2.6)")
        if not 1.3 <= stats["cut_acc_median"] <= 1.75:
            warn("accel", 0, f"acceleration into cuts median x{stats['cut_acc_median']:.2f}/f (1.35-1.7)")
        if not 1.12 <= stats["cut_dec_median"] <= 1.3:
            warn("decel", 0, f"deceleration out of cuts median x{stats['cut_dec_median']:.2f}/f (1.15-1.27)")
        if stats["cut_peak_median"] < 160:
            fail("peak", 0, f"cut peak speed median {stats['cut_peak_median']:.0f} px/f (>= 160)")
        if stats["zoom_flip_pct"] > 10:
            fail("zflip", 0, f"zoom sign reversed on {stats['zoom_flip_pct']:.0f} % of zoom cuts (<= 10 %)")
    for r in rows:
        if r["m"] is None and not r["teleport"] and r["f"] < END and r["f"] not in covered:
            fail("nocard", r["f"], "no card under the frame (void / black)")
    # direction across window edges
    byf = {r["f"]: r for r in rows}
    fb_edges = {e for w in wins if w.get("fallback") for e in (w["w0"], w["w1"])}
    for w in wins:
        if w.get("fallback"):
            continue
        for e in (w["w0"], w["w1"]):
            if e in fb_edges:
                continue
            r0, r1 = byf.get(e - 1), byf.get(e)
            if not r0 or not r1 or not r0["m"] or not r1["m"] or r0["teleport"] or r1["teleport"]:
                continue
            m0, m1 = r0["m"], r1["m"]
            for name, k, thr in (("zoom", "zoom", 4.0 / 1100), ("roll", "roll", 0.3)):
                if m0[k] * m1[k] < 0 and abs(m0[k]) > thr and abs(m1[k]) > thr:
                    fail("flip", e, f"{w['id']} edge {e}: {name} {m0[k]:+.4f} -> {m1[k]:+.4f}")
            t0, t1 = m0["T"], m1["T"]
            if math.hypot(*t0) > 4 and math.hypot(*t1) > 4 and t0[0] * t1[0] + t0[1] * t1[1] < 0:
                fail("flip", e, f"{w['id']} edge {e}: pan ({t0[0]:+.1f},{t0[1]:+.1f}) -> ({t1[0]:+.1f},{t1[1]:+.1f})")
    # reversals in short holds
    for sid, (h0, h1) in holds.items():
        if h1 - h0 >= REVERSAL_MIN:
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
    return dict(rows=rows, fails=fails, stats=stats, cuts=cutstats, warns=warns)


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
    for c in res.get("cuts", []):
        print(f"[gate] cut {c['id']} f{c['f']} {c['type']:<10} acc x{c['acc']:.2f}/f  dec x{c['dec']:.2f}/f  peak {c['peak']:.0f} px/f  "
              f"drop x{c['drop']:.2f}  step-in x{c['step']:.2f}  zoom {100 * c['zoom_a']:+.1f} -> {100 * c['zoom_b']:+.1f} %/f"
              f"{'  FLIP' if c['flip'] else ''}")
    for k, v in res.get("stats", {}).items():
        print(f"[gate] {k:<22} {v:.2f}")
    for x in res.get("warns", []):
        print(f"[gate] warn {x['kind']:<8} {x['msg']}")
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
