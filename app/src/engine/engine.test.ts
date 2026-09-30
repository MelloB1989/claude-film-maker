import { expect, test } from 'bun:test';
import { Engine, onScreen, ownedFrames, shutterPlan } from './engine';

// Expected values are hand-derived. Film frame n is at t = n / 30. A 0.5 shutter spans t ± 1/120 s (a quarter frame
// either side), and a fixed set of n sub-frames sits at offsets u = (k + 0.5) / n - 0.5, at times t + u / 60. An entry
// holds ε = 1e-6 s before its end. The cut is the film's (data/vo.json): ex [6.008, 15.608) cuts to her
// [15.608, 22.808), 8 ms after frame 468 (t = 15.6), so frame 468's shutter (to 15.6083) crosses it.

const ex = { id: 'ex', start: 6.008, end: 15.608 };
const her = { id: 'her', start: 15.608, end: 22.808 };
const hud = { id: 'hud', start: 0, end: 93.6 }; // an overlay across the cut (a HUD, the karaoke)
const CUT = 15.608, EPS = 1e-6;
const offsets = (n: number) => Array.from({ length: n }, (_, k) => (k + 0.5) / n - 0.5);
const ids = (sub: { entry: { id: string } }[]) => sub.map((x) => x.entry.id);

test('shutterPlan: the frame before a cut shows only the outgoing scene, its sub-frames past the cut held before it', () => {
  const t = 468 / 30;
  for (const n of [36, 324]) {
    const u = offsets(n);
    const plan = shutterPlan([ex, her], t, 1 / 30, 0.5, u);
    expect(plan.length).toBe(n);
    let held = 0;
    plan.forEach((sub, k) => {
      expect(ids(sub)).toEqual(['ex']);
      const s = t + u[k]! / 60, time = sub[0]!.time;
      expect(time).toBeLessThanOrEqual(CUT - EPS);
      if (s < CUT) expect(time).toBeCloseTo(s, 12);
      else {
        expect(time).toBe(CUT - EPS);
        held++;
      }
    });
    // past the cut: u >= 0.48 (8 ms of the 1/60 s shutter), which is 1 of 36 sub-frames and 6 of 324
    expect(held).toBe(n === 36 ? 1 : 6);
  }
});

test('shutterPlan: the first frame after a cut shows only the incoming scene, from the cut on', () => {
  // frame 469 (15.6333): its shutter opens at 15.625, after the cut
  for (const sub of shutterPlan([ex, her], 469 / 30, 1 / 30, 0.5, offsets(36))) {
    expect(ids(sub)).toEqual(['her']);
    expect(sub[0]!.time).toBeGreaterThanOrEqual(CUT);
  }
  // a cut exactly on a frame time (a [0, 2) to b [2, 4), frame 60): the frame is b's, and its early sub-frames (t - 3/480
  // and t - 1/480) hold at the cut
  const a = { id: 'a', start: 0, end: 2 }, b = { id: 'b', start: 2, end: 4 };
  const plan = shutterPlan([a, b], 60 / 30, 1 / 30, 0.5, offsets(4));
  expect(plan.map(ids)).toEqual([['b'], ['b'], ['b'], ['b']]);
  expect(plan.map((sub) => sub[0]!.time)).toEqual([2, 2, expect.closeTo(2 + 1 / 480, 12), expect.closeTo(2 + 3 / 480, 12)]);
});

test('shutterPlan: an overlay whose window covers the shutter is in every sub-frame, at the sub-frame time itself', () => {
  const t = 468 / 30, u = offsets(36);
  const plan = shutterPlan([ex, her, hud], t, 1 / 30, 0.5, u);
  plan.forEach((sub, k) => {
    expect(ids(sub)).toEqual(['hud', 'ex']); // compositing order: by start
    expect(sub[0]!.time).toBeCloseTo(t + u[k]! / 60, 12);
  });
  // the last sub-frame (15.60810): the overlay runs on past the cut, the scene holds
  expect(plan[35]![0]!.time).toBeCloseTo(15.6 + 17.5 / 36 / 60, 12);
  expect(plan[35]![1]!.time).toBe(CUT - EPS);
});

test('shutterPlan: the preview (samples 1) renders one sub-frame at t, of the entries on screen at t', () => {
  const at = (t: number) => shutterPlan([ex, her, hud], t, 1 / 30, 0.5, [0]).map((sub) => sub.map((x) => [x.entry.id, x.time]));
  expect(at(15.6)).toEqual([[['hud', 15.6], ['ex', 15.6]]]);
  expect(at(CUT)).toEqual([[['hud', CUT], ['her', CUT]]]); // the cut's own time is the incoming scene's
  // t itself is never moved, even within ε of the cut
  expect(at(CUT - 1e-7)).toEqual([[['hud', CUT - 1e-7], ['ex', CUT - 1e-7]]]);
  expect(at(100)).toEqual([[]]); // after the film: nothing on screen
});

