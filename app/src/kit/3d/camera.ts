// The 3D kit's camera, as pure functions: where a camera stands to frame a subject at a live aspect, and the camera-move
// vocabulary a block takes as params. No three.js, no DOM: bun tests every function, and a block turns the results into
// CamKeys (stage.ts CameraRig) or sets its camera from them each frame.
//
// A framing is an orbit: a target, an azimuth (degrees round the world's y axis from +z; + puts the camera to the
// subject's right), an elevation (degrees above the horizon; + looks down), a distance and a vertical fov. A move is a
// function of the shot's progress that offsets the framing: it pushes (the distance shrinks), pulls, orbits (the azimuth
// swings), drifts (a slow breathing figure of a few degrees), dollies (the camera and its target slide sideways), cranes
// (the camera rises over the subject) or holds. `amount` scales every move (1 is the house's: slow and luxurious; 2 is
// bold); the ease is the shot's (default inOutCubic for push, pull, orbit, dolly and crane, linear for drift).
import { clamp, ease, lerp } from '../../engine/util';

export type V3 = [number, number, number];

/** A named move (or a block's own keys: see Scene3D `camera`). */
export type CameraMove = 'static' | 'push' | 'pull' | 'orbit' | 'drift' | 'dolly' | 'crane';
export const CAMERA_MOVES: readonly CameraMove[] = ['static', 'push', 'pull', 'orbit', 'drift', 'dolly', 'crane'];

export interface Orbit {
  target: V3;
  /** Degrees round y from +z (+: the camera to the subject's right). */
  az: number;
  /** Degrees above the horizon (+: looking down). */
  el: number;
  dist: number;
  /** Vertical fov (degrees). */
  fov: number;
  /** Degrees about the view axis. */
  roll?: number;
}

/** What a move adds to a framing at a moment: a distance factor, degrees of azimuth, elevation and roll, a slide (fraction of the distance, camera and target together, in the view's right and up). */
export interface MoveOffset {
  dist: number;
  az: number;
  el: number;
  roll: number;
  slide: [number, number];
}

export const NO_MOVE: Readonly<MoveOffset> = { dist: 1, az: 0, el: 0, roll: 0, slide: [0, 0] };

/** The house numbers of each move at amount 1. */
export const MOVE = {
  /** push and pull: the distance closes by `dist` of itself over the shot. */
  push: { dist: 0.16 },
  /** orbit: the azimuth swings `az` degrees over the shot, centred on the framing. */
  orbit: { az: 22 },
  /** drift: a slow figure of `az` and `el` degrees and a hair of push, one period per `period` s. */
  drift: { az: 3.2, el: 1.6, dist: 0.035, roll: 0.5, period: 9 },
  /** dolly: the camera and its target slide `slide` of the distance sideways over the shot, centred on the framing. */
  dolly: { slide: 0.16 },
  /** crane: the elevation rises `el` degrees over the shot (from below the framing to above it) with a touch of push. */
  crane: { el: 12, dist: 0.06 },
} as const;

/**
 * A move's offset at shot progress p (0..1) and shot time lt (s, for the drift's figure), scaled by `amount`. Pure.
 * Throws on a name it does not know (a typo in film.ts fails while authoring).
 */
export function moveAt(move: CameraMove, p: number, lt: number, amount = 1, fn: (x: number) => number = ease.inOutCubic): MoveOffset {
  const k = fn(clamp(p));
  switch (move) {
    case 'static': return { ...NO_MOVE, slide: [0, 0] };
    case 'push': return { ...NO_MOVE, slide: [0, 0], dist: 1 + MOVE.push.dist * amount * (0.5 - k) };
    case 'pull': return { ...NO_MOVE, slide: [0, 0], dist: 1 - MOVE.push.dist * amount * (0.5 - k) };
    case 'orbit': return { ...NO_MOVE, slide: [0, 0], az: MOVE.orbit.az * amount * (k - 0.5) };
    case 'drift': {
      const D = MOVE.drift, w = (2 * Math.PI * lt) / D.period;
      return { dist: 1 + D.dist * amount * (0.5 - clamp(p)), az: D.az * amount * Math.sin(w), el: D.el * amount * Math.sin(2 * w + 0.7), roll: D.roll * amount * Math.sin(w + 1.3), slide: [0, 0] };
    }
    case 'dolly': return { ...NO_MOVE, slide: [MOVE.dolly.slide * amount * (k - 0.5), 0] };
    case 'crane': return { ...NO_MOVE, el: MOVE.crane.el * amount * (k - 0.5), dist: 1 + MOVE.crane.dist * amount * (0.5 - k), slide: [0, 0] };
    default: throw new Error(`unknown camera move '${move as string}' (moves: ${CAMERA_MOVES.join(', ')}, or a list of keys)`);
  }
}

