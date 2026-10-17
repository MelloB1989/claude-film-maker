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
