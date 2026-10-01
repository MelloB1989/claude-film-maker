// The clocks of scene 06 `diff` (Plan 2 Task 16): every moment the scene keys on, from her measured onsets and the
// score's grid, and the file's own time, which the history scrubber runs back and forth.
//
// Two clocks. The song's (t) drives the camera, the light and the scrubber. The file's (doc time, docTime) drives the
// editor Panel and what is drawn on it (the strike, the added rows): it is the song's until the scrub, where it is the
// playhead's place in the file's history played back, so the editor rewinds to 8b21e04 as the playhead runs back to
// it, holds there (the old version intact), and plays forward to 3f9a1c2 again. Everything here is a pure function of
// its inputs.
import type { AudioData } from '../engine/audio';
import { speedRamp, wordTimes } from '../engine/motion';
import { clamp, prog } from '../engine/util';
import { norm, type VO, type Word } from '../engine/vo';

/** A window of song time (s). */
export interface Span {
  at: number;
  end: number;
}

/** Every time the scene keys on (song seconds), from her onsets and the score's beats and downbeats. */
export function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'diff').map((x) => x.w);
  const word = (w: string, nth = 0): Word => {
    const h = ws.filter((x) => norm(x.w) === w)[nth];
    if (!h) throw new Error(`diff: no spoken "${w}" (#${nth})`);
    return h;
  };
  const beat = 60 / audio.bpm;
  const change = word('change'), your = word('your'), mind = word('mind');
  const ill = word('ill'), change2 = word('change', 1), mine = word('mine');
  const well = word('well'), always = word('always'), have = word('have'), diff = word('diff');
  const after = (t: number) => {
    const b = audio.beats.find((x) => x > t + 1e-6);
    if (b === undefined) throw new Error(`diff: no beat after ${t}`);
    return b;
  };
  // L15: the caret glides down the file from "Change" and lands on `Uses VS Code.` on the downbeat she reaches "your
  // mind" on; the selection runs across the line on "mind?", and it stirs on the next beat
  const land = audio.downbeats.find((d) => d > change.start + 0.2 && d < mind.start + 0.05) ?? your.start;
  const stir = audio.beats.find((b) => b > mind.start + 0.2 && b < ill.start - 0.3) ?? (mind.end + ill.start) / 2;
  // L16: the blade launches on "I'll" and cuts through the line into the impact on "change"; the frontmatter's
  // confidence takes a quick second cut just after; on "mine." both new rows open, `confidence: 0.9` whole and
  // `Uses neovim. Has since 2019.` typing in with her
  const strike: Span = { at: ill.start, end: change2.start };
  const conf: Span = { at: change2.start + 0.05, end: change2.start + 0.17 };
  const add = mine.start - 0.03, addEnd = mine.end + 0.08;
  // the history dock rises under the editor and lands on the downbeat before "We'll" (`gitloom diff` and its stat)
  const dock = audio.downbeats.find((d) => d > mine.start && d < well.start) ?? well.start - 0.15;
  // L17: the playhead runs back from 3f9a1c2 to 8b21e04 after "We'll", landing on the beat; holds there through
  // "always", the old version whole; runs forward again into the beat on "have"; then the romance, to the cut
  const back: Span = { at: well.start + 0.07, end: after(well.start + 0.2) };
  const fwd: Span = { at: always.end - 0.12, end: after(have.start - 0.1) };
  if (!(back.end < fwd.at && fwd.end < end - 0.3)) throw new Error('diff: the scrub does not fit between "We\'ll" and the cut');
  return {
    start, end, beat,
    change: change.start, land, select: mind.start, stir,
    strike, conf, add, addEnd,
    dock, well: well.start, back, fwd, diff: diff.start,
    /** Doc times of the two versions the scrubber spans: 8b21e04 (before the strike) and 3f9a1c2 (the rows added). */
    old: strike.at - 0.04,
    head: addEnd + 0.02,
  };
}
export type Times = ReturnType<typeof timesOf>;

