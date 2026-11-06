"""Lip-sync in the editor: measure WHEN a face's mouth moves against its voice (perfkit.lipsync), on an animation or
on what a sequence actually plays; build a performance's mouth from per-line solves placed at their cues; and project
a speaker's mouth into the shot cameras for the video-level check (film-ue lips render).

    lipsync.check     per line: lag (frames), correlation, onset lead; the silences; one diagnosis. FAILS on
                      |lag| > 1 frame, r < 0.35, a mouth that opens > 0.25 s ahead or talks in a silence
    lipsync.compose   the speech curves of a performance from per-line solves at their cues, rest between lines
    lipsync.mouth_boxes  the speaker's mouth box (0..1) per frame through the camera the edit shows

Times: frames are the sequence's display frames (24 fps on the reel); seconds are frames / fps from frame 0.
docs/unreal/research/lipsync.md says why each limit is what it is.
"""
from __future__ import annotations

import json
import os

import unreal

from . import op
from .assets import EAL, free, load
from ..errors import OpError, not_found
from ..perfkit import audio as AU
from ..perfkit import lipsync as LS

LSE = unreal.LevelSequenceEditorBlueprintLibrary


def _lines(lines, cues: str, who: str, fps: float) -> list:
    """[{"id", "t0", "t1"}] (s) from `lines` ({"id", "t0", "t1"} s, or {"id", "f0", "f1"} frames) or a cues.json on
    the box (its measured voice_frame/end_frame per line of `who`)."""
    out = []
    if cues:
        if not os.path.exists(cues):
            raise not_found("cues.json", cues, hint="push the cues built by `film-ue lips cues` to the box")
        doc = json.load(open(cues))
        if not doc.get("measured"):
            raise OpError(f"{cues} was not measured from the placed audio (no \"measured\": true)", code="bad_args",
                          hint="rebuild it: film-ue lips cues (VAD on the stems at their mix positions, words)")
        for k, c in doc["lines"].items():
            if who and c.get("who") != who:
                continue
            rec = {"id": k, "t0": c["voice_frame"] / fps, "t1": c["end_frame"] / fps}
            if c.get("words") and c.get("words_source") not in (None, "estimate", "none"):
                rec["words"] = [[w["start"] / fps, w["end"] / fps] for w in c["words"]]
            out.append(rec)
    for x in lines or []:
        if "t0" in x:
            out.append({"id": x["id"], "t0": float(x["t0"]), "t1": float(x["t1"])})
        else:
            out.append({"id": x["id"], "t0": float(x["f0"]) / fps, "t1": float(x["f1"]) / fps})
    if not out:
        raise OpError("no lines to check", code="bad_args", hint="pass lines=[{id, f0, f1}] or cues=<path> who=<who>")
    return out


def _anim_curves(a) -> dict:
    from .anim import read_all
    return read_all(a)


def _face_sections(seq, label: str, component: str) -> list:
    """The skeletal animation sections on `label`.`component` in `seq`: [{anim, f0, f1, offset_s, rate, row}]."""
    from .anim import section_offset_s
    from .seq import _comp_binding
    fps = seq.get_display_rate().numerator / seq.get_display_rate().denominator
    tick = seq.get_tick_resolution().numerator / seq.get_tick_resolution().denominator
    b = _comp_binding(seq, label, component, create=False)
    if b is None:
        raise not_found(f"{component} binding of", label, hint="seq.anim puts the face animation on it")
    out = []
    for t in b.find_tracks_by_type(unreal.MovieSceneSkeletalAnimationTrack):
        for s in t.get_sections():
            prm = s.get_editor_property("params")
            a = prm.get_editor_property("animation")
            if a is None:
                continue
            rate = prm.get_editor_property("play_rate")
            rate = rate.to_fixed_play_rate() if hasattr(rate, "to_fixed_play_rate") else rate
            out.append({"anim": a.get_path_name().split(".")[0],
                        "f0": s.get_start_frame() if s.has_start_frame() else seq.get_playback_start(),
                        "f1": s.get_end_frame() if s.has_end_frame() else seq.get_playback_end(),
                        "offset_s": round(section_offset_s(prm, tick), 4), "rate": float(rate),
                        "row": s.get_row_index(), "active": s.is_active(), "fps": fps})
    return out


def _audio_sections(seq) -> list:
    """Every audio section on the sequence (master tracks): sound, start frame, start offset (frames)."""
    fps = seq.get_display_rate().numerator / seq.get_display_rate().denominator
    tick = seq.get_tick_resolution().numerator / seq.get_tick_resolution().denominator
    out = []
    try:
        tracks = seq.find_tracks_by_type(unreal.MovieSceneAudioTrack)
    except Exception:
        tracks = []
    for t in tracks:
        for s in t.get_sections():
            snd = s.get_sound()
            try:
                off = s.get_start_offset().value / tick * fps
            except Exception:
                off = None
            out.append({"sound": snd.get_path_name().split(".")[0] if snd else None,
                        "f0": s.get_start_frame() if s.has_start_frame() else None,
                        "start_offset_frames": round(off, 3) if off is not None else None})
    return out


