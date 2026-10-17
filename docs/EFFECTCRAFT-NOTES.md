
## v2-core (agent-01): shots, MAIN, render
- `layer.property("ADBE Time Remapping").setValuesAtTimes(ts, vs)` works with one key per frame and interpolates linearly
  between keys; the two default keys are replaced. Remove keys past your last one, and set `layer.outPoint = comp.duration`.
  `layer.frameBlendingType = FrameBlendingType.NO_FRAME_BLEND` is accepted.
- `Property.keyInterpolationType(...)` is "not a callable function" (0.10.0): don't use it, write per-frame keys instead.
- Motion blur does NOT sample neighbouring layers across a hard cut: a layer with `inPoint = 15/30` over one with
  `outPoint = 15/30` renders pure colours on frames 14 and 15 with comp shutter 270/-135. No ghost frame, so cuts need no handle tricks.
- `ADBE Tile` (Motion Tile) with `Mirror Edges` = 1: `Output Width/Height` are percent of the layer and can be keyed. It is
  by far the slowest thing in the edit (a 500 % output turns a 0.6 s/frame draft frame into 6-10 s). Size it per frame to
  what the transform needs (moves.tile_need) and key it back to 100 elsewhere.
- `effectcraft-cli render --format png --start S --end E --out dir/f`: writes `dir/f_NNNNN.png` (NNNNN = comp frame).
  Frames are chosen by `ceil(t * fps)` for both ends: `--start (A-0.25)/fps --end (B-0.75)/fps` renders exactly A..B-1.
- Thread knob: the binary reads `RAYON_NUM_THREADS` (and `RAYON_RS_NUM_CPUS`); no CLI flag. Run N processes with
  `RAYON_NUM_THREADS=16/N` each on disjoint frame ranges.
- The render queue's VM does not sync `out/`: keep the `.ecproj` under another folder of the worktree (we use `build/`).
  A leftover output dir on the VM from an earlier job with the same name is reused: use a fresh name per experiment.
- Layer.inPoint/outPoint can be negative / beyond comp: fine (`startTime` negative for a precomp with handles).
