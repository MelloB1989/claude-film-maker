// Scene `merkle`: its times against the film's own voiceover and beat grid (merkle-time.ts), the tree as a Merkle tree
// of 10,000 files whose walk visits the fifty changed ones and no other (merkle-tree.ts), the cone tree's rings never
// touching, the hashes as the facts sheet's illustrative shape, and the copy and the counter's layout.
import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import * as opentype from 'opentype.js';
import { VO, norm } from '../engine/vo';
import { AudioData } from '../engine/audio';
import { FOLD_S, NEVER, STAMP_AT, nodeTimes, timesOf } from './merkle-time';
import {
  BRANCH, DEPTH, HASH_RE, LEAVES, N, OFF, SEED, SHAPE, buildTree, childOf, diveLeaf, hashOf, layout, leavesUnder, levelOf,
  parentOf, pathTo, pickChanged, reach, visited,
} from './merkle-tree';
import S from './merkle.strings.json';

const DATA = path.resolve(import.meta.dir, '../../../data');
const FONTS = path.resolve(import.meta.dir, '../../public/fonts');
const json = (f: string) => JSON.parse(readFileSync(path.join(DATA, f), 'utf8'));
const vo = new VO(json('vo.json'));
const audio = new AudioData(json('audio.json'));
const span = vo.scenes.find((s) => s.id === 'merkle')!;
const T = timesOf(vo, audio, span.start, span.end);
const words = vo.lines.filter((l) => l.scene === 'merkle').flatMap((l) => l.words);
const onGrid = (t: number, grid: number[]) => grid.some((b) => Math.abs(b - t) < 1e-9);
const tree = buildTree(pickChanged(SEED));
const times = nodeTimes(tree, T);
const COPY = S as string[];

describe('merkle: its times come from the data', () => {
  test('the moss reaches the root on the first downbeat after "changed?" begins', () => {
    const changed = words.find((w) => norm(w.w) === 'changed')!;
    expect(T.changed).toBe(changed.start);
    expect(onGrid(T.root, audio.downbeats)).toBe(true);
    expect(T.root).toBeGreaterThan(changed.start);
    expect(audio.downbeats.filter((d) => d > changed.start && d < T.root)).toHaveLength(0);
  });

  test('the walk goes one level a word, "I only look at fifty.", and lands on the second "fifty"', () => {
    const later = words.slice(words.findIndex((w) => norm(w.w) === 'i'));
    expect(later.map((w) => norm(w.w))).toEqual(['i', 'only', 'look', 'at', 'fifty']);
    expect(T.walk).toEqual(later.map((w) => w.start));
    expect(T.land).toBe(later[4]!.start);
    for (let k = 1; k <= DEPTH; k++) expect(T.walk[k]!).toBeGreaterThan(T.walk[k - 1]!);
    expect(T.walk[0]!).toBeGreaterThan(T.root);
  });

  test('every key time is inside the window, the landing with time to read it before the cut', () => {
    for (const t of [T.fifty, T.things, T.changed, T.root, ...T.walk]) {
      expect(t).toBeGreaterThan(span.start);
      expect(t).toBeLessThan(span.end);
    }
    expect(span.end - T.land).toBeGreaterThan(0.4);
    expect(onGrid(span.start, audio.beats)).toBe(true); // the cut lands on a beat
  });
});