/**
 * The slash: the blade's progress through its window (0..1 of the line), a launch that reaches full speed a quarter
 * of the way in, then the cut at full speed into the impact (the panel's strike is linear in doc time, so the slash is
 * played as a warp of doc time; the blade reads it from there too).
 */
export function slash(u: number): number {
  const a = 0.25, v = 1 / (1 - a / 2);
  u = clamp(u);
  return u < a ? (v / (2 * a)) * u * u : v * (a / 2 + (u - a));
}

/**
 * Speed curves of the scrub's two runs, [fraction of the window, speed]. Back: a quick launch and a fast run that
 * rewinds the new line, then a long slow-down as the cut draws out of the old one (the old version returns in slow
 * motion, five frames for the last third of the history). Forward: an easy start that lets the blade cut again, then the
 * run home, braking into HEAD.
 */
export const BACK: [number, number][] = [[0, 0], [0.1, 2.2], [0.36, 2.2], [0.5, 0.6], [0.82, 0.45], [1, 0]];
export const FWD: [number, number][] = [[0, 0], [0.12, 0.55], [0.4, 0.75], [0.55, 1.9], [0.85, 1.9], [1, 0]];

/** Progress 0..1 across a window, the speed following `curve` (motion.ts speedRamp: eased between its keys). */
export function ramped(t: number, w: Span, curve: [number, number][]): number {
  const d = w.end - w.at, ks = curve.map(([u, s]): [number, number] => [u * d, s]);
  return clamp(speedRamp(clamp(t - w.at, 0, d), ks) / speedRamp(d, ks));
}

/** The playhead's place in the history at t: 1 at 3f9a1c2 (HEAD), 0 at 8b21e04, as the scrub runs back and forth. */
export function historyAt(t: number, T: Pick<Times, 'back' | 'fwd'>): number {
  if (t <= T.back.at || t >= T.fwd.end) return 1;
  if (t < T.back.end) return 1 - ramped(t, T.back, BACK);
  if (t <= T.fwd.at) return 0;
  return ramped(t, T.fwd, FWD);
}

/** Whether the scrub is under way at t (the file's clock is the playhead's). */
export const scrubbing = (t: number, T: Pick<Times, 'back' | 'fwd'>) => t > T.back.at && t < T.fwd.end;

/**
 * The file's clock at song time t: the song's, with the slash played on its curve; the playhead's place in the history
 * through the scrub; then on from 3f9a1c2 at the song's pace.
 */
export function docTime(t: number, T: Pick<Times, 'strike' | 'back' | 'fwd' | 'old' | 'head'>): number {
  if (t <= T.back.at) {
    const s = T.strike;
    return t > s.at && t < s.end ? s.at + (s.end - s.at) * slash((t - s.at) / (s.end - s.at)) : t;
  }
  if (t < T.fwd.end) return T.old + historyAt(t, T) * (T.head - T.old);
  return T.head + (t - T.fwd.end);
}

/** How far a strike over `s` (doc time) has cut through n characters at doc time d (fractional, as Panel strikes). */
export const struckAt = (d: number, s: Span, n: number) => clamp((d - s.at) / (s.end - s.at)) * n;

/**
 * The heat of a strike's blade at doc time d (0..1): white-hot while it cuts, cooling over `cool` seconds after the
 * impact; none before it. Read from the file's clock, so a rewind heats it again as the playhead runs back to it.
 */
export function bladeHeat(d: number, s: Span, cool = 0.32): number {
  if (d < s.at) return 0;
  if (d <= s.end) return 1;
  return Math.exp(-(d - s.end) / cool);
}

/** The romance: 0 until the playhead is home again, rising to 1 over the rest of the scene. */
export const romance = (t: number, T: Pick<Times, 'fwd' | 'end'>) => prog(t, T.fwd.end - 0.1, T.end - 0.05);
