"""film-ue render: render specs from the operator's side (docs/unreal/render.md).

    film-ue render validate SPEC                   check a spec offline (schema + resolve), print the resolved form
    film-ue render estimate SPEC [--boxes N] [--state FILE]   chunks, pre-roll, time; offline with a state file
    film-ue render run SPEC [--no-wait] [--timeout S]         render it to the end (resumes); prints the report
    film-ue render cmdline SPEC                    manifests + command lines for one-process renders (no editor)
    film-ue render video SPEC [--kind h264|h265|prores] [--local DIR]    video from the frames (on the box, or here)
    film-ue render check SPEC --local DIR          per-frame QA of a finished render (missing, corrupt, black, flicker)
    film-ue render stitch SPEC --boxes N --local A --local B   frames per box; missing and duplicate frames
    film-ue render schema                          the spec's JSON schema

The ops themselves are generated commands beside these (op verbs win, so these names avoid them):
`film-ue render presets | plan | job | frames | status | cancel | gpu | describe | manifest | encode | concat | mrq`.

The `render` spec kind (film-ue plan/apply, WP11's engine): plan(spec, state) is pure; state is what render.plan
returns for the spec on the box (its chunks still to render), so a finished render plans nothing.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load_render_spec():
    """unreal/fmbridge/render_spec.py, the same module the bridge uses (pure, no unreal)."""
    name = "fmbridge_render_spec"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "unreal" / "fmbridge" / "render_spec.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rs = _load_render_spec()


# ------------------------------------------------------------------------------------------------- spec kind

def plan(spec: dict, state: dict) -> list:
    """The render kind's planner for film-ue plan/apply: one render.job step while the box says chunks are left.
    `state` is render.plan's answer for this spec (None/{} when it could not be read: then render)."""
    body = {k: v for k, v in spec.items() if k not in ("kind", "version", "description")}
    if state and state.get("chunks") == []:
        return []
    if state and state.get("chunks"):
        n, s = state.get("frames", 0), state.get("seconds", 0)
        why = f"{n} frames left in {len(state['chunks'])} chunks (~{s / 60:.0f} min)"
    else:
        why = "no render on the box yet"
    return [{"op": "render.job", "args": {"spec": body}, "why": why}]


def _describe(ue, spec: dict):
    body = {k: v for k, v in spec.items() if k not in ("kind", "version", "description")}
    call = getattr(ue, "call", None)
    return call("render.plan", spec=body) if call else ue.render.plan(spec=body)


SPEC_KINDS = [{"name": "render", "plan": plan, "describe": _describe, "order": 90, "schema": "render.schema.json"}]


# ---------------------------------------------------------------------------------------------- loading specs

def load_spec(path: str) -> dict:
    """The render document of a YAML/JSON file (the first with kind render, or the only one)."""
    text = Path(path).read_text()
    docs = None
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml
        except ImportError:
            raise SystemExit("PyYAML is not installed: uv sync (it is a client dependency), or write the spec as JSON")
        docs = [d for d in yaml.safe_load_all(text) if d is not None]
    else:
        d = json.loads(text)
        docs = d if isinstance(d, list) else [d]
    renders = [d for d in docs if isinstance(d, dict) and d.get("kind", "render") == "render"]
    if not renders:
        raise SystemExit(f"{path}: no document of kind render")
    return renders[0]


def _check(spec: dict) -> dict:
    errs = rs.validate(spec)
    if errs:
        raise SystemExit("render spec:\n  " + "\n  ".join(errs))
    try:
        return rs.resolve(spec)
    except rs.SpecError as e:
        raise SystemExit("render spec:\n  " + "\n  ".join(e.errors))


def _body(spec: dict) -> dict:
    return {k: v for k, v in spec.items() if k not in ("kind", "version", "description")}


# ---------------------------------------------------------------------------------------------- bridge calls

def _op(name: str, timeout: float = 900, wait: bool = True, **args):
    from . import client
    res = client.op(name, timeout=timeout, wait=wait, **args)
    if not res.get("ok"):
        msg = res.get("message") or res.get("error", "")
        hint = res.get("hint")
        raise SystemExit(f"{name}: {msg}" + (f"\n  hint: {hint}" if hint else ""))
    return res.get("result", res)


def _print(v) -> None:
    print(json.dumps(v, indent=1, default=str))


