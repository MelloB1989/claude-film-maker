// The cue sheet: each shot's cue module (a film's sfx cues, film.ts `sfx`) and the transitions' whooshes, run on the
// film's own data and resolved against its sound palette (films/<id>/data/sfx_palette.json) into
// films/<id>/data/sfx.json, which tools/ renders into the SFX bus (film-sfx). Pure and deterministic: the same data
// gives the same sheet, byte for byte.
import type { AudioData } from '../engine/audio';
import type { Track } from '../engine/track';
import type { TransitionEntry } from '../engine/transition';
import { FPS } from '../engine/util';
import type { SceneSpan, VO } from '../engine/vo';
import type { Cue, CueCtx, Duck, SceneCues } from './cue';
import { transitionCues, type TransitionSounds } from './transitions';

/** films/<id>/data/sfx_palette.json: each sound's prompt, length, alignment and gain (tools/ film-sfx-lib generates from it). */
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
  fps: number;
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

/** What a sheet is built from. */
export interface SheetInputs {
  vo: VO;
  audio: AudioData;
  /** The film's shots (their windows), in order. */
  shots: SceneSpan[];
  /** Cue modules by shot id; a shot without one places no sounds. */
  cues: Record<string, SceneCues>;
  tracks: Record<string, Track>;
  palette: Palette;
  transitions: TransitionEntry[];
  /** The film's length: every cue falls in [0, duration). */
  duration: number;
  /** The sounds a whip and a zoom-through make at their cuts (default whoosh_whip, whoosh_zoom; null: none). */
  transitionSounds?: TransitionSounds;
}

/**
 * The sheet: every shot's cue module and the transitions' cues, each cue's gain the palette's plus its own, sorted by
 * time, ids `<shot>.<nnnn>` in time order within each shot (ducks `<shot>.duck<n>`). Throws, naming the cue, on a
 * sound the palette doesn't have, a time that isn't a finite number, a cue outside the film [0, duration), or a cue
 * module for a shot the film doesn't have. A transition sound the palette lacks is left out.
 */
export function buildSheet(o: SheetInputs): SfxSheet {
  const { vo, audio, tracks, palette, transitions, duration } = o;
  const track = (shot: string) => {
    const t = tracks[shot];
    if (!t) throw new Error(`cue: no track ${shot} (have ${Object.keys(tracks).join(', ') || 'none'})`);
    return t;
  };
  for (const id of Object.keys(o.cues)) if (!o.shots.some((s) => s.id === id)) throw new Error(`cue: a cue module for '${id}', which is not a shot of the film`);
  const groups: { scene: string; items: (Cue | Duck)[] }[] = [];
  for (const span of o.shots) {
    const mod = o.cues[span.id];
    if (!mod) continue;
    const c: CueCtx = { vo, audio, scene: span, track, transitions };
    groups.push({ scene: span.id, items: mod(c) });
  }
  for (const g of transitionCues(transitions, o.transitionSounds)) {
    g.items = g.items.filter((x) => isDuck(x) || paletteSound(palette, x.sound));
    if (g.items.length) groups.push(g);
  }

  const cues: Omit<SheetCue, 'id'>[] = [];
  const ducks: Omit<SheetDuck, 'id'>[] = [];
  for (const { scene, items } of groups) {
    for (const x of items) {
      const name = `${scene} @ ${x.anchor}`;
      if (!Number.isFinite(x.t)) throw new Error(`cue ${name}: its time is not a number (${x.t})`);
      if (!(x.t >= 0 && x.t < duration)) throw new Error(`cue ${name}: ${x.t} is outside the film [0, ${duration})`);
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
    fps: FPS,
    generated_by: 'app/scripts/cues.ts (app/src/sfx/sheet.ts buildSheet)',
    cues: cues.map((c) => ({ id: `${c.scene}.${String((n[c.scene] = (n[c.scene] ?? 0) + 1)).padStart(4, '0')}`, ...c })),
    ducks: ducks.map((d) => ({ id: `${d.scene}.duck${(nd[d.scene] = (nd[d.scene] ?? 0) + 1)}`, ...d })),
  };
}
