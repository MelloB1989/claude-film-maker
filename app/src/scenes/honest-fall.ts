// The world of scene `honest` and its three arms, as pure functions of time (honest-time.ts gives the times).
//
// The arms are the three retrieval arms `braid` named (lexical, body, cues), thin diff threads now, bone at rest. Each
// is rooted off the frame, near the lens (the left edge, below the frame, the right edge), and reaches up and away into
// the dark to a tip under the evidence floor, a level line at FLOOR_Y across the plane z = 0. There the tips search:
// they wander a little, the bodies following a beat behind like tendrils, the last stretch of each curled up toward the
// floor, and on the downbeat where the music drops out they press up to it and stop short. Nothing clears it.
//
// Then each goes slack and falls: a physical catenary drop. At its release the thread's length is fixed (the reach's,
// so the plies never stretch) and its tip lets go: the curl and the arch relax into the catenary that length hangs in
// between root and tip (one quarter of a second), and the tip drops through air that slows it (quadratic drag,
// terminal speed VT), the root letting go a moment after, so the whole slack thread sinks with its tip leading, the
// catenary deepening and swinging as the ends fall at their own rates. Its time is the physical time of a speed ramp
// (motion.ts speedRamp): slow motion through the slack and the first of the drop, back to real time as it leaves.
import * as THREE from 'three';
import { speedRamp } from '../engine/motion';
import { TAU, clamp, ease, lerp, prog, smoothstep } from '../engine/util';
import { ARMS, type Arm, RISE_S, type Times } from './honest-time';

export type V3 = [number, number, number];

// ------------------------------------------------------------------------------------------------ the world (metres)

/** The evidence floor: the level of the line across the plane z = 0. */
export const FLOOR_Y = 0.3;
/** The thread: outer radius (about 5 px across at the tips), and how many points describe its centreline. */
export const RADIUS = 0.0048;
export const N_PTS = 48;
/** The closest a tip ever comes to the floor (its centreline; the tapered tip is narrower than the thread). */
export const MIN_GAP = 0.016;

export interface ArmSpec {
  /** Where it is rooted: off the frame. */
  root: V3;
  /** Its tip's hover centre (y is taken from the floor and `gap`). */
  tip: V3;
  /** The tip's resting gap under the floor. */
  gap: number;
  /** How much longer than the span it is while it searches (held nearly taut: a slight sag). */
  ease: number;
  /** The search: sway amplitudes (x, z), and phases. */
  sway: [number, number];
  phase: [number, number, number, number];
}

/**
 * The three arms. One comes in from the far left, thin and far, to the leftmost tip; one sweeps up out of the bottom
 * left corner close to the lens, soft, to the middle; one comes in from the right. Their roots are off the frame and
 * below their tips, so each hangs across the frame from the tip the search holds up under the floor; none crosses
 * another. The tips search in a loose, uneven row there, the middle one lowest.
 */
export const ARM: Record<Arm, ArmSpec> = {
  lexical: { root: [-1.0, -0.62, 3.05], tip: [-0.04, 0, -0.02], gap: 0.075, ease: 0.006, sway: [0.03, 0.025], phase: [1.9, 0.4, 2.6, 3.3] },
  body: { root: [-2.6, -0.22, -0.35], tip: [-0.66, 0, 0.02], gap: 0.036, ease: 0.014, sway: [0.034, 0.03], phase: [0.3, 2.1, 4.0, 1.2] },
  cues: { root: [2.45, -0.42, 0.75], tip: [0.6, 0, 0.02], gap: 0.05, ease: 0.011, sway: [0.036, 0.03], phase: [4.4, 3.1, 0.9, 5.2] },
};

// ------------------------------------------------------------------------------------------------ the camera

/** The lens (vertical fov, degrees) and the aperture. */
export const FOV = 26;
export const FSTOP = 2.2;
/**
 * The camera: level (no yaw, no roll: the floor stays a level line) and square to the plane z = 0, pushing in slowly
 * from the cut to the end, drifting a little to the right, the near arms sliding past the far tips.
 */
export function cameraAt(t: number, T: Pick<Times, 'start' | 'end'>): { pos: V3; target: V3 } {
  const u = ease.inOutQuad(prog(t, T.start, T.end));
  const x = lerp(-0.035, 0.035, u), y = lerp(0.03, -0.01, u), d = lerp(4.72, 4.3, u);
  return { pos: [x, y, d], target: [x, y - 0.012, 0] };
}

