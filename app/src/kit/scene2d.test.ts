import { afterEach, expect, test } from 'bun:test';
import { configure } from '../engine/config';
import { glow, srgbToLinear } from '../engine/look';
import { LIN, setTheme } from '../engine/palette';
import { glowInk, isTall, refUnit, safeRect } from './scene2d';

afterEach(() => {
  configure({ format: 'landscape' });
  setTheme('noir');
});

const parse = (css: string) => css.match(/[\d.]+/g)!.map(Number) as [number, number, number, number];

test('glowInk: the role at full strength, so the glow layer added at level L adds exactly glow(role, L)', () => {
  for (const theme of ['noir', 'midnight', 'aurora', 'ember', 'paper']) {
    setTheme(theme);
    for (const key of ['accent', 'accent2'] as const) {
      const [r, g, b, a] = parse(glowInk(key));
      expect(a).toBe(1);
      expect(Math.max(r, g, b)).toBe(255);
      const lin = [r, g, b].map((x) => srgbToLinear(x / 255));
      const want = glow(key, 1);
      for (let i = 0; i < 3; i++) expect(Math.abs(lin[i]! - want[i]!)).toBeLessThan(0.02);
      // the hue is the role's
      const c = LIN[key], m = Math.max(...c);
      for (let i = 0; i < 3; i++) expect(Math.abs(lin[i]! - c[i]! / m)).toBeLessThan(0.02);
    }
  }
  expect(parse(glowInk('accent', 0.4))[3]).toBe(0.4);
});

test('safeRect and refUnit follow the format', () => {
  configure({ format: 'landscape' });
  expect(isTall()).toBe(false);
  expect(refUnit()).toBe(1);
  const t = safeRect('title');
  expect([t.x0, t.y0, t.x1, t.y1]).toEqual([96, 54, 1824, 1026]);
  const a = safeRect('action');
  expect(a.w).toBeCloseTo(0.93 * 1920, 6);
  // a landscape frame has no feed UI: social is title-safe
  expect(safeRect('social')).toEqual(t);
  configure({ format: 'vertical' });
  expect(isTall()).toBe(true);
  expect(refUnit()).toBe(1);
  const s = safeRect('social');
  expect(s.y1).toBeLessThan(0.8 * 1920); // clear of the caption and buttons
  expect(s.x1).toBeLessThan(0.9 * 1080); // clear of the button column
  configure({ format: { width: 3840, height: 2160 } });
  expect(refUnit()).toBe(2);
});
