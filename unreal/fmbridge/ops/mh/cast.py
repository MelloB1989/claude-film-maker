"""MetaHuman variations (B47): mh.variants turns one seed and a few ranges into N distinct character specs (the pure
generator is _cast.py) and, on request, makes them (each converged by mh.apply), with a live preview of each in a row
for a contact sheet. The client-side `cast` spec kind (tools/filmtools/unreal/mh_cast.py) runs the same generator."""
from __future__ import annotations

import inspect

from .. import op
from ...errors import OpError
from . import _cast


def _generate(cast: dict) -> dict:
    try:
        return _cast.generate(cast)
    except _cast.CastError as e:
        raise OpError(f"cast: {e}", code="bad_args", hint="see examples/unreal/cast/ and docs/unreal/metahuman.md")


@op("mh.variants", mutates=True, idempotent=True, tags=["metahuman", "slow"])
def variants(*, cast: dict, make: bool = False, stop_before: str = "", preview: bool = False,
             spacing_cm: float = 70.0):
    """N distinct, plausible characters from one seed and ranges (age band, sex, height, build, skin tone, hair and
    wardrobe pools): deterministic per seed, as `character` specs; with `make`, each one is made and converged by
    mh.apply (a multi-tick job).

    Args: cast: the cast object (kind cast: seed, count, folder, presets, ranges; schema cast.schema.json).
    make: create/converge every member (needs the Epic sign-in unless rig is none or stop_before="mh.rig").
    stop_before: passed to each mh.apply (e.g. "mh.rig": shape only). preview: also place a live preview of each
    member in a row along +Y (labels Preview_<name>), for stills and a contact sheet. spacing_cm: the row spacing.
    Returns: {"members": [specs], "traits", "distances": nearest earlier member, "changed", "made": [{"name",
    "changed"}], "previews": [labels]}.
    Example: film-ue op mh.variants 'cast={"seed": 7, "count": 6, "folder": "/Game/Extras", "presets": ["Ada", "Jorge"], "rig": "none"}'
    """
    from .. import call
    g = _generate(cast)
    out = {**g, "changed": False, "made": [], "previews": []}
    if not (make or preview):
        return out
    for i, spec in enumerate(g["members"]):
        if make:
            r = call("mh.apply", spec=spec, stop_before=stop_before)
            if inspect.isgenerator(r):
                r = yield from r
            out["made"].append({"name": spec["name"], "changed": r["changed"]})
            out["changed"] = out["changed"] or r["changed"]
        if preview:
            p = call("mh.preview", path=spec["asset"], label=f"Preview_{spec['name']}",
                     loc=[0, i * float(spacing_cm), 0], yaw_deg=180)
            out["previews"].append(p["label"])
            out["changed"] = out["changed"] or p["changed"]
        yield
    return out
