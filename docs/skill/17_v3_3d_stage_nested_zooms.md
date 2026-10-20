# 17. Timeless v3: one Blender 3D stage, nested null-camera zooms, EffectCraft finishing (2026-10-18)

The user rejected v2's transitions ("not smooth at all ... simple, something more 3d crazy ... use best of blender and
effectcraft ... it has to be perfect") and sent three reference edits (eitaX "We ready?", eitaX Spider-Man 2 "Newest
Tank", sanchezae "We Ready?"). After the first v3 look they added the rule that defines v3.1: **zooms are a camera on 3D
nulls flying between static clips, and the next clip is already visible inside a feathered eye/lens/background shape**.
Code: claude-film-maker branch `amv3`: `films/timeless/amv3/{EDIT.md, REFS.md, edl.py}`, `blender/amv3/` (stage + modules,
README = the contract), `tools/filmtools/amv3/` (plates, tracks, prep, regions, mix, finishing, motion_metrics).

## 1. What makes the references smooth (measured: REFS.md, `motion_metrics.py`)
| metric | refs a / b / c | rejected v2 | v3 target (gate) |
|---|---|---|---|
| hold picture speed, median | 20 / 23 / 15 px/f | 4.5 | >= 12 |
| near-static hold frames (< 4 px/f) | 1-2.5 % | 44.6 % | <= 5 % |
| hold zoom rate, median | 2.1-2.5 %/f | 0.39 | >= 1.5 %/f |
| worst 1-frame speed drop out of a cut, median / p90 | 1.8-2.2 / 3.0-3.8 | 3.3 / 10.1 | <= 2.3 / 4 |
| acceleration into a cut (last 4 f) | x1.36-1.62 per frame | | x1.35-1.7 |
| deceleration out of a cut (>= 8 f tail) | x1.17-1.25 per frame | 1.31 | x1.15-1.27 |
| zoom sign kept across the cut | 22-23 of ~24 | 10 of 22 | reversals <= 10 % |
| hard cuts (no smear) | 0-18 % | 32 % | <= 15 %, only on hits |
- The camera NEVER stops (holds drift 1-3.5 %/f zoom + pan + roll); v2's moves stopped dead after each cut (a square wave).
- Attack expo-in (speed ~x2/f over the last 3-4 f), 1-3 frames of total smear (< 6 % sharpness) with an act-coloured
  light leak (+40-120 % luma) and 20-60 px chromatic split, landing at the SAME speed then expo-out (x0.8/f), lens
  defocus on B for 2-4 f (legible +2, sharp +4/+5). White flash only on the 2-3 biggest hits.
- Zoom sign carries through the cut (push -> push, pull -> pull); pan/roll screen direction always carries.
- Depth from layering: subject kept as foreground while the background becomes B; 3D words in the scene the camera flies
  through.
- Tool: `python -m filmtools.amv3.motion_metrics VIDEO|FRAME_DIR --out D --gate` (per-frame similarity fit on DIS flow,
  sharpness, cuts/smears, 16 gates). Judge stage renders at >= 32 spp (noise fakes sharpness).

## 2. The nested null-camera zoom (the user's method; EDIT.md "v3.1")
Reference frames: sanchezae c 164-179, eitaX a 56-71 (`films/timeless/amv3/refs_strips/nest_*`).
- Camera rig: `RIG_DOLLY -> RIG_ORBIT -> RIG_ROLL -> RIG_SHAKE -> CAM`, eased Bezier keys on the nulls with overlapping
  timing (position vs rotation vs roll) so the motion never stops. Clips are STATIC cards in world space; only the rig
  moves ("not the clip coming to us, coz it looks sloppy").
