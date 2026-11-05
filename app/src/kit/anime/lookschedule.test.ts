import { expect, test } from 'bun:test';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { GRADE, gradeAt, gradeKeys, warmAt, type LookSchedule } from './lookschedule';
import { trackAt } from './postkeys';

const S: LookSchedule = {
  arc: { cold: { grade: { saturation: 0.8, warmth: -0.1 } }, warm: { grade: { saturation: 1, warmth: 0.3 } } },
  base: { grade: { vignette: 0.2 } },
  shots: { a: {}, b: { warm: 1, grade: { contrast: 1.3 } }, c: { warm: [[0, 0], [2, 1]] }, d: { grade: { exposure: [[0, 1], [1, 0.5]] } } },
};

test('a shot blends the arc by its warmth, over the base and the defaults, under its own grade', () => {
  expect(gradeAt(S, 'a', 'saturation', 0)).toBeCloseTo(0.8, 9);
  expect(gradeAt(S, 'b', 'warmth', 0)).toBeCloseTo(0.3, 9);
  expect(gradeAt(S, 'b', 'contrast', 0)).toBe(1.3);
  expect(gradeAt(S, 'a', 'vignette', 0)).toBe(0.2);
  expect(gradeAt(S, 'a', 'bloom', 0)).toBe(GRADE.bloom);
  expect(gradeAt(S, 'nobody', 'saturation', 0)).toBeCloseTo(0.8, 9); // an unnamed shot: the cold end
  expect(warmAt(S, 'c', 1)).toBeCloseTo(0.5, 9);
  expect(gradeAt(S, 'c', 'saturation', 1)).toBeCloseTo(0.9, 9);
});

test('gradeKeys: one key for a constant, the shot\'s own keys as they are, a key a frame while the warmth moves', () => {
  const a = gradeKeys(S, 'a', 10, 12, 24);
  expect(a.saturation).toEqual([[0, 0.8]]);
  expect(gradeKeys(S, 'd', 0, 2, 24).exposure).toEqual([[0, 1], [1, 0.5]]);
  const c = gradeKeys(S, 'c', 41.8, 43.8, 24);
  expect(c.saturation.length).toBe(48);
  expect(c.saturation[0]![0]).toBeCloseTo(1004 / 24 - 41.8, 9); // the window's first frame, from the shot's start
  for (const [t, v] of c.saturation) expect(trackAt(c.saturation, t)).toBeCloseTo(v, 9);
  expect(c.vignette).toEqual([[0, 0.2]]); // the arc does not move it
});

// the same numbers the Python reader gives (blender/tests/test_look_schedule.py reads this file too)
test('the rain ferry\'s schedule grades as blender/lib/look_schedule.py does', () => {
  const p = path.resolve(import.meta.dir, '../../../../films/rain-ferry/data/look.json');
  if (!existsSync(p)) return;
  const s = JSON.parse(readFileSync(p, 'utf8')) as LookSchedule;
  expect(gradeAt(s, 'board', 'saturation', 2.75)).toBeCloseTo(0.868, 9);
  expect(gradeAt(s, 'freeze', 'saturation', 0.6)).toBeCloseTo(0.57, 9);
  expect(gradeAt(s, 'cross', 'warmth', 1)).toBeCloseTo(0.3, 9);
  expect(gradeAt(s, 'open', 'contrast', 0)).toBeCloseTo(1.1, 9);
  expect(gradeAt(s, 'title', 'bloom', 0)).toBeCloseTo(0.2, 9);
  expect(gradeAt(s, 'light', 'bloom', 1)).toBeCloseTo(0.475, 9);
});
