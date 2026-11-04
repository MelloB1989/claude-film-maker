"""Render shots -> cut -> mix -> deliver, generic: Unreal's per-shot frame sequences (Movie Render Queue output) and
the sound in, the deliverables out, from one declarative `delivery` spec. Generalised from the karma reel's cut.py
(fleet/agent-07/reel-assembly): nothing here names a film.

    kind: delivery            # JSON or YAML
    version: 1
    name: demo                # outputs are <out>/<name>-<output>.<ext>
    fps: 24
    out: out/demo             # relative to the spec's folder
    shots:                    # frames on the sequence's clock, [start, end)
      - {id: S01, start: 0, end: 48, frames: renders/S01}      # frames dir; pattern "{frame:04d}.png" by default,
      - {id: S02, start: 48, end: 120, frames: renders/S02, pattern: "SQ.{frame:04d}.png", offset: 0}
    edl: [[0, 24], [48, 120]] # optional: the sequence frames kept, in order (default: every shot, whole)
    fill: slate               # optional: a missing frame becomes a black slate instead of an error
    audio:                    # optional (silence otherwise)
      mix: mix.wav            # a finished mix on the sequence's clock, or build one:
      timing: timing.json     # an `audio` timing document (audio_timing): each line at its frame
      music: score.wav        # ducked under the voice (filmtools.mix.premix)
      lufs: -14
      true_peak: -1
    captions: {max_chars: 64, hold_frames: 6}     # from the timing document's words; SRT + VTT beside the outputs
    outputs:
      - {name: master, preset: prores4444}
      - {name: web, preset: h264, height: 1080, captions: burn}
      - {name: vertical, preset: h264, aspect: "9:16", height: 1920, crop: {S01: [[0, 0.3], [24, 0.6]]}}

Frame numbering: MRQ numbers a shot's frames on the sequence's clock ({frame} = the sequence frame) or from 0 (a shot
rendered as its own sequence). Both are found: a shot's frames are looked for at `frame - offset` and at
`frame - start - offset`, whichever has more of them. The picture and the sound both start at the output's frame 0
and run exactly as long; the sound is never offset with -itsoffset, -ss or trimmed by -shortest.

`plan(spec)` returns every step (with its ffmpeg argv) without running anything: `film-post plan spec.yaml --json`.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import audio_timing

KIND, VERSION = "delivery", 1
BT709 = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
AAC = ["-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart"]
PRESETS = {
    # name: (extension, video args, audio args)
    "prores4444": ("mov", ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuv444p10le", "-vendor", "apl0"],
                   ["-c:a", "pcm_s24le", "-ar", "48000"]),
    "prores422hq": ("mov", ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le", "-vendor", "apl0"],
                    ["-c:a", "pcm_s24le", "-ar", "48000"]),
    "h264": ("mp4", ["-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high", "-pix_fmt", "yuv420p",
                     "-g", "48", "-bf", "2"], AAC),
    "hevc": ("mp4", ["-c:v", "libx265", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p10le", "-profile:v",
                     "main10", "-tag:v", "hvc1", "-x265-params", "log-level=error"], AAC),
}
SPEC_KEYS = {"kind", "version", "name", "fps", "out", "shots", "edl", "fill", "audio", "captions", "outputs", "size"}
SHOT_KEYS = {"id", "start", "end", "frames", "pattern", "offset"}
AUDIO_KEYS = {"mix", "timing", "music", "lufs", "true_peak", "xfade_s"}
CAPTION_KEYS = {"max_chars", "hold_frames", "source"}
OUTPUT_KEYS = {"name", "preset", "height", "aspect", "crop", "captions", "crf", "fit"}
XFADE_S = 0.012  # the equal-power crossfade at each sound edit, centred on the cut


class SpecError(ValueError):
    pass


def _unknown(where: str, d: dict, known: set) -> None:
    extra = set(d) - known
    if extra:
        raise SpecError(f"{where}: unknown key(s) {', '.join(sorted(extra))} (known: {', '.join(sorted(known))})")


def even(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


# --- the spec --------------------------------------------------------------------------------------------------------


def load_spec(path: Path | str) -> dict:
    """A delivery spec from JSON or YAML, validated, with `_root` (its folder) for relative paths."""
    p = Path(path)
    text = p.read_text()
    if p.suffix.lower() in (".yaml", ".yml"):
        import yaml
        doc = yaml.safe_load(text)
    else:
        doc = json.loads(text)
    return validate(doc, root=p.parent)


def validate(doc: dict, root: Path | str = ".") -> dict:
    """The spec with defaults filled in, or a SpecError naming the first problem."""
    if not isinstance(doc, dict) or doc.get("kind") != KIND:
        raise SpecError(f"not a delivery spec (kind: {KIND})")
    _unknown("spec", doc, SPEC_KEYS)
    if int(doc.get("version", VERSION)) != VERSION:
        raise SpecError(f"version {doc['version']}: this tool reads version {VERSION}")
    s = {"name": "cut", "out": "out", "edl": None, "fill": None, "audio": {}, "captions": None, "size": None,
         **doc, "_root": str(root)}
    if not s.get("fps") or float(s["fps"]) <= 0:
        raise SpecError("fps: give the sequence's frame rate (frames per second)")
    s["fps"] = float(s["fps"])
    if not s.get("shots"):
        raise SpecError("shots: at least one {id, start, end, frames}")
    prev = None
    for sh in s["shots"]:
        _unknown(f"shot {sh.get('id')}", sh, SHOT_KEYS)
        for k in ("id", "start", "end", "frames"):
            if k not in sh:
                raise SpecError(f"shot {sh.get('id')}: no {k}")
        if not int(sh["start"]) < int(sh["end"]):
            raise SpecError(f"shot {sh['id']}: start {sh['start']} is not before end {sh['end']}")
        if prev and int(sh["start"]) < int(prev["end"]):
            raise SpecError(f"shot {sh['id']} starts at {sh['start']}, inside {prev['id']} (ends {prev['end']}): "
                            "shots are in order on the sequence's clock and do not overlap")
        prev = sh
    lo, hi = int(s["shots"][0]["start"]), int(s["shots"][-1]["end"])
    if s["edl"] is None:
        s["edl"] = [[int(sh["start"]), int(sh["end"])] for sh in s["shots"]]
        s["edl"] = merge(s["edl"])
    s["edl"] = [[int(a), int(b)] for a, b in s["edl"]]
    for a, b in s["edl"]:
        if not lo <= a < b <= hi:
            raise SpecError(f"edl {a}:{b} is empty or outside the shots ({lo}:{hi})")
    if s["fill"] not in (None, "slate"):
        raise SpecError("fill: 'slate' or leave it out")
    _unknown("audio", s["audio"], AUDIO_KEYS)
    if s["audio"].get("mix") and (s["audio"].get("timing") or s["audio"].get("music")):
        raise SpecError("audio: give a finished mix, or timing/music to build one, not both")
    if s["captions"] is not None:
        _unknown("captions", s["captions"], CAPTION_KEYS)
    if not s.get("outputs"):
        raise SpecError("outputs: at least one {name, preset}")
    names = set()
    for o in s["outputs"]:
        _unknown(f"output {o.get('name')}", o, OUTPUT_KEYS)
        if o.get("preset") not in PRESETS:
            raise SpecError(f"output {o.get('name')}: preset {o.get('preset')!r} is not one of {', '.join(PRESETS)}")
        if not o.get("name") or o["name"] in names:
            raise SpecError(f"output {o.get('name')!r}: a name is required and must be unique")
        names.add(o["name"])
        if o.get("captions") not in (None, "burn"):
            raise SpecError(f"output {o['name']}: captions is 'burn' or left out (SRT/VTT are always written)")
        if o.get("captions") and s["captions"] is None:
            raise SpecError(f"output {o['name']} burns captions but the spec has no captions section")
        if o.get("aspect") and not re.fullmatch(r"\d+:\d+", str(o["aspect"])):
            raise SpecError(f"output {o['name']}: aspect is 'W:H' (e.g. '9:16')")
    return s


def path_of(spec: dict, p: str | None) -> Path | None:
    if not p:
        return None
    q = Path(p)
    return q if q.is_absolute() else Path(spec["_root"]) / q


# --- the edit (pure) -------------------------------------------------------------------------------------------------


def merge(segs: list) -> list:
    """Adjacent [a, b) segments joined (shots back to back are one piece of the sequence)."""
    out = []
    for a, b in segs:
        if out and out[-1][1] == a:
            out[-1][1] = b
        else:
            out.append([a, b])
    return out


def length(segs: list) -> int:
    return sum(b - a for a, b in segs)


def to_out(segs: list, f: float) -> float | None:
    """The output frame of sequence frame f, None if the edit cut it."""
    off = 0
    for a, b in segs:
        if a <= f < b:
            return off + f - a
        off += b - a
    return None


def spans_out(segs: list, a: float, b: float) -> list:
    """Sequence [a, b) on the output's clock: one (x, y) per piece of the edit it falls in."""
    out, off = [], 0
    for sa, sb in segs:
        lo, hi = max(a, sa), min(b, sb)
        if lo < hi:
            out.append((off + lo - sa, off + hi - sa))
        off += sb - sa
    return out


