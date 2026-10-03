"""The sound-effects library: ElevenLabs sound generation from data/sfx_palette.json, cached by request.

Each variant of each sound is one API request. Its key is the sha256 of the request's canonical JSON, and its files
are audio/sfx/lib/<id>/<key[:12]>.{raw,wav}: the raw API bytes, and the trimmed, faded 48 kHz / 24-bit mono take.
audio/sfx/manifest.json records every variant (request, seed, cost, QC, hit time, the wav's sha256) and the pick per
sound. A request already in the manifest whose wav still has its recorded sha256 is never fetched again, and a raw
file already on disk is decoded rather than paid for twice.

    film-sfx-lib probe            # once: are seeds accepted, and are they deterministic?
    film-sfx-lib plan             # what is still to fetch, and its estimated credits
    film-sfx-lib gen --budget N   # fetch it, never crossing N credits this run
    film-sfx-lib sheet            # out/review/sfx/<family>.png: spectrograms, waveforms, hit marks, QC
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks, lfilter, resample_poly

from .elevenlabs import ElevenLabs, ElevenLabsError
from .paths import AUDIO, DATA, OUT
from .wav import SR, pcm16_to_float, read_wav, write_wav

PALETTE = DATA / "sfx_palette.json"
LIB = AUDIO / "sfx" / "lib"
MANIFEST = AUDIO / "sfx" / "manifest.json"
CREDIT_LOG = AUDIO / "credits.log"
BACKUP = Path(os.path.expanduser("~/Developer/code/gitloom-film-audio-backup/sfx"))
DEFAULT_CPS = 40.0  # credits per second of requested audio, until a real call measures it

PRE_S = 0.005    # an onset lands this long into its file
FADE_IN_S = 0.002
FADE_OUT_S = 0.020
SEAM_S = 0.050   # a loop's equal-power seam crossfade
TAIL_S = 0.030   # kept after the last audible frame
SILENT_DBFS = -60.0


# ---------------------------------------------------------------- palette and requests

def load_palette(path: Path = PALETTE) -> dict:
    return json.loads(Path(path).read_text())


def seed_of(palette: dict, sound_id: str, variant: int) -> int:
    return int(palette["seed_base"]) + 100 * list(palette["sounds"]).index(sound_id) + variant


def request_of(palette: dict, sound_id: str, variant: int) -> dict:
    """The exact JSON sent to /v1/sound-generation, plus the first output_format to try. When seeds are not sent
    (the API refused them), `variant` keys the request instead; it is stripped before sending."""
    s = palette["sounds"][sound_id]
    req = {"text": s["prompt"], "model_id": palette["model_id"], "duration_seconds": s["duration"],
           "prompt_influence": s["influence"], "loop": bool(s.get("loop", False))}
    if palette.get("send_seed", True):
        req["seed"] = seed_of(palette, sound_id, variant)
    else:
        req["variant"] = variant
    req["output_format"] = palette["output_formats"][0]
    return req


def request_key(req: dict) -> str:
    return hashlib.sha256(json.dumps(req, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_ok(lib: Path | None, entry: dict | None, key: str) -> bool:
    if not entry or entry.get("key") != key:
        return False
    if lib is None:
        return True
    wav = lib / entry["wav"]
    return wav.exists() and _sha(wav) == entry.get("sha256")


def _cached(palette: dict, manifest: dict, lib: Path | None, sound_id: str, variant: int, key: str) -> bool:
    vs = manifest.get("variants", {})
    if not _file_ok(lib, vs.get(f"{sound_id}/{variant}"), key):
        return False
    if not int(palette["sounds"][sound_id].get("slice", 0) or 0):
        return True
    n = vs[f"{sound_id}/{variant}"].get("slices")  # what the take yielded, which may be fewer than asked
    if n is None:
        return False
    return all(_file_ok(lib, vs.get(f"{sound_id}_{k}/{variant}"), key) for k in range(1, n + 1))


def plan(palette: dict, manifest: dict, lib: Path | None = LIB) -> list[tuple[str, int, dict]]:
    """(sound_id, variant, request) for every request not yet in the manifest with an intact wav. With lib=None
    only the manifest's keys are checked."""
    todo = []
    for sid in palette["sounds"]:
        for v in range(int(palette["variants"])):
            req = request_of(palette, sid, v)
            if not _cached(palette, manifest, lib, sid, v, request_key(req)):
                todo.append((sid, v, req))
    return todo


