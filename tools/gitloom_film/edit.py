"""Place the chosen takes on the film timeline, derive scene and act windows, and assemble the voiceover.

Gaps come from data/edit.json: line / scene / act gaps by boundary type, with per-line overrides. A scene starts
`scene_lead` seconds before its first word, but never before the previous scene's last word has ended. A word starts
at its spoken onset where film-pace measured one (the first word of a line, and any word after a pause; forced
alignment is 0-190 ms off there), and at its aligned start otherwise; ends are the aligned ends. Starts stay in order
and never precede their line's own start.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from .pace import load_selects
from .paths import AUDIO, DATA
from .vo import load_script
from .wav import SR, read_wav, write_wav


def load_takes(script: dict, paced_dir: Path, selects: dict) -> dict[str, dict]:
    out = {}
    for line in script["lines"]:
        k = selects.get(line["id"], {}).get("take", 1)
        p = paced_dir / line["id"] / f"{k}.json"
        if p.exists():
            out[line["id"]] = json.loads(p.read_text())
    return out


def _act_of(script: dict) -> dict[str, str]:
    return {s: a["id"] for a in script["acts"] for s in a["scenes"]}


def place(script: dict, takes: dict[str, dict], cfg: dict) -> dict:
    act_of = _act_of(script)
    t, prev, lines = cfg["lead_in"], None, []
    for line in script["lines"]:
        if line.get("optional") and not cfg.get("optional", {}).get(line["id"], False):
            continue
        if line["id"] not in takes:
            raise KeyError(f"no paced take for {line['id']}")
        tk = takes[line["id"]]
        if prev is None:
            gap = 0.0
        elif act_of[line["scene"]] != act_of[prev["scene"]]:
            gap = cfg["gap"]["act"]
        elif line["scene"] != prev["scene"]:
            gap = cfg["gap"]["scene"]
        else:
            gap = cfg["gap"]["line"]
        gap = cfg.get("overrides", {}).get(line["id"], {}).get("gap_before", gap)
        start = t + gap
        words, prev_ws = [], start
        for w in tk["words"]:
            ws = max(prev_ws, start + (w["onset"] if w.get("onset") is not None else w["start"]))
            words.append({"w": w["w"], "start": round(ws, 4), "end": round(start + w["end"], 4)})
            prev_ws = ws
        lines.append({
            "id": line["id"], "scene": line["scene"], "act": act_of[line["scene"]], "text": line["text"],
            "start": round(start, 4), "end": round(start + tk["duration"], 4), "take": tk["take"],
            "factor": tk.get("factor", 1.0),
            "words": words,
        })
        t, prev = start + tk["duration"], line
    duration = round(t + cfg["tail"], 4)
    scenes = scene_spans(script, lines, duration, cfg["scene_lead"])
    return {"duration": duration, "lines": lines, "scenes": scenes, "acts": act_spans(script, scenes)}


def scene_spans(script: dict, lines: list[dict], duration: float, lead: float) -> list[dict]:
    act_of = _act_of(script)
    order = [s for a in script["acts"] for s in a["scenes"]]
    spans: list[dict] = []
    for i, s in enumerate(order):
        ls = [l for l in lines if l["scene"] == s]
        if not ls:
            raise ValueError(f"scene {s} has no lines")
        if i == 0:
            start = 0.0
        else:
            prev_ls = [l for l in lines if l["scene"] == order[i - 1]]
            start = max(prev_ls[-1]["words"][-1]["end"] + 0.1, ls[0]["words"][0]["start"] - lead)
        spans.append({"id": s, "act": act_of[s], "start": round(start, 4)})
    for i, sp in enumerate(spans):
        sp["end"] = spans[i + 1]["start"] if i + 1 < len(spans) else duration
    return spans


def act_spans(script: dict, scenes: list[dict]) -> list[dict]:
    out = []
    for a in script["acts"]:
        mine = [s for s in scenes if s["id"] in a["scenes"]]
        out.append({"id": a["id"], "name": a["name"], "start": mine[0]["start"], "end": mine[-1]["end"]})
    return out


def assemble(vo: dict, paced_dir: Path, sr: int = SR) -> np.ndarray:
    out = np.zeros(int(math.ceil(vo["duration"] * sr)) + 1, dtype=np.float32)
    for l in vo["lines"]:
        x, _ = read_wav(paced_dir / l["id"] / f"{l['take']}.wav")
        i = int(round(l["start"] * sr))
        n = min(len(x), len(out) - i)
        out[i:i + n] += x[:n]
    return out


def write_vo(vo: dict) -> None:
    (DATA / "vo.json").write_text(json.dumps(vo, indent=1))
    write_wav(AUDIO / "vo" / "vo.wav", assemble(vo, AUDIO / "vo" / "paced"))


def main(argv=None):
    argparse.ArgumentParser(description="Place takes on the timeline and assemble the voiceover").parse_args(argv)
    script = load_script()
    cfg = json.loads((DATA / "edit.json").read_text())
    vo = place(script, load_takes(script, AUDIO / "vo" / "paced", load_selects()), cfg)
    write_vo(vo)
    for a in vo["acts"]:
        print(f"act {a['id']:>3} {a['name']:<12} {a['start']:6.2f} → {a['end']:6.2f}")
    print(f"duration {vo['duration']:.2f}s" + ("" if 85 <= vo["duration"] <= 95 else "   ⚠ outside 85–95 s"))
