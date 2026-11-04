# ue-helpers: morning report

This report covers the 2026-11-05 night. The lead (agent-10) keeps it current through the night; the final update
is at the bottom.

**Branch:** `ue-helpers`, built on `anime/rain-ferry` plus the reel and Linux work.

**What it is:** Unreal Engine 5.8 driven entirely from code for Claude.

- 348 bridge ops in 31 areas, all discoverable (`film-ue ops`, `film-ue describe`) and callable as
  `film-ue <area> <verb> --args` or through the Python SDK (`filmtools.unreal.sdk`).
- Declarative specs that converge (`film-ue plan|apply <spec.yaml>`).
- Actionable errors: code, message, hint and did-you-mean.
- `film-ue doctor` to check a box.
- A selftest per area for today's GPU box.
- A demo that exercises every work package.

**Tests:** 1018 unit tests green on a fake engine. They include:

- the whole demo applied end to end (the second plan is empty),
- all 15 selftests dry-run through the real harness (B45),
- `film-ue first-run` against the real bridge server, resuming after a stop.

**Not done:** nothing has run on a real editor yet (no GPU box tonight, by order). The selftests are the
acceptance tests.

Start here:

- [README.md](README.md): the docs index.
- [GUIDE.md](GUIDE.md): the loop for Claude.
- [RECIPES.md](RECIPES.md): 20 tasks with real JSON answers.
- [CONVENTIONS.md](CONVENTIONS.md).
- [DECISIONS.md](DECISIONS.md).
- [BACKLOG.md](BACKLOG.md).

## 1. What was built, per work package

| WP | owner | areas (op prefixes) | highlights | doc |
|---|---|---|---|---|
| WP0 lead/runtime | agent-10 | `ops.*`, registry | ops auto-discovery (a broken module is reported, not fatal), `ops.schema`, OpError(code/message/hint/candidates), shared fake engine `tools/tests/fakeunreal`, CONVENTIONS, the merge gate, `film-ue doctor` (B11), API_NOTES coverage (B40) | CONVENTIONS.md, doctor.md |
| WP1 platform | agent-07 | `editor.*`, `bridge.*`, `jobs.*`, `journal.*` | job registry with progress, cancel and a journal; transports (ssm/ssh/local); box up/down/TTL watchdog (AWS mocked); editor service; sync; `/batch`; auth and file-root hardening | platform.md |
| WP2 assets | agent-02 | `assets.*`, `mat.*`, `fab.*` | any-format import (Interchange/FBX/USD/Alembic), catalog search ("a 45 cm chair"), refs/audit/redirectors, 12 master materials as graph specs, `mat.instance` convergence, `material`/`asset` spec kinds, Fab library/import (Python route; FabScript C++ plugin optional) | assets.md |
| WP3 MetaHuman | agent-04 | `mh.*` (43 ops) | create/body/face/skin/eyes/wardrobe/groom colours, non-blocking cloud rig and textures, build skips when current, dress/leader/clip checks, `character` spec kind, export round trip (B27), seeded casts of extras (`cast` kind, B47) | metahuman.md |
| WP4 animation | agent-01 | `anim.*`, `perf.*` | perfkit (eye-head coordination, blinks, moods, emphasis from audio), curves, retarget (B30), `performance` spec kind; pose library `pose.*` (B31, agent-11) | animation.md, pose.md |
| WP5 env/look | agent-08 | `env.*`, `light.*`, `look.*` | sun/moon/sky/fog/HDRI, photometry with the engine's exposure calibration (EV100), light rigs relative to a camera (B17), presets (B16), grades, `environment`/`lighting` spec kinds | environment.md |
| WP6 layout | agent-10 (agent-12 stopped) | `level.*`, `layout.*`, `scene.*`, `wp.*` (agent-05) | find/describe/tag/folder, drop on support (bounds or trace), relative placement, row/grid/circle/seeded scatter that own their actors, align/distribute/snap, physics settle (B38), data layers (B44), `scene` spec with plan/apply/describe round trip; World Partition load by frustum/box (B37) | layout.md, wp.md |
| WP7 cameras | agent-11 | `cam.*`, `shot.*`, `foliage.*` | lens maths equal to CineCameraComponent's, framing solver (ECU..EWS, angles, thirds), moves, coverage on one side of the line, cut checks, shot lists from text (B18), shot list to render to review pipeline, foliage scatter/PCG (B39) | camera.md, foliage.md |
| WP8 Sequencer | agent-06 | `seq.*` (39) | pure model/plan/diff, `sequence` spec kind, batched writes (one call per track), retime/copy/chunks/pre-roll, timecode incl. drop-frame | sequencer.md |
| WP9 render | agent-05 | `render.*` | render spec with presets, chunking per camera cut with cloth pre-roll, resume, box split, VRAM guard, cost model, ffmpeg encode/concat, frame QA (B23/B24) | render.md |
| WP10 QA | agent-09 | `qa.*`, `view.*`, `groom.*` | viewport-free stills, contact sheets, exposure/framing/penetration/floating/overlaps, sequence review, visual baselines (B43), groom tuning (B28) | qa.md |
| WP11 DX | agent-13 | CLI, SDK, specs, selftests | generated `film-ue <area> <verb>`, typed SDK, plan/apply engine (kinds from every area), selftest harness and plan (B46), op journal (B32), GUIDE, RECIPES, Claude skill, DEMO | dx.md, GUIDE.md, RECIPES.md |
| WP12 audio/post | agent-03 | `audio.*`, film-post | audio import/place with dB and fades, timing doc, cut/mix/captions/EDL/encode delivery, loudness, `film-post speak` (text to TTS to face) | post.md |

