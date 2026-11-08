"""The end of a job: every frame there exactly once, with the size (and, deep, the hash) its worker recorded; then the
frames assembled into a video with a continuity check at every chunk boundary.

    verify(queue, root)                 from the listings alone (sizes): safe anywhere, private jobs included
    deep(store, job, chunks, dir)       download every frame and check its sha256 (a worker, for a private job)
    continuity(dir, ...)                the luma difference into each frame; a boundary that jumps is flagged
    encode(dir, ...)                    ffmpeg to H.264 mp4 or ProRes 422 HQ mov

Python 3.10, stdlib only (+ ffmpeg for continuity and encode): it runs on the workers.
"""
from __future__ import annotations

import hashlib
import os
import re
import statistics
import subprocess

from . import model
from .queue import Queue


def verify(q: Queue, root: str) -> dict:
    """{"ok", "frames", "present", "missing", "duplicates", "size_mismatch", "extra", "chunks_not_done",
    "cover"}. ok = every frame of [start, end) is in exactly one chunk's done.json and in the output at that size,
    and the output holds nothing else."""
    job, chunks = q.job(root), q.chunks(root)
    out = job["output"]
    s, e = job["frames"]
    cover = model.check_cover(chunks, job["frames"])
    owner: dict = {}
    dup, not_done, outside = [], [], []
    for c in chunks:
        done, _ = q.s.get_json(f"{root}c/{c['id']}/done.json")
        if not done:
            not_done.append(c["id"])
            continue
        for k, v in done["frames"].items():
            f = int(k)
            if not c["start"] <= f < c["end"]:
                outside.append((c["id"], f))
            if f in owner:
                dup.append(f)
            owner[f] = (c["id"], v)
    b, prefix = model.split_s3(out["prefix"])
    names: dict = {}
    extra = []
    for o in q.s.list(prefix):
        name = o["key"][len(prefix):]
        if "/" in name:
            continue  # _assembled/ and the like
        f = model.frame_of(name, out["ext"])
        if f is None or not s <= f < e:
            extra.append(name)
            continue
        names.setdefault(f, []).append((name, o["size"]))
    dup += [f for f, v in names.items() if len(v) > 1]
    missing = [f for f in range(s, e) if f not in names or f not in owner]
    mismatch = [f for f, v in names.items() if f in owner and v[0][1] != owner[f][1][0]]
    ok = not (cover or dup or missing or mismatch or extra or not_done or outside)
    return {"ok": ok, "frames": e - s, "present": len(names), "missing": model.runs(missing),
            "duplicates": sorted(set(dup)), "size_mismatch": mismatch[:50], "extra": extra[:50],
            "chunks_not_done": not_done, "outside": outside[:20], "cover": cover}


def manifest(q: Queue, root: str) -> dict:
    """{frame: [size, sha256]} from every done.json."""
    m = {}
    for c in q.chunks(root):
        done, _ = q.s.get_json(f"{root}c/{c['id']}/done.json")
        for k, v in (done or {}).get("frames", {}).items():
            m[int(k)] = v
    return m


def deep(store, job: dict, man: dict, local: str) -> dict:
    """Download every frame into `local` and compare its sha256 with the record. {"ok", "bad": [frames]}."""
    out = job["output"]
    b, prefix = model.split_s3(out["prefix"])
    os.makedirs(local, exist_ok=True)
    bad = []
    for f in range(*job["frames"]):
        p = os.path.join(local, model.frame_name(f, out))
        if not os.path.exists(p) or os.path.getsize(p) != man.get(f, [None])[0]:
            store.download(prefix + model.frame_name(f, out), p)
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        if f not in man or man[f][1] != h:
            bad.append(f)
    return {"ok": not bad, "bad": bad[:50], "checked": job["frames"][1] - job["frames"][0]}


def diff_series(local: str, ext: str, pad: int, start: int, end: int, run=subprocess.run) -> dict:
    """{frame: mean |luma(frame) - luma(frame-1)|} (0..255) for frames start+1 .. end-1, from ffmpeg."""
    pat = os.path.join(local, f"%0{pad}d.{ext}")
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-start_number", str(start), "-i", pat,
           "-frames:v", str(end - start), "-vf",
           "format=gray,tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG",
           "-f", "null", "-"]
    r = run(cmd, capture_output=True, text=True)
    vals = [float(x) for x in re.findall(r"lavfi\.signalstats\.YAVG=([0-9.]+)", r.stderr or "")]
    return {start + 1 + i: v for i, v in enumerate(vals)}


def continuity(diffs: dict, boundaries: list[int], *, window: int = 8, factor: float = 3.0, floor: float = 1.0) -> dict:
    """Each chunk boundary's jump against the frames around it: a boundary frame whose difference from the frame
    before is over factor x the local median (+ floor) is flagged. A cut in the edit is a jump too: pass cuts as
    `boundaries` only where chunks met mid-shot."""
    rows, flagged = [], []
    for b in boundaries:
        if b not in diffs:
            continue
        near = [diffs[f] for f in range(b - window, b + window + 1) if f != b and f in diffs]
        med = statistics.median(near) if near else 0.0
        bad = diffs[b] > factor * med + floor
        rows.append({"frame": b, "diff": round(diffs[b], 3), "local_median": round(med, 3), "jump": bad})
        if bad:
            flagged.append(b)
    return {"ok": not flagged, "flagged": flagged, "boundaries": rows}