@op("lipsync.check", mutates=False, idempotent=True, tags=["qa"])
def check(*, wav: str, lines: list | None = None, cues: str = "", who: str = "", anim: str = "", sequence: str = "",
          label: str = "", component: str = "Face", wav_frame: float = 0.0, anim_frame: float = 0.0, fps: float = 0.0,
          expected_lag_s: float = 0.0, limits: dict | None = None, span_frames: list | None = None) -> dict:
    """Lip-sync of one face against its voice: per line the lag between the voice's syllable rhythm and the mouth's
    opening (frames; < 0 = the mouth is EARLY), their correlation, how early the mouth starts, and the mouth in the
    silences. FAILS on |lag| > 1 frame, r < 0.35, an opening more than 0.25 s ahead of the first sound, or talking
    in a silence (open > 0.10 or busier than 25% of the lines). Each issue says what to do; `diagnosis` says whether
    it is one offset (misplaced section/audio), a drift (a frame-rate mismatch) or per line.

    What it reads (one of):
      sequence + label: what the sequence PLAYS on label.component (every skeletal animation section, with its start,
        offset and play rate): the placed face, as the render will show it. Also lists the sequence's audio sections.
      anim: an animation alone, its t=0 on master frame `anim_frame` (a solve right after speech.to_face: anim_frame =
        wav_frame, so the solver's own lag is measured; pass it as expected_lag_s to later checks).
    wav: the voice on the box, its first sample on master frame `wav_frame` (a 65 s stem from frame 0: 0; a line's WAV:
      its cue's file_frame). lines: [{"id", "f0", "f1"}] speech onset/offset frames, or cues=<cues.json on the box>
      who=<who> (it must be a measured one: film-ue lips cues). fps: default the sequence's, else 24.

    Returns {"pass", "lines": {id: {lag_frames, corr, onset_lead_s, ...}}, "silences", "issues", "diagnosis",
    "sections"?, "audio"?}.
    Example: film-ue op lipsync.check sequence=/Game/Reel/SEQ_Reel label=Host wav=/srv/ue/vo/vo_him.wav cues=/srv/ue/vo/cues.json who=him
    """
    if not os.path.exists(wav):
        raise not_found("WAV file", wav, hint="push it to the box (client.push); the path is on the box")
    res: dict = {}
    if sequence:
        if not label:
            raise OpError("sequence needs label (the speaker's actor)", code="bad_args")
        seq = load(sequence)
        if seq is None:
            raise not_found("level sequence", sequence)
        fps = fps or seq.get_display_rate().numerator / seq.get_display_rate().denominator
        secs = [s for s in _face_sections(seq, label, component) if s["active"]]
        if not secs:
            raise OpError(f"{label}.{component} plays no animation in {sequence}", code="bad_args",
                          hint="place the face first (seq.anim)")
        placed = []
        for s in secs:
            cur = _anim_curves(load(s["anim"]))
            t0, t1 = s["f0"] / fps, s["f1"] / fps
            placed.append((t0, t1, LS.place(cur, t0, s["offset_s"], s["rate"] or 1.0, end_s=t1)))
        curves = LS.merge_sections(placed)
        res["sections"] = secs
        res["audio"] = _audio_sections(seq)
        odd = [s for s in secs if abs(s["rate"] - 1.0) > 1e-6]
        if odd:
            res["warnings"] = [f"{s['anim']} plays at rate {s['rate']}: a face must play at 1.0" for s in odd]
    elif anim:
        if not EAL.does_asset_exist(anim.split(".")[0]):
            raise not_found("animation", anim)
        fps = fps or 24.0
        curves = LS.place(_anim_curves(load(anim)), anim_frame / fps)
    else:
        raise OpError("give sequence+label or anim", code="bad_args")
    env = AU.Envelope.from_wav(wav, offset_s=wav_frame / fps)
    ls = _lines(lines, cues, who, fps)
    span = (span_frames[0] / fps, span_frames[1] / fps) if span_frames else None
    rep = LS.check(env, curves, ls, fps=fps, limits=limits, expected_lag_s=expected_lag_s, span=span)
    return {**rep, **res, "fps": fps, "wav": wav, "wav_frame": wav_frame}


