import { expect, test } from 'bun:test';
import * as THREE from 'three';
import { beadGeometry, beadProfile, type BeadShape } from './bead';

// her's bead (her.ts): a 24 mm sphere on the 4.2 mm thread, its band centred where shot 2's camera looks, raised 0.4 rad
const HER: BeadShape = {
  radius: 0.024, bore: 0.0042 * 1.3, chamfer: 0.0042 * 0.7,
  centre: [Math.atan2(-0.118, 0.216), Math.atan2(0.02, Math.hypot(0.216, -0.118)) + 0.4],
};
// a plain one: the band on the face, a wide bore, and a band that nearly reaches the lips
const PLAIN: BeadShape = { radius: 1, bore: 0.2, chamfer: 0.1 };
const WIDE: BeadShape = { radius: 1, bore: 0.3, chamfer: 0.15, span: [1.3, 0.4], centre: [0.2, -0.1] };

/** Each triangle's corners: vertex index, position, normal, UV. */
function corners(geo: THREE.BufferGeometry) {
  const P = geo.getAttribute('position'), N = geo.getAttribute('normal'), UV = geo.getAttribute('uv'), I = geo.getIndex()!;
  const out: { i: number; p: number[]; n: number[]; uv: [number, number] }[][] = [];
  for (let t = 0; t < I.count; t += 3) {
    out.push([0, 1, 2].map((k) => {
      const i = I.getX(t + k);
      return { i, p: [P.getX(i), P.getY(i), P.getZ(i)], n: [N.getX(i), N.getY(i), N.getZ(i)], uv: [UV.getX(i), UV.getY(i)] as [number, number] };
    }));
  }
  return out;
}

test('no triangle of the bead smears the engraving: one that reaches the band spans only its own patch of it', () => {
  // the band is UV [0, 1]²; a lathe step moves a UV by about 0.02 along the band and 0.07 across it
  for (const o of [HER, PLAIN, WIDE]) {
    const bad: string[] = [];
    for (const tri of corners(beadGeometry(o))) {
      const us = tri.map((c) => c.uv[0]), vs = tri.map((c) => c.uv[1]);
      const reaches = Math.max(...us) >= 0 && Math.min(...us) <= 1 && Math.max(...vs) >= 0 && Math.min(...vs) <= 1;
      const span = Math.max(Math.max(...us) - Math.min(...us), Math.max(...vs) - Math.min(...vs));
      if (reaches && span > 0.25) bad.push(tri.map((c) => `(${c.uv[0].toFixed(2)}, ${c.uv[1].toFixed(2)})`).join(' '));
    }
    expect({ radius: o.radius, sweeps: bad.length, first: bad.slice(0, 3) }).toEqual({ radius: o.radius, sweeps: 0, first: [] });
  }
});

test('the bead is the same lathe, triangle for triangle: positions and normals, in the same order', () => {
  const lathe = new THREE.LatheGeometry(beadProfile(HER.radius, HER.bore, HER.chamfer), 160).rotateZ(-Math.PI / 2);
  const want = corners(lathe), got = corners(beadGeometry(HER));
  expect(got.length).toBe(want.length);
  got.forEach((tri, t) => tri.forEach((c, k) => {
    expect(c.p).toEqual(want[t]![k]!.p);
    expect(c.n).toEqual(want[t]![k]!.n);
  }));
});

test('away from the back seam and the chamfers, every corner keeps the band UV of its own position (the face as before)', () => {
  const [A, B] = HER.span ?? [0.95, 0.3], [a0, b0] = HER.centre!, r = HER.radius;
  let checked = 0;
  for (const tri of corners(beadGeometry(HER))) {
    const on = tri.every((c) => Math.hypot(...c.p) > 0.97 * r);
    const as = tri.map((c) => Math.atan2(c.p[0]!, c.p[2]!));
    if (!on || Math.max(...as) - Math.min(...as) > Math.PI) continue;
    for (const c of tri) {
      const [x, y, z] = c.p as [number, number, number];
      // stored as float32: exactly the value the band's formula gives, rounded once
      expect(c.uv[0]).toBe(Math.fround(0.5 + (Math.atan2(x, z) - a0) / (2 * A)));
      expect(c.uv[1]).toBe(Math.fround(0.5 + (Math.asin(Math.max(-1, Math.min(1, y / r))) - b0) / (2 * B)));
    }
    checked++;
  }
  expect(checked).toBeGreaterThan(30000);
});
