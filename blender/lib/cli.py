"""render.py's bpy-free half: its arguments, the shot's source and contract, its film frames, the frames a run renders,
the render sizes, the GPU backends, and the exit codes.

render.py imports bpy at the top, so nothing in it can be tested outside Blender; everything here runs under plain
pytest (blender/tests/test_cli.py). render.py keeps what needs Blender: building the scene, rendering a frame
(lib/export.py), and the scan's EXR reader.

Exit codes: 0, every frame written (or the scan found nothing wrong); 1, an error, including a frame-change handler that
raised (lib/handlers.py); 3, a frame that stayed blank or bad after its retries (lib/blank.py: blank, a black tile, or
values that are not finite), or a scan that found a problem (lib/scan.py).
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Callable, Iterable

from . import blank, handlers

# Each mode's render size is the film's logical frame (film.json `format`) scaled: half for look frames and previews
# (960x540 for a landscape film), 4/3 for a final (2560x1440), so every format keeps its aspect.
MODES = {
    "look": {"scale": 0.5, "samples": 32},
    "preview": {"scale": 0.5, "samples": 16},
    "final": {"scale": 4 / 3, "samples": 128},
}
EXIT_OK = 0
EXIT_ERROR = 1  # any error: render.py prints its traceback; a failed frame-change handler stops the run with it too
EXIT_BAD = 3  # a frame stayed blank or bad after its retries, or --scan found a problem with the plates

SHOT_KEYS = ("scene", "frames", "track", "look", "black_ok")  # what a SHOT dict may hold (render.py documents them)
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")


def parse_args(argv: list[str]):
    ap = argparse.ArgumentParser(prog="blender -b -P blender/render.py --",
                                 description="Render a Blender shot of a film (headless).")
    ap.add_argument("--film", help="the film: films/<id>/ (default: $FILM, else showcase)")
    ap.add_argument("--shot", required=True,
                    help="films/<film>/blender/shots/<shot>.py by name, or a path to a shot file")
    ap.add_argument("--mode", choices=list(MODES), help="required, except with --scan")
    ap.add_argument("--frames", help="film frames to render: a-b (inclusive), comma-separated")
    ap.add_argument("--res", type=parse_size, metavar="WxH", help="render size, in the film's aspect")
    ap.add_argument("--samples", type=int)
    ap.add_argument("--engine", choices=["cycles", "eevee"], default="cycles")
    ap.add_argument("--save-blend", action="store_true", help="save the built scene to out/<film>/blender/<shot>.blend")
    ap.add_argument("--allow-cpu", action="store_true",
                    help="let a final render on the CPU when no GPU is found (otherwise it stops)")
    ap.add_argument("--scan", action="store_true",
                    help="check the shot's existing plates: all there, all one size, none blank or bad; renders "
                         "nothing (exit 3 on any problem)")
    ap.add_argument("--expect-res", type=parse_size, metavar="WxH",
                    help="with --scan: every EXR plate must be this size (a final's, say)")
    a = ap.parse_args(argv)
    if not a.scan and not a.mode:
        ap.error("--mode is required (unless --scan)")
    return a


def parse_size(s: str) -> tuple[int, int]:
    """'WxH' as (W, H), both positive whole px."""
    m = re.fullmatch(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", s or "")
    if not m or int(m.group(1)) < 1 or int(m.group(2)) < 1:
        raise ValueError(f"{s!r} is not a size: WxH, in px")
    return int(m.group(1)), int(m.group(2))


def check_res(res: tuple[int, int], size: tuple[int, int], what: str = "--res") -> tuple[int, int]:
    """`res` if it has the logical frame's aspect (to within a px of rounding), else ValueError: tracks map the render
    onto the film's logical `size` px, and the engine composites the plate over its whole frame."""
    w, h = res
    W, H = size
    if abs(w * H / W - h) >= 1:
        raise ValueError(f"{what} {w}x{h} is not the film's aspect ({W}x{H}): its height at {w} wide is "
                         f"{w * H / W:g}")
    return res