describe('merkle: a Merkle tree of 10,000 files', () => {
  test('ten children a node, four levels: 10,000 leaves and 11,111 nodes, ids level by level', () => {
    expect(LEAVES).toBe(10000);
    expect(N).toBe(11111);
    expect(OFF).toEqual([0, 1, 11, 111, 1111, 11111]);
    for (const id of [0, 1, 7, 10, 11, 110, 111, 1110, 1111, 11110]) {
      const k = levelOf(id);
      expect(id).toBeGreaterThanOrEqual(OFF[k]!);
      expect(id).toBeLessThan(OFF[k + 1]!);
      if (k < DEPTH) for (let j = 0; j < BRANCH; j++) expect(parentOf(childOf(id, j))).toBe(id);
    }
    expect(leavesUnder(3)).toEqual([1111 + 2000, 1000]);
  });

  test('fifty changed files, clustered under four of the ten top-level directories, seeded', () => {
    expect(tree.changed).toHaveLength(50);
    expect(new Set(tree.changed).size).toBe(50);
    for (const leaf of tree.changed) expect(levelOf(leaf)).toBe(DEPTH);
    expect(pickChanged(SEED)).toEqual(tree.changed);
    const top = new Set(tree.changed.map((l) => pathTo(l)[1]));
    expect(top.size).toBe(4);
  });

  test('the lit nodes are the changed files and every ancestor of one (a hash covers its children\'s)', () => {
    for (let id = 0; id < N; id++) {
      const want = tree.changed.some((leaf) => pathTo(leaf).includes(id));
      expect(tree.lit[id]).toBe(want ? 1 : 0);
    }
  });

  test('the walk visits the fifty changed files and no other: every other file sits in exactly one skipped subtree', () => {
    expect(visited(tree)).toEqual(tree.changed);
    for (let leaf = OFF[DEPTH]!; leaf < N; leaf++) {
      if (tree.lit[leaf]) {
        expect(tree.fold[leaf]).toBe(-1);
        continue;
      }
      const roots = pathTo(leaf).filter((id) => tree.fold[id] === id);
      expect(roots).toHaveLength(1);
      expect(tree.fold[leaf]).toBe(roots[0]!);
    }
    // a skipped subtree is an unchanged child of a changed node, listed by its level
    tree.folds.forEach((ids, k) => {
      for (const id of ids) {
        expect(levelOf(id)).toBe(k);
        expect(tree.lit[id]).toBe(0);
        expect(tree.lit[parentOf(id)]).toBe(1);
      }
    });
    const skipped = tree.folds.flat().reduce((a, id) => a + leavesUnder(id)[1], 0);
    expect(skipped + 50).toBe(LEAVES);
  });

  test('the cone tree: every ring holds its subtrees apart, so no two cones touch', () => {
    for (let k = 1; k < DEPTH; k++) {
      const gap = 2 * SHAPE.r[k]! * Math.sin(Math.PI / BRANCH); // between neighbours on a ring
      expect(2 * reach(SHAPE, k)).toBeLessThan(gap);
    }
    const { pos } = layout();
    for (let id = 1; id < N; id++) {
      const k = levelOf(id), p = parentOf(id);
      expect(pos[id * 3 + 1]).toBeCloseTo(SHAPE.y[k]!, 6);
      expect(Math.hypot(pos[id * 3]! - pos[p * 3]!, pos[id * 3 + 2]! - pos[p * 3 + 2]!)).toBeCloseTo(SHAPE.r[k]!, 5);
    }
  });

  test('the dive goes to a changed file alone among its ten', () => {
    const leaf = diveLeaf(tree);
    expect(tree.changed).toContain(leaf);
    expect(tree.changed.filter((x) => parentOf(x) === parentOf(leaf))).toEqual([leaf]);
  });
});

