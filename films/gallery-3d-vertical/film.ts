// The 3D blocks in a vertical (1080x1920) frame: the same params as the landscape gallery frame for a phone. Headlines
// wrap to the narrow measure, a pair of panels stacks, the glyph field and the logo fit the width.
import { defineFilm } from '@engine/film';
import { GlyphCloud, Hero3D, Logo3D, Panel3D } from '@kit/3d';
import config from './film.json';

export default defineFilm({
  ...config,
  scenes: [
    { id: 'hero', scene: Hero3D, length: { bars: 2 }, params: { text: 'Launch films, built in 3D.', emphasis: ['3D.'], sync: 'beats', reveal: 'rise', exit: 'fall' } },
    {
      id: 'panels', scene: Panel3D, length: { bars: 2 }, transition: 'xfade',
      params: {
        layout: 'pair',
        panels: [
          { kind: 'terminal', title: 'zsh', w: 900, rows: 4, type: 0.3, lines: [{ text: '$ bun test src', kind: 'cmd' }, { text: '✔ 412 pass  0 fail', kind: 'out' }] },
          { kind: 'editor', title: 'film.ts', w: 900, lang: 'ts', rows: 4, type: { beat: 3 }, lines: [{ text: "scene: Hero3D," }, { text: "params: { text: 'Hi.' }," }] },
        ],
        highlight: { panel: 1, line: 0, at: { beat: 6 } },
      },
    },
    { id: 'cloud', scene: GlyphCloud, length: { bars: 2 }, transition: { kind: 'zoom', scale: 2.5 }, params: { resolve: '1080', resolveAt: { beat: 3 } } },
    { id: 'logo', scene: Logo3D, length: { bars: 2 }, transition: 'dip', params: { tagline: 'Launch films, written in code.' } },
  ],
});
