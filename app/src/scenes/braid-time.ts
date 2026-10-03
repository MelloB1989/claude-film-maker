// The times and the shared camera of scene `braid`, every one from the data. Blender's B08 (blender/shots/b08_braid.py)
// and this scene read one world, data/look/b08_braid.json: the thread's radius, P0 where the arms meet, the plait's axis
// and length, the card's hinge (where the plait's head lands) and facing, and the camera's keys, each at a cue from
// her words (L19) and the scene's window. B08 renders through its Python port of the engine's CameraRig, so the card
// this scene hangs on the hinge sits on the plate's rope with nothing to match by eye (braid.test.ts holds the tracked
// hinge to the engine's projection of it).
import type { AudioData } from '../engine/audio';
import type { CamKey, V3 } from '../engine/stage';
import { clamp, ease } from '../engine/util';
import { norm, type VO, type Word } from '../engine/vo';
import SPEC from '../../../data/look/b08_braid.json';

export const SHOT = 'b08_braid';
export const WORLD = SPEC;
export const ARMS = ['lexical', 'body', 'cues'] as const;
export type Arm = (typeof ARMS)[number];

/** Each arm's phrase in her line: the words its label lights as she says them. */
export const PHRASE: Record<Arm, readonly string[]> = { lexical: ['your', 'words'], body: ['what', 'you', 'meant'], cues: ['how', 'youd', 'ask'] };

/** B08's arm flight lands on the first word of its phrase; its plait starts ZIP_LEAD before "braided" (b08_braid.py Cues). */
export const ZIP_LEAD = 0.06;

export interface BraidTimes {
  start: number;
  end: number;
  /** Each arm's phrase, word by word: the first word's onset is when the arm lands (B08) and its label draws on. */
  phrase: Record<Arm, Word[]>;
  braided: number;
  into: number;
  one: number;
  answer: number;
  /** The plait starts here (B08's zip0) and its head lands on the hinge on `one`. */
  zip: number;
  beats: number[];
  downbeats: number[];
}

export function braidTimes(vo: VO, audio: AudioData, start: number, end: number): BraidTimes {
  const words = vo.lines.filter((l) => l.scene === 'braid').flatMap((l) => l.words);
  let from = 0;
  /** The next spoken word `w` (normalised) from where the last one was found: her line in order. */
  const next = (w: string): Word => {
    const i = words.findIndex((x, j) => j >= from && norm(x.w) === w);
    if (i < 0) throw new Error(`braid: no spoken "${w}" after word ${from}`);
    from = i + 1;
    return words[i]!;
  };
  const phrase = {} as Record<Arm, Word[]>;
  for (const a of ARMS) phrase[a] = PHRASE[a].map(next);
  const [braided, into, one, answer] = ['braided', 'into', 'one', 'answer'].map((w) => next(w).start) as [number, number, number, number];
  return {
    start, end, phrase, braided, into, one, answer, zip: braided - ZIP_LEAD,
    beats: audio.beats.filter((b) => b >= start - 1e-6 && b <= end + 1e-6),
    downbeats: audio.downbeats.filter((d) => d >= start - 1e-6 && d <= end + 1e-6),
  };
}

/** When an arm lands: her first word for it. */
export const landOf = (T: BraidTimes, a: Arm) => T.phrase[a][0]!.start;

type EaseName = keyof typeof ease;

/** The cue a camera key names (b08_braid.py Cues.cue). */
function cueTime(T: BraidTimes, cue: string): number {
  const c: Record<string, number> = {
    start: T.start, your: landOf(T, 'lexical'), what: landOf(T, 'body'), how: landOf(T, 'cues'),
    braided: T.braided, into: T.into, one: T.one, answer: T.answer, end: T.end,
  };
  const t = c[cue];
  if (t === undefined) throw new Error(`b08_braid.json: no cue '${cue}'`);
  return t;
}

/** B08's camera keys as a CameraRig takes them: positions in the engine's metres, each at its cue's time plus dt. */
export function braidKeys(T: BraidTimes): CamKey[] {
  return SPEC.camera.map((k) => {
    const name = ((k as { ease?: string }).ease ?? 'inOutCubic') as EaseName;
    const fn = ease[name];
    if (typeof fn !== 'function') throw new Error(`b08_braid.json: no ease '${name}'`);
    return {
      t: cueTime(T, k.cue) + ((k as { dt?: number }).dt ?? 0),
      pos: k.eye as V3,
      target: k.look as V3,
      fov: (k as { fov?: number }).fov,
      roll: (k as { roll?: number }).roll,
      ease: (x: number) => (fn as (x: number) => number)(x),
    };
  });
}

// ------------------------------------------------------------------------------------------------ the card's moments

/** The card: it swings open on the rope's end as the head lands, its rows land after it. */
export interface CardTimes {
  /** The swing's start (the head's last instant of flight) and how it settles (spring). */
  swing: number;
  /** The path's row types in from here, fast, while the card swings. */
  path: { at: number; end: number };
  /** The matched row lands on the downbeat of "answer": the three label words slide into it. */
  matched: number;
  /** Then `mode: raw` and `millis: 82`, a 32nd apart. */
  mode: number;
  millis: number;
  /** The footnote types in from here. */
  note: number;
}

export function cardTimes(T: BraidTimes): CardTimes {
  const down = T.downbeats.find((d) => d >= T.answer - 0.1) ?? T.answer;
  const step = 60 / 100 / 8;
  return {
    swing: T.one - 0.04,
    path: { at: T.one + 0.02, end: T.one + 0.2 },
    matched: down,
    mode: down + step,
    millis: down + 2 * step,
    note: T.one + 0.2,
  };
}

// ------------------------------------------------------------------------------------------------ the query

/** The query `what camera did I buy`: typed in from `lead` after the cut at `cps` characters a second. */
export const QUERY_TYPE = { lead: 0.06, cps: 48 } as const;

/** How many of the query's n characters show at t, typed from `at` (braid-type.ts drawQuery). */
export const queryShown = (t: number, at: number, n: number) => clamp(Math.floor((t - at) * QUERY_TYPE.cps) + 1, 0, n);
