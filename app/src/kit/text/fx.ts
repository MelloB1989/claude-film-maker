// Kinetic type, as pure functions: when each unit of a text lands (a stagger, the beat grid, explicit times, or the
// voiceover's spoken onsets), and how a unit looks at a time relative to its landing (rise, slam, blur, track, fade,
// typewriter, scramble, wipe, ghost), how a block leaves, balanced wrapping, word diffs and caption chunks. No DOM, no
// canvas: every value is a function of its inputs and time, so frames render the same in any order (motion blur's
// sub-frames, seeks) and bun tests them. States that step (a typed glyph, a scrambled one) snap to the frame grid
// (util.frameIdx), so every sub-frame of a frame agrees.
//
// Units: offsets, blur and tracking are in em of the unit's font size (the caller multiplies by its px size).
import { slam, spring } from '../../engine/motion';
import { FPS, clamp, ease, frameIdx, hash, lerp, prog, pulse } from '../../engine/util';
import { norm } from '../../engine/vo';

// ------------------------------------------------------------------------------------------------ time

/**
 * A time inside a shot: seconds after its start, `{ s }` the same, `{ beat: n }` the n-th beat of the film's grid
 * counted from the first beat at or after the shot's start (0 is that beat; fractions allowed: 0.5 is the "and"),
 * `{ bar: n }` the same for downbeats.
 */
export type TimeRef = number | { s: number } | { beat: number } | { bar: number };

/** The beat grid a TimeRef reads (AudioData has it). */
export interface Grid {
  beatAt(t: number): number;
  timeOfBeat(i: number): number;
  barAt(t: number): number;
  timeOfBar(i: number): number;
}

/** Song time of `ref` in a shot that starts at `start` (song seconds). Beats and bars need the grid. */
export function resolveTime(ref: TimeRef, start: number, grid?: Grid): number {
  if (typeof ref === 'number') return start + ref;
  if ('s' in ref) return start + ref.s;
  if (!grid) throw new Error('a time in beats or bars needs the film\'s beat grid');
  if ('beat' in ref) return grid.timeOfBeat(Math.ceil(grid.beatAt(start) - 1e-6) + ref.beat);
  return grid.timeOfBar(Math.ceil(grid.barAt(start) - 1e-6) + ref.bar);
}

/**
 * Landing times of `n` units, the first at `first` (song s): `stagger` seconds apart, or, with `every` (beats) and a
 * grid, on the grid every `every` beats from `first`'s beat (a fractional `first` beat keeps its offset).
 */
export function staggerTimes(n: number, first: number, o: { stagger?: number; every?: number; grid?: Grid } = {}): number[] {
  const out: number[] = [];
  if (o.every !== undefined && o.grid) {
    const b0 = o.grid.beatAt(first);
    for (let i = 0; i < n; i++) out.push(i === 0 ? first : o.grid.timeOfBeat(b0 + i * o.every));
    return out;
  }
  const s = o.stagger ?? 0.08;
  for (let i = 0; i < n; i++) out.push(first + i * s);
  return out;
}

/** A word with spoken times (vo.ts Word, a caption's word). */
export interface Spoken { w: string; start: number; end: number }
/** A span of song time, and whether it came from the voiceover (false: interpolated). */
export interface Span { start: number; end: number; matched: boolean }

/**
 * The display words of a text matched in order to spoken words (the shot's voiceover), so each lands on its onset.
 * Matching folds case and punctuation (vo.ts norm: "it’s" = "its"); a display word may skip up to `lookahead` spoken
 * words to find its match (a spoken filler the screen leaves out). A display word the voice never says is placed
 * between its matched neighbours, never before the one before it: highlighting never runs ahead of the voice. Words
 * after the last match follow it `gap` seconds apart. With no spoken words at all every span is `fallback`'s.
 */
