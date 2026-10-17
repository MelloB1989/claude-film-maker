# Timeless v2 pipeline (EffectCraft + Blender), runbook

v2 is a from-scratch rebuild of the Timeless AMV: an EffectCraft 0.10.0 project built by script from one EDL, Blender 5.x
for the 3D pieces, Python for data prep. v1 (`docs/PIPELINE-AMV.md`, `tools/filmtools/amv`, `blender/amv`) is untouched.
Creative spec: `films/timeless/amv2/EDIT.md`. Branch `amv2`. All commands run from the repo root with `PYTHONPATH=tools`.

```
edl.py -> edl.json ─┬─> prep (RIFE 240 fps + mattes, GPU pod) ─> $AMV2_DATA/{src240,mattes}
                    ├─> mix  ─> mix.wav + cues.csv
                    ├─> Blender pieces (GPU pod) ─> $AMV2_DATA/blender/{timeless3d,rift,shockwave,outro}
                    └─> ecbuild (libs) ─> .ecproj ─> render (VM, chunked) ─> frames ─> mp4 ─> package
```

`$AMV2_DATA` = `/home/nikhil/code/film-making/work/timeless_v2` on the render VM (ecbuild falls back to `out/timeless/amv2/data`).
It holds `src240/clip_<ID>.mp4`, `mattes/<clip>/NNNNN.png`, `blender/<element>/NNNN.png`, `mix.wav`, `cues.csv`, `special/`.
Container and VM do **not** share it: the VM has the real data, agent containers do not.

## 1. EDL
`python films/timeless/amv2/edl.py` writes `edl.json` (30 fps, 900 f, shots `[a,b)`, transitions, fx tags, titles, voice cues,
`hits`, `outro.hits`, `triptych`, `drop` = 480). Every stage reads it. Change the edit in `edl.py`, never in the JSON.

## 2. Prep: RIFE 240 fps + mattes (`tools/filmtools/amv2/prep.py`, `pod_prep.sh`)
- `bash tools/filmtools/amv2/pod_prep.sh [OUT]` on a RunPod 4090 pod with the repo and handover at their usual paths. It tests
  ffmpeg functionally (needs `-fps_mode`, ffmpeg >= 5.1, libx264; the pod image has 4.4) and downloads a static build if that
  fails, makes a venv, installs torch (cu124, else cu121) and pinned `transformers==5.20.1 timm==1.0.30 einops==0.8.2
  kornia==0.8.3`, pre-fetches the RIFE and BiRefNet weights, then runs both stages. Output `OUT/src240`, `OUT/mattes`
  (default `out/timeless/amv2_data`): copy to `$AMV2_DATA`.
- `prep.py rife240`: Practical-RIFE v4.25, 4 frames per source frame, same timeline, so output frame `4k` = source frame `k`
  and the clip keeps its duration (`4n` frames). **Never across a source cut**: the 3 frames before a cut repeat the last real
  frame (`retime.detect_cuts`; cuts in A09, M11, M13, M15, and one detected at A01 frame 1). A half-rate source (M01, >25 %
  repeated frames) is interpolated between its distinct frames (`--no-dedup` turns it off). Encode: h264 crf 12, **yuv420p**,
  `-g 8 -bf 0` (EffectCraft seeks constantly), bt709 tv. Sidecar `clip_<ID>.json` has frame counts and cut positions.
- `prep.py mattes` (default: A03_sunset_mask, M08_shuriken, T03_glove_city, M14_head_raise, M16_sunset_hero, T01_mask_night):
  BiRefNet (`ZhengPeng7/BiRefNet`) at 1024 px on the 240 fps frames, white subject on black, 8-bit grey PNG `NNNNN.png` from
  00000, triangle temporal smoothing radius 2 (never across a cut), levels 12..235 for a solid core. `matte.json` per clip.
- CPU smoke test (no GPU): `prep rife240 --clips M15_landing_crouch --out D --device cpu --scale 0.25 --limit 10`,
  `prep mattes --clips M16_sunset_hero --out D --device cpu --scale 0.5 --limit 1 --batch 1` (a 1024 px CPU run needs >7 GB).
  Verified on CPU only; check the first CUDA matte by eye.

