import { expect, test } from 'bun:test';
import * as THREE from 'three';
import { isColoured } from './logo';

const c = (hex: string) => new THREE.Color(hex);

test('a logo fill takes the accent by its chroma: saturated fills colour, whites and near-whites stay satin', () => {
  expect(isColoured(c('#ff6a1f'))).toBe(true);
  expect(isColoured(c('#3d7bff'))).toBe(true);
  expect(isColoured(c('#a78bfa'))).toBe(true);
  expect(isColoured(c('#f4ece1'))).toBe(false); // a warm theme's fg: HSL calls it 47% saturated
  expect(isColoured(c('#f2f2f2'))).toBe(false);
  expect(isColoured(c('#000000'))).toBe(false);
});
