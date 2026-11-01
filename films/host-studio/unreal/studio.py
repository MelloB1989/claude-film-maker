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

# clear the old studio (its floor and walls too: the room is a prop now)
L.delete([a[0] for a in L.actors() if a[0] not in KEEP])


# ------------------------------------------------------------------------------------------------- materials

def tex(folder, name):
    p = f"{folder}/{name}"
    return p if unreal.EditorAssetLibrary.does_asset_exist(p) else ""


def surface(name, tile_cm, color=(1.0, 1.0, 1.0), roughness=1.0, kind="Pbr", **kw):
    """A tileable surface from surfaces/ on world-scale UVs (1 UV = 1 m), the texture covering `tile_cm`."""
    a = tex(S, f"T_{name}_A")
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


def glass(name, color=(0.9, 0.92, 0.95), opacity=0.12, roughness=0.05):
    return K.material(f"MI_K_{name}", color, kind="Glass", opacity=opacity, roughness=roughness, specular=0.5, folder=M)


def leaf(name, color, transmission, texture=""):
    """Two-sided leaves that let the daylight through (foliage shading, fully opaque)."""
    return K.material(f"MI_K_{name}", color, kind="Sheer", texture=texture, opacity=1.0, roughness=0.5,
                      transmission=transmission, folder=M)


oak = surface("Oak", 100, roughness=1.0)
walnut = surface("Walnut", 100)
black_metal = plain("BlackMetal", (0.012, 0.012, 0.013), 0.45, 1.0)
brass = plain("Brass", (0.78, 0.56, 0.28), 0.3, 1.0)
gold = plain("Gold", (0.95, 0.7, 0.32), 0.22, 1.0)
silver = plain("Silver", (0.85, 0.85, 0.86), 0.3, 1.0)
alu = plain("Alu", (0.7, 0.7, 0.72), 0.35, 1.0)
satin_black = plain("SatinBlack", (0.014, 0.014, 0.015), 0.5)
matte_black = plain("MatteBlack", (0.012, 0.012, 0.012), 0.7)
pages = plain("Pages", (0.62, 0.57, 0.47), 0.85)
win_glass = glass("WindowGlass", opacity=0.04)
clear_glass = glass("ClearGlass", opacity=0.1)