def measured_rate(manifest: dict) -> float | None:
    cost = secs = 0.0
    for e in manifest.get("variants", {}).values():
        if e.get("parent") is None and e.get("cost_measured", True) and e.get("cost", 0) > 0:
            cost += e["cost"]
            secs += e["request"]["duration_seconds"]
    return cost / secs if secs else None


def estimate(todo, credits_per_second: float) -> int:
    return int(math.ceil(sum(req["duration_seconds"] for _, _, req in todo) * credits_per_second - 1e-9))


# ---------------------------------------------------------------- decoding

def pcm_channels(n_bytes: int, sr: int, duration: float | None) -> int:
    """sound-generation's pcm_* comes back as interleaved PCM16 *stereo* (measured: 0.5 s at pcm_48000 is 92160
    bytes = 0.48 s × 2 channels), although the docs say mono. The requested duration decides: 1 or 2 channels,
    whichever puts the length nearer it. Without a duration, mono."""
    if not duration:
        return 1
    ratio = (n_bytes / 2) / (duration * sr)
    return 2 if abs(ratio - 2) < abs(ratio - 1) else 1


def to_wav48(raw: bytes, output_format: str, duration: float | None = None) -> np.ndarray:
    """API bytes → mono float32 at 48 kHz. pcm_<rate> is PCM16 LE, stereo downmixed (see pcm_channels); anything
    else (mp3) goes through ffmpeg."""
    if output_format.startswith("pcm_"):
        sr = int(output_format.split("_")[1])
        ch = pcm_channels(len(raw), sr, duration)
        y = pcm16_to_float(raw[:len(raw) - len(raw) % (2 * ch)], ch)
        if ch > 1:
            y = y.mean(axis=1)
        if sr != SR:
            g = math.gcd(SR, sr)
            y = resample_poly(y, SR // g, sr // g).astype(np.float32)
        return y.astype(np.float32)
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / "in.bin", Path(td) / "out.wav"
        src.write_bytes(raw)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ar", str(SR), "-ac", "1", str(dst)],
                       check=True)
        y, _ = read_wav(dst)
    return y.astype(np.float32)


# ---------------------------------------------------------------- signal

def _frame_rms(y: np.ndarray, sr: int, win_s: float) -> np.ndarray:
    n = max(1, int(win_s * sr))
    m = len(y) // n
    if m == 0:
        return np.array([np.sqrt(np.mean(y ** 2)) if len(y) else 0.0])
    return np.sqrt(np.mean(y[:m * n].reshape(m, n) ** 2, axis=1))


def _noise_floor(y: np.ndarray, sr: int) -> float:
    return float(np.percentile(_frame_rms(y, sr, 0.005), 10))


def _walk_back(a: np.ndarray, j: int, lo: float, w: int, floor: int = 0) -> int:
    """From index j, step back (never before `floor`) while anything in the w samples before is above `lo`; then
    the first sample above `lo` in what was walked is the onset."""
    k = j
    while k > floor and a[max(floor, k - w):k].max() > lo:
        k -= 1
    above = np.nonzero(a[k:j + 1] > lo)[0]
    return k + int(above[0]) if len(above) else j


def find_hit(y: np.ndarray, sr: int, align: str | None) -> float:
    """Where in the file the cue lands, in seconds: the first transient ('onset'), the loudest sample ('peak'), or
    the end of the audible sound ('end')."""
    a = np.abs(np.asarray(y, dtype=np.float64))
    if not len(a) or a.max() == 0:
        return 0.0
    peak = a.max()
    if align == "peak":
        return float(np.argmax(a)) / sr
    if align == "end":
        return _audible_end(y, sr) / sr
    # The first 1 ms frame within 12 dB of the loudest frame is the hit; walk back from its first loud sample to
    # where the signal falls to the background just before it (hiss or room before a hit is not the hit).
    hop = max(1, int(0.001 * sr))
    env = _frame_rms(y, sr, 0.001)
    f = int(np.argmax(env >= 0.25 * env.max()))
    seg = a[f * hop:(f + 1) * hop]
    j = f * hop + int(np.argmax(seg >= 0.5 * seg.max()))
    bg_lo, bg_hi = max(0, f - 50), max(0, f - 5)
    bg = float(np.median(env[bg_lo:bg_hi])) if bg_hi > bg_lo else 0.0
    lo = min(max(0.02 * peak, 3 * _noise_floor(y, sr), 2.5 * bg), 0.5 * a[j])
    return _walk_back(a, j, lo, max(1, int(0.0005 * sr)), floor=max(0, j - int(0.03 * sr))) / sr


