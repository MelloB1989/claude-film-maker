"""The host's studio, "karma": built in the open level by the bridge's ops (unreal/fmbridge). Run it in the editor with
`film-ue exec films/host-studio/unreal/studio.py` after build.py has imported the textures and the props. Re-running
rebuilds it.

The room (cm): the back wall at x = -260, the camera side towards +X, screen-left +Y, the host at the origin facing +X.
    back wall      warm limewash; a floor-to-ceiling window at y +130..+280 with sheer linen curtains, daylight
    centre         a walnut slat panel (y -60..+110), the black Samarkan "karma" on it, halo-lit from behind
    left           an olive tree in a pale pot in front of the sheers
    right          four floating light-oak shelves with warm LED strips over a light-oak credenza, dressed with the
                   owner's things: the seven product books, the polaroid, the lyzn block, the maker tray, the framed
                   card, the coin and pickaxe, the root prompt, the records, the 27 NOV calendar, the MelloB block,
                   the black hoodie with its note
    host           a soft key from the window side, a weak fill, a warm hair light and a warm rim from the shelves
Every prop comes from Blender (props/), each FBX in its own folder; its material slots are dressed by name from MAT.
"""
import json
import math
import os

import unreal
from fmbridge.ops import level as L, look as K, mh

T = "/Game/Studio/Textures"  # the label textures (labels.py) and the old ones (textures.py)
S = "/Game/Studio/Surfaces"  # the tileable surfaces (surfaces.py)
M = "/Game/Studio/Materials"
KEEP = {"Host", "HostCam", "HostCamB"}
WALL = -260.0
MOOD = globals().get("MOOD", "day")  # "night": no sun, a blue-hour garden outside, warm downlights and practicals
NIGHT = MOOD == "night"

# clear the old studio (its floor and walls too: the room is a prop now)
L.delete([a[0] for a in L.actors() if a[0] not in KEEP])

# >>> host swap
# who plays him (round 3): "trey" (the round-2 MetaHuman, the fallback) or "op" (the operator's MetaHuman, bodies.py
# "op"); either way the actor is labelled "Host" on the same mark, so the lights, cameras and performance find it
HOST = globals().get("HOST", os.environ.get("HOST_BODY", "trey"))
HOST_BP = {"trey": "/Game/Host/Unpacked/Host/BP_Host",
           "op": "/Game/Host/Unpacked/Host_Op/BP_Host_Op"}[HOST]
_h = L.actor("Host") if any(a[0] == "Host" for a in L.actors()) else None
if _h is None or not _h.get_class().get_path_name().startswith(HOST_BP + "."):
    _loc, _yaw = ((_h.get_actor_location(), _h.get_actor_rotation().yaw) if _h is not None
                  else (unreal.Vector(30, 40, 0), 0.0))
    L.spawn("Host", asset=HOST_BP, loc=(_loc.x, _loc.y, _loc.z), rot_=_yaw, replace=True)
    # the reel's Host binding pointed at the actor just replaced: re-point it (its tracks are kept), and say so
    if unreal.EditorAssetLibrary.does_asset_exist("/Game/Reel/SEQ_Reel"):
        from fmbridge.ops import seq as _seq
        print("SEQ_Reel Host binding:", _seq.rebind("/Game/Reel/SEQ_Reel", ["Host"]))
# <<< host swap


# ------------------------------------------------------------------------------------------------- materials

def tex(folder, name):
    p = f"{folder}/{name}"
    return p if unreal.EditorAssetLibrary.does_asset_exist(p) else ""


# what each surface averages to (linear), for while its texture is missing
PLAIN = {"Limewash": (0.68, 0.62, 0.53), "OakFloor": (0.5, 0.33, 0.18), "Oak": (0.55, 0.38, 0.22),
         "OakEnd": (0.45, 0.3, 0.17), "Walnut": (0.13, 0.065, 0.03), "Felt": (0.012, 0.012, 0.012),
         "Wool": (0.62, 0.57, 0.48), "Stoneware": (0.66, 0.62, 0.55), "BookCloth": (0.016, 0.045, 0.028),
         "Fleece": (0.015, 0.015, 0.016), "Leather": (0.02, 0.02, 0.02), "Linen": (0.75, 0.72, 0.66)}


def surface(name, tile_cm, color=(1.0, 1.0, 1.0), roughness=1.0, kind="Pbr", **kw):
    """A tileable surface from surfaces/ on world-scale UVs (1 UV = 1 m), the texture covering `tile_cm`."""
    a = tex(S, f"T_{name}_A")
    if not a:
        color, roughness = PLAIN.get(name, color), min(roughness, 0.7)
    return K.material(f"MI_K_{name}", color, kind=kind, texture=a, normal=tex(S, f"T_{name}_N"), mask=tex(S, f"T_{name}_R"),
                      tiling=100.0 / tile_cm, roughness=roughness, metallic=0.0, folder=M, **kw)


def label(name, kind="Pbr", color=(1.0, 1.0, 1.0), roughness=0.8, **kw):
    return K.material(f"MI_K_Label_{name}", color, kind=kind, texture=tex(T, f"T_Label_{name}"),
                      normal=tex(T, f"T_Label_{name}_N"), mask=tex(T, f"T_Label_{name}_M"), roughness=roughness,
                      metallic=1.0, folder=M, **kw)


def plain(name, color, roughness=0.6, metallic=0.0, specular=None):
    return K.material(f"MI_K_{name}", color, roughness=roughness, metallic=metallic, specular=specular, folder=M)


def glow(name, color, intensity):
    return K.material(f"MI_K_{name}", color, kind="Emissive", intensity=intensity, folder=M)


def glass(name, color=(0.9, 0.92, 0.95), opacity=0.12, roughness=0.05, specular=0.3):
    return K.material(f"MI_K_{name}", color, kind="Glass", opacity=opacity, roughness=roughness, specular=specular, folder=M)


def leaf(name, color, transmission, texture=""):
    """Two-sided leaves that let the daylight through (foliage shading, fully opaque)."""
    return K.material(f"MI_K_{name}", color, kind="Sheer", texture=texture, opacity=1.0, roughness=0.5,
                      transmission=transmission, folder=M)


# >>> bespoke materials (graphs look.material's kinds cannot express; built here, rebuilt when BESPOKE_REV changes)
MEL = unreal.MaterialEditingLibrary
BESPOKE_REV = "2"


