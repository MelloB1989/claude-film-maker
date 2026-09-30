"""Render a Blender shot of the film (headless).

  /Applications/Blender.app/Contents/MacOS/Blender -b -P blender/render.py -- --shot <name> --mode look|preview|final
      [--frames a-b[,c,...]] [--res WxH] [--samples N] [--engine cycles|eevee] [--save-blend]
  /Applications/Blender.app/Contents/MacOS/Blender -b -P blender/render.py -- --shot <name> --scan

The shot is blender/shots/<name>.py. It defines
  SHOT = {"scene": "<scene id>", "frames": "scene" | [f0, f1], "track": [object names], "look": "<frames>",
          "black_ok": <frames>}
  build(ctx)
"frames" is the shot's span in film frames, [f0, f1): "scene" takes the frames the engine shows the scene on
(lib/timing.py scene_frames: from the first frame at or after its start in data/vo.json to the first at or after its
end). Blender's frame numbers are film frames (frame_start = f0), so keyframes set with ctx.frame(t) land on the
engine's frames.
build(ctx) makes the camera (as scene.camera), the lights and the animation; ctx has scene, shot, mode, f0, f1, res,
timing (lib.timing.Timing), frame(t) and time(f).

"black_ok" (optional) names the film frames that are legitimately black, say a fade from black with nothing lit; the
blank-frame guard below skips them. It takes what "look" takes, "a-b,c", or a list or range of film frames
(range(0, 18)), or a function of the film frame (lambda f: f < 18). A shot without it has no black frames: each must
come out lit. Declare only what is meant to be black. A dark frame is not blank: the ink world alone reads about 0.006
linear.

The blank-frame guard (lib/blank.py). With two renders on one GPU, Cycles on Metal has written runs of all-black frames,
with no error and a clean exit code, so every frame is checked once its EXR is written. Blank: the brightest RGB value
is at most 1e-4 (linear; at most 1/255 in a proxy, when a plate has no EXR). A frame with NaNs is not blank, and its
NaNs are logged. A blank frame is rendered again, up to twice, each attempt logged (after 15 s, then 30 s: a spell of
contention takes time to pass). One that is still blank stops the render with exit code 3 and an error naming the shot,
the film frame and the plate's path; the frames after it are not rendered.
  --scan                          checks a shot's existing plates the same way (the EXR, else the proxy) and lists the
                                  blank ones, rendering nothing: exit 3 if any are blank or unreadable, else 0.
                                  --mode and the render options are not used.
  GITLOOM_FORCE_BLANK=F[:N],...   test hook (Cycles): film frame F renders black on its first N attempts (default 1),
                                  to prove the retry. Unset, it does nothing.

  mode     resolution         samples  frames                              writes
  look     960x540            32       --frames, else SHOT["look"], else all  plates + look stills (AgX)
  preview  960x540            16       all (or --frames)                     plates
  final    2560x1440          128      all (or --frames)                     plates

Every rendered frame writes its plate: out/plates/<shot>/####.exr (linear half float) and
app/public/plates/<shot>/proxy/####.png (960x540 sRGB), #### = film frame - f0 (lib/export.py); look mode also writes
out/look/<shot>/<film frame>.png through the view transform. A new render of a frame replaces its plate. SHOT["track"]
names objects whose screen positions go to data/track/<shot>.json for the whole shot, in every mode (lib/export.py).
--frames are film frames, inclusive ("40-45,52"). --res overrides the size (16:9: tracks map it onto 1920x1080);
--samples the sample count; --engine eevee renders with EEVEE (preview); --save-blend keeps out/blender/<shot>.blend.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy  # noqa: E402

from lib import blank, export, scan, setup, timing  # noqa: E402

MODES = {
    "look": {"res": (960, 540), "samples": 32},
    "preview": {"res": (960, 540), "samples": 16},
    "final": {"res": (2560, 1440), "samples": 128},
}
EXIT_BLANK = 3  # a blank frame stopped the render, or --scan found blank or unreadable plates


@dataclass
class Ctx:
    """What a shot's build() gets."""
    scene: object
    shot: str
    mode: str
    f0: int
    f1: int
    res: tuple
    timing: timing.Timing

    def frame(self, t: float) -> int:
        """The film frame showing song time t."""
        return timing.frame(t)

    def time(self, f: float) -> float:
        """The song time of film frame f."""
        return f / timing.FPS


def parse_args(argv: list[str]):
    ap = argparse.ArgumentParser(prog="blender -b -P blender/render.py --", description=__doc__.split("\n\n")[0])
    ap.add_argument("--shot", required=True, help="blender/shots/<shot>.py")
    ap.add_argument("--mode", choices=list(MODES), help="required, except with --scan")
    ap.add_argument("--frames", help="film frames to render: a-b (inclusive), comma-separated")
    ap.add_argument("--res", help="WxH, 16:9")
    ap.add_argument("--samples", type=int)
    ap.add_argument("--engine", choices=["cycles", "eevee"], default="cycles")
    ap.add_argument("--save-blend", action="store_true", help="save the built scene to out/blender/<shot>.blend")
    ap.add_argument("--scan", action="store_true",
                    help="list the blank frames of the shot's existing plates; renders nothing (exit 3 if any)")
    a = ap.parse_args(argv)
    if not a.scan and not a.mode:
        ap.error("--mode is required (unless --scan)")
    return a


