import { expect, test } from 'bun:test';
import * as THREE from 'three';
import { DOF_MAX_BLUR_PX, cocPx, latticeDisc } from './dof';
import { CameraRig, type CamKey } from './stage';
import { ease } from './util';

// Expected values are hand-derived (Python, from the textbook thin-lens form c = A·|z − S|/z · f/(S − f) on a 16:9
// frame 36 × 20.25 mm), never from dof.ts.
const FOV_50MM = 22.895192527371208; // vertical fov of a 50 mm lens on that frame: 2·atan(10.125 / 50)
const lens = { focus: 4, fstop: 1.4, maxBlurPx: 1000 };

test('cocPx is the thin-lens circle of confusion: 50 mm f/1.4 focused at 4 m blurs 2 m to 24.1 px at 1080p', () => {
  expect(cocPx(2, lens, FOV_50MM, 1080)).toBeCloseTo(24.11091, 4);
  expect(cocPx(8, lens, FOV_50MM, 1080)).toBeCloseTo(12.05546, 4);
  expect(cocPx(3, lens, FOV_50MM, 1080)).toBeCloseTo(8.03697, 4);
  expect(cocPx(1e9, lens, FOV_50MM, 1080)).toBeCloseTo(24.11091, 4); // the far limit
  // it scales with the image: the same lens on a 4K frame
  expect(cocPx(2, lens, FOV_50MM, 2160)).toBeCloseTo(2 * 24.11091, 3);
});

test('cocPx is 0 at the focus distance and grows with |1/focus − 1/depth|', () => {
  expect(cocPx(4, lens, 30, 1080)).toBe(0);
  expect(cocPx(2.5, { ...lens, focus: 2.5 }, 20, 1080)).toBe(0);
  // proportional to |1/focus − 1/depth|, in front of the focus and behind it
  const k = cocPx(2, lens, 30, 1080) / Math.abs(1 / 4 - 1 / 2);
  for (const d of [0.5, 1, 1.5, 3, 3.9, 4.1, 5, 8, 20, 1e6]) expect(cocPx(d, lens, 30, 1080) / Math.abs(1 / 4 - 1 / d)).toBeCloseTo(k, 6);
  // monotonic away from the focus on both sides
  const near = [3.9, 3.5, 3, 2, 1].map((d) => cocPx(d, lens, 30, 1080));
  const far = [4.1, 5, 8, 20, 100].map((d) => cocPx(d, lens, 30, 1080));
  for (const s of [near, far]) for (let i = 1; i < s.length; i++) expect(s[i]!).toBeGreaterThan(s[i - 1]!);
  // stopping down shrinks it in proportion, a longer lens (narrower fov) grows it
  expect(cocPx(2, { ...lens, fstop: 2.8 }, 30, 1080)).toBeCloseTo(cocPx(2, lens, 30, 1080) / 2, 9);
  expect(cocPx(2, lens, 20, 1080)).toBeGreaterThan(cocPx(2, lens, 30, 1080));
});

test('cocPx is clamped at maxBlurPx, and at DOF_MAX_BLUR_PX when that is not given', () => {
  expect(cocPx(0.5, { ...lens, maxBlurPx: 10 }, 30, 1080)).toBe(10);
  expect(cocPx(3.9, { ...lens, maxBlurPx: 10 }, 30, 1080)).toBeLessThan(10); // under the cap it is untouched
  expect(cocPx(0.05, { focus: 4, fstop: 1.4 }, 30, 1080)).toBe(DOF_MAX_BLUR_PX);
  expect(cocPx(1e9, { focus: 0.3, fstop: 1.4 }, 20, 1080)).toBe(DOF_MAX_BLUR_PX);
});

