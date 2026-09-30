import { expect, test } from 'bun:test';
import { AudioData } from './audio';
import { onBeat, onDownbeat, slam, speedRamp, spring, whip, wordTimes } from './motion';
import type { Frame } from './scene';
import { keys } from './util';
import { VO } from './vo';

/** Largest value of fn over [a, b], sampled every `step`. */
const peak = (fn: (t: number) => number, a = 0, b = 1, step = 1e-4) => {
  let m = -Infinity;
  for (let t = a; t <= b; t += step) m = Math.max(m, fn(t));
  return m;
};
/** Overshoot of a damped spring's step response (the fraction above 1 at its first peak). */
const overshoot = (damping: number) => Math.exp((-Math.PI * damping) / Math.sqrt(1 - damping * damping));

// ---- spring ----

test('spring rests at 0 until t = 0, then settles on 1', () => {
  expect(spring(0)).toBe(0);
  expect(spring(-0.5)).toBe(0);
  expect(Math.abs(spring(2) - 1)).toBeLessThan(0.001);
});

test('spring overshoots at most 12% at damping 0.6 (the exact oscillator value is 9.5%)', () => {
  const over = peak((t) => spring(t, 5, 0.6)) - 1;
  expect(over).toBeLessThanOrEqual(0.12);
  expect(Math.abs(over - overshoot(0.6))).toBeLessThan(1e-3);
  expect(peak((t) => spring(t)) - 1).toBeLessThanOrEqual(0.12); // the defaults are the same spring
});

test('spring: damping is the damping ratio at every frequency of the motion language (4-6 Hz, 0.5-0.7)', () => {
  for (const f of [4, 5, 6]) {
    for (const z of [0.5, 0.6, 0.7]) {
      expect(Math.abs(peak((t) => spring(t, f, z)) - 1 - overshoot(z))).toBeLessThan(1e-3);
      expect(Math.abs(spring(2, f, z) - 1)).toBeLessThan(1e-3);
    }
  }
});

test('spring starts at rest and settles within 1% by 250 ms', () => {
  expect(spring(0.001)).toBeLessThan(0.001); // no launch velocity
  expect(spring(0.1)).toBeGreaterThan(1.03); // it has overshot by now
  for (let t = 0.25; t < 2; t += 0.001) expect(Math.abs(spring(t) - 1)).toBeLessThan(0.01);
});

test('spring at damping 1 or more never passes 1, and never produces NaN', () => {
  for (const z of [1, 1.0000001, 2, 10]) {
    let prev = 0;
    for (let t = 0; t < 3; t += 0.005) {
      const v = spring(t, 5, z);
      expect(Number.isFinite(v)).toBe(true);
      expect(v).toBeLessThanOrEqual(1 + 1e-9);
      expect(v).toBeGreaterThanOrEqual(prev - 1e-9);
      prev = v;
    }
    expect(spring(60, 5, z)).toBeCloseTo(1, 9);
  }
  expect(spring(0.2, 5, 2)).toBeLessThan(spring(0.2, 5, 1)); // heavier damping is slower
});

test('spring stays finite on degenerate input', () => {
  expect(spring(1, 0)).toBe(0); // a spring of no frequency never moves
  expect(spring(0.03, 5, 0)).toBeCloseTo(1 - Math.cos(2 * Math.PI * 5 * 0.03), 12); // undamped: a pure oscillation
  expect(spring(Infinity)).toBe(1);
  expect(spring(1, 5, -1)).toBe(spring(1, 5, 0)); // negative damping is clamped, not unstable
});

// ---- slam ----

test('slam is 0 before hit - lead, and rises after it', () => {
  const hit = 12.4;
  const lead = 0.05;
  for (let t = hit - 1; t < hit - lead - 1e-9; t += 0.001) expect(slam(t, hit, { lead })).toBe(0);
  expect(slam(hit - lead + 0.01, hit, { lead })).toBeGreaterThan(0);
});