def bespoke(name, build, folder=M):
    """A parent material of this studio's own: `build(m, x)` wires it; made once, rebuilt in place when BESPOKE_REV
    changes (its instances keep their values)."""
    path = f"{folder}/{name}"
    eal = unreal.EditorAssetLibrary
    if eal.does_asset_exist(path):
        m = unreal.load_asset(path)
        if eal.get_metadata_tag(m, "k_rev") == BESPOKE_REV:
            return m
        MEL.delete_all_material_expressions(m)
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.Material,
                                                                     unreal.MaterialFactoryNew())
    pos = [0]

    def x(cls, *ins, **props):
        """A MaterialExpression<cls>; each of `ins` is an expression or (expression, input pin), wired from its first
        output to the pin (default A, B in order; the only input when there is one). `param=` names a parameter."""
        pos[0] += 1
        e = MEL.create_material_expression(m, getattr(unreal, "MaterialExpression" + cls), -300 - 40 * pos[0],
                                           60 * pos[0])
        for k, v in props.items():
            e.set_editor_property("parameter_name" if k == "param" else k, v)
        for i, src in enumerate(ins):
            src, pin = src if isinstance(src, tuple) else (src, ("A", "B")[i] if len(ins) > 1 else "")
            MEL.connect_material_expressions(src, "", e, pin)
        return e

    def out(e, prop):
        MEL.connect_material_property(e, "", getattr(unreal.MaterialProperty, prop))
    build(m, x, out)
    MEL.recompile_material(m)
    eal.set_metadata_tag(m, "k_rev", BESPOKE_REV)
    eal.save_asset(path)
    return m


def instance(name, parent, vectors=None, scalars=None, folder=M):
    """An instance of a bespoke parent with its vector (linear RGB) and scalar parameters set."""
    path = f"{folder}/{name}"
    eal = unreal.EditorAssetLibrary
    mi = unreal.load_asset(path) if eal.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property("parent", parent)
    for k, v in (vectors or {}).items():
        MEL.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(*v, 1.0))
    for k, v in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(mi, k, float(v))
    eal.save_asset(path)
    return path


def _scalar(x, name, v):
    return x("ScalarParameter", param=name, default_value=v)


def _polished_metal(m, x, out):
    """Polished metal: Color (its F0), metallic 1, and a finish map from the mesh's vertex colours (the coin's Relief
    attribute): FieldRough where it is black, ReliefRough where R is 1 (the raised design), RimRough where G is 1
    (rims and edge); a mesh without vertex colours reads white and takes ReliefRough all over. The roughness is broken
    up by +-Var with a fine world-space noise (polish marks, fingerprints) and a slower one (uneven buffing), and the
    fine noise ripples the normal a little, so a highlight wobbles as it runs over the relief instead of sliding like
    CG chrome."""
    out(x("VectorParameter", param="Color", default_value=unreal.LinearColor(1.0, 0.77, 0.34, 1.0)), "MP_BASE_COLOR")
    out(x("Constant", r=1.0), "MP_METALLIC")
    vc = x("VertexColor")
    r = x("ComponentMask", vc, r=True, g=False, b=False, a=False)
    g = x("ComponentMask", vc, r=False, g=True, b=False, a=False)
    base = x("LinearInterpolate", (x("LinearInterpolate", (_scalar(x, "FieldRough", 0.3), "A"),
                                     (_scalar(x, "RimRough", 0.08), "B"), (g, "Alpha")), "A"),
             (_scalar(x, "ReliefRough", 0.08), "B"), (r, "Alpha"))
    wp = x("WorldPosition")
    fine = x("Noise", (wp, "Position"), scale=_FINE, levels=3, output_min=0.0, output_max=1.0)
    slow = x("Noise", (wp, "Position"), scale=_SLOW, levels=2, output_min=0.0, output_max=1.0)
    mix = x("LinearInterpolate", (fine, "A"), (slow, "B"), (x("Constant", r=0.45), "Alpha"))
    var = x("Multiply", x("Subtract", mix, x("Constant", r=0.5)), x("Multiply", _scalar(x, "Var", 0.3), x("Constant", r=2.0)))
    out(x("Multiply", base, x("Add", var, x("Constant", r=1.0))), "MP_ROUGHNESS")
    tilt = x("Multiply", x("Subtract", fine, x("Constant", r=0.5)), _scalar(x, "Ripple", 0.01))
    nrm = x("AppendVector", x("AppendVector", tilt, tilt), x("Constant", r=1.0))
    out(x("Normalize", nrm), "MP_NORMAL")


_FINE, _SLOW = 1.6, 0.25  # the noises' frequencies (per cm): ~6 mm polish marks, ~4 cm buffing


def _acrylic(m, x, out):
    """Frosted acrylic, opaque with subsurface scattering (Lumen lights it, it casts a real soft shadow, light soaks
    in and comes back warm) plus an LED glow from inside: GlowColor x Glow, strongest at the base and fading up the
    block, 0.2 + 0.8 (1 - h / GlowFade)^2 for h cm over the actor's pivot (its bottom centre)."""
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_SUBSURFACE)
    out(x("VectorParameter", param="Color", default_value=unreal.LinearColor(0.8, 0.79, 0.76, 1.0)), "MP_BASE_COLOR")
    out(_scalar(x, "Roughness", 0.42), "MP_ROUGHNESS")
    out(_scalar(x, "Specular", 0.5), "MP_SPECULAR")
    out(_scalar(x, "Scatter", 0.85), "MP_OPACITY")  # a subsurface material's opacity: how much light scatters in
    out(x("VectorParameter", param="ScatterColor", default_value=unreal.LinearColor(1.0, 0.82, 0.62, 1.0)),
        "MP_SUBSURFACE_COLOR")
    z = lambda e: x("ComponentMask", e, r=False, g=False, b=True, a=False)  # noqa: E731
    h = x("Subtract", z(x("WorldPosition")), z(x("ObjectPositionWS")))
    f = x("Saturate", x("OneMinus", x("Divide", h, _scalar(x, "GlowFade", 12.0))))
    fade = x("Add", x("Multiply", x("Multiply", f, f), x("Constant", r=0.8)), x("Constant", r=0.2))
    glow = x("Multiply", x("Multiply", x("VectorParameter", param="GlowColor",
                                         default_value=unreal.LinearColor(1.0, 0.72, 0.45, 1.0)),
                           _scalar(x, "Glow", 0.0)), fade)
    out(glow, "MP_EMISSIVE_COLOR")


GOLD_PARENT = bespoke("M_K_PolishedMetal", _polished_metal)
ACRYLIC_PARENT = bespoke("M_K_Acrylic", _acrylic)
# <<< bespoke materials

oak = surface("Oak", 100, roughness=1.0)
walnut = surface("Walnut", 100)
black_metal = plain("BlackMetal", (0.012, 0.012, 0.013), 0.45, 1.0)
brass = plain("Brass", (0.78, 0.56, 0.28), 0.3, 1.0)
GOLD = (1.0, 0.68, 0.25)  # gold's F0 (linear), a touch deeper than the textbook value: the room is warm already
# polished gold, evenly buffed (the GPU frame's accents, the pins, her hoops); the coin has its own finish below
gold = instance("MI_K_GoldPolished", GOLD_PARENT, vectors={"Color": GOLD},
                scalars={"FieldRough": 0.16, "ReliefRough": 0.16, "RimRough": 0.16, "Var": 0.3, "Ripple": 0.01})
# the coin: a satin field with mirror-polished relief and rims (from its Relief colours), so the B and the circuit
# read as bright metal against soft gold whatever the room puts in the reflection
coin_gold = instance("MI_K_CoinGold", GOLD_PARENT, vectors={"Color": GOLD},
                     scalars={"FieldRough": 0.26, "ReliefRough": 0.06, "RimRough": 0.06, "Var": 0.12, "Ripple": 0.008})
