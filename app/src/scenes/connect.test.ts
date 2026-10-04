// Scene `connect`: its times against the film's own voiceover and beat grid (connect-time.ts), its copy against the
// facts sheet (connect-cards.ts), the terminal's typing, the ✔'s pen and the carousel's turn and flips.
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { lineEnd } from '../engine/panels';
import { VO, norm } from '../engine/vo';
import { AudioData } from '../engine/audio';
import { CARDS, FACES, FLIP, STEP, TICK_DRAW, TURN, faceAngle, flipAt, penAt, penHeat, tickLevel, timesOf, turnAt } from './connect-time';
import { NAME, ROW, SIZE, cardSpecs, copyOf, faceOf, sdkLayout, terminalLines } from './connect-cards';
import { CHECK } from './connect-light';
import S from './connect.strings.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
const vo = new VO(json('vo.json'));
const audio = new AudioData(json('audio.json'));
const span = vo.scenes.find((s) => s.id === 'connect')!;
const T = timesOf(vo, audio, span.start, span.end);
const words = vo.lines.filter((l) => l.scene === 'connect').flatMap((l) => l.words);
const word = (w: string) => words.find((x) => norm(x.w) === norm(w))!;
const onGrid = (t: number, grid: number[]) => grid.some((b) => Math.abs(b - t) < 1e-9);
const copy = copyOf(S as string[]);
const facts = json('facts.json') as { verbatim: { text: string }[]; copy: { text: string }[] };
const sheet = [...facts.verbatim, ...facts.copy].map((e) => e.text);
const cps = (s: string) => Array.from(s);

describe('connect: its times come from the data', () => {
  test('the command types from "One" (on its beat) and is typed by the end of "command…", a moment before Enter', () => {
    expect(T.type.at).toBe(word('one').start);
    expect(onGrid(T.type.at, audio.beats)).toBe(true);
    expect(T.type.end).toBeGreaterThan(word('command').end - 0.25);
    expect(T.type.end).toBeLessThan(T.enter);
  });

  test('Enter lands on the downbeat in her pause between "command…" and "and"', () => {
    expect(onGrid(T.enter, audio.downbeats)).toBe(true);
    expect(T.enter).toBeGreaterThan(word('command').end - 0.1);
    expect(T.enter).toBeLessThan(word('and').start);
  });

  test('`claude mcp list` types in the pause; its answer prints as she says "I\'m"; the ✔ lands on the beat at "in"', () => {
    expect(T.list.at).toBeGreaterThan(T.enter);
    expect(T.out).toBeGreaterThan(T.list.end);
    expect(Math.abs(T.out - word("I'm").start)).toBeLessThan(0.15);
    expect(T.out).toBeLessThan(T.tick - TICK_DRAW);
    expect(onGrid(T.tick, audio.beats)).toBe(true);
    expect(Math.abs(T.tick - word('in').start)).toBeLessThan(0.15);
  });

  test('six cards on six beats in a row, the first after the ✔ (on "Code."), the last before the cut', () => {
    expect(T.cards).toHaveLength(CARDS);
    for (const c of T.cards) expect(onGrid(c, audio.beats)).toBe(true);
    for (let i = 1; i < CARDS; i++) expect(T.cards[i]! - T.cards[i - 1]!).toBeCloseTo(60 / audio.bpm, 6);
    expect(T.cards[0]!).toBeGreaterThan(T.tick);
    expect(Math.abs(T.cards[0]! - word('Code.').start)).toBeLessThan(0.1);
    expect(T.cards[CARDS - 1]!).toBeLessThan(span.end - 0.3);
    // the pull back to the carousel runs from "Claude" to the first card
    expect(T.reveal.at).toBeGreaterThan(word('Claude').start);
    expect(T.reveal.end).toBeLessThan(T.cards[0]!);
  });
});

describe('connect: the copy is the facts sheet\'s, verbatim', () => {
  test('the command is spec §11.1 line for line; `claude mcp list` and its answer are §11.1\'s', () => {
    expect(sheet).toContain(copy.cmd.join('\n'));
    expect(sheet).toContain(`${copy.list.slice(2)}\n${copy.connected}`);
    expect(sheet).toContain(copy.list);
  });

  test('the MCP config is §11.2 whole; the install and its hosts, and the four SDKs, are §11.2–11.3\'s', () => {
    expect(sheet).toContain(copy.mcp.join('\n'));
    expect(sheet).toContain(copy.install);
    expect(sheet).toContain(copy.hosts);
    expect(copy.sdks.map((s) => s.lang)).toEqual(['TypeScript', 'Python', 'Go', 'Rust']);
    for (const s of copy.sdks) {
      expect(sheet).toContain(s.lang);
      expect(sheet).toContain(s.install);
      expect(sheet).toContain(s.setup);
    }
  });

  test('the answer on screen is the line verbatim: the Panel\'s text with a blank where the Tick draws the ✔', () => {
    expect(cps(copy.connected)[copy.tick]).toBe('✔');
    expect(cps(copy.connectedBlank).map((ch, i) => (i === copy.tick ? '✔' : ch)).join('')).toBe(copy.connected);
    expect(cps(copy.connectedBlank)[copy.tick]).toBe(' ');
    // the Tick's mark is the Panel's: the same three points and weight
    expect(CHECK.pts.map((p) => [...p])).toEqual([[0.05, 0.37], [0.225, 0.075], [0.565, 0.7]]);
    expect(CHECK.w).toBe(0.12);
  });
});

