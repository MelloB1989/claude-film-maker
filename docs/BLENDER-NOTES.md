# Blender notes (bugs and gotchas hit while building the stage)

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
