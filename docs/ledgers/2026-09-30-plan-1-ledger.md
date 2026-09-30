# SDD ledger — plan: docs/plans/2026-09-30-plan-1-foundation-animatic.md

- **Spec:** docs/specs/2026-09-30-gitloom-launch-film-design.md (reachable; binding authority)
- **Branch:** plan-1-foundation, cut from main @ dbb9123. The merge base for the final review is dbb9123.

## Setup rulings

- **Ruling:** branch in place (plan-1-foundation), not a git worktree.
  - **Why:** paid audio (voice takes, score variants) lives on disk untracked, and removing a worktree would delete
    it. The repo is new, with nothing else on main.
  - **Cost if wrong:** none; the work can move into a worktree later.
- **Ruling:** stop at the plan's checkpoints: C1 (Task 6 Step 6), C2 (Task 8 Step 8) and C3 (Task 15 Step 7).
  - **Why:** spec §8.3 makes them human listening and viewing gates the user approved, and the agent can't hear audio
    (spec §5.6).
  - **Cost if wrong:** idle time only.
- **Ruling:** never run `git clean`. The controller copies `audio/` to `~/Developer/code/gitloom-film-audio-backup/`
  after Task 4 and after Task 8.
  - **Why:** the takes and the score cost credits, and neither the TTS nor the music model reproduces its output
    exactly.
  - **Cost if wrong:** about 150 MB of disk.

## Pre-flight scan

### Shared files and interfaces

| pair | producer → consumer | finding |
|---|---|---|
| T1 → T4–T15 | `paths.{ROOT,DATA,AUDIO,OUT,APP,FONTS}` | every name the consumers import is defined in T1 ✓ |
| T1 → T4–T15 | pyproject console scripts → each module's `main(argv=None)` | 10 scripts ↔ 10 mains, names match ✓ |
| T2 → T4 | `tts(voice_id, text, model_id, output_format, speed=, seed=)` | T4 call `client.tts(VOICE_ID, text, MODEL_ID, "pcm_48000", speed=speed)` ✓ |
| T2 → T8 | `compose(plan, output_format=, seed=)`, `ElevenLabsError.status` | T8 fallback uses both ✓ |
| T3 → T4, T5, T7, T8, T9 | `pcm16_to_float(b, channels)`, `write_wav`, `read_wav(mono=)`, `SR`, `words_from_alignment`, `words_to_dicts` | signatures match at every call site ✓ |
| T4 → T5 | take JSON `{take, duration, words[{w,start,end}], …}` | `pace_take` reads `words`; the main loop globs `takes/*/*.json` ✓ |
| T4 → T6, T7, T10, T15 | `load_script() -> dict` (acts, lines) | every consumer indexes `["lines"]`/`["acts"]` ✓ |
| T5 → T6, T7 | `load_selects()`, paced JSON `{take, factor, duration, words}` | `vo_page` and `place` read exactly these ✓ |
| T6 → T8 | `music_page(variants, out, sections)` | T8 passes `meta["sections"]` ✓ |
| T7 → T8 | `data/vo.json` scenes (id, start) and duration | `build_plan` reads the first scenes ex/her/loom/honest/proof/weave, all present in script.json ✓ |
| T7 → T9 | vo.json lines/words, `audio/vo/vo.wav` | vocal onsets and envelope ✓ |
| T7 → T10 | `act_spans(script, scenes)`, `write_vo(vo)` | imported by snap ✓ |
| T8 → T9, T11 | `data/music_plan.json {plan, meta{bpm,sections}, variants, chosen}` | beats reads meta+chosen, mix reads chosen ✓ |
| T9 → T10 | audio.json beats/downbeats/duration | ✓ |
| T9 → T13 | audio.json vs `AudioJSON` (duration, bpm, beats, downbeats, sections, fps, top-level envelopes, onsets{kick,snare,hat,vocal}) | the engine accepts top-level envelopes; extra keys (grid_error_ms, grid_fit) are harmless ✓ |
| T10 → T13, T14 | vo.json lines(id, scene, act, text, words), scenes(id, act, start, end), acts(id, name, start, end) | the `VO` class reads exactly these ✓ |
| T11 → T13, T15 | `audio/mix/mix.wav` | main.ts and render.ts point there after T13's edits ✓ |
| T12 → T13 | `Bricolage-w{750,875,1000}-{300,500,600,800}`, `JetBrainsMono-{400,500,700}`, `JetBrainsMonoItalic-400`, `Geist-{400,500,600}` | type.ts DEFS file names match ✓; T13 copies only `public/fonts/stroke`, so it doesn't clobber T12's fonts ✓ |
| T13 → T14 | `SceneSpan`/`Line` exports, `F`/`font`/`layout`, `Layer2D`/`clearRT`, `TimelineEntry` (+`file`, added in T14) | ✓ |
| T13 → T15 | `render.ts` modes after the sed edits (video, sheet --cuts, fps 30) | ✓ |