test('slam lands on the hit by default, overshoots, then settles', () => {
  const hit = 3.2;
  expect(Math.abs(slam(hit, hit) - 1)).toBeLessThan(1e-9); // first reaches 1 exactly on the onset
  expect(slam(hit - 0.01, hit)).toBeLessThan(1); // still approaching
  expect(slam(hit - 0.01, hit)).toBeGreaterThan(0.5); // and already in motion: the lead is real
  expect(slam(hit + 0.03, hit)).toBeGreaterThan(1.05); // past it
  expect(Math.abs(slam(hit + 2, hit) - 1)).toBeLessThan(1e-3);
  expect(slam(hit - 1, hit)).toBe(0);
});

test('slam lands on the hit for every spring in the motion language', () => {
  for (const freq of [4, 5, 6]) {
    for (const damping of [0.5, 0.6, 0.7]) {
      expect(Math.abs(slam(2, 2, { freq, damping }) - 1)).toBeLessThan(1e-9);
      expect(slam(2 - 0.002, 2, { freq, damping })).toBeLessThan(1);
      expect(slam(2 + 0.002, 2, { freq, damping })).toBeGreaterThan(1);
    }
  }
});

test('slam: lead 0 launches at the hit, and freq and damping pass through to the spring', () => {
  const hit = 1;
  for (const t of [0.9, 1, 1.03, 1.1, 1.3]) {
    expect(slam(t, hit, { lead: 0 })).toBe(spring(t - hit));
    expect(slam(t, hit, { lead: 0, freq: 6, damping: 0.5 })).toBe(spring(t - hit, 6, 0.5));
  }
});

test('slam of a spring that never overshoots starts at the hit', () => {
  expect(slam(1 - 0.001, 1, { damping: 1.5 })).toBe(0);
  expect(slam(1.2, 1, { damping: 1.5 })).toBeGreaterThan(0);
});

// ---- speedRamp ----

// 1x, then a fast ramp down to 0.25x, a long hold, and back up to 1x.
const SNAP: [number, number][] = [[0, 1], [1, 1], [1.2, 0.25], [3, 0.25], [3.2, 1]];

test('speedRamp maps a speed-1 segment 1:1', () => {
  const ks: [number, number][] = [[0, 1], [2, 1]];
  for (const t of [0, 0.3, 1, 1.999, 2, 5]) expect(speedRamp(t, ks)).toBeCloseTo(t, 12);
  expect(speedRamp(0.8, SNAP)).toBeCloseTo(0.8, 12); // and the run-up before the ramp
});

test('speedRamp advances a 0.25 segment at a quarter', () => {
  expect(speedRamp(3, SNAP) - speedRamp(1.2, SNAP)).toBeCloseTo(0.25 * 1.8, 12);
  expect(speedRamp(2, SNAP) - speedRamp(1.5, SNAP)).toBeCloseTo(0.125, 12);
  expect(speedRamp(5, SNAP) - speedRamp(4, SNAP)).toBeCloseTo(1, 12); // back at real time, held past the last key
});

test('speedRamp is monotonic and continuous through the ramps', () => {
  const dt = 1 / 240;
  let prev = speedRamp(-0.5, SNAP);
  for (let t = -0.5 + dt; t < 5; t += dt) {
    const v = speedRamp(t, SNAP);
    expect(v).toBeGreaterThanOrEqual(prev);
    expect(v - prev).toBeLessThanOrEqual(dt + 1e-12); // never faster than the fastest speed
    expect(v - prev).toBeGreaterThanOrEqual(0.25 * dt - 1e-12); // nor slower than the slowest
    prev = v;
  }
});

test('speedRamp: two keys at one time are an instant change of speed, and the mapped time stays continuous', () => {
  const ks: [number, number][] = [[0, 1], [1, 1], [1, 0.25], [2, 0.25], [2, 1]];
  expect(speedRamp(1, ks)).toBeCloseTo(1, 12);
  expect(speedRamp(1.5, ks) - speedRamp(1, ks)).toBeCloseTo(0.125, 12);
  expect(speedRamp(2, ks)).toBeCloseTo(1.25, 12);
  expect(speedRamp(3, ks)).toBeCloseTo(2.25, 12);
  const eps = 1e-9;
  expect(Math.abs(speedRamp(1 + eps, ks) - speedRamp(1 - eps, ks))).toBeLessThan(2 * eps);
  expect(Math.abs(speedRamp(2 + eps, ks) - speedRamp(2 - eps, ks))).toBeLessThan(2 * eps);
});

