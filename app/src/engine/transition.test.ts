import { describe, expect, test } from 'bun:test';
import { MAX_TAPS, matchWeight, shutterTaps, sideTime, stateAt, tapCount, transitionEntries, type TransitionSpec } from './transition';
import { firstUse, framePlan, lastUse, shutterOffsets, shutterPlan } from './engine';

const scenes = [{ id: 'a', act: 'I', start: 0, end: 4.008 }, { id: 'b', act: 'I', start: 4.008, end: 8.008 }, { id: 'c', act: 'I', start: 8.008, end: 12 }];
const whip: TransitionSpec = { from: 'a', to: 'b', kind: 'whip', pre: 0.1, post: 0.1, dir: [1, 0] };
const [W] = transitionEntries([whip], scenes, []);
const tl = scenes.map((s) => ({ ...s }));

describe('validation', () => {
  test('a word spoken inside the window fails, naming the pair and the word time', () =>
    expect(() => transitionEntries([whip], scenes, [{ start: 4.05 }])).toThrow(/a-b.*4\.05/));
  test('non-adjacent pairs, long sides and a cut with a window fail', () => {
    expect(() => transitionEntries([{ ...whip, to: 'c' }], scenes, [])).toThrow(/adjacent/);
    expect(() => transitionEntries([{ ...whip, pre: 0.6 }], scenes, [])).toThrow(/0\.5/);
    expect(() => transitionEntries([{ ...whip, kind: 'cut' }], scenes, [])).toThrow(/cut/);
  });
  test('the error names the word, its onset and the window', () =>
    expect(() => transitionEntries([whip], scenes, [{ start: 4.1, w: 'Change' }])).toThrow('transition a-b: word "Change" (4.1) starts inside [3.908, 4.141)'));
  test('a word one frame past the window, or before it, passes; the window is [cut − pre, cut + post + 1/30)', () => {
    expect(() => transitionEntries([whip], scenes, [{ start: 3.9 }, { start: 4.142 }])).not.toThrow();
    expect(() => transitionEntries([whip], scenes, [{ start: 3.908 }])).toThrow(/a-b/);
  });
  test('a side longer than a quarter of its scene fails', () => {
    const short = [{ id: 'a', act: 'I', start: 0, end: 1 }, { id: 'b', act: 'I', start: 1, end: 3 }];
    expect(() => transitionEntries([{ ...whip, pre: 0.3 }], short, [])).toThrow(/a-b.*25%/);
    expect(() => transitionEntries([{ ...whip, pre: 0.25, post: 0.5 }], short, [])).not.toThrow();
  });
  test('a pair given twice and negative sides fail (the 25% rule leaves no two windows room to overlap)', () => {
    expect(() => transitionEntries([whip, { ...whip, kind: 'xfade' }], scenes, [])).toThrow(/a-b.*once/);
    expect(() => transitionEntries([{ ...whip, post: -0.1 }], scenes, [])).toThrow(/a-b/);
  });
  test('a cut has no window, and is listed', () => {
    const [c] = transitionEntries([{ from: 'a', to: 'b', kind: 'cut', pre: 0, post: 0 }], scenes, [{ start: 4.01 }]);
    expect(c).toEqual({ id: 'a-b', spec: expect.anything(), cut: 4.008, start: 4.008, end: 4.008 });
  });
});

