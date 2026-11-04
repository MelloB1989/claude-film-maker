"""Audio in Unreal: WAVs in as SoundWaves, sounds onto named Sequencer audio tracks with their timing, and the audio
of a sequence read back. The editor is for timing (lip-sync, cuts against the voice); the final mix is made in post
(filmtools.unreal.post_cut / filmtools.mix) from the same timing, so the picture and the mix agree to the frame.

Times are frames at the sequence's display rate unless the name says `_s`; volumes are dB (`volume_db`, 0 = unity).
"""
from __future__ import annotations

import math
import os
import re

import unreal

from . import op
from ..errors import OpError
from .assets import EAL, load

_NAME_BAD = re.compile(r"[^A-Za-z0-9_]")


def asset_name(file: str) -> str:
    """A SoundWave's name from its file: the stem with anything Unreal refuses (spaces, dots, dashes) as `_`."""
    stem = os.path.splitext(os.path.basename(file.replace("\\", "/")))[0]
    name = _NAME_BAD.sub("_", stem).strip("_") or "Sound"
    return name if not name[0].isdigit() else f"S_{name}"


def _pkg(path: str) -> str:
    return path.split(".")[0]


def _duration(wave) -> float:
    try:
        return float(wave.get_editor_property("duration"))
    except Exception:
        return 0.0


def _source_file(wave) -> str:
    try:
        return str(wave.get_editor_property("asset_import_data").get_first_filename())
    except Exception:
        return ""


@op("audio.import", mutates=True, idempotent=True, tags=["audio"])
def import_sounds(*, files: list, folder: str = "/Game/Audio", names: dict | None = None, replace: bool = False,
                  save: bool = True) -> dict:
    """Import WAV files on the box as SoundWaves in `folder`, skipping any already there (idempotent).

    Args: files: absolute WAV paths on the box (push them first: client.push). folder: content folder. names:
    {file: asset name} to override the default (the file's stem, sanitised). replace: re-import over an existing
    sound (its source changed). save: save the new assets.
    Returns: {"changed", "sounds": [{"file", "path", "duration_s", "imported"}]}.
    Example: film-ue op audio.import 'files=["/srv/film/vo/L1.wav"]' folder=/Game/Audio/VO
    """
    names = names or {}
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        raise OpError(f"{len(missing)} file(s) not on the box: {', '.join(missing[:5])}", code="not_found",
                      hint="push them first (filmtools.unreal.client.push(local, remote)) and pass the remote paths")
    if not str(folder).startswith("/Game"):
        raise OpError(f"folder {folder!r} is not a content path", code="bad_args", hint="use /Game/...")
    todo, out = [], []
    for f in files:
        path = f"{folder.rstrip('/')}/{names.get(f) or asset_name(f)}"
        exists = EAL.does_asset_exist(path)
        out.append({"file": f, "path": path, "imported": not exists or replace})
        if not exists or replace:
            t = unreal.AssetImportTask()
            t.filename, t.destination_path, t.destination_name = f, folder, path.rsplit("/", 1)[-1]
            t.automated, t.replace_existing, t.save = True, True, bool(save)
            todo.append((t, path))
    if todo:
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t for t, _ in todo])
        failed = [p for t, p in todo if not EAL.does_asset_exist(p)]
        if failed:
            raise OpError(f"the engine imported nothing at {', '.join(failed)}", code="engine",
                          hint="is it a PCM WAV (16/24-bit)? the editor log has the importer's reason: film-ue log")
    for s in out:
        s["duration_s"] = round(_duration(load(s["path"])), 4)
    return {"changed": bool(todo), "sounds": out}


# --- sequences ------------------------------------------------------------------------------------------------------


def _seq(path: str):
    s = EAL.load_asset(path) if EAL.does_asset_exist(_pkg(path)) else None
    if s is None:
        raise OpError(f"no level sequence {path}", code="not_found",
                      hint="make one with seq.new, or list them with assets.list cls=LevelSequence")
    return s


def _rate(fr) -> float:
    return float(fr.numerator) / float(fr.denominator or 1)


def _fps(seq) -> float:
    return _rate(seq.get_display_rate())


def _ticks_per_frame(seq) -> float:
    return _rate(seq.get_tick_resolution()) / _fps(seq)


