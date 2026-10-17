
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