def encode(local: str, ext: str, pad: int, start: int, end: int, fps: float, out_path: str, kind: str = "mp4",
           run=subprocess.run) -> dict:
    pat = os.path.join(local, f"%0{pad}d.{ext}")
    codec = (["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "slow"] if kind == "mp4" else
             ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"])
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", f"{fps:g}", "-start_number", str(start), "-i", pat,
           "-frames:v", str(end - start), *codec, out_path]
    r = run(cmd, capture_output=True, text=True)
    return {"ok": r.returncode == 0, "path": out_path, "error": (r.stderr or "")[-400:]}


def boundaries(chunks: list[dict], cuts: list[int]) -> list[int]:
    """Where two chunks meet inside a shot (a chunk start that is not a cut and not the first)."""
    starts = sorted(c["start"] for c in chunks)[1:]
    return [s for s in starts if s not in set(cuts)]


def assemble(q: Queue, root: str, local: str, kinds=("mp4",), run=subprocess.run, log=print) -> dict:
    """Verify, download and hash-check every frame, check continuity at the chunk boundaries, encode, and upload
    the videos next to the frames (<prefix>_assembled/). For a private job this runs on a worker (the frames never
    leave AWS); for a public one anywhere."""
    job, chunks = q.job(root), q.chunks(root)
    out = job["output"]
    v = verify(q, root)
    rep = {"verify": v}
    if not v["ok"]:
        rep["ok"] = False
        return rep
    man = manifest(q, root)
    rep["deep"] = deep(q.s, job, man, local)
    s, e = job["frames"]
    diffs = diff_series(local, out["ext"], int(out["pad"]), s, e, run=run)
    rep["continuity"] = continuity(diffs, boundaries(chunks, job.get("cuts") or []))
    b, prefix = model.split_s3(out["prefix"])
    rep["videos"] = []
    for kind in kinds:
        path = os.path.join(local, f"_{job['id']}.{'mp4' if kind == 'mp4' else 'mov'}")
        enc = encode(local, out["ext"], int(out["pad"]), s, e, float(out.get("fps", 24)), path, kind, run=run)
        if enc["ok"]:
            key = f"{prefix}_assembled/{os.path.basename(path)[1:]}"
            q.s.upload(key, path, sse_kms=job["privacy"] == "private")
            enc["s3"] = f"s3://{b}/{key}"
        rep["videos"].append(enc)
    rep["ok"] = rep["deep"]["ok"] and rep["continuity"]["ok"] and all(x["ok"] for x in rep["videos"])
    return rep


# --- A/B: a farm render against a one-box render of the same frames -----------------------------------------------
def psnr_series(dir_a: str, dir_b: str, ext: str, pad: int, frames: list, run=subprocess.run) -> dict:
    """{frame: PSNR dB (inf when identical)} for the frames present in both folders, from ffmpeg's psnr filter."""
    out = {}
    for a, b in model.runs(frames):
        pa, pb = os.path.join(dir_a, f"%0{pad}d.{ext}"), os.path.join(dir_b, f"%0{pad}d.{ext}")
        cmd = ["ffmpeg", "-hide_banner", "-nostats", "-start_number", str(a), "-i", pa, "-start_number", str(a),
               "-i", pb, "-frames:v", str(b - a), "-lavfi", "[0:v][1:v]psnr=stats_file=-", "-f", "null", "-"]
        r = run(cmd, capture_output=True, text=True)
        for line in (r.stdout or "").splitlines():
            m = re.search(r"\bn:(\d+).*psnr_avg:(inf|[0-9.]+)", line)
            if m:
                out[a + int(m.group(1)) - 1] = float(m.group(2))
    return out


def compare(q: Queue, root_a: str, root_b: str, local: str, frames: list | None = None, run=subprocess.run) -> dict:
    """Job A (the farm's) against job B (one box): frames with the same sha256 are identical without looking;
    the rest are downloaded and measured. Numbers only (it runs on a worker for a private job)."""
    ja, jb = q.job(root_a), q.job(root_b)
    ma, mb = manifest(q, root_a), manifest(q, root_b)
    lo = max(ja["frames"][0], jb["frames"][0])
    hi = min(ja["frames"][1], jb["frames"][1])
    want = [f for f in (frames or range(lo, hi)) if f in ma and f in mb]
    same = [f for f in want if ma[f][1] == mb[f][1]]
    differ = [f for f in want if ma[f][1] != mb[f][1]]
    psnr = {f: float("inf") for f in same}
    if differ:
        da, db = os.path.join(local, "a"), os.path.join(local, "b")
        for d, j in ((da, ja), (db, jb)):
            os.makedirs(d, exist_ok=True)
            _, prefix = model.split_s3(j["output"]["prefix"])
            for f in differ:
                q.s.download(prefix + model.frame_name(f, j["output"]), os.path.join(d, model.frame_name(f, j["output"])))
        psnr.update(psnr_series(da, db, ja["output"]["ext"], int(ja["output"]["pad"]), differ, run=run))
    bnd = boundaries(q.chunks(root_a), ja.get("cuts") or [])
    near = sorted({f for b in bnd for f in (b - 1, b, b + 1) if f in psnr})
    finite = [v for v in psnr.values() if v != float("inf")]
    return {"frames": len(want), "identical": len(same), "measured": len(differ),
            "min_psnr": min(finite) if finite else "inf", "mean_psnr": round(sum(finite) / len(finite), 2) if finite else "inf",
            "boundaries": bnd, "boundary_psnr": {str(f): psnr[f] for f in near},
            "worst": sorted(((v, f) for f, v in psnr.items() if v != float("inf")))[:10],
            "missing": [f for f in range(lo, hi) if f not in psnr]}
