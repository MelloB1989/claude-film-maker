"""The Rain Ferry's cast (STORY.md), as realistic people in the film's toon look: Shinza, the young ronin
(rf/shinza.py), and Tsuru, the ferrywoman (rf/tsuru.py), each built on the core's people (blender/lib/human.py,
garments.py, hair.py). Only their designs live in this film: colours, build, face, hair, costume, props and pose.

Each builder takes (collection, look) and returns its character built facing +x with the feet at the origin: a root
empty (place and turn it), the rig, the head's centre (for blender/castsheet.py), the parts the wind moves (`tails`,
`cape`) and `breathe(frames, fps)`, which keys the character's breath across a shot.

    blender -b -P blender/castsheet.py -- --film rain-ferry --module rf.cast --builders shinza,tsuru

The standoff no longer builds them: it draws its cast as 2D cels (rf/shinza_cels.py, rf/shinza_full.py,
rf/tsuru_cels.py, blender/lib/cels.py).
"""
from __future__ import annotations

from .shinza import shinza
from .tsuru import tsuru

__all__ = ["shinza", "tsuru"]
