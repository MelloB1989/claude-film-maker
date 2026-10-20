"""Audit of the v3 mix: loudness, true peak, clipping, voice over bed (vs v2), voice words vs subtitle frames, every SFX
layer on its frame, per-transition SFX lift over the song, a clean end; plus a waveform/spectrogram PNG.

    PYTHONPATH=tools python -m filmtools.amv3.audit_mix3 [--edl films/timeless/amv3/edl.json]
        [--mix /home/nikhil/code/film-making/work/timeless_v3/mix.wav] [--json audit.json] [--png mix3.png]

The stems are rebuilt from the same code (and the voice balance stored in mix3_report.json next to the mix), so the
SFX bus is exact. Exit status 1 when a check fails.

Per transition, over the window [w0, w1) and +-2 f around the cut, the "lift" is the level of (music + SFX) minus the
music alone, in the air band (3-12 kHz: whooshes, glass, sparks) and the sub band (30-90 Hz: thumps, booms), and the
broadband SFX-to-music ratio. The references' cuts lift the air band ~+4-8 dB (ref b's biggest swells +12-17), see
`filmtools.amv3.analysis.ref_audio`; the check keeps every transition's broadband SFX under the music over its
window (the song leads, the SFX support it).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import scipy.signal as sg
import soundfile as sf

from filmtools.amv import audit_audio as A
from filmtools.amv2 import mix as M2
from filmtools.amv3 import mix3 as M

SR = M.SR
IMPULSIVE = {"thump", "slap", "impact", "thunder", "glass", "glass_dome", "glass_big", "metal_slam", "shockwave",
             "hit", "impact_boom", "sub_drop", "debris", "dust", "tinkle", "air_tail"}
BANDS = {"air": (3000, 12000), "sub": (30, 90)}


def _band(x, lo, hi):
    return sg.sosfiltfilt(sg.butter(4, [lo, hi], "band", fs=SR, output="sos"), x)


def _rms_db(x):
    return float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12))


def lifts(E: dict, stems: dict) -> list[dict]:
    """Per transition: its own SFX (`air_lift_own_db`, what `mix3.calibrate` aims) and the whole SFX bus
    (`air_lift_cut_db`, what is heard: overlapping tails included) over the music, in the air band at the cut; the
    sub band lift of the whole bus; and the broadband SFX/music ratios over the window and at the cut."""
    fps = E["fps"]
    mus = stems["music"].mean(axis=1)
    sfx = stems["sfx"].mean(axis=1)
    sub = sg.butter(4, BANDS["sub"], "band", fs=SR, output="sos")
    rows = []
    for T in E["cuts"]:
        own = stems["per_cut"].get(T["id"])
        mo = M.measure_cut(T, mus, own.mean(axis=1), fps)
        mb = M.measure_cut(T, mus, sfx, fps)
        (c0, c1), _ = M.cut_spans(T, fps, len(mus))
        sm, ss = sg.sosfiltfilt(sub, mus[c0:c1]), sg.sosfiltfilt(sub, (mus + sfx)[c0:c1])
        rows.append({"cut": T["id"], "type": T["type"], "f": T["f"], "window": [T["w0"], T["w1"]],
                     "target_air_lift_db": M.LIFT[T["type"]],
                     "air_lift_own_db": round(mo["air_lift_db"], 1), "air_lift_cut_db": round(mb["air_lift_db"], 1),
                     "sub_lift_cut_db": round(_rms_db(ss) - _rms_db(sm), 1),
                     "sfx_over_music_window_db": round(mo["sfx_over_music_window_db"], 1),
                     "sfx_over_music_cut_db": round(_rms_db(sfx[c0:c1]) - _rms_db(mus[c0:c1]), 1)})
    return rows


def cue_sync(E: dict, stems: dict) -> list[dict]:
    """Each layer, rendered alone: swells/swishes/rips must peak (10 ms RMS) within +-1 f of their frame; impulsive
    layers must have their onset (first sample over -20 dB of their peak) within +-1 f. Also the transient detector
    on the whole SFX bus for the impulsive layers (v2 style), reported."""
    fps = E["fps"]
    kit = json.loads((Path(E["sfx_dir"]) / "sfx_kit.json").read_text())
    rows = []
    for c in stems["cues"]:
        y, h = M.render_cue(c, kit, Path(E["sfx_dir"]))
        m = np.abs(y).max(axis=1)
        base = c["hit_sample"] - h
        if c["name"] in IMPULSIVE or c.get("gen") in ("thump", "impact", "glass", "slap", "metal_slam", "thunder"):
            on = int(np.argmax(m > 0.1 * m.max()))
            at = (base + on) / SR * fps
            kind = "onset"
        elif c["name"] in ("goo", "tunnel", "crackle_in", "crackle_out", "sparks_swirl", "shimmer"):
            # long beds: the designed event sample (snap / pass / peak) is checked through `h` only
            at = (base + h) / SR * fps
            kind = "event"
        else:
            e = np.sqrt(np.convolve(m ** 2, np.ones(480) / 480, "same"))
            at = (base + int(np.argmax(e))) / SR * fps
            kind = "peak"
        rows.append({"name": c["name"], "cut": c["cut"], "f": c["f"], "measured_f": round(at, 2),
                     "delta": round(at - c["f"], 2), "kind": kind})
    return rows


def check(E: dict, mix: np.ndarray, adj: dict, trims: dict) -> tuple[dict, dict]:
    fps, N = E["fps"], len(mix)
    rep, fails = {}, []
    L, tp = M2.lufs(mix), M2.true_peak_db(mix)
    rep["lufs"], rep["true_peak_dbtp"] = round(L, 2), round(tp, 2)
    rep["clipped_samples"] = int((np.abs(mix) >= 0.9999).sum())
    rep["sample_peak_dbfs"] = round(float(20 * np.log10(np.abs(mix).max())), 2)
    if abs(L + 14) > 0.3:
        fails.append(f"loudness {L:.2f} LUFS, wanted -14 +-0.3")
    if tp > -1.0:
        fails.append(f"true peak {tp:.2f} dBTP > -1")
    if rep["clipped_samples"]:
        fails.append(f"{rep['clipped_samples']} clipped samples")
    rep["length_samples"] = N
    if N != round(E["dur"] / fps * SR):
        fails.append(f"length {N} samples, wanted {round(E['dur'] / fps * SR)}")

    stems = M.build(E, adj, trims)
    # voice: speech over what is under it, per line, against v2's mix of the same lines (v2 cue plan, same EDL timing)
    rep["voice_over_bed"] = M2.voice_ratio(stems)
    rep["voice_over_bed_v2"] = _v2_voice_ratio()
    for r in rep["voice_over_bed"]:
        if r["voice_over_bed_db"] < 3.5:
            fails.append(f"voice {r['name']} only {r['voice_over_bed_db']} dB over the bed (< 3.5)")
    # voice under each cue: music and SFX levels over the spoken words, dB re the voice
    vr = []
    for v in stems["lines"]:
        mask = np.zeros(stems["N"], bool)
        for w in v["words"]:
            mask[v["start"] + int(w["t0"] * SR): v["start"] + int(w["t1"] * SR)] = True
        lv = _rms_db(stems["voice"][mask])
        vr.append({"name": v["name"], "frames": [v["f"], round((v["start"] / SR + v["words"][-1]["t1"]) * fps)],
                   "voice_over_music_db": round(lv - _rms_db(stems["music"][mask]), 1),
                   "voice_over_sfx_db": round(lv - _rms_db(stems["sfx"][mask]), 1)})
    rep["voice_detail"] = vr

    # voice words vs the subtitle reveal (stem onset frame + 1): 0-2 f window, as v2
    bad, words = [], []
    for v in stems["lines"]:
        refs = [v["start"] / SR + w["t0"] for w in v["words"]]
        meas = M2.word_onsets(stems, v)
        ons = A.word_onsets(stems["voice"].mean(axis=1), SR, refs)
        for w, o, mo in zip(v["words"], ons, meas):
            if o["t"] is None:
                continue
            d = (mo["frame"] + 1) - A.frame_of(o["t"], fps)
            words.append({"line": v["name"], "word": w["w"], "delta": d})
            if not 0 <= d <= 2:
                bad.append(words[-1])
    rep["voice_words_bad"] = bad
    if bad:
        fails.append(f"{len(bad)} voice words off the 0-2 frame subtitle window")

    # SFX on their frames
    sync = cue_sync(E, stems)
    rep["sfx_sync_off"] = [r for r in sync if abs(r["delta"]) > 1.0]
    rep["sfx_sync_max_abs_delta_f"] = max(abs(r["delta"]) for r in sync)
    if rep["sfx_sync_off"]:
        fails.append(f"{len(rep['sfx_sync_off'])} SFX layers more than 1 frame off their frame")
    tr = [(t * fps, s) for t, s in A.transients(stems["sfx"].mean(axis=1), SR, 3.0)]
    miss = []
    for c in stems["cues"]:
        if c["name"] in ("thump", "slap", "impact", "thunder", "glass", "glass_dome", "glass_big", "metal_slam", "hit",
                         "impact_boom"):
            if not any(abs(f - c["f"]) <= 1.0 for f, _ in tr):
                miss.append({"name": c["name"], "f": c["f"]})
    rep["impacts_without_bus_transient"] = miss

    # per transition lift
    rep["transitions"] = lifts(E, stems)
    loud = [r for r in rep["transitions"] if r["sfx_over_music_window_db"] > M.UNDER + 0.5]
    if loud:
        fails.append("SFX over the music across a window: " + ", ".join(f"{r['cut']} {r['sfx_over_music_window_db']:+.1f}" for r in loud))

    # the SFX must not pump the song through the master limiter
    pump = M.extra_reduction(E, stems)
    for r in rep["transitions"]:
        r["limiter_extra_reduction_db"] = round(pump[r["cut"]], 2)
    pumped = {k: round(v, 1) for k, v in pump.items() if v > M.PUMP + 0.5}
    if pumped:
        fails.append(f"SFX pump the limiter (> {M.PUMP + 0.5} dB extra reduction): {pumped}")

    # end + clicks (v2 audit)
    tail = mix[-int(0.5 * SR):].mean(axis=1)
    rms = np.sqrt(np.convolve(tail ** 2, np.ones(48) / 48, "same"))
    d = np.abs(np.diff(mix[-int(1.5 * SR):], axis=0)).max(axis=1)
    step = float(d[-int(0.1 * SR):].max() / (d[:-int(0.1 * SR)].max() + 1e-9))
    rep["end"] = {"last_sample": float(np.abs(mix[-1]).max()),
                  "rms_last_10ms_dbfs": round(float(20 * np.log10(rms[-480:].mean() + 1e-12)), 1),
                  "max_step_last_100ms_over_prev": round(step, 3)}
    if np.abs(mix[-1]).max() > 1e-4:
        fails.append("the file does not end on silence")
    if step > 1.0:
        fails.append("a step or click in the last 100 ms")
    hpx = sg.sosfilt(sg.butter(4, 8000, "high", fs=SR, output="sos"), mix.mean(axis=1))
    env = np.convolve(np.abs(hpx), np.ones(2400) / 2400, "same") + 1e-6
    ck = np.where(np.abs(hpx) / env > 40)[0]
    rep["click_candidates_f"] = sorted({int(i / SR * fps) for i in ck})[:20]
    rep["fails"] = fails
    return rep, stems


def _v2_voice_ratio() -> list[dict]:
    """The v2 baseline: v2's mix (its EDL, its cue plan and its own per-line voice auto balance, as amv2.mix.main)."""
    E2 = json.loads((M.ROOT / "films/timeless/amv2/edl.json").read_text())
    adj = {}
    for _ in range(6):
        r = {x["name"]: x["voice_over_bed_db"] for x in M2.voice_ratio(M2.build(E2, adj))}
        for v in E2["voice"]:
            deficit = 4.0 - r[v["name"]]
            if deficit > 0.2:
                t, xd = adj.get(v["name"], (0.0, 0.0))
                use = min(deficit, 6.0 - t)
                adj[v["name"]] = (t + use, xd - 0.7 * (deficit - use) if deficit > use else xd)
    return M2.voice_ratio(M2.build(E2, adj))


