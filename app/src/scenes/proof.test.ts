// Scene `proof`: its times against the film's own voiceover and beat grid (proof-time.ts), the odometer's count as a
// real counter's (proof-count.ts), the window that shows a drum's digit alone (proof-drums.ts), the board's layout
// against the fonts it sets (proof-board.ts), and its copy against the facts sheet.
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import * as opentype from 'opentype.js';
import { timesOf, ROLL_BEATS } from './proof-time';
import { CLICK, click, digitAt, drumsAt, rollEase, roundsOf } from './proof-count';
import { CENTRE, RADIUS, WINDOW } from './proof-drums';
import { BESIDE, boardLayout, sparkPoint } from './proof-board';
import { DEPTH } from '../engine/type3d';
import { VO, norm } from '../engine/vo';
import { AudioData } from '../engine/audio';
import S from './proof.strings.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const FONTS = path.resolve(import.meta.dir, '../../public/fonts');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
const font = (f: string) => {
  const b = readFileSync(path.join(FONTS, f));
  return opentype.parse(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer);
};
const vo = new VO(json('vo.json'));
const audio = new AudioData(json('audio.json'));
const span = vo.scenes.find((s) => s.id === 'proof')!;
const T = timesOf(vo, audio, span.start, span.end);
const words = vo.lines.filter((l) => l.scene === 'proof').flatMap((l) => l.words);
const word = (w: string) => words.find((x) => norm(x.w) === w)!;
const onGrid = (t: number, grid: number[]) => grid.some((b) => Math.abs(b - t) < 1e-9);
const COPY = S as string[];
const ROUNDS = roundsOf(COPY.slice(0, 10));
const beat = 60 / audio.bpm;

describe('proof: its times come from the data', () => {
  test('the slam is the downbeat the score comes back in on, while "Forty-four…" is still in the air', () => {
    expect(onGrid(T.slam, audio.downbeats)).toBe(true);
    const back = audio.sections.find((s) => s.start > span.start && s.start < span.end)!;
    expect(T.slam).toBe(back.start);
    expect(T.forty).toBe(word('fortyfour').start);
    expect(T.slam).toBeGreaterThan(T.forty);
    expect(T.slam).toBeLessThan(word('to').start);
  });

  test('one round a beat: kicked on the slam and the three beats after it, each landing on the "and"', () => {
    expect(T.kicks).toHaveLength(4);
    expect(T.kicks[0]).toBe(T.slam);
    for (const k of T.kicks) expect(onGrid(k, audio.beats)).toBe(true);
    for (let i = 1; i < 4; i++) expect(T.kicks[i]! - T.kicks[i - 1]!).toBeCloseTo(beat, 6);
    T.lands.forEach((l, i) => expect(l - T.kicks[i]!).toBeCloseTo(ROLL_BEATS * beat, 9));
  });

  test('91.4 lands as she says "four."; the bars flash on the next downbeat, before "Not"', () => {
    const four = word('four');
    expect(T.lands[3]!).toBeGreaterThan(four.start);
    expect(T.lands[3]!).toBeLessThan(four.end);
    expect(onGrid(T.bars, audio.downbeats)).toBe(true);
    expect(T.bars).toBeGreaterThan(T.lands[3]!);
    expect(T.bars - T.lands[3]!).toBeLessThan(beat);
    expect(T.bars).toBeLessThan(T.not);
  });

  test('the % lands on "bad"; the quote types from the beat after; the shine is the last downbeat; all in the window', () => {
    expect(T.bad).toBe(word('bad').start);
    expect(onGrid(T.quote, audio.beats)).toBe(true);
    expect(T.quote).toBeGreaterThan(T.bad);
    expect(T.quote - T.bad).toBeLessThan(beat + 0.2);
    expect(T.shine).not.toBeNull();
    expect(onGrid(T.shine!, audio.downbeats)).toBe(true);
    for (const t of [T.forty, ...T.kicks, ...T.lands, T.bars, T.bad, T.quote, T.shine!]) {
      expect(t).toBeGreaterThan(span.start);
      expect(t).toBeLessThan(span.end - 0.25);
    }
  });
});

