"""Frame interpolators for the retime stage: synthesise the clip image at a fractional position between two frames.

Every interpolator works in display (sRGB-encoded) values as float32 HxWx3 in 0..1, the domain optical-flow and RIFE
were built for; retime.py decodes the results to linear light before it averages the shutter samples.

    interp = make("flow")                       # or "rife"
    imgs = interp.between(frame0, frame1, [0.25, 0.5, 0.75])   # one float32 image per timestep
"""
from __future__ import annotations


class Interpolator:
    name = "base"

    def between(self, img0, img1, ts):
        """Images at times `ts` (each 0 < t < 1, 0 = img0, 1 = img1) between two float32 sRGB-encoded frames."""
        raise NotImplementedError


def make(mode: str, **kw) -> Interpolator:
    """The interpolator for a retime mode (`flow` | `rife`); heavy imports (cv2 / torch) happen here, not at import."""
    if mode == "flow":
        from .flow import FlowInterpolator
        return FlowInterpolator(**kw)
    if mode == "rife":
        from .rife import RifeInterpolator
        return RifeInterpolator(**kw)
    raise ValueError(f"no interpolator for mode {mode!r}")