def _audible_end(y: np.ndarray, sr: int) -> int:
    """The sample index just past the last audible 5 ms frame (above −60 dBFS and within 50 dB of the peak)."""
    n = int(0.005 * sr)
    rms = _frame_rms(y, sr, 0.005)
    peak = np.abs(y).max() if len(y) else 0.0
    thr = max(10 ** (SILENT_DBFS / 20), peak * 10 ** (-50 / 20))
    loud = np.nonzero(rms > thr)[0]
    return min(len(y), (int(loud[-1]) + 1) * n) if len(loud) else len(y)


def _fades(y: np.ndarray, sr: int) -> np.ndarray:
    y = y.copy()
    fi, fo = min(len(y), int(FADE_IN_S * sr)), min(len(y), int(FADE_OUT_S * sr))
    if fi:
        y[:fi] *= np.linspace(0, 1, fi, dtype=np.float32)
    if fo:
        y[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)
    return y


def _trim_onset(y: np.ndarray, sr: int, onset_idx: int) -> np.ndarray:
    pre = int(round(PRE_S * sr))
    start = onset_idx - pre
    y = np.concatenate([np.zeros(-start, np.float32), y]) if start < 0 else y[start:]
    end = min(len(y), _audible_end(y, sr) + int(TAIL_S * sr))
    return _fades(y[:max(end, pre + int(FADE_OUT_S * sr) + 1)], sr)


def _seam(y: np.ndarray, sr: int) -> np.ndarray:
    n = int(SEAM_S * sr)
    t = (np.arange(n) + 0.5) / n
    out = y[:-n].copy()
    out[:n] = y[:n] * np.sin(0.5 * np.pi * t) + y[-n:] * np.cos(0.5 * np.pi * t)
    return out.astype(np.float32)


def process(y: np.ndarray, sr: int, spec: dict) -> tuple[np.ndarray, float | None]:
    """Remove DC, then: a loop gets the seam crossfade and no trim (hit None); an onset sound is trimmed to 5 ms
    before its hit; an end sound is cut after its audible end. All but loops get the 2 ms / 20 ms fades."""
    y = (np.asarray(y, dtype=np.float32) - np.float32(np.mean(y))).astype(np.float32)
    if spec.get("loop"):
        return _seam(y, sr), None
    align = spec.get("align")
    if align == "onset":
        out = _trim_onset(y, sr, int(round(find_hit(y, sr, "onset") * sr)))
        return out, round(PRE_S * sr) / sr
    end = min(len(y), _audible_end(y, sr) + (0 if align == "end" else int(TAIL_S * sr)))
    out = _fades(y[:end], sr)
    return out, (len(out) / sr if align == "end" else find_hit(out, sr, "peak"))


def slice_hits(y: np.ndarray, sr: int, n: int, min_gap: float = 0.08) -> list[np.ndarray]:
    """The n strongest hits at least min_gap apart, in time order, each trimmed like a one-shot (its onset at 5 ms,
    faded). Every distinct hit is a boundary, chosen or not, so a slice ends before the next hit of any size. A
    candidate 30 dB under the loudest is not a hit; a bump in a tail (rising under 3 dB above its valley) is not a
    boundary."""
    y = np.asarray(y, dtype=np.float32)
    a = np.abs(y.astype(np.float64))
    hop = max(1, int(0.001 * sr))
    env = _frame_rms(y, sr, 0.001)
    noise = _noise_floor(y, sr)
    peaks, props = find_peaks(env, distance=max(1, int(min_gap * sr / hop)), prominence=0)
    if not len(peaks):
        return []
    prom = props["prominences"]
    keep = (env[peaks] >= env[peaks].max() * 10 ** (-30 / 20)) & (prom >= 0.3 * env[peaks])
    peaks, prom = peaks[keep], prom[keep]
    chosen = set(peaks[np.argsort(prom)[::-1][:n]].tolist())
    w = max(1, int(0.0005 * sr))
    onsets, floor = [], 0  # a hit's onset never walks back past the previous hit's peak
    for p in peaks:  # time order
        lo_i, hi_i = p * hop, min(len(a), (p + 1) * hop)
        pk = lo_i + int(np.argmax(a[lo_i:hi_i]))
        hi = 0.1 * a[pk]
        j = pk
        while j > floor and a[j - 1] > hi:
            j -= 1
        lo = min(max(0.02 * a[pk], 3 * noise), hi)
        onsets.append(_walk_back(a, j, lo, w, floor))
        floor = pk + 1
    out = []
    pre = int(round(PRE_S * sr))
    min_len = int(0.02 * sr)
    for i, (p, o) in enumerate(zip(peaks, onsets)):
        if int(p) not in chosen:
            continue
        end = onsets[i + 1] - pre if i + 1 < len(onsets) else len(y)
        seg = y[:max(end, min(len(y), o + min_len))]
        out.append(_trim_onset(seg, sr, o))
    return out


