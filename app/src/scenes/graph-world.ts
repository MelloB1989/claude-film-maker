// The world of scene `graph` (Plan 2 Task 20), in metres: the constellation of memories, the curves its threads hang in,
// and the light that runs along them, all pure functions of time so any frame renders alone.
//
// The memories are glass beads (engine/bead.ts), each with a pearl at its heart where its edges meet; an edge is the
// film's diff thread, drawn from pearl to pearl. A memory's links point out of it: user.md (the file the scene opens on,
// an editor hanging at the left) to acme.md; maya.md, new, to a trip that isn't written yet; the trip, once it is, on to
// its hotel and the hotel to its city. Unnamed memories round them, and the threads between them, make the graph.
import { clamp, ease, fract, hash, lerp, prog, smoothstep } from '../engine/util';
import { slam } from '../engine/motion';

export type V3 = [number, number, number];

/** The lens (vertical fov, degrees): a short tele, repo's and diff's. */
export const FOV = 24;
/** The thread (her diff thread, slimmer: an edge between memories, a fine cord) and the beads. */
export const THREAD_R = 0.0017;
export const BEAD_R = 0.021;
/** A bead's pearl, as a fraction of its radius. */
export const PEARL = 0.3;

export type NodeId = 'acme' | 'maya' | 'trip' | 'hotel' | 'city' | `c${number}`;

export interface NodeSpec {
  pos: V3;
  /** Radius (m). */
  r: number;
  /** Its label: a strings-file key (graph.ts maps it), none for the graph's unnamed memories. */
  label?: 'acme' | 'maya' | 'trip' | 'hotel' | 'city';
}

/**
 * The memories. The named ones run across the frame as the story reads, left to right: acme.md high, maya.md low in the
 * middle, the trip's place to its right, the hotel, the city; unnamed ones round them, some far back (bokeh) and one
 * near the lens.
 */
export const NODES: Record<NodeId, NodeSpec> = {
  acme: { pos: [-0.06, 0.17, -0.2], r: BEAD_R, label: 'acme' },
  maya: { pos: [0.03, -0.11, 0.04], r: BEAD_R, label: 'maya' },
  trip: { pos: [0.33, -0.05, -0.08], r: BEAD_R, label: 'trip' },
  hotel: { pos: [0.58, 0.12, -0.19], r: BEAD_R, label: 'hotel' },
  city: { pos: [0.83, -0.04, -0.31], r: BEAD_R, label: 'city' },
  // round them, near and far
  c1: { pos: [-0.3, 0.38, -0.6], r: 0.017 },
  c2: { pos: [0.24, 0.31, -0.46], r: 0.016 },
  c3: { pos: [-0.24, -0.27, -0.16], r: 0.016 },
  c4: { pos: [1.02, 0.27, -0.66], r: 0.017 },
  c5: { pos: [0.5, -0.36, -0.26], r: 0.015 },
  c6: { pos: [0.11, 0.34, -0.12], r: 0.014 },
  c7: { pos: [1.16, -0.2, -0.5], r: 0.016 },
  // the deep field: far back, out of focus, the graph going on into the dark
  c8: { pos: [-0.62, 0.02, -1.15], r: 0.02 },
  c9: { pos: [0.5, 0.55, -1.3], r: 0.02 },
  c10: { pos: [1.5, 0.08, -1.35], r: 0.02 },
  c11: { pos: [0.05, -0.42, -0.9], r: 0.018 },
  c12: { pos: [0.95, -0.45, -0.85], r: 0.018 },
  // between the story's memories, behind them: the graph is dense where the story runs
  c13: { pos: [0.19, 0.13, -0.36], r: 0.015 },
  c14: { pos: [0.43, 0.24, -0.52], r: 0.016 },
  c15: { pos: [-0.2, 0.0, -0.42], r: 0.015 },
};

/**
 * The edges that are there throughout (bone, at rest): pairs of memories, how much each hangs (m at its middle), and its
 * thickness against the story's threads (the graph round the story is finer).
 */
