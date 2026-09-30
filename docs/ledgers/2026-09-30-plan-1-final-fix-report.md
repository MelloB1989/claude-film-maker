# Final fix wave report: Plan 1

**Status: DONE_WITH_CONCERNS.** All findings are addressed (I1–I4, M1–M6), test-first. The suite has 128 passing
tests (91 at the start). The full chain was re-run. `film-sync` passes: 75 words are measured on `vo.wav`, each lit
+0.0 to +32.0 ms after its spoken onset, with only the three ruled act cuts waived. The animatic was re-rendered. No
audio was regenerated through the API.

The concerns are listed at the end:
1. Aspirated plosives and fricatives resolve to their voicing.
2. Four cuts moved one beat after C3.
3. The approved splice was cut 2–4 ms off the raw seed's own grid.

**Branch:** `plan-1-foundation`, 10c1672 → 16f35bf. Each commit is staged by explicit path and ends with the trailer.

| SHA | subject |
|---|---|
| `a03639a` | Words light on their measured spoken onset, and the sync report checks it on the voice |
| `5b9b782` | A film-music re-run keeps the pick, its edit and its plan; splices only cut a raw seed on its own grid |
| `4b66843` | Waivers and a section table in the sync report; envelopes from the music as heard; no redirects with the key |
| `16f35bf` | Voiceover re-placed on measured onsets, re-snapped, re-analysed and re-mixed; score state backfilled |

WAVs stay uncommitted. `~/11labs` was never read. The audio backup was not touched.

---

## I1. Word sync is measured on the audio

### What changed

**`tools/gitloom_film/onsets.py` (new).** `voice_onsets(samples, sr, words, min_gap=0.06)` is at `onsets.py:56`, and
`frames()` at `:38` gives 5 ms frames: dB relative to the take's loudest frame, and zero crossings per sample.

- A word is measured only if it is line-initial or follows a gap of at least `min_gap`. Any other word gets None.
- The window runs from `max(prev_end, start - 0.20)` to `start + 0.08`.
- The onset is the first frame at or above −30 dB that begins a voiced run. A voiced run means the next 30 ms stay
  above −35 dB, and at least 4 of their 6 frames have a ZCR under `ZCR_MAX = 0.10` (`:33–34`).
- If nothing qualifies, the result is None.

Two guards were added to the brief's sketch. Each one is test-pinned and comes from the real takes:

- **The window never runs past the word's own end** (`:74`).
  - Case: L18 "why I believe". "I" (aligned 0.774–0.828) is spoken inside the voice of "why", and "believe" starts at
    0.850, which is within `start + 0.08`.
  - Without the cap, "I" took the onset of "believe" (0.850): 76 ms after its aligned start, and past its aligned end.
- **The voiced run must begin a sound that started inside the window** (`:84`). A sound is a stretch of frames at or
  above −30 dB.
  - Case: L13 "Rules I". The aligner ends "Rules" at 0.504, but its voice runs on to 0.545, including a 30 ms voiced
    blip after the /z/.
  - The literal rule put "I" at 0.510. Its real onset is 0.610, after a dip to −45 dB, so "I" would have lit 100 ms
    ahead of the voice.
  - Because the loop scans forward, the first qualifying frame of a sound that began in the window is by construction
    that sound's first voiced run.

**`pace.py:86`.** After trimming and stretching, `pace_take` stores `"onset"` on every word. The value is in seconds
into the paced take, or null.

**`edit.py:57`.** A word's start is `start + onset` when an onset was measured, and `start + w["start"]` otherwise.
- There is no `word_lead`. Starts stay monotonic, and none precedes the line start.
- `word_lead` is removed from `data/edit.json` and from the code. The docstring is updated.

**`sync.py`:**
- `lit()` (`:59`) mirrors the engine: frame n renders at `n * (1/30)`, and a word lights once `start <= t`.
- `word_sync()` (`:70`) measures every line-opening or post-gap word of `vo.json` on `vo.wav`.
  - Each line's slice is measured on its own, so levels are relative to that line's own peak, as in its take.
  - It requires `0 <= lit - onset <= 1/30 + 0.002` (`LATE`, `:27`).
  - `SLACK` = 0.1 ms (`:28`) covers the 0.1 ms rounding of vo.json times and the take's placement on the nearest
    sample.
  - A line whose first word has no measurable onset is a problem, so a stale or misplaced `vo.wav` can't pass by
    measuring nothing.
