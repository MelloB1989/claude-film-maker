// The panel beats laid out in the right-hand panel box, each twice: over black (<id>_k) and over mid grey (<id>_g).
// tools/matte.py pulls straight colour and alpha from the pair (display-space "over": the engine composites a 2D layer
// the way Canvas2D blends), so grain, vignette and fringe are off here: they would differ between the two passes.
import { defineFilm } from '@engine/film';
import config from './film.json';
import { shots } from '../explain-whatsapp/shots';

const panel = (k: string) => k === 'panel';
export default defineFilm({
  ...config,
  post: { grain: 0, vignette: 0, ca: 0 },
  scenes: [
    ...shots({ layout: () => 'panel', only: panel, suffix: '_k', params: { background: '#000000' } }),
    ...shots({ layout: () => 'panel', only: panel, suffix: '_g', params: { background: '#808080' } }),
  ],
});
