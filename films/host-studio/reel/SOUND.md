# karma reel — score and sound (task R5)

The reel's sound: an ElevenLabs Music score conformed to the picture's grid, a frame-aligned effects palette and
cue sheet, and the mix with the presenters' voices (R4), mastered to −14 LUFS / −1 dBTP. Everything is made by code:
the prompts, seeds, layers, cues and levels are in [`score.py`](score.py), [`sfx.py`](sfx.py) and [`mix.py`](mix.py).

| File | What |
|---|---|
| `audio/mix/mix.wav` | **the mix**: 48 kHz stereo 24-bit, 3 120 000 samples (65.000 s from frame 0), −14.1 LUFS, −1.7 dBTP, LRA 5.7 LU. R6: `cut.py FRAMES --mix audio/mix/mix.wav` |
| `audio/mix/mix_45.wav` | **the 45 s cut** (PLAN §7 item 4, R6's edit list in [`mix45.py`](mix45.py)): 2 160 000 samples, −14.1 LUFS, −1.7 dBTP, LRA 5.9 LU; the score plays bar 12's riser and breath under S08 so the cut to S11 lands on the drop; `mix_45.json` has the lines' frames in the cut |
| `audio/score/score.wav` | the score alone, conformed and arranged, same length (peak −1 dBTP, not loudness-normalised) |
| `audio/sfx/beds.wav`, `fx.wav` | the effects' two stems (beds: room, outside, hum, crackle; fx: the one-shots), same length |
| `audio/sfx/cues.json` | the cue sheet as data: every one-shot's frame, sound, gain, pan, shot |
| `audio/score/takes/` | the three paid takes as composed (FLAC + their plan, request id, cost) and their analyses |
| `audio/score/check.png`, `audio/mix/mix.png` | spectrogram/bar grid/section spectra of the score; stem levels and short-term loudness of the mix |

Rebuild (from `tools/`, with numpy, scipy, soundfile, librosa, matplotlib; ffmpeg only for `filmtools.mix.measure`):

    python ../films/host-studio/reel/score.py conform --take v2-seed1   # the picked take -> score.wav (no credits)
    python ../films/host-studio/reel/sfx.py render                      # the cue sheet -> beds.wav, fx.wav
    python ../films/host-studio/reel/mix.py --vo-dir <R4's vo dir>      # vo_him.wav + vo_her.wav -> mix.wav
    python ../films/host-studio/reel/mix45.py --vo-dir <R4's vo dir>    # the same stems on the 45 s cut -> mix_45.wav

`score.py gen` and `sfx.py gen` are the only steps that spend credits (`fleetctl secret exec
ELEVENLABS_API_KEY=elevenlabs -- …`); both are cached and refuse to overwrite a take made from another plan.

## The score

Plan v2 (`score.py`, `V2`): ten chunks in whole bars, 96 BPM / 4/4 / D minor named in every chunk, downtempo
organic house with a lo-fi warmth (felt piano, Rhodes, tape pads, brushed kick, shakers, round sub, a tanpura drone
under the drop), no vocals. Three takes were composed (446 credits each; 1 338 in all):

| Take | Tempo | Verdict |
|---|---|---|
| v1-seed1 | 96.08 bpm | sections on their bars, but no kick or bass before bar 9 and the drop no bigger than the build |
| **v2-seed1** (picked) | 96.04 bpm, grid error 7 ms | groove from bar 9, the drop on 30.0 s, a drumless breakdown on bars 15–16 that lands on his silhouette and key-light reveal; ends on its B♭ groove |
| v2-seed2 | — | drums only from bar 21: unusable |

The model would not place a kick before bar 9 in any take, nor end on a ringing chord, so the conform does what the
plan asks with edits on the grid (`LAYERS`, `EDITS` in `score.py`):

- **Conform:** one varispeed of the whole take, 96.041 → 96.000 bpm (−0.7 cents), anchored on the drop: no splices
  were needed (the code splices section by section with equal-gain seams if a take drifts by more than 0.1%).
- **Bars 5–8:** a synthesised soft felt-beater kick on every beat and a brush on 2 and 4; a D2 sub on bars 7–8,
  ducked by the kick. Levels set against the drop's own low end (kick −11 dB, sub −13 dB).
- **Bars 9–12:** the take's groove arrives low-passed (320 Hz → 6.5 kHz, exponential) and 5 dB down, opening as it
  goes, with a noise riser over bars 11–12, so bar 13 is the first time the groove plays full-range.
- **The breath:** bar 12 beat 4 (f705–719) drops out (a 90 ms tail), and the drop opens hard on 30.000 s.
- **The last chord:** at bar 25 the groove's downbeat plays and the groove leaves over a beat; the take's own
  opening D-minor chord (bars 1–2) rings out over the title with a D2 sub tail: the B♭ groove resolves to it (VI → i)
  and the reel ends on the chord it began with. The fade to black is f1536–1559.

### Checks (`score.json`, `check.png`)

- Length 3 120 000 samples. Tempo after the conform: exactly 96 bpm by construction (one ratio); librosa's tracker
  reads 96.04 bpm with a 7 ms offset over the whole score (its own noise: the drumless bars pull it).
- **Beat alignment, per section** (kick onsets 20–150 Hz against the exact grid; median, signed): the synthesised
  kicks of bars 5–8 read −1.5 to −1.8 ms (the measure's own bias), the take's groove −1.5 to +7 ms in every section
  (bars 9–12 −1.3, 13–14 +1.8, 19–20 −1.5, 21–22 +5.2, 23–24 +7.0); no drift across the minute. A frame is 41.7 ms.
- **The drop:** the low band's onset measures 30.015 s (30.000 asked; 15 ms, the detector's 5 ms frames and the
  sub's rise time).
- **Spectra by section** (`check.png`): Morning sits 0.15–1 kHz with nothing under 100 Hz; bars 5–8 add the kick and
  sub at 45–75 Hz; the build's top end stays dark until the drop; Ignition is the first section with full energy from
  40 Hz to 12 kHz; the coda falls back to the piano chord over the sub.

## Effects (`sfx.py`, `cues.json`)

Procedural (seeded, so reproducible) except the birds bed (ElevenLabs sound generation, one 10 s loop, committed).
A crickets bed was generated too but came back silent (−74 dBFS); it is synthesised instead.

Beds: room tone throughout; birds through the window over DAY/GOLDEN, gone by f690; crickets and a far city from
dusk (f480/f520) into the night; the record's crackle from the needle drop (f705) through the breath and under the
drop, easing away by f960; the halo's 100 Hz neon hum from the first letter, one step up per letter, held to the
end and the last thing to fade.

## How the arrangement maps to the shots

| Shot | Frames | Music | Effects on the frame |
|---|---|---|---|
| S01 olive | 0–119 | Morning: felt-piano D-minor chords over vinyl, no drums | room tone, birds |
| S02 room | 120–239 | Morning continues | a clock's tick in eighths (f120–232), the sheers breathe (f138) |
| S03 spines | 240–299 | **First kick on f240** (synth kick + brush) | finger along book cloth (f244) |
| S04 polaroid | 300–359 | kick, piano | polaroid flick (f315, beat 2) |
| S05 lyzn | 360–419 | + D2 sub (bar 7) | glassy tick (f390, beat 3) |
| S06 coin | 420–479 | kick, sub, piano | **coin's ring with the kick (f420)**, brass tink (f450, beat 3) |
| S07 drone | 480–539 | the take's groove arrives, filtered (bar 9) | gimbal servo (f486), LED blip (f525, beat 4) |
| S08 terminal | 540–599 | filter opening | keystrokes f540/548/555, cursor ticks f570/585 |
| S09 27 NOV | 600–659 | riser begins (bar 11) | calendar page settling (f630) |
| S10 crate | 660–719 | riser, then **silence from f705** | **needle drop f705**, crackle through the breath |
| S11 sign | 720–779 | **THE DROP f720**: full groove on D, full range | sub whoomph + power swell (f720); a relay clack per letter f720/735/750/765/772; hum steps up |
| S12 studio on | 780–839 | groove | four downlight contactors f780/795/810/825 |
| S13 him | 840–959 | the take's own breakdown: pads, no drums | his key light's thunk (f900); L1 starts f930 |
| S14 his line | 960–1079 | groove returns (C), ducked 8 dB under L1 | cloth (f1000, his open hand) |
| S15 hand-off | 1080–1199 | G, ducked under L2/L3 | cloth (f1108, he turns to her) |
| S16 her line | 1200–1319 | **the lift on bar 21** (B♭, the counter-melody), ducked under L3 | cloth (f1236, her watch hand) |
| S17 together | 1320–1439 | B♭ groove, full; ducked under L4a/L4b | — |
| S18 title | 1440–1559 | **the last chord on f1440** (D minor, the opening's), sub tail; fade f1536–1559 | the halo's hum fades last |

## The mix (`mix.py`, `mix.json`, `mix.png`)

Score to −16 LUFS and voice to −15.5 LUFS (each integrated), effects as leveled in `sfx.py`; the score ducks under
the voice (sidechain 4:1, 25 ms attack, 250 ms hold, 450 ms release, capped at 8 dB) and the beds by 3 dB; then one
static gain and a look-ahead limiter to −14 LUFS / −1 dBTP. Measured with R4's stems (vo_him + vo_her):

- −14.08 LUFS integrated (ffmpeg ebur128: −14.1), true peak −1.69 dBTP (ffmpeg −1.7), LRA 5.7 LU; no latency
  (the mix against the sum of its stems: 0 samples).
- The score ducks 8.0 dB under every line (the plan asks for 6–9). The voice over the ducked score, per line:
  L1 +7.8 LU, L2 +9.3, L3 +6.1, L4a +9.0, L4b +7.1.
- The arc per shot (LUFS): the morning shots −15 to −22, the build −13 to −18, **S11 the drop −10.3** (the loudest
  shot), the presenters −12 to −15, the title −14.

## What is open

- Judged by measurement only (spectra, onsets, loudness): no one has listened yet. Worth an ear: the synthesised
  kick and brush in bars 5–8 against the take's piano, the riser's pitched sweep, the coda splice at f1440, and
  whether the birds read as birds at their level.
- The voice lines are R4's (agent-03:2) stems as of today; a new take re-mixes with `mix.py --vo-dir …` (the levels
  are set by loudness, so the balance holds).
- ElevenLabs Music on the account's pay-as-you-go tier: check commercial-use terms before publishing (PLAN.md §2).
