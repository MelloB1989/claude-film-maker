// The Netflix explainer's graphics: one shot per cutaway, timed to the producer's EDL (data/edl.json, copied from
// films/host-studio/explainers/edl/netflix.json on agent-11's branch): each shot runs its EDL frame count plus a 12
// frame tail that holds the end state, and builds on the words of its VO line (words[].f on the shot's clock).
// Variants, set by the environment of the render (tools: films/explain-netflix/render.sh):
//   VITE_NF_MATTE=black|grey  no studio, the frame cleared to that colour (alpha.py makes straight-alpha PNGs from the pair)
// Panel scenes have a second shot, <id>_panel, laid out in the presenter shot's right panel box.
import { defineFilm } from '@engine/film';
import config from './film.json';
import edl from './data/edl.json';

const FPS = 24, TAIL = 12;
const MATTE = (import.meta.env.VITE_NF_MATTE as string | undefined) ?? '';
const BG = MATTE === 'black' ? '#000000' : MATTE === 'grey' ? '#5a5a5a' : 'theme';

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

const cut = (id: string, gfx: keyof typeof scenes, extra: Record<string, unknown> = {}) => {
  const s = shot(gfx);
  return {
    id, scene: scenes[gfx], length: (s.frames + TAIL) / FPS,
    params: { words: s.words, frames: s.frames, background: BG, matte: MATTE, ...extra },
  };
};

export default defineFilm({
  ...config,
  post: MATTE ? { grain: 0, vignette: 0, ca: 0 } : { grain: 0.03 },
  scenes: [
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