// ------------------------------------------------------------------------------------------------ small vector help

const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const scale = (a: V3, k: number): V3 => [a[0] * k, a[1] * k, a[2] * k];
const len = (a: V3) => Math.hypot(a[0], a[1], a[2]);
const mix = (a: V3, b: V3, k: number): V3 => [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)];

/** `n` points evenly spaced in arc length along the polyline `p` (dense enough to stand for its curve); its length. */
export function resample(p: V3[], n: number): { pts: V3[]; length: number } {
  const S = [0];
  for (let i = 1; i < p.length; i++) S.push(S[i - 1]! + len(sub(p[i]!, p[i - 1]!)));
  const L = S[S.length - 1]!;
  const pts: V3[] = [];
  let k = 0;
  for (let i = 0; i < n; i++) {
    const s = (i / (n - 1)) * L;
    while (k < p.length - 2 && S[k + 1]! < s) k++;
    const seg = S[k + 1]! - S[k]!;
    pts.push(mix(p[k]!, p[k + 1]!, seg > 0 ? clamp((s - S[k]!) / seg) : 0));
  }
  return { pts, length: L };
}

// ------------------------------------------------------------------------------------------------ the catenary

/**
 * The catenary a thread of length L hangs in between a and b (L longer than |b − a|): `n` points evenly spaced along its
 * length from a to b, in the vertical plane through them. A thread no longer than the span is the straight line.
 *
 * In that plane, x along the level from a toward b (h to reach b) and y up (v to reach b): y = c·(cosh((x − x0)/c) −
 * cosh(x0/c)), its arc length from a s(x) = c·(sinh((x − x0)/c) + sinh(x0/c)). c solves 2c·sinh(h/2c) = √(L² − v²)
 * (Newton on sinh z = r·z, z = h/2c, from the right of its root, where it converges without fail), and the low point
 * x0 = h/2 − c·atanh(v/L).
 */
export function catenary(a: V3, b: V3, L: number, n: number): V3[] {
  const dx = b[0] - a[0], dz = b[2] - a[2], v = b[1] - a[1];
  const h = Math.hypot(dx, dz);
  const span = Math.hypot(h, v);
  const line = () => Array.from({ length: n }, (_, i) => mix(a, b, i / (n - 1)));
  if (L <= span * (1 + 1e-9) || h < 1e-9 * L) return line();
  const r = Math.sqrt(L * L - v * v) / h;
  // sinh z = r·z: convex for z > 0 with one root; Newton from its right converges monotonically
  let z = Math.max(1, 2 * Math.log(2 * r) + 1);
  for (let i = 0; i < 60; i++) {
    const f = Math.sinh(z) - r * z, d = Math.cosh(z) - r;
    const nz = z - f / d;
    if (!(nz > 0) || Math.abs(nz - z) < 1e-13 * z) {
      z = nz > 0 ? nz : z;
      break;
    }
    z = nz;
  }
  z = Math.min(z, 300);
  const c = h / (2 * z);
  const x0 = h / 2 - c * Math.atanh(clamp(v / L, -1 + 1e-12, 1 - 1e-12));
  const ex = dx / h, ez = dz / h;
  const s0 = Math.sinh(-x0 / c), y0 = Math.cosh(-x0 / c);
  const out: V3[] = [];
  for (let i = 0; i < n; i++) {
    const s = (i / (n - 1)) * L;
    const x = i === n - 1 ? h : x0 + c * Math.asinh(s / c + s0);
    const y = i === n - 1 ? v : c * (Math.cosh((x - x0) / c) - y0);
    out.push([a[0] + ex * x, a[1] + y, a[2] + ez * x]);
  }
  return out;
}

// ------------------------------------------------------------------------------------------------ the search

/** 0..1: the arms press up to the floor on the downbeat where the music drops out, and come off it. */
export function pressAt(t: number, hush: number): number {
  if (t < hush) return prog(t, hush - 0.3, hush, ease.inOutCubic);
  return 1 - prog(t, hush + 0.05, hush + 0.45, ease.outCubic);
}

/** How the search stills on "know…": 1 searching, falling toward 0.25 as it hangs there. */
const stillness = (t: number, T: Pick<Times, 'know' | 'knowEnd'>) => 1 - 0.75 * prog(t, T.know - 0.05, T.knowEnd + 0.1, ease.inOutQuad);

