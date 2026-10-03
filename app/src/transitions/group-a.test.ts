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
import B01 from '../../../data/track/b01_thread.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const vo = new VO(JSON.parse(readFileSync(path.join(DATA, 'vo.json'), 'utf8')));
const GROUP: TransitionSpec[] = [threadEx, exHer];
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
  test('ex → her is a hard cut; thread → ex is a match', () => {
    expect(exHer.kind).toBe('cut');
    expect(threadEx.kind).toBe('match');
  });
  test('the cold open is a plate: it holds (never runs past its last frame)', () => {
    expect(threadEx.fromMode ?? 'hold').toBe('hold');
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
