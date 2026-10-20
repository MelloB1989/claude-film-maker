"""FX spec: what Python knows that the EffectCraft script cannot compute. The core calls extend(E, ctx_py) before it writes
the script; everything lands under E["x"]["fx"], which ec/fx.jsx reads (every key is optional: fx.jsx has defaults).

Frames are absolute comp frames; positions are CLIP pixels (1920x1080 plate) at the tag's frame, which fx.jsx maps through the
shot's MAIN layer transform (ctx.shot(id)) so the effect follows the core's camera move. The numbers below were read off the
rendered plates (tools/filmtools/amv2/test_fx.py frames ...), not guessed.
"""

# Threshold level (0-255) of each ink frame, keyed by its tag frame: the plates are dark, so a fixed 128 would give an
# all-black frame. Chosen for ~40 % white.
INK_LEVEL = {587: 70, 656: 46, 690: 46}

# lens_glint@F / lens_flare@F: where the glint sits (a bright point on the lens / on the mesh)
GLINT = {14: (980, 470),      # S01 T01: Tobey's left lens, upper edge
         256: (1180, 486)}    # S09 A01: the hottest hex cell of Andrew's lens mesh
SUN = {"S10": (1310, 530)}    # S10 A03 sunset: the sun between the towers, right of his head
EYE = {"S08": (901, 390)}     # S08 T08: the left iris (same as the EDL's focus)
GLASS = {"S21": [(470, 330), (1210, 270), (780, 700)]}   # S21 M04: three glints, on the dome's window frame / shards


def extend(E, ctx_py=None):
    x = E.setdefault("x", {})
    x["fx"] = {
        "ink_level": {str(k): v for k, v in INK_LEVEL.items()},
        "glint": {str(k): list(v) for k, v in GLINT.items()},
        "sun": {k: list(v) for k, v in SUN.items()},
        "eye": {k: list(v) for k, v in EYE.items()},
        "glass": {k: [list(p) for p in v] for k, v in GLASS.items()},
    }
    return E