@op("lipsync.compose", mutates=True, idempotent=True, tags=["slow"])
def compose(*, parts: list, out: str, length_frames: float, start_frame: float = 0.0, fps: float = 24.0,
            base: str = "", keep_base: float = 0.0, fade_frames: float = 3.0, skeleton: str = "") -> dict:
    """A performance's mouth from per-line solves, each at its cue: one timebase, no talking in the silences.

    parts: [{"anim": a line's speech.to_face result, "frame": the master frame its WAV starts on (cues' file_frame)}].
    The animation `out` runs from master frame `start_frame` for `length_frames`: a copy of `base` (the performance
    the head/eyes/blinks are layered on: perf.face runs after this) with its speech curves (jaw, lips, tongue; not
    the smile layer) replaced, or a new animation on `skeleton`. Between lines the mouth rests (keep_base > 0 keeps
    that share of base's own mouth there, for breaths); each line fades in/out over `fade_frames` at its WAV's ends
    (a line WAV starts ~50 ms before its first sound, vo.py). Run lipsync.check on the result before layering.

    Returns {"out", "curves", "parts": [[anim, frame, seconds]], "changed"}.
    Example: film-ue op lipsync.compose out=/Game/Reel/Perf/AS_reel_him_mouth base=/Game/Speech/Anim/AS_reel_him start_frame=960 length_frames=624 'parts=[{"anim":"/Game/Speech/Anim/AS_reel_L1","frame":1018.8}]'
    """
    from .anim import _write, new as anim_new, read_all
    if not parts:
        raise OpError("no parts", code="bad_args", hint="parts=[{anim, frame}] per line")
    got = []
    for p in parts:
        if not EAL.does_asset_exist(p["anim"].split(".")[0]):
            raise not_found("line animation", p["anim"], hint="speech.to_face the line first")
        a = load(p["anim"])
        got.append(((float(p["frame"]) - start_frame) / fps, read_all(a)))
    length_s = length_frames / fps
    base_cur = None
    free(out)
    if base:
        if not EAL.does_asset_exist(base.split(".")[0]):
            raise not_found("base animation", base)
        if not EAL.duplicate_asset(base.split(".")[0], out):
            raise OpError(f"could not copy {base} to {out}", code="engine")
        base_cur = read_all(load(out))
    else:
        skel = skeleton or load(parts[0]["anim"]).get_skeleton().get_path_name().split(".")[0]
        anim_new(path=out, skeleton=skel, length_s=length_s, fps=30, replace=True)
    cur = LS.compose(got, length_s, rate=30.0, fade_s=fade_frames / fps, base=base_cur, keep_base=keep_base)
    if base_cur:  # speech curves the base has but no line drives: rest them too
        for n in base_cur:
            if LS.is_speech_curve(n) and n not in cur:
                cur[n] = ([0.0, length_s], [0.0, 0.0])
    o = load(out)
    _write(o, cur)
    EAL.save_asset(out)
    return {"out": out, "curves": len(cur), "parts": [[p["anim"], p["frame"], round(t, 3)] for p, (t, _) in
                                                      zip(parts, got)], "changed": True}


@op("lipsync.mouth_boxes", mutates=False, idempotent=True, tags=["qa", "slow"])
def mouth_boxes(*, sequence: str, label: str, frames: list, component: str = "Face", camera: str = "",
                bones: list | None = None, pad: float = 0.6, ticks: int = 2):
    """Where `label`'s mouth is in the picture, per frame: through `camera` or (default) the camera the edit shows on
    that frame, the mouth's corner/lip/jaw bones projected (cam.project's lens model) to a square box (0..1 from the
    top left) padded by `pad` x its size, for the video check's crop (film-ue lips render --boxes). A multi-tick
    job. Bones default to the MetaHuman face's FACIAL_C_Jaw, FACIAL_L/R_LipCorner, FACIAL_C_LipUpper/LipLower.

    Returns {"frames": {frame: {"camera", "box": [x0, y0, x1, y1], "visible"}}}.
    Example: film-ue op lipsync.mouth_boxes sequence=/Game/Reel/SEQ_Reel label=Host 'frames=[1000,1001]'
    """
    from ..camkit import lens
    from .cam import read as cam_read
    from .seq import _xform, component_of, cut_camera
    bones = bones or ["FACIAL_C_Jaw", "FACIAL_L_LipCorner", "FACIAL_R_LipCorner", "FACIAL_C_LipUpper",
                      "FACIAL_C_LipLower"]
    LSE.open_level_sequence(load(sequence))
    LSE.set_current_time(int(frames[0]) + 1)
    yield
    out = {}
    for f in frames:
        LSE.set_current_time(int(f))
        for _ in range(ticks):
            yield
        cam_label = camera or cut_camera(sequence, f)
        cam = cam_read(cam_label)
        comp = component_of(label, component)
        pts = []
        for b in bones:
            try:
                x = _xform(comp, b)
            except Exception:
                continue
            q = lens.project(cam, x[:3])
            if q["depth"] > 0:
                pts.append((q["u"], q["v"]))
        if len(pts) < 2:
            out[str(f)] = {"camera": cam_label, "box": None, "visible": False}
            continue
        us, vs = [p[0] for p in pts], [p[1] for p in pts]
        cu, cv = (min(us) + max(us)) / 2, (min(vs) + max(vs)) / 2
        aspect = cam["filmback"][0] / cam["filmback"][1]
        half_u = max(max(us) - min(us), (max(vs) - min(vs)) / aspect) * (0.5 + pad)
        half_v = half_u * aspect
        box = [round(cu - half_u, 4), round(cv - half_v, 4), round(cu + half_u, 4), round(cv + half_v, 4)]
        out[str(f)] = {"camera": cam_label, "box": box,
                       "visible": 0.0 <= cu <= 1.0 and 0.0 <= cv <= 1.0}
    return {"frames": out, "bones": bones}
