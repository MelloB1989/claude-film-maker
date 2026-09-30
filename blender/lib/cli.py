"""render.py's bpy-free half: its arguments, the shot's film frames, the frames a run renders, and the exit codes.

render.py imports bpy at the top, so nothing in it can be tested outside Blender; everything here runs under the tools
project's pytest (blender/tests/test_cli.py). render.py keeps what needs Blender: building the scene, rendering a frame
(lib/export.py), and the scan's EXR reader.

Exit codes: 0, every frame written (or the scan found nothing wrong); 1, an error, including a frame-change handler that
raised (lib/handlers.py); 3, a frame that stayed blank or bad after its retries (lib/blank.py: blank, a black tile, or
values that are not finite), or a scan that found a problem (lib/scan.py).
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Callable, Iterable

from . import blank, handlers, timing

MODES = {
    "look": {"res": (960, 540), "samples": 32},
    "preview": {"res": (960, 540), "samples": 16},
    "final": {"res": (2560, 1440), "samples": 128},
}
EXIT_OK = 0
EXIT_ERROR = 1  # any error: render.py prints its traceback; a failed frame-change handler stops the run with it too
EXIT_BAD = 3  # a frame stayed blank or bad after its retries, or --scan found a problem with the plates


def parse_args(argv: list[str]):
    ap = argparse.ArgumentParser(prog="blender -b -P blender/render.py --",
                                 description="Render a Blender shot of the film (headless).")
    ap.add_argument("--shot", required=True, help="blender/shots/<shot>.py")
    ap.add_argument("--mode", choices=list(MODES), help="required, except with --scan")
    ap.add_argument("--frames", help="film frames to render: a-b (inclusive), comma-separated")
    ap.add_argument("--res", help="WxH, 16:9")
    ap.add_argument("--samples", type=int)
    ap.add_argument("--engine", choices=["cycles", "eevee"], default="cycles")
    ap.add_argument("--save-blend", action="store_true", help="save the built scene to out/blender/<shot>.blend")
    ap.add_argument("--allow-cpu", action="store_true",
                    help="let a final render on the CPU when no Metal GPU is found (otherwise it stops)")
    ap.add_argument("--scan", action="store_true",
                    help="check the shot's existing plates: all there, all one size, none blank or bad; renders "
                         "nothing (exit 3 on any problem)")
    ap.add_argument("--expect-res", type=parse_res, metavar="WxH",
                    help="with --scan: every EXR plate must be this size (a final's, say)")
    a = ap.parse_args(argv)
    if not a.scan and not a.mode:
        ap.error("--mode is required (unless --scan)")
    return a


def parse_res(s: str) -> tuple[int, int]:
    w, h = (int(v) for v in s.lower().split("x"))
    if w * 9 != h * 16:
        raise ValueError(f"--res {s} is not 16:9: tracks map the frame onto 1920x1080")
    return w, h


def shot_frames(shot: dict) -> tuple[int, int]:
    """SHOT["frames"] as film frames [f0, f1): "scene" (the default) is the frames the engine shows the scene on."""
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
    spec = a.frames if a.frames is not None else (shot.get("look") if a.mode == "look" else None)
    if spec is None:
        return list(range(f0, f1))
    frames = timing.parse_frames(spec) if isinstance(spec, str) else sorted(set(int(f) for f in spec))
    bad = [f for f in frames if not f0 <= f < f1]
    if bad:
        raise ValueError(f"frames {bad} are outside the shot's film frames [{f0}, {f1})")
    return frames


class NoGpuError(RuntimeError):
    """A final found no Metal GPU to render on."""


def requires_gpu(a) -> bool:
    """A Cycles final needs the Metal GPU, unless --allow-cpu."""
    return a.mode == "final" and a.engine == "cycles" and not a.allow_cpu


def cycles_device(gpus: list[str], *, require_gpu: bool) -> str:
    """Cycles' device for the Metal GPUs found (lib/setup.py use_metal_gpu): "GPU", else "CPU", unless the run requires
    the GPU. A final on the CPU runs many times slower, so the night's budget is gone, and its noise differs from the GPU
    frames around it: it raises NoGpuError instead of carrying on with exit 0."""
    if gpus:
        return "GPU"
    if require_gpu:
        raise NoGpuError("no Metal GPU found: a final on the CPU would run many times slower, with noise unlike the GPU "
                         "frames around it. Pass --allow-cpu to render it on the CPU anyway")
    return "CPU"


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