describe('merkle: the moss climbs, the walk descends, the folds follow it', () => {
  const s = T.start;
  test('the moss climbs every lit path from the file up, reaching the root on the downbeat', () => {
    expect(times.moss[0]! + s).toBeCloseTo(T.root, 4); // (the shaders' float32)
    for (let id = 1; id < N; id++) {
      if (!tree.lit[id]) {
        expect(times.moss[id]).toBe(NEVER);
        continue;
      }
      expect(times.moss[id]!).toBeLessThan(times.moss[parentOf(id)]!);
      expect(times.moss[id]! + s).toBeGreaterThanOrEqual(T.changed - 1e-6);
    }
  });

  test('the walk reaches a level on its word; a skipped subtree folds as the walk reaches its parent, and is shut before the cut', () => {
    for (let id = 0; id < N; id++) {
      if (tree.lit[id]) expect(times.walk[id]! + s).toBeCloseTo(T.walk[levelOf(id)]!, 4);
      if (tree.fold[id] === id) {
        const reached = times.walk[parentOf(id)]!;
        expect(times.fold[id]!).toBeGreaterThanOrEqual(reached - 1e-6);
        expect(times.fold[id]! - reached).toBeLessThan(0.07);
        expect(times.fold[id]! + FOLD_S * STAMP_AT + s).toBeLessThan(span.end);
      } else expect(times.fold[id]).toBe(NEVER);
    }
    // the top-level folds are shut as she says "look"; the last stamps hit before "fifty."
    const shut = Math.max(...tree.folds[1]!.map((id) => times.fold[id]!)) + FOLD_S + s;
    expect(shut).toBeLessThan(T.walk[2]! + 0.1);
    const lastStamp = Math.max(...tree.folds.slice(1, DEPTH).flat().map((id) => times.fold[id]!)) + FOLD_S * STAMP_AT + s;
    expect(lastStamp).toBeLessThan(T.land);
  });
});

describe('merkle: hashes and copy', () => {
  test('every hash on screen is seven hex digits with a digit and a letter (the sheet\'s illustrative shape), and a change changes it', () => {
    for (let id = 0; id < N; id++) {
      if (levelOf(id) === DEPTH && !tree.lit[id]) continue;
      expect(hashOf(id, 0)).toMatch(HASH_RE);
      if (tree.lit[id]) {
        expect(hashOf(id, 1)).toMatch(HASH_RE);
        expect(hashOf(id, 1)).not.toBe(hashOf(id, 0));
      }
    }
  });

  test('the strings file holds the stamp, the counter, the footnote and the hashes the dive reads large', () => {
    expect(COPY.slice(0, 3)).toEqual(['= hash · skipped', 'visited 50 of 10,000', 'index is a pure cache · gitloom rebuild']);
    const path_ = pathTo(diveLeaf(tree));
    expect(COPY.slice(3)).toEqual([hashOf(0, 0), hashOf(0, 1), hashOf(path_[1]!, 0), ...path_.slice(1).map((id) => hashOf(id, 1))]);
  });

  test('the counter says what the tree does: fifty visited of its 10,000 files', () => {
    const m = /^visited (\d+) of ([\d,]+)$/.exec(COPY[1]!)!;
    expect(Number(m[1])).toBe(visited(tree).length);
    expect(Number(m[2]!.replace(/,/g, ''))).toBe(LEAVES);
  });

  test('the counter and its footnote sit inside the title-safe area', () => {
    const font = (f: string) => {
      const b = readFileSync(path.join(FONTS, f));
      return opentype.parse(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer);
    };
    const brico = font('Bricolage-w1000-800.ttf');
    // (advances summed glyph by glyph: opentype.js cannot run this face's contextual substitutions)
    const adv = (f: opentype.Font, s: string, px: number) => Array.from(s).reduce((w, c) => w + (f.charToGlyph(c).advanceWidth! / f.unitsPerEm) * px, 0);
    // (JetBrains Mono advances every character 0.6 em)
    const mono = (s: string, px: number) => Array.from(s).length * 0.6 * px;
    const x0 = 150, size = 34, hero = 168;
    const end = x0 + mono('visited', size) + 2 * 1.1 * mono(' ', size) + adv(brico, '50', hero) + mono('of 10,000', size);
    expect(x0).toBeGreaterThanOrEqual(96);
    expect(end).toBeLessThan(1920 - 96);
    expect(x0 + mono(COPY[2]!, 23)).toBeLessThan(1920 - 96);
    expect(966 + 0.25 * 23).toBeLessThanOrEqual(1080 - 96); // the footnote's descenders inside the safe line
  });
});