describe('connect: the terminal types in time', () => {
  const lines = terminalLines(copy, T);
  test('its rows: the command, the blank Enter leaves, `claude mcp list`, the answer, the prompt back', () => {
    expect(lines.map((l) => l.text)).toEqual([...copy.cmd, '', copy.list, copy.connectedBlank, '']);
    expect(lines[ROW.list]!.text).toBe(copy.list);
    expect(lines[ROW.out]!.text).toBe(copy.connectedBlank);
  });

  test('the command\'s first key on "One", its last at the end of its window; each line after the last, a breath apart', () => {
    expect(lines[0]!.at).toBe(T.type.at);
    expect(lineEnd(lines[2]!)).toBeCloseTo(T.type.end, 9);
    for (const i of [1, 2]) expect(lines[i]!.at!).toBeGreaterThan(lineEnd(lines[i - 1]!));
    expect(lines[0]!.cps).toBe(lines[2]!.cps);
  });

  test('Enter opens the blank row on the downbeat; `claude mcp list` is typed by its end; the answer prints at `out`', () => {
    expect(lines[3]!.at).toBe(T.enter);
    expect(lineEnd(lines[ROW.list]!)).toBeCloseTo(T.list.end, 9);
    expect(lines[ROW.out]!.at).toBe(T.out);
    expect(lines[ROW.out]!.cps).toBeUndefined();
  });
});

describe('connect: the ✔ is drawn on by a pen that lands on the beat', () => {
  test('nothing before the pen sets down; the whole mark on the beat; never back', () => {
    expect(penAt(T.tick - TICK_DRAW - 0.01, T.tick)).toBe(0);
    expect(penAt(T.tick, T.tick)).toBe(1);
    let last = 0;
    for (let t = T.tick - TICK_DRAW; t <= T.tick + 0.1; t += 0.004) {
      const p = penAt(t, T.tick);
      expect(p).toBeGreaterThanOrEqual(last);
      last = p;
    }
  });

  test('the pen is hot while it draws and cools after; the mark flares as it lands and settles to a glow', () => {
    expect(penHeat(T.tick - 0.05, T.tick)).toBe(1);
    expect(penHeat(T.tick + 0.3, T.tick)).toBeLessThan(0.05);
    expect(tickLevel(T.tick - TICK_DRAW - 0.01, T)).toBe(0);
    expect(tickLevel(T.tick, T)).toBeGreaterThan(tickLevel(T.tick + 0.5, T));
    expect(tickLevel(T.cards[0]! - 0.2, T)).toBeGreaterThan(1); // still lit (it blooms a little) through the hold
  });
});

describe('connect: the carousel turns a face and flips a card in on each beat', () => {
  test('a face a beat: card k is in front from its beat (the turn lands on it exactly) and holds there', () => {
    expect(FACES).toBe(CARDS + 1);
    expect(turnAt(T.cards[0]! - 0.3, T.cards)).toBe(0);
    T.cards.forEach((c, i) => {
      expect(turnAt(c, T.cards)).toBeCloseTo((i + 1) * STEP, 2);
      // still from its beat until the next turn sets off
      expect(faceAngle(i + 1, turnAt(c + 0.3, T.cards))).toBeCloseTo(0, 9);
      expect(turnAt(c - TURN.dur, T.cards)).toBeCloseTo(i * STEP, 9);
    });
    expect(turnAt(T.end, T.cards)).toBeCloseTo(CARDS * STEP, 9);
  });

  test('the terminal is face up throughout; a card lies face down until it flips in, face up from its beat', () => {
    for (const t of [T.start, T.tick, T.end]) expect(flipAt(t, 0, T.cards)).toBe(0);
    T.cards.forEach((c, i) => {
      expect(flipAt(c - 0.4, i + 1, T.cards)).toBe(Math.PI);
      expect(flipAt(c, i + 1, T.cards)).toBe(0);
      // it turns over only once its turn has it most of the way round
      expect(flipAt(c - FLIP.dur, i + 1, T.cards)).toBe(Math.PI);
      expect(TURN.dur).toBeGreaterThan(FLIP.dur);
    });
  });

  test('pure: the same time gives the same pose, in any order', () => {
    const ts = [T.cards[2]! - 0.05, T.start, T.cards[2]! - 0.05, T.end, T.tick];
    const a = ts.map((t) => [turnAt(t, T.cards), flipAt(t, 3, T.cards), penAt(t, T.tick), tickLevel(t, T)]);
    const b = ts.map((t) => [turnAt(t, T.cards), flipAt(t, 3, T.cards), penAt(t, T.tick), tickLevel(t, T)]);
    expect(a).toEqual(b);
    expect(a[0]).toEqual(a[2]!);
  });
});

describe('connect: the faces', () => {
  const face = faceOf(copy), cards = cardSpecs(copy);
  test('every face one size, wide enough for TypeScript\'s line at the code size', () => {
    for (const c of cards) expect([c.w, c.h]).toEqual([face.w, face.h]);
    expect(face.w).toBeGreaterThan(cps(copy.sdks[0]!.setup).length * 0.6 * SIZE);
  });

  test('an SDK card\'s name and its rows sit in its middle, the rows under the name\'s descenders', () => {
    const l = sdkLayout(face.h);
    expect(l.base - NAME.cap * NAME.px).toBeGreaterThan(0);
    expect(l.scroll).toBeLessThan(0);
    expect(l.base + NAME.gap).toBeGreaterThan(l.base + 0.2 * NAME.px);
  });
});
