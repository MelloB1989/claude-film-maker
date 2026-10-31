# unreal: the bridge into Unreal Engine

`fmbridge` puts the Unreal editor under claude-film-maker's control: everything a person does in the editor (build
a MetaHuman, solve a voice to a face, dress and light a set, cut a sequence, render it) can be done from a script on
the operator's machine. It was built for the presenter in `films/host-studio/`, on a cloud workstation (Windows,
UE 5.8, an L4/L40S GPU, NICE DCV for the occasional look), but nothing in it names a film.

```
operator's Mac                                 workstation (EC2, Windows)
film-ue / filmtools.unreal.client  ──SSM port-forward──▶  127.0.0.1:18765  fmbridge.server (inside the editor)
  (tools/filmtools/unreal)              no inbound port        │ HTTP thread: queue, files, desktop input, screen
                                                               ▼
                                                        Slate post-tick: Python and ops on the game thread
```

## Pieces

- `fmbridge/server.py`: an HTTP server on 127.0.0.1 inside the editor, token in `Saved/fmbridge.token`. `POST /exec`
  runs Python (its `result` comes back), `POST /op` calls a named op, `GET /job` follows an async one, `GET|PUT /file`
  moves files, `GET /screen` grabs the desktop, `POST /gui` clicks and types, `GET /log` tails the editor log.
  Work runs on the game thread from a Slate post-tick callback; the `unreal` API is never touched elsewhere.
  **Multi-tick jobs**: an op (or exec'd code) that returns a generator runs across editor ticks; each `yield` lets the
  editor tick once (a scrubbed sequence, an animation or a rig settles), `yield 0.5` waits that long. This is what
  lets an op scrub a shot frame by frame and measure what it sees.
- `fmbridge/ops/`: the operations, each a plain function registered with `@op("module.name")`; `film-ue ops` lists
  them with their signatures and docstrings.
  - `assets`: list, import, duplicate, props, save.
  - `level`: actors, spawn (shapes, assets, classes), move, aim, set properties, bone positions.
  - `look`: materials (surface, textured, screen, emissive, glass), cards (upright pictures), lights, lighting
    channels, fog, post-process, cine cameras, tracking focus, stills.
  - `mh`: MetaHuman presets, rig, textures, wardrobe, build, garment colour, garment inflate, face driving.
  - `speech`: voice to face with MetaHuman Animator's audio solver, in a mood.
  - `anim`: curves, the closed-loop gaze lock, pose baking between face and body.
  - `seq`: shots, animation swaps, transform keys, camera cuts, sampling, stills and contact sheets.
  - `render`: Movie Render Queue, deferred or path traced, with a frame range.
- `fmbridge/gui.py`: SendInput clicks, drags, typing and keys, and screenshots (DCV's grabber or GDI), for the few
  things only the UI does (Fab, some dialogs).
- `fmbridge/inbox.py`: the fallback transport: a `.py` dropped in `Saved/Bridge/in` (over SSM, no tunnel) runs the
  same way; the result lands in `Saved/Bridge/out`. `film-ue install` uses it to restart the bridge.
- `init_unreal.py`: starts the bridge when the editor starts.

## Use

```bash
cd tools
uv run film-ue set --instance i-0123456789abcdef0 --region ap-south-1 --project-dir 'C:\UEProjects\HostStudio'
uv run film-ue up                 # start the workstation and wait for SSM
uv run film-ue install            # copy fmbridge into Content/Python and (re)start it; seconds once it is up
uv run film-ue health
uv run film-ue ops anim           # what the anim ops take
uv run film-ue op level.move label=Key 'loc=[150,118,228]' 'look_at=[8,0,172]'
uv run film-ue exec films/host-studio/unreal/studio.py
uv run film-ue screen /tmp/ws.png
uv run film-ue down               # stop it (it costs by the hour)
```

From Python: `from filmtools.unreal import client` then `client.op("seq.still", path=..., frame=96, ...)`,
`client.exec_code(src)`, `client.push(local, remote)`, `client.pull(remote, local)`. The tunnel opens on demand
(it needs the AWS Session Manager plugin) and the token is fetched over SSM and cached.

## What the host taught us

These are the traps the ops already handle; they matter when writing new ones.

- **Rotators by keyword.** `unreal.Rotator(a, b, c)` is (roll, pitch, yaw). Ops take `{"pitch", "yaw", "roll"}`.
- **FColor by keyword.** `unreal.Color`'s positional order is B, G, R, A: `unreal.Color(r=..., g=..., b=..., a=...)`.
- **Blueprint components go stale.** Changing a property on one component of a Blueprint actor (a MetaHuman) reruns
  its construction script, which replaces the others: fetch each component afresh, by name, before touching it.
- **Animation edits land late.** After editing an animation's keys the editor swaps in the recompressed data a
  moment later (seconds, with many bone tracks); measure until the pose has changed (`anim._await_change`).
- **A face played by Sequencer** needs `ANIMATION_SINGLE_NODE` (its Blueprint has no slot), and then it no longer
  copies the body: its neck and chest stay in the reference pose while the body moves, and the face rig turns the
  head from the speech on the face alone. The chest then pokes through the shirt. `anim.bake_follow` and
  `anim.head_to_body` make face and body one skeleton (0.00 cm apart on every shared bone).
- **Eyes on the lens** are measured, not guessed: `anim.gaze_lock` calibrates the rig's eye-look curves, scrubs the
  shot, aims each eye at the camera from the eye bones' real pose, and refines until the error is a few hundredths of
  a degree, keeping small saccades so the stare stays alive.
- **Lighting channels** separate the host's light from the set's: key, fill and rims on channel 1 with the host,
  practicals on 0, a light meant for one thing (the slat graze) on its own channel.
- **Cine cameras default to a Super 35 back** (23.76 mm), not full frame: plan the frame with the real filmback.
- **A request sent while the bridge restarts** would hang on the old server: `install` waits for the new one, and
  `server.stop()` answers anything still queued.
