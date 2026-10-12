// Looks: the grade's neutral values, named look presets (the post parameters a look sets), the order a frame's post
// parameters resolve in, and the letterbox's geometry. Pure TS (types only from post.ts), so bun tests it.
//
// A frame's post parameters, last wins:
//   1. DEFAULT_POST (post.ts: the 'film' look, a neutral grade, no fades or hits);
//   2. the film's look (film.json / FilmSpec `look`, default 'film'): every look key, from LOOKS;
//   3. the film's `post`;
//   4. a shot's own look (ShotSpec `look`): every look key again, so it replaces the film's look on that shot, then the
//      film's `post` once more (the film's own tweaks hold on every shot) and the shot's `post`;
//   5. what the scene's render returns, then each overlay's (engine.ts composite); inside a transition the side the
//      frame is on (A before the cut, B from it), so a look changes on the cut.
// A look sets only look keys (LOOK_KEYS): never a fade, a flash, a shake, a zoom or the HUD.
import { LOOK } from './look';
import type { PostOverrides } from './scene';

/** The grade, neutral: a frame that sets none of these renders exactly as it did before they existed. */
export const NEUTRAL_GRADE = {
  /** 1 as is; 0 grey, above 1 richer (linear light, about luma). */
  saturation: 1,
  /** 1 as is: an S-curve about display mid-grey that keeps black and white (above 1 deeper, below 1 flatter). */
  contrast: 1,
  /** White balance, −1 cool … 0 … 1 warm (red up, blue down, luma kept). */
  warmth: 0,
  /** 0..1: a soft-light wash of `tintColor` over the picture (black and white kept). */
  tint: 0,
  /** The wash's colour: a palette role or #rrggbb. */
  tintColor: 'accent' as string,
  /** 0..~0.15: the black level raised toward the theme's bg2 hue (display units): a faded print. */
  lift: 0,
  /** The picture's aspect ratio between letterbox bars (2.39); 0 off. Bars at most LETTERBOX_MAX of the short side each. */
  letterbox: 0,
  /** 0..1: CRT scanlines, a line every 3 px of a 1080 px short side. */
  scanlines: 0,
};

/** The post keys a look sets: the film look's (look.ts LOOK) and the grade's. */
export type LookValues = typeof LOOK & typeof NEUTRAL_GRADE;
export const LOOK_KEYS = [...Object.keys(LOOK), ...Object.keys(NEUTRAL_GRADE)] as (keyof LookValues)[];

export type LookName = 'film' | 'clean' | 'cinematic' | 'neon' | 'dreamy' | 'gritty' | 'retro';

const FILM: LookValues = { ...LOOK, ...NEUTRAL_GRADE };

/**
 * The presets, each complete over LOOK_KEYS (from 'film', the engine's own look):
 * - film: look.ts LOOK, a neutral grade (the default);
 * - clean: crisp product-video: less bloom and halation, no fringe, a whisper of grain and vignette;
 * - cinematic: 2.39 letterbox, warmer, a deeper vignette and an S-curve, a touch less saturated;
 * - neon: wide hot bloom and halation, richer colour, a faint wash of the accent;
 * - dreamy: wide soft bloom, lifted blacks, a flatter curve, warm and a little desaturated;
 * - gritty: hard contrast, heavy grain, cool and desaturated, a deep vignette;
 * - retro: scanlines, a strong fringe, warm and faded.
 * Only accents glow in every one of them: the bloom's chroma gate (post.ts) is untouched, and fg never blooms.
 */
export const LOOKS: Record<LookName, LookValues> = {
  film: FILM,
  clean: { ...FILM, bloom: 0.45, halation: 0.12, ca: 0, grain: 0.018, vignette: 0.12 },
  cinematic: { ...FILM, letterbox: 2.39, warmth: 0.28, contrast: 1.14, saturation: 0.9, vignette: 0.5, lift: 0.012, grain: 0.05 },
  neon: { ...FILM, bloom: 1.1, bloomRadius: 0.95, halation: 0.6, saturation: 1.22, contrast: 1.06, tint: 0.14, vignette: 0.36 },
  dreamy: { ...FILM, bloom: 0.95, bloomRadius: 1, halation: 0.5, lift: 0.07, contrast: 0.88, saturation: 0.86, warmth: 0.12, vignette: 0.2, grain: 0.03, ca: 0.6 },
  gritty: { ...FILM, contrast: 1.32, saturation: 0.74, warmth: -0.15, grain: 0.11, vignette: 0.55, bloom: 0.5, ca: 0.55 },
  retro: { ...FILM, scanlines: 0.4, ca: 1.6, warmth: 0.45, saturation: 0.82, lift: 0.045, contrast: 1.05, grain: 0.07, vignette: 0.42 },
};

/** A look's values (default 'film'); throws on an unknown name, listing the presets. */
export function lookPost(look?: string): LookValues {
  const v = LOOKS[(look ?? 'film') as LookName];
  if (!v) throw new Error(`unknown look '${look}' (looks: ${Object.keys(LOOKS).join(', ')})`);
  return v;
}

/** Steps 2-3: the film's look with its `post` over it (engine.ts basePost puts it over DEFAULT_POST). */
export function filmLookPost(film: { look?: string; post?: PostOverrides }): PostOverrides {
  return { ...lookPost(film.look), ...(film.post ?? {}) };
}

/**
 * Step 4: a shot's post defaults (film.ts filmTimeline puts them on its timeline entry): its own look, the film's
 * `post` and its `post`; without a look of its own, its `post` alone (the film's look holds).
 */
export function shotLookPost(film: { post?: PostOverrides }, shot: { id: string; look?: string; post?: PostOverrides }): PostOverrides | undefined {
  if (shot.look === undefined) return shot.post;
  let v: LookValues;
  try {
    v = lookPost(shot.look);
  } catch (e) {
    throw new Error(`shot ${shot.id}: ${(e as Error).message}`);
  }
  return { ...v, ...(film.post ?? {}), ...(shot.post ?? {}) };
}

/** The most a letterbox bar covers: 13% of the frame's short side (2.39 in 16:9 is 12.8%). */
export const LETTERBOX_MAX = 0.13;

/**
 * The share of the frame's height each letterbox bar covers for a picture of `aspect` (width / height) in a w x h
 * frame: (h − w / aspect) / 2, at most LETTERBOX_MAX of the short side, so a vertical or square frame takes cinematic
 * bars instead of a slot. 0 for aspect 0 (off) or an aspect the frame already is or is narrower than.
 */
export function letterboxBar(aspect: number, w: number, h: number): number {
  if (!(aspect > 0)) return 0;
  return Math.min(Math.max(0, (h - w / aspect) / 2), LETTERBOX_MAX * Math.min(w, h)) / h;
}

/** The aspect whose bars cover `bar` of the height each (letterboxBar's inverse up to its cap): animate bars with it. */
export function letterboxAspect(bar: number, w: number, h: number): number {
  return w / Math.max(1e-6, h * (1 - 2 * Math.max(0, bar)));
}
