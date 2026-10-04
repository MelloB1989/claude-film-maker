// Scene `loom`'s times and type: every time from the data (L11–L14's words, the beats), the skills reach read off the
// plate's track, and the tier words behaving as their tiers do.
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { VO } from '../engine/vo';
import { Track } from '../engine/track';
import type { AudioData } from '../engine/audio';
import { EXPIRE, TIERS, loomTimes, reachTime } from './loom-time';
import { labelOn, letGo, lightWipe, reveal, rulesPull, stamp } from './loom-type';
import S from './loom.strings.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const vo = new VO(JSON.parse(readFileSync(path.join(DATA, 'vo.json'), 'utf8')));
const audio = JSON.parse(readFileSync(path.join(DATA, 'audio.json'), 'utf8')) as AudioData;
const scene = vo.scenes.find((s) => s.id === 'loom')!;
const T = loomTimes(vo, audio, scene.start, scene.end);
const raw = JSON.parse(readFileSync(path.join(DATA, 'vo.json'), 'utf8'));
const words = (id: string) => raw.lines.find((l: { id: string }) => l.id === id).words as { w: string; start: number }[];

describe('loom times', () => {
  test("are her lines L11–L14, word by word, and her strings are them", () => {
    expect(T.lines.map((l) => l.length)).toEqual([3, 4, 4, 6]);
    ['L11', 'L12', 'L13', 'L14'].forEach((id, i) => {
      expect(T.lines[i]!.map((w) => w.start)).toEqual(words(id).map((w) => w.start));
      expect(S[i]!.split(' ').length).toBe(words(id).length);
    });
    expect(T.tier).toEqual({ facts: words('L11')[0]!.start, incidents: words('L12')[0]!.start,
      rules: words('L13')[0]!.start, skills: words('L14')[0]!.start });
    expect(T.brk).toBe(words('L13')[3]!.start);
  });

  test('let the three expiring rows go evenly across "let go" (b05_loom.py Story.release)', () => {
    const [, , let_, go] = words('L12').map((w) => w.start);
    expect(T.release).toHaveLength(EXPIRE);
    expect(T.release[0]).toBe(let_!);
    expect(T.release[EXPIRE - 1]).toBeCloseTo(go!, 12);
    expect(T.release[1]! - T.release[0]!).toBeCloseTo(T.release[2]! - T.release[1]!, 12);
  });

  test('take the downbeats inside the window', () => {
    expect(T.downbeats.length).toBeGreaterThan(0);
    for (const d of T.downbeats) expect(d > scene.start && d < scene.end).toBe(true);
  });

  test('read the skills reach off the track: the first time the shuttle crosses the lane edge after "Skills"', () => {
    // a shuttle that flies 0..100 px and back each second, the edge at 80 px: until 3.5 s it turns back at 70
    const f0 = 30, n = 150;
    const shuttle: [number, number, number][] = [], reach: [number, number, number][] = [];
    for (let i = 0; i < n; i++) {
      const t = (f0 + i) / 30, ph = t % 2, x = ph < 1 ? ph * 100 : (2 - ph) * 100;
      shuttle.push([t < 3.5 ? Math.min(x, 70) : x, 500, 1]);
      reach.push([80, 500, 1]);
    }
    const track = new Track({ fps: 30, f0, anchors: { shuttle, reach } });
    const t = reachTime(track, 2.5);
    expect(t).toBeGreaterThan(3.5);
    expect(t).toBeCloseTo(4.8, 1); // turned back until 3.5 s; the next rise crosses 80 at 4.8 s
    expect(() => reachTime(track, 6.5)).toThrow();
  });
});

describe('loom type', () => {
  const at = 10;
  test('a tier word lights on its onset, never before, fully within 0.3 s', () => {
    expect(lightWipe(at - 0.05, at)).toBe(0);
    expect(lightWipe(at + 0.3, at)).toBe(1);
    expect(reveal(at - 0.05, at).a).toBe(0);
    expect(reveal(at + 0.2, at).a).toBe(1);
  });

  test('"Rules" pulls tight on its onset (wide before, 0 once settled) and rings only after "break"', () => {
    expect(rulesPull(at - 0.1, at, at + 1).track).toBeCloseTo(0.16, 6);
    expect(Math.abs(rulesPull(at + 0.6, at, at + 1).track)).toBeLessThan(0.002);
    expect(rulesPull(at + 0.99, at, at + 1).jolt).toBe(0);
    expect(Math.abs(rulesPull(at + 1.03, at, at + 1).jolt)).toBeGreaterThan(0.5);
  });

  test('"Incidents…" lets go in three waves with the rows, and is gone by a second after the last', () => {
    const rel = [20, 20.1, 20.2];
    for (let i = 0; i < 10; i++) {
      const g = letGo(19.9, i, 10, rel);
      expect(Math.abs(g.dy)).toBe(0);
      expect(g.a).toBe(1);
      expect(letGo(21.3, i, 10, rel).a).toBe(0);
    }
    // the first letters go with the first row, the last with the last
    expect(letGo(20.05, 0, 10, rel).dy).toBeLessThan(0);
    expect(Math.abs(letGo(20.05, 9, 10, rel).dy)).toBe(0);
  });

  test('a label draws on from its onset and the stamp lands on its', () => {
    expect(labelOn(at - 0.01, at, 18).typed).toBe(0);
    const on = labelOn(at + 1, at, 18);
    expect(on.dot).toBeCloseTo(1, 6);
    expect(on.leader).toBe(1);
    expect(on.typed).toBe(18);
    expect(stamp(at - 0.1, at).a).toBe(0);
    expect(stamp(at + 1, at).s).toBeCloseTo(1, 6);
    expect(stamp(at + 1, at).a).toBe(1);
  });

  test('the labels and the stamp are the spec\'s, in tier order', () => {
    expect(S.slice(4, 8)).toEqual(['facts/ · long-term', 'incidents/ · ttl 30d', 'rules/ · loaded whole', 'skills/ · lazy']);
    expect(TIERS.map((k, i) => S[4 + i]!.startsWith(`${k}/`))).toEqual([true, true, true, true]);
    expect(S[8]).toBe('gc: expire 3 incidents');
  });
});