type SearchTimes = Pick<Times, 'hush' | 'know' | 'knowEnd'>;

/** Where arm `a`'s tip searches at t: under the floor always (its gap is never less than MIN_GAP). */
export function tipAt(a: Arm, t: number, T: SearchTimes): V3 {
  const s = ARM[a], [p0, p1, p2, p3] = s.phase, k = stillness(t, T);
  const x = s.tip[0] + k * s.sway[0] * (0.62 * Math.sin(TAU * 0.52 * t + p0) + 0.38 * Math.sin(TAU * 0.91 * t + p1));
  const z = s.tip[2] + k * s.sway[1] * Math.sin(TAU * 0.37 * t + p2);
  // the gap: hovering, pressed up toward the floor at the hush with a small recoil off it, and sinking a little on "know…"
  const hover = s.gap + k * 0.011 * Math.sin(TAU * 0.68 * t + p3);
  const recoil = 0.014 * smoothstep(T.hush + 0.02, T.hush + 0.16, t) * (1 - smoothstep(T.hush + 0.2, T.hush + 0.6, t));
  const gap = lerp(hover, MIN_GAP, pressAt(t, T.hush)) + recoil + 0.03 * prog(t, T.know - 0.05, T.knowEnd + 0.15, ease.inOutQuad);
  return [x, FLOOR_Y - Math.max(MIN_GAP, gap), z];
}

/**
 * Arm `a` as it searches at t: the catenary it hangs in from its root to the tip the search holds up, nearly taut (a
 * shade longer than the span, ArmSpec.ease), as `N_PTS` points even in arc length.
 */
export function reachAt(a: Arm, t: number, T: SearchTimes): { pts: V3[]; length: number } {
  const s = ARM[a];
  const P = tipAt(a, t, T), R = s.root;
  const L = len(sub(P, R)) * (1 + s.ease);
  const pts = catenary(R, P, L, N_PTS);
  // pressed up against the floor, the last of it quivers (strained, a few px, dying in a fifth of a second)
  const q = quiverAt(t, T.hush);
  if (q !== 0) pts.forEach((p, i) => (p[1] += q * Math.exp(-(((N_PTS - 1 - i) / (N_PTS - 1) / 0.22) ** 2))));
  return { pts, length: L };
}

/** The quiver's lift at the tip at t (world units, ±QUIVER): from the hush, at 7 Hz, dying away. */
export const QUIVER = 0.005;
export function quiverAt(t: number, hush: number): number {
  const dt = t - hush;
  return dt <= 0 || dt > 0.8 ? 0 : QUIVER * Math.sin(TAU * 7 * dt) * Math.exp(-dt / 0.16);
}

// ------------------------------------------------------------------------------------------------ the fall

/** Gravity and the tip's terminal speed through the air (m/s): a light thread, slowed early. */
export const G = 9.81;
export const VT = 3.0;
/** The root lets go this long after the tip (physical s). */
export const ROOT_LAG = 0.3;
/** How long after its release an arm counts as slack (screen s): the floor's lift above its tip dies over this. */
export const SLACK_S = 0.26;
/** The fall's speed ramp (screen s from its release, speed): slow motion through the slack and the first of the drop,
 * then back to real time as it leaves the frame. */
export const SLOWMO: [number, number][] = [[0, 0.42], [0.5, 0.42], [0.95, 1]];

/**
 * The ripple that runs down an arm as it lets go (the tension leaving it): a short wave packet launched at the tip that
 * reaches the root WAVE.t physical s later, dying as it goes. Its front's arc fraction and its strength at τ.
 */
export const WAVE = { t: 0.3, decay: 0.16, amp: 0.011, width: 0.12, length: 0.22 };
export function waveAt(tau: number): { u: number; k: number } {
  if (tau <= 0 || tau >= WAVE.t) return { u: 0, k: 0 };
  return { u: 1 - tau / WAVE.t, k: Math.exp(-tau / WAVE.decay) * smoothstep(0, 0.025, tau) };
}

/**
 * The air on a falling arm: a slow undulation along it (amplitude, wavelength in arc fraction, frequency in physical Hz,
 * rising from `from` to `full` physical s into the fall), and its free end trailing up, by `trail` at terminal speed,
 * over its last `tail` of length.
 */
export const FLUTTER = { amp: 0.016, length: 0.55, freq: 1.4, from: 0.04, full: 0.3, trail: 0.05, tail: 0.18 };

