// The clock of `merkle`: every time the scene keys on, from the data (her measured onsets, the score's beats and
// downbeats). Nothing here is a hard-coded second.
//
// "Fifty things changed? I only look at fifty."
// - The cut lands on a beat, on the whole tree from the crane.
// - "changed?": the fifty files pulse moss, and the moss climbs their paths, reaching the root on the next downbeat
//   (every hash above a changed file changes).
// - "I only look at fifty.": the walk goes down the lit paths one level a word: the root on "I", the top-level
//   directories on "only", the next on "look", the last on "at", the fifty files on "fifty." At each level the
//   subtrees whose hash did not move fold shut beside it. The camera dives with it, and the counter lands on "fifty."
import { wordTimes } from '../engine/motion';
import { norm, type VO, type Word } from '../engine/vo';
import type { AudioData } from '../engine/audio';
import { hash } from '../engine/util';
import { DEPTH, N, levelOf, type Tree } from './merkle-tree';

/** A time that never comes (s). */
export const NEVER = 1e6;
/** How long a skipped subtree takes to fold shut (s), and when in that its stamp hits (share). */
export const FOLD_S = 0.42;
export const STAMP_AT = 0.5;

export function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'merkle').map((x) => x.w);
  const word = (w: string, nth = 0): Word => {
    const h = ws.filter((x) => norm(x.w) === w)[nth];
    if (!h) throw new Error(`merkle: no spoken "${w}" (#${nth})`);
    return h;
  };
  const beat = 60 / audio.bpm;
  const changed = word('changed');
  // the moss reaches the root on the first downbeat after "changed?" begins
  const root = audio.downbeats.find((d) => d > changed.start + 1e-6);
  if (root === undefined || root >= end) throw new Error('merkle: no downbeat after "changed?" in the window');
  // the walk: one level a word, the root on "I" and the files on the second "fifty"
  const walk = [word('i'), word('only'), word('look'), word('at'), word('fifty', 1)].map((w) => w.start);
  if (!(walk[0]! > root)) throw new Error('merkle: the walk must start after the moss reaches the root');
  return {
    start, end, beat,
    fifty: word('fifty').start, things: word('things').start, changed: changed.start, changedEnd: changed.end,
    /** The moss reaches the root (a downbeat). */
    root,
    /** When the walk reaches each level (0 the root … 4 the files). */
    walk,
    /** The walk lands on the fifty files ("fifty."), and the counter with it. */
    land: walk[4]!,
    landEnd: word('fifty', 1).end,
    /** The beats in the window. */
    beats: audio.beats.filter((b) => b >= start - 1e-6 && b < end),
  };
}
export type Times = ReturnType<typeof timesOf>;

/** Per-node times the shaders read (scene time: s from the scene's start). */
export interface TreeTimes {
  /** When the moss reaches a node (lit nodes; NEVER otherwise). */
  moss: Float32Array;
  /** When the walk reaches a node (lit nodes; NEVER otherwise). */
  walk: Float32Array;
  /** When each skipped subtree starts to fold, by its root (NEVER where a node roots none). */
  fold: Float32Array;
}

/**
 * Every node's times. The moss climbs every changed file's path from "changed?" to the root on the downbeat, level by
 * level, the files themselves a few frames apart (they pulse as a scatter, not a flash); the walk reaches level k on
 * its word; each skipped subtree starts to fold as the walk reaches its parent, the siblings a few frames apart.
 */
export function nodeTimes(tree: Tree, T: Times): TreeTimes {
  const s = T.start, moss = new Float32Array(N).fill(NEVER), walk = new Float32Array(N).fill(NEVER), fold = new Float32Array(N).fill(NEVER);
  const climb = [1, 0.82, 0.6, 0.35, 0].map((x) => T.changed + (T.root - T.changed) * x - s);
  for (let id = 0; id < N; id++) {
    const k = levelOf(id);
    if (tree.lit[id]) {
      moss[id] = climb[k]! + (k === DEPTH ? 0.05 * hash(id, 3) : 0);
      walk[id] = T.walk[k]! - s;
    }
    if (tree.fold[id] === id) fold[id] = T.walk[k - 1]! - s + 0.06 * hash(id, 5);
  }
  return { moss, walk, fold };
}
