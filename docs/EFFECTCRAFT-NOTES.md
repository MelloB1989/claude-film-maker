
## v2-core (agent-01): shots, MAIN, render
- `layer.property("ADBE Time Remapping").setValuesAtTimes(ts, vs)` works with one key per frame and interpolates linearly
  between keys; the two default keys are replaced. Remove keys past your last one, and set `layer.outPoint = comp.duration`.
  `layer.frameBlendingType = FrameBlendingType.NO_FRAME_BLEND` is accepted.
- `Property.keyInterpolationType(...)` is "not a callable function" (0.10.0): don't use it, write per-frame keys instead.
- Motion blur does NOT sample neighbouring layers across a hard cut: a layer with `inPoint = 15/30` over one with
  `outPoint = 15/30` renders pure colours on frames 14 and 15 with comp shutter 270/-135. No ghost frame, so cuts need no handle tricks.
- `ADBE Tile` (Motion Tile) with `Mirror Edges` = 1: `Output Width/Height` are percent of the layer and can be keyed. It is
  by far the slowest thing in the edit (a 500 % output turns a 0.6 s/frame draft frame into 6-10 s). Size it per frame to
  what the transform needs (moves.tile_need) and key it back to 100 elsewhere.
- `effectcraft-cli render --format png --start S --end E --out dir/f`: writes `dir/f_NNNNN.png` (NNNNN = comp frame).
  Frames are chosen by `ceil(t * fps)` for both ends: `--start (A-0.25)/fps --end (B-0.75)/fps` renders exactly A..B-1.
- Thread knob: the binary reads `RAYON_NUM_THREADS` (and `RAYON_RS_NUM_CPUS`); no CLI flag. Run N processes with
  `RAYON_NUM_THREADS=16/N` each on disjoint frame ranges.
- The render queue's VM does not sync `out/`: keep the `.ecproj` under another folder of the worktree (we use `build/`).
  A leftover output dir on the VM from an earlier job with the same name is reused: use a fresh name per experiment.
- Layer.inPoint/outPoint can be negative / beyond comp: fine (`startTime` negative for a precomp with handles).
# EffectCraft notes (v2 agents append a section per task)

## titles (agent-02, TITLES library)
Found while building `tools/filmtools/amv2/ec/titles.jsx` on EffectCraft 0.10.0.

- **Scripts cannot write files** (`File.open("w")` throws "scripts can't write files unless Preferences..."). Print with
  `writeLn` and redirect stdout, or `app.project.save(new File(p))` (that one works, including relative paths).
- **Text animator match names differ from AE.** `ap.addProperty("ADBE Text Tracking Amount")` actually adds the pair
  `trackingType` ("Tracking Type", 1 = Before & After) and `tracking` ("Tracking Amount"); animate `ap.property("tracking")`.
  The animator property list (match names): opacity, scale, fillColor, blur, skew, skewAxis, position, rotation, lineSpacing,
  strokeColor, strokeWidth, fillOpacity, trackingType, tracking, anchor, characterAlignment, characterRange, characterOffset,
  fillHue. Selector props: `ADBE Text Percent Start/End/Offset`, and `advanced` (units, basedOn, mode, amount, shape...).
  Text animators move the glyphs inside the layer, so a layer mask stays put: that is how the namecard mask-reveal works.
  `sourceRectAtTime` does not include animator tracking, only the document tracking.
- **Layer styles are not reachable as properties until added**, and can only be added through the engine command:
  `layer.selected = true; app.run("layer.style.add", {style: "dropShadow"})` (params must be an object, not a JSON string).
  After that `layer.property("ADBE Layer Styles").property("dropShadow")` exposes blendMode/color/opacity/angle/distance/size.
  **Bug:** `gradientOverlay.colors` (type Gradient) cannot be set from script ("value must be a number", for every shape I tried),
  so the white-to-hue text fill is a Gradient Ramp solid cut by an ALPHA track matte of the text instead.
- **`app.run(id, params)`** is the script door to every engine command (`effectcraft-cli commands` lists them).
- **Track mattes:** `layer.setTrackMatte(otherLayer, TrackMatteType.LUMA_INVERTED)` works with the matte layer anywhere in the
  stack (above or below), and a disabled matte layer is fine. `TrackMatteType.*` = ALPHA 5013, ALPHA_INVERTED 5014, LUMA 5015, LUMA_INVERTED 5016.
