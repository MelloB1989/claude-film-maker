# 16. Timeless v2: EffectCraft + Blender from scratch (2026-10-17)

The user rejected the first Linux rebuild (ref 15) and asked for "everything from scratch using Blender and EffectCraft". v2 is a
new EDL, look and code path: an **EffectCraft 0.10.0** project (open-source After Effects clone, headless CLI with the AE
object model) built by script, **Blender 5.2** for the 3D pieces, Python for data prep. Code: **claude-film-maker**, branch
`amv2`, `tools/filmtools/amv2/*`, `blender/amv2/*`, film folder `films/timeless/amv2/` (`EDIT.md` = creative spec, `edl.py` ->
`edl.json` = the single source of truth). Runbook: `docs/PIPELINE-AMV2.md`; tool bugs: `docs/EFFECTCRAFT-NOTES.md`. Start from there.

## 1. What each tool does
| piece | tool | module |
|---|---|---|
| cuts, speeds, transitions, fx tags, titles, voice, hits | one EDL (30 fps, 900 f) | `films/timeless/amv2/edl.py` |
| slow-motion source | RIFE v4.25 at 240 fps, same timeline as the 60 fps clip (frame 4k = source frame k), no interpolation across a source cut, h264 crf 12 yuv420p short GOP | `amv2/prep.py rife240` |
| subject mattes (titles behind the subject) | BiRefNet 1024 px on the 240 fps frames, white on black, temporally smoothed | `amv2/prep.py mattes` |
| editing and compositing | EffectCraft project: precomp `SHOT_<id>` per shot + comp `MAIN`; libs FX, GRADE, SPECIAL, TITLES, one global each, called in stacking order | `amv2/ecbuild.py`, `amv2/ec/*.jsx` |
| rift, drop portal, triptych shatter | EffectCraft layers (SPECIAL), shards cut from one pre-rendered still | `ec/special.jsx` |
| 3D: chrome TIMELESS, rift, shockwave, SAU_EDITZ outro | Blender Cycles, RGBA PNG per comp frame (straight alpha), also saved as .blend | `blender/amv2/{elements,outro}.py` |
| audio | song 0-30 s + voice (ducked music) + 84 SFX on exact frames, -14 LUFS, -1 dBTP, clean end | `amv2/mix.py`, `audit_mix.py` |
| delivery | portable folder: relative-path .ecproj, packed .blend, README, self-verifying | `amv2/package.py` |

## 2. Run order and timings
edl -> **prep on a RunPod 4090** (`pod_prep.sh`: RIFE 240 for 33 clips, 6 mattes) -> mix (3 s) -> **Blender pieces on the pod**
(`pod_render.sh`) -> ecbuild (draft 4.5 min) -> render on the VM through the queue (draft ~1.6 s/frame single process; full res
slower, ~4.5 s/frame measured once) -> encode CRF 16 with the mix -> review -> package. Always do a half-res draft first. A
whole-film render needs short chunked processes (gotcha 8).

## 3. Gotchas (each cost a probe or a render)
1. **Probe every EffectCraft feature with a 3-line script and look at the frame.** It is young: some match names differ from AE
   (text tracking, layer styles via `app.run("layer.style.add", ...)`), and `app.run(id, params)` / `effectcraft-cli commands` is
   the door to the engine.
2. **yuv444p h264 imports but decodes wrong** (mean error 165/255). Use yuv420p; `-g 8 -bf 0` seeks as fast as the 60 fps source.
3. **PNG alpha is imported straight, always** (no interpret-footage switch). Write straight-alpha PNGs from Blender; a
   premultiplied file gets dark glows.
4. Scripts cannot write files; `File.exists` is always false (probe with `importFile` in try/catch); fonts resolve by PostScript
   name from the installed fonts (install them in every container and VM job).
5. Curves cannot be set from script (Lumetri sliders instead); Posterize Time on an adjustment layer does nothing and freezes
   masks (use a time-remap hold); masks run before effects (use luma track mattes); the VR chromatic effect is spherical (wrap in
   Transform 95 %/105.26 %); Transform on an adjustment layer has no edge fill.
6. Motion blur does not sample across a hard cut, so cuts need no handles and there are no ghost frames. Never interpolate across a
   source cut in RIFE (v1's ghost frames): hold the last real frame.
7. Cost traps: Motion Tile with a big output (6-10 s/frame, key it per frame), cutting shards from a live nested comp (80 s/frame:
   pre-render a still), Blender volumetrics and full-res glare.
8. **`effectcraft-cli render` memory grows with frames rendered**: two long-range processes were OOM-killed (rc 137) on the 31 GB VM.
   Render short chunks (about 48 frames), one process each, retry once; 1-2 workers x 8 threads (more gave nothing: CPU-bound).
   `--start/--end` are seconds, `--out` is a prefix, `RAYON_NUM_THREADS` is the only thread knob, no GPU adapter on the VM.
9. The render queue VM syncs the worktree but not `out/`: keep the `.ecproj` in `build/`. Data that exists only on the VM
   (`$AMV2_DATA`) cannot be seen from the container, so build, render and package where the media is.
10. pod images ship ffmpeg 4.4: `-fps_mode` needs >= 5.1 (static build); Blender needs libSM/libGL/libXi...
    (`pod_bootstrap.sh`); CUDA torch wheel must match the pod driver (cu124, else cu121).
11. A `.blend` keeps relative paths to where it was saved: copied elsewhere, fonts and HDRIs go missing. Pack
    (`blender/amv2/pack_blend.py`) before delivering.
12. Measured word onsets beat the forced alignment (up to 0.17 s off): reveal subtitles at the `cues.csv` word frame + 1.
13. Check the result like a reviewer: contact sheet, cut strips, per-shot stats (`amv2/review.py`: black, frozen, ghost, clipped,
    jump flags) before shipping.

## 4. Infrastructure that made it work
- **Fleet agents own one stage each** (core/ecbuild, fx, grade, special, titles, elements, outro, prep+mix, package), with a
  contract: libs are `ec/<lib>.jsx` defining one global, python extras in `<lib>_spec.py: extend(E, ctx_py)`, integrated on a
  branch for test renders, merged to `amv2` when their tests pass.
- **Render queue** (agents hold no VM credentials): JSON job -> VM -> output copied back; `$AMV2_DATA` is the shared input.
- **RunPod 4090** for RIFE, BiRefNet and Cycles (`pod_prep.sh`, `pod_render.sh`, `filmtools.runpod`): the operator starts and
  stops the pod; scripts verify their output (frame counts, size, RGBA) and fail loudly. v1 used about $1-2 of GPU in total.
- **Package self-check**: the delivery is re-opened from a moved copy and 3 frames must equal the original project's render.
