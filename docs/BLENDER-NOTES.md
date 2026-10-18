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
- **Nested eye zoom geometry (v3.1):** with B physically behind A's eye opening, the opening grows as 1/z and B as
  1/(z + D), so their ratio is fixed by D alone. A small D lets B show small inside the eye but makes B land very zoomed
  in after the crossing. A large D lands B near 1x but shows only a crop of B inside the eye. eye_tunnel keys B's zoom
  rate and derives D from it (0.6 m with the eye at 1.6 m, B ~0.4x inside the eye, ~1.05x at the crossing, 1.44x at
  the hold).
- **`make_card` shares materials between cards of a shot.** Copy the material (`ob.data.materials[0] = mat.copy()`)
  before adding a per-card alpha (region holes, apertures), or every card of that shot gets the hole.
- **A glossy surface seen edge-on reflects what is in front of the camera.** Inside the symbiote goo funnel, a softbox
  strip behind the camera only lit the lip of the opening. The 149-152 sweep is a screen-space band emitted in the goo
  shader instead, broken up by the camera-space normal.
- **Texture Coordinate "Camera" Z:** use |z| for the depth (the screen u = x / |z| / 0.514). Assuming -z put every
  point at depth 1e-4, so the band never showed.
- **Region masks** (`regions/<shot>/<kind>/f_NNNNN.png`, hard edge at plate res) load through
  `ctx._sequence("regions/<shot>", kind, "png")`, a held comp-time sequence, so frames outside the masks don't read a
  missing file. Feather them in the shader with a 9-tap disc of the feather radius.
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
- **v3.1 keep (camera flies past a static subject into a static B):** for the camera to end past A's plane while B fills
  the frame from the start, B must sit deep (16 m, scaled x10-14). Two things follow:
  - The void environment's web strands then hang between the camera and B. Leave the void out when B covers the frame.
  - Start a cover-scale search at the analytic fill scale. A search from x1 in x1.04 steps ran out at x10.5 and
    silently inflated B's exit scale.
- Aim the camera's straight line through the crossing point in A's plane, not its end pose. The camera travels ~10x
  further in depth than sideways, so an end-pose offset is reached only after A's plane, and the camera flies through
  the subject's face.

### v3-layer refinements (land <= 1.3x, C30 black frames)
- **A hold extrapolated back from w1 can leave its card inside the window.** `B.at(t - w1)` runs B's exit rates
  backwards linearly. S31 in the full film exits tilting at -45 px/f, so 6 f before w1 B's framing is off the card. A
  bigger card never fixes that, because the camera pose on it scales too. The sweep cover search ran to x110 and the
  camera ended 140 m out: 8 black frames in the nest1 render. Fix: `eased_back(B, span)` keeps pose and rate at w1 and
  clamps the look-back softly at the longest tau that still covers. The cover search is also capped (`KB_MAX` 3).
  `--only` runs did not show it: the stub neighbours give S31 a gentle exit rate. Always check a full-EDL build.
- **The core's `cull_by_set` judges a card's set by its centre** (`matrix_world.translation`, one sample). A card
  scaled up to cover a far view (centre 50-200 m back) is hidden as "another set", and the world shows through
  (magenta). Keep cards within ~45 m of the set origin, or key `hide_render` yourself.
- **Landing scale vs cover is a hard budget.** B covers the frame only at s >= ~1.05-1.15 (centre, roll, margin). With
  a landing <= 1.3x, B has ~0.15-0.2 in ln s for the whole window. A static far B approached by the camera spends far
  more (the old keep landed at 1.78-1.99x). keep now rides B's card with the camera, showing B in its own (eased) hold
  motion, so B lands sharp and C1. The cost: B moves at hold speed after the cut, not with a decelerating zoom, so the
  stage gate's per-cut drop/step stats for a keep cut compare A's plane at the lens with B and read x100+ (as for the
  eye/lens nests, which the gate exempts).
