"""A film's settings: films/<id>/film.json (docs/CONVENTIONS.md), with the Python tools' own `pipeline` section.

`load()` reads the current film's film.json and merges its `pipeline` over PIPELINE_DEFAULTS (dicts merge key by
key; lists and values replace; `deliver.outputs` replaces whole). An unknown section or key is an error, so a typo
never falls back to a default silently. A value a tool cannot do without (the voice id) stays None here and the
tool that needs it stops with `Film.require`. Paths in film.json are relative to the film folder.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .paths import FilmPaths

FORMATS: dict[str, tuple[int, int]] = {"landscape": (1920, 1080), "vertical": (1080, 1920), "square": (1080, 1080),
                                       "portrait": (1080, 1350), "cinema": (1920, 804)}

# the mix's sidechains, keyed by the voice (mix.sidechain_gain): the music ducks 6-9 dB under a spoken voice, held
# through breaths; the effects duck lightly and stay up front
MUSIC_DUCK = {"thresh_db": -26.0, "ratio": 4.0, "attack_ms": 20.0, "release_ms": 350.0, "knee_db": 9.0,
              "range_db": 9.0, "hold_ms": 250.0}
SFX_DUCK = {"thresh_db": -24.0, "ratio": 2.0, "attack_ms": 20.0, "release_ms": 350.0, "knee_db": 9.0,
            "range_db": 4.0, "hold_ms": 0.0}

PIPELINE_DEFAULTS: dict = {
    "voice": {
        "provider": "elevenlabs",
        "name": "voice",                   # how listening pages and reports name the voice
        "voice_id": None,                  # required by film-vo
        "model": "eleven_multilingual_v2",
        "output_format": "pcm_48000",
        "speed": 1.0,
        "settings": {},                    # more voice_settings sent with each request (stability, style, ...)
        "seed": None,
        "key_file": "~/11labs",            # $ELEVENLABS_API_KEY wins over the file
        "pace": {"factor": 1.0, "min": 0.85, "max": 1.0, "target_wps": None},
        "chain": {},                       # overrides of vochain.CHAIN, stage by stage
    },
    "music": {
        "provider": "elevenlabs",
        "model": "music_v2_5",
        "bpm": None,                       # else film.json audio.bpm, else 120
        "seed_base": 1,
        "variants": 3,
        "label": "score",                  # variant files are audio/music/<label>-seed<N>.wav
        "styles": ["instrumental"],        # global positive styles (the tempo is added: "<bpm> BPM")
        "avoid": ["vocals"],               # global negative styles
        "sections": [],                    # [{name, scene | at, styles, avoid, adherence, gain_db, cutoff_hz, glide}]
        "fade_out": 2.0,                   # the mix's automation fades the score out over its last seconds
        "chosen": None,                    # the score to use when data/music_plan.json names none
        "temp": {"style": "pulse", "seed": 1, "phrase": 8},  # film-temptrack defaults
    },
    "mix": {
        "lufs": -14.0,
        "true_peak": -1.0,
        "limit_dbfs": -2.0,
        "music_gain_db": -4.0,
        "sfx_gain_db": 0.0,
        "music_duck": MUSIC_DUCK,
        "sfx_duck": SFX_DUCK,
        "duck_target_db": [6.0, 9.0],      # the music's median duck under the voice that film-mix accepts
    },
    "sfx": {"palette": "data/sfx_palette.json", "backup": None},
    "sync": {"duration": None},            # [min, max] seconds the film must run, or None for no check
    "deliver": {
        "segments": 4,
        "scale": 1,
        "samples": "auto",
        "pad": None,                       # colour around a picture fitted into another aspect: default the theme's bg
        "outputs": {"rough": {"codec": "copy"}, "master": {"crf": 16}},
        "hits": [],                        # [{sound, frame?}]: cues whose hit must land on its frame in each output
    },
    "fonts": [],                           # [{src, axes, out}]: static instances cut by film-fonts
}
_REPLACE = {("deliver", "outputs")}
_FREE = {("voice", "settings"), ("voice", "chain"), ("music", "sections"), ("deliver", "outputs"), ("deliver", "hits"),
         ("fonts",)}


def _merge(base: dict, over: dict, where: tuple[str, ...], src: Path) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        here = (*where, k)
        if k not in base and where not in _FREE:
            known = ", ".join(base) or "none"
            raise SystemExit(f"{src}: unknown setting pipeline.{'.'.join(here)} (known here: {known})")
        if isinstance(v, dict) and isinstance(base.get(k), dict) and here not in _REPLACE and here not in _FREE:
            out[k] = _merge(base[k], v, here, src)
        else:
            out[k] = copy.deepcopy(v)
    return out


def size_of(fmt, src: Path | str = "film.json") -> tuple[int, int]:
    """A film.json `format` as (width, height): a preset name or {"width": W, "height": H}."""
    if isinstance(fmt, str) and fmt in FORMATS:
        return FORMATS[fmt]
    if isinstance(fmt, dict) and isinstance(fmt.get("width"), int) and isinstance(fmt.get("height"), int):
        return fmt["width"], fmt["height"]
    raise SystemExit(f"{src}: format must be one of {', '.join(FORMATS)} or {{\"width\": W, \"height\": H}}, "
                     f"not {fmt!r}")


@dataclass
class Film:
    """A film's film.json, read: its paths, the raw document and the merged pipeline settings."""
    paths: FilmPaths
    raw: dict
    pipeline: dict

    @property
    def id(self) -> str:
        return self.paths.id

    @property
    def title(self) -> str:
        return self.raw.get("title") or self.id

    @property
    def fps(self) -> int:
        return int(self.raw.get("fps", 30))

    @property
    def size(self) -> tuple[int, int]:
        return size_of(self.raw.get("format", "landscape"), self.paths.config)

    @property
    def audio(self) -> dict:
        return self.raw.get("audio") or {}

    @property
    def bpm(self) -> float | None:
        b = self.pipeline["music"]["bpm"] or self.audio.get("bpm")
        return float(b) if b else None

    @property
    def beats_per_bar(self) -> int:
        return int(self.audio.get("beatsPerBar", 4))

    @property
    def mix_path(self) -> Path:
        """Where the player and render.ts read the film's audio (film.json audio.mix)."""
        return self.paths.path(self.audio.get("mix", "audio/mix/mix.wav"))

    @property
    def analysis_path(self) -> Path:
        """Where the engine reads the beat grid and features (film.json audio.analysis)."""
        return self.paths.path(self.audio.get("analysis", "data/audio.json"))

    def __getattr__(self, name: str):
        # voice, music, mix, sfx, sync, deliver, fonts: the merged pipeline sections
        if name in PIPELINE_DEFAULTS:
            return self.pipeline[name]
        raise AttributeError(name)

    def require(self, section: str, key: str):
        """pipeline.<section>.<key>, or a SystemExit naming the setting and the file it belongs in."""
        v = self.pipeline[section].get(key)
        if v in (None, "", []):
            raise SystemExit(f"set pipeline.{section}.{key} in {self.paths.config}")
        return v


def parse(raw: dict, fp: FilmPaths) -> Film:
    if not isinstance(raw, dict):
        raise SystemExit(f"{fp.config}: expected a JSON object")
    if raw.get("id", fp.id) != fp.id:
        raise SystemExit(f"{fp.config}: id {raw['id']!r} must equal the folder name {fp.id!r}")
    pipe = raw.get("pipeline") or {}
    if not isinstance(pipe, dict):
        raise SystemExit(f"{fp.config}: pipeline must be an object")
    film = Film(fp, raw, _merge(PIPELINE_DEFAULTS, pipe, (), fp.config))
    film.size  # noqa: B018 (validates the format)
    return film


def load(fp: FilmPaths | None = None) -> Film:
    """The film.json of `fp` (default: the current film)."""
    fp = fp or paths.current()
    if not fp.config.is_file():
        raise SystemExit(f"{fp.config} is missing (film-init {fp.id} writes one)")
    try:
        raw = json.loads(fp.config.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit(f"{fp.config}: not valid JSON ({e})") from None
    return parse(raw, fp)
