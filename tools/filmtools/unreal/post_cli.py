"""film-post: Unreal renders -> cut -> mix -> deliver, and the line timing that ties the voice, Unreal and post.

    film-post plan SPEC [--json]          every step of a delivery spec (ffmpeg argv included), nothing run
    film-post cut SPEC [--only a,b]       make the deliverables; exit 1 if any output fails its check
    film-post frames SPEC [--json]        which frames each shot must render, and which are missing on disk
    film-post edl SPEC                    the edit as CMX 3600 on stdout
    film-post captions SPEC               the SRT on stdout (needs audio.timing)
    film-post timing --lines L.json | --vo-json data/vo.json | --cues cues.json  [--fps 24] [-o timing.json]
                                          an `audio` timing document (filmtools.unreal.audio_timing)
    film-post handoff TIMING --faces faces.json [--wav-root /box/dir]
                                          per line, speech.to_face's args and where the face animation goes (WP4)

Everything prints JSON with --json (and `timing`/`handoff` always do), so an agent can read it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import audio_timing, post_cut


def _spec(path: str) -> dict:
    try:
        return post_cut.load_spec(path)
    except post_cut.SpecError as e:
        raise SystemExit(f"{path}: {e}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="film-post", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "cut", "frames", "edl", "captions"):
        p = sub.add_parser(name)
        p.add_argument("spec")
        p.add_argument("--json", action="store_true")
        if name == "cut":
            p.add_argument("--only", default="")
    t = sub.add_parser("timing")
    g = t.add_mutually_exclusive_group(required=True)
    g.add_argument("--lines")
    g.add_argument("--vo-json")
    g.add_argument("--cues")
    t.add_argument("--fps", type=float)
    t.add_argument("--name", default="main")
    t.add_argument("--speaker", default="")
    t.add_argument("-o", "--out")
    h = sub.add_parser("handoff")
    h.add_argument("timing")
    h.add_argument("--faces", required=True, help='JSON: {speaker: {"face_mesh", "label", "component"?, "mood"?}}')
    h.add_argument("--wav-root", default="")
    h.add_argument("--mood", default="CONFIDENCE")
    a = ap.parse_args(argv)

    if a.cmd == "timing":
        try:
            if a.lines:
                src = Path(a.lines)
                d = json.loads(src.read_text())
                lines, fps = (d["lines"], a.fps or d.get("fps")) if isinstance(d, dict) else (d, a.fps)
                if not fps:
                    raise SystemExit("--fps: the sequence's frame rate (or an fps key in the lines file)")
                doc = audio_timing.from_lines(lines, float(fps), a.name, src.parent)
            elif a.vo_json:
                if not a.fps:
                    raise SystemExit("--fps: the sequence's frame rate")
                doc = audio_timing.from_vo_json(json.loads(Path(a.vo_json).read_text()), a.fps, speaker=a.speaker,
                                                name=a.name)
            else:
                src = Path(a.cues)
                doc = audio_timing.from_cues_json(json.loads(src.read_text()), a.name, src.parent)
                if a.fps:
                    doc = audio_timing.rescale(doc, a.fps)
        except audio_timing.TimingError as e:
            raise SystemExit(str(e))
        text = json.dumps(doc, indent=1)
        if a.out:
            Path(a.out).write_text(text)
            print(json.dumps({"written": a.out, "lines": len(doc["lines"]), "problems": audio_timing.validate(doc),
                              "same_speaker_overlaps": audio_timing.overlaps(doc)}))
        else:
            print(text)
        return 0
    if a.cmd == "handoff":
        doc = audio_timing.load(a.timing)
        print(json.dumps(audio_timing.performance_handoff(doc, json.loads(Path(a.faces).read_text()), a.mood,
                                                          a.wav_root), indent=1))
        return 0

    spec = _spec(a.spec)
    if a.cmd == "plan":
        steps = post_cut.plan(spec)
        if a.json:
            print(json.dumps({"seconds": post_cut.seconds(spec), "frames": post_cut.length(spec["edl"]),
                              "steps": [s.to_json() for s in steps]}, indent=1))
        else:
            for i, s in enumerate(steps, 1):
                print(f"{i:2d}. {s.what}" + (f"  -> {s.writes}" if s.writes else ""))
        return 0
    if a.cmd == "frames":
        found = post_cut.find_frames(spec)
        res = {"needed": post_cut.frames_needed(spec), "found": sum(1 for v in found.values() if v),
               "missing": post_cut.missing_report(spec, found) or None}
        print(json.dumps(res, indent=1) if a.json else
              f"{res['found']}/{len(found)} frames on disk; missing: {res['missing'] or 'none'}")
        return 0
    if a.cmd == "edl":
        sys.stdout.write(post_cut.cmx3600(spec))
        return 0
    if a.cmd == "captions":
        if not spec["audio"].get("timing"):
            raise SystemExit("captions need audio.timing in the spec")
        doc = audio_timing.load(post_cut.path_of(spec, spec["audio"]["timing"]))
        if float(doc["fps"]) != spec["fps"]:
            doc = audio_timing.rescale(doc, spec["fps"])
        c = spec.get("captions") or {}
        cues = post_cut.caption_cues(doc, int(c.get("max_chars", 64)), int(c.get("hold_frames", 6)))
        srt, _ = post_cut.captions_text(cues, spec["edl"], spec["fps"])
        sys.stdout.write(json.dumps(cues) + "\n" if a.json else srt)
        return 0
    if a.cmd == "cut":
        try:
            rep = post_cut.run(spec, set(filter(None, a.only.split(","))) or None,
                               log=(lambda m: print(m, file=sys.stderr)))
        except post_cut.SpecError as e:
            raise SystemExit(str(e))
        print(json.dumps(rep, indent=1, default=str) if a.json else
              "\n".join(f"{o['name']}: {o['file']} " + ("ok" if not o["problems"] else "; ".join(o["problems"]))
                        for o in rep["outputs"]))
        return 0 if rep["ok"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
