import { expect, test } from 'bun:test';
import { LIN } from './palette';
import { DEFAULT_POST } from './post';
import {
  BLOOM_CHROMA, LOOK, bloomKey, bloomLum, bloomWeight, blendSRGB, compositeSRGB, glow, linearToSrgb, srgbToLinear,
  type DisplayBlend, type RGB, type RGBA,
} from './look';

// Expected values are hand-derived (Python, from the sRGB formula and the shader text), never from look.ts.
const T = DEFAULT_POST.bloomThreshold, K = DEFAULT_POST.bloomKnee;
const levels = (c: RGB) => c.map((x) => linearToSrgb(x) * 255);
const BONE_SRGB: RGB = [237 / 255, 231 / 255, 234 / 255]; // #ede7ea as designed
/** Input helper: a colour lit so its brightest channel reads `level` (bone under a key light, a specular). */
const lit = (c: RGB, level: number): RGB => c.map((x) => (x * level) / Math.max(...c)) as RGB;

test('the sRGB transfer matches IEC 61966-2-1 both ways', () => {
  expect(srgbToLinear(0.5)).toBeCloseTo(0.214041, 6);
  expect(srgbToLinear(237 / 255)).toBeCloseTo(0.846873, 6);
  expect(srgbToLinear(0.02)).toBeCloseTo(0.02 / 12.92, 9); // the linear toe
  expect(linearToSrgb(0.5)).toBeCloseTo(0.735357, 6);
  expect(linearToSrgb(0.001)).toBeCloseTo(0.01292, 9);
});

test('bloomLum is the prefilter key: the brightest channel (clamped at 40), not luma', () => {
  expect(bloomLum([0.2, 0.7, 0.1])).toBe(0.7);
  expect(bloomLum(LIN.bone)).toBeCloseTo(0.846873, 6);
  expect(bloomLum([100, 2, 3])).toBe(40);
});

test('bloomWeight mirrors the shader: Plan 1 settings give bone 0.146, blood 0.033, moss 0.0055', () => {
  expect(bloomWeight(bloomLum(LIN.bone), 0.85, 0.5)).toBeCloseTo(0.14576, 5);
  expect(bloomWeight(bloomLum(LIN.blood), 0.85, 0.5)).toBeCloseTo(0.033275, 6);
  expect(bloomWeight(bloomLum(LIN.moss), 0.85, 0.5)).toBeCloseTo(0.0055139, 7);
});

test('bloomWeight: zero below the knee, quadratic in it, 1 - threshold/lum above it', () => {
  expect(bloomWeight(0.5, 1, 0.5)).toBe(0);
  expect(bloomWeight(0, 1, 0.5)).toBe(0);
  expect(bloomWeight(1, 1, 0.5)).toBeCloseTo(0.1249994, 7); // (0.5^2 / (2 + 1e-5)) / 1
  expect(bloomWeight(3, 1, 0.1)).toBeCloseTo(2 / 3, 9);
});

test('the film look never blooms bone, nor anything up to display white', () => {
  expect(bloomWeight(bloomLum(LIN.bone), T, K)).toBe(0);
  expect(bloomWeight(bloomLum([1, 1, 1]), T, K)).toBe(0);
});

test('glow() drives a blood or moss accent to a bloom-key level, hue kept', () => {
  expect(glow('blood', 3)[0]).toBeCloseTo(3, 9);
  expect(glow('blood', 3)[2]).toBeCloseTo(0.330937, 6);
  expect(glow('moss', 1.5)[1]).toBeCloseTo(1.5, 9);
});

test('blood and moss at the glow level pass at least half their light to the bloom', () => {
  for (const key of ['blood', 'bloodBright', 'moss'] as const) expect(bloomKey(glow(key), T, K)).toBeGreaterThanOrEqual(0.5);
});

test('blood and moss, dim or bright, pass the chroma gate whole', () => {
  for (const key of ['blood', 'bloodBright', 'bloodDim', 'moss', 'mossDim'] as const)
    expect(bloomKey(glow(key, 4), 1, 0.1)).toBeCloseTo(0.75, 9); // the plain weight at 4: (4 - 1) / 4
});