# ----------------------------------------------------------------------------------------------- local work

def _local_frames(r: dict, root: str) -> set:
    names = []
    for d, _, files in os.walk(root):
        rel = os.path.relpath(d, root)
        names.extend(f if rel == "." else os.path.join(rel, f).replace("\\", "/") for f in files)
    return rs.frames_on_disk(r, names)


def encode_local(r: dict, root: str, kinds: list, fps: float, start: int | None = None, end: int | None = None,
                 audio: str = "") -> list:
    """Encode frames pulled to `root` (the render's out_dir layout) with the local ffmpeg."""
    ff = shutil.which("ffmpeg")
    if not ff:
        raise SystemExit("ffmpeg is not installed here (macOS: brew install ffmpeg; Ubuntu: apt-get install ffmpeg)")
    r = {**r, "out_dir": root}
    have = _local_frames(r, root)
    if not have:
        raise SystemExit(f"no frames of this render in {root}")
    lo = min(have) if start is None else start
    hi = max(have) + 1 if end is None else end
    gaps = rs.missing_frames(have, lo, hi)
    if gaps:
        raise SystemExit(f"frames missing in [{lo}, {hi}): {gaps[:10]}; render them or pass --start/--end")
    out = []
    for k in kinds:
        argv = rs.encode_args(r, {"kind": k, "audio": bool(audio)}, lo, hi, fps, audio_file=audio, ffmpeg=ff)
        subprocess.run(argv, check=True)
        out.append(argv[-1])
    return out


def pixel_qa(img, *, hot_ratio: float = 20.0, hot_min: float = 1.0) -> dict:
    """Bad pixels in one linear float image (H x W x C numpy array): NaN, Inf, negative values, and fireflies (a
    pixel brighter than hot_min and over hot_ratio x the mean of its 8 neighbours, as a lone sample spike is).
    Returns {"nan", "inf", "negative", "hot", "max"} (counts of pixels; max of the finite values)."""
    import numpy as np
    a = np.asarray(img, dtype=np.float32)
    if a.ndim == 2:
        a = a[..., None]
    nan = int(np.isnan(a).any(axis=-1).sum())
    inf = int(np.isinf(a).any(axis=-1).sum())
    fin = np.where(np.isfinite(a), a, 0.0)
    neg = int((fin < 0).any(axis=-1).sum())
    lum = fin[..., :3].mean(axis=-1) if fin.shape[-1] >= 3 else fin[..., 0]
    p = np.pad(lum, 1, mode="edge")
    h, w = lum.shape
    nb = sum(p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx) / 8.0
    hot = int(((lum > hot_min) & (lum > hot_ratio * np.maximum(nb, 1e-6))).sum())
    return {"nan": nan, "inf": inf, "negative": neg, "hot": hot, "max": float(fin.max()) if fin.size else 0.0}


def read_float_frame(path: str, width: int, height: int, ffmpeg: str):
    """A frame as linear float RGB (H x W x 3) through ffmpeg (any format ffmpeg reads, EXR PIZ included)."""
    import numpy as np
    raw = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path, "-f", "rawvideo",
                          "-pix_fmt", "gbrpf32le", "-"], capture_output=True, check=True).stdout
    planes = np.frombuffer(raw, dtype="<f4")[: width * height * 3].reshape(3, height, width)
    return np.stack([planes[2], planes[0], planes[1]], axis=-1)  # gbr planes -> rgb