- Push: B's card sits physically behind A's region (eye opening / mask lens / background = 1 - subject matte), sized so
  B's framing fills the region at reveal start; ~8-12 f before the camera reaches A's plane, A's alpha inside the region
  ramps 1 -> 0 (feathered, B already playing); the dolly path goes through the region (per-frame track) and lands on B's
  hold with the measured decel; DOF focused on B so A defocuses as it nears. Pull = mirror (A behind B's region; B's
  region fades back to opaque after the camera passes B's plane).
- Eye shape = the visible eye opening between the lids (SAM2 from the track point, crop-and-upscale for small eyes);
  lens shape = the mask lens; background = inverse BiRefNet matte. Feather scales with on-screen size.
- Only zoom-ins/outs use this; whips, wipes, shatters, portals keep their own methods.

## 3. Pipeline (what each tool does)
- Plates (Python, VM): per shot at comp rate from the RIFE 240 fps source with the speed ramp, 16-f handles (most handles
  are freeze frames: clips are short), `$AMV3_DATA/plates/<shot>/f_NNNNN.jpg`. Tracks (DIS flow + anchors, hand-checked:
  several EDL focus seeds were wrong). Mattes (BiRefNet) + depth (Video Depth Anything Small; Large OOMs a 24 GB 4090 at
  518) on the pod; scene-segment threshold must follow the shot's own speed (a fast reversed shot was split into 31).
- Stage (Blender 5.2 Cycles): every shot is a 1.92 x 1.08 m card (1 px = 1 mm, emission, Standard view transform =
  pixel-exact pass-through, Gaussian 0.3 filter), one camera (35 mm), real motion blur (shutter 0.75 holds -> ~1.0 at
  cuts), passes plate / text (titles, matte holdout) / light (emissive FX for glow). Modules `blender/amv3/xfx/<type>.py`
  with `bounds()` + `build()`; touching windows resolve right-to-left.
- Finishing (EffectCraft): per-act grade (v2 GRADE), lens FX sized from the refs in each window (CA, radial blur,
  bulge, act-coloured leaks from the picture's highlights, flash only on big hits), glow on the light pass, 2D titles,
  grain. EffectCraft 0.10 also ships a Transition category (Card Wipe, CC Glass Wipe, CC Twister, CC WarpoMatic, CC Light
  Wipe, Gradient Wipe, Iris Wipe...) + Shatter, Card Dance, CC Scatterize, CC Page Turn, CC Light Rays/Burst, Face Track
  Points, Roto Brush; Gradient Wipe driven by the subject matte = the "background fades first" reveal.
- Mix: synthesized SFX per transition type (swell peaking into the smear, impact on the cut, tail), levels calibrated
  to the refs (cuts lift 3-12 kHz +4-8 dB), at most 1 dB of extra limiter pumping.

## 4. Process lessons
- Measure the references with a tool before designing (two research agents, numbers, strips), and gate renders on it.
- Show the user something early, but say exactly what is missing; a raw stage pass without grade/leaks/titles reads
  "basic" to them.
- Fleet: `fleetctl run` has no model flag; set `/model claude-opus-5-5` with `fleetctl prompt` before each brief (and
  after `done`). A shared contract file + one module per agent + an integration tester before GPU time works.
- RunPod: syncing 4.7 GB (16-bit depth PNGs) VM -> pod takes ~30+ min; keep the pod for several renders (`--no-data`).

## 5. Lessons from the v3.1 build (2026-10-18, same day)
- **Nest in practice** (`blender/amv3/nest.py`, `regions.py`): B's copy sits physically behind A's region; A's alpha inside
  the region ramps 1 -> 0 from ~10 f before the crossing; DOF on B (A defocuses as it nears); a seamless copy -> home
  teleport after w1 (same relative pose). An eye that is only ~40 px wide on screen (S31) only reads late: prefer bg or
  a closer source frame. bg nests grow B <= 1.8x before the crossing so it reads as picture, not mirror tiles.
- **Region masks** (`tools/filmtools/amv3/regions.py`, SAM 2.1 large on a 4090: ~80 s for 9 shots): click on the track
  point, crop-and-upscale small eyes (x3-x10), and for a lens that becomes a defocused world (a pull-out) segment the rim +
  fabric and invert. Ship `regions/` to the pod with the other data (forgetting it silently gives ellipse stand-ins:
  grep the stage log for "stand-in").
- **Rig**: camera on RIG_DOLLY > ORBIT > ROLL > SHAKE, Bezier keys from the path's derivative, channels staggered by 1 f.
  Camera shake must be smooth (0.10-0.2 cycles/frame, one kick + a damped counter-swing): a 0.4 cycles/f yaw reads as a
  frame-to-frame direction flip. A short hold (< 6 f) between two zooms must keep the zoom sign (push -> push) or the
  camera nearly stops; whips before a short hold land gently (decay x1.4) and keep sliding.
- **Module-in-full-film bugs**: test every module in the FULL build, not only `--only` (stub neighbours give gentle
  states). A layer sweep's cover search went to a x110 card and rendered 8 black frames only in the full film.
- **Render speed** (Cycles 5.2 on a 4090, `blender/amv3/renderopt.py`): the GPU sat at ~36 % because per-frame CPU work
  dominated. What fixed it: per-frame visibility baked into static segments (hidden objects leave the depsgraph; animated
  hide_render is still evaluated at every motion subframe), object motion blur off on static cards, camera motion_steps
  4 -> 2 (17 -> 5 scene evaluations), emission sampling NONE on card materials (no light-tree rebuild), OIDN on the GPU
  (`denoising_use_gpu` defaults to False: OIDN ran on the CPU, ~4 s/frame), OIDN only on glass/FX frames, thin glass
  (transparent + Fresnel glossy, no refraction) for small shards, near-lens glass stopped down (no f/2 bokeh fireflies).
  Result: half res 6.1 -> 1.7 s/frame plate per process; full res 64 spp 1.13 s/frame plate, the whole film (835 f x 3
  passes, 3 processes on one GPU) in 12.5 min (~$0.19).
- **Finishing on real passes**: glows tuned on stand-ins blew out on the real light pass (full-frame shards on the drop):
  duck the light-pass glow on dense FX frames; flashes only on the listed hits; bright skies that are 30-60 % clipped in
  the source cannot be recovered, only rolled off.
- **EffectCraft transitions** (probe on real plates): premium = Shatter (extruded pieces, as an overlay burst on a hit),
  Gradient Wipe driven by a matte/depth, CC Light Rays from the incoming shot's highlights (keep < 15 % clipped), CC Glass
  Wipe as a refractive edge accent; cheap = Card Wipe without a lit void, CC Twister, CC Light Wipe, CC Scatterize. The
  motion is the transition; these only accent it.
- **Spend discipline**: one pod for prep + all renders; never idle it (terminate when waiting on review); v3 total GPU
  ~$3.6 (prep 0.22, stage + outro + regions + bench + 3 film renders).
