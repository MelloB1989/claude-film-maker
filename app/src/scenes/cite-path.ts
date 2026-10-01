// The thread's route for `cite` (Plan 2 Task 17), in the editor's px (x right, y down from its top edge, z out of its
// face): drawn out of the citation's end in the chat, down through the air into the editor's right margin at the top of
// line 11 (A), behind the panel under lines 11–14, out again at the foot of line 14 (B), and on past the panel's edge to
// where the eye comes to rest (the route's end).
//
// The route through the air is drawn slack (a living S as it is drawn out and hangs) and pulled taut by the stitch: a
// straight line from the citation to A. Behind the panel and after B it never moves.
//
// ArcPath measures a route as the Thread draws it: a centripetal Catmull-Rom through the points (three's
// CatmullRomCurve3, as thread3d's sampleArc), by arc length on a dense polyline. The centripetal curve keeps its shape
// under a similarity (it is built from distances), so the route measured here in the editor's px is the thread in the
// world, scaled: a distance along one is the other's times the scale, and an arc fraction is the same on both.
import * as THREE from 'three';
import { clamp, lerp } from '../engine/util';

export type P3 = [number, number, number];

/** A centripetal Catmull-Rom through `points`, measured by arc length (`K` chords). */
export class ArcPath {
  readonly length: number;
  readonly n: number;
  private curve: THREE.CatmullRomCurve3;
  private P: Float64Array;
  private S: Float64Array;
  private K: number;

  constructor(points: readonly P3[], K = 2048) {
    this.n = points.length;
    this.curve = new THREE.CatmullRomCurve3(points.map((p) => new THREE.Vector3(...p)), false, 'centripetal');
    this.K = K;
    this.P = new Float64Array((K + 1) * 3);
    this.S = new Float64Array(K + 1);
    const q = new THREE.Vector3();
    for (let k = 0; k <= K; k++) {
      this.curve.getPoint(k / K, q);
      this.P[3 * k] = q.x; this.P[3 * k + 1] = q.y; this.P[3 * k + 2] = q.z;
      if (k) this.S[k] = this.S[k - 1]! + Math.hypot(q.x - this.P[3 * k - 3]!, q.y - this.P[3 * k - 2]!, q.z - this.P[3 * k - 1]!);
    }
    this.length = this.S[K]!;
  }

  /** The distance along the route to control point i (the curve passes through each). */
  atPoint(i: number): number {
    const x = (clamp(i, 0, this.n - 1) / (this.n - 1)) * this.K, k = Math.min(this.K - 1, Math.floor(x)), f = x - k;
    return this.S[k]! + (this.S[k + 1]! - this.S[k]!) * f;
  }

  /**
   * The point at distance s along the route and the direction there; past either end, on along the end's direction (a
   * needle running on past the thread's end keeps its line).
   */
  at(s: number): { pos: THREE.Vector3; dir: THREE.Vector3 } {
    const K = this.K, S = this.S, P = this.P;
    const pt = (k: number) => new THREE.Vector3(P[3 * k]!, P[3 * k + 1]!, P[3 * k + 2]!);
    if (s <= 0 || s >= this.length) {
      const k = s <= 0 ? 0 : K - 1, a = pt(k), b = pt(k + 1), dir = b.clone().sub(a).normalize();
      return { pos: (s <= 0 ? a : b).addScaledVector(dir, s <= 0 ? s : s - this.length), dir };
    }
    let lo = 0, hi = K;
    while (hi - lo > 1) {
      const m = (lo + hi) >> 1;
      if (S[m]! < s) lo = m;
      else hi = m;
    }
    const a = pt(lo), b = pt(hi), seg = S[hi]! - S[lo]!, f = seg > 0 ? (s - S[lo]!) / seg : 0;
    // the direction over a few chords either side, so it turns smoothly rather than chord to chord
    const d0 = pt(Math.max(0, lo - 2)), d1 = pt(Math.min(K, hi + 2));
    return { pos: a.lerp(b, f), dir: d1.sub(d0).normalize() };
  }