def mode_res(mode: str, size: tuple[int, int]) -> tuple[int, int]:
    """A mode's default render size for a film whose logical frame is `size`: MODES' scale of it, rounded."""
    s = MODES[mode]["scale"]
    return max(1, round(size[0] * s)), max(1, round(size[1] * s))


# -------------------------------------------------------------------------------------------------------- the shot

def shot_source(film, shot: str) -> tuple[str, Path]:
    """(name, file) of --shot: a name is films/<film>/blender/shots/<name>.py (film: lib/film.py Film); a path to a .py
    file (anything with a '/' or ending in .py) is that file, named by its stem. The name names the plates and the
    track, so it must be a plain file name. Raises FileNotFoundError, naming the film's shots, when there is no such
    file."""
    if "/" in shot or "\\" in shot or shot.endswith(".py"):
        path = Path(shot).expanduser().resolve()
        name = path.stem
    else:
        name, path = shot, film.shot_path(shot)
    if not _NAME.fullmatch(name):
        raise ValueError(f"shot name {name!r}: letters, digits, '_', '-' and '.' only (it names the plates and track)")
    if not path.exists():
        have = ", ".join(film.shots()) or "none"
        raise FileNotFoundError(f"no shot {path} (film {film.id!r} has: {have}; a shot is "
                                f"films/{film.id}/blender/shots/<shot>.py)")
    return name, path


def check_shot(mod, name: str = "shot") -> dict:
    """A loaded shot module's SHOT, checked against the contract: a dict of SHOT_KEYS only, with a "scene" unless its
    "frames" are explicit, "track" a list of object names; and a build(ctx) function. Raises ValueError saying what is
    wrong (a misspelt key must not pass for a shot that tracks nothing)."""
    shot = getattr(mod, "SHOT", None)
    if not isinstance(shot, dict):
        raise ValueError(f"{name}: a shot defines SHOT = {{...}} (a dict)")
    if not callable(getattr(mod, "build", None)):
        raise ValueError(f"{name}: a shot defines build(ctx)")
    extra = sorted(set(shot) - set(SHOT_KEYS))
    if extra:
        raise ValueError(f"{name}: SHOT has unknown keys {extra} (it takes {', '.join(SHOT_KEYS)})")
    if shot.get("frames", "scene") == "scene" and not isinstance(shot.get("scene"), str):
        raise ValueError(f'{name}: SHOT needs a "scene" (an id in the film\'s timeline), or explicit '
                         '"frames": [f0, f1]')
    track = shot.get("track", [])
    if isinstance(track, str) or not all(isinstance(t, str) for t in track):
        raise ValueError(f'{name}: SHOT["track"] is a list of object names, not {track!r}')
    return shot


def shot_frames(shot: dict, timing) -> tuple[int, int]:
    """SHOT["frames"] as film frames [f0, f1): "scene" (the default) is the frames the engine shows the scene on, from
    `timing` (lib/timing.py Timing); [f0, f1] film frames name them outright."""
    fr = shot.get("frames", "scene")
    if fr == "scene":
        return timing.scene_frames(shot["scene"])
    f0, f1 = (int(v) for v in fr)
    if f1 <= f0:
        raise ValueError(f"SHOT frames {fr}: f1 must be after f0")
    return f0, f1


def frames_to_render(a, shot: dict, f0: int, f1: int) -> list[int]:
    """The film frames this run renders: --frames, else in look mode the shot's look frames, else all of [f0, f1). An
    empty --frames is an error (timing.parse_frames), not "everything": a resuming driver with nothing left to render
    must not render the whole shot again, or in look mode overwrite the plates with look frames."""
    from . import timing

    spec = a.frames if a.frames is not None else (shot.get("look") if a.mode == "look" else None)
    if spec is None:
        return list(range(f0, f1))
    frames = timing.parse_frames(spec) if isinstance(spec, str) else sorted(set(int(f) for f in spec))
    bad = [f for f in frames if not f0 <= f < f1]
    if bad:
        raise ValueError(f"frames {bad} are outside the shot's film frames [{f0}, {f1})")
    return frames


