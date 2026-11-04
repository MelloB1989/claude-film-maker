"""MetaHumans by code: the whole MetaHuman Character editor (Creator) as ops, plus the assembled character in a level.

    character.py   mh.presets, mh.add (preset / copy / blank), mh.duplicate, mh.describe, mh.find, mh.remove
    appearance.py  mh.body (measurement constraints), mh.face (blend, coefficients, landmarks), mh.skin, mh.eyes,
                   mh.eyelashes, mh.teeth, mh.makeup
    wardrobe.py    mh.wardrobe, mh.palette, mh.add_item, mh.clear_slot, mh.groom, mh.item_params, mh.item_set
    cloud.py       mh.auth_status, mh.login, mh.rig, mh.textures (multi-tick, fail fast without a sign-in)
    build.py       mh.can_build, mh.build, mh.preview
    actor.py       mh.components, mh.drive_face, mh.import_garment, mh.dress, mh.leader, mh.leader_check, mh.attach,
                   mh.clip_check, mh.cloth_inflate, mh.garment
    spec.py        mh.apply (converge to a `character` spec), mh.export (a character as a spec)
    cast.py        mh.variants (N distinct characters from a seed: background extras; pure generator _cast.py)

The guide is docs/unreal/metahuman.md. `from fmbridge.ops import mh` keeps working: the legacy names are here.
"""
from __future__ import annotations

from . import _core
from ._core import GROOMS, PRESETS, sub  # noqa: F401
from .character import add, describe, duplicate, find, from_preset, presets, remove  # noqa: F401
from .appearance import (body, body_constraints, eyelashes, eyes, face, face_landmarks, makeup,  # noqa: F401
                         settings_fields, skin, teeth)
from .wardrobe import add_item, clear_slot, groom, item_params, item_set, palette, wardrobe  # noqa: F401
from .cloud import auth_status, login, rig, textures  # noqa: F401
from .build import build, can_build, preview  # noqa: F401
from .actor import (attach, clip_check, cloth_inflate, components, dress, drive_face, garment,  # noqa: F401
                    import_garment, leader, leader_check)
from .spec import apply, export  # noqa: F401
from .cast import variants  # noqa: F401

_char = _core.char  # legacy helper names (films/ and old exec'd scripts)


def _signed_in() -> bool:
    return _core.signed_in() is not False
