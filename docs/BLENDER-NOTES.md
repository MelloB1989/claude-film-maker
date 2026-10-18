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

## v3-text3d (agent-02): 3D titles + text_fly

1. **Text meshes: keep the caps flat.** If you shade every face of a converted text mesh smooth, the bevel's normals
   bleed into the long thin cap triangles, and the whole front face gets tilted normals. A shader that separates face,
   bevel and sides by the object-space normal (TexCoord > Normal, z) then puts the rim glow over the entire face. Fix:
   faces with |n.z| > 0.995 stay flat, and every edge between a flat cap and a smooth bevel face is marked sharp
   (`edge.smooth = False`).
2. **Letter positions.** A text curve can't report per-character positions. Build each glyph as its own curve and
   offset it by (right edge of the prefix `text[:i+1]`) - (right edge of the lone glyph). That keeps the font's advances.
3. **Big bevels break condensed fonts.** On Anton with `bevel_depth` 0.05 em, the bevel self-intersects in narrow
   counters (the N of SPIDER-MAN turned into stray vertical bars, and the word's bbox doubled in height). Stay at
   ~0.03 em; for a fatter rim, use the shader's rim band instead of more geometry.
4. **Decorative fonts don't extrude.** The installed "Spider-Man" movie font has hairline spikes and serifs that become
   needles in 3D. Use a clean condensed face (Anton + `shear` for the italic, Barlow Condensed Black Italic).
5. **Teleport sampling.** The core keys a teleport at t_h -/+ EPS (0.02). Sampling the camera at t_h -/+ 0.001
   interpolates between those two keys and returns the same blended pose on both sides. The A->B transform then comes
   out as ~identity and the copies stay in A's set (invisible in B). Always sample at exactly t_h -/+ ctx.EPS.
6. **Visibility keys before the first key.** `hide_render` fcurves extrapolate constant backwards. If the first key
   is "visible", the object shows on every earlier frame (TIMELESS letters appeared 4 f early). Start the key range a
   few frames before any entrance, with the object hidden there.
7. **Light-pass twins.** The plate view layer renders the `light` collection too. An emission twin of each letter (for
   the glow pass) therefore needs its own sub-collection (`T3D_glow`), excluded in every view layer except `light`
   (`layer_collection.exclude = True`).
8. **Metal without an environment.** The stage world is a near-black void, so Principled metal reflects black. A
   view-space "matcap" (reflect(-Incoming, Normal) -> Vector Transform world->camera -> horizon band / sky / floor ramp)
   gives chrome and glossy sides that read anywhere and shimmer as the letters turn. It costs nothing.
9. **Per-letter shader parameters.** An object custom property keyed per frame (`ob["t3d_pop"]`) is readable in the
   shader through an Attribute node of type OBJECT. One material can then serve every letter, each with its own pop.
10. **mathutils:** `Matrix.Diagonal((x, y, z, w))`, not `Matrix.Diag`.
11. **Light linking** (`light.light_linking.receiver_collection`) keeps a title's key/rim lights off the cards and off
    the other sets. Cards are emission-only anyway, but other modules' glossy objects are not.