def plot(E: dict, mix: np.ndarray, stems: dict, rep: dict, path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fps = E["fps"]
    x = mix.mean(axis=1)
    t = np.arange(len(x)) / SR * fps
    fig, axs = plt.subplots(4, 1, figsize=(26, 15), sharex=True, gridspec_kw={"height_ratios": [1.2, 1.0, 2.2, 1.0]})
    colors = {"zt": "#3b82f6", "whip": "#10b981", "cube": "#a855f7", "flip": "#a855f7", "slam": "#ef4444",
              "open": "#64748b", "triptych": "#f59e0b"}
    ax = axs[0]
    step = 40
    ax.plot(t[::step], x[::step], color="0.35", lw=0.4)
    ax.set_ylabel("mix")
    ax.set_ylim(-1, 1)
    ax = axs[1]
    for k, col in (("music", "0.6"), ("sfx", "#e11d48"), ("voice", "#0ea5e9")):
        y = stems[k].mean(axis=1)
        e = np.sqrt(np.convolve(y ** 2, np.ones(1600) / 1600, "same"))[::400]
        ax.plot(t[::400], 20 * np.log10(e + 1e-6), color=col, lw=1, label=k)
    ax.set_ylim(-60, 0)
    ax.set_ylabel("stem dBFS (pre-master)")
    ax.legend(loc="upper left", ncol=3)
    ax = axs[2]
    ax.specgram(x, NFFT=2048, Fs=fps * 1.0 * SR / fps, noverlap=1536, cmap="magma", vmin=-110,
                xextent=(0, len(x) / SR * fps))
    ax.set_yscale("symlog", linthresh=200)
    ax.set_ylim(30, 20000)
    ax.set_ylabel("Hz")
    ax = axs[3]
    tr = rep["transitions"]
    ax.bar([r["f"] for r in tr], [r["air_lift_cut_db"] for r in tr], width=3, color="#f59e0b", label="air lift at cut (dB)")
    ax.scatter([r["f"] for r in tr], [r["target_air_lift_db"] for r in tr], marker="_", s=120, color="k", label="target")
    ax.bar([r["f"] + 3 for r in tr], [r["sub_lift_cut_db"] for r in tr], width=3, color="#6366f1", label="sub lift at cut (dB)")
    ax.axhspan(4, 8, color="#f59e0b", alpha=0.12, label="refs' typical air lift")
    ax.set_ylabel("dB over the song")
    ax.legend(loc="upper left", ncol=3)
    for T in E["cuts"]:
        col = colors.get(T["type"], "#f43f5e")
        for a in axs:
            a.axvspan(T["w0"], T["w1"], color=col, alpha=0.10, lw=0)
            a.axvline(T["f"], color=col, lw=1.0)
        axs[0].text(T["f"], 0.92, f"{T['id']}\n{T['type']}", fontsize=7, ha="center", va="top", color=col)
    for v in E["voice"]:
        axs[1].axvline(v["f"], color="#0ea5e9", ls="--", lw=0.8)
    axs[-1].set_xlabel("frame (30 fps)")
    axs[-1].set_xticks(range(0, E["dur"] + 1, 30))
    axs[-1].set_xlim(0, E["dur"])
    axs[0].set_title(f"Timeless v3 mix: {rep['lufs']} LUFS, {rep['true_peak_dbtp']} dBTP; cut frames (lines) and "
                     f"transition windows (shaded)")
    fig.tight_layout()
    fig.savefig(path, dpi=70)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--edl", default=str(M.ROOT / "films/timeless/amv3/edl.json"))
    ap.add_argument("--mix", default=str(M.OUT / "mix.wav"))
    ap.add_argument("--json")
    ap.add_argument("--png")
    a = ap.parse_args(argv)
    E = json.loads(Path(a.edl).read_text())
    mix, sr = sf.read(a.mix, dtype="float64", always_2d=True)
    assert sr == SR and mix.shape[1] == 2
    rp = Path(a.mix).parent / "mix3_report.json"
    adj, trims = {}, {}
    if rp.exists():
        r = json.loads(rp.read_text())
        adj = {k: (v["trim_db"], v["extra_duck_db"]) for k, v in r.get("voice_adjust", {}).items()}
        trims = r.get("transition_trim_db", {})
    rep, stems = check(E, mix, adj, trims)
    print(json.dumps({k: v for k, v in rep.items() if k != "transitions"}, indent=1))
    print("cut  type            f  target  air(own) air(bus)  sub(bus)  sfx/music window  sfx/music cut")
    for r in rep["transitions"]:
        print(f"{r['cut']}  {r['type']:12s} {r['f']:4d}  {r['target_air_lift_db']:+5.1f}   {r['air_lift_own_db']:+6.1f}"
              f"   {r['air_lift_cut_db']:+6.1f}   {r['sub_lift_cut_db']:+6.1f}      {r['sfx_over_music_window_db']:+6.1f}"
              f"          {r['sfx_over_music_cut_db']:+6.1f}   pump {r['limiter_extra_reduction_db']:.1f}")
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1))
    if a.png:
        plot(E, mix, stems, rep, a.png)
    return 1 if rep["fails"] else 0


if __name__ == "__main__":
    sys.exit(main())
