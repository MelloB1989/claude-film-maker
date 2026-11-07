"""The karma reel's lips rows for gate r6 (agent-09: every lips curve item was "not measured"), read from what
SEQ_Reel plays on the box after K2c's place. Numbers only.

    cd tools && uv run python ../films/host-studio/reel/r6/lips_numbers.py     # box A, editor up, Studio open

1. lipsync.check on SEQ_Reel per presenter, his L1/L2/L4a and her L3a/L3b/L4b, against the measured cues and stems
   (r5/lips.py: cues.json, vo_<who>.wav on the box) and each line's own solve (AS_reel5_<line>) as the reference.
   The check runs with this tree's perfkit.lipsync for that call (its onset search stops at the line before:
   fleet/agent-01/r6-lipsync-onset), in case the box's bridge predates it.
2. cli_lipsync.gate_numbers on those reports (lag, track_r, measured_against, onset_lead, silences, cues_fresh).
3. lips.lead_in_cm: the upper-to-lower lip gap (FACIAL_C_LipUpper/Lower on the Face) sampled by seq.sample (it
   plays the sequence across ticks, so the face is evaluated: cast_gate's seq.scrub + level.bone read a FROZEN face on
   box A, 0.0 on every line, talking included), mean |change| per frame in the 24 frames before each line's voice
   (clipped to after the speaker's previous line + 4), the worst line. Valid only if every line's lips open >= 0.3 cm
   while it is spoken; otherwise the row is an error, never a 0.

Writes films/host-studio/reel/r6/numbers/lips.json ({"gate": {item: {value, where}}}) and keeps the raw reports
beside it (lips_check_<who>.json, lead_in.json). render_lag_frames / render_conclusive are INFO (no render check).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REEL = HERE.parent
ROOT = REEL.parents[2]
sys.path.insert(0, str(REEL))
sys.path.insert(0, str(REEL / "r5"))

import perf as P  # noqa: E402
import lips as L  # noqa: E402
from filmtools.unreal import client  # noqa: E402

OUT = HERE / "numbers"

CHECK = r"""
import json, importlib.util
import fmbridge.ops.lipsync as OL
P = json.loads(PARAMS)
spec = importlib.util.spec_from_file_location("fmbridge.perfkit.lipsync_r6", P["kit"])
m = importlib.util.module_from_spec(spec)
m.__package__ = "fmbridge.perfkit"
spec.loader.exec_module(m)
old = OL.LS
OL.LS = m
try:
    result = OL.check(**P["args"])
finally:
    OL.LS = old
"""


def check(who: str) -> dict:
    kit = L.box("lipsync_r6.py")
    client.push(str(ROOT / "unreal" / "fmbridge" / "perfkit" / "lipsync.py"), kit)
    args = {"sequence": "/Game/Reel/SEQ_Reel", "label": P.LABEL[who], "wav": L.box(f"vo_{who}.wav"),
            "cues": L.box("cues.json"), "who": who, "reference": L.reference(who)}
    return P.ok(client.exec_code(f"PARAMS = {json.dumps(json.dumps({'kit': kit, 'args': args}))}\n" + CHECK,
                                 timeout=900))


LIP_GAP = ("FACIAL_C_LipUpper", "FACIAL_C_LipLower")


def lead_in(doc: dict) -> dict:
    lines = sorted(doc["lines"].items(), key=lambda kc: kc[1]["voice_frame"])
    worst, report, bad = None, {}, []
    for who in ("him", "her"):
        mine = [(k, c) for k, c in lines if c["who"] == who]
        wins = []
        for i, (k, c) in enumerate(mine):
            f0, f1 = int(round(c["voice_frame"])), int(round(c["end_frame"]))
            lo = max(f0 - 24, int(round(mine[i - 1][1]["end_frame"])) + 4 if i else 0)
            wins.append((k, lo, f0, f1))
        frames = sorted({f for _, lo, f0, f1 in wins for f in list(range(lo - 1, f0)) + list(range(f0, f1 + 1))})
        m = P.ok(client.op("seq.sample", path="/Game/Reel/SEQ_Reel", actor_label=P.LABEL[who], component="Face",
                           bones=list(LIP_GAP), frames=frames, ticks=2, timeout=3600))
        gap = {f: sum((a - b) ** 2 for a, b in zip(m["bones"][LIP_GAP[0]][i][:3], m["bones"][LIP_GAP[1]][i][:3])) ** 0.5
               for i, f in enumerate(frames)}
        for k, lo, f0, f1 in wins:
            d = [abs(gap[f] - gap[f - 1]) for f in range(lo, f0) if f in gap and f - 1 in gap]
            v = sum(d) / len(d) if d else 0.0
            spoken = [gap[f] for f in range(f0, f1 + 1) if f in gap]
            opening = (max(spoken) - min(spoken)) if spoken else 0.0
            report[f"{who} {k}"] = {"silence": [lo, f0 - 1], "mean_change_cm": round(v, 4), "open_cm": round(opening, 3)}
            if opening < 0.3:
                bad.append(f"{who} {k}")
            if worst is None or v > worst[0]:
                worst = (v, f"{who} {k} f{lo}-{f0 - 1}")
    (OUT / "lead_in.json").write_text(json.dumps(report, indent=1))
    if bad or worst is None:
        return {"value": None, "error": f"lip gap does not open while speaking on {bad or 'any line'}: the sample "
                                        f"read a frozen face (lead_in.json)"}
    return {"value": round(worst[0], 4), "where": worst[1]}


def main() -> None:
    from filmtools.unreal.cli_lipsync import gate_numbers
    OUT.mkdir(parents=True, exist_ok=True)
    doc = L.cues()  # refuses stale or unmeasured cues
    reps = {}
    for who in ("him", "her"):
        reps[who] = check(who)
        (OUT / f"lips_check_{who}.json").write_text(json.dumps(reps[who], indent=1))
        print(who, "pass", reps[who]["pass"], [i["message"] for i in reps[who]["issues"]][:4], flush=True)
    stems = {w: L.VO / f"vo_{w}.wav" for w in ("him", "her")}
    g = gate_numbers(reps, {}, doc, stems)["gate"]
    g["lips.render_lag_frames"] = {"value": None, "error": "INFO: the render measure is invalid (07 Nov ruling)"}
    g.pop("lips.render_conclusive", None)
    g["lips.lead_in_cm"] = lead_in(doc)
    (OUT / "lips.json").write_text(json.dumps({"gate": g, "source": "reel/r6/lips_numbers.py on SEQ_Reel"},
                                              indent=1))
    print(json.dumps(g, indent=1))


if __name__ == "__main__":
    main()
