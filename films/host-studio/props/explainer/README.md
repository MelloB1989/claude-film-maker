# Explainer props (round 6)

Seated-presenter explainer set: a podcast lounge chair, a small walnut desk, a broadcast dynamic mic on a desk boom
arm (posed for the set), a snake plant; then a desk with a modesty panel, a floor lamp and a floor snake plant; over-ear headphones lying on the desk. Original designs, no marks. Blender 4.2, headless, CPU only; run on a GPU
box (never on fleet hosts):

    blender -b --factory-startup -t 6 -P films/host-studio/props/explainer/build.py -- --out <dir> [--no-render]
    #  --only chair,desk,mic,plant,desk_panel,lamp,floorplant,headphones   --samples 64 --res 1200   --tex-size 256 (quick debug)

- `_pbr.py`: 12 tileable 2K PBR sets drawn in numpy (periodic noise via FFT filtering): ChairFabric (plain-woven
  heathered yarn), BrushedAlu, PowderBlack, Rubber, Grille (woven wire mesh), Walnut (rift-sawn, oiled), Leather,
  PlasticBlack, Steel, Ceramic, Soil, Leaf (sansevieria bands), Brass, ShadeLinen. Per set `T_<X>_BC` (sRGB), `T_<X>_N` (DirectX, as
  Unreal wants), `T_<X>_ORM` (linear R AO, G roughness, B metallic). Also world-scale UVs, UCX collision, sockets,
  FBX export (cm) and a re-import size check.
- `build.py`: the assets, their previews and `props.json` (sizes, slots, placement, dims for staging).

## In Unreal

- UV0 `UVMap` is tiled with the tile size BAKED IN (1 UV unit = `tile_m` metres): material Tiling = 1. UV1
  `Lightmap` is packed 0..1.
- Collision: `UCX_<asset>_NN` convex hulls in each FBX. Sockets: `SM_MicBoom` has `SOCKET_Capsule` (front of the
  grille, +X along the aim) and `SOCKET_MicCentre` (they did not survive agent-07's combined-mesh import: check by bounds).
- Axes: Blender (x, y, z) -> Unreal (x, -y, z). A set yaw psi in Unreal = Blender rotation -psi.

| asset | origin | key dims (cm) |
|---|---|---|
| SM_PodcastChair | floor, swivel axis under the seat; faces +X | seat top 45, seat front edge x 24.5, arms top 63 (inner y ±25.5), back top 86, 9° recline; 80 x 69 x 86 |
| SM_WalnutDesk | floor, centre of the top | top 110 (Y) x 55 (X) at z 74, 3 thick; knee clearance 63.4 |
| SM_MicBoom | the clamp on the desk top (z 0 = desk top); desk on local +X | posed for clamp (70, 32.6, 74) yaw -90 in agent-07's set frame, capsule (44, -6, 99) aimed at the mouth (32, -20, 113) |
| SM_DeskPlant | bottom centre of the pot | pot 12.8 across, 12.6 high; 44 tall |
| SM_WalnutDesk_Panel | as SM_WalnutDesk | + modesty panel on +X (x 23.7..25.5, y ±44, z 8..70) and a return at the set's +Y end |
| SM_FloorLamp | floor, centre of the base | 152 tall; linen drum 44/40 cm at z 120..150; SOCKET_Bulb at z 138.5; slots M_ShadeLinen (two-sided, translucent), M_LampBulb (emissive) |
| SM_FloorSnakePlant | bottom centre of the pot | pot 36 across, 35 high; 111 tall |
| SM_Headphones | desk contact, centre of the footprint | lying on its side, band crown on +X tipped 13.8° onto the desk; 22.5 (X) x 20.1 (Y) x 11.4; slots M_PlasticBlack, M_Leather, M_Steel |

The mic pose comes from `MIC_CLAMP_UE`, `MIC_CAPSULE_UE`, `MOUTH_UE` at the top of `build.py`: change them and rerun
(`--only mic`, ~1 min without renders) for another framing.
