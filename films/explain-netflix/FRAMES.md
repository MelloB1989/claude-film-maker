# Frames of each shot (24 fps)

Film frames each shot owns (a 1.5 frame `lead` puts every cut half way between two frames). Each shot is its EDL
frame count (agent-11's `edl/netflix.json`) plus a 12 frame tail that holds the end state.

| shot | first | frames | deliverable |
|---|---|---|---|
| title | 2 | 67 | title_full.mov |
| oca | 69 | 113 | oca_full.mov |
| prefill | 182 | 162 | prefill_full.mov |
| prefill_panel | 344 | 162 | prefill_panel.mov (ProRes 4444, alpha) |
| ladder | 506 | 147 | ladder_full.mov |
| abr | 653 | 175 | abr_full.mov |
| buffer | 828 | 98 | buffer_full.mov |
| buffer_panel | 926 | 98 | buffer_panel.mov (ProRes 4444, alpha) |
| planes | 1024 | 128 | planes_full.mov |
| end | 1152 | 48 | end_full.mov |
| lowerthird | 1200 | 72 | lowerthird.mov (ProRes 4444, alpha) |

Full shots: `GFX_REPO=<checkout> /srv/gfx/shard.sh explain-netflix <first/24> <(first+frames)/24> 8 <out> --only <shot>`.
Alpha shots: `films/explain-netflix/tools/matte.sh <shot> <first> <frames> <out>`.
