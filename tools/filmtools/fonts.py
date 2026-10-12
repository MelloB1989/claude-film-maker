"""Static font instances for the engine. opentype.js can't read variation data, so every width and weight a film
uses is cut from a variable source as its own file. Kerning lives in GPOS and survives instancing.

film.json pipeline.fonts lists the instances: [{"src": "fonts/src/Inter[opsz,wght].ttf", "axes": {"wght": 600},
"out": "Inter-600.ttf"}]. `src` is relative to the film folder, else to the repo root; `out` lands in films/<id>/fonts/
(the film's own fonts). OS/2 usWeightClass follows the wght axis (or `weight_class`), usWidthClass the wdth axis (or
`width_class`). The OFL licence files beside each source are copied along.

    film-fonts                                        every instance the film lists
    film-fonts --src X.ttf --axis wght=600 --out Y.ttf   one instance, no film needed
"""
import argparse
import shutil
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from . import cli, config, paths

# OS/2 usWidthClass by wdth axis percentage (the OpenType spec's table)
WIDTH_CLASSES = {50: 1, 62.5: 2, 75: 3, 87.5: 4, 100: 5, 112.5: 6, 125: 7, 150: 8, 200: 9}


def width_class(wdth: float) -> int:
    """The usWidthClass nearest a wdth axis value."""
    return WIDTH_CLASSES[min(WIDTH_CLASSES, key=lambda w: abs(w - wdth))]


def make_instance(src: Path, axes: dict[str, float], out: Path, weight_class: int, width_class: int = 5) -> Path:
    inst = instantiateVariableFont(TTFont(src), axes)
    inst["OS/2"].usWeightClass = weight_class
    inst["OS/2"].usWidthClass = width_class
    out.parent.mkdir(parents=True, exist_ok=True)
    inst.save(out)
    return out


def resolve_src(src: str, film_dir: Path | None, root: Path = paths.ROOT) -> Path:
    for base in ([film_dir] if film_dir else []) + [root]:
        if (base / src).is_file():
            return base / src
    raise SystemExit(f"font source {src} not found in {film_dir or ''} or {root}")


def build_all(specs: list[dict], out_dir: Path, film_dir: Path | None = None) -> list[Path]:
    """Every instance in `specs` (pipeline.fonts) into out_dir, with the sources' OFL licence files."""
    made, sources = [], set()
    for s in specs:
        src = resolve_src(s["src"], film_dir)
        axes = {k: float(v) for k, v in s.get("axes", {}).items()}
        wt = int(s.get("weight_class", round(axes.get("wght", 400))))
        wc = int(s.get("width_class", width_class(axes["wdth"]) if "wdth" in axes else 5))
        made.append(make_instance(src, axes, out_dir / s["out"], wt, wc))
        sources.add(src.parent)
    for d in sources:
        for lic in d.glob("OFL*.txt"):
            shutil.copy(lic, out_dir / lic.name)
    return made


def _axis(s: str) -> tuple[str, float]:
    tag, _, v = s.partition("=")
    if not tag or not v:
        raise argparse.ArgumentTypeError(f"--axis takes tag=value, not {s!r}")
    return tag, float(v)


def main(argv=None):
    ap = cli.parser("Cut static font instances from variable fonts (film.json pipeline.fonts, or one with --src)")
    ap.add_argument("--src", type=Path, help="one variable font to instance (with --out and --axis)")
    ap.add_argument("--axis", type=_axis, action="append", default=[], help="tag=value, e.g. wght=600 (repeatable)")
    ap.add_argument("--out", type=Path, help="the instance's file (with --src), or the folder for the film's list")
    film, rest = cli.take_film(list(sys.argv[1:] if argv is None else argv))
    a = ap.parse_args(rest)
    if a.src:
        if not a.out:
            ap.error("--src needs --out")
        axes = dict(a.axis)
        wc = width_class(axes["wdth"]) if "wdth" in axes else 5
        print(make_instance(a.src, axes, a.out, int(round(axes.get("wght", 400))), wc))
        return
    cli.film_argv(["--film", film] if film else [])
    f = config.load()
    if not f.fonts:
        raise SystemExit(f"no fonts to cut: list them in pipeline.fonts in {f.paths.config}")
    out = a.out or f.paths.dir / "fonts"
    made = build_all(f.fonts, out, f.paths.dir)
    print(f"{len(made)} fonts → {out}")