export const STANDING: [NodeId, NodeId, number, number][] = [
  ['acme', 'c1', 0.02, 0.75],
  ['acme', 'c2', 0.015, 0.75],
  ['c2', 'hotel', 0.02, 0.75],
  ['acme', 'c6', 0.008, 0.75],
  ['maya', 'c3', 0.012, 0.75],
  ['hotel', 'city', 0.012, 1],
  ['city', 'c4', 0.02, 0.75],
  ['city', 'c7', 0.012, 0.75],
  ['c5', 'city', 0.016, 0.75],
  ['c5', 'maya', 0.02, 0.75],
  ['c1', 'c8', 0.03, 0.9],
  ['c2', 'c9', 0.03, 0.9],
  ['c4', 'c10', 0.03, 0.9],
  ['c3', 'c11', 0.03, 0.9],
  ['c7', 'c12', 0.03, 0.9],
  ['c12', 'c11', 0.04, 0.9],
  ['c13', 'acme', 0.012, 0.75],
  ['c13', 'c14', 0.014, 0.75],
  ['c14', 'hotel', 0.012, 0.75],
  ['c14', 'c9', 0.03, 0.9],
  ['c15', 'acme', 0.01, 0.75],
  ['c15', 'c3', 0.02, 0.75],
  ['c15', 'c8', 0.03, 0.9],
];

const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const scale = (a: V3, k: number): V3 => [a[0] * k, a[1] * k, a[2] * k];
const mix = (a: V3, b: V3, k: number): V3 => [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)];
export const len3 = (a: V3) => Math.hypot(a[0], a[1], a[2]);
export const dist3 = (a: V3, b: V3) => len3(sub(a, b));
export { add, sub, scale, mix };

/**
 * A thread hung between a and b: `n` points from one to the other, dropping `sag` m below the chord at its middle (a
 * parabola in the vertical: the shape a light cord takes between two pins).
 */
export function hang(a: V3, b: V3, sag: number, n: number): V3[] {
  return Array.from({ length: n }, (_, i) => {
    const s = i / (n - 1);
    const p = mix(a, b, s);
    p[1] -= 4 * sag * s * (1 - s);
    return p;
  });
}

// ------------------------------------------------------------------------------------------------ the dangling link

/**
 * The forward reference: maya.md's thread to [[facts/trips/lisbon-2026.md]] before the trip exists. It reaches toward
 * where the trip will be and falls short, its last third drooping, the loose end hanging a little below and before the
 * place and swaying (the air moving it). From the heal the end springs up onto the trip's pearl and the thread pulls
 * nearly taut. Times are song seconds.
 */
export const DANGLE = {
  /** The loose end: how far short of the place it hangs (fraction of the way), how far below it (m), and its sway (m, Hz). */
  short: 0.16,
  drop: 0.075,
  sway: 0.008,
  swayHz: 0.9,
  /** How much the thread hangs at its middle before the heal, and after it (m). */
  sagLoose: 0.035,
  sagTaut: 0.008,
  /** The end's spring onto the pearl (Hz, damping): fast, a small overshoot, the snap. */
  freq: 5.5,
  damping: 0.55,
};

/** Where the loose end is at t, and how far the heal has pulled it in (0 loose, 1 home; it overshoots a hair). */
export function looseEnd(t: number, from: V3, to: V3, heal: number): { end: V3; k: number } {
  const D = DANGLE;
  const short = mix(from, to, 1 - D.short);
  const sway = Math.sin(2 * Math.PI * D.swayHz * t) * D.sway, bob = Math.sin(2 * Math.PI * D.swayHz * 1.37 * t + 1.1) * D.sway * 0.4;
  const hung = add(short, [sway * 0.6, -D.drop + bob, sway]);
  const k = slam(t, heal, { freq: D.freq, damping: D.damping });
  return { end: mix(hung, to, k), k };
}

