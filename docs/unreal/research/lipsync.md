# Lip sync, done properly (R5 research, track T1)

Why this exists: in round 4's 65 s cut, Host_Op's mouth opened wide at f1000-1008, but L1 ("Took you long enough.")
starts at f1020. That is about 0.7 s early. During his lines the mouth did not follow the words. Every gate passed:

- `perf.py verify` measured how much the jaw moved on a line (range ≥ 0.08), never when it moved.
- The silence windows stopped 6 frames before each line, so motion just before a line was never checked.
- agent-09's lip-gap metric flagged motion in the silence at f977-1001 (0.33 cm/frame), and it was waived as a smirk.
- cues.json was round 3's copy with `words_lost: true`, so nothing measured where the voice really starts.

This page covers the root causes, the correct pipeline, the knobs, the pitfalls, and the automatic checks that now
ship in core (`perfkit.lipsync`, `lipsync.*` ops, `film-ue lips`).

Trust tags: **[Epic docs]**, **[Epic source]** (read in the UE 5.8.4 tree, `Engine/Plugins/MetaHuman`,
`Engine/Plugins/VirtualProduction/CaptureData`), **[Epic forum]**, **[paper]**, **[vendor/forum]**,
**[ours]** (measured or read in this repo).

## 1. Root causes of our failure

1. **No timing check existed.**
   - Every lip number was an amplitude: jaw range and std on the line, or a lip-gap ratio.
   - A face shifted 17 frames still moves "a lot on the line", so it passed.
   - The fix is the lag and correlation gate (section 5).
2. **Two timebases.**
   - The face came from a whole-stem solve (`stem_<who>.wav`, cut from START) with other-mood lines spliced in at
     cues' `file_frame`.
   - The mix plays `vo_<who>.wav` built separately.
   - cues.json held the planned frames and estimated words, not frames measured from the audio the mix plays.
   - Nothing proved that the stem the solver heard is the audio the cut plays.
   - **[ours]** The committed `audio/mix/mix.wav` has the voice starting at f1021 (L1), f1097 (L2) and f1160 (L3a).
     These agree with the cues, so the audio is placed right and the early mouth came from the face side.