test('the DoF kernel is a disc on the pixel lattice, whole and in quarters: each integrates the disc, drift-free', () => {
  const px = (R: number) => { // pixel centres within R + 1/2 of a pixel corner
    let n = 0;
    for (let j = -30; j < 30; j++) for (let i = -30; i < 30; i++) if (Math.hypot(i + 0.5, j + 0.5) <= R + 0.5) n++;
    return n;
  };
  const key = (k: Float32Array, s: number) => `${k[4 * s]},${k[4 * s + 1]}`;
  const within = (k: Float32Array, lo: number, hi: number) =>
    Array.from({ length: k.length / 4 }, (_, s) => s).filter((s) => k[4 * s + 2]! >= lo && k[4 * s + 2]! < hi).map((s) => key(k, s));
  for (const core of [2, 3]) for (const R of [1, 4, 12.5, 24]) {
    const [whole] = latticeDisc(R, 1, core), parts = latticeDisc(R, 4, core);
    expect(parts.length).toBe(4);
    for (const k of [whole!, ...parts]) {
      let area = 0, mx = 0, my = 0;
      for (let s = 0; s < k.length / 4; s++) {
        const [x, y, r, a] = [k[4 * s]!, k[4 * s + 1]!, k[4 * s + 2]!, k[4 * s + 3]!];
        expect(Math.abs(x) % 1).toBe(0.5); // pixel centres
        expect(r).toBeCloseTo(Math.hypot(x, y), 5); // stored as float32
        if (s > 0) expect(r).toBeGreaterThanOrEqual(k[4 * s - 2]!);
        area += a; mx += a * x; my += a * y;
      }
      expect(area).toBeCloseTo(px(R), 3);
      expect(Math.abs(mx) + Math.abs(my)).toBeLessThan(1e-6);
      // every pixel of the dense core is there
      let want = 0;
      for (let j = -4; j < 4; j++) for (let i = -4; i < 4; i++) if (Math.hypot(i + 0.5, j + 0.5) < Math.min(core, R + 0.5)) want++;
      expect(within(k, 0, core).length).toBe(want);
    }
    // the quarters share the core (and any ring too thin to go round) and split the rest: together, the whole disc
    const count = new Map<string, number>();
    for (const q of parts.flatMap((k) => within(k, core, 99))) count.set(q, (count.get(q) ?? 0) + 1);
    for (const c of count.values()) expect(c === 1 || c === 4).toBe(true);
    expect([...count.keys()].sort()).toEqual(within(whole!, core, 99).sort());
    if (R >= 12) expect([...count.values()].filter((c) => c === 1).length).toBeGreaterThan(0.9 * count.size);
  }
  // it grows linearly with the radius, not with its area
  const n12 = latticeDisc(12)[0]!.length / 4, n24 = latticeDisc(24)[0]!.length / 4;
  expect(n24 / n12).toBeLessThan(2.5);
});

// ---- the camera rig ----

const cam = () => new THREE.PerspectiveCamera(40, 16 / 9, 0.1, 100);
const dir = (c: THREE.PerspectiveCamera) => c.getWorldDirection(new THREE.Vector3());
const up = (c: THREE.PerspectiveCamera) => new THREE.Vector3(0, 1, 0).applyQuaternion(c.quaternion);
const norm = (v: [number, number, number]) => new THREE.Vector3(...v).normalize();
const near3 = (a: THREE.Vector3, b: THREE.Vector3 | [number, number, number], digits = 9) => {
  const v = Array.isArray(b) ? new THREE.Vector3(...b) : b;
  expect(a.x).toBeCloseTo(v.x, digits); expect(a.y).toBeCloseTo(v.y, digits); expect(a.z).toBeCloseTo(v.z, digits);
};

const A: CamKey = { t: 1, pos: [0, 0, 5], target: [0, 0, 0], fov: 30 };
const B: CamKey = { t: 3, pos: [4, 2, 1], target: [2, 0, -2], fov: 20, roll: 10, ease: (x) => x * x };

test('CameraRig.apply gives the exact key values at the key times', () => {
  const rig = new CameraRig([B, A]); // keys in any order
  const c = cam();
  rig.apply(c, 1);
  expect(c.position.toArray()).toEqual([0, 0, 5]);
  expect(c.fov).toBe(30);
  near3(dir(c), [0, 0, -1]);
  near3(up(c), [0, 1, 0]);
  rig.apply(c, 3);
  expect(c.position.toArray()).toEqual([4, 2, 1]);
  expect(c.fov).toBe(20);
  near3(dir(c), norm([-2, -2, -3]));
  // outside the keys it holds the first and the last
  rig.apply(c, -4);
  expect(c.position.toArray()).toEqual([0, 0, 5]);
  rig.apply(c, 9);
  expect(c.position.toArray()).toEqual([4, 2, 1]);
  expect(c.fov).toBe(20);
  // the projection follows the fov
  const p = new THREE.PerspectiveCamera(20, 16 / 9, 0.1, 100).projectionMatrix;
  expect(c.projectionMatrix.elements[5]).toBeCloseTo(p.elements[5]!, 12);
});