def timecode(frame: int, fps: float) -> str:
    """HH:MM:SS:FF, non-drop (the nominal rate rounded: 23.976 counts as 24)."""
    n = int(round(fps))
    f = int(frame)
    return f"{f // (3600 * n):02d}:{f // (60 * n) % 60:02d}:{f // n % 60:02d}:{f % n:02d}"


def cmx3600(spec: dict, reel: str = "AX") -> str:
    """The edit as a CMX 3600 EDL (one video event per piece of each shot), for an NLE to conform the renders."""
    fps, segs = spec["fps"], spec["edl"]
    lines, n, rec = [f"TITLE: {spec['name'].upper()}", "FCM: NON-DROP FRAME", ""], 1, 0
    for a, b in segs:
        for sh in spec["shots"]:
            lo, hi = max(a, sh["start"]), min(b, sh["end"])
            if lo >= hi:
                continue
            lines.append(f"{n:03d}  {reel:<8} V     C        {timecode(lo, fps)} {timecode(hi, fps)} "
                         f"{timecode(rec, fps)} {timecode(rec + hi - lo, fps)}")
            lines.append(f"* FROM CLIP NAME: {sh['id']}")
            rec += hi - lo
            n += 1
    return "\n".join(lines) + "\n"


# --- captions (pure) -------------------------------------------------------------------------------------------------


