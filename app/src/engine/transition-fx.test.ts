// The effects kinds (wipe, iris, slide, spin, flash, glitch): validation, first and last frames, symmetry about the cut
// and the motion-blur tap budget. (transition.test.ts covers the original kinds, unchanged.)
import { describe, expect, test } from 'bun:test';
import {
  MAX_FX_TAPS, MAX_TAPS, edgeWeight, irisTrack, maxTaps, pairSeed, shutterTaps, stateAt, tapCount, transitionEntries, unitDir, wipeTrack,
  type TransitionKind, type TransitionSpec,
} from './transition';
import { transitionCues } from '../sfx/transitions';

const scenes = [{ id: 'a', act: 'I', start: 0, end: 4 }, { id: 'b', act: 'I', start: 4, end: 8 }];
const entry = (spec: Partial<TransitionSpec>, pre = 0.25, post = 0.25) =>
  transitionEntries([{ from: 'a', to: 'b', kind: 'wipe', pre, post, ...spec } as TransitionSpec], scenes, [])[0]!;
const FX: TransitionKind[] = ['wipe', 'iris', 'slide', 'spin', 'flash', 'glitch'];
/** Points across the frame (corners, edges, middle). */
const PTS: [number, number][] = [];
for (let x = 0; x <= 1920; x += 240) for (let y = 0; y <= 1080; y += 135) PTS.push([x, y]);

