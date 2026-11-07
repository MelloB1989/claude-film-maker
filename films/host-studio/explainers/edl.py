"""The explainers' edit: each film's shots as runs of VO lines, resolved against the cue sheet (audio/<film>/cues.json)
into frames. Re-run after any VO rebuild and every cut moves with the voice.

    python3 films/host-studio/explainers/edl.py            # -> edl/<film>.json + edl/<film>.csv for both films

A shot is (kind, first line, last line, what):
- "pres":  the presenter alone on camera `what` (CAM_MCU | CAM_CU | CAM_WIDE);
- "panel": the presenter on camera `what[0]`, framed left, with the graphic `what[1]`'s alpha side panel on the right;
- "gfx":   graphic scene `what` full frame (the graphics films' shot ids, films/explain-<film>/).
Cuts sit in the middle of the pause between two lines (sentence boundaries); the first shot starts at 0 and the last
runs to the end card, which holds END frames over the VO's tail. Captions: word-by-word chunks on "pres" and "panel"
shots (composite.py draws them); a "gfx" shot carries its own on-screen words.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
END = 36  # end card: the last 1.5 s

PLANS = {
    "whatsapp": [
        ("pres", "W01", "W01", "CAM_MCU"),            # hook on him: "over a hundred billion"
        ("gfx", "W02", "W02", "title"),               # the title over "almost none of them stay"
        ("pres", "W03", "W03", "CAM_CU"),             # "Here's how." punched in
        ("panel", "W04", "W04", ("CAM_MCU", "connect")),
        ("gfx", "W05", "W06", "erlang"),              # one process per connection; 2 million on one server
        ("pres", "W07", "W07", "CAM_WIDE"),           # "You hit send. Is your friend online?"
        ("gfx", "W08", "W09", "store"),               # straight down / waits / delivered -> deleted
        ("panel", "W10", "W11", ("CAM_MCU", "ticks")),
        ("gfx", "W12", "W12", "group"),               # encrypt once, server fans out
        ("pres", "W13", "W13", "CAM_CU"),             # "the server can't read a word of it"
        ("gfx", "W14", "W14", "e2e"),                 # Signal keys on the phones
        ("panel", "W15", "W15", ("CAM_MCU", "media")),
        ("pres", "W16", "W16", "CAM_MCU"),            # the recap, on him
        ("pres", "W17", "W17", "CAM_CU"),             # the closing line, on him
        ("gfx", None, None, "end"),
    ],
    "netflix": [
        ("pres", "N01", "N01", "CAM_MCU"),            # hook on her: "over three hundred million"
        ("pres", "N02", "N02", "CAM_CU"),             # "Hit play, and it just starts."
        ("gfx", "N03", "N03", "title"),               # "doesn't come from the cloud"
        ("pres", "N04", "N04", "CAM_MCU"),            # "builds its own servers"
        ("gfx", "N05", "N05", "oca"),                 # the box inside the ISP
        ("panel", "N06", "N07", ("CAM_MCU", "prefill")),
        ("pres", "N08", "N08", "CAM_CU"),             # "encoded at many sizes and bitrates"
        ("gfx", "N09", "N09", "ladder"),              # cartoon vs action ladders
        ("gfx", "N10", "N11", "abr"),                 # chunks, a rung per chunk
        ("panel", "N12", "N12", ("CAM_MCU", "buffer")),
        ("pres", "N13", "N13", "CAM_WIDE"),           # "all of that runs on AWS"
        ("gfx", "N14", "N14", "planes"),              # AWS points you to the box; the box streams
        ("pres", "N15", "N15", "CAM_MCU"),            # the recap, on her
        ("pres", "N16", "N16", "CAM_CU"),             # the closing line, on her
        ("gfx", None, None, "end"),
    ],
}


def resolve(film: str) -> dict:
    cues = json.loads((HERE / "audio" / film / "cues.json").read_text())
    lines = {ln["id"]: ln for ln in cues["lines"]}
    order = [ln["id"] for ln in cues["lines"]]
    total = cues["frames"]
    plan = PLANS[film]
    covered = [i for k, a, b, _ in plan if a for i in order[order.index(a):order.index(b) + 1]]
    assert covered == order, f"{film}: the plan must cover every line once, in order"
    shots, f = [], 0
    body = [s for s in plan if s[1]]
    for n, (kind, a, b, what) in enumerate(body):
        if n + 1 < len(body):
            nxt = lines[body[n + 1][1]]
            f1 = (lines[b]["end_f"] + nxt["start_f"]) // 2
        else:
            f1 = total - END
        shot = {"n": n + 1, "kind": kind, "f0": f, "f1": f1, "frames": f1 - f, "lines": order[order.index(a):order.index(b) + 1]}
        if kind == "pres":
            shot["camera"] = what
        elif kind == "panel":
            shot["camera"], shot["gfx"] = what
        else:
            shot["gfx"] = what
        shot["text"] = " ".join(lines[i]["text"] for i in shot["lines"])
        # every word on the shot's own clock (frame 0 = the shot's first frame): what a graphic lands its beats on
        shot["words"] = [{"w": w["w"], "f": w["f0"] - f, "f_end": w["f1"] - f, "line": i}
                         for i in shot["lines"] for w in lines[i]["words"]]
        shots.append(shot)
        f = f1
    shots.append({"n": len(shots) + 1, "kind": "gfx", "gfx": "end", "f0": f, "f1": total, "frames": total - f,
                  "lines": [], "text": "", "words": []})
    on = sum(s["frames"] for s in shots if s["kind"] == "pres")
    pan = sum(s["frames"] for s in shots if s["kind"] == "panel")
    return {"film": film, "fps": cues["fps"], "frames": total, "duration": cues["duration"], "vo": cues["vo"],
            "presenter": cues["presenter"], "share": {"presenter": round(on / total, 3), "panel": round(pan / total, 3),
                                                      "gfx": round(1 - (on + pan) / total, 3)},
            "shots": shots}


# Thinking glances off-lens (agent-04's head plan): phrase starts on camera where a beat of thought suits the words.
THINK = {"whatsapp": [("W07", "Is"), ("W10", "Your"), ("W15", "Photos")],
         "netflix": [("N06", "Every"), ("N08", "Each"), ("N13", "Your")]}
WHO = {"whatsapp": "him", "netflix": "her"}


def head_cues(film: str, e: dict) -> dict:
    """agent-04's cue JSON: VO t=0 sits on sequence frame 0; words and on-camera spans in seconds."""
    cues = json.loads((HERE / "audio" / film / "cues.json").read_text())
    lines = {ln["id"]: ln for ln in cues["lines"]}
    fps = e["fps"]
    think = [next(w["start"] for w in lines[i]["words"] if w["w"].strip(",.?:!").startswith(word)) for i, word in THINK[film]]
    return {"film": film, "fps": fps, "start": 0, "length_s": e["duration"],
            "words": [{"w": w["w"], "t0": w["start"], "t1": w["end"], "line": ln["id"]} for ln in cues["lines"] for w in ln["words"]],
            "on_cam": [[round(s["f0"] / fps, 4), round(s["f1"] / fps, 4), s["camera"] + ("_L" if s["kind"] == "panel" else "")]
                       for s in e["shots"] if s["kind"] in ("pres", "panel")],
            "think": think}


def main() -> None:
    (HERE / "edl").mkdir(exist_ok=True)
    for film in PLANS:
        e = resolve(film)
        (HERE / "edl" / f"{film}.json").write_text(json.dumps(e, indent=1) + "\n")
        with (HERE / "edl" / f"{film}.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["n", "kind", "camera", "gfx", "f0", "f1", "t0", "t1", "lines", "text"])
            for s in e["shots"]:
                w.writerow([s["n"], s["kind"], s.get("camera", ""), s.get("gfx", ""), s["f0"], s["f1"],
                            f"{s['f0'] / e['fps']:.3f}", f"{s['f1'] / e['fps']:.3f}", " ".join(s["lines"]), s["text"]])
        (HERE / "cues").mkdir(exist_ok=True)
        (HERE / "cues" / f"{WHO[film]}.json").write_text(json.dumps(head_cues(film, e), indent=1) + "\n")
        print(film, e["frames"], e["share"])
        for s in e["shots"]:
            print(f"  {s['n']:2} {s['kind']:5} {s.get('camera', ''):8} {s.get('gfx', ''):8} {s['f0']:5}-{s['f1']:5} {' '.join(s['lines'])}")


if __name__ == "__main__":
    main()