test('speedRamp is the integral of the speed curve that util keys() describes', () => {
  const ks: [number, number][] = [[0.5, 1], [1.5, 0.25], [2.5, 0.25], [3, 2], [4, 0.5]];
  const h = 1e-5;
  for (let t = 0.05; t < 4.5; t += 0.037) {
    const speed = (speedRamp(t + h, ks) - speedRamp(t - h, ks)) / (2 * h);
    expect(Math.abs(speed - keys(t, ks))).toBeLessThan(1e-5); // in the ramps too, not only on the plateaus
  }
  let area = 0;
  const dt = 1e-4;
  for (let t = 0; t < 4.5; t += dt) area += keys(t + dt / 2, ks) * dt;
  expect(Math.abs(speedRamp(4.5, ks) - area)).toBeLessThan(1e-4);
});

test('speedRamp holds the end speeds, treats no keys as real time, and ignores key order', () => {
  expect(speedRamp(0.5, [[1, 0.5], [2, 0.5]])).toBeCloseTo(0.25, 12); // before the first key: its speed
  expect(speedRamp(7, [[0, 2]])).toBeCloseTo(14, 12); // one key: a constant speed
  expect(speedRamp(3.3, [])).toBeCloseTo(3.3, 12);
  expect(speedRamp(1.7, [[2, 1], [0, 0.5]])).toBeCloseTo(speedRamp(1.7, [[0, 0.5], [2, 1]]), 12);
});

test('speedRamp: zero speed freezes time and negative speed runs it backwards', () => {
  expect(speedRamp(3, [[0, 0]])).toBeCloseTo(0, 12);
  expect(speedRamp(2, [[0, -1]])).toBeCloseTo(-2, 12);
  // a scrub: forward, back through a smooth stop, and forward again
  const scrub: [number, number][] = [[0, 1], [1, -1], [2, -1], [3, 1]];
  expect(speedRamp(2, scrub)).toBeLessThan(speedRamp(1, scrub));
  expect(speedRamp(5, scrub)).toBeGreaterThan(speedRamp(2, scrub));
});

// ---- whip ----

test('whip: k runs 0 to 1 and is 0.5 at the cut; the blur is 0 outside the move', () => {
  const cut = 10.3;
  expect(whip(cut - 1, cut)).toEqual({ k: 0, blurPx: 0 });
  expect(whip(cut + 1, cut)).toEqual({ k: 1, blurPx: 0 });
  const mid = whip(cut, cut);
  expect(mid.k).toBeCloseTo(0.5, 12);
  expect(mid.blurPx).toBeGreaterThan(0);
});

test('whip lasts 60-120 ms by default, and dur sets it', () => {
  const span = (dur?: number) => {
    let lo = Infinity;
    let hi = -Infinity;
    for (let t = 4.5; t <= 5.5; t += 0.0005) {
      if (whip(t, 5, dur).blurPx > 0) { lo = Math.min(lo, t); hi = Math.max(hi, t); }
    }
    return hi - lo;
  };
  expect(span()).toBeGreaterThanOrEqual(0.06);
  expect(span()).toBeLessThanOrEqual(0.12);
  expect(Math.abs(span(0.2) - 0.2)).toBeLessThan(0.002);
  expect(Math.abs(span(0.06) - 0.06)).toBeLessThan(0.002);
});

test('whip: k is monotonic; the blur is never negative, symmetric about the cut, and largest at the cut', () => {
  const cut = 4;
  const dur = 0.1;
  const atCut = whip(cut, cut, dur).blurPx;
  let prevK = -1;
  for (let i = -200; i <= 200; i++) {
    const w = whip(cut + i * 0.001, cut, dur);
    expect(w.k).toBeGreaterThanOrEqual(prevK);
    expect(w.blurPx).toBeGreaterThanOrEqual(0);
    expect(w.blurPx).toBeLessThanOrEqual(atCut);
    expect(w.blurPx).toBeCloseTo(whip(cut - i * 0.001, cut, dur).blurPx, 9);
    prevK = w.k;
  }
});