def check_frames(r: dict, root: str, start: int, end: int, *, black_luma: float = 4.0, flicker_ratio: float = 4.0,
                 ffmpeg: str | None = None, pixels_every: int = 1, hot_ratio: float = 20.0) -> dict:
    """Per-frame QA of a finished render in `root` (B24): missing frames, files cut off, black frames (mean luma
    below black_luma of 255) and flicker (a frame-to-frame luma change over flicker_ratio x the median change, and
    over 2/255), and for EXR frames NaN/Inf pixels and fireflies (every `pixels_every`-th frame). Luma and pixels come
    through ffmpeg. Returns a check: {"pass", "metric", "threshold", "why", "missing", "corrupt", "black", "flicker",
    "nan_frames", "firefly_frames", "luma", "pixels"}."""
    r = {**r, "out_dir": root}
    have = _local_frames(r, root)
    missing = rs.missing_frames(have, start, end)
    corrupt = []
    for f in sorted(x for x in have if start <= x < end):
        p = rs.frame_path(r, f)
        size = os.path.getsize(p)
        with open(p, "rb") as fh:
            head = fh.read(8)
            fh.seek(max(0, size - 16))
            tail = fh.read(16)
        if not rs.image_ok(head, tail, size):
            corrupt.append(f)
    luma = {}
    ff = ffmpeg or shutil.which("ffmpeg")
    if ff and not missing:
        pat, ext = rs._pattern(r)
        argv = [ff, "-hide_banner", "-loglevel", "error", "-start_number", str(start)]
        if ext == "exr":
            argv += ["-apply_trc", "iec61966_2_1"]
        argv += ["-i", pat, "-frames:v", str(end - start), "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
                 "-f", "null", "-"]
        txt = subprocess.run(argv, capture_output=True, text=True).stdout
        luma = rs.parse_signalstats(txt, start)
    q = rs.frame_qa(luma, black_luma=black_luma, flicker_ratio=flicker_ratio)
    pixels, nan_frames, hot_frames = {}, [], []
    if ff and rs._pattern(r)[1] == "exr":
        for f in sorted(x for x in have if start <= x < end and x not in corrupt)[::max(1, pixels_every)]:
            try:
                px = pixel_qa(read_float_frame(rs.frame_path(r, f), r["width"], r["height"], ff), hot_ratio=hot_ratio)
            except (subprocess.CalledProcessError, ValueError) as e:
                px = {"error": str(e)[:200]}
            pixels[f] = px
            if px.get("nan") or px.get("inf"):
                nan_frames.append(f)
            if px.get("hot"):
                hot_frames.append(f)
    bad = len(missing) + len(corrupt) + len(q["black"]) + len(q["flicker"]) + len(nan_frames) + len(hot_frames)
    why = []
    if missing:
        why.append(f"missing {missing[:5]}")
    if corrupt:
        why.append(f"corrupt {corrupt[:5]}")
    if q["black"]:
        why.append(f"black {q['black'][:5]}")
    if q["flicker"]:
        why.append(f"flicker at {q['flicker'][:5]}")
    if nan_frames:
        why.append(f"NaN/Inf pixels in {nan_frames[:5]}")
    if hot_frames:
        why.append(f"fireflies in {hot_frames[:5]}")
    if not luma:
        why.append("luma not measured (no ffmpeg, or frames missing)")
    return {"pass": bad == 0, "metric": bad, "threshold": 0, "why": "; ".join(why) or "every frame present and sane",
            "missing": missing, "corrupt": corrupt, **q, "nan_frames": nan_frames, "firefly_frames": hot_frames,
            "luma": luma, "pixels": pixels}


def stitch(r: dict, plan_: dict, have_by_dir: dict) -> dict:
    """Frames gathered from several boxes (B23): for each box its planned chunks and what of them is missing, frames
    found in more than one folder (duplicates: compare them before keeping one), and the job's missing frames."""
    ids = {c["id"]: c for c in plan_["chunks"]}
    have = set().union(*have_by_dir.values()) if have_by_dir else set()
    seen: dict = {}
    for d, fs in have_by_dir.items():
        for f in fs:
            seen.setdefault(f, []).append(d)
    dups = {f: ds for f, ds in sorted(seen.items()) if len(ds) > 1}
    boxes = plan_.get("boxes") or [{"box": 0, "chunks": list(ids)}]
    out = []
    for b in boxes:
        want = {f for cid in b["chunks"] for f in range(ids[cid]["start"], ids[cid]["end"])}
        out.append({"box": b["box"], "chunks": b["chunks"], "frames": len(want),
                    "missing": rs.missing_frames(have & want, min(want), max(want) + 1) if want else []})
    lo, hi = plan_["range"]
    missing = rs.missing_frames(have, lo, hi)
    return {"boxes": out, "missing": missing, "duplicates": dups, "complete": not missing}


# ------------------------------------------------------------------------------------------------------- CLI