## Task v3-renderopt (agent-08, 2026-10-18): stage render speed (blender/amv3/renderopt.py)
- **Animated visibility keeps an object in the render depsgraph.** An object whose `hide_render` is keyed is pulled
  into the depsgraph on every frame, even on frames where it is hidden. Its animation, image users and modifiers are
  evaluated at every motion-blur subframe, and Cycles syncs its materials and their images. A *static*
  `hide_render = True` drops the object from the depsgraph. The fix: bake the keys into a per-frame table, remove the
  fcurves, and render in segments with a constant visible set, setting `hide_render` statically per segment
  (`bpy.ops.render.render(animation=True)` per segment; persistent data keeps the session). 'Updating Images' went
  0.07 -> 0.01 s/frame, and the result is bit-identical to the keyed render.
- **Visibility edges and object motion blur.** With keyed visibility, a subframe where the object is hidden gets the
  centre transform (Cycles fills missing motion steps with the centre). So an FX object has no blur from the side
  where it does not exist yet. Making it statically visible blurs in its pre-appearance motion: the sling ring on
  its first frame (612) smeared across the frame. Objects with `cycles.use_motion_blur` whose visibility changes
  inside f +- 0.5 keep their original keys on those frames only.
- **Camera motion_steps n = (2 << (n - 1)) + 1 scene evaluations per frame** (4 -> 17, 2 -> 5). With the camera keyed
  every half frame, 2 steps gives the same blur: low-pass (16x16) diffs <= 3.6 levels on the whip 414-419; the rest is
  sampling noise.
- **Emissive cards are lights.** Every emission material is in the light tree by default (`emission_sampling`). With
  ~100-200 emissive cards / bokeh / strands visible, 'Updating Lights' cost ~0.04 s/frame, and next-event estimation
  spent shadow rays on cards (behind glass they are blocked anyway). `material.emission_sampling = 'NONE'` on
  cards / voids makes this free; BSDF rays still see them (unbiased). The property is `material.cycles.emission_sampling`
  in 5.2 (`hasattr(material, "emission_sampling")` is False: a probe on the material silently does nothing).
- **OIDN runs on the CPU even when rendering on the GPU.** `scene.cycles.denoising_use_gpu` defaults to False in 5.2.
  On the 4090 pod each OIDN frame (ACCURATE prefilter, albedo + normal) cost ~3.5-4 s inside the 'Sample' phase
  (480-484: 4.6 s vs 0.3 s at 485 with the same flakes and no OIDN), once per pass. Set it True on GPU renders.
- **Lens shatter crossing frame (479) bisected** (VM CPU, 4 spp, no OIDN; 5.1 s): hiding the ~100 shards -> 1.75 s,
  the two camera-attached area lights -> 3.05 s (transparent shadow rays shaded through every shard), the void env
  -> 3.3 s, the nest cards -> 3.4 s. DOF, motion blur, cracks, ring, chips: within the VM's +-10 % noise.
  transparent_max_bounces 12 -> 4 and max_bounces 4 -> 1: no gain.
- **Things that did nothing:** PNG compression 0 (the 0.17 s 'Finished' phase is not zlib; files 2x larger);
  compositing / sequencer off; adaptive sampling (bit-identical output at 64 spp with threshold 0.01 / 0.005: it
  never stopped a pixel early in these scenes).
- **Depth cards:** before static cards lost object motion blur, Displace + Smooth on the 193 x 109 tile-3 grid cost
  ~0.12 s/frame per visible depth card (re-evaluated per motion time). After it, a 5x leaner grid (same vertices over
  the card) rendered pixel-identically with no measurable gain, so it was dropped.
- **Measuring on the shared VM:** wall s/frame swings 30-50 % with other jobs. Use the per-phase split instead
  (`bpy.app.handlers.render_stats` strings with timestamps; AMV3_RO=...,stats writes ro_stats.txt), and diff
  premultiplied RGB. Straight RGB under near-zero alpha is noise and shows 255-level 'differences' in text/light passes.
