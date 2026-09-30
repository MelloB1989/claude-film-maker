"""Scan a shot's existing plates, rendering nothing (render.py --scan): are they all there, all one size, all fit?

The plate directory is walked as render.py writes it: out/plates/<shot>/####.exr (the linear plate) and
app/public/plates/<shot>/proxy/####.png (the 8-bit proxy), #### = film frame - f0. The shot's window [f0, f1) says which
plates there must be: one per film frame, #### from 0 to f1 - f0 - 1. The scan fails (render.py exits 3) on
  MISSING      a plate of the window with no file at all;
  EXTRA        a plate file beyond the window (a set rendered for another window: its numbers mean other frames);
  BLANK        a plate that is blank, or has a black tile (lib/blank.py fault);
  BAD          a plate with a NaN or an infinite RGB value;
  UNREADABLE   a plate that cannot be read (a truncated or damaged file), never passed over;
  MIXED SIZES  EXR plates of more than one size (an interrupted final among preview plates, or look frames rendered
               over a final: the last render of a frame wins), or with `expect_res`, WRONG SIZE: any other than it.
A plate is judged on its EXR when it has one and on its proxy when it has only that (the proxy is 960x540 whatever the
render's size, so only EXRs have their size checked, and only EXRs are checked tile by tile). Frames a shot declares
black (SHOT["black_ok"]) are not judged blank, but they must not hold NaNs either.

Reading an EXR needs Blender (export.read_linear); the walk, the judging and the report are bpy-free, tested with the
reader faked.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import blank, export


@dataclass(frozen=True)
class Finding:
    film_frame: int
    index: int  # the plate's file number: film frame - f0
    path: Path
    detail: str  # what is wrong: a blank frame's brightest value, the black tile, the NaNs, or why it is unreadable


@dataclass
class ScanResult:
    shot: str
    window: tuple[int, int]  # the shot's film frames [f0, f1)
    indices: tuple[int, int]  # the first and last plate number found
    plates: int = 0
    from_exr: int = 0  # plates judged on their EXR
    from_proxy: int = 0  # plates judged on their proxy, for lack of an EXR
    exempt: list[int] = field(default_factory=list)  # film frames declared black: not judged blank
    blank: list[Finding] = field(default_factory=list)  # blank, or with a black tile
    bad: list[Finding] = field(default_factory=list)  # with values that are not finite
    unreadable: list[Finding] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)  # plate numbers of the window with no file
    extra: list[int] = field(default_factory=list)  # plate numbers beyond the window
    sizes: dict[tuple[int, int], list[int]] = field(default_factory=dict)  # EXR (width, height): its film frames
    expect_res: tuple[int, int] | None = None
    dimmest: tuple[float, int] | None = None  # (brightest value, film frame) of the dimmest lit EXR plate

    @property
    def expected(self) -> int:
        return self.window[1] - self.window[0]

    @property
    def wrong_sizes(self) -> dict[tuple[int, int], list[int]]:
        """The sizes that fail: every size but `expect_res`, or all of them when the EXRs are of more than one."""
        if self.expect_res is not None:
            return {s: f for s, f in self.sizes.items() if s != tuple(self.expect_res)}
        return dict(self.sizes) if len(self.sizes) > 1 else {}

    @property
    def clean(self) -> bool:
        return not (self.blank or self.bad or self.unreadable or self.missing or self.extra or self.wrong_sizes)


def _numbered(directory: Path, suffix: str) -> dict[int, Path]:
    """The files `####<suffix>` in a directory by their number (anything else in it is not a plate)."""
    found: dict[int, Path] = {}
    if directory.is_dir():
        for p in directory.iterdir():
            m = re.fullmatch(r"(\d+)" + re.escape(suffix), p.name)
            if m:
                found[int(m.group(1))] = p
    return found


def scan_plates(shot: str, f0: int, f1: int, exempt: Callable[[int], bool] = lambda f: False, *,
                expect_res: tuple[int, int] | None = None, tile: int | None = blank.TILE, root: Path = export.REPO,
                read_exr: Callable[[Path], object] | None = None,
                read_png: Callable[[Path], object] | None = None) -> ScanResult:
    """Judge every plate of `shot` under `root` against its window [f0, f1); `exempt(film frame)` says which frames are
    declared black, `expect_res` (w, h) the one size every EXR must be (default: any, so long as they agree), and
    `tile` the render tile in px for the black-tile check. `read_exr` and `read_png` return a plate's pixels (defaults:
    export.read_linear, which needs Blender, and export.read_png). Raises FileNotFoundError when the shot has no plates
    at all: a typo'd shot name must not scan clean."""
    paths = export.plate_paths(shot, 0, root)
    exrs, pngs = _numbered(paths.exr.parent, ".exr"), _numbered(paths.proxy.parent, ".png")
    numbers = sorted(set(exrs) | set(pngs))
    if not numbers:
        raise FileNotFoundError(f"no plates for {shot!r}: no ####.exr in {paths.exr.parent}, no ####.png in "
                                f"{paths.proxy.parent}")
    read_exr = read_exr or export.read_linear
    read_png = read_png or export.read_png
    n = f1 - f0
    res = ScanResult(shot, (f0, f1), (numbers[0], numbers[-1]), plates=len(numbers), expect_res=expect_res)
    res.missing = [i for i in range(n) if i not in exrs and i not in pngs]
    res.extra = [i for i in numbers if i >= n]
    for i in numbers:
        if i >= n:
            continue  # not this window's: listed as extra, not judged
        film = f0 + i
        black_ok = exempt(film)
        if black_ok:
            res.exempt.append(film)
        on_exr = i in exrs
        path = exrs[i] if on_exr else pngs[i]
        try:
            px = np.asarray((read_exr if on_exr else read_png)(path))
        except Exception as e:  # a truncated or damaged file is a finding, and the scan goes on
            res.unreadable.append(Finding(film, i, path, f"{type(e).__name__}: {e}"))
            continue
        if on_exr:
            res.from_exr += 1
            res.sizes.setdefault((px.shape[1], px.shape[0]), []).append(film)
        else:
            res.from_proxy += 1
        bad = blank.fault(px, tile=tile if on_exr else None, black_ok=black_ok)
        if bad is not None:
            (res.bad if bad.kind == "nonfinite" else res.blank).append(Finding(film, i, path, bad.detail))
        elif on_exr and not black_ok:
            top = blank.peak(px)
            if res.dimmest is None or top < res.dimmest[0]:
                res.dimmest = (top, film)
    return res


