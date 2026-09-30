import { expect, test } from 'bun:test';
import * as THREE from 'three';
import { Thread } from './thread3d';

// Expected values are hand-derived (straight runs, a semicircle, the palette hex through the sRGB curve) or integrated
// here from three's own centripetal CatmullRomCurve3, never read back from thread3d.ts.
const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
/** A gentle S-curve that recedes in depth: it has an inflection near x = 0, where a Frenet frame would flip. */
const S_CURVE = [v(-0.6, -0.08, 0.1), v(-0.3, 0.06, 0.02), v(0, 0, 0), v(0.3, -0.06, -0.05), v(0.6, 0.08, -0.15)];
const R = 0.012;

/** The reference: arc length of three's centripetal Catmull-Rom through the points, by brute-force chords. */
function refLength(points: THREE.Vector3[], n = 200000) {
  const c = new THREE.CatmullRomCurve3(points, false, 'centripetal');
  const a = new THREE.Vector3(), b = new THREE.Vector3();
  let L = 0;
  c.getPoint(0, a);
  for (let i = 1; i <= n; i++) {
    c.getPoint(i / n, b);
    L += a.distanceTo(b);
    a.copy(b);
  }
  return L;
}

const semicircle = (r: number, n: number) =>
  Array.from({ length: n + 1 }, (_, i) => v(r * Math.cos((Math.PI * i) / n), r * Math.sin((Math.PI * i) / n), 0));

test('length() is the Catmull-Rom arc length: a straight run, a semicircle, and the S-curve within 1%', () => {
  expect(new Thread([v(0, 0, 0), v(1, 0, 0), v(3, 0, 0)], { radius: R }).length()).toBeCloseTo(3, 4);
  expect(Math.abs(new Thread(semicircle(1, 12), { radius: R }).length() / Math.PI - 1)).toBeLessThan(0.01);
  const L = refLength(S_CURVE);
  expect(Math.abs(new Thread(S_CURVE, { radius: R }).length() / L - 1)).toBeLessThan(0.01);
  // setPoints re-measures
  const t = new Thread(S_CURVE, { radius: R });
  t.setPoints([v(0, 0, 0), v(0, 2, 0)]);
  expect(t.length()).toBeCloseTo(2, 4);
});

test('setDraw(0, 0.5) opens the shader window on the first half of the arc length', () => {
  // unevenly spaced points on a straight line: curve parameter 0.5 is the middle point (x = 1), half the arc length is
  // x = 1.5. The window is in arc length, so it ends at 1.5.
  const t = new Thread([v(0, 0, 0), v(1, 0, 0), v(3, 0, 0)], { radius: R });
  t.setDraw(0, 0.5);
  expect(t.uniforms.uDraw.value.toArray()).toEqual([0, 0.5]);
  const end = t.pointAt(0.5);
  expect(end.x).toBeCloseTo(1.5, 2);
  expect(Math.hypot(end.y, end.z)).toBeLessThan(1e-9);
  // the samples the shader reads are evenly spaced along the arc, so any window [p0, p1] shows (p1 - p0) of the length
  const s = new Thread(S_CURVE, { radius: R });
  // the frame texture the vertex shader reads: row 0 holds the centreline points, sample i at arc fraction i / (M - 1)
  const data = s.frames.image.data as Float32Array, M = s.frames.image.width;
  const L = refLength(S_CURVE), step = L / (M - 1);
  for (let i = 1; i < M; i++) {
    const d = Math.hypot(data[4 * i]! - data[4 * (i - 1)]!, data[4 * i + 1]! - data[4 * (i - 1) + 1]!, data[4 * i + 2]! - data[4 * (i - 1) + 2]!);
    expect(Math.abs(d / step - 1)).toBeLessThan(0.01);
  }
  // the half-way sample splits the reference curve into two halves of equal arc length
  const c = new THREE.CatmullRomCurve3(S_CURVE, false, 'centripetal');
  const mid = s.pointAt(0.5);
  let best = 0, bestD = Infinity;
  for (let i = 0; i <= 20000; i++) {
    const d = c.getPoint(i / 20000).distanceTo(mid);
    if (d < bestD) { bestD = d; best = i / 20000; }
  }
  expect(bestD).toBeLessThan(1e-3);
  const a = new THREE.Vector3(), b = new THREE.Vector3();
  let L0 = 0;
  c.getPoint(0, a);
  for (let i = 1; i <= 100000; i++) {
    c.getPoint((best * i) / 100000, b);
    L0 += a.distanceTo(b);
    a.copy(b);
  }
  expect(Math.abs(L0 / (L / 2) - 1)).toBeLessThan(0.01);
});