describe('side times (Review Focus 4)', () => {
  test('hold clamps into the window; run clamps to the handles', () => {
    expect(sideTime('hold', 4.05, scenes[0]!, { head: 0, tail: 0 })).toEqual({ time: 4.008 - 1e-6, held: true });
    expect(sideTime('hold', 3.95, scenes[1]!, { head: 0, tail: 0 })).toEqual({ time: 4.008, held: true });
    const r = sideTime('run', 4.05, scenes[0]!, { head: 0, tail: 0.02 });
    expect(r.held).toBe(true); expect(r.time).toBeCloseTo(4.028, 5);   // clamped just inside end + tail
    expect(sideTime('run', 4.02, scenes[0]!, { head: 0, tail: 0.02 })).toEqual({ time: 4.02, held: false });
  });
  test('a plate scene in a transition is never asked for a time outside its window', () => {
    const offs = shutterOffsets({ min: 4, max: 324, tol: 3 });
    for (let n = 118; n < 125; n++) for (const sub of framePlan(tl, [W!], n / 30, 1 / 30, 0.5, offs))
      for (const l of sub) if (l.kind === 'transition') {
        expect(l.a.time).toBeLessThan(4.008); expect(l.b.time).toBeGreaterThanOrEqual(4.008);
      }
  });
  test("a 'run' side runs into its handles and no further", () => {
    const run = transitionEntries([{ ...whip, fromMode: 'run', toMode: 'run' }], scenes, []);
    const h = (id: string) => (id === 'a' ? { head: 0, tail: 0.05 } : { head: 0.03, tail: 0 });
    for (let n = 118; n < 125; n++) for (const sub of framePlan(tl, run, n / 30, 1 / 30, 0.5, shutterOffsets(36), h))
      for (const l of sub) if (l.kind === 'transition') {
        expect(l.a.time).toBeLessThan(4.058); expect(l.b.time).toBeGreaterThanOrEqual(4.008 - 0.03 - 1e-12);
      }
    // the frame at the cut: a runs on past its end, b has started early
    const [sub] = framePlan(tl, run, 4.0, 1 / 30, 0.5, [0.4], h);
    const l = sub![0]!;
    if (l.kind !== 'transition') throw new Error('expected a transition layer');
    expect(l.a).toEqual({ entry: tl[0], time: expect.closeTo(4 + 0.4 / 60, 12), held: false });
    expect(l.b).toEqual({ entry: tl[1], time: expect.closeTo(4 + 0.4 / 60, 12), held: false });
  });
});

describe('frame plan', () => {
  test('outside every transition it is shutterPlan, as scene layers', () => {
    const offs = shutterOffsets(12);
    const p = framePlan(tl, [W!], 2, 1 / 30, 0.5, offs), q = shutterPlan(tl, 2, 1 / 30, 0.5, offs);
    expect(p.map((s) => s.map((l) => l.kind === 'scene' && l.at))).toEqual(q.map((s) => s.map((x) => x)));
  });
  test('inside a transition the pair is one layer, and overlays come last', () => {
    const ov = { id: 'ov', act: '', start: 0, end: 12, kind: 'overlay' as const };
    const [sub] = framePlan([...tl, ov], [W!], 4.0, 1 / 30, 0.5, [0]);
    expect(sub!.map((l) => l.kind)).toEqual(['transition', 'overlay']);
  });
  test('overlays come after the scenes in start order, at their own times, outside transitions too', () => {
    const o1 = { id: 'o1', act: '', start: 1, end: 12, kind: 'overlay' as const }, o2 = { id: 'o2', act: '', start: 0, end: 12, kind: 'overlay' as const };
    const [sub] = framePlan([o1, ...tl, o2], [W!], 2, 1 / 30, 0.5, [0.25]);
    expect(sub!.map((l) => (l.kind === 'transition' ? 'tr' : `${l.kind} ${l.at.entry.id} ${l.at.time.toFixed(5)}`))).toEqual([
      `scene a ${(2 + 0.25 / 60).toFixed(5)}`, `overlay o2 ${(2 + 0.25 / 60).toFixed(5)}`, `overlay o1 ${(2 + 0.25 / 60).toFixed(5)}`,
    ]);
  });
  test('a scene lives until the end of its outgoing transition', () => expect(lastUse(tl[0]!, [W!])).toBeCloseTo(4.108, 9));
  test('and from the start of its incoming one', () => {
    expect(firstUse(tl[1]!, [W!])).toBeCloseTo(3.908, 9);
    expect(firstUse(tl[0]!, [W!])).toBe(0);
    expect(lastUse(tl[1]!, [W!])).toBe(8.008);
  });
});

describe('motion over the shutter', () => {
  test('taps are centred on t and span dt·shutter', () => {
    const s = shutterTaps(W!, 4.008, 1 / 30, 0.5, 9).map((x) => x.a.tx);
    expect((s[0]! + s[8]!) / 2).toBeCloseTo(stateAt(W!, 4.008).a.tx, 0);
  });
  test('the whip streak at the cut needs more taps at 4K, capped', () => {
    const k1 = tapCount(W!, 4.008, 1 / 30, 0.5, 1), k2 = tapCount(W!, 4.008, 1 / 30, 0.5, 2);
    expect(k2).toBeGreaterThan(k1); expect(k2).toBeLessThanOrEqual(MAX_TAPS);
    expect(tapCount(W!, 2, 1 / 30, 0.5, 1)).toBe(1);   // outside the window: no streak
  });
  test('A and B meet half way at the cut, and abut', () => {
    const s = stateAt(W!, 4.008);
    expect(s.a.tx).toBeCloseTo(-960, 0); expect(s.b.tx).toBeCloseTo(960, 0);
  });
  test('match: B shows first where A is brightest', () => {
    expect(matchWeight(0.7, 0.9, 0.12)).toBeGreaterThan(matchWeight(0.7, 0.3, 0.12));
    expect(matchWeight(1, 0.99, 0.12)).toBeLessThan(0.5);
  });
});