## 3. Mix (`tools/filmtools/amv2/mix.py`, `audit_mix.py`)
`python -m filmtools.amv2.mix` -> `out/timeless/amv2/{mix.wav,cues.csv,mix_report.json}`; `python -m filmtools.amv2.audit_mix`
exits non-zero on a failure. Song = first 30.0 s of `timeless_full.wav`; voice cues from `edl.voice` (placed on the cue
frame, never filtered), the music ducked by `duck` dB (100 ms attack, 400 ms raised-cosine release; SFX half as deep; a line
that sits < 4 dB over the bed gets up to +6 dB and an extra duck, Tom's line after the drop did). 84 SFX from `sfx_kit.json`
placed so `hit_offset` lands on the frame: whoosh/whip/web_zip (Tom act) per transition, glitch_tick, reverse_swell into the
rift, riser into 480, impact_boom + sub_drop on 480/656/819, shutter_flash, glint, `hit` per `edl.hits` scaled by strength,
outro hits from `outro.hits`. Master: BS.1770 gated loudness -14 LUFS (measured -14.04), 4x-oversampled look-ahead limiter,
true peak <= -1 dBTP (measured -1.25), music ends on a raised-cosine fade, exact 0 on the last sample. `cues.csv` `word`
rows carry the MEASURED spoken onset of each word (the alignment in `voice_lines.json` is up to 0.17 s off): reveal the
subtitle word at onset frame + 1.

## 4. Build the project (`ecbuild.py`, `ec/*.jsx`)
`python -m filmtools.amv2.ecbuild [--src clips|src240] [--draft] [--samples N] [--out P] [--emit-only]` writes one script and runs
it with `effectcraft-cli script`. `--draft` = half-res plan with 4 motion-blur samples (default 16). `--src src240` needs
`$AMV2_DATA/src240`; mattes/elements that do not exist are skipped. Contract (details in `tools/filmtools/amv2/ec/README.md`):
- Project: one precomp `SHOT_<id>` per shot (footage with one time-remap key per comp frame, 6 handle frames each side), and
  `MAIN` 1920x1080 30 fps 900 f with a layer per shot, camera moves and transition keys per frame, motion blur on (comp shutter
  270 deg, phase -135).
- Libraries `ec/{fx,grade,special,titles}.jsx`, one global each (`FX GRADE SPECIAL TITLES`), called in stacking order:
  shots, `FX.buildUnder`, `GRADE.build`, `FX.buildOver`, `SPECIAL.build`, `TITLES.build`. Libs never re-key `SHOT_` layers
  (SPECIAL owns the shots around `rift`, `drop_portal`, `panel_slam`). Python numbers go in `E.x.<lib>` via
  `<lib>_spec.py: extend(E, ctx_py)`. `ctx.matte(id)` gives a `MATTE_<id>` layer for titles behind the subject.
- An exception in a lib is a warning and ecbuild exits 1: fix it, do not render.
- Time: a draft build took 4.5 min in a 4-core container.
Test harnesses: `tools/filmtools/amv2/test_{fx,grade,special,titles,elements}.py`, `tools/tests/test_amv2_*.py`.

## 5. Render (`tools/filmtools/amv2/render.py`, render queue)
`python -m filmtools.amv2.render [--draft] [--frames A-B] [--procs P] [--threads T] [--src src240]` builds into `build/amv2/`
(the queue syncs the tree but **not `out/`**), drops one queue job (`/home/nikhil/code/.renderq/README.md`, 3 h limit, at most
3 jobs for all agents), checks every PNG (missing frames, unexpected black; black is intended only at f0-1 and in the outro
fade), encodes h264 CRF 16 yuv420p +faststart with `mix.wav`, writes a contact sheet and `timings.json`. Output
`out/timeless/amv2/{frames[_draft]/f_NNNNN.png, Timeless_v2[_draft].mp4}`.
- `effectcraft-cli render`: `--start/--end` are SECONDS (frames by `ceil(t*fps)`: `--start (A-0.25)/30 --end (B-0.75)/30` gives
  A..B-1), `--out dir/f` is a prefix (`f_NNNNN.png`), `--project` goes before `render`. The only thread knob is
  `RAYON_NUM_THREADS`. `--gpu` has no adapter on the VM.
- **Memory.** One long-range process per half of the film was OOM-killed (rc 137) on the 31 GB VM at both full and half res
  (`timeless_v2-render`, `int1-render` in the queue logs); the CLI's RSS grows with the frames it renders. The fix is a queue of
  short chunks, each its own process that exits (default 48 frames, 1 retry, cache budgets via
  `EFFECTCRAFT_CONFIG_DIR/prefs.json`), written by agent-01's `fleet/agent-01/v2-core` @ 6e593ee (**not merged into `amv2` when
  this was written**: check `render.py` for `--chunk`). Peak RSS measured there: 6.2 GB for a 96-frame full-res chunk.
  3 parallel processes gave no gain (the render is CPU-bound): use 1-2 workers x 8 threads.
- Review: `python tools/filmtools/amv2/review.py FRAMES_OR_MP4 --f0 0 --f1 450 --out DIR` (cut strips, title strips, per-shot stats, flags
  BLACK/DUP/GHOST/CLIP/JUMP). Look at the PNGs.

## 6. Blender pieces (GPU pod)
`blender/amv2/pod_render.sh <pod-ip> <port> [--samples 96] [--device OPTIX|CUDA] [--only a,b] [--procs-outro 2]` (from the VM):
bootstraps the pod (`tools/filmtools/pod_bootstrap.sh`: Blender 5.2.2 + the X/GL libs, rsync, ffmpeg), picks OPTIX else CUDA
(fails without a GPU unless `--allow-cpu`), ships `blender/ films/timeless/fonts fonts` (+ the Spider-Man outro font, not in
git), renders concurrently, pulls to `$AMV2_DATA/blender/<element>/NNNN.png` and verifies every frame is 1920x1080 RGBA.
Pieces: `elements.py` -> timeless3d 802-826, rift 244-262, shockwave 480-489; `outro.py` -> outro 819-899. File name = comp
frame. **EffectCraft imports every PNG as straight alpha**, so elements.py writes straight alpha (`--alpha straight`
default); the outro is opaque RGB. Stop the pod after: `python -m filmtools.runpod down <id>`.
`.blend` files: `out/timeless/amv2/blender/{titles3d,rift,shockwave,outro_v2}.blend`.