- `film-sync --words` lists every measured word.

**Tests:**
- `tests/test_onsets.py` (11 tests):
  - the tone within 5 ms;
  - a breath before the tone is ignored, both with a closure and running straight into the voice;
  - a plosive burst counts;
  - silence and room tone give None;
  - connected speech gives None;
  - a post-pause word is measured;
  - the previous word's tail is not an onset;
  - the search stops at the word's end;
  - a click is not an onset;
  - a swell-in is timed at −30 dB.
- `test_pace.py::test_pace_take_stores_each_words_measured_onset`.
- `test_edit.py` replaces the word_lead test with
  `test_a_measured_onset_places_the_word_and_an_unmeasured_word_keeps_its_aligned_start` and
  `test_word_starts_stay_in_order_and_never_precede_their_line`.
- `test_sync.py`: four `word_sync` tests, plus **the missing "words inside their line" test** (Task 15's candidate,
  verbatim).

### RED / GREEN

| test | RED | GREEN |
|---|---|---|
| test_onsets.py | `E ModuleNotFoundError: No module named 'gitloom_film.onsets'` (1 error) | 11 passed |
| test_pace.py | `KeyError` on `first["onset"]`, 1 failed / 7 passed | 8 passed |
| test_edit.py | `{'start': 1.11} != {'start': 1.03}` and `[1.04, 1.3, 1.5] == [1.0, 1.3, 1.3]`, 2 failed | 7 passed |
| test_sync.py | `ImportError: cannot import name 'word_sync'` | 9 passed |

**test_onsets.py, on the way to GREEN.** The first implementation used the plain median ZCR of the run. The
"breath running straight into the voice" test then failed with `assert (0.59 - 1e-09) <= 0.585`: a 3/3 split
(breath 0.126–0.134, tone 0.004–0.008) has a median of 0.067, so 15 ms of breath led the onset.
- I tightened the rule to "4 of 6 frames voiced". That allows up to 10 ms of burst or breath.
- In the same test, my first draft had put the breath's start before the window. The sound-began-in-window rule then
  (correctly) returned None, so I moved the breath inside the window.

**Mutation check.** Each rule was removed in turn from a scratch copy of `onsets.py`. Every mutant is killed by a
named test:

| rule removed | test(s) that fail |
|---|---|
| sound began inside the window | the previous word's tail; the search stops at the word's end |
| cap at the word's end | the search stops at the word's end |
| ZCR test | both breath tests |
| plain median instead of 4/6 | breath straight into the voice |
| `min_gap` | connected speech |
| 30 ms > −35 dB | breath with closure; the click |
| −30 dB onset level | the swell-in |

**test_sync.py.** The "words inside their line" test kills the mutant that Task 15 found surviving:
`FAILED ...::test_word_outside_its_line_is_reported` when the rule is removed.

**Real-data RED.** The new `film-sync` on the pre-fix data (10c1672 plus the new code) exited 1 with 45 word problems.
They match the review:
- L32 "I" lit 108 ms after its onset.
- L31 "I" 83 ms, L26 "One" 85, L29 "One" 89, L30 "GitLoom." 81.
- L23 "…I" 38 ms ahead of the voice, L22 "And" 23 ms ahead.

### ZCR threshold: 0.10 per 5 ms frame, and a run is voiced when 4 of its 6 frames are under it