# the lyzn block: frosted faces, polished round-overs that glow brighter (edge-lit), white engraved letters
ACRYLIC = {"Color": (0.78, 0.78, 0.77), "ScatterColor": (0.95, 0.92, 0.88), "GlowColor": (1.0, 0.86, 0.7)}
GLOW = 2.0 if NIGHT else 1.0  # the block's LED base: a little brighter in the dark room
acrylic_frost = instance("MI_K_AcrylicFrost", ACRYLIC_PARENT, vectors=ACRYLIC,
                         scalars={"Roughness": 0.4, "Scatter": 0.9, "Glow": 0.3 * GLOW, "GlowFade": 12.0})
acrylic_polish = instance("MI_K_AcrylicPolish", ACRYLIC_PARENT, vectors=ACRYLIC,
                          scalars={"Roughness": 0.05, "Scatter": 0.9, "Glow": 1.0 * GLOW, "GlowFade": 12.0})
acrylic_engrave = instance("MI_K_AcrylicEngrave", ACRYLIC_PARENT,
                           vectors={"Color": (0.95, 0.95, 0.94), "ScatterColor": (1.0, 0.95, 0.9),
                                    "GlowColor": (1.0, 0.88, 0.74)},
                           scalars={"Roughness": 0.8, "Scatter": 0.6, "Glow": 2.2 * GLOW, "GlowFade": 12.0})
silver = plain("Silver", (0.85, 0.85, 0.86), 0.3, 1.0)
alu = plain("Alu", (0.7, 0.7, 0.72), 0.35, 1.0)
satin_black = plain("SatinBlack", (0.014, 0.014, 0.015), 0.5)
matte_black = plain("MatteBlack", (0.012, 0.012, 0.012), 0.7)
pages = plain("Pages", (0.62, 0.57, 0.47), 0.85)
win_glass = glass("WindowGlass", opacity=0.04)
clear_glass = glass("ClearGlass", (0.02, 0.02, 0.02), opacity=0.03, roughness=0.02)  # picture glass, the candle jar

