"""Render a Blender shot of the film (headless).

  /Applications/Blender.app/Contents/MacOS/Blender -b -P blender/render.py -- --shot <name> --mode look|preview|final
      [--frames a-b[,c,...]] [--res WxH] [--samples N] [--engine cycles|eevee] [--save-blend]
  /Applications/Blender.app/Contents/MacOS/Blender -b -P blender/render.py -- --shot <name> --scan [--expect-res WxH]

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
blank-frame guard below does not ask them to be lit (their values must still be finite). It takes what "look" takes, "a-b,c", or a list or range of film frames
(range(0, 18)), or a function of the film frame (lambda f: f < 18). A shot without it has no black frames: each must
come out lit. Declare only what is meant to be black. A dark frame is not blank: the ink world alone reads about 0.006
linear.

The blank-frame guard (lib/blank.py). With two renders on one GPU, Cycles on Metal has written runs of all-black frames,
with no error and a clean exit code, so every frame is checked once its EXR is written. It is bad when any RGB value is
not finite (a NaN or an inf: the engine's bloom would spread it into a block of the film), when it is blank (the
brightest RGB value is at most 1e-4 linear; at most 1/255 in a proxy, when a plate has no EXR), or when one of its
Cycles tiles (2048 px) is black while the rest is lit. A bad frame is rendered again, up to twice, each attempt logged
(after 15 s, then 30 s: a spell of contention takes time to pass). One that is still bad stops the render with exit
code 3 and an error naming the shot, the film frame, what is wrong and the plate's path; the frames after it are not
rendered. A black_ok frame is only checked for values that are not finite.
  --scan                          checks a shot's existing plates against its window, rendering nothing: every plate
                                  there and no plate beyond it, the EXRs all one size, each plate judged as above (the
                                  EXR, else the proxy). Exit 3 on any missing, extra, blank, bad or unreadable plate or
                                  mixed sizes, else 0. --mode and the render options are not used.
  --expect-res WxH                with --scan: every EXR plate must be this size (a final's).
  GITLOOM_FORCE_BLANK=F[:N],...   test hook (Cycles): film frame F renders black on its first N attempts (default 1),
                                  to prove the retry. Unset, it does nothing.

A frame-change handler that raises fails its frame (lib/handlers.py). Blender prints a handler's exception and carries
on, so a shot posed by a handler would render (and track) a stale pose with exit code 0. Once the shot is built, every
function in frame_change_pre and frame_change_post is wrapped to record its exception; a frame whose frame_set or
render (its motion-blur steps) saw one stops the render with exit code 1, naming the handler and the frame, and the
frames after it are not rendered. The tracking pass fails the same way. The pure half of this file is lib/cli.py.

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

from lib import blank, cli, export, handlers, scan, setup, timing  # noqa: E402


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


def load_shot(name: str):
    path = HERE / "shots" / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(f"no shot {path}")
    spec = importlib.util.spec_from_file_location(f"shots.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str]) -> int:
    """Render (or --scan) a shot. Returns the exit code (lib/cli.py): 0; 1 when a frame-change handler failed;
    cli.EXIT_BAD for a frame that stayed blank or bad, or a scan that found a problem. Any other error raises (exit 1
    below)."""
    a = cli.parse_args(argv)
    mod = load_shot(a.shot)
    shot = mod.SHOT
    f0, f1 = cli.shot_frames(shot)
    black_ok = blank.black_ok(shot)  # a bad spec fails here, before anything is rendered
    if a.scan:
        res = scan.scan_plates(a.shot, f0, f1, black_ok, expect_res=a.expect_res)
        for line in scan.report(res):
            print(line, flush=True)
        return cli.EXIT_OK if res.clean else cli.EXIT_BAD

    cfg = cli.MODES[a.mode]
    res = cli.parse_res(a.res) if a.res else cfg["res"]
    samples = a.samples or cfg["samples"]
    engine = "BLENDER_EEVEE" if a.engine == "eevee" else "CYCLES"
    frames = cli.frames_to_render(a, shot, f0, f1)
    exempt = [f for f in frames if black_ok(f)]
    if exempt:
        print(f"[{a.shot}] {len(exempt)} of {len(frames)} frames are declared black_ok: the blank-frame guard does "
              "not ask them to be lit", flush=True)
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
    guarded = handlers.GUARD.install(frame_change_pre=bpy.app.handlers.frame_change_pre,
                                     frame_change_post=bpy.app.handlers.frame_change_post)
    if guarded:
        print(f"[{a.shot}] {guarded} frame-change handler{'s' if guarded > 1 else ''} guarded: an exception in one "
              "fails its frame (exit 1)", flush=True)

    if shot.get("track"):
        p = export.track(shot["track"], scene.camera, f0, f1, shot=a.shot)
        print(f"[{a.shot}] track {', '.join(shot['track'])} -> {p}")
    if a.save_blend:
        blend = export.REPO / "out" / "blender" / f"{a.shot}.blend"
        blend.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(blend), copy=True)
        print(f"[{a.shot}] saved {blend}")

    def render_one(f: int) -> list[str]:
        written = export.render_frame(scene, f, a.shot, f0, look=a.mode == "look", black_ok=black_ok(f))
        return [str(p.relative_to(export.REPO)) for p in written]

    return cli.render_frames(frames, render_one, shot=a.shot)


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
