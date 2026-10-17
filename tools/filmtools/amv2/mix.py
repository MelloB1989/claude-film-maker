"""v2 audio mix: the first 30 s of the song + the voice cues + SFX placed from the EDL, mastered to -14 LUFS / -1 dBTP.

    PYTHONPATH=tools python -m filmtools.amv2.mix [--edl films/timeless/amv2/edl.json] [--out out/timeless/amv2]
        [--lufs -14] [--tp -1] [--voice-trim DB]

Writes `<out>/mix.wav` (48 kHz, 24-bit stereo), `<out>/cues.csv` (every voice cue, voice word, SFX and the music
envelope events: kind, name, frame, time, gain) and `<out>/mix_report.json`. Everything is placed on exact samples:
an SFX is shifted so its `hit_offset` falls on the start of the EDL frame (frame f = f / fps s), a voice file so its
t = 0 falls on the cue frame. Music and SFX are ducked under the voice with a smooth (raised cosine) sidechain
envelope, the voice is never filtered, and the song ends on a raised-cosine fade (zero slope at both ends) that reaches
exact digital silence on the last sample, so there is no click and no step.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
import scipy.signal as sg
import soundfile as sf
from scipy.ndimage import minimum_filter1d

SR = 48000
ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------- loudness (ITU-R BS.1770-4)

_K1 = (np.array([1.53512485958697, -2.69169618940638, 1.19839281085285]),
       np.array([1.0, -1.69065929318241, 0.73248077421585]))
_K2 = (np.array([1.0, -2.0, 1.0]), np.array([1.0, -1.99004745483398, 0.99007225036621]))


def lufs(x: np.ndarray) -> float:
    """Integrated loudness of a 48 kHz (n, 2) signal, with the absolute (-70) and relative (-10 LU) gates."""
    y = sg.lfilter(*_K2, sg.lfilter(*_K1, x, axis=0), axis=0)
    n, step = int(0.4 * SR), int(0.1 * SR)
    if len(y) < n:
        return -math.inf
    c = np.concatenate([np.zeros((1, y.shape[1])), np.cumsum(y.astype(np.float64) ** 2, axis=0)])
    starts = np.arange(0, len(y) - n + 1, step)
    z = ((c[starts + n] - c[starts]) / n).sum(axis=1)             # channel weights are 1.0 for L and R
    l = -0.691 + 10 * np.log10(z + 1e-20)
    keep = l > -70
    if not keep.any():
        return -math.inf
    rel = -0.691 + 10 * np.log10(z[keep].mean()) - 10
    keep = l > max(-70, rel)
    return float(-0.691 + 10 * np.log10(z[keep].mean()))


def true_peak_db(x: np.ndarray) -> float:
    """Inter-sample peak in dBTP, 4x oversampled."""
    up = sg.resample_poly(x, 4, 1, axis=0)
    return float(20 * np.log10(np.abs(up).max() + 1e-12))


def limit(x: np.ndarray, ceil_db: float, look: float = 0.006) -> np.ndarray:
    """Look-ahead peak limiter on the 4x oversampled peak: the gain is the minimum over +-`look` s, smoothed by a Hann
    window of that length, so it never exceeds what any peak in the window needs and has no steps."""
    ceil = 10 ** (ceil_db / 20)
    up = sg.resample_poly(x, 4, 1, axis=0)
    # the oversampled peak of each sample interval
    pk = np.abs(up).reshape(-1, 4, up.shape[1]).max(axis=(1, 2))[:len(x)]
    g = np.minimum(1.0, ceil / np.maximum(pk, 1e-9))
    L = int(look * SR)
    gm = minimum_filter1d(g, size=2 * L + 1, mode="nearest")
    w = np.hanning(2 * L + 1)
    gs = np.convolve(np.pad(gm, L, mode="edge"), w / w.sum(), "valid")
    return x * gs[:, None]


# ---------------------------------------------------------------- audio helpers

def read_stereo(path: Path) -> np.ndarray:
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    assert sr == SR, f"{path}: {sr} Hz, the mix is {SR} Hz"
    return x if x.shape[1] == 2 else np.repeat(x[:, :1], 2, axis=1)


def db(g: float) -> float:
    return 20 * math.log10(max(g, 1e-9))


def lin(d: float) -> float:
    return 10 ** (d / 20)


def place(bus: np.ndarray, y: np.ndarray, start: int, gain: float = 1.0, fade_out: int = 96):
    """Add `y` into `bus` at sample `start` (may begin before 0 or run past the end; the cut-off tail is not clicky
    because the song end is a fade and the master ends on a fade)."""
    a, b = max(0, start), min(len(bus), start + len(y))
    if b > a:
        bus[a:b] += y[a - start:b - start] * gain


def raised_cos(n: int, up: bool) -> np.ndarray:
    r = 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / max(n - 1, 1))
    return r if up else r[::-1]


def duck_env(n: int, spans: list[tuple[int, int, float]], attack: float = 0.10, release: float = 0.40) -> np.ndarray:
    """Linear gain (n,) from spans (start, end sample, duck dB): fully ducked inside, raised-cosine attack before the
    start and release after the end. Overlapping spans take the deeper duck."""
    d = np.zeros(n)                                    # dB, <= 0
    for s, e, depth in spans:
        a, r = int(attack * SR), int(release * SR)
        env = np.concatenate([depth * raised_cos(a, True), np.full(max(e - s, 0), depth), depth * raised_cos(r, False)])
        lo = s - a
        i0, i1 = max(0, lo), min(n, lo + len(env))
        if i1 > i0:
            d[i0:i1] = np.minimum(d[i0:i1], env[i0 - lo:i1 - lo])
    return 10 ** (d / 20)


# ---------------------------------------------------------------- the cue plan (from the EDL)

# gains are dB relative to the kit file (every kit file peaks at -1 dBFS); the master then sets the loudness.
G = {"whoosh_fast": -13, "whoosh_mid": -13, "whoosh_long": -15, "whip": -12, "web_zip": -12, "glitch_tick": -13,
     "reverse_swell": -9, "riser": -9, "impact_boom": -6, "sub_drop": -9, "shutter_flash": -14, "glint": -15, "hit": -12}
BIG_DROPS = (480, 656, 819)          # impact_boom + sub_drop


def edl_cues(E: dict) -> list[dict]:
    """[{name, f, db, why}]: the SFX for every transition and hit of the EDL (f = the frame the kit's hit lands on)."""
    cues = []
    add = lambda name, f, d=None, why="": cues.append({"name": name, "f": f, "db": G[name] if d is None else d, "why": why})  # noqa: E731
    shots, hits = E["shots"], {int(f): s for f, s in E["hits"]}
    tom_f = next(a["f0"] for a in E["acts"] if a["id"] == "tom")
    # the transition into every shot (picture cut at shot.a), by the leaving shot's exit
    first = shots[0]
    add("whoosh_long", first["a"] + 12, -18, f"open {first['xin']}")
    for A, B in zip(shots, shots[1:]):
        f, x = B["a"], A["xout"]
        w = f"{A['id']}>{B['id']} {x}"
        if x.startswith("whip"):
            add("web_zip" if f >= tom_f else "whip", f, why=w)
        elif x.startswith(("zoom", "spin", "pull")):
            add("whoosh_mid" if x.startswith("spin") else "whoosh_fast", f, why=w)
        elif x == "light_sweep":
            add("whoosh_long", f, -16, w)
        elif x.startswith("glitch"):
            add("glitch_tick", f, why=w)
            add("glitch_tick", f - 3, G["glitch_tick"] - 6, w + " (stutter)")
        elif x == "rift":
            add("reverse_swell", f, why=w)                  # swell peaks on the tear (the cut into Andrew)
        elif x == "drop_portal":
            add("riser", f, why=w)
        # impact: the hit below carries it
    for A in shots:                                          # in-shot effects with a frame
        for fx in A["fx"]:
            name, _, at = fx.partition("@")
            if name == "flash" and at:
                add("shutter_flash", int(at), why=f"{A['id']} flash")
            elif name in ("lens_glint", "lens_flare") and at:
                add("glint", int(at), why=f"{A['id']} {name}")
            elif name == "glass_glint":
                add("glint", A["a"] + 5, why=f"{A['id']} {name}")
    # hits
    for f, s in sorted(hits.items()):
        if f in BIG_DROPS:
            add("impact_boom", f, G["impact_boom"] + (2 if f != 819 else 3), "drop/hit")
            add("sub_drop", f, G["sub_drop"] + (0 if f != 480 else 2), "drop/hit")
            continue
        if E["outro"]["f0"] < f < E["outro"]["f1"] or f in (785, 794):
            if s >= 3.0:
                add("impact_boom", f, G["impact_boom"] - 5, "strong hit")
        add("hit", f, -16 + 4 * (s - 1.6), f"hit {s}")
    add("shutter_flash", 819, -16, "outro shatter")
    add("glint", E["triptych"]["title"]["f"], why="TIMELESS")
    return sorted(cues, key=lambda c: (c["f"], c["name"]))


# ---------------------------------------------------------------- the mix

def build(E: dict, adj=None, log=print):
    """adj: {voice name: (voice trim dB, extra duck dB <= 0)} from the auto balance."""
    adj = adj or {}
    fps, dur = E["fps"], E["dur"]
    N = int(round(dur / fps * SR))
    sfx_dir, voice_dir = Path(E["sfx_dir"]), Path(E["voice_dir"])
    kit = json.loads((sfx_dir / "sfx_kit.json").read_text())
    fs = lambda f: int(round(f / fps * SR))                                  # noqa: E731

    song = read_stereo(Path(E["song"]["file"]))
    t0 = int(round(E["song"].get("t0", 0.0) * SR))
    music = song[t0:t0 + N].astype(np.float64).copy()
    assert len(music) == N, "the song is shorter than the edit"

    # voice bus + ducking spans (a line is ducked from 0.12 s before its first word to 0.30 s after its last)
    meta = {v["name"]: v for v in json.loads((voice_dir / "voice_lines.json").read_text())}
    voice = np.zeros((N, 2))
    spans, lines = [], []
    for v in E["voice"]:
        y = read_stereo(voice_dir / f"{v['name']}.wav").astype(np.float64) * lin(v.get("db", 0))
        s = fs(v["f"])
        vt, xd = adj.get(v["name"], (0.0, 0.0))
        place(voice, y, s, lin(vt))
        w = meta[v["name"]]["words"]
        a, b = s + int((w[0]["t0"] - 0.12) * SR), s + int((w[-1]["t1"] + 0.30) * SR)
        spans.append((a, b, v.get("duck", -6) + xd))
        lines.append({**v, "trim": vt, "xduck": xd, "start": s, "end": min(N, s + len(y)), "words": w})
    env = duck_env(N, spans)

    # music end: raised-cosine fade over the last FADE s, exactly 0 on the last sample
    FADE = 1.4
    nf = int(FADE * SR)
    end = np.ones(N)
    end[N - nf:] = 0.5 + 0.5 * np.cos(np.pi * np.arange(nf) / (nf - 1))
    music *= (env * end)[:, None]

    # SFX
    cues = edl_cues(E)
    sfx = np.zeros((N, 2))
    for c in cues:
        K = kit[c["name"]]
        y = read_stereo(sfx_dir / K["file"]).astype(np.float64)
        c["start"] = fs(c["f"]) - int(round(K["hit_offset"] * SR))
        c["hit_sample"] = fs(c["f"])
        place(sfx, y, c["start"], lin(c["db"]))
    sfx *= (0.5 * (1 + env))[:, None]                                         # SFX duck half as deep as the music
    return {"N": N, "music": music, "voice": voice, "sfx": sfx, "cues": cues, "lines": lines, "env": env, "fps": fps}


def master(stems: dict, target=-14.0, tp=-1.0, log=print):
    """Sum, set the integrated loudness with a limiter in the loop, end on a short cosine to digital silence."""
    N = stems["N"]
    mix = stems["music"] + stems["sfx"] + stems["voice"]
    ceil = tp - 0.25                                            # margin for the 24-bit write and resampling
    tail = int(0.040 * SR)
    fade = np.ones(N)
    fade[N - tail:] = 0.5 + 0.5 * np.cos(np.pi * np.arange(tail) / (tail - 1))
    g = lin(target - lufs(mix))
    for i in range(8):
        y = limit(mix * g, ceil) * fade[:, None]
        L = lufs(y)
        log(f"  master pass {i}: gain {db(g):+.2f} dB -> {L:.2f} LUFS, TP {true_peak_db(y):.2f}")
        if abs(L - target) < 0.05:
            break
        g *= lin(target - L)
    return y, g


def write_cues(path: Path, E: dict, stems: dict):
    fps = stems["fps"]
    rows = []
    for c in stems["cues"]:
        rows.append(["sfx", c["name"], c["f"], round(c["f"] / fps, 4), round(c["start"] / SR, 4), round(c["db"], 1), c["why"]])
    for v in stems["lines"]:
        rows.append(["voice", v["name"], v["f"], round(v["f"] / fps, 4), round(v["start"] / SR, 4), round(v.get("db", 0) + v["trim"], 1),
                     f"duck {v.get('duck', -6) + v['xduck']} dB"])
        for w in v["words"]:
            tw = v["start"] / SR + w["t0"]
            rows.append(["word", w["w"], round(tw * fps, 2), round(tw, 4), round(tw, 4), "", f"{v['name']} reveal f{math.ceil(tw * fps - 1e-9)}"])
    rows.append(["music", "end_fade", E["dur"] - round(1.4 * fps), round((E["dur"] - round(1.4 * fps)) / fps, 4), "", "", "raised cosine to silence at the last sample"])
    rows.sort(key=lambda r: (float(r[2]), r[0]))
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["kind", "name", "frame", "time_s", "start_s", "gain_db", "note"])
        w.writerows(rows)


