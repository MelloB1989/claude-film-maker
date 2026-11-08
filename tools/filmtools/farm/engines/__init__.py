"""Renderers a worker runs a chunk with. Each module has:

    CONTIGUOUS: bool                    render one unbroken range (temporal state) or just the missing frames
    prepare(job, ctx) -> None           once per job on a worker (downloads, syncs, editor)
    render(job, chunk, todo, scratch, ctx) -> iterator of (frame, path)
                                        frames as they are finished; pre-roll frames included (the worker drops them)

`ctx` (worker.Ctx) has log(msg), stopping() (the lease was lost or the box is going down), conf (the worker's
settings) and sh(cmd). Python 3.10, stdlib only.
"""
from __future__ import annotations

import os

from .. import model


class RenderError(RuntimeError):
    """The chunk did not render; the message says why (it goes to the lease and the worker's log)."""


def get(engine: str):
    if engine == "blender":
        from . import blender
        return blender
    if engine == "ue":
        from . import ue
        return ue
    raise RenderError(f"no engine {engine!r}")


def frames_on_disk(d: str, ext: str = "") -> dict:
    """{frame: path} of NNNN.ext files in a folder."""
    out = {}
    if not os.path.isdir(d):
        return out
    for n in os.listdir(d):
        f = model.frame_of(n, ext)
        if f is not None:
            out[f] = os.path.join(d, n)
    return out
