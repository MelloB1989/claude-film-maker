// Scene `diff`: its times against the film's own voiceover and beat grid (diff-time.ts timesOf), its two clocks (the
// file's rewinds with the playhead and is the song's elsewhere), the scrub's speed ramp, and its copy against the facts
// sheet (the file at both commits, the diff, the history).
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { BACK, FWD, bladeHeat, docTime, historyAt, ramped, romance, scrubbing, slash, struckAt, timesOf } from './diff-time';
import { HISTORY, ROW, fileLines } from './diff';
import { VO, norm } from '../engine/vo';
import { AudioData } from '../engine/audio';
import S from './diff.strings.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
const vo = new VO(json('vo.json'));
const audio = new AudioData(json('audio.json'));
const span = vo.scenes.find((s) => s.id === 'diff')!;
const T = timesOf(vo, audio, span.start, span.end);
const words = vo.lines.filter((l) => l.scene === 'diff').flatMap((l) => l.words);
const at = (w: string, nth = 0) => words.filter((x) => norm(x.w) === norm(w))[nth]!.start;
const onGrid = (t: number, grid: number[]) => grid.some((b) => Math.abs(b - t) < 1e-9);

describe('diff: its times come from the data', () => {
  test('the caret glides from "Change" and lands on the downbeat before "mind?", which selects the line', () => {
    expect(T.change).toBe(at('change'));
    expect(onGrid(T.land, audio.downbeats)).toBe(true);
    expect(T.land).toBeGreaterThan(at('change'));
    expect(T.land).toBeLessThan(at('mind'));
    expect(T.select).toBe(at('mind'));
    expect(onGrid(T.stir, audio.beats)).toBe(true);
    expect(T.stir).toBeLessThan(T.strike.at);
  });

  test('the blade launches on "I\'ll" and lands on "change"; the rows open on "mine."', () => {
    expect(T.strike.at).toBe(at("i'll"));
    expect(T.strike.end).toBe(at('change', 1));
    expect(T.conf.at).toBeGreaterThan(T.strike.end);
    expect(T.add).toBeCloseTo(at('mine') - 0.03, 9);
    expect(T.addEnd).toBeGreaterThan(T.add);
    expect(T.addEnd).toBeLessThan(T.dock);
  });

  test('the dock lands on the downbeat before "We\'ll"; the scrub lands on the beats, back and home', () => {
    expect(onGrid(T.dock, audio.downbeats)).toBe(true);
    expect(T.dock).toBeLessThan(at("we'll"));
    expect(T.back.at).toBeGreaterThan(at("we'll"));
    expect(onGrid(T.back.end, audio.beats)).toBe(true);
    expect(onGrid(T.fwd.end, audio.beats)).toBe(true);
    expect(T.back.end).toBeLessThan(T.fwd.at);
    expect(T.fwd.at).toBeLessThan(at('have'));
    expect(T.fwd.end).toBeGreaterThan(at('have'));
    for (const t of [T.land, T.strike.end, T.dock, T.back.end, T.fwd.end]) {
      expect(t).toBeGreaterThan(span.start);
      expect(t).toBeLessThan(span.end - 0.5);
    }
  });
});