# ---------------------------------------------------------------- QC and the pick

def _k_weight(y: np.ndarray, sr: int) -> np.ndarray:
    """ITU-R BS.1770 K-weighting (the 48 kHz coefficients)."""
    b1, a1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585]
    b2, a2 = [1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621]
    return lfilter(b2, a2, lfilter(b1, a1, y))


def lufs(y: np.ndarray, sr: int = SR) -> float:
    """Integrated loudness (BS.1770, gated). A sound shorter than one 400 ms block is measured ungated."""
    z = _k_weight(np.asarray(y, dtype=np.float64), sr)
    blk, hop = int(0.4 * sr), int(0.1 * sr)
    if len(z) < blk:
        ms = np.mean(z ** 2) if len(z) else 0.0
        return float(-0.691 + 10 * np.log10(ms)) if ms > 0 else -120.0
    ms = np.array([np.mean(z[i:i + blk] ** 2) for i in range(0, len(z) - blk + 1, hop)])
    ld = -0.691 + 10 * np.log10(np.maximum(ms, 1e-20))
    g = ms[ld > -70]
    if not len(g):
        return -120.0
    rel = -0.691 + 10 * np.log10(np.mean(g)) - 10
    g = ms[(ld > -70) & (ld > rel)]
    return float(-0.691 + 10 * np.log10(np.mean(g)))


def qc(y: np.ndarray, sr: int) -> dict:
    y = np.asarray(y, dtype=np.float32)
    a = np.abs(y)
    peak = float(a.max()) if len(a) else 0.0
    onset = find_hit(y, sr, "onset")
    env = _frame_rms(y, sr, 0.001)
    i0 = int(onset * sr) // max(1, int(0.001 * sr))
    attack_ms = float(np.argmax(env[i0:i0 + 200])) if i0 < len(env) else 0.0
    e20 = 20 * np.log10(np.maximum(_frame_rms(y, sr, 0.02), 1e-6))
    loud = e20 > (e20.max() - 40)
    rough = float(np.std(np.diff(e20[loud]))) if loud.sum() > 2 else 0.0
    spec = np.abs(np.fft.rfft(y.astype(np.float64))) if len(y) else np.zeros(1)
    freqs = np.fft.rfftfreq(len(y), 1 / sr) if len(y) else np.zeros(1)
    centroid = float((spec * freqs).sum() / spec.sum()) if spec.sum() > 0 else 0.0
    frames = _frame_rms(y, sr, 0.01)
    return {
        "peak_dbfs": round(20 * math.log10(peak), 2) if peak > 0 else -120.0,
        "lufs": round(lufs(y, sr), 2),
        "onset_s": round(onset, 5),
        "dur_s": round(len(y) / sr, 4),
        "centroid_hz": round(centroid, 1),
        "silence_ratio": round(float(np.mean(frames < 10 ** (SILENT_DBFS / 20))), 3),
        "clipped": bool(int((a >= 0.999).sum()) >= 2),
        "dc": round(float(np.mean(y)), 6) if len(y) else 0.0,
        "attack_ms": attack_ms,
        "roughness_db": round(rough, 3),
    }


def faults(q: dict, align: str | None, loop: bool = False) -> list[str]:
    f = []
    if q["clipped"]:
        f.append("clipped")
    if q["silence_ratio"] > 0.6:
        f.append("silent")
    if q["peak_dbfs"] < -40:
        f.append("quiet")
    if not loop and align in ("onset", "peak") and q.get("raw_onset_s", q["onset_s"]) > 0.3:
        f.append("late onset")
    return f


def pick(variants: list[dict], family: str) -> int:
    """The auto pick: drop clipped, >60 % silent, peaking under −40 dBFS, or (one-shots) no onset in the first
    300 ms, and any more than 20 LU quieter than the loudest survivor; of the rest, the sharpest attack for onset sounds, the smoothest envelope for beds, risers and whooshes.
    −1 when every variant fails. `family` is kept for the record; the shape comes from each variant's align/loop."""
    ok = [i for i, v in enumerate(variants) if not faults(v["qc"], v.get("align"), v.get("loop", False))]
    if not ok:
        return -1
    top = max(variants[i]["qc"]["lufs"] for i in ok)
    ok = [i for i in ok if variants[i]["qc"]["lufs"] >= top - 20]  # a take 20 LU under the best is a near-miss
    if all(variants[i].get("align") == "onset" and not variants[i].get("loop") for i in ok):
        return min(ok, key=lambda i: (variants[i]["qc"]["attack_ms"], -variants[i]["qc"]["peak_dbfs"]))
    return min(ok, key=lambda i: variants[i]["qc"]["roughness_db"])


