// Scene `ex`: the float cloud's data (ex-cloud.ts) and the scene's times (ex.ts timesOf) against the film's own
// voiceover and beat grid. (The glyph atlas's distance field and the split-flap's schedule are the engine's: glyphs.test.ts.)
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import {
  ADV, BERLIN_SLOTS, CELLS, EM, PITCH, REGION, SPHEROID, buildCloud, cardFloats, cells, fall, fallOf, floatOf, morphTargets, shown,
} from './ex-cloud';
import { timesOf } from './ex';
import { VO } from '../engine/vo';
import { AudioData } from '../engine/audio';
import S from './ex.strings.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
/** The facts sheet's float numeral (spec §11.10): the shape every numeral of the cloud must have. */
const FLOAT = new RegExp(
  (json('facts.json').illustrative_patterns as { pattern: string; why: string }[]).find((p) => p.why.includes('float numerals'))!.pattern,
);
const NAMED = [0.2143, -0.0931, 0.7715];

describe('ex: the float cloud', () => {
  const c = buildCloud(NAMED);

  test('about six thousand numerals, the same every time', () => {
    expect(c.numerals.length).toBeGreaterThan(5500);
    expect(c.numerals.length).toBeLessThan(6500);
    const again = buildCloud(NAMED);
    expect(again.numerals.map((n) => [n.x, n.y, n.z, n.text])).toEqual(c.numerals.map((n) => [n.x, n.y, n.z, n.text]));
  });

  test('every numeral is a float numeral of the facts sheet, seven cells with a sign or a blank first', () => {
    for (const n of c.numerals) {
      expect(Array.from(n.text)).toHaveLength(CELLS);
      expect(shown(n.v)).toMatch(FLOAT);
      expect(n.text.trimStart()).toBe(shown(n.v));
    }
    for (const s of [S[14], S[15], S[16]]) expect(s).toMatch(FLOAT);
    expect(cells(-0.0931)).toBe('−0.0931');
    expect(cells(0.2143)).toBe(' 0.2143');
    for (let k = 0; k < 2000; k++) expect(shown(floatOf(k))).toMatch(FLOAT);
  });

  test('inside the loose spheroid, strengths 25–60% of bone, drawn far layer first', () => {
    for (const n of c.numerals) {
      expect(n.rn).toBeLessThan(1.1);
      expect(n.bright).toBeGreaterThanOrEqual(0.25);
      expect(n.bright).toBeLessThanOrEqual(0.6);
    }
    for (let i = 1; i < c.numerals.length; i++) expect(c.numerals[i]!.z).toBeGreaterThanOrEqual(c.numerals[i - 1]!.z);
    expect(c.numerals.every((n, i) => n.id === i)).toBe(true);
  });

  test('the Maya region is an exact 5x3 block of the front layer, with nothing in front of it', () => {
    expect(c.region).toHaveLength(REGION.rows);
    const z = c.region[0]![0]!.z;
    for (const row of c.region) {
      expect(row).toHaveLength(REGION.cols);
      row.forEach((n, s) => {
        expect(n.z).toBe(z);
        expect(n.slot).toBe(s);
        if (s > 0) expect(n.x - row[s - 1]!.x).toBeCloseTo(PITCH.x, 9); // columns one pitch apart, unjittered
      });
    }
    // rows one pitch apart, top to bottom
    expect(c.region[0]![0]!.y - c.region[1]![0]!.y).toBeCloseTo(PITCH.y, 9);
    // nothing nearer the camera overlaps the block
    const x0 = c.region[0]![0]!.x - ADV, x1 = c.region[0]![REGION.cols - 1]!.x + (CELLS + 1) * ADV;
    const y0 = c.region[2]![0]!.y - EM, y1 = c.region[0]![0]!.y + 2 * EM;
    const inFront = c.numerals.filter((n) => n.z > z + 1e-9 && n.x + CELLS * ADV > x0 && n.x < x1 && n.y > y0 && n.y < y1);
    expect(inFront).toHaveLength(0);
    expect(c.named.map((n) => n.v)).toEqual(NAMED);
  });
});