describe('validation names the pair and the rule', () => {
  test('dir: a unit vector or an angle (whip takes an angle now too)', () => {
    expect(unitDir(90, 0)).toEqual([0, 1]);
    expect(unitDir(180, 0)).toEqual([-1, 0]);
    expect(unitDir([0.6, 0.8], 0)).toEqual([0.6, 0.8]);
    expect(unitDir([1, 1], 0)).toBeNull();
    expect(() => entry({ kind: 'wipe', dir: [1, 1] })).toThrow(/a-b.*unit vector or an angle/);
    expect(() => entry({ kind: 'slide', dir: [2, 0] })).toThrow(/a-b.*slide/);
    expect(() => entry({ kind: 'whip', dir: 270 })).not.toThrow();
    expect(() => entry({ kind: 'whip' })).toThrow(/a-b.*whip needs `dir`/);
  });
  test('wipe and iris: soft is px, 0 or more; edge is an accent or null', () => {
    expect(() => entry({ kind: 'wipe', soft: -1 })).toThrow(/a-b.*soft/);
    expect(() => entry({ kind: 'iris', edge: 'fg' as never })).toThrow(/a-b.*edge.*only accents glow/);
    expect(() => entry({ kind: 'iris', edge: null, soft: 0 })).not.toThrow();
    expect(() => entry({ kind: 'iris', center: [1, NaN] })).toThrow(/a-b.*center/);
  });
  test('spin, flash and glitch', () => {
    expect(() => entry({ kind: 'spin', angle: 0 })).toThrow(/a-b.*angle/);
    expect(() => entry({ kind: 'spin', scale: 0 })).toThrow(/a-b.*scale/);
    expect(() => entry({ kind: 'flash', color: 'pink' })).toThrow(/a-b.*palette role or #rrggbb/);
    expect(() => entry({ kind: 'flash', color: '#ffeedd' })).not.toThrow();
    expect(() => entry({ kind: 'flash', color: 'accent2' })).not.toThrow();
    expect(() => entry({ kind: 'glitch', amount: 0 })).toThrow(/a-b.*amount/);
  });
  test('the window rules hold for them as for every kind', () => {
    expect(() => entry({ kind: 'iris' }, 0.6)).toThrow(/a-b.*0\.5/);
    expect(() => entry({ kind: 'glitch' }, 0, 0)).toThrow(/a-b.*needs a window/);
  });
});

describe('first frame all A, last frame all B', () => {
  test('wipe and iris: B weighs 0 everywhere at the start and 1 everywhere at the end, any dir, any centre', () => {
    for (const spec of [{ kind: 'wipe' }, { kind: 'wipe', dir: 135 }, { kind: 'wipe', dir: [0, -1] }, { kind: 'iris' }, { kind: 'iris', center: [100, 900], soft: 0 }] as Partial<TransitionSpec>[]) {
      const e = entry(spec);
      const s0 = stateAt(e, e.start), s1 = stateAt(e, e.end);
      for (const p of PTS) {
        expect(edgeWeight(e, s0, p)).toBe(0);
        expect(edgeWeight(e, s1, p)).toBe(1);
      }
      expect(s0.light).toBe(0); expect(s1.light).toBe(0);
    }
  });
  test('slide: B starts off frame and lands at rest; A starts untouched', () => {
    for (const dir of [undefined, 0, 90, [0, -1]] as TransitionSpec['dir'][]) {
      const e = entry({ kind: 'slide', dir }), s0 = stateAt(e, e.start), s1 = stateAt(e, e.end);
      expect(s0.a).toMatchObject({ tx: 0, ty: 0, s: 1 }); expect(s0.dim).toBe(0); expect(s0.shadow).toBe(0);
      // B's placement keeps it wholly off the frame (by a whole frame's extent along dir)
      expect(Math.abs(s0.b.tx) === 1920 || Math.abs(s0.b.ty) === 1080).toBe(true);
      expect(s1.b).toMatchObject({ tx: 0, ty: 0, s: 1 });
    }
    // the default: B enters from the right
    expect(stateAt(entry({ kind: 'slide' }), 3.75).b.tx).toBe(1920);
  });
  test('spin: A untouched at the start, B at rest at the end', () => {
    const e = entry({ kind: 'spin', angle: -120 }), s0 = stateAt(e, e.start), s1 = stateAt(e, e.end);
    expect(s0.wB).toBe(0); expect(s0.a).toMatchObject({ r: 0, s: 1 });
    expect(s1.wB).toBe(1); expect(s1.b).toMatchObject({ r: 0, s: 1 });
  });
  test('flash and glitch: nothing at either end, the side by the frame', () => {
    for (const kind of ['flash', 'glitch'] as const) {
      const e = entry({ kind }), s0 = stateAt(e, e.start), s1 = stateAt(e, e.end);
      expect(s0.wB).toBe(0); expect(s1.wB).toBe(1);
      expect(s0.light ?? s0.glitch).toBe(0); expect(s1.light ?? s1.glitch).toBe(0);
    }
  });
});

describe('through the cut', () => {
  const xs = [0.02, 0.07, 0.13, 0.2, 0.24];
  test('wipe and iris: the edge is half way at the cut and runs symmetrically about it; its light peaks there', () => {
    const e = entry({ kind: 'iris', edge: 'accent2' });
    expect(stateAt(e, 4).edge).toBeCloseTo(0.5, 9);
    expect(stateAt(e, 4).light).toBeCloseTo(1, 9);
    for (const x of xs) {
      expect(stateAt(e, 4 - x).edge! + stateAt(e, 4 + x).edge!).toBeCloseTo(1, 9);
      expect(stateAt(e, 4 - x).light).toBeCloseTo(stateAt(e, 4 + x).light!, 9);
    }
    expect(stateAt(entry({ kind: 'wipe' }), 4).light).toBe(0); // no edge, no light
  });
  test('wipe: the edge runs the frame along dir; iris: out to the farthest corner', () => {
    expect(wipeTrack({ from: 'a', to: 'b', kind: 'wipe', pre: 0, post: 0, soft: 100 })).toMatchObject({ dir: [1, 0], d0: -50, d1: 1970 });
    expect(irisTrack({ from: 'a', to: 'b', kind: 'iris', pre: 0, post: 0, center: [0, 0], soft: 10 }).r1).toBeCloseTo(Math.hypot(1920, 1080) + 5, 9);
  });
  test('slide: A dims and B shadows it symmetrically; B half in at the cut', () => {
    const e = entry({ kind: 'slide', dir: 0 });
    expect(stateAt(e, 4).b.tx).toBeCloseTo(-960, 6);
    for (const x of xs) {
      expect(stateAt(e, 4 - x).dim! + stateAt(e, 4 + x).dim!).toBeCloseTo(0.6, 9);
      expect(stateAt(e, 4 - x).shadow).toBeCloseTo(stateAt(e, 4 + x).shadow!, 9);
    }
  });
  test('spin: A turns out as B turns in, mirror images about the cut', () => {
    const e = entry({ kind: 'spin', angle: 90, scale: 1.5 });
    expect(stateAt(e, 4 - 1e-9).a.r).toBeCloseTo(Math.PI / 4, 6);
    expect(stateAt(e, 4).b.r).toBeCloseTo(-Math.PI / 4, 6);
    expect(stateAt(e, 4).b.s).toBeCloseTo(1.5, 6);
    for (const x of xs) {
      const p = stateAt(e, 4 - x), q = stateAt(e, 4 + x);
      expect(p.a.r).toBeCloseTo(-q.b.r!, 9);
      expect(p.a.s).toBeCloseTo(q.b.s, 9);
    }
  });
  test('glitch: strongest at the cut, symmetric about it, its pattern the frame\'s over the whole shutter', () => {
    const e = entry({ kind: 'glitch' });
    expect(stateAt(e, 4).glitch).toBe(1);
    for (const x of xs) expect(stateAt(e, 4 - x).glitch).toBeCloseTo(stateAt(e, 4 + x).glitch!, 9);
    const taps = shutterTaps(e, 4.1, 1 / 30, 0.5, 9);
    expect(new Set(taps.map((s) => s.step)).size).toBe(1);
    expect(taps[0]!.step).toBe(123);
    // seeded by the pair: another pair tears another way
    expect(pairSeed('a-b')).not.toBe(pairSeed('b-c'));
    expect(pairSeed('a-b')).toBe(pairSeed('a-b'));
  });
  test('flash: rises to its peak at the cut and falls after it', () => {
    const e = entry({ kind: 'flash' });
    expect(stateAt(e, 4 - 1e-9).light).toBeCloseTo(1, 6);
    expect(stateAt(e, 4).light).toBe(1);
    expect(stateAt(e, 3.9).light!).toBeLessThan(stateAt(e, 3.95).light!);
    expect(stateAt(e, 4.1).light!).toBeGreaterThan(stateAt(e, 4.15).light!);
  });
});

describe('motion blur', () => {
  test('every effects kind takes more taps the faster it runs, never over its budget', () => {
    expect(maxTaps('wipe')).toBe(MAX_FX_TAPS);
    expect(maxTaps('whip')).toBe(MAX_TAPS);
    expect(MAX_FX_TAPS * 3).toBeLessThanOrEqual(MAX_TAPS * 2); // the same uniform array
    for (const kind of FX) {
      const spec: Partial<TransitionSpec> = { kind, edge: kind === 'wipe' || kind === 'iris' ? 'accent' : undefined };
      // a probe just off the cut (flash and glitch change fastest either side of it)
      const slow = tapCount(entry(spec, 0.4, 0.4), 4 - 0.05, 1 / 30, 0.5, 1);
      const fast = tapCount(entry(spec, 0.15, 0.15), 4 - 0.05, 1 / 30, 0.5, 1);
      expect(fast).toBeGreaterThan(slow);
      expect(fast).toBeLessThanOrEqual(MAX_FX_TAPS);
      expect(tapCount(entry(spec), 2, 1 / 30, 0.5, 1)).toBe(1); // outside the window
    }
  });
  test('a spin counts its arc: twice the angle, more taps', () => {
    const t = 4 - 1 / 60;
    expect(tapCount(entry({ kind: 'spin', angle: 180 }), t, 1 / 30, 0.5, 1)).toBeGreaterThan(tapCount(entry({ kind: 'spin', angle: 90 }), t, 1 / 30, 0.5, 1));
    // a turn with no scaling still streaks
    expect(tapCount(entry({ kind: 'spin', scale: 1 }), t, 1 / 30, 0.5, 1)).toBeGreaterThan(4);
  });
  test('4K takes more taps than 1080p', () => {
    const e = entry({ kind: 'wipe' });
    expect(tapCount(e, 3.99, 1 / 30, 0.5, 2)).toBeGreaterThan(tapCount(e, 3.99, 1 / 30, 0.5, 1));
  });
});

describe('sounds', () => {
  test('a slide and a spin whoosh by default; a wipe is silent', () => {
    const cues = transitionCues([entry({ kind: 'slide' }), { ...entry({ kind: 'wipe' }), id: 'x-y' }, { ...entry({ kind: 'spin' }), id: 'y-z' }]);
    expect(cues.map((c) => c.scene)).toEqual(['a-b', 'y-z']);
    // B comes in from the right: the whoosh leans right
    expect(cues[0]!.items[0]).toMatchObject({ sound: 'whoosh_whip', t: 4, pan: 0.25 });
  });
});
