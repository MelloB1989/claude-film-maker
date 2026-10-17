# EffectCraft libraries for Timeless v2

`python -m filmtools.amv2.ecbuild` writes ONE script and runs it with `effectcraft-cli script`:

    var E = {...};  var CORE = {...};  var OUT_PROJECT = "...";   // data
    ec/fx.jsx  ec/grade.jsx  ec/special.jsx  ec/titles.jsx          // the libs that exist, concatenated
    ec/core.jsx                                                      // shots + MAIN, then calls the libs

JS is ES5-ish (the After Effects object model). Every lib defines exactly ONE global (`FX`, `GRADE`, `SPECIAL`,
`TITLES`) and keeps every helper inside it. Core globals you may use (all defined before your code runs, at call time):
`E, ctx, proj` (= app.project), `FPS, W, H`, `f2t(frame)`, `TG/POS/SCL/ROT/OPA/ANC/FXP(layer)`, `TRY(what, fn)` (catches,
records a warning), `warn(s)`, `log(s)`. A lib that wants to be standalone-testable should not rely on them (copy what it
needs inside its global).

## Call order (new layers go on top: the call order is the stacking order from the bottom)
1. core: `SHOT_<id>` layers (and `MATTE_<id>`)  2. `FX.buildUnder(main, E, ctx)`  3. `GRADE.build(main, E, ctx)`
4. `FX.buildOver(main, E, ctx)`  5. `SPECIAL.build(main, E, ctx)`  6. `TITLES.build(main, E, ctx)`.
A missing lib or function is skipped (`[core] skip ...` in the log). An exception inside a lib is caught and counted as a
warning: the build then exits 1, so fix it.

## E
The parsed `films/timeless/amv2/edl.json` (`E.shots[i] = {id, clip, a, b, src, speed, drift, focus, xin, xout, fx, note}`,
`E.titles`, `E.hits`, `E.acts`, `E.triptych`, `E.outro`, `E.watermark`, `E.voice`, `E.drop`, ...) plus `E.x.<lib>`: whatever
`filmtools/amv2/<lib>_spec.py: extend(E, ctx_py)` put there (`ctx_py = {fps, w, h, root: Path, data: Path, src, log}`).
`E.x.<lib>` exists (as `{}`) when the spec module exists.

## ctx
| | |
|---|---|
| `ctx.fps, ctx.w, ctx.h` | 30, 1920, 1080 |
| `ctx.root`, `ctx.data` | repo root, `$AMV2_DATA` (or its local fallback) as strings |
| `ctx.src` | `"clips"` (60 fps handover clips) or `"src240"` (RIFE 240 fps) |
| `ctx.elements` | the project FolderItem `03_ELEMENTS`: put imported elements (Blender sequences, fonts' images) here |
| `ctx.log(msg)` | prints `[core] msg` |
| `ctx.shot(id)` | the MAIN layer `SHOT_<id>` (e.g. `ctx.shot("S10")`), or null |
| `ctx.shotComp(id)` | the precomp `SHOT_<id>` (1920x1080) |
| `ctx.matte(id)` | the disabled MAIN layer `MATTE_<id>` (white subject on black, same remap and transform as the shot) or null |
| `ctx.handles` | `[6, 6]`: handle frames of every shot precomp before `a` and after `b` |

### The SHOT_ layers (read this before timing anything)
* Layer in/out are exactly `[a, b)`: `layer.inPoint = a/30`, `layer.outPoint = b/30`. The precomp has 6 spare frames each
  side (`ctx.handles`): precomp time 0 = MAIN frame `a - 6`, so `layer.startTime = (a - 6)/30`. A lib may extend
  `inPoint`/`outPoint` into the handles (SPECIAL does that around its portals).
* Transform keys exist for every frame in `[a-6, b+6)` (position, scale, rotation; anchor = the shot's `focus`, default the
  centre): the `drift` plus the xin/xout moves. **Libs must not re-key SHOT_ layers**; SPECIAL owns the transform of the
  shots around `rift`, `drop_portal`, `panel_slam` (core gives those drift only and a hard cut, no mirror tile). For
  shake use an adjustment layer or a parent null you create yourself.
* Motion blur is on for every SHOT layer; comp shutter 270 deg, phase -135, samples from `--samples`.
* Mirror-edge Motion Tile (`ADBE Tile`, effect named `edge tile`) is on the layer wherever the frame edge would show.
* Frame blending is off. Never interpolate across a source cut: `source_cut@F` is exact.
* `SHOT_S01` fades in from black (`open_lightsweep`): opacity keys. MAIN's background is black.
* Footage layer inside each precomp is named `footage <clip>` and has time remap keys (one per comp frame).

## GRADE and the triptych (agent-05)
SPECIAL runs after GRADE, so its triptych panels sit ABOVE the grade layers and are not graded by `GRADE.build`. For each panel
layer call `GRADE.applyPanel(layer, i, E, ctx)` (i = index in `E.triptych.panels`): per-panel trim + the Tom look + bloom +
sharpen + limiter, as effects on the layer itself. (`E.x.grade.panels["0".."2"]` holds the trims.)
