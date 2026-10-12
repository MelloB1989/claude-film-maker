// The kit's 3D blocks, one shot each, at 110 BPM: every shot a block configured by params alone (docs/kit/3d.md).
// The voiceover is written here as captions, its times given from each shot's start (at()), so the `sync: 'vo'` shots
// land their words on it and shots can be re-cut without re-timing it.
import { defineFilm } from '@engine/film';
import { Cards3D, GlyphCloud, Hero3D, Logo3D, Panel3D } from '@kit/3d';
import config from './film.json';

/** A bar at 110 BPM (s). The shots in order and their lengths in bars. */
const BAR = 240 / 110;
const LENGTHS = { hero: 2, voice: 2, panels: 3, cloud: 2, cards: 3, logo: 3 } as const;
type Shot = keyof typeof LENGTHS;
const ORDER = Object.keys(LENGTHS) as Shot[];
/** Where a shot starts (film s), plus `dt`. */
const at = (shot: Shot, dt = 0) => ORDER.slice(0, ORDER.indexOf(shot)).reduce((s, k) => s + LENGTHS[k] * BAR, 0) + dt;
const len = (shot: Shot) => ({ bars: LENGTHS[shot] });

export default defineFilm({
  ...config,
  vo: [
    { text: 'Made in code, lit like a studio.', start: at('voice', 0.55), end: at('voice', 2.7) },
    { text: 'Every frame, a pure function of time.', start: at('cloud', 0.5), end: at('cloud', 3.2) },
  ],
  scenes: [
    {
      // extruded type: a word on every beat, slammed in; it blows out at the camera and whips left on the cut
      id: 'hero', scene: Hero3D, length: len('hero'),
      params: { text: 'Launch films,\nbuilt in 3D.', emphasis: ['3D.'], sync: 'beats', reveal: 'slam', exit: 'blow', exitDur: 0.5, whip: 'left' },
    },
    {
      // the same block on the voice: each word tips up as it is said; the camera orbits; the words fall away
      id: 'voice', scene: Hero3D, length: len('voice'), transition: { kind: 'whip', dir: [-1, 0] },
      params: { text: 'Made in code,\nlit like a studio.', emphasis: ['studio.'], emphasisColor: 'accent2', sync: 'vo', reveal: 'tip', exit: 'fall', camera: 'orbit' },
    },
    {
      // two panels as an open book: a terminal types, an editor answers; its key line lit
      id: 'panels', scene: Panel3D, length: len('panels'), transition: 'xfade',
      params: {
        layout: 'pair',
        panels: [
          { kind: 'terminal', title: 'zsh', rows: 8, type: 0.4, lines: [
            { text: '$ bun scripts/render.ts stills', kind: 'cmd' },
            { text: 'rendering 12 frames…', kind: 'out' },
            { text: '✔ out/stills/f_0001.png', kind: 'out' },
            { text: '$ bun test src', kind: 'cmd' },
            { text: '✔ 412 pass  0 fail', kind: 'out' },
          ] },
          { kind: 'editor', title: 'film.ts', lang: 'ts', rows: 8, type: { beat: 4 }, enter: 0.3, lines: [
            { text: 'scenes: [' },
            { text: "  { id: 'hero', scene: Hero3D," },
            { text: "    params: { text: 'Launch.' } }," },
            { text: "  { id: 'logo', scene: Logo3D }," },
            { text: '],' },
          ] },
        ],
        highlight: { panel: 1, line: 1, at: { beat: 9 }, color: 'accent2' },
      },
    },
    {
      // a field of glyphs drifting past; on the downbeat they fly into a number
      id: 'cloud', scene: GlyphCloud, length: len('cloud'), transition: { kind: 'zoom', scale: 2.5 },
      params: { resolve: '60 fps', resolveAt: { beat: 3 }, resolveColor: 'fg', sparkle: 0.04 },
    },
    {
      // a carousel of cards, a step every two beats, the front one in focus
      id: 'cards', scene: Cards3D, length: len('cards'), transition: 'dip',
      params: {
        layout: 'carousel', every: 2,
        cards: [
          { title: 'Type', lines: ['Extruded, bevelled,', 'on the beat.'] },
          { title: 'Panels', lines: ['Terminals and editors', 'typing in.'] },
          { title: 'Glyphs', lines: ['Thousands of them,', 'resolving.'] },
          { title: 'Logo', lines: ['Your mark,', 'in satin and light.'] },
          { title: 'Cards', lines: ['A carousel', 'that keeps time.'] },
        ],
      },
    },
    {
      id: 'logo', scene: Logo3D, length: len('logo'), transition: { kind: 'whip', dir: [0, 1] },
      params: { tagline: 'Launch films, written in code.', reveal: 'spin', exit: 'fade' },
    },
  ],
});
