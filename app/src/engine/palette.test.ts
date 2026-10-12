import { expect, test } from 'bun:test';
import { HEX, LIN, rgba } from './palette';

test('the palette starts as the default theme (noir): its roles, and no stray keys', () => {
  expect(HEX.bg).toBe('#110d10');
  expect(HEX.accent).toBe('#c22b45');
  expect(HEX.accent2).toBe('#4aad63');
  expect(Object.keys(HEX)).not.toContain("signal");
});

test('linear conversion and CSS colours', () => {
  const [r, g, b] = LIN.accent;
  expect(r).toBeCloseTo(0.5395, 3);
  expect(g).toBeCloseTo(0.0242, 3);
  expect(b).toBeCloseTo(0.0595, 3);
  expect(rgba('accent2', 0.5)).toBe('rgba(74,173,99,0.5)');
});
