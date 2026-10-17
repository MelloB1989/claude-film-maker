
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
