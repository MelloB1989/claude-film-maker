import { expect, test } from 'bun:test';
import { Scene } from '../engine/scene';
import type { Frame } from '../engine/scene';
import { checkLayers, layerAlpha, layerFrame, layerParams, layerWindow, stackHandles } from './stack';

class A extends Scene {
  render() {}
}

test('checkLayers: a non-empty array of layers, each with a scene and sane values', () => {
  expect(checkLayers([{ scene: A }, { scene: () => Promise.resolve({ default: A }), blend: 'add', opacity: 0.5, start: 1, end: -0.5, fade: 0.2 }], 's', 4)).toHaveLength(2);
  expect(() => checkLayers(undefined, 's')).toThrow(/shot s: Stack needs `layers`/);
  expect(() => checkLayers([], 's')).toThrow(/non-empty/);
  expect(() => checkLayers([{}], 's')).toThrow(/layer 0: `scene`/);
  expect(() => checkLayers([{ scene: A }, { scene: A, blend: 'overlay' }], 's')).toThrow(/layer 1: blend is normal \| add \| screen \| multiply/);
  expect(() => checkLayers([{ scene: A, opacity: 1.5 }], 's')).toThrow(/opacity is 0..1/);
  expect(() => checkLayers([{ scene: A, start: '1' }], 's')).toThrow(/start is a number/);
  expect(() => checkLayers([{ scene: A, start: -1 }], 's')).toThrow(/start is >= 0/);
  expect(() => checkLayers([{ scene: A, start: 2, end: 1 }], 's', 4)).toThrow(/empty/);
  expect(() => checkLayers([{ scene: A, start: 3, end: -2 }], 's', 4)).toThrow(/empty/);
  expect(() => checkLayers([{ scene: A, params: [] }], 's')).toThrow(/params/);
  expect(() => checkLayers([{ scene: A, fade: -1 }], 's')).toThrow(/fade/);
});

test('layerWindow: s from the shot start, a negative end counts back from its end, missing edges are the shot\'s', () => {
  expect(layerWindow({}, 10, 14)).toEqual({ start: 10, end: 14, open: { start: true, end: true } });
  expect(layerWindow({ start: 0.5, end: 3 }, 10, 14)).toEqual({ start: 10.5, end: 13, open: { start: false, end: false } });
  expect(layerWindow({ end: -1 }, 10, 14)).toEqual({ start: 10, end: 13, open: { start: true, end: false } });
});

test('layerAlpha: shown in its window, an open edge never cuts (handles), fades only at given edges', () => {
  const open = layerWindow({}, 10, 14);
  expect(layerAlpha({}, open, 9.5)).toBe(1); // in the head: runs with the shot
  expect(layerAlpha({ opacity: 0.4 }, open, 14.3)).toBe(0.4);
  const w = layerWindow({ start: 1, end: 3 }, 10, 14);
  expect(layerAlpha({}, w, 10.99)).toBe(0);
  expect(layerAlpha({}, w, 11)).toBe(1);
  expect(layerAlpha({}, w, 13)).toBe(0); // [start, end)
  expect(layerAlpha({ fade: 0.5 }, w, 11)).toBe(0);
  expect(layerAlpha({ fade: 0.5 }, w, 11.25)).toBeCloseTo(0.5, 9);
  expect(layerAlpha({ fade: 0.5 }, w, 12)).toBe(1);
  expect(layerAlpha({ fade: 0.5 }, w, 12.75)).toBeCloseTo(0.5, 9);
  // a fade on an open edge does nothing there
  expect(layerAlpha({ fade: 0.5 }, layerWindow({ end: 3 }, 10, 14), 10)).toBe(1);
});

test('layerParams: the shot id, transparent above the first layer, the layer\'s own params win', () => {
  expect(layerParams({}, 0, 'open', 3)).toEqual({ shot: 'open', n: 3 });
  expect(layerParams({ params: { title: 'x' } }, 1, 'open')).toEqual({ shot: 'open', background: 'none', title: 'x' });
  expect(layerParams({ params: { background: 'theme' } }, 2, 'open').background).toBe('theme');
});

test('stackHandles: the smallest of the layers\'', () => {
  expect(stackHandles([{ head: 1, tail: 1 }, { head: 0.5, tail: 2 }, { head: 0.8, tail: 0.25 }])).toEqual({ head: 0.5, tail: 0.25 });
});

test('layerFrame: the layer\'s own window, and its clock shifted by offset with the grid read there', () => {
  const f = { t: 11, dt: 1 / 30, lt: 1, p: 0.25, start: 10, end: 14, seeked: false, preroll: false, beat: 22, bar: 5.5, beatPhase: 0, barPhase: 0.5, beatsPerBar: 4, a: {} } as unknown as Frame;
  const grid = { beatAt: (t: number) => t * 2, barAt: (t: number) => t / 2, beatsPerBar: 4 };
  const w = layerWindow({ start: 0.5 }, 10, 14);
  const g = layerFrame(f, w, 0, grid);
  expect([g.t, g.lt, g.start, g.end]).toEqual([11, 0.5, 10.5, 14]);
  expect(g.p).toBeCloseTo(0.5 / 3.5, 12);
  const h = layerFrame(f, w, 0.25, grid);
  expect([h.t, h.start, h.end, h.lt]).toEqual([11.25, 10.75, 14.25, 0.5]);
  expect(h.beat).toBe(22.5);
  expect(h.beatPhase).toBeCloseTo(0.5, 12);
});
