import { expect, spyOn, test } from 'bun:test';
import * as THREE from 'three';
import { Engine, onScreen, ownedFrames, shutterOffsets, shutterPlan, type AdaptiveSampling, type TimelineEntry } from './engine';
import { Plate, type PlateKind } from './plates';
import { Scene, type Frame, type SceneClass, type SceneCtx } from './scene';
import { mulberry32 } from './util';

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

test('prepare: with motion blur, each scene on screen at t prepares every sub-frame time render() renders, held in its window', async () => {
  const t = 468 / 30;
  // the times of a frame's sub-frames: t + u / 60 at a 0.5 shutter, held before the end of the entry's window
  const subTimes = (end: number, u: number[]) => [...new Set(u.map((x) => (t + x / 60 < end ? t + x / 60 : end - EPS)))];
  for (const samples of [4, { min: 4, max: 324, tol: 3 }]) {
    const { engine, calls } = preparing([ex, her, hud]);
    await engine.prepare(t, 1 / 30, samples, 0.5);
    // her is not on screen at t (it starts inside the shutter), and ex's sub-frames past the cut hold before it
    const u = shutterOffsets(samples);
    expect(calls.ex!.length).toBe(samples === 4 ? 4 : 324 - 5); // (6 of 324 are past the cut, held at one time)
    expect(calls).toEqual({ ex: subTimes(CUT, u).map((x) => expect.closeTo(x, 12)), hud: subTimes(93.6, u).map((x) => expect.closeTo(x, 12)) });
  }
  // at the cut, her's early sub-frames hold at its start: three times for four sub-frames (hud has no scene)
  const { engine, calls } = preparing([ex, her, hud], ['hud']);
  await engine.prepare(CUT, 1 / 30, 4, 0.5);
  expect(calls).toEqual({ her: [CUT, expect.closeTo(CUT + 0.125 / 60, 12), expect.closeTo(CUT + 0.375 / 60, 12)] });
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

test('shutterOffsets: a fixed count evenly spread, and every sub-frame an adaptive run may render', () => {
  expect(shutterOffsets(1)).toEqual([0]);
  expect(shutterOffsets(4)).toEqual([-0.375, -0.125, 0.125, 0.375]);
  const a = shutterOffsets({ min: 4, max: 324, tol: 3 });
  expect(a.length).toBe(324);
  // a lower max (an entry's maxSamples) runs a prefix of the same order, and each step's prefix is evenly spread
  expect(shutterOffsets({ min: 12, max: 108, tol: 3 })).toEqual(a.slice(0, 108));
  for (const n of [4, 12, 36, 108, 324]) {
    expect([...a.slice(0, n)].sort((x, y) => x - y)).toEqual(shutterOffsets(n).map((x) => expect.closeTo(x, 12)));
  }
});

// ------------------------------------------------------------------ a stand-in engine that renders (no WebGL)

/** A window of a stand-in timeline, and its scene class (none: a module that fails to load). */
interface Shot {
  id: string;
  start: number;
  end: number;
  scene?: SceneClass;
}

/**
 * A stand-in engine that runs the real prepare(), render(), composite() and exportFrames() over no-op GPU plumbing.
 * Export mode (`exporting`) starts with no scene loaded, as init({ exporting: true }) leaves it; the player has every
 * scene loaded. `only`: the ids --only loads (default all). `clears` records every clear colour (the red fill).
 */
async function standIn(shots: Shot[], o: { exporting?: boolean; only?: string[] } = {}) {
  const clears: number[][] = [];
  const tex = new THREE.Texture();
  const rt = () => ({ texture: tex, width: 1920, height: 1080 });
  const pass = () => ({ u: { src: { value: null }, a: { value: null }, b: { value: null }, k: { value: 0 } }, render() {} });
  const renderer = {
    getClearColor: (c: THREE.Color) => c.setRGB(0, 0, 0),
    getClearAlpha: () => 1,
    setRenderTarget() {},
    setClearColor: (c: THREE.Color) => void clears.push([c.r, c.g, c.b]),
    clear() {},
  };
  const audio = { beatAt: () => 0, barAt: () => 0, sample: () => ({}) };
  const timeline: TimelineEntry[] = shots.map(({ id, start, end, scene }) => ({
    id, start, end,
    load: () => (scene ? Promise.resolve({ default: scene }) : Promise.reject(new Error(`scene module not found: scenes/${id}.ts`))),
  }));
  const ctx = { renderer, audio, vo: {}, comp: { draw() {} }, W: 1920, H: 1080, id: '', params: {}, start: 0, end: 0 } as unknown as SceneCtx;
  const engine = Object.assign(Object.create(Engine.prototype), {
    renderer, audio, ctx, timeline, exporting: !!o.exporting, loaded: new Map(), errors: [], lastT: -1, lastSamples: 1,
    lastErrors: [], hudOff: false, rts: [rt(), rt(), rt()], mixRT: rt(), sumRT: rt(), newRT: rt(), avgRT: rt(), finalRT: rt(),
    accum: pass(), xfade: pass(), blit: pass(), comp: ctx.comp, hud: { draw: () => tex }, post: { render() {} },
    sampleError: () => 99, // an adaptive run never converges here: it renders every sub-frame up to its max
  }) as Engine;
  for (const entry of timeline.filter((e) => !o.only || o.only.includes(e.id))) {
    let scene: Scene | null = null;
    const cls = shots.find((s) => s.id === entry.id)!.scene;
    if (!o.exporting && cls) {
      scene = new cls({ ...ctx, id: entry.id, start: entry.start, end: entry.end });
      await scene.init();
    }
    engine.loaded.set(entry.id, { entry, scene, lastT: -1 });
  }
  return { engine, clears };
}

/**
 * A stand-in scene class that logs its life: `init a`, `render a <frame>` (at 30 fps; not its preroll), `dispose a`.
 * `plate`: a plate it shows (it prepares it, and reads it in render(): in export, a frame not loaded throws). `fail`:
 * its init fails, or its render() at the times given.
 */
function logged(id: string, log: string[], o: { plate?: () => Plate; fail?: 'init' | ((t: number) => boolean); stateful?: boolean } = {}): SceneClass {
  return class extends Scene {
    private plate = o.plate?.();
    override stateful = !!o.stateful;
    override init() {
      log.push(`init ${id}`);
      if (o.fail === 'init') throw new Error(`${id}: no track`);
    }
    override async prepare(t: number) {
      await this.plate?.prepare(t);
    }
    render(f: Frame) {
      if (!f.preroll) log.push(`render ${id} ${Math.round(f.t * 30)}`);
      this.plate?.texture(f.t);
      if (typeof o.fail === 'function' && o.fail(f.t)) throw new Error(`${id} broke`);
    }
    override dispose() {
      log.push(`dispose ${id}`);
      this.plate?.dispose();
    }
  };
}

/** A plate loader that serves `have` (or every frame), recording what it loaded and what was disposed. */
function fakeLoader(have?: (url: string) => boolean) {
  const calls: string[] = [];
  const disposed: string[] = [];
  const load = async (url: string, _kind: PlateKind) => {
    if (have && !have(url)) throw new Error(`404 ${url}`);
    calls.push(url);
    const tex = new THREE.Texture();
    tex.name = url;
    tex.addEventListener('dispose', () => disposed.push(url));
    return tex;
  };
  return { load, calls, disposed };
}

const range = (a: number, b: number) => Array.from({ length: b - a }, (_, i) => a + i);

/** Keeps what the engine logs about failing scenes out of the test output; returns the restore. */
function quiet() {
  const e = spyOn(console, 'error').mockImplementation(() => {});
  const w = spyOn(console, 'warn').mockImplementation(() => {});
  return () => (e.mockRestore(), w.mockRestore());
}

test('prepare() covers render(): every sub-frame of every frame finds its plate frame loaded (fps 24 to 60, shutter to 1, fixed and adaptive)', async () => {
  const rand = mulberry32(11);
  const samplings: (number | AdaptiveSampling)[] = [1, 2, 3, 4, 5, 8, 12, { min: 4, max: 36, tol: 3 }, { min: 12, max: 108, tol: 3 }, { min: 4, max: 324, tol: 3 }];
  // per fps, the most plate frames one film frame needed: what an export's plate cache must hold between its prepare()
  // and its render()
  const most: Record<number, number> = {};
  for (const fps of [24, 25, 30, 60]) {
    for (const shutter of [0.05, 0.3, 0.5, 0.8, 0.9, 1]) {
      for (const samples of samplings) {
        const seen = new Map<string, Set<number>>();
        const plated = (id: string): SceneClass => class extends Scene {
          // an export plate (the default cap) whose shot starts with its window
          private plate = new Plate(id, Math.round(this.ctx.start * 30), { mode: 'export', load: fakeLoader().load });
          override async prepare(t: number) {
            await this.plate.prepare(t);
          }
          render(f: Frame) {
            this.plate.texture(f.t); // throws on a plate frame not loaded
            seen.get(id)!.add(this.plate.index(f.t));
          }
        };
        // cuts exactly on a frame time, 1 ms after one, and at random, and an overlay across them all
        const c1 = 1, c2 = c1 + 7 / fps + 0.001, c3 = c2 + 0.2 + 0.3 * rand();
        const shots = [
          { id: 'a', start: 0, end: c1 }, { id: 'b', start: c1, end: c2 }, { id: 'c', start: c2, end: c3 }, { id: 'd', start: c3, end: 3 },
          { id: 'over', start: 0, end: 3 },
        ].map((s) => ({ ...s, scene: plated(s.id) }));
        const { engine } = await standIn(shots, { exporting: true });
        // an export's frames around each cut, in order
        for (const n of [c1, c2, c3].flatMap((c) => range(Math.round(c * fps) - 3, Math.round(c * fps) + 4))) {
          // (prepare() renders a scene's first frame once, off-screen, as its warm-up: the same frame's plate frames)
          for (const s of shots) seen.set(s.id, new Set());
          await engine.prepare(n / fps, 1 / fps, samples, shutter);
          engine.render(n / fps, 1 / fps, false, samples, shutter);
          for (const s of seen.values()) most[fps] = Math.max(most[fps] ?? 0, s.size);
        }
      }
    }
  }
  // 30·shutter/fps plate frames pass per film frame: one plate frame at 30 fps, two at 60, three at 24 and 25 with a
  // shutter over 0.8 (so the export cache keeps 3, not 2)
  expect(most).toEqual({ 24: 3, 25: 3, 30: 1, 60: 2 });
});

test('render: a sub-frame held at the end of its window gets dt = 0 (no time passes for it)', async () => {
  const dts: number[][] = [];
  class Rec extends Scene {
    render(f: Frame) {
      dts.push([f.t, f.dt]);
    }
  }
  const { engine } = await standIn([{ ...ex, scene: Rec }, { ...her, scene: Rec }]);
  engine.render(467 / 30, 1 / 30, false, 36, 0.5);
  dts.length = 0;
  // frame 468's last sub-frame (15.6 + 0.486 / 60) is past the cut: ex holds just before it
  engine.render(468 / 30, 1 / 30, false, 36, 0.5);
  expect(dts.slice(0, 35).map(([, dt]) => dt)).toEqual(Array(35).fill(expect.closeTo(1 / 30 / 36, 15)));
  expect(dts[35]).toEqual([CUT - EPS, 0]);
});

test('export: a scene whose render() throws fails the frame and the export, the error recorded; the player shows red', async () => {
  const restore = quiet();
  const shots = [{ id: 'a', start: 0, end: 1, scene: logged('a', [], { fail: (t) => t >= 0.5 }) }];
  const { engine } = await standIn(shots, { exporting: true });
  await engine.prepare(0.4);
  engine.render(0.4, 1 / 30, false);
  await engine.prepare(0.5);
  expect(() => engine.render(0.5, 1 / 30, false)).toThrow('scene a render(0.5) failed: a broke');
  expect(engine.errors).toEqual([expect.stringContaining('[a] render(0.5): Error: a broke')]);
  // the export sends frames 0…14 and rejects at frame 15 (t = 0.5): nothing after it goes out
  const sent: number[] = [];
  const e2 = (await standIn(shots, { exporting: true })).engine;
  await expect(e2.exportFrames({ from: 0, to: 1, fps: 30 }, (n) => void sent.push(n))).rejects.toThrow('scene a render(0.5) failed');
  expect(sent).toEqual(range(0, 15));
  // the player keeps going, the frame filled red
  const { engine: player, clears } = await standIn(shots);
  expect(() => player.render(0.5, 1 / 30, false)).not.toThrow();
  expect(clears).toContainEqual([0.25, 0, 0]);
  restore();
});

test('render: a stateful scene that throws while it is fast-forwarded (preroll) fails like any render error', async () => {
  const restore = quiet();
  const shots = [{ id: 's', start: 0, end: 2, scene: logged('s', [], { stateful: true, fail: (t) => t < 0.2 }) }];
  // a seek to 1 fast-forwards it from 0, where it throws
  const { engine } = await standIn(shots, { exporting: true });
  await engine.prepare(1);
  expect(() => engine.render(1, 1 / 30, false)).toThrow('scene s render(1) failed: s broke');
  const { engine: player, clears } = await standIn(shots);
  expect(() => player.render(1, 1 / 30, false)).not.toThrow();
  expect(clears).toContainEqual([0.25, 0, 0]);
  restore();
});

test('export: a scene whose init() fails rejects the still, and fails an export before its first frame', async () => {
  const restore = quiet();
  const log: string[] = [];
  const shots = [{ id: 'a', start: 0, end: 1, scene: logged('a', log) }, { id: 'b', start: 1, end: 2, scene: logged('b', log, { fail: 'init' }) }];
  const { engine } = await standIn(shots, { exporting: true });
  await expect(engine.prepare(1.5)).rejects.toThrow('scene b init failed: b: no track');
  expect(engine.errors).toEqual([expect.stringContaining('[b] init: Error: b: no track')]);
  // an export of both fails before a's first frame goes out, not when it reaches b
  const sent: number[] = [];
  const e2 = (await standIn(shots, { exporting: true })).engine;
  await expect(e2.exportFrames({ from: 0, to: 2, fps: 30 }, (n) => void sent.push(n))).rejects.toThrow('scene b init failed');
  expect(sent).toEqual([]);
  // so does a scene whose module does not load
  const e3 = (await standIn([{ id: 'c', start: 0, end: 1 }], { exporting: true })).engine;
  await expect(e3.prepare(0.5)).rejects.toThrow('scene c init failed: scene module not found: scenes/c.ts');
  restore();
});

test('export: the warm-up frame before the range is best effort: a plate frame the range never shows cannot fail it', async () => {
  const restore = quiet();
  const log: string[] = [];
  const none = fakeLoader(() => false); // a's plate has no frames at all
  const shots = [
    { id: 'a', start: 0, end: 1.01, scene: logged('a', log, { plate: () => new Plate('a', 0, { mode: 'export', load: none.load }) }) },
    { id: 'b', start: 1.01, end: 2, scene: logged('b', log) },
  ];
  const { engine } = await standIn(shots, { exporting: true });
  const sent: number[] = [];
  // b's frames 31…59 (a owns 0…30, so the warm-up frame, 30, is a's)
  expect(await engine.exportFrames({ from: 31 / 30, to: 2, fps: 30 }, (n) => void sent.push(n))).toEqual({ 1: 29 });
  expect(sent).toEqual(range(31, 60));
  expect(engine.errors).toEqual([]);
  // (b's window ends where the range does, at 2: it goes after its last frame too)
  // (b's first frame renders twice: its warm-up, off-screen, then the frame)
  expect(log).toEqual(['init a', 'dispose a', 'init b', 'render b 31', ...range(31, 60).map((n) => `render b ${n}`), 'dispose b']);
  restore();
});

test('export: each scene loads just before its first frame and is disposed after its last, its plate frames with it', async () => {
  const log: string[] = [];
  const L = fakeLoader();
  const shots = [
    { id: 'a', start: 0, end: 1.01, scene: logged('a', log, { plate: () => new Plate('a', 0, { mode: 'export', load: L.load }) }) },
    { id: 'b', start: 1.01, end: 2, scene: logged('b', log) },
    { id: 'c', start: 2, end: 3, scene: logged('c', log) },
  ];
  const { engine } = await standIn(shots, { exporting: true });
  await engine.exportFrames({ from: 28 / 30, to: 33 / 30, fps: 30 }, (n) => void log.push(`sent ${n}`));
  expect(log).toEqual([
    'init b', 'dispose b', // the check: a later scene of the range inits once before any frame goes out (c has none)
    'init a', 'render a 27', 'render a 27', // a's warm-up (off-screen), then the range's warm-up frame
    'render a 28', 'sent 28', 'render a 29', 'sent 29', 'render a 30', 'sent 30',
    'dispose a', // after its last frame (its window ends at 1.01, before frame 31)
    'init b', 'render b 31', 'render b 31', 'sent 31', 'render b 32', 'sent 32', // b's warm-up, then its first frame
  ]);
  expect(L.calls.length).toBe(4); // plate frames 27…30, each loaded once
  expect([...L.disposed].sort()).toEqual([...L.calls].sort()); // and each released
});

test('export stills: a scene loads when a frame first needs it and stays loaded; --only leaves the others red', async () => {
  const restore = quiet();
  const log: string[] = [];
  const shots = [{ id: 'a', start: 0, end: 1, scene: logged('a', log) }, { id: 'b', start: 1, end: 2, scene: logged('b', log) }];
  const { engine } = await standIn(shots, { exporting: true });
  for (const t of [1.5, 0.5, 1.6]) {
    await engine.prepare(t);
    engine.render(t, 1 / 30, false);
  }
  // (each scene's first frame renders twice: its warm-up, off-screen, then the still)
  expect(log).toEqual(['init b', 'render b 45', 'render b 45', 'init a', 'render a 15', 'render a 15', 'render b 48']);
  // a scene --only left out renders red, as documented; a loaded one rendered without its prepare() is an error
  const { engine: only, clears } = await standIn(shots, { exporting: true, only: ['b'] });
  expect(() => only.render(0.5, 1 / 30, false)).not.toThrow();
  expect(clears).toContainEqual([0.25, 0, 0]);
  expect(() => only.render(1.5, 1 / 30, false)).toThrow('scene b render(1.5) failed');
  restore();
});

test('export: a scene\'s first frame renders once off-screen first (its warm-up), with the frame\'s own sampling and seek state', async () => {
  const frames: string[] = [];
  class Rec extends Scene {
    render(f: Frame) {
      frames.push(`${this.ctx.id} ${f.t.toFixed(4)} dt ${f.dt.toFixed(5)}${f.seeked ? ' seeked' : ''}`);
    }
  }
  const shots = [{ id: 'a', start: 0, end: 1, scene: Rec }, { id: 'b', start: 1, end: 2, scene: Rec }];
  const { engine } = await standIn(shots, { exporting: true });
  await engine.prepare(0.5, 1 / 30, 4, 0.5);
  const warm = [...frames];
  frames.length = 0;
  engine.render(0.5, 1 / 30, false, 4, 0.5);
  // the warm-up is the frame itself: its four sub-frames, the first a seek (dt 0), and the frame renders the same after it
  expect(warm).toHaveLength(4);
  expect(frames).toEqual(warm);
  expect(warm[0]).toContain('seeked');
  // once per load: the next frame has no warm-up, and stays sequential
  frames.length = 0;
  await engine.prepare(0.5 + 1 / 30, 1 / 30, 4, 0.5);
  expect(frames).toEqual([]);
  engine.render(0.5 + 1 / 30, 1 / 30, false, 4, 0.5);
  expect(frames.some((x) => x.includes('seeked'))).toBe(false);
});

test('export: no warm-up in the player, or while a stateful scene is on screen (it would step twice)', async () => {
  const log: string[] = [];
  const player = (await standIn([{ id: 'a', start: 0, end: 1, scene: logged('a', log) }])).engine;
  await player.prepare(0.5);
  expect(log).toEqual(['init a']); // (the player inits every scene up front)
  const slog: string[] = [];
  const { engine } = await standIn([{ id: 's', start: 0, end: 1, scene: logged('s', slog, { stateful: true }) }], { exporting: true });
  await engine.prepare(0.5);
  expect(slog).toEqual(['init s']);
});

test('export: a scene disposed and loaded again warms up again', async () => {
  const log: string[] = [];
  const shots = [{ id: 'a', start: 0, end: 1, scene: logged('a', log) }, { id: 'b', start: 1, end: 2, scene: logged('b', log) }];
  const { engine } = await standIn(shots, { exporting: true });
  await engine.exportFrames({ from: 29 / 30, to: 31 / 30, fps: 30 }, () => {});
  await engine.exportFrames({ from: 29 / 30, to: 30 / 30, fps: 30 }, () => {});
  expect(log.filter((x) => x === 'render a 28')).toHaveLength(4); // each export's warm-up frame, after a's warm-up
});