test('setDraw clamps to [0, 1], and an empty window hides the thread', () => {
  const t = new Thread(S_CURVE, { radius: R });
  t.setDraw(-0.3, 1.4);
  expect(t.uniforms.uDraw.value.toArray()).toEqual([0, 1]);
  expect(t.mesh.visible).toBe(true);
  t.setDraw(0.6, 0.6);
  expect(t.mesh.visible).toBe(false);
  t.setDraw(0.7, 0.2);
  expect(t.mesh.visible).toBe(false);
  t.setDraw(0.2, 0.7);
  expect(t.mesh.visible).toBe(true);
});

test('the drawn end tapers to a point: at the end of the window the plies meet on the centreline', () => {
  const t = new Thread(S_CURVE, { radius: R, plies: 3, colors: ['bone', 'bone', 'bone'] });
  t.setDraw(0, 0.4);
  const tip = t.pointAt(0.4);
  for (let i = 0; i < 3; i++) expect(t.plyCentre(0.4, i).distanceTo(tip)).toBeLessThan(1e-9);
  // well inside the window the plies sit off the centreline, at the ply offset
  const c = t.pointAt(0.2);
  for (let i = 0; i < 3; i++) expect(t.plyCentre(0.2, i).distanceTo(c)).toBeGreaterThan(0.3 * R);
});

test('setPoints keeps a stable ply phase for the same points', () => {
  const us = Array.from({ length: 41 }, (_, i) => i / 40);
  const fresh = new Thread(S_CURVE, { radius: R, plies: 3 });
  const moved = new Thread(S_CURVE, { radius: R, plies: 3 });
  moved.setPoints(S_CURVE.map((p, i) => p.clone().add(v(0.05 * i, -0.1, 0.2 * Math.sin(i)))));
  moved.setPoints(S_CURVE);
  for (let k = 0; k < 10; k++) moved.setPoints(S_CURVE); // every frame, the same points
  for (const u of us) for (let i = 0; i < 3; i++) expect(moved.plyCentre(u, i).distanceTo(fresh.plyCentre(u, i))).toBeLessThan(1e-12);
  expect(Array.from(moved.frames.image.data as Float32Array)).toEqual(Array.from(fresh.frames.image.data as Float32Array));
});

test('the plies run continuously along the thread, through the S-curve inflection (no frame flip)', () => {
  const twist = 8; // turns per unit length: helix angle atan(2π · 8 · d) at ply offset d
  const t = new Thread(S_CURVE, { radius: R, plies: 3, twist });
  const n = 4000, L = t.length();
  // a ply centre moves along its helix: at most 1/cos(helix) of the centreline step, a little more in the end tapers.
  // A flipped frame jumps it across the thread (up to 2 ply offsets, ~40 steps).
  const d = 0.5 * R, helix = Math.sqrt(1 + (2 * Math.PI * twist * d) ** 2);
  for (let i = 0; i < 3; i++) {
    let prev = t.plyCentre(0, i);
    for (let k = 1; k <= n; k++) {
      const p = t.plyCentre(k / n, i);
      expect(p.distanceTo(prev)).toBeLessThan(1.5 * helix * (L / n));
      prev = p;
    }
  }
});

