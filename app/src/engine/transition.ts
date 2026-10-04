// Transitions between adjacent scenes: the specs (transitions/<from>-<to>.ts), their windows around the cut, the time
// each side renders at, and the transition's own motion (whip, zoom, match, xfade, dip) as states over the shutter.
// Pure: no three.js, so bun tests it, and every value is a function of the spec, the scene windows and time.
// transition-gl.ts draws the states; engine.ts plans which layers a frame renders (framePlan).
import type { SceneSpan, VO } from './vo';
import { ease as EASE } from './util';

export type TransitionKind = 'cut' | 'whip' | 'match' | 'zoom' | 'xfade' | 'dip';
/** How a side renders inside the window: 'hold' clamps into its own window, 'run' into its handles. */
export type SideMode = 'hold' | 'run';
/** Seconds a scene may render before its start (head) and after its end (tail): engine-built content only. */
export interface Handles { head: number; tail: number }

export interface TransitionSpec {
  /** Adjacent scene ids in vo.json. */
  from: string;
  to: string;
  kind: TransitionKind;
  /** Seconds of window before and after the cut (0, 0 for 'cut'). */
  pre: number;
  post: number;
  /** Default 'hold'. */
  fromMode?: SideMode;
  toMode?: SideMode;
  /** whip: unit direction the CAMERA travels (logical px axes: +x right, +y down); the picture moves the other way. */
  dir?: [number, number];
  /** whip: logical px the picture travels over the window (default: the frame's extent along dir). */
  distance?: number;
  /** zoom: logical px the camera pushes through (A) and emerges from (B); default the frame's centre. */
  center?: [number, number];
  /** zoom: A's scale at the cut (default 5). */
  scale?: number;
  /** zoom: B's scale at the cut (default 1.6), settling to 1. */
  bFrom?: number;
  /** match: luma-key softness (default 0.12). */
  soft?: number;
  /** Default 'inOutQuart'. */
  ease?: 'inOutQuart' | 'inOutCubic' | 'outExpo';
}

/** A transition module's default export (transitions/<from>-<to>.ts): its spec, or a function of the voiceover that makes it. */
export type TransitionModule = { default: TransitionSpec | ((vo: VO) => TransitionSpec) };

/** The spec a transition module gives for this voiceover. */
export function specOf(m: TransitionModule, vo: VO): TransitionSpec {
  return typeof m.default === 'function' ? m.default(vo) : m.default;
}

/** A validated spec on the timeline: `id` = `${from}-${to}`, its window [start, end) around `cut`. */
export interface TransitionEntry { id: string; spec: TransitionSpec; cut: number; start: number; end: number }

/** A picture's placement, logical px: source point q shows at c + s·(q − c) + (tx, ty). */
export interface Xform { tx: number; ty: number; s: number; cx: number; cy: number }

export interface TransitionState {
  /** B's weight 0..1 (xfade, match: nominal); 0 or 1 for the frame-sided kinds (whip: which picture leads). */
  wB: number;
  a: Xform;
  b: Xform;
  /** 0..1 dip toward ink. */
  ink: number;
  /** match: the luma threshold, 1 + soft → −soft (all A → all B); other kinds: -1. */
  match: number;
}

/** Uniform slots in TransitionPass: the most states a frame's shutter is drawn from. */
export const MAX_TAPS = 96;
/**
 * TransitionPass draws SUB_TAPS samples along each span between two adjacent taps (their states interpolated), so n
 * taps give (n − 1)·SUB_TAPS samples over the shutter: the uniform array stays small while a streak is continuous.
 */
export const SUB_TAPS = 8;
/** The most a sample may step along a streak, physical px. */
const STEP_PX = 1.5;
/** How far before its end (s) a side holds at or past it (as engine.ts holds an entry). */
export const HOLD = 1e-6;
/** The logical frame. */
const FW = 1920, FH = 1080;
/** The longest side, s, and the largest share of its scene's window. */
const MAX_SIDE = 0.5, MAX_SHARE = 0.25;
const FRAME = 1 / 30;

const r3 = (x: number) => x.toFixed(3);
const num = (x: number) => String(+x.toFixed(3));

/**
 * The specs on the timeline, validated (each failure throws, naming the pair and the rule):
 * - `from` and `to` are adjacent in `scenes`; the cut is the boundary between them;
 * - 0 ≤ pre, post ≤ 0.5 s, pre ≤ 25% of A's window and post ≤ 25% of B's; a 'cut' has pre = post = 0;
 * - one spec per pair, and no two windows overlap;
 * - no word onset falls in [cut − pre, cut + post + 1/30) (a word is never spoken mid-transition; a 'cut' has no window).
 * Returned in cut order.
 */