MAT = {
    # the room
    "M_Wall": surface("Limewash", 200), "M_Ceiling": plain("Ceiling", (0.72, 0.7, 0.66), 0.9),
    "M_Floor": surface("OakFloor", 200), "M_Baseboard": plain("Baseboard", (0.66, 0.62, 0.56), 0.55),
    "M_WinFrame": plain("WinFrame", (0.68, 0.66, 0.62), 0.4), "M_Glass": win_glass,
    "M_Sheer": K.material("MI_K_Sheer", (1.0, 0.98, 0.94), kind="Sheer", texture=tex(S, "T_Linen_A"),
                          mask=tex(S, "T_Linen_O"), tiling=100.0 / 8, opacity=0.9, roughness=0.8,
                          transmission=(1.0, 0.92, 0.8), glow=0.25, folder=M),
    "M_Rod": black_metal, "M_Rug": surface("Wool", 60),
    # the slat wall and the sign
    "M_Walnut": walnut, "M_Felt": surface("Felt", 40, color=(0.6, 0.6, 0.6)),
    "M_LetterBlack": plain("Powder", (0.011, 0.011, 0.012), 0.62),
    "M_Metal": plain("BracketMetal", (0.8, 0.66, 0.42), 0.35, 1.0),  # the card's bracket (and the sign's hidden pins)
    # furniture
    "M_Oak": oak, "M_OakEnd": surface("OakEnd", 20), "M_Alu": alu,
    "M_LedStrip": glow("LedStrip", (1.0, 0.66, 0.36), 9.0), "M_Plinth": matte_black,
    # plants
    "M_Pot": surface("Stoneware", 30, roughness=0.7), "M_Pebbles": plain("Pebbles", (0.24, 0.21, 0.18), 0.9),
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
    "M_Stoneware": surface("Stoneware", 30, roughness=0.6),
    "M_CeramicBlack": plain("CeramicBlack", (0.02, 0.02, 0.022), 0.55),
    "M_CeramicWhite": plain("CeramicWhite", (0.72, 0.7, 0.66), 0.35),
    "M_Acrylic": K.material("MI_K_Acrylic", (0.92, 0.94, 0.96), kind="Glass", opacity=0.45, roughness=0.45, folder=M),
    "M_Label_Lyzn": label("Lyzn", kind="PbrMasked", roughness=0.7),
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
    K.slots(label_, {n: MAT[n] for n in names if n in MAT})
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
       K.material("MI_K_Outside", kind="Screen", texture=tex(T, "T_Outside"), intensity=40.0, roughness=1.0, folder=M))

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
    K.light(f"ShelfLed{n}", "rect", loc=(WALL + 23, SH_C, z - 5.2), look_at=(WALL + 18, SH_C, z - 60), intensity=2.2,
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
prop("BooksMain", "books_main", (D, SH_L - 42, TOPS[2]))
prop("Polaroid", "polaroid", (WALL + 17, SH_L - 83, TOPS[2]), yaw=8, roll=-12)
prop("VaseSpeckle", "vase_speckle", (WALL + 14, SH_L - 97, TOPS[2]), yaw=40)
prop("LyznBlock", "lyzn_block", (WALL + 15, SH_L - 116, TOPS[2]), yaw=-8)
# third shelf: the maker tray, the candle, the coin and the pickaxe
prop("IotTray", "iot_tray", (WALL + 12, SH_L - 34, TOPS[1]), yaw=3)
prop("Candle", "candle", (WALL + 14, SH_L - 78, TOPS[1]))
K.light("CandleLight", "point", loc=(WALL + 14, SH_L - 78, TOPS[1] + 13), intensity=0.8, temperature=1900, radius=120,
        shadows=True, volumetric=0.0)
prop("Coin", "bitcoin_coin", (WALL + 6, SH_L - 95, TOPS[1] + 2.0), pitch=-72)
prop("Pickaxe", "pickaxe", (WALL + 12, SH_L - 115, TOPS[1]), yaw=-20)
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
    prop("StickyNote", "sticky_note", (WALL + n["x"], CR_C - 95 - n["y"], CR_TOP + n["z"]), yaw=n.get("yaw", 0.0),
         pitch=n.get("pitch", 0.0))
prop("Stool", "stool", (-95, 20, 0), yaw=25)  # for the empty-room shots; hidden when the host is in frame

# ------------------------------------------------------------------------------------------------- daylight
K.sky(elevation=28, azimuth=-28, lux=55000, temperature=5300, sky_intensity=1.0, shadow_softness=0.7)
K.light("WindowSky", "rect", loc=(WALL + 14, 205, 150), look_at=(WALL + 300, 205 - 60, 120), intensity=18,
        temperature=6200, width=150, height=280, barn_angle=80, volumetric=0.0)
K.light("RoomBounce", "rect", loc=(150, 0, 290), look_at=(0, 0, 0), intensity=1.5, temperature=4500, width=300,
        height=300, shadows=False, specular=0.0, volumetric=0.0)

# --------------------------------------------------------------------------------------------- the host's light
FACE = (8.0, 0.0, 172.0)
K.light("Key", "rect", loc=(140, 130, 215), look_at=FACE, intensity=9.0, temperature=5000, width=140, height=140,
        barn_angle=70, volumetric=0.0)
K.light("Fill", "rect", loc=(190, -125, 160), look_at=FACE, intensity=1.0, temperature=4800, width=180, height=180,
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

# --------------------------------------------------------------------------------------------- air, lens, cameras
K.fog(density=0.0015, volumetric=True, albedo=(0.95, 0.93, 0.9), extinction=0.15, height_falloff=0.02)
K.post({"auto_exposure_method": "AutoExposureMethod.AEM_MANUAL", "auto_exposure_bias": 11.0, "white_temp": 5600.0,
        "bloom_intensity": 0.25, "bloom_threshold": 1.0, "vignette_intensity": 0.25, "film_grain_intensity": 0.06,
        "scene_fringe_intensity": 0.0, "lumen_final_gather_quality": 4.0, "lumen_reflection_quality": 2.0,
        "lumen_scene_detail": 2.0, "lumen_scene_lighting_quality": 2.0, "lumen_max_trace_distance": 2000.0})
mh.cloth_inflate("Host", cm=1.0)
SUPER35 = [23.76, 13.365]
CAMS = {  # name: (location, look-at, focal mm, aperture, filmback)
    "KarmaHost": ([160, 12, 168], [0, -10, 160], 30.0, 2.8, SUPER35),
    "KarmaWide": ([395, -60, 150], [WALL, 30, 135], 22.0, 5.6, [36.0, 20.25]),
    "KarmaVertical": ([170, 8, 160], [0, 0, 170], 28.0, 2.8, [13.365, 23.76]),
    "KarmaShelf": ([WALL + 95, SH_L + 25, 205], [WALL + 10, SH_L - 60, 182], 50.0, 2.8, [24.0, 30.0]),
    "KarmaCredenza": ([WALL + 120, CR_C + 45, 140], [WALL + 15, CR_C - 10, 100], 45.0, 2.8, [24.0, 30.0]),
    "KarmaSign": ([WALL + 160, SLAT_Y - 70, 185], [WALL, SLAT_Y, 228], 50.0, 4.0, [24.0, 24.0]),
}
for name, (loc, at, focal, ap, fb) in CAMS.items():
    K.camera(name, loc, at, focal=focal, aperture=ap, filmback=fb, pilot=False)
L.save_level()
result = {"actors": len(L.actors()), "undressed": UNDRESSED}