- **Display names:** `ADBE Motion Blur` is "Directional Blur" (Direction, Blur Length); `ADBE Glo2` params Glow Threshold/Radius/Intensity,
  Glow Colors (1 = original, 3 = A & B colours here), Color A/B; `ADBE Linear Wipe` completion 0 = nothing wiped.
- Shape layers: `ADBE Vector Filter - Repeater` (Copies, Transform > Position) works and two in one group give a dot grid
  (the caption box halftone). `ADBE Vector Filter - Roughen/Trim/Offset/Zigzag/PB/RC` exist; `ADBE Vector Filter - Wiggler` does not.
- Fonts: EffectCraft finds installed fonts by PostScript name (`BebasNeue-Regular`, `Anton-Regular`, `Montserrat-Light`,
  `ChineseRocksRg-Regular`, `Bangers-Regular`). They are not installed in the agent containers by default: copy
  `handover/amv_handover/fonts/*` and `films/timeless/fonts/*` to `~/.local/share/fonts` and run `fc-cache -f`.
- `setTemporalEaseAtKey` accepts 1 or N KeyframeEase entries for an N-D property; `setInterpolationTypeAtKey(k, HOLD)` works.
## fx (EffectCraft FX library: `tools/filmtools/amv2/ec/fx.jsx`)
Probed with 3-line scripts and by looking at the rendered frame (EffectCraft 0.10.0). Bugs and workarounds:

- **VR Chromatic Aberrations is spherical.** It treats the frame as an equirect image: the top and bottom rows are warped into
  coloured arches (frame layout 2 moves the pole to the middle instead). Workaround, used by `FX.chromaStack`: on the same
  adjustment layer, Transform to 95 %, then the effect, then Transform to 105.26 %. The empty border takes the warp, the result
  is a clean radial RGB split with no softening you can see. Set `Falloff Distance` 0, red `+a`, blue `-a`.
- **Masks run before effects (as in AE).** A subtract mask on a layer carrying Fractal Noise + Polar Coordinates does not open a
  hole in the rays, it is warped by the polar map. Use a luma track matte (a solid with a radial Gradient Ramp + Levels), see
  `FX.speedLines`. The matte layer must be directly above the layer; `setTrackMatte` hides it.
- **Polar Coordinates `Type of Conversion`**: 2 is Rect to Polar (vertical noise lines -> rays from the centre); 1 is Polar to
  Rect (U-shaped arcs). Fractal Noise: set `Transform > Uniform Scaling` 0, then `Scale Width` 5 / `Scale Height` 3200 for sparse
  vertical streaks. Properties inside groups are reached with `fx.property("Transform").property("Scale Width")`.
- **Transform effect on an adjustment layer has no edge fill**: shifted content leaves a transparent (black) gap. For a shake,
  key `Scale Height` (with `Uniform Scale` on) up by `max(|dx|/960, |dy|/540) + rotation` per frame. For slice displacement use
  the Offset effect (`Shift Center To`), which wraps and leaves no gap. A masked adjustment layer limits its effect to the mask.
- **Posterize Time on an adjustment layer does nothing to the layers below** (frames 10 and 11 stayed different). On a footage
  or precomp layer it works: grid = layer time, anchored at layer time 0, rate `fps/p` repeats frames in blocks of p. For a
  1-frame hold of frame h (h shows h-1) the layer position m must be 1 mod p; `FX.stutter` picks the smallest p that works and keys
  `Frame Rate` 120 -> `fps/p` -> 120 around h. This puts one effect on a SHOT_ layer (no transform is touched).
- **Threshold** `Level` is 0-255 (sRGB). Black/white come out as 0 and 255. The plates are dark (luma median ~40-60), so a fixed
  128 gives an all-black ink frame: per-frame levels in `fx_spec.INK_LEVEL`.
- **Levels (`ADBE Easy Levels2`)** inputs are 0-1, not 0-255. `property.minValue` throws "property has no minimum" on some
  properties (dropdowns): do not read it.
- **Glow** (`ADBE Glo2`): `Glow Threshold` is in percent of luma; the plates carry large clipped skies, so anything below ~70
  floods them. With `Glow Colors` 2 the halo takes `Color A`/`Color B`. Shadow/Highlight with `Auto Amounts` 0 and `Highlight
  Amount` 35 pulls clipped fire highlights back (6 % of the M12 frame >= 250 -> 1.8 %) without changing the mean.
