import { expect, test } from 'bun:test';
import { HEX, LIN, rgba } from './palette';

test('GitLoom tokens replace the P(doom) palette', () => {
  expect(HEX.ink).toBe('#110d10');
  expect(HEX.blood).toBe('#c22b45');
  expect(HEX.moss).toBe('#4aad63');
  expect(Object.keys(HEX)).not.toContain("signal");
});

test('linear conversion and CSS colours', () => {
  const [r, g, b] = LIN.blood;
  expect(r).toBeCloseTo(0.5395, 3);
  expect(g).toBeCloseTo(0.0242, 3);
  expect(b).toBeCloseTo(0.0595, 3);
  expect(rgba('moss', 0.5)).toBe('rgba(74,173,99,0.5)');
});
