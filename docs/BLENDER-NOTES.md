# Blender notes

## Task v3-outro (agent-08, 2026-10-18): blender/amv3/outro3.py

- **No Blender here.** On 2026-10-18 neither this container nor the kbuild host had `blender` or `ffmpeg` on PATH, and
  neither had PIL. Every render, strip and probe went through the render queue (`/home/nikhil/code/.renderq`, VM).
  `/work/q.sh`-style wrappers: write the job JSON, wait for `.done`, grep the `.log`.
- **Animated curve bevel factor kills that object's motion blur.** Keying `bevel_factor_start/end` (the draw-on of web
  curves) changes the evaluated mesh topology, and Cycles prints `Topology differs, disabling motion blur for object
  <name>` for those frames. The object then loses its own object motion blur too (its rotation and scale keys), but
  camera motion blur still smears it. Keep draw-ons short, or draw on with a material mask instead of the bevel factor
  when the object must blur.
- **Importing v2's outro as a library works.** `sys.path.insert(0, blender/amv2)` + `import outro as v2` gives its
  materials, portal, shafts, lights and `setup_render` without running it (`main` is guarded), and v2 stays untouched.
  Its builders key `v2.frames()` (819-899), so they line up with the v3 outro range.
- **v2's world reflection bands whiten a red coat.** The glossy-only studio bands (RGB ~3.4-4.0) turned a coated red face
  salmon-pink under AgX Punchy. outro3 scales those two Mix colours by 0.55 (`soften_world_bands`) and uses a darker base
  red (0.32, 0, 0.005).
- **Keying at half frames** (`frame=f + 0.5`) is accepted by `keyframe_insert`, and with LINEAR interpolation the centred
  0.75 shutter then samples the exact path of fast letters and the camera.