MAT = {
    # the room
    "M_Wall": surface("Limewash", 200), "M_Ceiling": plain("Ceiling", (0.72, 0.7, 0.66), 0.9),
    "M_Floor": surface("OakFloor", 200), "M_Baseboard": plain("Baseboard", (0.66, 0.62, 0.56), 0.55),
    "M_WinFrame": plain("WinFrame", (0.68, 0.66, 0.62), 0.4), "M_Glass": clear_glass,
    "M_Sheer": K.material("MI_K_Sheer", (1.0, 0.98, 0.94), kind="Sheer", texture=tex(S, "T_Linen_A"),
                          mask=tex(S, "T_Linen_O"), tiling=100.0 / 8, opacity=0.9, roughness=0.8,
                          transmission=(0.66, 0.63, 0.58), glow=0.01 if NIGHT else 0.12, folder=M),
    "M_Rod": black_metal, "M_Rug": surface("Wool", 60),
    # the slat wall and the sign
    "M_Walnut": walnut, "M_Felt": surface("Felt", 40, color=(0.6, 0.6, 0.6)),
    "M_LetterBlack": plain("Powder", (0.011, 0.011, 0.012), 0.62),
    "M_Metal": plain("BracketMetal", (0.8, 0.66, 0.42), 0.35, 1.0),  # the card's bracket (and the sign's hidden pins)
    # furniture
    "M_Oak": oak, "M_OakEnd": surface("OakEnd", 20), "M_Alu": alu,
    "M_LedStrip": glow("LedStrip", (1.0, 0.66, 0.36), 9.0), "M_Plinth": matte_black,
    # plants
    "M_Pot": surface("Stoneware", 30, roughness=0.3), "M_Pebbles": plain("Pebbles", (0.24, 0.21, 0.18), 0.9),
    "M_Soil": plain("Soil", (0.05, 0.035, 0.025), 0.95), "M_Bark": plain("Bark", (0.16, 0.13, 0.1), 0.9),
    "M_LeafTop": leaf("OliveTop", (0.07, 0.09, 0.05), (0.35, 0.42, 0.12)),
    "M_LeafUnder": leaf("OliveUnder", (0.2, 0.22, 0.17), (0.35, 0.42, 0.12)),
    "M_Leaf": leaf("Pothos", (1.0, 1.0, 1.0), (0.4, 0.5, 0.1), texture=tex(T, "T_PothosLeaf")),
    "M_Stem": plain("Stem", (0.1, 0.16, 0.05), 0.6), "M_Root": plain("Root", (0.12, 0.09, 0.06), 0.8),
    # music
    "M_FootMetal": brass, "M_BlackMetal": plain("Anodised2", (0.015, 0.015, 0.016), 0.35, 1.0), "M_Platter": satin_black, "M_Vinyl": plain("Vinyl", (0.008, 0.008, 0.008), 0.25),
    "M_Label_Record": label("Record", roughness=0.6), "M_ArmMetal": silver,
    "M_StandMetal": black_metal, "M_HPBlack": matte_black,
    "M_HPLeather": surface("Leather", 10, color=(0.4, 0.4, 0.4), roughness=0.9), "M_HPMetal": silver,
    "M_Sleeve1": plain("Sleeve1", (0.015, 0.015, 0.015), 0.6), "M_Sleeve2": plain("Sleeve2", (0.2, 0.04, 0.035), 0.7),
    "M_Sleeve3": plain("Sleeve3", (0.45, 0.3, 0.08), 0.7), "M_Sleeve4": plain("Sleeve4", (0.1, 0.12, 0.14), 0.7),
    "M_Sleeve5": plain("Sleeve5", (0.6, 0.56, 0.47), 0.7), "M_Label_SleeveFront": label("SleeveFront"),
    # the maker tray and the framed card
    "M_PcbGreen": plain("PcbGreen", (0.02, 0.17, 0.06), 0.35), "M_PcbBlue": plain("PcbBlue", (0.01, 0.07, 0.3), 0.35),
    "M_Gold": gold, "M_ChipBlack": plain("Chip", (0.015, 0.015, 0.015), 0.5), "M_ChipLid": silver,
    "M_PortMetal": silver, "M_Breadboard": plain("Breadboard", (0.75, 0.74, 0.7), 0.5),
    "M_WireRed": plain("WireRed", (0.5, 0.02, 0.02), 0.4), "M_WireBlack": plain("WireBlack", (0.01, 0.01, 0.01), 0.4),
    "M_WireYellow": plain("WireYellow", (0.7, 0.5, 0.02), 0.4), "M_WireBlue": plain("WireBlue", (0.02, 0.1, 0.5), 0.4),
    "M_LedRed": glow("LedRed", (1.0, 0.05, 0.03), 40), "M_LedYellow": glow("LedYellow", (1.0, 0.6, 0.05), 40),
    "M_LedGreen": glow("LedGreen", (0.1, 1.0, 0.15), 40),
    "M_FrameBlack": satin_black, "M_FanBlack": matte_black, "M_AccentGold": gold,
    "M_PrintRed": plain("PrintRed", (0.5, 0.03, 0.03), 0.5), "M_PrintBlue": plain("PrintBlue", (0.02, 0.06, 0.45), 0.5),
    "M_Ceramic": plain("SmdCeramic", (0.35, 0.3, 0.22), 0.5), "M_ResistorBody": plain("Resistor", (0.55, 0.45, 0.3), 0.5),
    "M_Shroud": plain("Shroud", (0.025, 0.025, 0.028), 0.4, 0.6), "M_PcbBlack": plain("PcbBlack", (0.02, 0.02, 0.02), 0.35),
    "M_Heatsink": alu, "M_Copper": plain("Copper", (0.95, 0.55, 0.38), 0.3, 1.0),
    "M_PlasticBlack": matte_black, "M_FrameBacking": surface("Linen", 8, color=(0.7, 0.68, 0.64), roughness=1.0),
    # small objects
    "M_Brass": brass, "M_HandleWood": walnut, "M_Wax": plain("Wax", (0.75, 0.68, 0.55), 0.6),
    "M_Wick": matte_black, "M_Flame": glow("Flame", (1.0, 0.6, 0.25), 60),
    "M_Stoneware": surface("Stoneware", 30, roughness=0.25),
    "M_CeramicBlack": plain("CeramicBlack", (0.012, 0.012, 0.013), 0.08, specular=0.6),  # high-gloss glazes
    "M_CeramicWhite": plain("CeramicWhite", (0.78, 0.77, 0.73), 0.1, specular=0.6),
    "M_ClayFoot": plain("ClayFoot", (0.5, 0.42, 0.32), 0.85),
    # the drone and its remote
    "M_DroneBody": plain("DroneBody", (0.42, 0.42, 0.41), 0.45), "M_DroneDark": plain("DroneDark", (0.06, 0.06, 0.065), 0.5),
    "M_Motor": plain("Motor", (0.03, 0.03, 0.032), 0.35, 0.8), "M_Prop": plain("Prop", (0.55, 0.55, 0.54), 0.4),
    "M_GimbalBlack": plain("Gimbal", (0.012, 0.012, 0.013), 0.3), "M_Lens": glass("Lens", (0.01, 0.01, 0.015), 0.6, 0.02),
    "M_LedFront": glow("DroneLed", (1.0, 0.05, 0.03), 25), "M_ControllerBody": plain("Controller", (0.05, 0.05, 0.055), 0.5),
    # her watch (black, as in the concept)
    "M_WatchCase": plain("WatchCase", (0.02, 0.02, 0.022), 0.3, 1.0), "M_WatchBlack": matte_black,
    "M_WatchGlass": glass("WatchGlass", (0.01, 0.01, 0.01), 0.15, 0.02),
    "M_Label_WatchFace": K.material("MI_K_Label_WatchFace", kind="Screen", texture=tex(T, "T_Label_WatchFace"),
                                    intensity=1.5, roughness=0.05, folder=M),
    "M_WatchBand": plain("WatchBand", (0.015, 0.015, 0.016), 0.7),
    "M_Acrylic": acrylic_frost, "M_AcrylicPolish": acrylic_polish, "M_AcrylicEngrave": acrylic_engrave,
    # the label objects
    "M_Label_Name": label("Name", roughness=0.5), "M_CalStand": black_metal, "M_Wire": silver,
    "M_Paper": plain("Paper", (0.82, 0.81, 0.78), 0.85), "M_Label_Calendar": label("Calendar", roughness=0.85),
    "M_Case": plain("Anodised", (0.018, 0.018, 0.02), 0.4, 1.0),
    "M_ScreenGlass": glass("ScreenGlass", (0.02, 0.02, 0.02), opacity=0.25, roughness=0.02),
    "M_Label_Terminal": K.material("MI_K_Label_Terminal", kind="Screen", texture=tex(T, "T_Label_Terminal"),
                                   intensity=2.2, roughness=0.1, folder=M),
    "M_Label_Polaroid": label("Polaroid", roughness=0.35), "M_PolaroidBack": plain("PolaroidBack", (0.06, 0.06, 0.06), 0.6),
    "M_Label_Sticky": label("Sticky", roughness=0.85), "M_StickyBack": plain("StickyBack", (0.85, 0.7, 0.2), 0.85),
    "M_Mat": plain("PrintMat", (0.8, 0.79, 0.75), 0.9), "M_Label_Print": label("Print", roughness=0.85),
    # books
    "M_GreenCloth": surface("BookCloth", 10), "M_Pages": pages,
    "M_Book_Cream": plain("BookCream", (0.62, 0.56, 0.44), 0.8), "M_Book_White": plain("BookWhite", (0.7, 0.69, 0.65), 0.75),
    "M_Book_Grey": plain("BookGrey", (0.22, 0.22, 0.21), 0.85), "M_Book_Black": plain("BookBlack", (0.02, 0.02, 0.02), 0.7),
    "M_Book_Navy": plain("BookNavy", (0.02, 0.04, 0.1), 0.75), "M_Book_Sage": plain("BookSage", (0.24, 0.28, 0.2), 0.8),
    "M_Book_Green": plain("BookGreen", (0.03, 0.08, 0.05), 0.8),
    "M_Book_Terracotta": plain("BookTerracotta", (0.4, 0.13, 0.06), 0.8),
    # the hoodie
    "M_Fleece": surface("Fleece", 10, color=(0.5, 0.5, 0.5)), "M_Rib": surface("Fleece", 10, color=(0.45, 0.45, 0.45)),
    "M_Drawcord": plain("Drawcord", (0.012, 0.012, 0.012), 0.8), "M_Aglet": silver,
}
for i in range(1, 8):
    MAT[f"M_Label_Spine{i}"] = label(f"Spine{i}", roughness=1.0)

UNDRESSED = {}
OVERRIDE = {"Window": {"M_Glass": win_glass},  # a slot name that means something else on one prop
            "Coin": {"M_Gold": coin_gold}}


def prop(label_, name, loc, yaw=0.0, pitch=0.0, roll=0.0, scale=1.0):
    """A Blender prop (props/, imported by build.py) dressed by slot name, or None when it is not imported yet."""
    path = f"/Game/Studio/Props/{name}/{name}"
    if not unreal.EditorAssetLibrary.does_asset_exist(path):
        UNDRESSED[label_] = "not imported"
        return None
    L.spawn(label_, asset=path, loc=loc, rot_={"yaw": yaw, "pitch": pitch, "roll": roll}, scale=scale)
    names = []
    for c in L.actor(label_).get_components_by_class(unreal.StaticMeshComponent):
        names += [str(n) for n in c.get_material_slot_names()]
    K.slots(label_, {n: OVERRIDE.get(label_, {}).get(n, MAT[n]) for n in names if n in MAT})
    missing = [n for n in names if n not in MAT]
    if missing:
        UNDRESSED[label_] = missing
    return label_


def bbox(label_):
    o, e = L.actor(label_).get_actor_bounds(False)
    return [o.x - e.x, o.y - e.y, o.z - e.z], [o.x + e.x, o.y + e.y, o.z + e.z]


