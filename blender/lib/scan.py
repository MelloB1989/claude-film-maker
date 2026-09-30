"""Scan a shot's existing plates for blank frames, rendering nothing (render.py --scan).

The plate directory is walked as render.py writes it: out/plates/<shot>/####.exr (the linear plate) and
app/public/plates/<shot>/proxy/####.png (the 8-bit proxy), #### = film frame - f0. A plate is judged on its EXR when it
has one (blank: brightest RGB value <= 1e-4) and on its proxy when it has only that (<= 1/255): lib/blank.py. Frames a
shot declares black (SHOT["black_ok"]) are skipped, and a plate that cannot be read is reported, never passed over.

Reading an EXR needs Blender (export.read_linear); the walk, the judging and the report are bpy-free, tested with the
reader faked.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import blank, export


@dataclass(frozen=True)
class Finding:
    film_frame: int
    index: int  # the plate's file number: film frame - f0
    path: Path
    detail: str  # blank: how bright its brightest value is; unreadable: why


@dataclass
class ScanResult:
    shot: str
    indices: tuple[int, int]  # the first and last plate number found
    plates: int = 0
    from_exr: int = 0  # plates judged on their EXR
    from_proxy: int = 0  # plates judged on their proxy, for lack of an EXR
    exempt: list[int] = field(default_factory=list)  # film frames skipped: declared black
    blank: list[Finding] = field(default_factory=list)
    unreadable: list[Finding] = field(default_factory=list)
    dimmest: tuple[float, int] | None = None  # (brightest value, film frame) of the dimmest lit EXR plate

    @property
    def clean(self) -> bool:
        return not self.blank and not self.unreadable


def _numbered(directory: Path, suffix: str) -> dict[int, Path]:
    """The files `####<suffix>` in a directory by their number (anything else in it is not a plate)."""
    found: dict[int, Path] = {}
    if directory.is_dir():
        for p in directory.iterdir():
            m = re.fullmatch(r"(\d+)" + re.escape(suffix), p.name)
            if m:
                found[int(m.group(1))] = p
    return found


def scan_plates(shot: str, f0: int, exempt: Callable[[int], bool] = lambda f: False, *, root: Path = export.REPO,
                read_exr: Callable[[Path], object] | None = None, read_png: Callable[[Path], object] | None = None,
                log: Callable[[str], None] | None = None) -> ScanResult:
    """Judge every plate of `shot` under `root`; f0 is the shot's first film frame and `exempt(film frame)` says which
    frames are declared black. `read_exr` and `read_png` return a plate's pixels (defaults: export.read_linear, which
    needs Blender, and export.read_png); `log` takes the NaN notes (default: print). Raises FileNotFoundError when the
    shot has no plates at all: a typo'd shot name must not scan clean."""
    paths = export.plate_paths(shot, 0, root)
    exrs, pngs = _numbered(paths.exr.parent, ".exr"), _numbered(paths.proxy.parent, ".png")
    numbers = sorted(set(exrs) | set(pngs))
    if not numbers:
        raise FileNotFoundError(f"no plates for {shot!r}: no ####.exr in {paths.exr.parent}, no ####.png in "
                                f"{paths.proxy.parent}")
    read_exr = read_exr or export.read_linear
    read_png = read_png or export.read_png
    say = log or (lambda message: print(message, flush=True))
    res = ScanResult(shot, (numbers[0], numbers[-1]), plates=len(numbers))
    for i in numbers:
        film = f0 + i
        if exempt(film):
            res.exempt.append(film)
            continue
        on_exr = i in exrs
        path = exrs[i] if on_exr else pngs[i]
        try:
            px = (read_exr if on_exr else read_png)(path)
        except Exception as e:  # a truncated or damaged file is a finding, and the scan goes on
            res.unreadable.append(Finding(film, i, path, f"{type(e).__name__}: {e}"))
            continue
        if on_exr:
            res.from_exr += 1
        else:
            res.from_proxy += 1
        if blank.is_blank(px, log=lambda message: say(f"[{shot}] film frame {film}: {message}")):
            res.blank.append(Finding(film, i, path, f"brightest RGB value {blank.peak(px):g}"))
        elif on_exr:
            top = blank.peak(px)
            if top == top and (res.dimmest is None or top < res.dimmest[0]):  # not NaN
                res.dimmest = (top, film)
    return res


def report(res: ScanResult) -> list[str]:
    """The scan as lines to print: a summary, then one line per blank or unreadable plate."""
    verdict = "all lit" if res.clean else ", ".join(
        part for part in (f"{len(res.blank)} BLANK" if res.blank else "",
                          f"{len(res.unreadable)} UNREADABLE" if res.unreadable else "") if part)
    first, last = res.indices
    plates = f"{res.plates} plate" + ("" if res.plates == 1 else "s")
    summary = (f"[{res.shot}] {plates} ({first:04d}-{last:04d}): {verdict}. Judged on {res.from_exr} EXR "
               f"and {res.from_proxy} proxy only; {len(res.exempt)} declared black_ok, skipped.")
    if res.dimmest is not None:
        summary += f" Dimmest EXR plate: film frame {res.dimmest[1]}, brightest RGB value {res.dimmest[0]:.3g}."
    lines = [summary]
    for label, findings in (("BLANK", res.blank), ("UNREADABLE", res.unreadable)):
        for f in findings:  # a reader's own error already names the file
            where = "" if str(f.path) in f.detail else f": {f.path}"
            lines.append(f"[{res.shot}] {label} film frame {f.film_frame} (plate {f.index:04d}): {f.detail}{where}")
    return lines
