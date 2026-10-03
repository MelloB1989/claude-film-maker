// The cue sheet (Plan 3 Task 8, spec §5.3): every scene's cue module and the transitions' whooshes, run on the film's
// own data and resolved against the sound palette (data/sfx_palette.json) into data/sfx.json, which tools/ renders into
// the SFX bus (film-sfx). Pure and deterministic: the same data gives the same sheet, byte for byte.
import type { AudioData } from '../engine/audio';
import type { Track } from '../engine/track';
import type { TransitionEntry } from '../engine/transition';
import type { VO } from '../engine/vo';
import type { Cue, CueCtx, Duck, SceneCues } from './cue';
import { transitionCues } from './transitions';
import thread from './scenes/thread';
import ex from './scenes/ex';
import her from './scenes/her';
import repo from './scenes/repo';
import loom from './scenes/loom';
import diff from './scenes/diff';
import cite from './scenes/cite';
import braid from './scenes/braid';
import merkle from './scenes/merkle';
import graph from './scenes/graph';
import honest from './scenes/honest';
import proof from './scenes/proof';
import connect from './scenes/connect';
import anywhere from './scenes/anywhere';
import weave from './scenes/weave';

/** Every scene's cue module, by its id in vo.json. */
export const SCENES: Record<string, SceneCues> = {
  thread, ex, her, repo, loom, diff, cite, braid, merkle, graph, honest, proof, connect, anywhere, weave,
};

/** data/sfx_palette.json: each sound's prompt, length, alignment and gain (tools/ film-sfx-lib generates from it). */
export interface PaletteSound {
  family: string;
  prompt: string;
  duration: number;
  loop: boolean;
  align: 'onset' | 'peak' | 'end' | null;
  gain: number;
  /** How many slices the take is cut into (`<id>_1` … `<id>_<slice>`), 0 for a whole take. */
  slice: number;
}
export interface Palette {
  sounds: Record<string, PaletteSound>;
}

export type SheetCue = Cue & { id: string; scene: string; prompt: string; duration: number; gain: number };
export type SheetDuck = Duck & { id: string; scene: string };

export interface SfxSheet {
  fps: 30;
  generated_by: string;
  cues: SheetCue[];
  ducks: SheetDuck[];
}

/** The palette sound a cue's id names: the sound itself, or the sound a slice id (`flap_3`) is cut from. */
export function paletteSound(palette: Palette, id: string): PaletteSound | null {
  const own = palette.sounds[id];
  if (own) return own;
  const m = /^(.+)_(\d+)$/.exec(id);
  if (!m) return null;
  const base = palette.sounds[m[1]!], k = Number(m[2]);
  return base && base.slice > 0 && k >= 1 && k <= base.slice ? base : null;
}

const isDuck = (x: Cue | Duck): x is Duck => (x as Duck).kind === 'duck';

/**
 * The sheet: every scene module and the transitions' cues, each cue's gain the palette's plus its own, sorted by time,
 * ids `<scene>.<nnnn>` in time order within each scene (ducks `<scene>.duck<n>`). Throws, naming the cue, on a sound the
 * palette doesn't have, a time that isn't a finite number, or a cue outside the film [0, duration).
 */
export function buildSheet(vo: VO, audio: AudioData, tracks: Record<string, Track>, palette: Palette, transitions: TransitionEntry[]): SfxSheet {
  const track = (shot: string) => {
    const t = tracks[shot];
    if (!t) throw new Error(`cue: no track ${shot} (have ${Object.keys(tracks).join(', ')})`);
    return t;
  };
  const groups: { scene: string; items: (Cue | Duck)[] }[] = [];
  for (const span of vo.scenes) {
    const mod = SCENES[span.id];
    if (!mod) throw new Error(`cue: no cue module for scene ${span.id} (sfx/scenes/${span.id}.ts)`);
    const c: CueCtx = { vo, audio, scene: span, track, transitions };
    groups.push({ scene: span.id, items: mod(c) });
  }
  for (const g of transitionCues(transitions)) groups.push(g);

  const cues: Omit<SheetCue, 'id'>[] = [];
  const ducks: Omit<SheetDuck, 'id'>[] = [];
  for (const { scene, items } of groups) {
    for (const x of items) {
      const name = `${scene} @ ${x.anchor}`;
      if (!Number.isFinite(x.t)) throw new Error(`cue ${name}: its time is not a number (${x.t})`);
      if (!(x.t >= 0 && x.t < vo.duration)) throw new Error(`cue ${name}: ${x.t} is outside the film [0, ${vo.duration})`);
      if (isDuck(x)) {
        if (!(x.dur > 0 && Number.isFinite(x.dur))) throw new Error(`cue ${name}: a duck needs a length (dur ${x.dur})`);
        ducks.push({ ...x, scene });
        continue;
      }
      const p = paletteSound(palette, x.sound);
      if (!p) throw new Error(`cue ${name}: no sound "${x.sound}" in the palette`);
      if (x.dur !== undefined && !(x.dur > 0 && Number.isFinite(x.dur))) throw new Error(`cue ${name}: dur must be a positive length (${x.dur})`);
      cues.push({
        sound: x.sound, t: x.t, anchor: x.anchor, gain: p.gain + (x.gain ?? 0), pan: x.pan ?? 0,
        ...(x.dur !== undefined ? { dur: x.dur } : {}),
        scene, prompt: p.prompt, duration: x.dur ?? p.duration,
      });
    }
  }
  // by time; ties keep the order the modules gave (stable sort)
  cues.sort((a, b) => a.t - b.t);
  ducks.sort((a, b) => a.t - b.t);
  const n: Record<string, number> = {};
  const nd: Record<string, number> = {};
  return {
    fps: 30,
    generated_by: 'app/scripts/cues.ts (app/src/sfx/sheet.ts buildSheet)',
    cues: cues.map((c) => ({ id: `${c.scene}.${String((n[c.scene] = (n[c.scene] ?? 0) + 1)).padStart(4, '0')}`, ...c })),
    ducks: ducks.map((d) => ({ id: `${d.scene}.duck${(nd[d.scene] = (nd[d.scene] ?? 0) + 1)}`, ...d })),
  };
}
