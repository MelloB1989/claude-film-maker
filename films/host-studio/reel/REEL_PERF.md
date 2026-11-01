# R4 — the presenters' performances

Task R4 of [PLAN.md](PLAN.md) §6: the voice lines L1–L4, and each presenter's face and body for S13–S18.

## The voice (`vo.py`, `vo_selects.json`)

ElevenLabs `eleven_multilingual_v2`, stability 0.45, similarity 0.8, style 0.25, speaker boost; every take has its
own seed (9600 + k), so `vo.py takes` makes the same takes again. 310 credits for everything below.

**Auditioned** (one L1 or L3 take each, then more takes of the finalists), measured rather than guessed:

| Voice | Line | Speech | Fit to slot | Words/s | Median f0 | Range (st) | Spectral centroid | Silence floor | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Tarun (him) | L1 | 5.9–7.7 s | 0.94–1.24 | 2.6–3.4 | 133–143 Hz | 11–13 | 2.9–3.3 kHz | −90 dB | **chosen**: warm, clean, a light Indian-English accent |
| Ranbir | L1 | 8.3 s | 1.33 | 2.4 | 111 Hz | 9.6 | 3.8 kHz | room noise in the voice | too slow, noisy |
| Shrey | L1 | 5.2–5.6 s | 0.83–0.89 | 3.6–3.9 | 97 Hz | 8–10 | 3.3 kHz | −60…−72 dB | deep but rushed; hiss in the gaps |
| Tripti (her) | L3 | 5.7–6.7 s | 0.89–1.06 | 2.1–2.5 | 176–230 Hz | 13–15 | 2.6–2.8 kHz | −90 dB | **chosen**: the warmest, clean, calm pace |
| Ziina | L3 | 4.1 s | 0.65 | 3.4 | 174 Hz | 7.7 | 3.5 kHz | −48 dB | rushed, noisy tail |
| Priyanka | L3 | 7.4 s | 1.16 | 1.9 | 180 Hz | 5.3 | 3.4 kHz | −89 dB | flat, a 1.3 s hole mid-line |

"Fit" is the speech's length over the plan's window; the forced aligner's loss (1 credit a take) was the clarity
check; spectrograms of every take are `out/host-studio/reel/vo/takes.png`. Tarun's takes 1 and 3 of L1 draw out
"Thisss" (0.5 s of sibilance, plain on the spectrogram); take 2 does not.

**Selects** (why in `vo_selects.json`): L1 tarun-2, L2 tarun-1, L3 tripti-1, L4a tarun-3, L4b tripti-3. Each is trimmed
to 50 ms before the voice and 250 ms after it, levelled to −20 dBFS speech RMS (peak ≤ −1 dBFS), and placed with its
first word on the plan's frame:

| Line | Voice starts | Last word ends | Plan window |
|---|---|---|---|
| L1 | f930 | f1069 | f930–1080 |
| L2 | f1110 | f1141 | f1110–1150 |
| L3 | f1158 | f1305 | f1158–1310 |
| L4a "Welcome…" (him) | f1360 | f1373 | f1360–1382 |
| L4b "…to karma." (her) | f1386 | f1403 | f1386–1410 |

Files (not in git: the repo keeps generated audio out): `out/host-studio/reel/vo/` — `L1.wav` … `L4b.wav`,
`vo_him.wav`/`vo_her.wav`/`vo.wav` (65 s stems on the master clock), `cues.json` (each line's file frame, voice frame
and word frames; R6's captions and R5's ducking read it).

## The performances (`perf.py`)

The pipeline (`perf.py` docstring has the commands):

1. **Solve**: each presenter's whole screen time as one audio solve (him f840–1560 in CONFIDENCE 0.8, her f1080–1560
   in CONFIDENCE 0.9), so blinks, breaths and the listening face between lines are one continuous performance; the
   lines whose mood differs (L2 HAPPINESS 0.6, L4a/L4b HAPPINESS 0.7) solved alone and **spliced** over it at their
   frames with a 4-frame cross-fade.
2. **Silent beats** on the face curves (`BEATS`): his head down in the dark then up to the lens with the key light
   (f840–914), the hand-off turn to her after L2 (HeadYaw to ~45°, f1136–1152, held through S15, back during S16), her
   head turned to him while he speaks and then to the lens for L3 (f1156), smiles (his at "the next one", hers at it
   too, both after "…to karma." held through the title), a small settling nod for both (~f1405).
3. **Stage**: my own copies of the presenters (same Blueprint class) and test cameras keyed from `shots.py`, all
   moved 25 m under the floor (out of every reel camera), one test sequence per presenter.
4. **Sync** (shot.py's recipe): face and body one skeleton; the body takes the head motion.
5. **Gaze**: `anim.gaze_lock` one range at a time — each shot's lens, and the partner's eyes for the hand-off (`GAZE`).
6. **Gestures**: none in the engine's content; a hand-keyed open hand for S14 and a small watch-hand lift for S16
   (`GESTURES`), axes measured on the rig (`arm_axes`), used only if they read naturally (`USE_GESTURE`).
7. **Place**: `perf.py place --seq /Game/Reel/SEQ_Reel` (R7): one Face and one Body section per presenter from
   f840 / f1080. Run `mh.drive_face` on Host and Presenter first.

## Status

(filled in below as the editor passes run)