# --------------------------------------------------------------------------------------------------------- the GPU

GPU_BACKENDS = ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL")  # tried in this order: the first with a device wins
GPU_ENV = "FILM_GPU"  # pins the backends to try ("CUDA", "OPTIX,CUDA"), or "none" for the CPU


class NoGpuError(RuntimeError):
    """A final found no GPU to render on."""


def gpu_backends(value: str | None = None) -> tuple[str, ...]:
    """The Cycles GPU backends to try, in order: $FILM_GPU's (comma-separated; "none" or "cpu": none), else
    GPU_BACKENDS. A backend this Blender does not have is passed over (lib/setup.py use_gpu), so the default works on
    any platform: OptiX or CUDA on NVIDIA, HIP on AMD, oneAPI on Intel, Metal on a Mac."""
    if value is None or not value.strip():
        return GPU_BACKENDS
    names = tuple(v.strip().upper() for v in value.split(",") if v.strip())
    if names in (("NONE",), ("CPU",)):
        return ()
    bad = [n for n in names if n not in GPU_BACKENDS]
    if bad:
        raise ValueError(f"{GPU_ENV}={value!r}: unknown backend {bad} (have {', '.join(GPU_BACKENDS)}, or none)")
    return names


def requires_gpu(a) -> bool:
    """A Cycles final needs a GPU, unless --allow-cpu."""
    return a.mode == "final" and a.engine == "cycles" and not a.allow_cpu


def cycles_device(gpus: list[str], *, require_gpu: bool, tried: Iterable[str] = GPU_BACKENDS) -> str:
    """Cycles' device for the GPUs found (lib/setup.py use_gpu): "GPU", else "CPU", unless the run requires the GPU. A
    final on the CPU runs many times slower and its noise differs from GPU frames around it: it raises NoGpuError
    instead of carrying on with exit 0."""
    if gpus:
        return "GPU"
    if require_gpu:
        raise NoGpuError(f"no GPU found (tried {', '.join(tried) or 'none'}): a final on the CPU would run many times "
                         "slower, with noise unlike GPU frames around it. Pass --allow-cpu to render it on the CPU "
                         "anyway")
    return "CPU"


# ------------------------------------------------------------------------------------------------------ the frames

def _say(line: str) -> None:
    print(line, flush=True)


def _warn(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def render_frames(frames: list[int], render_one: Callable[[int], Iterable[str]], *, shot: str,
                  out: Callable[[str], None] = _say, err: Callable[[str], None] = _warn,
                  clock: Callable[[], float] = time.time) -> int:
    """Render `frames` in order, each with render_one(film frame), which returns what it wrote; returns the exit code.

    A frame that stays blank or bad (blank.BadFrameError) stops the run with EXIT_BAD, and a frame-change handler that
    raised (handlers.HandlerError) with EXIT_ERROR; either way the frames after it are not rendered, and the error says
    which --frames finish the run. Any other exception is raised on (render.py prints it and exits 1)."""
    took = []
    for i, f in enumerate(frames):
        t1 = clock()
        try:
            written = list(render_one(f))
        except (blank.BadFrameError, handlers.HandlerError) as e:
            err(f"ERROR: {e}")
            err(f"[{shot}] the render stopped at film frame {f} ({i} of {len(frames)} frames written). "
                f"To finish it: --frames {blank.frames_spec(frames[i:])}")
            return EXIT_BAD if isinstance(e, blank.BadFrameError) else EXIT_ERROR
        took.append(clock() - t1)
        out(f"[{shot}] film frame {f} ({i + 1}/{len(frames)}) {took[-1]:.1f}s -> " + ", ".join(written))
    if took:
        out(f"[{shot}] {len(took)} frames in {sum(took):.1f}s: first {took[0]:.1f}s, "
            f"then {sum(took[1:]) / max(1, len(took) - 1):.1f}s a frame")
    return EXIT_OK
