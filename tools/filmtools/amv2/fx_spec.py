"""FX spec: what Python knows that the EffectCraft script cannot compute. The core calls extend(E, ctx_py) before it writes
the script; everything lands under E["x"]["fx"], which ec/fx.jsx reads (all keys optional: fx.jsx has defaults).

All frames are absolute comp frames, positions are screen pixels at the tag's frame (1920x1080) unless noted. The numbers
below were measured by looking at the clip frames (tools/filmtools/amv2/test_fx.py renders them), not guessed.
"""

# Threshold level (0-255) of each ink frame, keyed by its tag frame: the plates are dark, so a fixed 128 would give an
# all-black frame. Chosen for ~40 % white.
INK_LEVEL = {587: 70, 656: 46, 690: 46}


def extend(E, ctx_py=None):
    x = E.setdefault("x", {})
    x["fx"] = {
        "ink_level": {str(k): v for k, v in INK_LEVEL.items()},
    }
    return E
