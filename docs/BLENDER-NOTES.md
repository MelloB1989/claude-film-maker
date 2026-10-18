# Blender notes (Timeless v3 stage)

Blender bugs and traps hit while building the v3 stage modules. Append a section headed by your task.

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