test('stretching the thread stretches its plies: their phase stays with the material, it never crawls', () => {
  const t = new Thread(S_CURVE, { radius: R, plies: 3 });
  // the angle of the blood strand round the centreline, in the thread's own frame (not ply 0: the diff thread's bone
  // core is centred on the axis, and has no angle)
  const angle = (u: number) => {
    const f = t.frameAt(u), d = t.plyCentre(u, 1).sub(f.pos);
    expect(d.length()).toBeGreaterThan(0.5 * R);
    return Math.atan2(d.dot(f.binormal), d.dot(f.normal));
  };
  const us = [0.2, 0.35, 0.5, 0.65, 0.8];
  const before = us.map(angle);
  const L = t.length();
  t.setPoints(S_CURVE.map((p) => p.clone().sub(S_CURVE[0]!).multiplyScalar(1.1).add(S_CURVE[0]!))); // 10% longer
  expect(t.length() / L).toBeCloseTo(1.1, 6);
  // anchored to the length it has now, the phase at u = 0.5 would move by 0.1 · 0.5 of all the turns: many radians
  us.forEach((u, i) => expect(Math.abs(angle(u) - before[i]!)).toBeLessThan(1e-4));
});

test('a small change of the points moves the plies by about as much (no phase jumps)', () => {
  const t = new Thread(S_CURVE, { radius: R, plies: 3 });
  const before = Array.from({ length: 101 }, (_, k) => [0, 1, 2].map((i) => t.plyCentre(k / 100, i)));
  // a small, uneven nudge: it bends and stretches the curve a little
  t.setPoints(S_CURVE.map((p, i) => p.clone().add(v(1e-4 * Math.sin(i), -1e-4 * Math.cos(2 * i), 5e-5 * Math.sin(3 * i)))));
  for (let k = 0; k <= 100; k++) for (let i = 0; i < 3; i++) {
    // a 10° slip of the phase would move a ply centre by 0.17 ply offsets (1e-3 here)
    expect(t.plyCentre(k / 100, i).distanceTo(before[k]![i]!)).toBeLessThan(5e-4);
  }
});

test('the diff thread is the bone 3-ply with the blood and moss strands laid in its grooves, `−` a groove ahead', () => {
  const t = new Thread(S_CURVE, { radius: R, plies: 3, colors: ['bone', 'blood', 'moss'] });
  // the angle of a ply round the centreline, in the thread's own frame
  const angle = (p: THREE.Vector3, u: number) => {
    const f = t.frameAt(u), d = p.clone().sub(f.pos);
    return Math.atan2(d.dot(f.binormal), d.dot(f.normal));
  };
  for (const u of [0.2, 0.5, 0.8]) {
    const c = t.pointAt(u), bone = t.plyCentre(u, 0), blood = t.plyCentre(u, 1), moss = t.plyCentre(u, 2);
    expect(bone.distanceTo(c)).toBeLessThan(1e-9); // the core's centre is the axis
    // plies of radius 0.5 at 0.5 from the axis leave grooves between them; a strand of radius 0.2 touching the plies
    // either side sits at 0.5·cos 60° + √(0.7² − (0.5·sin 60°)²) = 0.8 from the axis, flush with the outer radius
    expect(blood.distanceTo(c)).toBeCloseTo(0.8 * R, 9);
    expect(moss.distanceTo(c)).toBeCloseTo(0.8 * R, 9);
    // neighbouring grooves, the blood a third of a turn ahead: it passes each point along the thread first
    const d = angle(blood, u) - angle(moss, u);
    expect(Math.atan2(Math.sin(d), Math.cos(d))).toBeCloseTo((2 * Math.PI) / 3, 6);
  }
  // one colour twists as equals: three plies on a circle, none on the axis
  const bone = new Thread(S_CURVE, { radius: R, plies: 3, colors: ['bone', 'bone', 'bone'] });
  for (let i = 0; i < 3; i++) expect(bone.plyCentre(0.5, i).distanceTo(bone.pointAt(0.5))).toBeCloseTo(0.5 * R, 9);
});

