// Scene `graph`: its times against the film's own voiceover and beat grid (graph-time.ts), the copy it shows (verbatim
// from the facts sheet, and the runs of it the scene lights), the dangling link and its heal, the walk's light, and the
// terminal's place in the frame.
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { VO, norm } from '../engine/vo';
import { AudioData } from '../engine/audio';
import { lineEnd } from '../engine/panels';
import { HOP, HOPS, timesOf } from './graph-time';
import { DANGLE, NODES, STANDING, bloodAt, dangleAt, dashAt, dist3, healFront, looseEnd, mossAt, runAt, type V3 } from './graph-world';
import { ALIAS, ANSWER_LINE, FILE_LINES, LINK, TAG_NAME, TERM_AT } from './graph';
import S from './graph.strings.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
const vo = new VO(json('vo.json'));
const audio = new AudioData(json('audio.json'));
const span = vo.scenes.find((s) => s.id === 'graph')!;
const T = timesOf(vo, audio, span.start, span.end);
const words = vo.lines.filter((l) => l.scene === 'graph').flatMap((l) => l.words);
const word = (w: string, nth = 0) => words.filter((x) => norm(x.w) === w)[nth]!;
const onGrid = (t: number, grid: number[]) => grid.some((b) => Math.abs(b - t) < 1e-9);
const [, , , , , WORKS, ACME, , FORWARD, TRIP, , , VOCAB, ANSWER, K8S, KUBE] = S as string[];
const chars = (s: string, a: number, b: number) => Array.from(s).slice(a, b).join('');

describe('graph: its times come from the data', () => {
  test('the link lifts off on the downbeat she says "I" on, and lands in acme.md on the eighth, inside "connect"', () => {
    expect(onGrid(T.lift, audio.downbeats)).toBe(true);
    expect(Math.abs(T.lift - word('i').start)).toBeLessThan(0.1);
    expect(T.land).toBeCloseTo(T.lift + T.beat / 2, 12);
    expect(T.land).toBeGreaterThan(word('connect').start);
    expect(T.land).toBeLessThan(word('connect').end + 0.05);
    expect(T.underline.at).toBeGreaterThan(span.start);
    expect(T.underline.end).toBeLessThan(T.lift);
  });

  test('the dangling link pings on a beat; the trip is written on the beat after "dots…", and the walk runs on from it', () => {
    expect(onGrid(T.ping, audio.beats)).toBe(true);
    expect(onGrid(T.heal, audio.beats)).toBe(true);
    expect(T.ping).toBeGreaterThan(T.land);
    expect(T.heal).toBeGreaterThan(word('dots').end - 0.05);
    expect(T.heal - T.ping).toBeCloseTo(T.beat, 9);
    expect(T.hops).toHaveLength(HOPS);
    T.hops.forEach((h, i) => expect(h).toBeCloseTo(T.heal + (i + 1) * HOP * T.beat, 12));
  });

  test('the walk lands before the command types with "and I learn"; the answer lands on the downbeat before "your"', () => {
    expect(T.type.at).toBeGreaterThan(T.hops[HOPS - 1]!);
    expect(T.type.at).toBeGreaterThan(word('and').start);
    expect(onGrid(T.answer, audio.downbeats)).toBe(true);
    expect(T.answer).toBeGreaterThan(word('learn').start - 0.2);
    expect(T.answer).toBeLessThan(word('your').start);
    expect(T.type.end).toBeLessThan(T.answer);
    const cmd = { text: VOCAB!, kind: 'cmd' as const, at: T.type.at, cps: (Array.from(VOCAB!).length - 3) / (T.type.end - T.type.at) };
    expect(lineEnd(cmd)).toBeCloseTo(T.type.end, 9);
  });

  test('k8s lifts off on "your" and the search lands on the beat inside "language.", with time to fly there in one move', () => {
    expect(T.seek).toBeGreaterThan(T.answer);
    expect(Math.abs(T.seek - word('your').start)).toBeLessThan(0.05);
    expect(onGrid(T.found, audio.beats)).toBe(true);
    expect(T.found).toBeGreaterThan(word('language').start);
    expect(T.found).toBeLessThan(word('language').end);
    // one continuous move from the answer up the thread into acme.md: no cut in the scene
    expect('cut' in T).toBe(false);
    expect(T.found - T.seek).toBeGreaterThan(0.35);
    expect(span.end - T.found).toBeGreaterThan(0.5); // the find holds before the cut to honest
    for (const t of [T.lift, T.land, T.ping, T.heal, T.answer, T.found]) {
      expect(t).toBeGreaterThan(span.start);
      expect(t).toBeLessThan(span.end);
    }
  });
});

