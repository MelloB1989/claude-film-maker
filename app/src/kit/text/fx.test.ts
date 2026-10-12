import { expect, test } from 'bun:test';
import { AudioData } from '../../engine/audio';
import { FPS } from '../../engine/util';
import {
  REVEALS, alignToVO, captionChunks, caretOn, chunkAt, compose, currentWord, diffWords, emphasisGlow, exitState, fitScale,
  glyphTimes, isOneOf, resolveTime, revealLead, revealState, scrambleGlyph, scrambleText, staggerTimes, sweep, typedCount,
  wordsOf, wrapBalanced,
} from './fx';

const grid = AudioData.grid({ duration: 60, bpm: 120 }); // a beat every 0.5 s, a bar every 2 s
const close = (a: number, b: number, eps = 1e-6) => expect(Math.abs(a - b)).toBeLessThan(eps);

// ---- time ----

test('resolveTime: seconds after the shot start, or beats and bars counted from the first one at or after it', () => {
  expect(resolveTime(0.4, 10)).toBe(10.4);
  expect(resolveTime({ s: 1 }, 10)).toBe(11);
  close(resolveTime({ beat: 0 }, 10.1, grid), 10.5); // the first beat at or after 10.1
  close(resolveTime({ beat: 2 }, 10.1, grid), 11.5);
  close(resolveTime({ beat: 0 }, 10, grid), 10); // a start on a beat is that beat
  close(resolveTime({ beat: 0.5 }, 10, grid), 10.25); // the "and"
  close(resolveTime({ bar: 1 }, 10.1, grid), 14); // bars at 12, 14
  expect(() => resolveTime({ beat: 1 }, 0)).toThrow('beat grid');
});

test('staggerTimes: seconds apart, or on the beat grid', () => {
  expect(staggerTimes(3, 1, { stagger: 0.1 }).map((x) => +x.toFixed(6))).toEqual([1, 1.1, 1.2]);
  const b = staggerTimes(4, 2, { every: 1, grid });
  expect(b.map((x) => +x.toFixed(6))).toEqual([2, 2.5, 3, 3.5]);
  const half = staggerTimes(3, 2.25, { every: 0.5, grid });
  expect(half.map((x) => +x.toFixed(6))).toEqual([2.25, 2.5, 2.75]);
});

// ---- the voiceover ----

const spoken = [
  { w: 'Memory', start: 1.0, end: 1.4 },
  { w: 'that', start: 1.45, end: 1.6 },
  { w: 'um,', start: 1.62, end: 1.7 },
  { w: 'never', start: 1.8, end: 2.1 },
  { w: 'forgets.', start: 2.2, end: 2.8 },
];

test('alignToVO: display words land on their spoken onsets, folding case and punctuation, skipping fillers', () => {
  const s = alignToVO(['MEMORY', 'that', 'never', 'forgets'], spoken);
  expect(s.map((x) => x.start)).toEqual([1.0, 1.45, 1.8, 2.2]);
  expect(s.every((x) => x.matched)).toBe(true);
});

test('alignToVO: a word the voice never says sits between its neighbours, never ahead of the one before it', () => {
  const s = alignToVO(['Memory', 'that', 'truly', 'never', 'forgets'], spoken);
  expect(s[2]!.matched).toBe(false);
  expect(s[2]!.start).toBeGreaterThanOrEqual(s[1]!.start);
  expect(s[2]!.start).toBeLessThanOrEqual(s[3]!.start);
  // after the last match: gap apart, after it
  const t = alignToVO(['Memory', 'forever'], spoken.slice(0, 1), { gap: 0.2 });
  close(t[1]!.start, 1.2);
  // nothing spoken: the fallback, gap apart
  const u = alignToVO(['a', 'b'], [], { fallback: 5, gap: 0.1 });
  expect(u.map((x) => x.start)).toEqual([5, 5.1]);
});

test('glyphTimes: a word lands glyph by glyph over the time it is spoken, the first on its onset', () => {
  const g = glyphTimes({ start: 2, end: 2.4 }, 4);
  expect(g.map((x) => +x.toFixed(6))).toEqual([2, 2.1, 2.2, 2.3]);
  expect(Math.min(...g)).toBe(2);
});

// ---- reveals ----

test('revealState: nothing before a unit starts, all of it well after it lands, for every reveal', () => {
  for (const r of REVEALS) {
    const before = revealState(r, 5 - 0.5, 5);
    if (r === 'ghost') expect(before.alpha).toBeGreaterThan(0);
    else expect(before.alpha).toBe(0);
    const after = revealState(r, 5 + 2, 5);
    expect(after.alpha).toBeCloseTo(1, 4);
    expect(Math.abs(after.dy)).toBeLessThan(1e-3);
    expect(after.scale).toBeCloseTo(1, 3);
    expect(after.blur).toBeLessThan(1e-3);
    expect(after.track).toBeLessThan(1e-3);
    expect(after.clip).toBeCloseTo(1, 4);
  }
});

