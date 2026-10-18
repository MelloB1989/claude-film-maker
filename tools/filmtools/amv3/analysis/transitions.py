"""Summarise ref_metrics.py output per transition window and per hold (REFS.md tables).

Usage: python transitions.py <metrics.csv> <cuts.json> [--holds]
cuts.json: [{"id": "c08", "w0": 210, "cut": 216, "w1": 232, "type": "..."}, ...]  (frames inclusive)

Per window it prints the per-frame speed trace (z = 100 * ln s, % zoom per frame; + = push in), roll deg/frame, pan
px/frame, sharpness relative to the clean frame before w0, luma, R/B split, and flags frames where tracking failed
(inlier ratio < 0.15 = smeared/cut frames: their motion values are not measurements).
Ease fit: frames from 10 % of the peak speed to the peak (attack) and from the peak down to 10 % (settle), and the
per-frame decay ratio of the speed on the exit side (expo-out: speed(n+1) = k * speed(n)).
"""
import csv
import json
import math
import sys


def load(path):
    rows = {}
    for r in csv.DictReader(open(path)):
        d = {}
        for k, v in r.items():
            try:
                d[k] = float(v)
            except ValueError:
                d[k] = float("nan")
        rows[int(d["f"])] = d
    return rows


def speed(r):
    """Combined picture speed in 'percent of frame per frame': zoom %, pan as % of width, roll as edge px %."""
    if r["sim_inl"] != r["sim_inl"] or r["sim_inl"] < 0.15:
        return None
    z = 100 * math.log(max(r["sim_s"], 1e-3))
    p = 100 * math.hypot(r["sim_tx"], r["sim_ty"]) / 1350
    rr = 100 * math.radians(r["sim_rot"]) * 0.5  # roll as px at the frame edge / width
    return math.copysign(math.sqrt(z * z + p * p + rr * rr), 1)


def window(R, c):
    w0, w1, cut = c["w0"], c["w1"], c["cut"]
    ref = R.get(w0 - 1) or R[w0]
    out = [f"### {c['id']}  {c.get('type', '')}  window {w0}-{w1}, cut {cut}"]
    out.append("f | z %/f | roll deg/f | pan px/f (x,y) | sharp rel | luma | CA px (rad/lat) | track")
    sp = {}
    for f in range(w0, w1 + 1):
        r = R.get(f)
        if not r:
            continue
        ok = r["sim_inl"] == r["sim_inl"] and r["sim_inl"] >= 0.15
        z = 100 * math.log(max(r["sim_s"], 1e-3))
        s = speed(r)
        if s is not None:
            sp[f] = s
        out.append(f"{f} | {z:+.1f} | {r['sim_rot']:+.2f} | {r['sim_tx']:+.0f},{r['sim_ty']:+.0f} | "
                   f"{r['sharp'] / max(ref['sharp'], 1):.2f} | {r['luma']:.0f} | {r['ca_rad']:.1f}/{r['ca_lat']:.1f} | "
                   f"{'ok' if ok else 'SMEAR'}")
    pre = {f: v for f, v in sp.items() if f < cut}
    post = {f: v for f, v in sp.items() if f >= cut}
    if pre:
        fp = max(pre, key=pre.get)
        pk = pre[fp]
        a = [f for f in sorted(pre) if f <= fp and pre[f] >= 0.1 * pk]
        out.append(f"attack: peak {pk:.1f} %/f at f{fp}, from 10 % at f{a[0] if a else fp} ({fp - (a[0] if a else fp)} f)")
    if post:
        fq = max(post, key=post.get)
        pk = post[fq]
        s10 = next((f for f in sorted(post) if f > fq and post[f] <= 0.1 * pk), None)
        ks = [post[f + 1] / post[f] for f in sorted(post) if f >= fq and f + 1 in post and post[f] > 0.5]
        k = sum(ks) / len(ks) if ks else float("nan")
        out.append(f"settle: B speed {pk:.1f} %/f at f{fq}, 10 % at f{s10} ({(s10 - fq) if s10 else '>' + str(w1 - fq)} f), "
                   f"decay k = {k:.2f}/f")
    return "\n".join(out)


def holds(R, cuts, fps=30):
    out = ["hold | frames | zoom %/s (mean, min..max) | roll deg/s | pan px/s | still frames (speed < 0.3 %/f)"]
    cs = sorted(cuts, key=lambda c: c["w0"])
    for a, b in zip(cs, cs[1:]):
        f0, f1 = a["w1"] + 1, b["w0"] - 1
        if f1 - f0 < 3:
            continue
        zs, rs, ps, still = [], [], [], 0
        for f in range(f0, f1 + 1):
            r = R.get(f)
            if not r or r["sim_inl"] != r["sim_inl"] or r["sim_inl"] < 0.15:
                continue
            zs.append(100 * math.log(r["sim_s"]))
            rs.append(r["sim_rot"])
            ps.append(math.hypot(r["sim_tx"], r["sim_ty"]))
            if (speed(r) or 0) < 0.3:
                still += 1
        if zs:
            out.append(f"{a['id']}->{b['id']} | {f0}-{f1} | {fps * sum(zs) / len(zs):+.0f} ({fps * min(zs):+.0f}..{fps * max(zs):+.0f}) | "
                       f"{fps * sum(rs) / len(rs):+.1f} | {fps * sum(ps) / len(ps):.0f} | {still}/{len(zs)}")
    return "\n".join(out)


def main():
    R = load(sys.argv[1])
    cuts = json.load(open(sys.argv[2]))
    for c in cuts:
        print(window(R, c))
        print()
    if "--holds" in sys.argv:
        print(holds(R, cuts))


if __name__ == "__main__":
    main()