describe('graph: the copy', () => {
  test('every string is the facts sheet\'s, and the runs the scene lights are what they claim', () => {
    expect(chars(WORKS!, LINK.from, LINK.to)).toBe('[[facts/orgs/acme.md]]');
    expect(WORKS!.includes(ACME!)).toBe(true);
    expect(chars(FORWARD!, TAG_NAME.from, TAG_NAME.to)).toBe(TRIP);
    expect(FORWARD).toBe(`[[facts/trips/${TRIP}]]`);
    expect(chars(ANSWER_LINE, ALIAS.from, ALIAS.to)).toBe(K8S);
    expect(ANSWER_LINE.trim()).toBe(ANSWER);
    expect(ANSWER).toBe('k8s → kubernetes  ·  search finds either form');
    expect(VOCAB).toBe('$ gitloom vocab add --term kubernetes --alias k8s');
    expect(VOCAB!.includes(`--term ${KUBE}`) && VOCAB!.includes(`--alias ${K8S}`)).toBe(true);
  });

  test('the editor shows the file\'s last eight lines, 11–18, ending on the link', () => {
    expect(FILE_LINES).toHaveLength(8);
    expect(FILE_LINES[7]).toBe(WORKS);
    expect(FILE_LINES[0]).toBe('## Editor');
  });
});

describe('graph: the dangling link and its heal', () => {
  const from = NODES.maya.pos, to = NODES.trip.pos;

  test('before the heal it falls short of the trip and hangs below it, swaying; after it, its end is on the trip', () => {
    for (const t of [T.ping - 0.2, T.ping, T.heal - 0.25]) {
      const { end, k } = looseEnd(t, from, to, T.heal);
      expect(k).toBe(0);
      expect(dist3(end, to)).toBeGreaterThan(0.05);
      expect(end[1]).toBeLessThan(to[1] - DANGLE.drop / 2);
    }
    const settled = looseEnd(T.heal + 0.6, from, to, T.heal);
    expect(dist3(settled.end, to)).toBeLessThan(1e-3);
    // it snaps home on the heal itself (the spring's impact lands on the beat)
    expect(looseEnd(T.heal, from, to, T.heal).k).toBeCloseTo(1, 6);
  });

  test('the thread runs from maya.md to its end, and is a pure function of t', () => {
    const a = dangleAt(T.ping, from, to, T.heal, 40), b = dangleAt(T.ping, from, to, T.heal, 40);
    expect(a).toEqual(b);
    expect(dist3(a[0]!, from)).toBeLessThan(1e-12);
    expect(dist3(a[39]!, looseEnd(T.ping, from, to, T.heal).end)).toBeLessThan(1e-12);
    // it droops below its chord
    const mid = a[20]!, chord = [(a[0]![0] + a[39]![0]) / 2, (a[0]![1] + a[39]![1]) / 2, (a[0]![2] + a[39]![2]) / 2] as V3;
    expect(mid[1]).toBeLessThan(chord[1]);
  });

  test('blood dashes until the heal; the heal sweeps them away from the root, moss behind it; none left once it arrives', () => {
    const us = Array.from({ length: 101 }, (_, i) => i / 100);
    const lit = us.filter((u) => dashAt(u, T.ping) > 0.9).length;
    expect(lit).toBeGreaterThan(25);
    expect(lit).toBeLessThan(75);
    for (const u of us) expect(mossAt(u, T.heal - 0.01, T.heal, T.hops[0]!)).toBe(0);
    const mid = (T.heal + T.hops[0]!) / 2, f = healFront(mid, T.heal, T.hops[0]!);
    expect(f).toBeGreaterThan(0.1);
    expect(f).toBeLessThan(1);
    for (const u of us) {
      if (u < f - 0.05) expect(bloodAt(u, mid, T.heal, T.hops[0]!)).toBe(0);
      if (u < f - 0.05) expect(mossAt(u, mid, T.heal, T.hops[0]!)).toBeGreaterThan(0.2);
      if (u > f + 0.05) expect(mossAt(u, mid, T.heal, T.hops[0]!)).toBe(0);
    }
    for (const u of us) expect(bloodAt(u, T.hops[0]! + 0.01, T.heal, T.hops[0]!)).toBe(0);
  });

  test('a hop\'s light: none before it, its head at the far end when it lands, an ember after', () => {
    const [t0, t1] = [T.hops[0]!, T.hops[1]!];
    for (const u of [0, 0.5, 1]) expect(runAt(t0 - 0.01, u, t0, t1)).toBe(0);
    expect(runAt(t1, 1, t0, t1)).toBeGreaterThan(0.9);
    expect(runAt(t1 + 0.3, 0.5, t0, t1)).toBeGreaterThan(0.05);
    expect(runAt(t1 + 0.3, 0.5, t0, t1)).toBeLessThan(0.6);
  });
});

describe('graph: the world', () => {
  test('every edge joins two memories the graph has, and no memory sits on another', () => {
    for (const [a, b] of STANDING) {
      expect(NODES[a]).toBeDefined();
      expect(NODES[b]).toBeDefined();
      expect(a).not.toBe(b);
    }
    const ids = Object.keys(NODES) as (keyof typeof NODES)[];
    for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
      expect(dist3(NODES[ids[i]!].pos, NODES[ids[j]!].pos)).toBeGreaterThan(NODES[ids[i]!].r + NODES[ids[j]!].r + 0.05);
    }
  });

  test('the terminal stands inside the title-safe frame', () => {
    const half = 1020 / 2;
    expect(TERM_AT.x - half).toBeGreaterThanOrEqual(96);
    expect(TERM_AT.x + half).toBeLessThanOrEqual(1920 - 96);
    expect(TERM_AT.y + 110).toBeLessThanOrEqual(1080 - 96);
  });
});
