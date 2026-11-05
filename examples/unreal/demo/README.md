# The demo: a 3-shot MetaHuman scene, end to end, by spec

One host at a desk in a two-walled set, lit with key, fill and rim, says one line. Three shots (a wide, a medium
close-up with a push-in, a close-up) are cut together, reviewed, rendered and delivered. Every work package is
exercised. Everything is declarative: `film-ue apply` converges, and a second apply changes nothing.

| stage | file | WP | what | time on an L4 |
|---|---|---|---|---|
| 0 | (box) | WP1, WP11 | the box is up, the bridge answers, the selftests pass | 5 min |
| 1 | `10-character.yaml` | WP3 | MetaHuman from a preset, cloud rig + textures, built Blueprint | 10-20 min |
| 2 | `20-set.yaml` | WP6, WP2 | the level and the set (scene spec) with the host in it | 1 min |
| 3 | `30-look.yaml` | WP5 | three rect lights, haze, fixed exposure | 1 min |
| 4 | `40-performance.yaml` | WP4, WP12 | the voice line solved to a face animation | 2-4 min |
| 5 | `50-sequence.yaml` | WP8, WP12 | a 7 s sequence: body idle, face line, voice on a track | 1 min |
| 6 | `60-shots.yaml` | WP7 | three cameras framed by the solver, keys, cuts | 1 min |
| 7 | `70-qa.yaml` | WP10 | one review of the cut: stills, framing, exposure, floating props | 2 min |
| 8 | `80-render.yaml` | WP9 | Movie Render Queue, preview then final | 2 min / 10 min |
| 9 | `90-delivery.yaml` | WP12 | the film files (film-post) | 2 min |

All commands run from `tools/` (`cd tools && uv run film-ue ...`; below, `film-ue` for short). `vars.yaml` holds the
names and paths; every stage file includes it, so each stage applies by itself; `demo.yaml` includes stages 1-7 in
order. Every apply prints its steps and ends with `converged` or what is left. `--set name=value` overrides a var.

## 0. The box: one resumable command

```bash
film-ue --box demo first-run --epic --voice path/to/demo_line.wav
```
It checks and fixes, in order: the settings, reaching the box, the editor service, the bridge (installed from this
checkout), the shader compile, `film-ue doctor`, the Epic sign-in (`--epic`: it prints a code for
epicgames.com/activate), `film-ue selftest platform dx`, and puts the voice line (any 3-5 s spoken WAV) at
`/srv/film/demo/demo_line.wav`. On a failure it stops with the exact next command; run it again to continue
(`film-ue --box demo first-run --status` shows where it is; docs/unreal/platform.md). Expected at the end: every step
done and "next, film-ue apply examples/unreal/demo/10-character.yaml".

Then, optionally, every area's acceptance test before the demo (~15 min; `film-ue selftest plan` shows the order):
```bash
film-ue --box demo selftest                       # stops after a failed gate; report in selftest-reports/<time>/
```
Check: first-run ends with every step done (the MetaHuman stage needs the Epic sign-in step).

## 1. The MetaHuman (WP3)

```bash
film-ue plan ../examples/unreal/demo/10-character.yaml        # 4 steps: mh.from_preset, mh.rig, mh.textures, mh.build
film-ue apply ../examples/unreal/demo/10-character.yaml --stop
```
Expected: `mh.from_preset` -> `/Game/_Demo/MH/Demo_Host`; `mh.rig` and `mh.textures` (minutes each, the cloud);
`mh.build` -> the Blueprint path; `converged`. Now check the two paths the later stages need:

```bash
film-ue assets list --path /Game/_Demo/MH --cls Blueprint      # the BP: set host_bp to it
film-ue assets list --path /Game/_Demo/MH --cls SkeletalMesh   # the *FaceMesh: set face_mesh to it
```
If they differ from `host_bp` / `face_mesh` in `demo.yaml`, edit the vars (or pass `--set host_bp=... --set
face_mesh=...` to every command below). Check: `film-ue plan ../examples/unreal/demo/10-character.yaml` shows every
document as `=` (converged: `unless` sees the Blueprint).

Failures: `mh.rig` "no Epic sign-in" -> stage 0's epic-login. `mh.build` "no BP_Host built ... is the character
rigged" -> mh.rig did not finish: look at `film-ue log 200`.

## 2-7. The scene, the light, the performance, the sequence, the shots, the review