export function transitionEntries(specs: TransitionSpec[], scenes: SceneSpan[], words: { start: number; w?: string }[]): TransitionEntry[] {
  const seen = new Set<string>();
  const out = specs.map((spec) => {
    const id = `${spec.from}-${spec.to}`;
    const bad = (why: string) => new Error(`transition ${id}: ${why}`);
    const i = scenes.findIndex((s) => s.id === spec.from);
    if (i < 0) throw bad(`${spec.from} is not a scene in vo.json`);
    if (!scenes.some((s) => s.id === spec.to)) throw bad(`${spec.to} is not a scene in vo.json`);
    const A = scenes[i]!, B = scenes[i + 1];
    if (!B || B.id !== spec.to) throw bad(`${spec.from} and ${spec.to} are not adjacent in vo.json`);
    if (seen.has(id)) throw bad('a pair takes one transition, given once');
    seen.add(id);
    const { pre, post } = spec;
    if (!(Number.isFinite(pre) && Number.isFinite(post))) throw bad('pre and post must be numbers');
    if (spec.kind === 'cut') {
      if (pre !== 0 || post !== 0) throw bad(`a 'cut' has no window: pre and post are 0 (got ${pre}, ${post})`);
    } else {
      if (pre < 0 || post < 0 || pre > MAX_SIDE || post > MAX_SIDE) throw bad(`each side is 0 to ${MAX_SIDE} s (pre ${pre}, post ${post})`);
      if (pre + post <= 0) throw bad(`a '${spec.kind}' needs a window (pre + post > 0)`);
      if (pre > MAX_SHARE * (A.end - A.start) + 1e-9) throw bad(`pre ${pre} s is over 25% of ${A.id}'s ${r3(A.end - A.start)} s window`);
      if (post > MAX_SHARE * (B.end - B.start) + 1e-9) throw bad(`post ${post} s is over 25% of ${B.id}'s ${r3(B.end - B.start)} s window`);
    }
    if (spec.kind === 'whip') {
      const d = spec.dir;
      if (!d || Math.abs(Math.hypot(d[0], d[1]) - 1) > 1e-6) throw bad('a whip needs `dir`, a unit vector');
    }
    if (spec.kind === 'zoom' && ((spec.scale ?? 5) <= 0 || (spec.bFrom ?? 1.6) <= 0)) throw bad('zoom scales are positive');
    const cut = A.end;
    const e: TransitionEntry = { id, spec, cut, start: cut - pre, end: cut + post };
    if (spec.kind !== 'cut') {
      const lo = cut - pre, hi = cut + post + FRAME;
      const w = words.find((x) => x.start >= lo && x.start < hi);
      if (w) throw bad(`${w.w !== undefined ? `word "${w.w}"` : 'a word'} (${num(w.start)}) starts inside [${r3(lo)}, ${r3(hi)})`);
    }
    return e;
  }).sort((a, b) => a.cut - b.cut);
  for (let k = 1; k < out.length; k++) {
    if (out[k]!.start < out[k - 1]!.end) throw new Error(`transition ${out[k]!.id}: its window overlaps ${out[k - 1]!.id}'s`);
  }
  return out;
}

/**
 * The time a side renders at for song time t: 'hold' clamps into its own window [start, end) (at or past the end it is
 * end − HOLD), 'run' into [start − head, end + tail). `held` when clamped (no time passes for it).
 */
export function sideTime(mode: SideMode, t: number, w: { start: number; end: number }, h: Handles): { time: number; held: boolean } {
  const lo = mode === 'run' ? w.start - h.head : w.start, hi = mode === 'run' ? w.end + h.tail : w.end;
  if (t < lo) return { time: lo, held: true };
  if (t >= hi) return { time: hi - HOLD, held: true };
  return { time: t, held: false };
}

const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);
const ident = (c: [number, number]): Xform => ({ tx: 0, ty: 0, s: 1, cx: c[0], cy: c[1] });

/**
 * Window progress eased through the cut: [0, uc] → [0, 0.5] on the ease's first half and [uc, 1] → [0.5, 1] on its
 * second (uc = pre / (pre + post)), so the cut is always the ease's midpoint, its fastest moment.
 */
function throughCut(e: TransitionEntry, t: number): number {
  const fn = EASE[e.spec.ease ?? 'inOutQuart'];
  const { start, cut, end } = e;
  if (t <= start) return 0;
  if (t >= end) return 1;
  return t < cut ? fn(0.5 * (t - start) / (cut - start)) : fn(0.5 + 0.5 * (t - cut) / (end - cut));
}