def _tracks(seq) -> list:
    return list(seq.find_tracks_by_type(unreal.MovieSceneAudioTrack))


def _track(seq, name: str):
    return next((t for t in _tracks(seq) if str(t.get_display_name()) == name), None)


def db_to_gain(db: float) -> float:
    return 10 ** (float(db) / 20.0)


def gain_to_db(g: float) -> float:
    return 20 * math.log10(g) if g > 0 else -120.0


def _channel_name(ch) -> str:
    """A scripting channel's channel name ("Volume"). Not get_name(): that is the transient UObject's name, made
    unique per call (MakeUniqueObjectName), so it reads "Volume_1", "Volume_2"... while earlier ones live."""
    try:
        return str(ch.get_editor_property("channel_name"))
    except Exception:
        return str(ch.get_name()).rsplit("_", 1)[0] if "_" in str(ch.get_name()) else str(ch.get_name())


def _volume_channel(section):
    for ch in section.get_all_channels():
        if _channel_name(ch).lower() in ("volume", "soundvolume"):
            return ch
    return None


def _describe_section(seq, s) -> dict:
    fps, tpf = _fps(seq), _ticks_per_frame(seq)
    snd = s.get_sound()
    off = s.get_start_offset()
    off_ticks = int(getattr(off, "value", off) or 0)
    ch = _volume_channel(s)
    vol = 1.0
    if ch is not None:
        try:
            vol = float(ch.get_default()) if ch.has_default() else 1.0
        except Exception:
            vol = 1.0
    start, end = int(s.get_start_frame()), int(s.get_end_frame())
    keys = _volume_keys(ch) if ch is not None else []
    fi, fo = fades_of(keys, start, end)
    if keys and (fi or fo):  # the level is the keys' held value, not the default
        vol = max(v for _, v in keys)
    return {"sound": _pkg(snd.get_path_name()) if snd is not None else None, "start_frame": start, "end_frame": end,
            "row": int(s.get_row_index()), "offset_s": round(off_ticks / tpf / fps, 4),
            "volume_db": round(gain_to_db(vol), 2), "fade_in_frames": fi, "fade_out_frames": fo,
            "start_s": round(start / fps, 4), "end_s": round(end / fps, 4)}


def _volume_keys(ch) -> list:
    """[(display frame, linear gain)] of a Volume channel, in time order."""
    out = []
    for k in ch.get_keys():
        t = k.get_time()
        fn = getattr(t, "frame_number", t)
        out.append((int(getattr(fn, "value", fn)), float(k.get_value())))
    return sorted(out)


def fades_of(keys: list, start: int, end: int) -> tuple:
    """Pure: (fade_in_frames, fade_out_frames) from the keys audio.place writes: silence at the clip's start rising
    to the level, and the level falling to silence at its end. 0 when there is no such ramp."""
    fi = fo = 0
    if len(keys) >= 2 and keys[0][0] == start and keys[0][1] <= 1e-4 and keys[1][1] > 1e-4:
        fi = keys[1][0] - start
    if len(keys) >= 2 and keys[-1][0] == end and keys[-1][1] <= 1e-4 and keys[-2][1] > 1e-4:
        fo = end - keys[-2][0]
    return fi, fo


def _linear():
    """EMovieSceneKeyInterpolation.Linear, or None if the Python wrapper does not export the enum (it is a UENUM()
    without BlueprintType; add_key then keys with its default, Auto)."""
    try:
        return unreal.MovieSceneKeyInterpolation.LINEAR
    except AttributeError:
        return None


def fade_keys(start: int, end: int, gain: float, fade_in: int, fade_out: int) -> list:
    """Pure: the Volume keys [(frame, gain)] for a clip's fades (none without fades: the default holds the level)."""
    if not fade_in and not fade_out:
        return []
    if fade_in < 0 or fade_out < 0 or fade_in + fade_out > end - start:
        raise OpError(f"fades of {fade_in}+{fade_out} frames do not fit a {end - start}-frame clip at {start}",
                      code="bad_args", hint="shorten the fades or lengthen the clip")
    keys = [(start, 0.0), (start + fade_in, gain)] if fade_in else [(start, gain)]
    keys += [(end - fade_out, gain), (end, 0.0)] if fade_out else [(end, gain)]
    return [k for i, k in enumerate(keys) if i == 0 or k[0] != keys[i - 1][0]]


