"""clothkit: Chaos cloth by numbers, in plain Python (no `unreal`, no numpy): it runs in the editor's embedded Python
(3.11) and on the operator's side alike, so a garment's cloth setup, its painted maps and its pre-roll are computed,
unit-tested and explained without an engine. fmbridge.ops.cloth puts it on garments and sequences; fmbridge.qa.cloth
judges the simulation it produces.

- `presets`: fabric presets (cotton_tee, overshirt_light, trousers): the Chaos cloth config values, the zones of the
  garment (anchored at the shoulders or the waist, free at the hem and the sleeves) and their max distances, with the
  reasons and sources (docs/unreal/research/cloth-physics.md).
- `paint`: per-vertex maps from a garment's rest pose: each vertex's zone (nearest bone segment), its max distance
  (a ramp from the anchor to the hem), its backstop, merged with the fit's vertex colours (R = ease to the body,
  G = pinned) when the garment has them.
- `preroll`: how many frames a shot needs before its first rendered frame for the cloth to settle, and what that
  means for an MRQ job (engine warm-up held on the first frame, or played through the camera cut's handles).
"""