test('CameraRig.apply eases between keys with the ease of the key it is heading to', () => {
  const rig = new CameraRig([A, B]);
  const c = cam();
  rig.apply(c, 2); // halfway in time, x² → a quarter of the way
  near3(c.position, [1, 0.5, 4]);
  near3(dir(c), new THREE.Vector3(0.5, 0, -0.5).sub(new THREE.Vector3(1, 0.5, 4)).normalize());
  expect(c.fov).toBeCloseTo(27.5, 12);
  // the default ease is inOutCubic: a quarter of the time goes 1/16 of the way, half goes half
  const r2 = new CameraRig([{ t: 0, pos: [0, 0, 0], target: [0, 0, -1] }, { t: 2, pos: [8, 0, 0], target: [8, 0, -1] }]);
  const c2 = cam();
  r2.apply(c2, 0.5);
  near3(c2.position, [8 * ease.inOutCubic(0.25), 0, 0]);
  expect(c2.position.x).toBeCloseTo(0.5, 12);
  r2.apply(c2, 1);
  near3(c2.position, [4, 0, 0]);
  // keys without a fov leave the camera's own
  expect(c2.fov).toBe(40);
});

test('roll turns the camera about its view axis, in degrees, counter-clockwise as seen from behind it', () => {
  const rig = new CameraRig([{ t: 0, pos: [0, 0, 5], target: [0, 0, 0], roll: 90 }]);
  const c = cam();
  rig.apply(c, 0);
  near3(dir(c), [0, 0, -1]);
  near3(up(c), [-1, 0, 0]);
  const r2 = new CameraRig([A, B]);
  r2.apply(c, 2); // x² ease: a quarter of B's 10°
  const d = dir(c), flat = new THREE.Vector3().crossVectors(d, new THREE.Vector3(0, 1, 0)).normalize();
  const upNoRoll = new THREE.Vector3().crossVectors(flat, d).normalize();
  expect(THREE.MathUtils.radToDeg(up(c).angleTo(upNoRoll))).toBeCloseTo(2.5, 9);
});

test('through three keys the path is a smooth curve: exact at the keys, no kink where segments meet', () => {
  const keys: CamKey[] = [
    { t: 0, pos: [0, 0, 6], target: [0, 0, 0], ease: ease.linear },
    { t: 1, pos: [3, 1, 4], target: [0, 0, 0], ease: ease.linear },
    { t: 2.5, pos: [5, 0, 0], target: [0, 0, 0], ease: ease.linear },
  ];
  const rig = new CameraRig(keys);
  const c = cam();
  const at = (t: number) => { rig.apply(c, t); return c.position.clone(); };
  expect(at(1).toArray()).toEqual([3, 1, 4]);
  // the direction of travel just before the middle key matches the one just after it
  const e = 1e-4;
  const vIn = at(1).sub(at(1 - e)).normalize(), vOut = at(1 + e).sub(at(1)).normalize();
  expect(vIn.angleTo(vOut)).toBeLessThan(1e-3);
  // a straight polyline would kink there: the chord directions differ by far more
  const chordIn = new THREE.Vector3(3, 1, -2).normalize(), chordOut = new THREE.Vector3(2, -1, -4).normalize();
  expect(chordIn.angleTo(chordOut)).toBeGreaterThan(0.3);
  // collinear keys evenly spaced in time and space, with linear eases, give uniform straight motion
  const line = new CameraRig([0, 1, 2, 3].map((i) => ({ t: i, pos: [i * 2, 0, 0] as [number, number, number], target: [i * 2, 0, -1] as [number, number, number], ease: ease.linear })));
  line.apply(c, 1.3);
  near3(c.position, [2.6, 0, 0]);
  // a held key (the same position twice) holds still in between
  const hold = new CameraRig([{ t: 0, pos: [1, 2, 3], target: [0, 0, 0] }, { t: 1, pos: [1, 2, 3], target: [0, 0, 0] }, { t: 2, pos: [5, 2, 3], target: [0, 0, 0] }]);
  hold.apply(c, 0.5);
  near3(c.position, [1, 2, 3]);
});
