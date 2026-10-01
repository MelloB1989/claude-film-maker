// Scene `cite`: its times against the film's own voiceover and beat grid (cite-time.ts timesOf), the needle's run along
// its thread (where its tip is, the thread's end, the slack taken up), the thread's route (in front of the file's face in
// the air, behind it under the cited lines, out again under line 14), the needle's shape, and the copy against the facts
// sheet (the file line for line, the citation's line range on the shown file's own lines, the blame).
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { EYE_TO_TIP, NEEDLE, POISE, eyeAt, formAt, hermite, tautAt, threadEnd, timesOf, tipAt, tipPasses, type Run } from './cite-time';
import { ArcPath, airRoute, stitchRoute, type P3 } from './cite-path';
import { SHAPE, needleProfile } from './cite-needle';
import { CITED, CITE_RUNS, FILE_TEXT } from './cite';
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

  test('the needle forms out of the pause, done with "I\'ll"; strikes on the downbeat; out an eighth later; the pull lands on "line."', () => {
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

describe('cite: the needle runs along its thread', () => {
  const run: Run = { a: 300, b: 500, end: 600 };
  test('the thread is drawn out of the label from nothing, the tip hanging over the entry through the pause', () => {
    expect(tipAt(T.draw.at - 0.01, T, run)).toBe(0);
    expect(tipAt(T.draw.end, T, run)).toBeCloseTo(run.a - POISE, 9);
    expect(tipAt((T.draw.end + T.form.at) / 2, T, run)).toBe(run.a - POISE);
    for (let t = T.draw.at; t < T.draw.end; t += 0.01) expect(tipAt(t + 0.01, T, run)).toBeGreaterThanOrEqual(tipAt(t, T, run));
  });

  test('it strikes into the entry on the downbeat, runs under the lines slower than it struck, and is out of the exit on the eighth', () => {
    expect(tipAt(T.strike, T, run)).toBeCloseTo(run.a, 9);
    expect(tipAt(T.exit, T, run)).toBeCloseTo(run.b, 9);
    for (let t = T.form.end; t + 0.004 <= T.pull; t += 0.004) expect(tipAt(t + 0.004, T, run)).toBeGreaterThan(tipAt(t, T, run));
    const speed = (t: number) => (tipAt(t + 0.002, T, run) - tipAt(t - 0.002, T, run)) / 0.004;
    const mid = (T.strike + T.exit) / 2;
    expect(speed(T.strike + 0.004)).toBeGreaterThan(3 * speed(mid));
    expect(speed(T.exit - 0.004)).toBeGreaterThan(2 * speed(mid));
  });

  test('the pull brakes into the rest on the beat, the eye at the thread\'s end, and the tug rings out', () => {
    expect(eyeAt(tipAt(T.pull, T, run))).toBeCloseTo(run.end, 9);
    expect(Math.abs(tipAt(T.pull + 0.5, T, run) - (run.end + EYE_TO_TIP))).toBeLessThan(0.01);
    expect(Math.abs(tipAt(T.pull + 0.03, T, run) - (run.end + EYE_TO_TIP))).toBeGreaterThan(1);
  });

  test('the thread ends at its tip until the needle forms, the front running back to the eye, then at the eye', () => {
    expect(formAt(T.form.at, T)).toBe(0);
    expect(formAt(T.form.end, T)).toBe(1);
    expect(threadEnd(T.draw.end, T, run)).toBe(tipAt(T.draw.end, T, run));
    expect(threadEnd(T.form.end, T, run)).toBeCloseTo(eyeAt(tipAt(T.form.end, T, run)), 9);
    expect(threadEnd(T.exit, T, run)).toBeCloseTo(eyeAt(run.b), 9);
    for (let t = T.form.at; t <= T.form.end; t += 0.01) expect(threadEnd(t, T, run)).toBeLessThanOrEqual(tipAt(t, T, run));
  });

  test('the slack is taken up through the pull and rings past straight after it', () => {
    expect(tautAt(T.exit, T)).toBe(0);
    expect(tautAt(T.pull, T)).toBeCloseTo(1, 9);
    expect(tautAt(T.pull + 0.02, T)).toBeGreaterThan(1);
    expect(Math.abs(tautAt(T.pull + 0.4, T) - 1)).toBeLessThan(0.01);
  });

  test('the lines light in order as the point passes under them', () => {
    const ss = [320, 360, 400, 440, 480];
    const ts = ss.map((s) => tipPasses(s, T, run));
    for (let i = 1; i < ts.length; i++) expect(ts[i]!).toBeGreaterThan(ts[i - 1]!);
    expect(ts[0]!).toBeGreaterThan(T.strike);
    expect(ts[ts.length - 1]!).toBeLessThan(T.exit);
  });

  test('a Hermite segment holds its ends and speeds', () => {
    expect(hermite(0, 0, 3, 7, 1, 9, -2)).toBe(3);
    expect(hermite(1, 0, 3, 7, 1, 9, -2)).toBeCloseTo(9, 12);
    expect((hermite(1e-6, 0, 3, 7, 1, 9, -2) - 3) / 1e-6).toBeCloseTo(7, 4);
  });
});

describe('cite: the thread\'s route', () => {
  const from: P3 = [526, -80, 75], stitch = stitchRoute({ x: 520, top: 72, foot: 226 });
  const A = stitch[0]!, B = stitch[4]!;
  const route = (taut: number) => [...airRoute(from, A, taut), ...stitch.slice(1)];
  const air = airRoute(from, A, 0).length;

  test('it is drawn out of the label, through the air in front of the file, into its face at A', () => {
    const r = route(0);
    expect(r[0]).toEqual(from);
    expect(r[air - 1]).toEqual(A);
    for (const p of r.slice(1, air - 1)) expect(p[2]).toBeGreaterThan(0);
    // the run into A is straight and at 45°: the needle's line
    const [p, q] = [r[air - 3]!, r[air - 2]!];
    const d1 = [q[0] - p[0], q[1] - p[1], q[2] - p[2]], d2 = [A[0] - q[0], A[1] - q[1], A[2] - q[2]];
    const cos = (d1[0]! * d2[0]! + d1[1]! * d2[1]! + d1[2]! * d2[2]!) / (Math.hypot(...d1) * Math.hypot(...d2));
    expect(cos).toBeGreaterThan(0.999);
    expect(Math.abs(d2[1]! / -d2[2]! - 1)).toBeLessThan(0.15);
  });

  test('behind the panel from A to B, then out and past it', () => {
    expect(A[2]).toBe(0);
    expect(B[2]).toBe(0);
    for (const p of stitch.slice(1, 4)) expect(p[2]).toBeLessThan(0);
    for (const p of stitch.slice(5)) expect(p[2]).toBeGreaterThan(0);
    const path = new ArcPath(route(0));
    for (let s = path.atPoint(air - 1) + 2; s < path.atPoint(air + 3) - 2; s += 4) expect(path.at(s).pos.z).toBeLessThan(0);
  });

  test('taut, the air is the straight line from the label to A; slack, it is longer', () => {
    const taut = route(1).slice(0, air);
    for (const p of taut) {
      const f = (p[1] - from[1]) / (A[1] - from[1]);
      expect(p[0]).toBeCloseTo(from[0] + (A[0] - from[0]) * f, 9);
      expect(p[2]).toBeCloseTo(from[2] + (A[2] - from[2]) * f, 9);
    }
    expect(new ArcPath(route(0)).atPoint(air - 1)).toBeGreaterThan(new ArcPath(route(1)).atPoint(air - 1));
  });

  test('a measured route passes through its points, and runs on past its ends along them', () => {
    const path = new ArcPath(route(0));
    for (const i of [0, air - 1, air + 3, route(0).length - 1]) {
      const p = path.at(path.atPoint(i)).pos, q = route(0)[i]!;
      expect(Math.hypot(p.x - q[0], p.y - q[1], p.z - q[2])).toBeLessThan(0.05);
    }
    const end = path.at(path.length).pos, past = path.at(path.length + 10);
    expect(past.pos.distanceTo(end)).toBeCloseTo(10, 6);
  });
});

describe('cite: the needle', () => {
  test('a slim lathe from a round head to a fine point, its eye in the head', () => {
    const p = needleProfile();
    expect(p[0]!.x).toBe(0);
    expect(p[p.length - 1]!.x).toBe(0);
    expect(p[p.length - 1]!.y).toBe(NEEDLE.len);
    for (let i = 1; i < p.length; i++) expect(p[i]!.y).toBeGreaterThan(p[i - 1]!.y);
    expect(Math.max(...p.map((v) => v.x))).toBeLessThan(SHAPE.shaft + SHAPE.swell + 0.01);
    expect(NEEDLE.eye - SHAPE.eyeHalf).toBeGreaterThan(SHAPE.cap);
    expect(NEEDLE.eye + SHAPE.eyeHalf).toBeLessThan(NEEDLE.len - SHAPE.taper);
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