test('a dim accent at the glow level still glows', () => {
  expect(bloomKey(glow('bloodDim'), T, K)).toBeGreaterThan(0);
  expect(bloomKey(glow('mossDim'), T, K)).toBeGreaterThan(0);
});

test('bone never blooms, lit or specular, at any intensity', () => {
  for (const level of [1, 2, 4, 40]) expect(bloomKey(lit(LIN.bone, level), T, K)).toBe(0);
  expect(bloomKey([3, 2.94, 2.97], T, K)).toBe(0); // a desaturated specular white at 3.0
});

test('the chroma gate: grey light passes nothing, pure colour the whole weight, a quarter up the gate 0.156 of it', () => {
  expect(bloomKey([4, 4, 4], 1, 0.1)).toBe(0);
  expect(bloomKey([4, 0, 0], 1, 0.1)).toBeCloseTo(0.75, 9); // chroma 1: the plain weight, (4 - 1) / 4
  const [lo, hi] = BLOOM_CHROMA, chroma = lo + 0.25 * (hi - lo), g = 4 * (1 - chroma); // (max - min) / max = chroma
  expect(bloomKey([4, g, g], 1, 0.1)).toBeCloseTo(0.75 * 0.15625, 9); // smoothstep at a quarter: 0.25^2 * 2.5
});

test('bloomWeight is monotonic in lum and never passes more than all the light', () => {
  for (const [t, k] of [[T, K], [0.85, 0.5], [1, 0.1]] as const) {
    let prev = 0;
    for (let l = 0; l <= 40; l += 0.005) {
      const w = bloomWeight(l, t, k);
      expect(w).toBeGreaterThanOrEqual(prev);
      expect(w).toBeLessThanOrEqual(1);
      prev = w;
    }
  }
});

test('blendSRGB: 28% bone over black shows 28% of bone as designed, not the 52% linear light gives', () => {
  const out = levels(blendSRGB([0, 0, 0], BONE_SRGB, 0.28));
  [66.36, 64.68, 65.52].forEach((want, i) => expect(Math.abs(out[i]! - want)).toBeLessThanOrEqual(1));
});

test('blendSRGB: 28% bone over ink mixes the display values', () => {
  const out = levels(blendSRGB(LIN.ink, BONE_SRGB, 0.28));
  [78.6, 74.04, 77.04].forEach((want, i) => expect(Math.abs(out[i]! - want)).toBeLessThanOrEqual(1));
});

test('blendSRGB keeps the destination at alpha 0 and shows the source at alpha 1', () => {
  blendSRGB(LIN.ink, BONE_SRGB, 0).forEach((x, i) => expect(x).toBeCloseTo(LIN.ink[i]!, 9));
  blendSRGB(LIN.ink, BONE_SRGB, 1).forEach((x, i) => expect(x).toBeCloseTo(LIN.bone[i]!, 9));
});

test('the engine renders with the film look', () => {
  expect(DEFAULT_POST).toMatchObject(LOOK);
});

// ---- the Compositor's display-space draw (gl.ts srgbFrag), every mode

const MODES: DisplayBlend[] = ['normal', 'add', 'screen', 'multiply', 'max'];
const rgb3 = <T>(f: (i: number) => T) => [f(0), f(1), f(2)];

/**
 * The Compositor's fixed-function blend, written out from the blend factors gl.ts get() sets per mode: `src` is the
 * pass's output (premultiplied), `dst` the target.
 */
