# Timeless v3 finishing (EffectCraft): FINISH

`python -m filmtools.amv3.ecfinish build --stage DIR` writes ONE script and runs it with `effectcraft-cli script`:

    var E = {edl.json + E.x.finish (finish_spec.py) + E.x.titles (v2 titles_spec)};  var OUT_PROJECT = "...";
    ec/grade3.jsx (GRADE3)  ec/lens.jsx (LENS)  ../../amv2/ec/titles.jsx (TITLES, v2, unchanged)  ec/finish.jsx (core)

Python computes every number (per-frame keys); the JSX only creates layers and sets keys, so a look is changed in
`finish_spec.py` (LOOK_PUSH, SKIN, RECIPE, LEAKS, FLASH_EV, LUMA_CAP ...) and rebuilt.

## Comp FINISH, bottom to top
| layer(s) | from | what |
|---|---|---|
| `OUTRO (v2 Blender)` | `$AMV2_DATA/blender/outro/0819-0899.png` | under the plate (plate alpha is 0 after the triptych shatter) |
| `PLATE (stage)` | `<stage>/plate/f_NNNNN.png` | the stage picture (scaled to 1920 if rendered at --res 0.5) |
| `GRADE_TRIM` | v2 grade_spec trims | Levels + Hue/Sat keyed per shot, linear A -> B across each CUTS window |
| `GRADE_LOOK` | v2 GRADE.LOOKS + LOOK_PUSH | Lumetri + Color Balance + Hue/Sat, keyed per act (6-frame blend at 252 and 480) |
| `GRADE_SKIN` | SKIN | Lumetri HSL Secondary skin key, saturation 80 inside it (faces stay faces) |
| `GRADE_BLOOM`, `GRADE_SHARPEN` | per act | Glow above a high threshold (76-80 %), Unsharp Mask |
| `LENS <Cnn> optics/bloom/leak/wash/exposure` | edl `cuts[].lens` + RECIPE | per window, see `lens.jsx` header |
| `TEXT (stage 3D titles)` | `<stage>/text/` | straight alpha, 35 % of the act split tone, soft outline glow |
| `LIGHT glow core/halo/bloom` | `<stage>/light/` | three ADD layers, Glow only (Composite Original = None) |
| `TITLE ...`, `WATERMARK` | v2 TITLES lib | subs (cues.csv word frames), name cards, caption boxes; + `name_andrew` (finish_spec.ANDREW_CARD) |
| `LETTERBOX` | shots with fx `letterbox` | v2's 2.39 bars, eased in 10 f, out 3 f |
| `FINISH_GRAIN/VIGNETTE/LIMIT` | FINISH | fine mono grain, vignette, highlight shoulder + Levels 0.012..0.975 |

## Lens FX time profile (per window, finish_spec.lens_plan)
`p(x)`: rise into the cut (cubic for flow cuts, linear for portals), 1.0 on f-1 and f, cubic fall over 5 frames;
from `<stage>/zvec.json` (per-frame camera speed) when the stage writes it. Every light key (leak, wash, bloom,
exposure, flash) is multiplied by the frame's **headroom**: 1 on a dark plate frame, falling to 0.06 at plate mean
luma >= 0.58 (measured with ffmpeg signalstats at build time), so bright frames never turn into a milky veil.
CA (edge px, VR CA amount = px / 1.65): RECIPE[type].ca x edl `ca` on the smear, then (8 + 0.6 ca) px fading over 8 f.
White flash (edl `flash` > 0): 3 frames, first-frame EV solved from the plate's 90th-percentile luma for ~30 % clipped.

## Render
`python -m filmtools.amv3.ecfinish render --stage '$AMV3_DATA/stage/<name>' --res full --name final` (one queue job:
build on the VM, keep `$AMV3_DATA/builds/final.ecproj`, 48-frame chunks, 2 workers x 8 threads), then encode
`out/timeless/amv3/Timeless_v3.mp4` (h264 CRF 16 yuv420p, `$AMV2_DATA/mix.wav` until the v3 mix exists).
Review: `python -m filmtools.amv3.finish_review pairs|strip|stats` (stats needs numpy: Blender's bundled python here).
