// Scene `cite`: its times against the film's own voiceover and beat grid (cite-time.ts timesOf), the thread's run along
// its route (where its drawn tip is, the slack drawn in), the route (on the label's face, through the air, lying on the
// file's face beside the cited lines, never into a panel), and the copy against the facts sheet (the file line for line,
// the citation's line range on the shown file's own lines, the blame).
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { hermite, layEnd, tautAt, timesOf, tipAt, tipPasses, type Run } from './cite-time';
import { ArcPath, LAND, seamRoute } from './cite-path';
import { CITED, CITE_RUNS, FACES, FILE_TEXT, THREAD_PX, seamSpec } from './cite';
import { VO, norm } from '../engine/vo';
import { AudioData } from '../engine/audio';
import S from './cite.strings.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
const vo = new VO(json('vo.json'));
const audio = new AudioData(json('audio.json'));
const span = vo.scenes.find((s) => s.id === 'cite')!;
const T = timesOf(vo, audio, span.start, span.end);
const words = vo.lines.filter((l) => l.scene === 'cite').flatMap((l) => l.words);
const at = (w: string, nth = 0) => words.filter((x) => norm(x.w) === norm(w))[nth]!.start;
const onGrid = (t: number, grid: number[]) => grid.some((b) => Math.abs(b - t) < 1e-9);

describe('cite: its times come from the data', () => {
  test('the question is typing across the cut and sent before the downbeat she says "Ask" on, where the answer streams', () => {
    expect(T.question.at).toBeLessThan(span.start);
    expect(T.question.end).toBeGreaterThan(span.start);
    expect(onGrid(T.answer, audio.downbeats)).toBe(true);
    expect(Math.abs(T.answer - at('ask'))).toBeLessThan(0.05);
    expect(T.question.end).toBeLessThan(T.answer);
    expect(T.answerEnd).toBeLessThan(at('why'));
  });

  test('the chip is clicked on "why" and let go on the beat after, where the citation streams in, done by "believe"\'s end', () => {
    expect(T.chip).toBeGreaterThan(T.answerEnd);
    expect(T.chip).toBeLessThan(T.click);
    expect(T.click).toBe(at('why'));
    expect(onGrid(T.release, audio.beats)).toBe(true);
    expect(T.release).toBeGreaterThan(T.click);
    expect(T.cite.at).toBeGreaterThan(T.release);
    expect(T.cite.end).toBeLessThan(at('something'));
  });

  test('the file jumps to its lines on a beat; the thread is drawn out of the label, its tip arriving on the beat in the pause', () => {
    expect(onGrid(T.scroll, audio.beats)).toBe(true);
    expect(T.scroll).toBeGreaterThan(T.release);
    expect(T.draw.at).toBeLessThan(T.cite.end);
    expect(onGrid(T.draw.end, audio.beats)).toBe(true);
    expect(T.draw.end).toBeGreaterThan(at('something'));
    expect(T.draw.end).toBeLessThan(at("i'll"));
  });

  test('the approach runs through the pause, done with "I\'ll"; it lands on the downbeat; the light lands on "line."', () => {
    expect(T.form.at).toBeGreaterThan(T.draw.end);
    expect(T.form.end).toBeGreaterThan(at("i'll"));
    expect(T.form.end).toBeLessThan(T.strike);
    expect(onGrid(T.strike, audio.downbeats)).toBe(true);
    expect(Math.abs(T.strike - at("i'll"))).toBeLessThan(0.1);
    expect(T.exit - T.strike).toBeCloseTo(T.beat / 2, 9);
    expect(onGrid(T.pull, audio.beats)).toBe(true);
    expect(Math.abs(T.pull - at('line'))).toBeLessThan(0.05);
    expect(T.pull).toBeLessThan(span.end - 0.5);
  });
});

describe('cite: the thread runs along its route', () => {
  const run: Run = { land: 400, end: 600 };
  const speed = (t: number) => (tipAt(t + 0.002, T, run) - tipAt(t - 0.002, T, run)) / 0.004;

  test('it is drawn out of the underline from nothing and never stops until the seam is laid', () => {
    expect(tipAt(T.draw.at - 0.01, T, run)).toBe(0);
    for (let t = T.draw.at + 0.004; t + 0.004 < layEnd(T); t += 0.004) expect(tipAt(t + 0.004, T, run)).toBeGreaterThan(tipAt(t, T, run));
    expect(tipAt(layEnd(T), T, run)).toBe(run.end);
    expect(tipAt(T.end, T, run)).toBe(run.end);
  });

  test('it lands on the file on the downbeat at the speed it lays the seam, which is laid before the light lands', () => {
    expect(tipAt(T.strike, T, run)).toBeCloseTo(run.land, 9);
    expect(Math.abs(speed(T.strike) / speed(T.strike - 0.004) - 1)).toBeLessThan(0.05);
    expect(layEnd(T)).toBeLessThan(T.pull);
    expect(layEnd(T)).toBeGreaterThan(T.exit);
  });

  test('the air draws in as the light lands on "line." and rings past it, settling', () => {
    expect(tautAt(T.exit, T)).toBe(0);
    expect(tautAt(T.pull, T)).toBeCloseTo(1, 9);
    expect(tautAt(T.pull + 0.02, T)).toBeGreaterThan(1);
    expect(Math.abs(tautAt(T.pull + 0.5, T) - 1)).toBeLessThan(0.01);
  });

  test('the lines light in order as the tip passes them', () => {
    const ts = [420, 460, 500, 540, 580].map((s) => tipPasses(s, T, run));
    for (let i = 1; i < ts.length; i++) expect(ts[i]!).toBeGreaterThan(ts[i - 1]!);
    expect(ts[0]!).toBeGreaterThan(T.strike);
    expect(ts[ts.length - 1]!).toBeLessThan(layEnd(T));
  });

  test('a Hermite segment holds its ends and speeds', () => {
    expect(hermite(0, 0, 3, 7, 1, 9, -2)).toBe(3);
    expect(hermite(1, 0, 3, 7, 1, 9, -2)).toBeCloseTo(9, 12);
    expect((hermite(1e-6, 0, 3, 7, 1, 9, -2) - 3) / 1e-6).toBeCloseTo(7, 4);
  });
});

