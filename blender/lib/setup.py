"""A clean render scene for a shot: Cycles on the Metal GPU, 30 fps, AgX, centred motion blur, denoising.

The EXR plates are written in the scene's linear working space, which is pinned to Linear Rec.709 (the engine's
linear sRGB). The view transform (AgX by default) only shapes what Blender shows and the look stills: the engine
applies its own look to the plates.
"""
from __future__ import annotations

import bpy

LOGICAL = (1920, 1080)


def use_metal_gpu() -> list[str]:
    """Point Cycles at the Metal GPU (and not the CPU beside it). Returns the devices in use; empty means no GPU."""
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = "METAL"
    except TypeError:
        return []
    prefs.get_devices()
    used = []
    for d in prefs.devices:
        d.use = d.type == "METAL"
        if d.use:
            used.append(d.name)
    return used


def clear_scene() -> None:
    """Remove the startup file's objects (the default cube, light and camera) and the data they leave behind."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.lights, bpy.data.cameras, bpy.data.materials, bpy.data.curves):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)


def new_scene(res=(960, 540), fps: int = 30, engine: str = "CYCLES", samples: int = 32, denoise: bool = True,
              motion_blur: float = 0.5, view: str = "AgX", transparent: bool = False, require_gpu: bool = False):
    """Reset the current scene for a shot and return it.

    res: render size in px (16:9: tracks map it onto the film's 1920x1080). engine: 'CYCLES' or 'BLENDER_EEVEE'.
    motion_blur: the shutter in frames, centred on the frame (0 turns it off); the engine's own motion blur is centred
    too. transparent: a transparent film (the world still lights the scene). require_gpu: raise cli.NoGpuError rather
    than fall back to the CPU when no Metal GPU is found (render.py sets it for a final, unless --allow-cpu).
    """
    scene = bpy.context.scene
    clear_scene()
    ws = getattr(getattr(bpy.data, "colorspace", None), "working_space", "Linear Rec.709")
    if ws != "Linear Rec.709":  # the EXRs are written in it, and the engine composites them as linear sRGB
        raise RuntimeError(f"the blend file's working colour space is {ws}, not Linear Rec.709")

    r = scene.render
    r.engine = engine
    r.resolution_x, r.resolution_y = res
    r.resolution_percentage = 100
    r.pixel_aspect_x = r.pixel_aspect_y = 1.0
    r.fps, r.fps_base = fps, 1.0
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
        from .cli import cycles_device

        c = scene.cycles
        gpus = use_metal_gpu()
        c.device = cycles_device(gpus, require_gpu=require_gpu)
        if not gpus:
            print("setup: no Metal GPU found, rendering on the CPU")
        c.samples = samples
        c.use_adaptive_sampling = True
        c.adaptive_threshold = 0.01
        c.use_denoising = denoise
        if denoise:
            c.denoiser = "OPENIMAGEDENOISE"
            c.denoising_input_passes = "RGB_ALBEDO_NORMAL"
            c.denoising_prefilter = "ACCURATE"
            c.denoising_use_gpu = True
        c.seed = 0
        c.use_animated_seed = True  # deterministic per frame, not the same grain on every frame
        c.sample_clamp_indirect = 10.0
        scene.cycles_curves.shape = "THICK"  # hair fibres as round 3D curves
    else:
        scene.eevee.taa_render_samples = samples

    from . import lights

    lights.world_color(None)  # black until the shot lights it (lights.studio), not the startup file's grey
    return scene
