
## grade (agent-05)
- **Curves (`ADBE CurvesCustom`) and Lumetri `rgbCurves` strings cannot be set from a script** (`"RGB" can not be set`; expressions refused too). `effectcraft-cli set <comp> <layer> effects/#N/rgb "0,0 .5,.7 1,1"` works. Workaround: Lumetri curve sliders (`curveMasterShadows/Midtones/Highlights`), which work and key. An identity Curves is added to GRADE_LIMIT for hand tweaks.
- Levels: `Gamma` > 1 brightens (out = in^(1/g)). "Levels (Individual Controls)" (`ADBE Pro Levels2`) = master levels first, then the channel levels (error < 0.001). Channel Output White is a clean per-channel gain.
- Hue/Saturation: Master Saturation < 0 is an exact HSL saturation scale of 1 + s/100. Master Hue + rotates toward higher hue angle.
- Lumetri: params nested by short name (`ADBE Lumetri-0002` > `tone` > `contrast`). Colour wheels: 0.5 grey is neutral. Contrast 50 clips hard around 0.5. `Sharpen` and `Faded Film` have no visible effect (Faded Film lifts blacks slightly). Highlights/Whites negative act as a highlight shoulder. Blacks/Shadows positive lift black.
- Unsharp Mask works (amount 80 radius 1.2 doubles Laplacian energy). `Noise` at small amounts is nearly invisible; `Grain Implant` works.
- Keying wheel colours with `setValuesAtTimes` works (used for the keyed act looks).
- No ffmpeg/numpy in this container: grade_spec caches pixel samples (`grade_samples.npz`) and trims (`grade_trims.json`).