describe('ex: the cards', () => {
  test('a sentence becomes one seven-cell float per seven characters, its letters melting into their cells', () => {
    const berlin = S[4]!, lisbon = S[5]!;
    expect(cardFloats(berlin, 7)).toHaveLength(3);
    expect(cardFloats(lisbon, 11)).toHaveLength(5);
    expect(BERLIN_SLOTS).toHaveLength(3);
    for (const [text, seed] of [[berlin, 7], [lisbon, 11]] as const) {
      const fl = cardFloats(text, seed), tg = morphTargets(text, fl);
      expect(tg).toHaveLength(Array.from(text).length);
      expect(tg.join('')).toBe(fl.map(cells).join('').slice(0, tg.length));
      for (const v of fl) expect(shown(v)).toMatch(FLOAT);
    }
  });
});

describe('ex: the collapse', () => {
  test('a numeral falls under gravity and lands after sqrt(2h/g); every slot of the line is within it', () => {
    const f = fall(0.5, 0.75, 6);
    expect(f.dur).toBeCloseTo(0.5, 9);
    expect(fall(0.49, 0.75, 6).landed).toBe(false);
    expect(fall(0.5, 0.75, 6).landed).toBe(true);
    expect(fall(-0.1, 0.75, 6).k).toBe(0);
    for (const n of buildCloud(NAMED).numerals) {
      const { slot, delay } = fallOf(n);
      expect(slot).toBeGreaterThanOrEqual(0);
      expect(slot).toBeLessThanOrEqual(1);
      expect(delay).toBeLessThan(0.02); // the sculpture drops as one
    }
    expect(SPHEROID.rx).toBeGreaterThan(SPHEROID.ry);
  });
});

describe('ex: its times come from the voiceover and the score', () => {
  const vo = new VO(json('vo.json'));
  const audio = new AudioData(json('audio.json'));
  const span = vo.scenes.find((s) => s.id === 'ex')!;
  const T = timesOf(vo, audio, span.start, span.end);
  const onBeat = (t: number) => audio.beats.some((b) => Math.abs(b - t) < 1e-9);
  const onDownbeat = (t: number) => audio.downbeats.some((b) => Math.abs(b - t) < 1e-9);

  test('the downbeats are events: the reveal, the Berlin card, the first stamp, the fatal line', () => {
    for (const t of [T.reveal, T.berlin, T.stamps[0]!, T.resolve]) expect(onDownbeat(t)).toBe(true);
  });

  test('the flaps land on beats, and the stamps on successive beats before the drop', () => {
    expect(onBeat(T.wave1)).toBe(true);
    expect(onBeat(T.wave2)).toBe(true);
    expect(T.wave2).toBeGreaterThan(T.wave1);
    T.stamps.forEach((t, i) => {
      expect(onBeat(t)).toBe(true);
      if (i) expect(audio.beatAt(t) - audio.beatAt(T.stamps[i - 1]!)).toBeCloseTo(1, 6);
    });
    expect(T.stamps[2]!).toBeLessThan(T.drop);
    expect(onBeat(T.drop)).toBe(true);
    expect(onBeat(T.punch)).toBe(true);
  });

  test('in order within the window, keyed on her words', () => {
    const seq = [T.start, T.its, T.reveal, T.vector, T.store, T.typeOut, T.berlin, T.lisbonIn, T.lisbonMorph, T.lisbonDive, T.wave1,
      T.wave2, T.query, T.stamps[0]!, T.why, T.stamps[2]!, T.drop, T.resolve, T.punch, T.end];
    for (let i = 1; i < seq.length; i++) expect(seq[i]!).toBeGreaterThan(seq[i - 1]!);
    const word = (w: string) => vo.words.find((x) => x.w.replace(/[^\w]/g, '').toLowerCase() === w)!.start;
    expect(T.why).toBe(word('why'));
    expect(T.vector).toBe(word('vector'));
    expect(Math.abs(T.drop - word('commitment'))).toBeLessThan(0.1);
  });
});
