"""Round 5, track T1: the presenters' lip sync, re-done on one timebase and proved (r5/lipsync.md is the plan).

    cd tools && uv run python ../films/host-studio/reel/r5/lips.py cues            # cues from the MIX (local, no box)
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
R4_STEMS = VO / "r4_stems"        # round 4's stems, kept aside: they placed L1 ~14 frames before the mix
# The solve units: one per line WAV. Only L1, L2, L3, L4a, L4b.wav exist (Nov 1): L3 holds L3a + L3b, solved whole
# and placed once (its mood the longer part's, L3b's); cues split it at its pause for captions and checks.
UNIT_MOOD = {"L3.wav": MOODS["L3b"]}
LENGTH = {w: P.END + P.POST_ROLL - P.START[w] for w in ("him", "her")}


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


def plan_lines() -> dict:
    """The line list from the plan (cues_v2.json, never the measured cues.json: a second run would take its
    measured frames as the plan), mapped onto the line WAVs that exist; L3a + L3b -> L3.wav with a split."""
    plan = json.loads((REEL / "cues_v2.json").read_text())
    lines = dict(plan["lines"])
    if not (VO / "L3a.wav").exists() and (VO / "L3.wav").exists():
        a, b = lines.pop("L3a"), lines.pop("L3b")
        lines["L3"] = {**a, "wav": "L3.wav", "text": f"{a['text']} {b['text']}", "split": [
            {"id": "L3a", "text": a["text"], "voice_frame": a["voice_frame"], "mood": a["mood"],
             "intensity": a["intensity"], "slot_end": a["slot_end"]},
            {"id": "L3b", "text": b["text"], "voice_frame": b["voice_frame"], "mood": b["mood"],
             "intensity": b["intensity"], "slot_end": b["slot_end"]}]}
    missing = [c["wav"] for c in lines.values() if not (VO / c["wav"]).exists()]
    if missing:
        raise SystemExit(f"line WAVs missing in {VO}: {missing}")
    return {**plan, "lines": lines}


def cmd_cues(words: str) -> dict:
    """Cues from the delivered mix: each line WAV located in mix.wav, the voice stems rebuilt there (out/.../vo/
    vo_<who>.wav, round 4's kept in vo/r4_stems/ and checked against the mix: they must FAIL on L1), measured."""
    import shutil
    from filmtools.unreal.cli_lipsync import cues_from_mix
    R4_STEMS.mkdir(parents=True, exist_ok=True)
    for w in ("him", "her"):
        if (VO / f"vo_{w}.wav").exists() and not (R4_STEMS / f"vo_{w}.wav").exists():
            shutil.copy2(VO / f"vo_{w}.wav", R4_STEMS / f"vo_{w}.wav")
    old = {w: R4_STEMS / f"vo_{w}.wav" for w in ("him", "her") if (R4_STEMS / f"vo_{w}.wav").exists()}
    doc = cues_from_mix(plan_lines(), VO, MIX, VO / "mix_aligned", old, FPS, words)
    for w, info in doc["stems"].items():  # what perf.py, the checks and the gate read
        shutil.copy2(info["path"], VO / f"vo_{w}.wav")
        info["path"] = str(VO / f"vo_{w}.wav")
    CUES.write_text(json.dumps(doc, indent=1))
    fails = [i for i in doc["issues"] if i["severity"] == "fail"]
    return {"lines": {k: {"file_frame": c["file_frame"], "voice": [c["voice_frame"], c["end_frame"]],
                          "planned": c.get("voice_frame_planned"), "mix_score": c.get("mix_score"),
                          "words": c["words_source"]} for k, c in doc["lines"].items()},
            "fails": fails, "old_stems": doc.get("old_stems"), "pass": not fails}


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
    files = [VO / "vo_him.wav", VO / "vo_her.wav", CUES] + [VO / u["wav"] for w in ("him", "her") for u in units(w)]
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
    ap.add_argument("cmd", choices=["cues", "push", "probe", "solve", "bias", "compose", "check", "boxes"])
    ap.add_argument("--who", choices=["him", "her"], default="him")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--stage", default="face", choices=["solve", "face", "final", "placed"])
    ap.add_argument("--words", default="auto", choices=["auto", "whisper", "estimate", "none"])
    ap.add_argument("--keep-base", type=float, default=0.0)
    a = ap.parse_args()
    if a.cmd == "check":
        cmd_check(a.who, a.stage)
    r = {"cues": lambda: cmd_cues(a.words), "push": cmd_push, "probe": lambda: cmd_probe(a.who),
         "solve": lambda: cmd_solve(a.only), "bias": cmd_bias, "compose": lambda: cmd_compose(a.who, a.keep_base),
         "boxes": lambda: cmd_boxes(a.who)}[a.cmd]()
    print(json.dumps(r, indent=1, default=str))


if __name__ == "__main__":
    main()
