"""The 3D SAU_EDITZ outro: `blender -b -P blender/amv/outro.py -- --film <dir> [--res-scale ..] [--samples ..] [--frames a-b]
[--out out/<id>/amv/outro] [--save out/<id>/amv/outro.blend]`

Renders comp frames `outro.f .. dur-1` of the film's plan as opaque 1920x1080 PNGs `<out>/<f:04d>.png` (pipeline stage
`outro`, docs/PIPELINE-AMV.md). The timeline lives in `outro_schedule.py` (bpy-free, tested), the scene in
`outro_geo.py` / `outro_look.py`. Headless; the same script does a small CPU test and the full GPU render.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "tools"))
sys.path.insert(0, str(HERE.parent))

import bpy  # noqa: E402

from amv import outro_geo, outro_look, outro_schedule as sch  # noqa: E402
from filmtools.amv import plan as planmod  # noqa: E402

FONT = "fonts/Spider-Man.otf.ttf"


def parse(argv):
    ap = argparse.ArgumentParser(prog="outro.py")
    ap.add_argument("--film", required=True, help="film folder (films/<id>)")
    ap.add_argument("--res-scale", type=float, default=1.0)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--frames", help="comp frames: a-b ranges and single frames, comma separated; default the whole outro")
    ap.add_argument("--every", type=int, default=1, help="render every Nth frame of the range")
    ap.add_argument("--out", help="output folder (default out/<id>/amv/outro next to the film's out/)")
    ap.add_argument("--save", help="save the .blend here")
    ap.add_argument("--device", default="auto", help="auto | cpu | gpu")
    ap.add_argument("--hide", default="", help="debug: comma separated object-name prefixes to leave out of the render")
    ap.add_argument("--no-comp", action="store_true", help="debug: skip the compositor (raw Cycles frame)")
    ap.add_argument("--no-render", action="store_true")
    return ap.parse_args(argv)


def frame_list(arg, f0, last, every=1):
    """Comp frames to render: `a-b` ranges and single frames, comma separated; every `every`-th of a range."""
    if not arg:
        return list(range(f0, last + 1, every))
    out = []
    for tok in arg.split(","):
        a, _, b = tok.partition("-")
        out.extend(range(max(f0, int(a)), min(last, int(b or a)) + 1, every if b else 1))
    return out


def setup_render(args, plan):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = args.samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.02
    cy.use_denoising = True
    cy.max_bounces = 6
    cy.volume_bounces = 1
    cy.volume_step_rate = 1.5
    cy.volume_max_steps = 256
    cy.sample_clamp_indirect = 8.0
    cy.sample_clamp_direct = 40.0
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 0.4
    sc.render.resolution_x, sc.render.resolution_y = planmod.W, planmod.H
    sc.render.resolution_percentage = max(1, round(args.res_scale * 100))
    sc.render.fps = plan.fps
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = planmod.SHUTTER_ANGLE / 360.0          # 301 deg
    sc.render.motion_blur_position = "CENTER"
    sc.render.film_transparent = False
    ims = sc.render.image_settings
    ims.file_format, ims.color_mode, ims.color_depth = "PNG", "RGB", "8"
    ims.compression = 15
    sc.render.dither_intensity = 0.0              # the last frame must be exactly black
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.use_compositing = True
    sc.render.compositor_device = "CPU"            # headless: no GL context for the GPU compositor
    sc.render.use_sequencer = False
    dev = args.device
    prefs = bpy.context.preferences.addons["cycles"].preferences
    gpu = False
    if dev in ("auto", "gpu"):
        for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
            try:
                prefs.compute_device_type = kind
                prefs.get_devices()
                devs = [d for d in prefs.devices if d.type == kind]
                if devs:
                    for d in prefs.devices:
                        d.use = d.type == kind
                    gpu = True
                    break
            except Exception:
                continue
    cy.device = "GPU" if gpu else "CPU"
    print("outro: cycles device", cy.device)


def main(argv):
    args = parse(argv)
    film = Path(args.film).resolve()
    plan = planmod.load(film)
    o = plan.raw["outro"]
    f0, n = o["f"], o["n"]
    last = f0 + n - 1
    assert f0 + n == plan.dur, "the outro must run to the end of the film"
    out = Path(args.out) if args.out else film.parents[1] / "out" / film.name / "amv" / "outro"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = f0, last
    setup_render(args, plan)
    mats = [outro_look.face_material(), outro_look.bevel_material(), outro_look.side_material()]
    objs, layout = outro_geo.build_letters(film / FONT, mats, sc.collection)
    outro_look.build_world()
    outro_look.build_lights(n, f0)
    outro_look.build_volume()
    outro_look.build_rings(n, f0)
    outro_look.build_sparks(layout, n, f0)
    outro_look.build_camera(n, f0)
    outro_look.animate_letters(objs, n, f0)
    outro_look.build_compositor(n, f0, planmod.W, planmod.H)
    for ob in bpy.data.objects:
        if any(h and ob.name.startswith(h) for h in args.hide.split(",")):
            ob.hide_render = True
    sc.render.use_compositing = not args.no_comp
    print(f"outro: layout width {layout['width']:.2f} BU height {layout['height']:.2f} BU")
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).resolve()), compress=True)
    if args.no_render:
        return
    out.mkdir(parents=True, exist_ok=True)
    import time
    for f in frame_list(args.frames, f0, last, args.every):
        t = time.time()
        sc.frame_set(f)
        sc.render.filepath = f"{out}/{f:04d}"
        bpy.ops.render.render(write_still=True)
        print(f"outro: frame {f} rendered in {time.time() - t:.1f}s")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
