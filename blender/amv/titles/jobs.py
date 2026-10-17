"""Plan -> title jobs: which titles the edit has, their ids, frame ranges and output folders (bpy-free).

The titles stage renders every title of the plan as an RGBA PNG sequence, `out/<film>/amv/titles/<title_id>/<k:04d>.png`
with k = 0 .. dur-1 counted from the title's `f_in` (docs/PIPELINE-AMV.md). This module is the contract the renderer
(`render.py`), the bake (which composites frame k = f - f_in) and the tests agree on, so it imports neither bpy nor numpy.

`<title_id>`: a shot title is `<shot name>.<i>` (i-th entry of the shot's `titles`), a screen title `screen.<i>`
(i-th entry of the plan's `titles`), the watermark `watermark`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

WATERMARK_ID = "watermark"


@dataclass(frozen=True)
class TitleJob:
    """One title to render: `style` picks `blender/amv/titles/<style>.py`, `spec` is the plan's spec dict."""
    id: str
    style: str
    spec: dict = field(compare=False)
    f_in: int
    dur: int
    shot: str | None = None   # shot name for a shot title (layer space), None for a screen title / watermark

    @property
    def screen(self) -> bool:
        """Screen-space title (not riding a shot's camera)."""
        return self.shot is None

    def frames(self, only=None) -> list[int]:
        """The title frames to render, k = 0 .. dur-1 (`only`: an iterable restricting them, e.g. `--frames`)."""
        ks = range(self.dur)
        if only is None:
            return list(ks)
        keep = set(only)
        return [k for k in ks if k in keep]

    def comp_frame(self, k: int) -> int:
        """The comp frame title frame `k` is shown at."""
        return self.f_in + k

    def out_dir(self, titles_dir) -> Path:
        return Path(titles_dir) / self.id

    @staticmethod
    def frame_name(k: int) -> str:
        return f"{k:04d}.png"


def _dur(spec: dict, what: str) -> int:
    d = spec.get("dur")
    if not isinstance(d, int) or d <= 0:
        raise ValueError(f"title {what}: spec.dur must be a positive int, got {d!r}")
    return d


def jobs_from_plan(plan) -> list[TitleJob]:
    """Every title of `plan` (a `filmtools.amv.plan.Plan`, or anything with `.raw`/`.shots`), shot titles first in
    shot order, then the screen titles in plan order, then the watermark still (`watermark`, dur 1). The outro is not a title."""
    jobs: list[TitleJob] = []
    for shot in plan.shots:
        for i, t in enumerate(shot.titles):
            tid = f"{shot.name}.{i}"
            jobs.append(TitleJob(tid, t["style"], t["spec"], int(t["f_in"]), _dur(t["spec"], tid), shot.name))
    for i, t in enumerate(plan.raw.get("titles") or []):
        tid = f"screen.{i}"
        jobs.append(TitleJob(tid, t["style"], t["spec"], int(t["f_in"]), _dur(t["spec"], tid), None))
    # the watermark is one still (watermark.py): the compositor reads titles/watermark/0000.png
    jobs.append(TitleJob(WATERMARK_ID, "watermark", {}, 0, 1, None))
    ids = [j.id for j in jobs]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate title ids in the plan")
    return jobs


def select(jobs, ids=None, styles=None) -> list[TitleJob]:
    """Jobs filtered by exact ids and/or styles; an unknown id is an error (a typo must not render nothing)."""
    jobs = list(jobs)
    if ids:
        known = {j.id for j in jobs}
        missing = [i for i in ids if i not in known]
        if missing:
            raise KeyError(f"unknown title id(s) {missing}; plan has {sorted(known)}")
        jobs = [j for j in jobs if j.id in set(ids)]
    if styles:
        jobs = [j for j in jobs if j.style in set(styles)]
    return jobs
