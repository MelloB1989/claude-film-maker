"""The host's studio, built in the open level by the bridge's ops (unreal/fmbridge): run in the editor with
`film-ue exec films/host-studio/unreal/studio.py` after build.py has imported the textures. Re-running rebuilds it.

The frame: the camera (HostCam, 38 mm on a Super 35 back) stands 2.3 m in front of the host and looks back along -X
at the wall (x = -260), so screen-left is +Y. At the wall the frame spans y -147..159 and z 52..224; the host covers
y -45..55 there.
    screen-left   floating walnut shelves under warm light: books, a print, a vase, an orb lamp, a plant
    centre-right  a walnut slat wall grazed from above, a pink neon </> on it, two teal light bars beside it
    midground     a side table on the right with a monitor of code and a lamp, between the host and the wall
    host          a big soft key camera-left, a weak fill, warm hair light, teal and amber rims, an eye light
    air           a thin haze, so the lights have a body
"""
import math
import random

import unreal
from fmbridge.ops import level as L, look as K, mh

T = "/Game/Studio/Textures"
M = "/Game/Studio/Materials"
KEEP = {"Floor", "BackWall", "SideWallL", "Host", "HostCam"}
rnd = random.Random(5)

# clear the old dressing and lights
L.delete([a[0] for a in L.actors() if a[0] not in KEEP])

# ------------------------------------------------------------------------------------------------- materials
mat = {
    "wall": K.material("MI_HS_Wall", (0.022, 0.023, 0.026), roughness=0.9, folder=M),
    "floor": K.material("MI_HS_Floor", (0.03, 0.028, 0.026), roughness=0.55, folder=M),
    "felt": K.material("MI_HS_Felt", (0.006, 0.006, 0.007), roughness=1.0, specular=0.2, folder=M),
    "walnut": K.material("MI_HS_Walnut", (1.0, 0.9, 0.85), kind="Textured", texture=f"{T}/T_Walnut", roughness=0.45, folder=M),
    "oak": K.material("MI_HS_Oak", (1.6, 1.45, 1.25), kind="Textured", texture=f"{T}/T_Walnut", roughness=0.5, folder=M),
    "metal": K.material("MI_HS_BlackMetal", (0.02, 0.02, 0.022), roughness=0.35, metallic=1.0, folder=M),
    "ceramic": K.material("MI_HS_Ceramic", (0.75, 0.72, 0.66), roughness=0.25, folder=M),
    "terracotta": K.material("MI_HS_Terracotta", (0.42, 0.16, 0.08), roughness=0.8, folder=M),
    "leaf": K.material("MI_HS_Leaf", (0.03, 0.12, 0.035), roughness=0.55, folder=M),
    "screen": K.material("MI_HS_CodeScreen", kind="Screen", texture=f"{T}/T_CodeScreen", intensity=2.5, folder=M),
    "neon": K.material("MI_HS_Neon", kind="Screen", texture=f"{T}/T_Neon", intensity=14.0, roughness=0.3, folder=M),
    "poster": K.material("MI_HS_Poster", (0.55, 0.55, 0.55), kind="Textured", texture=f"{T}/T_Poster", roughness=0.7, folder=M),
    "warm_led": K.material("MI_HS_WarmLed", (1.0, 0.55, 0.22), kind="Emissive", intensity=18.0, folder=M),
    "teal_led": K.material("MI_HS_TealLed", (0.05, 0.85, 0.75), kind="Emissive", intensity=22.0, folder=M),
    "orb": K.material("MI_HS_Orb", (1.0, 0.62, 0.3), kind="Emissive", intensity=9.0, folder=M),
    "bulb": K.material("MI_HS_Bulb", (1.0, 0.7, 0.4), kind="Emissive", intensity=40.0, folder=M),
}
books = [K.material(f"MI_HS_Book{i}", c, roughness=0.75, folder=M) for i, c in enumerate([
    (0.25, 0.04, 0.03), (0.03, 0.06, 0.12), (0.6, 0.5, 0.35), (0.02, 0.02, 0.02), (0.05, 0.16, 0.13), (0.55, 0.2, 0.05),
    (0.7, 0.68, 0.62)])]

K.apply("BackWall", mat["wall"])
K.apply("SideWallL", mat["wall"])
K.apply("Floor", mat["floor"])


def box(label, center, size, material, rot=None):
    return L.spawn(label, shape="cube", loc=center, size=size, rot_=rot, material=material)


# ------------------------------------------------------------------------------------------ the slat wall
SY0, SY1, SZ = -105.0, 35.0, 262.0
box("SlatBacker", (-258.5, (SY0 + SY1) / 2, SZ / 2), (3, SY1 - SY0, SZ), mat["felt"])
y, i = SY0 + 2.5, 0
while y < SY1 - 2:
    box(f"Slat{i:02d}", (-255.5, y, SZ / 2), (3.5, 4.5, SZ), mat["walnut"])
    y, i = y + 6.6, i + 1
