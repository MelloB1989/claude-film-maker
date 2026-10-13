"""Fit a new take's pauses to an old take's rhythm, so the words land where the picture expects them.

At every pause (a gap of 0.12 s or more in either take), silence is inserted or removed at the quietest point of the
new take's gap so the next word starts, relative to the line's first word, where it did in the old take. A gap is
never cut below min(its length, max(0.10 s, 0.6 x the old gap)), never grows by more than 0.6 s, and never grows past
the old gap + 0.15 s (drift is not bought with unnatural pauses). Joins get 4 ms
fades. Within a phrase nothing moves, so the remaining drift is the voice's own pace.

    fit_gaps.py score <takes dir> <paced dir> <line> <old paced take> <new take>... [--weight word=3 ...]
    fit_gaps.py write <takes dir> <paced dir> <line> <old paced take> <new take> <out take>
Run with the tools' environment: cd tools && uv run python ../films/campx-launch/audio/scripts/fit_gaps.py ...
"""
import json
import sys
from pathlib import Path

import numpy as np

from filmtools.wav import read_wav, write_wav

PAUSE, MIN_GAP, MAX_GROW, FADE = 0.12, 0.10, 0.6, 0.004
OVER_OLD = 0.15  # a fitted gap grows to at most the old gap plus this
QUIET_DB = -40.0  # a gap is edited only where it has a 10 ms stretch this quiet (not inside a breath)


def rel(words):
    t0 = words[0]["start"]
    return [w["start"] - t0 for w in words]


def quiet(x, sr, a, b):
    if x is None:
        return True
    s = x[int((a + 0.2 * (b - a)) * sr):int((b - 0.2 * (b - a)) * sr)]
    h = int(0.01 * sr)
    if len(s) < h:
        return False
    rms = min(np.sqrt(np.mean(s[j:j + h] ** 2)) for j in range(0, len(s) - h + 1, h // 2))
    return 20 * np.log10(rms + 1e-12) < QUIET_DB


def plan(old, new, x=None, sr=None):
    """[(boundary index, new gap, target gap)] and the fitted relative word starts."""
    o, n = rel(old), rel(new)
    ops, shift, fitted = [], 0.0, [0.0]
    for i in range(len(new) - 1):
        ng = new[i + 1]["start"] - new[i]["end"]
        og = old[i + 1]["start"] - old[i]["end"]
        if (ng >= PAUSE or og >= PAUSE) and ng >= 0.05 and quiet(x, sr, new[i]["end"], new[i + 1]["start"]):
            want = o[i + 1] - (n[i + 1] + shift)
            lo = min(ng, max(MIN_GAP, 0.6 * og))
            hi = min(ng + MAX_GROW, max(ng, og + OVER_OLD))  # never a pause much longer than the old one
            tgt = float(np.clip(ng + want, lo, hi))
            if abs(tgt - ng) >= 0.005:
                ops.append((i, ng, tgt))
                shift += tgt - ng
        fitted.append(n[i + 1] + shift)
    return ops, fitted


def drift(old, new, weights, x=None, sr=None):
    ops, fitted = plan(old, new, x, sr)
    o = rel(old)
    d = np.array(fitted) - np.array(o)
    w = np.array([weights.get(x["w"].strip(".,'").lower().removesuffix("'s"), 1.0) for x in old])
    end_new = (new[-1]["end"] - new[0]["start"]) + sum(t - g for _, g, t in ops)
    return {"wrms": float(np.sqrt(np.sum(w * d * d) / np.sum(w))), "max": float(np.max(np.abs(d))),
            "end_delta": float(end_new - (old[-1]["end"] - old[0]["start"])),
            "edit_s": float(sum(abs(t - g) for _, g, t in ops)), "ops": len(ops), "per_word": d.tolist()}


def apply(x, sr, words, ops):
    """The audio with each gap moved to its target length, and the words' new times."""
    cuts = []  # (sample, +n insert / -n remove)
    for i, ng, tgt in ops:
        a, b = words[i]["end"], words[i + 1]["start"]
        delta = tgt - ng
        h = int(0.01 * sr)
        ia, ib = int((a + 0.2 * (b - a)) * sr), int((b - 0.2 * (b - a)) * sr)
        if delta > 0:
            e = [np.sum(x[j:j + h] ** 2) for j in range(ia, max(ia + 1, ib - h), h // 2)]
            at = ia + int(np.argmin(e)) * (h // 2) + h // 2
            cuts.append((at, int(round(delta * sr))))
        else:
            r = int(round(-delta * sr))
            lo, hi = int((a + 0.02) * sr), int((b - 0.02) * sr) - r
            if hi <= lo:
                at = int(((a + b) / 2) * sr) - r // 2
            else:
                e = np.convolve(x[lo:hi + r] ** 2, np.ones(r), "valid")
                at = lo + int(np.argmin(e))
            cuts.append((at, -r))
    f = int(FADE * sr)
    down, up = np.linspace(1, 0, f), np.linspace(0, 1, f)
    out, prev = [], 0
    for at, n in sorted(cuts):
        seg = x[prev:at].copy()
        seg[-f:] *= down
        out.append(seg)
        if n > 0:
            out.append(np.zeros(n, dtype=x.dtype))
            prev = at
        else:
            prev = at - n
        x = x.copy()
        x[prev:prev + f] *= up
    out.append(x[prev:])
    y = np.concatenate(out)
    moved = []
    for w in words:
        s = sum(n for at, n in cuts if at / sr <= w["start"]) / sr
        moved.append({**w, "start": round(w["start"] + s, 4), "end": round(w["end"] + s, 4)})
    return y, moved


def main(argv):
    cmd, takes, paced, line, old_k = argv[:5]
    weights = {}
    rest = []
    for a in argv[5:]:
        if a.startswith("--weight="):
            k, v = a.removeprefix("--weight=").split("=")
            weights[k.lower()] = float(v)
        else:
            rest.append(a)
    old = json.loads((Path(paced) / line / f"{old_k}.json").read_text())["words"]
    if cmd == "score":
        for k in rest:
            new = json.loads((Path(takes) / line / f"{k}.json").read_text())["words"]
            x, sr = read_wav(Path(takes) / line / f"{k}.wav")
            r = drift(old, new, weights, x, sr)
            print(f"{line} take {k}: weighted rms {r['wrms']:.3f} s · max {r['max']:.3f} s · end {r['end_delta']:+.3f} s"
                  f" · {r['ops']} gap edits, {r['edit_s']:.2f} s moved")
        return
    k, out_k = rest
    m = json.loads((Path(takes) / line / f"{k}.json").read_text())
    x, sr = read_wav(Path(takes) / line / f"{k}.wav")
    ops, _ = plan(old, m["words"], x, sr)
    y, words = apply(x, sr, m["words"], ops)
    write_wav(Path(takes) / line / f"{out_k}.wav", y, sr)
    meta = {**m, "take": int(out_k), "duration": round(len(y) / sr, 4), "words": words, "derived_from": int(k),
            "edit": [f"gap after {m['words'][i]['w']!r} {g:.2f}s -> {t:.2f}s (fitted to take {old_k})"
                     for i, g, t in ops]}
    (Path(takes) / line / f"{out_k}.json").write_text(json.dumps(meta, indent=1))
    print(line, out_k, meta["edit"], meta["duration"])


if __name__ == "__main__":
    main(sys.argv[1:])
