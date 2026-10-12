import { expect, test } from 'bun:test';
import { camAt, cursorAt, project, quad, rise, window, type View } from './geometry';

const v: View = { sx: 960, sy: 540, bw: 1200, bh: 750, fx: 0.5, fy: 0.5, yaw: 0, dist: 2000 };

test('the focus point sits on the anchor, with or without yaw', () => {
  for (const yaw of [0, -0.2, 0.3]) {
    const p = project({ ...v, yaw }, 0.5, 0.5);
    expect(p.x).toBeCloseTo(960);
    expect(p.y).toBeCloseTo(540);
  }
});

test('without yaw the projection is a plain scale and shift', () => {
  const p = project(v, 1, 1);
  expect(p.x).toBeCloseTo(960 + 600);
  expect(p.y).toBeCloseTo(540 + 375);
  expect(p.s).toBeCloseTo(1);
});

test('a yaw makes one side nearer: it grows, the other shrinks', () => {
  const t = { ...v, yaw: (-14 * Math.PI) / 180 };
  const l = project(t, 0, 0.5), r = project(t, 1, 0.5);
  expect(l.s).toBeGreaterThan(1);
  expect(r.s).toBeLessThan(1);
  const q = quad(t, [0, 0, 1, 1]);
  expect(q[3]!.y - q[0]!.y).toBeGreaterThan(q[2]!.y - q[1]!.y);
});

test('the camera eases between keys and holds at the ends', () => {
  const keys = [{ t: 0, x: 0.5, y: 0.5, z: 1 }, { t: 4, x: 0.8, y: 0.2, z: 4 }];
  expect(camAt(keys, -1).z).toBe(1);
  expect(camAt(keys, 9).x).toBe(0.8);
  const m = camAt(keys, 2);
  expect(m.x).toBeCloseTo(0.65);
  expect(m.z).toBeCloseTo(2); // log-space: the geometric mean
});

test('windows ease in and out', () => {
  expect(window(0, 1, 3)).toBe(0);
  expect(window(2, 1, 3)).toBeCloseTo(1);
  expect(window(3, 1, 3)).toBeCloseTo(0);
  expect(window(99, 1, undefined)).toBe(1);
  expect(rise(0.25, 0, 0.5)).toBeCloseTo(0.5);
});

test('the cursor glides between keys and reports click ages', () => {
  const keys = [{ t: 1, at: [0.1, 0.1] as [number, number] }, { t: 3, at: [0.9, 0.9] as [number, number], click: true }];
  expect(cursorAt(keys, 0)).toBeNull();
  expect(cursorAt(keys, 1)!.at).toEqual([0.1, 0.1]);
  expect(cursorAt(keys, 3.25)!.clicks[0]).toBeCloseTo(0.25);
  expect(cursorAt(keys, 2)!.clicks).toEqual([]);
  expect(cursorAt(keys, 9)!.at).toEqual([0.9, 0.9]);
});