  /** The first distance along [s0, s1] where the route's `axis` coordinate crosses v (bisection on the dense samples). */
  crossing(axis: 0 | 1 | 2, v: number, s0: number, s1: number): number {
    const f = (s: number) => this.at(s).pos.getComponent(axis) - v;
    let a = s0, b = s1;
    const fa = f(a);
    if (Math.sign(fa) === Math.sign(f(b))) return Number.NaN;
    for (let i = 0; i < 40; i++) {
      const m = (a + b) / 2;
      if (Math.sign(f(m)) === Math.sign(fa)) a = m;
      else b = m;
    }
    return (a + b) / 2;
  }
}

/** The holes and the stitch's shape behind the panel and after it, from the margin's x and the rows it binds. */
export interface StitchSpec {
  /** The stitch's x in the right margin. */
  x: number;
  /** The top of the first row it binds and the foot of the last (px). */
  top: number;
  foot: number;
}

/** How far inside the bound rows the holes are, how deep the needle runs behind the panel (px). */
const INSET = 7;
const DEPTH = 46;

/**
 * The route behind the panel and on to the rest, from A: in at 45° to the face, down behind lines 11–14 at DEPTH, up
 * through B at 45°, then out and away past the panel's right edge, the eye coming to rest in the air. Index 0 is A, 4 is B.
 */
export function stitchRoute(s: StitchSpec): P3[] {
  const a = s.top + INSET, b = s.foot - INSET, mid = (a + b) / 2, x = s.x;
  return [
    [x, a, 0],
    [x, a + 0.33 * (mid - a) + 8, -0.55 * DEPTH],
    [x, mid, -DEPTH],
    [x, b - 0.33 * (b - mid) - 8, -0.55 * DEPTH],
    [x, b, 0],
    [x + 1, b + 22, 22],
    [x + 20, b + 42, 36],
    [x + 62, b + 56, 44],
  ];
}

/**
 * The route through the air from the citation's end `from` (just behind the label's face, so the thread comes out of
 * it) to A, slack: out of the label toward the camera, falling in a long curve that swells toward the lens, then a
 * straight run into A from above at 45° (the needle's line when it strikes, so the thread trails straight out of its
 * eye). `taut` 0..1 straightens it into the line from `from` to A (past 1, it bows the other way: the twang); `sway` (px)
 * breathes it sideways while it hangs. A is the route's last point.
 */
export function airRoute(from: P3, A: P3, taut: number, sway: P3 = [0, 0, 0]): P3[] {
  const [fx, fy, fz] = from, [ax, ay, az] = A, dy = ay - fy;
  const line = (f: number): P3 => [lerp(fx, ax, f), fy + dy * f, lerp(fz, az, f)];
  const k = 1 - taut;
  const at = (f: number, slack: P3): P3 => {
    const l = line(f), w = Math.sin(Math.PI * f); // the sway is largest mid-fall and nothing at the ends
    return [lerp(l[0], slack[0], k) + w * sway[0], lerp(l[1], slack[1], k) + w * sway[1], lerp(l[2], slack[2], k) + w * sway[2]];
  };
  // the curve: offsets from the straight line at fractions of the fall
  const curve: { f: number; off: P3 }[] = [{ f: 0.05, off: [3, 0, 13] }, { f: 0.22, off: [13, 0, 30] }];
  // the straight run in: points on the 45° line above A, at their own fractions of the fall
  const run: P3[] = [[ax + 8, ay - 88, az + 82], [ax + 4, ay - 44, az + 41]];
  return [
    [fx, fy, fz],
    ...curve.map(({ f, off }) => { const l = line(f); return at(f, [l[0] + off[0], l[1] + off[1], l[2] + off[2]]); }),
    ...run.map((p) => at((p[1] - fy) / dy, p)),
    [ax, ay, az],
  ];
}