test('setFray separates the plies around `at` and leaves the rest of the thread where it was', () => {
  const t = new Thread(S_CURVE, { radius: R, plies: 3, colors: ['bone', 'bone', 'bone'] });
  const spread = (u: number) => t.plyCentre(u, 0).distanceTo(t.plyCentre(u, 1));
  const far = [0.1, 0.9].map((u) => [0, 1, 2].map((i) => t.plyCentre(u, i)));
  const tight = spread(0.5);
  expect(tight).toBeCloseTo(Math.sqrt(3) * 0.5 * R, 6); // three plies on a circle of radius d = R/2
  t.setFray(0.5, 1, 0.05);
  const full = spread(0.5);
  expect(full).toBeGreaterThan(1.5 * tight);
  t.setFray(0.5, 0.5, 0.05);
  const half = spread(0.5);
  expect(half).toBeGreaterThan(tight); // it opens with the amount
  expect(half).toBeLessThan(full);
  t.setFray(0.5, 1, 0.05);
  // the untwist is local: beyond the frayed stretch no ply has moved or turned
  [0.1, 0.9].forEach((u, j) => [0, 1, 2].forEach((i) => expect(t.plyCentre(u, i).distanceTo(far[j]![i]!)).toBeLessThan(1e-9)));
  t.setFray(0.5, 0);
  expect(spread(0.5)).toBeCloseTo(tight, 12);
});

test('bone never glows; blood and moss glow at the level asked, their hue kept', () => {
  const t = new Thread(S_CURVE, { radius: R, plies: 3, colors: ['bone', 'blood', 'moss'], glow: 2.5 });
  const g = t.uniforms.uGlow.value.map((c) => c.toArray());
  expect(g[0]).toEqual([0, 0, 0]);
  // blood #c22b45 and moss #4aad63 in linear light, scaled so the brightest channel reads 2.5 (look.ts glow())
  [2.5, 0.1119488, 0.2757808].forEach((x, k) => expect(g[1]![k]!).toBeCloseTo(x, 5));
  [0.4096711, 2.5, 0.7464482].forEach((x, k) => expect(g[2]![k]!).toBeCloseTo(x, 5));
  t.setGlow(0);
  expect(t.uniforms.uGlow.value.flatMap((c) => c.toArray())).toEqual([0, 0, 0, 0, 0, 0, 0, 0, 0]);
  // an all-bone thread gets no glow at any level
  const bone = new Thread(S_CURVE, { radius: R, plies: 3, colors: ['bone', 'bone', 'bone'], glow: 6 });
  expect(bone.uniforms.uGlow.value.flatMap((c) => c.toArray())).toEqual([0, 0, 0, 0, 0, 0, 0, 0, 0]);
});

test('fibres are seeded: two threads build identical geometry whatever Math.random says', () => {
  // three itself draws object UUIDs from Math.random, so it can't be banned: pin it to different values instead
  const build = (r: number) => {
    const random = Math.random;
    Math.random = () => r;
    try {
      return new Thread(S_CURVE, { radius: R, plies: 3 });
    } finally {
      Math.random = random;
    }
  };
  const a = build(0.1), b = build(0.9);
  const attrs = (t: Thread) => {
    const out: number[][] = [];
    t.mesh.traverse((o) => {
      const g = (o as THREE.Mesh).geometry;
      if (g) for (const k of Object.keys(g.attributes).sort()) out.push(Array.from(g.attributes[k]!.array as ArrayLike<number>));
    });
    return out;
  };
  const A = attrs(a), B = attrs(b);
  expect(A.length).toBeGreaterThan(1); // the plies and the fibres
  expect(A).toEqual(B);
});
