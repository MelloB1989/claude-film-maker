# ue-helpers: morning report

This report covers the 2026-11-05 night. The lead (agent-10) keeps it current through the night; the final update
is at the bottom.

**Branch:** `ue-helpers`, built on `anime/rain-ferry` plus the reel and Linux work.

**What it is:** Unreal Engine 5.8 driven entirely from code for Claude.

- About 300 bridge ops in 25 areas, all discoverable (`film-ue ops`, `film-ue describe`) and callable as
  `film-ue <area> <verb> --args` or through the Python SDK (`filmtools.unreal.sdk`).
- Declarative specs that converge (`film-ue plan|apply <spec.yaml>`).
- Actionable errors: code, message, hint and did-you-mean.
- `film-ue doctor` to check a box.
- A selftest per area for today's GPU box.
- A demo that exercises every work package.

**Tests:** 832 unit tests green on a fake engine.

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
| WP2 assets | agent-02 | `assets.*`, `mat.*`, `fab.*` | any-format import (Interchange/FBX/USD/Alembic), catalog search ("a 45 cm chair"), refs/audit/redirectors, 12 master materials as graph specs, `mat.instance` convergence, Fab library/import (FabScript C++ plugin) | (assets.md pending) |
| WP3 MetaHuman | agent-04 | `mh.*` (43 ops) | create/body/face/skin/eyes/wardrobe/groom colours, non-blocking cloud rig and textures, build skips when current, dress/leader/clip checks, `character` spec kind, export round trip (B27) | metahuman.md |
| WP4 animation | agent-01 | `anim.*`, `perf.*` | perfkit (eye-head coordination, blinks, moods, emphasis from audio), curves, retarget (B30), `performance` compiler | (animation.md pending) |
| WP5 env/look | agent-08 | `env.*`, `light.*`, `look.*` | sun/sky (NOAA), photometry/exposure calibration, light rigs (B17), grades | (pending merge) |
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
832 passed (ue-helpers 0e9bab4)
```

Also: `film-ue dx docs` checks that every `film-ue ...` line in the docs names real ops and arguments, and
`python -m filmtools.unreal.apinotes` reports engine APIs used but not in any API_NOTES (240/344 covered at
22:00 UTC).

## 3. Today on the GPU box

Before anything else:

1. `film-ue doctor`
2. `film-ue install`
3. `film-ue epic-login` (needed by mh)

Then run `film-ue selftest`. It runs in this order and stops after a failed gate. The table is from
`film-ue selftest plan --md`:

| # | selftest | covers | needs | est. |
|---|---|---|---|---|
| 1 | platform (gate) | editor, bridge, jobs | nothing | 60 s |
| 2 | dx (gate) | ops registry, schema, errors, journal | nothing | 10 s |
| 3 | layout | level, layout, scene (+ settle, data layers) | GPU for stills/physics | 1.5 min |
| 4 | mh | mh | presets; Epic sign-in for part 2 | 2 min (+ cloud) |
| 5 | seq | seq | GPU for stills | 60 s |
| 6 | cam | cam, shot | GPU | 2 min |
| 7 | render | render | GPU | 4 min |
| 8 | qa | qa, view, groom | GPU | 2 min |
| 9 | audio | audio | nothing | 10 s |
| 10 | foliage | foliage | GPU for the still | 30 s |
| 11 | wp | wp | nothing | 30 s |

About 15 minutes in all (worst case, every timeout: 2.8 h). The first run also records the visual baselines (B43).
After that, run the demo (`examples/unreal/demo/README.md`) stage by stage.

What each selftest proves is in its module docstring and the area doc's "Selftest" section.

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
- **The orchestrator was offline.** Decisions the lead took alone are in DECISIONS.md.