def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="film-ue render", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("schema", help="the spec's JSON schema")
    v = sub.add_parser("validate", help="check a spec offline")
    v.add_argument("spec")
    p = sub.add_parser("estimate", help="chunks, pre-roll and time (render.plan)")
    p.add_argument("spec")
    p.add_argument("--boxes", type=int)
    p.add_argument("--state", help="offline: a JSON {playback, fps, cuts, done} instead of asking the box")
    r = sub.add_parser("run", help="render a spec to the end (render.job)")
    r.add_argument("spec")
    r.add_argument("--no-wait", action="store_true")
    r.add_argument("--timeout", type=float, default=24 * 3600)
    m = sub.add_parser("cmdline", help="one-process command lines (render.manifest)")
    m.add_argument("spec")
    e = sub.add_parser("video", help="video from the frames (render.encode, or ffmpeg here with --local)")
    e.add_argument("spec")
    e.add_argument("--kind", action="append", choices=rs.VIDEO_KINDS)
    e.add_argument("--start", type=int)
    e.add_argument("--end", type=int)
    e.add_argument("--local", help="frames pulled to this folder: encode here")
    e.add_argument("--fps", type=float, default=24.0, help="with --local")
    e.add_argument("--audio", default="", help="with --local: an audio file to put under it")
    c = sub.add_parser("check", help="per-frame QA of a finished render")
    c.add_argument("spec")
    c.add_argument("--local", required=True, help="the frames, pulled to this folder")
    c.add_argument("--start", type=int)
    c.add_argument("--end", type=int)
    s = sub.add_parser("stitch", help="frames per box, missing and duplicate frames")
    s.add_argument("spec")
    s.add_argument("--boxes", type=int, required=True)
    s.add_argument("--local", action="append", required=True, help="a folder of frames from one box (repeat per box)")
    s.add_argument("--state", help="offline state JSON (as for estimate)")
    a = ap.parse_args(argv)

    if a.cmd == "schema":
        _print(rs.SCHEMA)
        return 0
    spec = load_spec(a.spec)
    r = _check(spec)
    if a.cmd == "validate":
        _print(r)
        return 0
    if a.cmd == "estimate":
        if a.boxes:
            spec = {**spec, "boxes": a.boxes}
            r = _check(spec)
        out = rs.plan(r, json.loads(Path(a.state).read_text())) if a.state else _op("render.plan", spec=_body(spec))
        _print({k: v for k, v in out.items() if k != "spec"})
        return 0
    if a.cmd == "stitch":
        full_spec = {**spec, "boxes": a.boxes, "resume": False}
        rf = _check(full_spec)
        full = rs.plan(rf, json.loads(Path(a.state).read_text())) if a.state else _op("render.plan", spec=_body(full_spec))
        res = stitch(rf, full, {d: _local_frames(rf, d) for d in a.local})
        _print(res)
        return 0 if res["complete"] and not res["duplicates"] else 1
    if a.cmd == "run":
        if a.no_wait:
            from . import client
            print(client.submit("render.job", spec=_body(spec)))
            return 0
        from . import client
        jid = client.submit("render.job", spec=_body(spec))
        res = client.wait(jid, timeout=a.timeout, on_progress=lambda j: print(j.get("message", ""), file=sys.stderr))
        if not res.get("ok"):
            raise SystemExit(f"render.job: {res.get('message') or res.get('error')}" +
                             (f"\n  hint: {res['hint']}" if res.get("hint") else ""))
        rep = res.get("result", {})
        _print({k: v for k, v in rep.items() if k != "spec"})
        return 0 if rep.get("status") == "ok" else 1
    if a.cmd == "cmdline":
        _print(_op("render.manifest", spec=_body(spec)))
        return 0
    if a.cmd == "video":
        kinds = a.kind or [o["kind"] for o in r["outputs"] if o["kind"] in rs.VIDEO_KINDS] or ["h264"]
        if a.local:
            _print(encode_local(r, a.local, kinds, a.fps, a.start, a.end, a.audio))
        else:
            _print(_op("render.encode", spec=_body(spec), start=a.start, end=a.end,
                       outputs=[{"kind": k} for k in kinds], timeout=6 * 3600))
        return 0
    if a.cmd == "check":
        have = _local_frames(r, a.local)
        if not have:
            raise SystemExit(f"no frames of this render in {a.local}")
        lo = min(have) if a.start is None else a.start
        hi = max(have) + 1 if a.end is None else a.end
        res = check_frames(r, a.local, lo, hi)
        _print({k: v for k, v in res.items() if k not in ("luma", "pixels")})
        return 0 if res["pass"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
