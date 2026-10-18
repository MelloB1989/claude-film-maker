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

## Task v3-xfxB (agent-07): glass shatters, lightning, panels (Blender 5.2, Cycles CPU on the VM)
- **Camera motion blur smears "instantaneous" emitters.** A lightning bolt that lives one frame still gets the
  camera's motion blur (static objects blur when the camera moves), so a fast push turns thin filaments into wide
  ribbons. `ob.cycles.use_motion_blur = False` does NOT help (it only drops the object's own motion). Fix: key the
  bolt to ride with the camera through its frame (`_fx3d.ride_camera`: M(t) = cam(t) @ cam(t_ref)^-1 @ M_world),
  and give each frame its own bolt object visible on [k-0.5, k+0.5) so no shape changes mid-shutter.
- **Additive emitters have alpha 0 in a transparent film.** Emission + Transparent BSDF (light that never occludes)
  renders with alpha 0 and full RGB. Use the light pass as RGB add (finishing: footage alpha "Ignore"), never
  alpha-over. Plain Emission (opaque) keeps alpha 1.
- **A tinted Transparent BSDF in front of an emission card did not visibly darken it** (meant as a multiply filter).
  A Mix Shader of Transparent and a dim Emission (keyed factor) works as a darkening veil.
- **Bevelled Voronoi shards show their seams** while they are still coplanar (the bevel rounds every edge). Keep an
  intact card until the break frame and show the shards only from the break.
- `bpy -P script.py` exits 0 on a Python exception unless you pass `--python-exit-code 1`.
- Render queue: a job file name that already has a `.done` returns at once with the OLD log; use a fresh name per run.
- Thin emissive crack lines over a fast push: they get the card's radial blur too; keep them thin (0.2-0.6 mm in card
  space) and moderately bright or they read as white bands.

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
- **The render queue does not sync `out/` to the VM**, so a job cannot read frames that an earlier job copied back. Make
  strips inside the same job, or locally (here: a venv with Pillow, `python -m venv /work/venv && pip install pillow`).
- **Timings (outro3, Blender 5.2.2 Cycles CPU, VM, 12 threads):** 1080p at 48-64 spp is 52-84 s/frame (897-899 drop to
  1-26 s); 960x540 at 16 spp is 8-13 s; 480x270 at 16 spp is 2-4 s. Scene build is ~0.6 s.
- **AgX turns strong emission white.** Energy rings at strength 7-8 lost their act colours. At 1.2-2.8 (with hits
  flaring them to ~2x) they keep gold / cyan / red and still bloom.