```bash
film-ue plan ../examples/unreal/demo/demo.yaml                 # what is left, stage by stage
film-ue apply ../examples/unreal/demo/demo.yaml --json > /tmp/demo-apply.json
film-ue apply ../examples/unreal/demo/demo.yaml                # again: every stage "=", ends "converged"
```
Expected on the first full apply (in this order):
- `level /Game/_Demo/L_Demo`: `level.new` (or `level.open`).
- `scene demo-set`: 6 `level.spawn`, their `level.tag` / `level.folder`, one `layout.drop` (Desk, Stool rest on the
  floor).
- `op light-key|light-fill|light-rim|haze|exposure`: `look.light` x3, `look.fog`, `look.post` (these re-run on every
  apply: marked `!`).
- `op speech`: `speech.to_face` (1-3 min) -> `/Game/_Demo/Speech/Anim/AS_demo_line` and the SoundWave
  `/Game/_Demo/Speech/Audio/demo_line`. If the WAV was not named demo_line.wav, set `voice_sound` to what
  `film-ue assets list --path /Game/_Demo/Speech/Audio` shows.
- `op sequence|body-idle|face-line|face-driven`: `seq.new`, two `seq.anim`, `mh.drive_face`.
- `audio demo-audio`: `audio.place` (VO at frame 48).
- `shot /Game/_Demo/SEQ_Demo`: `shot.apply`: cameras `CAM_Demo_S1..S3`, keys, cuts at 48 and 120.
- `op review`: `qa.review` -> `{"pass", "verdict", "summary", "issues", "image": ".../qa/review.png"}`.

Check, without a UI:
```bash
film-ue seq cuts --path /Game/_Demo/SEQ_Demo                   # [["CAM_Demo_S1", 0, 48], ["CAM_Demo_S2", 48, 120], [..., 120, 168]]
film-ue view stills --sequence /Game/_Demo/SEQ_Demo --out-dir /srv/film/demo/out/stills --per-shot 2
film-ue pull /srv/film/demo/out/stills/sheet.png /tmp/demo-sheet.png     # the cut in one picture: LOOK at it
film-ue pull /srv/film/demo/out/qa/review.png /tmp/demo-review.png
film-ue qa framing --subjects '["Host"]' --sequence /Game/_Demo/SEQ_Demo --frame 80 --camera CAM_Demo_S2 --json
```
What good looks like: the WS shows the host full length at the desk; S2 a medium close-up from the left 3/4 pushing
in; S3 a close-up from the right 3/4; eyes sharp (focus follows the eyes); no "fail" issues in the review (a "warn"
on exposure is fine for a preview). The mouth moves from frame 48 with the voice.

Common fixes: the host faces away from the cameras -> change its `rot: {yaw: ...}` in `20-set.yaml` (MetaHumans face
+Y in their Blueprint; the solver frames whatever faces it, so the shots follow) and apply again; floating props ->
the review lists them with a `fix`; the face does not move -> `mh.drive_face` ran before the face section existed:
apply again (it converges).

## 8. Render (WP9)

```bash
film-ue plan ../examples/unreal/demo/80-render.yaml
film-ue apply ../examples/unreal/demo/80-render.yaml                     # preview: fast, for a look
film-ue apply ../examples/unreal/demo/80-render.yaml --set preset=final  # the final (~0.7 s/frame at 1080p)
film-ue render progress --out-dir /srv/film/demo/out/render --expected 168   # frames so far, while it runs
```
Expected: 168 PNGs in `/srv/film/demo/out/render`; a second apply with the same preset changes nothing.
Path tracing (`pathtrace`) runs out of memory on the 24 GB L4: do not use it on that box.

## 9. Deliver (WP12)

```bash
film-ue pull-dir /srv/film/demo/out/render ../out/demo/render
film-post plan ../examples/unreal/demo/90-delivery.yaml
film-post apply ../examples/unreal/demo/90-delivery.yaml                  # ../out/demo/web.mp4
```

## Clean up

Keep it (the next apply converges without redoing anything), or leave the level and delete the folder:
```bash
film-ue level new --path /Game/_Scratch/L_Empty
film-ue exec -c "import unreal; result = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).delete_directory('/Game/_Demo')"
```

## Tested here (without a box)

`tools/tests/test_ue_dx_spec.py::test_demo_*`: every document validates against its kind's schema, every step names a
real op with real argument names (checked against the op schema), and the stages run in dependency order
(MetaHuman before the set, the sequence before its audio and shots, the review last).