## 2. Test status

```
cd tools && python -m pytest -q tests/test_ue_*.py tests/test_unreal_*.py tests/test_fmbridge_jobs.py
1018 passed (ue-helpers d67bfec)
```

Also: `film-ue dx docs` checks that every `film-ue ...` line in the docs names real ops and arguments, and
`python -m filmtools.unreal.apinotes` reports engine APIs used but not in any API_NOTES (357/357 covered: every engine name the
bridge uses has a verified API_NOTES row, and a test now fails on a new uncovered name).

## 3. Today on the GPU box

**First command:** `film-ue first-run` (B49, agent-07). It is a resumable checklist:

1. settings
2. reach the box
3. start the editor
4. install the bridge
5. wait for shaders
6. `film-ue doctor`
7. Epic sign-in
8. selftest platform + dx
9. the demo's stage 0

Each stop prints the next exact command, and a rerun continues where it stopped.

Then run the selftests. The plan below is generated by `film-ue selftest plan --md`:

Generated by `film-ue selftest plan --md` from the selftest modules. Run all of it with `film-ue selftest`
(this order; it stops after a failed gate: platform, dx), or one area at a time with `film-ue selftest <name>`.

Before: `film-ue --box NAME first-run --epic` (it runs doctor, installs the bridge and passes platform + dx; then `film-ue selftest --list` shows the capabilities: gpu, epic_login); `film-ue epic-login` first if epic_login is no (needed by: assets, mh).

