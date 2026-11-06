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
        --yaml ../films/host-studio/reel/r3/30-final.yaml --qa-pop $G/her_final.json --qa $G/editor_after.json \
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


POP_ONLY = ("hair.cut_pop_ratio",)


def _pop_exclude(g: dict, qa_paths: list, excludes: list) -> None:
    """hair.pop_reach_pct again from the full results' pop rows, without the windows a ruling in the round's spec
    names (`hair_pop_exclude`: [{"shot", "frames": [f0, f1], "reason", "by"}]: a measure-scope decision, e.g. her
    planned motion at a shot's start, proved on the render against round 4; never a waiver). Every pop it drops is
    listed in the item."""
    for e in excludes:
        if not (str(e.get("reason") or "").strip() and str(e.get("by") or "").strip()):
            g["hair.pop_reach_pct"] = _err(f"hair_pop_exclude {e} needs a reason and who decided it")
            return
    kept, dropped = [], []
    for p in qa_paths:
        d = json.loads(_read(p) or "null") or {}
        d = d["result"] if isinstance(d.get("result"), dict) else d
        for r in (d.get("characters") or {"": d}).values():
            for pop in r.get("pops") or []:
                hit = next((e for e in excludes if f"Reel_{e['shot']}" in (pop.get("shot"), f"Reel_{pop.get('shot')}")
                            or e["shot"] == pop.get("shot")), None)
                if hit and hit["frames"][0] <= pop["frame"] <= hit["frames"][1]:
                    dropped.append({**pop, "by": hit["by"], "reason": hit["reason"]})
                else:
                    kept.append(pop)
    if not dropped:
        return
    worst = max(kept, key=lambda q: abs(q["reach"]), default=None)
    g["hair.pop_reach_pct"] = {"value": round(abs(worst["reach"]) * 100, 2) if worst else 0.0,
                               "where": f"{worst['shot']} f{worst['frame']}" if worst else "no pop over the line",
                               "excluded_by_ruling": dropped}


def hair(check: str, yaml_path: str, qa_paths: list, pop_paths: list | None = None,
         excludes: list | None = None) -> dict:
    g = {}
    c = json.loads(_read(check)) if _read(check) else None
    if c is None:
        g["hair.lock"] = _err(f"no groom.lock_check result at {check!r}")
    else:
        c = c.get("result", c) if isinstance(c.get("result"), dict) else c  # film-ue op's wrapper
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
    judged, popped = [], []  # every cut each result judged, so the gate output shows them (the orchestrator's check)
    for p in list(qa_paths) + list(pop_paths or []):
        only = POP_ONLY if p in (pop_paths or []) else None
        d = json.loads(_read(p) or "null")
        if d is None:
            for k in only or ("hair.cut_reach_pct", "hair.pop_reach_pct", "hair.cut_pop_ratio"):
                g.setdefault(k, _err(f"no film-qa hair result at {p!r}"))
            continue
        if isinstance(d.get("result"), dict):  # film-ue op's {"ok", "result": {...}}
            d = d["result"]
        src = "editor" if "characters" in d else "render"
        rows = [c for r in (d.get("characters") or {"": d}).values() for c in (r.get("cuts") or [])
                if isinstance(c, dict) and "from" in c]
        judged += [f"{src} {c['from']}->{c['to']} f{c.get('frame')} {c['reach'][2] * 100:+.2f}%" for c in rows]
        popped += [f"{c['from']}->{c['to']} f{c.get('cut')} x{c['ratio']}" if "ratio" in c else
                   f"{c['from']}->{c['to']} missing {c.get('missing')}" for c in d.get("cut_pops") or []]
        for k, v in (d.get("gate") or {}).items():
            if only and k not in only:  # the render's night matte: only its pixel cut pop is a measure
                continue
            # several results (render-side film-qa hair, the editor's qa.hair_continuity): a measured number beats
            # an error (the render matte saturates at night: hair.matte_saturated), and the worst number wins
            old = g.get(k)
            vv, ov = (x.get("value") if isinstance(x, dict) else x for x in (v, old))
            bad_new = vv is None or (isinstance(v, dict) and bool(v.get("error")))
            bad_old = old is None or ov is None or (isinstance(old, dict) and bool(old.get("error")))
            if old is None or (bad_old and not bad_new) or (not bad_old and not bad_new and vv > ov):
                g[k] = v
    if excludes and qa_paths:
        _pop_exclude(g, qa_paths, excludes)
    for k, extra in (("hair.cut_reach_pct", {"cuts_judged": judged}), ("hair.cut_pop_ratio", {"pop_cuts": popped})):
        if k in g and (qa_paths or pop_paths):
            g[k] = {**(g[k] if isinstance(g[k], dict) else {"value": g[k]}), **extra}
    return g


