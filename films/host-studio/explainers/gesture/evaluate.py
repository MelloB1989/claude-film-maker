"""agent-09's body rows (qa_perf.body_rows, on fleet/agent-09/r7-perf-gate until it merges) on agent-01's performance
built from the sheet + this timing (round 7, agent-10): the numbers the gate reads, before anything goes to box B.

    python gesture/evaluate.py netflix [--no-timing]
"""
import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPL = HERE.parent
ROOT = EXPL.parents[1]
sys.path.insert(0, str(EXPL))
import gesturekit as G  # noqa: E402
import perform as P  # noqa: E402
import seatkit as S  # noqa: E402

FPS = 30
QA_REL = "tools/filmtools/unreal/qa_perf.py"
QA_BRANCH = __import__("os").environ.get("QA_BRANCH", "origin/fleet/agent-09/r7-explainer-gate")  # the gate the round runs


def qa_perf():
    """agent-09's qa_perf: from this tree once merged, else read from its branch."""
    p = ROOT / QA_REL
    if not p.exists():
        src = subprocess.run(["git", "-C", str(ROOT), "show", f"{QA_BRANCH}:{QA_REL}"], check=True,
                             capture_output=True, text=True).stdout
        p = Path(tempfile.mkdtemp()) / "qa_perf.py"
        p.write_text(src)
    spec = importlib.util.spec_from_file_location("qa_perf", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def performer(film: str, timing):
    who = {"netflix": "her", "whatsapp": "him"}[film]
    sheet = json.loads((EXPL / "acting" / f"{who}.json").read_text())
    cues = json.loads((EXPL / "audio" / film / "cues.json").read_text())
    sk = S.Skeleton.from_read(json.loads((EXPL / "skeletons" / f"{who}_body_read.json").read_text()))
    try:  # gesturekit @2fdfb152+ takes the dict form (gap_merge + gestures); older ones only the list
        plan = G.plan_from_sheet(sheet, cues, timing=timing)
    except AttributeError:
        plan = G.plan_from_sheet(sheet, cues, timing=timing["gestures"] if isinstance(timing, dict) else timing)
    se, _ = S.autotune(sk, P.set_of(who), P.STYLE[who])
    return G.Performer(sk, P.set_of(who), se.sy, plan), cues, sheet


def evaluate(film: str, use_timing: bool = True) -> dict:
    body_rows = qa_perf().body_rows
    who = {"netflix": "her", "whatsapp": "him"}[film]
    tp = EXPL / "acting" / f"timing_{who}.json"
    timing = json.loads(tp.read_text()) if use_timing and tp.exists() else None
    if isinstance(timing, dict) and "gestures" not in timing:
        timing = None
    perf, cues, sheet = performer(film, timing)
    n = int(cues["duration"] * FPS) + 1
    frames, bones = list(range(n)), {"hand_l": [], "hand_r": []}
    clear = {"l": 1e9, "r": 1e9}
    for i in frames:
        F = perf.fk(perf.pose(i / FPS))
        A = {b: perf.actor(v[0]) for b, v in F.items()}
        for b in bones:
            bones[b].append(A[b])
        if perf.plan.speak_w(i / FPS) > 0.5:
            for s in "lr":
                clear[s] = min(clear[s], G.clearance(A, F, s, perf.tor))
    samples = {"frames": frames, "bones": bones}
    speak = [[int(ln["start"] * FPS), int(ln["end"] * FPS) + 1] for ln in cues["lines"]]

    def cut(spans, a, b):
        return [[max(x, int(a * FPS)), min(y, int(b * FPS))] for x, y in spans if y > a * FPS and x < b * FPS]

    on_cam = [[int(ln["t0"] * FPS), int(ln["t1"] * FPS) + 1] for ln in sheet["lines"] if ln.get("on_cam")]
    out = {"whole": body_rows(samples, FPS, speak, perf.set.desk_top),
           "on_cam": body_rows(samples, FPS, [s for s in speak if any(x <= s[0] < y for x, y in on_cam)],
                               perf.set.desk_top)}
    for sp in sheet["test"]["spans"]:
        a, b = sp["f0"] / cues["fps"], sp["f1"] / cues["fps"]
        out[f'{sp["camera"]} {sp["lines"][0]}-{sp["lines"][-1]}'] = body_rows(samples, FPS, cut(speak, a, b),
                                                                              perf.set.desk_top)
    res = {k: {r.split(".")[1]: v.get("value") for r, v in rows.items()} for k, rows in out.items()}
    res["upperarm_torso_clear_cm_min"] = {s: round(v, 2) for s, v in clear.items()}
    res["events"] = len(perf.plan.events)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("film", nargs="?", default="netflix")
    ap.add_argument("--no-timing", action="store_true")
    a = ap.parse_args()
    print(json.dumps(evaluate(a.film, not a.no_timing), indent=1))