# ---------------------------------------------------------------- generation

def _is_format_refusal(e: ElevenLabsError) -> bool:
    return 400 <= e.status < 500 and "format" in e.detail.lower()


def _load_manifest(path: Path) -> dict:
    m = json.loads(path.read_text()) if path.exists() else {}
    m.setdefault("variants", {})
    m.setdefault("picks", {})
    return m


def _save_manifest(path: Path, m: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    m["variants"] = dict(sorted(m["variants"].items()))
    m["picks"] = dict(sorted(m["picks"].items()))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=2) + "\n")
    tmp.replace(path)


def _fetch(client, palette: dict, req: dict, formats: list[str]):
    body = {k: v for k, v in req.items() if k not in ("output_format", "variant", "text", "model_id",
                                                      "duration_seconds", "prompt_influence")}
    for i, fmt in enumerate(formats):
        try:
            return client.sound(req["text"], duration_seconds=req["duration_seconds"],
                                prompt_influence=req["prompt_influence"], loop=body.get("loop", False),
                                model_id=req["model_id"], output_format=fmt, seed=body.get("seed")), i
        except ElevenLabsError as e:
            if not _is_format_refusal(e) or i == len(formats) - 1:
                raise
    raise AssertionError("unreachable")


def _record(lib: Path, sid: str, v: int, key: str, req: dict, seed: int, fmt: str, cost: int, measured: bool,
            request_id: str, y: np.ndarray, hit: float | None, q: dict, suffix: str = "", parent: str | None = None):
    wav = lib / sid.split("/")[0] / f"{key[:12]}{suffix}.wav"
    write_wav(wav, y)
    return {"key": key, "request": {k: x for k, x in req.items() if k != "output_format"}, "seed": seed,
            "output_format": fmt, "cost": cost, "cost_measured": measured, "request_id": request_id,
            "wav": str(wav.relative_to(lib)), "sha256": _sha(wav), "qc": q,
            "hit_s": None if hit is None else round(hit, 6), "parent": parent,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}


def _store(palette: dict, manifest: dict, lib: Path, sid: str, v: int, req: dict, raw: bytes, fmt: str, cost: int,
           measured: bool, request_id: str) -> None:
    spec = palette["sounds"][sid]
    key = request_key(req)
    seed = seed_of(palette, sid, v)
    y = to_wav48(raw, fmt, req["duration_seconds"])
    out, hit = process(y, SR, spec)
    q = qc(out, SR)
    q["raw_onset_s"] = round(find_hit(y - np.mean(y), SR, "onset"), 5)
    manifest["variants"][f"{sid}/{v}"] = _record(lib, sid, v, key, req, seed, fmt, cost, measured, request_id,
                                                 out, hit, q)
    n = int(spec.get("slice", 0) or 0)
    if n:
        parts = slice_hits(y - np.mean(y), SR, n, float(spec.get("slice_gap", 0.08)))
        for k, part in enumerate(parts, 1):
            manifest["variants"][f"{sid}_{k}/{v}"] = _record(
                lib, sid, v, key, req, seed, fmt, 0, measured, request_id, part, PRE_S, qc(part, SR),
                suffix=f"_{k}", parent=f"{sid}/{v}")
        for k in range(len(parts) + 1, n + 1):
            manifest["variants"].pop(f"{sid}_{k}/{v}", None)
        manifest["variants"][f"{sid}/{v}"]["slices"] = len(parts)


def _pick_entry(palette: dict, manifest: dict, target: str, src: str, auto: int) -> dict | None:
    spec = palette["sounds"][src]
    chosen = spec.get("pick")
    if chosen is None or f"{target}/{chosen}" not in manifest["variants"]:
        chosen = auto if auto >= 0 else next((v for v in range(int(palette["variants"]))
                                              if f"{target}/{v}" in manifest["variants"]), None)
    e = manifest["variants"].get(f"{target}/{chosen}")
    if e is None:
        return None
    return {"variant": chosen, "auto": auto, "rejected": auto < 0 and spec.get("pick") is None,
            "family": spec["family"], "gain": spec["gain"], "align": spec.get("align"), "loop": spec.get("loop", False),
            "wav": e["wav"], "hit_s": e["hit_s"]}


