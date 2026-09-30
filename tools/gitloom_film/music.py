"""Generate score variants from the composition plan. Prefers 48 kHz PCM; if the plan tier refuses it (HTTP 403),
falls back to 128 kbps MP3 and decodes it. Every variant is written as 48 kHz stereo 24-bit WAV, next to a sidecar
recording the plan it came from. A re-run merges into data/music_plan.json: the pick and its edit survive it."""
import argparse
import hashlib
import json
import subprocess
import tempfile
import webbrowser
from pathlib import Path

import numpy as np

from .audition import music_page
from .elevenlabs import ElevenLabs, ElevenLabsError
from .music_plan import build_plan, to_chunks
from .paths import AUDIO, DATA, OUT, ROOT
from .wav import pcm16_to_float, read_wav, write_wav


def compose_with_fallback(client, plan: dict, seed: int) -> tuple[bytes, str]:
    """`plan` is the readable section plan; music_v2_5 takes a chunk plan, so that is what gets sent."""
    chunks = to_chunks(plan)
    try:
        return client.compose(chunks, output_format="pcm_48000", seed=seed).audio, "pcm_48000"
    except ElevenLabsError as e:
        if e.status != 403:
            raise
    return client.compose(chunks, output_format="mp3_44100_128", seed=seed).audio, "mp3_44100_128"


def decode(audio: bytes, fmt: str, planned_seconds: float) -> np.ndarray:
    if fmt == "pcm_48000":
        ratio = (len(audio) / 2) / (planned_seconds * 48000)
        channels = 2 if abs(ratio - 2) < abs(ratio - 1) else 1
        x = pcm16_to_float(audio, channels)
        return np.stack([x, x], axis=1) if channels == 1 else x
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / "in.mp3", Path(td) / "out.wav"
        src.write_bytes(audio)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ar", "48000", "-ac", "2", str(dst)],
                       check=True)
        x, _ = read_wav(dst, mono=False)
    return x


def sidecar(wav: Path) -> Path:
    """A variant's record of what made it: {format, plan, chunks}."""
    return wav.with_suffix(".plan.json")


def _made_from(wav: Path, chunks: dict) -> bool:
    side = sidecar(wav)
    return wav.exists() and side.exists() and json.loads(side.read_text()).get("chunks") == chunks


def variant_path(out_dir: Path, label: str, seed: int, chunks: dict) -> Path:
    """`{label}-seed{seed}.wav` unless that file holds another plan (or one nobody recorded); then a name keyed by
    the chunks, `{label}-seed{seed}-{hash8}.wav`, so a new plan never lands on an old seed's audio."""
    plain = out_dir / f"{label}-seed{seed}.wav"
    if not plain.exists() or _made_from(plain, chunks):
        return plain
    h = hashlib.sha256(json.dumps(chunks, sort_keys=True).encode()).hexdigest()[:8]
    return out_dir / f"{label}-seed{seed}-{h}.wav"


def generate_variants(client, plan: dict, out_dir: Path, seeds: list[int], label: str = "score",
                      log=print) -> list[Path]:
    """One variant per seed. A seed's file is reused only when its sidecar holds this plan's chunks; existing
    audio is never overwritten."""
    secs = sum(s["duration_ms"] for s in plan["sections"]) / 1000
    chunks = to_chunks(plan)
    paths = []
    for seed in seeds:
        wav = variant_path(out_dir, label, seed, chunks)
        if not _made_from(wav, chunks):
            if wav.exists():
                raise FileExistsError(f"{wav} exists but its sidecar does not hold this plan; not overwriting it")
            audio, fmt = compose_with_fallback(client, plan, seed)
            write_wav(wav, decode(audio, fmt, secs))
            sidecar(wav).write_text(json.dumps({"format": fmt, "plan": plan, "chunks": chunks}, indent=1))
            log(f"{wav.name}: {fmt}")
        paths.append(wav)
    return paths


def chosen_plan(mp: dict, root: Path = ROOT) -> dict | None:
    """The composition plan the chosen score was composed from: its source seed's (a splice's source, else the
    chosen file itself), read from that seed's sidecar."""
    src = (mp.get("edit") or {}).get("source") or mp.get("chosen")
    side = sidecar(root / src) if src else None
    return json.loads(side.read_text())["plan"] if side and side.exists() else None


def merge_plan(old: dict | None, plan: dict, meta: dict, variants: list[str], root: Path = ROOT) -> dict:
    """A film-music run's result merged into data/music_plan.json: the pick (`chosen`) and its `edit` stay, new
    variants join the list once, `plan`/`meta` record the latest run, and `chosen_plan` keeps the pick's own plan."""
    mp = {**(old or {}), "plan": plan, "meta": meta}
    mp["variants"] = list(dict.fromkeys([*mp.get("variants", []), *variants]))
    mp.setdefault("chosen", None)
    cp = chosen_plan(mp, root)
    if cp is not None:
        mp["chosen_plan"] = cp
    return mp


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate score variants from data/vo.json")
    ap.add_argument("--variants", type=int, default=3)
    ap.add_argument("--seed-base", type=int, default=11)
    ap.add_argument("--bpm", type=float, default=100.0)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)
    plan, meta = build_plan(json.loads((DATA / "vo.json").read_text()), a.bpm)
    client = ElevenLabs(credit_log=AUDIO / "credits.log")
    paths = generate_variants(client, plan, AUDIO / "music", [a.seed_base + i for i in range(a.variants)])
    rel = [str(p.relative_to(ROOT)) for p in paths]
    mp_path = DATA / "music_plan.json"
    old = json.loads(mp_path.read_text()) if mp_path.exists() else None
    mp_path.write_text(json.dumps(merge_plan(old, plan, meta, rel), indent=1))
    page = music_page(paths, OUT / "auditions" / "music.html", meta["sections"])
    print(page)
    if not a.no_open:
        webbrowser.open(page.as_uri())