- Keyed properties: `setValuesAtTimes(times[], values[])` takes absolute comp seconds for layers that start at comp time 0 (the FX
  layers do); 2-D values work for Position, Scale and `Shift Center To`; mask paths can be keyed with it too (Shape values).
- `render-frame --scale 0.5` gives quick previews; `render --out seq/g%04d.png` writes the literal `g%04d_00174.png` (the frame
  number is appended, the pattern is not expanded).
- A frame in the middle of a glitch (6 effect layers) costs ~5 s here, an ordinary frame 1-3 s. First `effectcraft-cli script` run
  after a long idle takes ~20 s.
## grade (agent-05)
- **Curves (`ADBE CurvesCustom`) and Lumetri `rgbCurves` strings cannot be set from a script** (`"RGB" can not be set`; expressions refused too). `effectcraft-cli set <comp> <layer> effects/#N/rgb "0,0 .5,.7 1,1"` works. Workaround: Lumetri curve sliders (`curveMasterShadows/Midtones/Highlights`), which work and key. An identity Curves is added to GRADE_LIMIT for hand tweaks.
- Levels: `Gamma` > 1 brightens (out = in^(1/g)). "Levels (Individual Controls)" (`ADBE Pro Levels2`) = master levels first, then the channel levels (error < 0.001). Channel Output White is a clean per-channel gain.
- Hue/Saturation: Master Saturation < 0 is an exact HSL saturation scale of 1 + s/100. Master Hue + rotates toward higher hue angle.
- Lumetri: params nested by short name (`ADBE Lumetri-0002` > `tone` > `contrast`). Colour wheels: 0.5 grey is neutral. Contrast 50 clips hard around 0.5. `Sharpen` and `Faded Film` have no visible effect (Faded Film lifts blacks slightly). Highlights/Whites negative act as a highlight shoulder. Blacks/Shadows positive lift black.
- Unsharp Mask works (amount 80 radius 1.2 doubles Laplacian energy). `Noise` at small amounts is nearly invisible; `Grain Implant` works.
- Keying wheel colours with `setValuesAtTimes` works (used for the keyed act looks).
- No ffmpeg/numpy in this container: grade_spec caches pixel samples (`grade_samples.npz`) and trims (`grade_trims.json`).
## outro (agent-06): Blender 5.2 notes (no EffectCraft use)
- The outro is a self-contained Blender script (`blender/amv2/outro.py`); output is opaque RGB PNG, black at 899.
- Blender 5.2: `scene.compositing_node_group` (not use_nodes), Glare/Translate take sockets (`inputs["Type"]`), actions are layered
  (`all_fcurves` helper). Poly-spline point keys disable motion blur for that object ("Topology differs"): strands are unblurred.
- Additive flash cards lift blacks visibly under AgX: keep flash amplitude <= 0.2 linear.
- Euler order matters for cards stood up with rotation X 90 degrees: use rotation_mode ZYX to spin about the card's own normal.
## special (rift, drop portal, triptych/shatter) — agent-04, EffectCraft 0.10.0

Bugs and workarounds found while building `tools/filmtools/amv2/ec/special.jsx`:

- **`File.exists` is always `false`**, even for existing files. Probe a file by `importFile` inside try/catch instead (a missing file
  throws `I/O error ... No such file or directory`). `importOk()` in special.jsx does this.
- **Posterize Time freezes more than the picture**: with it on a layer, the layer's *masks* are evaluated at the frozen time too
  (a mask animated over the freeze never moved). Freeze with a **time-remap hold** on a second layer of the shot precomp instead.
- **Time remap**: `setValuesAtTimes` on a fresh remap leaves the default keys (2 values gave 3 keys), so remove keys by value
  afterwards. A layer's in/out cannot pass the source duration until its time remap is enabled and you set `outPoint` **before**
  `inPoint` (setting `inPoint` first clamps it to the old out point).
- **Shape layers**: path vertices are relative to the layer position, so `position = [0,0]` makes them comp pixels. The **first**
  added vector group is drawn on top (the reverse of After Effects). `moveBefore(x)` puts the layer **above** x, `moveAfter` below.