## 7. Package (`tools/filmtools/amv2/package.py`, `blender/amv2/pack_blend.py`)
`python -m filmtools.amv2.package --mp4 M --ecproj P --blend-dir D --data $AMV2_DATA --mix $AMV2_DATA/mix.wav --cues
$AMV2_DATA/cues.csv --force` -> `deliverables/Timeless_v2_SAU_EDITZ/{mp4, effectcraft/*.ecproj, media/, fonts/, blender/,
audio/, README.md}`. The `.ecproj` is JSON: every Footage `path`/`sequence` is rewritten relative to it (`../media/...`;
EffectCraft resolves relative paths against the project file, probed). Only referenced media is shipped, hard-linked. The
`.blend` files run through Blender (`pack_blend.py`: relocate lost fonts/HDRI, pack, relative-remap; needs Blender, so run it
on the VM). Verification built in: a moved copy renders 3 frames from another cwd, each must be pixel-identical to the original
project's render, PSNR vs the mp4 is reported. Run it on the machine that has the media (the VM): a package of the draft was
599 MB (src240 529 MB for the 35 clips used).

## 8. EffectCraft 0.10.0 gotchas that matter (full list: `docs/EFFECTCRAFT-NOTES.md`)
1. **yuv444p h264 decodes wrong**; use yuv420p. 240 fps files import as 240 fps and time-remap correctly; short GOP is fine.
2. **PNG alpha is always straight.** Write straight-alpha PNGs; a premultiplied one is dimmed twice at the edges.
3. **Scripts cannot write files** (`File.open("w")` throws), `File.exists` is always false (probe with `importFile` in try/catch),
   `app.project.save()` works (also with relative paths). Fonts resolve by PostScript name from the system: install
   `handover/.../fonts/*` and `films/timeless/fonts/*` to `~/.local/share/fonts` + `fc-cache -f` (not installed in containers).
4. **Curves/rgbCurves cannot be set from script**; use Lumetri sliders. Layer styles only via
   `app.run("layer.style.add", {style: "dropShadow"})`; `gradientOverlay.colors` is unsettable. `app.run(id, params)` reaches every
   engine command (`effectcraft-cli commands`).
5. Time remap: `setValuesAtTimes` keeps the two default keys (remove them); set `outPoint` before `inPoint` when extending past the
   source duration; `keyInterpolationType` is not callable.
6. **Posterize Time** does nothing on an adjustment layer and also freezes the layer's masks: freeze with a time-remap hold.
7. Masks run before effects (a mask on a layer with Polar Coordinates is warped); use a luma track matte
   (`setTrackMatte(layer, TrackMatteType.LUMA_INVERTED)`, matte anywhere in the stack, disabled is fine).
8. VR Chromatic Aberrations is spherical (arches at the top and bottom): wrap it in Transform 95 % / 105.26 % (`FX.chromaStack`).
9. A Transform effect on an adjustment layer has no edge fill (shake = scale up per frame; slices = Offset effect, it wraps).
10. Motion Tile (mirror edges) is the slowest effect (500 % output: 0.6 -> 6-10 s/frame): size it per frame.
11. Precomps are not cached between layers: 35 shard layers over a live nested comp cost ~80 s/frame, so pre-render one still.
12. Motion blur does not sample across a hard cut: no ghost frame, no handle tricks needed.
13. Shatter plugin renders flat grey; shape layers: first added group draws on top, vertices are relative to the layer position;
    `moveBefore(x)` puts a layer above x.
14. Render facts: `RAYON_NUM_THREADS` only; leftover output dirs on the VM are reused (fresh name per experiment); the first
    script run after idle takes ~20 s.

## 9. Timings and costs (measured; blank = not measured yet)
| step | where | measured |
|---|---|---|
| ecbuild, draft | 4-core container | 4.5 min |
| single frame, ordinary / mid-glitch (6 fx layers) | container | 1-3 s / ~5 s; remapped 240 fps h264 frame 0.6-1.5 s |
| MAIN render, draft (half res, 4 samples) | VM, 1 process | ~1.57 s/frame (900 f = 23.5 min) |
| MAIN render, full res | VM | one full-res bench of 96 frames: 4.5 s/frame (431 s) |
| mix + audit | container | 3 s |
| BiRefNet 512 px | 4-core CPU | ~400 s/frame (smoke only) |
| RIFE 240, mattes, Blender pieces | RunPod 4090 | see the script output (`pod_render.sh` prints per-piece timings) |
| GPU cost | RunPod | v1 rebuild used about $1-2 in total; v2 pod time not recorded yet |