def parse_res(s: str) -> tuple[int, int]:
    w, h = (int(v) for v in s.lower().split("x"))
    if w * 9 != h * 16:
        raise ValueError(f"--res {s} is not 16:9: tracks map the frame onto 1920x1080")
    return w, h


def load_shot(name: str):
    path = HERE / "shots" / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(f"no shot {path}")
    spec = importlib.util.spec_from_file_location(f"shots.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def shot_frames(shot: dict) -> tuple[int, int]:
    fr = shot.get("frames", "scene")
    if fr == "scene":
        return timing.scene_frames(shot["scene"])
    f0, f1 = (int(v) for v in fr)
    if f1 <= f0:
        raise ValueError(f"SHOT frames {fr}: f1 must be after f0")
    return f0, f1


def frames_to_render(a, shot: dict, f0: int, f1: int) -> list[int]:
    spec = a.frames or (shot.get("look") if a.mode == "look" else None)
    if spec is None:
        return list(range(f0, f1))
    frames = timing.parse_frames(spec) if isinstance(spec, str) else sorted(set(int(f) for f in spec))
    bad = [f for f in frames if not f0 <= f < f1]
    if bad:
        raise ValueError(f"frames {bad} are outside the shot's film frames [{f0}, {f1})")
    return frames


def main(argv: list[str]) -> int:
    """Render (or --scan) a shot. Returns the exit code: 0, or EXIT_BLANK for a blank frame."""
    a = parse_args(argv)
    mod = load_shot(a.shot)
    shot = mod.SHOT
    f0, f1 = shot_frames(shot)
    black_ok = blank.black_ok(shot)  # a bad spec fails here, before anything is rendered
    if a.scan:
        res = scan.scan_plates(a.shot, f0, black_ok)
        for line in scan.report(res):
            print(line, flush=True)
        return 0 if res.clean else EXIT_BLANK

    cfg = MODES[a.mode]
    res = parse_res(a.res) if a.res else cfg["res"]
    samples = a.samples or cfg["samples"]
    engine = "BLENDER_EEVEE" if a.engine == "eevee" else "CYCLES"
    frames = frames_to_render(a, shot, f0, f1)
    exempt = [f for f in frames if black_ok(f)]
    if exempt:
        print(f"[{a.shot}] {len(exempt)} of {len(frames)} frames are declared black_ok: the blank-frame guard "
              "skips them", flush=True)
    forced = blank.parse_force_blank(os.environ.get(blank.FORCE_ENV))
    if forced:
        outside = sorted(set(forced) - set(frames))
        if outside:  # a hook that silently renders nothing would pass for a guard that works
            raise ValueError(f"{blank.FORCE_ENV} names film frames {outside} that this run does not render")
        print(f"[{a.shot}] TEST HOOK {blank.FORCE_ENV}={os.environ[blank.FORCE_ENV]!r}: these frames render black on "
              f"purpose (film frame: attempts) {forced}", flush=True)

    scene = setup.new_scene(res, samples=samples, engine=engine)
    scene.frame_start, scene.frame_end = f0, f1 - 1
    scene["shot"] = a.shot
    ctx = Ctx(scene, a.shot, a.mode, f0, f1, res, timing.film())
    t0 = time.time()
    mod.build(ctx)
    if scene.camera is None:
        raise RuntimeError(f"{a.shot}.build() set no scene.camera")
    print(f"[{a.shot}] built in {time.time() - t0:.1f}s: film frames [{f0}, {f1}), {a.mode} {res[0]}x{res[1]}, "
          f"{engine} {samples} samples, device {scene.cycles.device if engine == 'CYCLES' else 'EEVEE'}")

    if shot.get("track"):
        p = export.track(shot["track"], scene.camera, f0, f1, shot=a.shot)
        print(f"[{a.shot}] track {', '.join(shot['track'])} -> {p}")
    if a.save_blend:
        blend = export.REPO / "out" / "blender" / f"{a.shot}.blend"
        blend.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(blend), copy=True)
        print(f"[{a.shot}] saved {blend}")

    took = []
    for i, f in enumerate(frames):
        t1 = time.time()
        try:
            written = export.render_frame(scene, f, a.shot, f0, look=a.mode == "look", black_ok=black_ok(f))
        except blank.BlankFrameError as e:
            print(f"ERROR: {e}", file=sys.stderr, flush=True)
            print(f"[{a.shot}] the render stopped at film frame {f} ({i} of {len(frames)} frames written). "
                  f"To finish it: --frames {blank.frames_spec(frames[i:])}", file=sys.stderr, flush=True)
            return EXIT_BLANK
        took.append(time.time() - t1)
        print(f"[{a.shot}] film frame {f} ({i + 1}/{len(frames)}) {took[-1]:.1f}s -> "
              + ", ".join(str(p.relative_to(export.REPO)) for p in written), flush=True)
    if took:
        print(f"[{a.shot}] {len(took)} frames in {sum(took):.1f}s: first {took[0]:.1f}s, "
              f"then {sum(took[1:]) / max(1, len(took) - 1):.1f}s a frame")
    return 0


if __name__ == "__main__":
    try:
        code = main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        sys.exit(1)
    if code:
        sys.exit(code)
