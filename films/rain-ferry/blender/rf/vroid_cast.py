"""The Rain Ferry's cast as VRoid Studio models (films/rain-ferry/assets/vroid/<name>.vrm, VRM 1.0; base_masc.vrm
stands in for a character whose file is not there yet), through the core's blender/lib/vrm.py: posed for the standoff
as the cels draw them, soaked by the rain, and given what VRoid does not make (blender/lib/props.py). Each
character has its own module, rf/vroid_shinza.py and rf/vroid_tsuru.py, sharing rf/vroid_common.py.

Each builder takes (collection, look) and returns the character facing +x with its feet at the origin (rf/cast.py's
convention): "root" (place and turn it), "vrm" (the vrm.Character), "head" (between the eyes, for castsheet.py) and
"face", a function of the cels' `eyes` (1 open; less narrowed, more wide) giving the expressions to set.

    blender -b -P blender/castsheet.py -- --film rain-ferry --module rf.vroid_cast --builders shinza,tsuru \\
        --out out/rain-ferry/vroid
"""
from __future__ import annotations

from .vroid_shinza import shinza
from .vroid_tsuru import tsuru

__all__ = ["shinza", "tsuru"]
