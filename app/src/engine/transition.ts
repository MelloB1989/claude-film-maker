// Transitions between adjacent scenes: the specs (transitions/<from>-<to>.ts), their windows around the cut, the time
// each side renders at, and the transition's own motion (whip, zoom, match, xfade, dip) as states over the shutter.
// Pure: no three.js, so bun tests it, and every value is a function of the spec, the scene windows and time.
// transition-gl.ts draws the states; engine.ts plans which layers a frame renders (framePlan).
import type { SceneSpan, VO } from './vo';
import { ease as EASE } from './util';
import { FPS, H as FH, W as FW } from './config';
import { ROLES } from './palette';

/**
 * The kinds. The first six draw with TransitionPass's original program; the rest (FX_KINDS) with its effects program:
 * - wipe: a soft edge sweeps across along `dir`, B behind it, with an optional glowing line on the edge (`edge`);
 * - iris: a circle grows from `center`, B inside it, with an optional glowing ring (`edge`);
 * - slide: B slides in over A along `dir` while A recedes (scales down, dims, drifts the same way more slowly);
 * - spin: a rotational whip about the centre, both pictures turning and scaling through the cut (edges mirrored);
 * - flash: A blows out into an exposure flash of `color` at the cut and B emerges from it;
 * - glitch: slice displacement and an RGB split around a hard switch at the cut, seeded by the pair.
 */
export type TransitionKind = 'cut' | 'whip' | 'match' | 'zoom' | 'xfade' | 'dip' | 'wipe' | 'iris' | 'slide' | 'spin' | 'flash' | 'glitch';
/** The kinds TransitionPass draws with its effects program (three vec4 per tap). */
export const FX_KINDS: readonly TransitionKind[] = ['wipe', 'iris', 'slide', 'spin', 'flash', 'glitch'];
export const isFxKind = (k: TransitionKind) => FX_KINDS.includes(k);
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
  /**
   * A unit vector (logical px axes: +x right, +y down) or an angle in degrees (0 right, 90 down).
   * whip: the way the CAMERA travels (required); the picture moves the other way. wipe: the way the edge sweeps (default
   * 0, left to right). slide: the way B travels in (default 180: B enters from the right, moving left).
   */
  dir?: [number, number] | number;
  /** whip: logical px the picture travels over the window (default: the frame's extent along dir). */
  distance?: number;
  /** zoom, iris: logical px the camera pushes through / the circle grows from; default the frame's centre. */
  center?: [number, number];
  /** zoom: A's scale at the cut (default 5). spin: both pictures' scale at the cut (default 1.3). */
  scale?: number;
  /** zoom: B's scale at the cut (default 1.6), settling to 1. */
  bFrom?: number;
  /** match: luma-key softness (default 0.12). wipe, iris: the edge's width, logical px (default 6% of the short side). */
  soft?: number;
  /** wipe, iris: a thin glowing line on the edge, in an accent (default none). */
  edge?: 'accent' | 'accent2' | null;
  /** spin: degrees turned over the window (default 90; negative turns the other way). */
  angle?: number;
  /** flash: the flash's colour, a palette role or #rrggbb (default 'fg'). */
  color?: string;
  /** glitch: strength (default 1): how far slices tear and how wide the RGB split runs. */
  amount?: number;
  /** Default 'inOutQuart' ('inOutCubic' for wipe, iris and slide). */
  ease?: 'inOutQuart' | 'inOutCubic' | 'outExpo';
}

/** A `dir` as a unit vector: an angle in degrees (0 right, 90 down) or a vector that must already be unit (else null). */
export function unitDir(d: [number, number] | number | undefined, fallback: [number, number] | number): [number, number] | null {
  const v = d ?? fallback;
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) return null;
    const r = (v * Math.PI) / 180;
    // (+ 0: never -0; snap the axes so 0, 90, 180 and 270 are exact)
    const c = Math.cos(r), s = Math.sin(r);
    return [(Math.abs(c) < 1e-12 ? 0 : c) + 0, (Math.abs(s) < 1e-12 ? 0 : s) + 0];
  }
  if (!Array.isArray(v) || v.length !== 2 || !v.every(Number.isFinite) || Math.abs(Math.hypot(v[0], v[1]) - 1) > 1e-6) return null;
  return [v[0], v[1]];
}

