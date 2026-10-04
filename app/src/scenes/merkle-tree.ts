// The Merkle tree of scene `merkle`, as data: ten children a node, four levels under the root, so 10,000 leaves (10⁴)
// and 11,111 nodes. Pure TypeScript (no GPU), so bun tests it; merkle-gl.ts draws it.
//
// - Ids run level by level: the root is 0, its ten children 1–10, theirs 11–110, then 111–1110, and the leaves (the
//   files) 1111–11110. A node's children are consecutive, so a subtree's leaves are one run of ids.
// - The layout is a cone tree (Robertson's, from Xerox PARC): each node's children stand on a ring under it, and each
//   ring is small enough that no two subtrees touch, so the leaves on the floor are rosettes of rosettes. An unchanged
//   subtree is then a cone that can close like an umbrella and draw up into its node: "folds shut".
// - The changes are clustered as a commit's are, a few directories deep in a few places: fifty files under four of the
//   ten top-level directories. Every ancestor of a changed file changes (its hash covers theirs), so the lit tree is
//   the fifty paths from the root down. The walk that indexes it starts at the root and goes down only those paths: at
//   each lit node, every child whose hash did not move is a whole subtree skipped (a fold root), so the walk visits
//   the fifty files and no other.
// - Hashes are seven hex digits, the shape git abbreviates to (spec §11.10: the tree's values are illustrative).
import { hash, mulberry32 } from '../engine/util';

/** Children per node, and levels under the root. */
export const BRANCH = 10;
export const DEPTH = 4;
/** The first id of each level (and the node count, at DEPTH + 1). */
export const OFF: readonly number[] = Array.from({ length: DEPTH + 2 }, (_, k) => (BRANCH ** k - 1) / (BRANCH - 1));
export const N = OFF[DEPTH + 1]!;
export const LEAVES = BRANCH ** DEPTH;

export function levelOf(id: number): number {
  for (let k = DEPTH; k > 0; k--) if (id >= OFF[k]!) return k;
  return 0;
}
export function parentOf(id: number): number {
  const k = levelOf(id);
  return k === 0 ? -1 : OFF[k - 1]! + Math.floor((id - OFF[k]!) / BRANCH);
}
export function childOf(id: number, j: number): number {
  const k = levelOf(id);
  return OFF[k + 1]! + (id - OFF[k]!) * BRANCH + j;
}
/** Which child of its parent a node is (0..9). */
export const slotOf = (id: number) => (id - OFF[levelOf(id)]!) % BRANCH;
/** The path from the root down to `id`, both included. */
export function pathTo(id: number): number[] {
  const out = [id];
  for (let p = parentOf(id); p >= 0; p = parentOf(p)) out.push(p);
  return out.reverse();
}

// ------------------------------------------------------------------------------------------------ the layout

export interface Shape {
  /** Height of each level (m): the root first, the leaves (on the floor) last. */
  y: readonly number[];
  /** Radius of each level's ring about its parent (m); [0] (the root) is unused. */
  r: readonly number[];
  /** Turn of each level's ring (rad), added to the angle of the node it hangs from. */
  turn: readonly number[];
}

/**
 * The cone tree as built: a tabletop model a little over a metre across (the lens then gives the wide shot its depth
 * and the dive its macro). Each ring is small enough that the subtrees beside it never touch: a ring of radius r_k of
 * ten nodes spaced 2π·r_k/10 apart holds cones that reach r_{k+1} + r_{k+2} + … out from each node.
 */
export const SHAPE: Shape = {
  y: [0.6, 0.4, 0.2, 0.045, 0],
  r: [0, 0.4, 0.095, 0.022, 0.0052],
  turn: [0, Math.PI / BRANCH, 0, 0, 0],
};

/** How far a level's subtrees reach from their node (m), at the floor: its own ring and every ring below it. */
export const reach = (s: Shape, k: number) => s.r.slice(k + 1).reduce((a, b) => a + b, 0);

/** Rest positions (x, y, z per node) and each node's angle about its parent (rad). */
export function layout(s: Shape = SHAPE): { pos: Float32Array; ang: Float32Array } {
  const pos = new Float32Array(N * 3), ang = new Float32Array(N);
  pos[1] = s.y[0]!;
  for (let id = 1; id < N; id++) {
    const k = levelOf(id), p = parentOf(id);
    const a = ang[p]! + s.turn[k]! + (2 * Math.PI * slotOf(id)) / BRANCH;
    ang[id] = a;
    pos[id * 3] = pos[p * 3]! + s.r[k]! * Math.cos(a);
    pos[id * 3 + 1] = s.y[k]!;
    pos[id * 3 + 2] = pos[p * 3 + 2]! + s.r[k]! * Math.sin(a);
  }
  return { pos, ang };
}

// ------------------------------------------------------------------------------------------------ the change

/** The seed of the fifty changed files the scene shows. */
export const SEED = 1;

/**
 * How many children a node at each level spreads its changes over: the commit touches four of the ten top-level
 * directories, a few subdirectories in each, a few of theirs; the last level is the files themselves.
 */
const FAN = [4, 3.5, 2.6] as const;

