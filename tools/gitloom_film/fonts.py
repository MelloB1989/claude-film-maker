"""Static font instances for the engine. opentype.js can't read variation data, so every width and weight the film
uses is cut from the pinned variable sources as its own file. Kerning lives in GPOS and survives instancing."""
import argparse
import shutil
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from .paths import APP, FONTS

SRC = FONTS / "src"
BRICOLAGE = [(w, wt) for w in (75, 87.5, 100) for wt in (300, 500, 600, 800)]
WIDTH_CLASS = {75: 3, 87.5: 4, 100: 5}
MONO, GEIST = (400, 500, 700), (400, 500, 600)


def bricolage_name(wdth: float, wght: int) -> str:
    return f"Bricolage-w{int(round(wdth * 10))}-{wght}.ttf"


def make_instance(src: Path, axes: dict[str, float], out: Path, weight_class: int, width_class: int = 5) -> Path:
    inst = instantiateVariableFont(TTFont(src), axes)
    inst["OS/2"].usWeightClass = weight_class
    inst["OS/2"].usWidthClass = width_class
    out.parent.mkdir(parents=True, exist_ok=True)
    inst.save(out)
    return out


def build_all(src_dir: Path, out_dir: Path) -> list[Path]:
    made = []
    b = src_dir / "BricolageGrotesque[opsz,wdth,wght].ttf"
    for w, wt in BRICOLAGE:
        made.append(make_instance(b, {"opsz": 96, "wdth": w, "wght": wt}, out_dir / bricolage_name(w, wt), wt,
                                  WIDTH_CLASS[w]))
    for wt in MONO:
        made.append(make_instance(src_dir / "JetBrainsMono[wght].ttf", {"wght": wt},
                                  out_dir / f"JetBrainsMono-{wt}.ttf", wt))
    made.append(make_instance(src_dir / "JetBrainsMono-Italic[wght].ttf", {"wght": 400},
                              out_dir / "JetBrainsMonoItalic-400.ttf", 400))
    for wt in GEIST:
        made.append(make_instance(src_dir / "Geist[wght].ttf", {"wght": wt}, out_dir / f"Geist-{wt}.ttf", wt))
    for lic in src_dir.glob("OFL-*.txt"):
        shutil.copy(lic, out_dir / lic.name)
    return made


def main(argv=None):
    argparse.ArgumentParser(description="Cut static font instances into app/public/fonts").parse_args(argv)
    made = build_all(SRC, APP / "public" / "fonts")
    print(f"{len(made)} fonts → app/public/fonts")