Calibrated on all 106 paced takes (5 ms frames, dB relative to each take's loudest frame):

| population | n | p5 | p25 | p50 | p75 | p95 |
|---|---|---|---|---|---|---|
| in-word frames ≥ −30 dB (speech) | 24,100 | 0.008 | 0.013 | 0.025 | 0.050 | 0.331 |
| pause interior, −50…−25 dB, ≥150 ms from any word (breath-like: exhalation tails) | 663 | 0.071 | 0.105 | 0.126 | 0.151 | 0.200 |
| room tone < −55 dB | 4,406 | 0.142 | 0.281 | 0.368 | 0.418 | 0.452 |

The speech histogram is bimodal:
- **Voiced mode, 0–0.10.** Per 0.02 bin: 10281 / 6318 / 2626 / 964 / 405. That is 85.5% of in-word frames.
- **Valley, 0.10–0.20.** Per bin: 268 / 166 / 142 / 143 / 110.
- **Unvoiced mode, 0.20–0.44.** Fricatives and aspiration.

**Why 0.10:**
- It is the upper edge of the voiced mode.
- It sits under breath's p25 (0.105) and median (0.126). The takes have no separate inhalations; the breath-like
  sound is the breathy tail of words such as "you…" and "conversation…" (ZCR 0.10–0.20, −25 to −50 dB).

**Why "4 of 6" rather than the median:**
- A plain median passes a 3/3 split. The two middle values, voiced ~0.01 and breath ~0.13, average under 0.10.
- 4 of 6 caps any noise at the head of a run at 10 ms, which is the allowance that lets a plosive burst head the run.

**On the real takes:**
- 379 line-initial or post-gap words; 271 onsets; 108 None (acoustically connected speech, where the aligner's gap is
  fictional).
- Onset minus aligned start: median −53 ms, p10 −104, p90 +23, min −182, max +69.
  - The min, L03/3 "you…", is genuine: a clean dip to −45 dB before it.
  - The max, "Skills,", is voicing after /sk/.
- In the chosen takes: 83 onsets. The line-initial words match the review's measurements: L32 "I" −135 ms, L31 −129,
  L26 "One" −114, L29/L30 −106, L23 "…I" −10, L22 "And" −18.

### Re-pacing

- `film-pace`: "106 takes paced".
- All 106 paced WAVs are **byte-identical** to before (shasum).
- All 106 JSONs are unchanged apart from the new `onset` field.
- 271 of 535 words carry a measured onset.
- `selects.json` sets no per-line `factor`, so every take keeps ×0.90.

---

## I2. The vocal data in audio.json comes after the snap

The chain ran in the documented order: `film-pace → film-edit → film-snap → film-beats → film-mix → film-sync`.
- `data/audio.json`'s first vocal onset is now 0.935, which is L01 "Your" in the snapped vo.json (was 0.958).
- The beat grid, downbeats, sections, bpm, grid fit and grid error are identical to before.
- The loop is documented in the README (M3).

## I3. Section starts against cuts, and floor for future scores

**Table.** `sync.py:97` `section_table()`, printed by `film-sync` as information only. It never fails. The output is
under the film-sync section below.

**Floor.**
- `music_plan.py:35` now uses `math.floor(start / bar + 1e-9)`; the epsilon keeps a scene exactly on a bar line on
  that bar.
- The 2-bar minimum is kept. The docstring says sections start on the bar at or before their scene.
- The test is now `test_sections_are_whole_bars_starting_on_the_bar_at_or_before_their_scene`. It requires
  `0 <= scene - section < bar` for all six, and "the ex" at 4.8 s (6.2 s is 2.58 bars).
- RED: `assert 0 <= (6.2 - 7.2)`. GREEN: 4 passed.
- This affects future `film-music` runs only. The score was not regenerated.

## I4. Re-running film-music can't corrupt the score state

**`music.py:95` `merge_plan()`**, used by `main` (`:120`):
- keeps `chosen` and `edit`;
- appends new variants, de-duplicated and in order;
- overwrites `plan` and `meta` with the latest run;
- sets `chosen_plan` from `chosen_plan()` (`:87`). That function reads the sidecar of the chosen score's source: the
  splice's `edit.source`, else `chosen`.

**`generate_variants` (`:67`)** reuses `score-seed{N}.wav` only if its `.plan.json` holds the new plan's chunks
(`_made_from`, `:52`).
- Otherwise `variant_path` (`:57`) names the file `{label}-seed{seed}-{sha256(chunks)[:8]}.wav`.
- A WAV of unknown provenance, with no sidecar, is never reused.
- An existing WAV is never overwritten: `FileExistsError` if a hashed name somehow collides.

**`splice.py`:**
- `main` refuses a source ending in `-edit.wav` (`:104`, SystemExit naming `edit.source`).
- `source_grid()` (`:82`):
  - The first splice takes the grid from `audio.json` after checking that its duration matches the source's.
  - It stores `source_downbeats` and `source_beat_period` in `edit` (`:113`).
  - Later splices use the stored grid.
  - An edit without a stored grid is refused rather than re-cut on the edit's own analysis.
- I store `source_beat_period` too, so a re-cut's bar length doesn't depend on the current `audio.json` either.

**Tests:**
- `test_music.py`:
  - `test_a_changed_plan_gets_its_own_file_and_never_overwrites`;
  - `test_a_seed_file_of_unknown_plan_is_not_reused`;
  - `test_merge_keeps_the_pick_and_the_edit_and_adds_variants`;
  - `test_merge_into_nothing_starts_a_fresh_plan`.
- `test_splice.py`:
  - `test_splice_refuses_an_edit_as_its_source`;
  - `test_the_first_splice_stores_the_sources_downbeats`;
  - `test_a_later_splice_cuts_on_the_stored_downbeats_not_the_edits_analysis`;
  - `test_an_edit_without_stored_downbeats_is_not_recut_on_the_current_analysis`;
  - `test_the_first_splice_needs_the_analysis_of_its_source`.

**RED / GREEN:**
- **merge.** RED: `ImportError merge_plan`.
- **generate_variants** (after `merge_plan` existed). RED:
  - `assert (1 == 2)`: a changed plan reused the old seed's WAV.
  - `assert (0 == 1)`: a sidecar-less WAV was reused.
  - GREEN: 9 passed.
- **splice.** RED: 5 failed.
  - `FileNotFoundError`: the -edit source was not refused.
  - `edit` lacked `source_downbeats`.
  - `ValueError: bar 3 runs past the end of the file`: the re-cut ran on the edit's shifted grid.
  - `DID NOT RAISE` ×2.
  - GREEN: 14 passed.

**Backfill (data commit):**
- **`chosen_plan`** is seed 11's round-1 plan, from `audio/music/score-seed11.plan.json`. It is asserted equal to the
  sidecar's `plan`.
- **`edit.source_downbeats`** (39 downbeats, 0.005 … 91.213) and **`source_beat_period`** (0.60005) come from Task 9's
  committed analysis of the raw seed (`d30c1ac:data/audio.json`).
- **Variants 11, 12 and 13 are restored.** The earlier film-music re-run had dropped them: `variants` held only 21
  and 22, which is the corruption this finding describes.

**Finding, confirmed on disk.** The approved `score-seed11-edit.wav` was itself produced by exactly this bug. The
Task 9b controller re-cut ran on the first edit's analysis (`debef18`/`cd9078f`: downbeats 0.008 + 2.4k) rather than
the raw seed's own grid (0.005 + 2.4002k).
- Re-splicing the raw seed with the map on `debef18`'s downbeats reproduces the file sample for sample. On
  `d30c1ac`'s grid it gives a file 48 samples longer.
- The joins sit **2–4 ms before** the raw seed's own downbeats: source bars 24 −2.0, 26 −3.0, 28 −3.0, 30 −3.0,
  36 −4.0 ms, under 10 ms equal-power crossfades.
- I did **not** re-cut: C3 approved this audio. See concern 3.

---

## Minor fixes

**M1.** `automate.py:36`. `lanes` raises `ValueError` for a section with no rule; the docstring is updated.
- Test: `test_a_section_without_a_rule_is_an_error`. RED: `DID NOT RAISE ValueError`. GREEN: 5 passed.
- The beats fixtures' made-up section names "a"/"b" became "the tour" and "proof and everywhere", since `analyze` now
  runs `lanes`.

**M2.** `elevenlabs.py:41` `_NoRedirect`, whose `redirect_request` returns None. `_OPENER.open` is at `:55`. The
client now raises on any non-2xx: `not 200 <= r.status < 300` (`:114`). Two tests:
- `test_a_redirect_is_an_error_not_a_success`: a fake 302 raises `ElevenLabsError(302)`, with one call and no credit
  log.
- `test_the_transport_does_not_follow_redirects`: a real local server answers 302.
  - RED: `assert (501 == 302)`. urllib followed the redirect, re-sending the key header, and the target answered the
    converted GET with 501.
  - GREEN: status 302, and the server saw exactly one request, `("/v1/music", KEY)`.

**M3.** `README.md`:
- `film-realign` and `film-splice` are in the stage table.
- The table is reordered to edit → snap → beats → mix.
- The re-run order is stated after pacing or placement changes.
- It warns that `--music` must name the spliced `score-seed11-edit.wav`.
- It documents `data/sync_waivers.json`.

**M4.** `sync.py:106` `report()`. A waiver key `"cut <scene>"` matches problems starting with the key plus a space,
so "cut her" never matches "cut hero".
- Waived problems print as `waived: … (<ruling>)` and don't fail the gate.
- A waiver that matches nothing prints a `note:` (not a failure).
- `data/sync_waivers.json` is seeded with her, loom and connect, with the given reason.
- After the re-run the same three scenes, and only they, are the problem lines. Her and connect moved (below). The
  keys name scenes, not times, so the entries still match and were left as seeded.
- Tests: waived-but-others-fail, only-waived-passes, and stale waiver noted. RED: `ImportError` (report,
  section_table). GREEN: 13 passed.

**M5.** `beats.py:132`. `analyze(..., automate=True)` works in two stages:
- It fits the grid, downbeats and sections on the raw score as before.
- It then applies `apply(y, sr, *lanes(sections, …))` and takes rms/low/mid/high (`_envelopes`, `:96`), drums (onset
  strength) and the kick/snare/hat onsets from the automated music.
- The raw rms still decides `grid_fit`'s audible stretches.
- `film-beats --no-automation` (`:157`) pairs with `film-mix --no-automation`.

Test: `test_envelopes_follow_the_automated_mix_and_the_grid_follows_the_score`. RED:
`TypeError: analyze() got an unexpected keyword argument 'automate'`. GREEN: 10 passed. Its synthetic score has no dip:
- raw honest ≥ 0.8 × tour;
- heard honest < 0.3 × tour;
- the grid is identical.

"Near-zero" became "12 dB down" because honest is a −12 dB dip by the Task 11 ruling. On the real score, the honest
window's rms envelope is now **0.006** (was 0.022), because the score's own −24 dB drop adds to it. Cold open fell from
0.298 to 0.094, while the tour and proof are unchanged (0.306 and 0.303).

**M6.** `beats.py:26` `WRAP = 0.03`. At `:44`, if the fitted phase is within 30 ms of the period, the grid prepends
`phase - period`.
- Test: `test_fit_grid_keeps_beat_0_when_its_fitted_phase_wraps`. The true phase is +3 ms with jitter whose median is
  −4.5 ms, which makes the fit wrap.
  - RED: `assert 0.5984999999999996 == 0.003 ± 0.006`.
  - GREEN.
- `test_fit_grid_does_not_invent_a_beat_before_a_late_first_beat`: phase 0.5 s gets no extra beat.
- The real score's grid is unchanged (first beat 0.008).

---

## The re-run (I1 step 5)

```
film-pace   → 106 takes paced (WAVs byte-identical; JSONs + onset)
film-edit   → act I 0.00→16.00 · II →28.19 · III →72.97 · IV →86.37 · V →93.49 · duration 93.49s
film-snap   → 16/32 lines nudged onto beats · duration 93.60s
              thread 0.000 · ex 6.008 · her 15.608 · repo 22.808 · loom 28.208 · diff 37.808 · cite 42.608 ·
              braid 46.808 · merkle 53.408 · graph 57.008 · honest 61.208 · proof 66.608 · connect 72.608 ·
              anywhere 79.208 · weave 86.408 → 93.600
film-beats  → 100.0 BPM · grid fit 0.97 · grid error 2.7 ms · 156 beats · 39 downbeats (sections unchanged)
film-mix    → audio/mix/mix.wav · automated · -14.1 LUFS · -1.9 dBTP
```

`film-snap` now puts the **real** onsets on beats. Four cuts move by one beat as a direct result:

| cut | before | after | why |
|---|---|---|---|
| her | 16.208 | 15.608 | "Not" nudged −139 ms onto the 16.208 beat, so the cut must be ≤ 16.088 |
| cite | 43.208 | 42.608 | "Ask" onto 43.208 |
| proof | 66.008 | 66.608 | "Forty-four…" is now 192 ms from a beat and is not nudged |
| connect | 73.208 | 72.608 | "One" onto 73.208 |

The film is still 93.600 s.

### film-sync, in full (exit 0)

```
word sync: 75 words measured on vo.wav, each lit +0.0 to +32.0 ms after its spoken onset (allowed 0 to +35.3)
music sections against the cuts they open (information only):
  cold open              opens thread   at   0.000s   cut   0.000s   section − cut     +0 ms
  the ex                 opens ex       at   7.208s   cut   6.008s   section − cut  +1200 ms
  her                    opens her      at  16.808s   cut  15.608s   section − cut  +1200 ms
  the tour               opens loom     at  28.808s   cut  28.208s   section − cut   +600 ms
  honest                 opens honest   at  62.408s   cut  61.208s   section − cut  +1200 ms
  proof and everywhere   opens proof    at  67.208s   cut  66.608s   section − cut   +600 ms
  weave                  opens weave    at  86.408s   cut  86.408s   section − cut     +0 ms
waived: cut her at 15.608s is 1200 ms off the downbeat (act cut on a beat: no downbeat fits between the previous scene's last word and 0.12 s before the first word; ruled at Task 15, C3-approved)
waived: cut loom at 28.208s is 600 ms off the downbeat (act cut on a beat: no downbeat fits between the previous scene's last word and 0.12 s before the first word; ruled at Task 15, C3-approved)
waived: cut connect at 72.608s is 600 ms off the downbeat (act cut on a beat: no downbeat fits between the previous scene's last word and 0.12 s before the first word; ruled at Task 15, C3-approved)
sync OK (3 waived)
```

**Cross-check.** The chosen takes carry 81 measured onsets (L18b is optional and excluded). All 81 were re-measured
on `vo.wav` with their takes' own windows: each is lit +0.0 to +32.0 ms after its onset. `film-sync`'s gap rule skips
6 of them, because their onset lies under 60 ms after the previous word's aligned end:

| line | word | lit after onset |
|---|---|---|
| L04 | "overwrites" | +2.0 ms |
| L17 | "always" | +4.3 ms |
| L18 | "me" | +15.3 ms |
| L19 | "ask…" | +13.7 ms |
| L19 | "answer." | +7.0 ms |
| L27 | second "any" | +26.8 ms |

### Per-word sync errors, L22, L23, L26–L32 (lit − spoken onset, measured on vo.wav)

| line | word | onset (s) | first lit frame (s) | error |
|---|---|---|---|---|
| L22 | And | 61.808 | 61.833 | +25.3 ms |
| L23 | …I | 64.538 | 64.567 | +28.7 ms |
| L26 | One | 73.208 | 73.233 | +25.3 ms |
| L26 | command… | 73.578 | 73.600 | +22.0 ms |
| L26 | and | 74.628 | 74.633 | +5.3 ms |
| L26 | Claude | 75.223 | 75.233 | +10.3 ms |
| L26 | Code. | 75.588 | 75.600 | +12.0 ms |
| L27 | Or | 76.626 | 76.633 | +6.8 ms |
| L27 | any | 76.906 | 76.933 | +26.8 ms |
| L27 | in | 77.972 | 78.000 | +28.5 ms |
| L27 | any (2nd) | 78.207 | 78.233 | +26.8 ms (cross-check; see above) |
| L28 | On | 79.808 | 79.833 | +25.3 ms |
| L28 | or | 81.203 | 81.233 | +30.3 ms |
| L28 | in | 81.783 | 81.800 | +17.0 ms |
| L28 | cloud. | 82.198 | 82.200 | +2.0 ms |
| L29 | One | 83.078 | 83.100 | +22.0 ms |
| L29 | every | 84.228 | 84.233 | +5.3 ms |
| L30 | GitLoom. | 86.719 | 86.733 | +13.8 ms |
| L31 | I | 88.208 | 88.233 | +25.3 ms |
| L32 | I | 90.258 | 90.267 | +8.2 ms |

Before the fix, the same check gave L32 +108, L31 +83, L30 +81, L29 "One" +89, L26 "One" +85, L23 −38 (ahead) and
L22 −23 (ahead).

**Why +25.3 ms recurs.** A word snapped onto a beat lights on the next frame: the beat grid (0.008 + 0.6k) is offset
from the frame grid by 8 ms.

**Unmeasured words.** Words inside connected speech (for example L22 "when", "I"; L23 "say", "so."; L26 "I'm"; L27
"agent,", "language.") have no acoustic boundary, so they keep their aligned starts.

---

## Animatic re-render

`cd app && ~/.bun/bin/bun scripts/render.ts video --samples 1 --out ../out/animatic.mp4` exited 0. Its final lines:

```
2808/2808 frames  10.8 fps  eta 0s
wrote /Users/0mellob/Developer/code/gitloom-film/out/animatic.mp4 (2808 frames in 370.1s)
sub-frames per frame (count:frames): 1:2808
BROWSER LOG:
[error] Failed to load resource: the server responded with a status of 404 (Not Found)
```

- The 404 is Chrome's `/favicon.ico` probe, the same line Task 15 traced. There is no `SCENE ERRORS` block.
- `ffprobe`: `h264 1920x1080 30/1`, `aac`, `duration=93.600000`, 475 MB.
- **The cuts are in the picture.** I decoded all 2808 frames at 240×136. The 14 largest frame-to-frame jumps fall
  exactly on the new cut frames, `ceil(30 × start)`: 181, **469** (her 15.608), 685, 847, 1135, **1279** (cite),
  1405, 1603, 1711, 1837, **1999** (proof), **2179** (connect), 2377, 2593.
- Jump size is 2.71–4.87 at the cuts, against at most 0.59 elsewhere (median 0.21).

---

## Concerns

1. **Aspirated plosives and fricatives light at their voicing, not at the burst.**
   - "Plosive bursts count" holds for a burst of up to 10 ms that runs straight into voicing. The same 10 ms
     allowance is what keeps a breath out.
   - After an aspirated burst, an affricate or a fricative, the next 30 ms are noise at breath-like or higher ZCR. The
     run then starts at the voicing, per the ruling's own definition.
   - Eleven words in the film have an audible unvoiced head of 30 ms or more before their measured onset (unvoiced
     head in ms, peak dB relative to the take's loudest frame):

     | line | word | head | peak |
     |---|---|---|---|
     | L02 | "to" | 45 ms | −12 dB |
     | L04 | "tells" | 90 ms | −12 dB |
     | L05 | "Commitment" | 45 ms | −17 dB |
     | L11 | "keep." | 85 ms | −18 dB |
     | L15 | "Change" | 100 ms | −10 dB |
     | L24 | "to" | 50 ms | −14 dB |
     | L26 | "command…" | 30 ms | −22 dB |
     | L26 | "Claude" | 35 ms | −25 dB |
     | L20 | "Fifty" (/f/) | 35 ms | −24 dB |
     | L25 | "for" (/f/) | 75 ms | −20 dB |
     | L04 | "and" (breathy onset) | 30 ms | −19 dB |

   - L14 "Skills," is separate: its /s/ is a sound of its own, 155 ms before the voiced /k/-release onset.
   - These words light up to that much after the consonant becomes audible. They are never ahead of the voice, and
     `film-sync` passes because it uses the same definition.
   - Counting those heads would be a small change: take the onset at the start of a contiguous loud unvoiced head.
     But it would also count fricatives and L04's breathy "and", so it needs a ruling.
2. **Picture timing moved after C3.**
   - Four cuts moved one beat: her, cite, proof and connect (table above). `film-snap` nudged 16 lines onto beats, by
     up to 148 ms (its limit is 150 ms). First-word times changed by up to 222 ms, onset correction included: L31
     "I", 88.430 → 88.208.
   - Her is now 1200 ms before its downbeat (was 600) and stays under its waiver. Connect is now 600 ms (was 1200).
   - Honest's offset is unchanged (+1200). Proof's is now +600 (was +1200): the slam lands 408 ms into "Forty-four…"
     (was 600 ms).
   - The user approved the old timing at C3, so her and proof deserve a re-watch.
3. **The approved splice was cut on the wrong grid, 2–4 ms off the raw seed's own downbeats.** This is the I4 bug,
   which had already happened at the Task 9b re-cut.
   - It was left as is (approved audio).
   - Because `edit.source_downbeats` now holds the raw seed's true grid, a future re-cut with the same map would not
     be bit-identical to the approved file: joins would move 2–4 ms, and the file would be 1 ms longer.
4. **`film-sync` re-measures 75 of the 81 measured words.** It uses vo.json's times with the brief's gap rule; the
   other 6 were verified by the cross-check above.
