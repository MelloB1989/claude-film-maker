"""How many frames a shot's cloth needs before its first rendered frame, and whether a render plan gives them.

Cloth has history. At the start of a render (a fresh PIE world) or after a teleport-and-reset, Chaos starts every
particle at its skinned position and the garment then falls into its drape over ~0.5-1.5 s: a hem dropping, an open
overshirt swinging shut. A frame rendered during that fall is a "cold start" (round 3: her overshirt hung open at the
right shoulder in a chunk that started mid-shot).

MRQ gives the cloth that time in one of two ways (MoviePipelineAntiAliasingSetting, per camera cut):
- **hold**: `engine_warm_up_count` + `render_warm_up_count` frames at the shot's first frame. The world ticks at
  the output frame rate while the sequence stays on that frame, so the cloth settles into the first frame's pose.
  Right for a chunk that starts at its cut's start. It does not reproduce motion from before the cut.
- **play** (`use_camera_cut_for_warm_up`): the camera cut's frames before the chunk's start are evaluated one by
  one, nothing rendered, so a mid-shot chunk gets the motion that led into it. It needs at least `need` frames
  between the cut start and the chunk start, and the cut start itself is a cold start, so short gaps fall back to
  rendering from the cut start.

`need = ceil(settle_s x fps x margin)`: the slowest garment in the shot decides (presets.settle_s).
"""
from __future__ import annotations

import math

MARGIN = 1.5


def need_frames(settle_s: float, fps: float, margin: float = MARGIN) -> int:
    return int(math.ceil(max(0.0, settle_s) * fps * margin))


def check_chunks(chunks: list, *, need: int, warmup_engine: int, warmup_render: int) -> dict:
    """Whether each MRQ chunk of a render plan (render.plan's "chunks": {"id", "cut_start", "start", "end",
    "preroll"}) gives the cloth `need` frames before its first rendered frame.

    Returns {"ok", "need", "warmup_engine": the engine warm-up to set (at least what is set), "chunks": [{"id",
    "mode": "hold"|"play", "frames", "ok", "fix"}]}."""
    out, ok = [], True
    set_engine = warmup_engine
    hold = warmup_engine + warmup_render
    for c in chunks:
        pre = int(c.get("preroll") or 0)
        if pre > 0:
            good = pre >= need
            fix = "" if good else (f"render this cut from its start ({c['cut_start']}): only {pre} frames of play "
                                   f"pre-roll before {c['start']} (need {need})")
            out.append({"id": c.get("id"), "mode": "play", "frames": pre, "ok": good, "fix": fix})
        else:
            good = hold >= need
            if not good:
                set_engine = max(set_engine, need - warmup_render)
            fix = "" if good else (f"warmup_engine {need - warmup_render} (now {warmup_engine}): the shot holds only "
                                   f"{hold} frames before {c['start']} (need {need})")
            out.append({"id": c.get("id"), "mode": "hold", "frames": hold, "ok": good, "fix": fix})
        ok = ok and good
    return {"ok": ok, "need": need, "warmup_engine": set_engine, "chunks": out}


def live_steps(frame: int, frames: int, mode: str = "hold", start: int | None = None) -> list:
    """The sequence frames to evaluate, one tick each, to pre-roll the live level before reading `frame` (stills,
    qa.cloth, qa.clip under simulation): hold = `frame` repeated; play = from max(start, frame - frames) up to frame
    (a run-up through the real motion), then `frame`. The first step resets the cloth (teleport and reset)."""
    if mode == "hold":
        return [frame] * max(1, frames) + [frame]
    if mode != "play":
        raise ValueError(f"mode {mode!r}: hold or play")
    a = frame - frames if start is None else max(start, frame - frames)
    return list(range(a, frame)) + [frame]
