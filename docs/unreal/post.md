# Audio, post and delivery (WP12)

The voice and the sound into Unreal with their timing (`audio.*` ops), one **timing document** that the voice, the
faces (WP4) and post all read, and a generic **render shots → cut → mix → deliver** pipeline (`film-post`) over
Movie Render Queue frames. The editor does timing; the mix and the deliverables are made in post from the same frames.

```
filmtools vo/edit (or any WAVs) ──▶ timing.json (kind: timing) ──▶ audio.lines ──▶ Sequencer track "VO"
                                         │                    └──▶ performance_handoff ──▶ speech.to_face + face anim (WP4)
MRQ frames per shot ─────────────────────┴──▶ film-post cut delivery.yaml ──▶ masters, web, 9:16, SRT/VTT, EDL, cut.json
```

## Recipes

**Put the voice on a sequence, timed.**

```bash
cd tools
# 1. a timing document from what you have: film-edit's data/vo.json, the reel's cues.json, or a plain lines list
uv run film-post timing --vo-json ../films/<id>/data/vo.json --fps 24 --speaker host -o /tmp/timing.json
uv run film-post timing --lines lines.json --fps 24 -o /tmp/timing.json      # [{id, wav, start_s|start_frame, text?, words?, speaker?}]
# 2. the WAVs onto the box (client.push), then one call imports them and places every line
uv run film-ue op audio.lines sequence=/Game/Seq/SQ_Main wav_root=/srv/film/vo track=VO timing=@/tmp/timing.json
# 3. check
uv run film-ue op audio.describe sequence=/Game/Seq/SQ_Main
```

Check: each line's `start_frame` in `audio.describe` equals the timing doc's (rescaled if the doc's fps differs:
the op says so in `fps_note`). Re-running returns `changed: false`.

**Any sound at a frame (score, effects), at a level.**

```bash
uv run film-ue op audio.import 'files=["/srv/film/score.wav"]' folder=/Game/Audio
uv run film-ue op audio.place sequence=/Game/Seq/SQ_Main track=Music \
    'clips=[{"sound":"/Game/Audio/score","start_frame":0,"volume_db":-4}]' extend=true
```

Overlapping clips stack on rows as Sequencer draws them. `replace=true` (the default) means the track holds exactly
these clips. Re-running with the same clips changes nothing.