### Each task against itself

| task | finding |
|---|---|
| T1 | test expects `FONTS`, which paths.py defines; the commit includes uv.lock from `uv sync` ✓ |
| T2 | retry test: sleeps [2.0, 4.0] match the backoff; the error test's scrubbed body contains `<redacted>`; the URL/body assertions match the code ✓ |
| T3 | the alignment test indices, recomputed by hand (conversation 0.6–1.8, Forty-four 0.5–1.5), match ✓ |
| T4 | 33 lines (L01–L32 + L18b); takes = 8×4 + 24×3 + 2 = 106, as Step 6 expects ✓ |
| T5 | trim test arithmetic (1.12 s, 0.04, 1.04) and pace test (0.036) recomputed ✓ |
| T6 | the "chosen" count assertion was corrected to 2 (L02 falls back to take 1) before the plan was committed ✓ |
| T7 | placement (1.0/2.5/4.0/7.5, duration 10) and s2 cut 3.74 recomputed ✓ |
| T8 | bars (7.2/7.2/14.4/36.0/4.8/14.4/7.2 = 91.2 s) and the 2-bar stretch (4800 ms) recomputed ✓; the channel inference covers mono and stereo ✓ |
| T9 | `_norm` fixed for sparse signals and `grid_fit` added (both before the plan commit); downbeat 14.65 recomputed ✓ |
| T10 | cut picks 3.8/7.4 and the fallback band 2.15–2.29 recomputed ✓ |
| T11 | ebur128 summary regexes match the ffmpeg summary format; sidechain input order is [signal][key] ✓ |
| T12 | the sources are downloaded (Step 1) before the tests that read them (Step 2) ✓ |
| T13 | the FPS import uses perl (BSD sed can't insert `\n`); typescript is a devDependency; the grep is scoped against false positives ✓ |
| T14 | `edit.ts` stays free of `import.meta.glob`, so bun can test it; card types line up with T13's exports ✓ |
| T15 | the check test cases recomputed (3.9 off by 100 ms; 8.0 is a beat but not a downbeat) ✓ |

**Result:** no conflicts between tasks, or between a task and the Global Constraints. No rubric-defect mandates. No
further rulings needed.

## Progress
- **Task 1: complete** (commits dbb9123..b5aaa2b, review clean)
  - ⚠️ docs/specs tracked? Resolved: tracked since ea75770.
  - Minor (deferred): test_paths positive/`and`-marker cases are weak (plan-mandated).
  - Minor (deferred): `app/node_modules/` in .gitignore is redundant with `node_modules/` (plan-mandated).
  - Minor (deferred): the whole-branch review must confirm all ten `film-*` modules and the app/ and fonts/src dirs end
    up existing.

## User direction (2026-09-30, mid-run)

The user asked for fewer reviews ("only important and tricky things") and Opus 5.5 for creative work, and is eager to
see results.

- **Ruling:** full task reviews only for T9 (beats), T11 (mix/loudness) and T13 (engine fork).
  - T14 is checked by the controller looking at rendered stills.
  - Mechanical tasks (T2, T3, T5, T6, T7, T10, T12, T15-code) get a controller spot-check of the report's test evidence.
  - The final whole-branch review is kept, on Opus.
  - **Why:** the user's instruction outranks the skill default; these tasks transcribe complete code that their own
    tests verify.
  - **Cost if wrong:** a defect in a skipped task surfaces later, caught by the next task's tests or the final review.
- **Ruling:** Opus for T13, T14 and all creative work in Plans 2–4; Sonnet for tasks with real-world steps (T4, T5,
  T8, T9, T11); Haiku only for pure transcription.
  - **Why:** the user wants no degraded quality on creative work.
  - **Cost if wrong:** spend only.
- **Task 2: complete** (commits b5aaa2b..0e328eb, spot-checked: the suite passes; no review per the user's direction)
- **Task 3: complete** (commits 0e328eb..10812de, spot-checked: 19 pass)
- **Task 4: complete** (commits 10812de..f5bbc10, spot-checked; 106 takes, 318 credits; audio backed up)
- **Ruling:** added Task 4b (brief `task-4b-brief.md`): re-time every take with ElevenLabs forced alignment before
  pacing.
  - **Why:** v4's TTS alignment is quantized to 80 ms and measured up to 180 ms off the audio (L02/1: "zero" at 2.70
    real vs 2.88 TTS; speech starts at 0.16 vs 0.0). Spec §2 binds words to ±1 frame, and Task 5's trim needs true
    word edges. The probe cost 1 credit and gave 20 ms resolution.
  - **Cost if wrong:** about 106 credits and one small module.
- **Task 4b: complete** (commits f5bbc10..afab660, spot-checked).
  - forced 106, fallback 0; 84 credits logged.
  - 88/106 takes had hidden leading silence of more than 0.1 s.
  - Note for scene work: tiny-span words ("a", "I", ~1–40 ms) mean hold times should use the next word's start.
- **Task 5: complete** (commits afab660..727f4ce, spot-checked; 37 pass; 106 paced; take-1 sum 87.76 s raw → 74.65 s paced).
  - **Ruling:** accept deviation 727f4ce (the trim widens over contiguous speech above −45 dB).
    - **Why:** the aligner starts first words ~85 ms late and ends last words ~80–110 ms early, so the verbatim trim cut
      speech from 97/106 heads.
    - **Cost if wrong:** a few ms of extra room tone per take.
  - **Ruling:** Task 7's `place()` applies `word_lead` from data/edit.json (set to 0.05 s) to word starts only. The
    result is monotonic (never before the previous word's start) and never before the line start.
    - **Why:** measured on paced take 1 of every line, aligned first-word starts trail the audible onset by a median
      53–72 ms (threshold −15..−30 dB). The after-pause median of ~110 ms is inflated by early word ends. Spec §2
      wants reveal within ±1 frame, and 50 ms stays under the measured bias, so a reveal never runs ahead of the voice.
    - **Cost if wrong:** words appear up to 50 ms early, which is imperceptible as anticipation.
  - **Ruling:** Task 6 adds `.gitignore` entries for generated audio (`audio/vo/paced/`, `audio/vo/vo.wav`,
    `audio/music/`, `audio/mix/`).
    - **Why:** 36 MB+ of WAV sits untracked, one `git add -A` from the repo. The backup plus regenerability cover
      loss.
    - **Cost if wrong:** none.
- **Task 6: complete** (commits 727f4ce..3ca6ab9, spot-checked; 39 pass). C1 opened for the user.
- **C1: closed.**
  - **Ruling:** takes picked by the controller at the user's request ("all takes almost sound same, go with what works
    best"). Lowest forced-alignment loss per line; outliers >20% off the median length or clipping ruled out (none
    were). 20/33 lines are non-default picks. Commit: see git log.
  - **Cost if wrong:** swap any take at C3 with a one-line selects edit.
- **Task 7:** ec51eb4 placed at 95.64 s (over the 95 s ceiling).
  - **Ruling:** gaps line 0.35 / scene 0.55 / act 1.0, tail 2.3 → target ≤ 93.6 s of voiceover.
    - **Why:** the score is whole bars (2.4 s at 100 BPM) and the film ends on its last bar, so the voiceover must end
      by 93.6 s for the film to end by 95 s. All values sit within the spec §8.2 ranges; no lines are cut.
    - **Cost if wrong:** slightly tighter act breaks; the user can loosen them at C3.
  - Fix round 1/5 dispatched (resumed implementer).
- **Task 7: fix round 1/5** (1 addressed, 0 open; commits ec51eb4..4fbe878).
- **Task 7: complete** (commits faa3bd2..4fbe878, spot-checked; 45 pass). Voiceover 93.49 s; acts I 0–16.03, II –28.13,
  III –73.03, IV –86.43, V –93.49.
- **Task 8:** BLOCKED on the first live call (HTTP 422: the composition_plan type is invalid for music_v2_5). 0 credits
  spent.
  - **Ruling:** keep music_v2_5 (spec §5.2, best quality) and add `to_chunks()`, sending
    `{"chunks": [{text:"[Name]", duration_ms, positive_styles: global+local, negative_styles: global+local,
    context_adherence:"high", conditioning_ref:null, condition_strength:null}]}`.
    - **Why:** the free /v1/music/plan endpoint shows the v2.5 schema. A live 3 s probe with our 15 styles succeeded:
      pcm_48000 is stereo, the response has no character-cost header, and the probe cost ~4 credits by the balance.
    - **Cost if wrong:** a re-generation. Balance before the variants: 886 used / 39,994.
  - Fix round 1/5 dispatched (resumed implementer).
- **Task 8: fix round 1/5** (the chunk format is fixed; commit 3b8d8fa). 3 variants, 3,548 credits by the balance.
  - Per-bar RMS shows the model ignored the section dynamics (seeds 11/13 flat at 0 dB; seed 12 pumps and ends
    abruptly).
  - **Ruling:** fix round 2 splits the styles into a PALETTE (all chunks) and a GROOVE_KIT (her/tour/proof only), gives
    the quiet sections explicit negatives, and sets context adherence to "low" for honest and proof. Generate seeds
    21 and 22; all five are candidates at C2 with measured arc adherence.
    - **Why:** to_chunks put "soft round kick, brushed hats…" into every chunk, contradicting "no drums/near silence".
    - **Cost if wrong:** about 2,400 credits (34.4k left).
- **Task 8: fix round 2/5** (commit e66ddba; tests 54 pass). Seeds 21 and 22 generated. None of the 5 meets the drop
  or cold-open depth. Seed 22 alone has the drop→slam shape (bar 27 −11 dB, slam at 28).
- **Task 8: complete** (commits 4fbe878..e66ddba). Music backed up.
  - **Ruling:** the section dynamics move to mix automation (a new addendum to Task 11). Gain and low-pass lanes are
    driven by the snapped sections in audio.json: muffled cold open, the ex sweeping open, instant open at her, a true
    drop-out for honest, a slam at proof, a fade at the end.
    - **Why:** music_v2_5 ignores per-section loudness even with an explicit palette/kit split and low adherence
      (2 rounds, 5 variants). Automation is deterministic, exact to the beat, and free.
    - **Cost if wrong:** the filter sweep may sound processed; the user judges it at C3.
  - **Ruling:** run T12 and T13 while C2 is pending, then T9→T10→T11(+automation)→T14→T15.
    - **Why:** T12/T13 don't depend on the chosen score; this keeps momentum.
    - **Cost if wrong:** none (no dependency is violated).
- **C2:** opened for the user (5 variants).
- **Task 12: complete** (commits e66ddba..43a2dde, spot-checked; 56 pass; 19 fonts)
- **C2: closed.** The user picked seed 11 (liked 11 and 12; "for now you can go with 11"). Set `chosen` =
  audio/music/score-seed11.wav and commit after T13 finishes, to avoid a git race.
  - **Ruling:** add Task 9b, "cut the score to picture". After Task 9 analyses seed 11, splice it on its bar grid so
    its own drop (source bars 28–31) moves out of the proof window. A bar map (decided from the measured grid) sends
    the loud re-entry bars (source 32–35) to the proof downbeat (output bar 28), with 10 ms equal-power crossfades at
    each splice. Mix automation (the Task 11 addendum) then makes the honest drop-out (output bars 26–27) silent.
    - **Why:** the seed's natural drop sits at 67.2–76.8 s, exactly where spec §5.2 wants the slam.
    - **Cost if wrong:** audible seams; the user judges at C3, and seed 12 remains the fallback.
- **Task 13:** implemented (commits 43a2dde..ad7107d); review dispatched against the vendor→fork diff.
  - Deviations: re-pinned bun.lock, the test quote style, three post members (the brief said four).
  - Minor (deferred): the preroll step stays 1/60 (it matters only for stateful scenes); stale "song/sung" comments.
- **C2 pick committed** (chosen = seed 11).
- **Task 13 review:** spec and named risks all verified (GLSL compiled in real Chrome, 19/19 fonts, lock hashes equal
  the vendor's).
  - 2 Important open: (1) the engine.ts:323 preroll step 1/60 → 1/FPS; (2) the post.ts:134 orange halation tint
    vec3(1.0,0.18,0.04) → palette blood, plus the post.ts:22 comment.
  - Fix round 1 is queued until T9 commits, to avoid a git race.
  - Minor (deferred): the preview passes dt=1/FPS on rAF ticks (a stateful scene would run ~2× fast in the 60 Hz
    preview); decide before the first stateful scene.
  - Minor (deferred), **Plan 2 look-dev must tune bloom**: with threshold 0.85 and knee 0.5, bone blooms most (weights
    bone 0.146, blood 0.033, moss 0.006). "Only blood/moss bloom" needs deliberate settings.
  - Minor (deferred): render.ts hard-codes 30 on 5 lines; vo.ts `syl` is unused and scenes/acts/duration aren't
    validated; stale "song/sung" comments.
- **Task 9:** implemented (commits f2585ed..d30c1ac).
  - 99.992 BPM, fit 0.95, error 1.9 ms, first downbeat 0.005 s; sections within 12 ms of the plan.
  - 3 deviations (librosa 1.0.0): lag compensation, `active` = sound within a beat, median pairwise-slope fit.
  - Review dispatched. Task 13 fix round 1 dispatched in parallel (app/ only; the review is read-only).
- **Task 13: fix round 1/5** (2 addressed, 0 open; commits ad7107d..05b8ec9). The fix diff was verified by the
  controller (3 lines), per the user's lighter-review direction.
- **Task 13: complete** (commits 43a2dde..05b8ec9). Note for Plan 2: the blood halation is ~61% as bright as the old
  orange at 0.25, so retune it in look-dev.
- **Ruling:** Task 9b bar map = `0-27,32-35,24-27,36-38`.
  - out 0–27 = src 0–27 (honest bars 26–27 are muted by automation)
  - out 28–31 = src 32–35 (the loud re-entry after the source's own drop → the proof slam)
  - out 32–35 = src 24–27 (the pre-drop groove)
  - out 36–38 = src 36–38 (the source's own fading ending)
  - **Why:** RMS shows seed 11's drop in src bars 28–31, exactly the proof window.
  - **Cost if wrong:** audible seams at out 28/32/36; the user hears it at C3.
- **Task 9b: complete** (commits 05b8ec9..debef18, spot-checked). Deviation accepted: `bar_edges` gets a 50 ms end
  tolerance for the 13 ms-short last bar (no audio change).
  - **Ruling:** switch to the implementer's alternative map `0-25,30-35,24-27,36-38`, re-run by the controller
    (tool invocation only).
    - **Why:** the honest bars become the source's own drop (−24 dB), and out 27→28 = src 31→32 is the composer's own
      re-entry, so the proof slam has no splice. The only splice sits at honest's start, where automation fades
      anyway.
    - **Result:** bars 22–25 at 0 dB, 26–27 at −24, 28–35 at 0, 36–37 fading. Fit 0.97. Audio backed up.
    - **Cost if wrong:** one re-run.
- **Task 10: complete** (commits cd9078f..139e753, spot-checked; 78 pass; 14/32 lines nudged; 93.60 s; 15 cuts on beats)
- **Task 11:** implemented (commits 139e753..d8002ad). −13.8 LUFS, −1.5 dBTP. BUT ffmpeg loudnorm fell back to
  dynamic mode (the peak/loudness ratio 15.2 dB > the 12.5 dB allowance), halving the drawn arc.
  - **Ruling:** fix round 1 = a static gain plus alimiter at −2 dBFS, iterated to within 0.2 LU of −14; scipy
    declared; RULES honest −60 → −12 dB (a dip into the score's natural −24 dB drop). A new test pins that the
    mastering keeps a 12 dB arc.
    - **Why:** the arc is the spec's §5.2 intent, and the implementer proved the approach in scratch (−14.3/−1.9).
      Honest: "one soft pad breath at most" beats a digital mute that reads as a dropout.
    - **Cost if wrong:** a limiter-coloured master (unlikely at a ~1–3 dB reduction). Honest can go back to −60 at C3.
- **Task 9: complete** (commits f2585ed..d30c1ac, review Approved; 3 deviations upheld on their merits).
  - Minor (deferred), **watch on any re-analysis**: phase wrap in `fit_grid` (`% period` can drop beat 0 if the fitted
    phase is slightly negative). Current first downbeat is +8 ms, OK. Guard: assert `downbeats[0] < 0.05`, or the
    two-line fix.
  - Minor (deferred): the labeller seed limits runs to ~2.2 min (fix:
    `np.median(beats[8:] - beats[:-8]) / 8`); irrelevant at 93.6 s.
  - Minor (deferred): report framing; a test comment about "two stray beats".
- **Task 11: fix round 1/5** (3 addressed, 0 open; commits d8002ad..1f17476). −14.1 LUFS, −1.9 dBTP; the arc
  survives (cold −6.2, ex −7.9 dB vs tour).
  - **Ruling:** accept the deviation `latency=1` on alimiter.
    - **Why:** without it the mix sits 239 samples (5 ms) late against the picture; a click-alignment test pins it.
    - **Cost if wrong:** none.
- **Task 11: complete** (commits 139e753..1f17476). Controller-verified the mastering code (the user's lighter-review
  direction); the implementer's alignment/loudness tests cover sync. Mix backed up.
  - Minor (deferred), **for C3 listening**: the limiter takes up to 3.3 dB at ~6 spots (21.7, 39.1, 48.1, 75.4, 79.3,
    86.4 s); check the honest pad breath by ear.
- **Task 14:** implemented (commits 1f17476..a0cd2a9). Controller viewed f_0059.19.png: on-brand, crisp, correct
  karaoke state.
  - Accepted visual fixes: bloom/halation 0 on the card (bone must not glow); the watermark alpha on ink; the braid
    collision; the title-safe margin; ✔ dropped from the mono text (no glyph).
  - **Ruling:** fix round 1 holds the highlight on the current word until min(next start, end + 0.6 s).
    - **Why:** the red highlight dropped for 1–2 frames between close words (100 frames in the film), which would read
      as flicker at C3.
    - **Cost if wrong:** none.
  - Minor (deferred), **for Plan 2**: transparent Canvas layers blend in linear light (low alphas render brighter);
    the global bloom defaults are untuned; the connect scene must draw its own ✔ in moss.
- **Task 14: fix round 1/5** (1 addressed, 0 open; commits a0cd2a9..a9a87fe).
- **Task 14: complete** (commits 1f17476..a9a87fe; checked by stills). Flicker frames 480 → 0; double highlights
  11 → 0; releases only in the 12 pauses ≥ 0.6 s.
- **Task 15: complete** (commits a9a87fe..10c1672). Animatic out/animatic.mp4: 93.6 s, 1080p30, 2,808 frames,
  374 s render; 14 clean cuts on the contact sheet.
  - film-sync flags 3 act cuts on beats, not downbeats: her 16.208 (−600 ms), loom 28.208 (−600 ms), connect 73.208
    (−1200 ms).
  - **Ruling:** accept them for now (C3 judges).
    - **Why:** no downbeat fits their windows; forcing downbeats needs about +2.4 s of VO shifts, pushing the film past
      95 s (40 bars). Every cut is still on a beat. The music's section changes (automation) are keyed to downbeats
      independently: her's filter reveal lands on "me" of "Not me", the spec's intent, and loom/connect have no
      musical change at their cut.
    - **Cost if wrong:** re-place 3 lines at C3.
  - Minor (deferred): the sync tests don't cover the "words inside their line" rule (a candidate test is in the
    report).
- **C3:** opened for the user.
- **C3: APPROVED by the user.** Pacing OK, the honesty drop feels intentional, the proof slam hits, the ending lands.
  - Q5 (processed-sounding music) was unclear to the user; I explained it. Treated as a pass unless they flag
    something later.
  - The 3 accepted act cuts on beats stand.
  - Plan 1 is functionally complete, pending the final whole-branch review.
- **User direction for Plan 2 (2026-09-30):** "use crazy, sexy, kick ass, motion graphics in plan 2. the visuals must
  look premium."
  - Plan 2 must raise the motion energy (3D kinetic type slams on beats, whips/speed ramps, match-cuts through the
    thread, macro Blender with volumetric light and DoF) while staying premium (palette and type discipline, no
    cheap FX).
  - Plan 2 starts with a look test (3 hero frames + a motion test) before all 15.
- **Final review (Opus): Needs fixes.**
  - I1: word sync fails on line-initial words; the aligner's error varies 0–140 ms, so a constant lead is wrong.
  - I2: the vocal fields in audio.json predate the snap.
  - I3: section starts trail the cuts by 0.6–1.2 s.
  - I4: a film-music re-run corrupts state.
  - Plus 8 minors.
  - **Ruling:** one fix wave (final-fix-brief.md). I1 is solved by acoustic, voicing-aware onsets stored per word
    (word_lead removed) plus an audio-measured sync check. I2 re-runs the chain. I3 becomes an informational film-sync
    table plus floor for future scores; the user approved the current honest/proof offsets at C3. I4 merges
    music_plan.json, reuses seeds only on a plan match, has splice refuse -edit sources and store the source grid,
    and backfills chosen_plan. M1 automate rule assert; M2 no-redirect opener; M3 README; M4 sync waivers for the
    3 ruled act cuts; M5 envelopes from the automated music; M6 fit_grid wrap guard.
    - **Cost if wrong:** one re-run of the chain.
  - Fix dispatched on Opus.
- **Final fix wave:** DONE (commits 10c1672..16f35bf; 128 tests). film-sync OK: 75 words lit +0 to +32 ms after the
  measured onset; the 3 act cuts are waived. Animatic re-rendered.
  - **Ruling:** the 4 cuts that moved by a beat (her 15.608, cite 42.608, proof 66.608, connect 72.608) stand.
    - **Why:** "Not"@16.21 on a beat → "me" → the her reveal on the 16.808 downbeat (pickup → downbeat). The honest
      drop still lands on "don't know"; the proof slam still hits inside "Forty-four…", now 0.6 s after the cut, not
      1.2. Same relationships as approved at C3, only tighter.
    - **Cost if wrong:** the user flags it on a re-watch.
  - **Ruling:** the fricative/plosive onset refinement becomes Plan 2 Task 1 (no second final-fix wave, per the
    skill).
    - **Rule:** the onset = the start of the contiguous run (≥ −35 dB, gaps ≤ 15 ms) ending in the voiced run, so a
      breath separated by a gap is excluded.
    - **Why:** 11 words light 30–100 ms after their consonant becomes audible ("Skills" 155 ms); Plan 2's kinetic type
      consumes vo.json.
    - **Cost if wrong:** one chain re-run.
  - Accepted: the splice joins sit 2–4 ms early (inaudible; source_downbeats now stores the true grid).
- **Scoped re-review of the fix wave:** all findings addressed (0 open). New items:
  - N1 (consonant onsets; confirmed, with numbers: "Skills" +155 ms, a stop-closure gap).
  - N2 (latent: a film-music merge overwrites the meta that beats reads).
  - N3 (cut moves plus the M5 envelope change; an optional user re-watch).
  - Minors: the test_sync assertion, waivers matched by scene only, stale waiver reasons, vo.wav missing.
  - **Ruling:** N1, N2 and the minors are folded into Plan 2 Task 1:
    - bridge one stop-closure gap ≤ 90 ms after a ≥ −25 dB fricative;
    - an unwaivable any-sound check (≤ 40 ms) on line-initial words;
    - "act cut not on a beat" is unwaivable;
    - `chosen_meta` guard;
    - fix the sync test and the waiver texts.
    - **Why:** the skill allows no second final-fix wave; Plan 2 Task 1 runs before any scene reads word times.
    - **Cost if wrong:** the words stay late until Plan 2 Task 1.
  - N3: the user is told an optional re-watch of her/proof exists; the timing relationships are unchanged in kind.
- **Final review: complete; Plan 1 is ready to merge.**