@op("audio.describe", mutates=False, idempotent=True, tags=["audio"])
def describe(*, sequence: str) -> dict:
    """A sequence's audio tracks and clips, with frames and seconds.

    Args: sequence: the LevelSequence path.
    Returns: {"sequence", "fps", "tracks": [{"name", "clips": [{"sound", "start_frame", "end_frame", "row",
    "offset_s", "volume_db", "fade_in_frames", "fade_out_frames", "start_s", "end_s"}]}]}.
    Example: film-ue op audio.describe sequence=/Game/Seq/SQ_Main
    """
    seq = _seq(sequence)
    tracks = [{"name": str(t.get_display_name()),
               "clips": sorted((_describe_section(seq, s) for s in t.get_sections()),
                               key=lambda c: (c["start_frame"], c["row"]))} for t in _tracks(seq)]
    return {"sequence": _pkg(sequence), "fps": _fps(seq), "tracks": tracks}


def _clip(c, fps: float) -> dict:
    """A clip in any accepted form as {"sound", "start_frame", "end_frame"?, "offset_s", "volume_db"}."""
    if isinstance(c, (list, tuple)):
        c = {"sound": c[0], "start_frame": c[1]}
    c = dict(c)
    unknown = set(c) - {"sound", "start_frame", "start_s", "end_frame", "duration_s", "offset_s", "volume_db", "id",
                        "start", "end", "offset", "volume", "fade_in_frames", "fade_out_frames"}
    if unknown:
        raise OpError(f"clip {c.get('id') or c.get('sound')}: unknown key(s) {', '.join(sorted(unknown))}",
                      code="bad_args", hint="a clip is {sound, start_frame|start_s, end_frame|duration_s?, offset_s?, "
                                            "volume_db?, fade_in_frames?, fade_out_frames?, id?}")
    if "sound" not in c:
        raise OpError(f"clip {c}: no sound", code="bad_args", hint="give the SoundWave path (audio.import makes it)")
    start = c.get("start_frame", c.get("start"))
    if start is None and "start_s" in c:
        start = round(float(c["start_s"]) * fps)
    if start is None:
        raise OpError(f"clip {c['sound']}: no start_frame or start_s", code="bad_args")
    end = c.get("end_frame", c.get("end"))
    if end is None and "duration_s" in c:
        end = int(start) + int(math.ceil(float(c["duration_s"]) * fps - 1e-6))
    vol = c.get("volume_db")
    if vol is None and "volume" in c:  # seq.audio's linear gain
        vol = gain_to_db(float(c["volume"]))
    return {"sound": _pkg(c["sound"]), "start_frame": int(start), "end_frame": None if end is None else int(end),
            "offset_s": float(c.get("offset_s", c.get("offset", 0.0)) or 0.0), "volume_db": float(vol or 0.0),
            "fade_in_frames": int(c.get("fade_in_frames", 0) or 0), "fade_out_frames": int(c.get("fade_out_frames", 0) or 0)}


def plan_clips(clips: list, durations: dict, fps: float) -> list:
    """Pure: the sections to make, with ends and rows filled in. A clip with no end runs to its sound's end (after
    offset_s); overlapping clips stack on rows (row 0 first), as Sequencer would draw them."""
    out, taken = [], []
    for c in sorted(clips, key=lambda c: c["start_frame"]):
        end = c["end_frame"]
        if end is None:
            end = c["start_frame"] + int(math.ceil((durations[c["sound"]] - c["offset_s"]) * fps - 1e-6))
        if end <= c["start_frame"]:
            raise OpError(f"clip {c['sound']} at {c['start_frame']} is empty (end {end})", code="bad_args",
                          hint="offset_s is past the sound's end, or end_frame is before start_frame")
        row = 0
        while any(r == row and s < end and c["start_frame"] < e for s, e, r in taken):
            row += 1
        taken.append((c["start_frame"], end, row))
        out.append({**c, "end_frame": end, "row": row})
    return out


