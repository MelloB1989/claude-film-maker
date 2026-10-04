import { expect, test } from 'bun:test';
import * as THREE from 'three';
import { blendSpace } from './gl';
import { LOOK, bloomKey, compositeSRGB, glow, type RGB } from './look';
import { LIN } from './palette';

/** A Layer2D upload (an sRGB canvas texture), and a render target's colour (linear light, no colour space). */
const layer = () => Object.assign(new THREE.Texture(), { colorSpace: THREE.SRGBColorSpace });
const light = () => new THREE.Texture();

test('a 2D layer mixes normal and multiply in display space, and adds light for add, screen and max', () => {
  expect(blendSpace('normal', layer())).toBe('srgb');
  expect(blendSpace('multiply', layer())).toBe('srgb');
  for (const mode of ['add', 'screen', 'max'] as const) expect(blendSpace(mode, layer())).toBe('linear');
});

test('render targets always mix light, a space the caller passes wins, and replace never mixes', () => {
  for (const mode of ['normal', 'add', 'screen', 'multiply', 'max', 'replace'] as const) expect(blendSpace(mode, light())).toBe('linear');
  expect(blendSpace('add', layer(), 'srgb')).toBe('srgb');
  expect(blendSpace('normal', layer(), 'linear')).toBe('linear');
  expect(blendSpace('replace', layer(), 'srgb')).toBe('linear');
});

test('why: a soft glow texel tinted glow() reaches the bloom added as light, and not mixed as display values', () => {
  // a white texel at alpha 0.5 over ink, tinted glow('blood'): its light is tint x 0.5 over the ink
  const tint = glow('blood'), a = 0.5;
  const asLight = LIN.ink.map((d, i) => d + tint[i]! * a) as RGB;
  const asDisplay = compositeSRGB('add', [...LIN.ink, 1], [1, 1, 1, a], { tint }).slice(0, 3) as RGB;
  expect(bloomKey(asLight, LOOK.bloomThreshold, LOOK.bloomKnee)).toBeGreaterThan(0.15);
  expect(bloomKey(asDisplay, LOOK.bloomThreshold, LOOK.bloomKnee)).toBe(0);
});
