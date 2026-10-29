import { expect, test } from 'bun:test';
import { W, H } from '../../engine/config';
import { FX_KINDS, stateAt, transitionEntries } from '../../engine/transition';
import { cameraAt, drift } from './parallax';
import { lightningAt, rainClock } from './rain';
import { trackAt } from './postkeys';
import { cueAlpha } from './subtitles';

test('rainClock: no keys is the shot clock; slowing to a stop integrates the falling rate, then holds', () => {
  expect(rainClock(2.5)).toEqual({ clock: 2.5, rate: 1 });
  // from rate 1 at the shot's start to 0 at 1 s: the clock gains half a second over that second, then stops
  const k: [number, number][] = [[1, 0]];
  expect(rainClock(0.5, k).clock).toBeCloseTo(0.375, 9);
  expect(rainClock(0.5, k).rate).toBeCloseTo(0.5, 9);
  expect(rainClock(1, k).clock).toBeCloseTo(0.5, 9);
  expect(rainClock(3, k).clock).toBeCloseTo(0.5, 9);
  expect(rainClock(3, k).rate).toBe(0);
  // keys that start later: rate 1 until the first, then the ramp
  const k2: [number, number][] = [[3, 0], [2, 1]];
  expect(rainClock(2, k2).clock).toBeCloseTo(2, 9);
  expect(rainClock(3, k2).clock).toBeCloseTo(2.5, 9);
  // a rain that starts frozen and comes back: never runs backwards
  const k3: [number, number][] = [[0, 0], [1.4, 1]];
  let prev = -Infinity;
  for (let t = 0; t <= 3; t += 0.05) {
    const c = rainClock(t, k3).clock;
    expect(c).toBeGreaterThanOrEqual(prev);
    prev = c;
  }
});

test('lightningAt: a bright flicker, a second one after it, nothing outside', () => {
  expect(lightningAt(1, [])).toBe(0);
  expect(lightningAt(0.9, [1])).toBe(0);
  expect(lightningAt(1, [1])).toBeGreaterThan(1);
  expect(lightningAt(1.12, [1])).toBeGreaterThan(lightningAt(1.1, [1]));
  expect(lightningAt(1.7, [1])).toBe(0);
});

test('trackAt: eased between keys, held outside them, stepped when asked', () => {
  const k: [number, number][] = [[0, 0], [1, 10]];
  expect(trackAt(k, -1)).toBe(0);
  expect(trackAt(k, 2)).toBe(10);
  expect(trackAt(k, 0.5)).toBeCloseTo(5, 9);
  expect(trackAt(k, 0.25)).toBeLessThan(2.5); // inOutSine eases in
  expect(trackAt({ keys: k, ease: 'linear' }, 0.25)).toBeCloseTo(2.5, 9);
  const strobe = { keys: [[0, 1], [0.2, 0], [0.3, 1]] as [number, number][], step: true };
  expect(trackAt(strobe, 0.1)).toBe(1);
  expect(trackAt(strobe, 0.25)).toBe(0);
  expect(trackAt(strobe, 0.35)).toBe(1);
  // keys out of order are sorted
  expect(trackAt([[1, 10], [0, 0]], 0.5)).toBeCloseTo(5, 9);
});

test('cueAlpha: a subtitle fades in from its start and out after its end', () => {
  const c = { start: 1, end: 2, text: 'x' };
  expect(cueAlpha(c, 0.99, 0.1)).toBe(0);
  expect(cueAlpha(c, 1.05, 0.1)).toBeCloseTo(0.5, 9);
  expect(cueAlpha(c, 1.5, 0.1)).toBe(1);
  expect(cueAlpha(c, 2.05, 0.1)).toBeCloseTo(0.5, 9);
  expect(cueAlpha(c, 2.1, 0.1)).toBe(0);
});

test('cameraAt: pans in px of the frame, pushes geometrically, rolls in radians, holds outside its `at`', () => {
  const m = { from: { x: 0, zoom: 1 }, to: { x: 0.1, y: -0.05, zoom: 4, roll: 90 }, ease: 'linear' as const };
  expect(cameraAt(m, 0)).toEqual({ px: 0, py: 0, zoom: 1, roll: 0 });
  const b = cameraAt(m, 1);
  expect(b.px).toBeCloseTo(0.1 * W, 9);
  expect(b.py).toBeCloseTo(-0.05 * H, 9);
  expect(b.roll).toBeCloseTo(Math.PI / 2, 9);
  expect(cameraAt(m, 0.5).zoom).toBeCloseTo(2, 9); // the geometric middle of 1 and 4
  const late = { ...m, at: [0.5, 1] as [number, number] };
  expect(cameraAt(late, 0.25)).toEqual(cameraAt(late, 0));
  expect(cameraAt(undefined, 0.7)).toEqual({ px: 0, py: 0, zoom: 1, roll: 0 });
  // the handheld drift stays within -1..1 and is a pure function of time
  for (let t = 0; t < 20; t += 0.37) for (const v of drift(t, 3)) expect(Math.abs(v)).toBeLessThanOrEqual(1);
  expect(drift(4.2, 3)).toEqual(drift(4.2, 3));
});

test('ink transition: an effects kind whose blots open from all A to all B; its params are checked', () => {
  expect(FX_KINDS).toContain('ink');
  const spans = [{ id: 'a', act: '', start: 0, end: 2 }, { id: 'b', act: '', start: 2, end: 4 }];
  const [e] = transitionEntries([{ from: 'a', to: 'b', kind: 'ink', pre: 0.4, post: 0.4 }], spans, []);
  const at = (t: number) => stateAt(e!, t);
  expect(at(e!.start).wB).toBe(0);
  expect(at(e!.start).edge).toBe(0);
  expect(at(e!.end - 1e-6).edge).toBeCloseTo(1, 4);
  let prev = -1;
  for (let t = e!.start; t < e!.end; t += 0.02) {
    const k = at(t).edge!;
    expect(k).toBeGreaterThanOrEqual(prev);
    prev = k;
  }
  expect(() => transitionEntries([{ from: 'a', to: 'b', kind: 'ink', pre: 0.4, post: 0.4, scale: 0 }], spans, [])).toThrow(/scale/);
  expect(() => transitionEntries([{ from: 'a', to: 'b', kind: 'ink', pre: 0.4, post: 0.4, color: 'pink' }], spans, [])).toThrow(/color/);
  expect(() => transitionEntries([{ from: 'a', to: 'b', kind: 'ink', pre: 0.4, post: 0.4, color: '#101012' }], spans, [])).not.toThrow();
});
