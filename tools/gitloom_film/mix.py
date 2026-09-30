"""Mix the voice over the score. The music ducks under her through a sidechain compressor (about 6–9 dB for a spoken
voice), then two-pass EBU R128 normalisation brings it to −14 LUFS with true peak ≤ −1 dBTP, at 48 kHz / 24-bit.
Given the analysed sections, the score's arc (automate.py) is drawn into the music before it is ducked."""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

from .automate import apply, lanes
from .paths import AUDIO, DATA, ROOT
from .wav import read_wav, write_wav

TARGET_I, TARGET_TP = -14.0, -1.5  # aim under −1.0 so the true-peak estimate has margin


def _ff(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y", *args], capture_output=True, text=True,
                          check=True)


def premix(vo: Path, music: Path, out: Path, music_gain_db: float = -2.0) -> None:
    graph = ("[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[vo][key];"
             f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={music_gain_db}dB[mu];"
             "[mu][key]sidechaincompress=threshold=0.03:ratio=4:attack=20:release=350:makeup=1[duck];"
             "[duck][vo]amix=inputs=2:normalize=0:duration=longest[mix]")
    _ff(["-i", str(vo), "-i", str(music), "-filter_complex", graph, "-map", "[mix]", "-ar", "48000",
         "-c:a", "pcm_s24le", str(out)])


def measure(path: Path) -> dict:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True, check=True)
    tail = r.stderr[r.stderr.rfind("Summary:"):]
    return {"I": float(re.search(r"I:\s+(-?[\d.]+) LUFS", tail).group(1)),
            "TP": float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail).group(1))}


def loudnorm(src: Path, out: Path) -> dict:
    base = f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA=11"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-af", f"{base}:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, check=True)
    m = json.loads(r.stderr[r.stderr.rfind("{"):r.stderr.rfind("}") + 1])
    af = (f"{base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    _ff(["-i", str(src), "-af", af, "-ar", "48000", "-c:a", "pcm_s24le", str(out)])
    return measure(out)


def mix(vo: Path, music: Path, out: Path, sections: list[dict] | None = None) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        if sections:
            y, sr = read_wav(music, mono=False)
            music = Path(td) / "music-auto.wav"
            write_wav(music, apply(y, sr, *lanes(sections, sr, len(y))), sr)
        pre = Path(td) / "pre.wav"
        premix(vo, music, pre)
        return loudnorm(pre, out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mix the voiceover over the score into audio/mix/mix.wav")
    ap.add_argument("--music", help="score WAV (default: the chosen variant)")
    ap.add_argument("--no-automation", action="store_true",
                    help="mix the score as it is, without drawing its arc from the analysed sections")
    a = ap.parse_args(argv)
    music = ROOT / (a.music or json.loads((DATA / "music_plan.json").read_text())["chosen"])
    sections = None if a.no_automation else json.loads((DATA / "audio.json").read_text())["sections"]
    m = mix(AUDIO / "vo" / "vo.wav", music, AUDIO / "mix" / "mix.wav", sections=sections)
    ok = abs(m["I"] - TARGET_I) <= 0.5 and m["TP"] <= -1.0
    how = "raw" if a.no_automation else "automated"
    print(f"audio/mix/mix.wav · {how} · {m['I']:.1f} LUFS · {m['TP']:.1f} dBTP" + ("" if ok else "   ⚠ outside target"))
