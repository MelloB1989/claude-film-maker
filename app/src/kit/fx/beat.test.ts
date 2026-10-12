import { describe, expect, test } from 'bun:test';
import { AudioData } from '../../engine/audio';
import { letterboxBar } from '../../engine/looks';
import { KICK_PEAK, bars, flash, hitEnv, kick, lastHit, pump, punch, shake } from './beat';

// 120 BPM, 4/4: a beat every 0.5 s, a bar every 2 s
const grid = AudioData.grid({ duration: 30, bpm: 120 });

describe('hits', () => {
  test('on the grid: beats, downbeats (= bars), backbeats, every n-th', () => {
    expect(lastHit(1.3, { on: 'beat', grid })).toBeCloseTo(1, 9);
    expect(lastHit(1.0, { on: 'beat', grid })).toBeCloseTo(1, 9); // a hit at t is t's
    expect(lastHit(3.9, { on: 'downbeat', grid })).toBeCloseTo(2, 9);
    expect(lastHit(3.9, { on: 'bar', grid })).toBeCloseTo(2, 9);
    expect(lastHit(1.9, { on: 'backbeat', grid })).toBeCloseTo(1.5, 9); // beat 4 of bar 1
    expect(lastHit(1.4, { on: 'backbeat', grid })).toBeCloseTo(0.5, 9); // beat 2
    expect(lastHit(1.9, { on: 'beat', every: 2, grid })).toBeCloseTo(1, 9);
    expect(lastHit(7.9, { on: 'bar', every: 2, grid })).toBeCloseTo(4, 9);
  });
  test('at times, every n-th, inside [from, to)', () => {
    expect(lastHit(2.5, { on: [1, 2.2, 3] })).toBe(2.2);
    expect(lastHit(0.5, { on: [1, 2.2, 3] })).toBe(-Infinity);
    expect(lastHit(3.5, { on: [1, 2.2, 3], every: 2 })).toBe(3);
    expect(lastHit(5.2, { on: 'beat', grid, from: 6 })).toBe(-Infinity);
    expect(lastHit(9, { on: 'beat', grid, to: 7.2 })).toBeCloseTo(7, 9);
    expect(() => lastHit(1, { on: 'beat' })).toThrow(/grid/);
  });
  test('an envelope jumps on the hit and falls to 5% over its decay', () => {
    expect(hitEnv(0, 0.2)).toBe(1);
    expect(hitEnv(0.2, 0.2)).toBeCloseTo(Math.exp(-3), 9);
    expect(hitEnv(-0.01, 0.2)).toBe(0);
  });
});

describe('effects', () => {
  test('punch: the house kick lands on the hit, never zooms out, rests within 300 ms', () => {
    expect(kick(KICK_PEAK)).toBeCloseTo(1, 9);
    expect(KICK_PEAK).toBeGreaterThan(0.03); expect(KICK_PEAK).toBeLessThan(0.045);
    expect(punch({ t: 2 }, { on: 'downbeat', grid, amount: 0.05 })).toBeCloseTo(1.05, 6);
    expect(punch({ t: 2.3 }, { on: 'downbeat', grid, amount: 0.05 })).toBeCloseTo(1, 3);
    for (let t = 0; t < 4; t += 0.01) expect(punch({ t }, { on: 'beat', grid })).toBeGreaterThanOrEqual(1);
    // it leads its hit: the frame before already rises
    expect(punch({ t: 2 - 1 / 30 }, { on: 'downbeat', grid })).toBeGreaterThan(1);
  });
  test('shake: still before the first hit, strongest after it, gone by its decay; seeded', () => {
    expect(shake({ t: 0.9 }, { on: [1], amount: 20 })).toEqual([0, 0]);
    const a = shake({ t: 1.02 }, { on: [1], amount: 20 }), b = shake({ t: 1.02 }, { on: [1], amount: 20 });
    expect(a).toEqual(b);
    expect(Math.hypot(...a)).toBeGreaterThan(0);
    expect(Math.hypot(...shake({ t: 1.6 }, { on: [1], amount: 20, decay: 0.2 }))).toBeLessThan(0.01);
    expect(shake({ t: 1.02 }, { on: [1], amount: 20, seed: 2 })).not.toEqual(a);
  });
  test('flash and pump peak on the hit and decay', () => {
    expect(flash({ t: 2 }, { grid })).toBeCloseTo(0.3, 9);
    expect(flash({ t: 2.16 }, { grid })).toBeCloseTo(0.3 * Math.exp(-3), 9);
    expect(pump({ t: 1.5 }, { grid, amount: -0.2 })).toBeCloseTo(0.8, 9);
    expect(pump({ t: 1.5 + 0.4 }, { grid, amount: -0.2 })).toBeCloseTo(1, 2);
  });
  test('bars spring in and out: none before, the aspect once settled, none after', () => {
    expect(letterboxBar(bars({ t: 0.5 }, { in: 1 }), 1920, 1080)).toBe(0);
    expect(bars({ t: 2 }, { in: 1, aspect: 2.39 })).toBeCloseTo(2.39, 6);
    // the overshoot: bars a touch deeper than settled
    expect(letterboxBar(bars({ t: 1.12 }, { in: 1 }), 1920, 1080)).toBeGreaterThan(letterboxBar(2.39, 1920, 1080));
    expect(letterboxBar(bars({ t: 4 }, { in: 1, out: 3 }), 1920, 1080)).toBeCloseTo(0, 6);
  });
});
