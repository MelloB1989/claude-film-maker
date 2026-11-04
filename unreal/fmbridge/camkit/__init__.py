"""camkit: cinematography by numbers, in plain Python (no `unreal`, no numpy): it runs in the editor's embedded Python
(3.11) and on the operator's side alike, so every camera decision can be computed, unit-tested and explained without
an engine. fmbridge.ops.camera puts it on cameras and sequences.

- `geo`: vectors and Unreal's rotators (left-handed, Z up, X forward, Y right; rotators by keyword).
- `lens`: filmback and lens presets (the engine's own), fields of view, depth of field, and projection of world points
  to the frame as the cine camera draws it.
- `framing`: subjects as landmarks (head top, eyes, chin, chest, waist, knees, feet...), shot sizes (ECU..EWS), and
  the framing solver: subject + size + angle/side/height + lens or distance + composition -> camera transform.
- `moves`: camera moves (dolly, truck, pedestal, crane, orbit/arc, push-in, pull-out, pan, tilt, zoom, dolly zoom,
  whip pan) as eased keyframes, plus handheld noise.
- `coverage`: the coverage of a scene (master, singles, overs, close-ups, inserts) on one side of the line.
- `shotlist`: the shot list spec (validated, with times in frames, seconds or dialogue lines) resolved into a plan.
- `checks`: numeric checks of a frame and of a cut: headroom, cut-offs at joints, feet, safe areas, lead room, the
  180-degree line, the 30-degree rule, focus.
- `png`: a tiny PNG reader/writer and drawing for contact sheets and overlays (thirds, safe frames, labels).
"""