def _alnum(t: str) -> int:
    return sum(ch.isalnum() for ch in t)


def caption_cues(doc: dict, max_chars: int = 64, hold_frames: int = 6) -> list:
    """Captions from a timing document: each line split at its clauses into cues of at most max_chars, each running
    from its first spoken word to its last (matched by letters and digits), held hold_frames after unless the next
    begins. A line with no words is spread over its frames by characters. [[start, end, text]] on the sequence's
    clock."""
    out = []
    for ln in doc["lines"]:
        text = ln.get("text") or " ".join(w["w"] for w in ln.get("words", []))
        if not text.strip():
            continue
        chunks = []
        for p in (p for p in re.split(r"(?<=[.,:;?!—…])\s+", text.strip()) if p):
            if chunks and len(chunks[-1]) + 1 + len(p) <= max_chars:
                chunks[-1] += " " + p
            else:
                chunks.append(p)
        ws = ln.get("words") or []
        if ws and _alnum("".join(chunks)) == _alnum("".join(w["w"] for w in ws)):
            i = 0
            for c in chunks:
                need, j = _alnum(c), i
                while need > 0 and j < len(ws):
                    need -= _alnum(ws[j]["w"])
                    j += 1
                out.append([ws[i]["start_frame"], ws[j - 1]["end_frame"], c])
                i = j
            continue
        first = ws[0]["start_frame"] if ws else ln["start_frame"]
        last = ws[-1]["end_frame"] if ws else ln["end_frame"]
        n, t = sum(len(c) for c in chunks), first
        for c in chunks:
            d = round((last - first) * len(c) / n)
            out.append([t, t + d, c])
            t += d
        out[-1][1] = last
    out.sort(key=lambda c: c[0])
    for a, b in zip(out, out[1:]):
        a[1] = min(a[1] + hold_frames, b[0])
    if out:
        out[-1][1] += hold_frames
    return out


