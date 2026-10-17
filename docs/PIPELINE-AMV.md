# The AMV pipeline (plan-driven phonk / AMV edits, rendered in Blender)

An AMV here is a SanchezAE-style phonk edit: movie footage cut on the beat, a camera that never stops (zoom-ins and
pull-outs on every cut), eye-portal transitions, flash cuts, styled titles that ride the camera, a heavy glow grade and
a 3D extruded watermark outro. It was first built in After Effects by script; this pipeline rebuilds it on Linux with
Blender (Cycles) as the renderer, Python for the image work, and EffectCraft (getartcraft.com, the open-source After
Effects) as an editable project export.

The edit itself is data: **`films/<id>/amv/plan.json`**, every per-frame value of the edit. The pipeline never makes
editorial decisions; it renders the plan. Read `tools/filmtools/amv/plan.py` first: it defines the plan's
conventions (AE's: anchor at the layer centre, y down, rotation clockwise, scale %, linear keys, per-frame arrays) and
the accessors every stage uses, so the stages agree to the pixel.

The first film made with it is `films/timeless/` (Tobey -> Andrew -> Tom Holland Spider-Man, song "Timeless", 900 f at
30 fps, watermark SAU_EDITZ). Its handover from the After Effects era (specs, the AE scripts that are the exact spec of
every layer, references, a full-quality AE render of f0-599) is outside the repo at
`/home/nikhil/code/film-making/handover/amv_handover/` (`MASTER_PROMPT.md` first, then `skill/amv-edit/`).

## Stages and their contracts

```
clips (60p, intra) ──retime──► src frames ──bake──► layer frames ──┐
titles (Blender) ─────────────────┘ (shot-space titles)           ├─► Blender scene (Cycles, motion blur) ──► frames ──► mp4
                       screen-space titles, outro (Blender) ───────┘     + compositor: flash, strobes, grade,
                                                                           bloom, letterbox, accents, overlays
```

All outputs go under `out/<id>/amv/` (gitignored). Frame numbers in file names are **comp frames**, zero-padded to 4,
unless a stage says otherwise. Images are 8-bit sRGB PNG with **straight** alpha unless a stage says otherwise.

| stage | code | input | output |
|---|---|---|---|
| retime | `tools/filmtools/amv/retime.py` | plan, clips | `out/<id>/amv/src/<shot>/<f>.png`: 1920x1080 RGB, the clip as the layer shows it at comp frame f, integrated over the shutter |
| titles | `blender/amv/titles/` | plan titles | `out/<id>/amv/titles/<title_id>/<k>.png`: 1920x1080 RGBA, k = 0..dur-1 from the title's `f_in` |
| bake | `tools/filmtools/amv/bake.py` (+ `layerfx.py`) | src frames, shot titles, mattes | `out/<id>/amv/layers/<shot>/<f>.png`: RGBA at the shot's canvas (`Shot.canvas`), the layer exactly as AE renders it before its transform |
| grade | `blender/amv/grade.py` (+ `tools/filmtools/amv/grade_np.py`, its numpy twin) | | a compositor node group |
| scene | `blender/amv/scene.py`, CLI `blender/amv/build.py` | plan, layer frames, overlays | `out/<id>/amv/<id>.blend`; renders `out/<id>/amv/frames/<f>.png` |
| outro | `blender/amv/outro.py` | plan `outro` | `out/<id>/amv/outro/<f>.png` (comp frames `outro.f .. dur-1`) |
| export | `tools/filmtools/amv/effectcraft.py` | plan, layer frames | an EffectCraft project |

`<title_id>`: a shot title is `<shot name>.<i>` (i-th entry of the shot's `titles`), a screen title `screen.<i>`
(i-th entry of the plan's `titles`), the watermark `watermark`.

### retime: what the layer shows (AE's time remap + frame blending + motion-blur sub-samples)

AE rendered each shot as a precomp whose footage layer is time-remapped (`remap`), with frame blending (Frame Mix)
on `slow` shots, and the main comp's motion blur (301 deg shutter, phase -150 deg, 64 samples) sampled the precomp at
sub-frame times, so each output frame integrates the clip over the shutter. Retime reproduces that: for comp frame f,
take `plan.shutter_times(f, K)`, map each through `Shot.remap` (linear between frames) to clip seconds, fetch the
clip frame at that time (`mix`: linear blend of the two nearest 60p frames, AE Frame Mix; `rife`: optical-flow
interpolation at the exact time, the open-source stand-in for Twixtor, which the user's AE toolset had), and average.
`--mode nearest` (no blending, K = 1) exists for quick drafts.

### bake: the layer, in After Effects order

Inside the shot precomp, then on the main-comp layer, in this order (`build.jsx` is the spec):

1. **Balance**: Exposure `Shot.ev(f)` stops (AE's Exposure effect works in linear light), then Hue/Saturation master
   saturation `Shot.sat` when non-zero.
2. **Shot titles**: each title's RGBA frame `k = f - f_in` over the plate, for `0 <= k < dur` (and `k` < the shot's end).
3. **Matte cutout** (shots with `matte` and titles): the balanced plate, luma-matted by the matte frame, over the titles,
   so the hero word sits behind the subject; `rim`: a glow on the cutout (AE Glow: threshold 55 %, radius 18, intensity 0.6).
4. **Mask**: the eye-dive hole (`Shot.hole`): alpha 0 inside a feathered, expanded ellipse in layer px.
5. **Effects**, each on the result of the one before: Motion Tile (`tile` %, mirror edges, the canvas grows to
   `Shot.canvas`), CC Radial Fast Blur (`Shot.rfb`: amount, centre in layer px, Zoom = Brightest), Directional Blur
   (`Shot.dblur`), Optics Compensation (`Shot.bulge`: field of view, Reverse Lens Distortion on, FOV orientation
   value 2, view centre 960,540 of the layer).

The output canvas puts layer pixel (x, y) at canvas pixel (x + ox, y + oy) (`Shot.canvas`). Everything not covered
by the mirrored tile is transparent.

### scene: the main comp in Blender

- One scene, 1920x1080, `fps` from the plan, frames `0 .. dur-1`; Cycles; colour management **Standard** (not AgX or
  Filmic) so an emission plane shows its texture's sRGB values unchanged; pixel filter width ~1 px.
- Camera: orthographic, looking down -Z, framing exactly the 1920x1080 screen. 1 Blender unit = 100 px. Screen px
  (x, y) is world (x/100 - 9.6, 5.4 - y/100).
- A shot = a plane sized to its canvas (canvas px / 100), the layer frames as an image-sequence texture (emission,
  alpha from the PNG), the anchor at the layer centre (canvas offset accounted for), a linear key on every frame for
  location / rotation (z = -rz) / scale (s / 100). Stacking = `Plan.stack()` order, by z.
- Motion blur: Cycles, shutter 301/360 = 0.836, position Center, enough motion steps for curved per-frame paths.
- Opacity keys (`opacity`), the drop portal (`portals[]`: an `A_in` copy of shot A's layer with its own per-frame
  transform + opacity, alpha-matted by a per-frame screen-space ellipse `mx, my, mrx, mry, mrot, mfe`, placed directly
  above shot B), the portal's glint (a 4-point star pair, additive, keyed as `build.jsx`).
- Compositor, in this order on the shots: `flash_ev` exposure, 1-frame `black` and `invert` (+ duotone tint #010105 ->
  #C7DAE8) strobes, `halftone` hit frames (2 frames, dot grid 13), the **grade** node group, then over it: letterbox
  bars (`bars[f]` px top and bottom), `accents` lines, screen-space titles, watermark, and the outro frames from
  `outro.f` on.

### grade: the user's "Premium Glow CC" preset, rebuilt

The AE grade was the user's preset (Sapphire S_Sharpen -> Magic Bullet Looks: cool 3-way + lens vignette ~34 ->
Lumetri: Contrast 25, Highlights 10, Shadows 45, Whites 20, Blacks -12, Saturation 150 -> Brightness & Contrast 15 / 20),
then Color Balance (shadows -10/7/10, mids -2/4/-3, highlights 12/5/-12, preserve luminosity) and a Glow (threshold
84 %, radius 90, intensity 0.25). Exact values: handover `skill/amv-edit/references/13_color_grading.md`. Rebuilt as a
compositor node group (working in display-referred sRGB values, as AE's 8-bit project did) whose numpy twin is fitted
to the AE render's frames and tested to match the node group.

## Environment notes

- Blender 5.2.2 and static ffmpeg/ffprobe for every machine on the shared code path: `/home/nikhil/code/film-making/bin/`
  (`blender`, `ffmpeg`, `ffprobe`).
- Final renders run on a RunPod GPU pod (Cycles OptiX/CUDA). Code must run headless (`blender -b`), take paths and
  frame ranges as arguments, and never assume a display.
- Heavy outputs (frames) go to `out/<id>/amv/` on the machine that renders; tests write to a temp dir.

## EffectCraft export (`tools/filmtools/amv/effectcraft.py`)

The FilmCraft (Premiere-style) side, the installer and the general exporters: `docs/ARTCRAFT.md`.

An editable project of the same edit for the user's Linux machine: [EffectCraft](https://getartcraft.com/apps/effectcraft)
(open-source, Rust, After Effects-like; `.ecproj` = versioned JSON, schema 2). Built the way `build.jsx` built the AE project.

```
PYTHONPATH=tools python -m filmtools.amv.effectcraft --film films/timeless \
    [--layers out/timeless/amv/layers] [--titles ...] [--outro ...] [--source clips|baked|auto] \
    [--out out/timeless/amv/timeless.effectcraft-project] [--cli PATH] [--emit-only] [--preview 30,245,490 --scale 0.33]
```

`--out` is a folder: `<id>.ecproj`, `build.jsx` (self-contained, runnable with `effectcraft-cli script build.jsx`), `spec.json`
(every resolved number), `preview/`. The CLI is found via `--cli`, `$EFFECTCRAFT_CLI`, PATH, or the artcraft install dir (`python -m filmtools.artcraft install effectcraft`).

- **Tool**: the v0.10.0 release `effectcraft-0.10.0-linux-x86_64.tar.gz` (github.com/storytold/effectcraft/releases) has a headless
  `effectcraft-cli`: `script`, `render-frame`, `render` (mp4/png/exr...), `props`, `mcp`. No cargo build needed.
- **How**: `effectcraft_build.jsx` is a spec interpreter on EffectCraft's embedded After Effects object model, so the project is
  valid by construction. EffectCraft's match names differ from AE's (`ADBE Exposure2-0003` is the Red channel), so effect
  parameters are set by display name.
- **Clips mode** (default): per shot a precomp with the 60p clip, time remap keys, Frame Mix on `slow`, Exposure / Hue-Sat trim, the
  matte cutout (luma matte + CC-style rim Glow), titles; on the main layer Motion Tile (mirror), eye-dive hole (Add + Subtract
  mask, keyed shape / feather / expansion), CC Radial Fast Blur (Zoom Brightest), Directional Blur, Optics Compensation, per-frame
  position / scale / rotation keys (straight runs collapsed within 1e-3), 301 deg / -150 / 64-sample motion blur on the comp.
  Baked mode uses the bake stage's PNG sequences with only the transform keys.
- **Main comp** (bottom to top as build.jsx): audio mix, shots (+ the drop portal: `A_in` + ellipse alpha track matte), strobes
  (black, invert + tint, CC Ball Action halftone), flash exposure keys, grade adjustment layer (Unsharp, Color Balance, Lumetri,
  Brightness/Contrast, Color Balance teal/orange, Glow), letterbox bars, accents, portal glint, titles, outro, watermark.
- **Approximate**: grade values are fitted to the AE render (Lumetri / Glow differ from Adobe's); titles and the 3D outro are the
  Blender PNG sequences when present, otherwise text placeholders; `dips`, `flash_tint`, `voice`/`sfx` tracks are not exported
  (the film has no dips / tint; audio is the mix).
