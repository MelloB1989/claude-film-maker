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

## Task v3-xfxA (agent-04): signature transitions eye_tunnel, symbiote, sling_ring, web_wipe

- **No Blender in the agent container or on the build host.** The shared binary `film-making/bin/blender-5.2.2-linux-x64`
  needs libSM/libICE/libGL. Without root: `apt-get -o Dir::State::Lists=<dir> -o Dir::Cache=<dir> update`, then
  `apt-get download libsm6 libice6 libgl1 libglvnd0 libglx0 libglx-mesa0`, `dpkg-deb -x` into a folder and set
  `LD_LIBRARY_PATH`. A wrapper in shared code (`.worktrees/agent-04/blibs/blender`) works locally and through `kbuild`.
- **`Vector.to_track_quat('-Z', 'Y')` flips 180 deg of roll** when the direction passes close to the axis (a camera looking
  almost straight down -Z with a tiny lateral tilt). It made a 130 deg/f spin in one frame. For camera look-ahead use
  the minimal rotation `Vector((0, 0, -1)).rotation_difference(fwd)` and add the roll after it.
- **mathutils is float32.** Finite-difference rates (`ds`, `dc`, `dr`) taken through Matrix/Quaternion with h = 1e-3 frame
  come out as 0 or noise; use h >= 0.02.
- `importlib.util.module_from_spec` does not register the module; register it in `sys.modules` yourself if you want to
  reach module state from a debug script.
- **Image-sequence frame mapping** (shader Image Texture, source SEQUENCE): image number =
  `clamp(scene_frame - frame_start + 1, 1, frame_duration) + frame_offset` (or wrapped when `use_cyclic`). To play
  `f_NNNNN.jpg` in comp time with holds outside the plate: `frame_start = lo`, `frame_offset = lo - 1`,
  `frame_duration = hi - lo`. Several nodes may share one image with different offsets.
- **Deformation motion blur from numpy:** one shape key per frame (or half frame) with value keys 0 -> 1 -> 0 on the
  neighbours, LINEAR, gives exact linear interpolation between computed states and Cycles blurs it (constant topology).
  Used for the symbiote goo (57 k verts x 25 keys) and the sling sparks (6.4 k verts x 35 keys); build time 3-6 s.
- `Speed` profiles: monotone cubic (Fritsch-Carlson) speed keys, integrated for position, never overshoot, and are C1, so
  a camera path built from them passes the "no step change" check. Easier to tune than eases when a move has several
  beats (dive, cruise, surge, landing).
- **Emission + Standard view transform clips fast:** thick light rings at strength 9 read as flat white bands under motion
  blur. Thin geometry (bevel 3-6 mm at 1-4 m), strength 3-10, colour saturated, and let finishing add the glow.
- **Double fog trap:** mixing a colour toward the fog colour by `exp(-d / k)` AND scaling the emission strength by the
  same factor makes far objects black, not foggy. Do one or the other.
- **Card edges inside a 3D transition:** a scaled card copy that the camera approaches always shows `s(t) / s_end =
  d_end / (d_end + travel)`; if the camera keeps travelling after a portal, the copy must be large and deep (sling_ring:
  x5.6 at 7 m) or B lands zoomed in.
- `ShaderNodeMix` (RGBA): inputs 0 = factor, 6/7 = A/B colour, output 2 = colour.
