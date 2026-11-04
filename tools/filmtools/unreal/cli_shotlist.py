"""film-ue shotlist: a shot list (kind shot) offline: its shots resolved to frames and cameras, and the pipeline
that shoots, renders and reviews it (WP7 + WP9 + WP10) as one multi-document YAML for `film-ue apply`.

    film-ue shotlist table SPEC [--json]                 # shots, frames, cameras, sizes (no editor)
    film-ue shotlist pipeline SPEC --out /srv/renders [--preset draft] [--level /Game/Maps/Set] [--per-shot 2]
                     [--no-review] [--review-mode capture|mrq] [--h264] [-o pipeline.yaml]
"""
from __future__ import annotations

import json
import sys

NAMES = ("shotlist",)


def register(sub) -> None:
    p = sub.add_parser("shotlist", help="a shot list offline: its table, or the shoot -> render -> review pipeline")
    s = p.add_subparsers(dest="shotlist_cmd", required=True)
    t = s.add_parser("table", help="the shots resolved to frames, cameras and sizes (no editor)")
    t.add_argument("spec")
    t.add_argument("--json", action="store_true")
    q = s.add_parser("pipeline", help="the shot spec + a render + a review per shot, as one YAML for film-ue apply")
    q.add_argument("spec")
    q.add_argument("--out", required=True, help="the box folder renders and reviews go under")
    q.add_argument("--preset", default="draft", help="render preset (render.presets): preview, draft, final, ...")
    q.add_argument("--level", default="")
    q.add_argument("--per-shot", type=int, default=2, help="review frames per shot")
    q.add_argument("--no-review", action="store_true")
    q.add_argument("--review-mode", default="capture", help="view.still mode for the review (capture, mrq)")
    q.add_argument("--h264", action="store_true", help="also encode an H.264 review video with the render")
    q.add_argument("-o", "--output", default="-", help="file to write (default stdout)")


def _load(path: str) -> dict:
    import yaml
    with open(path) as f:
        docs = [d for d in yaml.safe_load_all(f) if d]
    shots = [d for d in docs if d.get("kind") == "shot"]
    if len(shots) != 1:
        raise SystemExit(f"{path}: expected one kind: shot document, found {len(shots)}")
    return shots[0]


def dispatch(a) -> bool:
    if getattr(a, "cmd", None) not in NAMES:
        return False
    from . import cam_kind
    spec = _load(a.spec)
    try:
        if a.shotlist_cmd == "table":
            rows = cam_kind.shot_table(spec)
            if a.json:
                print(json.dumps(rows, indent=1))
            else:
                for r in rows:
                    print(f"{r['id']:<14} {r['camera']:<20} {r['start']:>6}-{r['end']:<6} {r['size'] or '-':<7} "
                          f"{', '.join(r['subjects'])}")
            return True
        import yaml
        outputs = [{"kind": "h264", "crf": 18}] if a.h264 else None
        docs = cam_kind.pipeline_docs(spec, a.out, a.preset, a.level, a.per_shot, not a.no_review, a.review_mode,
                                      outputs)
        text = yaml.safe_dump_all(docs, sort_keys=False, width=120)
        if a.output == "-":
            sys.stdout.write(text)
        else:
            with open(a.output, "w") as f:
                f.write(text)
            print(f"wrote {a.output}: 1 shot list, 1 render, {len(docs) - 2} reviews; film-ue plan {a.output}")
    except ValueError as e:
        raise SystemExit(f"film-ue shotlist: {e}")
    return True
