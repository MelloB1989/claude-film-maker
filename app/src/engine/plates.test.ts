import { expect, spyOn, test } from 'bun:test';
import * as THREE from 'three';
import { LRU, Plate, plateIndex, type PlateKind } from './plates';
import { Track } from './track';

// Expected values are hand-derived: film frame n is t = n / 30, a plate's file index is n - f0, and a track holds one
// anchor sample per film frame from its f0.

test('plateIndex: film frame round(t * 30) minus the plate f0, a half frame rounding up', () => {
  expect(plateIndex(47 / 30, 40)).toBe(7);
  expect(plateIndex(46.5 / 30, 40)).toBe(7); // Math.round(46.5) = 47 (half-even rounding would say 46)
  expect(plateIndex(47.5 / 30, 40)).toBe(8);
  expect(plateIndex(47.49 / 30, 40)).toBe(7);
  expect(plateIndex(40 / 30, 40)).toBe(0);
  expect(plateIndex(0, 0)).toBe(0);
});

test("plateIndex: every sub-frame of a 0.5 shutter shows the frame's own plate", () => {
  // the engine spreads sub-frames over t ± 0.25 frame at shutter 0.5: the plate carries its own motion blur
  for (const u of [-0.2499, -0.125, 0, 0.125, 0.2499]) expect(plateIndex((47 + u) / 30, 40)).toBe(7);
});

test('LRU: a get refreshes an entry, and a set past the cap evicts the least recently used', () => {
  const evicted: string[] = [];
  const lru = new LRU<string, number>(3, (_v, k) => evicted.push(k));
  lru.set('a', 1);
  lru.set('b', 2);
  lru.set('c', 3);
  expect(lru.get('a')).toBe(1); // a is now the most recent
  lru.set('d', 4);
  expect(evicted).toEqual(['b']);
  expect(lru.keys()).toEqual(['c', 'a', 'd']);
  lru.set('e', 5);
  lru.set('f', 6);
  expect(evicted).toEqual(['b', 'c', 'a']);
  expect(lru.keys()).toEqual(['d', 'e', 'f']);
  expect(lru.has('a')).toBe(false);
  expect(lru.get('a')).toBeUndefined();
});

/** A loader that serves `have` (or everything) and records what was asked for. */
function fakeLoader(have?: (url: string) => boolean) {
  const calls: string[] = [];
  const disposed: string[] = [];
  const load = async (url: string, _kind: PlateKind) => {
    calls.push(url);
    if (have && !have(url)) throw new Error(`404 ${url}`);
    const tex = new THREE.Texture();
    tex.name = url;
    tex.addEventListener('dispose', () => disposed.push(url));
    return tex;
  };
  return { load, calls, disposed };
}

const proxy = (i: number) => `plates/_cube/proxy/${String(i).padStart(4, '0')}.png`;
const exr = (i: number) => `out/plates/_cube/${String(i).padStart(4, '0')}.exr`;
const at = (n: number) => n / 30; // film frame n
const flush = () => new Promise((r) => setTimeout(r, 0));

test('Plate (export): prepare(t) loads the EXR of frame round(t * 30) - f0, and texture(t) is that frame', async () => {
  const L = fakeLoader();
  const p = new Plate('_cube', 40, { mode: 'export', load: L.load });
  await p.prepare(at(47));
  expect(L.calls).toEqual([exr(7)]);
  expect(p.texture(at(47))!.name).toBe(exr(7));
  expect(p.texture((47 + 0.2) / 30)!.name).toBe(exr(7)); // a sub-frame of frame 47
});

test('Plate (export): an unprepared frame throws instead of showing a neighbour', async () => {
  const L = fakeLoader();
  const p = new Plate('_cube', 40, { mode: 'export', load: L.load });
  await p.prepare(at(47));
  expect(() => p.texture(at(48))).toThrow('not prepared');
});

