"""The karma reel's lips rows for gate r6 (agent-09: every lips curve item was "not measured"), read from what
SEQ_Reel plays on the box after K2c's place. Numbers only.

    cd tools && uv run python ../films/host-studio/reel/r6/lips_numbers.py     # box A, editor up, Studio open

1. lipsync.check on SEQ_Reel per presenter, his L1/L2/L4a and her L3a/L3b/L4b, against the measured cues and stems
   (r5/lips.py: cues.json, vo_<who>.wav on the box) and each line's own solve (AS_reel5_<line>) as the reference.
   The check runs with this tree's perfkit.lipsync for that call (its onset search stops at the line before:
   fleet/agent-01/r6-lipsync-onset), in case the box's bridge predates it.
2. cli_lipsync.gate_numbers on those reports (lag, track_r, measured_against, onset_lead, silences, cues_fresh).
3. lips.lead_in_cm = cast_gate.py lipgap's worst silence motion (cm per frame of the upper-to-lower lip gap on the
   evaluated face, in each speaker's silence before their line).

Writes films/host-studio/reel/r6/numbers/lips.json ({"gate": {item: {value, where}}}) and keeps the raw reports
beside it (lips_check_<who>.json, lipgap.json). render_lag_frames / render_conclusive are INFO (no render check).
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


def main() -> None:
    from filmtools.unreal.cli_lipsync import gate_numbers
    import cast_gate as CG
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
    gap = CG.lipgap(str(OUT / "lipgap.json"))
    worst = max(((v["off_cm"], k) for k, v in gap["lines"].items()), default=None)
    g["lips.lead_in_cm"] = ({"value": round(worst[0], 4), "where": f"{worst[1]} (silence before the line)"} if worst
                            else {"value": None, "error": "lipgap measured no line"})
    (OUT / "lips.json").write_text(json.dumps({"gate": g, "source": "reel/r6/lips_numbers.py on SEQ_Reel"},
                                              indent=1))
    print(json.dumps(g, indent=1))


if __name__ == "__main__":
    main()