def _stamp(f: float, fps: float, sep: str) -> str:
    ms = int(round(f * 1000 / fps))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def captions_text(cues: list, segs: list, fps: float) -> tuple[str, str]:
    """(SRT, VTT) for the cues as the edit keeps them, on the output's clock."""
    keep = [(x, y, t) for a, b, t in cues for x, y in spans_out(segs, a, b)]
    srt = "".join(f"{i}\n{_stamp(a, fps, ',')} --> {_stamp(b, fps, ',')}\n{t}\n\n" for i, (a, b, t) in enumerate(keep, 1))
    vtt = "WEBVTT\n\n" + "".join(f"{_stamp(a, fps, '.')} --> {_stamp(b, fps, '.')}\n{t}\n\n" for a, b, t in keep)
    return srt, vtt


# --- frames ----------------------------------------------------------------------------------------------------------


def find_frames(spec: dict) -> dict:
    """{sequence frame: Path or None} for every frame the edit keeps, per shot from its frames dir (sequence or
    shot-local numbering, whichever has more)."""
    found = {}
    for sh in spec["shots"]:
        need = [f for a, b in spec["edl"] for f in range(max(a, sh["start"]), min(b, sh["end"]))]
        if not need:
            continue
        d, pat, off = path_of(spec, sh["frames"]), sh.get("pattern", "{frame:04d}.png"), int(sh.get("offset", 0))
        best = {}
        for base in (0, int(sh["start"])):
            hit = {f: d / pat.format(frame=f - base - off) for f in need}
            hit = {f: p for f, p in hit.items() if p.exists()}
            if len(hit) > len(best):
                best = hit
        found.update({f: best.get(f) for f in need})
    return found


def missing_report(spec: dict, found: dict) -> str:
    by = {}
    for f in sorted(k for k, v in found.items() if v is None):
        sh = next(s for s in spec["shots"] if s["start"] <= f < s["end"])
        by.setdefault(sh["id"], []).append(f)
    return ", ".join(f"{k} {v[0]}-{v[-1]} ({len(v)} frames)" for k, v in by.items())


def png_size(path: Path) -> tuple[int, int]:
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise SpecError(f"{path} is not a PNG (set the shot's pattern to the renders' extension, or render PNG)")
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def stage(spec: dict, found: dict, work: Path, size: tuple[int, int]) -> Path:
    """Link the frames in output order (seq/00000.png ...) so ffmpeg reads one image sequence; a slate (black) for a
    missing frame when spec.fill is 'slate'."""
    seq = work / "seq"
    shutil.rmtree(seq, ignore_errors=True)
    seq.mkdir(parents=True)
    if any(v is None for v in found.values()):
        if spec.get("fill") != "slate":
            raise SpecError("missing frames (fill: slate to stand black in): " + missing_report(spec, found))
        slate = work / "slate.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={size[0]}x{size[1]}",
                        "-frames:v", "1", str(slate)], check=True)
    for f, p in found.items():
        (seq / f"{int(to_out(spec['edl'], f)):05d}.png").symlink_to(Path(p).resolve() if p else work / "slate.png")
    return seq


# --- the sound -------------------------------------------------------------------------------------------------------