**Declaratively (WP11's spec engine).** `examples/unreal/audio/voice-and-score.yaml`, kind `audio`:
`film-ue plan` / `film-ue apply`. A second plan is empty once the tracks match.

**Drive the faces from the same timing (WP4 handoff).**

```bash
uv run film-post handoff /tmp/timing.json --faces faces.json --wav-root /srv/film/vo
# faces.json: {"host": {"face_mesh": "/Game/MH/Host/Face", "label": "Host", "component": "Face", "mood": "CONFIDENCE"}}
```

Per line it prints `speech` (the exact args of `speech.to_face`) and `place` (actor label, component, start/end
frame) for where the face animation goes. A speaker with no face (a narrator) is left out.

**A speaking face from text, in one call (B29, `perf_speak`).**

```bash
fleetctl secret exec ELEVENLABS_API_KEY=elevenlabs -- uv run film-post speak --text "Welcome in." --id L1 \
    --sequence /Game/Seq/SQ_Main --start-frame 48 --face-mesh /Game/MH/Host/Face --label Host \
    --voice-id <id> --box-dir /srv/film/vo --out-dir out/vo        # --dry-run: the plan, no TTS, no bridge
```

It runs, in order: TTS on the client (the take cached in out/vo/L1.wav + .json, keyed on text and voice, so a re-run
pays nothing), `client.push`, `audio.lines` (replace=false: the line is added to VO, never duplicated),
`speech.to_face` (WP4), `perf.face` (WP4: head, eyes, blinks, brows over the lip-sync, `emphasis` [[t_s, 0.3..1]]
from the word alignment; skipped with a note in `notes` when the bridge lacks it; `--no-perf-face` skips it) and
`seq.anim` (the face animation at the line's frame, added to the face track; `--replace-face` empties it first).
Check: the JSON result's `steps[*].result`, `anim`, and `audio.describe` for the VO clip at the frame. Op boundary
agreed with WP4 (agent-01): the orchestration is client-side and adds no op.

**Cut and deliver Unreal renders.** Write a `delivery` spec (`examples/unreal/delivery/two-shots.yaml`), then:

```bash
uv run film-post plan  spec.yaml --json      # every step with its ffmpeg argv; nothing runs
uv run film-post frames spec.yaml            # which frames each shot must render, which are missing on disk
uv run film-post cut   spec.yaml             # make them; exit 1 if any output fails its check
uv run film-post edl   spec.yaml > cut.edl   # CMX 3600 for an NLE
```

Check: `<out>/cut-<name>.json` lists every output with `problems` (frame count, size, audio length against picture
within 1.5 frames) and the cut's loudness. `ok: true` when every output is clean.

## Op reference (`film-ue ops audio`)

| op | what | idempotent |
|---|---|---|
| `audio.import(files, folder, names?, replace?, save?)` | WAVs on the box → SoundWaves; skips any already there | yes |
| `audio.place(sequence, clips, track, replace?, extend?)` | clips `{sound, start_frame\|start_s, end_frame\|duration_s?, offset_s?, volume_db?, fade_in_frames?, fade_out_frames?}` on a named track | yes (converges) |
| `audio.describe(sequence)` | every audio track and clip: frames, seconds, row, offset_s, volume_db | read-only |
| `audio.remove(sequence, track)` | remove a named track (`"*"` = all audio tracks) | yes |
| `audio.lines(sequence, timing, folder?, track?, wav_root?, extend?)` | import + place a timing document's lines | yes |

`seq.audio` (WP8's older op, linear volume) still works; the `audio.*` ops are the agent-facing ones.

## Client modules

- `filmtools.unreal.audio_timing`: the timing document (`from_lines`, `from_vo_json`, `from_cues_json`, `validate`,
  `overlaps` (one speaker, two lines at once), `rescale`, `performance_handoff`, `load`).
- `filmtools.unreal.audio_kind`: the `audio` spec kind (`plan(spec, state)` is pure); schema
  `tools/filmtools/unreal/schemas/audio.schema.json`.
- `filmtools.unreal.post_cut`: the delivery spec and pipeline (`load_spec`, `validate`, `plan`, `run`, plus pure
  pieces: `to_out`, `spans_out`, `timecode`, `cmx3600`, `caption_cues`, `captions_text`, `crop_expr`,
  `encode_args`, `cut_audio_args`, `vo_bus_args`, `check_output`). The mastering uses `filmtools.mix` (static gain to
  the LUFS target + a delay-free limiter; never two-pass loudnorm, which rides the gain).
- `filmtools.unreal.perf_speak`: B29 (`speak`, `synthesize`, `plan`, `emphasis`).
- `filmtools.unreal.post_cli`: `film-post`.

## Spec kinds

**`timing`** (a data document, not applied):
`{"kind": "timing", "version": 1, "fps", "lines": [{"id", "speaker", "wav", "start_frame", "end_frame",
"duration_s", "offset_s", "volume_db", "text", "words": [{"w", "start_frame", "end_frame"}], "mood"?}]}`. A line's
`start_frame` is where its WAV starts (its first word is in `words`). Example: `examples/unreal/audio/timing.json`.

**`audio`** (applied by `film-ue apply`): `sequence`, `tracks: [{name, timing, wav_root, folder} | {name, clips}]`,
`remove_others`. Example: `examples/unreal/audio/voice-and-score.yaml`.

**`delivery`** (run by `film-post`): `fps`, `out`, `shots: [{id, start, end, frames, pattern?, offset?}]` on the
sequence's clock, `edl?`, `fill?: slate`, `audio: {mix} | {timing, music?}` + `lufs`, `true_peak`, `xfade_s`,
`captions?: {max_chars, hold_frames}`, `outputs: [{name, preset, height?, aspect?, crop?, captions?: burn, crf?}]`.
Presets: `prores4444`, `prores422hq` (mov, PCM 24-bit), `h264`, `hevc` (mp4, AAC 320k). Full reference in the
module docstring of `post_cut.py`.

## Gotchas

- **Times are frames at the sequence's display rate.** A timing doc at another rate is rescaled by `audio.lines`
  (and `film-post` rescales it to the spec's fps). Seconds only where a name ends in `_s`.
- **A section's start offset is in tick resolution**, not display frames (`set_start_offset` takes an FFrameNumber at
  `get_tick_resolution()`, 24000/s by default). `audio.place` converts from `offset_s`.
- **Levels and fades live on the section's Volume channel.** `volume_db` sets its default (linear gain 10^(dB/20));
  `fade_in_frames` / `fade_out_frames` add linear keys from/to silence (at most four a clip). `audio.describe` reads
  the fades back from the keys. `EMovieSceneKeyInterpolation` is a `UENUM()` without BlueprintType: if the Python
  wrapper does not export it, the keys fall back to add_key's default (Auto), a slightly curved ramp.
- **MRQ frame numbering**: a shot rendered from the master sequence is numbered on the master's clock; a shot
  rendered as its own sequence from 0. `film-post` finds either; if renders start at a handle (f-12 numbered 0) set
  the shot's `offset`.
- **WP9's render layout** (`render.mrq`, agent-05): frames at `<out_dir>/NNNN.png` (the sequence's display frame) are
  read with the default pattern; with several passes point the shot's `frames` at `<out_dir>/FinalImage` (and set
  `pattern` to the pass's extension). `render.encode` makes a one-job review video; masters come from `film-post`.
- **Cloth needs pre-roll** (docs/linux/engine.md): render each shot from its start even when the edit keeps only its
  end, and let the edl drop the head. `film-post frames` prints the ranges the edit needs.
- **Never offset the sound with `-itsoffset`, `-ss` or `-shortest`**: picture and sound both start at output frame 0
  and the sound is padded/trimmed to the picture's exact length. The sound edit is an equal-power crossfade (12 ms)
  centred on each cut, so a cut never clicks.
- **RGB → YUV is explicit BT.709** (`scale=...:out_color_matrix=bt709:out_range=tv`); ffmpeg's implicit conversion of
  PNG frames is BT.601 (a colour shift).
- **Burned captions go through an ASS file per output, never `subtitles=x.srt:force_style=...`.** libass lays an SRT
  out in its default 384x288 script space, so a FontSize or MarginV given in pixels comes out several times too big
  (and stretched at 9:16). `ass_text` writes PlayResX/Y = the output's size, the type and margins in its pixels,
  inside the safe area (`SAFE`: 9:16 keeps clear of the top 12%, bottom 22%, left 6%, right 12% that the apps' UI
  covers; other aspects get 5% title-safe). `caption_safe_check` estimates each cue's wrap and fails over 2 lines:
  the output's `problems` say so, and the fix is a lower `captions.max_chars`. It needs an ffmpeg with libass
  (`ass` filter); without one, deliver the SRT/VTT sidecars and drop `captions: burn`.
- **Loudness**: `film-post loudness mix.wav` gives the check shape (`pass`, `metric`, `threshold`, `why`) against
  -14 LUFS / -1 dBTP; `film-post cut` remasters a cut that drifts from the target.
- **WAV names become asset names**: spaces, dots and dashes are `_`; a leading digit gets `S_`. `audio.lines` names
  each SoundWave after its line id.

## API_NOTES (UE 5.8.4 source box, `/srv/ue-src/UnrealEngine-5.8.4`; all verified 2026-11-04)

| Python call | reflected API | source file:line |
|---|---|---|
| `AssetImportTask.filename/destination_path/destination_name/replace_existing/automated/save` | UPROPERTYs | Engine/Source/Editor/UnrealEd/Public/AssetImportTask.h:36,40,44,48,56,60 |
| `AssetTools.import_asset_tasks` | `ImportAssetTasks` BlueprintCallable | Engine/Source/Developer/AssetTools/Public/IAssetTools.h:541-542 |
| `SoundWave.get_editor_property("duration")` | `USoundBase::Duration` BlueprintReadOnly | Engine/Source/Runtime/Engine/Classes/Sound/SoundBase.h:201-202 |
| `SoundWave.get_editor_property("asset_import_data")` | VisibleAnywhere | Engine/Source/Runtime/Engine/Classes/Sound/SoundWave.h:878-879 |
| `AssetImportData.get_first_filename()` | `K2_GetFirstFilename` ScriptName GetFirstFilename | Engine/Source/Runtime/Engine/Classes/EditorFramework/AssetImportData.h:139-140 |
| `seq.find_tracks_by_type / add_track / remove_track` | MovieSceneSequenceExtensions | Plugins/MovieScene/SequencerScripting/Source/SequencerScripting/Public/ExtensionLibraries/MovieSceneSequenceExtensions.h:59,79,89 |
| `seq.get_display_rate / get_tick_resolution` | same | MovieSceneSequenceExtensions.h:98,116 |
| `seq.get_playback_end / set_playback_end` | same | MovieSceneSequenceExtensions.h:192,228 |
| `track.set_display_name / get_display_name / add_section / get_sections / remove_section` | MovieSceneTrackExtensions | .../ExtensionLibraries/MovieSceneTrackExtensions.h:33,42,72,81,90 |
| `section.get_start_frame / get_end_frame / set_range / get_all_channels` | MovieSceneSectionExtensions | .../ExtensionLibraries/MovieSceneSectionExtensions.h:45,72,145,220 |
| `section.set_row_index / get_row_index` | UMovieSceneSection UFUNCTIONs | Engine/Source/Runtime/MovieScene/Public/MovieSceneSection.h:541-546 |
| `section.set_sound / get_sound` | UMovieSceneAudioSection UFUNCTIONs | Engine/Source/Runtime/MovieSceneTracks/Public/Sections/MovieSceneAudioSection.h:37-42 |
| `section.set_start_offset / get_start_offset` (FFrameNumber, tick resolution) | UFUNCTIONs over `StartFrameOffset` | MovieSceneAudioSection.h:49-54, 306-307 |
| Volume channel name `"Volume"` (and `"Pitch"`) | `SetIdentifiers` in the editor data | Engine/Source/Runtime/MovieSceneTracks/Private/Sections/MovieSceneAudioSection.cpp:85-86, 236 |
| `channel.add_key(FrameNumber, value, sub_frame, MovieSceneTimeUnit.DISPLAY_RATE, interp) / get_keys`, `key.get_time() / get_value()` | UMovieSceneScriptingFloatChannel / FloatKey UFUNCTIONs; `EMovieSceneTimeUnit` UENUM(BlueprintType); `EMovieSceneKeyInterpolation` UENUM() | MovieSceneScriptingFloat.h:375-376, 410-411, 33, 49; Engine/Source/Runtime/MovieScene/Public/MovieSceneTimeUnit.h:11-15; KeyParams.h:10-22 |
| `channel.set_default / get_default / has_default` | UMovieSceneScriptingFloatChannel UFUNCTIONs | Plugins/MovieScene/SequencerScripting/Source/SequencerScripting/Private/KeysAndChannels/MovieSceneScriptingFloat.h:598-599, 616-617, 650-651 |
| (not used yet) MRQ audio: `MoviePipelineWaveOutput.file_name_format_override` | UPROPERTY | Plugins/MovieScene/MovieRenderPipeline/Source/MovieRenderPipelineRenderPasses/Public/MoviePipelineWaveOutput.h:34-35 |

## Selftest

`film-ue selftest audio` (`unreal/fmbridge/selftest/audio.py`): writes two sine WAVs under Saved/Selftest/audio,
imports them (names, durations, idempotent re-import), makes a 24 fps scratch sequence with `seq.new`, places three
clips (row stacking, -6 dB, 0.5 s offset, read back by `audio.describe`; re-run unchanged), places a 48 fps timing
document with `audio.lines` (rescaled frames; idempotent), and removes a track twice. 13 checks, about 10 s, no GPU,
no Epic login, no assets. It also runs on the fake engine in `tools/tests/test_ue_audio.py`.

Unit tests: `tools/tests/test_ue_audio.py`, `test_ue_audio_timing.py`, `test_ue_audio_kind.py`, `test_ue_post_cut.py`
(39 tests with the runtime's own, about 2 s).

## HANDOFF

Done (branch `fleet/agent-03/ue-post`): the audio ops, ext_audio fake, the timing document + WP4 handoff, the `audio`
spec kind + schema + examples, `post_cut` + `film-post`, the selftest, this doc.

Not done / next:
- **Never run against real ffmpeg here** (the fleet container has none): `film-post cut` is unit-tested at the argv
  level only. First thing on a box with ffmpeg: `film-post cut examples/unreal/delivery/two-shots.yaml` with test
  frames (any PNGs in out/renders/S01, S02) and read `cut-two-shots.json`.
- B29 (claimed via the lead): `perf_speak` + `film-post speak` done with a fake TTS and a recorded bridge. Untested:
  a real ElevenLabs call (the key comes in the morning: `fleetctl secret exec ELEVENLABS_API_KEY=elevenlabs -- ...`),
  and `perf.face`'s exact argument names (agent-01's, landing on fleet/agent-01/ue-anim: anim, wav, mood, emphasis).
- B25 (claimed): fades in frames and the client LUFS check are done. Not done: an `audio.mix`-style call that
  places a set of stems (VO/Music/SFX WAVs) with levels in one go; today that is one `audio.place` per track, or an
  `audio` spec with several tracks (which is the declarative way and probably enough).
- B26 (claimed): presets (ProRes 4444 / 422 HQ, H.264, HEVC), 9:16 crop keys, burned captions in the safe area with a
  check, argv from the spec: done. Not run against a real ffmpeg yet (see the first point).
- The fade ramp's shape (Linear vs Auto fallback) is unverified until the selftest runs in a real editor: check
  `audio.describe` on a faded clip and the key interpolation in the editor log if the wrapper lacks the enum.
- A `cli_post.py` hook so `film-ue post ...` mirrors `film-post` (DECISIONS: WP11 wires `register(subparsers)`).
- The reel's Pillow title cards / overlay captions (`cut.py`) were not carried over: captions burn through libass;
  titles are film-specific and belong in `films/<id>/`.
- MRQ's own audio output (`MoviePipelineWaveOutput`) could render the sequence's mix from Unreal; post builds its
  mix from the timing instead, so they agree by construction.
