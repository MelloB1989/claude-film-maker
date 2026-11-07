// WhatsApp explainer graphics: every graphics beat full frame, back to back (the review cut; each shot is also
// rendered alone with --only <id> as <id>_full.mov). The panel versions with alpha are films/explain-whatsapp-panel.
import { defineFilm } from '@engine/film';
import config from './film.json';
import { shots } from './shots';

export default defineFilm({
  ...config,
  post: { grain: 0.02, vignette: 0.22 },
  scenes: shots({ layout: () => 'full' }),
});
