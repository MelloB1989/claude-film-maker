// Scene `anywhere`: its times against the film's own voiceover and beat grid (anywhere-time.ts), its copy against the
// facts sheet, the namespaces' doubling (each copy's place and where it comes from), the Memory Graph's simulation (pure,
// settling, its tiers in their regions), the chips' deal and the ✔'s pen.
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { VO, norm } from '../engine/vo';
import { AudioData } from '../engine/audio';
import { lineEnd } from '../engine/panels';
import { CHIPS, DOUBLINGS, NAMESPACES, blockAfter, cellOf, copyOffset, levelOf, nsName, timesOf } from './anywhere-time';
import { PEN, chipNames, dealAt, layoutChipRows, penAt } from './anywhere-machine';
import { TIERS, memoryGraph, placeAt, simulate, tierAngle } from './anywhere-graph';
import { PLAY, toolWidth } from './anywhere-console';
import S from './anywhere.strings.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
const vo = new VO(json('vo.json'));
const audio = new AudioData(json('audio.json'));
const span = vo.scenes.find((s) => s.id === 'anywhere')!;
const T = timesOf(vo, audio, span.start, span.end);
const words = vo.lines.filter((l) => l.scene === 'anywhere').flatMap((l) => l.words);
const word = (w: string) => words.find((x) => norm(x.w) === norm(w))!;
const onGrid = (t: number, grid: number[]) => grid.some((b) => Math.abs(b - t) < 1e-9);
const facts = json('facts.json') as { verbatim: { text: string }[]; copy: { text: string }[]; illustrative_patterns: { pattern: string; why: string }[] };
const sheet = [...facts.verbatim, ...facts.copy].map((e) => e.text);
const strings = S as string[];
const q = 60 / audio.bpm / 4;

describe('anywhere: its times come from the data', () => {
  test('the install line types from "On" (on its beat), done as "machine…" ends, a moment before Enter', () => {
    expect(T.type.at).toBe(word('On').start);
    expect(onGrid(T.type.at, audio.beats)).toBe(true);
    expect(T.type.end).toBeGreaterThan(word('machine...').end - 0.1);
    expect(T.type.end).toBeLessThan(T.enter);
  });

  test('the four chips are dealt a sixteenth apart from the first beat in her pause, Enter a sixteenth before', () => {
    expect(T.chips).toHaveLength(CHIPS);
    expect(onGrid(T.chips[0]!, audio.beats)).toBe(true);
    expect(T.chips[0]!).toBeGreaterThan(word('machine...').end);
    for (let i = 1; i < CHIPS; i++) expect(T.chips[i]! - T.chips[i - 1]!).toBeCloseTo(q, 9);
    expect(T.chips[0]! - T.enter).toBeCloseTo(q, 9);
    expect(T.chips[CHIPS - 1]!).toBeLessThan(T.split);
  });

  test('the split is the downbeat between "machine…" and "in"; the cards deal on sixteenths from it', () => {
    expect(onGrid(T.split, audio.downbeats)).toBe(true);
    expect(T.split).toBeGreaterThan(word('machine...').end);
    expect(T.split).toBeLessThan(word('in').start);
    T.deal.forEach((d, i) => expect(d).toBeCloseTo(T.split + i * q, 9));
  });

  test('the tool calls land on the beat on "cloud." and the next; the graph settles from its card\'s deal', () => {
    expect(onGrid(T.retrieve, audio.beats)).toBe(true);
    expect(Math.abs(T.retrieve - word('cloud.').start)).toBeLessThan(q);
    expect(T.remember - T.retrieve).toBeCloseTo(4 * q, 9);
    expect(T.settle.at).toBe(T.deal[1]!);
    expect(T.settle.end).toBeGreaterThan(T.remember);
  });

  test('"One" opens the first namespace; the cut is half a frame before the downbeat on "for"', () => {
    expect(T.first).toBe(word('One').start);
    expect(onGrid(T.down, audio.downbeats)).toBe(true);
    expect(Math.abs(T.down - word('for').start)).toBeLessThan(q);
    const x = T.cut * 30;
    expect(x - Math.floor(x)).toBeCloseTo(0.5, 6);
    expect(T.cut).toBeLessThan(T.down);
    expect(T.down - T.cut).toBeLessThan(1 / 30);
  });

  test('eleven doublings a sixteenth apart from the one after the downbeat, done with a beat before the cut out', () => {
    expect(T.doublings).toHaveLength(DOUBLINGS);
    T.doublings.forEach((d, k) => expect(d).toBeCloseTo(T.down + (k + 1) * q, 9));
    expect(T.doublings[DOUBLINGS - 1]!).toBeLessThan(span.end - 60 / audio.bpm);
  });

  test('the label types on "user", the footnote on the beat on "have."; all in the window', () => {
    expect(Math.abs(T.label - word('user').start)).toBeLessThan(0.05);
    expect(onGrid(T.note, audio.beats)).toBe(true);
    expect(Math.abs(T.note - word('have.').start)).toBeLessThan(q);
    for (const t of [T.type.at, ...T.chips, T.split, T.retrieve, T.remember, T.first, T.cut, ...T.doublings, T.label, T.note]) {
      expect(t).toBeGreaterThan(span.start);
      expect(t).toBeLessThan(span.end);
    }
  });
});