K.light("SlatGraze", "rect", loc=(-249, (SY0 + SY1) / 2, SZ + 4), look_at=(-256, (SY0 + SY1) / 2, 0), intensity=14,
        temperature=2900, width=SY1 - SY0 - 10, height=4, barn_angle=88, volumetric=0.3)
SLATS = ["SlatBacker"] + [f"Slat{k:02d}" for k in range(i)]
K.channels(["SlatGraze"], [2])  # it grazes the slats alone: on the plain wall it threw the shelves' shadows
K.channels(SLATS, [0, 2])
box("NeonBack", (-252.6, -72, 196), (1.2, 64, 34), mat["felt"])
K.card("Neon", (-252.0, -72, 196), 60, 30, mat["neon"])

# teal light bars at the slat wall's right edge
for n, yy in enumerate((-115.0, -128.0)):
    box(f"TealBar{n}", (-256.0, yy, 140), (2.5, 2.5, 230), mat["teal_led"])
    K.light(f"TealBarLight{n}", "rect", loc=(-252.0, yy, 140), look_at=(0, yy, 140), intensity=4.0,
            color=(0.05, 0.9, 0.8), width=3, height=225, shadows=False)

# ------------------------------------------------------------------------------------------ shelves, left
SH_Y0, SH_Y1 = 58.0, 190.0
for n, z in enumerate((92.0, 148.0, 204.0)):
    box(f"Shelf{n}", (-246.0, (SH_Y0 + SH_Y1) / 2, z), (28, SH_Y1 - SH_Y0, 4), mat["oak"])
    box(f"ShelfLed{n}", (-234.0, (SH_Y0 + SH_Y1) / 2, z - 2.4), (1.0, SH_Y1 - SH_Y0 - 4, 0.6), mat["warm_led"])
    K.light(f"ShelfLight{n}", "rect", loc=(-238.0, (SH_Y0 + SH_Y1) / 2, z - 3), look_at=(-250.0, (SH_Y0 + SH_Y1) / 2, z - 60),
            intensity=1.4, temperature=2700, width=SH_Y1 - SH_Y0 - 6, height=3, barn_angle=45, volumetric=0.2)


def book_row(prefix, y0, z, count, lean_last=False):
    y = y0
    for k in range(count):
        th, hh = rnd.uniform(2.2, 4.5), rnd.uniform(18, 26)
        box(f"{prefix}{k}", (-248.0, y + th / 2, z + 2 + hh / 2), (rnd.uniform(14, 18), th, hh), rnd.choice(books))
        y += th + 0.15
    if lean_last:
        box(f"{prefix}Lean", (-248.0, y + 5, z + 2 + 10), (16, 3, 22), rnd.choice(books), rot={"roll": -16})
    return y


# top shelf: a row of books, a white vase, the orb lamp
book_row("BookA", 62, 204, 7, lean_last=True)
L.spawn("Vase", shape="cylinder", loc=(-247, 118, 204 + 2 + 11), size=(12, 12, 22), material=mat["ceramic"])
L.spawn("Orb", shape="sphere", loc=(-246, 150, 204 + 2 + 8), size=(16, 16, 16), material=mat["orb"])
K.light("OrbLight", "point", loc=(-240, 150, 214), intensity=1.6, temperature=2400, radius=200, shadows=False)
# middle shelf: the print leaning on the wall, a plant
L.spawn("Print", shape="cube", loc=(-254, 84, 148 + 2 + 26), size=(1.5, 40, 52), material=mat["poster"],
        rot_={"pitch": 0, "yaw": 0, "roll": 0})
L.move("Print", rot_={"pitch": -8, "yaw": 0, "roll": 0})
L.spawn("PlantPot", shape="cylinder", loc=(-246, 132, 148 + 2 + 7), size=(15, 15, 14), material=mat["terracotta"])
for k in range(9):  # a loose ball of leaves: soft and organic at this blur
    a, r = k * 2.4, rnd.uniform(3, 8)
    L.spawn(f"Leaf{k}", shape="sphere", loc=(-246 + rnd.uniform(-4, 4), 132 + math.cos(a) * r, 148 + 16 + rnd.uniform(6, 20)),
            size=(rnd.uniform(9, 13), rnd.uniform(9, 14), rnd.uniform(7, 11)), material=mat["leaf"])
# bottom shelf: books lying flat, a speaker
for k in range(3):
    box(f"Stack{k}", (-248, 74 + k * 1.5, 92 + 2 + 2.2 + k * 4.4), (20, 26 - k * 2, 4.2), books[(k + 2) % len(books)],
        rot={"yaw": rnd.uniform(-6, 6)})
box("Speaker", (-246, 128, 92 + 2 + 13), (18, 15, 26), mat["metal"])
L.spawn("SpeakerCone", shape="cylinder", loc=(-236.8, 128, 92 + 2 + 16), size=(9, 9, 0.6), material=mat["felt"],
        rot_={"pitch": 90, "yaw": 0, "roll": 0})

