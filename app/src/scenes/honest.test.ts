// Scene `honest`: its times against the film's own voiceover and beat grid (honest-time.ts), the catenary its arms hang
// in, the search that never clears the floor, the fall that keeps each arm's length and leaves the frame empty before
// the answer, and its copy (the card is real JSON).
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import * as THREE from 'three';
import { VO, norm } from '../engine/vo';
import { AudioData } from '../engine/audio';
import { ARMS, RELEASE_GAP, timesOf } from './honest-time';
import { ARM, FLOOR_Y, FOV, MIN_GAP, QUIVER, armAt, cameraAt, catenary, drop, fallTime, pressAt, reachAt, tipAt, type V3 } from './honest-fall';
import { cardSpec } from './honest';
import S from './honest.strings.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
const vo = new VO(json('vo.json'));
const audio = new AudioData(json('audio.json'));
const span = vo.scenes.find((s) => s.id === 'honest')!;
const T = timesOf(vo, audio, span.start, span.end);
const words = vo.lines.filter((l) => l.scene === 'honest').flatMap((l) => l.words);
const word = (w: string, nth = 0) => words.filter((x) => norm(x.w) === w)[nth]!;
const onGrid = (t: number, grid: number[]) => grid.some((b) => Math.abs(b - t) < 1e-9);
const dist = (a: V3, b: V3) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
const polyLength = (p: V3[]) => p.reduce((s, q, i) => (i ? s + dist(q, p[i - 1]!) : 0), 0);

describe('honest: its times come from the data', () => {
  test('the question is typed between the cut and "And"; the floor draws across as she says it', () => {
    expect(T.ask).toBeGreaterThan(span.start);
    expect(T.asked).toBeLessThan(word('and').start);
    expect(T.floor.at).toBeLessThan(word('and').start);
    expect(T.floor.end).toBeGreaterThan(word('when').start);
    for (const a of ARMS) expect(T.rise(a)).toBeGreaterThanOrEqual(T.asked);
  });

  test('the arms press up to the floor on the downbeat where the music drops out, before "know"', () => {
    expect(onGrid(T.hush, audio.downbeats)).toBe(true);
    expect(T.hush).toBe(audio.sections.find((s) => s.name === 'honest')!.start);
    expect(T.hush).toBeGreaterThan(word('and').start);
    expect(T.hush).toBeLessThan(word('know').start);
  });

  test('they let go from the beat after "know…", one by one, with room for the fall before "…I"', () => {
    expect(onGrid(T.release, audio.beats)).toBe(true);
    expect(T.release).toBeGreaterThan(word('know').end - 0.03);
    const slack = ARMS.map((a) => T.slack(a)).sort((x, y) => x - y);
    expect(slack[0]).toBe(T.release);
    expect(slack[2]! - slack[0]!).toBeCloseTo(2 * RELEASE_GAP, 12);
    expect(word('i', 1).start - T.release).toBeGreaterThan(1.4);
  });

  test('the card comes with her "…I"; I don\'t know. on "say", on its downbeat; all inside the scene', () => {
    expect(T.respond).toBeCloseTo(word('i', 1).start - 0.02, 12);
    expect(onGrid(T.say, audio.downbeats)).toBe(true);
    expect(Math.abs(T.say - word('say').start)).toBeLessThan(0.08);
    const note = Array.from(S[7]!).length;
    expect(T.note + (note - 1) / 120).toBeLessThan(span.end - 0.5); // the footnote is whole well before the cut
    for (const t of [T.hush, T.release, T.respond, T.say]) {
      expect(t).toBeGreaterThan(span.start);
      expect(t).toBeLessThan(span.end - 0.6);
    }
  });
});

describe('honest: the catenary', () => {
  const a: V3 = [-1, -0.2, 0.4], b: V3 = [0.8, 0.5, -0.1];
  test('runs from one end to the other, its points even along its length, which is the thread\'s', () => {
    for (const L of [2.05, 2.4, 3.5, 9]) {
      const p = catenary(a, b, L, 400);
      expect(dist(p[0]!, a)).toBeLessThan(1e-12);
      expect(dist(p[399]!, b)).toBeLessThan(1e-12);
      expect(polyLength(p)).toBeCloseTo(L, 2);
      const steps = p.slice(1).map((q, i) => dist(q, p[i]!));
      expect(Math.max(...steps) - Math.min(...steps)).toBeLessThan(1e-3 * (L / 399));
    }
  });

  test('hangs below the chord in the vertical plane through its ends, deeper the longer it is', () => {
    const sag = (L: number) => {
      const p = catenary(a, b, L, 101);
      let most = 0;
      for (let i = 1; i < 100; i++) {
        // the chord's height at the point's own fraction of the span (the points are even in length, not in span)
        const s = Math.hypot(p[i]![0] - a[0], p[i]![2] - a[2]) / Math.hypot(b[0] - a[0], b[2] - a[2]);
        expect(p[i]![1]).toBeLessThan(a[1] + (b[1] - a[1]) * s + 1e-9);
        most = Math.max(most, a[1] + (b[1] - a[1]) * s - p[i]![1]);
        // in the plane: x and z stay on the line between the ends' footprints
        const cross = (p[i]![0] - a[0]) * (b[2] - a[2]) - (p[i]![2] - a[2]) * (b[0] - a[0]);
        expect(Math.abs(cross)).toBeLessThan(1e-9);
      }
      return most;
    };
    expect(sag(2.2)).toBeLessThan(sag(2.6));
    expect(sag(2.6)).toBeLessThan(sag(4));
  });

  test('a thread no longer than the span is the straight line', () => {
    const p = catenary(a, b, dist(a, b), 5);
    expect(p[2]![1]).toBeCloseTo((a[1] + b[1]) / 2, 12);
  });
});

