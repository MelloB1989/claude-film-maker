// The kit's 3D blocks, one shot each, at 110 BPM: every shot a block configured by params alone.
import { defineFilm } from '@engine/film';
import { Hero3D } from '@kit/3d';
import config from './film.json';

const BAR = 240 / 110;
const LENGTHS = { hero: 2, vo: 2 } as const;
type Shot = keyof typeof LENGTHS;
const ORDER = Object.keys(LENGTHS) as Shot[];
const at = (shot: Shot, dt = 0) => ORDER.slice(0, ORDER.indexOf(shot)).reduce((s, k) => s + LENGTHS[k] * BAR, 0) + dt;
const len = (shot: Shot) => ({ bars: LENGTHS[shot] });

export default defineFilm({
  ...config,
  vo: [
    { text: 'Made in code, lit like a studio.', start: at('vo', 0.5), end: at('vo', 2.6) },
  ],
  scenes: [
    { id: 'hero', scene: Hero3D, length: len('hero'), params: { text: 'Launch films,\nbuilt in 3D.', emphasis: ['3D.'], sync: 'beats', reveal: 'slam', exit: 'blow', whip: 'left' } },
    { id: 'vo', scene: Hero3D, length: len('vo'), transition: { kind: 'whip', dir: [-1, 0] }, params: { text: 'Made in code,\nlit like a studio.', emphasis: ['studio.'], emphasisColor: 'accent2', sync: 'vo', reveal: 'tip', exit: 'fall', camera: 'orbit' } },
  ],
});