export function alignToVO(display: readonly string[], spoken: readonly Spoken[], o: { lookahead?: number; gap?: number; fallback?: number } = {}): Span[] {
  const look = o.lookahead ?? 4, gap = o.gap ?? 0.18;
  const out: (Span | null)[] = display.map(() => null);
  let j = 0;
  display.forEach((d, i) => {
    const key = norm(d);
    if (!key) return;
    for (let k = j; k < Math.min(spoken.length, j + 1 + look); k++) {
      if (norm(spoken[k]!.w) === key) {
        out[i] = { start: spoken[k]!.start, end: spoken[k]!.end, matched: true };
        j = k + 1;
        return;
      }
    }
  });
  // fill the gaps: between matched neighbours, spread evenly; before the first, at the first; after the last, gap apart
  const fb = o.fallback ?? 0;
  for (let i = 0; i < out.length; i++) {
    if (out[i]) continue;
    let a = i - 1;
    while (a >= 0 && !out[a]?.matched) a--;
    let b = i + 1;
    while (b < out.length && !out[b]?.matched) b++;
    const A = a >= 0 ? out[a]! : null, B = b < out.length ? out[b]! : null;
    let start: number;
    if (A && B) start = lerp(A.start, B.start, (i - a) / (b - a));
    else if (A) start = A.start + (i - a) * gap;
    else if (B) start = B.start;
    else start = fb + i * gap;
    out[i] = { start, end: start + gap * 0.9, matched: false };
  }
  return out as Span[];
}

/**
 * Landing times of a spoken word's `n` glyphs: spread over the time it is spoken, the first on its onset, so a word
 * types or lands glyph by glyph as it is said and never ahead of it.
 */
export function glyphTimes(span: { start: number; end: number }, n: number): number[] {
  const d = Math.max(0, span.end - span.start);
  return Array.from({ length: n }, (_, j) => span.start + (n > 1 ? (j / n) * d : 0));
}

// ------------------------------------------------------------------------------------------------ reveals

export type Reveal = 'rise' | 'slam' | 'blur' | 'track' | 'typewriter' | 'scramble' | 'wipe' | 'fade' | 'ghost';
export const REVEALS: readonly Reveal[] = ['rise', 'slam', 'blur', 'track', 'typewriter', 'scramble', 'wipe', 'fade', 'ghost'];

/** How a unit looks: offsets, blur and extra tracking in em; `clip` 0..1 of its width shown (a wipe). */
export interface UnitState {
  alpha: number;
  dx: number;
  dy: number;
  scale: number;
  blur: number;
  clip: number;
  track: number;
}

export const SHOWN: Readonly<UnitState> = { alpha: 1, dx: 0, dy: 0, scale: 1, blur: 0, clip: 1, track: 0 };
const HIDDEN: Readonly<UnitState> = { alpha: 0, dx: 0, dy: 0, scale: 1, blur: 0, clip: 0, track: 0 };

/** The motion of each reveal (house style: fast, tight springs, no cartoon bounce). */
export const REVEAL = {
  /** rise: from `drop` em below (the line's mask hides it), a 4 Hz spring at 0.72 (4% overshoot) landing at `at`. */
  rise: { drop: 0.9, freq: 4, damping: 0.72, fadeIn: 0.12 },
  /** slam: from `from`x scale to 1, the house spring (5 Hz, 0.6) whose first arrival is the hit. */
  slam: { from: 1.9, blur: 0.06, freq: 5, damping: 0.6, fadeIn: 0.04 },
  /** blur: out of a `blur` em defocus, a hair large, over `dur` (outCubic). */
  blur: { blur: 0.22, scale: 0.05, dur: 0.5 },
  /** track: from `track` em of extra spacing per glyph to none, over `dur` (outExpo). */
  track: { track: 0.55, dur: 0.95, fadeIn: 0.35 },
  /** fade: in over `dur`, rising the last `rise` em. */
  fade: { dur: 0.32, rise: 0.12 },
  /** ghost: there from the start at `floor`, lit at its landing over `dur`. */
  ghost: { floor: 0.2, dur: 0.14 },
  /** wipe: uncovered left to right over `dur` (outCubic) from its landing. */
  wipe: { dur: 0.32 },
} as const;

