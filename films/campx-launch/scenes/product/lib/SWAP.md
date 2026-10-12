# Product scenes: how the data drives them

`ingestui`, `readui`, `markui` and `control` are four one-line classes over `UiScene` (ui.ts). Everything a scene
shows is in `params.ts`, in image coordinates (0..1 over the screenshot; `px(x, y)` and `rg(x, y, w, h)` convert PNG
pixels and the INDEX.md regions).

To change a scene: edit its `Cfg`.

- `images`: the screenshot(s), paths relative to the film folder; a later image crossfades in at `from` (local s).
- `base`: size at zoom 1 (`w` = fraction of the frame's width, or `h` of its height). `anchor`, `yaw` (deg), `dist`.
- `cam`: keys `{ t, x, y, z }`: look at image point (x, y) at zoom z (1 = fitted). Cosine-eased, zoom in log space.
- `spots`: focus pulls `{ t0, t1, rect }`: the rest defocuses and dims; `dim` 0..1, `pad` in image units.
- `callouts` `{ t, until, text, sub, at, off }`: dot on `at`, thin leader, pill at `off` (ref px from the dot).
- `boxes` `{ t, until, rect, label, tone }`, `ticks` `{ t, at }`, `chips` `{ t, text, at, pulse }`,
  `cursor` `[{ t, at, click }]` (glides between keys; `click` ripples).

The film can override any key per entry with `params: { cfg: { ... } }`. Text comes only from the VO or the real UI;
there are no counters (none of the screenshots has a number that changes on screen).