describe('anywhere: the copy is the facts sheet\'s', () => {
  test('the install line, the chips, the console\'s names, the label and the footnote are on the sheet verbatim', () => {
    for (const s of [strings[2]!, strings[3]!, 'Playground', 'Memory Graph', 'Namespaces', 'gitloom_retrieve', 'gitloom_remember',
      'Maya moved to Lisbon in March 2026.', 'user-0001 … user-2048', 'one per end user · a storage boundary, not a WHERE clause',
      'free plan · no card · storage is free']) {
      expect(strings).toContain(s);
      expect(sheet).toContain(s);
    }
  });

  test('the chips are the line\'s four, split at its dots', () => {
    expect(chipNames(strings[3]!)).toEqual(['one static binary', 'no CGo', 'arm64 + amd64', 'licence verified offline']);
  });

  test('the headlines are her line, split at its pause', () => {
    const line = vo.lines.find((l) => l.id === 'L28')!.text;
    expect(`${strings[0]} ${strings[1]}`).toBe(line);
  });

  test('every namespace is the sheet\'s illustrative shape, user-0001 to user-2048, the range\'s ends', () => {
    const shape = new RegExp(facts.illustrative_patterns.find((p) => p.why.includes('namespace'))!.pattern);
    const names = Array.from({ length: NAMESPACES }, (_, i) => nsName(i));
    for (const n of names) expect(shape.test(n)).toBe(true);
    expect(new Set(names).size).toBe(NAMESPACES);
    expect(`${names[0]} … ${names[NAMESPACES - 1]}`).toBe('user-0001 … user-2048');
  });

  test('the graph labels its four tiers by the names the strings file holds', () => {
    expect(strings.slice(10, 14)).toEqual([...TIERS]);
  });
});

describe('anywhere: the namespaces double', () => {
  test('2,048 namespaces fill 64 columns by 32 rows, one each', () => {
    const seen = new Set<string>();
    for (let i = 0; i < NAMESPACES; i++) {
      const c = cellOf(i);
      expect(c.x).toBeGreaterThanOrEqual(0);
      expect(c.x).toBeLessThan(64);
      expect(c.y).toBeLessThan(32);
      seen.add(`${c.x},${c.y}`);
    }
    expect(seen.size).toBe(NAMESPACES);
    expect(blockAfter(DOUBLINGS)).toEqual({ cols: 64, rows: 32 });
  });

  test('after n doublings the first 2^n fill one block, which the next doubling copies beside itself', () => {
    for (let n = 0; n <= DOUBLINGS; n++) {
      const b = blockAfter(n);
      expect(b.cols * b.rows).toBe(2 ** n);
      for (let i = 0; i < 2 ** n; i++) {
        const c = cellOf(i);
        expect(c.x).toBeLessThan(b.cols);
        expect(c.y).toBeLessThan(b.rows);
      }
    }
  });

  test('each copy comes from its original: the same place in the block before, one block back along the axis', () => {
    expect(levelOf(0)).toBe(-1);
    for (let i = 1; i < NAMESPACES; i++) {
      const k = levelOf(i), o = copyOffset(i), c = cellOf(i), src = cellOf(i - 2 ** k);
      expect(i).toBeGreaterThanOrEqual(2 ** k);
      expect(i).toBeLessThan(2 ** (k + 1));
      expect({ x: c.x - o.dx, y: c.y - o.dy }).toEqual(src);
      expect(k % 2 === 0 ? o.dy : o.dx).toBe(0);
    }
  });
});