/** The dangling thread's centreline at t: hung from `from` to its loose end, drooping toward the end (n points). */
export function dangleAt(t: number, from: V3, to: V3, heal: number, n: number): V3[] {
  const { end, k } = looseEnd(t, from, to, heal);
  const sag = lerp(DANGLE.sagLoose, DANGLE.sagTaut, clamp(k));
  // the droop leans toward the loose end (a cord held at one end), and evens out as it is pulled taut
  const lean = lerp(0.62, 0.5, clamp(k));
  return Array.from({ length: n }, (_, i) => {
    const s = i / (n - 1);
    const p = mix(from, end, s);
    const u = s <= lean ? (s / lean) * 0.5 : 0.5 + ((s - lean) / (1 - lean)) * 0.5;
    p[1] -= 4 * sag * u * (1 - u);
    return p;
  });
}

// ------------------------------------------------------------------------------------------------ light along threads

/**
 * The dangling link's blood dashes along it (arc fraction 0..1): `count` dashes marching out toward the loose end, `duty`
 * of each lit, soft edges. Before the heal they march; on the heal they lengthen and close up from the root out, so the
 * thread fills with light, and the light turns moss (healBlend). Returns the blood envelope's level at u.
 */
export const DASH = { count: 11, duty: 0.46, speed: 0.55, soft: 0.08 };

/** A dash's light at arc fraction u at t: 1 inside a dash, 0 between them, soft edges, marching out toward the end. */
export function dashAt(u: number, t: number): number {
  const x = fract(u * DASH.count - t * DASH.speed);
  const s = DASH.soft;
  return smoothstep(0, s, x) * (1 - smoothstep(DASH.duty - s, DASH.duty, x));
}

/**
 * The heal's front along the dangling thread (arc fraction): it leaves maya.md (0) on the heal and reaches the trip (1)
 * at `reach`, decelerating into it; -1 before the heal.
 */
export function healFront(t: number, heal: number, reach: number): number {
  return t < heal ? -1 : prog(t, heal, reach, ease.outQuad) * 1.02;
}

/** The blood at arc fraction u: the dashes, ahead of the heal's front (swept away as it passes). */
export function bloodAt(u: number, t: number, heal: number, reach: number): number {
  const f = healFront(t, heal, reach);
  return dashAt(u, t) * smoothstep(-0.015, 0.025, u - f);
}

/**
 * The moss at arc fraction u: behind the heal's front, white-hot at the front and settling to an ember along the healed
 * thread (`ember`), the whole of it fading down to that ember after the front arrives.
 */
export function mossAt(u: number, t: number, heal: number, reach: number, ember = 0.22): number {
  const f = healFront(t, heal, reach);
  if (f < 0) return 0;
  const behind = smoothstep(-0.02, 0.015, f - u);
  const head = Math.exp(-Math.max(0, f - u) / 0.18);
  const after = t > reach ? Math.exp(-(t - reach) / 0.35) : 1;
  return behind * clamp(ember + (1 - ember) * head * after);
}

/**
 * A light running along a thread from u = 0 to u = 1 between `t0` and `t1` (a hop of the walk; the moss of an edge
 * landing running back): its head's place, eased, and a tail behind it. Level at arc fraction u.
 */
export function runAt(t: number, u: number, t0: number, t1: number, tail = 0.35): number {
  if (t < t0) return 0;
  const head = prog(t, t0, t1, ease.outCubic);
  const d = head - u;
  if (d < -0.04) return 0;
  const front = smoothstep(-0.04, 0.0, d);
  const behind = Math.exp(-Math.max(0, d) / tail);
  // once it has arrived the whole edge keeps an ember that fades
  const after = t > t1 ? Math.exp(-(t - t1) / 0.45) : 1;
  return clamp(front * lerp(0.4, 1, behind) * after + (t > t1 ? 0.2 * Math.exp(-(t - t1) / 1.4) : 0));
}

/** A seeded unit vector (the beads' turn round their bores). */
export function seeded(i: number): V3 {
  const a = hash(i, 3) * Math.PI * 2, z = hash(i, 7) * 2 - 1, r = Math.sqrt(1 - z * z);
  return [r * Math.cos(a), r * Math.sin(a), z];
}
