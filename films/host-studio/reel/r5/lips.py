"""Round 5, track T1: the presenters' lip sync, re-done on one timebase and proved (r5/lipsync.md is the plan).

    cd tools && uv run python ../films/host-studio/reel/r5/lips.py voice           # per-line WAVs from the mix's voice
    cd tools && uv run python ../films/host-studio/reel/r5/lips.py cues            # cues from them (local, no box)
    cd tools && uv run python ../films/host-studio/reel/r5/lips.py push            # stems, line WAVs, cues -> the box
    cd tools && uv run python ../films/host-studio/reel/r5/lips.py probe --who him # P1: where round 4's lag entered
    cd tools && uv run python ../films/host-studio/reel/r5/lips.py solve [--only L1]   # mouth-only solve per line WAV
    cd tools && uv run python ../films/host-studio/reel/r5/lips.py bias            # P2: each raw solve's own lag
    cd tools && uv run python ../films/host-studio/reel/r5/lips.py compose --who him   # -> AS_reel_<who>_solve
    cd tools && uv run python ../films/host-studio/reel/r5/lips.py check --who him [--stage face|placed]
    cd tools && uv run python ../films/host-studio/reel/r5/lips.py boxes --who him # mouth boxes for the render check

compose writes AS_reel_<who>_solve, the very asset perf.py naturalize reads, so the rest of perf.py (naturalize, sync,
gaze, place) runs unchanged after it. Every step prints JSON; `check` exits 1 on a fail. Nothing here renders.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REEL = HERE.parent
sys.path.insert(0, str(REEL))
import perf as P  # noqa: E402  the round-4 driver: START, END, names, the box paths
from shots import FPS  # noqa: E402
from vo import MOODS, OUT as VO  # noqa: E402

from filmtools.unreal import client  # noqa: E402

CUES = VO / "cues.json"           # the measured one (lips.py cues), what everything reads
MIX = REEL / "audio" / "mix" / "mix.wav"  # the delivered mix: CANONICAL (the orchestrator, r5): the viewer hears it
SEP = REEL / "audio" / "vo_sep"   # option D (r5): the voice separated from mix.wav (demucs htdemucs), cut per line
R4_STEMS = VO / "r4_stems"        # round 4's stems (the v1 script), kept aside, never mixed or solved from again
UNIT_MOOD: dict = {}  # a WAV holding several lines solves in this mood (none now: D cuts one WAV per line)
LENGTH = {w: P.END + P.POST_ROLL - P.START[w] for w in ("him", "her")}
LENGTH_ALL = P.END + P.POST_ROLL + 24  # the stems' frames (the reel and a second)


def box(*parts: str) -> str:
    return P._j(P.IMPORT, *parts)


def cues() -> dict:
    doc = json.loads(CUES.read_text())
    if not doc.get("measured"):
        raise SystemExit(f"{CUES} is not measured: run `lips.py cues` first")
    from filmtools.unreal.cli_lipsync import stale
    bad = stale(doc, {w: VO / f"vo_{w}.wav" for w in ("him", "her")})
    if bad:
        raise SystemExit(f"cues.json is stale for {bad}: the stems changed since; run `lips.py cues` again")
    return doc


def plan() -> dict:
    """The planned v2 lines (cues_v2.json: who, text, voice_frame, slot_end): never the measured cues.json."""
    return json.loads((REEL / "cues_v2.json").read_text())


def cmd_voice(vocals: Path) -> dict:
    """Option D, step 1: the per-line WAVs cut from the voice separated from the delivered mix (demucs htdemucs
    vocals of audio/mix/mix.wav) into audio/vo_sep/, each checked for its speaker; voice.json is their provenance."""
    from filmtools.unreal.cli_lipsync import lines_from_voice
    lines, issues, man = lines_from_voice(vocals, plan(), SEP, MIX, FPS, "htdemucs (two_stems=vocals)")
    (SEP / "lines.json").write_text(json.dumps({"lines": lines}, indent=1))
    return {"lines": {k: [c["file_frame"], c["voice_frame"], c["voice_frame_planned"], c["f0_hz"]]
                      for k, c in lines.items()}, "leak_db": man.get("leak_db"), "issues": issues,
            "pass": not [i for i in issues if i["severity"] == "fail"]}


def cmd_cues(words: str) -> dict:
    """Option D, step 2: the cues from the line WAVs cut from the mix's voice: stems with each at its cut's place
    (out/.../vo/vo_<who>.wav; round 4's v1 stems kept in vo/r4_stems/), measured, each line located on the mix's
    voice (>= 0.8) and proven to come from THIS mix (voice.json's sha256s)."""
    import shutil
    from filmtools.unreal.cli_lipsync import build_cues, stems_from_lines
    R4_STEMS.mkdir(parents=True, exist_ok=True)
    for w in ("him", "her"):
        if (VO / f"vo_{w}.wav").exists() and not (R4_STEMS / f"vo_{w}.wav").exists():
            shutil.copy2(VO / f"vo_{w}.wav", R4_STEMS / f"vo_{w}.wav")
    cut = json.loads((SEP / "lines.json").read_text())["lines"]
    doc_lines = {"fps": FPS, "frames": plan().get("frames"),
                 "lines": {k: {**c, "place": "file_frame", "voice_frame": c["voice_frame_planned"]}
                           for k, c in cut.items()}}
    stems, _, issues = stems_from_lines(doc_lines, SEP, VO, LENGTH_ALL, FPS)
    man = json.loads((SEP / "voice.json").read_text())
    doc = build_cues(doc_lines, stems, FPS, words, line_dir=SEP, mix=MIX, mix_voice=SEP / "vocals.wav", mix_meta=man)
    doc["issues"] = issues + doc["issues"]
    doc["canonical"] = "mix (separated voice)"
    CUES.write_text(json.dumps(doc, indent=1))
    fails = [i for i in doc["issues"] if i["severity"] == "fail"]
    return {"lines": {k: {"file_frame": c["file_frame"], "voice": [c["voice_frame"], c["end_frame"]],
                          "planned": c.get("voice_frame_planned"), "mix_score": c.get("mix_score"),
                          "words": c["words_source"]} for k, c in doc["lines"].items()},
            "fails": fails, "pass": not fails}


def units(who: str) -> list:
    """The solve units of `who`: one per line WAV, [{"key", "wav", "file_frame", "lines", "mood", "intensity"}]."""
    out = {}
    for k, c in sorted(cues()["lines"].items(), key=lambda kc: kc[1]["file_frame"]):
        if c["who"] != who:
            continue
        u = out.setdefault(c["wav"], {"key": Path(c["wav"]).stem, "wav": c["wav"], "file_frame": c["file_frame"],
                                      "lines": []})
        u["lines"].append(k)
    for u in out.values():
        u["mood"], u["intensity"] = UNIT_MOOD.get(u["wav"]) or MOODS[u["lines"][0]]
    return list(out.values())


def cmd_push() -> list:
    cues()  # refuses stale cues
    d = Path(cues()["line_dir"])
    files = [VO / "vo_him.wav", VO / "vo_her.wav", CUES] + [d / u["wav"] for w in ("him", "her") for u in units(w)]
    return [client.push(str(p), box(p.name)) for p in files]


def check_anim(anim: str, who: str, at_frame: float) -> dict:
    """lipsync.check on an animation whose t=0 plays on master frame `at_frame`, against who's stem from frame 0."""
    return P.ok(client.op("lipsync.check", anim=anim, anim_frame=at_frame, wav=box(f"vo_{who}.wav"),
                          cues=box("cues.json"), who=who, fps=FPS, timeout=600))


def summary(r: dict) -> dict:
    return {"pass": r["pass"], "diagnosis": r["diagnosis"],
            "lines": {k: [v["lag_frames"], v["corr"], v["onset_lead_s"]] for k, v in r["lines"].items()},
            "silence": r["silence"], "issues": [i["message"] for i in r["issues"]]}


def cmd_probe(who: str) -> dict:
    """P1: round 4's face at each stage, against the same stem: the stage where the lag first appears is the bug.
    Expected: the solve in sync (|lag| <= 1); a later stage ~-17 frames on L1."""
    s0 = P.START[who]
    stages = {"1_base_solve": (f"{P.SPEECH}/Anim/AS_{P.anim_name(who)}", s0),
              "2_composed": (f"{P.ANIM}/AS_reel_{who}_solve", s0),
              "3_naturalized": (f"{P.ANIM}/AS_reel_{who}_face", s0),
              "4_follow": (f"{P.ANIM}/AS_reel_{who}_follow", s0),
              "5_final_face": (P.final_face(who), s0)}
    out = {}
    for name, (anim, f) in stages.items():
        try:
            out[name] = summary(check_anim(anim, who, f))
        except SystemExit as e:
            out[name] = {"error": str(e)[:300]}
    lines = json.loads(CUES.read_text())["lines"]
    for k in P.SPLICES[who]:  # the round-4 splice solves alone, at their WAV's place in the mix
        if k not in lines:
            continue
        try:
            out[f"0_line_{k}"] = summary(check_anim(f"{P.SPEECH}/Anim/AS_{P.anim_name(k)}", who,
                                                   lines[k]["file_frame"]))
        except SystemExit as e:
            out[f"0_line_{k}"] = {"error": str(e)[:300]}
    try:
        out["6_placed"] = summary(P.ok(client.op("lipsync.check", sequence="/Game/Reel/SEQ_Reel", label=P.LABEL[who],
                                                 wav=box(f"vo_{who}.wav"), cues=box("cues.json"), who=who,
                                                 timeout=600)))
    except SystemExit as e:
        out["6_placed"] = {"error": str(e)[:300]}
    return out


def line_anim(k: str) -> str:
    return f"{P.SPEECH}/Anim/AS_reel5_{k}"


def cmd_solve(only: list | None) -> dict:
    """One mouth-only solve per line WAV (head off, blinks off: perfkit owns them), in its mood."""
    out = {}
    for who in ("him", "her"):
        mesh = P.face_mesh(who)
        for u in units(who):
            k = u["key"]
            if only and k not in only:
                continue
            r = P.ok(client.op("speech.to_face", wav=box(u["wav"]), name=f"reel5_{k}", face_mesh=mesh,
                               mood=u["mood"], intensity=u["intensity"], process_mask="mouth", head=False,
                               blinks=False, fallback=False, timeout=1800))
            out[k] = {"anim": r["anim"], "timing": r.get("timing"), "options": r.get("options"),
                      "missing": r.get("missing_options")}
            if not (r.get("timing") or {}).get("ok", False):
                print(f"WARNING {k}: {r.get('timing')}", file=sys.stderr)
    return out


def cmd_bias() -> dict:
    """P2: each raw line solve against its own WAV, both on the line's file_frame: the solver's own lag (expected
    |lag| <= 1 frame; the mean is the expected_lag_s later checks may subtract)."""
    doc = cues()
    out = {}
    for who in ("him", "her"):
        for u in units(who):
            ls = [{"id": k, "f0": doc["lines"][k]["voice_frame"], "f1": doc["lines"][k]["end_frame"]}
                  for k in u["lines"]]
            r = P.ok(client.op("lipsync.check", anim=line_anim(u["key"]), anim_frame=u["file_frame"],
                               wav=box(u["wav"]), wav_frame=u["file_frame"], lines=ls, fps=FPS, timeout=600))
            out.update({k: r["lines"][k] for k in u["lines"]})
    lags = [v["raw_lag_s"] for v in out.values()]
    out["mean_lag_s"] = round(sum(lags) / len(lags), 4)
    return out


def cmd_compose(who: str, keep_base: float) -> dict:
    parts = [{"anim": line_anim(u["key"]), "frame": u["file_frame"]} for u in units(who)]
    base = f"{P.SPEECH}/Anim/AS_{P.anim_name(who)}"  # round 4's whole-performance solve: only the canvas
    return P.ok(client.op("lipsync.compose", parts=parts, out=f"{P.ANIM}/AS_reel_{who}_solve", base=base,
                          start_frame=P.START[who], length_frames=LENGTH[who], fps=FPS, keep_base=keep_base,
                          timeout=1800))


def cmd_check(who: str, stage: str) -> dict:
    if stage == "placed":
        r = P.ok(client.op("lipsync.check", sequence="/Game/Reel/SEQ_Reel", label=P.LABEL[who],
                           wav=box(f"vo_{who}.wav"), cues=box("cues.json"), who=who, timeout=600))
    else:
        anim = {"solve": f"{P.ANIM}/AS_reel_{who}_solve", "face": f"{P.ANIM}/AS_reel_{who}_face",
                "final": P.final_face(who)}[stage]
        r = check_anim(anim, who, P.START[who])
    out = P.OUT / f"lips_check_{who}_{stage}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, indent=1))
    s = summary(r)
    print(json.dumps(s, indent=1))
    raise SystemExit(0 if r["pass"] else 1)


def cmd_boxes(who: str) -> dict:
    doc = cues()
    mine = [c for c in doc["lines"].values() if c["who"] == who]
    frames = sorted({f for c in mine for f in range(int(c["voice_frame"] - 30), int(c["end_frame"] + 30))})
    r = P.ok(client.op("lipsync.mouth_boxes", sequence="/Game/Reel/SEQ_Reel", label=P.LABEL[who], frames=frames,
                       timeout=3600))
    out = P.OUT / f"mouth_boxes_{who}.json"
    out.write_text(json.dumps(r, indent=1))
    return {"out": str(out), "frames": len(r["frames"]), "hidden": [f for f, v in r["frames"].items()
                                                                    if not v["visible"]][:20]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["voice", "cues", "push", "probe", "solve", "bias", "compose", "check", "boxes"])
    ap.add_argument("--vocals", type=Path, default=SEP / "vocals.wav", help="demucs vocals of audio/mix/mix.wav")
    ap.add_argument("--who", choices=["him", "her"], default="him")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--stage", default="face", choices=["solve", "face", "final", "placed"])
    ap.add_argument("--words", default="auto", choices=["auto", "whisper", "estimate", "none"])
    ap.add_argument("--keep-base", type=float, default=0.0)
    a = ap.parse_args()
    if a.cmd == "check":
        cmd_check(a.who, a.stage)
    r = {"voice": lambda: cmd_voice(a.vocals), "cues": lambda: cmd_cues(a.words), "push": cmd_push, "probe": lambda: cmd_probe(a.who),
         "solve": lambda: cmd_solve(a.only), "bias": cmd_bias, "compose": lambda: cmd_compose(a.who, a.keep_base),
         "boxes": lambda: cmd_boxes(a.who)}[a.cmd]()
    print(json.dumps(r, indent=1, default=str))


if __name__ == "__main__":
    main()
