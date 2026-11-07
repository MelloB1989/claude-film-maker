// The Netflix explainer's graphics: one shot per cutaway, timed to the producer's EDL (data/edl.json, copied from
// films/host-studio/explainers/edl/netflix.json on agent-11's branch): each shot runs its EDL frame count plus a 12
// frame tail that holds the end state, and builds on the words of its VO line (words[].f on the shot's clock).
// Matte variants are films of their own (films/explain-netflix-black, -grey: this timeline with `matte` set): no
// studio, the frame cleared to that colour, the pair alpha.py turns into straight-alpha PNGs.
// Panel scenes have a second shot, <id>_panel, laid out in the presenter shot's right panel box.
import { defineFilm } from '@engine/film';
import config from './film.json';
import edl from './data/edl.json';

type Config = typeof config;

const FPS = 24, TAIL = 12;

type Word = { w: string; f: number };
const shot = (gfx: string) => (edl.shots as { gfx?: string; frames: number; words: Word[] }[]).find((s) => s.gfx === gfx)!;

const scenes = {
  title: () => import('./scenes/title'),
  oca: () => import('./scenes/oca'),
  prefill: () => import('./scenes/prefill'),
  ladder: () => import('./scenes/ladder'),
  abr: () => import('./scenes/abr'),
  buffer: () => import('./scenes/buffer'),
  planes: () => import('./scenes/planes'),
  end: () => import('./scenes/endcard'),
};

/** The film, over the studio (matte '') or cleared to black or grey for the alpha passes. */
export function netflixFilm(cfg: Config, MATTE: '' | 'black' | 'grey' = '') {
const BG = MATTE === 'black' ? '#000000' : MATTE === 'grey' ? '#5a5a5a' : 'theme';
const cut = (id: string, gfx: keyof typeof scenes, extra: Record<string, unknown> = {}) => {
  const s = shot(gfx);
  return {
    id, scene: scenes[gfx], length: (s.frames + TAIL) / FPS,
    params: { words: s.words, frames: s.frames, background: BG, matte: MATTE, ...extra },
  };
};

return defineFilm({
  ...cfg,
  post: MATTE ? { grain: 0, vignette: 0, ca: 0 } : { grain: 0.03 },
  scenes: [
    // a 1.5 frame lead: every cut then falls half way between two frames, so a shot owns exactly its frame count
    // (frame 2 is title's first; FRAMES.md lists each shot's frames) whatever the float sum of the lengths
    { id: 'lead', scene: scenes.end, length: 1.5 / FPS, params: { background: BG, matte: MATTE } },
    cut('title', 'title'),
    cut('oca', 'oca'),
    cut('prefill', 'prefill'),
    cut('prefill_panel', 'prefill', { panel: true }),
    cut('ladder', 'ladder'),
    cut('abr', 'abr'),
    cut('buffer', 'buffer'),
    cut('buffer_panel', 'buffer', { panel: true }),
    cut('planes', 'planes'),
    cut('end', 'end'),
    { id: 'lowerthird', scene: () => import('./scenes/lowerthird'), length: 72 / FPS, params: { background: BG, matte: MATTE } },
  ],
});
}

export default netflixFilm(config);