def _same(have: list, want: list) -> bool:
    key = lambda c: (c["sound"], c["start_frame"], c["end_frame"], c["row"])  # noqa: E731
    if sorted(map(key, have)) != sorted(map(key, want)):
        return False
    hv = {key(c): c for c in have}
    return all(abs(hv[key(c)]["offset_s"] - c["offset_s"]) < 1e-3 and
               abs(hv[key(c)]["volume_db"] - c["volume_db"]) < 0.05 and
               hv[key(c)].get("fade_in_frames", 0) == c.get("fade_in_frames", 0) and
               hv[key(c)].get("fade_out_frames", 0) == c.get("fade_out_frames", 0) for c in want)


@op("audio.place", mutates=True, idempotent=True, tags=["audio", "sequencer"])
def place(*, sequence: str, clips: list, track: str = "Audio", replace: bool = True, extend: bool = False) -> dict:
    """Put sounds on a named audio track of a sequence at their frames; re-running with the same clips changes nothing.

    Args: sequence: LevelSequence path. clips: [{"sound": SoundWave path, "start_frame" (or "start_s"),
    "end_frame" or "duration_s" (default: to the sound's end), "offset_s" (seconds into the sound, default 0),
    "volume_db" (default 0), "fade_in_frames"/"fade_out_frames" (linear ramps from/to silence), "id"?}] or [sound, start_frame] pairs. track: the track's name ("VO", "Music", "SFX").
    replace: the track holds exactly these clips (else they are added to it; one already there at the same frame
    is left as it is). extend: lengthen the playback range
    to the last clip's end.
    Returns: {"changed", "track", "clips": [{"sound", "start_frame", "end_frame", "row", "offset_s", "volume_db"}],
    "end_frame"}.
    Example: film-ue op audio.place sequence=/Game/Seq/SQ_Main track=VO 'clips=[{"sound":"/Game/Audio/VO/L1","start_frame":48}]'
    """
    seq = _seq(sequence)
    fps = _fps(seq)
    want = [_clip(c, fps) for c in clips]
    durations = {}
    for c in want:  # validate every sound before touching the sequence
        if c["sound"] not in durations:
            if not EAL.does_asset_exist(c["sound"]):
                raise OpError(f"no sound {c['sound']}", code="not_found", hint="import it with audio.import")
            durations[c["sound"]] = _duration(load(c["sound"]))
    t = _track(seq, track)
    have = [_describe_section(seq, s) for s in t.get_sections()] if t is not None else []
    if not replace:
        there = {(h["sound"], h["start_frame"]) for h in have}  # adding a clip that is already there is a no-op
        want = [dict(h) for h in have] + [c for c in want if (c["sound"], c["start_frame"]) not in there]
    planned = plan_clips(want, durations, fps)
    for c in planned:  # check fades fit before touching anything
        fade_keys(c["start_frame"], c["end_frame"], 1.0, c["fade_in_frames"], c["fade_out_frames"])
    changed = not (t is not None and _same(have, planned))
    if changed:
        if t is None:
            t = seq.add_track(unreal.MovieSceneAudioTrack)
            if t is None:
                raise OpError(f"could not add an audio track to {sequence}", code="engine")
            t.set_display_name(track)
        for s in list(t.get_sections()):
            t.remove_section(s)
        tpf = _ticks_per_frame(seq)
        for c in planned:
            s = t.add_section()
            s.set_range(c["start_frame"], c["end_frame"])
            s.set_row_index(c["row"])
            s.set_sound(load(c["sound"]))
            if c["offset_s"]:
                s.set_start_offset(unreal.FrameNumber(int(round(c["offset_s"] * fps * tpf))))
            keys = fade_keys(c["start_frame"], c["end_frame"], db_to_gain(c["volume_db"]), c["fade_in_frames"],
                             c["fade_out_frames"])
            if c["volume_db"] or keys:
                ch = _volume_channel(s)
                if ch is None:
                    raise OpError("an audio section has no Volume channel", code="engine")
                ch.set_default(db_to_gain(c["volume_db"]))
                lin = _linear()
                for f, g in keys:  # at most four keys a clip: no batching needed
                    if lin is not None:
                        ch.add_key(unreal.FrameNumber(f), g, 0.0, unreal.MovieSceneTimeUnit.DISPLAY_RATE, lin)
                    else:
                        ch.add_key(unreal.FrameNumber(f), g)
    end = max((c["end_frame"] for c in planned), default=0)
    if extend and end > seq.get_playback_end():
        seq.set_playback_end(end)
        changed = True
    if changed:
        EAL.save_asset(_pkg(sequence))
    return {"changed": changed, "track": track, "clips": [{k: c[k] for k in ("sound", "start_frame", "end_frame",
                                                                             "row", "offset_s", "volume_db",
                                                                             "fade_in_frames", "fade_out_frames")}
                                                          for c in planned], "end_frame": end}


