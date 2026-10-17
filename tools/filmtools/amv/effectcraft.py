"""EffectCraft export: the AMV plan as an editable EffectCraft project (getartcraft.com, the open-source After Effects).

The film is rendered in Blender, but the user edits in After Effects on Windows and on Linux wants the After Effects-like
open-source app. This stage hands them the same edit as a project they can open, scrub and re-time: `<id>.ecproj`
(EffectCraft's versioned JSON project, schema 2), generated from the plan the way `build.jsx` generated the AE project:

    plan ──► build_spec() ──► spec.json ──► effectcraft_build.jsx ──► `effectcraft-cli script` ──► <id>.ecproj

Why a script and not hand-written JSON: EffectCraft 0.10's headless CLI embeds the After Effects object model
(`app.project`, `comp.layers.add`, `property.setValuesAtTimes` ...), so the project is built by the app's own loader
and is valid by construction, instead of us guessing at a 700 KB-per-demo JSON schema that changes between releases.
The split keeps the editorial logic testable without the binary: *this module* turns the plan into a plain-data spec
(every number already resolved through `plan.py`'s accessors: per-frame keys, hole ellipses, grade values, layer order),
and `effectcraft_build.jsx` (next to it) is a dumb interpreter of that spec, a port of `build.jsx`.

Differences from the AE build, all because the open-source app has no equivalent plug-in:
- Magic Bullet Looks / Sapphire Sharpen / Deep Glow are replaced by native effects (CC Vignette-free: Lumetri vignette,
  Unsharp Mask, Color Balance, Glow), values from handover `13_color_grading.md`.
- Titles and the 3D outro are the Blender-rendered PNG sequences when present (`out/<id>/amv/titles`, `.../outro`),
  else editable text placeholders in the same place and timing.
- EffectCraft's property match names are NOT After Effects' (Exposure2-0003 is the Red channel there), so the script
  addresses effect parameters by display name, which both apps share.

Shots come in two flavours (`--source`): `clips` (the default, the editable one: the 60p clip in a per-shot precomp with
time remap + frame blending, the exposure / saturation trim, the matte cutout, the eye-dive hole mask and the tile /
radial blur / directional blur / lens effects as live effects) and `baked` (the Blender pipeline's layer PNG sequences,
exactly what the Blender scene textures, with only the transform keys on top; shots without baked frames fall back to clips); `auto` picks clips where the clip file
exists and the baked sequence otherwise.

CLI: python -m filmtools.amv.effectcraft --film films/timeless [--layers out/timeless/amv/layers]
         [--out out/timeless/amv/timeless.effectcraft-project] [--source clips|baked|auto] [--cli PATH] [--emit-only]
`--out` is a directory (the name asked for in the brief ends in `-project`): it holds `<id>.ecproj`, the generated
`build.jsx`, `spec.json` and, with `--preview 30,245,490`, low-res frames rendered by the CLI.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import plan as P
from ..artcraft.effectcraft import find_cli, preview_frames, run_script   # shared with the other exporters

JSX = Path(__file__).with_name("effectcraft_build.jsx")
KEY_TOL = 1e-3          # px / % / deg: runs of per-frame keys straighter than this are stored as one linear span

# Grade (handover 13_color_grading.md §2-3), native stand-ins on one adjustment layer, in stack order.
GRADE_LOOKS_CB = [-3, -2, 4, -1, 0, 1, 0, 0, 0]          # Magic Bullet's faint cool shadows / mids (§2.2 stand-in)
# EffectCraft's Lumetri / Glow are not Adobe's: with the handover values (sat 150, glow 84/0.25) the grade rendered
# ~35 % darker and more saturated than AE's full-quality render, so exposure, saturation and glow are fitted on 8 frames
# of that render (mean luma 116 vs AE 119, p95 231 vs 228, HSV saturation 59 vs 56 %). The rest are the preset's values.
GRADE_LUMETRI = {"exposure": 0.5, "contrast": 25, "highlights": 10, "shadows": 45, "whites": 20, "blacks": -12, "saturation": 115}
GRADE_VIGNETTE = {"amount": -0.35, "midpoint": 50}       # Lumetri vignette stand-in for the Looks lens vignette
GRADE_SHARPEN = {"amount": 50, "radius": 1.5}            # Unsharp Mask stand-in for Sapphire S_Sharpen
GRADE_BC = {"brightness": 15, "contrast": 20}
GRADE_GLOW = {"threshold": 70, "radius": 90, "intensity": 0.6}


# ---------------------------------------------------------------------------------------------------------------- keys

def compress(keys, tol=KEY_TOL):
    """`[[frame, v, ...], ...]` (linear keys) with every straight run replaced by its two ends: the compressed keys
    interpolate to the originals within `tol`. Per-frame curves keep every frame where they bend."""
    if len(keys) <= 2:
        return [list(k) for k in keys]
    out = [list(keys[0])]
    i = 0
    n = len(keys)
    while i < n - 1:
        j = i + 1
        # extend the span i..j while every point between lies on the chord
        while j + 1 < n and _on_chord(keys, i, j + 1, tol):
            j += 1
        out.append(list(keys[j]))
        i = j
    return out


def _on_chord(keys, i, j, tol):
    f0, f1 = keys[i][0], keys[j][0]
    for m in range(i + 1, j):
        u = (keys[m][0] - f0) / (f1 - f0)
        for c in range(1, len(keys[i])):
            if abs(keys[m][c] - (keys[i][c] + (keys[j][c] - keys[i][c]) * u)) > tol:
                return False
    return True


def array_keys(arr, f0, tol=KEY_TOL):
    """A per-frame array starting at comp frame `f0` as compressed keys `[[frame, value], ...]`; list values
    (positions) become `[frame, x, y]` rows internally and are folded back to `[frame, [x, y]]`."""
    if not arr:
        return []
    rows = [[f0 + i] + (list(v) if isinstance(v, (list, tuple)) else [v]) for i, v in enumerate(arr)]
    rows = compress(rows, tol)
    if isinstance(arr[0], (list, tuple)):
        return [[r[0], r[1:]] for r in rows]
    return [[r[0], r[1]] for r in rows]


def lin_keys(keys):
    """Plan `[[frame, value], ...]` key lists (AE linear keys) as plain lists, sorted."""
    return [[k[0], k[1]] for k in sorted(keys or [], key=lambda k: k[0])]


def multi_keys(keys, i):
    """Column `i` (1-based) of `[[frame, v1, v2, ...], ...]` as `[[frame, value], ...]`."""
    return [[k[0], k[i]] for k in sorted(keys or [], key=lambda k: k[0])]


def shape_keys(frames, rows):
    """Compress ellipse rows `[cx, cy, rx, ry, feather]` per frame (same straight-run rule as other keys)."""
    ks = compress([[f] + list(r) for f, r in zip(frames, rows)])
    return ks


# ---------------------------------------------------------------------------------------------------------------- spec

@dataclass
class Options:
    film_dir: Path
    layers_dir: Path | None = None
    titles_dir: Path | None = None
    outro_dir: Path | None = None
    source: str = "clips"          # clips | baked | auto


def _seq_first(dirpath: Path, pattern="*.png"):
    """The first file of an image sequence folder, or None (also None for an empty / missing folder)."""
    if dirpath is None or not dirpath.is_dir():
        return None
    files = sorted(dirpath.glob(pattern))
    return files[0] if files else None


def _seq_count(dirpath: Path):
    return len(list(dirpath.glob("*.png"))) if dirpath is not None and dirpath.is_dir() else 0


def shot_mode(plan: P.Plan, shot: P.Shot, opts: Options):
    """`clips` or `baked` for one shot: honours `--source`; `auto` falls back to the baked sequence when the clip
    is missing (a machine without the 4K sources can still open the edit)."""
    has_clip = plan.clip(shot).exists()
    baked = _seq_first(opts.layers_dir / shot.name) if opts.layers_dir else None
    if opts.source == "baked" and baked is not None:
        return "baked"
    if opts.source == "baked" and not has_clip:
        raise SystemExit(f"--source baked: no layer frames in {opts.layers_dir}/{shot.name} and no clip to fall back on")
    if opts.source == "clips" or has_clip:
        return "clips"
    if baked is None:
        raise SystemExit(f"shot {shot.name}: clip {plan.clip(shot)} missing and no baked layer frames")
    return "baked"


def shot_spec(plan: P.Plan, shot: P.Shot, opts: Options):
    f0 = shot.a
    n = shot.end - shot.a
    mode = shot_mode(plan, shot, opts)
    raw = shot.raw
    s = {"index": shot.index, "name": shot.name, "a": shot.a, "b": shot.b, "end": shot.end, "n": n, "mode": mode,
         "slow": shot.slow, "under": shot.under, "flipx": bool(raw.get("flipx")),
         "transform": {
             "pos": array_keys([[x, y] for x, y in zip(raw["px"], raw["py"])], f0),
             "scale": array_keys(raw["s"], f0),
             "rot": array_keys(raw["rz"], f0)},
         "opacity": lin_keys(raw.get("opacity"))}
    if mode == "baked":
        w, h, ox, oy = shot.canvas
        first = _seq_first(opts.layers_dir / shot.name)
        s["baked"] = {"first": str(first.resolve()), "w": w, "h": h, "frames": _seq_count(first.parent)}
        return s       # everything below is already inside the baked frames (bake.py: balance .. optics)
    s["clip"] = str(plan.clip(shot).resolve())
    s["src"] = shot.src
    s["remap"] = array_keys(raw["remap"], 0)       # shot-relative frame -> clip seconds
    s["ev"] = lin_keys(raw["expo_keys"]) if raw.get("expo_keys") else float(raw.get("ev") or 0.0)
    s["sat"] = shot.sat
    s["tile"] = list(shot.tile)
    if shot.hole(shot.a) is not None:
        f_from = max(shot.a, raw["hole_f0"] - 1)
        frames = list(range(f_from, shot.end))
        rows = [shot.hole(f)[:5] for f in frames]
        s["hole"] = {"shape": shape_keys(frames, rows),
                     "offset": [[raw["hole_f0"], 0], [shot.b - 3, 4], [shot.b - 1, 40]]}
    if raw.get("rfb"):
        s["rfb"] = {"amount": multi_keys(raw["rfb"], 1),
                    "center": [[k[0], [k[2], k[3]]] for k in sorted(raw["rfb"], key=lambda k: k[0])]}
    if raw.get("dblur"):
        s["dblur"] = {"dir": float(raw.get("dblur_dir", 90)), "length": lin_keys(raw["dblur"])}
    if raw.get("bulge"):
        s["bulge"] = lin_keys(raw["bulge"])
    if raw.get("defocus"):
        s["defocus"] = lin_keys(raw["defocus"])
    if shot.matte and shot.titles:
        first = plan.path(shot.matte)
        s["matte"] = {"first": str(first.resolve()), "f0": raw.get("matte_f0", 0), "rim": shot.rim}
    s["titles"] = [title_spec(plan, opts, f"{shot.name}.{i}", t, shot.a, shot.end) for i, t in enumerate(shot.titles)]
    return s


def title_spec(plan, opts, title_id, t, comp_f0, limit_end):
    """One title: its Blender PNG sequence when rendered (`titles/<id>/<k>.png`), else a text placeholder spec.
    `limit_end` clips shot titles to the shot (comp frames)."""
    spec = t["spec"]
    out = {"id": title_id, "style": t["style"], "f_in": t["f_in"], "dur": spec["dur"], "text": spec["text"],
           "sub": spec.get("sub"), "size": spec.get("size", 90), "pos": spec.get("pos") or t.get("pos"),
           "scale": t.get("scale"), "palette": spec.get("palette") or spec.get("variant"),
           "out": min(t["f_in"] + spec["dur"], limit_end), "seq": None}
    first = _seq_first(opts.titles_dir / title_id) if opts.titles_dir else None
    if first is not None:
        out["seq"] = str(first.resolve())
    return out


def portal_spec(plan, p):
    f0 = p["f0"]
    s = {"name": p["name"], "A": p["A"], "B": p["B"], "f0": f0, "f1": p["f1"],
         "pos": array_keys([[x, y] for x, y in zip(p["px"], p["py"])], f0),
         "scale": array_keys(p["s"], f0), "rot": array_keys(p["rz"], f0), "opacity": array_keys(p["op"], f0),
         "hole": shape_keys(list(range(f0, f0 + len(p["mx"]))),
                            [[p["mx"][i], p["my"][i], p["mrx"][i], p["mry"][i], p["mfe"][i], p["mrot"][i]]
                             for i in range(len(p["mx"]))]),
         "rfb_amount": [[f0, 60], [f0 + 2, 25], [f0 + 4, 0]]}
    g = p.get("glint")
    if g:
        s["glint"] = {"f0": g["f0"], "r": g["r"], "pos": array_keys([[x, y] for x, y in zip(g["x"], g["y"])], g["f0"]),
                      "n": len(g["x"])}
    return s


def watermark_opacity(plan):
    """build.jsx: 62 %, fading to 0 under the lower-third titles (`wm_hide` = [[from, to], ...])."""
    keys = [[0, 62]]
    for a, b in plan.raw.get("wm_hide") or []:
        keys += [[a - 3, 62], [a, 0], [b, 0], [b + 3, 62]]
    keys.sort(key=lambda k: k[0])
    out = []
    for k in keys:
        if not out or out[-1][0] != k[0]:
            out.append(k)
    return out


def build_spec(plan: P.Plan, opts: Options):
    """The whole project as plain data: comp settings, footage, and `layers` bottom to top (the order the script adds
    them: later = above), mirroring the order build.jsx ends with."""
    raw = plan.raw
    shots = [shot_spec(plan, s, opts) for s in plan.shots]
    layers = []
    shot_pos = {}
    for sh in plan.stack():
        shot_pos[sh.index] = len(layers)
        layers.append({"type": "shot", "shot": sh.index})
        for p in (raw.get("portals") or []):
            if p["B"] == sh.index:
                if p["A"] not in shot_pos:
                    raise SystemExit(f"portal {p['name']}: shot A ({p['A']}) must be stacked below its portal")
                layers.append({"type": "portal", "portal": portal_spec(plan, p)})
    for f in raw.get("black") or []:
        layers.append({"type": "black", "f": f})
    for f in raw.get("invert") or []:
        layers.append({"type": "invert", "f": f, "black": "#010105", "white": "#C7DAE8"})
    for f in raw.get("halftone") or []:
        layers.append({"type": "halftone", "f": f, "n": 2, "grid": 13})
    layers.append({"type": "flash", "ev": lin_keys(raw.get("flash_ev"))})
    gr = raw.get("grade") or {}
    cb = gr.get("cb", [-10, 7, 10, -2, 4, -3, 12, 5, -12])
    lum = dict(GRADE_LUMETRI, blacks=gr.get("blacks", GRADE_LUMETRI["blacks"]))
    layers.append({"type": "grade", "out": raw["outro"]["f"], "sharpen": GRADE_SHARPEN, "looks_cb": GRADE_LOOKS_CB,
                   "lumetri": lum, "vignette": GRADE_VIGNETTE, "bc": GRADE_BC, "teal_orange": cb,
                   "glow": GRADE_GLOW})
    bars = raw.get("bars") or []
    layers.append({"type": "bars", "out": raw["outro"]["f"], "top": array_keys(bars, 0), "n": len(bars)})
    for a in raw.get("accents") or []:
        layers.append({"type": "accent", "f": a["f"], "n": a["n"], "y": a["y"]})
    for p in (raw.get("portals") or []):
        if p.get("glint"):
            layers.append({"type": "glint", "portal": p["name"]})
    for i, t in enumerate(raw.get("titles") or []):
        layers.append({"type": "title", "title": title_spec(plan, opts, f"screen.{i}", t, 0, plan.dur)})
    layers.append({"type": "outro", "f": raw["outro"]["f"], "n": raw["outro"]["n"], "dur": plan.dur,
                   "seq": (lambda p: str(p.resolve()) if p else None)(_seq_first(opts.outro_dir))})
    wm = (plan.root / "film.json")
    wm_text = (json.loads(wm.read_text()).get("amv") or {}).get("watermark", "SAU_EDITZ") if wm.exists() else "SAU_EDITZ"
    wm_seq = _seq_first(opts.titles_dir / "watermark") if opts.titles_dir else None
    layers.append({"type": "watermark", "text": wm_text, "out": raw["outro"]["f"], "opacity": watermark_opacity(plan),
                   "seq": str(wm_seq.resolve()) if wm_seq else None})
    audio = plan.path(raw["audio"])
    footage = {}
    for sh in shots:
        if sh["mode"] == "clips":
            footage[sh["src"]] = sh["clip"]
    return {"version": 1, "film": plan.root.name, "fps": plan.fps, "dur": plan.dur, "w": P.W, "h": P.H,
            "comp_name": f"MAIN {plan.root.name} {(json.loads(wm.read_text()).get('amv') or {}).get('watermark', '') if wm.exists() else ''}".strip(),
            "shutter": {"angle": P.SHUTTER_ANGLE, "phase": P.SHUTTER_PHASE, "samples": 64, "limit": 256},
            "footage": footage, "shots": shots, "layers": layers,
            "audio": str(audio.resolve()) if audio.exists() else None}


# ---------------------------------------------------------------------------------------------------------------- run

def render_jsx(spec, out_path: Path, project_path: Path):
    """The script the CLI runs: the spec as a literal, the output path, then the interpreter."""
    head = (f"var SPEC = {json.dumps(spec, separators=(',', ':'))};\n"
            f"var OUT_PROJECT = {json.dumps(str(project_path))};\n")
    out_path.write_text(head + JSX.read_text())


def default_paths(film_dir: Path):
    film_id = film_dir.resolve().name
    # out/ sits next to films/ (the repo root's out/<id>/amv)
    root = film_dir.resolve().parent.parent
    base = root / "out" / film_id / "amv"
    return film_id, base


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--film", required=True, type=Path, help="film folder (films/<id>)")
    ap.add_argument("--layers", type=Path, help="baked layer frames (default out/<id>/amv/layers)")
    ap.add_argument("--titles", type=Path, help="title PNG sequences (default out/<id>/amv/titles)")
    ap.add_argument("--outro", type=Path, help="outro PNG sequence (default out/<id>/amv/outro)")
    ap.add_argument("--out", type=Path, help="project folder (default out/<id>/amv/<id>.effectcraft-project)")
    ap.add_argument("--source", choices=["clips", "baked", "auto"], default="clips")
    ap.add_argument("--cli", help="path to effectcraft-cli (else $EFFECTCRAFT_CLI, PATH, the artcraft install dir)")
    ap.add_argument("--emit-only", action="store_true", help="write spec.json + build.jsx, do not run the CLI")
    ap.add_argument("--preview", help="comma list of comp frames to render low-res after building, e.g. 30,245,490")
    ap.add_argument("--preview-side", type=int, default=640, help="longest side in px of the preview frames")
    ap.add_argument("--scale", type=float, help="preview scale 0..1 of 1920 (overrides --preview-side)")
    a = ap.parse_args(argv)

    plan = P.load(a.film)
    film_id, base = default_paths(a.film)
    opts = Options(film_dir=a.film, layers_dir=a.layers or base / "layers", titles_dir=a.titles or base / "titles",
                   outro_dir=a.outro or base / "outro", source=a.source)
    out = a.out or base / f"{film_id}.effectcraft-project"
    out.mkdir(parents=True, exist_ok=True)
    spec = build_spec(plan, opts)
    (out / "spec.json").write_text(json.dumps(spec, indent=1))
    project = out / f"{film_id}.ecproj"
    render_jsx(spec, out / "build.jsx", project)
    print(f"spec: {len(spec['layers'])} main-comp layers, {len(spec['shots'])} shots -> {out / 'build.jsx'}")
    if a.emit_only:
        return 0
    cli = find_cli(a.cli)
    if not cli:
        print("effectcraft-cli not found (--cli / $EFFECTCRAFT_CLI); run `effectcraft-cli script build.jsx` yourself",
              file=sys.stderr)
        return 2
    code, so, se = run_script(cli, out / "build.jsx")
    sys.stdout.write(so)
    if code != 0 or not project.exists():
        sys.stderr.write(se)
        return code or 1
    print(f"project: {project} ({project.stat().st_size // 1024} KB)")
    if a.preview:
        frames = [int(x) for x in a.preview.split(",")]
        for p in preview_frames(cli, project, frames, out / "preview", int(1920 * a.scale) if a.scale else a.preview_side):
            print("preview:", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
