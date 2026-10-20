"""Graded stills with ArtCraft's LightCraft + PhotoCraft, headless: photos for a film's `assets/`, posters, thumbnails,
social cuts (Instagram 4:5, stories), in a named look, cropped to an exact size, with a check that nothing went soft.

    photo ──► LightCraft: the look's develop settings + the photo's own, a sky mask, radial spots on people / faces,
          │   exported whole (uncropped, native size, 16-bit TIFF: LightCraft's crop path softens detail)
          └─► PhotoCraft: crop to the target's aspect + Lanczos resize, glow, light leak, output sharpening ──► JPEG
              check(): the result's fine detail against a Lanczos resize of the same crop of the ungraded photo

Looks are data (`LOOKS`, or a spec's own `looks` built on one of them): `clean` (true colour, lifted shadows, crisp),
`fresh` (true-to-life and punchy: vivid sky, true greens, deep blacks, no glow or grain), `golden-hour` (warm skin, olive
greens, soft bloom and a warm light leak from the top-left, fine grain). They are tuned on camera JPEG / HEIC files,
where LightCraft's white balance is relative (6500 = as shot); on raw files it is Kelvin, so a look's wb is left out.

Coordinates (crop, focus, spots) are 0..1 of the photo as it is shown (orientation applied), x right, y down.

CLI:
  python -m filmtools.artcraft.photo looks
  python -m filmtools.artcraft.photo grade PHOTO... --look fresh[,golden-hour] [--target instagram-portrait|WxH|W:H@L|film]
         [--crop x0,y0,x1[,y1] | --focus x,y --zoom Z] [--sky] [--spot x,y,r]... [--face x,y,r]...
         (--out DIR | --film ID) [--check] [--sheet] [--keep-tiff]
  python -m filmtools.artcraft.photo spec photos.json [--look ...] [--only a,b] [--out DIR | --film ID] [--check] [--sheet]

A spec (paths relative to it; an unknown key is an error):
  {"film": "showcase", "look": ["fresh"], "target": "instagram-portrait",
   "looks": {"fresh-warm": {"base": "fresh", "develop": {"wb.temp": 6700}}},
   "photos": [{"src": "IMG_1161.HEIC", "name": "01-hero", "crop": [0.21, 0.14, 0.83], "sky": true,
               "spots": [{"kind": "person", "at": [0.52, 0.42], "r": [0.11, 0.17]},
                         {"kind": "face", "at": [0.52, 0.345], "r": 0.035}],
               "develop": {"light.exposure": -0.15}, "looks": {"golden-hour": {"finish": {"leak": 8}}}}]}
Output: <out>/<look>/<name>.jpg and <out>/<look>/grade.json (what was done to each, and its detail ratio).
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import lightcraft as LC
from . import photocraft as PC

FACE_SOFT = {"texture": -30, "clarity": -10}           # skin, at soften 1; scaled by a photo's `soften`
RAW_EXT = {".dng", ".cr2", ".cr3", ".arw", ".nef", ".raf", ".rw2", ".rwl", ".pef", ".orf", ".srw"}
DETAIL_MIN = 0.95      # check(): below this the result is softer than a plain resize (LightCraft's own crop scored 0.53-0.87)

LOOKS = {
    "clean": {
        "about": "true colour, highlights held, shadows lifted, crisp; the baseline",
        "develop": {"light.highlights": -25, "light.shadows": 15, "light.whites": 5, "color.vibrance": 8,
                    "effects.clarity": 3, "detail.sharpenAmount": 15},
        "sky": {"exposure": -0.1, "saturation": 10},
        "person": {"exposure": 0.15, "shadows": 15}, "face": {"exposure": 0.1, "shadows": 10},
        "finish": {"sharpen": 30},
    },
    "fresh": {
        "about": "true-to-life and punchy: slightly cool, deep blacks, vivid sky, true greens; no glow, leak or grain",
        "develop": {"wb.temp": 6350, "wb.tint": 0, "light.exposure": 0.1, "light.contrast": 22, "light.highlights": -45,
                    "light.shadows": 20, "light.whites": 15, "light.blacks": -14, "curve.highlights": 5, "curve.darks": -8,
                    "color.vibrance": 30, "color.saturation": 5, "mixer.blue.sat": 20, "mixer.blue.lum": -15,
                    "mixer.aqua.sat": 10, "mixer.green.hue": 5, "mixer.green.sat": 10, "mixer.yellow.sat": -10,
                    "mixer.orange.sat": -8, "mixer.orange.lum": 12, "mixer.red.sat": -10, "grading.shadows.hue": 220,
                    "grading.shadows.sat": 6, "effects.clarity": 6, "effects.texture": 4, "effects.dehaze": 4,
                    "detail.sharpenAmount": 15},
        "sky": {"exposure": -0.2, "saturation": 25},
        "person": {"exposure": 0.2, "shadows": 20}, "face": {"exposure": 0.15, "shadows": 15},
        "finish": {"sharpen": 35},
    },
    "golden-hour": {
        "about": "warm skin and light, olive greens, gold highlights over teal shadows, soft bloom, warm leak, fine grain",
        "develop": {"wb.temp": 7200, "wb.tint": 5, "light.exposure": 0.12, "light.contrast": 18, "light.highlights": -40,
                    "light.shadows": 22, "light.whites": 6, "light.blacks": -10, "curve.shadows": 6, "color.vibrance": 18,
                    "mixer.orange.sat": 8, "mixer.orange.lum": 10, "mixer.green.hue": -30, "mixer.green.sat": -22,
                    "mixer.green.lum": -10, "mixer.yellow.hue": -10, "mixer.blue.sat": 12, "mixer.blue.lum": -10,
                    "grading.shadows.hue": 200, "grading.shadows.sat": 10, "grading.highlights.hue": 40,
                    "grading.highlights.sat": 20, "grading.balance": 15, "effects.clarity": 4, "vignette.amount": -18,
                    "vignette.feather": 75, "grain.amount": 3, "grain.size": 15, "detail.sharpenAmount": 15},
        "sky": {"exposure": -0.3, "saturation": 20, "temp": -10},
        "person": {"exposure": 0.3, "shadows": 25, "temp": 12}, "face": {"exposure": 0.22, "shadows": 20},
        "finish": {"glow": 18, "glow_radius": 30, "leak": 17, "leak_color": "#ffd08a", "sharpen": 35},
    },
}
LOOK_KEYS = {"about", "base", "develop", "sky", "person", "face", "finish"}
FINISH = {"glow": 0, "glow_radius": 30, "glow_blend": "softLight", "leak": 0, "leak_color": "#ffd08a", "leak_angle": -45,
          "sharpen": 30, "sharpen_radius": 0.8, "sharpen_threshold": 3}

TARGETS = {                                             # (width, height)
    "instagram-portrait": (1440, 1800), "instagram-square": (1440, 1440), "instagram-landscape": (1440, 754),
    "story": (1080, 1920), "youtube-thumb": (1920, 1080), "poster": (2000, 3000),
    "landscape": (1920, 1080), "vertical": (1080, 1920), "square": (1080, 1080),
}


# --------------------------------------------------------------------------------------------------------- looks

def _merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def resolve_look(name: str, extra: dict | None = None) -> dict:
    """A look by name: a built-in, or one of `extra` (a spec's `looks`), which may build on another with `base`."""
    table = {**LOOKS, **(extra or {})}
    if name not in table:
        raise SystemExit(f"no look {name!r} (looks: {', '.join(table)})")
    look, seen = table[name], [name]
    bad = set(look) - LOOK_KEYS
    if bad:
        raise SystemExit(f"look {name!r}: unknown key(s) {', '.join(sorted(bad))} (known: {', '.join(sorted(LOOK_KEYS))})")
    while "base" in look:
        b = look["base"]
        if b in seen or b not in table:
            raise SystemExit(f"look {name!r}: base {b!r} is {'circular' if b in seen else 'not a look'}")
        seen.append(b)
        look = _merge(table[b], {k: v for k, v in look.items() if k != "base"})
    bad = set(look.get("finish", {})) - set(FINISH)
    if bad:
        raise SystemExit(f"look {name!r}: unknown finish key(s) {', '.join(sorted(bad))} (known: {', '.join(FINISH)})")
    return {"develop": {}, "sky": {}, "person": {}, "face": {}, **look, "finish": {**FINISH, **look.get("finish", {})}}


# -------------------------------------------------------------------------------------------- targets and crops

def parse_target(t, film_size: tuple[int, int] | None = None) -> tuple[int, int]:
    """A target size: a TARGETS name, "film" (the film's frame), "WxH", "W:H@L" (aspect, long edge L) or [W, H]."""
    if isinstance(t, (list, tuple)) and len(t) == 2:
        return int(t[0]), int(t[1])
    s = str(t)
    if s in TARGETS:
        return TARGETS[s]
    if s == "film":
        if not film_size:
            raise SystemExit("target 'film' needs --film (its film.json format)")
        return film_size
    try:
        if "x" in s:
            w, h = (int(v) for v in s.lower().split("x"))
            return w, h
        if ":" in s:
            ar, _, long = s.partition("@")
            aw, ah = (float(v) for v in ar.split(":"))
            long = int(long or 1800)
            return (long, round(long * ah / aw)) if aw >= ah else (round(long * aw / ah), long)
    except ValueError:
        pass
    raise SystemExit(f"target {t!r}: a name ({', '.join(TARGETS)}, film), WxH or W:H@L")


def crop_rect(img: tuple[int, int], size: tuple[int, int], crop=None, focus=None, zoom: float = 1.0) -> tuple:
    """The pixel rect (x, y, w, h) to cut from an `img` (w, h) photo for a `size` (w, h) still, at exactly its aspect.
    `crop` [x0, y0, x1]: that width from (x0, y0), the height from the aspect; [x0, y0, x1, y1]: the largest rect of
    the aspect centred in that box. Else the largest rect of the aspect, / `zoom`, centred on `focus` (default the
    middle). The rect is kept inside the photo (moved, then shrunk if it must be)."""
    W, H = img
    ar = size[0] / size[1]
    if crop is not None:
        if len(crop) == 3:
            x0, y0, x1 = crop
            w = (x1 - x0) * W
            h = w / ar
            cx, cy = x0 * W + w / 2, y0 * H + h / 2
        elif len(crop) == 4:
            x0, y0, x1, y1 = crop
            bw, bh = (x1 - x0) * W, (y1 - y0) * H
            w, h = (bw, bw / ar) if bw / bh <= ar else (bh * ar, bh)
            cx, cy = (x0 + x1) / 2 * W, (y0 + y1) / 2 * H
        else:
            raise SystemExit(f"crop {crop}: [x0, y0, x1] or [x0, y0, x1, y1]")
    else:
        w, h = (W, W / ar) if W / H <= ar else (H * ar, H)
        w, h = w / max(zoom, 1.0), h / max(zoom, 1.0)
        fx, fy = focus or (0.5, 0.5)
        cx, cy = fx * W, fy * H
    if w > W or h > H:                                   # bigger than the photo: the largest that fits
        s = min(W / w, H / h)
        w, h = w * s, h * s
    w = int(round(w))
    h = min(int(round(w / ar)), H)
    x = int(round(min(max(cx - w / 2, 0), W - w)))
    y = int(round(min(max(cy - h / 2, 0), H - h)))
    return x, y, w, h


# --------------------------------------------------------------------------------------------------------- shots

SHOT_KEYS = {"src", "name", "crop", "focus", "zoom", "sky", "lum_hi", "spots", "develop", "soften", "looks", "target"}
SPOT_KEYS = {"kind", "at", "r", "values", "lum_hi", "feather"}


@dataclass
class Shot:
    src: Path
    name: str
    crop: list | None = None
    focus: list | None = None
    zoom: float = 1.0
    sky: bool = False                 # add the look's sky mask (only where there is sky: the mask is a heuristic)
    lum_hi: float | None = None       # spots stay below this luminance; default 0.55 with sky (no halo), else 0.85
    spots: list = field(default_factory=list)     # {"kind": person|face|custom, "at": [x, y], "r": r|[rx, ry], "values"?}
    develop: dict = field(default_factory=dict)   # this photo's develop values, every look (exposure, highlights...)
    soften: float = 1.0               # face spots smooth skin by FACE_SOFT x soften (0: not at all)
    looks: dict = field(default_factory=dict)     # per-look overrides: {"golden-hour": {"develop": {}, "finish": {}}}
    target: object = None             # this photo's own target, else the spec's / CLI's

    @classmethod
    def from_dict(cls, d: dict, base: Path) -> "Shot":
        bad = set(d) - SHOT_KEYS
        if bad:
            raise SystemExit(f"photo {d.get('name') or d.get('src')}: unknown key(s) {', '.join(sorted(bad))}")
        for s in d.get("spots", []):
            if set(s) - SPOT_KEYS or "at" not in s or "r" not in s:
                raise SystemExit(f"photo {d.get('src')}: a spot is {{kind, at: [x, y], r, values?, lum_hi?, feather?}}: {s}")
        src = (base / d["src"]).resolve()
        return cls(src=src, name=d.get("name") or src.stem, **{k: v for k, v in d.items() if k not in ("src", "name")})


def lc_steps(shot: Shot, look: dict, look_name: str) -> list:
    """The LightCraft steps for one photo in one look (the export is added by the caller)."""
    over = shot.looks.get(look_name, {})
    values = {**look["develop"], **shot.develop, **over.get("develop", {})}
    if shot.src.suffix.lower() in RAW_EXT:                 # Kelvin on raws: a relative look wb would be absolute
        values = {k: v for k, v in values.items() if not k.startswith("wb.") or k in shot.develop or k in over.get("develop", {})}
    steps = [LC.develop(values)]
    if shot.sky:
        steps += LC.sky({**look["sky"], **over.get("sky", {})})
    lum_hi = shot.lum_hi if shot.lum_hi is not None else (0.55 if shot.sky else 0.85)
    for i, s in enumerate(shot.spots):
        kind = s.get("kind", "person")
        if kind == "person":
            vals = {**look["person"], **over.get("person", {})}
        elif kind == "face":
            vals = {**look["face"], **{k: v * shot.soften for k, v in FACE_SOFT.items()}, **over.get("face", {})}
        elif kind == "custom":
            vals = {}
        else:
            raise SystemExit(f"{shot.name}: spot kind {kind!r} (person, face, custom)")
        vals = {**vals, **s.get("values", {})}
        steps += LC.spot(s["at"], s["r"], vals, s.get("lum_hi", lum_hi), s.get("feather", 75), name=f"{kind}{i + 1}")
    return steps


def pc_steps(shot: Shot, look: dict, look_name: str, img: tuple[int, int], size: tuple[int, int]) -> tuple[list, tuple]:
    """The PhotoCraft steps (crop + resize, finish, sharpen) and the crop rect."""
    fin = {**look["finish"], **shot.looks.get(look_name, {}).get("finish", {})}
    rect = crop_rect(img, size, shot.crop, shot.focus, shot.zoom)
    scale = max(size) / 1800                               # finish radii are tuned at a 1800 px long edge
    steps = PC.crop_resize(rect, size)
    steps += PC.glow(fin["glow_radius"] * scale, fin["glow"], fin["glow_blend"])
    steps += PC.light_leak(fin["leak_color"], fin["leak"], fin["leak_angle"])
    if len(steps) > 1:
        steps += PC.flatten()
    steps += PC.sharpen(fin["sharpen"], fin["sharpen_radius"] * max(scale, 0.5), fin["sharpen_threshold"])
    return steps, rect


# ---------------------------------------------------------------------------------------------- detail check

def detail(gray) -> float:
    """Fine detail relative to mid detail: the spectrum's energy at 0.3..0.5 cycles/px over 0.1..0.2. A blur lowers
    it; contrast and brightness changes do not (both bands scale together); sharpening and grain raise it."""
    import numpy as np
    g = np.asarray(gray, dtype=np.float32)
    F = np.abs(np.fft.fftshift(np.fft.fft2(g - g.mean())))
    h, w = g.shape
    yy, xx = np.ogrid[:h, :w]
    r = np.hypot((yy - h / 2) / h, (xx - w / 2) / w)
    return float(F[(r >= 0.3) & (r < 0.5)].mean() / max(F[(r >= 0.1) & (r < 0.2)].mean(), 1e-9))


def check(lc_cli: str, shot: Shot, rect: tuple, size: tuple, result: Path, work: Path) -> float:
    """The result's `detail` over that of the ungraded photo, cropped the same and Lanczos-resized: ~1 or more is as
    sharp as a plain resize, below DETAIL_MIN something softened it."""
    from PIL import Image                                   # Pillow comes with matplotlib
    ref_tif = work / f"{shot.name}.ref.tif"
    LC.run(lc_cli, shot.src, [LC.export_full(ref_tif, 8)], work, f"{shot.name}.ref.jsonl")
    x, y, w, h = rect
    with Image.open(ref_tif) as im:
        ref = im.convert("L").crop((x, y, x + w, y + h)).resize(size, Image.LANCZOS)
    with Image.open(result) as im:
        got = im.convert("L")
    ref_tif.unlink(missing_ok=True)
    return round(detail(got) / detail(ref), 3)


# ---------------------------------------------------------------------------------------------------- grading

def grade(shot: Shot, look_name: str, size: tuple, out_dir: Path, lc_cli: str, pc_cli: str, work: Path,
          extra_looks: dict | None = None, do_check: bool = False, keep_tiff: bool = False, log=print) -> dict:
    """One photo in one look: <out_dir>/<name>.jpg. Returns what was done (crop, sizes, detail ratio)."""
    if not shot.src.exists():
        raise SystemExit(f"{shot.name}: {shot.src} does not exist")
    look = resolve_look(look_name, extra_looks)
    tif = work / f"{shot.name}.{look_name}.tif"
    res = LC.run(lc_cli, shot.src, lc_steps(shot, look, look_name) + [LC.export_full(tif)], work, f"{shot.name}.{look_name}.jsonl")
    exp = res[-1]["result"]
    img = (int(exp["width"]), int(exp["height"]))
    steps, rect = pc_steps(shot, look, look_name, img, size)
    out = out_dir / f"{shot.name}.jpg"
    PC.run(pc_cli, tif, steps, out)
    rec = {"name": shot.name, "src": str(shot.src), "look": look_name, "out": str(out), "photo": list(img),
           "crop": list(rect), "size": list(size), "enlarged": rect[2] < size[0]}
    if rec["enlarged"]:
        log(f"warning: {shot.name}: the crop is {rect[2]}x{rect[3]} px, enlarged to {size[0]}x{size[1]} (softer)")
    if do_check:
        rec["detail"] = check(lc_cli, shot, rect, size, out, work)
        if rec["detail"] < DETAIL_MIN:
            log(f"warning: {shot.name} ({look_name}): detail {rec['detail']} of a plain resize (< {DETAIL_MIN}): softened")
    if keep_tiff:
        rec["tiff"] = str(tif)
    else:
        tif.unlink(missing_ok=True)
    log(f"{look_name}/{out.name}: {rect[2]}x{rect[3]} from {img[0]}x{img[1]} -> {size[0]}x{size[1]}"
        + (f", detail {rec['detail']}" if "detail" in rec else ""))
    return rec


def sheet(outs: dict, dest: Path, cell: int = 420) -> Path:
    """A contact sheet: one row per photo, one column per look ({look: [paths]}, rows matched by file name)."""
    from PIL import Image, ImageDraw, ImageFont
    looks = list(outs)
    names = sorted({p.name for ps in outs.values() for p in ps})
    font = ImageFont.load_default(size=max(12, cell // 20))
    pad = cell // 12
    th = round(cell * 1.25)
    s = Image.new("RGB", (len(looks) * (cell + 8), pad + len(names) * (th + 8)), "white")
    d = ImageDraw.Draw(s)
    for c, look in enumerate(looks):
        d.text((c * (cell + 8) + 4, 4), look, fill="black", font=font)
        for r, n in enumerate(names):
            p = next((q for q in outs[look] if q.name == n), None)
            if p is None or not p.exists():
                continue
            with Image.open(p) as im:
                t = im.convert("RGB")
                t.thumbnail((cell, th))
                s.paste(t, (c * (cell + 8), pad + r * (th + 8)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    s.save(dest, quality=90)
    return dest


def run_all(shots: list, looks: list, target, out: Path, lc_cli: str, pc_cli: str, extra_looks=None, film_size=None,
            do_check=False, do_sheet=False, keep_tiff=False, log=print) -> dict:
    """Every shot in every look; writes <out>/<look>/<name>.jpg + grade.json (+ <out>/sheet.jpg)."""
    for name in looks:
        resolve_look(name, extra_looks)                     # fail before any rendering
    done: dict = {}
    with tempfile.TemporaryDirectory(prefix="photo-") as tmp:
        work = Path(tmp)
        for name in looks:
            recs = [grade(s, name, parse_target(s.target or target, film_size), out / name, lc_cli, pc_cli, work,
                          extra_looks, do_check, keep_tiff, log) for s in shots]
            (out / name / "grade.json").write_text(json.dumps(recs, indent=1) + "\n")
            done[name] = recs
            if keep_tiff:
                for r in recs:
                    t = out / name / Path(r["tiff"]).name
                    shutil.move(r["tiff"], t)
                    r["tiff"] = str(t)
    if do_sheet:
        log(f"sheet: {sheet({n: [Path(r['out']) for r in rs] for n, rs in done.items()}, out / 'sheet.jpg')}")
    return done


# ------------------------------------------------------------------------------------------------------------ cli

def _floats(s: str, n: tuple, what: str) -> list:
    v = [float(x) for x in s.split(",")]
    if len(v) not in n:
        raise SystemExit(f"{what} {s!r}: {' or '.join(str(k) for k in n)} comma-separated numbers")
    return v


def _spot(s: str, kind: str) -> dict:
    v = _floats(s, (3, 4), f"--{kind}")
    return {"kind": kind, "at": v[:2], "r": v[2] if len(v) == 3 else v[2:]}


def _film(film: str | None):
    """(out root for stills, the film's frame size) of a film id or film folder, or (None, None)."""
    if not film:
        return None, None
    from .. import config, paths
    p = Path(film).resolve()
    if (p / "film.json").is_file():                         # a folder, as filmcraft.py's --film takes
        fp = paths.FilmPaths(p.name, p, p.parent.parent / "out" / p.name)
    else:
        fp = paths.film_paths(str(film))
    fmt = json.loads(fp.config.read_text()).get("format", "landscape") if fp.config.exists() else "landscape"
    return fp.out / "stills", config.size_of(fmt, fp.config)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    lk = sub.add_parser("looks", help="list the built-in looks")
    lk.add_argument("--json", action="store_true")
    for name in ("grade", "spec"):
        p = sub.add_parser(name, help="grade photos given on the command line" if name == "grade" else "grade a spec file's photos")
        if name == "grade":
            p.add_argument("photos", nargs="+", type=Path)
            p.add_argument("--crop", help="x0,y0,x1 or x0,y0,x1,y1 (0..1)")
            p.add_argument("--focus", help="x,y the crop centres on (0..1)")
            p.add_argument("--zoom", type=float, default=1.0, help="crop this much tighter than the largest (>= 1)")
            p.add_argument("--sky", action="store_true", help="the look's sky mask (photos with sky only)")
            p.add_argument("--spot", action="append", default=[], help="x,y,r: brighten a person there (repeatable)")
            p.add_argument("--face", action="append", default=[], help="x,y,r: brighten + soften a face there (repeatable)")
            p.add_argument("--soften", type=float, default=1.0, help="skin smoothing on --face spots, 0..1")
        else:
            p.add_argument("spec", type=Path)
            p.add_argument("--only", help="comma list of photo names")
        p.add_argument("--look", help="comma list of looks (default: the spec's, else fresh)")
        p.add_argument("--target", help=f"{', '.join(TARGETS)}, film, WxH or W:H@L (default instagram-portrait)")
        p.add_argument("--out", type=Path, help="output folder (default out/<film>/stills with --film)")
        p.add_argument("--film", help="film id: output under out/<id>/stills, and the 'film' target")
        p.add_argument("--check", action="store_true", help="measure each result's detail against a plain resize")
        p.add_argument("--sheet", action="store_true", help="also write <out>/sheet.jpg")
        p.add_argument("--keep-tiff", action="store_true", help="keep LightCraft's full-size graded TIFFs beside the JPEGs")
        p.add_argument("--lightcraft", help="lightcraft-cli path (else $LIGHTCRAFT_CLI, PATH, the artcraft install dir)")
        p.add_argument("--photocraft", help="photocraft-cli path (else $PHOTOCRAFT_CLI, PATH, the artcraft install dir)")
    a = ap.parse_args(argv)

    if a.cmd == "looks":
        if a.json:
            print(json.dumps(LOOKS, indent=1))
        else:
            for n, lo in LOOKS.items():
                print(f"{n:12s} {lo['about']}")
        return 0

    spec: dict = {}
    if a.cmd == "spec":
        spec = json.loads(a.spec.read_text())
        bad = set(spec) - {"film", "look", "target", "looks", "photos"}
        if bad:
            raise SystemExit(f"{a.spec}: unknown key(s) {', '.join(sorted(bad))} (film, look, target, looks, photos)")
        shots = [Shot.from_dict(d, a.spec.parent) for d in spec.get("photos", [])]
        if a.only:
            want = set(a.only.split(","))
            shots = [s for s in shots if s.name in want]
            if missing := want - {s.name for s in shots}:
                raise SystemExit(f"--only: no photo named {', '.join(sorted(missing))}")
    else:
        spots = [_spot(s, "person") for s in a.spot] + [_spot(s, "face") for s in a.face]
        shots = [Shot(src=p.resolve(), name=p.stem, crop=_floats(a.crop, (3, 4), "--crop") if a.crop else None,
                      focus=_floats(a.focus, (2,), "--focus") if a.focus else None, zoom=a.zoom, sky=a.sky,
                      spots=spots, soften=a.soften) for p in a.photos]
    if not shots:
        raise SystemExit("no photos to grade")
    if len({s.name for s in shots}) != len(shots):
        raise SystemExit("two photos have the same name; give them names (spec) or rename the files")
    looks = a.look.split(",") if a.look else (lambda v: [v] if isinstance(v, str) else v)(spec.get("look", ["fresh"]))
    stills, film_size = _film(a.film or spec.get("film"))
    out = a.out or stills
    if out is None:
        raise SystemExit("--out DIR or --film ID (out/<id>/stills)")
    lc_cli, pc_cli = LC.find_cli(a.lightcraft), PC.find_cli(a.photocraft)
    for app, cli in (("lightcraft", lc_cli), ("photocraft", pc_cli)):
        if not cli:
            print(f"{app}-cli not found: python -m filmtools.artcraft install {app}   (or --{app} / ${app.upper()}_CLI)",
                  file=sys.stderr)
            return 2
    run_all(shots, looks, a.target or spec.get("target", "instagram-portrait"), out, lc_cli, pc_cli,
            spec.get("looks"), film_size, a.check, a.sheet, a.keep_tiff)
    return 0


if __name__ == "__main__":
    sys.exit(main())
