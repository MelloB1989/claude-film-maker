# EffectCraft notes (v2 agents append a section per task)

## elements (Blender RGBA elements, agent-07)

Probed against effectcraft-cli 0.10.0 while checking how the Blender element sequences composite.

- **PNG alpha is imported as STRAIGHT alpha, always.** A 3-line probe (`importFile` a PNG, `layers.add`, `render-frame` over a
  grey solid) was compared pixel by pixel with both formulas: straight `rgb*a + bg*(1-a)` matched with a mean error of
  0.0013, premultiplied `rgb + bg*(1-a)` with 0.19. `FootageItem.mainSource.alphaMode`, `.premulColor` and `.hasAlpha` all read
  `undefined` (hasAlpha is `false` even for a PNG with alpha), so there is no scripted interpret-footage switch.
  Workaround: `blender/amv2/elements.py` writes straight-alpha PNGs by default (`--alpha straight`); `--alpha premul` exists
  for a build that can interpret premultiplied footage. A premultiplied PNG imported as-is gets its soft edges and glows
  dimmed (multiplied by alpha twice).
- Single-frame `render-frame` of a 1920x1080 comp with one 1080p PNG layer takes about 1.6 s.
- The element sequences are named by comp frame (`NNNN.png`, e.g. `0802.png`), so import them as a numbered sequence and
  start the layer at that comp frame (or set `startTime = frame / 30`), no remap is needed.
