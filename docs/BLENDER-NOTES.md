# Blender notes (bugs, gotchas, measured settings)

## Task v3-core (agent-01): the amv3 3D stage, Blender 5.2.2 / Cycles

- **Image sequences before their first frame.** `ImageUser` clamps the relative frame to `[0, frames]` (not
  `[1, frames]`), so a card that has to hold its first plate frame shows file `offset + 0`, which doesn't exist (pink).
  The stage avoids `frame_start` / `frame_offset` arithmetic entirely: every sequence is a folder of symlinks
  `<out>/_seq/<kind>/<shot>/f_00000..f_00899` that point at the nearest real frame, with `frame_start 0, frame_duration
  900, frame_offset -1` (scene frame N -> file N). Holding the end frames outside the plate range is then free.
- **Plate fidelity vs the pixel filter.** A frame at s = 1 (card exactly fills the frame), diffed against the plate JPEG
  at 1920x1080, 16 spp. Share of pixels within +-2 levels: Blackman-Harris 1.5 (default) 95.5 %, BH 1.0 97.0 %,
  Box 1.0 96.7 %, Gaussian 0.6 98.4 %, Gaussian 0.45 98.9 %, **Gaussian 0.3 99.4 %** (p99 2 levels, bias +0.004, gradient
  energy 98.6 % of the plate). The plate pass uses Gaussian 0.3. The text and light passes use BH 1.5 (antialiased 3D
  edges). With Standard view, Look None and dither 0, there is no colour bias.
- **Sample count and smear metrics.** At 8 spp the motion-blur smear is speckled, and Laplacian-based sharpness
  (`motion_metrics.py`) scores those frames as sharp (smear median 0, 56 % "hard cuts"). The same frames at 32 spp give
  smear median 5, 0 % hard cuts. Judge smears at >= 32 spp.
- **Layered actions (5.x).** `action.fcurves` is gone. `action.fcurve_ensure_for_datablock(id, path, index=i)` works,
  then `keyframe_points.add(n)` + `foreach_set("co", ...)`. It keys 2500 camera keys in well under a second.
  `keyframe_insert` with `preferences.edit.keyframe_new_interpolation_type = 'LINEAR'` also works (slower).
- **Camera motion blur steps.** `cam.cycles.motion_steps` exists on the camera object (set to 4). Keys every 0.25 f in
  windows keep fast rolls (up to ~60 deg/f at the cut) from being linearised inside the shutter.
- **Teleports and the shutter.** A set change at a half frame t_h is keyed at t_h - 0.02 / t_h + 0.02. The shutter
  (centred) of the frames on either side must stay <= 2 * (0.5 - 0.025) = 0.95, or one sample lands on the other set.
  `render.motion_blur_shutter` is animatable (keyed per frame).
- **Gate fit.** A linear similarity fit (d = T + a p + b perp p) reads a big per-frame roll as a zoom-out (a = cos th - 1).
  Use the exact form: scale |1 + a + ib|, angle atan2(b, 1 + a).
- `World.use_nodes` prints a deprecation warning in 5.2 (to be removed in 6.0). It's harmless.
- The VM's python venv has no matplotlib. `motion_metrics.py` writes `summary.json` and `metrics.csv` and then fails on
  the plot.

## Task v3-xfxB (agent-07): glass shatters, lightning, panels (Blender 5.2, Cycles CPU on the VM)
- **Camera motion blur smears "instantaneous" emitters.** A lightning bolt that lives one frame still gets the
  camera's motion blur (static objects blur when the camera moves), so a fast push turns thin filaments into wide
  ribbons. `ob.cycles.use_motion_blur = False` does NOT help (it only drops the object's own motion). Fix: key the
  bolt to ride with the camera through its frame (`_fx3d.ride_camera`: M(t) = cam(t) @ cam(t_ref)^-1 @ M_world),
  and give each frame its own bolt object visible on [k-0.5, k+0.5) so no shape changes mid-shutter.
- **Additive emitters have alpha 0 in a transparent film.** Emission + Transparent BSDF (light that never occludes)
  renders with alpha 0 and full RGB. Use the light pass as RGB add (finishing: footage alpha "Ignore"), never
  alpha-over. Plain Emission (opaque) keeps alpha 1.
- **A tinted Transparent BSDF in front of an emission card did not visibly darken it** (meant as a multiply filter).
  A Mix Shader of Transparent and a dim Emission (keyed factor) works as a darkening veil.
- **Bevelled Voronoi shards show their seams** while they are still coplanar (the bevel rounds every edge). Keep an
  intact card until the break frame and show the shards only from the break.
- `bpy -P script.py` exits 0 on a Python exception unless you pass `--python-exit-code 1`.
- Render queue: a job file name that already has a `.done` returns at once with the OLD log; use a fresh name per run.
- Thin emissive crack lines over a fast push: they get the card's radial blur too; keep them thin (0.2-0.6 mm in card
  space) and moderately bright or they read as white bands.