test('rise and slam land on their time: in place exactly at `at`, already moving just before', () => {
  for (const r of ['rise', 'slam'] as const) {
    const at = revealState(r, 3, 3);
    expect(Math.abs(at.dy)).toBeLessThan(1e-6);
    expect(Math.abs(at.scale - 1)).toBeLessThan(1e-6);
    expect(revealState(r, 3 - revealLead(r) / 2, 3).alpha).toBeGreaterThan(0);
    expect(revealState(r, 3 - revealLead(r) - 0.01, 3).alpha).toBe(0);
  }
  // the lead is short: the house springs reach their mark in under 140 ms
  expect(revealLead('slam')).toBeLessThan(0.1);
  expect(revealLead('rise')).toBeLessThan(0.14);
});

test('the house springs stay tight: slam undershoots its scale by under 12%, rise overshoots by under 5% of its drop', () => {
  let minScale = Infinity, minDy = Infinity;
  for (let t = 0; t < 1; t += 1e-3) {
    minScale = Math.min(minScale, revealState('slam', t, 0.2).scale);
    minDy = Math.min(minDy, revealState('rise', t, 0.2).dy);
  }
  expect(1 - minScale).toBeLessThan(0.12 * 0.9);
  expect(-minDy).toBeLessThan(0.05);
});

test('typewriter: glyphs land on the frame grid, the first on its time, one state per frame', () => {
  expect(typedCount(1 - 0.5 / FPS, 1, 30, 10)).toBe(1); // the frame at 1 shows the first glyph over its whole shutter
  expect(typedCount(1 - 0.6 / FPS, 1, 30, 10)).toBe(0);
  expect(typedCount(1, 1, 30, 10)).toBe(1);
  expect(typedCount(1 + 3 / FPS, 1, 30, 10)).toBe(4);
  expect(typedCount(1 + 3 / FPS + 0.4 / FPS, 1, 30, 10)).toBe(4); // a sub-frame agrees with its frame
  expect(typedCount(9, 1, 30, 10)).toBe(10);
  expect(caretOn(1, 2)).toBe(true);
});

test('scramble: deterministic, seeded, settles left to right, spaces stay, case follows', () => {
  const a = scrambleText('HELLO WORLD', 1.05, 1.1, { seed: 7 });
  const b = scrambleText('HELLO WORLD', 1.05, 1.1, { seed: 7 });
  expect(a).toBe(b);
  expect(Array.from(a)[5]).toBe(' ');
  expect(scrambleText('HELLO WORLD', 1.05, 1.1, { seed: 8 })).not.toBe(a);
  // before churning: nothing; long after: the text
  expect(scrambleText('HELLO', 0.5, 1.1)).toBe('');
  expect(scrambleText('HELLO', 3, 1.1)).toBe('HELLO');
  // half way through settling: a settled prefix
  const mid = Array.from(scrambleText('ABCDEFGHIJ', 1.1 + 4 * 0.035 + 0.001, 1.1));
  expect(mid.slice(0, 4).join('')).toBe('ABCD');
  // lowercase churns in lowercase
  const low = scrambleGlyph('a', 0, 1, 1.1, 1.2);
  expect(low).toBe(low.toLowerCase());
  // one frame shows one glyph across its shutter
  const f = Math.round(1.0 * FPS) / FPS;
  expect(scrambleGlyph('A', 3, f - 0.3 / FPS, 1.1, 1.5)).toBe(scrambleGlyph('A', 3, f + 0.3 / FPS, 1.1, 1.5));
});

test('sweep, emphasisGlow, exitState and compose', () => {
  expect(sweep(0, 1)).toBe(0);
  expect(sweep(2, 1)).toBe(1);
  expect(emphasisGlow(0.9, 1)).toBe(0);
  expect(emphasisGlow(1, 1)).toBe(1);
  expect(emphasisGlow(5, 1)).toBeCloseTo(0.55, 3);
  expect(exitState('none', 9.9, 10).alpha).toBe(1);
  expect(exitState('fade', 9, 10, 0.3).alpha).toBe(1);
  expect(exitState('fade', 10, 10, 0.3).alpha).toBe(0);
  expect(exitState('rise', 10, 10, 0.3).dy).toBeLessThan(0);
  const c = compose({ alpha: 0.5, dx: 1, dy: 1, scale: 2, blur: 1, clip: 0.5, track: 0 }, { alpha: 0.5, dx: 1, dy: 0, scale: 2, blur: 0, clip: 1, track: 0.1 });
  expect(c).toEqual({ alpha: 0.25, dx: 2, dy: 1, scale: 4, blur: 1, clip: 0.5, track: 0.1 });
});