test('Plate (export): a missing EXR fails, naming it, and never falls back to the proxy unless proxies are opted into', async () => {
  const L = fakeLoader((url) => url.endsWith('.png'));
  const p = new Plate('_cube', 40, { mode: 'export', load: L.load });
  await expect(p.prepare(at(47))).rejects.toThrow(`plate _cube frame 7 (film frame 47): no ${exr(7)}`);
  expect(L.calls).toEqual([exr(7)]);
  expect(() => p.texture(at(47))).toThrow('not prepared');
});

test('Plate (export, proxies opted into): the proxy stands in for a missing EXR, with one warning; a frame missing both rejects', async () => {
  const warn = spyOn(console, 'warn').mockImplementation(() => {});
  const L = fakeLoader((url) => url.endsWith('.png'));
  const p = new Plate('_cube', 40, { mode: 'export', proxies: true, load: L.load });
  await p.prepare(at(47));
  await p.prepare(at(48));
  expect(L.calls).toEqual([exr(7), proxy(7), exr(8), proxy(8)]);
  expect(p.texture(at(47))!.name).toBe(proxy(7));
  expect(warn.mock.calls.map((c) => String(c[0]))).toEqual([expect.stringContaining(`plate _cube: no EXR for frame 7 (${exr(7)})`)]);
  warn.mockRestore();
  const none = new Plate('_cube', 40, { mode: 'export', proxies: true, load: fakeLoader(() => false).load });
  await expect(none.prepare(at(47))).rejects.toThrow('_cube frame 7');
});

test('Plate (export): a plate smaller than the output warns once (it is upscaled); one at least its size does not', async () => {
  const warn = spyOn(console, 'warn').mockImplementation(() => {});
  const sized = (w: number, h: number) => async (url: string) => {
    const tex = new THREE.Texture();
    tex.name = url;
    tex.image = { width: w, height: h };
    return tex;
  };
  const small = new Plate('_cube', 40, { mode: 'export', output: [3840, 2160], load: sized(2560, 1440) });
  for (let n = 40; n < 44; n++) await small.prepare(at(n));
  expect(warn.mock.calls.map((c) => String(c[0]))).toEqual([expect.stringContaining('plate _cube is 2560x1440, smaller than the 3840x2160 output')]);
  warn.mockClear();
  const big = new Plate('_cube', 40, { mode: 'export', output: [1920, 1080], load: sized(2560, 1440) });
  await big.prepare(at(40));
  expect(warn).not.toHaveBeenCalled();
  warn.mockRestore();
});

test('Plate: a frame is loaded once, however often and however concurrently it is prepared', async () => {
  const L = fakeLoader();
  const p = new Plate('_cube', 40, { mode: 'export', load: L.load });
  await Promise.all([p.prepare(at(47)), p.prepare(at(47)), p.prepare((47 + 0.2) / 30)]);
  await p.prepare(at(47));
  expect(L.calls).toEqual([exr(7)]);
});

test('Plate (preview): at most 8 textures are kept; the least recently used are disposed first', async () => {
  const L = fakeLoader();
  const p = new Plate('_cube', 40, { mode: 'preview', ahead: 0, load: L.load });
  for (let n = 40; n < 50; n++) await p.prepare(at(n)); // frames 0..9
  expect(L.disposed).toEqual([proxy(0), proxy(1)]);
  expect(p.texture(at(42))!.name).toBe(proxy(2));
  // frame 2 was just used, so the next load evicts frame 3, not 2
  await p.prepare(at(50));
  expect(L.disposed).toEqual([proxy(0), proxy(1), proxy(3)]);
  p.dispose(); // releases the 8 still held
  expect([...L.disposed].sort()).toEqual([...L.calls].sort());
});

test('Plate (export): at most 3 textures are kept (the most one film frame needs: engine.test.ts), the stalest disposed first', async () => {
  const L = fakeLoader();
  const p = new Plate('_cube', 40, { mode: 'export', load: L.load });
  for (let n = 40; n < 45; n++) await p.prepare(at(n)); // frames 0..4
  expect(L.disposed).toEqual([exr(0), exr(1)]);
  expect(() => p.texture(at(41))).toThrow('not prepared');
  expect(p.texture(at(42))!.name).toBe(exr(2));
  // frame 2 was just used, so the next load evicts frame 3, not 2
  await p.prepare(at(45));
  expect(L.disposed).toEqual([exr(0), exr(1), exr(3)]);
  p.dispose(); // releases the 3 still held
  expect([...L.disposed].sort()).toEqual([...L.calls].sort());
});

