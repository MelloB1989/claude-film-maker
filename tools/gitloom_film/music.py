"""Generate score variants from the composition plan. Prefers 48 kHz PCM; if the plan tier refuses it (HTTP 403),
falls back to 128 kbps MP3 and decodes it. Every variant is written as 48 kHz stereo 24-bit WAV, next to a sidecar
recording the plan it came from and its section timing. A re-run merges into data/music_plan.json: the pick and its
edit survive it, and the pick's own section timing (`chosen_meta`) is recomputed from its sidecar."""
import argparse
import hashlib
import json
import re
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
    """A variant's record of what made it: {format, plan, chunks, meta} (sidecars written before meta have none)."""
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
                      log=print, meta: dict | None = None) -> list[Path]:
    """One variant per seed. A seed's file is reused only when its sidecar holds this plan's chunks; existing
    audio is never overwritten. `meta` (the plan's section timing, music_plan.build_plan) goes into each new sidecar."""
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
            side = {"format": fmt, "plan": plan, "chunks": chunks, **({"meta": meta} if meta is not None else {})}
            sidecar(wav).write_text(json.dumps(side, indent=1))
            log(f"{wav.name}: {fmt}")
        paths.append(wav)
    return paths


def pick_sidecar(mp: dict, root: Path = ROOT) -> Path | None:
    """The sidecar of the seed the chosen score was composed as: a splice's source, else the chosen file itself."""
    src = (mp.get("edit") or {}).get("source") or mp.get("chosen")
    return sidecar(root / src) if src else None


def chosen_plan(mp: dict, root: Path = ROOT) -> dict | None:
    """The composition plan the chosen score was composed from, read from its seed's sidecar."""
    side = pick_sidecar(mp, root)
    return json.loads(side.read_text())["plan"] if side and side.exists() else None


_TEMPO = re.compile(r"\s*(\d+(?:\.\d+)?)\s*BPM\s*", re.IGNORECASE)


def plan_meta(plan: dict, bpm: float) -> dict:
    """The section timing a plan was composed to (music_plan.build_plan's meta): each section from where the ones
    before it end, in seconds."""
    sections, at = [], 0
    for s in plan["sections"]:
        sections.append({"name": s["section_name"], "start": round(at / 1000, 4),
                         "end": round((at + s["duration_ms"]) / 1000, 4)})
        at += s["duration_ms"]
    return {"bpm": bpm, "sections": sections}


def pick_meta(mp: dict, root: Path = ROOT) -> dict | None:
    """The chosen score's own section timing, from its seed's sidecar, never from whichever film-music run wrote
    `meta` last: the meta the sidecar records, else (a sidecar from before sidecars kept it) its plan's sections at
    their durations, at the one tempo its plan's global styles name ("100 BPM"). None when nothing is chosen, the
    sidecar is missing, or it holds no meta and its plan names no single tempo."""
    side = pick_sidecar(mp, root)
    if side is None or not side.exists():
        return None
    doc = json.loads(side.read_text())
    if "meta" in doc:
        return doc["meta"]
    tempos = [float(m.group(1)) for style in doc["plan"].get("positive_global_styles", [])
              if (m := _TEMPO.fullmatch(style))]
    return plan_meta(doc["plan"], tempos[0]) if len(tempos) == 1 else None


def merge_plan(old: dict | None, plan: dict, meta: dict, variants: list[str], root: Path = ROOT) -> dict:
    """A film-music run's result merged into data/music_plan.json: the pick (`chosen`) and its `edit` stay, new
    variants join the list once, `plan`/`meta` record the latest run, `chosen_plan` keeps the pick's own plan, and
    `chosen_meta` the pick's own section timing (pick_meta), recomputed from its sidecar on every merge: no later run
    moves the pick's sections, and a pick changed by hand gets its own (it is dropped when it cannot be known)."""
    old = old or {}
    mp = {**old, "plan": plan, "meta": meta}
    mp["variants"] = list(dict.fromkeys([*mp.get("variants", []), *variants]))
    mp.setdefault("chosen", None)
    cp = chosen_plan(mp, root)
    if cp is not None:
        mp["chosen_plan"] = cp
    cm = pick_meta(mp, root)
    if cm is not None:
        mp["chosen_meta"] = cm
    else:
        mp.pop("chosen_meta", None)
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
    paths = generate_variants(client, plan, AUDIO / "music", [a.seed_base + i for i in range(a.variants)], meta=meta)
    rel = [str(p.relative_to(ROOT)) for p in paths]
    mp_path = DATA / "music_plan.json"
    old = json.loads(mp_path.read_text()) if mp_path.exists() else None
    mp_path.write_text(json.dumps(merge_plan(old, plan, meta, rel), indent=1))
    page = music_page(paths, OUT / "auditions" / "music.html", meta["sections"])
    print(page)
    if not a.no_open:
        webbrowser.open(page.as_uri())