test('whip: the blur follows the speed of the move', () => {
  const cut = 2;
  const dur = 0.09;
  const h = 1e-6;
  const speed = (t: number) => (whip(t + h, cut, dur).k - whip(t - h, cut, dur).k) / (2 * h);
  const atCut = whip(cut, cut, dur).blurPx;
  for (const dt of [-0.04, -0.02, -0.01, 0, 0.01, 0.02, 0.04]) {
    const t = cut + dt;
    expect(Math.abs(whip(t, cut, dur).blurPx / atCut - speed(t) / speed(cut))).toBeLessThan(1e-4);
  }
});

test('whip with no duration is an instant cut with no blur', () => {
  expect(whip(4.9, 5, 0)).toEqual({ k: 0, blurPx: 0 });
  expect(whip(5, 5, 0)).toEqual({ k: 1, blurPx: 0 });
});

// ---- wordTimes ----

const voData = {
  duration: 12,
  lines: [
    { id: 'L01', scene: 'ex', act: 'I', text: 'Not me.', start: 1, end: 2,
      words: [{ w: 'Not', start: 1.0, end: 1.4 }, { w: 'me.', start: 1.5, end: 2.0 }] },
    { id: 'L02', scene: 'her', act: 'I', text: 'Every memory, a commit.', start: 3, end: 5,
      words: [{ w: 'Every', start: 3.0, end: 3.3 }, { w: 'memory,', start: 3.35, end: 3.9 },
        { w: 'a', start: 4.2, end: 4.3 }, { w: 'commit.', start: 4.35, end: 5.0 }] },
    { id: 'L03', scene: 'her', act: 'I', text: 'Every fact, a blame.', start: 6, end: 8,
      words: [{ w: 'Every', start: 6.0, end: 6.3 }, { w: 'fact,', start: 6.35, end: 6.9 },
        { w: 'a', start: 7.2, end: 7.3 }, { w: 'blame.', start: 7.35, end: 8.0 }] },
    { id: 'L04', scene: 'loom', act: 'II', text: 'Loom.', start: 9, end: 10, words: [{ w: 'Loom.', start: 9.1, end: 9.8 }] },
  ],
  scenes: [
    { id: 'ex', act: 'I', start: 0, end: 2.5 }, { id: 'her', act: 'I', start: 2.5, end: 8.5 },
    { id: 'loom', act: 'II', start: 8.5, end: 10.5 }, { id: 'quiet', act: 'II', start: 10.5, end: 12 },
  ],
  acts: [{ id: 'I', name: 'One', start: 0, end: 8.5 }, { id: 'II', name: 'Two', start: 8.5, end: 12 }],
};

test('wordTimes returns the scene\'s words in spoken order, with at = the word\'s start', () => {
  const vo = new VO(voData);
  const wt = wordTimes(vo, 'her');
  expect(wt.map((x) => x.w.w)).toEqual(['Every', 'memory,', 'a', 'commit.', 'Every', 'fact,', 'a', 'blame.']);
  for (const x of wt) expect(x.at).toBe(x.w.start);
  for (let i = 1; i < wt.length; i++) expect(wt[i]!.at).toBeGreaterThan(wt[i - 1]!.at);
  expect(wt.map((x) => x.at)).toEqual([3.0, 3.35, 4.2, 4.35, 6.0, 6.35, 7.2, 7.35]);
});

test('wordTimes hands back the VO\'s own words, and only the requested scene\'s', () => {
  const vo = new VO(voData);
  const wt = wordTimes(vo, 'her');
  for (const x of wt) expect(x.w).toBe(vo.words[x.w.gi]!); // same objects: line, index and gi intact
  expect(wordTimes(vo, 'ex').map((x) => x.w.w)).toEqual(['Not', 'me.']);
  expect(wordTimes(vo, 'loom').map((x) => x.at)).toEqual([9.1]);
});

test('wordTimes: a scene with no spoken words is empty; a scene the VO has never heard of throws', () => {
  const vo = new VO(voData);
  expect(wordTimes(vo, 'quiet')).toEqual([]);
  expect(() => wordTimes(vo, 'hre')).toThrow('hre');
});

// ---- onBeat / onDownbeat ----