def settle(frames: str, spec: str, shot: str, first: int = 4, rest: int = 12, line: float = 1.8,
           box: list | None = None) -> dict:
    """Head + hair motion at a shot's start, on rendered frames: head-box frame differences (qa/hair.py box_diff, no
    matte) of the first `first` frame pairs over the median of the next `rest` pairs. Anything that moves or changes
    in the box at the start reads: a hair simulation settling, a head snapping into its pose, but also a render job's
    own start (exposure adaptation, temporal history) and planned motion. A DIAGNOSTIC, not a gate line: round 5b's
    S15 read 12.3 with round 4's final_d reading the same shape (13.8), while the eye saw her head snap only in round
    5, so the number did not separate them on a large box. Compare with round 4 (the same command on final_d), on a
    TIGHT box around the head. `box`: frame fractions, else the spec's box for the shot (hair_spec.py builds the
    FIRST shot's box from its END frames: pass --box from a projection at the shot's start when the head moves)."""
    from filmtools.unreal import qa_local
    qa_local.qa()
    im, h = sys.modules["fmqa.image"], sys.modules["fmqa.hair"]
    sp = json.loads(Path(spec).read_text())
    box = box or (sp.get("boxes") or {}).get(shot)
    a0 = next((c[1] for c in sp.get("cuts") or [] if c[0] == shot), None)
    if not box or a0 is None:
        return {"error": f"no box/cut for {shot} in {spec}"}
    have = _frames(frames)
    need = range(a0, a0 + first + rest + 1)
    if any(f not in have for f in need):
        return {"error": f"frames missing in {frames}: {[f for f in need if f not in have][:8]}"}
    imgs = {f: im.read(have[f]) for f in need}
    d = [round(h.box_diff(imgs[f], imgs[f + 1], box), 3) for f in range(a0, a0 + first + rest)]
    base = sorted(d[first:])[len(d[first:]) // 2]
    ratio = round(max(d[:first]) / max(base, 0.5), 3)
    return {"what": "head+hair motion at the shot start (diagnostic)", "shot": shot, "box": box, "diffs": d,
            "start_max": max(d[:first]), "median_after": base, "ratio": ratio, "line": line, "pass": ratio <= line,
            "gate": {"shot.start_motion_ratio": {"value": ratio, "where": f"{shot} f{a0}-{a0 + first}"}}}


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
    h.add_argument("--qa", action="append", default=[], help="film-qa hair / qa.hair_continuity json (repeatable)")
    h.add_argument("--spec", default="", help="the round's gate spec: its hair_pop_exclude rulings, if any")
    h.add_argument("--qa-pop", action="append", default=[], help="film-qa hair on NIGHT renders: only its "
                   "hair.cut_pop_ratio is taken (the luma matte reads dark clothing as hair: reach is not a measure)")
    h.add_argument("--out", required=True)
    st = sub.add_parser("settle", help="head+hair motion at a shot's first frames, on the rendered frames (diagnostic)")
    st.add_argument("--box", default="", help="x0,y0,x1,y1 frame fractions (default: the spec's box for the shot)")
    st.add_argument("--frames", required=True)
    st.add_argument("--spec", required=True, help="hair_spec.py's json (its boxes and cuts)")
    st.add_argument("--shot", default="S15")
    st.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "settle":
        r = settle(a.frames, a.spec, a.shot, box=[float(v) for v in a.box.split(",")] if a.box else None)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(r, indent=1))
        print(json.dumps(r, indent=1))
        return 0 if r.get("pass") else 1
    if a.cmd == "shot":
        g = shot_cams(a.probe, a.framing)
    elif a.cmd == "ssim":
        g = ssim(a.frames, a.ref, [x for x in a.shots.split(",") if x], a.step)
    else:
        ex = (json.loads(Path(a.spec).read_text()).get("hair_pop_exclude") or []) if a.spec else []
        g = hair(a.check, a.yaml, a.qa, a.qa_pop, ex)
    out = {"gate": g}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0 if all(isinstance(v, dict) and not v.get("error") for v in g.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