function fixedBlend(mode: DisplayBlend, src: RGBA, dst: RGBA): RGBA {
  const c = (f: (s: number, d: number) => number) => rgb3((i) => f(src[i]!, dst[i]!));
  switch (mode) {
    case 'normal': return [...c((s, d) => s + d * (1 - src[3])), src[3] + dst[3] * (1 - src[3])] as RGBA; // One, OneMinusSrcAlpha
    case 'add': return [...c((s, d) => s + d), dst[3]] as RGBA; // One, One; alpha Zero, One
    case 'screen': return [...c((s, d) => s + d * (1 - s)), dst[3]] as RGBA; // One, OneMinusSrcColor; alpha Zero, One
    case 'multiply': return [...c((s, d) => s * d + d * (1 - src[3])), dst[3]] as RGBA; // DstColor, OneMinusSrcAlpha
    case 'max': return [...c((s, d) => Math.max(s, d)), Math.max(src[3], dst[3])] as RGBA; // MaxEquation, alpha too
  }
}

test('compositeSRGB: each mode is its fixed-function blend run on display values, then decoded to light', () => {
  const vals = [0, 0.002, 0.05, 0.3, 0.8, 1];
  for (const mode of MODES) for (const d of vals) for (const c of vals) for (const a of [0.1, 0.5, 1]) for (const opacity of [0.4, 1]) {
    const dst: RGBA = [d, 0.5 * d, 0.2, 0.7], tex: RGBA = [c, 1 - c, 0.5, a];
    const pm = mode !== 'multiply' ? a : 1; // the default premult: all but multiply
    const src = [...rgb3((i) => linearToSrgb(tex[i]!) * pm * opacity), a * opacity] as RGBA;
    const want = fixedBlend(mode, src, [...rgb3((i) => linearToSrgb(dst[i]!)), dst[3]] as RGBA);
    const got = compositeSRGB(mode, dst, tex, { opacity });
    rgb3((i) => expect(got[i]!).toBeCloseTo(srgbToLinear(want[i]!), 9));
    expect(got[3]).toBeCloseTo(want[3], 12);
  }
});

test('compositeSRGB: a glow() layer added in display space, the reviewer\'s numbers', () => {
  // a white texel at alpha 0.5, tinted glow('blood') (3, 0.134, 0.331), over ink: the display-space add lands the red
  // at 0.735, under the bloom's opening at 1.0; added as light it is 1.506 (Python, from the shader text)
  const out = compositeSRGB('add', [...LIN.ink, 1], [1, 1, 1, 0.5], { tint: glow('blood') });
  [0.7348317, 0.0516909, 0.1115310].forEach((want, i) => expect(out[i]!).toBeCloseTo(want, 6));
  expect(out[3]).toBe(1);
  // nothing drawn (alpha 0, no light): the target keeps its exact value
  const dst: RGBA = [0.3, 2, 40, 0.5];
  expect(compositeSRGB('normal', dst, [0.7, 0.7, 0.7, 0], {})).toBe(dst);
});

test('compositeSRGB never goes below 0, nor to NaN: HDR cores under it, opacity above 1, hot tints', () => {
  // two that did: `normal` at opacity 1.5 leaves the target at 1 - 1.5 of itself, and a screen of a level-3 tint over a
  // specular core at 12 is s + D(1 - s) = 1.61 + 2.92 * (1 - 1.61) = -0.17 in display values (Python); both decoded to NaN
  expect(compositeSRGB('normal', [1, 1, 1, 1], [0, 0, 0, 1], { opacity: 1.5 })[0]).toBe(0);
  expect(compositeSRGB('screen', [12, 12, 12, 1], [1, 1, 1, 1], { tint: glow('blood') })[0]).toBe(0);
  const tints: RGB[] = [[1, 1, 1], glow('blood'), glow('moss', 6)];
  for (const mode of MODES) for (const d of [0, 0.05, 1, 4, 12, 40]) for (const c of [0, 0.2, 1]) for (const a of [0, 0.3, 1])
    for (const opacity of [0.5, 1, 1.5, 3]) for (const tint of tints) {
      for (const x of compositeSRGB(mode, [d, 0.5 * d, d, 1], [c, c, 1 - c, a], { opacity, tint })) {
        expect(Number.isNaN(x)).toBe(false);
        expect(x).toBeGreaterThanOrEqual(0);
      }
    }
});