/**
 * A unit's state at song time `t` for a reveal landing at `at`. Rise and slam land at `at` (their motion starts just
 * before it, so the impact is on the beat or the spoken onset); the others start at `at`. Typewriter and scramble units
 * are fully there once landed (their glyph steps are typedCount and scrambleGlyph's, on the frame grid).
 */
export function revealState(style: Reveal, t: number, at: number): UnitState {
  switch (style) {
    case 'rise': {
      const R = REVEAL.rise;
      const k = slam(t, at, { freq: R.freq, damping: R.damping });
      if (k <= 0) return HIDDEN;
      const launch = at - riseTime(R.freq, R.damping);
      return { ...SHOWN, alpha: prog(t, launch, launch + R.fadeIn), dy: (1 - k) * R.drop };
    }
    case 'slam': {
      const R = REVEAL.slam;
      const k = slam(t, at, { freq: R.freq, damping: R.damping });
      if (k <= 0) return HIDDEN;
      const launch = at - riseTime(R.freq, R.damping);
      return { ...SHOWN, alpha: prog(t, launch, launch + R.fadeIn), scale: 1 + (R.from - 1) * (1 - k), blur: R.blur * clamp(1 - k) };
    }
    case 'blur': {
      const R = REVEAL.blur;
      const k = prog(t, at, at + R.dur, ease.outCubic);
      if (t < at) return HIDDEN;
      return { ...SHOWN, alpha: Math.pow(k, 0.6), blur: R.blur * (1 - k), scale: 1 + R.scale * (1 - k) };
    }
    case 'track': {
      const R = REVEAL.track;
      if (t < at) return HIDDEN;
      const k = prog(t, at, at + R.dur, ease.outExpo);
      return { ...SHOWN, alpha: prog(t, at, at + R.fadeIn, ease.outCubic), track: R.track * (1 - k), blur: 0.03 * (1 - k) };
    }
    case 'fade': {
      const R = REVEAL.fade;
      if (t < at) return HIDDEN;
      const k = prog(t, at, at + R.dur, ease.outCubic);
      return { ...SHOWN, alpha: k, dy: R.rise * (1 - k) };
    }
    case 'ghost': {
      const R = REVEAL.ghost;
      return { ...SHOWN, alpha: lerp(R.floor, 1, prog(t, at, at + R.dur, ease.outCubic)) };
    }
    case 'wipe': {
      if (t < at) return HIDDEN;
      return { ...SHOWN, clip: prog(t, at, at + REVEAL.wipe.dur, ease.outCubic) };
    }
    case 'typewriter':
    case 'scramble':
      return frameTime(t) >= at - 1e-9 ? SHOWN : HIDDEN;
  }
}

/** When an under-damped spring launched at 0 first reaches 1 (motion.ts slam's default lead). */
export function riseTime(freq: number, damping: number): number {
  const z = Math.max(0, damping);
  return z < 1 ? (Math.PI / 2 + Math.asin(z)) / (2 * Math.PI * freq * Math.sqrt(1 - z * z)) : 0;
}

/** How long before `at` a reveal's motion starts (rise and slam launch early so they land on it). */
export function revealLead(style: Reveal): number {
  if (style === 'rise') return riseTime(REVEAL.rise.freq, REVEAL.rise.damping);
  if (style === 'slam') return riseTime(REVEAL.slam.freq, REVEAL.slam.damping);
  if (style === 'scramble') return SCRAMBLE.churn;
  return 0;
}

/** How long after `at` a reveal is still moving (for scheduling what follows it). */
export function revealTail(style: Reveal): number {
  switch (style) {
    case 'rise': case 'slam': return 0.25;
    case 'blur': return REVEAL.blur.dur;
    case 'track': return REVEAL.track.dur;
    case 'fade': return REVEAL.fade.dur;
    case 'wipe': return REVEAL.wipe.dur;
    default: return 0.1;
  }
}

/** A frame's own time: t snapped to the frame grid, constant over its motion-blur shutter. */
export const frameTime = (t: number) => frameIdx(t) / FPS;

/** Glyphs of `n` typed from `at` at `cps` per second, counted on the frame grid (the first lands on `at`). */
export function typedCount(t: number, at: number, cps: number, n: number): number {
  return clamp(Math.floor((frameTime(t) - at) * cps + 1 + 1e-9), 0, n);
}

