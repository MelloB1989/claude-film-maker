"""The karma reel's 45 s cut (PLAN.md §7 item 4): mix_45.wav, the stems re-cut on R6's picture edit list and mixed
by mix.py's chain (the same levels, the same duck, -14 LUFS / -1 dBTP), 48 kHz stereo 24-bit, 1080 x 2000 samples.

    cd tools && python ../films/host-studio/reel/mix45.py                 # the voice from audio/vo/
    cd tools && python ../films/host-studio/reel/mix45.py --vo-dir DIR    # R4's stems

The picture keeps master frames 120-180 (S02), 240-360 (S03, S04), 420-480 (S06), 540-600 (S08), 720-840 (S11, S12)
and 900-1560 (S13 bar 2 to the end): every cut is on a bar line (a bar is 60 frames at 96 bpm). The beds, the
effects and the voice follow the picture. The score follows it too except under S08, which plays bar 12 (master
660-720) instead of bar 10: the riser and the breath (f705-719) then lead into the drop on the cut to S11, as in
the long cut. Every splice is an equal-power crossfade that ends on the bar line, so the incoming downbeat is whole
(the incoming source's pre-roll fades in under the outgoing segment's last milliseconds).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mix as M  # noqa: E402
from mix import SPF, SR, load, loudness, master, sidechain_gain, true_peak, write_wav  # noqa: E402

# (master start, master end) frames, in the cut's order, and the score's source where it differs from the picture's
PICTURE = [(120, 180), (240, 360), (420, 480), (540, 600), (720, 840), (900, 1560)]
SCORE = [(120, 180), (240, 360), (420, 480), (660, 720), (720, 840), (900, 1560)]
FRAMES = sum(b - a for a, b in PICTURE)  # 1080
N = FRAMES * SPF  # 2 160 000
XFADE_MS = {"music": 10.0, "voice": 10.0, "fx": 10.0, "beds": 40.0}
HEAD_MS = 20.0  # a fade-in on the first sample: the cut starts inside the morning's bed and piano


def recut(x: np.ndarray, segs: list[tuple[int, int]], xfade_ms: float) -> np.ndarray:
    """Concatenate master segments of x with equal-power crossfades ending on each splice."""
    L = int(SR * xfade_ms / 1000)
    t = (np.arange(L) + 0.5) / L
    fin, fout = np.sin(t * np.pi / 2)[:, None], np.cos(t * np.pi / 2)[:, None]
    out = np.zeros((N, 2))
    at = 0
    for i, (a, b) in enumerate(segs):
        s0, s1 = a * SPF, b * SPF
        out[at:at + s1 - s0] = x[s0:s1]
        if i:  # the outgoing segment's last L samples fade out under the incoming segment's pre-roll
            pre = x[s0 - L:s0] if s0 >= L else np.zeros((L, 2))
            out[at - L:at] = out[at - L:at] * fout + pre * fin
        at += s1 - s0
    assert at == N
    h = int(SR * HEAD_MS / 1000)
    out[:h] *= np.sin((np.arange(h) + 0.5) / h * np.pi / 2)[:, None]
    return out


def to_cut(master_frame: int) -> int | None:
    """A master frame's frame in the cut, or None if the picture drops it."""
    at = 0
    for a, b in PICTURE:
        if a <= master_frame < b:
            return at + master_frame - a
        at += b - a
    return None


def mix45(vo_dir: Path | None) -> dict:
    music, g_music = M._to(load(M.AUDIO / "score" / "score.wav"), M.MUSIC_LUFS)  # leveled on the whole score
    music = recut(music, SCORE, XFADE_MS["music"])
    beds = recut(load(M.AUDIO / "sfx" / "beds.wav") * 10 ** (M.BEDS_DB / 20), PICTURE, XFADE_MS["beds"])
    fx = recut(load(M.AUDIO / "sfx" / "fx.wav") * 10 ** (M.FX_DB / 20), PICTURE, XFADE_MS["fx"])
    v, src = M.voice(vo_dir, {})
    if v is None:
        raise SystemExit("no voice stems: pass --vo-dir")
    v, g_voice = M._to(v, M.VOICE_LUFS)  # leveled on the whole voice, then cut: the lines are all after f900
    v = recut(v, PICTURE, XFADE_MS["voice"])
    key = v.mean(axis=1)
    duck = sidechain_gain(key, N, SR, **M.MUSIC_DUCK)
    music = music * duck[:, None]
    beds = beds * sidechain_gain(key, N, SR, **M.BEDS_DUCK)[:, None]
    stems = {"music": music, "voice": v, "beds": beds, "fx": fx}
    out, gain = master(sum(stems.values()))
    d = M.AUDIO / "mix"
    write_wav(d / "mix_45.wav", out.astype(np.float32))
    lines = {k: (to_cut(f0), to_cut(f1), who) for k, (f0, f1, who) in M.LINES.items()}
    rep = {
        "lufs": round(loudness(out, SR), 2), "true_peak_dbtp": round(max(true_peak(out[:, 0]), true_peak(out[:, 1])), 2),
        "seconds": round(len(out) / SR, 4), "samples": len(out), "master_gain_db": round(gain, 2),
        "voice": src, "score_gain_db": round(g_music, 2), "voice_gain_db": round(g_voice, 2),
        "picture_master_frames": PICTURE, "score_master_frames": SCORE,
        "lines_cut_frames": {k: [f0, f1, who] for k, (f0, f1, who) in lines.items()},
        "duck": {k: {"median_db": round(float(np.median(20 * np.log10(duck[f0 * SPF:(f1 + 1) * SPF] + 1e-12))), 1)}
                 for k, (f0, f1, _) in lines.items()},
        "segments_lufs": {f"{a}-{b}": round(loudness(out[i * SPF:(i + b - a) * SPF], SR), 1)
                          for (a, b), i in zip(PICTURE, np.cumsum([0] + [b - a for a, b in PICTURE])[:-1])},
    }
    (d / "mix_45.json").write_text(json.dumps(rep, indent=1, default=int))
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vo-dir", type=Path, default=M.AUDIO / "vo", help="R4's stems (vo_him.wav, vo_her.wav)")
    a = ap.parse_args(argv)
    print(json.dumps(mix45(a.vo_dir), indent=1, default=int))


if __name__ == "__main__":
    main()