describe('cite: the thread\'s route never goes into a panel', () => {
  const spec = seamSpec();
  const inside = (p: { x: number; y: number }, f: { x0: number; y0: number; x1: number; y1: number }) => p.x > f.x0 && p.x < f.x1 && p.y > f.y0 && p.y < f.y1;

  test('it starts under `L11–14` on the label\'s face and lands on the file at the top of line 11, past the lines\' ends', () => {
    const r = seamRoute(spec);
    expect(r[0]![2]).toBeCloseTo(FACES.label.z + spec.lift, 9);
    expect(r[LAND]![1]).toBeGreaterThan(spec.top);
    expect(r[LAND]![1]).toBeLessThan(spec.top + 20);
    expect(r[LAND]![2]).toBeCloseTo(spec.lift, 9);
    for (const p of r.slice(LAND)) expect(p[2]).toBe(spec.lift);
    expect(r[r.length - 1]![1]).toBeLessThan(spec.foot);
  });

  for (const [name, taut] of [['slack', 0], ['drawn in', 1], ['ringing', 1.12]] as const) {
    test(`${name}: over a panel's face it is always at least its radius in front of it`, () => {
      const path = new ArcPath(seamRoute(spec, taut, [6, 4, 5]));
      for (let s = 0; s <= path.length; s += 0.5) {
        const p = path.at(s).pos;
        if (inside(p, FACES.label)) expect(p.z - FACES.label.z).toBeGreaterThan(THREAD_PX);
        if (inside(p, FACES.file)) expect(p.z - FACES.file.z).toBeGreaterThan(THREAD_PX);
        expect(p.z).toBeGreaterThan(THREAD_PX); // nothing behind the file either
      }
    });
  }

  test('a measured route passes through its points, and runs on past its ends along them', () => {
    const r = seamRoute(spec), path = new ArcPath(r);
    for (const i of [0, LAND, r.length - 1]) {
      const p = path.at(path.atPoint(i)).pos, q = r[i]!;
      expect(Math.hypot(p.x - q[0], p.y - q[1], p.z - q[2])).toBeLessThan(0.05);
    }
    const end = path.at(path.length).pos, past = path.at(path.length + 10);
    expect(past.pos.distanceTo(end)).toBeCloseTo(10, 6);
  });
});

describe('cite: the copy is the facts sheet\'s', () => {
  const facts = json('facts.json') as { verbatim: { text: string }[]; copy: { text: string }[] };
  const copy = facts.copy.map((e) => e.text);
  test('the file is spec §11.4 line for line', () => {
    expect(FILE_TEXT).toHaveLength(18);
    expect(facts.verbatim.map((e) => e.text)).toContain(FILE_TEXT.join('\n'));
  });

  test('the citation is §4\'s, and its lines are the shown file\'s own: `## Editor` is line 11, lines 11–14 its section', () => {
    const cite = (S as string[]).find((s) => s.startsWith('facts/people/user.md#'))!;
    expect(copy).toContain(cite);
    expect(Array.from(cite).slice(...CITE_RUNS.range).join('')).toBe('L11–14');
    expect(Array.from(cite).slice(...CITE_RUNS.section).join('')).toBe('#editor');
    expect(Array.from(cite).slice(...CITE_RUNS.hash).join('')).toBe('3f9a1c2');
    expect(CITED.map((i) => i + 1)).toEqual([11, 12, 13, 14]);
    expect(FILE_TEXT[CITED[0]]).toBe('## Editor');
    expect(FILE_TEXT[CITED[2]]).toBe('Uses neovim. Has since 2019.');
    expect(FILE_TEXT[CITED[3] + 1]).toBe('## Timezone');
  });

  test('the chat and the blame are §4\'s', () => {
    for (const s of ['what editor do I use?', 'neovim.', '3f9a1c2 · 2026-07-26']) {
      expect(S).toContain(s);
      expect(copy).toContain(s);
    }
    expect(S).toContain('why?');
  });
});