def update_picks(palette: dict, manifest: dict) -> None:
    """One pick per sound, and for a sliced sound one per slice id (`key_soft_3`): each slice is judged on its own
    across the variants that produced it, since a take with gaps fails the whole-take silence rule by design. A
    palette `pick` (an int) overrides the auto pick wherever that variant exists."""
    picks = {}
    nv = int(palette["variants"])
    for sid, spec in palette["sounds"].items():
        n = int(spec.get("slice", 0) or 0)
        for target in ([f"{sid}_{k}" for k in range(1, n + 1)] if n else [sid]):
            have = [v for v in range(nv) if f"{target}/{v}" in manifest["variants"]]
            if not have or (not n and len(have) < nv):
                continue
            k = pick([{"qc": manifest["variants"][f"{target}/{v}"]["qc"], "align": spec.get("align"),
                       "loop": spec.get("loop", False)} for v in have], spec["family"])
            p = _pick_entry(palette, manifest, target, sid, have[k] if k >= 0 else -1)
            if p:
                picks[target] = p
    manifest["picks"] = picks


def generate(palette: dict, client, lib: Path, manifest_path: Path, budget: int, dry_run: bool = False,
             log=lambda *a: None) -> dict:
    manifest = _load_manifest(manifest_path)
    todo = plan(palette, manifest, lib)
    cps = measured_rate(manifest) or DEFAULT_CPS
    est = estimate(todo, cps)
    res = {"todo": [(s, v) for s, v, _ in todo], "estimate": est, "credits_per_second": cps, "spent": 0,
           "fetched": [], "refused": False, "stopped": False}
    if dry_run:
        return res
    if est > budget:
        res["refused"] = True
        log(f"refused: estimate {est} > budget {budget}")
        return res
    formats = list(palette["output_formats"])
    spent = 0
    for sid, v, req in todo:
        key = request_key(req)
        raw_path = lib / sid / f"{key[:12]}.raw"
        meta_path = raw_path.with_suffix(".rawmeta.json")
        if raw_path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text())
            if meta.get("key") == key:  # paid before, but the take was never recorded: decode it, free
                _store(palette, manifest, lib, sid, v, req, raw_path.read_bytes(), meta["output_format"],
                       meta["cost"], meta["cost_measured"], meta["request_id"])
                _save_manifest(manifest_path, manifest)
                res["fetched"].append((sid, v))
                continue
        nxt = estimate([(sid, v, req)], cps)
        if spent + nxt > budget:
            res["stopped"] = True
            log(f"stop: {sid}/{v} (~{nxt}) would cross the budget; spent {spent}, left {budget - spent}")
            break
        r, fi = _fetch(client, palette, req, formats)
        if fi:
            formats = formats[fi:]  # a refused format stays refused for this run
        measured = r.cost > 0
        cost = r.cost if measured else nxt
        spent += cost
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(r.audio)
        meta_path.write_text(json.dumps({"key": key, "output_format": r.output_format, "cost": cost,
                                         "cost_measured": measured, "request_id": r.request_id}) + "\n")
        _store(palette, manifest, lib, sid, v, req, r.audio, r.output_format, cost, measured, r.request_id)
        cps = measured_rate(manifest) or cps
        manifest["credits_per_second"] = round(cps, 3)
        _save_manifest(manifest_path, manifest)
        res["fetched"].append((sid, v))
        log(f"{sid}/{v}: {cost} credits ({r.output_format}); spent {spent}, left {budget - spent}")
    update_picks(palette, manifest)
    _save_manifest(manifest_path, manifest)
    res["spent"] = spent
    res["credits_per_second"] = cps
    return res


def reprocess(palette: dict, lib: Path, manifest_path: Path) -> int:
    """Re-decode, re-trim, re-slice and re-QC every take whose raw bytes are on disk, for the palette's current
    requests (free: no API call). Used after a change to the post-processing."""
    manifest = _load_manifest(manifest_path)
    n = 0
    for sid in palette["sounds"]:
        for v in range(int(palette["variants"])):
            req = request_of(palette, sid, v)
            key = request_key(req)
            raw = lib / sid / f"{key[:12]}.raw"
            meta_path = raw.with_suffix(".rawmeta.json")
            if not (raw.exists() and meta_path.exists()):
                continue
            meta = json.loads(meta_path.read_text())
            if meta.get("key") != key:
                continue
            _store(palette, manifest, lib, sid, v, req, raw.read_bytes(), meta["output_format"], meta["cost"],
                   meta["cost_measured"], meta["request_id"])
            n += 1
    update_picks(palette, manifest)
    _save_manifest(manifest_path, manifest)
    return n


