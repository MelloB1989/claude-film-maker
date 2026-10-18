# Blender notes (bugs, gotchas, measured settings)

## Task v3-core (agent-01): the amv3 3D stage, Blender 5.2.2 / Cycles

- **Image sequences before their first frame.** `ImageUser` clamps the relative frame to `[0, frames]` (not
  `[1, frames]`), so a card that has to hold its first plate frame shows file `offset + 0`, which doesn't exist (pink).
  The stage avoids `frame_start` / `frame_offset` arithmetic entirely: every sequence is a folder of symlinks
  `<out>/_seq/<kind>/<shot>/f_00000..f_00899` that point at the nearest real frame, with `frame_start 0, frame_duration
  900, frame_offset -1` (scene frame N -> file N). Holding the end frames outside the plate range is then free.
- **Plate fidelity vs the pixel filter.** A frame at s = 1 (card exactly fills the frame), diffed against the plate JPEG
  at 1920x1080, 16 spp. Share of pixels within +-2 levels: Blackman-Harris 1.5 (default) 95.5 %, BH 1.0 97.0 %,
  Box 1.0 96.7 %, Gaussian 0.6 98.4 %, Gaussian 0.45 98.9 %, **Gaussian 0.3 99.4 %** (p99 2 levels, bias +0.004, gradient
  energy 98.6 % of the plate). The plate pass uses Gaussian 0.3. The text and light passes use BH 1.5 (antialiased 3D
  edges). With Standard view, Look None and dither 0, there is no colour bias.
- **Sample count and smear metrics.** At 8 spp the motion-blur smear is speckled, and Laplacian-based sharpness
  (`motion_metrics.py`) scores those frames as sharp (smear median 0, 56 % "hard cuts"). The same frames at 32 spp give
  smear median 5, 0 % hard cuts. Judge smears at >= 32 spp.
- **Layered actions (5.x).** `action.fcurves` is gone. `action.fcurve_ensure_for_datablock(id, path, index=i)` works,
  then `keyframe_points.add(n)` + `foreach_set("co", ...)`. It keys 2500 camera keys in well under a second.
  `keyframe_insert` with `preferences.edit.keyframe_new_interpolation_type = 'LINEAR'` also works (slower).
- **Camera motion blur steps.** `cam.cycles.motion_steps` exists on the camera object (set to 4). Keys every 0.25 f in
  windows keep fast rolls (up to ~60 deg/f at the cut) from being linearised inside the shutter.
- **Teleports and the shutter.** A set change at a half frame t_h is keyed at t_h - 0.02 / t_h + 0.02. The shutter
  (centred) of the frames on either side must stay <= 2 * (0.5 - 0.025) = 0.95, or one sample lands on the other set.
  `render.motion_blur_shutter` is animatable (keyed per frame).
- **Gate fit.** A linear similarity fit (d = T + a p + b perp p) reads a big per-frame roll as a zoom-out (a = cos th - 1).
  Use the exact form: scale |1 + a + ib|, angle atan2(b, 1 + a).
- `World.use_nodes` prints a deprecation warning in 5.2 (to be removed in 6.0). It's harmless.
- The VM's python venv has no matplotlib. `motion_metrics.py` writes `summary.json` and `metrics.csv` and then fails on
  the plot.

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