3. **The solver itself is not early.**
   - **[Epic source]** For audio input, `UMetaHumanPerformance::UpdateFrameRanges` takes the processing range from
     `UFootageCaptureData::GetAudioFrameRange`. With the default `TimecodeAlignment = Relative`, that function moves
     the range to start at 0 (`CaptureData.cpp:515`).
   - The performance's frame rate for audio is `FFrameRate(30, 1)` (`MetaHumanPerformance.cpp:1002`).
   - **[Epic forum]** Inference runs at 50 Hz and is resampled to the performance rate on export
     ([thread](https://forums.unrealengine.com/t/umetahumanperformanceexportutils-framerate-locked-on-audio-to-animation/2692295)).
   - So frame 0 of the solve is the wave's first sample, at 30 fps, with at most ±10 ms of nearest-neighbour
     resampling jitter. A 0.7 s lead must enter after the solve: in compose/splice, naturalize, gaze/bake, placement,
     or a stem that differs from what the mix plays.
   - The GPU probe P1 (the round-5 plan) runs `lipsync.check` after each of those stages to find the exact one.
4. **Mouth in the silences.**
   - The whole-stem solve animates the mouth everywhere. Its breaths, lip smacks and the splice fades all reach the
     face.
   - The perfkit layers add smiles on top.
   - `SPEECH_GAIN = 1.7` with a 0..1 clamp then exaggerates and flattens the jaw. This affects tracking, not timing.
5. **Full-face solve under perfkit.**
   - The solver's own head motion (kept "softened") and blinks were layered under perfkit's.
   - With perfkit owning head, eyes, blinks and brows, the solve should give only the mouth (Process Mask "Mouth
     Only", head DISABLED, no blinks). Track T2 covers the blink nod.

## 2. The correct pipeline (what pros do: one timebase, measured)

1. **One source of truth for line timing: `film-ue lips cues`.**
   - VAD runs on each speaker's stem as the mix places it (frame 0 = sample 0), inside each line's window. This gives
     `voice_frame` and `end_frame` as measured onset and offset.
   - Words come from a forced aligner (stable-ts `align` on CPU with the known text) or are estimated and flagged.
   - The stems' sha256 are recorded, so `stale()` refuses cues measured on different audio.
   - Face placement, captions and the mix all read this one file.
2. **One solve per line, from the line's own WAV.**
   - Use `speech.to_face process_mask=mouth head=false blinks=false`.
   - The line's WAV starts ~50 ms before its first word (vo.py), and its `file_frame` is where that WAV starts in the
     master. So the solve's t = 0 goes on `file_frame`, by construction.
   - **[Epic docs]**
     [Audio driven animation](https://dev.epicgames.com/documentation/en-us/metahuman/audio-driven-animation):
     Process Mask (Full Face / Mouth Only) is meant for layering lip animation. Head Movement is optional. Realtime
     Audio has no head motion and hides the other options.
3. **Compose the mouth on the performance's timebase: `lipsync.compose`.**
   - Each line's speech curves (jaw, lips, tongue) go at their `file_frame`, with a 3-frame fade at the WAV's ends.
   - The mouth rests between lines (optionally a small share of a base for breaths).
   - The smile/expression curves are left to perfkit.
   - This replaces the whole-stem solve and splices.
4. **perfkit layers on top** (`perf.face`): head, eyes, blinks, brows and expressions. It must not move the speech
   curves in time. Speech gain is a separate decision; prefer ≤ 1.3 without clamping the jaw.
5. **Place the face section at START with offset 0 and play rate 1.** The audio section plays the same stems from
   frame 0.
   - **[Epic docs]**
     [MovieSceneSkeletalAnimationParams](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MovieSceneSkeletalAnimationParams?application_version=5.6):
     `start_frame_offset` and `first_loop_start_frame_offset` are in tick-resolution frames. Convert display frames
     × (tick ÷ display rate).
   - **[Epic forum]** [Scripting units](https://forums.unrealengine.com/t/discrepancy-when-setting-frame-values-in-sequencer-display-frame-rate-vs-tick-resolution-frame-rate/265092)
6. **Gate it**, then render, then gate the render (section 5).

Alternatives considered:

- **MetaHuman's Level Sequence export with `export_audio_track=True`.**
  - **[Epic docs]**
    [settings](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MetaHumanPerformanceExportLevelSequenceSettings?application_version=5.7)
  - It puts the solved wave and the face on one sequence, which is the textbook single timebase.
  - We place per-line sections ourselves, so the same guarantee comes from `file_frame` plus the check.
- **NVIDIA Audio2Face-3D**, open-sourced on 24 Sep 2025.
  - It ships an SDK (MIT), models under the NVIDIA Open Model License, and a UE plugin v2.5 for UE 5.5/5.6.
  - It needs CUDA 12.8 and TensorRT, and states no support for 5.7/5.8.
  - **[vendor/forum]** [NVIDIA blog](https://developer.nvidia.com/blog/nvidia-open-sources-audio2face-animation-model),
    [SDK](https://github.com/NVIDIA/Audio2Face-3D-SDK)
  - Not for 5.8.4 now. animation.md keeps the MetaHuman solver as the default.
- **Word timing on CPU.**
  - **[paper]** [Rousso et al. 2024](https://arxiv.org/html/2406.19363v1): on TIMIT word boundaries, MFA has a
    median error of 12.5 ms (89% within 50 ms) and WhisperX 23.5 ms (82%). Plain Whisper timestamps are worse
    ([WhisperX paper](https://arxiv.org/html/2303.00747v2)).
  - MFA needs conda. stable-ts `align` and whisperX are pip-only and run on CPU.
  - We use VAD for the onset and offset (it does not depend on an ASR model) and the aligner only for word interiors.

## 3. Knobs and their values

| Where | Knob | Value | Why |
|---|---|---|---|
| speech.to_face | `process_mask` | `mouth` when perfkit owns the rest | `audio_driven_animation_output_controls` = `MouthOnly` **[Epic source]** `AudioDrivenAnimationConfig.h:29` |
| speech.to_face | `head` | `false` | `head_movement_mode` = `Disabled` (enum `TransformTrack, ControlRig, Disabled`, `MetaHumanPerformance.h:52`), and the export's `enable_head_movement` false |
| speech.to_face | `blinks` | `false` | `generate_blinks` (`bGenerateBlinks`, `MetaHumanPerformance.h:373`); perfkit blinks |
| performance | `timecode_alignment` | leave `Relative` (the default) | frame 0 = the wave's first sample |
| performance | `downmix_channels` | true (the default) | mono stems anyway |
| lipsync.compose | `fade_frames` | 3 | inside the ~50 ms lead-in of each line WAV |
| face section | offset / play rate | 0 / 1.0 | lipsync.check warns on any other play rate |
| sequence | clock source | Audio for real-time playback | **[Epic forum]** [fix for audio lagging lips in game](https://forums.unrealengine.com/t/audio-sync-issues-when-playing-the-game/2122431); MRQ renders are frame-stepped and unaffected |

## 4. Pitfalls

- **Planned frames are not measured frames.** Always place from measured `file_frame` and `voice_frame`.
- **A stem rebuilt without rebuilding the cues.** cues.json now records the stems' sha256.
- **Display frames vs ticks** in section offsets; see section 2.5.
- **SyncNet's default search is too narrow.** `--vshift 15` is ±0.6 s at 25 fps, so a 0.7 s error sits at the edge
  of the window. Use 30. It assumes 25 fps and 16 kHz.
  - **[vendor/forum]** [joonson/syncnet_python](https://github.com/joonson/syncnet_python) (MIT)
- **SyncNet scores mean little on a CG face.**
  - **[paper]** LSE-C on real video is ~7-8 and on out-of-sync dubbed video 0.9-2.6
    ([Wav2Lip](https://ar5iv.labs.arxiv.org/html/2008.10010)).
  - The scores correlate weakly with human judgement ([2511.04520](https://arxiv.org/pdf/2511.04520)) and move with
    the crop ([2405.04327](https://arxiv.org/pdf/2405.04327)).
  - Calibrate the confidence threshold on this avatar's known-good lines, and prove sensitivity with a shifted-audio
    control.
- **The mouth naturally leads the sound a little.**
  - **[paper]** [Chandrasekaran et al. 2009](https://pmc.ncbi.nlm.nih.gov/articles/PMC2700967/): 100-300 ms at
    phrase onsets.
  - **[paper]** [Schwartz & Savariaux 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC4117430): -40 to +200 ms in
    connected speech.
  - So the onset allowance is 0.25 s, and the lag gate measures the whole line's rhythm, not just the onset.
- **Perception thresholds.** **[paper/standard]**
  [ITU-R BT.1359](https://www.itu.int/dms_pubrec/itu-r/rec/bt/R-REC-BT.1359-1-199811-I!!PDF-E.pdf): detectable at
  +45 / -125 ms and acceptable to +90 / -185 ms (+ = sound early). One frame at 24 fps (42 ms) is inside both. Our bug
  was -700 ms.

## 5. Verify automatically

**Curve gate: `lipsync.check`** (editor op), or `film-ue lips curves` (offline, on `anim.read_curves` output). It is
built on `perfkit.lipsync.check`. Per line of the speaker:

| metric | how | FAIL when | why that limit |
|---|---|---|---|
| `lag_frames` | cross-correlation of the voice's loudness and the mouth's opening (jawOpen + lip parting − lip seal), both band-passed to 1-8 Hz (the syllable band), searched ±1 s at 100 Hz with sub-sample peak | \|lag\| > 1 frame | ITU detectability; the brief |
| `corr` | Pearson r at that lag | < 0.35 | in our synthetic tests, solver-like tracking reads 0.9+, while a mouth moving to other syllables in the same spans reads below 0.3. Recalibrate on the real solve with GPU probe P2 |
| `onset_lead_s` | first rise of the mouth above rest + 25% of its range, before the measured voice onset | > 0.25 s | natural anticipation is 100-300 ms (Chandrasekaran) |
| `open_range` | 90th percentile minus rest on the line | < 0.08 | no lip-sync at all (round 3's rule) |
| `words_moving` | share of aligned words (not estimated ones) with mouth range ≥ 0.04 | < 80% | the research recommends ≥ 90% of word intervals; 80% leaves room for unaligned clitics |
| silences | outside every VAD span, widened by 0.25 s anticipation and 0.25 s release: the 95th percentile of opening above rest, and the mean speed as a share of the lines' | open > 0.10 or busy > 25% | a breath or smile stays under 0.05 open and a few % busy; talking is ~100% busy |

`diagnosis` reads the per-line lags:

- `in sync`.
- `offset`: all lines off by the same amount. The section or audio is misplaced.
- `drift`: the lag grows with time. A frame-rate or play-rate mismatch, e.g. 30 fps keys read as 24.
- `scattered`: each line was placed on its own, and wrongly.

`expected_lag_s` removes the solver's own bias. Measure it with `lipsync.check anim=<raw line solve>
anim_frame=<file_frame> wav=<line wav> wav_frame=<file_frame>`.

Round 4's case is a unit test: a mouth 0.7 s early fails `lag` (-16.8 frames), `onset` and `silence`, with the
diagnosis `offset`.

**Render gate: `film-ue lips render`.** Run it after every render with dialogue.

- It crops the speaker's mouth from each frame:
  - `lipsync.mouth_boxes` projects the MetaHuman mouth bones (`FACIAL_C_Jaw`, `FACIAL_L/R_LipCorner`,
    `FACIAL_C_LipUpper/Lower`) through the camera the edit shows;
  - or `--box` takes one box for a locked-off shot.
- Two signals come from the crop: darkness (the open mouth's cavity against the rim) and motion (frame difference).
  Each is cross-correlated with the voice (motion against the envelope's change).
- **Control:** the voice shifted 6 frames must move the measured lag by 6 ± 1.5. Otherwise the measure cannot see
  this shot, and the verdict is `inconclusive` (exit 2), never `pass`. The research recommends the same control for
  SyncNet.
- FAIL on \|lag\| > 1 frame or r < 0.3.
- With `--syncnet-dir` (a syncnet_python checkout and its `data/syncnet_v2.model`), each line is also scored by
  SyncNet:
  - input: a 224 px face crop at 25 fps with 16 kHz audio, `vshift` 30;
  - the offset is converted to 24 fps frames;
  - FAIL on \|offset\| > 1 frame or confidence < `--min-conf` (3.0 by default; calibrate it with probe P3).

This is the robust automatic pass/fail for a rendered CG avatar: the curve gate (deterministic, before render), then
the render gate's crop signal with its sensitivity control, with SyncNet as a second opinion. SyncNet alone is not
enough on CG faces.

## 6. Links

- MetaHuman audio-driven animation: https://dev.epicgames.com/documentation/en-us/metahuman/audio-driven-animation
- MetaHumanPerformance Python API (5.7): https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MetaHumanPerformance?application_version=5.7
- Export utils: https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MetaHumanPerformanceExportUtils?application_version=5.7
- Python scripting for MetaHuman Animator (process_audio_performance.py, export_performance.py): https://dev.epicgames.com/documentation/en-us/metahuman/python-scripting-for-metahuman-animator
- Frame rates of the audio solve (Epic staff): https://forums.unrealengine.com/t/supported-frame-rates-in-metahuman-animator/2698066
- Realtime audio (Live Link, lookahead 80-240 ms, no head): https://dev.epicgames.com/documentation/en-us/metahuman/realtime-animation
- Sequencer time (tick resolution 24000, display rate): https://docs.unrealengine.com/4.26/AnimatingObjects/Sequencer/Workflow/TimeRefactorNotes
- SyncNet: https://www.robots.ox.ac.uk/~vgg/publications/2016/Chung16a/chung16a.pdf, https://github.com/joonson/syncnet_python
- Wav2Lip LSE-C/D: https://ar5iv.labs.arxiv.org/html/2008.10010
- Audio2Face-3D: https://github.com/NVIDIA/Audio2Face-3D-SDK
- stable-ts: https://github.com/jianfch/stable-ts; whisperX: https://github.com/m-bain/whisperX; MFA: https://montreal-forced-aligner.readthedocs.io/