/**
 * Engine.prepare on a stand-in engine (no WebGL): the timeline, and per entry a scene that records the times it is
 * asked to prepare, except the `bare` entries (no scene: a module that failed, or one --only left unloaded).
 */
function preparing(timeline: { id: string; start: number; end: number }[], bare: string[] = []) {
  const calls: Record<string, number[]> = {};
  const scene = (id: string) => ({ prepare: async (x: number) => void (calls[id] ??= []).push(x) });
  const loaded = new Map(timeline.map((entry) => [entry.id, { entry, lastT: -1, scene: bare.includes(entry.id) ? null : scene(entry.id) }]));
  return { engine: Object.assign(Object.create(Engine.prototype), { timeline, loaded }) as Engine, calls };
}

test('prepare: with motion blur, each scene on screen at t prepares t and its shutter ends, held in its window', async () => {
  const t = 468 / 30;
  for (const samples of [4, { min: 4, max: 324, tol: 3 }]) {
    const { engine, calls } = preparing([ex, her, hud]);
    await engine.prepare(t, 1 / 30, samples, 0.5);
    // her is not on screen at t (it starts inside the shutter), and ex's shutter end holds before the cut
    expect(calls).toEqual({
      ex: [expect.closeTo(t - 1 / 120, 12), t, CUT - EPS],
      hud: [expect.closeTo(t - 1 / 120, 12), t, expect.closeTo(t + 1 / 120, 12)],
    });
  }
  // at the cut, her's shutter opens before its start and holds there, at t: two times, not three (hud has no scene)
  const { engine, calls } = preparing([ex, her, hud], ['hud']);
  await engine.prepare(CUT, 1 / 30, 4, 0.5);
  expect(calls).toEqual({ her: [CUT, expect.closeTo(CUT + 1 / 120, 12)] });
});

test('prepare: without motion blur (samples 1), each scene on screen at t prepares t only', async () => {
  const { engine, calls } = preparing([ex, her, hud]);
  await engine.prepare(468 / 30, 1 / 30, 1, 0.5);
  expect(calls).toEqual({ ex: [468 / 30], hud: [468 / 30] });
});

test('ownedFrames: a window [s, e) owns frames ceil(s·fps) … ceil(e·fps) − 1', () => {
  expect(ownedFrames(her, 30)).toEqual({ first: 469, last: 684 }); // 15.608·30 = 468.24, 22.808·30 = 684.24: 216 frames
  expect(ownedFrames(her, 60)).toEqual({ first: 937, last: 1368 }); // 936.48 and 1368.48: 432 frames
  // a boundary exactly on a frame time: that frame is the later window's (the film ends at 93.6, frame 2808)
  expect(ownedFrames({ start: 86.408, end: 93.6 }, 30)).toEqual({ first: 2593, last: 2807 });
  expect(ownedFrames({ start: 2, end: 4 }, 30)).toEqual({ first: 60, last: 119 });
  expect(ownedFrames({ start: 2, end: 4 }, 60)).toEqual({ first: 120, last: 239 });
  // even where s·fps rounds past it: 8.3·30 is 249.00000000000003, but frame 249 is at 249 / 30 = 8.3 itself
  expect(ownedFrames({ start: 8.3, end: 16.1 }, 30)).toEqual({ first: 249, last: 482 });
  expect(ownedFrames({ start: 8.3, end: 16.1 }, 60)).toEqual({ first: 498, last: 965 });
  // a window between two frame times owns none
  expect(ownedFrames({ start: 15.608, end: 15.62 }, 30)).toEqual({ first: 469, last: 468 });
});

test("ownedFrames: frame f is a window's exactly when the window is on screen at f / fps (boundaries on a 0.1 s grid)", () => {
  for (const fps of [24, 25, 30, 60]) {
    for (let i = 0; i < 1000; i++) {
      const w = { start: i / 10, end: (i + 1 + (i % 7)) / 10 };
      const { first, last } = ownedFrames(w, fps);
      const on = (f: number) => onScreen([w], f / fps).length === 1;
      expect([on(first - 1), on(first), on(last), on(last + 1)]).toEqual([false, true, true, false]);
    }
  }
});
