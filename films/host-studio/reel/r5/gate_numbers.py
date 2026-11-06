"""Round 5b (T4, agent-09): gate v2's number files for the items no track's check writes itself. Each subcommand
reads the raw outputs already on the box and writes {"gate": {item: {"value", "where"} | {"value": None, "error"}}}
for `film-qa gate`. No frame leaves the box (face rule): it runs there, from tools/.

    cd tools
    # shot.cameras_ok: probe_cam --check's stdout and framing.py's stdout, saved right before the render
    uv run python ../films/host-studio/reel/r5/gate_numbers.py shot --probe $R/probe_check.txt \
        --framing $R/framing.txt --out $R/gate_cams.json
    # shot.render_matches_r4: every rendered presenter frame vs round 4's same frame (min SSIM)
    uv run python ../films/host-studio/reel/r5/gate_numbers.py ssim --frames /srv/ue/reel/r5/final \
        --ref /srv/ue/reel/r3/final_d --shots S13,S15,S16,S17,S18 --out $R/gate_ssim.json
    # hair.lock + hair.render_cvars (+ the hair.* numbers of film-qa hair on the finals and of the editor's
    # qa.hair_continuity: a measured number beats an error, the worst number wins)
    uv run python ../films/host-studio/reel/r5/gate_numbers.py hair --check $G/check_after.json \
        --yaml ../films/host-studio/reel/r3/30-final.yaml --qa $G/her_final.json --qa $G/editor_after.json \
        --out $G/hair_gate.json

A missing input writes the item with an error, so the gate FAILS it as "the check errored" rather than passing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REEL))
from cast_gate import SHOTS_13, _cams  # noqa: E402
from shots import SHOTS  # noqa: E402

LOCK_KEYS = ("r.HairStrands.LODMode", "r.HairStrands.AutoLOD.Bias", "r.HairStrands.UseCardsInsteadOfStrands")


def _err(msg: str) -> dict:
    return {"value": None, "error": msg}


def _read(p: str) -> str | None:
    return Path(p).read_text() if p and Path(p).is_file() else None


def shot_cams(probe: str, framing: str) -> dict:
    c = _cams(_read(probe), _read(framing))
    where = f"the 13 shots ({c['cameras_ok'] or 'not probed'})"
    if c["cameras_ok"] is None:
        return {"shot.cameras_ok": _err("no probe_cam --check output: " + "; ".join(c["failed"]))}
    if _read(framing) is None:
        return {"shot.cameras_ok": _err("no framing.py output")}
    return {"shot.cameras_ok": {"value": int(c["pass"]), "where": where, "failed": c["failed"]}}


def _frames(d: str) -> dict:
    out = {}
    for p in sorted(Path(d).rglob("*")):
        if p.suffix.lower() in (".png", ".jpg", ".jpeg"):
            m = re.findall(r"\d+", p.stem)
            if m:
                out.setdefault(int(m[-1]), str(p))
    return out


def ssim(frames: list, ref: str, shots: list, step: int = 1) -> dict:
    """min SSIM of every rendered frame inside `shots` vs round 4's same frame number (`frames`: dirs, merged; a
    later dir's frame replaces an earlier one's)."""
    from filmtools.unreal import qa_local
    qa_local.qa()
    im, cm = sys.modules["fmqa.image"], sys.modules["fmqa.compare"]
    have, refs = {}, _frames(ref)
    for d in frames:
        have.update(_frames(d))
    spans = {s.id: (s.start, s.end) for s in SHOTS if s.id in shots}
    missing = [s for s in shots if s not in spans]
    if missing:
        return {"shot.render_matches_r4": _err(f"unknown shots {missing}")}
    per, unmatched = {}, []
    for sid, (a, b) in spans.items():
        fs = [f for f in range(a, b, step) if f in have]
        if not fs:
            unmatched.append(f"{sid}: no rendered frame in {', '.join(frames)}")
            continue
        vals = []
        for f in fs:
            if f not in refs:
                unmatched.append(f"{sid} f{f}: no round-4 frame")
                continue
            r = cm.against_reference(im.read(have[f]), im.read(refs[f]), name=f"f{f}", min_ssim=0.0)
            vals.append((r["ssim"], f))
        if vals:
            lo = min(vals)
            per[sid] = {"min": round(lo[0], 4), "at": lo[1], "frames": len(vals),
                        "mean": round(sum(v for v, _ in vals) / len(vals), 4)}
    if unmatched and not per:
        return {"shot.render_matches_r4": _err("; ".join(unmatched[:6]))}
    if any(s not in per for s in shots):
        return {"shot.render_matches_r4": {**_err("shots not measured: " + ", ".join(s for s in shots if s not in per)),
                                           "per_shot": per}}
    worst = min(per.items(), key=lambda kv: kv[1]["min"])
    return {"shot.render_matches_r4": {"value": worst[1]["min"], "where": f"{worst[0]} f{worst[1]['at']}",
                                       "per_shot": per, "unmatched": unmatched[:20]}}


def _yaml_cvars(path: str) -> dict:
    import yaml
    docs = [d for d in yaml.safe_load_all(Path(path).read_text()) if isinstance(d, dict)]
    cv = {}
    for d in docs:
        cv.update(d.get("cvars") or {})
    return cv


def hair(check: str, yaml_path: str, qa_paths: list) -> dict:
    g = {}
    c = json.loads(_read(check)) if _read(check) else None
    if c is None:
        g["hair.lock"] = _err(f"no groom.lock_check result at {check!r}")
    else:
        c = c.get("check", c)  # groom.lock's result carries lock_check's under "check"
        g["hair.lock"] = {"value": int(bool(c.get("pass"))), "where": "the level, before the render",
                          "problems": c.get("problems", [])}
    want = dict((c or {}).get("render_cvars") or {k: v for k, v in zip(LOCK_KEYS, (0, 1.0, 0))})
    if not _read(yaml_path):
        g["hair.render_cvars"] = _err(f"no render spec at {yaml_path!r}")
    else:
        have = _yaml_cvars(yaml_path)
        bad = [f"{k}={have.get(k)!r} (want {v})" for k, v in want.items()
               if k not in have or float(have[k]) != float(v)]
        g["hair.render_cvars"] = {"value": int(not bad), "where": Path(yaml_path).name, "mismatch": bad}
    for p in qa_paths:
        d = json.loads(_read(p) or "null")
        if d is None:
            for k in ("hair.cut_reach_pct", "hair.pop_reach_pct", "hair.cut_pop_ratio"):
                g.setdefault(k, _err(f"no film-qa hair result at {p!r}"))
            continue
        for k, v in (d.get("gate") or {}).items():
            # several results (render-side film-qa hair, the editor's qa.hair_continuity): a measured number beats
            # an error (the render matte saturates at night: hair.matte_saturated), and the worst number wins
            old = g.get(k)
            vv, ov = (x.get("value") if isinstance(x, dict) else x for x in (v, old))
            bad_new = vv is None or (isinstance(v, dict) and bool(v.get("error")))
            bad_old = old is None or ov is None or (isinstance(old, dict) and bool(old.get("error")))
            if old is None or (bad_old and not bad_new) or (not bad_old and not bad_new and vv > ov):
                g[k] = v
    return g


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shot")
    s.add_argument("--probe", required=True, help="probe_cam --check stdout")
    s.add_argument("--framing", required=True, help="framing.py stdout")
    s.add_argument("--out", required=True)
    m = sub.add_parser("ssim")
    m.add_argument("--frames", required=True, action="append", help="rendered frames dir (repeatable)")
    m.add_argument("--ref", required=True, help="round 4's frames (final_d)")
    m.add_argument("--shots", default="S13,S15,S16,S17,S18")
    m.add_argument("--step", type=int, default=1)
    m.add_argument("--out", required=True)
    h = sub.add_parser("hair")
    h.add_argument("--check", required=True, help="groom.lock_check (or groom.lock) result json")
    h.add_argument("--yaml", required=True, help="the finals' render spec")
    h.add_argument("--qa", action="append", default=[], help="film-qa hair --out json (repeatable)")
    h.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "shot":
        g = shot_cams(a.probe, a.framing)
    elif a.cmd == "ssim":
        g = ssim(a.frames, a.ref, [x for x in a.shots.split(",") if x], a.step)
    else:
        g = hair(a.check, a.yaml, a.qa)
    out = {"gate": g}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0 if all(isinstance(v, dict) and not v.get("error") for v in g.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