/** Default `dir` per kind (whip has none: it must say). */
const DEFAULT_DIR: Partial<Record<TransitionKind, number>> = { wipe: 0, slide: 180 };

/** A deterministic seed in [0, 1) from a pair's id (FNV-1a): a glitch's pattern is the pair's own. */
export function pairSeed(id: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h / 4294967296;
}

/** wipe and iris: the edge's width, logical px (6% of the frame's short side by default; at least 1 px). */
export function edgeSoft(spec: Pick<TransitionSpec, 'soft'>): number {
  return Math.max(1, spec.soft ?? 0.06 * Math.min(FW, FH));
}

/**
 * Where a wipe's edge runs: along unit `dir`, from `d0` (the frame's nearest corner along it, less half the soft
 * width) at edge progress 0 to `d1` (the farthest, plus half) at 1: so 0 shows all A and 1 all B.
 */
export function wipeTrack(spec: TransitionSpec): { dir: [number, number]; d0: number; d1: number; soft: number } {
  const dir = unitDir(spec.dir, DEFAULT_DIR.wipe!)!, soft = edgeSoft(spec);
  const ds = [[0, 0], [FW, 0], [0, FH], [FW, FH]].map(([x, y]) => x! * dir[0] + y! * dir[1]);
  return { dir, d0: Math.min(...ds) - soft / 2, d1: Math.max(...ds) + soft / 2, soft };
}

/** Where an iris's circle grows: from `center`, radius −soft/2 at progress 0 to the farthest corner + soft/2 at 1. */
export function irisTrack(spec: TransitionSpec): { center: [number, number]; r0: number; r1: number; soft: number } {
  const c = spec.center ?? [FW / 2, FH / 2], soft = edgeSoft(spec);
  const R = Math.max(...[[0, 0], [FW, 0], [0, FH], [FW, FH]].map(([x, y]) => Math.hypot(x! - c[0], y! - c[1])));
  return { center: [c[0], c[1]], r0: -soft / 2, r1: R + soft / 2, soft };
}

/** A transition module's default export (transitions/<from>-<to>.ts): its spec, or a function of the voiceover that makes it. */
export type TransitionModule = { default: TransitionSpec | ((vo: VO) => TransitionSpec) };

/** The spec a transition module gives for this voiceover. */
export function specOf(m: TransitionModule, vo: VO): TransitionSpec {
  return typeof m.default === 'function' ? m.default(vo) : m.default;
}

/** A validated spec on the timeline: `id` = `${from}-${to}`, its window [start, end) around `cut`. */
export interface TransitionEntry { id: string; spec: TransitionSpec; cut: number; start: number; end: number }

/**
 * A picture's placement, logical px: source point q shows at c + s·R(r)·(q − c) + (tx, ty), R(r) a turn by r radians
 * (clockwise on screen, +y being down; spin only, else 0 or absent).
 */
export interface Xform { tx: number; ty: number; s: number; cx: number; cy: number; r?: number }

export interface TransitionState {
  /** B's weight 0..1 (xfade, match, wipe, iris: nominal); 0 or 1 for the frame-sided kinds (whip: which picture leads). */
  wB: number;
  a: Xform;
  b: Xform;
  /** 0..1 dip toward ink. */
  ink: number;
  /** match: the luma threshold, 1 + soft → −soft (all A → all B); other kinds: -1. */
  match: number;
  /** wipe, iris: the edge's progress 0..1 (all A → all B). */
  edge?: number;
  /** wipe, iris: the edge line's light 0..1 (0 at both ends of the window); flash: the flash's level 0..1. */
  light?: number;
  /** slide: A dimmed toward ink 0..1, and the shadow B casts on it 0..1. */
  dim?: number;
  shadow?: number;
  /** glitch: its strength 0..1 (1 at the cut), and the frame its pattern is drawn for (constant over a frame's shutter). */
  glitch?: number;
  step?: number;
}

