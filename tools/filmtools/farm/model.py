"""Farm jobs: what to render, where the frames go, how it is cut into chunks, and the pre-roll each chunk renders and
throws away.

A job is a plain dict (job.yaml/json, docs/FARM.md):

    {"id": "wide-pushin", "engine": "ue" | "blender", "frames": [start, end),      # end exclusive, scene frames
     "privacy": "public" | "private", "presenter": false,                         # a presenter in frame => private
     "output": {"prefix": "s3://BUCKET/.../frames/", "ext": "png", "pad": 4},
     "chunk": 48,                  # frames per chunk ("auto": the frames over 3 x the workers)
     "preroll": 24,                # frames rendered before each chunk's first frame and thrown away (TSR, hair)
     "cuts": [0, 120, 300],        # optional: shot starts. Chunks break on them; pre-roll never crosses one
     "max_attempts": 4,
     "ue": {...} | "blender": {...}}   # the engine's own settings (engines/ue.py, engines/blender.py)

Everything here is pure (no AWS, no clock), and runs on the workers too: Python 3.10, stdlib only.
"""
from __future__ import annotations

import math
import re

ENGINES = ("blender", "ue")
PRIVACY = ("public", "private")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
# frames rendered before a chunk and thrown away, by engine, when the job does not say: UE's TSR/temporal history and
# groom/cloth state need it; Cycles and EEVEE render every frame from nothing
DEFAULT_PREROLL = {"ue": 24, "blender": 0}
# a chunk this short is mostly pre-roll and start-up; the planner never cuts smaller (a shot may be shorter)
MIN_CHUNK = 8


class JobError(ValueError):
    """A job that cannot run as written (the message says what to change)."""


def is_private_prefix(s3: str) -> bool:
    """A destination under a .../private/ prefix (SSE-KMS, the box role only): the same test as film-ue's sync."""
    return "/private/" in s3.rstrip("/") + "/"


def split_s3(url: str) -> tuple[str, str]:
    """s3://bucket/key/prefix -> (bucket, key/prefix)."""
    if not url.startswith("s3://"):
        raise JobError(f"{url!r} is not an s3:// URL")
    b, _, k = url[5:].partition("/")
    if not b:
        raise JobError(f"{url!r} has no bucket")
    return b, k


def validate(job: dict, *, bucket: str = "", private_root: str = "ue-linux/private/") -> dict:
    """The job with its defaults filled in, or JobError. The FACE RULE: a job with a presenter is private, and a
    private job writes only under s3://<bucket>/<private_root> (SSE-KMS)."""
    j = dict(job)
    for k in ("id", "engine", "frames", "privacy", "output"):
        if k not in j:
            raise JobError(f"job: missing {k!r}")
    if not ID_RE.match(str(j["id"])):
        raise JobError(f"job id {j['id']!r}: lower-case letters, digits, - and _ (at most 48)")
    if j["engine"] not in ENGINES:
        raise JobError(f"engine {j['engine']!r}: one of {', '.join(ENGINES)}")
    if j["privacy"] not in PRIVACY:
        raise JobError(f"privacy {j['privacy']!r}: public or private")
    if j.get("presenter") and j["privacy"] != "private":
        raise JobError("a job with a presenter in frame is private (the face rule): privacy: private")
    f = j["frames"]
    if not (isinstance(f, (list, tuple)) and len(f) == 2 and all(isinstance(x, int) for x in f) and f[0] < f[1]):
        raise JobError(f"frames {f!r}: [start, end) with start < end (end exclusive)")
    j["frames"] = [int(f[0]), int(f[1])]
    out = dict(j["output"])
    if "prefix" not in out:
        raise JobError("output: missing 'prefix' (s3://bucket/path/)")
    b, key = split_s3(out["prefix"])
    out["prefix"] = f"s3://{b}/{key.rstrip('/')}/"
    out.setdefault("ext", "png")
    out.setdefault("pad", 4)
    if out["ext"] not in ("png", "exr", "jpeg", "jpg", "tif", "tiff"):
        raise JobError(f"output ext {out['ext']!r}: png, exr, jpeg, tif")
    if not 1 <= int(out["pad"]) <= 8:
        raise JobError("output pad: 1..8 digits")
    if j["privacy"] == "private":
        if not is_private_prefix(out["prefix"]) or (bucket and (b != bucket or not key.startswith(private_root))):
            where = f"s3://{bucket}/{private_root}" if bucket else "a .../private/ prefix"
            raise JobError(f"a private job writes only under {where}, not {out['prefix']}")
        out["sse"] = "aws:kms"
    j["output"] = out
    j.setdefault("presenter", False)
    j.setdefault("preroll", DEFAULT_PREROLL[j["engine"]])
    if not isinstance(j["preroll"], int) or j["preroll"] < 0:
        raise JobError("preroll: a whole number of frames >= 0")
    j.setdefault("chunk", "auto")
    if j["chunk"] != "auto" and (not isinstance(j["chunk"], int) or j["chunk"] < 1):
        raise JobError("chunk: frames per chunk (>= 1) or 'auto'")
    cuts = sorted({int(c) for c in j.get("cuts") or []})
    j["cuts"] = cuts
    j.setdefault("max_attempts", 4)
    j.setdefault(j["engine"], {})
    return j