# ---------------------------------------------------------------- the determinism probe

def probe(palette: dict, client, lib: Path = LIB, sound_id: str = "glass_clink") -> dict:
    """Two identical requests with the same seed. Rejected seed → seeds_honoured false and seeds never sent;
    otherwise identical PCM → true, different → false."""
    s = palette["sounds"][sound_id]
    seed = seed_of(palette, sound_id, 0)
    outs, spent = [], 0
    for i in range(2):
        try:
            r = client.sound(s["prompt"], duration_seconds=0.5, prompt_influence=s["influence"],
                             model_id=palette["model_id"], output_format=palette["output_formats"][0], seed=seed)
        except ElevenLabsError as e:
            if 400 <= e.status < 500 and "seed" in e.detail.lower():
                palette["seeds_honoured"], palette["send_seed"] = False, False
                return {"seeds_honoured": False, "rejected": True, "spent": spent}
            raise
        spent += r.cost
        d = lib / "_probe"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{sound_id}-seed{seed}-{i}.raw").write_bytes(r.audio)
        outs.append(r.audio)
    same = outs[0] == outs[1]
    palette["seeds_honoured"], palette["send_seed"] = same, True
    a, b = pcm16_to_float(outs[0]), pcm16_to_float(outs[1])
    n = min(len(a), len(b))
    corr = float(np.corrcoef(a[:n], b[:n])[0, 1]) if n > 1 and a[:n].std() > 0 and b[:n].std() > 0 else 0.0
    return {"seeds_honoured": same, "rejected": False, "spent": spent, "bytes": [len(a) * 2, len(b) * 2],
            "correlation": round(corr, 4)}


