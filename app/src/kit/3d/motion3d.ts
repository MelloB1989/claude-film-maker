// How a 3D unit (a glyph, a word, a card) lands and leaves, as pure functions of time: offsets in em of the unit's
// size, rotations in radians, a scale and whether it is drawn yet. The house springs (motion.ts slam) land exactly on
// `at` (a beat, a spoken onset), so the impact is on the sound; nothing bounces like a cartoon.
import { slam } from '../../engine/motion';
import { clamp, ease, hash, prog } from '../../engine/util';

export type Reveal3D = 'slam' | 'rise' | 'tip' | 'drop' | 'scale';
export const REVEALS_3D: readonly Reveal3D[] = ['slam', 'rise', 'tip', 'drop', 'scale'];

export interface Pose3D {
  /** Drawn yet (false before the motion starts). */
  on: boolean;
  dx: number;
  dy: number;
  /** + toward the camera. */
  dz: number;
  rx: number;
  ry: number;
  rz: number;
  s: number;
}

export const REST: Readonly<Pose3D> = { on: true, dx: 0, dy: 0, dz: 0, rx: 0, ry: 0, rz: 0, s: 1 };
const OFF: Readonly<Pose3D> = { ...REST, on: false };

/** The reveals' springs and travel (em). */
export const REVEAL_3D = {
  slam: { freq: 5, damping: 0.6, from: 1.8, dz: 2.4 },
  rise: { freq: 4, damping: 0.72, drop: 0.9, tilt: 0.7 },
  tip: { freq: 4.5, damping: 0.62, pivot: 0.26 },
  drop: { freq: 5, damping: 0.6, height: 1.6, turn: 0.25 },
  scale: { freq: 5, damping: 0.62 },
} as const;

/**
 * A unit's pose at t for a reveal landing at `at`. `v` in [-1, 1] varies it per unit (a dropping glyph's lean). Throws
 * on an unknown reveal.
 */
export function revealPose(style: Reveal3D, t: number, at: number, v = 0): Pose3D {
  switch (style) {
    case 'slam': {
      const R = REVEAL_3D.slam, k = slam(t, at, R);
      if (k <= 0) return OFF;
      return { ...REST, s: 1 + (R.from - 1) * (1 - k), dz: R.dz * (1 - k) };
    }
    case 'rise': {
      const R = REVEAL_3D.rise, k = slam(t, at, R);
      if (k <= 0) return OFF;
      return { ...REST, dy: -R.drop * (1 - k), rx: R.tilt * (1 - k) };
    }
    case 'tip': {
      // lying back on its baseline, face up, it tips up to stand: the centre swings round the baseline
      const R = REVEAL_3D.tip, k = slam(t, at, R);
      if (k <= 0) return OFF;
      const th = (Math.PI / 2) * (1 - k);
      return { ...REST, rx: -th, dy: R.pivot * Math.cos(th) - R.pivot, dz: -R.pivot * Math.sin(th) };
    }
    case 'drop': {
      const R = REVEAL_3D.drop, k = slam(t, at, R);
      if (k <= 0) return OFF;
      return { ...REST, dy: R.height * (1 - k), rz: R.turn * v * (1 - k) };
    }
    case 'scale': {
      const k = slam(t, at, REVEAL_3D.scale);
      if (k <= 0) return OFF;
      return { ...REST, s: k };
    }
    default:
      throw new Error(`unknown 3D reveal '${style as string}' (reveals: ${REVEALS_3D.join(', ')})`);
  }
}

export type Exit3D = 'fall' | 'blow' | 'scatter';
export const EXITS_3D: readonly Exit3D[] = ['fall', 'blow', 'scatter'];

/**
 * A unit's exit offset at t: unit i of n leaves `stagger` s after the one before it, the last finishing on `end`, each
 * over `dur`. fall: tips forward and drops away under gravity; blow: flies at the camera, spinning, spreading from the
 * centre (seeded); scatter: drifts back and apart, shrinking. Added to the reveal's pose.
 */
export function exitPose(style: Exit3D, t: number, end: number, i: number, n: number, o: { dur?: number; stagger?: number; seed?: number; x?: number } = {}): Pose3D {
  const dur = o.dur ?? 0.55, st = o.stagger ?? 0.035, seed = o.seed ?? 1;
  const t1 = end - (n - 1 - i) * st, t0 = t1 - dur;
  // gravity: quadratic in time; the others accelerate (inCubic)
  const u = clamp((t - t0) / dur);
  if (u <= 0) return REST;
  const r = (k: number) => hash(seed, i, k) * 2 - 1;
  switch (style) {
    case 'fall': return { ...REST, dy: -3.2 * u * u, rx: 1.6 * u * u, dz: 0.6 * u };
    case 'blow': {
      const k = ease.inCubic(u);
      return { ...REST, dz: 7 * k, dx: (o.x ?? r(1)) * 2.2 * k, dy: r(2) * 1.6 * k, rx: r(3) * 3 * k, ry: r(4) * 3 * k, rz: r(5) * 2 * k, s: 1 + 0.4 * k };
    }
    case 'scatter': {
      const k = prog(t, t0, t1, ease.inOutCubic);
      return { ...REST, dz: -2.5 * k, dx: r(1) * 1.4 * k, dy: r(2) * 1.4 * k, s: 1 - 0.85 * k, on: k < 0.999 };
    }
    default:
      throw new Error(`unknown 3D exit '${style as string}' (exits: ${EXITS_3D.join(', ')}, or the base's fade, rise, sink)`);
  }
}

/** Two poses composed: offsets and rotations add, scales multiply, drawn only if both are. */
export function composePose(a: Pose3D, b: Pose3D): Pose3D {
  return { on: a.on && b.on, dx: a.dx + b.dx, dy: a.dy + b.dy, dz: a.dz + b.dz, rx: a.rx + b.rx, ry: a.ry + b.ry, rz: a.rz + b.rz, s: a.s * b.s };
}