def voice_ratio(stems: dict) -> list[dict]:
    """Per line: speech level against the ducked music + SFX under it (dB over the active words)."""
    out = []
    for v in stems["lines"]:
        mask = np.zeros(stems["N"], bool)
        for w in v["words"]:
            mask[v["start"] + int(w["t0"] * SR): v["start"] + int(w["t1"] * SR)] = True
        rv = np.sqrt((stems["voice"][mask] ** 2).mean())
        rb = np.sqrt(((stems["music"] + stems["sfx"])[mask] ** 2).mean())
        out.append({"name": v["name"], "voice_over_bed_db": round(db(rv / rb), 1)})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--edl", default=str(ROOT / "films/timeless/amv2/edl.json"))
    ap.add_argument("--out", default=str(ROOT / "out/timeless/amv2"))
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--tp", type=float, default=-1.0)
    ap.add_argument("--voice-trim", type=float, default=None, help="dB added to every voice line (default: auto per line, so each sits >= 4 dB over the bed)")
    a = ap.parse_args(argv)
    E = json.loads(Path(a.edl).read_text())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    adj = {}
    if a.voice_trim is not None:
        adj = {v["name"]: (a.voice_trim, 0.0) for v in E["voice"]}
    else:                                  # each line >= 4 dB over what is under it: first trim the voice (<= +6 dB), then duck deeper
        for _ in range(6):
            stems = build(E, adj)
            r = {x["name"]: x["voice_over_bed_db"] for x in voice_ratio(stems)}
            for v in E["voice"]:
                deficit = 4.0 - r[v["name"]]
                if deficit > 0.2:
                    t, xd = adj.get(v["name"], (0.0, 0.0))
                    use = min(deficit, 6.0 - t)
                    adj[v["name"]] = (t + use, xd - 0.7 * (deficit - use) if deficit > use else xd)
    stems = build(E, adj)
    y, g = master(stems, a.lufs, a.tp, print)
    sf.write(str(out / "mix.wav"), y.astype(np.float32), SR, subtype="PCM_24")
    write_cues(out / "cues.csv", E, stems)
    chk, _ = sf.read(str(out / "mix.wav"), dtype="float64", always_2d=True)
    rep = {"frames": E["dur"], "samples": len(chk), "lufs": round(lufs(chk), 2), "true_peak_dbtp": round(true_peak_db(chk), 2),
           "master_gain_db": round(db(g), 2), "voice_adjust": {k: {"trim_db": round(t, 1), "extra_duck_db": round(x, 1)} for k, (t, x) in adj.items()}, "voice_over_bed": voice_ratio(stems),
           "sfx_count": len(stems["cues"]), "last_sample": float(np.abs(chk[-1]).max())}
    (out / "mix_report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
