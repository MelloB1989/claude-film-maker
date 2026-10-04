// The film's look: the post-processing defaults every scene starts from (DEFAULT_POST takes them), glow() for
// emissive accents, and pure mirrors of the two pieces of GPU math that decide how a frame reads: the bloom
// prefilter's key, a soft threshold gated by chroma (post.ts), and the display-space draws that 2D layers composite
// with (gl.ts, Compositor). Pure TS, so bun can test them.
import type { PostOverrides } from './scene';
import { LIN, type PaletteKey } from './palette';
import { smoothstep } from './util';

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

/**
 * The prefilter's chroma gate (post.ts): its weight is scaled by smoothstep(lo, hi, chroma), chroma being
 * (max - min) / max of the linear colour. Chroma doesn't change with intensity, so neutral light never blooms however
 * bright: bone (0.056), a specular white (~0.02), bone under a warm 4000 K key (0.27). A warmer key on bone opens the
 * gate: 3500 K reads about 0.37. Blood (0.96), bloodDim (0.95), moss (0.84) and mossDim (0.67) pass whole.
 */
export const BLOOM_CHROMA: readonly [number, number] = [0.3, 0.6];

/** Chroma as the prefilter sees it: (max - min) / max of the colour after its clamp at 40. */
export function bloomChroma(c: RGB): number {
  const r = Math.min(c[0], 40), g = Math.min(c[1], 40), b = Math.min(c[2], 40);
  const hi = Math.max(r, g, b);
  return (hi - Math.min(r, g, b)) / Math.max(hi, 1e-5);
}

/**
 * The fraction of a colour's light that reaches the bloom (post.ts, mirrored exactly): the soft threshold, gated by
 * chroma.
 */
export function bloomKey(c: RGB, threshold: number, knee: number): number {
  return bloomWeight(bloomLum(c), threshold, knee) * smoothstep(BLOOM_CHROMA[0], BLOOM_CHROMA[1], bloomChroma(c));
}

/** The palette colours that may glow: blood and moss, and their dim and bright shades. Bone never does. */
export type GlowKey = Extract<PaletteKey, 'blood' | 'bloodBright' | 'bloodDim' | 'moss' | 'mossDim'>;
/** The film's emissive level: a soft glow whose core stays blood or moss. Hot cores (about 4 and up) whiten. */
export const GLOW_LEVEL = 3;

/**
 * An emissive accent: the palette colour scaled so the bloom key reads `level`, hue kept. Use glow('blood'|'moss') for
 * any emissive accent (a material's emissive, a 2D glow layer's tint); it is the one way scenes set emissive levels.
 * A glow layer is drawn 'add' (or 'screen', 'max'), which the Compositor mixes as light (gl.ts blendSpace), so its
 * halo blooms at these levels.
 */
export function glow(key: GlowKey, level = GLOW_LEVEL): RGB {
  const c = LIN[key], m = Math.max(c[0], c[1], c[2]);
  return [(c[0] * level) / m, (c[1] * level) / m, (c[2] * level) / m];
}

/**
 * Display-space "over", as design tools, browsers and Canvas2D blend: `src` (sRGB-encoded, straight) at alpha `a` over
 * `dst` (linear, may be HDR), mixed as display values, returned as linear light. The Compositor's 'srgb' space runs
 * the same math on the GPU. 28% bone over ink shows as 28% of the way from ink to bone, not the 53% grey that mixing
 * linear light gives. (compositeSRGB is the whole display-space draw, every mode.)
 */
export function blendSRGB(dst: RGB, src: RGB, a: number): RGB {
  const mix = (d: number, s: number) => srgbToLinear(a * s + (1 - a) * linearToSrgb(Math.max(d, 0)));
  return [mix(dst[0], src[0]), mix(dst[1], src[1]), mix(dst[2], src[2])];
}

/** A texel or a target's pixel: linear colour and alpha. */
export type RGBA = [number, number, number, number];
/** The modes the Compositor can mix in display space (gl.ts BlendMode, all but 'replace'). */
export type DisplayBlend = 'normal' | 'add' | 'screen' | 'multiply' | 'max';

// GLSL's toSRGB and toLinear (glsl/common.ts) as the GPU runs them, NaN included: mix() weighs both sides of the step,
// so toLinear of a value below -0.055 takes pow of a negative base, and the NaN survives the zero weight.
// (linearToSrgb and srgbToLinear pick one side and never make a NaN.)
const step = (edge: number, x: number) => (x < edge ? 0 : 1);
const mixGL = (a: number, b: number, s: number) => a * (1 - s) + b * s;
const toSRGB = (c: number) => mixGL(12.92 * c, 1.055 * Math.pow(Math.max(c, 0), 1 / 2.4) - 0.055, step(0.0031308, c));
const toLinear = (c: number) => mixGL(c / 12.92, Math.pow((c + 0.055) / 1.055, 2.4), step(0.04045, c));

/**
 * The Compositor's display-space draw (gl.ts, its srgbFrag), mirrored exactly: texel `tex` (its colour as sampled, so
 * linear, and straight alpha) drawn with `mode`, `opacity`, `tint` and `premult` (default: all but 'multiply') over a
 * target pixel `dst` (linear light, may be HDR). The layer is encoded to display values and the target to how it would
 * show, the mode's fixed-function equation (the Compositor's linear path, gl.ts get()) runs on them, and the result is
 * decoded back to light, from no lower than 0: a display value below 0 (`normal` at opacity above 1, a screen of a hot
 * tint over a hot target) would decode to NaN. Returns the pixel's new colour and alpha; `dst` itself where the texel
 * draws nothing.
 */
export function compositeSRGB(mode: DisplayBlend, dst: RGBA, tex: RGBA, o: { opacity?: number; tint?: RGB; premult?: boolean } = {}): RGBA {
  const opacity = o.opacity ?? 1, tint = o.tint ?? [1, 1, 1], premult = o.premult ?? mode !== 'multiply';
  const s = [0, 1, 2].map((i) => toSRGB(Math.max(tex[i]! * tint[i]!, 0)) * (premult ? tex[3] : 1) * opacity);
  const a = tex[3] * opacity;
  if (a <= 0 && s.every((x) => x === 0)) return dst; // the shader discards: the target keeps its exact value
  const D = [0, 1, 2].map((i) => toSRGB(Math.max(dst[i]!, 0)));
  const eq = (s: number, d: number) =>
    mode === 'normal' ? s + d * (1 - a)
      : mode === 'add' ? s + d
        : mode === 'screen' ? s + d * (1 - s)
          : mode === 'multiply' ? s * d + d * (1 - a)
            : Math.max(s, d);
  const oa = mode === 'normal' ? a + dst[3] * (1 - a) : mode === 'max' ? Math.max(a, dst[3]) : dst[3];
  const out = (i: number) => toLinear(Math.max(eq(s[i]!, D[i]!), 0));
  return [out(0), out(1), out(2), oa];
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
 * Fix round 1 (the controller's ruling) made two changes and left the values above as they were:
 * - The chroma gate (BLOOM_CHROMA 0.3..0.6) keeps bone, white light and speculars out of the bloom at any intensity.
 *   Bone lit to 2, 4 or 40, a specular white at 3 and bone under a 4000 K key add nothing. Blood and moss pass whole.
 * - The tone shoulder (post.ts) keeps a glow's hue. At level 3 a core stays blood (255, 62, 96) or moss
 *   (113, 255, 148), not pink or mint. Only hot cores whiten, from about 4 on the brightest channel after bloom.
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