- **Text layers**: `position` is the baseline centre. For Anton the caps centre sits `0.44 * fontSize` above the position.
- **Twirl** `Twirl Radius` clamps to 100. **Polar Coordinates** `Type of Conversion = 2` is the one that turns noise into a vortex.
  Fractal Noise `Scale`/`Offset Turbulence` live under its `Transform` group. Tritone + Turbulent Displace give a good liquid look.
- **Shatter** (`ec.sim.shatter`) rendered flat grey/black with its default View/Render settings; not used. Own shards instead:
  a polygon mask per shard of a still. **Cutting 35 shards out of the live triptych comp costs ~80 s per frame** (each shard
  re-renders the whole nested comp: precomps are not cached between layers), so special_spec.py pre-renders one still of the
  triptych at the shatter frame and the shards cut that (about 5 s per frame).
- Useful and working: `ec.vr.chromaticaberrations` (per-channel Aberration (Red/Green/Blue) = the red/blue split), `ADBE Ripple`
  (shockwave), `ec.sim.ccballaction` (halftone-like dots), `ec.blur.ccradialfast` (zoom streaks), Bevel Alpha (shard rim).
- `effectcraft-cli` is not on PATH in the agent container (use the full path); it is on the VM's PATH.
# EffectCraft notes (v2 agents append a section per task)

## elements (Blender RGBA elements, agent-07)

Probed against effectcraft-cli 0.10.0 while checking how the Blender element sequences composite.

- **PNG alpha is imported as STRAIGHT alpha, always.** A 3-line probe (`importFile` a PNG, `layers.add`, `render-frame` over a
  grey solid) was compared pixel by pixel with both formulas: straight `rgb*a + bg*(1-a)` matched with a mean error of
  0.0013, premultiplied `rgb + bg*(1-a)` with 0.19. `FootageItem.mainSource.alphaMode`, `.premulColor` and `.hasAlpha` all read
  `undefined` (hasAlpha is `false` even for a PNG with alpha), so there is no scripted interpret-footage switch.
  Workaround: `blender/amv2/elements.py` writes straight-alpha PNGs by default (`--alpha straight`); `--alpha premul` exists
  for a build that can interpret premultiplied footage. A premultiplied PNG imported as-is gets its soft edges and glows
  dimmed (multiplied by alpha twice).
- Single-frame `render-frame` of a 1920x1080 comp with one 1080p PNG layer takes about 1.6 s.
- The element sequences are named by comp frame (`NNNN.png`, e.g. `0802.png`), so import them as a numbered sequence and
  start the layer at that comp frame (or set `startTime = frame / 30`), no remap is needed.

### fx follow-up
- Comic ink: no Halftone effect in 0.10, so the halftone is an ordered dither: a black solid with `ADBE Checkerboard` (Size From = 2, white squares), Gaussian blur 6, rotated 45, Linear Light at 17% sits under the Threshold adjustment layer; Tint maps ink/paper; a 5 px RGB split on top is the misregistration. (Checkerboard `Size From` 1 = corner point, and a black Color made the whole layer black.)
- FX skips automatic shake/flash/chroma/ink inside the SPECIAL windows 244-262, 468-492, 777-830 (riser and explicit looks still run).
## v2-prep (agent-08): 240 fps footage
- **yuv444p h264 decodes wrong**: a 240 fps `-pix_fmt yuv444p` file imports (fps 240, right size) but `render-frame` gives a wrong picture (mean abs diff 165/255 against the 60 fps original). Use `yuv420p`.
- 240 fps h264 imports as `frameRate 240`, duration correct; layer time remap at a 30 fps comp lands on the same picture as the 60 fps original (mean diff ~0.9/255, the re-encode).
- Random access: `-g 8 -keyint_min 8 -bf 0` (crf 12) renders a remapped 1080p frame in ~0.6-1.5 s, the same or faster than the 60 fps original (~1.8-2.7 s; shared, noisy box). All-intra (`-g 1`) was not faster and 2.6x bigger (60 MB vs 23 MB for 1.35 s of footage).
- (grade round 2) Glow with `Glow Colors` = 2 (A & B) and Color A = Color B gives a uniform tint; keyable per act. Lumetri Temperature is a strong, cheap way to separate acts. Lumetri Contrast pivots at 0.5 and pulls dark shots down hard, so grade_curves.py measures each act's real tone curve (grey ramp through GRADE.build) and grade_spec solves the per-shot trims against it.
- Layers SPECIAL adds after GRADE sit above the grade (the triptych panels): use GRADE.applyPanel(layer, i, E, ctx).