describe('anywhere: the Memory Graph settles', () => {
  const g = memoryGraph();
  const sim = simulate(g, 300);

  test('the simulation is pure: the same memory gives the same ticks', () => {
    const again = simulate(memoryGraph(), 300);
    expect(again.ticks.length).toBe(sim.ticks.length);
    for (const k of [0, 1, 7, 50, 300]) expect(Array.from(again.ticks[k]!)).toEqual(Array.from(sim.ticks[k]!));
  });

  test('it settles: by its last ticks nothing moves', () => {
    const p = { x: 0, y: 0 }, r = { x: 0, y: 0 };
    let most = 0;
    for (let i = 0; i < sim.nodes.length; i++) {
      placeAt(sim, 299, i, p);
      placeAt(sim, 300, i, r);
      most = Math.max(most, Math.hypot(r.x - p.x, r.y - p.y));
    }
    expect(most).toBeLessThan(0.1);
  });

  test('each tier settles into its own region, round the centre in its own direction', () => {
    const p = { x: 0, y: 0 };
    for (const tier of TIERS) {
      let x = 0, y = 0, n = 0;
      sim.nodes.forEach((nd, i) => {
        if (nd.tier !== tier) return;
        placeAt(sim, 300, i, p);
        x += p.x;
        y += p.y;
        n++;
      });
      const a = Math.atan2(y / n, x / n), want = tierAngle(tier);
      const diff = Math.abs(Math.atan2(Math.sin(a - want), Math.cos(a - want)));
      expect(diff).toBeLessThan(0.5);
    }
  });

  test('it starts as one disc with the tiers mixed through it: nothing starts on top of anything', () => {
    const t0 = sim.ticks[0]!;
    let nearest = Infinity;
    for (let i = 0; i < sim.nodes.length; i++) {
      for (let j = i + 1; j < sim.nodes.length; j++) nearest = Math.min(nearest, Math.hypot(t0[2 * i]! - t0[2 * j]!, t0[2 * i + 1]! - t0[2 * j + 1]!));
    }
    expect(nearest).toBeGreaterThan(10);
  });
});

describe('anywhere: the machine', () => {
  test('the install line is typed by the time Enter brings the new prompt', () => {
    const n = Array.from(strings[2]!).length;
    const l = { text: strings[2]!, kind: 'cmd' as const, at: T.type.at, cps: (n - 3) / (T.type.end - T.type.at) };
    expect(lineEnd(l)).toBeCloseTo(T.type.end, 9);
  });

  test('a chip is dealt on its sixteenth: hidden before it launches, home as it lands, settled soon after', () => {
    const land = 10;
    expect(dealAt(land - 0.3, land).on).toBe(false);
    expect(dealAt(land, land).s).toBeCloseTo(1, 6);
    expect(Math.abs(dealAt(land + 0.5, land).s - 1)).toBeLessThan(0.01);
    expect(dealAt(land + 0.5, land).tilt).toBeLessThan(0.02);
  });

  test('the chips lay out in rows inside the page, the licence chip last with its ✔', () => {
    const rows = layoutChipRows(chipNames(strings[3]!), 112, 440, 790);
    expect(rows).toHaveLength(4);
    for (const r of rows) expect(r.x + r.w).toBeLessThanOrEqual(112 + 790 + 1e-6);
    expect(rows.map((r) => r.check)).toEqual([false, false, false, true]);
  });

  test('the ✔\'s pen sets down, runs and lands with its chip', () => {
    expect(penAt(10 - PEN - 0.01, 10)).toBe(0);
    expect(penAt(10, 10)).toBeCloseTo(1, 9);
    expect(penAt(10 - PEN / 2, 10)).toBeGreaterThan(0.2);
  });

  test('the tool rows fit the Playground card', () => {
    for (const name of ['gitloom_retrieve', 'gitloom_remember']) expect(PLAY.tool.x + toolWidth(name)).toBeLessThan(PLAY.w - 20);
  });
});
