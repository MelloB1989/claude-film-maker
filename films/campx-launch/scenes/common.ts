// Shared by the lead's scenes: image loading, the brand gradient, the spoken words of a scene, word reveals.
import { filmUrl } from '@engine/config';
import { HEX } from '@engine/palette';
import { wordTimes } from '@engine/motion';
import type { VO, Word } from '@engine/vo';
import { ease, prog } from '@engine/util';

export async function loadImg(rel: string): Promise<HTMLImageElement> {
  const img = new Image();
  img.decoding = 'async';
  img.src = filmUrl(rel);
  await img.decode();
  return img;
}

/** Free an image's decode. */
export const dropImg = (i: HTMLImageElement | null) => {
  if (i) i.src = '';
};

/**
 * The brand gradient as light: indigo → magenta → coral. The indigo end is the theme's deepest accent tint
 * (accentDim), then accent, then accent2Bright.
 */
export function brandGradient(c: CanvasRenderingContext2D, x0: number, x1: number, bright = true): CanvasGradient {
  const g = c.createLinearGradient(x0, 0, x1, 0);
  g.addColorStop(0, bright ? HEX.accentBright : HEX.accentDim);
  g.addColorStop(0.5, bright ? HEX.accent : HEX.accent);
  g.addColorStop(1, HEX.accent2Bright);
  return g;
}

/** The spoken words of a shot, [] without a voiceover (or when it has no such scene): scenes fall back to fixed times. */
export function spoken(vo: VO, id: string): { w: Word; at: number }[] {
  try {
    return wordTimes(vo, id);
  } catch {
    return [];
  }
}

/** Time of the first spoken word of `id` equal to `word` (case, punctuation and curly quotes ignored), else `fallback`. */
export function wordAt(words: { w: Word; at: number }[], word: string, fallback: number, from = 0): number {
  const norm = (x: string) => x.toLowerCase().replace(/[’‘]/g, "'").replace(/[^\p{L}\p{N}']/gu, '');
  const p = norm(word);
  for (let i = from; i < words.length; i++) if (norm(words[i]!.w.w) === p) return words[i]!.at;
  return fallback;
}

/** 0..1 for a word that arrives at `at` (s of film time), over `dur`: a soft focus-pull in. */
export const arrive = (t: number, at: number, dur = 0.8) => ease.outCubic(prog(t, at, at + dur));

/** A free-standing offscreen canvas at the film's logical size. */
export function offscreen(w: number, h: number): HTMLCanvasElement {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return c;
}

export const freeCanvas = (c: HTMLCanvasElement | null) => {
  if (c) c.width = c.height = 0;
};