// ---- layout math ----

const mono = (s: string) => s.length * 10; // a mono face: 10 px a character

test('wrapBalanced: the fewest lines that fit, balanced, never wider than the measure', () => {
  expect(wrapBalanced(['one', 'two'], mono, 100)).toEqual(['one two']);
  // 'aaaa bbbb cccc dddd' is 190 wide: two lines of 90, not 140 + 40
  expect(wrapBalanced(['aaaa', 'bbbb', 'cccc', 'dddd'], mono, 150)).toEqual(['aaaa bbbb', 'cccc dddd']);
  const lines = wrapBalanced('the quick brown fox jumps over the lazy dog'.split(' '), mono, 160);
  expect(lines.length).toBe(3);
  for (const l of lines) expect(mono(l)).toBeLessThanOrEqual(160);
  expect(lines.join(' ')).toBe('the quick brown fox jumps over the lazy dog');
  // a word wider than the measure gets a line of its own
  expect(wrapBalanced(['a', 'supercalifragilistic', 'b'], mono, 100)).toEqual(['a', 'supercalifragilistic', 'b']);
  expect(wrapBalanced([], mono, 100)).toEqual([]);
});

test('fitScale, wordsOf, isOneOf', () => {
  expect(fitScale(50, 100)).toBe(1);
  expect(fitScale(200, 100)).toBe(0.5);
  expect(wordsOf('  Ship  it, now ')).toEqual([{ w: 'Ship', i0: 2, i1: 6 }, { w: 'it,', i0: 8, i1: 11 }, { w: 'now', i0: 12, i1: 15 }]);
  expect(isOneOf('Never,', ['never'])).toBe(true);
  expect(isOneOf('it’s', ["it's"])).toBe(true);
  expect(isOneOf('forgets', ['never'])).toBe(false);
});

test('diffWords: kept, removed and added words in order', () => {
  expect(diffWords('Uses VS Code', 'Uses neovim')).toEqual([
    { w: 'Uses', op: '=' }, { w: 'VS', op: '-' }, { w: 'Code', op: '-' }, { w: 'neovim', op: '+' },
  ]);
  expect(diffWords('a b c', 'a b c').every((x) => x.op === '=')).toBe(true);
  expect(diffWords('', 'new').map((x) => x.op)).toEqual(['+']);
});

// ---- captions ----

const words = (s: string, t0 = 0, step = 0.3) => s.split(' ').map((w, i) => ({ w, start: t0 + i * step, end: t0 + i * step + 0.25 }));

test('captionChunks: runs of at most maxWords, breaking early at a phrase end, never across lines', () => {
  const lines = [{ words: words('Ship your story, in ninety seconds flat today') }, { words: words('On the beat.', 5) }];
  const ch = captionChunks(lines, { maxWords: 3 });
  expect(ch.map((c) => c.words.map((w) => w.w).join(' '))).toEqual(['Ship your story,', 'in ninety seconds', 'flat today', 'On the beat.']);
  expect(ch.map((c) => c.line)).toEqual([0, 0, 0, 1]);
  // each shows until the next starts, or `hold` after its last word
  close(ch[0]!.end, ch[1]!.start);
  close(ch[2]!.end, lines[0]!.words[7]!.end + 0.7);
});

test('captionChunks: a lone last word borrows one from the run before it', () => {
  const ch = captionChunks([{ words: words('one two three four five') }], { maxWords: 4 });
  expect(ch.map((c) => c.words.length)).toEqual([3, 2]);
});

test('chunkAt and currentWord', () => {
  const ch = captionChunks([{ words: words('a b c d e f', 1) }], { maxWords: 3, lead: 0.05, hold: 0.5 });
  expect(chunkAt(ch, 0.5)).toBe(-1);
  expect(chunkAt(ch, 0.96)).toBe(0);
  expect(chunkAt(ch, 1.9)).toBe(1);
  expect(chunkAt(ch, 9)).toBe(-1);
  const ws = words('a b c', 1);
  expect(currentWord(ws, 0.9)).toBe(-1);
  expect(currentWord(ws, 1.0)).toBe(0);
  expect(currentWord(ws, 1.28)).toBe(0); // in the gap before b: held
  expect(currentWord(ws, 1.65)).toBe(2);
  expect(currentWord(ws, 3)).toBe(-1); // released after the pause
});