/** How far a body falling from rest through air with quadratic drag has dropped after τ s. */
export const drop = (tau: number) => (tau <= 0 ? 0 : ((VT * VT) / G) * Math.log(Math.cosh((G * tau) / VT)));

/** The physical time of a fall released at `at`, at song time t (0 before it). */
export const fallTime = (t: number, at: number) => (t <= at ? 0 : speedRamp(t - at, SLOWMO));

export interface ArmPose {
  /** The centreline: N_PTS points even in arc length, root first. */
  pts: V3[];
  /** The draw window (arc fractions): the reach draws on from the root. */
  draw: [number, number];
  /** 0 while it reaches and searches, rising to 1 as it goes slack. */
  slack: number;
  /** The release ripple's front (arc fraction) and strength, 0 outside it: the blood flicker rides it. */
  wave: { u: number; k: number };
}

/**
 * Arm `a` at t: drawing on from its root from `rise` (RISE_S, the tip racing out and settling under the floor),
 * searching, then from `slack` going slack and falling.
 */
export function armAt(a: Arm, t: number, T: SearchTimes & Pick<Times, 'rise' | 'slack'>): ArmPose {
  const rise = T.rise(a), at = T.slack(a);
  const draw: [number, number] = [0, prog(t, rise, rise + RISE_S, ease.outCubic)];
  if (t <= at) return { pts: reachAt(a, t, T).pts, draw, slack: 0, wave: { u: 0, k: 0 } };
  // the reach as it was when it let go: its shape and its length, which the thread keeps
  const held = reachAt(a, at, T);
  const L = held.length;
  const tau = fallTime(t, at);
  const R0 = held.pts[0]!, P0 = held.pts[N_PTS - 1]!;
  const root: V3 = [R0[0], R0[1] - drop(tau - ROOT_LAG), R0[2]];
  let tip: V3 = [P0[0], P0[1] - drop(tau), P0[2]];
  // the thread holds the tip to its length (it cannot fall further from the root than the thread is long)
  const d = sub(tip, root), far = len(d), reach = 0.985 * L;
  if (far > reach) tip = add(root, scale(d, reach / far));
  const pts = catenary(root, tip, L, N_PTS);
  // what the air does to a slack thread falling through it, displaced square to the thread in the plane it hangs in
  // (toward up): the release ripple running down it; a slow undulation that grows as it falls; and the free end trailing
  // up as it gathers speed
  const wave = waveAt(tau);
  const flut = FLUTTER.amp * smoothstep(FLUTTER.from, FLUTTER.full, tau);
  const trail = FLUTTER.trail * Math.tanh((G * tau) / VT);
  const ph = ARM[a].phase[0];
  const out = pts.map((p) => [...p] as V3);
  for (let i = 1; i < N_PTS; i++) {
    const u = i / (N_PTS - 1);
    let d = 0;
    if (wave.k > 0) {
      const x = u - wave.u;
      d += WAVE.amp * wave.k * Math.exp(-((x / WAVE.width) ** 2)) * Math.sin((TAU * x) / WAVE.length);
    }
    d += flut * smoothstep(0, 0.2, u) * Math.sin(TAU * (u / FLUTTER.length - FLUTTER.freq * tau) + ph);
    if (u > 1 - FLUTTER.tail) d += trail * ((u - (1 - FLUTTER.tail)) / FLUTTER.tail) ** 2;
    if (d === 0) continue;
    const tan = sub(pts[Math.min(i + 1, N_PTS - 1)]!, pts[i - 1]!), tl = len(tan) || 1;
    const ty = tan[1] / tl;
    const n: V3 = [(-ty * tan[0]) / tl, 1 - ty * ty, (-ty * tan[2]) / tl]; // up, made square to the tangent
    const nl = len(n) || 1;
    out[i] = add(pts[i]!, scale(n, d / nl));
  }
  return { pts: out, draw, slack: smoothstep(0, SLACK_S, t - at), wave };
}

/** The arms' points as three.js vectors (Thread.setPoints), into `out` (reused frame to frame). */
export function toVectors(pts: V3[], out: THREE.Vector3[]): THREE.Vector3[] {
  for (let i = 0; i < pts.length; i++) (out[i] ??= new THREE.Vector3()).set(pts[i]![0], pts[i]![1], pts[i]![2]);
  out.length = pts.length;
  return out;
}

export { ARMS };