describe('proof: the odometer counts as a real one does', () => {
  const at = (t: number) => drumsAt(t, ROUNDS, T.kicks, T.lands);
  const shows = (t: number) => {
    const d = at(t);
    return d.round === 4 ? `${digitAt(d.tens)}${digitAt(d.ones)}.${digitAt(d.tenths)}` : `${digitAt(d.tens)}${digitAt(d.ones)}`;
  };

  test('at rest it shows each round\'s figure: 44 until the slam, then 72, 80, 83 and 91.4 from their landings', () => {
    expect(shows(span.start)).toBe('44');
    expect(shows(T.slam - 1e-3)).toBe('44');
    ['72', '80', '83', '91.4'].forEach((fig, i) => {
      expect(shows(T.lands[i]!)).toBe(fig);
      expect(shows(T.lands[i]! + 0.25)).toBe(fig);
      if (i < 3) expect(shows(T.kicks[i + 1]! - 1e-3)).toBe(fig);
    });
    expect(shows(span.end - 1e-3)).toBe('91.4');
  });

  test('a drum at rest stands square to the window: its position is a whole digit once the click has died', () => {
    // (by the next kick the click is down to a thousandth of a step: a twenty-fifth of a degree)
    for (const t of [span.start, T.kicks[1]! - 0.01, T.kicks[3]! - 0.01, T.lands[3]! + 1]) {
      const d = at(t);
      for (const p of [d.tens, d.ones, ...(d.round === 4 ? [d.tenths] : [])]) expect(Math.abs(p - Math.round(p))).toBeLessThan(2e-3);
    }
  });

  test('the tens drum turns only while the ones drum passes from 9 to 0 (the carry), and it only counts up', () => {
    let prev = at(T.kicks[0]!);
    for (let t = T.kicks[0]!; t < T.lands[0]!; t += 0.002) {
      const d = at(t);
      const onesInStep = ((d.ones % 10) + 10) % 10;
      if (onesInStep < 9 - 1e-9) expect(d.tens).toBe(Math.floor(d.tens));
      expect(d.ones).toBeGreaterThanOrEqual(prev.ones - 1e-9);
      expect(d.tens).toBeGreaterThanOrEqual(prev.tens - 1e-9);
      prev = d;
    }
  });

  test('the last round counts in tenths: the tenths drum spins 84 steps, the ones drum steps 8, the tens ticks once', () => {
    const a = at(T.kicks[3]!), b = at(T.lands[3]!);
    expect(b.tenths - a.tenths).toBeCloseTo(84, 6);
    expect(b.ones - a.ones).toBeCloseTo(8, 6);
    expect(b.tens - a.tens).toBeCloseTo(1, 6);
  });

  test('a roll is kicked at full speed and decelerates into its landing; the detent clicks a hair past and back', () => {
    expect(rollEase(0)).toBe(0);
    expect(rollEase(1)).toBe(1);
    expect(rollEase(0.1)).toBeGreaterThan(0.3); // a third of the run in the first tenth of the time
    expect(rollEase(0.9)).toBeGreaterThan(0.999);
    expect(click(0)).toBe(0);
    expect(click(-1)).toBe(0);
    expect(click(Infinity)).toBe(0);
    let most = 0;
    for (let dt = 0; dt < 1; dt += 0.001) most = Math.max(most, Math.abs(click(dt)));
    expect(most).toBeLessThanOrEqual(CLICK.amp);
    expect(most).toBeGreaterThan(0.5 * CLICK.amp);
    expect(Math.abs(click(0.3))).toBeLessThan(0.01);
  });

  test('the drums stand at the figure\'s kerning at rest and loosen only while they turn', () => {
    expect(at(span.start).loose).toBe(0);
    expect(at(span.start).kern).toBe(1);
    for (let i = 0; i < 4; i++) {
      expect(at(T.kicks[i]!).loose).toBe(0);
      expect(at((T.kicks[i]! + T.lands[i]!) / 2).loose).toBeGreaterThan(0.5);
      expect(at(T.lands[i]!).loose).toBe(0);
      expect(at(T.lands[i]!).kern).toBe(1);
    }
  });

  test('it is a pure function of t: any order, the same drums', () => {
    const ts = [70.1, 66.3, 69.2, 67.31, 68.9, 66.3, 70.1];
    const a = ts.map(at), b = [...ts].reverse().map(at).reverse();
    expect(a).toEqual(b);
  });
});

