// Light on a panel (panel-light.ts): each overlay is a plane a hair in front of the panel's face, placed in panel px
// (from its top left, y down: x/1000 - w/2000 across, h/2000 - y/1000 up, as the panel's own mesh is laid out),
// drawn after it with no depth write.
import { expect, test } from 'bun:test';
import * as THREE from 'three';
import { Bar, Blade, Halo, OVER, Spot, Wash } from './panel-light';
import { glow } from './look';
import { LIN } from './palette';

const P = { w: 640, h: 400 };
const close = (a: readonly number[], b: readonly number[]) => a.forEach((x, i) => expect(x).toBeCloseTo(b[i]!, 9));
const mat = (m: THREE.Mesh) => m.material as THREE.ShaderMaterial;
const u = (m: THREE.Mesh, k: string) => mat(m).uniforms[k]!.value;

test('every light is unlit, added over the panel after it (renderOrder), and writes no depth', () => {
  const lights = [new Blade(P, 1.4, 10), new Halo(P, 'blood', 1), new Wash(P), new Bar(P, 'moss'), new Spot(P)];
  for (const l of lights) {
    expect(mat(l.mesh).depthWrite).toBe(false);
    expect(mat(l.mesh).transparent).toBe(true);
    expect(l.mesh.frustumCulled).toBe(false);
  }
  expect(lights.slice(0, 4).map((l) => [l.mesh.renderOrder, mat(l.mesh).blending])).toEqual(Array(4).fill([OVER, THREE.AdditiveBlending]));
  // the spot darkens outside its pool: premultiplied over, after the other lights
  const s = mat(lights[4]!.mesh);
  expect([lights[4]!.mesh.renderOrder, s.blending, s.blendSrc, s.blendDst]).toEqual([OVER + 1, THREE.CustomBlending, THREE.OneFactor, THREE.OneMinusSrcAlphaFactor]);
  for (const l of lights) l.dispose();
});

test('Blade: from its tail to its tip along y, in the glow\'s colour; hidden until it is longer than a px and a half', () => {
  const b = new Blade(P, 1.4, 10);
  expect((u(b.mesh, 'uColor') as THREE.Vector3).toArray()).toEqual(glow('blood', 1));
  b.set(100, 300, 210, 0.7, 1.16);
  close(b.mesh.position.toArray(), [(100 - 320) / 1000, (200 - 210) / 1000, 0.6 / 1000]);
  close(b.mesh.scale.toArray(), [(200 + 14) / 1000, 20 / 1000, 1]); // the plane reaches 14 px past the tip, for the head's light
  expect([u(b.mesh, 'uLen'), u(b.mesh, 'uHeat'), u(b.mesh, 'uEmber'), u(b.mesh, 'uHot')]).toEqual([200, 0.7, 1.16, 3.6]);
  expect(b.mesh.visible).toBe(true);
  b.set(100, 101.5, 210, 1, 1);
  expect(b.mesh.visible).toBe(false);
  b.dispose();
});

test('Halo: a round glow centred on a point, its level a glow() level; off at 0', () => {
  const h = new Halo(P, 'moss', 13);
  h.set(150, 320, 1.25);
  close(h.mesh.position.toArray(), [(150 - 320) / 1000, (200 - 320) / 1000, 0.5 / 1000]);
  close(h.mesh.scale.toArray(), [0.026, 0.026, 1]);
  expect(u(h.mesh, 'uLevel')).toBe(1.25);
  expect((u(h.mesh, 'uColor') as THREE.Vector3).toArray()).toEqual(glow('moss', 1));
  h.set(150, 320, 0);
  expect(h.mesh.visible).toBe(false);
  h.dispose();
});

test('Wash: a box of faint bone light from (x0, y0) to (x1, y1); Bar: a sign the height of its row', () => {
  const w = new Wash(P);
  w.set(0, 300, 640, 338.5, 0.007, 0.05);
  close(w.mesh.position.toArray(), [0, (200 - 319.25) / 1000, 0.4 / 1000]);
  close(w.mesh.scale.toArray(), [0.64, 0.0385, 1]);
  expect((u(w.mesh, 'uColor') as THREE.Vector3).toArray()).toEqual([...LIN.bone]);
  expect([u(w.mesh, 'uLevel'), u(w.mesh, 'uEdge')]).toEqual([0.007, 0.05]);
  w.set(0, 300, 0.2, 338.5, 0.5);
  expect(w.mesh.visible).toBe(false); // narrower than a quarter px
  const b = new Bar(P, 'blood');
  b.set(11, 300, 338.5, 2.6);
  close(b.mesh.position.toArray(), [(11 - 320) / 1000, (200 - 319.25) / 1000, 0.5 / 1000]);
  close(b.mesh.scale.toArray(), [0.014, 0.0385, 1]);
  expect(b.mesh.visible).toBe(true);
  b.set(11, 300, 300.5, 2.6);
  expect(b.mesh.visible).toBe(false); // a row not yet a px open
  w.dispose();
  b.dispose();
});

test('Spot: covers the whole panel, its pool where it is set; off at 0', () => {
  const s = new Spot(P);
  s.mesh.geometry.computeBoundingBox();
  const bb = s.mesh.geometry.boundingBox!;
  expect(bb.max.x - bb.min.x).toBeCloseTo(0.64, 6); // positions are float32
  expect(bb.max.y - bb.min.y).toBeCloseTo(0.4, 6);
  s.set(290, 330, 340, 92, 0.6);
  expect((u(s.mesh, 'uCentre') as THREE.Vector2).toArray()).toEqual([290, 330]);
  expect((u(s.mesh, 'uRadius') as THREE.Vector2).toArray()).toEqual([340, 92]);
  expect(s.mesh.visible).toBe(true);
  s.set(290, 330, 340, 92, 0);
  expect(s.mesh.visible).toBe(false);
  s.dispose();
});