# fairy bulbs along the upper left: bokeh at f/2
for k in range(14):
    t = k / 13
    yy, zz = 30 + t * 140, 222 - math.sin(t * math.pi) * 12 + rnd.uniform(-2, 2)
    L.spawn(f"Bulb{k}", shape="sphere", loc=(-250 + rnd.uniform(-4, 4), yy, zz), size=(2.4, 2.4, 2.4), material=mat["bulb"])

# --------------------------------------------------------------------------------- the side table, midground right
TX, TY = -120.0, -80.0
box("TableTop", (TX, TY, 74), (55, 85, 3.5), mat["oak"])
for n, (dx, dy) in enumerate(((-22, -36), (-22, 36), (22, -36), (22, 36))):
    L.spawn(f"TableLeg{n}", shape="cylinder", loc=(TX + dx, TY + dy, 36), size=(3, 3, 72), material=mat["metal"])
yaw = 19.0  # the monitor turned toward the camera
box("Monitor", (TX - 6, TY - 4, 112), (2.5, 62, 36), mat["metal"], rot={"yaw": yaw})
K.card("MonitorScreen", (TX - 6, TY - 4, 112), 59, 33.2, mat["screen"], yaw=yaw, offset=1.35)
box("MonitorStand", (TX - 8, TY - 4, 85), (12, 3, 20), mat["metal"], rot={"yaw": yaw})
K.light("MonitorGlow", "rect", loc=(TX + 2, TY - 2, 112), look_at=(60, 40, 112), intensity=0.5, color=(0.45, 0.6, 1.0),
        width=55, height=30, shadows=False)
L.spawn("LampShade", shape="cone", loc=(TX + 8, TY - 30, 112), size=(16, 16, 14), material=mat["metal"],
        rot_={"pitch": 0, "yaw": 0, "roll": 180})
L.spawn("LampStem", shape="cylinder", loc=(TX + 8, TY - 30, 93), size=(1.5, 1.5, 34), material=mat["metal"])
K.light("LampLight", "spot", loc=(TX + 8, TY - 30, 106), look_at=(TX + 8, TY - 30, 70), intensity=12, temperature=2600,
        cone=50, radius=300)

# --------------------------------------------------------------------------------------------- the host's light
FACE = (8.0, 0.0, 172.0)
K.light("Key", "rect", loc=(150, 118, 228), look_at=FACE, intensity=10.0, temperature=5200, width=130, height=130,
        barn_angle=70, volumetric=0.4)
K.light("Fill", "rect", loc=(190, -125, 160), look_at=FACE, intensity=1.1, temperature=6500, width=180, height=180,
        specular=0.3, volumetric=0.0)
K.light("HairLight", "rect", loc=(-85, 25, 258), look_at=(0, 0, 186), intensity=7.0, temperature=3600, width=60,
        height=30, barn_angle=55)
K.light("RimTeal", "rect", loc=(-90, -105, 182), look_at=(0, 0, 160), intensity=5.0, color=(0.15, 0.8, 0.78), width=25,
        height=130, barn_angle=50)
K.light("RimAmber", "rect", loc=(-90, 105, 178), look_at=(0, 0, 160), intensity=3.5, color=(1.0, 0.6, 0.3), width=25,
        height=120, barn_angle=50)
K.light("EyeLight", "rect", loc=(214, 6, 186), look_at=FACE, intensity=0.5, temperature=6000, width=24, height=24,
        shadows=False, volumetric=0.0)
# lighting channels: the host's lights reach only the host (no spill or shadows on the set), the set's only the set
HOST_LIGHTS = ["Key", "Fill", "HairLight", "RimTeal", "RimAmber", "EyeLight"]
K.channels(HOST_LIGHTS, [1])
K.channels(["Host"], [1])
mh.garment("Host", "Shirt", vectors={"diffuse_color_1": (0.032, 0.034, 0.038), "diffuse_color_2": (0.045, 0.047, 0.052)})

# --------------------------------------------------------------------------------------------- air and lens
K.fog(density=0.012, volumetric=True, albedo=(0.85, 0.85, 0.9), extinction=0.35, height_falloff=0.02)
K.post({"auto_exposure_method": "AutoExposureMethod.AEM_MANUAL", "auto_exposure_bias": 9.2, "white_temp": 6200.0,
        "bloom_intensity": 0.3, "bloom_threshold": 1.0, "vignette_intensity": 0.35, "film_grain_intensity": 0.08,
        "scene_fringe_intensity": 0.0})
mh.cloth_inflate("Host", cm=1.0)
cam = L.actor("HostCam").get_cine_camera_component()
cam.set_editor_property("current_aperture", 2.0)
cam.set_editor_property("current_focal_length", 38.0)
L.save_level()
result = {"actors": len(L.actors())}
