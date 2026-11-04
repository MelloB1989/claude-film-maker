"""The canonical sequence document, pure (no `unreal`): what seq.describe returns, what a SEQUENCE SPEC compiles to,
what seq.plan diffs and seq.apply writes. One shape for reading and writing, so a describe fed back to apply is a
no-op, and copy / retime / offset are pure transforms of the document.

    {"sequence": "/Game/Seq/SEQ_A", "fps": "24", "tick_resolution": 24000, "range": [0, 240],
     "markers": [{"frame": 48, "label": "beat"}],
     "bindings": [{"name": "Hero", "kind": "possessable", "class": "SkeletalMeshActor", "parent": "", "bound": true}],
     "tracks": [TRACK, ...]}

A TRACK:
    {"kind": "transform", "binding": "Hero", "component": "", "name": "",
     "params": {...},                                   # kind-specific, track level (e.g. a material slot)
     "sections": [{"range": [0, 240] | [null, null], "row": 0, "params": {...},
                   "channels": {"location.x": {"keys": [[0, 0.0, "auto"], ...], "default": null}, ...}}]}

Its identity is (kind, binding, component, name): `name` is the property path (float/bool/color/... tracks), the track's
display name (audio, event, sub), "slot:N" (material), the collection path (mpc), else "". A binding is an actor label;
a component binding is the actor label plus `component` (its name). Master tracks have binding "".
Frames are display frames; section `offset`s are seconds into the clip; colours are linear floats.
"""
from __future__ import annotations

import copy as _copy

from ._curves import keys_equal, values_equal
from ._time import snap

# kind -> (channel names in engine order, value type, whether the track holds one section per param (partial))
KINDS = {
    "transform": (["location.x", "location.y", "location.z", "rotation.roll", "rotation.pitch", "rotation.yaw",
                   "scale.x", "scale.y", "scale.z"], float),
    "float": (["value"], float),
    "double": (["value"], float),
    "bool": (["value"], bool),
    "byte": (["value"], int),
    "integer": (["value"], int),
    "string": (["value"], str),
    "visibility": (["visible"], bool),
    "spawn": (["spawned"], bool),
    "color": (["r", "g", "b", "a"], float),
    "vector": (["x", "y", "z", "w"], float),
    "anim": (["weight"], float),
    "audio": (["volume", "pitch"], float),
    "camera_cut": ([], None),
    "fade": (["value"], float),
    "level_visibility": ([], None),
    "material": ([], None),       # channels are parameter names (scalar keys floats, vector keys [r,g,b,a])
    "mpc": ([], None),            # channels are the collection's parameter names
    "event": ([], None),
    "shot": ([], None),
    "sub": ([], None),
}
# kinds whose channels are independent parameters: apply replaces only the channels a spec names
PARTIAL = {"material", "mpc"}
# kinds that live on the sequence itself, not on a binding
MASTER = {"camera_cut", "fade", "level_visibility", "shot", "sub", "mpc", "audio", "event"}
TRANSFORM_CHANNELS = KINDS["transform"][0]


def track_id(t: dict) -> tuple:
    return (t["kind"], t.get("binding") or "", t.get("component") or "", t.get("name") or "")


def track_label(t: dict) -> str:
    """A short readable name for a track: "Hero.Body/anim", "Light/float:Intensity", "/camera_cut"."""
    b = t.get("binding") or ""
    if t.get("component"):
        b += "." + t["component"]
    return f"{b}/{t['kind']}" + (f":{t['name']}" if t.get("name") else "")


