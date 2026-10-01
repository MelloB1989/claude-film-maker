// The times scene `loom` keys on, every one from the data: her four lines (L11–L14) word by word, the incidents' three
// rows letting go across "let go", "break", the downbeats, and the moment the shuttle first flies into the skills lane.
// That last one is the plate's own: blender/shots/b05_loom.py decides when the shuttle reaches skills (the first
// left-to-right pass that lands after she names them), and tracks the shuttle and the lane's edge (`shuttle`, `reach`,
// both on the race, so their order on screen is their order along it); the scene reads the crossing from the track,
// so the word and the warps light on the same frame.
import type { AudioData } from '../engine/audio';
import type { Track } from '../engine/track';
import { norm, type VO, type Word } from '../engine/vo';

export const TIERS = ['facts', 'incidents', 'rules', 'skills'] as const;
export type Tier = (typeof TIERS)[number];

/** Rows that expire on "let go" (b05_loom.py EXPIRE). */
export const EXPIRE = 3;

export interface LoomTimes {
  start: number;
  end: number;
  /** L11–L14, each its words with their onsets. */
  lines: Word[][];
  /** Each tier word's onset ("Facts", "Incidents…", "Rules", "Skills,"). */
  tier: Record<Tier, number>;
  /** The three expiring rows let go evenly across "let go" (b05_loom.py Story.release). */
  release: number[];
  brk: number;
  /** The downbeats inside the window. */
  downbeats: number[];
}

export function loomTimes(vo: VO, audio: AudioData, start: number, end: number): LoomTimes {
  const lines = vo.lines.filter((l) => l.scene === 'loom').map((l) => l.words);
  if (lines.length !== 4) throw new Error(`loom: expected L11–L14, found ${lines.length} lines`);
  const word = (li: number, w: string) => {
    const hit = lines[li]!.find((x) => norm(x.w) === w);
    if (!hit) throw new Error(`loom: no spoken "${w}" in line ${li + 1}`);
    return hit.start;
  };
  const tier = { facts: word(0, 'facts'), incidents: word(1, 'incidents'), rules: word(2, 'rules'), skills: word(3, 'skills') };
  const let_ = word(1, 'let'), go = word(1, 'go');
  return {
    start, end, lines, tier,
    release: Array.from({ length: EXPIRE }, (_, i) => let_ + ((go - let_) * i) / (EXPIRE - 1)),
    brk: word(2, 'break'),
    downbeats: audio.downbeats.filter((d) => d > start && d < end),
  };
}

/**
 * When the shuttle first crosses into the skills lane after `after` (song seconds): the first frame where the tracked
 * shuttle's x reaches the tracked lane edge's, interpolated between the frames either side. Throws if it never does.
 */
export function reachTime(track: Track, after: number): number {
  const fps = 30;
  const f0 = Math.max(track.f0, Math.ceil(after * fps));
  const gap = (f: number) => track.at('shuttle', f / fps).x - track.at('reach', f / fps).x;
  for (let f = f0 + 1; f < track.f0 + track.frames; f++) {
    const a = gap(f - 1), b = gap(f);
    if (a < 0 && b >= 0) return (f - 1 + a / (a - b)) / fps;
  }
  throw new Error('loom: the tracked shuttle never reaches the skills lane');
}
