# Explainers — log (round 6, 07 Nov, IST)

## Props (agent-05, branch fleet/agent-05/r6-props)

| IST | |
|---|---|
| 16:20 | Brief: chair, broadcast mic on desk boom with cable, walnut desk, optional headphones/plant; Blender headless on box A CPU (agent-06's slot: `/srv/ue/props_r6`, nice 15, `-t 6`, never the editor/project/reel paths) |
| 16:35 | `props/explainer/_pbr.py` (12 tileable 2K PBR sets drawn in numpy, UVs, UCX, FBX) + `build.py`; dims matched to agent-07's layout (chair (20,-20,0), desk centre (78,-20,0) top 74, mic from her left +Y) |
| 16:58 | Debug run on box A (256 px textures, no renders): all four FBX re-import at the built size in cm (chair 79.7 x 69 x 86, desk 55 x 110 x 74, mic boom 48 x 30.9 x 77, plant 12.9 x 12.8 x 43.9) |
| 17:02 | Full run: textures 70 s; FBX + textures + props.json → `s3://…/ue-linux/props/explainer/` |
| 17:10 | By eye: walnut figure too burl-like, leaf bands lost in noise → redrawn (rift-sawn walnut, clean sansevieria bands), job restarted |
| 17:15 | agent-07: UV0 has the tile baked in (material Tiling 1); plant moved to (100,25,74) by the clamp; headphones skipped (optional) |
| 17:25 | Chair preview: the desk's legs were never joined into SM_WalnutDesk (they floated in the scene) → fixed, re-uploaded; gentler normals on fine metals/rubber/plastic |
| 17:50 | Previews by eye: chair, desk, mic, plant, set (agent-07 frame) good; brushed alu still read hammered: not denoise (256 spp no-denoise test showed it) but low-frequency ROUGHNESS blotches on a mirror-like metal → alu varies only along its streaks; fixed (test render clean) |
| 18:05 | agent-07 moved the desk in (near edge x 38) and mirrored the boom to the -Y edge (scale -1 at yaw -90): no re-pose needed. Armrest 63.0 vs apron underside 63.4 noted |
| 18:30 | A full re-run died at once: `cd && rm && nohup … &` on one line ran the whole chain in a subshell that SSM killed with the command → relaunch with `setsid nohup` on its own line |
| 18:45 | Orchestrator (via agent-07): her feet never seen, WIDE's empty right → SM_WalnutDesk_Panel, SM_FloorLamp (practical, SOCKET_Bulb), SM_FloorSnakePlant; all 7 FBX re-import at size; uploaded with all textures |

## 18:40-18:51 IST, agent-05: SM_WalnutDesk_Waterfall (task 8c95)
- The operator found the panel desk's lower part "very weird" (legs, front). It is replaced by a waterfall desk: one
  3.2 cm walnut slab runs over the top and down both ends to the floor (mitred, 3.5 mm soft edges, grain wraps).
  A modesty panel is recessed 9 cm behind the camera-side edge and stops 13 cm off the floor. No legs, no apron.
- Size: 110 x 55 with the top at 71, as agent-07 and the orchestrator asked (agent-01's pose); underside of the top
  67.8. Origin and frame are the same as SM_WalnutDesk_Panel; placed at (59.5, -20, 0).
- Material: one slot, M_WalnutFine, with UV0 in metres and U along the grain, so /Game/Studio/Materials/MI_K_Walnut
  goes straight on. The Blender preview uses T_WalnutFine (grain lines ~4 mm, low contrast, satin), checked at 1:1.
- Built on box B (CPU, nice 15, 6 threads). Files are in s3 props/explainer: fbx/, textures/T_WalnutFine_*,
  preview/ (_CAM_WIDE has grey proxy legs; they are hidden), and the merged props.json.
- Open: the mic C-clamp on the -Y edge at x 67 has the waterfall end panel directly under that edge, so its lower jaw
  would sit inside the wood. Clamp it on the far (+X) edge, or use a top-mount/grommet base.