// 100 BPM in 4/4, offset like the score's grid: a beat every 0.6 s, a downbeat every 4th beat.
const beats = Array.from({ length: 40 }, (_, i) => 0.008 + 0.6 * i);
const downbeats = beats.filter((_, i) => i % 4 === 0);
const audio = new AudioData({ duration: 24, bpm: 100, fps: 100, beats, downbeats, sections: [], features: {}, onsets: {} });
/** A frame as Engine.frameFor builds it: the beat grid drives beat, bar and their phases. */
const frameAt = (t: number): Frame => {
  const beat = audio.beatAt(t);
  const bar = audio.barAt(t);
  return {
    t, dt: 1 / 30, lt: t, p: 0, start: 0, end: 24, seeked: false, preroll: false,
    beat, bar, beatPhase: beat - Math.floor(beat), barPhase: bar - Math.floor(bar),
    a: audio.sample(t), under: null, tin: 1, tout: 0,
  };
};

test('onBeat is 1 on a beat and halves every halfLife beats', () => {
  expect(onBeat(frameAt(beats[5]!))).toBeCloseTo(1, 12);
  const quarter = frameAt(beats[5]! + 0.6 * 0.25); // a quarter of a beat later
  expect(onBeat(quarter, 0.25)).toBeCloseTo(0.5, 9);
  expect(onBeat(quarter, 0.125)).toBeCloseTo(0.25, 9);
  expect(onBeat(quarter, 0.5)).toBeCloseTo(Math.SQRT1_2, 9);
});

test('onBeat decays inside a beat and fires again on the next one', () => {
  let prev = Infinity;
  for (let i = 0; i < 100; i++) {
    const v = onBeat(frameAt(beats[3]! + 0.0001 + i * 0.0059));
    expect(v).toBeLessThan(prev);
    expect(v).toBeGreaterThan(0);
    prev = v;
  }
  expect(onBeat(frameAt(beats[4]!))).toBeGreaterThan(prev);
  expect(onBeat(frameAt(beats[4]!))).toBeCloseTo(1, 12);
});

test('onBeat tracks the grid: a beat that comes early or late still fires on the beat', () => {
  const swung = [0, 0.5, 1.15, 1.7, 2.4]; // an uneven grid
  const a = new AudioData({ duration: 4, bpm: 100, fps: 100, beats: swung, downbeats: [0], sections: [], features: {}, onsets: {} });
  const at = (t: number) => { const b = a.beatAt(t); return { ...frameAt(0), beat: b, beatPhase: b - Math.floor(b) }; };
  for (const b of swung.slice(0, 4)) expect(onBeat(at(b))).toBeCloseTo(1, 12);
  // halfway between two beats is the same phase, whatever their spacing
  expect(onBeat(at(0.25))).toBeCloseTo(onBeat(at(1.15 + 0.275)), 9);
});

test('onDownbeat is 1 on a downbeat and does not fire on the other beats', () => {
  for (const d of [downbeats[1]!, downbeats[4]!]) expect(onDownbeat(frameAt(d))).toBeCloseTo(1, 12);
  const offBeat = frameAt(beats[9]!); // one beat after the downbeat at beats[8]
  expect(onBeat(offBeat)).toBeCloseTo(1, 12);
  expect(onDownbeat(offBeat)).toBeLessThan(0.5);
  expect(onDownbeat(frameAt(beats[10]!))).toBeLessThan(onDownbeat(offBeat)); // it keeps decaying to the next downbeat
});

test('onDownbeat halves every halfLife beats after the downbeat, and its accent outlasts a beat tick', () => {
  const later = frameAt(downbeats[2]! + 0.6 * 0.5); // half a beat after a downbeat
  expect(onDownbeat(later, 0.5)).toBeCloseTo(0.5, 9);
  expect(onDownbeat(later, 0.25)).toBeCloseTo(0.25, 9);
  expect(onDownbeat(later)).toBeGreaterThan(onBeat(later)); // default half-lives
});

// ---- purity ----

test('every helper is a pure function of its inputs: the same answer in any order of calls', () => {
  const ts = Array.from({ length: 60 }, (_, i) => i * 0.0377);
  const all = (t: number) => [spring(t), slam(t, 1), speedRamp(t, SNAP), whip(t, 1), onBeat(frameAt(t)), onDownbeat(frameAt(t))];
  const forward = ts.map(all);
  const backward = [...ts].reverse().map(all).reverse();
  expect(backward).toEqual(forward);
  expect(ts.map(all)).toEqual(forward);
});