describe('diff: the file has a clock of its own', () => {
  test('the slash launches from rest and cuts at full speed into the impact', () => {
    expect(slash(0)).toBe(0);
    expect(slash(1)).toBeCloseTo(1, 12);
    for (let u = 0; u < 1; u += 0.01) expect(slash(u + 0.01)).toBeGreaterThan(slash(u));
    const speed = (u: number) => (slash(u + 1e-4) - slash(u - 1e-4)) / 2e-4;
    expect(speed(0.01)).toBeLessThan(0.2);
    expect(speed(0.99)).toBeGreaterThan(1.1);
  });

  test('it is the song\'s before the scrub (the slash played on its curve), and keeps the strike in its window', () => {
    expect(docTime(T.start + 0.1, T)).toBe(T.start + 0.1);
    expect(docTime(T.dock, T)).toBe(T.dock);
    const mid = (T.strike.at + T.strike.end) / 2;
    expect(docTime(mid, T)).toBeGreaterThan(T.strike.at);
    expect(docTime(mid, T)).toBeLessThan(mid);
    expect(docTime(T.strike.end - 1e-9, T)).toBeCloseTo(T.strike.end, 6);
  });

  test('through the scrub it is the playhead\'s: HEAD, back to 8b21e04 (the old version, whole), then HEAD again', () => {
    expect(historyAt(T.back.at, T)).toBe(1);
    expect(historyAt(T.back.end, T)).toBeCloseTo(0, 9);
    expect(historyAt((T.back.end + T.fwd.at) / 2, T)).toBe(0);
    expect(historyAt(T.fwd.end, T)).toBe(1);
    expect(docTime((T.back.end + T.fwd.at) / 2, T)).toBe(T.old);
    expect(T.old).toBeLessThan(T.strike.at);
    expect(T.head).toBeGreaterThan(T.addEnd);
    // it runs back without turning, then forward without turning
    for (let t = T.back.at; t < T.back.end; t += 0.005) expect(historyAt(t + 0.005, T)).toBeLessThanOrEqual(historyAt(t, T) + 1e-12);
    for (let t = T.fwd.at; t < T.fwd.end; t += 0.005) expect(historyAt(t + 0.005, T)).toBeGreaterThanOrEqual(historyAt(t, T) - 1e-12);
    // and on from HEAD at the song's pace after
    expect(docTime(T.fwd.end + 0.3, T)).toBeCloseTo(T.head + 0.3, 9);
    expect(scrubbing((T.back.end + T.fwd.at) / 2, T)).toBe(true);
    expect(scrubbing(T.dock, T)).toBe(false);
  });

  test('the scrub\'s runs are speed ramps: from rest, fast inside, slowing into their landings', () => {
    const speed = (w: { at: number; end: number }, curve: [number, number][], u: number) => {
      const d = w.end - w.at;
      return (ramped(w.at + (u + 0.005) * d, w, curve) - ramped(w.at + (u - 0.005) * d, w, curve)) / 0.01;
    };
    for (const [w, curve] of [[T.back, BACK], [T.fwd, FWD]] as const) {
      expect(ramped(w.at, w, curve)).toBe(0);
      expect(ramped(w.end, w, curve)).toBeCloseTo(1, 12);
      expect(speed(w, curve, 0.005)).toBeLessThan(0.3);
      expect(speed(w, curve, 0.995)).toBeLessThan(0.3);
    }
    // back: the new line rewinds fast, then the old line comes back in slow motion (the last third of the history in
    // the last half of the run)
    expect(speed(T.back, BACK, 0.25)).toBeGreaterThan(3 * speed(T.back, BACK, 0.7));
    expect(1 - ramped((T.back.at + T.back.end) / 2, T.back, BACK)).toBeLessThan(0.36);
    // forward: an easy start (the blade cuts again), then the run home
    expect(speed(T.fwd, FWD, 0.7)).toBeGreaterThan(2 * speed(T.fwd, FWD, 0.25));
  });

  test('a cut is hot while it cuts, cools after, and is not there before; a rewind heats it again', () => {
    expect(bladeHeat(T.strike.at - 0.01, T.strike)).toBe(0);
    expect(bladeHeat((T.strike.at + T.strike.end) / 2, T.strike)).toBe(1);
    expect(bladeHeat(T.strike.end + 1, T.strike)).toBeLessThan(0.05);
    expect(struckAt(T.strike.end, T.strike, 13)).toBe(13);
    expect(struckAt(T.strike.at, T.strike, 13)).toBe(0);
    const back = (t: number) => bladeHeat(docTime(t, T), T.strike);
    expect(back(T.back.at + 0.25)).toBeGreaterThan(back(T.back.at + 0.02));
  });

  test('the romance comes up once the playhead is home', () => {
    expect(romance(T.back.end, T)).toBe(0);
    expect(romance(T.end, T)).toBeGreaterThan(0.95);
  });
});

describe('diff: the copy is the facts sheet\'s', () => {
  const facts = json('facts.json') as { verbatim: { text: string }[]; copy: { text: string }[] };
  const lines = fileLines(T);
  test('at 3f9a1c2 the file is spec §11.4 line for line (the struck rows gone)', () => {
    const now = lines.filter((l) => l.kind !== 'del').map((l) => l.text).join('\n');
    expect(facts.verbatim.map((e) => e.text)).toContain(now);
  });

  test('at 8b21e04 it is the same file with the two lines §11.5 takes out', () => {
    const was = lines.filter((l) => l.kind !== 'add');
    expect(was).toHaveLength(18);
    expect(was[3]!.text).toBe('confidence: 0.6');
    expect(was[12]!.text).toBe('Uses VS Code.');
    const diff = facts.verbatim.find((e) => e.text.includes('gitloom diff'))!.text;
    for (const [i, mark] of [[ROW.confOld, '-'], [ROW.confNew, '+'], [ROW.old, '-'], [ROW.neo, '+']] as const) expect(diff).toContain(`${mark} ${lines[i]!.text}`);
  });

  test('the dock\'s command and stat are §11.5\'s, the history is repo\'s log, oldest first', () => {
    expect(S).toContain('$ gitloom diff facts/people/user.md 8b21e04 3f9a1c2');
    expect(S).toContain('1 file changed, 2 insertions(+), 2 deletions(-)');
    expect(HISTORY.map((c) => c.hash)).toEqual(['105ca74', 'a41c9d0', '8b21e04', '3f9a1c2']);
    expect(HISTORY.filter((c) => c.msg).map((c) => `${c.hash} ${c.msg}`)).toEqual(['8b21e04 remember: uses VS Code', '3f9a1c2 remember: uses neovim']);
    for (const c of HISTORY.filter((c) => c.msg)) expect(facts.copy.map((e) => e.text)).toContain(`${c.hash} ${c.msg}`);
  });
});
