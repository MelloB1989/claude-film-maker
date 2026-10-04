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

/** A frame-to-frame move of the labels (px a frame, averaged over the four) fast enough to be one of the tour's snaps. */
const SNAP_PX = 40;

/**
 * The way the camera travelled on the tour's last snap (a unit vector, logical px axes, +y down): the tracked labels'
 * mean frame-to-frame move over the frames of the last snap, reversed (the picture moves the other way). loom → diff
 * whips on in that direction. Throws if the track has no snap.
 */
export function lastSnapDir(track: Track): [number, number] {
  const fps = 30, at = (k: string, f: number) => track.at(`lbl_${k}`, f / fps);
  const step = (f: number) => {
    let dx = 0, dy = 0;
    for (const k of TIERS) {
      const a = at(k, f - 1), b = at(k, f);
      dx += (b.x - a.x) / TIERS.length;
      dy += (b.y - a.y) / TIERS.length;
    }
    return { dx, dy };
  };
  let sx = 0, sy = 0, inSnap = false;
  for (let f = track.f0 + track.frames - 1; f > track.f0; f--) {
    const s = step(f), fast = Math.hypot(s.dx, s.dy) > SNAP_PX;
    if (fast) (sx += s.dx), (sy += s.dy), (inSnap = true);
    else if (inSnap) break;
  }
  const d = Math.hypot(sx, sy);
  if (!(d > 0)) throw new Error('loom: the tracked labels never snap');
  return [-sx / d, -sy / d];
}

/** A frame-to-frame move of the shuttle along its race (px) fast enough to be a pass in flight. */
const FLY_PX = 40;
/** A landing: the box checks the shuttle to under this share of its speed from one frame to the next. */
const CHECK = 0.2;

/** A pass of the shuttle, as the plate shows it (film times): when it leaves its box and when it lands in the other. */
export interface Pass {
  /** Its last still frame before it flies (null when it was already flying on the plate's first frame). */
  depart: number | null;
  land: number;
  /** Which way it flew: +1 to the right of the frame, −1 to the left. */
  dir: 1 | -1;
}

/**
 * The tracked shuttle's passes (film times, frame times): it lands where it is flying (its x along the race, taken from
 * the tracked lane edge `reach` on the same race so the camera's moves cancel, changing fast) and on the next frame has
 * all but stopped, and the pass after it flies back the other way (its x velocity changes sign). It departs on the frame
 * after the last one it is still on. The plate lands one on every beat (b05_loom.py WeaveClock); a landing on the
 * plate's last frame has no next frame to see it stop by, so it is not found.
 */
export function shuttlePasses(track: Track): Pass[] {
  const fps = 30, f0 = track.f0, n = track.frames;
  const x = (f: number) => track.at('shuttle', f / fps).x - track.at('reach', f / fps).x;
  const v = (f: number) => x(f) - x(f - 1);
  const out: Pass[] = [];
  for (let f = f0 + 1; f < f0 + n - 1; f++) {
    const a = v(f), b = v(f + 1);
    if (!(Math.abs(a) > FLY_PX && Math.abs(b) < CHECK * Math.abs(a))) continue;
    // the next pass, if the plate has one, flies back (moving at half this landing's speed or more: off frame, where the
    // projection stretches the race, the box's recoil alone can cross FLY_PX)
    const fast = Math.max(FLY_PX, CHECK * Math.abs(a));
    for (let g = f + 2; g < f0 + n; g++) {
      const w = v(g);
      if (Math.abs(w) > 0.5 * Math.abs(a)) {
        if (Math.sign(w) === Math.sign(a)) throw new Error(`loom: the shuttle lands at frame ${f} and flies on the same way`);
        break;
      }
    }
    // where this pass set out: the frame before its run of flying frames
    let g = f;
    while (g > f0 + 1 && Math.abs(v(g - 1)) > fast) g--;
    out.push({ depart: g > f0 + 1 ? (g - 1) / fps : null, land: f / fps, dir: a > 0 ? 1 : -1 });
  }
  return out;
}
