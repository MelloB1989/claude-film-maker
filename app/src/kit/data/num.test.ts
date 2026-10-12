import { expect, test } from 'bun:test';
import { columnsOf, countAt, decimalsOf, drumAt, drumFace, flapColumn, formatNumber } from './num';

test('decimalsOf and formatNumber', () => {
  expect(decimalsOf(91.4)).toBe(1);
  expect(decimalsOf(1200)).toBe(0);
  expect(decimalsOf(0.125)).toBe(3);
  expect(formatNumber(1284000)).toBe('1,284,000');
  expect(formatNumber(91.4, 1)).toBe('91.4');
  expect(formatNumber(1234.5, 2, ' ', ',')).toBe('1 234,50');
  expect(formatNumber(-12, 0)).toBe('−12');
  expect(formatNumber(1234, 0, '')).toBe('1234');
});

test('countAt: from before it starts, eased up, exactly the value from its landing on', () => {
  expect(countAt(0, 44, 91.4, 2, 1)).toBe(44);
  const mid = countAt(1.5, 44, 91.4, 2, 1);
  expect(mid).toBeGreaterThan(44);
  expect(mid).toBeLessThan(91.4);
  expect(countAt(2, 44, 91.4, 2, 1)).toBe(91.4);
  expect(countAt(9, 44, 91.4, 2, 1)).toBe(91.4);
  // monotonic
  let prev = -Infinity;
  for (let t = 0; t <= 2.2; t += 0.01) {
    const v = countAt(t, 0, 100, 2, 1.4, 'outCubic');
    expect(v).toBeGreaterThanOrEqual(prev);
    prev = v;
  }
});

test('columnsOf: digits with their places, marks between', () => {
  const c = columnsOf('$1,28.5%');
  expect(c.map((x) => (x.kind === 'digit' ? x.d : x.ch))).toEqual(['$', 1, ',', 2, 8, '.', 5, '%']);
  expect(c.filter((x) => x.kind === 'digit').map((x) => (x as { place: number }).place)).toEqual([0, 1, 2, 3]);
});

test('drumAt: each drum lands on its digit, the last exactly on the landing time, the rightmost spinning most', () => {
  const land = 3, n = 3;
  for (let i = 0; i < n; i++) {
    const d = [9, 1, 4][i]!;
    expect(drumFace(drumAt(land + 1, d, i, n, land)).a).toBe(d);
    expect(Math.abs(drumAt(land + 1, d, i, n, land) - Math.round(drumAt(land + 1, d, i, n, land)))).toBeLessThan(1e-6);
  }
  expect(drumFace(drumAt(land, 4, 2, n, land)).a).toBe(4); // the last lands exactly on `land`
  expect(drumAt(0, 4, 2, n, land)).toBe(0); // before it starts: at its first face
  // travel grows to the right
  expect(drumAt(9, 0, 2, n, land)).toBeGreaterThan(drumAt(9, 0, 0, n, land));
});

test('drumFace: the digit showing, the next, the roll between', () => {
  expect(drumFace(12.25)).toEqual({ a: 2, b: 3, f: 0.25 });
  expect(drumFace(9.5)).toEqual({ a: 9, b: 0, f: 0.5 });
});

test('flapColumn: from before, seeded digits between (never the from or to), the target after; deterministic', () => {
  const land = 2;
  expect(flapColumn(0, '0', '7', 0, 2, land)).toEqual({ a: '0', b: '0', p: 0 });
  expect(flapColumn(land + 0.01, '0', '7', 1, 2, land)).toEqual({ a: '7', b: '7', p: 0 });
  const mid = flapColumn(land - 0.2, '0', '7', 1, 2, land, { seed: 3 });
  expect(mid).toEqual(flapColumn(land - 0.2, '0', '7', 1, 2, land, { seed: 3 }));
  for (let t = land - 1; t < land; t += 0.013) {
    const s = flapColumn(t, '0', '7', 1, 2, land, { steps: 6, step: 0.075 });
    expect(s.p).toBeGreaterThanOrEqual(0);
    expect(s.p).toBeLessThanOrEqual(1);
    if (s.a !== '0' && s.a !== '7') expect(['0', '7']).not.toContain(s.a);
  }
});