def vo_bus_args(doc: dict, wav_root: Path, out: Path, fps: float) -> list[str]:
    """ffmpeg argv that lays every line of a timing document at its frame on one 48 kHz stereo bus (adelay, no
    normalisation), from the sequence's frame 0."""
    ins, graph = [], []
    for k, ln in enumerate(doc["lines"]):
        p = Path(ln["wav"])
        ins += ["-i", str(p if p.is_absolute() else wav_root / p)]
        ms = int(round(ln["start_frame"] / fps * 1000))
        head = f"atrim=start={ln['offset_s']:.6f},asetpts=PTS-STARTPTS," if ln.get("offset_s") else ""
        gain = f",volume={ln['volume_db']:.2f}dB" if ln.get("volume_db") else ""
        graph.append(f"[{k}:a]{head}aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}:all=1{gain}[v{k}]")
    graph.append("".join(f"[v{k}]" for k in range(len(doc["lines"]))) +
                 f"amix=inputs={len(doc['lines'])}:normalize=0:duration=longest[vo]")
    return ["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(graph), "-map", "[vo]", "-ar", "48000",
            "-c:a", "pcm_s24le", str(out)]


def cut_audio_args(src: Path, segs: list, fps: float, out: Path, xfade_s: float = XFADE_S) -> list[str]:
    """ffmpeg argv that cuts a sequence-clock track on the edit: each piece in order, an equal-power crossfade
    centred on each cut, padded or trimmed to exactly the picture's length."""
    d = length(segs) / fps
    if len(segs) == 1:
        a, b = segs[0][0] / fps, segs[0][1] / fps
        return ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af",
                f"atrim=start={a:.6f}:end={b:.6f},asetpts=PTS-STARTPTS,apad=whole_dur={d:.6f},atrim=end={d:.6f}",
                "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", str(out)]
    x, graph = xfade_s / 2, []
    for i, (a, b) in enumerate(segs):  # each inner side runs x past the cut: each crossfade eats 2x
        lo = a / fps - (x if i else 0)
        hi = b / fps + (x if i < len(segs) - 1 else 0)
        graph.append(f"[0:a]atrim=start={max(lo, 0):.6f}:end={hi:.6f},asetpts=PTS-STARTPTS[p{i}]")
    last = "p0"
    for i in range(1, len(segs)):
        graph.append(f"[{last}][p{i}]acrossfade=d={xfade_s}:c1=qsin:c2=qsin[x{i}]")
        last = f"x{i}"
    graph.append(f"[{last}]apad=whole_dur={d:.6f},atrim=end={d:.6f}[out]")
    return ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", ";".join(graph), "-map", "[out]",
            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", str(out)]


# --- the picture -----------------------------------------------------------------------------------------------------


def out_size(o: dict, src: tuple[int, int]) -> tuple[int, int]:
    """An output's size: its aspect (default the source's) at its height (default the source's)."""
    sw, sh = src
    aw, ah = (map(int, str(o["aspect"]).split(":")) if o.get("aspect") else (sw, sh))
    h = int(o.get("height") or sh)
    return even(h * aw / ah), even(h)


def crop_expr(spec: dict, o: dict, src_w: int, crop_w: int) -> str:
    """ffmpeg crop x for output frame n when an output's aspect is narrower than the source: per shot its keys
    [[frame in the shot, centre 0..1], ...] (default centred) eased by smoothstep; nested if()s, commas escaped."""
    keys_of = o.get("crop") or {}

    def x(c):
        return min(max(c * src_w - crop_w / 2, 0), src_w - crop_w)
    parts, off = [], 0
    for a, b in spec["edl"]:
        for sh in spec["shots"]:
            if sh["end"] <= a or sh["start"] >= b:
                continue
            ks = keys_of.get(sh["id"], [[0, 0.5]])
            ks = [[0, float(ks)]] if isinstance(ks, (int, float)) else [[int(f), float(c)] for f, c in ks]
            n0 = off + sh["start"] - a  # n of the shot's first frame (before the piece when the piece starts inside)
            expr = f"{x(ks[-1][1]):.1f}"
            for (fa, ca), (fb, cb) in reversed(list(zip(ks, ks[1:]))):
                u = f"clip((n-{n0 + fa})/{fb - fa}\\,0\\,1)"
                expr = f"if(lt(n\\,{n0 + fb})\\,{x(ca):.1f}+({x(cb) - x(ca):.1f})*{u}*{u}*(3-2*{u})\\,{expr})"
            if ks[0][0]:
                expr = f"if(lt(n\\,{n0 + ks[0][0]})\\,{x(ks[0][1]):.1f}\\,{expr})"
            parts.append((off + min(sh["end"], b) - a, expr))
        off += b - a
    out = parts[-1][1]
    for end, expr in reversed(parts[:-1]):
        out = f"if(lt(n\\,{end})\\,{expr}\\,{out})"
    return f"floor({out})"


