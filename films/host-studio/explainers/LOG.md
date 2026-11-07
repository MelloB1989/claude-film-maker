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