def _frames(films: list[int]) -> str:
    return ("film frame " if len(films) == 1 else "film frames ") + blank.frames_spec(films)


def report(res: ScanResult) -> list[str]:
    """The scan as lines to print: a summary, then one line per problem."""
    counts = [(len(res.blank), "BLANK"), (len(res.bad), "BAD"), (len(res.unreadable), "UNREADABLE"),
              (len(res.missing), "MISSING"), (len(res.extra), "EXTRA")]
    parts = [f"{k} {label}" for k, label in counts if k]
    if res.wrong_sizes:
        parts.append("WRONG SIZE" if res.expect_res is not None else "MIXED SIZES")
    verdict = "all lit" if res.clean else ", ".join(parts)
    first, last = res.indices
    f0, f1 = res.window
    plates = (f"{res.plates} plate" + ("" if res.plates == 1 else "s") if res.plates == res.expected
              else f"{res.plates} of {res.expected} plates")
    summary = (f"[{res.shot}] {plates} ({first:04d}-{last:04d}) for film frames [{f0}, {f1}): {verdict}. Judged on "
               f"{res.from_exr} EXR and {res.from_proxy} proxy only; {len(res.exempt)} declared black_ok.")
    if len(res.sizes) == 1:
        (w, h), = res.sizes
        summary += f" EXR size {w}x{h}."
    if res.dimmest is not None:
        summary += f" Dimmest EXR plate: film frame {res.dimmest[1]}, brightest RGB value {res.dimmest[0]:.3g}."
    lines = [summary]
    for label, findings in (("BLANK", res.blank), ("BAD", res.bad), ("UNREADABLE", res.unreadable)):
        for f in findings:  # a reader's own error already names the file
            where = "" if str(f.path) in f.detail else f": {f.path}"
            lines.append(f"[{res.shot}] {label} film frame {f.film_frame} (plate {f.index:04d}): {f.detail}{where}")
    if res.missing:
        films = [f0 + i for i in res.missing]
        lines.append(f"[{res.shot}] MISSING {_frames(films)}: no plate; render them with --frames "
                     f"{blank.frames_spec(films)}")
    for i in res.extra:
        lines.append(f"[{res.shot}] EXTRA plate {i:04d} (film frame {f0 + i}): beyond the shot's film frames "
                     f"[{f0}, {f1}); a plate set rendered for another window")
    if res.wrong_sizes:
        head = (f"WRONG SIZE, not {res.expect_res[0]}x{res.expect_res[1]}" if res.expect_res is not None
                else "MIXED SIZES, the EXR plates are not all one size")
        lines.append(f"[{res.shot}] {head}: " + "; ".join(f"{w}x{h}: {_frames(films)}"
                                                          for (w, h), films in sorted(res.wrong_sizes.items())))
    return lines
