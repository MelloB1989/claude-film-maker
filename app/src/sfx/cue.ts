// The cue sheet's vocabulary (Plan 3 Task 8): a cue is one sound placed on one moment of the film, and every moment is
// an anchor in the data: a word's onset, a beat, a downbeat, a tracked Blender event, a scene's own event (its time
// module), or a transition's cut. A scene's cue module (sfx/scenes/<id>.ts) is a pure function of the voiceover, the
// score's grid, the tracks and the transitions; nothing in it is a hard-coded second.
//
// Anchors, as the sheet records them:
//   word:<line>:<i>    the onset of word i (0-based) of line <line> (t is exactly its start)
//   beat:<n>           audio.beats[n];  downbeat:<n>  audio.downbeats[n]
//   cut:<from>-<to>    a transition's cut (the scene boundary)
//   <scene>:<event>    a scene's own moment, from its time module (plus an offset in frames: `thread:snap+2f`)
//   <prefix>:key:<i>   the i-th key of a typed line (typing())
import type { AudioData } from '../engine/audio';
import type { Track } from '../engine/track';
import type { TransitionEntry } from '../engine/transition';
import { hash } from '../engine/util';
import { norm, type SceneSpan, type VO } from '../engine/vo';

/** One sound on one moment: its hit (onset, peak or end, as the palette aligns it) lands on t. */
export interface Cue {
  /** A palette sound id, or one of a sliced sound's slices (`flap_3`, `key_soft_7`). */
  sound: string;
  t: number;
  anchor: string;
  /** dB added to the palette's gain. */
  gain?: number;
  /** −1 (left) … 1 (right); 0 when left out. */
  pan?: number;
  /** Beds and loops only: how long it plays from t (s). */
  dur?: number;
}

/**
 * A duck: a bus held `depth` dB down from t to t + dur, fading into it over `fade` s before t and out of it over `fade`
 * s after t + dur (so it is at full depth for the whole of [t, t + dur]). `music` ducks the score; `all` the score and
 * the effects (never the voice).
 */
export interface Duck {
  kind: 'duck';
  t: number;
  dur: number;
  depth: number;
  fade: number;
  bus: 'music' | 'all';
  anchor: string;
}

export interface CueCtx {
  vo: VO;
  audio: AudioData;
  /** The scene the module places sounds for (its window in vo.json). */
  scene: SceneSpan;
  track: (shot: string) => Track;
  transitions: TransitionEntry[];
}

export type SceneCues = (c: CueCtx) => (Cue | Duck)[];

/** A moment: its time and its anchor. */
export interface At {
  t: number;
  anchor: string;
}

/**
 * Word `w` (compared normalised: case and punctuation aside) of line `line` (`L07`), its `nth` occurrence there. Throws
 * when the line has no such word, so a cue whose word was edited away fails loudly rather than vanishing.
 */
export function word(c: CueCtx, line: string, w: string, nth = 0): At {
  const l = c.vo.lines.find((x) => x.id === line);
  const q = norm(w);
  const hits = l ? l.words.filter((x) => norm(x.w) === q) : [];
  const hit = hits[nth];
  if (!l || !hit) throw new Error(`cue: no word "${w}" in ${line}${nth ? ` (#${nth})` : ''}`);
  return { t: hit.start, anchor: `word:${line}:${hit.index}` };
}

/** The beats in [a, b), each anchored to its index in the grid. */
export function beatsIn(c: CueCtx, a: number, b: number): At[] {
  const out: At[] = [];
  c.audio.beats.forEach((t, i) => {
    if (t >= a && t < b) out.push({ t, anchor: `beat:${i}` });
  });
  return out;
}

/** A time that is a beat of the grid (a time module's beat), anchored to its index; throws if it is not on the grid. */
export function onBeat(c: CueCtx, t: number): At {
  const i = c.audio.beats.findIndex((b) => Math.abs(b - t) < 1e-9);
  if (i < 0) throw new Error(`cue: ${t} is not a beat`);
  return { t: c.audio.beats[i]!, anchor: `beat:${i}` };
}

/** A time that is a downbeat of the grid, anchored to its index; throws if it is not one. */
export function onDownbeat(c: CueCtx, t: number): At {
  const i = c.audio.downbeats.findIndex((b) => Math.abs(b - t) < 1e-9);
  if (i < 0) throw new Error(`cue: ${t} is not a downbeat`);
  return { t: c.audio.downbeats[i]!, anchor: `downbeat:${i}` };
}

/** A scene's own moment (from its time module), named `<scene>:<event>`. */
export const event = (c: CueCtx, name: string, t: number): At => ({ t, anchor: `${c.scene.id}:${name}` });

/** A cue for `sound` on a moment, with its options. */
export const cue = (sound: string, at: At, o: Omit<Cue, 'sound' | 't' | 'anchor'> = {}): Cue => ({ sound, t: at.t, anchor: at.anchor, ...o });

/** The palette's soft keys, one a keystroke. */
export const KEYS = 8;

/**
 * One soft key a newly shown character: scans the frame times n/30 from `from` to the first at or after `to` and, where a frame shows k characters
 * more than the frame before it, places k keys spread evenly inside that frame (1/(30k) apart, the first on the frame).
 * The key sound (key_soft_1…8), a gain jitter of ±1.5 dB and a pan of ±0.15 are seeded by (seed, key index), so the
 * typing is humanised but the same every run. A frame's k keys are each 10·log10(k) dB softer, so they sum to one
 * key's energy: a burst typed at 100 characters a second patters at the level of one typed at 30, rather than roaring.
 */
export function typing(prefix: string, count: (t: number) => number, from: number, to: number, seed: string): Cue[] {
  const s = seedOf(seed);
  // to the first frame at or after `to`: a line whose last key is due between two frames shows it on the later one
  const f0 = Math.ceil(from * 30 - 1e-6), f1 = Math.ceil(to * 30 - 1e-6);
  const out: Cue[] = [];
  let shown = count((f0 - 1) / 30), i = 0;
  for (let f = f0; f <= f1; f++) {
    const now = count(f / 30), k = now - shown;
    for (let j = 0; j < k; j++, i++) {
      out.push({
        sound: `key_soft_${1 + Math.floor(hash(s, i, 1) * KEYS)}`,
        t: (f + j / k) / 30,
        anchor: `${prefix}:key:${i}`,
        gain: Math.round(((hash(s, i, 2) * 2 - 1) * 1.5 - 10 * Math.log10(k)) * 100) / 100,
        pan: Math.round((hash(s, i, 3) * 2 - 1) * 0.15 * 1000) / 1000,
      });
    }
    if (now > shown) shown = now;
  }
  return out;
}

/** A string seed as a number for hash(). */
function seedOf(s: string): number {
  let h = 0;
  for (const ch of s) h = (Math.imul(h, 31) + ch.codePointAt(0)!) | 0;
  return (h >>> 0) % 1000003;
}

/** A sliced sound's slice, picked by hash: `flap_1` … `flap_<n>`. */
export const slice = (base: string, n: number, ...seed: number[]) => `${base}_${1 + Math.floor(hash(...seed) * n)}`;