### fx review round (f540-830)
- Ink frames: only hits >= 3.0 (656), 1 f on the hit frame, ink adjustment at 50 % with a half-strength dither; weaker explicit `ink_frame` tags become a soft white pop.
- One flash per hit, none within 5 f of another flash or an ink frame; hits >= 2.0 with no shake/chroma/flash/ink get a 2 f zoom punch (104 -> 101.8 %).
- Perf: the real MAIN (draft) renders at ~1.57 s/frame in one effectcraft-cli process on the build host (900 f = 23.5 min); 3 parallel processes gave no gain (CPU-saturated). `--gpu` has no adapter (no Vulkan/GL drivers) in the container.

### fx review round 2 (f290-560)
- Speed lines: Fractal Noise complexity 5 / lower contrast (mixed ray thickness, length, brightness), 25 % fewer rays, long fade towards the centre, tinted to the act's key colour (gold / cyan / orange); no auto rays on zoom/pull exits, and tagged shots start their rays after a zoom/pull entry (radial blur already there).
- Chroma/glitch edge line: the RGB split shifts channels inward from the *shrunk* picture's edge, so a coloured 2-10 px line sat on the frame edge whatever the margin (95 vs 93 % made no difference). Post-scale now overscans by (max amp + 3 px)/540 (about 3-6 % net zoom on the hit frames).
- Zoom punch also on weak hits (>= 1.5) with no other picture event, and on hits >= 2.0 at a whip cut (416, 536).
### special, round 2 (real core)
- **Effects can't sample outside the layer**: Ripple on an adjustment layer pulls transparent edge pixels in (scalloped frame rim). Pre-scaling does nothing; zoom the picture in *after* the ripple (`ADBE Geometry2`: props `Uniform Scale`, `Scale Height`; set Anchor/Position to the centre or it scales about the corner) to crop the rim.
- **CC Radial Fast Blur `Zoom`**: 1 standard, 2 brightest (streaky/blocky on a 300 % upscaled source), 3 darkest. Use 1 on upscaled faces.
- **Shot comps in the real core carry handle frames**: comp time of frame f = f/30 - SHOT layer `startTime` (do not assume time 0 = `a`).
- **Gitignored paths (out/) are not synced to the render VM**: put probe scripts under a tracked dir (e.g. lab/).
- PNG sequences with alpha import as straight alpha by default; `AlphaMode` is not defined in this runtime.
- Memory (v2-core): one `effectcraft-cli render` process at 1920x1080 / 16 samples peaks at ~6.1 GB RSS after 96 frames
  (VmHWM polled from /proc: the VM has no /usr/bin/time) and keeps growing, so two long processes OOM on the 31 GB VM next
  to other jobs. Prefs `memory.layerCacheMb / mediaCacheMb / previewCacheMb`, `disk.diskCacheEnabled` exist (strings in the
  binary; read from `$EFFECTCRAFT_CONFIG_DIR/prefs.json`), but setting them changed nothing measurable (6215 vs 6059 MB).
  Fix that works: many short chunks (render.py `--chunk 48`), each its own process, an xargs queue of `--procs` workers,
  one retry per chunk.
- `effectcraft-cli script` / `render` project paths inside the job: the VM resolves `$AMV2_DATA` (240 fps sources, mattes,
  mix) only on the VM, so ecbuild runs there (render.py builds inside the queue job).

## fx final fix round
- Flash: >=3.0 hits get 1 f hard white (100%); every other flash is an exposure pop (+1.5 EV, 3 f decay). No semi-transparent white solids.
- Light sweep: no full-width hairline (short glint that rides the band), band/core/wash gains cut ~45%.
- Hits 2.0-3.0 (not ink/chroma) get a 106->100 punch plus a light chroma split, even when they already shake (631, 732).
- sparks_glow and eye_glow catchlight thresholds raised (94/93), intensity ~0.4, eye ring/core opacity cut (S07/S08 blob, lifted blacks).
- ecbuild default --src is src240 (missing locally): build with --src clips.
