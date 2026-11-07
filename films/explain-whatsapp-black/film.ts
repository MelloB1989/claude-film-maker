// The caption-band gate's pass (gfx.caption_band_clear, agent-09): every beat full frame, then the panel beats in their
// card, all over black with params.matte (no studio, grain or vignette: the graphic alone). tools/bandcheck.ts reads it.
import { defineFilm } from '@engine/film';
import config from './film.json';
import { LEAD, shots } from '../explain-whatsapp/shots';

const black = { background: '#000000', matte: true };
export default defineFilm({
  ...config,
  post: { grain: 0, vignette: 0, ca: 0 },
  scenes: [
    { ...LEAD, params: { ...LEAD.params, ...black } },
    ...shots({ layout: () => 'full', params: black }),
    ...shots({ layout: () => 'panel', only: (k) => k === 'panel', suffix: '_panel', params: black }),
  ],
});
