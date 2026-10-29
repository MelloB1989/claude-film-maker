"""Render a Blender shot of a film (headless).

  blender -b -P blender/render.py -- [--film <id>] --shot <name> --mode look|preview|final
      [--frames a-b[,c,...]] [--res WxH] [--samples N] [--engine cycles|eevee] [--save-blend] [--allow-cpu]
  blender -b -P blender/render.py -- [--film <id>] --shot <name> --scan [--expect-res WxH]

`blender` is Blender 4.2 or later on the PATH, or wherever $BLENDER points ("$BLENDER" -b -P ...; on macOS it lives at
/Applications/Blender.app/Contents/MacOS/Blender). Run it from anywhere: paths are the repo's, found from this file.

The film is --film, else $FILM, else showcase (docs/CONVENTIONS.md); its films/<id>/film.json gives the logical frame
(`format`), the `fps` and the `theme` (lib/film.py). The shot is films/<id>/blender/shots/<name>.py (or --shot
path/to/shot.py: any file, named by its stem). It defines
  SHOT = {"scene": "<scene id>", "frames": "scene" | [f0, f1], "track": [object names], "look": "<frames>",
          "black_ok": <frames>}
  build(ctx)
and nothing else is read from it; an unknown SHOT key is an error (lib/cli.py check_shot). "frames" is the shot's span
in film frames, [f0, f1): "scene" (the default) takes the frames the engine shows the scene on (lib/timing.py
scene_frames: from the first frame at or after its start in films/<id>/data/timeline.json, else data/vo.json, to the
first at or after its end); explicit frames need no scene. Blender's frame numbers are film frames (frame_start = f0),
so keyframes set with ctx.frame(t) land on the engine's frames.
build(ctx) makes the camera (as scene.camera), the lights and the animation; ctx (Ctx below) has scene, film, shot,
mode, f0, f1, res, size (the logical frame), fps, theme, timing, spec (films/<id>/data/look/<shot>.json, or None),
look (the shot's scene in the film's look schedule, films/<id>/data/look.json: lib/look_schedule.py), look_at(f) (its
State at film frame f: the arc, light, satsuei, rain and mist the shot builds with), frame(t) and time(f). The film's theme is in use before build() runs (lib/theme.py), so materials take palette roles:
materials.satin("fg"), lights.studio(world="bg").

"black_ok" (optional) names the film frames that are legitimately black, say a fade from black with nothing lit; the
blank-frame guard below does not ask them to be lit (their values must still be finite). It takes what "look" takes,
"a-b,c", or a list or range of film frames (range(0, 18)), or a function of the film frame (lambda f: f < 18). A shot
without it has no black frames: each must come out lit. Declare only what is meant to be black. A dark frame is not
blank: a dark world alone reads about 0.006 linear.

The blank-frame guard (lib/blank.py). With two renders on one GPU, Cycles has written runs of all-black frames, with no
error and a clean exit code, so every frame is checked once its EXR is written. It is bad when any RGB value is not
finite (a NaN or an inf: the engine's bloom would spread it into a block of the film), when it is blank (the brightest
RGB value is at most 1e-4 linear; at most 1/255 in a proxy, when a plate has no EXR), or when one of its Cycles tiles
(2048 px) is black while the rest is lit. A bad frame is rendered again, up to twice, each attempt logged (after 15 s,
then 30 s: a spell of contention takes time to pass). One that is still bad stops the render with exit code 3 and an
error naming the shot, the film frame, what is wrong and the plate's path; the frames after it are not rendered. A
black_ok frame is only checked for values that are not finite.
  --scan                          checks a shot's existing plates against its window, rendering nothing: every plate
                                  there and no plate beyond it, the EXRs all one size, each plate judged as above (the
                                  EXR, else the proxy). Exit 3 on any missing, extra, blank, bad or unreadable plate or
                                  mixed sizes, else 0. --mode and the render options are not used.
  --expect-res WxH                with --scan: every EXR plate must be this size (a final's).
  FILM_FORCE_BLANK=F[:N],...      test hook (Cycles): film frame F renders black on its first N attempts (default 1),
                                  to prove the retry. Unset, it does nothing.
  FILM_GPU=OPTIX|CUDA|HIP|ONEAPI|METAL[,...]|none
                                  the GPU backends to try, in order (default: all of them, in that order; the first with
                                  a device renders). "none" renders on the CPU.

A frame-change handler that raises fails its frame (lib/handlers.py). Blender prints a handler's exception and carries
on, so a shot posed by a handler would render (and track) a stale pose with exit code 0. Once the shot is built, every
function in frame_change_pre and frame_change_post is wrapped to record its exception; a frame whose frame_set or
render (its motion-blur steps) saw one stops the render with exit code 1, naming the handler and the frame, and the
frames after it are not rendered. The tracking pass fails the same way. The pure half of this file is lib/cli.py.

  mode     resolution (a 1920x1080 film)   samples  frames                                writes
  look     half the logical (960x540)      32       --frames, else SHOT["look"], else all  plates + look stills (AgX)
  preview  half the logical (960x540)      16       all (or --frames)                     plates
  final    4/3 the logical (2560x1440)     128      all (or --frames)                     plates

Every rendered frame writes its plate: out/<film>/plates/<shot>/####.exr (linear half float) and
out/<film>/plates/<shot>/proxy/####.png (8-bit sRGB at half the logical size), #### = film frame - f0 (lib/export.py);
look mode also writes out/<film>/look/<shot>/<film frame>.png through the view transform. A new render of a frame
replaces its plate. SHOT["track"] names objects whose screen positions go to films/<film>/data/track/<shot>.json for
the whole shot, in every mode, in the film's logical px (lib/export.py). --frames are film frames, inclusive
("40-45,52"). --res overrides the size (in the film's aspect: tracks map it onto the logical frame); --samples the
sample count; --engine eevee renders with EEVEE (preview); --save-blend keeps out/<film>/blender/<shot>.blend. A final
on Cycles stops (exit 1) when no GPU is found, rather than run many times slower on the CPU with other noise;
--allow-cpu lets it. An empty --frames is an error, never "every frame".
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

from lib import blank, cli, export, handlers, look_schedule, scan, setup, theme, timing  # noqa: E402
from lib import film as films  # noqa: E402


@dataclass
class Ctx:
    """What a shot's build() gets."""
    scene: object
    film: films.Film
    shot: str
    mode: str
    f0: int
    f1: int
    res: tuple  # the render size, px
    timing: timing.Timing
    spec: dict | None = None  # films/<id>/data/look/<shot>.json: the world the shot shares with its engine scene
    look: look_schedule.ShotLook | None = None  # its scene's entry in the film's look schedule (data/look.json)

    @property
    def size(self) -> tuple[int, int]:
        """The film's logical frame (width, height) px: what tracks and the engine's px are in."""
        return self.film.size

    @property
    def fps(self) -> float:
        return self.film.fps

    @property
    def theme(self) -> theme.Theme:
        return self.film.theme

    def frame(self, t: float) -> int:
        """The film frame showing film time t."""
        return self.timing.frame(t)

    def time(self, f: float) -> float:
        """The film time of film frame f."""
        return self.timing.time(f)

    def look_at(self, f: float) -> look_schedule.State:
        """The look schedule's state at film frame f: its keys are in s from the scene's start, as the engine's are (from
        the shot's first frame when the timeline has no window for it)."""
        if self.look.start is not None:
            return self.look.at_film(self.time(f))
        return self.look.at(self.time(f) - self.time(self.f0))