test('Plate: a frame that finishes loading after dispose() is released, not kept', async () => {
  let land!: () => void;
  const gate = new Promise<void>((r) => (land = r));
  const L = fakeLoader();
  const p = new Plate('_cube', 40, { mode: 'preview', ahead: 0, load: async (url, kind) => (await gate, L.load(url, kind)) });
  const loading = p.prepare(at(42)); // (the player prefetches without waiting)
  p.dispose();
  land();
  await loading;
  expect(L.disposed).toEqual([proxy(2)]);
});

test('Plate (preview): proxies, prefetching ahead; an unloaded frame shows the nearest loaded one', async () => {
  const L = fakeLoader();
  const p = new Plate('_cube', 40, { mode: 'preview', load: L.load });
  expect(p.texture(at(45))).toBeNull(); // nothing loaded yet
  await p.prepare(at(42));
  await flush(); // the prefetches land
  expect(L.calls).toEqual([proxy(2), proxy(3), proxy(4)]); // the frame, then two ahead
  expect(p.texture(at(42))!.name).toBe(proxy(2));
  expect(p.texture(at(49))!.name).toBe(proxy(4)); // nearest: 4
  expect(p.texture(at(40))!.name).toBe(proxy(2));
  const q = new Plate('_cube', 40, { mode: 'preview', ahead: 0, load: fakeLoader().load });
  await q.prepare(at(42));
  await q.prepare(at(44));
  expect(q.texture(at(43))!.name).toBe(proxy(2)); // a tie goes to the earlier frame
});

test('Plate: with a frame count, times before and after the plate hold its first and last frames', async () => {
  const L = fakeLoader();
  const p = new Plate('_cube', 40, { mode: 'export', count: 20, load: L.load });
  await p.prepare(at(30));
  await p.prepare(at(75));
  expect(L.calls).toEqual([exr(0), exr(19)]);
  expect(p.texture(at(12))!.name).toBe(exr(0));
  expect(p.texture(at(60))!.name).toBe(exr(19));
});

const TRACK = {
  fps: 30,
  f0: 40,
  anchors: {
    corner: [[100, 200, 1], [130, 180, 1], [160, 160, 0], [161, 159, 0]] as [number, number, number][],
  },
};

test('Track.at: the sample of film frame n at t = n / 30', () => {
  const tr = new Track(TRACK);
  expect(tr.at('corner', at(40))).toEqual({ x: 100, y: 200, visible: 1 });
  expect(tr.at('corner', at(41))).toEqual({ x: 130, y: 180, visible: 1 });
  expect(tr.at('corner', at(42))).toEqual({ x: 160, y: 160, visible: 0 });
});

test('Track.at: linear between frames, visibility fading between a visible and a hidden frame', () => {
  const tr = new Track(TRACK);
  const a = tr.at('corner', 40.5 / 30);
  expect(a.x).toBeCloseTo(115, 9);
  expect(a.y).toBeCloseTo(190, 9);
  expect(a.visible).toBeCloseTo(1, 9);
  const b = tr.at('corner', 41.25 / 30);
  expect(b.x).toBeCloseTo(137.5, 9);
  expect(b.y).toBeCloseTo(175, 9);
  expect(b.visible).toBeCloseTo(0.75, 9);
});

test('Track.at: holds the first and last samples outside the track, and rejects an unknown anchor', () => {
  const tr = new Track(TRACK);
  expect(tr.at('corner', at(10))).toEqual({ x: 100, y: 200, visible: 1 });
  expect(tr.at('corner', at(90))).toEqual({ x: 161, y: 159, visible: 0 });
  expect(() => tr.at('nope', at(40))).toThrow('nope');
  expect(tr.f0).toBe(40);
  expect(tr.frames).toBe(4);
});
