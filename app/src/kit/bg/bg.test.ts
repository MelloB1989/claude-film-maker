import { afterEach, expect, test } from 'bun:test';
import { GLOW_LEVEL } from '../../engine/look';
import { LIN, setTheme } from '../../engine/palette';
import { onBeat } from '../../engine/motion';
import { hotInk, inkLevel, pulseAt } from './base';
import { pulseArea, warpTravel } from './warp';

afterEach(() => setTheme('noir'));

test('inkLevel: only an accent (or a saturated #hex) is driven past its own colour; fg never blooms', () => {
  for (const theme of ['noir', 'midnight', 'aurora', 'paper']) {
    setTheme(theme);
    expect(inkLevel('accent', 2)).toBe(2);
    expect(inkLevel('accent2', 2.5)).toBe(2.5);
    const fg = LIN.fg, m = Math.max(...fg);
    expect(inkLevel('fg', 3)).toBeCloseTo(m, 9);
    expect(hotInk('fg', 3)).toEqual(fg);
    expect(inkLevel('surface', 3)).toBeCloseTo(Math.max(...LIN.surface), 9);
  }
  expect(inkLevel('#ff2040', 2)).toBe(2); // saturated: may glow
  expect(inkLevel('#e0e0e0', 2)).toBeLessThan(1); // grey: stays put
  // capped
  expect(inkLevel('accent', 40)).toBe(GLOW_LEVEL + 1);
  // the hue is kept
  const h = hotInk('accent', 2), c = LIN.accent;
  expect(h[0] / h[2]).toBeCloseTo(c[0] / c[2], 9);
  expect(Math.max(...h)).toBeCloseTo(2, 9);
});

test('pulseAt: the house beat pulse, 0 for none, throws on an unknown kind', () => {
  const f = { beatPhase: 0.1, barPhase: 0.3, beatsPerBar: 4 };
  expect(pulseAt('none', f)).toBe(0);
  expect(pulseAt('beat', f)).toBeCloseTo(onBeat(f as never, 0.3), 12);
  expect(pulseAt('downbeat', { ...f, barPhase: 0 })).toBe(1);
  expect(() => pulseAt('snare' as never, f)).toThrow(/pulse/);
});

test('pulseArea: the integral of the cut-off beat pulse, continuous across beats', () => {
  const hl = 0.3;
  // numeric integral of pulse(phase) = 0.5^(phase / hl) over beats 0..3.7
  let s = 0;
  const dx = 1e-4;
  for (let x = dx / 2; x < 3.7; x += dx) s += Math.pow(0.5, (x - Math.floor(x)) / hl) * dx;
  expect(pulseArea(3.7, hl)).toBeCloseTo(s, 4);
  for (const b of [1, 2, 5, 17]) expect(pulseArea(b - 1e-9, hl)).toBeCloseTo(pulseArea(b, hl), 6);
  // monotonic
  let prev = -Infinity;
  for (let b = 0; b < 6; b += 0.01) {
    const a = pulseArea(b, hl);
    expect(a).toBeGreaterThanOrEqual(prev);
    prev = a;
  }
  // downbeats: one pulse a bar
  expect(pulseArea(4, 0.6, 4)).toBeCloseTo((0.6 / Math.LN2) * (1 - Math.pow(0.5, 4 / 0.6)), 9);
});

test('warpTravel: real time without a pulse; with one, the speed is the travel\'s derivative', () => {
  const base = { time: 3, speed: 1, boost: 3, beatsPerBar: 4, secondsPerBeat: 0.5 };
  expect(warpTravel({ ...base, pulse: 'none', beat: 6, now: 0 })).toEqual({ travel: 3, vel: 1 });
  const at = (beat: number) => {
    const now = Math.pow(0.5, (beat - Math.floor(beat)) / 0.3);
    return warpTravel({ ...base, time: beat * 0.5, pulse: 'beat', beat, now });
  };
  const b = 6.2, h = 1e-5;
  const d = (at(b + h).travel - at(b - h).travel) / (2 * h * 0.5); // per second
  expect(d).toBeCloseTo(at(b).vel, 3);
});