| # | selftest | covers | REQUIRES (else skipped) | needs | est. | timeout | gate |
|---|---|---|---|---|---|---|---|
| 1 | `platform` | editor, bridge, jobs | - | nothing (no GPU, no Epic sign-in, no assets) | 60 s | 40.0 min | yes |
| 2 | `dx` | ops, journal | - | nothing (no GPU, no sign-in) | 10 s | 2.0 min | yes |
| 3 | `assets` | assets, mat, fab | gpu | GPU (stills, shader statistics); Fab sign-in optional | 3.0 min | 15.0 min |  |
| 4 | `layout` | level, layout, scene | gpu | GPU for the stills (the rest runs without one) | 1.5 min | 10.0 min |  |
| 5 | `mh` | mh | - | the MetaHuman Creator core data (presets); GPU for the stills; the Epic sign-in for part 2 (film-ue epic-lo... | 2.0 min | 25.0 min |  |
| 6 | `anim` | anim, perf | gpu | the MetaHuman plugin's optional content (/MetaHumanCharacter/Optional/Animation) and a GPU for the stills; ... | 2.0 min | 15.0 min |  |
| 7 | `seq` | seq | - | GPU only for the stills (everything else runs without one); no assets beyond the engine's (an AnimSequence ... | 60 s | 15.0 min |  |
| 8 | `cam` | cam, shot | gpu | a GPU (stills) | 2.0 min | 15.0 min |  |
| 9 | `render` | render | gpu | GPU | 4.0 min | 25.0 min |  |
| 10 | `qa` | qa, view, groom | gpu | GPU (a real RHI; offscreen is fine) | 2.0 min | 10.0 min |  |
| 11 | `audio` | audio | - | an editor with the bridge (no GPU work, no Epic login, no assets: it writes its own sine-tone WAVs into the... | 10 s | 2.0 min |  |
| 12 | `env` | env, light | gpu | GPU (a real RHI; offscreen is fine) | 4.0 min | 15.0 min |  |
| 13 | `foliage` | foliage | - | a GPU only for the still (skipped otherwise); no Epic login, no assets beyond the engine's basic shapes | 30 s | 5.0 min |  |
| 14 | `pose` | pose | - | a GPU for stills; a body Control Rig and its skeletal mesh in the project (else it is skipped with a note: e.g | 60 s | 10.0 min |  |
| 15 | `wp` | wp | - | nothing (no GPU work, no assets beyond engine shapes) | 30 s | 5.0 min |  |

Estimated total: 24.8 min; worst case (every TIMEOUT): 209.0 min.
Afterwards: `selftest-reports/<time>/summary.md`; then the demo (examples/unreal/demo/README.md).


**When a check fails:** every area doc has a "Day-1 triage" table: the failing check, its likely cause, the exact fix.

| area | doc |
|---|---|
| platform | platform.md |
| dx | dx.md |
| layout | layout.md |
| mh | metahuman.md |
| anim | animation.md |
| pose | pose.md |
| seq | sequencer.md |
| cam | camera.md |
| foliage | foliage.md |
| render | render.md |
| wp | wp.md |
| qa | qa.md |
| env | environment.md |
| audio/post | post.md |
| assets | assets.md |

What each selftest proves is in its module docstring and in the area doc's "Selftest" section. The first run also
records the visual baselines (B43), and later runs are checked against them.

## 4. Risks and open decisions for the operator

Updated through the night:

- **Nothing is proven on an engine yet.** Every engine call was checked against the 5.8.4 source (API_NOTES
  tables), but return shapes (tuples from out-params, enum names) only show up live. The selftests are ordered so
  the cheap foundations fail first.
- **EditorScriptingUtilities** (EditorAssetLibrary) is a plugin that is off by default (WP2's finding). The
  project must enable it, and `film-ue doctor` fails without it.
- **Fab needs a C++ plugin** (`unreal/plugins/FabScript`, WP2). It must be built into the project on the box.
  Fab ops answer `unsupported` without it.
- **`layout.settle` runs Simulate in Editor.** Whether that works in an offscreen `-unattended` editor is unknown;
  the layout selftest answers it.
- **MetaHuman cloud steps need the Epic sign-in on the box,** and cloud time is variable.
- **Uncalled:** a real ElevenLabs TTS call (`film-post speak`) and real ffmpeg (none on the fleet). The key comes
  through `fleetctl secret` only.
- **PyYAML is a direct client dependency** now. Re-lock `tools/uv.lock` on a dev machine (`uv lock`).
- **Behaviour change for host-studio (the reel):** `look.fog volumetric=true` now really enables volumetric fog
  (`enable_volumetric_fog`). The old code set a property name that does not exist in 5.8, so volumetric fog was
  silently never on. Re-renders of the reel's shots will differ in the haze. To keep the old look, pass
  `volumetric=false` in the studio scripts. Other deliberate differences: `tools/tests/test_ue_look_legacy.py`.
- **Cross-area API audits (B57) found live-only bugs the fakes hid, all fixed tonight:**
  - MetaHuman iris property names (`pattern`/`rotation`; every cast's eyes step).
  - The FBX option `use_t0_as_ref_pose`.
  - The audio Volume channel matched by its unique object name.
  - `seq.eval`'s ControlRigSequencerLibrary name.
  - The gaze-lock clip offset.
  - The hidden TraceTypeQuery enum (ECC_VISIBILITY).
  - `env.quality` writing project settings on the CDO (modal-dialog risk).

  The rule for how engine calls return in Python (PyGenUtil.cpp) is now in CONVENTIONS §12.
- **The orchestrator was offline.** Decisions the lead took alone are in DECISIONS.md.