# ----------------------------------------------------------------------------------------------------- the room
for lab, name in (("Room", "room_shell"), ("Window", "window"), ("Curtains", "curtains"), ("Rug", "rug")):
    prop(lab, name, (0, 0, 0))
# the garden outside, out of focus behind the glass
K.card("Outside", (WALL - 140, 205, 150), 520, 900,
       K.material("MI_K_Outside", kind="Screen", texture=tex(T, "T_OutsideNight" if NIGHT else "T_Outside"),
                  intensity=1.2 if NIGHT else 18.0, roughness=1.0, folder=M))

# ------------------------------------------------------------------------------------------- slats and the sign
SLAT_Y, SLAT_DEPTH = 25.0, 3.4
prop("SlatPanel", "slat_panel", (WALL, SLAT_Y, 0))
SIGN_Z, SIGN_SCALE = 210.0, 1.2  # the concept's sign is ~120 cm across the 170 cm panel
if prop("Sign", "karma_sign", (WALL + SLAT_DEPTH, SLAT_Y, SIGN_Z), scale=SIGN_SCALE):
    halo = os.path.join(unreal.Paths.project_saved_dir(), "Import", "host-studio", "props", "karma_halo.json")
    if os.path.exists(halo):  # a soft glow card on the slats exactly behind the letters
        b = json.load(open(halo))
        w, h = (b["y1"] - b["y0"]) * SIGN_SCALE, (b["z1"] - b["z0"]) * SIGN_SCALE
        K.card("SignHalo", (WALL + SLAT_DEPTH + 0.3, SLAT_Y - (b["y0"] + b["y1"]) / 2 * SIGN_SCALE,
                            SIGN_Z + (b["z0"] + b["z1"]) / 2 * SIGN_SCALE),
               w * 1.3, h * 1.6, K.material("MI_K_Halo", (1.0, 0.62, 0.32), kind="Glow", texture=tex(T, "T_KarmaHalo"),
                                            intensity=2.5, folder=M))
    lo, hi = bbox("Sign")
    for k in range(9):  # LEDs on the letters' backs: warm light raking the slats around each letter
        y = lo[1] + 6 + (hi[1] - lo[1] - 12) * k / 8
        K.light(f"Halo{k}", "point", loc=(WALL + SLAT_DEPTH + 2.0 * SIGN_SCALE, y, (lo[2] + hi[2]) / 2), intensity=1.2,
                temperature=2700, radius=45, shadows=True, volumetric=0.0)
    K.channels([f"Halo{k}" for k in range(9)], [2])
    K.channels(["SlatPanel"], [0, 2])

# ---------------------------------------------------------------------------------------- the olive tree, left
prop("OliveTree", "olive_tree", (WALL + 62, 205, 0), yaw=35)

# ------------------------------------------------------------------------------------ shelves and credenza, right
SH_L, SH_LEN = -60.0, 150.0           # the shelves' left end (screen-left, +Y) and length
SH_C = SH_L - SH_LEN / 2
TOPS = (125.0, 162.0, 199.0, 236.0)   # shelf top surfaces, bottom to top
for n, z in enumerate(TOPS):
    prop(f"Shelf{n}", "shelf", (WALL, SH_C, z - 4.5))
    K.light(f"ShelfLed{n}", "rect", loc=(WALL + 23, SH_C, z - 5.2), look_at=(WALL + 18, SH_C, z - 60),
            intensity=0.45 if NIGHT else 1.15,
            temperature=2700, width=SH_LEN - 8, height=1.6, barn_angle=60, volumetric=0.0)
CR_C, CR_TOP = -135.0, 72.0
prop("Credenza", "credenza", (WALL, CR_C, 0))

D = WALL + 4.0  # where a row of books stands: 4 cm off the wall
# top shelf: the trailing pothos at the left end, the framed card, two vases on a little stack of books
prop("Pothos", "pothos_trailing", (WALL, SH_L, TOPS[3]))
prop("GpuFrame", "gpu_frame", (WALL + 1.5, SH_L - 50, TOPS[3]))
prop("VaseWhite", "vase_white", (WALL + 13, SH_L - 90, TOPS[3]), yaw=20)
prop("BookStack", "books_stack", (WALL + 12, SH_L - 122, TOPS[3]), yaw=-4)
prop("VaseBlack", "vase_black", (WALL + 12, SH_L - 122, TOPS[3] + 8.4))
# second shelf: the seven product books among plain ones, the polaroid half behind a vase, the lyzn block bookend
prop("BooksMain", "books_main", (D, SH_L - 62, TOPS[2]))  # clear of the pothos' vines (they reach ~30 cm in)
# Vaishnavi's polaroid: in front of the vase, leaning back on the last books, turned to the host camera
prop("Polaroid", "polaroid", (WALL + 21, SH_L - 103, TOPS[2]), yaw=20, pitch=12, scale=1.25)
prop("VaseSpeckle", "vase_speckle", (WALL + 11, SH_L - 116, TOPS[2]), yaw=40, scale=0.8)
prop("LyznBlock", "lyzn_block", (WALL + 15, SH_L - 132, TOPS[2]), yaw=-8)
# third shelf: the maker tray, the candle, the coin and the pickaxe
prop("IotTray", "iot_tray", (WALL + 12, SH_L - 28, TOPS[1]), yaw=3)
prop("Drone", "drone", (WALL + 12.5, SH_L - 64, TOPS[1]), yaw=-8)
prop("Candle", "candle", (WALL + 14, SH_L - 93, TOPS[1]))
K.light("CandleLight", "point", loc=(WALL + 14, SH_L - 93, TOPS[1] + 14), intensity=0.1, temperature=1800, radius=70,
        shadows=False, volumetric=0.0)
prop("Coin", "bitcoin_coin", (WALL + 11, SH_L - 109, TOPS[1]), yaw=20)  # turned out to the room, as displayed
prop("Pickaxe", "pickaxe", (WALL + 9, SH_L - 128, TOPS[1]), yaw=-10)
# bottom shelf: the root prompt, the print, a looser row of books, the small pothos
prop("Terminal", "terminal_display", (WALL + 12, SH_L - 22, TOPS[0]), yaw=4)
K.light("TerminalGlow", "rect", loc=(WALL + 16, SH_L - 22, TOPS[0] + 4), look_at=(WALL + 60, SH_L - 22, TOPS[0] + 4),
        intensity=0.15, color=(0.35, 1.0, 0.5), width=20, height=4, shadows=False, volumetric=0.0)
