"""The Rain Ferry's cast as VRoid Studio models (films/rain-ferry/assets/vroid/<name>.vrm, VRM 1.0; base_masc.vrm
stands in for a character whose file is not there yet), through the core's blender/lib/vrm.py: dressed as STORY.md
has them, soaked by the rain (or dry), and given what VRoid does not make (blender/lib/props.py). Each character has
its own module, rf/vroid_shinza.py and rf/vroid_tsuru.py (their variants: kasa, sword, pipe, pole, seated, wet, ...),
sharing rf/vroid_common.py (what carries each prop, how to animate them).

Each builder takes (collection, look, **variant) and returns the character facing +x with its feet at the origin
(rf/cast.py's convention): "root" (place and turn it), "vrm" (the vrm.Character), "head" (between the eyes, for
castsheet.py), "face", a function of the cels' `eyes` (1 open; less narrowed, more wide) giving the expressions to
set, "props" (every prop object) and "parts" (the props by name, for a shot to move or detach). Called with no
variant they are the standoff's.

The cast sheets' variants are builders of their own here (VARIANTS: shinza_kasa_on, tsuru_drawn, ...):

    blender -b -P blender/castsheet.py -- --film rain-ferry --module rf.vroid_cast --builders shinza,tsuru \\
        --out out/rain-ferry/vroid
    blender -b -P blender/castsheet.py -- --film rain-ferry --module rf.vroid_cast \\
        --builders shinza_kasa_on,shinza_back,shinza_broken,shinza_dry,tsuru_pipe,tsuru_shoulder,tsuru_drawn,tsuru_seated
"""
from __future__ import annotations

from functools import partial

from .vroid_shinza import shinza
from .vroid_tsuru import tsuru

VARIANTS = {
    "shinza_kasa_on": (shinza, dict(kasa="on", sword="back")),      # shot 4's walk: the hat low, the sword slung
    "shinza_back": (shinza, dict(kasa="back", sword="back")),       # on the jetty before the draw
    "shinza_broken": (shinza, dict(kasa=None, sword="broken")),     # after the flash
    "shinza_dry": (shinza, dict(kasa=None, sword="broken", headband=False, wet=0.0)),     # kneeling in the sun
    "tsuru_pipe": (tsuru, dict(pipe="mouth", pole="boat", seated=True)),    # smoking at the end of the jetty
    "tsuru_pipe_hand": (tsuru, dict(pipe="hand", pole="boat")),
    "tsuru_shoulder": (tsuru, dict(pole="shoulder")),               # walking back to the boat
    "tsuru_drawn": (tsuru, dict(pole="drawn")),                     # the flash
    "tsuru_seated": (tsuru, dict(pipe="hand", pole="hand", seated=True)),
    "tsuru_dry": (tsuru, dict(pole="shoulder", wet=0.0)),
}
for _name, (_builder, _kw) in VARIANTS.items():
    globals()[_name] = partial(_builder, name=_builder.__name__, **_kw)

__all__ = ["shinza", "tsuru", *VARIANTS]
