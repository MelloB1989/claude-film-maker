import { expect, test } from 'bun:test';
import { LIN } from './palette';
import { DEFAULT_POST } from './post';
import { LOOK, bloomLum, bloomWeight, blendSRGB, glow, linearToSrgb, srgbToLinear, type RGB } from './look';

// Expected values are hand-derived (Python, from the sRGB formula and the shader text), never from look.ts.
const T = DEFAULT_POST.bloomThreshold, K = DEFAULT_POST.bloomKnee;
const levels = (c: RGB) => c.map((x) => linearToSrgb(x) * 255);
const BONE_SRGB: RGB = [237 / 255, 231 / 255, 234 / 255]; // #ede7ea as designed

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

test('blood and moss driven to 3.0 pass at least half their light to the bloom', () => {
  expect(glow(LIN.blood, 3)[0]).toBeCloseTo(3, 9);
  expect(glow(LIN.blood, 3)[2]).toBeCloseTo(0.330937, 6); // the hue is kept
  expect(glow(LIN.moss, 3)[1]).toBeCloseTo(3, 9);
  for (const c of [LIN.blood, LIN.bloodBright, LIN.moss]) expect(bloomWeight(bloomLum(glow(c, 3)), T, K)).toBeGreaterThanOrEqual(0.5);
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