def auto_chunk(frames: list, workers: int, *, per_worker: int = 3, floor: int = MIN_CHUNK) -> int:
    """Frames per chunk for `workers` boxes: about `per_worker` chunks each, so a box lost to a spot reclaim costs
    a third of its share, and the tail (the last chunk running alone) stays short."""
    n = frames[1] - frames[0]
    return max(floor, math.ceil(n / max(1, workers * per_worker)))


def cut_start(frame: int, cuts: list, scene_start: int) -> int:
    """The first frame of the shot `frame` is in (the scene start if no cut is at or before it)."""
    best = scene_start
    for c in cuts:
        if c <= frame:
            best = max(best, c)
    return best


def preroll_from(start: int, job_start: int, cuts: list, preroll: int) -> int:
    """Where a chunk starting at `start` begins rendering: `preroll` frames earlier, but never before the job's first
    frame or across a cut. At the job's start and at a cut, a single box starts cold there too (the engine's own
    warm-up handles it), so a chunk there needs nothing more and the two renders match."""
    return max(job_start, cut_start(start, cuts, job_start), start - preroll)


def plan_chunks(job: dict, workers: int = 1) -> list[dict]:
    """The job's frames cut into chunks: [{"id", "start", "end", "render_from", "preroll", "cut_start"}], covering
    [start, end) exactly once, in order. Chunks break on every cut; inside a shot the frames are split evenly into
    pieces of at most `chunk`."""
    s, e = job["frames"]
    size = auto_chunk(job["frames"], workers) if job.get("chunk", "auto") == "auto" else int(job["chunk"])
    bounds = [s] + [c for c in job.get("cuts") or [] if s < c < e] + [e]
    chunks = []
    for a, b in zip(bounds, bounds[1:]):
        k = max(1, math.ceil((b - a) / size))
        base, extra = divmod(b - a, k)
        x = a
        for i in range(k):
            y = x + base + (1 if i < extra else 0)
            rf = preroll_from(x, s, job.get("cuts") or [], int(job.get("preroll", 0)))
            chunks.append({"id": f"c{len(chunks):04d}", "start": x, "end": y, "render_from": rf, "preroll": x - rf,
                           "cut_start": cut_start(x, job.get("cuts") or [], s)})
            x = y
    return chunks


def check_cover(chunks: list, frames: list) -> list[str]:
    """Problems with a chunk list as a partition of [start, end): gaps, overlaps, empty chunks. [] = good."""
    errs, at = [], frames[0]
    for c in sorted(chunks, key=lambda c: c["start"]):
        if c["end"] <= c["start"]:
            errs.append(f"{c['id']}: empty [{c['start']}, {c['end']})")
        if c["start"] > at:
            errs.append(f"gap [{at}, {c['start']})")
        elif c["start"] < at:
            errs.append(f"{c['id']}: overlaps [{c['start']}, {at})")
        at = max(at, c["end"])
    if at < frames[1]:
        errs.append(f"gap [{at}, {frames[1]})")
    return errs


def frame_name(frame: int, out: dict) -> str:
    return f"{frame:0{int(out['pad'])}d}.{out['ext']}"


def frame_of(name: str, ext: str = "") -> int | None:
    """The frame number of a frame file's name (NNNN.ext), else None."""
    stem, dot, x = name.rpartition("/")[2].rpartition(".")
    if not dot or (ext and x != ext) or not stem.isdigit():
        return None
    return int(stem)


def todo(chunk: dict, have: dict, job: dict, *, contiguous: bool) -> dict | None:
    """What is left of a chunk, given the frames already in the output and trusted (`have`: {frame: ...}).

    contiguous (UE: temporal history, sims): one range from the first missing frame to the last, pre-rolled again
    from that frame; frames in between that exist are rendered (for the history) but not uploaded again.
    Not contiguous (Blender): just the missing frames.
    None when every frame is there."""
    missing = [f for f in range(chunk["start"], chunk["end"]) if f not in have]
    if not missing:
        return None
    if contiguous:
        a, b = missing[0], missing[-1] + 1
        rf = preroll_from(a, job["frames"][0], job.get("cuts") or [], int(job.get("preroll", 0)))
        return {"render_from": rf, "start": a, "end": b, "frames": list(range(a, b)), "missing": missing,
                "preroll": a - rf}
    return {"render_from": missing[0], "start": missing[0], "end": missing[-1] + 1, "frames": missing,
            "missing": missing, "preroll": 0}


def runs(frames: list) -> list[tuple[int, int]]:
    """Sorted frames as [start, end) runs: [1,2,3,7,8] -> [(1,4), (7,9)]."""
    out = []
    for f in sorted(set(frames)):
        if out and out[-1][1] == f:
            out[-1] = (out[-1][0], f + 1)
        else:
            out.append((f, f + 1))
    return out


def eta_s(done: int, total: int, fps: float) -> float | None:
    """Seconds left at `fps` (all workers together), None when nothing is known yet."""
    if fps <= 0:
        return None
    return max(0, total - done) / fps