/** Two offsets combined (factors multiply, the rest add). */
export function combine(a: MoveOffset, b: MoveOffset): MoveOffset {
  return { dist: a.dist * b.dist, az: a.az + b.az, el: a.el + b.el, roll: a.roll + b.roll, slide: [a.slide[0] + b.slide[0], a.slide[1] + b.slide[1]] };
}

/** An orbit moved by an offset. */
export function moved(o: Orbit, m: MoveOffset): Orbit {
  return { ...o, az: o.az + m.az, el: o.el + m.el, dist: o.dist * m.dist, roll: (o.roll ?? 0) + m.roll, target: slid(o, m.slide) };
}

/** The view's right and up (unit vectors) for an azimuth and elevation, and the direction back to the camera. */
export function basis(az: number, el: number): { back: V3; right: V3; up: V3 } {
  const a = (az * Math.PI) / 180, e = (el * Math.PI) / 180;
  const back: V3 = [Math.sin(a) * Math.cos(e), Math.sin(e), Math.cos(a) * Math.cos(e)];
  const right: V3 = [Math.cos(a), 0, -Math.sin(a)];
  // up = back × right
  const up: V3 = [back[1] * right[2] - back[2] * right[1], back[2] * right[0] - back[0] * right[2], back[0] * right[1] - back[1] * right[0]];
  return { back, right, up };
}

function slid(o: Orbit, s: [number, number]): V3 {
  if (!s[0] && !s[1]) return [...o.target];
  const { right, up } = basis(o.az, o.el);
  return [0, 1, 2].map((i) => o.target[i]! + (right[i]! * s[0] + up[i]! * s[1]) * o.dist) as V3;
}

/** The camera's position for an orbit. */
export function orbitPos(o: Orbit): V3 {
  const { back } = basis(o.az, o.el);
  return [o.target[0] + back[0] * o.dist, o.target[1] + back[1] * o.dist, o.target[2] + back[2] * o.dist];
}

/**
 * The distance at which a box `w` x `h` (world units, square to the view) fills a frame of `aspect` (W / H) with a
 * `fov`° vertical lens, leaving `margin` (a fraction of the frame, each side) clear: whichever of its width and its
 * height is the tighter fit decides. So a wide headline backs the camera off in a vertical frame, a tall stack in a
 * landscape one.
 */
export function fitDistance(w: number, h: number, fov: number, aspect: number, margin: number | [number, number] = 0.1): number {
  const [mx, my] = typeof margin === 'number' ? [margin, margin] : margin;
  const ty = Math.tan((fov * Math.PI) / 360), tx = ty * aspect;
  return Math.max(w / (2 * tx * Math.max(0.05, 1 - 2 * mx)), h / (2 * ty * Math.max(0.05, 1 - 2 * my)));
}

/** World units per logical px at `dist` from a `fov`° lens in a frame `H` px tall (the inverse of stage.ts typePxPerUnit). */
export const unitsPerPx = (fov: number, dist: number, H: number) => (2 * dist * Math.tan((fov * Math.PI) / 360)) / H;

/** The whip's numbers: it turns the camera `deg` degrees over `dur` s (60-120 ms) ending on the cut. */
export const WHIP = { deg: 28, dur: 0.11 } as const;

export type WhipDir = 'left' | 'right' | 'up' | 'down';

/**
 * A whip out at the end of a shot: the camera turns toward `dir`, accelerating (inQuart) over the last `dur` seconds
 * before `end` so it leaves the frame at speed on the cut (the next shot's whip transition picks it up). A pan: the
 * camera turns about itself, `yaw` degrees about its up axis (+: to the left) and `pitch` about its right (+: up), so
 * the picture leaves the other way. 0 before the window.
 */
export function whipOut(t: number, end: number, dir: WhipDir, o: { deg?: number; dur?: number } = {}): { yaw: number; pitch: number } {
  const { deg = WHIP.deg, dur = WHIP.dur } = o;
  const d = deg * ease.inQuart(clamp((t - (end - dur)) / dur));
  return { yaw: dir === 'left' ? d : dir === 'right' ? -d : 0, pitch: dir === 'up' ? d : dir === 'down' ? -d : 0 };
}

/** Linear interpolation of two V3s. */
export const lerp3 = (a: V3, b: V3, k: number): V3 => [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)];