prop("Print", "framed_print", (WALL + 6, SH_L - 50, TOPS[0]))
prop("BooksLow", "books_low", (D, SH_L - 95, TOPS[0]))
prop("ShelfPlant", "plant_shelf", (WALL + 13, SH_L - 135, TOPS[0]), yaw=180)
# the credenza: the turntable, headphones, the MelloB block, the crate of records, the calendar, the hoodie
prop("Turntable", "turntable", (WALL + 22, CR_C + 62, CR_TOP), yaw=-6)
prop("Headphones", "headphones", (WALL + 15, CR_C + 22, CR_TOP), yaw=12)
prop("Nameplate", "nameplate", (WALL + 36, CR_C + 14, CR_TOP), yaw=8)
prop("Crate", "record_crate", (WALL + 17, CR_C - 22, CR_TOP), yaw=-4)
prop("Calendar", "desk_calendar", (WALL + 36, CR_C - 44, CR_TOP), yaw=-14)
prop("Hoodie", "hoodie", (WALL, CR_C - 95, CR_TOP))
NOTE = os.path.join(unreal.Paths.project_saved_dir(), "Import", "host-studio", "props", "hoodie_note.json")
if os.path.exists(NOTE):  # the hoodie's report says where the note's flat patch is, in the hoodie's frame
    n = json.load(open(NOTE))
    prop("StickyNote", "sticky_note", (WALL + n["x"], CR_C - 95 - n["y"], CR_TOP + n["z"]), yaw=-n.get("yaw", 0.0),
         pitch=n.get("pitch", 0.0))
prop("Stool", "stool", (-95, 20, 0), yaw=25)  # for the empty-room shots; hidden when the host is in frame

# ------------------------------------------------------------------------------------------------- daylight
if not NIGHT:
    K.sky(elevation=28, azimuth=-28, lux=17000, temperature=5100, sky_intensity=0.6, shadow_softness=0.7)
    K.light("WindowSky", "rect", loc=(WALL + 14, 205, 150), look_at=(WALL + 300, 205 - 60, 120), intensity=8,
            temperature=6200, width=150, height=280, barn_angle=80, volumetric=0.0)
    K.light("RoomBounce", "rect", loc=(150, 0, 290), look_at=(0, 0, 0), intensity=0.8, temperature=4500, width=300,
            height=300, shadows=False, specular=0.0, volumetric=0.0)
else:
    # the sun off below the horizon; a cool moonlit glow from the window and a cool fill against the warm practicals
    K.sky(elevation=-8, azimuth=-28, lux=0.0, temperature=7500, sky_intensity=0.04, shadow_softness=2.0)
    K.light("WindowSky", "rect", loc=(WALL + 14, 205, 150), look_at=(WALL + 300, 205 - 60, 120), intensity=1.2,
            color=(0.3, 0.45, 0.95), width=150, height=280, barn_angle=80, shadows=False, volumetric=0.0)
    K.light("RoomBounce", "rect", loc=(150, 0, 290), look_at=(0, 0, 0), intensity=0.4, temperature=10000, width=300,
            height=300, shadows=False, specular=0.0, volumetric=0.0)
    # warm recessed downlights: pools on the credenza, a wash down the slats, a lift on the olive tree
    for name, loc, at, cd in (("DownCredenza", (WALL + 55, CR_C, 296), (WALL + 25, CR_C, CR_TOP), 12.0),
                              ("DownSlats", (WALL + 32, SLAT_Y, 296), (WALL + 4, SLAT_Y, 90), 10.0),
                              ("DownOlive", (WALL + 75, 205, 296), (WALL + 62, 205, 120), 9.0),
                              ("DownShelves", (WALL + 60, SH_C, 296), (WALL + 15, SH_C, 140), 0.8)):
        K.light(name, "spot", loc=loc, look_at=at, intensity=cd, temperature=2700, cone=32, radius=600,
                volumetric=0.4, shadows=name != "DownSlats")  # the slat wash would throw the sign's shadow down the slats

# --------------------------------------------------------------------------------------------- the host's light
FACE = (8.0, 0.0, 172.0)
K.light("Key", "rect", loc=(140, 130, 215), look_at=FACE, intensity=5.5 if NIGHT else 9.0,
        temperature=4300 if NIGHT else 5000, width=140, height=140,
        barn_angle=70, volumetric=0.0)
K.light("Fill", "rect", loc=(190, -125, 160), look_at=FACE, intensity=0.7, temperature=4800, width=180, height=180,
        specular=0.3, volumetric=0.0)
K.light("HairLight", "rect", loc=(-85, 25, 258), look_at=(0, 0, 186), intensity=5.0, temperature=3800, width=60,
        height=30, barn_angle=55, volumetric=0.0)
K.light("RimWarm", "rect", loc=(-90, -105, 180), look_at=(0, 0, 160), intensity=3.0, temperature=3000, width=25,
        height=130, barn_angle=50, volumetric=0.0)
K.light("RimWindow", "rect", loc=(-90, 110, 185), look_at=(0, 0, 160), intensity=3.5, temperature=6000, width=25,
        height=130, barn_angle=50, volumetric=0.0)
K.light("EyeLight", "rect", loc=(214, 6, 186), look_at=FACE, intensity=0.5, temperature=5600, width=24, height=24,
        shadows=False, volumetric=0.0)
HOST_LIGHTS = ["Key", "Fill", "HairLight", "RimWarm", "RimWindow", "EyeLight"]
K.channels(HOST_LIGHTS, [1])
K.channels(["Host"], [0, 1])  # the daylight reaches the host too, so the host sits in the room's light
mh.garment("Host", "Shirt", vectors={"diffuse_color_1": (0.032, 0.034, 0.038), "diffuse_color_2": (0.045, 0.047, 0.052)})
# >>> his outfit
# his slim charcoal trousers (props/his_outfit.py, imported onto his skeleton by props/his_outfit_ue/import_outfit.py),
# a skeletal mesh component under his body that takes the body's pose (leader pose), worn under the default garment's
# tee (kept); the default garment's shorts are cut out (their slots get a fully transparent masked material).
HIS_DIR = "/Game/Host/Host_Outfit"
HIS_TROUSERS = f"{HIS_DIR}/SKM_Host_Trousers"
if unreal.EditorAssetLibrary.does_asset_exist(HIS_TROUSERS):
    his_mats = {"M_Trousers": K.material("MI_K_HisTrousers", (1.0, 1.0, 1.0), kind="Pbr",
                                         texture=tex(HIS_DIR, "T_HisTwill_A"), normal=tex(HIS_DIR, "T_HisTwill_N"),
                                         mask=tex(HIS_DIR, "T_HisTwill_M"), tiling=100.0 / 1.0, roughness=1.0,
                                         metallic=0.0, folder=M)}
    his_hidden = K.material("MI_K_HisHidden", (1.0, 1.0, 1.0), kind="PbrMasked", texture=tex(HIS_DIR, "T_HisHidden"),
                            folder=M)

    def his_part(name):  # fetched afresh each time: a change on one component rebuilds the others
        return next((c for c in L.actor("Host").get_components_by_class(unreal.SkeletalMeshComponent)
                     if c.get_name() == name), None)

    if his_part("Trousers") is None:
        sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
        SDL = unreal.SubobjectDataBlueprintFunctionLibrary
        body_h = next(h for h in sds.k2_gather_subobject_data_for_instance(L.actor("Host"))  # the blueprint's
                      if str(SDL.get_variable_name(SDL.get_data(h))) == "Body")  # components are templates: by variable
        new_h, why = sds.add_new_subobject(unreal.AddNewSubobjectParams(
            parent_handle=body_h, new_class=unreal.SkeletalMeshComponent))
        if why and str(why):
            raise RuntimeError(f"his outfit: add_new_subobject failed: {why}")
        sds.rename_subobject(new_h, unreal.Text("Trousers"))
    his_part("Trousers").set_skeletal_mesh_asset(unreal.load_asset(HIS_TROUSERS))
    for slot_, mi_ in his_mats.items():
        his_part("Trousers").set_material_by_name(slot_, unreal.load_asset(mi_))
    his_part("Trousers").set_editor_property("lighting_channels", his_part("Body").get_editor_property("lighting_channels"))
    def his_garment():  # the default garment (tee + shorts): "SkeletalMesh" on Trey, by elimination on another build
        return his_part("SkeletalMesh") or next((c for c in L.actor("Host").get_components_by_class(
            unreal.SkeletalMeshComponent) if c.get_name() not in ("Body", "Face", "Trousers")), None)

    if his_garment() is not None:
        for i, slot_ in enumerate(his_garment().get_material_slot_names()):  # the shorts: four slots, one name
            low_ = str(slot_).lower()
            # only the shorts: on another build the outfit's slot names may also cover the tee (round 3: dark patches
            # at Host_Op's tee hem); a slot naming the top too is left alone
            if "short" in low_ and not any(w in low_ for w in ("shirt", "tee", "top", "torso", "upper")):
                his_garment().set_material(i, unreal.load_asset(his_hidden))
    else:
        print("his outfit: no default garment on Host (no tee): wear one (mh.add_item ... slot=Outfits) and rebuild")
    his_part("Trousers").set_editor_property("use_bounds_from_leader_pose_component", True)
    # leader pose last, on every garment (after agent-02): a change to one instance component re-creates the others,
    # and a re-created component has lost its leader (it then stays in its bind pose while the body moves)
    for c in L.actor("Host").get_components_by_class(unreal.SkeletalMeshComponent):
        if c.get_name() not in ("Body", "Face"):
            c.set_leader_pose_component(his_part("Body"))