def _sub_path(p: Path) -> str:
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def encode_args(spec: dict, o: dict, seq: Path, audio: Path, src: tuple[int, int], srt: Path | None, out: Path) -> list:
    """ffmpeg argv for one output: the staged frames (RGB -> BT.709 limited range, explicitly: ffmpeg's implicit
    conversion is BT.601), cropped to the output's aspect if it is narrower, scaled, captions burned in (libass)
    if asked, the cut's audio from 0, exactly the edit's frame count."""
    ext, vargs, aargs = PRESETS[o["preset"]]
    n, fps = length(spec["edl"]), spec["fps"]
    w, h = out_size(o, src)
    sw, sh = src
    chain = []
    if w / h < sw / sh - 1e-3:  # narrower: crop a window of the source, keyed per shot
        cw = even(sh * w / h)
        chain.append(f"crop=w={cw}:h={sh}:x='{crop_expr(spec, o, sw, cw)}':y=0")
    elif w / h > sw / sh + 1e-3:
        raise SpecError(f"output {o['name']}: {w}x{h} is wider than the source {sw}x{sh}; crop is only to narrower")
    chain.append(f"scale={w}:{h}:flags=lanczos:out_color_matrix=bt709:out_range=tv")
    if o.get("captions") == "burn" and srt is not None:
        size = max(12, round(h / (34 if w < h else 26)))
        chain.append(f"subtitles='{_sub_path(srt)}':force_style='FontName=DejaVu Sans,FontSize={size},Outline=1,"
                     f"Shadow=1,MarginV={round(h * (0.2 if w < h else 0.06))}':original_size={w}x{h}")
    if o.get("crf") is not None and "-crf" in vargs:
        vargs = list(vargs)
        vargs[vargs.index("-crf") + 1] = str(o["crf"])
    return ["ffmpeg", "-v", "error", "-y", "-framerate", f"{fps:g}", "-i", str(seq / "%05d.png"), "-i", str(audio),
            "-map", "0:v", "-map", "1:a", "-vf", ",".join(chain), "-frames:v", str(n), "-r", f"{fps:g}", *vargs,
            *BT709, *aargs, str(out)]


def output_path(spec: dict, o: dict) -> Path:
    return path_of(spec, spec["out"]) / f"{spec['name']}-{o['name']}.{PRESETS[o['preset']][0]}"


# --- plan, run, check ------------------------------------------------------------------------------------------------


@dataclass
class Step:
    what: str
    argv: list = field(default_factory=list)
    writes: str = ""

    def to_json(self) -> dict:
        return {"what": self.what, "argv": [str(a) for a in self.argv], "writes": self.writes}


