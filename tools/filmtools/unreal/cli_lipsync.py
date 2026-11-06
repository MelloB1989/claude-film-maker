"""film-ue lips: one source of truth for when each line is spoken, and the checks that the face says it then.

    film-ue lips cues   --lines cues.json --stem him=vo_him.wav --stem her=vo_her.wav [--words auto] --out cues.json
        each line's real speech onset/offset measured (VAD) on the stem AT ITS MIX POSITION (frame 0 = sample 0),
        words aligned inside it (whisper/stable-ts/elevenlabs when installed or granted, else estimated and flagged),
        the stems' sha256 recorded so a stale cues.json is refused. Face placement, captions and the mix read it.
    film-ue lips curves --curves face.json --start-frame 960 --wav vo_him.wav --cues cues.json --who him
        the curve-level gate (perfkit.lipsync) offline, on anim.read_curves output: lag, correlation, silences.
    film-ue lips render --video cut.mp4 --wav mix.wav --cues cues.json --who him (--boxes boxes.json | --box ...)
        the video-level gate on a RENDER: the speaker's mouth crop against the voice (darkness + motion vs the
        envelope, lag and correlation, with a shifted-audio control), plus SyncNet (offset, confidence) when
        --syncnet-dir points at a syncnet_python checkout with its weights. Run after every render with dialogue.

(`film-ue lips`, not `lipsync`: `film-ue lipsync <verb>` stays the editor's ops, lipsync.check/compose/mouth_boxes.)
Every command prints JSON with "pass" and "issues" (each with a "fix") and exits 0 pass, 1 fail, 2 inconclusive.
docs/unreal/research/lipsync.md has the sources for every limit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "unreal" / "fmbridge"))
from perfkit import audio as AU  # noqa: E402
from perfkit import lipsync as LS  # noqa: E402

from ..wav import read_wav  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def envelope(x: np.ndarray, sr: int, rate: float = 100.0, offset_s: float = 0.0) -> AU.Envelope:
    """perfkit's loudness envelope (0..1 over the clip's top 45 dB) from samples, vectorised."""
    if x.ndim > 1:
        x = x.mean(axis=1)
    hop = max(1, int(sr / rate))
    n = len(x) // hop
    sq = (x[:n * hop].astype(np.float64) ** 2).reshape(n, hop).sum(axis=1)
    win = sq + np.concatenate([sq[1:], [0.0]])
    rms = np.sqrt(win / (2 * hop))
    db = 20 * np.log10(np.maximum(rms, 1e-9))
    if not len(db):
        return AU.Envelope([0.0], rate, offset_s)
    top = np.sort(db)[int(len(db) * 0.98)]
    lo = max(-50.0, top - 45.0)
    vals = np.clip((db - lo) / max(1e-6, top - lo), 0.0, 1.0)
    return AU.Envelope(vals.tolist(), rate, offset_s)


# --- cues --------------------------------------------------------------------------------------------------------

def _estimate_words(text: str, t0: float, t1: float) -> list:
    ws = [w for w in text.replace("…", " ").split() if any(c.isalnum() for c in w)]
    if not ws:
        return []
    n = [max(1, sum(c.isalnum() for c in w)) for w in ws]
    gap = 0.06 * (len(ws) - 1)
    span = max(0.1, (t1 - t0) - gap)
    out, t = [], t0
    for w, k in zip(ws, n):
        d = span * k / sum(n)
        out.append({"w": w, "start": t, "end": t + d})
        t += d + 0.06
    return out


def _whisper_words(x: np.ndarray, sr: int, text: str) -> list | None:
    """Word times (s, from the clip's start) from a CPU aligner when one is installed: stable-ts's align (the text is
    known, so it is forced alignment), else faster-whisper's word timestamps. None when neither is."""
    try:
        import stable_whisper  # type: ignore
    except ImportError:
        stable_whisper = None
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != 16000:
        from scipy.signal import resample_poly
        g = math.gcd(sr, 16000)
        x = resample_poly(x, 16000 // g, sr // g)
    x = x.astype(np.float32)
    if stable_whisper is not None:
        m = stable_whisper.load_model("base", device="cpu")
        r = m.align(x, text, language="en")
        return [{"w": w.word.strip(), "start": float(w.start), "end": float(w.end)} for w in r.all_words()]
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        return None
    m = WhisperModel("base.en", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(x, word_timestamps=True, initial_prompt=text)
    return [{"w": w.word.strip(), "start": float(w.start), "end": float(w.end)} for s in segs for w in s.words]


def measure_line(x: np.ndarray, sr: int, f0: float, f1: float, fps: float) -> dict | None:
    """The speech onset/offset (master frames, floats) of the voice in master frames [f0, f1) of a stem that starts on
    frame 0, by VAD; None when the slot is silent."""
    i0, i1 = max(0, int(f0 / fps * sr)), min(len(x), int(f1 / fps * sr))
    seg = x[i0:i1]
    if len(seg) < sr // 20:
        return None
    env = envelope(seg, sr, offset_s=i0 / sr)
    spans = LS.vad(env.values, env.rate, env.offset_s)
    if not spans:
        return None
    return {"onset": spans[0][0] * fps, "offset": spans[-1][1] * fps, "spans": [[a * fps, b * fps] for a, b in spans]}


LOCATE_SR = 8000


def _mono8k(x: np.ndarray, sr: int) -> np.ndarray:
    from scipy.signal import resample_poly
    if x.ndim > 1:
        x = x.mean(axis=1)
    g = math.gcd(sr, LOCATE_SR)
    return resample_poly(x.astype(np.float64), LOCATE_SR // g, sr // g)


def locate(needle: np.ndarray, hay: np.ndarray, sr: int, hay_sr: int | None = None) -> tuple:
    """Where a line's WAV sits inside a longer recording (a stem, or the mix with music under it): the time (s) of
    the needle's first sample in `hay` and the normalised correlation at that lag (1 = the same samples; a voice under
    ducked music reads ~0.4-0.9; another take of the line ~0.1-0.3). Waveform cross-correlation at 8 kHz, so the time
    is good to a sample there (0.125 ms)."""
    from scipy.signal import correlate
    a = _mono8k(needle, sr)
    b = _mono8k(hay, hay_sr or sr)
    if len(b) < len(a):
        return None, 0.0
    c = correlate(b, a, mode="valid", method="fft")
    e = np.concatenate([[0.0], np.cumsum(b * b)])
    win = np.sqrt(np.maximum(e[len(a):] - e[:-len(a)], 1e-12))
    score = c / (win * (np.linalg.norm(a) + 1e-12))
    i = int(np.argmax(score))
    return i / LOCATE_SR, float(score[i])


def build_cues(lines_doc: dict, stems: dict, fps: float = 24.0, words: str = "auto", pre_s: float = 0.5,
               post_s: float = 0.5, line_dir: Path | None = None, mix: Path | None = None,
               min_score: float = 0.6, min_mix_score: float = 0.8, max_mismatch_frames: float = 0.5,
               mix_voice: Path | None = None, mix_meta: dict | None = None) -> dict:
    """A measured cues.json from the line list (an earlier cues.json: who, text, wav, file_frame, slot_end per line)
    and the speakers' stems as the mix places them (frame 0 = sample 0). Per line: the VAD onset/offset in the window
    from file_frame - pre_s to its file's end (or slot_end) + post_s; words aligned in that span (`words`: auto |
    whisper | estimate | none), snapped so the first starts at the onset and the last ends at the offset.

    With `line_dir` (the line WAVs the face is solved from): each line WAV is LOCATED in its stem by cross-correlation
    (file_frame measured, not trusted from the list) and the VAD runs on exactly that span. A line WAV that is not
    in the stem (score < min_score: another take) FAILS. With `mix` (the audio the cut plays): each line is located
    in the mix too and FAILS when the mix plays it more than `max_mismatch_frames` away from the stem (round 4: the
    face was solved from stems whose L1 sat ~14 frames before the mix's), or not at all."""
    loaded = {who: read_wav(Path(p)) for who, p in stems.items()}
    # the lines are located in the mix's own voice stem when there is one (mix.py writes stem-voice.wav: the voice
    # as it went into the master, so the same samples score ~1.0); else in the mix itself (music under it)
    mixed = read_wav(Path(mix_voice or mix), mono=True) if (mix or mix_voice) else None
    out = {}
    issues = []
    def finish_line(k, rec, text):
        x, sr = loaded[rec["who"]]
        t0, t1 = rec["voice_frame"] / fps, rec["end_frame"] / fps
        ws, src = None, "estimate"
        if words in ("auto", "whisper"):
            i0, i1 = int(t0 * sr) - sr // 10, int(t1 * sr) + sr // 10
            try:
                got = _whisper_words(x[max(0, i0):i1], sr, text)
            except Exception as e:  # an aligner that is installed but fails: say so, estimate
                got = None
                issues.append({"code": "aligner", "line": k, "severity": "warn", "message": f"{k}: aligner failed: {e}",
                               "fix": "pip install stable-ts (CPU), or accept the estimate"})
            if got:
                base = max(0, i0) / sr
                ws, src = [{"w": w["w"], "start": base + w["start"], "end": base + w["end"]} for w in got], "whisper"
            elif words == "whisper":
                raise SystemExit("no aligner installed: uv pip install stable-ts (or faster-whisper), or --words estimate")
        if ws is None and words != "none":
            ws = _estimate_words(text, t0, t1)
        if ws:
            ws[0]["start"] = t0 if abs(ws[0]["start"] - t0) < 0.15 or src == "estimate" else ws[0]["start"]
            ws[-1]["end"] = t1 if abs(ws[-1]["end"] - t1) < 0.15 or src == "estimate" else ws[-1]["end"]
            rec["words"] = [{"w": w["w"], "start": round(w["start"] * fps, 2), "end": round(w["end"] * fps, 2)}
                            for w in ws]
        rec["words_source"] = src if ws else "none"
        out[k] = rec

    for k, c in sorted(lines_doc["lines"].items(), key=lambda kc: kc[1].get("file_frame", 0)):
        who = c["who"]
        if who not in loaded:
            raise SystemExit(f"no stem for {who} (line {k}): pass --stem {who}=<vo_{who}.wav>")
        x, sr = loaded[who]
        start = c.get("file_frame", c.get("voice_frame", 0)) - pre_s * fps
        end = max(c.get("end_frame") or 0, c.get("slot_end") or 0) + post_s * fps
        loc = {}
        lw = Path(line_dir) / c["wav"] if line_dir and c.get("wav") else None
        if lw is not None and not lw.exists():
            issues.append({"code": "no_wav", "line": k, "severity": "fail",
                           "message": f"{k}: {lw} does not exist, so the line was not located (mix_score None)",
                           "fix": "one WAV holding several lines (L3 = L3a + L3b) is one entry with \"split\" "
                           "(r5/lips.py plan_lines does it); or name the WAV that exists"})
        if lw is not None and lw.exists():
            y, ysr = read_wav(lw)
            t, sc = locate(y, x, ysr, sr)
            loc = {"file_frame": round(t * fps, 2) if t is not None else None, "stem_score": round(sc, 3)}
            if t is None or sc < min_score:
                issues.append({"code": "not_in_stem", "line": k, "severity": "fail",
                               "message": f"{k}: {c['wav']} is not in the {who} stem (best match {sc:.2f} at "
                               f"f{(t or 0) * fps:.1f}): the stem holds another take or edit",
                               "fix": "rebuild the stems from the line WAVs the face is solved from (vo.py cues), or "
                               "solve from the WAVs the stems were made of"})
            else:
                start, end = t * fps - 0.1 * fps, (t + len(y) / ysr) * fps + 0.1 * fps
                if mixed is not None:
                    mx, msr = mixed
                    tm, scm = locate(y, mx, ysr, msr)
                    loc["mix_frame"] = round(tm * fps, 2) if tm is not None else None
                    loc["mix_score"] = round(scm, 3)
                    if tm is None or scm < min_mix_score:
                        issues.append({"code": "not_in_mix", "line": k, "severity": "fail",
                                       "message": f"{k}: {c['wav']} is not in the mix (best {scm:.2f}): the cut plays "
                                       "another take", "fix": "re-mix from these stems (mix.py --vo-dir) or solve "
                                       "the face from the WAVs the mix was made of"})
                    elif abs(tm - t) * fps > max_mismatch_frames:
                        d = (tm - t) * fps
                        issues.append({"code": "mix_mismatch", "line": k, "severity": "fail",
                                       "message": f"{k}: the mix plays it on f{tm * fps:.1f}, the stem on f{t * fps:.1f} "
                                       f"({d:+.1f} frames): a face solved from the stem is {abs(d):.1f} frames "
                                       f"{'EARLY' if d > 0 else 'LATE'} in the cut",
                                       "fix": "one timebase: re-mix from these stems (mix.py --vo-dir) and re-cut, "
                                       "or rebuild the stems to the mix's placement before solving"})
        m = measure_line(x, sr, start, end, fps)
        if m is None:
            issues.append({"code": "silent", "line": k, "severity": "fail",
                           "message": f"{k}: no voice in its stem between f{start:.0f} and f{end:.0f}",
                           "fix": "the stem is not the one the mix plays, or the line moved: rebuild the stems"})
            continue
        rec = {**{kk: c[kk] for kk in ("who", "text", "wav", "take", "mood", "intensity", "slot_end", "candidates")
                  if kk in c},
               "file_frame": loc.get("file_frame", c.get("file_frame")), "file_frame_listed": c.get("file_frame"),
               **{kk: v for kk, v in loc.items() if kk != "file_frame"}, "voice_frame": round(m["onset"], 2),
               "end_frame": round(m["offset"], 2), "voice_frame_planned": c.get("voice_frame"),
               "spans": [[round(a, 2), round(b, 2)] for a, b in m["spans"]]}
        if c.get("voice_frame") is not None and abs(m["onset"] - c["voice_frame"]) > 1.0:
            issues.append({"code": "moved", "line": k, "severity": "warn",
                           "message": f"{k}: the voice starts on f{m['onset']:.1f}, not the planned f{c['voice_frame']}",
                           "fix": "place the face from voice_frame/file_frame here (measured), never from the plan"})
        parts = [(k, rec, c.get("text", ""))]
        if c.get("split"):  # one WAV holding several lines (L3 = L3a + L3b): cut at the longest pauses
            subs, spans = c["split"], m["spans"]
            if len(spans) < len(subs):
                issues.append({"code": "split", "line": k, "severity": "fail",
                               "message": f"{k}: {len(spans)} voiced spans, cannot split into {len(subs)} lines",
                               "fix": "solve and caption it as one line, or split the WAV by hand"})
            else:
                gaps = sorted(range(1, len(spans)), key=lambda i: spans[i][0] - spans[i - 1][1], reverse=True)
                cuts = sorted(gaps[:len(subs) - 1])
                bounds = [0] + cuts + [len(spans)]
                parts = []
                for sub, i0, i1 in zip(subs, bounds, bounds[1:]):
                    r = {**rec, "text": sub.get("text", ""), "voice_frame": round(spans[i0][0], 2),
                         "end_frame": round(spans[i1 - 1][1], 2), "split_of": k,
                         "spans": [[round(x, 2), round(y, 2)] for x, y in spans[i0:i1]],
                         "voice_frame_planned": sub.get("voice_frame")}
                    for kk in ("mood", "intensity", "slot_end"):
                        if kk in sub:
                            r[kk] = sub[kk]
                    parts.append((sub["id"], r, sub.get("text", "")))
        for k, rec, text in parts:
            finish_line(k, rec, text)
    if mix_meta is not None:  # the CLI passes {} when --mix has no --mix-json: unproven fails
        issues += same_vo({who: Path(p) for who, p in stems.items()}, Path(mix) if mix else None, mix_voice, mix_meta,
                          line_dir)
    doc = {"fps": fps, "frames": lines_doc.get("frames"), "measured": True, "lines": out,
           "stems": {who: {"path": str(p), "sha256": sha256(Path(p))} for who, p in stems.items()},
           "mix": {"path": str(mix), "sha256": sha256(Path(mix))} if mix else None,
           "mix_voice": {"path": str(mix_voice), "sha256": sha256(Path(mix_voice))} if mix_voice else None,
           "line_dir": str(line_dir) if line_dir else None, "issues": issues}
    return doc


def same_vo(stems: dict, mix: Path | None, mix_voice: Path | None, meta: dict | None,
            line_dir: Path | None = None) -> list:
    """The round-4 bug as a check: the voice the MIX was built from must be the voice the FACES are solved from.
    Proven by provenance, not by ear: mix.json (mix.py) records the sha256 of the voice stems it read
    ("voice_sha256": {who: sha}), of the voice stem it wrote ("stem_voice_sha256") and of mix.wav ("mix_sha256");
    every one must equal the files here. A mix without those records cannot be proven: it fails too."""
    out = []

    def bad(code, msg, fix):
        out.append({"code": code, "line": "", "severity": "fail", "message": msg, "fix": fix})
    remix = "re-mix from the solve's stems (mix.py --vo-dir <the stems' dir>), then rebuild the cues"
    if meta and meta.get("source") == "separated":  # the line WAVs were cut from this very mix's voice
        if mix is not None and meta.get("mix_sha256") != sha256(mix):
            bad("vo_not_mixed", f"the line WAVs were separated from another mix ({str(meta.get('mix_sha256'))[:12]}),"
                f" not {mix.name} ({sha256(mix)[:12]})", "separate again from the delivered mix (lips.py separate)")
        for name, sha in (meta.get("lines_sha256") or {}).items():
            p = Path(line_dir) / name if line_dir else None
            if p is None or not p.exists() or sha256(p) != sha:
                bad("vo_not_mixed", f"{name} is not the WAV cut from the mix's voice", "cut it again (lips.py lines)")
        return out
    if not meta:
        bad("vo_unproven", "no mix.json: nothing says which voice the mix was built from", remix)
        return out
    want = meta.get("voice_sha256") or {}
    if not want:
        bad("vo_unproven", "mix.json records no voice_sha256 (a mix.py from before round 5)", remix)
    for who, p in stems.items():
        got = sha256(p)
        if want and want.get(who) != got:
            bad("vo_not_mixed", f"the {who} stem the faces are solved from ({p.name}, {got[:12]}) is not the one the "
                f"mix was built from ({str(want.get(who))[:12]})", remix)
    if mix is not None and meta.get("mix_sha256") and meta["mix_sha256"] != sha256(mix):
        bad("mix_changed", f"{mix.name} is not the mix.json's mix (re-mixed or replaced since)", remix)
    if mix_voice is not None and meta.get("stem_voice_sha256") and meta["stem_voice_sha256"] != sha256(mix_voice):
        bad("mix_changed", f"{mix_voice.name} is not the mix.json's voice stem", remix)
    return out


def prepare_take(x: np.ndarray, sr: int, floor_db: float = -42.0, pre_s: float = 0.05, post_s: float = 0.25) -> tuple:
    """A raw take as vo.py build made a line WAV of it: trimmed from `pre_s` before the first moment above `floor_db`
    (relative to its loudest 20 ms) to `post_s` after the last, 10 ms fades, voiced RMS to -20 dBFS with the peak under
    -1 dBFS. Returns (line samples, the trim's start in the take, s)."""
    if x.ndim > 1:
        x = x.mean(axis=1)
    hop = sr // 100
    n = len(x) // hop - 1
    fr = np.stack([x[i * hop:i * hop + 2 * hop] for i in range(max(1, n))])
    e = 10 * np.log10(np.mean(fr ** 2, axis=1) + 1e-12)
    on = np.where(e > e.max() + floor_db)[0]
    t0, t1 = on[0] * hop / sr, (on[-1] + 2) * hop / sr
    a, b = max(0.0, t0 - pre_s), min(len(x) / sr, t1 + post_s)
    y = x[int(a * sr):int(b * sr)].astype(np.float32).copy()
    fade = int(0.01 * sr)
    y[:fade] *= np.linspace(0, 1, fade)
    y[-fade:] *= np.linspace(1, 0, fade)
    h = sr // 100
    m = 1 + max(0, len(y) - 2 * h) // h
    rms = np.sqrt(np.mean(np.stack([y[i * h:i * h + 2 * h] for i in range(m)]) ** 2, axis=1))
    act = rms[rms > rms.max() * 0.1]
    y *= min(10 ** (-20 / 20) / np.sqrt(np.mean(act ** 2)), 10 ** (-1 / 20) / np.abs(y).max())
    return y, a


def _takes_for(takes_dir: Path | None, key: str) -> list:
    """The raw takes that may be a line: takes_dir/<line>/*.wav (vo.py's layout), else takes_dir/<line>-*.wav."""
    if not takes_dir:
        return []
    d = Path(takes_dir)
    return sorted((d / key).glob("*.wav")) if (d / key).is_dir() else sorted(d.glob(f"{key}-*.wav"))


def stems_from_mix(lines_doc: dict, line_dir: Path, mix: Path, out_dir: Path, fps: float = 24.0,
                   min_mix_score: float = 0.8, takes_dir: Path | None = None) -> tuple:
    """The delivered mix is canonical (the viewer hears it): each line is located in the mix by cross-correlation,
    and each speaker's voice stem is rebuilt with every line at exactly that place (frame 0 = sample 0, the mix's
    length). The line is the line WAV in `line_dir`, or, when `takes_dir` is given, whichever of it and the line's raw
    takes (takes_dir/<line>/*.wav) the mix holds best: a take is trimmed and levelled as vo.py build does and placed
    where its trimmed start sits. The chosen line WAVs (what the face is solved from) are written to out_dir/lines.
    Returns ({who: stem path}, lines_doc with file_frame = the mix's and "take", issues, out_dir/lines). A line the
    mix does not hold fails (not_in_mix, with every candidate's score)."""
    mx, msr = read_wav(Path(mix), mono=True)
    out_dir = Path(out_dir)
    (out_dir / "lines").mkdir(parents=True, exist_ok=True)
    stems, issues, doc = {}, [], {**lines_doc, "lines": {}}
    import soundfile as sf
    sr0 = None
    for k, c in sorted(lines_doc["lines"].items(), key=lambda kc: kc[1].get("file_frame", 0)):
        cands = []
        if (Path(line_dir) / c["wav"]).exists():
            cands.append(("line", Path(line_dir) / c["wav"]))
        cands += [(p.stem, p) for p in _takes_for(takes_dir, k)]
        scored = []
        for name, path in cands:
            y, ysr = read_wav(path)
            off = 0.0
            if name != "line":
                y, off = prepare_take(y, ysr)
            t, sc = locate(y, mx, ysr, msr)
            scored.append((sc, name, y, ysr, t))
        if not scored:
            issues.append({"code": "no_wav", "line": k, "severity": "fail", "message": f"{k}: no line WAV or take",
                           "fix": f"put {c['wav']} in {line_dir} or its takes in {takes_dir}/{k}/"})
            continue
        sc, name, y, ysr, t = max(scored, key=lambda r: r[0])
        sr0 = sr0 or ysr
        if ysr != sr0:
            raise SystemExit(f"{k}: {ysr} Hz, the other lines {sr0} Hz")
        board = {n: round(s_, 3) for s_, n, *_ in sorted(scored, key=lambda r: -r[0])[:5]}
        if t is None or sc < min_mix_score:
            issues.append({"code": "not_in_mix", "line": k, "severity": "fail",
                           "message": f"{k}: neither {c['wav']} nor any take is in the mix (best: {board})",
                           "fix": "the mix was made from WAVs that are gone: re-mix from these (mix.py --vo-dir) "
                           "and re-cut, or find the mix's own VO"})
            continue
        st = stems.setdefault(c["who"], np.zeros(int(round(len(mx) / msr * ysr)), np.float32))
        i0 = int(round(t * ysr))
        st[i0:i0 + len(y)] += y[:max(0, len(st) - i0)]
        sf.write(out_dir / "lines" / c["wav"], y, ysr, subtype="PCM_24")
        doc["lines"][k] = {**c, "file_frame": round(t * fps, 2), "file_frame_listed": c.get("file_frame"),
                           "mix_score": round(sc, 3), "take": c.get("take") if name == "line" else name,
                           "candidates": board}
    paths = {}
    for who, st in stems.items():
        paths[who] = out_dir / f"vo_{who}.wav"
        sf.write(paths[who], st, sr0, subtype="PCM_24")
    return paths, doc, issues, out_dir / "lines"


def cues_from_mix(lines_doc: dict, line_dir: Path, mix: Path, stems_dir: Path, old_stems: dict | None = None,
                  fps: float = 24.0, words: str = "auto", takes_dir: Path | None = None) -> dict:
    """The round-5 cues: the mix canonical (stems_from_mix), measured on the rebuilt stems and verified against the
    mix (build_cues with line_dir + mix: every line must pass). The old stems, if given, are checked against the mix
    too and reported under "old_stems" (round 4's: mix_mismatch on L1)."""
    paths, placed, issues, chosen = stems_from_mix(lines_doc, line_dir, mix, stems_dir, fps, takes_dir=takes_dir)
    doc = build_cues(placed, paths, fps, words, line_dir=chosen, mix=mix)
    doc["line_dir"] = str(chosen)  # the line WAVs to solve from (a take the mix holds, where the line WAV was not)
    doc["issues"] = issues + doc["issues"]
    doc["canonical"] = "mix"
    if old_stems:
        old = build_cues(lines_doc, old_stems, fps, "none", line_dir=line_dir, mix=mix)  # the r4 WAVs, as they were
        doc["old_stems"] = {"stems": old["stems"], "issues": [i for i in old["issues"] if i["severity"] == "fail"],
                            "pass": not [i for i in old["issues"] if i["severity"] == "fail"]}
    return doc


def stems_from_lines(lines_doc: dict, line_dir: Path, out_dir: Path, frames: int, fps: float = 24.0) -> tuple:
    """Voice stems from the line WAVs (the ones the faces are solved from), each placed so its first sound (VAD)
    lands on the line's planned voice_frame (a split WAV: its first part's). Returns ({who: path}, {line: file_frame},
    issues). Mix from these stems (mix.py --vo-dir out_dir) and the mix's voice IS the solve's."""
    import soundfile as sf
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stems, placed, issues, sr0 = {}, {}, [], None
    for k, c in sorted(lines_doc["lines"].items(), key=lambda kc: kc[1].get("voice_frame", 0)):
        y, sr = read_wav(Path(line_dir) / c["wav"])
        sr0 = sr0 or sr
        if sr != sr0:
            raise SystemExit(f"{c['wav']}: {sr} Hz, the other lines {sr0} Hz")
        env = envelope(y, sr)
        sp = LS.vad(env.values, env.rate)
        if not sp:
            issues.append({"code": "silent", "line": k, "severity": "fail", "message": f"{c['wav']} has no voice",
                           "fix": "replace the WAV"})
            continue
        if c.get("place") == "file_frame":  # a WAV whose place is known (cut from the mix): exactly there
            ff = c["file_frame"]
        else:
            target = (c["split"][0].get("voice_frame") if c.get("split") else None) or c["voice_frame"]
            ff = target - sp[0][0] * fps
        st = stems.setdefault(c["who"], np.zeros(int(round(frames / fps * sr)), np.float32))
        i0 = int(round(ff / fps * sr))
        if i0 < 0:
            raise SystemExit(f"{k}: would start before frame 0")
        st[i0:i0 + len(y)] += y[:max(0, len(st) - i0)]
        placed[k] = round(ff, 2)
    paths = {}
    for who, st in stems.items():
        paths[who] = out_dir / f"vo_{who}.wav"
        sf.write(paths[who], st, sr0, subtype="PCM_24")
    return paths, placed, issues


def median_f0(x: np.ndarray, sr: int, lo: float = 70.0, hi: float = 400.0) -> float | None:
    """The median pitch (Hz) of a voice's loud frames, by autocorrelation (40 ms frames): him ~100-150, her ~180-260."""
    if x.ndim > 1:
        x = x.mean(axis=1)
    n, hop = int(0.04 * sr), int(0.01 * sr)
    if len(x) < n:
        return None
    fr = np.stack([x[i:i + n] for i in range(0, len(x) - n, hop)])
    e = (fr ** 2).mean(axis=1)
    loud = fr[e > np.percentile(e, 60)]
    f0s = []
    for f in loud:
        f = f - f.mean()
        ac = np.correlate(f, f, "full")[n - 1:]
        a, b = int(sr / hi), int(sr / lo)
        if ac[0] <= 0 or b >= len(ac):
            continue
        k = a + int(np.argmax(ac[a:b]))
        if ac[k] / ac[0] > 0.4:
            f0s.append(sr / k)
    return float(np.median(f0s)) if f0s else None


def lines_from_voice(vocals: Path, plan: dict, out_dir: Path, mix: Path, fps: float = 24.0, model: str = "",
                     split_f0_hz: float = 165.0, pre_s: float = 0.05, post_s: float = 0.25) -> tuple:
    """Per-line WAVs cut from a voice separated from the delivered mix (demucs vocals): per planned line (plan lines
    {id: {who, text, voice_frame, slot_end}}), the voice is found by VAD between 0.6 s before its planned start and
    the next line's planned start, cut from `pre_s` before its first sound to `post_s` after its last (as vo.py made
    line WAVs), levelled to -20 dBFS voiced RMS. Each line's speaker is checked by pitch (under `split_f0_hz` = him).
    Writes out_dir/<id>.wav and out_dir/voice.json (the provenance: the mix's sha256, the model, every WAV's sha256).
    Returns (lines {id: {..., wav, file_frame, f0_hz}}, issues, manifest)."""
    import soundfile as sf
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    v, sr = read_wav(Path(vocals), mono=True)
    env = envelope(v, sr)
    vals = np.array(env.values)
    p20, p98 = np.percentile(vals, 20), np.percentile(vals, 98)
    on, off = p20 + 0.45 * (p98 - p20), p20 + 0.25 * (p98 - p20)  # over the separation's own floor (leakage)
    order = sorted(plan["lines"].items(), key=lambda kc: kc[1]["voice_frame"])
    lines, issues, manifest = {}, [], {"source": "separated", "mix_sha256": sha256(Path(mix)), "model": model,
                                       "vocals_sha256": sha256(Path(vocals)), "lines_sha256": {}}
    windows = []
    prev_end = 0.0  # s: a window never reaches back into the line before (r5: L4b's caught L4a's tail)
    for i, (k, c) in enumerate(order):
        a = max(c["voice_frame"] - 0.6 * fps, (prev_end + 0.05) * fps)
        b = order[i + 1][1]["voice_frame"] - 0.15 * fps if i + 1 < len(order) else (c.get("slot_end") or a) + 2 * fps
        i0, i1 = max(0, int(a / fps * env.rate)), min(len(vals), int(b / fps * env.rate))
        sp = LS.vad(list(vals[i0:i1]), env.rate, i0 / env.rate, on=on, off=off)
        if not sp:
            issues.append({"code": "silent", "line": k, "severity": "fail",
                           "message": f"{k}: no voice in the separated vocals between f{a:.0f} and f{b:.0f}",
                           "fix": "the separation lost it, or the line is elsewhere: check the mix by ear"})
            continue
        t0, t1 = sp[0][0], sp[-1][1]
        prev_end = t1
        c0, c1 = max(0.0, t0 - pre_s, windows[-1][1] if windows else 0.0), min(len(v) / sr, t1 + post_s)
        y = v[int(c0 * sr):int(c1 * sr)].astype(np.float32).copy()
        fade = int(0.01 * sr)
        y[:fade] *= np.linspace(0, 1, fade)
        y[-fade:] *= np.linspace(1, 0, fade)
        h = sr // 100
        rms = np.sqrt(np.mean(np.stack([y[j:j + 2 * h] for j in range(0, max(1, len(y) - 2 * h), h)]) ** 2, axis=1))
        act = rms[rms > rms.max() * 0.1]
        y *= min(10 ** (-20 / 20) / np.sqrt(np.mean(act ** 2)), 10 ** (-1 / 20) / np.abs(y).max())
        f0 = median_f0(y, sr)
        who = "him" if f0 is not None and f0 < split_f0_hz else "her"
        if f0 is None or who != c["who"]:
            issues.append({"code": "speaker", "line": k, "severity": "fail",
                           "message": f"{k}: the voice at f{t0 * fps:.0f} reads as {who} (median f0 {f0 or 0:.0f} Hz), the "
                           f"plan says {c['who']}", "fix": "the window caught the other presenter: check the plan's "
                           "frames against the mix"})
        p = out_dir / f"{k}.wav"
        sf.write(p, y, sr, subtype="PCM_24")
        manifest["lines_sha256"][p.name] = sha256(p)
        windows.append((t0, t1))
        lines[k] = {**{kk: c[kk] for kk in ("who", "text", "mood", "intensity", "slot_end") if kk in c},
                    "wav": p.name, "file_frame": round(c0 * fps, 2), "voice_frame": round(t0 * fps, 2),
                    "voice_frame_planned": c["voice_frame"], "f0_hz": round(f0, 1) if f0 else None}
    # leakage: the vocals' level between the lines (from the first to the last), against their level on the lines
    if windows:
        span = (windows[0][0], windows[-1][1])
        mask_line = np.zeros(len(vals), bool)
        for t0, t1 in windows:
            mask_line[int(t0 * env.rate):int(t1 * env.rate)] = True
        idx = np.arange(int(span[0] * env.rate), min(len(vals), int(span[1] * env.rate)))
        n_hop = max(1, int(sr / env.rate))
        rms_db = lambda m: 10 * np.log10(np.mean(np.concatenate([v[j * n_hop:(j + 1) * n_hop] ** 2 for j in m]) + 1e-12))  # noqa: E731
        gaps, onl = idx[~mask_line[idx]], idx[mask_line[idx]]
        if len(gaps) and len(onl):
            manifest["leak_db"] = round(float(rms_db(gaps) - rms_db(onl)), 1)
            if manifest["leak_db"] > -25:
                issues.append({"code": "leak", "line": "", "severity": "warn",
                               "message": f"the separated vocals are only {-manifest['leak_db']:.0f} dB quieter between "
                               "the lines than on them: music may reach the solver",
                               "fix": "lips.py bias decides (corr >= 0.5); else regenerate the takes (vo.py)"})
    (out_dir / "voice.json").write_text(json.dumps({**manifest, "issues": issues}, indent=1))
    return lines, issues, manifest


def stale(cues: dict, stems: dict) -> list:
    """The stems whose content differs from what cues.json was measured on ([] = fresh)."""
    have = cues.get("stems") or {}
    return [who for who, p in stems.items() if have.get(who, {}).get("sha256") != sha256(Path(p))]


# --- the curve gate offline ---------------------------------------------------------------------------------------

def curve_check(curves: dict, start_frame: float, wav: Path, cues: dict, who: str, fps: float = 24.0,
                wav_frame: float = 0.0, expected_lag_s: float = 0.0) -> dict:
    x, sr = read_wav(wav)
    env = envelope(x, sr, offset_s=wav_frame / fps)
    cur = LS.place({n: (list(tv[0]), list(tv[1])) for n, tv in curves.items()}, start_frame / fps)
    lines = []
    for k, c in cues["lines"].items():
        if c["who"] != who:
            continue
        rec = {"id": k, "t0": c["voice_frame"] / fps, "t1": c["end_frame"] / fps}
        if c.get("words") and c.get("words_source") not in (None, "estimate", "none"):  # estimated words prove nothing
            rec["words"] = [[w["start"] / fps, w["end"] / fps] for w in c["words"]]
        lines.append(rec)
    return LS.check(env, cur, lines, fps=fps, expected_lag_s=expected_lag_s)


# --- the render gate ----------------------------------------------------------------------------------------------

def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise SystemExit("ffmpeg is needed (apt install ffmpeg)")
    return exe


def video_size(video: Path) -> tuple:
    out = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate", "-of", "json", str(video)], capture_output=True,
                         text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den)


def read_gray(video: Path, f0: int, f1: int, fps: float, width: int = 640) -> np.ndarray:
    """Frames [f0, f1) as grey float32 [n, h, w] at `width` px wide (ffmpeg, frame-accurate select)."""
    w, h, _ = video_size(video)
    hh = int(round(h * width / w / 2)) * 2
    cmd = [_ffmpeg(), "-v", "error", "-i", str(video), "-vf",
           f"select='between(n\\,{f0}\\,{f1 - 1})',scale={width}:{hh},format=gray", "-vsync", "0", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.uint8)
    n = len(a) // (width * hh)
    return a[:n * width * hh].reshape(n, hh, width).astype(np.float32) / 255.0


def mouth_signals(frames: np.ndarray, boxes: list) -> dict:
    """Per frame, from the mouth crop: "dark" (how much of the crop's centre is darker than its rim: an open mouth
    shows its cavity) and "motion" (mean absolute change from the previous frame)."""
    n, h, w = frames.shape
    dark, motion, prev = [], [], None
    for i in range(n):
        x0, y0, x1, y1 = boxes[i]
        a0, a1 = int(max(0, x0) * w), int(min(1, x1) * w)
        b0, b1 = int(max(0, y0) * h), int(min(1, y1) * h)
        crop = frames[i, b0:max(b1, b0 + 4), a0:max(a1, a0 + 4)]
        ch, cw = crop.shape
        core = crop[ch // 4:3 * ch // 4, cw // 4:3 * cw // 4]
        rim = np.concatenate([crop[:ch // 6].ravel(), crop[-ch // 6:].ravel()]) if ch >= 6 else crop.ravel()
        dark.append(float(np.median(rim) - np.percentile(core, 20)))
        if prev is not None and prev.shape == crop.shape:
            motion.append(float(np.abs(crop - prev).mean()))
        else:
            motion.append(0.0)
        prev = crop
    return {"dark": dark, "motion": motion}


def _band(v: list, rate: float) -> list:
    return LS.bandpass(list(v), rate, 1.0, min(8.0, rate / 2.5))


def av_lag(env: AU.Envelope, sig: list, f0: int, fps: float, max_lag_s: float = 1.0, motion: bool = False) -> dict:
    """Lag (s; < 0 = picture early) and correlation of a per-frame mouth signal against the voice, frame-rate."""
    t = [(f0 + i) / fps for i in range(len(sig))]
    a = [env.at(x) for x in t]
    if motion:  # motion follows the envelope's changes, not its level
        a = [abs(a[i] - a[i - 1]) if i else 0.0 for i in range(len(a))]
    return LS.xcorr(_band(a, fps), _band(sig, fps), fps, max_lag_s)


def _boxes_for(frames: list, boxes: dict | None, box: list | None) -> list:
    out = []
    for f in frames:
        b = None
        if boxes:
            rec = boxes.get(str(f)) or boxes.get(f)
            b = rec.get("box") if isinstance(rec, dict) else rec
        b = b or box
        if not b:
            raise SystemExit(f"no mouth box for frame {f}: pass --boxes (lipsync.mouth_boxes) or --box x0,y0,x1,y1")
        out.append(b)
    return out


def render_check(video: Path, wav: Path, cues: dict, who: str, boxes: dict | None = None, box: list | None = None,
                 wav_frame: float = 0.0, pad_s: float = 1.0, max_lag_frames: float = 1.0, min_corr: float = 0.3,
                 control_shift: int = 6, syncnet_dir: Path | None = None, min_conf: float = 3.0,
                 frames_override: dict | None = None) -> dict:
    """The video-level gate on a render: per line of `who`, the mouth crop's darkness and motion against the voice
    (the better of the two), with a control (the voice shifted `control_shift` frames must move the lag by that
    much, else the measure is not sensitive on this shot: inconclusive), and SyncNet when available.
    frames_override: {line: ndarray [n, h, w]} for tests (no ffmpeg)."""
    w_h_fps = video_size(video) if frames_override is None else (0, 0, cues.get("fps", 24.0))
    fps = w_h_fps[2]
    x, sr = read_wav(wav)
    env = envelope(x, sr, offset_s=wav_frame / fps)
    res, issues, inconclusive = {}, [], []
    for k, c in sorted(cues["lines"].items(), key=lambda kc: kc[1]["voice_frame"]):
        if c["who"] != who:
            continue
        f0 = int(math.floor(c["voice_frame"] - pad_s * fps))
        f1 = int(math.ceil(c["end_frame"] + pad_s * fps))
        frames = frames_override[k] if frames_override else read_gray(video, f0, f1, fps)
        bx = _boxes_for(list(range(f0, f0 + len(frames))), boxes, box)
        sig = mouth_signals(frames, bx)
        best = None
        for name in ("dark", "motion"):
            r = av_lag(env, sig[name], f0, fps, motion=name == "motion")
            if best is None or r["corr"] > best[1]["corr"]:
                best = (name, r)
        name, r = best
        shifted = AU.Envelope(env.values, env.rate, env.offset_s + control_shift / fps)
        rc = av_lag(shifted, sig[name], f0, fps, motion=name == "motion")
        moved = (r["lag_s"] - rc["lag_s"]) * fps  # the voice made later by k frames: the mouth reads k frames earlier
        sensitive = abs(moved - control_shift) <= 1.5
        lag_f = r["lag_s"] * fps
        rec = {"frames": [f0, f1], "signal": name, "lag_frames": round(lag_f, 2), "corr": round(r["corr"], 3),
               "control_moved_frames": round(moved, 2), "sensitive": sensitive}
        if not sensitive or r["corr"] < 0.15:
            inconclusive.append(k)
            rec["verdict"] = "inconclusive"
        elif abs(lag_f) > max_lag_frames or r["corr"] < min_corr:
            rec["verdict"] = "fail"
            way = "EARLY" if lag_f < 0 else "LATE"
            issues.append({"code": "render_lag" if abs(lag_f) > max_lag_frames else "render_corr", "line": k,
                           "severity": "fail", "message": f"{k}: in the render the mouth is {abs(lag_f):.1f} frames "
                           f"{way} (r {r['corr']:.2f})", "fix": "run lipsync.check on the sequence: it says whether the "
                           "face section or the solve is misplaced; re-place, re-render the shot"})
        else:
            rec["verdict"] = "pass"
        res[k] = rec
    sn = None
    if syncnet_dir:
        sn = syncnet(video, wav, cues, who, boxes, box, syncnet_dir, fps, wav_frame)
        for k, s in sn.get("lines", {}).items():
            off = s.get("offset_frames")
            if off is None:
                continue
            if abs(off) > max_lag_frames or s.get("conf", 0) < min_conf:
                issues.append({"code": "syncnet", "line": k, "severity": "fail",
                               "message": f"{k}: SyncNet offset {off:+.1f} frames, confidence {s.get('conf'):.1f} "
                               f"(limits |offset| <= {max_lag_frames:g}, conf >= {min_conf:g})",
                               "fix": "as render_lag; a low confidence alone on a CG face: compare with a known-good "
                               "line of the same character before trusting it"})
    verdict = "fail" if issues else ("inconclusive" if inconclusive else "pass")
    return {"pass": verdict == "pass", "verdict": verdict, "lines": res, "issues": issues,
            "inconclusive": inconclusive, "syncnet": sn, "fps": fps}


SYNCNET_RUN = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from SyncNetInstance import SyncNetInstance
class O: pass
opt = O(); opt.batch_size = 20; opt.vshift = int(sys.argv[4]); opt.tmp_dir = sys.argv[5]; opt.reference = "fm"
s = SyncNetInstance(); s.loadParameters(sys.argv[1] + "/data/syncnet_v2.model")
offset, conf, dist = s.evaluate(opt, videofile=sys.argv[2])
print(json.dumps({"offset": int(offset), "conf": float(conf), "min_dist": float(dist.min()) if hasattr(dist, "min") else None}))
"""


def syncnet(video: Path, wav: Path, cues: dict, who: str, boxes, box, syncnet_dir: Path, fps: float,
            wav_frame: float, vshift: int = 30) -> dict:
    """SyncNet (Chung & Zisserman 2016; joonson/syncnet_python) per line: the speaker's FACE crop (the mouth box
    grown to the face) at 224 px and 25 fps with the line's audio at 16 kHz, evaluated with vshift 30 (+-1.2 s: the
    default 15 cannot see a 0.7 s error). Offset in 25-fps frames, converted to the render's frames; positive =
    audio leads in syncnet_python's convention, reported here as the picture's lag (negative = picture early)."""
    out = {"lines": {}, "vshift": vshift}
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "run.py"
        script.write_text(SYNCNET_RUN)
        for k, c in cues["lines"].items():
            if c["who"] != who:
                continue
            f0 = max(0, int(c["voice_frame"] - 1.5 * fps))
            f1 = int(c["end_frame"] + 1.5 * fps)
            mid = (f0 + f1) // 2
            b = _boxes_for([mid], boxes, box)[0]
            cx, cy, half = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, (b[2] - b[0]) * 1.4
            clip = Path(tmp) / f"{k}.avi"
            w, h, _ = video_size(video)
            side = int(half * 2 * w)
            x0, y0 = int((cx - half) * w), int((cy - half * w / h * 1.3) * h)
            t0 = f0 / fps
            subprocess.run([_ffmpeg(), "-v", "error", "-y", "-ss", f"{t0:.4f}", "-t", f"{(f1 - f0) / fps:.4f}",
                            "-i", str(video), "-ss", f"{t0 - wav_frame / fps:.4f}", "-t", f"{(f1 - f0) / fps:.4f}",
                            "-i", str(wav), "-map", "0:v", "-map", "1:a", "-vf",
                            f"crop={side}:{side}:{max(0, x0)}:{max(0, y0)},scale=224:224,fps=25", "-ar", "16000",
                            "-ac", "1", "-c:v", "mjpeg", "-q:v", "2", str(clip)], check=True)
            r = subprocess.run([sys.executable, str(script), str(syncnet_dir), str(clip), "x", str(vshift),
                                str(Path(tmp) / "work")], capture_output=True, text=True)
            if r.returncode:
                out["lines"][k] = {"error": r.stderr[-400:]}
                continue
            got = json.loads(r.stdout.strip().splitlines()[-1])
            # syncnet_python: offset > 0 = the audio leads the video, i.e. the picture is late
            out["lines"][k] = {**got, "offset_frames": round(got["offset"] * fps / 25.0, 2)}
    return out


# --- gate v2 numbers (agent-09's film-qa gate) -------------------------------------------------------------------

def gate_numbers(curve_reports: dict, render_reports: dict, cues: dict | None, stems: dict) -> dict:
    """{"gate": {item: {"value", "where", "error"?}}} for film-qa gate from lipsync.check reports per speaker
    ({who: report}), render reports ({who: report}) and the cues + stems (freshness). Worst case over speakers and
    lines; a missing measure is an "error" (the gate fails it)."""
    g = {}

    def worst(items, key, pick):
        best = None
        for who, rep in items:
            for lid, rec in (rep.get("lines") or {}).items():
                v = rec.get(key)
                if v is None:
                    continue
                if best is None or pick(v, best[0]):
                    best = (v, f"{who} {lid} f{round(rec.get('t0', 0) * rep.get('fps', 24))}" if "t0" in rec
                            else f"{who} {lid} f{rec.get('frames', ['?'])[0]}")
        return best

    def put(item, got, conv=lambda v: v):
        g[item] = {"value": conv(got[0]), "where": got[1]} if got else {"value": None, "error": "not measured"}

    cur = list(curve_reports.items())
    put("lips.lag_frames", worst(cur, "lag_frames", lambda v, b: abs(v) > abs(b)), lambda v: round(abs(v), 2))
    put("lips.track_r", worst(cur, "corr", lambda v, b: v < b))
    put("lips.onset_lead_ms", worst(cur, "onset_lead_s", lambda v, b: v > b), lambda v: round(v * 1000))
    sil = [(who, s) for who, rep in cur for s in rep.get("silences", [])]
    for item, key in (("lips.silence_open", "open"), ("lips.silence_busy", "busy")):
        if sil:
            who, s = max(sil, key=lambda ws: ws[1][key])
            g[item] = {"value": s[key], "where": f"{who} f{s['frames'][0]}-{s['frames'][1]}"}
        else:
            g[item] = {"value": None, "error": "no silences measured"}
    ren = list(render_reports.items())
    if ren:
        put("lips.render_lag_frames", worst(ren, "lag_frames", lambda v, b: abs(v) > abs(b)),
            lambda v: round(abs(v), 2))
        inc = [f"{who} {k}" for who, rep in ren for k in rep.get("inconclusive", [])]
        g["lips.render_conclusive"] = {"value": int(not inc), "where": ", ".join(inc) or "all lines"}
    else:
        g["lips.render_lag_frames"] = {"value": None, "error": "no render check (film-ue lips render)"}
    if cues is None:
        g["lips.cues_fresh"] = {"value": 0, "where": "cues.json", "error": "no cues.json"}
    else:
        fresh = bool(cues.get("measured")) and not stale(cues, stems) and not any(
            c.get("words_lost") for c in cues["lines"].values())
        g["lips.cues_fresh"] = {"value": int(fresh), "where": "cues.json"}
    return {"gate": g}


# --- CLI ----------------------------------------------------------------------------------------------------------

def _kv(items: list) -> dict:
    out = {}
    for s in items or []:
        k, _, v = s.partition("=")
        out[k] = v
    return out


def register(sub) -> None:
    p = sub.add_parser("lips", help="lip-sync offline: measured cues, curve check, render check (film-ue lips -h)")
    s = p.add_subparsers(dest="lipsync_cmd", required=True)
    c = s.add_parser("cues", help="cues.json measured from the stems at their mix positions")
    c.add_argument("--lines", type=Path, required=True, help="a cues.json naming the lines (who, text, file_frame)")
    c.add_argument("--stem", action="append", required=True, help="who=path: the speaker's stem, frame 0 = sample 0")
    c.add_argument("--words", default="auto", choices=["auto", "whisper", "estimate", "none"])
    c.add_argument("--line-dir", type=Path, help="the line WAVs the face is solved from: each is located in its stem")
    c.add_argument("--mix", type=Path, help="the audio the cut plays: each line must sit there where the stem has it")
    c.add_argument("--mix-voice", type=Path, help="the mix's own voice stem (mix.py's stem-voice.wav): lines are "
                   "located there (score ~1.0 when it is their voice)")
    c.add_argument("--mix-json", type=Path, help="mix.py's mix.json: proves the mix was built from these stems")
    c.add_argument("--takes", type=Path, help="raw takes DIR/<line>/*.wav: with --from-mix, the take the mix holds wins")
    c.add_argument("--from-mix", type=Path, metavar="STEMS_DIR",
                   help="the mix is canonical: locate each line in --mix, rebuild the voice stems there into "
                        "STEMS_DIR, then measure on them (--line-dir and --mix needed; --stem is the old stems, checked "
                        "against the mix and reported)")
    c.add_argument("--fps", type=float, default=24.0)
    c.add_argument("--out", type=Path, required=True)
    k = s.add_parser("curves", help="the curve gate on anim.read_curves output")
    k.add_argument("--curves", type=Path, required=True)
    k.add_argument("--start-frame", type=float, required=True, help="master frame the animation's t=0 plays on")
    k.add_argument("--wav", type=Path, required=True)
    k.add_argument("--wav-frame", type=float, default=0.0)
    k.add_argument("--cues", type=Path, required=True)
    k.add_argument("--who", required=True)
    k.add_argument("--fps", type=float, default=24.0)
    k.add_argument("--expected-lag-s", type=float, default=0.0)
    vp = s.add_parser("voice", help="per-line WAVs cut from a voice separated from the mix (demucs vocals)")
    vp.add_argument("--vocals", type=Path, required=True)
    vp.add_argument("--plan", type=Path, required=True, help="the planned lines (cues_v2.json: who, text, voice_frame)")
    vp.add_argument("--mix", type=Path, required=True, help="the mix the vocals were separated from")
    vp.add_argument("--model", default="htdemucs")
    vp.add_argument("--fps", type=float, default=24.0)
    vp.add_argument("--out", type=Path, required=True)
    gp = s.add_parser("gate", help="gate v2 numbers (film-qa gate) from the curve/render reports")
    gp.add_argument("--curve", action="append", default=[], help="who=lipsync.check JSON (repeat per speaker)")
    gp.add_argument("--render", action="append", default=[], help="who=film-ue lips render JSON")
    gp.add_argument("--cues", type=Path, required=True)
    gp.add_argument("--stem", action="append", default=[], help="who=the stem the mix plays")
    gp.add_argument("--out", type=Path, required=True)
    r = s.add_parser("render", help="the video gate on a rendered MP4")
    r.add_argument("--video", type=Path, required=True)
    r.add_argument("--wav", type=Path, required=True, help="the voice (a stem or the mix), frame 0 = sample 0")
    r.add_argument("--wav-frame", type=float, default=0.0)
    r.add_argument("--cues", type=Path, required=True)
    r.add_argument("--who", required=True)
    r.add_argument("--boxes", type=Path, help="lipsync.mouth_boxes output (frames -> box)")
    r.add_argument("--box", help="x0,y0,x1,y1 (0..1): one mouth box for every frame (a locked-off shot)")
    r.add_argument("--syncnet-dir", type=Path, help="a syncnet_python checkout with data/syncnet_v2.model")
    r.add_argument("--min-conf", type=float, default=3.0)


def _done(rep: dict) -> None:
    print(json.dumps(rep, indent=1, default=str))
    v = rep.get("verdict") or ("pass" if rep.get("pass") else "fail")
    raise SystemExit({"pass": 0, "fail": 1}.get(v, 2))


def dispatch(a) -> bool:
    if getattr(a, "cmd", None) != "lips":
        return False
    if a.lipsync_cmd == "cues":
        lines_doc = json.loads(a.lines.read_text())
        if a.from_mix:
            if not (a.line_dir and a.mix):
                raise SystemExit("--from-mix needs --line-dir and --mix")
            doc = cues_from_mix(lines_doc, a.line_dir, a.mix, a.from_mix, _kv(a.stem), a.fps, a.words, a.takes)
        else:
            doc = build_cues(lines_doc, _kv(a.stem), a.fps, a.words, line_dir=a.line_dir, mix=a.mix,
                             mix_voice=a.mix_voice,
                             mix_meta=json.loads(a.mix_json.read_text()) if a.mix_json else ({} if a.mix else None))
        a.out.write_text(json.dumps(doc, indent=1))
        _done({"pass": not [i for i in doc["issues"] if i["severity"] == "fail"], "out": str(a.out),
               "issues": doc["issues"], "lines": {k: [v["voice_frame"], v["end_frame"], v["words_source"]]
                                                  for k, v in doc["lines"].items()}})
    elif a.lipsync_cmd == "curves":
        cues = json.loads(a.cues.read_text())
        if not cues.get("measured"):
            raise SystemExit(f"{a.cues} is not measured: build it with film-ue lips cues")
        cur = json.loads(a.curves.read_text())
        cur = cur.get("result", cur)
        _done(curve_check(cur, a.start_frame, a.wav, cues, a.who, a.fps, a.wav_frame, a.expected_lag_s))
    elif a.lipsync_cmd == "voice":
        lines, issues, man = lines_from_voice(a.vocals, json.loads(a.plan.read_text()), a.out, a.mix, a.fps, a.model)
        _done({"pass": not [i for i in issues if i["severity"] == "fail"], "lines": lines, "issues": issues,
               "leak_db": man.get("leak_db"), "manifest": str(a.out / "voice.json")})
    elif a.lipsync_cmd == "gate":
        def load(kv):
            out = {}
            for who, p in _kv(kv).items():
                d = json.loads(Path(p).read_text())
                out[who] = d.get("result", d)
            return out
        cues = json.loads(a.cues.read_text()) if a.cues.exists() else None
        doc = gate_numbers(load(a.curve), load(a.render), cues, _kv(a.stem))
        a.out.write_text(json.dumps(doc, indent=1))
        print(json.dumps(doc, indent=1))
    elif a.lipsync_cmd == "render":
        cues = json.loads(a.cues.read_text())
        boxes = json.loads(a.boxes.read_text()) if a.boxes else None
        if boxes:
            boxes = boxes.get("result", boxes).get("frames", boxes)
        box = [float(v) for v in a.box.split(",")] if a.box else None
        _done(render_check(a.video, a.wav, cues, a.who, boxes, box, a.wav_frame, syncnet_dir=a.syncnet_dir,
                           min_conf=a.min_conf))
    return True
