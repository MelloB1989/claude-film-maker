// The film's format and where its files are: the logical canvas scenes lay out in (W x H), the output scale, the frame
// rate, and the film's folder. Every value is a live binding: configure() sets them before the engine builds anything
// (main.ts, from the film's film.json), and code reads them when it runs, never at import. Defaults are the landscape
// 1920x1080 at 30 fps, which tests and tools that never configure get.
import { SCALE } from './scale';

export { SCALE };

/** Named formats (logical px). Every size is even, so H.264's 4:2:0 chroma takes it at any scale. */
export const FORMATS = {
  landscape: { width: 1920, height: 1080 },
  vertical: { width: 1080, height: 1920 },
  square: { width: 1080, height: 1080 },
  portrait: { width: 1080, height: 1350 },
  cinema: { width: 1920, height: 804 },
} as const;
export type FormatName = keyof typeof FORMATS;
/** A format's name or its size; a name is checked when it is resolved (film.json gives any string). */
export type FormatSpec = FormatName | (string & {}) | { width: number; height: number };

/** Logical canvas: scenes lay out in these px at every output scale. */
export let W = 1920;
export let H = 1080;
/** Physical (output) size: the logical canvas times SCALE. */
export let PW = W * SCALE;
export let PH = H * SCALE;
/** Frames per second of the film (the frame grid every per-frame state snaps to). */
export let FPS = 30;
/** The film's id and the URL of its folder (relative to the page, ends in /). */
export let FILM_ID = 'showcase';
export let FILM_BASE = 'films/showcase/';

/** A format spec resolved to logical px; throws on an unknown name or a size that is not even and positive. */
export function resolveFormat(f: FormatSpec = 'landscape'): { width: number; height: number } {
  const s = typeof f === 'string' ? (FORMATS as Record<string, { width: number; height: number }>)[f] : f;
  if (!s) throw new Error(`unknown format '${f}' (formats: ${Object.keys(FORMATS).join(', ')}, or { width, height })`);
  const { width, height } = s;
  for (const [k, v] of [['width', width], ['height', height]] as const) {
    if (!Number.isInteger(v) || v < 16 || v % 2) throw new Error(`format ${k} must be an even whole number of px (>= 16), got ${v}`);
  }
  return { width, height };
}

/** Set the format, the frame rate and the film. Call before anything is built (main.ts, scripts, tests). */
export function configure(o: { format?: FormatSpec; fps?: number; film?: string; base?: string }) {
  if (o.format !== undefined) {
    const { width, height } = resolveFormat(o.format);
    W = width;
    H = height;
    PW = W * SCALE;
    PH = H * SCALE;
  }
  if (o.fps !== undefined) {
    if (!(o.fps > 0 && o.fps <= 240)) throw new Error(`fps must be in (0, 240], got ${o.fps}`);
    FPS = o.fps;
  }
  if (o.film !== undefined) {
    FILM_ID = o.film;
    FILM_BASE = o.base ?? `films/${o.film}/`;
  }
}

/** A file of the film's folder, as a URL relative to the page: filmUrl('data/vo.json') → films/<id>/data/vo.json. */
export const filmUrl = (rel: string) => (/^([a-z]+:|\/)/i.test(rel) ? rel : FILM_BASE + rel.replace(/^\.\//, ''));
/** A file of the film's render output (out/<id>/...), served by the dev server: outUrl('plates/x/0001.exr'). */
export const outUrl = (rel: string) => `out/${FILM_ID}/${rel.replace(/^\.\//, '')}`;
/** The frame's aspect, width over height. */
export const aspect = () => W / H;