- **Additive emission over transparency** (Add Shader of Transparent + Emission) is the clean way to fake god-rays and
  glow rings: there is no dark fringe. Mix-shader shaft cards with weak emission occlude what is behind them and read as
  dark bands (v2's shafts did this once dimmed).

## v3-text3d (agent-02): 3D titles + text_fly

1. **Text meshes: keep the caps flat.** If you shade every face of a converted text mesh smooth, the bevel's normals
   bleed into the long thin cap triangles, and the whole front face gets tilted normals. A shader that separates face,
   bevel and sides by the object-space normal (TexCoord > Normal, z) then puts the rim glow over the entire face. Fix:
   faces with |n.z| > 0.995 stay flat, and every edge between a flat cap and a smooth bevel face is marked sharp
   (`edge.smooth = False`).
2. **Letter positions.** A text curve can't report per-character positions. Build each glyph as its own curve and
   offset it by (right edge of the prefix `text[:i+1]`) - (right edge of the lone glyph). That keeps the font's advances.
3. **Big bevels break condensed fonts.** On Anton with `bevel_depth` 0.05 em, the bevel self-intersects in narrow
   counters (the N of SPIDER-MAN turned into stray vertical bars, and the word's bbox doubled in height). Stay at
   ~0.03 em; for a fatter rim, use the shader's rim band instead of more geometry.
4. **Decorative fonts don't extrude.** The installed "Spider-Man" movie font has hairline spikes and serifs that become
   needles in 3D. Use a clean condensed face (Anton + `shear` for the italic, Barlow Condensed Black Italic).
5. **Teleport sampling.** The core keys a teleport at t_h -/+ EPS (0.02). Sampling the camera at t_h -/+ 0.001
   interpolates between those two keys and returns the same blended pose on both sides. The A->B transform then comes
   out as ~identity and the copies stay in A's set (invisible in B). Always sample at exactly t_h -/+ ctx.EPS.
6. **Visibility keys before the first key.** `hide_render` fcurves extrapolate constant backwards. If the first key
   is "visible", the object shows on every earlier frame (TIMELESS letters appeared 4 f early). Start the key range a
   few frames before any entrance, with the object hidden there.
7. **Light-pass twins.** The plate view layer renders the `light` collection too. An emission twin of each letter (for
   the glow pass) therefore needs its own sub-collection (`T3D_glow`), excluded in every view layer except `light`
   (`layer_collection.exclude = True`).
8. **Metal without an environment.** The stage world is a near-black void, so Principled metal reflects black. A
   view-space "matcap" (reflect(-Incoming, Normal) -> Vector Transform world->camera -> horizon band / sky / floor ramp)
   gives chrome and glossy sides that read anywhere and shimmer as the letters turn. It costs nothing.
9. **Per-letter shader parameters.** An object custom property keyed per frame (`ob["t3d_pop"]`) is readable in the
   shader through an Attribute node of type OBJECT. One material can then serve every letter, each with its own pop.
10. **mathutils:** `Matrix.Diagonal((x, y, z, w))`, not `Matrix.Diag`.
11. **Light linking** (`light.light_linking.receiver_collection`) keeps a title's key/rim lights off the cards and off
    the other sets. Cards are emission-only anyway, but other modules' glossy objects are not.
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
## Task v3-layer (agent-06): subject-layer cards
- **Coplanar cards z-fight as see-through, not as flicker.** A matted subject card exactly on top of its own opaque plate
  card (same plane) renders the plate ~50 % transparent everywhere: a ray that hits the transparent part of the matte card
  continues and skips the coincident plate at random. Keep a layered card >= 4 mm in front (`layer.ZSEP`); the parallax
  is sub-pixel.
- **Tiled cards mirror the matte too.** `make_card(tile=3)` uses MIRROR for every texture, so a matte card or a matte
  hole on a tiled mesh shows mirrored subject copies around the card. Set the matte image node to CLIP (transparent
  outside 0..1). Use tile=3 copies for layered cards anyway: a copy must use the same mesh and depth displacement as the
  home card, or the teleport onto it shows.
- **make_card caches materials** per (shot, alpha, ...), so the home card and every copy share one. Copy the material
  (`ob.data.materials[0] = m.copy()`) before you patch nodes or key node values.
- An opaque card's material (`alpha="none"`) has no matte image node. To cut a hole, add one
  (`ctx._sequence("mattes", sid, "png")` + `cards.setup_user`).
- **motion_metrics on layered transitions:** with B sharp behind a smeared foreground subject (ref c10 style), the
  sharpness drop is local. The tool counts the window as one or two hard cuts (0 smear frames) and reads a large
  1-frame drop when the subject leaves the frame.

### v3.1 (rig of nulls, nested zooms)
- **Object motion blur costs a subframe sync per object.** With camera motion blur on, every object that has
  `cycles.use_motion_blur` set gets re-synced at the shutter's subframes, even if it never moves. Static cards
  (displaced by an animated depth sequence) dominated: full-res 1 spp plate overhead fell from 1.66 to 0.88 s/frame
  (VM CPU, 12 threads) once the cards without transform animation had object motion blur off. The camera's own blur is
  unaffected.
- **Bezier handles from the path.** Keys written with `fcurve_ensure_for_datablock` + `foreach_set("co")`, then each
  key's `handle_left/right_type = "FREE"` and the handle positions set at 1/3 of the neighbour gap along the slope
  (the slope sampled from the path at t + h). Set the types to FREE before the positions or `fc.update()` recomputes
  them.
- **Swing-twist for the rig.** A camera world rotation splits into RIG_ORBIT (swing) and RIG_ROLL (twist about the
  local -Z view axis): twist angle = 2 atan2(q.z, q.w), swing = q @ Rz(angle)^-1. Unwrap the angle against the
  previous key; flip the swing quaternion's sign to keep it on the same hemisphere (Bezier per component).
- **Animatable feather.** A region mask blurred once (3 box passes) and thresholded in the shader with
  MapRange(SMOOTHSTEP, 0.5 - w, 0.5 + w) gives a feather whose width is a keyable Value node. The 0.5 contour of
  the blurred mask stays on the hard edge for shapes much wider than the blur. A 36 x 20 px eye needs a 1 px box,
  so the blur radius follows the region's size.
