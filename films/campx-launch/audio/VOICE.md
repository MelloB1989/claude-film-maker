# CampX launch film: voice, score, effects and mix

## The voice: Varsha (ElevenLabs shared library)
- **Varsha - Warm and Clear**, `kL06KYMvPY56NluIQ72m`. Indian English, female, middle-aged, use case narrative. Its
  description: "warm and clear tone, neutral accent with precise pronunciation, ideal for audiobooks, podcasts,
  corporate videos and educational content". About 28k clones, 46M characters in the last year; verified for
  `eleven_multilingual_v2` with an Indian accent.
- Model `eleven_multilingual_v2`, speed 1.0, stability 0.45, similarity 0.75, style 0.1, speaker boost on
  (film.json `pipeline.voice`).

### How it was chosen
I could not listen to the takes, so the choice rests on the library metadata plus measurements of the takes. I searched
`/v1/shared-voices` (female, accent indian, language en/hi, use case narrative_story, plus a text search for "indian
narrator") and the account's own `/v1/voices`, which has no Indian narrator. I shortlisted four voices by description
and usage, then generated line 1 with each one (same settings):

| voice | line 1 | words/s | pitch range | brightness (centroid) | pauses | notes |
|---|---|---|---|---|---|---|
| Tripti - Luxury TVC & Brand Films | 5.99 s | 1.78 | 15.0 st | 3.4 kHz | at the comma and the full stop | Its brief fits ("product launch films, restraint"), but it is slow: line 7 took 18.2 s at speed 1.1 and does not fit its 16 s window. It also paused inside phrases ("But / the final word") |
| **Varsha - Warm and Clear** | 4.92 s | 2.17 | 12.2 st | **2.2 kHz** (warmest) | at the comma and the full stop | Line 7 took 14.4 s at speed 1.0 (fits with room), with pauses only at sentence ends and list commas |
| Riya Rao - Confident and Clear | 4.50 s | 2.39 | 10.7 st | 3.7 kHz | at the full stop only | Brighter; less warm |
| Ziina - Confident and Clear | 4.18 s | 2.61 | 7.4 st | 4.4 kHz | short | Narrow pitch range (flat, corporate) and the brightest; reads rushed |

I picked Varsha for three reasons: she is the warmest-sounding of the four (lowest spectral centroid), she paces
naturally at about 2.2-2.4 words/s, and she phrases in whole sentences. Tripti read the most cinematically, but she
was too slow for the fixed scene windows.

### Pronunciation ("CampX" = camp-ex, "Medha" = MAY-dhaa)
The script keeps the brief's spellings; no respelling was needed in the TTS text. I checked this with a proxy, since I
cannot listen. In every take, "CampX" carries **two** syllable nuclei (vowel-band energy peaks) and lasts about 0.42 s.
A control take with the spelling "Camp Ex" gives the same 1+1 nuclei. "Campks" would carry one. "Medha" carries two
nuclei in every take, and its length matches a control take spelled "Maydha". This is **not proof**, so please listen to
L03 and L09 ("CampX") and L03, L05, L06 and L07 ("Medha"). If "Medha" comes out as "MED-ha", regenerate those lines with
"Maydha" in the TTS text. The tools send `text` as is, so that needs a separate spoken-text field, which they do not
have yet.

## Takes (audio/vo/selects.json)
I generated 3 takes per line, then force-aligned and paced them (factor 1.0, no time-stretch). I picked takes by
words/s (target 2.3-2.6), pauses at sentence and list boundaries only, a falling pitch at the end of each statement
(no upspeak), and a median pitch consistent from line to line.

| line | take | why |
|---|---|---|
| L01 | 3 | 2.2 w/s, clear comma and sentence pauses, falling end |
| L02 | 4 = take 3 with the pause after "page," lengthened 0.20 → 0.42 s | take 3 was the slowest read; the longer pause gives "a student's future" its weight |
| L03 | 4 = take 2 with the pause after "Evaluation." lengthened 0.26 → 0.55 s | a beat between the product name and "Powered by Medha AI" |
| L04 | 1 | 2.32 w/s and the tightest of the clean reads (it has to finish before 35 s); take 2 hitched after "Upload" |
| L05 | 1 | 2.44 w/s, unhurried |
| L06 | 2 | take 1 ran too fast (3.1 w/s); take 3 was choppy |
| L07 | 3 | 2.37 w/s, sentence pauses of 0.5-0.9 s; take 2 broke up inside phrases |
| L08 | 4 = take 3 with both sentence pauses lengthened to 0.5 s | a tagline read, three statements; take 2 rose at the end |
| L09 | 4 = take 1 with the pause after "smarter." lengthened 0.24 → 0.42 s | "CampX. / Evaluate smarter. / Decide faster." |

The derived takes (number 4) were made by `audio/scripts/breathe.py`. It inserts digital silence at the quietest point
of the gap, with 4 ms fades, and shifts the later word times. Each JSON records `derived_from` and `edit`.

## Placement (data/edit.json → data/vo.json)
Every line starts on a beat 0.5 s after its scene's cut (L01 at 2.0 s and L02 at 10.0 s, to give the opening room).
data/edit.json's per-line `gap_before` values are computed from the paced take lengths so the first word lands
exactly there; film-snap then moved each line by 3 ms or less. Lines 4-6 carry `"until"` in data/script.json (see
below).

| line | scene (window) | first word → last word | margin after cut / before window end | words/s |
|---|---|---|---|---|
| L01 | open 0-9 | 2.00 → 6.59 | 2.00 / 2.41 | 2.18 |
| L02 | stakes 9-15 | 10.00 → 12.70 | 1.00 / 2.30 | 2.59 |
| L03 | title 15-21 | 15.50 → 19.57 | 0.50 / 1.43 | 1.96 |
| L04 | ingest3d → ingestui 21-35 | 21.50 → 34.03 | 0.50 / 0.97 | 2.31 |
| L05 | read3d → readui 35-49 | 35.50 → 44.97 | 0.50 / 4.03 | 2.43 |
| L06 | mark3d → markui 49-62 | 49.50 → 56.41 | 0.50 / 5.59 | 2.75 |
| L07 | control 62-78 | 62.50 → 76.03 | 0.50 / 1.97 | 2.37 |
| L08 | outcome 78-85 | 78.50 → 82.00 | 0.50 / 3.00 | 1.72 |
| L09 | end 85-90 | 85.51 → 88.58 | 0.51 / 1.42 | 1.63 |

## Score (audio/music, data/music_plan.json)
- ElevenLabs `music_v2_5`, 120 BPM in 4/4 (2 s bars), so every cut at a whole second sits on a beat. Nine sections
  follow the arc in film.json `pipeline.music.sections`, with a gain arc drawn in the mix: intro (drone and felt
  piano), stakes (piano motif), title (lift), ingest / read / mark (a pulsing arpeggio that builds), control
  (warmest), outcome (the peak), end (resolve and tail). The first request was refused as "copyrighted material"
  because the styles named a composer and a brand; I removed both names.
- Variants: seeds 11, 12 and 13. Seeds 11 and 12 fade out from about 72-76 s, so the outcome peak and the end are
  missing (outcome at -47 and -41 dB RMS). **Seed 13** holds its level through the outcome (-23.6 dB) and resolves at
  84 s with a decaying tail. It is the pick.
- Alignment: the score's tracked grid is 119.99 BPM (grid error 3.7 ms), but its downbeats sat 0.263 s late. I made
  `score-seed13-aligned.wav` (`audio/scripts/align_score.py`: trim 0.263 s from the head, pad the tail; its sidecar
  records this), so beats land on whole and half seconds. That file is `chosen` in data/music_plan.json.
- film-beats warns "grid fit 0.86, the tempo drifts". It does not drift: the grid error is 3.7 ms over 90 s. The fit
  is low because the intro, stakes and end are drumless, so few onsets land on beats there.
- The music changes 1 s before the odd-second cuts (sections open on bar lines). The score's own swell comes at 16 s
  (the title SFX impact is on the 15 s cut) and its resolve at 84 s (the logo impact is on the 85 s cut).

## Effects (data/sfx_palette.json, audio/sfx)
- A palette of 16 sounds × 2 variants, all generated (664 credits by the headers, 452 by the subscription): soft,
  whip and zoom whooshes; paper rustle and flutter; scanner hum (loop) and scan sweep; particle dissolve; digital
  ticks (6 slices); glass chime; UI click, soft confirm and alert pulse; title riser; title and logo impacts. Picks
  overridden by hand: `impact_title` variant 0 (deeper, longer body) and `alert_pulse` variant 1 (two pulses).
- The engine's cue sheet (`bun scripts/cues.ts`) would only give the two transition whooshes, because film.ts has no
  `sfx.cues` yet. So data/sfx.json is **hand-written** by `audio/scripts/handsheet.py`: 36 cues anchored to the
  timeline cuts and to voiceover word onsets in data/vo.json. Examples: dissolve on "removes", chimes on "key / point /
  point", click and confirm on "Accept", alert on "flagged", riser and impact on the title cut, impact on the logo cut.
  **Re-running cues.ts overwrites it.** Re-run `python3 audio/scripts/handsheet.py films/campx-launch` (from the repo
  root) instead, or add cue modules to film.ts.

## Mix (audio/mix)
film-vo-chain uses the default chain. film-mix: -14.0 LUFS, -1.9 dBTP, LRA 5.2, music ducked a median 8.0 dB under
the voice, effects ducked 3.3 dB. The limiter takes up to 6.8 dB, on 8.5% of the film: this is speech peaks (the voice's
peak-to-loudness ratio is about 20 dB). A firmer voice compressor (3:1 at -25 dB) made the peaks worse and set off the
sibilance check, so I reverted it. film-sync: **sync OK** (cuts on beats, every line inside its window, 86 words lit
0-33 ms after their spoken onsets).

## Re-running the chain
From `tools/`, with `FILM=campx-launch` and ffmpeg on PATH:
film-edit → film-snap → film-beats → film-vo-chain → `python3 ../films/campx-launch/audio/scripts/handsheet.py
../films/campx-launch` → film-sfx → film-mix → film-sync. Do not run film-vo again: every take exists and it skips
them. A new film-pace run keeps the derived take-4 files, because they live in `takes/`.

## Tool change
`tools/filmtools/sync.py` now accepts an optional `"until": "<scene>"` on a script line: the line may run on into
that later scene, and film-sync checks it ends by that scene's end. The brief has lines 4-6 spill from each 3d plate
into the UI scene after it, and without this film-sync could not pass. The change is additive, with a test in
`tools/tests/test_sync.py` and a sentence in `tools/README.md`.