describe('proof: the window shows a drum\'s digit alone', () => {
  test('a figure at rest is whole inside the window, and its neighbours on the ring stand outside it', () => {
    const half = 0.345; // Bricolage's figures run from −0.014 to 0.674 em about their middle (CENTRE)
    expect(Math.abs(CENTRE - (0.674 - 0.014) / 2)).toBeLessThan(0.01);
    // the back of the digit is nearer the shaft than its face, so it spans the wider angle
    const own = Math.atan2(half, RADIUS - DEPTH);
    expect(own).toBeLessThan(WINDOW[0]);
    expect((2 * Math.PI) / 10 - own).toBeGreaterThan(WINDOW[1]);
  });
});

describe('proof: the board fits the type it sets', () => {
  const brico = font('Bricolage-w1000-800.ttf'), mono = font('JetBrainsMono-400.ttf');
  const adv = (f: opentype.Font, s: string) => Array.from(s).reduce((w, c) => w + f.charToGlyph(c).advanceWidth! / f.unitsPerEm, 0);
  const width = adv(brico, '91.4%');
  const L = boardLayout(width);

  test('beside a two-digit figure the chart stands clear of it, and once dropped it sits under the % above the tags', () => {
    const widest = Math.max(...ROUNDS.slice(0, 4).map((r) => adv(brico, r.figure)));
    expect(L.spark.x0).toBeGreaterThan(widest + 0.2);
    expect(L.spark.x1).toBeLessThanOrEqual(width);
    // beside: its tags over the rule, its top at most the figure's cap
    expect(L.spark.tagY + BESIDE).toBeGreaterThan(L.rule.y);
    expect(L.spark.y1 + BESIDE).toBeLessThan(0.69);
    // the nodes climb with the scores, inside the chart
    const pts = ROUNDS.map((r, i) => sparkPoint(L, i, ROUNDS.length, r.value));
    for (let i = 1; i < pts.length; i++) {
      expect(pts[i]![0]).toBeGreaterThan(pts[i - 1]![0]);
      expect(pts[i]![1]).toBeGreaterThan(pts[i - 1]![1]);
    }
    for (const [, y] of pts) {
      expect(y).toBeGreaterThan(L.spark.y0 - 1e-9);
      expect(y).toBeLessThan(L.spark.y1 + 1e-9);
    }
  });

  test('the bars\' longest label fits its column, the bars clear the chart, and the board is under the rule', () => {
    const longest = Math.max(...COPY.slice(10, 16).map((s) => adv(mono, s.slice(0, s.lastIndexOf(' ')))));
    expect(longest * L.bars.label).toBeLessThan(L.bars.labelW - 0.03);
    expect(L.bars.x1).toBeLessThan(L.spark.x0 - 0.15);
    expect(L.bars.top).toBeLessThan(L.rule.y);
    const notesW = Math.max(adv(mono, COPY[16]!), adv(mono, COPY[17]!)) * L.notes.size;
    expect(notesW).toBeLessThan(width);
  });

  test('the drums turn wide digits apart: the tabular gap clears the widest figure on the ring', () => {
    const widest = Math.max(...Array.from('0123456789').map((c) => adv(brico, c)));
    expect(widest).toBeLessThan(0.62); // TAB in proof.ts
  });
});

describe('proof: the copy is the facts sheet\'s', () => {
  const facts = json('facts.json') as { verbatim: { text: string }[]; copy: { text: string }[] };
  const fold = (s: string) => s.replace(/[‘’]/g, "'");
  const sheet = [...facts.verbatim, ...facts.copy].map((e) => fold(e.text));

  test('the rounds are spec §11.8\'s, in order, tag and figure', () => {
    expect(ROUNDS.map((r) => r.tag)).toEqual(['v1', 'v3', 'v4', 'v5', 'v7']);
    expect(ROUNDS.map((r) => r.value)).toEqual([44, 72, 80, 83, 91.4]);
    const line = ROUNDS.map((r) => `${r.tag} ${r.figure}`).join(' → ');
    expect(sheet).toContain(line);
  });

  test('the bars, the source and the quote are on the sheet whole', () => {
    for (const s of COPY.slice(10)) expect(sheet).toContain(fold(s));
    expect(COPY.slice(10, 16).map((s) => s.slice(s.lastIndexOf(' ') + 1))).toEqual(['94.9', '87.9', '96.4', '100', '97.1', '85.7']);
  });
});