def load_shot(path: Path, name: str):
    """Import a shot file as module shots.<name>."""
    spec = importlib.util.spec_from_file_location(f"shots.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def prepare(a, repo: Path = films.REPO) -> tuple:
    """The film, the shot's name, module, SHOT and window [f0, f1) for parsed arguments `a` (--film, --shot), the film
    read from `repo`; the film's theme is put in use. A bad film, theme, shot or window fails here, before anything is
    built."""
    film = films.load(a.film, repo)
    theme.use(film.theme)
    name, path = cli.shot_source(film, a.shot)
    mod = load_shot(path, name)
    shot = cli.check_shot(mod, str(path))
    f0, f1 = cli.shot_frames(shot, film.timing())
    return film, name, mod, shot, f0, f1


def main(argv: list[str]) -> int:
    """Render (or --scan) a shot. Returns the exit code (lib/cli.py): 0; 1 when a frame-change handler failed;
    cli.EXIT_BAD for a frame that stayed blank or bad, or a scan that found a problem. Any other error raises (exit 1
    below)."""
    a = cli.parse_args(argv)
    film, name, mod, shot, f0, f1 = prepare(a)
    black_ok = blank.black_ok(shot)  # a bad spec fails here, before anything is rendered
    print(f"[{name}] film {film.id}: {film.width}x{film.height} logical, {film.fps} fps, theme {film.theme.name}",
          flush=True)
    if a.scan:
        expect = cli.check_res(a.expect_res, film.size, "--expect-res") if a.expect_res else None
        res = scan.scan_plates(film, name, f0, f1, black_ok, expect_res=expect)
        for line in scan.report(res):
            print(line, flush=True)
        return cli.EXIT_OK if res.clean else cli.EXIT_BAD

    cfg = cli.MODES[a.mode]
    res = cli.check_res(a.res, film.size) if a.res else cli.mode_res(a.mode, film.size)
    samples = a.samples or cfg["samples"]
    engine = "BLENDER_EEVEE" if a.engine == "eevee" else "CYCLES"
    frames = cli.frames_to_render(a, shot, f0, f1)
    exempt = [f for f in frames if black_ok(f)]
    if exempt:
        print(f"[{name}] {len(exempt)} of {len(frames)} frames are declared black_ok: the blank-frame guard does "
              "not ask them to be lit", flush=True)
    forced = blank.parse_force_blank(os.environ.get(blank.FORCE_ENV))
    if forced:
        outside = sorted(set(forced) - set(frames))
        if outside:  # a hook that silently renders nothing would pass for a guard that works
            raise ValueError(f"{blank.FORCE_ENV} names film frames {outside} that this run does not render")
        print(f"[{name}] TEST HOOK {blank.FORCE_ENV}={os.environ[blank.FORCE_ENV]!r}: these frames render black on "
              f"purpose (film frame: attempts) {forced}", flush=True)

    scene = setup.new_scene(res, fps=film.fps, samples=samples, engine=engine, require_gpu=cli.requires_gpu(a))
    scene.frame_start, scene.frame_end = f0, f1 - 1
    scene["shot"] = name
    scene["film"] = film.id
    look = look_schedule.load(film).shot(shot.get("scene") or name)
    ctx = Ctx(scene, film, name, a.mode, f0, f1, res, film.timing(), film.spec(name), look)
    t0 = time.time()
    mod.build(ctx)
    if scene.camera is None:
        raise RuntimeError(f"{name}.build() set no scene.camera")
    print(f"[{name}] built in {time.time() - t0:.1f}s: film frames [{f0}, {f1}), {a.mode} {res[0]}x{res[1]}, "
          f"{engine} {samples} samples, device {scene.cycles.device if engine == 'CYCLES' else 'EEVEE'}")
    guarded = handlers.GUARD.install(frame_change_pre=bpy.app.handlers.frame_change_pre,
                                     frame_change_post=bpy.app.handlers.frame_change_post)
    if guarded:
        print(f"[{name}] {guarded} frame-change handler{'s' if guarded > 1 else ''} guarded: an exception in one "
              "fails its frame (exit 1)", flush=True)

    if shot.get("track"):
        p = export.track(film, shot["track"], scene.camera, f0, f1, shot=name)
        print(f"[{name}] track {', '.join(shot['track'])} -> {p}")
    if a.save_blend:
        blend = film.blend_path(name)
        blend.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(blend), copy=True)
        print(f"[{name}] saved {blend}")

    def render_one(f: int) -> list[str]:
        written = export.render_frame(scene, film, f, name, f0, look=a.mode == "look", black_ok=black_ok(f))
        return [str(p.relative_to(film.repo)) for p in written]

    return cli.render_frames(frames, render_one, shot=name)


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
