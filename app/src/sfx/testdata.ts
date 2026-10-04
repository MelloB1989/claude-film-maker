// The film's real data for the cue sheet (data/vo.json, data/audio.json, data/track/*.json, data/sfx_palette.json and
// the 14 transitions), and a copy with every time shifted, for the test that cues follow the data (Review Focus 2).
// app/scripts/cues.ts builds data/sfx.json from load().
import { AudioData, type AudioJSON } from '../engine/audio';
import { Track, type TrackData } from '../engine/track';
import { specOf, transitionEntries, type TransitionEntry, type TransitionModule } from '../engine/transition';
import { VO } from '../engine/vo';
import type { Palette } from './sheet';
import VO_JSON from '../../../data/vo.json';
import AUDIO_JSON from '../../../data/audio.json';
import PALETTE from '../../../data/sfx_palette.json';
import B01 from '../../../data/track/b01_thread.json';
import B03 from '../../../data/track/b03_reform.json';
import B05 from '../../../data/track/b05_loom.json';
import B08 from '../../../data/track/b08_braid.json';
import B15 from '../../../data/track/b15_weave.json';
import * as anywhereWeave from '../transitions/anywhere-weave';
import * as braidMerkle from '../transitions/braid-merkle';
import * as citeBraid from '../transitions/cite-braid';
import * as connectAnywhere from '../transitions/connect-anywhere';
import * as diffCite from '../transitions/diff-cite';
import * as exHer from '../transitions/ex-her';
import * as graphHonest from '../transitions/graph-honest';
import * as herRepo from '../transitions/her-repo';
import * as honestProof from '../transitions/honest-proof';
import * as loomDiff from '../transitions/loom-diff';
import * as merkleGraph from '../transitions/merkle-graph';
import * as proofConnect from '../transitions/proof-connect';
import * as repoLoom from '../transitions/repo-loom';
import * as threadEx from '../transitions/thread-ex';

/** The film's transitions (transitions/<from>-<to>.ts, the dev probes aside), by file name. */
export const TRANSITIONS: Record<string, TransitionModule> = {
  'anywhere-weave': anywhereWeave, 'braid-merkle': braidMerkle, 'cite-braid': citeBraid, 'connect-anywhere': connectAnywhere,
  'diff-cite': diffCite, 'ex-her': exHer, 'graph-honest': graphHonest, 'her-repo': herRepo, 'honest-proof': honestProof,
  'loom-diff': loomDiff, 'merkle-graph': merkleGraph, 'proof-connect': proofConnect, 'repo-loom': repoLoom, 'thread-ex': threadEx,
} as Record<string, TransitionModule>;

const TRACKS = { b01_thread: B01, b03_reform: B03, b05_loom: B05, b08_braid: B08, b15_weave: B15 } as unknown as Record<string, TrackData>;

export type SheetInputs = [VO, AudioData, Record<string, Track>, Palette, TransitionEntry[]];

/** The cue sheet's inputs from raw data (deep-copied, so a caller may edit them). */
export function inputs(vo: unknown, audio: unknown, tracks: Record<string, TrackData>): SheetInputs {
  const v = new VO(clone(vo) as ConstructorParameters<typeof VO>[0]);
  const a = new AudioData(clone(audio) as AudioJSON);
  const t = Object.fromEntries(Object.entries(tracks).map(([k, d]) => [k, new Track(clone(d))]));
  const specs = Object.keys(TRANSITIONS).sort().map((k) => specOf(TRANSITIONS[k]!, v));
  return [v, a, t, PALETTE as unknown as Palette, transitionEntries(specs, v.scenes, v.words)];
}

/** The real data. */
export const load = (): SheetInputs => inputs(VO_JSON, AUDIO_JSON, TRACKS);

/**
 * The real data with every time s later: the words (and their syllables), the lines, the scene and act windows and the
 * film's end; the beats, downbeats, sections and onsets; and each track's first frame by round(s·30) frames.
 */
export function shifted(s: number): SheetInputs {
  const vo = clone(VO_JSON) as any;
  vo.duration += s;
  for (const l of vo.lines) {
    l.start += s;
    l.end += s;
    for (const w of l.words) {
      w.start += s;
      w.end += s;
      if (w.syl) w.syl = w.syl.map(([a, b]: [number, number]) => [a + s, b + s]);
    }
  }
  for (const x of [...vo.scenes, ...vo.acts]) {
    x.start += s;
    x.end += s;
  }
  const au = clone(AUDIO_JSON) as any;
  au.duration += s;
  au.beats = au.beats.map((b: number) => b + s);
  au.downbeats = au.downbeats.map((b: number) => b + s);
  au.sections = au.sections.map((x: { name: string; start: number; end: number }) => ({ ...x, start: x.start + s, end: x.end + s }));
  for (const k of Object.keys(au.onsets ?? {})) au.onsets[k] = au.onsets[k].map(([t, v]: [number, number]) => [t + s, v]);
  const tr = Object.fromEntries(Object.entries(TRACKS).map(([k, d]) => [k, { ...clone(d), f0: d.f0 + Math.round(s * 30) }]));
  return inputs(vo, au, tr);
}

function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x)) as T;
}
