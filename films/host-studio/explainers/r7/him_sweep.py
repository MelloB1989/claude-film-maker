"""R7 (agent-01): the gate's rows for a list of Performer variants on a body read, in ONE run, for his real skeleton
ON THE BOX (it never leaves the box; this prints only the rows and the times they fire at, no positions).

    cd <r7-body tree>/films/host-studio/explainers
    python3 r7/him_sweep.py --who him --read <his body_read.json> base PALM_DELAY=0.10 PALM_DELAY=0.15,PALM_W=20
    python3 r7/him_sweep.py --who him --read <his body_read.json> --spans base ...   # + the TEST spans 0-179, 422-480

A variant is NAME=VALUE[,NAME=VALUE...] (Performer class attributes; G.NAME sets a gesturekit module constant), or
'base'. Each prints: the FAIL rows (whole take, and the TEST spans with --spans), the right/left hand-minus-upper-arm
lag (median ms) with the 4 segments that lead most (time, ms), the snaps' times per hand, the rest_contact frames'
times (tips_only: tented on the pads, else hovering), palm_to_camera's times.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import gesturekit as G  # noqa: E402
import naturalness as N  # noqa: E402
import perform as PF  # noqa: E402
from arm_track_who import track_of  # noqa: E402

TEST_SPANS = [(0, 179), (422, 480)]


def apply(var: str) -> list:
    """set a variant's attributes; returns the old values to put back, [(target, name, value)]."""
    old = []
    if var == "base":
        return old
    for kv in var.split(","):
        k, v = kv.split("=")
        tgt, name = (G, k[2:]) if k.startswith("G.") else (G.Performer, k)
        was = getattr(tgt, name)
        old.append((tgt, name, was))
        setattr(tgt, name, type(was)(float(v)) if isinstance(was, (int, float)) else eval(v))
        for tune in PF.TUNE_OF.values():  # a presenter's own constant (perform.TUNE_OF) would set it back per Performer
            if name in tune and tgt is G.Performer:
                old.append((tune, name, tune[name]))
                tune[name] = getattr(tgt, name)
    return old


def seg_lag(tk: "N.Take", s: str) -> list:
    """(start s, hand minus upper arm ms) per movement, as Take.lag counts them."""
    up = tk._angspeed([N.sub(f["p"]["lowerarm_" + s], f["p"]["upperarm_" + s]) for f in tk.F])
    fo = tk._angspeed([N.sub(f["p"]["hand_" + s], f["p"]["lowerarm_" + s]) for f in tk.F])
    hd = tk._angspeed([N.hand_frame(f["p"], s)[2] for f in tk.F])
    out = []
    for a, b in tk.segments(s):
        o = [tk._onset(w, max(0, a - 3), b) for w in (up, fo, hd)]
        if None not in o:
            out.append((round(tk.F[a]["t"], 2), round(1000 * (o[2] - o[0]), 1)))
    return out


def why(tk: "N.Take", s: str, t: float) -> str:
    """at a snap (hand s, time t): per frame i-2..i+2 the worst DIP head's speed relative to the wrist (cm/s) split
    into its curl part (in the hand's own frame) and the rest (the hand turning), with the hand's, the forearm's and
    the upper arm's angular speeds (deg/s) and the wrist's speed (cm/s). Speeds only, no positions."""
    i = min(range(len(tk.F)), key=lambda k: abs(tk.F[k]["t"] - t))
    hf = [N.hand_frame(f["p"], s) for f in tk.F]
    hand_w = [max(a, b) for a, b in zip(tk._angspeed([h[0] for h in hf]), tk._angspeed([h[2] for h in hf]))]
    fore_w = tk._angspeed([N.sub(f["p"]["hand_" + s], f["p"]["lowerarm_" + s]) for f in tk.F])
    up_w = tk._angspeed([N.sub(f["p"]["lowerarm_" + s], f["p"]["upperarm_" + s]) for f in tk.F])
    tips = [f"{fn}_03_{s}" for fn in ("thumb",) + N.FINGERS]

    def loc(k, b):  # the DIP head in the hand's own frame
        r = N.sub(tk.F[k]["p"][b], tk.F[k]["p"]["hand_" + s])
        return [N.dot(r, a) for a in hf[k]]

    out = []
    for k in range(max(1, i - 2), min(len(tk.F), i + 3)):
        best = max(tips, key=lambda b: N.norm(N.sub(N.sub(tk.F[k]["p"][b], tk.F[k]["p"]["hand_" + s]),
                                                     N.sub(tk.F[k - 1]["p"][b], tk.F[k - 1]["p"]["hand_" + s]))))
        v = N.norm(N.sub(N.sub(tk.F[k]["p"][best], tk.F[k]["p"]["hand_" + s]),
                         N.sub(tk.F[k - 1]["p"][best], tk.F[k - 1]["p"]["hand_" + s]))) / tk.dt
        curl = N.norm(N.sub(loc(k, best), loc(k - 1, best))) / tk.dt
        out.append(f"{tk.F[k]['t']:.2f} {best.split('_')[0]} v{v:.0f} curl{curl:.0f} hand{hand_w[k]:.0f} "
                   f"fore{fore_w[k]:.0f} up{up_w[k]:.0f} wr{tk.v[s][k]:.0f}")
    return f"{s}@{t}: " + "; ".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("variants", nargs="+")
    ap.add_argument("--who", choices=("her", "him"), required=True)
    ap.add_argument("--read", required=True)
    ap.add_argument("--spans", action="store_true", help="also the TEST spans (sequence frames 0-179, 422-480)")
    ap.add_argument("--why", action="store_true", help="after each line, what moves the fingertip at each snap")
    a = ap.parse_args()
    for var in a.variants:
        old = apply(var)
        try:
            doc = track_of(a.who, Path(a.read))
        finally:
            for tgt, name, v in reversed(old):
                tgt.__setitem__(name, v) if isinstance(tgt, dict) else setattr(tgt, name, v)
        line = [var]
        for spans in ([None, TEST_SPANS] if a.spans else [None]):
            tk = N.Take(doc, spans)
            rep = tk.report()
            fails = [f"{k.replace('move.', '')} {r['value']}" for k, r in N.rows(rep).items() if r["pass"] is False]
            line.append(("TEST " if spans else "WHOLE ") + str(fails))
            if spans is None:
                lg = {s: rep["lag"][s]["hand_minus_upper_ms_p50"] for s in "lr"}
                worst = sorted(seg_lag(tk, "r"), key=lambda x: x[1])[:4]
                rc = rep["rest_contact"]
                line += [f"lag r {lg['r']:.1f} l {lg['l']:.1f} r_lead {worst}",
                         f"snaps l {rep['snaps']['l']['t']} r {rep['snaps']['r']['t']}",
                         f"rest_contact {rc['frames']} (tips_only {rc['tips_only']}) {rc['t']}",
                         f"palm_cam {rep['palm_cam']['t']}"]
        print(" | ".join(line), flush=True)
        if a.why:
            tk = N.Take(doc)
            sn = tk.report()["snaps"]
            for s in "lr":
                for t in sn[s]["t"]:
                    print("  why " + why(tk, s, t), flush=True)
        doc = None


if __name__ == "__main__":
    main()