# <<< his outfit

# her: the female presenter on the same mark, hidden until a shot asks for her (stills.py --who her)
HER_BP = "/Game/Host/Unpacked/Presenter/BP_Presenter"
if unreal.EditorAssetLibrary.does_asset_exist(HER_BP):
    host = L.actor("Host")
    her = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_object(
        unreal.load_asset(HER_BP), host.get_actor_location(), host.get_actor_rotation())
    her.set_actor_label("Presenter")
    her.set_actor_hidden_in_game(True)
    her.set_is_temporarily_hidden_in_editor(True)
    K.channels(["Presenter"], [0, 1])
    # >>> outfit
    # her fitted outfit (props/her_outfit.py, imported onto her skeleton by props/her_outfit_ue/import_outfit.py): a
    # cream rib-knit top tucked into high-rise charcoal trousers, skeletal mesh components under her body that take the
    # body's pose (leader pose, set at the end of her section). Her MetaHuman is built without the default garment, so these are all she wears.
    FIT_DIR = "/Game/Host/Presenter_Outfit"
    fit = {"Top": (f"{FIT_DIR}/SKM_Presenter_Top", {
               "M_Top": K.material("MI_K_HerTop", (1.0, 1.0, 1.0), kind="Pbr", texture=tex(FIT_DIR, "T_HerRib_A"),
                                   normal=tex(FIT_DIR, "T_HerRib_N"), mask=tex(FIT_DIR, "T_HerRib_M"),
                                   tiling=100.0 / 2.0, roughness=1.0, metallic=0.0, folder=M)}),
           "Trousers": (f"{FIT_DIR}/SKM_Presenter_Trousers", {
               "M_Trousers": K.material("MI_K_HerTrousers", (1.0, 1.0, 1.0), kind="Pbr",
                                        texture=tex(FIT_DIR, "T_HerWool_A"), normal=tex(FIT_DIR, "T_HerWool_N"),
                                        mask=tex(FIT_DIR, "T_HerWool_M"), tiling=100.0 / 1.0, roughness=1.0,
                                        metallic=0.0, folder=M),
               "M_Hardware": plain("HerGold", (0.9, 0.62, 0.28), 0.25, metallic=1.0)})}

    def her_part(name):  # fetched afresh each time: a change on one component rebuilds the others
        return next((c for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent)
                     if c.get_name() == name), None)

    for part, (mesh, mats) in fit.items():
        if not unreal.EditorAssetLibrary.does_asset_exist(mesh):
            continue
        if her_part(part) is None:
            sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
            SDL = unreal.SubobjectDataBlueprintFunctionLibrary
            body_h = next(h for h in sds.k2_gather_subobject_data_for_instance(L.actor("Presenter"))  # the
                          if str(SDL.get_variable_name(SDL.get_data(h))) == "Body")  # template is Body_GEN_VARIABLE
            new_h, _ = sds.add_new_subobject(unreal.AddNewSubobjectParams(
                parent_handle=body_h, new_class=unreal.SkeletalMeshComponent))
            sds.rename_subobject(new_h, unreal.Text(part))
        her_part(part).set_skeletal_mesh_asset(unreal.load_asset(mesh))
        for slot_, mi_ in mats.items():
            her_part(part).set_material_by_name(slot_, unreal.load_asset(mi_))
        her_part(part).set_editor_property("lighting_channels", her_part("Body").get_editor_property("lighting_channels"))
    # <<< outfit
    # small gold hoops through the lobes, a black smartwatch on the left wrist, riding her bones
    comps = {c.get_name(): c for c in her.get_components_by_class(unreal.SkeletalMeshComponent)}
    face, body_ = comps["Face"], comps["Body"]
    rule = unreal.AttachmentRule.KEEP_WORLD

    def ride(lab):  # a prop spawns Static, and a Static root silently refuses to attach to a moving bone
        L.actor(lab).root_component.set_mobility(unreal.ComponentMobility.MOVABLE)
        return L.actor(lab)

    for side, bone in (("L", "FACIAL_L_Ear4"), ("R", "FACIAL_R_Ear4")):
        p = face.get_socket_location(bone)
        inward = 0.25 if side == "L" else -0.25  # through the lobe, not on its surface
        if prop(f"HerEar{side}", "hoop_earring", (p.x - 0.1, p.y + inward, p.z + 0.15)):
            ride(f"HerEar{side}").attach_to_component(face, bone, rule, rule, rule, False)
    a, b = body_.get_socket_location("lowerarm_twist_02_l"), body_.get_socket_location("hand_l")
    fwd = (b - a).normal()
    out = body_.get_socket_location("wrist_outer_l") - body_.get_socket_location("wrist_inner_l")
    up = (out - fwd * out.dot(fwd)).normal()  # the back of the wrist, square to the forearm
    at = b - fwd * 3.6  # just above the wrist bone
    if prop("HerWatch", "smartwatch", (at.x, at.y, at.z)):
        w = ride("HerWatch")
        w.attach_to_component(body_, "lowerarm_twist_02_l", rule, rule, rule, False)
        w.set_actor_rotation(unreal.MathLibrary.make_rot_from_yz(fwd, up), False)  # once attached (it kept the bone's)
    # her hair: sleek black, even root to tip. The preset's hair (melanin 0.8, redness 0.25) read with green lengths in
    # the warm day shots, from no parameter of the material and no light (reel hair tests a-h); full melanin hides it.
    # A child of each preset instance (strands, cards, helmet) so the rest of the preset's look carries over.
    hair = next((c for c in L.actor("Presenter").get_components_by_class(unreal.GroomComponent)
                 if c.get_name() == "Hair"), None)
    if hair:
        for i, suffix in enumerate(("", "_Cards", "_Helmet")):
            parent = unreal.load_asset(f"/Game/Host/Unpacked/Presenter/Grooms/MI_WI_Hair_L_Straight_Hair{suffix}")
            if parent:
                hair.set_material(i, unreal.load_asset(instance(
                    f"MI_K_HerHair{suffix}", parent, scalars={"hairMelanin": 1.0, "hairRedness": 0.05})))
    # leader pose last, on every garment (hers and the overshirt): a change to one instance component re-creates the
    # others, and a re-created component has lost its leader (it then stays in its bind pose while the body moves)
    for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent):
        if c.get_name() not in ("Body", "Face"):
            c.set_leader_pose_component(her_part("Body"))
    for lab in ("HerEarL", "HerEarR", "HerWatch"):
        try:
            x = L.actor(lab)
            x.set_actor_hidden_in_game(True)
            x.set_is_temporarily_hidden_in_editor(True)
            K.channels([lab], [0, 1])
        except ValueError:
            pass
    # >>> overshirt
    # her olive cotton-twill overshirt, worn open over her fitted top (props/overshirt.py, imported onto her skeleton by
    # props/overshirt_ue/import_overshirt.py): a skeletal mesh component under her body that takes the body's pose
    # (leader pose). Set last: a property change on her components reruns her construction script.
    SHIRT_DIR = "/Game/Host/Presenter_Overshirt"
    SHIRT = f"{SHIRT_DIR}/SKM_Presenter_Overshirt"
    if unreal.EditorAssetLibrary.does_asset_exist(SHIRT):
        shirt_mats = {
            "M_Overshirt": K.material("MI_K_Overshirt", (1.0, 1.0, 1.0), kind="Pbr",
                                      texture=tex(SHIRT_DIR, "T_OvershirtTwill_A"),
                                      normal=tex(SHIRT_DIR, "T_OvershirtTwill_N"),
                                      mask=tex(SHIRT_DIR, "T_OvershirtTwill_M"), tiling=100.0 / 2.0,
                                      roughness=1.0, metallic=0.0, folder=M),
            "M_Buttons": plain("OvershirtButtons", (0.07, 0.05, 0.032), 0.32, specular=0.5),  # dark horn
        }

        def her_comp(name):
            return next((c for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent)
                         if c.get_name() == name), None)

        if her_comp("Overshirt") is None:
            sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
            SDL = unreal.SubobjectDataBlueprintFunctionLibrary
            handles = sds.k2_gather_subobject_data_for_instance(L.actor("Presenter"))
            # the blueprint's own components come back as their templates (Body_GEN_VARIABLE): match the variable name
            body_h = next(h for h in handles if str(SDL.get_variable_name(SDL.get_data(h))) == "Body")
            new_h, why = sds.add_new_subobject(unreal.AddNewSubobjectParams(
                parent_handle=body_h, new_class=unreal.SkeletalMeshComponent))
            if why and str(why):
                raise RuntimeError(f"overshirt: add_new_subobject failed: {why}")
            sds.rename_subobject(new_h, unreal.Text("Overshirt"))
        her_comp("Overshirt").set_skeletal_mesh_asset(unreal.load_asset(SHIRT))
        for slot_, mi_ in shirt_mats.items():
            her_comp("Overshirt").set_material_by_name(slot_, unreal.load_asset(mi_))
        her_comp("Overshirt").set_editor_property("lighting_channels",
                                                  her_comp("Body").get_editor_property("lighting_channels"))
        her_comp("Overshirt").set_editor_property("use_bounds_from_leader_pose_component", True)
        her_comp("Overshirt").set_leader_pose_component(her_comp("Body"))
    # <<< overshirt