/**
 * The changed files (leaf ids, ascending): `count` of them, clustered (FAN), seeded. Each lit node passes its share
 * on to a few of its children, at least one file each and never more than a child's subtree holds.
 */
export function pickChanged(seed: number, count = 50): number[] {
  const rnd = mulberry32(seed);
  const out: number[] = [];
  const spread = (id: number, n: number) => {
    const k = levelOf(id);
    if (k === DEPTH) {
      out.push(id);
      return;
    }
    const cap = BRANCH ** (DEPTH - k - 1); // leaves under one child
    const want = k === DEPTH - 1 ? n : Math.round(FAN[k]! * (0.75 + 0.5 * rnd()));
    const m = Math.max(Math.ceil(n / cap), Math.min(BRANCH, n, Math.max(1, want)));
    // m distinct children (a seeded shuffle)
    const kids = Array.from({ length: BRANCH }, (_, j) => j);
    for (let i = BRANCH - 1; i > 0; i--) {
      const j = Math.floor(rnd() * (i + 1));
      [kids[i], kids[j]] = [kids[j]!, kids[i]!];
    }
    const pick = kids.slice(0, m).sort((a, b) => a - b);
    // n split over them: one each, the rest by seeded weights, none past its cap
    const share = pick.map(() => 1);
    const w = pick.map(() => 0.35 + rnd());
    for (let left = n - m; left > 0; left--) {
      let best = -1, bw = -1;
      pick.forEach((_, i) => {
        if (share[i]! >= cap) return;
        const s = w[i]! / share[i]!;
        if (s > bw) (bw = s), (best = i);
      });
      share[best]!++;
    }
    pick.forEach((j, i) => spread(childOf(id, j), share[i]!));
  };
  spread(0, count);
  return out.sort((a, b) => a - b);
}

// ------------------------------------------------------------------------------------------------ hashes

const HEX = '0123456789abcdef';
/** The illustrative hash shape (facts.json): seven hex digits with a digit and a letter. */
export const HASH_RE = /^(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7}$/;

/** A node's hash, seven hex digits: `gen` 0 is the indexed tree's, 1 the hash a changed node has now. */
export function hashOf(id: number, gen: 0 | 1): string {
  for (let tries = 0; ; tries++) {
    let s = '';
    for (let i = 0; i < 7; i++) s += HEX[Math.floor(hash(id, gen, tries, i, 977) * 16)]!;
    if (HASH_RE.test(s)) return s;
  }
}

// ------------------------------------------------------------------------------------------------ the tree

export interface Tree {
  pos: Float32Array;
  ang: Float32Array;
  /** The changed files (leaf ids). */
  changed: number[];
  /** Per node: 1 if it changed (a changed file or an ancestor of one). */
  lit: Uint8Array;
  /**
   * Per node: the root of the skipped subtree it is in (itself if it is one), or -1 on a lit path. A skipped subtree
   * is an unchanged child of a lit node: the walk compares its hash and goes no further.
   */
  fold: Int32Array;
  /** The skipped subtrees' roots, by level (a level-4 one is a single unchanged file beside a changed one). */
  folds: number[][];
}

export function buildTree(changed: readonly number[], s: Shape = SHAPE): Tree {
  const { pos, ang } = layout(s);
  const lit = new Uint8Array(N);
  for (const leaf of changed) for (const id of pathTo(leaf)) lit[id] = 1;
  const fold = new Int32Array(N).fill(-1);
  const folds: number[][] = Array.from({ length: DEPTH + 1 }, () => []);
  // in id order a parent comes before its children, so a node's fold is known before theirs
  for (let id = 1; id < N; id++) {
    if (lit[id]) continue;
    const p = parentOf(id);
    if (lit[p]) {
      fold[id] = id;
      folds[levelOf(id)]!.push(id);
    } else fold[id] = fold[p]!;
  }
  return { pos, ang, changed: [...changed], lit, fold, folds };
}

/** The files the walk reads: the leaves it reaches, every one of them a changed file. */
export function visited(t: Tree): number[] {
  const out: number[] = [];
  for (let id = OFF[DEPTH]!; id < N; id++) if (t.lit[id]) out.push(id);
  return out;
}

/** The leaves under a node (ids, one run). */
export function leavesUnder(id: number): [first: number, count: number] {
  const k = levelOf(id), n = BRANCH ** (DEPTH - k);
  return [OFF[DEPTH]! + (id - OFF[k]!) * n, n];
}

/**
 * The file the camera dives to: a changed file alone among its ten (its rosette shows one lit and nine skipped) on the
 * path with the fewest lit siblings (the most folds beside the dive); the lowest id of those.
 */
export function diveLeaf(t: Tree): number {
  const litKids = (id: number) => new Set(t.changed.filter((leaf) => pathTo(leaf).includes(id)).map((leaf) => pathTo(leaf)[levelOf(id) + 1]!)).size;
  const crowd = (leaf: number) => pathTo(leaf).slice(1, DEPTH).reduce((a, id) => a + litKids(id), 0);
  const lone = t.changed.filter((leaf) => t.changed.filter((x) => parentOf(x) === parentOf(leaf)).length === 1);
  return lone.sort((a, b) => crowd(a) - crowd(b) || a - b)[0]!;
}
