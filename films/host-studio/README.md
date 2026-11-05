# host-studio

A presenter for tech explainers: a MetaHuman talking to camera in a dark creator studio, made in Unreal Engine 5.8
on a cloud workstation and driven entirely through the bridge (`unreal/`, `film-ue`).

- `textures.py`: the set's textures, drawn in code: the monitor's editor, the neon `</>`, the shelf print, walnut.
- `unreal/studio.py`: the set and its light, built in the open level by the bridge's ops (run in the editor).
- `build.py`: draws and imports the textures, builds the studio, brings back a still.
- `shot.py`: a line as a finished shot: voice to face in a mood, two cameras cut on the voice's pauses, face and body
  made one skeleton, the eyes locked on the lens, a Movie Render Queue render, an mp4.
- `props/`: Blender scripts for the props (plants, the boom mic, the keyboard, the mug), exported as FBX.

```bash
cd tools
uv run python ../films/host-studio/build.py               # the set, and a still
uv run python ../films/host-studio/shot.py --all          # solve, cameras, sync, gaze, render → out/host-studio/
```