/** The state at time s, the side (which picture shows, for zoom and dip) given by `sideB`. */
function stateOn(e: TransitionEntry, s: number, sideB: boolean): TransitionState {
  const sp = e.spec, c: [number, number] = sp.center ?? [FW / 2, FH / 2];
  const st: TransitionState = { wB: sideB ? 1 : 0, a: ident(c), b: ident(c), ink: 0, match: -1 };
  const { start, cut, end } = e;
  switch (sp.kind) {
    case 'cut':
      return st;
    case 'whip': {
      const d = sp.dir!, dist = sp.distance ?? Math.abs(d[0]) * FW + Math.abs(d[1]) * FH;
      const k = throughCut(e, s);
      // (+ 0: never -0, so a still axis compares equal to 0)
      st.a.tx = -d[0] * dist * k + 0; st.a.ty = -d[1] * dist * k + 0;
      st.b.tx = d[0] * dist * (1 - k) + 0; st.b.ty = d[1] * dist * (1 - k) + 0;
      st.wB = k < 0.5 ? 0 : 1;
      return st;
    }
    case 'zoom': {
      // geometric in scale (a push reads as even speed), A in-quart to `scale`, B out-quart from `bFrom`
      const xa = cut > start ? clamp01((s - start) / (cut - start)) : 1;
      const xb = end > cut ? clamp01((s - cut) / (end - cut)) : 1;
      st.a.s = Math.exp(Math.log(sp.scale ?? 5) * EASE.inQuart(xa));
      st.b.s = Math.exp(Math.log(sp.bFrom ?? 1.6) * (1 - EASE.outQuart(xb)));
      return st;
    }
    case 'match': {
      const k = throughCut(e, s);
      // over [1 + soft, −soft], so the first frame is all A and the last all B (the smoothstep spans thr ± soft)
      const soft = sp.soft ?? 0.12;
      st.match = 1 + soft - k * (1 + 2 * soft);
      st.wB = k;
      return st;
    }
    case 'xfade':
      st.wB = EASE.inOutCubic(clamp01((s - start) / (end - start)));
      return st;
    case 'dip': {
      const fn = EASE[sp.ease ?? 'inOutQuart'];
      st.ink = sideB ? (end > cut ? 1 - fn(clamp01((s - cut) / (end - cut))) : 0) : cut > start ? fn(clamp01((s - start) / (cut - start))) : 1;
      return st;
    }
  }
}

/** The transition's state at t (u = (t − start)/(end − start) clamped to the window; the side by t against the cut). */
export function stateAt(e: TransitionEntry, t: number): TransitionState {
  return stateOn(e, t, t >= e.cut);
}

/**
 * n states evenly over the shutter of the frame at t, [t − dt·shutter/2, t + dt·shutter/2], both ends included (n = 1:
 * the state at t). The side is the frame's (t against the cut) for every tap: a zoom's or a dip's frame never mixes A
 * and B, and a tap past the cut holds its side's end state.
 */
export function shutterTaps(e: TransitionEntry, t: number, dt: number, shutter: number, n: number): TransitionState[] {
  const sideB = t >= e.cut, span = dt * shutter;
  if (n <= 1) return [stateOn(e, t, sideB)];
  return Array.from({ length: n }, (_, k) => stateOn(e, t + span * (k / (n - 1) - 0.5), sideB));
}

/** How far any shown point moves between two placements of a picture, logical px (an upper bound). */
function moved(p: Xform, q: Xform): number {
  // a source point at distance r from the centre moves |Δs|·r plus the translation; r is at most the farthest frame
  // corner from the placed centre, over the smaller scale
  const cx = p.cx + p.tx, cy = p.cy + p.ty;
  const R = Math.max(Math.hypot(cx, cy), Math.hypot(FW - cx, cy), Math.hypot(cx, FH - cy), Math.hypot(FW - cx, FH - cy));
  return Math.hypot(q.tx - p.tx, q.ty - p.ty) + (Math.abs(q.s - p.s) / Math.min(p.s, q.s)) * R;
}

/** How many probes tapCount walks the shutter with. */
const PROBES = 16;

/**
 * Taps for the frame at t (1..MAX_TAPS): enough that TransitionPass's samples (SUB_TAPS per span between taps) step at
 * most 1.5 physical px along the longest streak over the shutter, so a whip or a zoom streaks continuously instead of
 * in stepped copies. The streak is in physical px (`pxScale`: 2 at 4K, twice the taps). A weight that changes over the
 * shutter (xfade, dip, match) counts its change in 8-bit levels as px. 1 outside the window.
 */
export function tapCount(e: TransitionEntry, t: number, dt: number, shutter: number, pxScale: number): number {
  if (!(t >= e.start && t < e.end)) return 1;
  const s = shutterTaps(e, t, dt, shutter, PROBES + 1);
  let streak = 0, levels = 0;
  let sa = 0, sb = 0;
  for (let k = 1; k < s.length; k++) {
    const p = s[k - 1]!, q = s[k]!;
    sa += moved(p.a, q.a);
    sb += moved(p.b, q.b);
    levels += 255 * (Math.abs(q.wB - p.wB) * (e.spec.kind === 'xfade' ? 1 : 0) + Math.abs(q.ink - p.ink) + (q.match > -1 ? Math.abs(q.match - p.match) : 0));
  }
  streak = Math.max(sa, sb) * pxScale;
  const samples = Math.max(streak / STEP_PX, levels / STEP_PX);
  if (samples <= 1) return 1;
  return Math.min(MAX_TAPS, Math.ceil(samples / SUB_TAPS) + 1);
}

/** match: B's weight where A's display luma is `lumaA`: smoothstep(threshold − soft, threshold + soft, lumaA). */
export function matchWeight(threshold: number, lumaA: number, soft: number): number {
  const x = clamp01((lumaA - (threshold - soft)) / (2 * soft));
  return x * x * (3 - 2 * x);
}
