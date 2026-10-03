// Transitions group A (Plan 3 Task 4): thread → ex, ex → her, her → repo, repo → loom. Each spec against the real
// voiceover (its scene windows and every word), and the match cut's anchors from B01's track.
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { transitionEntries, type TransitionSpec } from '../engine/transition';
import { VO } from '../engine/vo';
import { Track, type TrackData } from '../engine/track';
import { TITLE_SAFE, fibreSeeds } from '../scenes/ex-cloud';
import threadEx from './thread-ex';
import exHer from './ex-her';
import herRepo from './her-repo';
import repoLoom from './repo-loom';
import { exitError, fitLine, lineThrough, solve2 } from '../scenes/repo-exit';
import B05 from '../../../data/track/b05_loom.json';
import B01 from '../../../data/track/b01_thread.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const vo = new VO(JSON.parse(readFileSync(path.join(DATA, 'vo.json'), 'utf8')));
const GROUP: TransitionSpec[] = [threadEx, exHer, herRepo, repoLoom];
const scene = (id: string) => vo.scenes.find((s) => s.id === id)!;

describe('group A: the specs', () => {
  test('validate against the real voiceover, words included, together', () => {
    const es = transitionEntries(GROUP, vo.scenes, vo.words);
    expect(es.map((e) => e.id)).toEqual(GROUP.map((s) => `${s.from}-${s.to}`));
    for (const s of GROUP) expect(() => transitionEntries([s], vo.scenes, vo.words)).not.toThrow();
  });
  test('each cut is its scene boundary', () => {
    for (const e of transitionEntries(GROUP, vo.scenes, vo.words)) expect(e.cut).toBe(scene(e.spec.to).start);
  });
  test('ex → her is a hard cut; thread → ex and repo → loom are matches', () => {
    expect(exHer.kind).toBe('cut');
    expect(threadEx.kind).toBe('match');
    expect(repoLoom.kind).toBe('match');
  });
  test('the plates hold: the cold open past its last frame, loom before its first', () => {
    expect(threadEx.fromMode ?? 'hold').toBe('hold');
    expect(repoLoom.toMode ?? 'hold').toBe('hold');
  });
});

describe('her → repo: the whip', () => {
  test('the camera tilts up (the picture goes down), within a few degrees of the vertical', () => {
    const [dx, dy] = herRepo.dir!;
    expect(herRepo.kind).toBe('whip');
    expect(dy).toBeLessThan(-0.99);
    expect(Math.abs(dx)).toBeLessThan(0.1);
  });
  test('a whip of 60–120 ms each side of the cut, clear of "I\'m"', () => {
    expect(herRepo.pre).toBeGreaterThanOrEqual(0.06);
    expect(herRepo.pre).toBeLessThanOrEqual(0.12);
    expect(herRepo.post).toBeGreaterThanOrEqual(0.06);
    expect(herRepo.post).toBeLessThanOrEqual(0.12);
  });
});

describe('thread → ex: the fibres', () => {
  const track = new Track(B01 as unknown as TrackData);
  const cut = scene('ex').start;
  const F = Math.ceil(cut * 30);
  const fibres = track.names().filter((n) => /^fibre_\d+$/.test(n));

  test('B01 tracks twelve freed fibres', () => expect(fibres.length).toBe(12));
  test('every fibre is visible on the last frame before the cut, inside title-safe', () => {
    for (const n of fibres) {
      const a = track.at(n, (F - 1) / 30);
      expect(a.visible).toBe(1);
      expect(a.x).toBeGreaterThanOrEqual(TITLE_SAFE.x0);
      expect(a.x).toBeLessThanOrEqual(TITLE_SAFE.x1);
      expect(a.y).toBeGreaterThanOrEqual(TITLE_SAFE.y0);
      expect(a.y).toBeLessThanOrEqual(TITLE_SAFE.y1);
    }
  });
  test('ex seeds at least six numerals, each within 2 px of a tracked fibre at the cut', () => {
    const seeds = fibreSeeds(track, cut);
    expect(seeds.length).toBeGreaterThanOrEqual(6);
    const at = fibres.map((n) => track.at(n, cut));
    for (const s of seeds) expect(Math.min(...at.map((a) => Math.hypot(a.x - s.x, a.y - s.y)))).toBeLessThanOrEqual(2);
  });
  test('the seeds are a function of the track and the cut', () => {
    expect(fibreSeeds(track, cut)).toEqual(fibreSeeds(new Track(B01 as unknown as TrackData), cut));
  });
});

describe('repo → loom: the string lands on the fell', () => {
  const loom = new Track(B05 as unknown as TrackData);
  const F = Math.ceil(scene('loom').start * 30);
  test('loom starts on its track: the fell is tracked from its first frame, its left end in frame', () => {
    expect(loom.f0).toBe(F);
    const l = loom.at('fell_l', F / 30);
    expect(l.visible).toBe(1);
    expect(l.x).toBeGreaterThan(0);
    expect(l.x).toBeLessThan(1920);
  });
  test('a line fits its points; a line through two points', () => {
    const L = fitLine([0, 400, 800, 1200].map((x) => ({ x, y: 600 - 0.08 * x })));
    expect(L.angle).toBeCloseTo(Math.atan(-0.08), 12);
    expect(L.at(1000)).toBeCloseTo(520, 9);
    const T = lineThrough({ x: 558, y: 588 }, { x: 2943, y: 402 });
    expect(T.at(558)).toBeCloseTo(588, 9);
    expect(T.at(2943)).toBeCloseTo(402, 9);
    expect(() => fitLine([{ x: 1, y: 1 }])).toThrow(/1 point/);
  });
  test('the exit solve turns and tilts a projected string onto the fell', () => {
    // a stand-in camera: roll r (deg) turns the string about the frame's centre, tilt v (m) shifts it 900 px per m
    const fell = lineThrough(loom.at('fell_l', F / 30), loom.at('fell_r', F / 30));
    const project = ([r, v]: [number, number]) => {
      const a = ((r - 1.3) * Math.PI) / 180, pts = [];
      for (let x = 0; x <= 1920; x += 40) {
        const y0 = 520 - 0.05 * x, dx = x - 960, dy = y0 - 540;
        pts.push({ x: 960 + dx * Math.cos(a) - dy * Math.sin(a), y: 540 + dx * Math.sin(a) + dy * Math.cos(a) + 900 * (v - 0.04) });
      }
      return fitLine(pts);
    };
    const p = solve2((q) => exitError(project(q), fell, 1240), [0, 0], [0.05, 0.0005], [1e-4, 0.5]);
    const [da, dy] = exitError(project(p), fell, 1240);
    expect(Math.abs(da)).toBeLessThan(1e-4);
    expect(Math.abs(dy)).toBeLessThan(0.5);
  });
  test('the match stays clear of "Facts": post under the word limit', () => {
    const [e] = transitionEntries([repoLoom], vo.scenes, vo.words);
    const next = vo.words.find((w) => w.start >= e!.cut)!;
    expect(e!.end + 1 / 30).toBeLessThanOrEqual(next.start);
  });
});
