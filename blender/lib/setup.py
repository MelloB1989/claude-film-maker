"""A clean render scene for a shot: Cycles on the GPU, the film's fps, AgX, centred motion blur, denoising.

The GPU backend is found, not assumed: OptiX, CUDA, HIP, oneAPI and Metal are tried in turn (lib/cli.py GPU_BACKENDS;
$FILM_GPU pins them, or "none" for the CPU), and the first with a device renders, on its devices only. Without one, a
preview or a look frame renders on the CPU and a final stops unless --allow-cpu (lib/cli.py cycles_device).

The EXR plates are written in the scene's linear working space, which is pinned to Linear Rec.709 (the engine's
linear sRGB). The view transform (AgX by default) only shapes what Blender shows and the look stills: the engine
applies its own look to the plates.
"""
from __future__ import annotations

import math

import bpy


def _devices(prefs, backend: str) -> list:
    """The devices Cycles lists for `backend` (prefs.compute_device_type must be set to it)."""
    if hasattr(prefs, "get_devices_for_type"):
        return [d for d in prefs.get_devices_for_type(backend) if d.type == backend]
    prefs.get_devices()
    return [d for d in prefs.devices if d.type == backend]


def use_gpu(backends) -> tuple[str | None, list[str]]:
    """Point Cycles at the first of `backends` (lib/cli.py gpu_backends) this Blender has and finds a device for, using
    its devices and not the CPU beside them. Returns (backend, device names); (None, []) when none has a device."""
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in backends:
        try:
            prefs.compute_device_type = backend
        except TypeError:  # not built into this Blender, or not on this platform
            continue
        found = _devices(prefs, backend)
        if not found:
            continue
        for d in prefs.devices:
            d.use = d.type == backend
        return backend, [d.name for d in found]
    try:
        prefs.compute_device_type = "NONE"
    except TypeError:
        pass
    return None, []


def clear_scene() -> None:
    """Remove the startup file's objects (the default cube, light and camera) and the data they leave behind."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.lights, bpy.data.cameras, bpy.data.materials, bpy.data.curves):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)


def new_scene(res=(960, 540), fps: float = 30, engine: str = "CYCLES", samples: int = 32, denoise: bool = True,
              motion_blur: float = 0.5, view: str = "AgX", transparent: bool = False, require_gpu: bool = False,
              gpu_backends=None):
    """Reset the current scene for a shot and return it.

    res: render size in px (in the film's aspect: tracks map it onto the film's logical frame). fps: the film's (a
    fractional rate such as 29.97 is set as a whole rate over a base). engine: 'CYCLES' or 'BLENDER_EEVEE'.
    motion_blur: the shutter in frames, centred on the frame (0 turns it off); the engine's own motion blur is centred
    too. transparent: a transparent film (the world still lights the scene). require_gpu: raise cli.NoGpuError rather
    than fall back to the CPU when no GPU is found (render.py sets it for a final, unless --allow-cpu). gpu_backends:
    the backends to try (default lib/cli.py gpu_backends($FILM_GPU)).
    """
    import os

    from . import cli

    scene = bpy.context.scene
    clear_scene()
    ws = getattr(getattr(bpy.data, "colorspace", None), "working_space", "Linear Rec.709")
    if ws != "Linear Rec.709":  # the EXRs are written in it, and the engine composites them as linear sRGB
        raise RuntimeError(f"the blend file's working colour space is {ws}, not Linear Rec.709")

    r = scene.render
    try:
        r.engine = engine
    except TypeError:  # Blender 4.2 to 4.4 call EEVEE BLENDER_EEVEE_NEXT
        if engine != "BLENDER_EEVEE":
            raise
        r.engine = engine = "BLENDER_EEVEE_NEXT"
    r.resolution_x, r.resolution_y = res
    r.resolution_percentage = 100
    r.pixel_aspect_x = r.pixel_aspect_y = 1.0
    r.fps = math.ceil(fps)
    r.fps_base = r.fps / fps
    r.film_transparent = transparent
    r.use_motion_blur = motion_blur > 0
    if motion_blur > 0:
        r.motion_blur_shutter = motion_blur
        r.motion_blur_position = "CENTER"
    r.use_compositing = False  # nothing between the render and the files
    r.use_sequencer = False
    r.use_persistent_data = True  # keep the synced scene between frames

    scene.display_settings.display_device = "sRGB"
    vs = scene.view_settings
    vs.view_transform = view
    vs.look = "None"
    vs.exposure = 0.0
    vs.gamma = 1.0
    vs.use_curve_mapping = False

    if engine == "CYCLES":
        c = scene.cycles
        tried = cli.gpu_backends(os.environ.get(cli.GPU_ENV)) if gpu_backends is None else tuple(gpu_backends)
        backend, gpus = use_gpu(tried)
        c.device = cli.cycles_device(gpus, require_gpu=require_gpu, tried=tried)
        if gpus:
            print(f"setup: Cycles on {backend}: {', '.join(gpus)}")
        else:
            print(f"setup: no GPU found (tried {', '.join(tried) or 'none'}), rendering on the CPU")
        c.samples = samples
        c.use_adaptive_sampling = True
        c.adaptive_threshold = 0.01
        c.use_denoising = denoise
        if denoise:
            c.denoiser = "OPENIMAGEDENOISE"
            c.denoising_input_passes = "RGB_ALBEDO_NORMAL"
            c.denoising_prefilter = "ACCURATE"
            c.denoising_use_gpu = bool(gpus)
        c.seed = 0
        c.use_animated_seed = True  # deterministic per frame, not the same grain on every frame
        c.sample_clamp_indirect = 10.0
        scene.cycles_curves.shape = "THICK"  # hair fibres as round 3D curves
    else:
        scene.eevee.taa_render_samples = samples

    from . import lights

    lights.world_color(None)  # black until the shot lights it (lights.studio), not the startup file's grey
    return scene