@op("audio.remove", mutates=True, idempotent=True, tags=["audio", "sequencer"])
def remove(*, sequence: str, track: str) -> dict:
    """Remove a named audio track from a sequence (nothing to remove is fine).

    Args: sequence: LevelSequence path. track: the track's name, or "*" for every audio track.
    Returns: {"changed", "removed": [names]}.
    Example: film-ue op audio.remove sequence=/Game/Seq/SQ_Main track=VO
    """
    seq = _seq(sequence)
    gone = [t for t in _tracks(seq) if track == "*" or str(t.get_display_name()) == track]
    for t in gone:
        seq.remove_track(t)
    if gone:
        EAL.save_asset(_pkg(sequence))
    return {"changed": bool(gone), "removed": [str(t.get_display_name()) for t in gone]}


@op("audio.lines", mutates=True, idempotent=True, tags=["audio", "sequencer"])
def lines(*, sequence: str, timing: dict, folder: str = "/Game/Audio/VO", track: str = "VO",
          wav_root: str = "", extend: bool = True, replace: bool = True) -> dict:
    """Import a timing document's voice lines and place each at its frame on one track: the voice, timed, in one call.

    Args: sequence: LevelSequence path. timing: a timing document (filmtools.unreal.audio_timing:
    {"kind": "timing", "fps", "lines": [{"id", "wav", "start_frame", ...}]}). folder: where the SoundWaves go.
    track: the track's name. wav_root: a box directory the lines' relative `wav` paths are under. extend: lengthen
    the playback range to the last line. replace: the track holds exactly these lines (False: they are added to
    what is there, a line already at its frame left alone; for adding one line at a time).
    Returns: {"changed", "lines": [{"id", "sound", "start_frame", "end_frame"}], "fps_note"?}.
    Example: film-ue op audio.lines sequence=/Game/Seq/SQ_Main wav_root=/srv/film/vo timing=@timing.json
    """
    if not isinstance(timing, dict) or "lines" not in timing:
        raise OpError("timing is not a timing document", code="bad_args",
                      hint="make one with filmtools.unreal.audio_timing (film-post timing)")
    seq = _seq(sequence)
    fps = _fps(seq)
    doc_fps = float(timing.get("fps") or fps)
    scale = fps / doc_fps
    wavs = [os.path.join(wav_root, ln["wav"]) if wav_root and not os.path.isabs(ln["wav"]) else ln["wav"]
            for ln in timing["lines"]]
    names = {w: asset_name(ln.get("id") or w) for w, ln in zip(wavs, timing["lines"])}
    imp = import_sounds(files=wavs, folder=folder, names=names)
    clips = [{"sound": s["path"], "start_frame": int(round(ln["start_frame"] * scale)),
              "offset_s": float(ln.get("offset_s", 0.0)), "volume_db": float(ln.get("volume_db", 0.0))}
             for s, ln in zip(imp["sounds"], timing["lines"])]
    placed = place(sequence=sequence, clips=clips, track=track, replace=replace, extend=extend)
    by_start = {(c["sound"], c["start_frame"]): c for c in placed["clips"]}
    out = [{"id": ln.get("id"), "sound": c["sound"], "start_frame": c["start_frame"],
            "end_frame": by_start[(c["sound"], c["start_frame"])]["end_frame"]}
           for ln, c in zip(timing["lines"], clips)]
    res = {"changed": imp["changed"] or placed["changed"], "lines": out}
    if scale != 1:
        res["fps_note"] = f"timing at {doc_fps:g} fps rescaled to the sequence's {fps:g}"
    return res