# --------------------------------------------------------------------------------------------- air, lens, cameras
K.fog(density=0.0006 if NIGHT else 0.0001, volumetric=True, albedo=(0.95, 0.93, 0.9), extinction=0.05,
      height_falloff=0.02)
K.post({"auto_exposure_method": "AutoExposureMethod.AEM_MANUAL", "auto_exposure_bias": 9.1 if NIGHT else 8.3, "white_temp": 5600.0,
        "bloom_intensity": 0.25, "bloom_threshold": 1.0, "vignette_intensity": 0.25, "film_grain_intensity": 0.06,
        "scene_fringe_intensity": 0.0, "lumen_final_gather_quality": 4.0, "lumen_reflection_quality": 2.0,
        "lumen_scene_detail": 2.0, "lumen_scene_lighting_quality": 2.0, "lumen_max_trace_distance": 2000.0})
# hair strands take the sky light unoccluded: in this closed, daylit room it would turn the host's hair white
unreal.SystemLibrary.execute_console_command(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(),
                                             "r.HairStrands.SkyLighting 0")
SUPER35 = [23.76, 13.365]
CAMS = {  # name: (location, look-at, focal mm, aperture, filmback)
    "KarmaHost": ([192, 12, 178], [0, -14, 166], 27.0, 4.0, SUPER35),
    "KarmaWide": ([255, -35, 150], [WALL, 15, 140], 30.0, 5.6, [36.0, 20.25]),
    "KarmaVertical": ([178, 6, 174], [0, 0, 166], 24.0, 2.8, [13.365, 23.76]),
    "KarmaShelf": ([WALL + 125, SH_L + 40, 192], [WALL + 8, SH_L - 78, 178], 35.0, 4.0, [24.0, 30.0]),
    "KarmaCredenza": ([WALL + 135, CR_C + 60, 135], [WALL + 15, CR_C - 15, 100], 38.0, 4.0, [24.0, 30.0]),
    "KarmaSign": ([WALL + 250, SLAT_Y - 70, 178], [WALL, SLAT_Y + 4, 224], 40.0, 5.6, [24.0, 24.0]),
}
for name, (loc, at, focal, ap, fb) in CAMS.items():
    K.camera(name, loc, at, focal=focal, aperture=ap, filmback=fb, pilot=False)


def finish():
    """The last steps run across editor ticks: the shirts are pushed out a few mm so skin under the tight tee stops
    poking through, and mh.cloth_inflate only swaps a garment's material once its shaders have compiled and a few
    frames have rendered (a material swapped or recompiled while it is drawn crashes the renderer; see README)."""
    inflated = {}
    for lab, cm in (("Host", 0.4), ("Presenter", 1.0)):
        try:
            L.actor(lab)
        except ValueError:
            continue
        inflated[lab] = yield from mh.cloth_inflate(lab, cm=cm, which="Shirt")  # over the shorts, not with them
    L.save_level()
    return {"actors": len(L.actors()), "undressed": UNDRESSED, "inflated": inflated}


result = finish()