/** A typing caret's visibility: solid while typing (until `done`), then blinking `period` frames on and off. */
export function caretOn(t: number, done: number, period = 16): boolean {
  const f = frameIdx(t), d = frameIdx(done);
  return f <= d || Math.floor((f - d) / period) % 2 === 1;
}

/** Scramble: glyphs churn for `churn` s before the first settles; each next one settles `per` s later. */
export const SCRAMBLE = { churn: 0.28, per: 0.035, charset: 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#%&*+=<>/\\' } as const;

/**
 * The glyph a scrambled text shows at index `i` (of the final `ch`) at time t: nothing before it starts churning
 * (`at` − churn), a seeded random glyph from `charset` (a new one every frame, on the frame grid) until it settles at
 * `settle`, then its own. Whitespace never churns. Deterministic: (seed, i, frame).
 */
export function scrambleGlyph(ch: string, i: number, t: number, at: number, settle: number, seed = 1, charset: string = SCRAMBLE.charset): string {
  if (/\s/u.test(ch)) return ch;
  const tq = frameTime(t);
  if (tq < at - SCRAMBLE.churn - 1e-9) return '';
  if (tq >= settle - 1e-9) return ch;
  const cs = Array.from(charset);
  const k = Math.floor(hash(seed, i, frameIdx(t)) * cs.length);
  const r = cs[Math.min(cs.length - 1, k)]!;
  // keep the case of letters (a lowercase line churns in lowercase)
  return ch === ch.toLowerCase() && ch !== ch.toUpperCase() ? r.toLowerCase() : r;
}

/** A whole scrambled string: glyph i settles at `at` + i·per. */
export function scrambleText(text: string, t: number, at: number, o: { per?: number; seed?: number; charset?: string } = {}): string {
  const per = o.per ?? SCRAMBLE.per;
  return Array.from(text).map((ch, i) => scrambleGlyph(ch, i, t, at, at + i * per, o.seed ?? 1, o.charset)).join('');
}

/** A sweep's progress 0..1 (a highlighter, an underline, a strike) from `at` over `dur`, inOutCubic. */
export const sweep = (t: number, at: number, dur = 0.3) => prog(t, at, at + dur, ease.inOutCubic);

/** An emphasis word's glow: a flare as it lands (to 1), settling to `sustain`. 0 before it lands. */
export function emphasisGlow(t: number, at: number, sustain = 0.55, halfLife = 0.22): number {
  if (t < at) return 0;
  return sustain + (1 - sustain) * pulse(t, at, halfLife);
}

// ------------------------------------------------------------------------------------------------ exits

export type Exit = 'none' | 'fade' | 'rise' | 'blur' | 'sink';

/** A block's exit at t: over the last `dur` seconds before `end` (inCubic). Multiplies over a unit's reveal state. */
export function exitState(style: Exit, t: number, end: number, dur = 0.3): UnitState {
  if (style === 'none' || dur <= 0) return SHOWN;
  const k = prog(t, end - dur, end, ease.inCubic);
  if (k <= 0) return SHOWN;
  switch (style) {
    case 'fade': return { ...SHOWN, alpha: 1 - k };
    case 'rise': return { ...SHOWN, alpha: 1 - k, dy: -0.5 * k };
    case 'sink': return { ...SHOWN, alpha: 1 - k, dy: 0.5 * k };
    case 'blur': return { ...SHOWN, alpha: 1 - k, blur: 0.2 * k, scale: 1 + 0.04 * k };
  }
}

/** Two states composed: alphas, scales and clips multiply, offsets, blurs and tracking add. */
export function compose(a: UnitState, b: UnitState): UnitState {
  return { alpha: a.alpha * b.alpha, dx: a.dx + b.dx, dy: a.dy + b.dy, scale: a.scale * b.scale, blur: a.blur + b.blur, clip: Math.min(a.clip, b.clip), track: a.track + b.track };
}

// ------------------------------------------------------------------------------------------------ layout math

/**
 * Words broken into the fewest lines no wider than `maxW`, balanced: of the ways to break into that many lines, the one
 * whose widest line is narrowest (so two lines come out near-equal, not one full and a widow). `widthOf` measures a
 * run of words joined by single spaces. A single word wider than maxW gets a line of its own (the caller shrinks it).
 */
export function wrapBalanced(words: readonly string[], widthOf: (s: string) => number, maxW: number): string[] {
  const n = words.length;
  if (n === 0) return [];
  const whole = words.join(' ');
  if (widthOf(whole) <= maxW || n === 1) return [whole];
  const w = (i: number, j: number) => widthOf(words.slice(i, j).join(' ')); // words [i, j)
  // fewest lines: greedy
  let lines = 0;
  for (let i = 0; i < n; lines++) {
    let j = i + 1;
    while (j < n && w(i, j + 1) <= maxW) j++;
    i = j;
  }
  // best[k][i]: the narrowest widest line breaking words [i, n) into k lines (and where the first one ends)
  const memo = new Map<string, { cost: number; cut: number }>();
  const best = (k: number, i: number): { cost: number; cut: number } => {
    const key = `${k}:${i}`;
    const hit = memo.get(key);
    if (hit) return hit;
    let r = { cost: Infinity, cut: n };
    if (k === 1) r = { cost: w(i, n) <= maxW || n - i === 1 ? w(i, n) : Infinity, cut: n };
    else {
      for (let j = i + 1; j <= n - (k - 1); j++) {
        const first = w(i, j);
        if (first > maxW && j - i > 1) break;
        const rest = best(k - 1, j);
        const c = Math.max(first, rest.cost);
        if (c < r.cost) r = { cost: c, cut: j };
      }
    }
    memo.set(key, r);
    return r;
  };
  const out: string[] = [];
  for (let k = lines, i = 0; k >= 1 && i < n; k--) {
    const { cut } = best(k, i);
    out.push(words.slice(i, cut).join(' '));
    i = cut;
  }
  return out;
}

/** Scale (<= 1) that brings a run `width` wide inside `maxW`. */
export const fitScale = (width: number, maxW: number) => (width > maxW && width > 0 ? maxW / width : 1);

/** Text split into words, keeping each word's start and end index in the string (code points). */
export function wordsOf(text: string): { w: string; i0: number; i1: number }[] {
  const chars = Array.from(text);
  const out: { w: string; i0: number; i1: number }[] = [];
  let i = 0;
  while (i < chars.length) {
    while (i < chars.length && /\s/u.test(chars[i]!)) i++;
    if (i >= chars.length) break;
    const i0 = i;
    while (i < chars.length && !/\s/u.test(chars[i]!)) i++;
    out.push({ w: chars.slice(i0, i).join(''), i0, i1: i });
  }
  return out;
}

/** Whether a display word is one of `list` (folded as vo.ts norm folds: case and punctuation). */
export function isOneOf(word: string, list: readonly string[] | undefined): boolean {
  if (!list?.length) return false;
  const k = norm(word);
  return !!k && list.some((x) => norm(x) === k);
}

// ------------------------------------------------------------------------------------------------ diff

export type DiffOp = '=' | '-' | '+';

/** A word diff of `a` to `b` (longest common subsequence, folded as norm folds): kept, removed and added words in order. */
export function diffWords(a: string, b: string): { w: string; op: DiffOp }[] {
  const A = wordsOf(a).map((x) => x.w), B = wordsOf(b).map((x) => x.w);
  const m = A.length, n = B.length;
  const L = Array.from({ length: m + 1 }, () => new Int32Array(n + 1));
  for (let i = m - 1; i >= 0; i--) for (let j = n - 1; j >= 0; j--) L[i]![j] = norm(A[i]!) === norm(B[j]!) ? L[i + 1]![j + 1]! + 1 : Math.max(L[i + 1]![j]!, L[i]![j + 1]!);
  const out: { w: string; op: DiffOp }[] = [];
  let i = 0, j = 0;
  while (i < m || j < n) {
    if (i < m && j < n && norm(A[i]!) === norm(B[j]!)) { out.push({ w: B[j]!, op: '=' }); i++; j++; }
    else if (i < m && (j >= n || L[i + 1]![j]! >= L[i]![j + 1]!)) out.push({ w: A[i++]!, op: '-' });
    else out.push({ w: B[j++]!, op: '+' });
  }
  return out;
}

// ------------------------------------------------------------------------------------------------ captions

/** A caption chunk: a few consecutive words of one line, on screen over [start, end). */
export interface Chunk { words: Spoken[]; start: number; end: number; line: number }

/** Ends a phrase: a chunk may break after it early. */
const PHRASE_END = /[.!?;:,…—–]["”’)]*$/u;

/**
 * Caption chunks from spoken lines: each line's words in runs of at most `maxWords` (and `maxChars` characters),
 * breaking early after a phrase's end (a comma, a full stop) once a run has `minWords`; never across lines, and never a
 * lone word left at a line's end when the run before it can spare one. Each chunk shows from `lead` before its first
 * word until the next chunk starts, or `hold` after its last word ends if that comes first.
 */
export function captionChunks(lines: readonly { words: readonly Spoken[] }[], o: { maxWords?: number; maxChars?: number; minWords?: number; lead?: number; hold?: number } = {}): Chunk[] {
  const maxWords = Math.max(1, o.maxWords ?? 4), maxChars = o.maxChars ?? Infinity, minWords = o.minWords ?? 2;
  const lead = o.lead ?? 0.06, hold = o.hold ?? 0.7;
  const runs: { words: Spoken[]; line: number }[] = [];
  lines.forEach((l, li) => {
    const ws = l.words.filter((w) => w.w.trim());
    let cur: Spoken[] = [];
    const lineRuns: Spoken[][] = [];
    const chars = (r: Spoken[]) => r.reduce((s, w) => s + w.w.length, 0) + Math.max(0, r.length - 1);
    for (const w of ws) {
      if (cur.length && (cur.length >= maxWords || chars([...cur, w]) > maxChars)) { lineRuns.push(cur); cur = []; }
      cur.push(w);
      if (cur.length >= minWords && PHRASE_END.test(w.w)) { lineRuns.push(cur); cur = []; }
    }
    if (cur.length) lineRuns.push(cur);
    // a lone last word borrows one from the run before it
    const last = lineRuns[lineRuns.length - 1], prev = lineRuns[lineRuns.length - 2];
    if (last && prev && last.length === 1 && prev.length > minWords && !PHRASE_END.test(prev[prev.length - 1]!.w)) last.unshift(prev.pop()!);
    for (const r of lineRuns) runs.push({ words: r, line: li });
  });
  runs.sort((a, b) => a.words[0]!.start - b.words[0]!.start);
  return runs.map((r, i) => {
    const start = r.words[0]!.start - lead;
    const next = runs[i + 1] ? runs[i + 1]!.words[0]!.start - lead : Infinity;
    return { words: r.words, line: r.line, start, end: Math.min(next, r.words[r.words.length - 1]!.end + hold) };
  });
}

/** The chunk on screen at t (index), or -1. */
export function chunkAt(chunks: readonly Chunk[], t: number): number {
  for (let i = chunks.length - 1; i >= 0; i--) if (t >= chunks[i]!.start) return t < chunks[i]!.end ? i : -1;
  return -1;
}

/**
 * The word being spoken in a chunk at t: the latest word started, held through the gap to the next word but let go
 * `release` s after it ends (a pause goes quiet). -1 before the first or after the release.
 */
export function currentWord(words: readonly Spoken[], t: number, release = 0.5): number {
  let k = -1;
  for (let i = 0; i < words.length; i++) if (words[i]!.start <= t) k = i;
  if (k < 0) return -1;
  const w = words[k]!, next = words[k + 1];
  return t < Math.min(next?.start ?? Infinity, w.end + release) ? k : -1;
}

/** A spring from 0 to 1 launched at `at` (the house spring), for anything that pops in on an onset. */
export const popIn = (t: number, at: number, freq = 5, damping = 0.62) => spring(t - at, freq, damping);