describe('kinds', () => {
  const entry = (spec: Partial<TransitionSpec>) => transitionEntries([{ ...whip, ...spec } as TransitionSpec], scenes, [])[0]!;
  test('whip: the pictures always abut, A leaving and B arriving, still at both ends of the window', () => {
    for (let t = 3.9; t <= 4.12; t += 0.01) {
      const s = stateAt(W!, t);
      expect(s.b.tx - s.a.tx).toBeCloseTo(1920, 6);
      expect(s.a.ty).toBe(0); expect(s.match).toBe(-1); expect(s.ink).toBe(0);
    }
    expect(stateAt(W!, 3.908).a.tx).toBeCloseTo(0, 9);
    expect(stateAt(W!, 4.108).b.tx).toBeCloseTo(0, 9);
    // the camera moves up: the picture moves down, B arrives from above
    const up = stateAt(entry({ dir: [0, -1] }), 4.008);
    expect(up.a.ty).toBeCloseTo(540, 6); expect(up.b.ty).toBeCloseTo(-540, 6);
  });
  test('zoom: A pushes in to `scale` before the cut, B settles from `bFrom` after it, the side by the frame time', () => {
    const z = entry({ kind: 'zoom', center: [700, 300], dir: undefined });
    expect(stateAt(z, 3.908).a.s).toBeCloseTo(1, 9);
    expect(stateAt(z, 4.008 - 1e-9).a.s).toBeCloseTo(5, 3);
    expect(stateAt(z, 4.008).b.s).toBeCloseTo(1.6, 6);
    expect(stateAt(z, 4.108).b.s).toBeCloseTo(1, 9);
    expect(stateAt(z, 4.0).wB).toBe(0); expect(stateAt(z, 4.008).wB).toBe(1);
    expect(stateAt(z, 4.0).a).toMatchObject({ cx: 700, cy: 300, tx: 0, ty: 0 });
    // every tap of a frame before the cut is A's, past the cut too (A held at `scale`)
    const taps = shutterTaps(z, 4.0, 1 / 30, 0.5, 8);
    expect(taps.every((x) => x.wB === 0)).toBe(true);
    expect(taps[7]!.a.s).toBeCloseTo(5, 6);
    expect(tapCount(z, 4.0, 1 / 30, 0.5, 1)).toBeGreaterThan(10); // a radial streak
  });
  test('match: the threshold runs 1 → 0.5 at the cut → 0', () => {
    const m = entry({ kind: 'match', dir: undefined });
    expect(stateAt(m, 3.908).match).toBeCloseTo(1, 9);
    expect(stateAt(m, 4.008).match).toBeCloseTo(0.5, 9);
    expect(stateAt(m, 4.108).match).toBeCloseTo(0, 9);
    expect(matchWeight(0.5, 0.5, 0.12)).toBeCloseTo(0.5, 9);
  });
  test('xfade: B weighs in with inOutCubic', () => {
    const x = entry({ kind: 'xfade', dir: undefined });
    expect(stateAt(x, 3.908).wB).toBeCloseTo(0, 9);
    expect(stateAt(x, 4.008).wB).toBeCloseTo(0.5, 9);
    expect(stateAt(x, 3.958).wB).toBeCloseTo(4 * 0.25 ** 3, 9);
  });
  test('dip: A goes to ink before the cut, B comes from it after; never both', () => {
    const d = entry({ kind: 'dip', dir: undefined });
    for (let t = 3.9; t <= 4.12; t += 0.004) {
      const s = stateAt(d, t);
      expect(s.wB === 0 || s.wB === 1).toBe(true);
      expect(s.wB).toBe(t >= 4.008 ? 1 : 0);
    }
    expect(stateAt(d, 4.008 - 1e-9).ink).toBeCloseTo(1, 6);
    expect(stateAt(d, 4.008).ink).toBeCloseTo(1, 9);
    expect(stateAt(d, 4.108).ink).toBeCloseTo(0, 9);
    const hard = entry({ kind: 'dip', post: 0, dir: undefined });
    expect(stateAt(hard, 4.008).ink).toBe(0);
    expect(shutterTaps(hard, 3.99, 1 / 30, 0.5, 4).every((s) => s.wB === 0)).toBe(true);
  });
});