describe('honest: nothing clears the floor', () => {
  test('every point of every arm stays under the floor while it searches, the tips closest on the hush', () => {
    for (const a of ARMS) {
      for (let t = T.rise(a); t <= T.slack(a); t += 1 / 120) {
        const p = armAt(a, t, T);
        for (const q of p.pts) expect(q[1]).toBeLessThan(FLOOR_Y - (MIN_GAP - QUIVER) + 1e-9);
      }
      expect(FLOOR_Y - tipAt(a, T.hush, T)[1]).toBeCloseTo(MIN_GAP, 9);
      expect(pressAt(T.hush, T.hush)).toBe(1);
    }
    expect(MIN_GAP - QUIVER).toBeGreaterThan(0.008);
  });

  test('each arm searches from a root off the frame, its tip under the floor, nearly taut', () => {
    const cam = camAt(T.hush);
    for (const a of ARMS) {
      const r = onScreen(cam, ARM[a].root);
      expect(r.x < -100 || r.x > 2020 || r.y > 1180).toBe(true);
      const tip = onScreen(cam, tipAt(a, T.hush, T));
      expect(tip.x).toBeGreaterThan(96);
      expect(tip.x).toBeLessThan(1824);
      const reach = reachAt(a, T.hush, T);
      expect(reach.length / dist(ARM[a].root, tipAt(a, T.hush, T))).toBeLessThan(1.02);
    }
  });
});

describe('honest: the fall', () => {
  test('is slow motion: a quarter of a second in, under half that has passed for the falling thread', () => {
    expect(fallTime(T.release + 0.25, T.release)).toBeLessThan(0.125);
    expect(fallTime(T.release - 0.1, T.release)).toBe(0);
    expect(drop(0)).toBe(0);
    for (let tau = 0.05; tau < 1; tau += 0.05) expect(drop(tau + 0.01)).toBeGreaterThan(drop(tau));
  });

  test('keeps each arm\'s length (the plies never stretch) and its root follows its tip down', () => {
    for (const a of ARMS) {
      const at = T.slack(a), held = reachAt(a, at, T).length;
      for (const dt of [0.1, 0.4, 0.8]) {
        const p = armAt(a, at + dt, T).pts;
        expect(Math.abs(polyLength(p) / held - 1)).toBeLessThan(0.03);
      }
      const late = armAt(a, at + 1.1, T).pts;
      expect(late[0]![1]).toBeLessThan(ARM[a].root[1] - 0.2);
    }
  });

  test('leaves the frame empty before the card comes up', () => {
    for (const t of [T.respond - 0.15, T.respond, T.end]) {
      const cam = camAt(t);
      for (const a of ARMS) for (const q of armAt(a, t, T).pts) expect(onScreen(cam, q).y).toBeGreaterThan(1080);
    }
  });

  test('is a pure function of t: any order, the same points', () => {
    const ts = [T.slack('cues') + 0.37, T.hush + 0.01, T.release + 0.2, T.rise('body') + 0.1];
    const first = ts.map((t) => ARMS.map((a) => armAt(a, t, T).pts));
    const again = [...ts].reverse().map((t) => ARMS.map((a) => armAt(a, t, T).pts)).reverse();
    expect(again).toEqual(first);
  });
});

describe('honest: the copy is the facts sheet\'s', () => {
  test('the card is the response, real shape: it parses as JSON to the three fields', () => {
    const text = cardSpec().lines.map((l) => l.text).join('\n');
    expect(JSON.parse(text)).toEqual({ memories: [], candidates: 2, filtered_out: 2 });
  });

  test('the footnote is LiveSearch.tsx\'s line verbatim, and I don\'t know. is her words', () => {
    const facts = json('facts.json') as { verbatim: { text: string }[] };
    expect(facts.verbatim.map((e) => e.text)).toContain(S[7]!);
    expect(S[8]).toBe('I don’t know.');
    expect(vo.lines.find((l) => l.scene === 'honest')!.text).toContain('I don’t know');
  });
});

// ------------------------------------------------------------------------------------------------ helpers

function camAt(t: number) {
  const cam = new THREE.PerspectiveCamera(FOV, 16 / 9, 0.05, 40), c = cameraAt(t, T);
  cam.position.set(...c.pos);
  cam.lookAt(...c.target);
  cam.updateProjectionMatrix();
  cam.updateMatrixWorld();
  return cam;
}

function onScreen(cam: THREE.PerspectiveCamera, p: V3) {
  const q = new THREE.Vector3(...p).project(cam);
  return { x: ((q.x + 1) / 2) * 1920, y: ((1 - q.y) / 2) * 1080 };
}

