import { expect, test } from 'bun:test';
import { CARD_LAYOUTS, PANEL_LAYOUTS, boundsOf, cardPlacement, panelPlacements, slotAt } from './layout3d';
import { extrudeShapes } from './logo';
import * as THREE from 'three';

const sizes = [{ w: 1.1, h: 0.5 }, { w: 1.1, h: 0.4 }, { w: 0.9, h: 0.6 }];

test('panel layouts: one placement per panel, finite, and a pair side by side in landscape but stacked in a tall frame', () => {
  for (const l of PANEL_LAYOUTS) {
    for (const aspect of [16 / 9, 9 / 16, 1]) {
      const ps = panelPlacements(l, sizes, { aspect });
      expect(ps.length).toBe(sizes.length);
      for (const p of ps) for (const v of [...p.pos, ...p.rot]) expect(Number.isFinite(v)).toBe(true);
    }
  }
  const wide = panelPlacements('pair', sizes.slice(0, 2), { aspect: 16 / 9 });
  expect(wide[0]!.pos[0]).toBeLessThan(wide[1]!.pos[0]);
  expect(Math.abs(wide[0]!.pos[1] - wide[1]!.pos[1])).toBeLessThan(1e-9);
  const tall = panelPlacements('pair', sizes.slice(0, 2), { aspect: 9 / 16 });
  expect(tall[0]!.pos[1]).toBeGreaterThan(tall[1]!.pos[1]);
  // a stack recedes, the first in front
  const st = panelPlacements('stack', sizes, { aspect: 16 / 9 });
  expect(st[0]!.pos[2]).toBeGreaterThan(st[2]!.pos[2]);
  expect(() => panelPlacements('heap' as never, sizes, { aspect: 1 })).toThrow(/unknown panel layout/);
});

test('bounds: a box round the placed panels', () => {
  const b = boundsOf([{ pos: [0, 0, 0], rot: [0, 0, 0] }, { pos: [2, 1, -1], rot: [0, 0, 0] }], [{ w: 1, h: 1 }]);
  expect(b.w).toBeCloseTo(3, 6);
  expect(b.h).toBeCloseTo(2, 9);
  b.centre.forEach((v, i) => expect(v).toBeCloseTo([1, 0.5, -0.5][i]!, 6));
});

test('cards: the card at the slot is in front and square to the camera, its neighbours behind or aside', () => {
  const size = { w: 0.7, h: 0.56 };
  for (const l of CARD_LAYOUTS) {
    const front = cardPlacement(l, 2, 5, 2, size, 16 / 9);
    for (const v of [...front.pos, ...front.rot]) expect(Number.isFinite(v)).toBe(true);
    expect(front.rot[1]).toBeCloseTo(0, 9);
    if (l !== 'grid') {
      const next = cardPlacement(l, 3, 5, 2, size, 16 / 9);
      expect(next.pos[2]).toBeLessThanOrEqual(front.pos[2] + 1e-9);
    }
  }
  // the carousel turns smoothly: half a slot is half way
  const a = cardPlacement('carousel', 1, 5, 1.5, size, 1), b = cardPlacement('carousel', 2, 5, 1.5, size, 1);
  expect(a.pos[0]).toBeCloseTo(-b.pos[0], 9);
  expect(() => cardPlacement('pile' as never, 0, 1, 0, size, 1)).toThrow(/unknown card layout/);
});

test('slotAt: one slot per `every` beats from b0, eased, clamped to the last card', () => {
  const grid = { beatAt: (t: number) => t * 2, timeOfBeat: (b: number) => b / 2 }; // 120 BPM
  expect(slotAt(0, grid, 0, 2, 5)).toBe(0);
  expect(slotAt(0.99, grid, 0, 2, 5)).toBe(0);
  expect(slotAt(1, grid, 0, 2, 5)).toBeCloseTo(0, 9);
  expect(slotAt(1.5, grid, 0, 2, 5)).toBeCloseTo(1, 9);
  expect(slotAt(100, grid, 0, 2, 5)).toBe(4);
});

test('extrudeShapes: unit height, centred, its face at z = 0 running back to −depth, with the seam attribute', () => {
  const s = new THREE.Shape([new THREE.Vector2(10, 20), new THREE.Vector2(50, 20), new THREE.Vector2(50, 100), new THREE.Vector2(10, 100)]);
  const g = extrudeShapes([s], { x0: 10, y0: 20, x1: 50, y1: 100 }, 0.2, 0.01);
  const b = g.boundingBox!;
  expect(b.max.y - b.min.y).toBeCloseTo(1, 6);
  expect(b.max.x - b.min.x).toBeCloseTo(0.5, 6);
  expect((b.max.x + b.min.x) / 2).toBeCloseTo(0, 6);
  expect(b.max.z).toBeCloseTo(0, 6);
  expect(b.min.z).toBeCloseTo(-0.2, 6);
  const d = g.getAttribute('type3dDepth');
  expect(d.count).toBe(g.getAttribute('position').count);
  g.dispose();
});
