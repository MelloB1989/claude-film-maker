// The thread's route for `cite` (Plan 2 Task 17, fix 1), in the editor's px (x right, y down from its top edge, z out of
// its face). One continuous line, never through anything: it starts as an underline lying on the citation label's face
// under `L11–14`, runs off the label's foot, falls in one long curve through the air in front of the file, and comes
// down onto the file's face at the top of line 11 just past the lines' ends (the landing), where it lies flat and runs
// down the margin beside lines 11–14 as a seam, turning in under line 14 like a bracket's foot (the route's end).
//
// Wherever it lies on a face it lies a hair above it (its radius plus a little), so no geometry ever passes into a panel.
// The air between is a slack curve that breathes while it is drawn and draws in a little when the light lands (taut).
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

/** Where the seam lies: the underline on the label, the margin's x and the rows it runs beside (editor px). */
export interface SeamSpec {
  /** The underline under the citation's range: its left and right ends, its y, and the label's face z. */
  under: { x0: number; x1: number; y: number; z: number };
  /** The label's foot (y), where the thread runs off it. */
  labelFoot: number;
  /** The seam's x in the file's right margin, and the top of the first row and the foot of the last it runs beside. */
  x: number;
  top: number;
  foot: number;
  /** How far above a face the thread's axis lies (px): its radius and a little air. */
  lift: number;
}

/** The index of the landing (the first point lying on the file's face) in seamRoute's points. */
export const LAND = 8;

/** The air's arc: the angles (degrees, 0 at the underline's end, 90 at the approach) its points sit at. */
const ARC = [18, 38, 56, 73];

/**
 * The route from the underline to the seam's foot. The air is one quarter-ellipse in the label's and file's plane, from
 * the underline's end (running on right, so the underline flows into it) round to the approach straight down onto the
 * margin, so it never turns back on itself; it stays a hair over the label's face until it has passed its foot, then
 * swells toward the lens and comes down to lie on the file. `taut` 0..1 draws the arc in toward its chord and the swell
 * back (past 1 it rings the other way); `sway` (px) breathes the air while it is drawn.
 */
export function seamRoute(s: SeamSpec, taut = 0, sway: P3 = [0, 0, 0]): P3[] {
  const { under: u, x, top, foot, lift } = s, zl = u.z + lift, zf = lift;
  const k = 1 - 0.3 * taut;
  const near: P3 = [x, top - 40, zf + 14];
  const rx = near[0] - u.x1, ry = near[1] - u.y;
  // the angle where the arc runs off the label's foot, with a little margin: the face's z holds until past it
  const off = (Math.acos(clamp((near[1] - s.labelFoot) / ry, -1, 1)) * 180) / Math.PI + 4;
  const air = ARC.map((deg): P3 => {
    const th = (deg * Math.PI) / 180, f = deg / 90;
    const ex = u.x1 + rx * Math.sin(th), ey = near[1] - ry * Math.cos(th);
    const cx = lerp(u.x1, near[0], f), cy = lerp(u.y, near[1], f);
    const w = Math.sin(Math.PI * f); // the sway is largest mid-arc and nothing at its ends
    const fall = smooth(clamp((deg - off) / (90 - off)));
    const swell = deg > off ? 34 * k * Math.sin((Math.PI * (deg - off)) / (90 - off)) : 0;
    return [lerp(cx, ex, k) + w * sway[0], lerp(cy, ey, k) + w * sway[1], lerp(zl, near[2], fall) + swell + w * Math.max(0, sway[2])];
  });
  return [
    [u.x0, u.y, zl],
    [u.x1, u.y, zl],
    ...air,
    near,
    [x, top - 12, zf + 3],
    [x, top + 6, zf],
    [x, (top + foot) / 2, zf],
    [x, foot - 16, zf],
    [x - 9, foot - 4, zf],
    [x - 30, foot - 1, zf],
  ];
}

const smooth = (x: number) => x * x * (3 - 2 * x);