def save_palette(palette: dict, path: Path = PALETTE) -> None:
    Path(path).write_text(json.dumps(palette, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- review sheets

def sheet(palette: dict, manifest: dict, lib: Path = LIB, out_dir: Path = OUT / "review" / "sfx") -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    fams: dict[str, list[str]] = {}
    for sid, spec in palette["sounds"].items():
        fams.setdefault(spec["family"], []).append(sid)
    nv = int(palette["variants"])
    written = []
    for fam, ids in fams.items():
        fig, axes = plt.subplots(2 * len(ids), nv, figsize=(7 * nv, 3.6 * len(ids)), squeeze=False,
                                 gridspec_kw={"height_ratios": [2, 1] * len(ids)})
        for r, sid in enumerate(ids):
            spec = palette["sounds"][sid]
            p = manifest["picks"].get(sid) or manifest["picks"].get(f"{sid}_1")
            for v in range(nv):
                ax_s, ax_w = axes[2 * r][v], axes[2 * r + 1][v]
                e = manifest["variants"].get(f"{sid}/{v}")
                if not e or not (lib / e["wav"]).exists():
                    ax_s.set_title(f"{sid}/{v}: missing")
                    continue
                y, sr = read_wav(lib / e["wav"])
                nfft = 1024
                ax_s.specgram(y + 1e-9, NFFT=nfft, Fs=sr, noverlap=nfft * 3 // 4, cmap="magma", vmin=-130, vmax=-20)
                ax_s.set_yscale("symlog", linthresh=200)
                ax_s.set_ylim(30, sr / 2)
                q = e["qc"]
                star = " ★" if p and p["variant"] == v else ""
                ax_s.set_title(f"{sid}/{v}{star}  [{spec.get('align') or 'loop'}]  "
                               f"pk {q['peak_dbfs']} dB  {q['lufs']} LUFS  dur {q['dur_s']}s  "
                               f"sil {q['silence_ratio']}  cen {q['centroid_hz']:.0f} Hz  att {q['attack_ms']:.0f} ms  "
                               f"rough {q['roughness_db']}{'  CLIP' if q['clipped'] else ''}", fontsize=8)
                t = np.arange(len(y)) / sr
                ax_w.plot(t, y, lw=0.4, color="#333")
                ax_w.set_xlim(0, len(y) / sr)
                ax_w.set_ylim(-1, 1)
                if e["hit_s"] is not None:
                    ax_w.axvline(e["hit_s"], color="#d02", lw=1)
                for k in range(1, int(spec.get("slice", 0) or 0) + 1):
                    se = manifest["variants"].get(f"{sid}_{k}/{v}")
                    if se:
                        ax_w.text(0.01 + 0.12 * (k - 1), 0.8, f"#{k} {se['qc']['dur_s']:.2f}s",
                                  transform=ax_w.transAxes, fontsize=6)
                ax_w.tick_params(labelsize=6)
                ax_s.tick_params(labelsize=6)
        fig.tight_layout()
        f = out_dir / f"{fam}.png"
        fig.savefig(f, dpi=70)
        plt.close(fig)
        written.append(f)
    # sliced one-shots get a sheet of their own, slice by slice
    for sid, spec in palette["sounds"].items():
        n = int(spec.get("slice", 0) or 0)
        if not n:
            continue
        fig, axes = plt.subplots(nv, n, figsize=(2.2 * n, 2.0 * nv), squeeze=False)
        for v in range(nv):
            for k in range(1, n + 1):
                ax = axes[v][k - 1]
                e = manifest["variants"].get(f"{sid}_{k}/{v}")
                if not e or not (lib / e["wav"]).exists():
                    ax.set_title(f"{v}/{k} missing", fontsize=7)
                    continue
                y, sr = read_wav(lib / e["wav"])
                ax.plot(np.arange(len(y)) / sr, y, lw=0.4, color="#333")
                ax.axvline(e["hit_s"], color="#d02", lw=0.8)
                ax.set_ylim(-1, 1)
                ax.set_title(f"{sid}_{k}/{v} {e['qc']['dur_s']:.2f}s pk {e['qc']['peak_dbfs']:.0f}", fontsize=6)
                ax.tick_params(labelsize=5)
        fig.tight_layout()
        f = out_dir / f"slices-{sid}.png"
        fig.savefig(f, dpi=70)
        plt.close(fig)
        written.append(f)
    return written


# ---------------------------------------------------------------- CLI

def backup(manifest: dict, lib: Path = LIB, dest: Path = BACKUP) -> int:
    n = 0
    for e in manifest["variants"].values():
        for src in [lib / e["wav"], (lib / e["wav"]).with_suffix(".raw")]:
            if src.exists():
                dst = dest / "lib" / src.relative_to(lib)
                if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    n += 1
    if MANIFEST.exists():
        shutil.copy2(MANIFEST, dest / "manifest.json")
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(prog="film-sfx-lib", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    sub.add_parser("plan")
    g = sub.add_parser("gen")
    g.add_argument("--budget", type=int, required=True)
    g.add_argument("--dry-run", action="store_true")
    sub.add_parser("sheet")
    sub.add_parser("backup")
    sub.add_parser("reprocess")
    args = ap.parse_args(argv)

    palette = load_palette()
    log = lambda *a: print(*a, flush=True)  # noqa: E731
    if args.cmd == "plan":
        man = _load_manifest(MANIFEST)
        todo = plan(palette, man, LIB)
        cps = measured_rate(man) or DEFAULT_CPS
        for sid, v, req in todo:
            print(f"{sid}/{v}  {req['duration_seconds']}s  seed {req.get('seed', '-')}")
        print(f"{len(todo)} requests, {sum(r['duration_seconds'] for *_, r in todo):.1f} s, "
              f"estimate {estimate(todo, cps)} credits at {cps:.1f}/s")
        return 0
    if args.cmd == "sheet":
        for f in sheet(palette, _load_manifest(MANIFEST)):
            print(f)
        return 0
    if args.cmd == "reprocess":
        print(f"{reprocess(palette, LIB, MANIFEST)} takes rebuilt from their raw bytes")
        print(f"backup: {backup(_load_manifest(MANIFEST))} files → {BACKUP}")
        return 0
    if args.cmd == "backup":
        print(f"{backup(_load_manifest(MANIFEST))} files copied to {BACKUP}")
        return 0

    client = ElevenLabs(credit_log=CREDIT_LOG)
    try:
        before = client.credits_used()
    except Exception:  # noqa: BLE001 (the key may lack user_read; the per-call headers still count)
        before = None
    if args.cmd == "probe":
        res = probe(palette, client)
        save_palette(palette)
        print(json.dumps(res))
    else:
        res = generate(palette, client, LIB, MANIFEST, args.budget, dry_run=args.dry_run, log=log)
        print(f"fetched {len(res['fetched'])}, spent {res['spent']} (headers), left {args.budget - res['spent']}"
              f"{', REFUSED: estimate ' + str(res['estimate']) if res['refused'] else ''}"
              f"{', stopped at the budget' if res['stopped'] else ''}")
        if res["fetched"]:
            print(f"backup: {backup(_load_manifest(MANIFEST))} files → {BACKUP}")
        if res["refused"]:
            return 1
    if before is not None:
        try:
            print(f"subscription: {client.credits_used() - before} credits used by this command")
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