def plan(spec: dict, src_size: tuple[int, int] | None = None) -> list[Step]:
    """Every step of the delivery, without running anything. src_size: the renders' size (default spec.size, else
    read from the first frame found, else 1920x1080 for planning)."""
    fps, segs = spec["fps"], spec["edl"]
    out, work = path_of(spec, spec["out"]), path_of(spec, spec["out"]) / "work"
    src = tuple(src_size or spec.get("size") or (1920, 1080))
    steps = [Step(f"stage {length(segs)} frames from {len(spec['shots'])} shots in edit order", [], str(work / "seq"))]
    a = spec["audio"]
    seq_audio = work / "mix_seq.wav"
    if a.get("mix"):
        steps.append(Step("the finished mix (sequence clock)", ["cp", str(path_of(spec, a["mix"])), str(seq_audio)],
                          str(seq_audio)))
    elif a.get("timing"):
        doc = audio_timing.load(path_of(spec, a["timing"]))
        if float(doc["fps"]) != fps:
            doc = audio_timing.rescale(doc, fps)
        vo = work / "vo.wav"
        steps.append(Step(f"voice bus: {len(doc['lines'])} lines at their frames",
                          vo_bus_args(doc, path_of(spec, a["timing"]).parent, vo, fps), str(vo)))
        steps.append(Step("music ducked under the voice, mastered (filmtools.mix.premix + loudnorm)"
                          if a.get("music") else "voice mastered (filmtools.mix.loudnorm)",
                          ["filmtools.mix", str(vo), str(path_of(spec, a.get("music")) or ""), str(seq_audio)],
                          str(seq_audio)))
    else:
        steps.append(Step("silence (no audio section)", ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                                                         "anullsrc=r=48000:cl=stereo", "-t",
                                                         f"{segs[-1][1] / fps:.6f}", "-c:a", "pcm_s24le",
                                                         str(seq_audio)], str(seq_audio)))
    cut = work / "mix.wav"
    steps.append(Step(f"sound cut on the edit's {len(segs) - 1} cut(s), {length(segs)} frames long",
                      cut_audio_args(seq_audio, segs, fps, cut, float(a.get("xfade_s", XFADE_S))), str(cut)))
    srt = None
    if spec.get("captions") is not None:
        srt = out / f"{spec['name']}.srt"
        steps.append(Step("captions from the timing document's words (SRT, VTT)", [], str(srt)))
    for o in spec["outputs"]:
        p = output_path(spec, o)
        steps.append(Step(f"encode {o['name']} ({o['preset']}, {'x'.join(map(str, out_size(o, src)))})",
                          encode_args(spec, o, work / "seq", cut, src, srt, p), str(p)))
    steps.append(Step("cut.json: what was made, checked (frames, size, audio length, loudness)", [],
                      str(out / f"cut-{spec['name']}.json")))
    return steps