def new_track(kind: str, binding: str = "", component: str = "", name: str = "", params: dict | None = None,
              sections: list | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown track kind {kind!r}: one of {', '.join(sorted(KINDS))}")
    return {"kind": kind, "binding": binding or "", "component": component or "", "name": name or "",
            "params": dict(params or {}), "sections": list(sections or [])}


def new_section(rng=(None, None), row: int = 0, params: dict | None = None, channels: dict | None = None) -> dict:
    return {"range": [None if rng[0] is None else snap(rng[0]), None if rng[1] is None else snap(rng[1])],
            "row": int(row), "params": dict(params or {}), "channels": dict(channels or {})}


def channel(keys: list | None = None, default=None) -> dict:
    return {"keys": list(keys or []), "default": default}


def index(doc_or_tracks) -> dict:
    tracks = doc_or_tracks["tracks"] if isinstance(doc_or_tracks, dict) else doc_or_tracks
    return {track_id(t): t for t in tracks}


# --- equality ----------------------------------------------------------------------------------------------------------

def _params_equal(a: dict, b: dict, tol: float, only: set | None = None) -> bool:
    keys = (set(a) | set(b)) if only is None else only
    for k in keys:
        if k.startswith("_"):
            continue
        if not values_equal(a.get(k), b.get(k), tol):
            return False
    return True


def channel_equal(a: dict | None, b: dict | None, tol: float = 1e-4) -> bool:
    a, b = a or channel(), b or channel()
    if not keys_equal(a.get("keys") or [], b.get("keys") or [], tol):
        return False
    da, db = a.get("default"), b.get("default")
    if da is None or db is None:  # an unspecified default is no claim
        return True
    return values_equal(da, db, tol)


def section_equal(a: dict, b: dict, tol: float = 1e-4, channels: set | None = None) -> bool:
    if list(a.get("range") or [None, None]) != list(b.get("range") or [None, None]):
        return False
    if int(a.get("row", 0)) != int(b.get("row", 0)):
        return False
    # params the desired section names are compared; the engine may report more (defaults) than a spec says
    if not _params_equal(a.get("params") or {}, b.get("params") or {}, tol, only=set(a.get("params") or {})):
        return False
    names = channels if channels is not None else set(a.get("channels") or {}) | set(b.get("channels") or {})
    return all(channel_equal((a.get("channels") or {}).get(n), (b.get("channels") or {}).get(n), tol) for n in names)


def track_equal(want: dict, have: dict | None, tol: float = 1e-4) -> bool:
    """`have` (read from the engine) already is what `want` (desired) asks for. Desired params and channels are what
    counts: extra engine-side detail (defaults it reports, params a spec leaves alone) does not make them differ.
    For PARTIAL kinds only the desired channels are compared."""
    if have is None:
        return False
    if not _params_equal(want.get("params") or {}, have.get("params") or {}, tol, only=set(want.get("params") or {})):
        return False
    ws, hs = want.get("sections") or [], have.get("sections") or []
    if want["kind"] in PARTIAL:
        names = {n for s in ws for n in (s.get("channels") or {})}
        hs_all = {n: c for s in hs for n, c in (s.get("channels") or {}).items()}
        ws_all = {n: c for s in ws for n, c in (s.get("channels") or {}).items()}
        return all(channel_equal(ws_all[n], hs_all.get(n), tol) and hs_all.get(n) is not None for n in names)
    if len(ws) != len(hs):
        return False
    key = lambda s: (s.get("row", 0), -1e18 if s["range"][0] is None else s["range"][0])  # noqa: E731
    return all(section_equal(w, h, tol) for w, h in zip(sorted(ws, key=key), sorted(hs, key=key)))


# --- time transforms (copy, retime, offset) ------------------------------------------------------------------------

def _map(f, fn):
    return None if f is None else snap(fn(f))


def transform_time(doc: dict, *, offset: float = 0.0, scale: float = 1.0, pivot: float = 0.0,
                   after: float | None = None, fps: float | None = None) -> tuple:
    """A copy of `doc` (a sequence document, or one track) with time mapped f -> pivot + (f - pivot) * scale + offset.
    `after`: only what lies at or after that frame moves (a ripple: insert time with offset > 0, close a gap with
    offset < 0); sections straddling it keep their start and stretch. Animation sections play at rate / scale so
    they still fit; audio cannot be retimed (its pitch would change): it is moved, not stretched, and noted.
    Returns (new doc, notes)."""
    if scale <= 0:
        raise ValueError(f"scale must be > 0, got {scale}")
    notes: list = []

    def fn(f):
        if after is not None and f < after:
            return f
        return pivot + (f - pivot) * scale + offset

    out = _copy.deepcopy(doc)
    tracks = out["tracks"] if "tracks" in out else [out]
    for t in tracks:
        for s in t.get("sections") or []:
            s0, s1 = s["range"]
            n0, n1 = _map(s0, fn), _map(s1, fn)
            if t["kind"] == "audio" and scale != 1.0 and s0 is not None and s1 is not None:
                n1 = snap(n0 + (s1 - s0))
                notes.append(f"{track_label(t)}: audio at {s0} moved, not stretched (scale {scale})")
            s["range"] = [n0, n1]
            if t["kind"] == "anim" and scale != 1.0:
                s["params"]["rate"] = float(s["params"].get("rate", 1.0)) / scale
            for c in (s.get("channels") or {}).values():
                for k in c.get("keys") or []:
                    k[0] = snap(fn(k[0]))
                    if scale != 1.0 and len(k) > 3 and k[3]:
                        for n in ("arrive", "leave"):
                            if n in k[3]:
                                k[3][n] = k[3][n] / scale  # slope per frame shrinks as time stretches
    if "range" in out and isinstance(out["range"], list):
        a, b = out["range"]
        out["range"] = [_map(a, fn), _map(b, fn)]
    for m in out.get("markers") or []:
        m["frame"] = snap(fn(m["frame"]))
    return out, notes


def clip(doc: dict, start: float, end: float, *, to: float = 0.0, fps: float = 24.0) -> tuple:
    """The part of `doc` in [start, end), moved so `start` lands on `to`: sections cut to the window (an animation or
    audio section cut at its head starts that much later into its clip), keys outside it dropped with a key added at
    each edge holding the value there (so the curve reads the same inside), markers inside kept. For copying a shot
    out of a long sequence. Returns (new doc, notes)."""
    from ._curves import evaluate
    notes: list = []
    out = _copy.deepcopy(doc)
    tracks = out["tracks"] if "tracks" in out else [out]
    kept = []
    for t in tracks:
        secs = []
        for s in t.get("sections") or []:
            s0, s1 = s["range"]
            lo = start if s0 is None else max(s0, start)
            hi = end if s1 is None else min(s1, end)
            if hi <= lo:
                continue
            if s0 is not None and lo > s0 and t["kind"] in ("anim", "audio"):
                rate = float(s["params"].get("rate", 1.0))
                s["params"]["offset"] = round(float(s["params"].get("offset", 0.0)) + (lo - s0) / fps * rate, 6)
            if s0 is not None and lo > s0 and t["kind"] in ("shot", "sub"):
                s["params"]["offset"] = snap(float(s["params"].get("offset", 0)) + (lo - s0) * float(
                    s["params"].get("timescale", 1.0)))
            s["range"] = [None if s0 is None else snap(lo - start + to), None if s1 is None else snap(hi - start + to)]
            for name, c in (s.get("channels") or {}).items():
                ks = c.get("keys") or []
                if not ks:
                    continue
                inside = [list(k) for k in ks if start <= k[0] < end]
                head = [] if any(k[0] == start for k in inside) else [[start, evaluate(ks, start), ks[0][2]]]
                last_in = [k for k in ks if k[0] < end]
                tail = []
                if any(k[0] >= end for k in ks):
                    tail = [[end - 1, evaluate(ks, end - 1), "auto"]] if not any(k[0] == end - 1 for k in inside) else []
                ks2 = head + inside + tail if (inside or last_in) else [[start, evaluate(ks, start), ks[0][2]]]
                for k in ks2:
                    k[0] = snap(k[0] - start + to)
                c["keys"] = ks2
            secs.append(s)
        if secs or not t.get("sections"):
            t["sections"] = secs
            kept.append(t)
        else:
            notes.append(f"{track_label(t)}: nothing in [{start}, {end}), left out")
    if "tracks" in out:
        out["tracks"] = kept
        out["range"] = [snap(to), snap(to + end - start)]
        out["markers"] = [dict(m, frame=snap(m["frame"] - start + to)) for m in out.get("markers") or []
                          if start <= m["frame"] < end]
    return out, notes


def stretch(doc: dict, start: float, end: float, scale: float) -> tuple:
    """A copy of `doc` with the span [start, end) played `scale` times as long and everything after it moved by the
    difference (a ripple): f < start stays, start <= f <= end -> start + (f - start) * scale, f > end -> f + (end -
    start) * (scale - 1). Animation sections wholly inside play at rate / scale; ones straddling an edge keep their
    rate (noted); audio moves, never stretches (noted). Returns (new doc, notes)."""
    if scale <= 0 or end <= start:
        raise ValueError(f"stretch needs start < end and scale > 0, got [{start}, {end}) x{scale}")
    notes: list = []

    def fn(f):
        if f < start:
            return f
        if f <= end:
            return start + (f - start) * scale
        return f + (end - start) * (scale - 1)

    out = _copy.deepcopy(doc)
    tracks = out["tracks"] if "tracks" in out else [out]
    for t in tracks:
        for s in t.get("sections") or []:
            s0, s1 = s["range"]
            inside = s0 is not None and s1 is not None and start <= s0 and s1 <= end
            if t["kind"] == "audio" and s0 is not None and s1 is not None:
                n0 = fn(s0)
                s["range"] = [snap(n0), snap(n0 + (s1 - s0))]
                if scale != 1.0 and (start <= s0 < end or start < s1 <= end):
                    notes.append(f"{track_label(t)}: audio at {s0} moved, not stretched")
            else:
                s["range"] = [_map(s0, fn), _map(s1, fn)]
            if t["kind"] == "anim" and scale != 1.0:
                if inside:
                    s["params"]["rate"] = float(s["params"].get("rate", 1.0)) / scale
                elif s0 is not None and s1 is not None and s0 < end and start < s1:
                    notes.append(f"{track_label(t)}: the animation section [{s0}, {s1}) straddles the stretch; its "
                                 f"rate is kept")
            for c in (s.get("channels") or {}).values():
                for k in c.get("keys") or []:
                    inside_k = start <= k[0] <= end
                    k[0] = snap(fn(k[0]))
                    if inside_k and scale != 1.0 and len(k) > 3 and k[3]:
                        for n in ("arrive", "leave"):
                            if n in k[3]:
                                k[3][n] = k[3][n] / scale
    if "range" in out and isinstance(out["range"], list):
        out["range"] = [_map(out["range"][0], fn), _map(out["range"][1], fn)]
    for m in out.get("markers") or []:
        m["frame"] = snap(fn(m["frame"]))
    return out, notes