/** Uniform slots in TransitionPass: the most states a frame's shutter is drawn from. */
export const MAX_TAPS = 96;
/** The effects kinds pack three vec4 per tap in the same uniform array (two per tap for the others). */
export const MAX_FX_TAPS = Math.floor((2 * MAX_TAPS) / 3);
/** The most taps a kind's frame is drawn from. */
export const maxTaps = (kind: TransitionKind) => (isFxKind(kind) ? MAX_FX_TAPS : MAX_TAPS);
/**
 * TransitionPass draws SUB_TAPS samples along each span between two adjacent taps (their states interpolated), so n
 * taps give (n − 1)·SUB_TAPS samples over the shutter: the uniform array stays small while a streak is continuous.
 */
export const SUB_TAPS = 8;
/** The most a sample may step along a streak, physical px. */
const STEP_PX = 1.5;
/** How far before its end (s) a side holds at or past it (as engine.ts holds an entry). */
export const HOLD = 1e-6;
/** The longest side, s, and the largest share of its scene's window. */
const MAX_SIDE = 0.5, MAX_SHARE = 0.25;
/** One frame of the film (s). */
const frame = () => 1 / FPS;

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
      if (spec.dir === undefined || !unitDir(spec.dir, 0)) throw bad('a whip needs `dir`, a unit vector or an angle in degrees');
    }
    if (spec.kind === 'zoom' && ((spec.scale ?? 5) <= 0 || (spec.bFrom ?? 1.6) <= 0)) throw bad('zoom scales are positive');
    validateFx(spec, bad);
    const cut = A.end;
    const e: TransitionEntry = { id, spec, cut, start: cut - pre, end: cut + post };
    if (spec.kind !== 'cut') {
      const lo = cut - pre, hi = cut + post + frame();
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

const HEX_RE = /^#[0-9a-fA-F]{6}$/;
const finite = (x: unknown) => typeof x === 'number' && Number.isFinite(x);

/** The effects kinds' rules (transitionEntries): each failure is thrown through `bad`, which names the pair. */
function validateFx(spec: TransitionSpec, bad: (why: string) => Error) {
  const k = spec.kind;
  if ((k === 'wipe' || k === 'slide') && spec.dir !== undefined && !unitDir(spec.dir, 0)) throw bad(`a ${k}'s \`dir\` is a unit vector or an angle in degrees`);
  if (k === 'wipe' || k === 'iris') {
    if (spec.soft !== undefined && !(finite(spec.soft) && spec.soft >= 0)) throw bad(`a ${k}'s \`soft\` is a width in px, 0 or more (got ${spec.soft})`);
    if (spec.edge != null && spec.edge !== 'accent' && spec.edge !== 'accent2') throw bad(`a ${k}'s \`edge\` is 'accent', 'accent2' or null (only accents glow; got '${spec.edge}')`);
  }
  if (k === 'iris' && spec.center !== undefined && !(Array.isArray(spec.center) && spec.center.length === 2 && spec.center.every(finite))) throw bad('an iris `center` is [x, y] in logical px');
  if (k === 'spin') {
    if (spec.angle !== undefined && !(finite(spec.angle) && spec.angle !== 0)) throw bad(`a spin's \`angle\` is a nonzero number of degrees (got ${spec.angle})`);
    if (spec.scale !== undefined && !(finite(spec.scale) && spec.scale > 0)) throw bad(`a spin's \`scale\` is positive (got ${spec.scale})`);
  }
  if (k === 'flash' && spec.color !== undefined && !((ROLES as readonly string[]).includes(spec.color) || HEX_RE.test(spec.color))) {
    throw bad(`a flash's \`color\` is a palette role or #rrggbb (got '${spec.color}')`);
  }
  if (k === 'glitch' && spec.amount !== undefined && !(finite(spec.amount) && spec.amount > 0)) throw bad(`a glitch's \`amount\` is positive (got ${spec.amount})`);
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
  const k = e.spec.kind;
  const fn = EASE[e.spec.ease ?? (k === 'wipe' || k === 'iris' || k === 'slide' ? 'inOutCubic' : 'inOutQuart')];
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
      const d = unitDir(sp.dir, 0)!, dist = sp.distance ?? Math.abs(d[0]) * FW + Math.abs(d[1]) * FH;
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
    case 'wipe':
    case 'iris': {
      // the edge runs from all A to all B, fastest at the cut; its line is dark at both ends of the window
      const k = throughCut(e, s);
      st.edge = k;
      st.wB = k;
      st.light = sp.edge ? 4 * k * (1 - k) : 0;
      return st;
    }
    case 'slide': {
      // B travels in along dir from off frame and lands at rest; A drifts a quarter as far, shrinks 8% and dims, and B's
      // leading edge casts a soft shadow on it (0 at both ends)
      const d = unitDir(sp.dir, DEFAULT_DIR.slide!)!, L = Math.abs(d[0]) * FW + Math.abs(d[1]) * FH;
      const k = throughCut(e, s);
      st.b.tx = -d[0] * L * (1 - k) + 0; st.b.ty = -d[1] * L * (1 - k) + 0;
      st.a.tx = d[0] * L * 0.25 * k + 0; st.a.ty = d[1] * L * 0.25 * k + 0;
      st.a.s = 1 - 0.08 * k;
      st.wB = 1;
      st.dim = 0.6 * k;
      st.shadow = 0.5 * 4 * k * (1 - k);
      return st;
    }
    case 'spin': {
      // both turn the same way, A out to angle/2 at the cut and B in from −angle/2, both scaled `scale` there (geometric)
      const k = throughCut(e, s), th = ((sp.angle ?? 90) * Math.PI) / 180, S = sp.scale ?? 1.3;
      st.a.r = th * k + 0; st.b.r = -th * (1 - k) + 0;
      st.a.s = Math.exp(Math.log(S) * 2 * k);
      st.b.s = Math.exp(Math.log(S) * 2 * (1 - k));
      st.wB = k < 0.5 ? 0 : 1;
      return st;
    }
    case 'flash':
    case 'glitch': {
      // the frame's side; the effect peaks at the cut: rising (quadratic) through A's side, falling through B's
      const x = cut > start ? clamp01((s - start) / (cut - start)) : 1, y = end > cut ? clamp01((s - cut) / (end - cut)) : 1;
      const lvl = sideB ? (sp.kind === 'flash' ? (1 - y) ** 3 : (1 - y) ** 2) : x * x;
      if (sp.kind === 'flash') st.light = lvl;
      else {
        st.glitch = lvl;
        st.step = Math.round(s * FPS);
      }
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
  const taps = Array.from({ length: n }, (_, k) => stateOn(e, t + span * (k / (n - 1) - 0.5), sideB));
  // a glitch's pattern is the frame's: every tap draws the same one (a digital tear is crisp, never blurred)
  if (e.spec.kind === 'glitch') for (const x of taps) x.step = Math.round(t * FPS);
  return taps;
}

/** How far any shown point moves between two placements of a picture, logical px (an upper bound). */
function moved(p: Xform, q: Xform): number {
  // a source point at distance r from the centre moves |Δs|·r plus the translation; r is at most the farthest frame
  // corner from the placed centre, over the smaller scale. A turn moves every shown point at most R·|Δr| along its arc.
  const cx = p.cx + p.tx, cy = p.cy + p.ty;
  const R = Math.max(Math.hypot(cx, cy), Math.hypot(FW - cx, cy), Math.hypot(cx, FH - cy), Math.hypot(FW - cx, FH - cy));
  const d = Math.hypot(q.tx - p.tx, q.ty - p.ty) + (Math.abs(q.s - p.s) / Math.min(p.s, q.s)) * R;
  return p.r === undefined && q.r === undefined ? d : d + Math.abs((q.r ?? 0) - (p.r ?? 0)) * R;
}

/** How far an effects kind's edge moves between two states, logical px (wipe: along dir; iris: its radius). */
function edgeMoved(e: TransitionEntry, p: TransitionState, q: TransitionState): number {
  if (p.edge === undefined || q.edge === undefined) return 0;
  const span = e.spec.kind === 'wipe' ? (({ d0, d1 }) => d1 - d0)(wipeTrack(e.spec)) : (({ r0, r1 }) => r1 - r0)(irisTrack(e.spec));
  return Math.abs(q.edge - p.edge) * span;
}

/** How many probes tapCount walks the shutter with. */
const PROBES = 16;

/**
 * Taps for the frame at t (1..MAX_TAPS): enough that TransitionPass's samples (SUB_TAPS per span between taps) step at
 * most 1.5 physical px along the longest streak over the shutter, so a whip or a zoom streaks continuously instead of
 * in stepped copies. The streak is in physical px (`pxScale`: 2 at 4K, twice the taps). A weight that changes over the
 * shutter (xfade, dip, match; flash's level, slide's dim, glitch's strength, an edge's light) counts its change in
 * 8-bit levels as px; a wipe's or an iris's edge counts its travel as a streak; a spin counts its arc. At most
 * maxTaps(kind). 1 outside the window.
 */
export function tapCount(e: TransitionEntry, t: number, dt: number, shutter: number, pxScale: number): number {
  if (!(t >= e.start && t < e.end)) return 1;
  const s = shutterTaps(e, t, dt, shutter, PROBES + 1);
  const fx = isFxKind(e.spec.kind);
  let streak = 0, levels = 0;
  let sa = 0, sb = 0, se = 0;
  for (let k = 1; k < s.length; k++) {
    const p = s[k - 1]!, q = s[k]!;
    sa += moved(p.a, q.a);
    sb += moved(p.b, q.b);
    levels += 255 * (Math.abs(q.wB - p.wB) * (e.spec.kind === 'xfade' ? 1 : 0) + Math.abs(q.ink - p.ink) + (q.match > -1 ? Math.abs(q.match - p.match) : 0));
    if (fx) {
      se += edgeMoved(e, p, q);
      const d = (a?: number, b?: number) => Math.abs((b ?? 0) - (a ?? 0));
      levels += 255 * (d(p.light, q.light) + d(p.dim, q.dim) + d(p.shadow, q.shadow) + d(p.glitch, q.glitch));
    }
  }
  streak = Math.max(sa, sb, se) * pxScale;
  const samples = Math.max(streak / STEP_PX, levels / STEP_PX);
  if (samples <= 1) return 1;
  return Math.min(maxTaps(e.spec.kind), Math.ceil(samples / SUB_TAPS) + 1);
}

/**
 * wipe, iris: B's weight at logical px `p` in state `s`, as TransitionPass draws it: 1 − smoothstep(e − soft/2,
 * e + soft/2, d), d the point's distance along dir (wipe) or from the centre (iris), e the edge's at its progress.
 */
export function edgeWeight(e: TransitionEntry, s: TransitionState, p: [number, number]): number {
  const k = s.edge ?? 0;
  let d: number, at: number, soft: number;
  if (e.spec.kind === 'wipe') {
    const w = wipeTrack(e.spec);
    d = p[0] * w.dir[0] + p[1] * w.dir[1];
    at = w.d0 + (w.d1 - w.d0) * k;
    soft = w.soft;
  } else {
    const w = irisTrack(e.spec);
    d = Math.hypot(p[0] - w.center[0], p[1] - w.center[1]);
    at = w.r0 + (w.r1 - w.r0) * k;
    soft = w.soft;
  }
  const x = clamp01((d - (at - soft / 2)) / soft);
  return 1 - x * x * (3 - 2 * x);
}

/** match: B's weight where A's display luma is `lumaA`: smoothstep(threshold − soft, threshold + soft, lumaA). */
export function matchWeight(threshold: number, lumaA: number, soft: number): number {
  const x = clamp01((lumaA - (threshold - soft)) / (2 * soft));
  return x * x * (3 - 2 * x);
}