def _run(argv: list) -> None:
    r = subprocess.run([str(a) for a in argv], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{argv[0]} failed ({r.returncode}): {' '.join(map(str, argv))[:400]}\n{r.stderr[-2000:]}")


def master(vo: Path, music: Path | None, out: Path, lufs: float, work: Path) -> dict:
    """The voice (and music ducked under it) mastered to `lufs` with filmtools.mix (static gain + limiter)."""
    from ..mix import loudnorm, premix
    src = vo
    if music:
        src = work / "premix.wav"
        premix(vo, music, src)
    return loudnorm(src, out, lufs)


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format",
                        "-count_frames", str(path)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def check_output(info: dict, n: int, size: tuple[int, int], fps: float) -> list[str]:
    """Problems with one output from its ffprobe JSON (empty when it is right): one video and one audio stream, the
    frame count, the size, the audio's length against the picture's (within 1.5 frames)."""
    v = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    a = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    p = []
    if len(v) != 1 or len(a) != 1:
        return [f"{len(v)} video and {len(a)} audio streams, not 1 and 1"]
    frames = int(v[0].get("nb_read_frames") or v[0].get("nb_frames") or 0)
    if frames != n:
        p.append(f"{frames} frames, not {n}")
    if (int(v[0]["width"]), int(v[0]["height"])) != tuple(size):
        p.append(f"{v[0]['width']}x{v[0]['height']}, not {size[0]}x{size[1]}")
    ad = float(a[0].get("duration") or info.get("format", {}).get("duration") or 0)
    if abs(ad - n / fps) > 1.5 / fps:
        p.append(f"audio {ad:.3f} s against picture {n / fps:.3f} s")
    return p


def run(spec: dict, only: set | None = None, log=print) -> dict:
    """Make the deliverables. Returns the cut report (also written to <out>/cut-<name>.json)."""
    fps, segs = spec["fps"], spec["edl"]
    out = path_of(spec, spec["out"])
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    found = find_frames(spec)
    first = next((p for p in found.values() if p), None)
    if first is None:
        raise SpecError("no frames found for any shot: check each shot's frames dir and pattern ("
                        + missing_report(spec, found) + ")")
    src = tuple(spec.get("size") or png_size(first))
    seq = stage(spec, found, work, src)
    log(f"staged {len(found)} frames ({sum(1 for v in found.values() if v is None)} slates)")
    a, seq_audio = spec["audio"], work / "mix_seq.wav"
    report = {"name": spec["name"], "fps": fps, "frames": length(segs), "seconds": round(length(segs) / fps, 4),
              "edl": segs, "source_size": list(src), "outputs": []}
    lufs, tp = float(a.get("lufs", -14.0)), float(a.get("true_peak", -1.0))
    doc = None
    if a.get("timing"):
        doc = audio_timing.load(path_of(spec, a["timing"]))
        if float(doc["fps"]) != fps:
            doc = audio_timing.rescale(doc, fps)
    if a.get("mix"):
        shutil.copy(path_of(spec, a["mix"]), seq_audio)
        report["sound"] = "the finished mix"
    elif doc is not None:
        vo = work / "vo.wav"
        _run(vo_bus_args(doc, path_of(spec, a["timing"]).parent, vo, fps))
        m = master(vo, path_of(spec, a.get("music")), seq_audio, lufs, work)
        report["sound"] = f"{len(doc['lines'])} lines{' over the music' if a.get('music') else ''}, mastered: {m}"
    else:
        _run(plan(spec, src)[1].argv)
        report["sound"] = "silence"
    cut = work / "mix.wav"
    _run(cut_audio_args(seq_audio, segs, fps, cut, float(a.get("xfade_s", XFADE_S))))
    if a.get("mix") or doc is not None:
        from ..mix import loudnorm, measure
        m = measure(cut)
        if abs(m["I"] - lufs) > 0.5 or m["TP"] > tp:
            fixed = work / "mix_master.wav"
            m = loudnorm(cut, fixed, lufs)
            shutil.move(fixed, cut)
            report["sound"] += f"; the cut remastered to {lufs:g} LUFS"
        report["loudness"] = m
    srt = None
    if spec.get("captions") is not None:
        if doc is None:
            raise SpecError("captions need audio.timing (the words they are timed on)")
        c = spec["captions"]
        cues = caption_cues(doc, int(c.get("max_chars", 64)), int(c.get("hold_frames", 6)))
        s, v = captions_text(cues, segs, fps)
        srt = out / f"{spec['name']}.srt"
        srt.write_text(s)
        srt.with_suffix(".vtt").write_text(v)
        report["captions"] = {"cues": len(cues), "srt": str(srt)}
    (out / f"{spec['name']}.edl").write_text(cmx3600(spec))
    for o in spec["outputs"]:
        if only and o["name"] not in only:
            continue
        p = output_path(spec, o)
        log(f"encoding {p.name}")
        _run(encode_args(spec, o, seq, cut, src, srt, p))
        size = out_size(o, src)
        problems = check_output(probe(p), length(segs), size, fps)
        report["outputs"].append({"name": o["name"], "file": str(p), "size": list(size), "problems": problems})
    report["ok"] = all(not o["problems"] for o in report["outputs"])
    (out / f"cut-{spec['name']}.json").write_text(json.dumps(report, indent=1, default=str))
    return report


def frames_needed(spec: dict) -> dict:
    """Per shot, the sequence frames the edit keeps [[first, end)] (what to render: `render` only these ranges)."""
    out = {}
    for sh in spec["shots"]:
        r = [[max(a, sh["start"]), min(b, sh["end"])] for a, b in spec["edl"] if max(a, sh["start"]) < min(b, sh["end"])]
        if r:
            out[sh["id"]] = r
    return out


def seconds(spec: dict) -> float:
    return round(length(spec["edl"]) / spec["fps"], 4)

