// The film's look: the post-processing defaults every scene starts from (DEFAULT_POST takes them), and pure mirrors
// of the two pieces of GPU math that decide how a frame reads: the bloom prefilter's soft threshold (post.ts) and the
// display-space "over" that 2D layers composite with (gl.ts, Compositor). Pure TS, so bun can test them.
import type { PostOverrides } from './scene';

export type RGB = [number, number, number];

/** Linear light -> sRGB-encoded display value (IEC 61966-2-1), extended above 1 for HDR. Mirrors GLSL toSRGB. */
export const linearToSrgb = (x: number) => (x < 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055);
/** sRGB-encoded display value -> linear light. Mirrors GLSL toLinear. */
export const srgbToLinear = (x: number) => (x < 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4));

/**
 * The bloom prefilter's key (post.ts): the colour's brightest channel, after the prefilter's clamp at 40. Not Rec.709
 * luma: on luma, blood driven to 3x its palette value (0.41) would still sit below plain bone (0.81), and no threshold
 * could let blood glow while bone stays crisp.
 */
export const bloomLum = (c: RGB) => Math.max(Math.min(c[0], 40), Math.min(c[1], 40), Math.min(c[2], 40));

/**
 * The fraction of a pixel's light the prefilter passes to the bloom (post.ts, mirrored exactly): zero up to
 * threshold - knee, a quadratic soft knee, then 1 - threshold / lum. Monotonic and <= 1 when threshold >= knee.
 */
export function bloomWeight(lum: number, threshold: number, knee: number): number {
  const q = Math.min(Math.max(lum - threshold + knee, 0), 2 * knee);
  const rq = (q * q) / (4 * knee + 1e-5);
  return Math.max(rq, lum - threshold) / Math.max(lum, 1e-5);
}

/** A linear colour scaled so the bloom key reads `level`, hue kept: how a scene drives blood or moss into glow. */
export function glow(c: RGB, level: number): RGB {
  const m = Math.max(c[0], c[1], c[2], 1e-9);
  return [(c[0] * level) / m, (c[1] * level) / m, (c[2] * level) / m];
}

/**
 * Display-space "over", as design tools, browsers and Canvas2D blend: `src` (sRGB-encoded, straight) at alpha `a` over
 * `dst` (linear, may be HDR), mixed as display values, returned as linear light. The Compositor's 'srgb' space runs
 * the same math on the GPU. 28% bone over ink shows as 28% of the way from ink to bone, not the 53% grey that mixing
 * linear light gives.
 */
export function blendSRGB(dst: RGB, src: RGB, a: number): RGB {
  const mix = (d: number, s: number) => srgbToLinear(a * s + (1 - a) * linearToSrgb(Math.max(d, 0)));
  return [mix(dst[0], src[0]), mix(dst[1], src[1]), mix(dst[2], src[2])];
}

/**
 * The film look; DEFAULT_POST takes these. Set 2026-10-01 by rendering the four Plan 1 cards and an HDR look-test frame
 * (bone type beside blood and moss glyphs, threads and a glow ladder from 1.0 to 6.0; Plan 2 Task 2 report):
 * - bloomThreshold 1.25, bloomKnee 0.25: bloom opens at 1.0, display white, so nothing a 2D layer or an unlit palette
 *   colour holds can bloom. Bone (key 0.847) weighs 0 where Plan 1's 0.85/0.5 gave it 0.146, the most of any colour.
 *   Accents glow only when a scene drives them past white (`glow`): 17% of their light at 1.5, 38% at 2, 58% at 3.
 *   The knee lets a brightening glow come in without a pop.
 * - bloom 0.6: a soft crimson aura around a level-3 hero word that stays off the bone beside it.
 * - halation 0.35: a faint warm haze, a few levels deep, around blood (post.ts drives it by the glow's red).
 * - ca 0.38: R and B shift 0.6 px at the left/right frame edges (1.58·ca); Plan 1's 1.2 fringed the titles by ~1.6 px.
 * - grain 0.045, vignette 0.28: texture and falloff that are felt rather than seen. Exposure and radius unchanged.
 * Glow cores keep their hue up to about level 1.5 (blood) and 1.25 (moss); above that the per-channel tone shoulder
 * takes them toward pink and mint.
 */
export const LOOK = {
  exposure: 1,
  bloom: 0.6,
  bloomThreshold: 1.25,
  bloomKnee: 0.25,
  bloomRadius: 0.75,
  halation: 0.35,
  ca: 0.38,
  grain: 0.045,
  vignette: 0.28,
} satisfies PostOverrides;
